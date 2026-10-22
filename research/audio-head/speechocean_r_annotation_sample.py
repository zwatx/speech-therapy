"""Source-pinned, train-only /R/ annotation-feasibility sample.

The internal manifest holds source identities and ratings. The separate queue
uses private HMAC IDs and contains only the prompt and canonical target position.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tarfile
import tempfile
import wave

from speechocean_audit import FILES, REVISION, mapping, pinned_bytes
from speechocean_r_label_audit import derive_one_r, selected_json_objects


HERE = Path(__file__).resolve().parent
METADATA = HERE / "outputs/speechocean762-metadata-v1"
AUDIO = HERE / "outputs/speechocean762-audio-v1/speechocean762"
ARCHIVE = AUDIO.parent / "speechocean762.tar.gz"
RECIPE = HERE / "experiments/speechocean-r-annotation-sample-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-annotation-sample-v1"
SELECTED_TRAIN_IDS_SHA256 = "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3"
ARCHIVE_SHA256 = "876c34b828c2ebcc35ba2ff1ba5947d50e6b0162fc4a4af91db0942422b3bdd5"
STRATA = ("child.ceiling", "child.belowCeiling", "adult.ceiling", "adult.belowCeiling")
QUEUE_FIELDS = {"reviewerId", "targetPrompt", "targetWord", "wordIndexZeroBased",
                "phoneIndexWithinWordZeroBased"}
AUTHORITY = {"productionEligible": False, "calibrationEligible": False,
             "learnerFeedbackEligible": False, "clinicalUseEligible": False,
             "annotationComplete": False}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def write_json(path: Path, value: dict) -> None:
    require(not path.is_symlink(), "Generated JSON cannot be a symlink")
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    descriptor, temporary = tempfile.mkstemp(prefix=".annotation-", suffix=".tmp",
                                             dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def private_directory(path: Path) -> None:
    """Set permissions after callers have verified any existing generated content."""
    require(path.is_dir() and not path.is_symlink(), "Generated directory is not a real directory")
    path.chmod(0o700)


def require_real_generated_path(path: Path, anchor: Path) -> None:
    """Reject redirects within the generated output tree before writing."""
    require(path.is_relative_to(anchor) and not anchor.is_symlink(),
            "Generated path is outside the real output tree")
    current = path
    while current != anchor:
        require(not current.is_symlink(), "Generated path contains a symlink")
        current = current.parent


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Sample recipe path differs from predeclaration")
    recipe = json.loads(path.read_text())
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-annotation-sample-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("selectedTrainIdsSha256") == SELECTED_TRAIN_IDS_SHA256 and
            recipe.get("sourceArchiveSha256") == ARCHIVE_SHA256 and
            recipe.get("sourceMetadataSha256") == {name: FILES[name][1] for name in
                ("train/utt2spk", "train/spk2age", "resource/scores.json", "resource/scores-detail.json")} and
            recipe.get("strataOrder") == list(STRATA) and
            recipe.get("clipsPerStratum") == 10 and
            recipe.get("distinctSpeakersAcrossSample") is True and
            recipe.get("selectionSeed") == "speechocean-r-annotation-feasibility-2026-09-23-v1" and
            set(recipe.get("reviewerQueueFields", [])) == QUEUE_FIELDS and
            recipe.get("outputDirectory") == "outputs/speechocean-r-annotation-sample-v1" and
            all(recipe.get(key) is False for key in AUTHORITY),
            "Annotation sample recipe differs from predeclaration")
    return recipe


def target_position(row: dict) -> tuple[int, int, str]:
    positions = [(word_index, phone_index, word["text"])
                 for word_index, word in enumerate(row["words"])
                 for phone_index, phone in enumerate(word["phones"])
                 if phone == "R"]
    require(len(positions) == 1, "Expected one canonical R position")
    return positions[0]


def build_candidates(metadata: Path = METADATA) -> list[dict]:
    train = mapping(pinned_bytes(metadata, "train/utt2spk"), r"\d{9}", r"\d{4}")
    ages = mapping(pinned_bytes(metadata, "train/spk2age"), r"\d{4}", r"\d{1,3}")
    require(len(train) == 2500 and len(set(train.values())) == 125 and
            set(ages) == set(train.values()), "Unexpected pinned author train speaker maps")
    train_ids = set(train)
    aggregate = selected_json_objects(pinned_bytes(metadata, "resource/scores.json"), train_ids)
    detail = selected_json_objects(pinned_bytes(metadata, "resource/scores-detail.json"), train_ids)
    candidates = []
    for utterance in sorted(train):
        result = derive_one_r(aggregate[utterance], detail[utterance])
        if result is None:
            continue
        score, five = result
        speaker = train[utterance]
        age = int(ages[speaker])
        require(age <= 15 or age >= 19, "Eligible speaker outside predeclared age bands")
        age_band = "child" if age <= 15 else "adult"
        score_band = "ceiling" if score == 2 else "belowCeiling"
        word_index, phone_index, word = target_position(aggregate[utterance])
        candidates.append({"sourceId": utterance, "speakerId": speaker, "age": age,
                           "stratum": f"{age_band}.{score_band}", "aggregateRScore": score,
                           "fiveRaterScores": list(five), "targetPrompt": aggregate[utterance]["text"],
                           "targetWord": word, "wordIndexZeroBased": word_index,
                           "phoneIndexWithinWordZeroBased": phone_index})
    ids = [row["sourceId"] for row in candidates]
    require(len(ids) == 766 and hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()
            == SELECTED_TRAIN_IDS_SHA256, "Train one-R candidate IDs differ from pinned probe")
    return candidates


def select_sample(candidates: list[dict], recipe: dict) -> list[dict]:
    seed = recipe["selectionSeed"]
    require(len({row["sourceId"] for row in candidates}) == len(candidates), "Duplicate candidate source ID")
    selected = []
    speakers = set()
    for stratum in recipe["strataOrder"]:
        ranked = sorted((row for row in candidates if row["stratum"] == stratum),
                        key=lambda row: hashlib.sha256(
                            f"{seed}:{stratum}:{row['sourceId']}".encode()).hexdigest())
        chosen = 0
        for row in ranked:
            if row["speakerId"] in speakers:
                continue
            selected.append(dict(row))
            speakers.add(row["speakerId"])
            chosen += 1
            if chosen == recipe["clipsPerStratum"]:
                break
        require(chosen == recipe["clipsPerStratum"], f"Insufficient distinct speakers in {stratum}")
    require(len(selected) == 40 and len(speakers) == 40, "Sample is not forty distinct speakers")
    return selected


def verify_selected_wavs(selected: list[dict], archive: Path = ARCHIVE,
                         audio: Path = AUDIO) -> dict[str, str]:
    require(sha256_file(archive) == ARCHIVE_SHA256, "Official audio archive SHA-256 mismatch")
    wav_map = {}
    for line in (audio / "train/wav.scp").read_text().splitlines():
        columns = line.split()
        require(len(columns) == 2 and columns[0] not in wav_map, "Invalid author train WAV map")
        wav_map[columns[0]] = columns[1]
    require(len(wav_map) == 2500, "Unexpected author train WAV map size")
    expected = {}
    for row in selected:
        utterance, speaker = row["sourceId"], row["speakerId"]
        relative = f"WAVE/SPEAKER{speaker}/{utterance}.WAV"
        require(wav_map.get(utterance) == relative, "WAV source identity differs from speaker map")
        path = audio / relative
        require(path.is_file() and path.resolve().is_relative_to((audio / "WAVE").resolve()),
                "Selected WAV missing or outside corpus")
        with wave.open(str(path), "rb") as wav:
            require((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype())
                    == (1, 2, 16000, "NONE") and 1600 <= wav.getnframes() <= 480000,
                    "Selected WAV format outside mono PCM16 16 kHz, 0.1–30 seconds")
        member = "speechocean762/" + relative
        require(member not in expected, "Duplicate selected archive member")
        expected[member] = sha256_file(path)
        row["wavPath"] = str(path)
        row["wavSha256"] = expected[member]
    observed = {}
    with tarfile.open(archive, mode="r|gz") as source:
        for member in source:
            if member.name not in expected:
                continue
            require(member.isfile() and member.name not in observed,
                    "Duplicate or non-file selected archive member")
            stream = source.extractfile(member)
            require(stream is not None, "Selected archive WAV unreadable")
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
            observed[member.name] = digest.hexdigest()
            require(observed[member.name] == expected[member.name],
                    "Extracted selected WAV differs from pinned archive")
    require(set(observed) == set(expected), "Selected WAV missing from pinned archive")
    return expected


def blinded_queue(selected: list[dict], key: bytes) -> dict:
    require(len(key) == 32, "Blinding key must be 256 bits")

    def keyed_digest(prefix: str, utterance: str) -> str:
        return hmac.new(key, f"{prefix}:{utterance}".encode(), hashlib.sha256).hexdigest()

    items = []
    ids = set()
    for row in selected:
        reviewer_id = keyed_digest("reviewer", row["sourceId"])[:16]
        require(reviewer_id not in ids, "Opaque reviewer ID collision")
        ids.add(reviewer_id)
        row["reviewerId"] = reviewer_id
        item = {name: row[name] for name in QUEUE_FIELDS}
        require(set(item) == QUEUE_FIELDS, "Reviewer queue fields differ from blind schema")
        items.append((keyed_digest("queue", row["sourceId"]), item))
    items.sort(key=lambda pair: pair[0])
    return {"schemaVersion": 1, "purpose": "blinded public-speech annotation-feasibility queue",
            "indexBasis": "zero-based word and within-word phone positions",
            "annotationComplete": False,
            "items": [item for _, item in items]}


def run(output: Path = OUTPUT) -> dict:
    recipe = load_recipe()
    require(output.resolve() == OUTPUT.resolve(), "Sample output differs from locked recipe")
    require_real_generated_path(output, HERE)
    candidates = build_candidates()
    selected = select_sample(candidates, recipe)
    wav_hashes = verify_selected_wavs(selected)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_path = output / "internal-manifest.json"
    require(not manifest_path.is_symlink(), "Internal manifest cannot be a symlink")
    old = None
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        require(old.get("recipeSha256") == sha256_file(RECIPE) and
                [row["sourceId"] for row in old.get("clips", [])] ==
                [row["sourceId"] for row in selected],
                "Existing internal manifest differs from locked selection")
        key = bytes.fromhex(old["blindingKeyHex"])
        require(len(key) == 32, "Existing blinding key malformed")
    else:
        key = secrets.token_bytes(32)
    queue = blinded_queue(selected, key)
    manifest = {"schemaVersion": 1, "purpose": "internal source mapping for annotation feasibility",
                "recipeSha256": sha256_file(RECIPE), "blindingKeyHex": key.hex(),
                "sourceArchiveSha256": ARCHIVE_SHA256,
                "sourceMetadataRevision": REVISION,
                "sourceMetadataSha256": recipe["sourceMetadataSha256"],
                "selectedTrainIdsSha256": SELECTED_TRAIN_IDS_SHA256,
                "verifiedWavMembers": len(wav_hashes), "clips": selected,
                **AUTHORITY}
    if old is not None:
        require(old == manifest, "Existing internal manifest differs from verified source")
    write_json(manifest_path, manifest)
    write_json(output / "reviewer-queue.json", queue)
    candidates_by_stratum = Counter(row["stratum"] for row in candidates)
    selected_by_stratum = Counter(row["stratum"] for row in selected)
    report = {"schemaVersion": 1, "purpose": recipe["purpose"],
              "recipeSha256": sha256_file(RECIPE),
              "internalManifestSha256": sha256_file(manifest_path),
              "reviewerQueueSha256": sha256_file(output / "reviewer-queue.json"),
              "sourceArchiveSha256": ARCHIVE_SHA256,
              "selectedTrainIdsSha256": SELECTED_TRAIN_IDS_SHA256,
              "authorPartition": "train", "testRatingsOpened": False,
              "candidateClips": len(candidates), "candidateCountsByStratum": dict(candidates_by_stratum),
              "selectedClips": len(selected), "selectedSpeakers": len({row["speakerId"] for row in selected}),
              "selectedCountsByStratum": dict(selected_by_stratum),
              "verifiedWavMembers": len(wav_hashes),
              "reviewerQueueExcludes": ["source IDs", "speaker IDs", "age", "ratings", "model outputs", "audio bytes"],
              "limitations": ["The age and score strata support an annotation-feasibility check, not a representative sample.",
                              "No SLP annotation has been collected; this does not establish clinical or inter-rater reliability.",
                              "Canonical /R/ position and prompt are reference metadata, not verified produced phones.",
                              "A reviewer with external corpus access may infer source identity from distinctive prompt text; distribute only the queue and controlled audio mapping."],
              **AUTHORITY}
    write_json(output / "report.json", report)
    private_directory(output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({"selectedClips": result["selectedClips"],
                      "selectedCountsByStratum": result["selectedCountsByStratum"]}))
