"""Source-locked SpeechOcean762 metadata audit; never a CTC training manifest.

Only the authors' score files and speaker maps are fetched. No audio path is
constructed or opened. The corpus license is CC BY 4.0 per OpenSLR SLR101.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request


REVISION = "613968e3b0b789fc33936fb5eba1973176ba7d11"
SOURCE = f"https://raw.githubusercontent.com/jimbozhang/speechocean762/{REVISION}"
HOMEPAGE = "https://openslr.org/101/"
AUTHORS = "Junbo Zhang, Zhiwen Zhang, Yongqing Wang, Zhiyong Yan, Qiong Song, Yukai Huang, Ke Li, Daniel Povey, Yujun Wang"
LIMIT_BYTES = 30_000_000
# Sizes and SHA-256 were observed from the authors' repository at REVISION.
FILES = {
    "resource/scores.json": (9_755_534, "31c847b8ee29d61d8fe338bcbb1d4c4721425f05481d2144ad57cd19ea1159f8"),
    "resource/scores-detail.json": (19_692_352, "8a90ff40558fe8032d9bfa919429dcae267c0ec3fbdedf1dca30c0515ea989e1"),
    "train/utt2spk": (37_500, "e83546f91fa7444547b8c690ef004ad514eee1f7066d38ec87f7a6c847c84737"),
    "test/utt2spk": (37_500, "061291f397f8c281ff1bf6bf388e875ab9c4cc0de66f37d8559e690af08964be"),
    "train/spk2age": (964, "783be59032da6a140c143fde9c850da1148d48a3aadd27745f2e1b412f981a02"),
    "test/spk2age": (962, "bcc719f23f2352b76f3cec80f12a02f97d775ecfa7b77646be136159caf036d3"),
    "train/spk2gender": (875, "a49aa195c66b0bf5082c0621907c2597abb66231f77a187df2930196cf292232"),
    "test/spk2gender": (875, "4c59b3694169b84a2e69b44632c03d2cfb3ef309f29633a40a729b54d5b77485"),
    "README.md": (12_951, "4f29e91dda24a591bbb7c99b52a9b874779fda6ad4c3346a7430f51e957da3c2"),
}
PHONE = re.compile(r"[A-Z]+[012]?")
ANNOTATED_PHONE = re.compile(r"(?:[A-Z]+[012]?|\{[A-Z]+[012]?\}|\([A-Z]+[012]?\)|\[[A-Z]+[012]?\])")
CTC_FIELDS = {"producedPhones", "targetPhones", "pseudoPhones", "ctcTargets", "labelSource"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_metadata(destination: Path) -> None:
    """Fetch only pinned metadata, with a cumulative 30 MB inbound byte cap."""
    require(not destination.exists(), "Destination already exists")
    require(sum(size for size, _ in FILES.values()) <= LIMIT_BYTES, "Metadata source budget exceeds 30 MB")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="speechocean-metadata-", dir=destination.parent))
    received = 0
    try:
        for name, (expected_size, expected_hash) in FILES.items():
            url = f"{SOURCE}/{name}"
            request = urllib.request.Request(url, headers={"User-Agent": "speech-therapy-metadata-audit"})
            with urllib.request.urlopen(request, timeout=30) as response:
                require(response.url == url, "Metadata source redirected")
                declared = response.headers.get("Content-Length")
                require(declared is None or int(declared) == expected_size, "Metadata Content-Length differs from pin")
                data = response.read(min(expected_size + 1, LIMIT_BYTES - received + 1))
            received += len(data)
            require(received <= LIMIT_BYTES, "Metadata inbound budget exceeded")
            require(len(data) == expected_size and sha256(data) == expected_hash,
                    f"Metadata source pin mismatch: {name}")
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise


def pinned_bytes(root: Path, name: str) -> bytes:
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()), "Metadata path escapes source directory")
    size, expected_hash = FILES[name]
    require(path.is_file() and path.stat().st_size == size, f"Metadata size mismatch: {name}")
    data = path.read_bytes()
    require(sha256(data) == expected_hash, f"Metadata SHA-256 mismatch: {name}")
    return data


def unique_json(data: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(data, object_pairs_hook=pairs,
                       parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {constant}")))
    require(type(value) is dict, "Score file must be a JSON object")
    return value


def mapping(data: bytes, key_pattern: str, value_pattern: str) -> dict[str, str]:
    rows = {}
    for line in data.decode("utf-8").splitlines():
        columns = line.split()
        require(len(columns) == 2, "Invalid speaker map row")
        key, value = columns
        require(re.fullmatch(key_pattern, key) is not None and re.fullmatch(value_pattern, value) is not None,
                "Invalid speaker map value")
        require(key not in rows, "Duplicate speaker map key")
        rows[key] = value
    require(bool(rows), "Empty speaker map")
    return rows


def number(value, lower: float, upper: float) -> bool:
    return type(value) in (int, float) and lower <= value <= upper


def scores(value, lower: float, upper: float) -> bool:
    return type(value) is list and len(value) == 5 and all(number(v, lower, upper) for v in value)


def exact_fields(value, fields: set[str], where: str) -> None:
    require(type(value) is dict, f"{where} must be an object")
    require(not CTC_FIELDS.intersection(value), f"{where} cannot present ratings as CTC training labels")
    require(set(value) == fields, f"Unexpected {where} fields")


def validate_scores(aggregate: dict, detail: dict, splits: dict[str, dict[str, str]],
                    ages: dict[str, dict[str, str]], genders: dict[str, dict[str, str]]) -> dict:
    """Validate actual rating structure without constructing produced-phone targets."""
    utterance_ids = set()
    speaker_sets = {}
    for split in ("train", "test"):
        utterances = splits[split]
        speakers = set(utterances.values())
        require(len(utterances) == 2_500 and len(speakers) == 125, "Unexpected published split size")
        require(not utterance_ids.intersection(utterances), "Utterance appears in both splits")
        require(set(ages[split]) == speakers and set(genders[split]) == speakers,
                "Speaker demographics do not match split")
        require(all(0 < int(age) < 120 for age in ages[split].values()), "Invalid age")
        require(all(gender in {"m", "f"} for gender in genders[split].values()), "Invalid gender")
        utterance_ids.update(utterances)
        speaker_sets[split] = speakers
    require(not speaker_sets["train"].intersection(speaker_sets["test"]), "Speaker appears in both splits")
    require(set(aggregate) == utterance_ids and set(detail) == utterance_ids,
            "Score IDs do not exactly match published speaker maps")

    root_fields = {"accuracy", "completeness", "fluency", "prosodic", "total", "text", "words"}
    word_fields = {"accuracy", "stress", "total", "text", "phones", "phones-accuracy"}
    detail_word_fields = {"accuracy", "stress", "total", "text", "ref-phones", "phones"}
    words = phones = inserted = substitutions = 0
    phone_scores = Counter()
    # The per-position range across five 0/1/2 ratings is descriptive agreement,
    # not a pronunciation-error target or clinical decision threshold.
    rater_score_ranges = Counter({0: 0, 1: 0, 2: 0})
    for utterance in sorted(utterance_ids):
        row, original = aggregate[utterance], detail[utterance]
        exact_fields(row, root_fields, "aggregate utterance")
        exact_fields(original, root_fields, "per-rater utterance")
        require(type(row["text"]) is str and row["text"] and row["text"] == original["text"],
                "Utterance text mismatch")
        for key in ("accuracy", "completeness", "fluency", "prosodic", "total"):
            require(number(row[key], 0, 10), "Aggregate sentence score outside 0–10")
            # Aggregate completeness uses 0–10; the five original rater values use 0–1.
            require(scores(original[key], 0, 1 if key == "completeness" else 10),
                    "Invalid five-rater sentence scores")
        require(type(row["words"]) is list and row["words"] and
                type(original["words"]) is list and len(row["words"]) == len(original["words"]),
                "Word lists differ")
        for word, annotated in zip(row["words"], original["words"]):
            exact_fields(word, word_fields | ({"mispronunciations"} if "mispronunciations" in word else set()),
                         "aggregate word")
            exact_fields(annotated, detail_word_fields, "per-rater word")
            require(type(word["text"]) is str and word["text"] and word["text"] == annotated["text"],
                    "Word text mismatch")
            require(all(number(word[k], 0, 10) for k in ("accuracy", "total")) and
                    word["stress"] in (5, 10), "Invalid aggregate word scores")
            require(scores(annotated["accuracy"], 0, 10) and scores(annotated["total"], 0, 10) and
                    scores(annotated["stress"], 5, 10) and all(v in (5, 10) for v in annotated["stress"]),
                    "Invalid five-rater word scores")
            canonical = word["phones"]
            require(type(canonical) is list and canonical and len(canonical) <= 100 and
                    all(type(p) is str and PHONE.fullmatch(p) for p in canonical),
                    "Invalid canonical phone sequence")
            require(annotated["ref-phones"] == " ".join(canonical),
                    "Canonical phone sequence differs between score files")
            ratings = word["phones-accuracy"]
            require(type(ratings) is list and len(ratings) == len(canonical) and
                    all(number(score, 0, 2) for score in ratings), "Invalid aggregate phone ratings")
            require(type(annotated["phones"]) is list and len(annotated["phones"]) == 5,
                    "Expected five annotated phone strings")
            rater_scores = []
            for text in annotated["phones"]:
                require(type(text) is str and text, "Invalid annotated phone string")
                tokens = text.split()
                require(tokens and all(ANNOTATED_PHONE.fullmatch(token) for token in tokens),
                        "Invalid phone annotation syntax")
                observed = [token for token in tokens if not token.startswith("[")]
                require([token.strip("{}()") for token in observed] == canonical,
                        "Rater annotation differs from canonical phones")
                rater_scores.append([0 if token.startswith("(") else 1 if token.startswith("{") else 2
                                     for token in observed])
                inserted += sum(token.startswith("[") for token in tokens)
            for index, score in enumerate(ratings):
                five_scores = [rater[index] for rater in rater_scores]
                require(abs(score - sum(five_scores) / 5) < 1e-9,
                        "Aggregate phone rating differs from five raters")
                phone_scores[str(score)] += 1
                rater_score_ranges[max(five_scores) - min(five_scores)] += 1
            notes = word.get("mispronunciations", [])
            require(type(notes) is list, "Mispronunciation notes must be a list")
            for error in notes:
                exact_fields(error, {"canonical-phone", "index", "pronounced-phone"}, "mispronunciation")
                index = error["index"]
                require(type(index) is int and 0 <= index < len(canonical), "Invalid mispronunciation index")
                require(error["canonical-phone"] == re.sub(r"[012]$", "", canonical[index]) and
                        type(error["pronounced-phone"]) is str and 0 < len(error["pronounced-phone"]) <= 32,
                        "Invalid mispronunciation description")
                require(ratings[index] < 0.5, "Mispronunciation note lacks low expert rating")
                substitutions += 1
            words += 1
            phones += len(canonical)
    require(sum(rater_score_ranges.values()) == phones and sum(phone_scores.values()) == phones,
            "Phone rating count differs from canonical positions")
    return {"utterances": len(utterance_ids), "speakers": {k: len(v) for k, v in speaker_sets.items()},
            "words": words, "canonicalPhonePositions": phones, "annotatedInsertionsAcrossRaters": inserted,
            "lowScoreMispronunciationNotes": substitutions, "aggregatePhoneScoreCounts": dict(sorted(phone_scores.items(), key=lambda kv: float(kv[0]))),
            "unanimousFiveRaterPhonePositions": rater_score_ranges[0],
            "nonUnanimousFiveRaterPhonePositions": rater_score_ranges[1] + rater_score_ranges[2],
            "fiveRaterScoreRangeCounts": {str(spread): rater_score_ranges[spread] for spread in (0, 1, 2)}}


def audit(root: Path) -> dict:
    files = {name: pinned_bytes(root, name) for name in FILES}
    aggregate = unique_json(files["resource/scores.json"])
    detail = unique_json(files["resource/scores-detail.json"])
    splits = {part: mapping(files[f"{part}/utt2spk"], r"\d{9}", r"\d{4}") for part in ("train", "test")}
    ages = {part: mapping(files[f"{part}/spk2age"], r"\d{4}", r"\d{1,3}") for part in ("train", "test")}
    genders = {part: mapping(files[f"{part}/spk2gender"], r"\d{4}", r"[mf]") for part in ("train", "test")}
    summary = validate_scores(aggregate, detail, splits, ages, genders)
    return {"schemaVersion": 1, "purpose": "public-expert-rating-audit",
            "labelSource": "expert-pronunciation-ratings-of-canonical-phones",
            "source": {"corpus": "speechocean762", "homepage": HOMEPAGE, "license": "CC BY 4.0",
                       "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
                       "licenseEvidence": HOMEPAGE, "attribution": AUTHORS,
                       "repository": "https://github.com/jimbozhang/speechocean762", "revision": REVISION,
                       "modifications": "Original metadata bytes unchanged; this report summarizes and validates them.",
                       "files": {name: {"url": f"{SOURCE}/{name}", "bytes": size, "sha256": digest}
                                 for name, (size, digest) in FILES.items()}},
            "metadataBytes": sum(size for size, _ in FILES.values()),
            "summary": summary,
            "limitations": ["Canonical phones are not produced-phone transcripts or CTC training targets.",
                            "Mispronunciation notes are selective and may contain unknown or distorted phones.",
                            "English L2 pronunciation ratings do not validate child speech sound disorder decisions.",
                            "Audio, model inference, calibration, and clinical feedback were not evaluated."],
            "productionEligible": False, "learnerFeedbackEligible": False, "calibrated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fetch", "audit"))
    parser.add_argument("directory", type=Path, help="Local metadata directory; never an audio archive")
    parser.add_argument("--report", type=Path, help="New path for the research-only JSON audit report")
    args = parser.parse_args()
    try:
        if args.action == "fetch":
            require(args.report is None, "--report applies only to audit")
            fetch_metadata(args.directory)
        else:
            report = audit(args.directory)
            serialized = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
            if args.report:
                with args.report.open("x") as output:
                    output.write(serialized)
            else:
                print(serialized, end="")
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"SpeechOcean metadata audit failed: {exc}\n")
