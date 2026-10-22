"""Bounded public CMU Arctic import with explicit automatic-alignment provenance."""
import argparse
from pathlib import Path
import re
import urllib.parse
import urllib.request

from data import AUTHORITY, BLANK, SAMPLE_RATE, digest, load_manifest, load_pcm, read_json, write_json
from labels import ARCTIC_PHONES, parse_alignment
from arctic_profiles import LICENSE_HASHES, PROFILES, validate_profile_selection

BASE = "http://festvox.org/cmu_arctic/cmu_arctic/"


class Downloader:
    def __init__(self, limit_bytes=25_000_000):
        self.limit, self.downloaded = limit_bytes, 0

    def fetch(self, speaker, relative, max_bytes, expected_hash=None):
        if speaker not in LICENSE_HASHES or not re.fullmatch(r"(?:COPYING|README|(?:wav|lab)/arctic_a\d{4}\.(?:wav|lab))", relative):
            raise ValueError("Unapproved corpus source path")
        url = f"{BASE}cmu_us_{speaker}_arctic/{relative}"
        if self.downloaded + max_bytes > self.limit:
            raise ValueError("Corpus download budget would be exceeded")
        with urllib.request.urlopen(url, timeout=20) as response:
            if urllib.parse.urlparse(response.url).hostname not in {"festvox.org", "www.festvox.org"}:
                raise ValueError("Corpus response redirected outside the official host")
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > max_bytes:
                raise ValueError("Corpus file exceeds size limit")
            data = response.read(max_bytes + 1)
        self.downloaded += len(data)
        if len(data) > max_bytes or self.downloaded > self.limit:
            raise ValueError("Corpus file or total download exceeds size limit")
        sha = digest(data)
        if expected_hash is not None and sha != expected_hash:
            raise ValueError("Corpus source SHA-256 mismatch")
        return data, {"url": url, "sha256": sha, "bytes": len(data)}


