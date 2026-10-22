"""Pinned, train-only descriptive audit of five-rater /R/ labels.

Only selected author-train score objects are decoded. Published test score
objects are skipped lexically; no audio or model features are opened.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from speechocean_audit import (ANNOTATED_PHONE, FILES, PHONE, REVISION,
                               exact_fields, mapping, number, pinned_bytes)


HERE = Path(__file__).resolve().parent
METADATA = HERE / "outputs/speechocean762-metadata-v1"
OUTPUT = HERE / "outputs/speechocean-r-label-audit-v1/report.json"
TRAIN_IDS_SHA256 = "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3"
AUTHORITY = {"productionEligible": False, "calibrationEligible": False,
             "learnerFeedbackEligible": False, "clinicalUseEligible": False,
             "clinicalReliabilityEstablished": False}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _skip_space(text: str, position: int) -> int:
    while position < len(text) and text[position] in " \t\r\n":
        position += 1
    return position


def _skip_object_value(text: str, position: int) -> int:
    """Skip a pinned non-train JSON object without decoding any of its fields."""
    require(position < len(text) and text[position] == "{", "Expected score object")
    stack = []
    in_string = escaped = False
    for index in range(position, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            require(bool(stack) and stack[-1] == ("{" if char == "}" else "["),
                    "Malformed score object nesting")
            stack.pop()
            if not stack:
                return index + 1
    raise ValueError("Unterminated score object")


def selected_json_objects(data: bytes, selected_ids: set[str]) -> dict[str, dict]:
    """Decode only named top-level objects from a SHA-pinned score file."""
    text = data.decode("utf-8")

    def unique_pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate selected JSON key")
            result[key] = value
        return result

    decoder = json.JSONDecoder(object_pairs_hook=unique_pairs,
                               parse_constant=lambda value: (_ for _ in ()).throw(
                                   ValueError(f"Invalid selected JSON number: {value}")))
    position = _skip_space(text, 0)
    require(position < len(text) and text[position] == "{", "Expected score root object")
    position += 1
    selected = {}
    seen = set()
    while True:
        position = _skip_space(text, position)
        require(position < len(text), "Unterminated score root object")
        if text[position] == "}":
            position += 1
            break
        key, position = decoder.raw_decode(text, position)
        require(type(key) is str and key not in seen, "Duplicate or invalid score ID")
        seen.add(key)
        position = _skip_space(text, position)
        require(position < len(text) and text[position] == ":", "Missing score value separator")
        position = _skip_space(text, position + 1)
        if key in selected_ids:
            value, position = decoder.raw_decode(text, position)
            require(type(value) is dict, "Selected score must be an object")
            selected[key] = value
        else:
            position = _skip_object_value(text, position)
        position = _skip_space(text, position)
        require(position < len(text) and text[position] in ",}", "Missing score entry separator")
        if text[position] == ",":
            position += 1
            continue
        position += 1
        break
    require(_skip_space(text, position) == len(text), "Trailing score file content")
    require(set(selected) == selected_ids, "Selected author-train IDs missing from score file")
    return selected


def derive_one_r(aggregate: dict, detailed: dict) -> tuple[float, tuple[int, ...]] | None:
    """Reconstruct the five scores at the sole canonical R position, if any."""
    root_fields = {"accuracy", "completeness", "fluency", "prosodic", "total", "text", "words"}
    exact_fields(aggregate, root_fields, "aggregate utterance")
    exact_fields(detailed, root_fields, "per-rater utterance")
    require(aggregate["text"] == detailed["text"] and
            type(aggregate["words"]) is list and type(detailed["words"]) is list and
            len(aggregate["words"]) == len(detailed["words"]),
            "Aggregate and detailed utterance words differ")
    positions = [(word_index, phone_index)
                 for word_index, word in enumerate(aggregate["words"])
                 for phone_index, phone in enumerate(word["phones"])
                 if phone == "R"]
    if len(positions) != 1:
        return None
    word_index, phone_index = positions[0]
    word = aggregate["words"][word_index]
    annotated = detailed["words"][word_index]
    require(type(word["phones"]) is list and all(type(phone) is str and PHONE.fullmatch(phone)
                                                  for phone in word["phones"]),
            "Invalid canonical phone sequence")
    require(type(word["phones-accuracy"]) is list and
            len(word["phones-accuracy"]) == len(word["phones"]) and
            word["text"] == annotated["text"] and
            annotated["ref-phones"] == " ".join(word["phones"]),
            "Canonical word and rater annotation differ")
    require(type(annotated["phones"]) is list and len(annotated["phones"]) == 5,
            "Expected exactly five rater annotations")
    five = []
    for annotation in annotated["phones"]:
        require(type(annotation) is str and annotation, "Invalid rater annotation")
        tokens = annotation.split()
        require(tokens and all(ANNOTATED_PHONE.fullmatch(token) for token in tokens),
                "Malformed rater phone token")
        canonical_tokens = [token for token in tokens if not token.startswith("[")]
        require([token.strip("{}()") for token in canonical_tokens] == word["phones"],
                "Rater phone sequence differs from canonical word")
        token = canonical_tokens[phone_index]
        five.append(0 if token.startswith("(") else 1 if token.startswith("{") else 2)
    aggregate_score = word["phones-accuracy"][phone_index]
    require(number(aggregate_score, 0, 2) and
            abs(float(aggregate_score) - sum(five) / 5) < 1e-9,
            "Published R aggregate differs from five individual raters")
    return float(aggregate_score), tuple(five)


def audit(metadata: Path = METADATA) -> dict:
    train_map = mapping(pinned_bytes(metadata, "train/utt2spk"), r"\d{9}", r"\d{4}")
    require(len(train_map) == 2500 and len(set(train_map.values())) == 125,
            "Unexpected author train split size")
    selected_ids = set(train_map)
    aggregate = selected_json_objects(pinned_bytes(metadata, "resource/scores.json"), selected_ids)
    detailed = selected_json_objects(pinned_bytes(metadata, "resource/scores-detail.json"), selected_ids)
    rows = []
    for utterance in sorted(train_map):
        result = derive_one_r(aggregate[utterance], detailed[utterance])
        if result is not None:
            score, five = result
            rows.append((utterance, train_map[utterance], score, five))
    ids = [row[0] for row in rows]
    require(len(ids) == 766 and
            hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest() == TRAIN_IDS_SHA256,
            "Exactly-one-R train selection differs from prior probe")
    aggregate_counts = Counter(str(score) for _, _, score, _ in rows)
    rater_counts = Counter(score for _, _, _, five in rows for score in five)
    spreads = Counter(max(five) - min(five) for _, _, _, five in rows)
    patterns = Counter(",".join(map(str, sorted(five))) for _, _, _, five in rows)
    unanimous_2 = sum(all(score == 2 for score in five) for _, _, _, five in rows)
    unanimous_1 = sum(all(score == 1 for score in five) for _, _, _, five in rows)
    unanimous_0 = sum(all(score == 0 for score in five) for _, _, _, five in rows)
    mixed = sum(len(set(five)) > 1 for _, _, _, five in rows)
    require(unanimous_0 + unanimous_1 + unanimous_2 + mixed == len(rows),
            "Label agreement categories do not cover selected utterances")
    speaker_counts = Counter(speaker for _, speaker, _, _ in rows)
    return {"schemaVersion": 1, "purpose": "descriptive author-train /R/ label-quality audit",
            "source": {"corpus": "SpeechOcean762", "authorMetadataRevision": REVISION,
                       "pinnedFilesSha256": {name: FILES[name][1] for name in
                                             ("train/utt2spk", "resource/scores.json", "resource/scores-detail.json")},
                       "selectedTrainIdsSha256": TRAIN_IDS_SHA256},
            "partition": "author train only", "testScoreObjectsDecoded": False, "audioOpened": False,
            "selection": "Exactly one canonical R; same 766 train IDs as frozen-feature probes",
            "selectedUtterances": len(rows), "selectedSpeakers": len(speaker_counts),
            "trainSpeakersWithoutSelectedR": len(set(train_map.values()) - set(speaker_counts)),
            "selectedClipsPerSpeaker": {"minimum": min(speaker_counts.values()),
                                        "maximum": max(speaker_counts.values())},
            "aggregateScoreCounts": {str(i / 5): aggregate_counts[str(i / 5)] for i in range(11)},
            "individualRaterScoreCounts": {str(i): rater_counts[i] for i in range(3)},
            "unanimousTwo": unanimous_2,
            "unanimousZero": unanimous_0,
            "unanimousOne": unanimous_1,
            "unanimousZeroOrOne": unanimous_0 + unanimous_1,
            "mixedRatings": mixed,
            "disagreementSpreadCounts": {str(i): spreads[i] for i in range(3)},
            "sortedFiveRaterPatternCounts": dict(sorted(patterns.items())),
            "meanAggregateScore": sum(score for _, _, score, _ in rows) / len(rows),
            "limitations": ["Agreement counts describe these five annotations; they do not establish clinical reliability.",
                            "The labels rate canonical phone positions in English learner speech, not verified produced phones or child speech sound disorders.",
                            "Selection requires exactly one canonical /R/ and excludes other utterances.",
                            "Only author-train score objects were decoded; the published test ratings and audio were not inspected."],
            **AUTHORITY}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"report": str(args.output), "selectedUtterances": report["selectedUtterances"]}))


if __name__ == "__main__":
    main()
