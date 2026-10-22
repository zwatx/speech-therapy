"""Read-only audit of selective /R/ notes in pinned SpeechOcean author-train data.

The notes describe a subset of very low-rated canonical /R/ positions. They are
not a produced-phone transcript or a clinical speech sound disorder label.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from speechocean_audit import PHONE, REVISION, exact_fields, mapping, number, pinned_bytes
from speechocean_r_label_audit import (METADATA, TRAIN_IDS_SHA256, derive_one_r,
                                      selected_json_objects)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def age_band(age: int) -> str:
    require(type(age) is int and 0 < age < 120, "Invalid speaker age")
    return "child_15_or_younger" if age <= 15 else "adult_19_or_older" if age >= 19 else "age_16_to_18"


def r_note(word: dict, phone_index: int) -> str | None:
    """Validate a selected word's notes and return its sole /R/ note, if any."""
    fields = {"accuracy", "stress", "total", "text", "phones", "phones-accuracy"}
    exact_fields(word, fields | ({"mispronunciations"} if "mispronunciations" in word else set()),
                 "aggregate word")
    phones = word["phones"]
    require(type(phones) is list and phones and
            all(type(phone) is str and PHONE.fullmatch(phone) for phone in phones),
            "Invalid canonical phones")
    require(type(word["phones-accuracy"]) is list and
            len(word["phones-accuracy"]) == len(phones) and
            all(number(score, 0, 2) for score in word["phones-accuracy"]),
            "Invalid phone ratings")
    require(phones[phone_index] == "R", "Selected index is not canonical R")
    notes = word.get("mispronunciations", [])
    require(type(notes) is list, "Mispronunciation notes must be a list")
    found = []
    for note in notes:
        exact_fields(note, {"canonical-phone", "index", "pronounced-phone"}, "mispronunciation")
        index = note["index"]
        require(type(index) is int and 0 <= index < len(phones), "Invalid mispronunciation index")
        require(note["canonical-phone"] == re.sub(r"[012]$", "", phones[index]),
                "Mispronunciation canonical phone differs from indexed phone")
        produced = note["pronounced-phone"]
        require(type(produced) is str and 0 < len(produced) <= 32,
                "Invalid pronounced-phone description")
        if index == phone_index:
            found.append(produced)
    require(len(found) <= 1, "Duplicate R-position mispronunciation notes")
    return found[0] if found else None


def summarize(train: dict[str, str], ages: dict[str, str],
              aggregate: dict[str, dict], detailed: dict[str, dict]) -> dict:
    require(set(train) == set(aggregate) == set(detailed), "Author-train score IDs differ")
    require(set(train.values()) == set(ages), "Author-train age map differs from speakers")
    clip_counts = Counter()
    noted_counts = Counter()
    low_counts = Counter()
    speakers = defaultdict(set)
    noted_speakers = defaultdict(set)
    descriptions = Counter()
    threshold = Counter()
    selected_ids = []
    for utterance in sorted(train):
        selected = derive_one_r(aggregate[utterance], detailed[utterance])
        if selected is None:
            continue
        score, _ = selected
        positions = [(word_index, phone_index)
                     for word_index, word in enumerate(aggregate[utterance]["words"])
                     for phone_index, phone in enumerate(word["phones"]) if phone == "R"]
        require(len(positions) == 1, "Exactly-one-R selection changed")
        word_index, phone_index = positions[0]
        note = r_note(aggregate[utterance]["words"][word_index], phone_index)
        speaker = train[utterance]
        band = age_band(int(ages[speaker]))
        selected_ids.append(utterance)
        clip_counts[band] += 1
        speakers[band].add(speaker)
        has_note = note is not None
        low = score < 0.5
        threshold["both" if has_note and low else
                  "note_only" if has_note else
                  "low_score_only" if low else "neither"] += 1
        if low:
            low_counts[band] += 1
        if has_note:
            noted_counts[band] += 1
            noted_speakers[band].add(speaker)
            descriptions[note] += 1
    bands = ("child_15_or_younger", "adult_19_or_older", "age_16_to_18")
    return {
        "source": "SpeechOcean762 pinned author train", "authorMetadataRevision": REVISION,
        "selection": "Exactly one canonical R in the utterance",
        "selected": {"clips": len(selected_ids), "speakers": len(set().union(*speakers.values())),
                     "byAgeBand": {band: {"clips": clip_counts[band], "speakers": len(speakers[band])}
                                   for band in bands}},
        "rPositionNotes": {"clips": sum(noted_counts.values()),
                           "speakers": len(set().union(*noted_speakers.values())),
                           "byAgeBand": {band: {"clips": noted_counts[band],
                                                "speakers": len(noted_speakers[band])}
                                         for band in bands},
                           "pronouncedPhoneDescriptions": dict(sorted(descriptions.items()))},
        "scoreBelowHalf": {"clips": sum(low_counts.values()),
                           "byAgeBand": {band: low_counts[band] for band in bands}},
        "noteVsScoreBelowHalf": {key: threshold[key] for key in
                                 ("both", "note_only", "low_score_only", "neither")},
        "notePresenceEquivalentToScoreBelowHalf": not threshold["note_only"] and
                                                   not threshold["low_score_only"],
        "testScoreObjectsDecoded": False, "audioOpened": False,
    }


def audit(metadata: Path = METADATA) -> dict:
    train = mapping(pinned_bytes(metadata, "train/utt2spk"), r"\d{9}", r"\d{4}")
    ages = mapping(pinned_bytes(metadata, "train/spk2age"), r"\d{4}", r"\d{1,3}")
    require(len(train) == 2500 and len(set(train.values())) == 125,
            "Unexpected author-train partition size")
    selected_ids = set(train)
    aggregate = selected_json_objects(pinned_bytes(metadata, "resource/scores.json"), selected_ids)
    detailed = selected_json_objects(pinned_bytes(metadata, "resource/scores-detail.json"), selected_ids)
    result = summarize(train, ages, aggregate, detailed)
    require(result["selected"]["clips"] == 766, "Pinned exactly-one-R cohort changed")
    one_r_ids = sorted(utterance for utterance in train
                       if sum(phone == "R" for word in aggregate[utterance]["words"]
                              for phone in word["phones"]) == 1)
    require(hashlib.sha256(("\n".join(one_r_ids) + "\n").encode()).hexdigest() ==
            TRAIN_IDS_SHA256, "Pinned exactly-one-R IDs changed")
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True, allow_nan=False))
