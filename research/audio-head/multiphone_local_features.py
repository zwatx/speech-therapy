"""Estimated canonical target intervals and local acoustic research features.

Canonical mappings and forced CTC occupancy are hypotheses, never produced-phone
or timing labels. No ratings determine alignment, inclusion, or feature values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time

import numpy as np

from alignment_pilot import viterbi_ctc
from encoders import WavLMEncoder
from multiphone_data import json_sha
from speechocean_audit import pinned_bytes
from speechocean_r_label_audit import selected_json_objects
from speechocean_r_probe import AUDIO, METADATA

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "experiments/multiphone-local-features-v1.json"
BASE = HERE / "outputs/multiphone-20260926"
VOCAB = HERE.parent.parent / ("node_modules/.pnpm/@huggingface+transformers@4.2.0/node_modules/"
                              "@huggingface/transformers/.cache/onnx-community/"
                              "wav2vec2-lv-60-espeak-cv-ft-ONNX/c69750f5043e5e1f8a71ab95dd3b98338c280c92/vocab.json")
VOCAB_SHA = "d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0"
SCALAR_NAMES = ["targetMeanLogPosterior", "targetMeanPosterior", "targetMaxPosterior",
                "meanLogMarginVsBestOtherPhone", "meanLogFractionOfNonblankMass",
                "targetArgmaxFraction", "meanBlankPosterior", "meanSpecialPosterior",
                "meanFullVocabularyEntropy", "ctcTargetOccupancySeconds", "occupiedFrames",
                "utteranceViterbiLogProbabilityPerFrame", "greedyCanonicalTokenErrorRate"]
FALSE_FLAGS = {key: False for key in ("frameTimesValidated", "producedPhoneLabelsAvailable",
                                      "authorTestInferencePerformed", "clinicalUseEligible",
                                      "learnerFeedbackEligible")}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    with path.open("x") as output:
        path.chmod(0o600)
        output.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def capture_digests(paths: dict[str, Path]) -> dict[str, str]:
    return {name: digest(path) for name, path in paths.items()}


def require_unchanged(paths: dict[str, Path], expected: dict[str, str]) -> None:
    require(capture_digests(paths) == expected, "Source, recipe, input or cache index changed during extraction")


def validate_manifest_rows(manifest: dict, cohort: dict) -> None:
    """Bind every exported target to its original immutable cohort position."""
    require(manifest["authorPartition"] == cohort["authorPartition"] == "train", "Expected author training")
    seen_clips, seen_rows = set(), set()
    for clip in manifest["clips"]:
        index = clip["clipIndex"]
        require(type(index) is int and 0 <= index < len(cohort["clips"]) and index not in seen_clips,
                "Invalid or duplicate manifest clip index")
        source = cohort["clips"][index]
        require(all(clip[key] == source[key] for key in
                    ("id", "speakerId", "audioPath", "audioSha256", "sampleCount")),
                "Manifest clip differs from its original cohort row")
        phones = clip["canonicalPhones"]
        require(isinstance(phones, list) and len(phones) == source["canonicalPhoneCount"],
                "Canonical prompt length differs from original cohort")
        seen_clips.add(index)
        for target in clip["targetRows"]:
            row_index = target["rowIndex"]
            require(type(row_index) is int and 0 <= row_index < len(cohort["rows"]) and row_index not in seen_rows,
                    "Invalid or duplicate target row index")
            row = cohort["rows"][row_index]
            require(row["trainingEligible"] is True and row["clipIndex"] == index and row["clipId"] == clip["id"] and
                    target["rowId"] == row["id"] and all(target[key] == row[key] for key in
                        ("targetId", "targetPhone", "wordIndex", "phoneIndex")),
                    "Manifest target differs from its original cohort row")
            position = target["canonicalIndex"]
            require(type(position) is int and 0 <= position < len(phones) and
                    phones[position] == row["targetPhone"] and phones.count(row["targetPhone"]) == 1,
                    "Canonical target position differs from its original unique target")
            seen_rows.add(row_index)
    expected = {i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"] and row["clipIndex"] in seen_clips}
    require(seen_rows == expected, "Manifest omits eligible targets from selected clips")


def convolution_frames(samples: int, recipe: dict) -> int:
    for kernel, stride in zip(recipe["convKernel"], recipe["convStride"], strict=True):
        samples = (samples - kernel) // stride + 1
    return samples


def canonical_mapping(phones: list[str], vocabulary: dict, recipe: dict) -> tuple[list[str], list[int], list[str]]:
    require(bool(phones) and all(re.fullmatch(r"[A-Z]+[012]?", phone) for phone in phones),
            "Expected canonical ARPAbet symbols")
    mapped, flags = [], set()
    for index, phone in enumerate(phones):
        base = re.sub(r"[012]$", "", phone)
        token = recipe["stressOverrides"].get(phone, recipe["consonants"].get(base, recipe["vowels"].get(base)))
        require(token is not None and token in vocabulary and vocabulary[token] > 3,
                f"Canonical phone has no declared non-special CTC mapping: {phone}")
        mapped.append(token)
        if base in recipe["vowels"]:
            flags.add("provisional-vowel-length-dialect-stress-mapping")
        if base in ("T", "D"):
            flags.add("canonical-t-d-does-not-model-flap-variants")
        if base == "L":
            flags.add("canonical-l-does-not-model-dark-or-syllabic-variants")
        if base == "ER":
            flags.add("er-stress-collapsed-to-rhotic-schwa")
        if base == "R" and index and re.sub(r"[012]$", "", phones[index - 1]) in recipe["vowels"]:
            flags.add("postvocalic-r-may-compete-with-merged-rhotic-tokens")
    return mapped, [vocabulary[token] for token in mapped], sorted(flags)


def geometry_selection(clips: list[dict], indices: list[int]) -> list[int]:
    require(len(indices) >= 3 and len(set(indices)) == len(indices), "Need at least three unique fit clips")
    ordered = sorted(indices, key=lambda index: (clips[index]["sampleCount"], clips[index]["id"]))
    return [ordered[0], ordered[len(ordered) // 2], ordered[-1]]


def prepare_manifest(cohort_path: Path, splits_path: Path, output: Path, vocabulary_path: Path = VOCAB,
                     scope: str = "preflight") -> dict:
    recipe = json.loads(RECIPE.read_text())
    require(digest(cohort_path) == recipe["cohortSha256"] and digest(splits_path) == recipe["splitsSha256"],
            "Study inputs differ from the fixed local-feature recipe")
    require(digest(vocabulary_path) == VOCAB_SHA, "Vocabulary pin differs")
    cohort, splits = json.loads(cohort_path.read_text()), json.loads(splits_path.read_text())
    require(splits["cohortCanonicalSha256"] == json_sha(cohort) and
            cohort["authorPartition"] == splits["authorPartition"] == "train", "Cohort/split binding differs")
    vocabulary = json.loads(vocabulary_path.read_text())
    require(len(vocabulary) == 392 and vocabulary["<pad>"] == 0, "Expected full pinned CTC vocabulary")
    fold = splits["folds"][0]
    require(scope in ("preflight", "author-train"), "Unknown manifest scope")
    eligible_rows = [i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"]]
    indices = (geometry_selection(cohort["clips"], fold["innerFitClips"]) if scope == "preflight"
               else sorted({cohort["rows"][i]["clipIndex"] for i in eligible_rows}))
    selected_ids = {cohort["clips"][i]["id"] for i in indices}
    # Only explicitly selected author-train prompt objects are decoded; no test objects.
    scores = selected_json_objects(pinned_bytes(METADATA, "resource/scores.json"), selected_ids)
    train_bytes = pinned_bytes(METADATA, "train/utt2spk")
    train_map = dict(line.split() for line in train_bytes.decode().splitlines())
    selected_rows = set(fold["innerFitRows"] if scope == "preflight" else eligible_rows)
    clips = []
    for index in indices:
        source = cohort["clips"][index]
        score = scores[source["id"]]
        require(train_map.get(source["id"]) == source["speakerId"] and score["text"] == source["text"],
                "Selected prompt is not bound to its verified training speaker")
        phones = [phone for word in score["words"] for phone in word["phones"]]
        mapped, tokens, ambiguity = canonical_mapping(phones, vocabulary, recipe)
        offsets = np.cumsum([0] + [len(word["phones"]) for word in score["words"]]).tolist()
        target_rows = []
        for row_index, row in enumerate(cohort["rows"]):
            if row_index not in selected_rows or row["clipIndex"] != index:
                continue
            canonical_index = offsets[row["wordIndex"]] + row["phoneIndex"]
            require(phones[canonical_index] == row["targetPhone"] and
                    score["words"][row["wordIndex"]]["text"] == row["targetWord"],
                    "Target row position differs from the canonical prompt")
            target_rows.append({"rowIndex": row_index, "rowId": row["id"], "targetId": row["targetId"],
                                "targetPhone": row["targetPhone"], "canonicalIndex": canonical_index,
                                "wordIndex": row["wordIndex"], "phoneIndex": row["phoneIndex"]})
        require(bool(target_rows), "Selected clip has no eligible inner-fit targets")
        clips.append({key: source[key] for key in ("id", "speakerId", "audioPath", "audioSha256", "sampleCount")} |
                     {"clipIndex": index, "canonicalPhones": phones, "mappedTokens": mapped,
                      "mappedTokenIds": tokens, "mappingAmbiguities": ambiguity, "targetRows": target_rows})
    result = {"schemaVersion": 1, "experiment": recipe["experiment"], "authorPartition": "train",
              "fold": 0 if scope == "preflight" else None,
              "partition": "innerFitRows" if scope == "preflight" else "allEligibleAuthorTrain",
              "selection": recipe["preflightSelection"] if scope == "preflight" else "all eligible author-training rows",
              "eligibleCohortRows": len(eligible_rows), "fullCohortCoverage": scope == "author-train",
              "cohortPath": str(cohort_path.resolve()), "cohortSha256": digest(cohort_path),
              "splitsPath": str(splits_path.resolve()), "splitsSha256": digest(splits_path),
              "trainMapPath": str(METADATA / "train/utt2spk"), "trainMapSha256": hashlib.sha256(train_bytes).hexdigest(),
              "audioRoot": str(AUDIO), "vocabularyPath": str(vocabulary_path.resolve()), "vocabularySha256": VOCAB_SHA,
              "recipePath": str(RECIPE), "recipeSha256": digest(RECIPE), "generatorSha256": digest(Path(__file__)),
              "clips": clips, **FALSE_FLAGS}
    require(output.resolve().is_relative_to((HERE / "outputs").resolve()), "Keep manifest in ignored research outputs")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    return result


def edit_distance(left: list[int], right: list[int]) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def greedy_tokens(log_prob: np.ndarray) -> list[int]:
    sequence = []
    previous = None
    for value in log_prob.argmax(1).tolist():
        if value != previous and value != 0:
            sequence.append(value)
        previous = value
    return sequence


def validate_log_prob(value: np.ndarray, expected_frames: int) -> None:
    require(value.dtype == np.dtype("<f4") and value.shape == (expected_frames, 392) and
            0 < expected_frames <= 1500 and np.isfinite(value).all() and (value <= 1e-6).all() and
            np.allclose(np.exp(value.astype(np.float64)).sum(1), 1, atol=3e-5, rtol=0),
            "Invalid full-vocabulary float32 log posterior matrix")


def local_features(log_prob: np.ndarray, target_tokens: list[int], positions: list[int], recipe: dict) -> tuple[list[dict], dict]:
    require(len(set(positions)) == len(positions) and all(type(p) is int and 0 <= p < len(target_tokens) for p in positions),
            "Invalid canonical target positions")
    validate_log_prob(log_prob, len(log_prob))
    require(all(type(token) is int and 3 < token < 392 for token in target_tokens), "Canonical path includes a special token")
    values = log_prob.astype(np.float64)
    path, score = viterbi_ctc(values, target_tokens, blank=0)
    decoded = greedy_tokens(values)
    utterance = {"viterbiLogProbabilityPerFrame": score / len(values),
                 "greedyCanonicalTokenErrorRate": edit_distance(target_tokens, decoded) / len(target_tokens),
                 "greedyExactCanonicalSequence": decoded == target_tokens,
                 "canonicalTokens": len(target_tokens), "greedyTokens": len(decoded)}
    results = []
    for position in positions:
        frames = np.flatnonzero(np.asarray(path) == 2 * position + 1)
        require(len(frames) > 0 and np.array_equal(frames, np.arange(frames[0], frames[-1] + 1)),
                "Canonical target state is absent or fragmented")
        start, end = int(frames[0]), int(frames[-1] + 1)
        token = target_tokens[position]
        local = values[start:end]
        probabilities = np.exp(local)
        competitors = [i for i in range(4, 392) if i != token]
        expected = local[:, token]
        # Nonblank mass includes the special-token residual; no 24-phone renormalization.
        nonblank_max = local[:, 1:].max(1)
        log_nonblank = nonblank_max + np.log(np.exp(local[:, 1:] - nonblank_max[:, None]).sum(1))
        statistics = [float(expected.mean()), float(probabilities[:, token].mean()),
                      float(probabilities[:, token].max()), float((expected - local[:, competitors].max(1)).mean()),
                      float((expected - log_nonblank).mean()), float(np.mean(local.argmax(1) == token)),
                      float(probabilities[:, 0].mean()), float(probabilities[:, 1:4].sum(1).mean()),
                      float(-(probabilities * local).sum(1).mean()), (end - start) * .02, end - start,
                      utterance["viterbiLogProbabilityPerFrame"], utterance["greedyCanonicalTokenErrorRate"]]
        flags = ["unverified-forced-canonical-location"]
        if end - start < recipe["minimumTargetFramesDiagnostic"]:
            flags.append("fewer-than-two-target-state-frames")
        if statistics[5] < .5:
            flags.append("target-is-not-argmax-on-most-occupied-frames")
        results.append({"canonicalIndex": position, "tokenId": token, "intervalFrames": [start, end],
                        "estimatedFrameCenterSeconds": [(start * 320 + 199.5) / 16000,
                                                         ((end - 1) * 320 + 199.5) / 16000],
                        "scalarFeatures": statistics, "diagnosticFlags": flags})
    return results, utterance


def pooled_window(frames: np.ndarray, interval: list[int], expected_ctc_frames: int, context: int) -> tuple[np.ndarray, list[int]]:
    require(frames.dtype == np.float32 and frames.shape == (expected_ctc_frames, 768) and np.isfinite(frames).all(),
            "WavLM and CTC frame grids differ")
    start, end = interval
    require(type(context) is int and context >= 0 and 0 <= start < end <= len(frames), "Invalid estimated pooling interval")
    window = [max(0, start - context), min(len(frames), end + context)]
    return frames[window[0]:window[1]].mean(0, dtype=np.float64).astype(np.float32), window


def extract_features(manifest_path: Path, cache: Path, output: Path, wavlm_cache: Path | None = None) -> dict:
    started = time.perf_counter()
    input_paths = {"manifest": manifest_path, "recipe": RECIPE, "ctcIndex": cache / "index.json",
                   "ctcConfig": cache / "config.json", "source/multiphone_local_features.py": Path(__file__),
                   "source/alignment_pilot.py": HERE / "alignment_pilot.py"}
    initial_digests = capture_digests(input_paths)
    manifest, recipe = json.loads(manifest_path.read_text()), json.loads(RECIPE.read_text())
    added_paths = {"cohort": Path(manifest["cohortPath"]), "splits": Path(manifest["splitsPath"]),
                   "vocabulary": Path(manifest["vocabularyPath"])}
    if wavlm_cache:
        added_paths.update({"wavlmIndex": wavlm_cache / "index.json", "wavlmConfig": wavlm_cache / "config.json"})
    initial_digests.update(capture_digests(added_paths))
    input_paths.update(added_paths)
    require(manifest["recipeSha256"] == digest(RECIPE) and manifest["vocabularySha256"] == VOCAB_SHA,
            "Manifest mapping recipe differs")
    require(digest(Path(manifest["cohortPath"])) == manifest["cohortSha256"] == recipe["cohortSha256"] and
            digest(Path(manifest["splitsPath"])) == manifest["splitsSha256"] == recipe["splitsSha256"],
            "Original study binding differs")
    cohort = json.loads(Path(manifest["cohortPath"]).read_text())
    validate_manifest_rows(manifest, cohort)
    eligible_indices = {i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"]}
    require(manifest["eligibleCohortRows"] == len(eligible_indices), "Eligible cohort size differs")
    config, index = json.loads((cache / "config.json").read_text()), json.loads((cache / "index.json").read_text())
    require(config["manifestSha256"] == digest(manifest_path) and index["configSha256"] == digest(cache / "config.json") and
            index["complete"] is True and set(index["entries"]) == {clip["id"] for clip in manifest["clips"]},
            "CTC cache is incomplete or belongs to another manifest")
    vocabulary = json.loads(Path(manifest["vocabularyPath"]).read_text())
    require(digest(Path(manifest["vocabularyPath"])) == VOCAB_SHA and config["frameStrideSamples"] == 320 and
            config["frameReceptiveFieldSamples"] == 400, "CTC vocabulary or geometry differs")
    wavlm_index, wavlm_config = None, None
    if wavlm_cache:
        wavlm_config = json.loads((wavlm_cache / "config.json").read_text())
        wavlm_index = json.loads((wavlm_cache / "index.json").read_text())
        require(wavlm_config["encoder"] == WavLMEncoder.identity and
                wavlm_config["cohortSha256"] == manifest["cohortSha256"] and wavlm_index["complete"] is True and
                wavlm_index["configSha256"] == digest(wavlm_cache / "config.json"), "WavLM cache binding differs")
        model_config_path = HERE / "outputs/model-cache/models--microsoft--wavlm-base-plus/snapshots" / WavLMEncoder.identity["revision"] / "config.json"
        require(digest(model_config_path) == WavLMEncoder.identity["artifactSha256"]["config.json"], "WavLM config pin differs")
        model_config = json.loads(model_config_path.read_text())
        require(model_config["conv_kernel"] == recipe["convKernel"] and model_config["conv_stride"] == recipe["convStride"],
                "WavLM convolution grid differs from CTC")
    rows, clip_reports, pooled = [], [], []
    for clip in manifest["clips"]:
        mapped, tokens, _ = canonical_mapping(clip["canonicalPhones"], vocabulary, recipe)
        require(mapped == clip["mappedTokens"] and tokens == clip["mappedTokenIds"], "Canonical token mapping changed")
        entry = index["entries"][clip["id"]]
        path = (cache / entry["path"]).resolve()
        expected_frames = convolution_frames(clip["sampleCount"], recipe)
        require(path.is_relative_to(cache.resolve()) and digest(path) == entry["sha256"] and
                entry["frames"] == expected_frames and entry["audioSha256"] == clip["audioSha256"] and
                entry["configSha256"] == index["configSha256"], "CTC entry hash or waveform binding differs")
        log_prob = np.fromfile(path, dtype="<f4").reshape(expected_frames, 392)
        validate_log_prob(log_prob, expected_frames)
        estimates, diagnostics = local_features(log_prob, tokens, [row["canonicalIndex"] for row in clip["targetRows"]], recipe)
        wavlm = None
        if wavlm_cache:
            saved_entry = wavlm_index["entries"][clip["id"]]
            saved_path = (wavlm_cache / saved_entry["path"]).resolve()
            require(saved_path.is_relative_to(wavlm_cache.resolve()) and digest(saved_path) == saved_entry["sha256"],
                    "WavLM feature digest differs")
            with np.load(saved_path, allow_pickle=False) as saved:
                require(str(saved["audio_sha256"]) == clip["audioSha256"] and
                        str(saved["config_sha256"]) == wavlm_index["configSha256"], "WavLM source waveform differs")
                wavlm = saved["frames"].copy()
        for target, estimate in zip(clip["targetRows"], estimates, strict=True):
            row = {**target, "clipId": clip["id"], **estimate, "mappingAmbiguities": clip["mappingAmbiguities"]}
            if wavlm is not None:
                value, window = pooled_window(wavlm, estimate["intervalFrames"], expected_frames, recipe["poolingContextFrames"])
                row["pooledFeatureIndex"], row["estimatedPoolingWindowFrames"] = len(pooled), window
                pooled.append(value)
            rows.append(row)
        clip_reports.append({"clipId": clip["id"], **diagnostics, "targets": len(estimates)})
    require(output.resolve().is_relative_to((HERE / "outputs").resolve()), "Keep features in ignored research outputs")
    output.mkdir(parents=True, exist_ok=False)
    if pooled:
        np.save(output / "estimated-wavlm-pooled.npy", np.asarray(pooled, dtype=np.float32), allow_pickle=False)
    scalars = np.asarray([row["scalarFeatures"] for row in rows], dtype=np.float32)
    require(scalars.shape == (len(rows), len(SCALAR_NAMES)) and np.isfinite(scalars).all(), "Invalid scalar feature matrix")
    np.save(output / "scalars.npy", scalars, allow_pickle=False)
    row_indices = [row["rowIndex"] for row in rows]
    expected_indices = [row["rowIndex"] for clip in manifest["clips"] for row in clip["targetRows"]]
    require(row_indices == expected_indices and len(row_indices) == len(set(row_indices)), "Target-row coverage changed")
    require(set(row_indices) <= eligible_indices and
            (set(row_indices) == eligible_indices) == manifest["fullCohortCoverage"], "Full-cohort coverage flag differs")
    report = {"schemaVersion": 1, "experiment": recipe["experiment"], "manifestSha256": initial_digests["manifest"],
              "manifestPath": str(manifest_path.resolve()), "ctcIndexPath": str((cache / "index.json").resolve()),
              "recipePath": str(RECIPE), "wavlmIndexPath": str((wavlm_cache / "index.json").resolve()) if wavlm_cache else None,
              "cohortSha256": manifest["cohortSha256"], "splitsSha256": manifest["splitsSha256"],
              "mappingVersion": recipe["mappingVersion"], "rowIndices": row_indices,
              "complete": True, "fullCohortCoverage": manifest["fullCohortCoverage"],
              "eligibleCohortRows": manifest["eligibleCohortRows"], "failedRows": [], "unmappableRows": [],
              "ctcIndexSha256": initial_digests["ctcIndex"], "recipeSha256": initial_digests["recipe"],
              "sourceSha256": {name: initial_digests["source/" + name] for name in ("multiphone_local_features.py", "alignment_pilot.py")},
              "inputSha256": initial_digests,
              "scalarFeatureNames": SCALAR_NAMES, "rows": rows, "clipDiagnostics": clip_reports,
              "wavlmIndexSha256": initial_digests["wavlmIndex"] if wavlm_cache else None,
              "pooledFeaturesSha256": digest(output / "estimated-wavlm-pooled.npy") if pooled else None,
              "scalarFeatures": {"path": "scalars.npy", "sha256": digest(output / "scalars.npy"),
                                 "shape": list(scalars.shape), "dtype": "float32"},
              "pooledFeatures": {"path": "estimated-wavlm-pooled.npy", "sha256": digest(output / "estimated-wavlm-pooled.npy"),
                                 "shape": [len(rows), 768], "dtype": "float32"} if pooled else None,
              "elapsedSeconds": time.perf_counter() - started,
              "inclusionPolicy": "Every declared target retained; diagnostics never exclude by rating or model support",
              "intervalMeaning": "Frames occupied by a forced canonical CTC state, usually emission spikes; not phoneme-duration boundaries",
              "limitations": recipe["mappingLimitations"], **FALSE_FLAGS}
    require_unchanged(input_paths, initial_digests)
    write_json(output / "features.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="phase", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--cohort", type=Path, default=BASE / "cohort.json")
    prepare.add_argument("--splits", type=Path, default=BASE / "splits.json")
    prepare.add_argument("--vocabulary", type=Path, default=VOCAB)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--scope", choices=("preflight", "author-train"), default="preflight")
    extract = subparsers.add_parser("extract")
    extract.add_argument("--manifest", type=Path, required=True)
    extract.add_argument("--cache", type=Path, required=True)
    extract.add_argument("--wavlm-cache", type=Path)
    extract.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (prepare_manifest(args.cohort, args.splits, args.output, args.vocabulary, args.scope) if args.phase == "prepare"
              else extract_features(args.manifest, args.cache, args.output, args.wavlm_cache))
    print(json.dumps({"phase": args.phase, "clips": len(result.get("clips", result.get("clipDiagnostics", []))),
                      "rows": len(result.get("rows", [])), "output": str(args.output)}))
