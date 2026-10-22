"""Author-training-only, single-occurrence consonant rating examples.

The targets are five subjective corpus ratings at a canonical phone position.
They are not produced phones, time intervals, or child pronunciation decisions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import wave

import numpy as np

from speechocean_audit import ANNOTATED_PHONE, FILES, PHONE, mapping, pinned_bytes
from speechocean_r_label_audit import selected_json_objects
from speechocean_r_annotation_sample import (AUDIO, ARCHIVE_SHA256, METADATA,
                                            verify_selected_wavs)

HERE = Path(__file__).resolve().parent
RECIPE_PATH = HERE / "experiments/multiphone-data-v1.json"
OUTPUT = HERE / "outputs/multiphone-20260926"
TARGETS = tuple("B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG ZH".split())
SYMBOLS = ("b", "p", "m", "t", "d", "n", "k", "ɡ", "f", "v", "s", "z",
           "ʃ", "tʃ", "dʒ", "l", "ɹ", "w", "j", "h", "θ", "ð", "ŋ", "ʒ")
SOURCE_FILES = ("train/utt2spk", "train/spk2age", "resource/scores.json",
                "resource/scores-detail.json")
FALSE_FLAGS = {key: False for key in (
    "authorTestObjectsDecoded", "authorTestInferencePerformed", "calibrated",
    "productionEligible", "learnerFeedbackEligible", "clinicalUseEligible",
    "targetTimingVerified", "producedPhoneLabelsAvailable")}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def json_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_recipe(path: Path = RECIPE_PATH) -> dict:
    recipe = json.loads(path.read_text())
    require(recipe.get("schemaVersion") == 1 and recipe.get("authorPartition") == "train" and
            recipe.get("targetPhones") == list(TARGETS) and
            recipe.get("singleOccurrencePerTargetPerClip") is True and
            recipe.get("minimumTargetRows") == 100 and
            recipe.get("minimumTargetSpeakers") == 50 and
            recipe.get("outerFolds") == 5 and recipe.get("splitSeed") == 20260926 and
            recipe.get("innerValidationSpeakerFraction") == 0.2 and
            recipe.get("sourceArchiveSha256") == ARCHIVE_SHA256 and
            recipe.get("sourceMetadataSha256") == {name: FILES[name][1] for name in SOURCE_FILES},
            "Multiphone data recipe differs from the fixed train-only declaration")
    return recipe


def derive_examples(clip_id: str, speaker_id: str, age: int,
                    aggregate: dict, detailed: dict) -> list[dict]:
    require(type(age) is int and (1 <= age <= 15 or 19 <= age < 120),
            "Speaker outside the declared corpus age bands")
    require(aggregate.get("text") == detailed.get("text") and
            isinstance(aggregate.get("text"), str) and bool(aggregate["text"]) and
            isinstance(aggregate.get("words"), list) and
            isinstance(detailed.get("words"), list) and
            len(aggregate["words"]) == len(detailed["words"]),
            "Aggregate and detailed utterance words differ")
    positions = {phone: [] for phone in TARGETS}
    for word_index, (word, detail) in enumerate(zip(aggregate["words"], detailed["words"], strict=True)):
        canonical = word.get("phones")
        require(isinstance(canonical, list) and bool(canonical) and
                all(isinstance(phone, str) and PHONE.fullmatch(phone) for phone in canonical) and
                word.get("text") == detail.get("text") and
                detail.get("ref-phones") == " ".join(canonical) and
                isinstance(word.get("phones-accuracy"), list) and
                len(word["phones-accuracy"]) == len(canonical) and
                isinstance(detail.get("phones"), list) and len(detail["phones"]) == 5,
                "Canonical word or five-rater phone structure differs")
        rater_scores = []
        for annotation in detail["phones"]:
            require(isinstance(annotation, str) and bool(annotation), "Invalid annotation string")
            tokens = annotation.split()
            require(all(ANNOTATED_PHONE.fullmatch(token) for token in tokens), "Malformed phone annotation")
            observed = [token for token in tokens if not token.startswith("[")]
            require([token.strip("{}()") for token in observed] == canonical,
                    "Rater sequence differs from canonical phone positions")
            rater_scores.append([0 if token.startswith("(") else 1 if token.startswith("{") else 2
                                 for token in observed])
        for phone_index, phone in enumerate(canonical):
            five = [scores[phone_index] for scores in rater_scores]
            published = word["phones-accuracy"][phone_index]
            require(type(published) in (int, float) and 0 <= published <= 2 and
                    abs(sum(five) / 5 - published) <= 1e-9,
                    "Published aggregate differs from the five individual ratings")
            if phone in positions:
                counts = [five.count(value) for value in range(3)]
                positions[phone].append({"targetWord": word["text"], "wordIndex": word_index,
                                         "phoneIndex": phone_index, "raterCounts": counts})
    return [{"id": f"{clip_id}:{phone}", "clipId": clip_id, "speakerId": speaker_id,
             "age": age, "ageBand": "child" if age <= 15 else "adult",
             "targetId": target_id, "targetPhone": phone, **positions[phone][0]}
            for target_id, phone in enumerate(TARGETS) if len(positions[phone]) == 1]


def target_summary(rows: list[dict], recipe: dict) -> list[dict]:
    result = []
    for target_id, phone in enumerate(TARGETS):
        selected = [row for row in rows if row["targetId"] == target_id]
        speakers = len({row["speakerId"] for row in selected})
        eligible = len(selected) >= recipe["minimumTargetRows"] and speakers >= recipe["minimumTargetSpeakers"]
        result.append({"id": target_id, "phone": phone, "symbol": SYMBOLS[target_id],
                       "rows": len(selected), "speakers": speakers,
                       "words": len({row["targetWord"] for row in selected}),
                       "raterCounts": [sum(row["raterCounts"][i] for row in selected) for i in range(3)],
                       "mixedRatingRows": sum(sum(value > 0 for value in row["raterCounts"]) > 1 for row in selected),
                       "age2To12Rows": sum(2 <= row["age"] <= 12 for row in selected),
                       "trainingEligible": eligible, "primaryMetricEligible": eligible,
                       "exclusionReason": None if eligible else "Below 100 rows or 50 speakers"})
    return result


def load_training_cohort(recipe: dict | None = None) -> dict:
    recipe = load_recipe() if recipe is None else recipe
    require(recipe == load_recipe(), "Cohort settings differ from the locked data recipe")
    train = mapping(pinned_bytes(METADATA, "train/utt2spk"), r"\d{9}", r"\d{4}")
    ages = mapping(pinned_bytes(METADATA, "train/spk2age"), r"\d{4}", r"\d{1,3}")
    require(len(train) == 2500 and len(set(train.values())) == 125 and
            set(ages) == set(train.values()), "Published author-training cohort changed")
    aggregate = selected_json_objects(pinned_bytes(METADATA, "resource/scores.json"), set(train))
    detailed = selected_json_objects(pinned_bytes(METADATA, "resource/scores-detail.json"), set(train))
    rows = [row for clip_id in sorted(train)
            for row in derive_examples(clip_id, train[clip_id], int(ages[train[clip_id]]),
                                       aggregate[clip_id], detailed[clip_id])]
    clip_ids = sorted({row["clipId"] for row in rows})
    source_rows = [{"sourceId": clip_id, "speakerId": train[clip_id]} for clip_id in clip_ids]
    # Existing verifier binds only selected train WAVs to the pinned archive.
    verify_selected_wavs(source_rows)
    clips = []
    for row in source_rows:
        path = Path(row["wavPath"])
        require(sha256_file(path) == row["wavSha256"], "Public training WAV changed during read")
        with wave.open(str(path), "rb") as wav:
            count = wav.getnframes()
            samples = np.frombuffer(wav.readframes(count), dtype="<i2").astype(np.float64) / 32768.0
        require(len(samples) == count and np.isfinite(samples).all(), "Truncated public training WAV")
        clip_id = row["sourceId"]
        age = int(ages[row["speakerId"]])
        clips.append({"id": clip_id, "speakerId": row["speakerId"], "audioPath": str(path),
                      "audioSha256": row["wavSha256"], "age": age,
                      "ageBand": "child" if age <= 15 else "adult", "sampleCount": count,
                      "durationSeconds": count / 16000, "rms": float(np.sqrt(np.mean(samples ** 2))),
                      "peak": float(np.max(np.abs(samples))), "text": aggregate[clip_id]["text"],
                      "canonicalPhoneCount": sum(len(word["phones"]) for word in aggregate[clip_id]["words"])})
    summaries = target_summary(rows, recipe)
    eligible = {target["id"] for target in summaries if target["trainingEligible"]}
    clip_indices = {clip_id: index for index, clip_id in enumerate(clip_ids)}
    for row in rows:
        row["clipIndex"] = clip_indices[row["clipId"]]
        row["trainingEligible"] = row["targetId"] in eligible
    require(len(rows) == 14843 and len(clips) == 2495 and len(eligible) == 23,
            "Pinned target cohort counts differ from pre-training audit")
    return {"schemaVersion": 1, "experiment": recipe["experiment"], "recipe": recipe,
            "authorPartition": "train", "targetPhones": list(TARGETS),
            "eligibleTargetIds": sorted(eligible), "targets": summaries,
            "clips": clips, "rows": rows,
            "labelSummary": {"rawRows": len(rows), "eligibleRows": sum(row["trainingEligible"] for row in rows),
                             "clips": len(clips), "speakers": len(set(train.values())),
                             "excludedAuthorTrainClipsWithoutUniqueTarget": len(train) - len(clips)},
            "provenance": {"sourceArchiveSha256": ARCHIVE_SHA256,
                           "sourceMetadataSha256": {name: FILES[name][1] for name in SOURCE_FILES},
                           "sourceCodeSha256": {name: sha256_file(HERE / name) for name in
                                                ("multiphone_data.py", "speechocean_audit.py",
                                                 "speechocean_r_label_audit.py", "speechocean_r_annotation_sample.py")},
                           "audioPathBasis": "Absolute paths inside the verified local public SpeechOcean WAVE root",
                           "selectedClipIdsSha256": json_sha(clip_ids)},
            "limitations": ["Canonical-position subjective ratings; no verified production transcription or timing.",
                            "Corpus ages 6–37; no age 2–5 data or established child SSD cohort.",
                            "All folds are exploratory within previously used author-training data.",
                            "Related target rows share waveforms; all remain grouped by speaker and clip.",
                            "ZH stays visible in the manifest but is excluded from primary fitting and metrics."],
            **FALSE_FLAGS}


def build_splits(cohort: dict, recipe: dict | None = None) -> dict:
    recipe = cohort["recipe"] if recipe is None else recipe
    require(recipe == cohort["recipe"] and cohort.get("authorPartition") == "train",
            "Split recipe or author partition differs from cohort")
    rows, clips = cohort["rows"], cohort["clips"]
    require(len({clip["id"] for clip in clips}) == len(clips) and
            len({row["id"] for row in rows}) == len(rows) and
            len({(row["clipIndex"], row["targetId"]) for row in rows}) == len(rows),
            "Duplicate clip, row, or target occurrence")
    for row in rows:
        index = row["clipIndex"]
        require(type(index) is int and 0 <= index < len(clips) and
                row["clipId"] == clips[index]["id"] and
                row["speakerId"] == clips[index]["speakerId"] and
                row["trainingEligible"] == (row["targetId"] in cohort["eligibleTargetIds"]) and
                len(row["raterCounts"]) == 3 and
                all(type(value) is int and value >= 0 for value in row["raterCounts"]) and
                sum(row["raterCounts"]) == 5,
                "Row identity, speaker, eligibility, or five-rater counts differ from its clip")
    speakers = {clip["speakerId"] for clip in clips}
    seed, folds = recipe["splitSeed"], recipe["outerFolds"]
    rank = lambda scope, value: hashlib.sha256(f"{seed}:{scope}:{value}".encode()).hexdigest()
    ordered = sorted(speakers, key=lambda speaker: rank("outer", speaker))
    require(len(ordered) >= 2 * folds, "Insufficient speakers for grouped folds")
    assignments = {speaker: index % folds for index, speaker in enumerate(ordered)}
    partitions = []
    for fold in range(folds):
        outer_fit = {speaker for speaker in speakers if assignments[speaker] != fold}
        outer_holdout = speakers - outer_fit
        inner_order = sorted(outer_fit, key=lambda speaker: rank(f"inner:{fold}", speaker))
        count = max(1, round(len(inner_order) * recipe["innerValidationSpeakerFraction"]))
        inner_validation = set(inner_order[:count])
        inner_fit = outer_fit - inner_validation
        require(bool(inner_fit), "Inner validation consumes the entire fit")
        groups = {"outerFit": outer_fit, "outerHoldout": outer_holdout,
                  "innerFit": inner_fit, "innerValidation": inner_validation}
        part = {"fold": fold, "lexicalOverlap": {}}
        for name, group in groups.items():
            part[name + "Speakers"] = sorted(group)
            part[name + "Clips"] = [i for i, clip in enumerate(clips) if clip["speakerId"] in group]
            part[name + "Rows"] = [i for i, row in enumerate(rows)
                                    if row["speakerId"] in group and row["trainingEligible"]]
            part[name + "TargetRaterCounts"] = {
                TARGETS[target]: [sum(rows[i]["raterCounts"][score] for i in part[name + "Rows"]
                                     if rows[i]["targetId"] == target) for score in range(3)]
                for target in cohort["eligibleTargetIds"]}
        for fit, holdout in (("outerFit", "outerHoldout"), ("innerFit", "innerValidation")):
            fit_indices, held_indices = part[fit + "Clips"], part[holdout + "Clips"]
            require({clips[i]["audioSha256"] for i in fit_indices}.isdisjoint(
                {clips[i]["audioSha256"] for i in held_indices}), "Duplicate WAV crosses a speaker split")
            part["lexicalOverlap"]["outer" if fit == "outerFit" else "inner"] = {
                "exactPromptTexts": len({clips[i]["text"] for i in fit_indices} &
                                        {clips[i]["text"] for i in held_indices}),
                "targetWordTypes": len({rows[i]["targetWord"] for i in part[fit + "Rows"]} &
                                       {rows[i]["targetWord"] for i in part[holdout + "Rows"]})}
        partitions.append(part)
    require(sorted(i for part in partitions for i in part["outerHoldoutRows"]) ==
            [i for i, row in enumerate(rows) if row["trainingEligible"]],
            "Eligible rows must receive exactly one outer holdout prediction")
    return {"schemaVersion": 1, "experiment": recipe["experiment"], "splitSeed": seed,
            "cohortCanonicalSha256": json_sha(cohort), "speakerAssignments": assignments,
            "folds": partitions, "authorPartition": "train",
            "selectionRule": "Settings and stopping use only inner validation; outer holdouts evaluate the locked matrix once",
            "lexicalPosture": "Speaker-disjoint; target words may recur. Not a word-disjoint result.",
            "finalEvaluationStatus": "A genuinely independent final cohort is reserved for future collection/access; historical author test remains unused here",
            **FALSE_FLAGS}


def persist(output: Path = OUTPUT) -> tuple[dict, dict]:
    require(not (output / "cohort.json").exists() and not (output / "splits.json").exists(),
            "Cohort or split artifact already exists; never overwrite a locked manifest")
    cohort = load_training_cohort()
    splits = build_splits(cohort)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, value in (("cohort.json", cohort), ("splits.json", splits)):
        descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
    return cohort, splits


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    cohort, splits = persist(args.output)
    print(json.dumps({"output": str(args.output), **cohort["labelSummary"],
                      "excludedTargets": [row["phone"] for row in cohort["targets"] if not row["trainingEligible"]],
                      "outerFolds": len(splits["folds"])}, indent=2))
