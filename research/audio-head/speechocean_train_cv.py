"""Train-only nested speaker cross-validation for frozen SpeechOcean /R/ features.

The published author test partition is not scored, inspected, or used for any
setting in this experiment. This is an exploratory research artifact only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "4"

import numpy as np

from encoders import Wav2VecEncoder, WavLMEncoder
from speechocean_audit import FILES, mapping, pinned_bytes
from speechocean_r_label_audit import selected_json_objects
from speechocean_r_probe import (ARCHIVE, ARCHIVE_SHA256, AUDIO, AUTHORITY, HERE, METADATA,
                                 fit_ridge, metrics, predict_ridge, rating_baseline,
                                 selected_r, sha256_file, write_json)


RECIPE = HERE / "experiments/speechocean-r-train-cv-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-train-cv-v1"
ENCODERS = {"wav2vec2-base": Wav2VecEncoder, "wavlm-base-plus": WavLMEncoder}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest_key(seed: int, *parts: object) -> str:
    return hashlib.sha256(":".join(map(str, (seed, *parts))).encode()).hexdigest()


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Train CV recipe path differs from predeclaration")
    recipe = json.loads(path.read_text())
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-train-cv-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("maxCpuMathThreads") == 4 and
            recipe.get("knownAuthorTest") is True and
            recipe.get("authorTestUsedForSettings") is False and
            recipe.get("sourceArchiveSha256") == ARCHIVE_SHA256 and
            recipe.get("outerFolds") == 5 and
            recipe.get("outerSeed") == 20260923 and
            recipe.get("innerFractionOfOuterTrainSpeakers") == 0.2 and
            recipe.get("ridgeAlphas") == [1.0, 10.0, 100.0, 1000.0] and
            recipe.get("targetWordSmoothing") == [1.0, 5.0, 20.0] and
            recipe.get("selectionMetric") == "inner validation MAE; smallest candidate breaks ties" and
            recipe.get("constantTwo") == 2.0 and
            recipe.get("trainMeanBaseline") is True and
            recipe.get("reportOuterPromptOverlap") is True and
            recipe.get("predictionsClipped") is False and
            recipe.get("outputDirectory") == "outputs/speechocean-r-train-cv-v1" and
            all(recipe.get(key) is False for key in AUTHORITY),
            "Train CV recipe differs from predeclaration")
    require(set(recipe.get("inputs", {})) == set(ENCODERS), "Expected exactly two pinned feature inputs")
    return recipe


def load_inputs(recipe: dict) -> tuple[list[dict], dict[str, np.ndarray], dict]:
    require(sha256_file(ARCHIVE) == recipe["sourceArchiveSha256"],
            "Official audio archive SHA-256 mismatch")
    rows_by_encoder = {}
    positions_by_encoder = {}
    matrices = {}
    evidence = {}
    for kind, encoder in ENCODERS.items():
        pin = recipe["inputs"][kind]
        directory = HERE / pin["directory"]
        require(directory.resolve().is_relative_to((HERE / "outputs").resolve()),
                "Feature directory outside research outputs")
        actual_hashes = {
            "featureIndexSha256": sha256_file(directory / "feature-index.json"),
            "featureProgressSha256": sha256_file(directory / "feature-progress.json"),
            "featureArraySha256": sha256_file(directory / "features.npy"),
        }
        require(all(actual_hashes[key] == pin[key] for key in actual_hashes),
                f"{kind} feature cache differs from predeclared SHA-256")
        index = json.loads((directory / "feature-index.json").read_text())
        progress = json.loads((directory / "feature-progress.json").read_text())
        require(index.get("encoder") == encoder.identity and
                index.get("recipeVersion") == pin["recipeVersion"] and
                index.get("sourceArchiveSha256") == ARCHIVE_SHA256 and
                type(index.get("rows")) is list and
                progress.get("completed") == len(index["rows"]) and
                progress.get("featureArraySha256") == actual_hashes["featureArraySha256"] and
                progress.get("featureIndexSha256") == actual_hashes["featureIndexSha256"],
                f"{kind} feature cache metadata mismatch")
        train_positions = [i for i, row in enumerate(index["rows"]) if row.get("split") == "train"]
        train_rows = [index["rows"][i] for i in train_positions]
        require(len(train_rows) == recipe["expectedTrainClips"] and
                len({row["speaker"] for row in train_rows}) == recipe["expectedTrainSpeakers"] and
                len({row["id"] for row in train_rows}) == len(train_rows),
                "Unexpected author train selection")
        require(all(set(row) == {"id", "split", "speaker", "audioPath", "audioSha256", "rating"} and
                    type(row["rating"]) in (int, float) and 0 <= row["rating"] <= 2 and
                    abs(row["rating"] * 5 - round(row["rating"] * 5)) < 1e-8
                    for row in train_rows), "Invalid author train feature row")
        features = np.load(directory / "features.npy", mmap_mode="r", allow_pickle=False)
        require(features.shape == (len(index["rows"]), 768) and
                features.dtype == np.dtype("float32"), "Feature cache shape or dtype changed")
        selected = np.asarray(features[train_positions], dtype=np.float64)
        require(np.isfinite(selected).all(), "Nonfinite train feature")
        rows_by_encoder[kind] = train_rows
        positions_by_encoder[kind] = train_positions
        matrices[kind] = selected
        evidence[kind] = {"directory": pin["directory"], "encoder": encoder.identity,
                          "recipeVersion": pin["recipeVersion"], **actual_hashes,
                          "trainRows": len(train_rows)}
    reference = rows_by_encoder["wav2vec2-base"]
    require(rows_by_encoder["wavlm-base-plus"] == reference and
            positions_by_encoder["wavlm-base-plus"] == positions_by_encoder["wav2vec2-base"],
            "Train row identity or order differs across encoders")
    train_map = mapping(pinned_bytes(METADATA, "train/utt2spk"), r"\d{9}", r"\d{4}")
    author_scores = selected_json_objects(pinned_bytes(METADATA, "resource/scores.json"),
                                          set(train_map))
    train_r = {utterance: selected_r(author_scores[utterance])
               for utterance in train_map}
    selected_ids = {utterance for utterance, selection in train_r.items() if selection is not None}
    require(selected_ids == {row["id"] for row in reference},
            "Cached one-/R/ train selection differs from pinned author metadata")
    for row in reference:
        path = Path(row["audioPath"])
        require(path.resolve().is_relative_to((AUDIO / "WAVE").resolve()) and
                sha256_file(path) == row["audioSha256"] and
                row["speaker"] == train_map[row["id"]] and
                abs(row["rating"] - train_r[row["id"]][1]) < 1e-9,
                "Selected author train WAV differs from feature cache source")
        row["targetWord"] = train_r[row["id"]][0]
        row["text"] = author_scores[row["id"]]["text"]
    evidence["authorTrainMetadata"] = {
        "scoresSha256": FILES["resource/scores.json"][1],
        "utt2spkSha256": FILES["train/utt2spk"][1],
        "selectedOneRTrainClips": len(reference)}
    return reference, matrices, evidence


def outer_speaker_folds(speakers: set[str], folds: int, seed: int) -> dict[str, int]:
    ordered = sorted(speakers, key=lambda speaker: digest_key(seed, "outer", speaker))
    require(len(ordered) >= folds * 2, "Too few speakers for outer folds")
    return {speaker: index % folds for index, speaker in enumerate(ordered)}


def inner_validation_speakers(speakers: set[str], fold: int, fraction: float, seed: int) -> set[str]:
    ordered = sorted(speakers, key=lambda speaker: digest_key(seed, "inner", fold, speaker))
    count = max(1, round(len(ordered) * fraction))
    require(count < len(ordered), "Inner validation would consume all speakers")
    return set(ordered[:count])


def choose_ridge(x: np.ndarray, y: np.ndarray, inner_fit: np.ndarray, inner_val: np.ndarray,
                 alphas: list[float]) -> tuple[float, list[dict]]:
    trials = []
    for alpha in alphas:
        head = fit_ridge(x[inner_fit], y[inner_fit], alpha)
        trials.append({"alpha": alpha,
                       **metrics(predict_ridge(head, x[inner_val]), y[inner_val])})
    best = min(trials, key=lambda item: (item["mae"], item["alpha"]))
    return best["alpha"], trials


def choose_word_smoothing(rows: list[dict], y: np.ndarray, inner_fit: np.ndarray,
                          inner_val: np.ndarray, candidates: list[float]) -> tuple[float, list[dict]]:
    trials = []
    for smoothing in candidates:
        prediction = rating_baseline([rows[i] for i in inner_fit], y[inner_fit],
                                     [rows[i] for i in inner_val], smoothing, "targetWord")
        trials.append({"smoothing": smoothing, **metrics(prediction, y[inner_val])})
    best = min(trials, key=lambda item: (item["mae"], item["smoothing"]))
    return best["smoothing"], trials


def evaluate(rows: list[dict], matrices: dict[str, np.ndarray], recipe: dict) -> tuple[dict, list[dict]]:
    require(len(rows) == 766 and set(matrices) == set(ENCODERS), "Expected paired author train inputs")
    y = np.asarray([row["rating"] for row in rows], dtype=np.float64)
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    predictions = {name: np.full(len(rows), np.nan) for name in (*ENCODERS, "targetWord", "constantTwo", "trainMean")}
    fold_reports = []
    for fold in range(recipe["outerFolds"]):
        outer_train = np.asarray([i for i, row in enumerate(rows) if assignments[row["speaker"]] != fold], dtype=int)
        outer_holdout = np.asarray([i for i, row in enumerate(rows) if assignments[row["speaker"]] == fold], dtype=int)
        train_speakers = {rows[i]["speaker"] for i in outer_train}
        holdout_speakers = {rows[i]["speaker"] for i in outer_holdout}
        require(train_speakers.isdisjoint(holdout_speakers), "Outer speaker overlap")
        inner_speakers = inner_validation_speakers(train_speakers, fold,
                                                  recipe["innerFractionOfOuterTrainSpeakers"],
                                                  recipe["outerSeed"])
        inner_fit = np.asarray([i for i in outer_train if rows[i]["speaker"] not in inner_speakers], dtype=int)
        inner_val = np.asarray([i for i in outer_train if rows[i]["speaker"] in inner_speakers], dtype=int)
        require(inner_speakers.isdisjoint({rows[i]["speaker"] for i in inner_fit}) and
                len(inner_fit) + len(inner_val) == len(outer_train), "Inner speaker overlap")
        shared_prompts = ({rows[i]["text"] for i in outer_train} &
                          {rows[i]["text"] for i in outer_holdout})
        fold_predictions = {}
        selected = {}
        for kind, x in matrices.items():
            alpha, trials = choose_ridge(x, y, inner_fit, inner_val, recipe["ridgeAlphas"])
            head = fit_ridge(x[outer_train], y[outer_train], alpha)
            fold_predictions[kind] = predict_ridge(head, x[outer_holdout])
            selected[kind] = {"alpha": alpha, "innerTrials": trials}
        smoothing, trials = choose_word_smoothing(rows, y, inner_fit, inner_val,
                                                  recipe["targetWordSmoothing"])
        fold_predictions["targetWord"] = rating_baseline(
            [rows[i] for i in outer_train], y[outer_train],
            [rows[i] for i in outer_holdout], smoothing, "targetWord")
        fold_predictions["constantTwo"] = np.full(len(outer_holdout), 2.0)
        fold_predictions["trainMean"] = np.full(len(outer_holdout), y[outer_train].mean())
        selected["targetWord"] = {"smoothing": smoothing, "innerTrials": trials}
        for name, result in fold_predictions.items():
            predictions[name][outer_holdout] = result
        fold_reports.append({"fold": fold, "holdoutClips": len(outer_holdout),
                             "holdoutSpeakers": len(holdout_speakers),
                             "holdoutSpeakerIds": sorted(holdout_speakers),
                             "outerTrainClips": len(outer_train),
                             "outerTrainSpeakers": len(train_speakers),
                             "outerTrainSpeakerIds": sorted(train_speakers),
                             "innerFitSpeakers": len({rows[i]["speaker"] for i in inner_fit}),
                             "innerFitSpeakerIds": sorted({rows[i]["speaker"] for i in inner_fit}),
                             "innerValidationSpeakers": len(inner_speakers),
                             "innerValidationSpeakerIds": sorted(inner_speakers),
                             "exactPromptTextsSharedWithOuterTrain": len(shared_prompts),
                             "outerHoldoutClipsWithSeenPromptText": sum(
                                 rows[i]["text"] in shared_prompts for i in outer_holdout),
                             "selection": selected,
                             "metrics": {name: metrics(result, y[outer_holdout])
                                         for name, result in fold_predictions.items()}})
        print(f"Completed outer fold {fold + 1}/{recipe['outerFolds']}", flush=True)
    require(all(np.isfinite(result).all() for result in predictions.values()),
            "Missing or nonfinite out-of-fold prediction")
    oof = [{"id": row["id"], "speaker": row["speaker"],
            "outerFold": assignments[row["speaker"]], "rating": float(y[i]),
            "predictions": {name: float(result[i]) for name, result in predictions.items()}}
           for i, row in enumerate(rows)]
    summary = {"folds": fold_reports,
               "pooledOutOfFold": {name: metrics(result, y) for name, result in predictions.items()},
               "outOfFoldClips": len(rows),
               "outOfFoldSpeakers": len(assignments),
               "predictionRange": {name: [float(result.min()), float(result.max())]
                                   for name, result in predictions.items()},
               "predictionsOutsideRatingRange": {name: int(np.count_nonzero((result < 0) | (result > 2)))
                                                 for name, result in predictions.items()}}
    return summary, oof


def run(output: Path = OUTPUT) -> dict:
    started = time.perf_counter()
    recipe = load_recipe()
    require(output.resolve() == OUTPUT.resolve(), "Train CV output differs from predeclared directory")
    rows, matrices, cache_evidence = load_inputs(recipe)
    fitting_started = time.perf_counter()
    summary, oof = evaluate(rows, matrices, recipe)
    fit_seconds = time.perf_counter() - fitting_started
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "out-of-fold.json", oof)
    provenance = {"experiment": recipe["experiment"], "recipeSha256": sha256_file(RECIPE),
                  "sourceArchiveSha256": ARCHIVE_SHA256,
                  "cacheEvidence": cache_evidence,
                  "authorPartition": "train", "authorTestUsedForSettings": False,
                  "knownAuthorTest": True, **AUTHORITY}
    write_json(output / "provenance.json", provenance)
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": sha256_file(RECIPE),
              "provenanceSha256": sha256_file(output / "provenance.json"),
              "outOfFoldSha256": sha256_file(output / "out-of-fold.json"),
              "outerAssignment": recipe["outerAssignment"],
              "innerAssignment": recipe["innerAssignment"],
              "selectionMetric": recipe["selectionMetric"],
              "maxCpuMathThreads": recipe["maxCpuMathThreads"],
              "nestedFitSeconds": fit_seconds,
              "elapsedSeconds": time.perf_counter() - started,
              "authorPartition": "train", "authorTestUsedForSettings": False,
              "knownAuthorTest": True,
              **summary,
              "interpretation": "Exploratory train-only nested CV comparison; paired speaker folds support descriptive differences, not a model winner or clinical claim.",
              "limitations": ["Five-rater pronunciation scores are subjective weak supervision, not produced-phone labels.",
                              "Whole-utterance pooling does not isolate the /R/ interval.",
                              "Speaker-disjoint folds do not establish household or recording-condition independence.",
                              "Speaker grouping does not make prompt text disjoint across folds; exact prompt overlap is reported per fold.",
                              "This reuses one public corpus and frozen feature caches; it is not external validation.",
                              "The published author test was previously inspected in other experiments but supplies no labels or metrics to this CV."],
              **AUTHORITY}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))