def import_corpus(output: Path, source_lock: Path | None = None,
                  profile: str = "single-speaker-v1", holdout_lock: Path | None = None) -> Path:
    if output.exists():
        raise ValueError("Output already exists; use a new corpus directory")
    replay = read_json(source_lock) if source_lock else None
    if replay and (replay.get("corpus") != "cmu-arctic-0.95" or replay.get("labelSource") != "automatic-phone-alignment"):
        raise ValueError("Unsupported corpus source lock")
    if replay:
        profile = replay.get("profile", "single-speaker-v1")
        validate_profile_selection(replay["selected"], profile)
    if profile not in PROFILES:
        raise ValueError("Unsupported corpus profile")
    holdout = read_json(holdout_lock) if holdout_lock else None
    if holdout:
        if holdout.get("corpus") != "cmu-arctic-0.95" or holdout.get("labelSource") != "automatic-phone-alignment":
            raise ValueError("Invalid held-out corpus lock")
        validate_profile_selection(holdout["selected"], holdout.get("profile", "single-speaker-v1"))
    if profile == "four-speaker-v1" and not replay and not holdout:
        raise ValueError("Expanded profile requires the previously recorded holdout lock")
    output.mkdir(parents=True)
    limit = 100_000_000 if profile == "four-speaker-v1" else 25_000_000
    downloader = Downloader(limit)
    heldout_digest = digest(holdout_lock.read_bytes()) if holdout_lock else (replay or {}).get("heldoutSourceLockSha256")
    write_json(output / "import-plan.json", {"profile": profile, "selection": PROFILES[profile],
                 "downloadLimitBytes": limit, "heldoutSourceLockSha256": heldout_digest,
                 "heldoutStatus": "previously-inspected-engineering-holdout" if profile == "four-speaker-v1" else "engineering-only"})
    files, selected, rejected, items = {}, [], [], []
    for speaker in PROFILES[profile]:
        # Expansion pins both held-out speakers to their original selected bytes and labels.
        reference = replay or (holdout if speaker in {"rms", "slt"} else None)
        # Preserve the complete per-speaker license and README; do not relicense the audio.
        directory = output / speaker
        directory.mkdir()
        for name in ("COPYING", "README"):
            local = f"{speaker}/{name}"
            expected = LICENSE_HASHES[speaker] if name == "COPYING" else None
            if reference:
                expected = reference["files"][local]["sha256"]
                if name == "COPYING" and expected != LICENSE_HASHES[speaker]:
                    raise ValueError("Source lock changes the reviewed license")
            data, record = downloader.fetch(speaker, name, 30_000, expected)
            (output / local).write_bytes(data)
            files[local] = record
        split, start, stop, wanted = PROFILES[profile][speaker]
        candidates = [i["utterance"] for i in reference["selected"] if i["speaker"] == speaker] if reference else [f"arctic_a{i:04d}" for i in range(start, stop + 1)]
        accepted = 0
        for utterance in candidates:
            if accepted == wanted:
                break
            if not re.fullmatch(r"arctic_a\d{4}", utterance) or not start <= int(utterance[-4:]) <= stop:
                raise ValueError("Source lock changes the predefined prompt split")
            paths = {}
            for kind, extension, maximum in [("wav", "wav", 400_000), ("lab", "lab", 20_000)]:
                relative = f"{kind}/{utterance}.{extension}"
                local = f"{speaker}/{utterance}.{extension}"
                expected = reference["files"][local]["sha256"] if reference else None
                data, record = downloader.fetch(speaker, relative, maximum, expected)
                paths[extension] = (local, data, record)
                (output / local).write_bytes(data)
            try:
                samples = load_pcm(output / paths["wav"][0])
                phones = parse_alignment(paths["lab"][1], len(samples) / SAMPLE_RATE)
            except ValueError as exc:
                if reference:
                    raise ValueError("Locked corpus item no longer passes validation") from exc
                rejected.append({"speaker": speaker, "utterance": utterance, "reason": str(exc)})
                for local, _, _ in paths.values():
                    (output / local).unlink()
                continue
            for local, _, record in paths.values():
                files[local] = record
            selected.append({"speaker": speaker, "utterance": utterance, "split": split})
            items.append({"id": f"cmu-{speaker}-{utterance}", "audioPath": paths["wav"][0],
                          "audioSha256": paths["wav"][2]["sha256"], "alignmentPath": paths["lab"][0],
                          "alignmentSha256": paths["lab"][2]["sha256"],
                          "speakerHash": digest(f"cmu-arctic-speaker:{speaker}".encode()), "householdHash": None,
                          "split": split, "pseudoPhones": phones,
                          "provenance": f"CMU Arctic 0.95; {paths['lab'][2]['url']}; automatic Sphinx/FestVox alignment; not human-produced-phone truth"})
            accepted += 1
        if accepted != wanted:
            raise ValueError(f"Insufficient acceptable source clips for {speaker}: {accepted}/{wanted}")
    lock = {"schemaVersion": 1, "corpus": "cmu-arctic-0.95", "labelSource": "automatic-phone-alignment",
            "sourceHomepage": "http://festvox.org/cmu_arctic/", "sourcePaper": "https://www.cs.cmu.edu/~awb/papers/ssw5/arctic.pdf",
            "transport": "official HTTP source; hashes pin observed bytes, not authenticated transport",
            "profile": profile, "heldoutSourceLockSha256": heldout_digest,
            "selectionPolicy": "first valid <=5s clips in the named predeclared speaker/prompt profile; replay exact locked holdouts",
            "files": files, "selected": selected}
    write_json(output / "source-lock.json", lock)
    write_json(output / "import-report.json", {"downloadedBytes": downloader.downloaded, "accepted": len(items),
                                               "rejected": rejected, "replayedSourceLock": source_lock is not None,
                                               "sourceLockSha256": digest((output / 'source-lock.json').read_bytes()), **AUTHORITY})
    write_json(output / "manifest.json", {"schemaVersion": 2, "purpose": "public-speech-engineering",
               "labelSource": "automatic-phone-alignment", "splitIdentityBasis": "speaker-disjoint-households-unknown",
               "sourceLockSha256": digest((output / "source-lock.json").read_bytes()),
               "vocabulary": [BLANK, *ARCTIC_PHONES], "items": items, **AUTHORITY})
    (output / "MODIFICATIONS.txt").write_text(
        "CMU Arctic 0.95 by John Kominek and Alan W Black, Carnegie Mellon University.\n"
        "Original WAV and automatic LAB bytes are unchanged. This engineering subset selects\n"
        "clips, partitions by speaker and prompt range, and adds manifests/phone sequences.\n"
        "Labels remain automatic alignments, not verified speech productions. Full original\n"
        "COPYING and README notices are retained for every speaker. No synthesis or voice cloning.\n")
    load_manifest(output / "manifest.json")
    return output / "manifest.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-lock", type=Path, help="Replay an earlier selection and require its exact source hashes")
    parser.add_argument("--profile", choices=list(PROFILES), default="single-speaker-v1")
    parser.add_argument("--holdout-lock", type=Path, help="Preserve exact prior calibration/test files while expanding training")
    arguments = parser.parse_args()
    try:
        print(import_corpus(arguments.output, arguments.source_lock, arguments.profile, arguments.holdout_lock))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Corpus import failed: {exc}\n")
