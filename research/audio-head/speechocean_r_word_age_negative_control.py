"""Locked author-train categorical confound probe for five /R/ rater scores.

Only selected author-train score objects and the train age map are decoded.
No audio, acoustic features, author-test labels, or author-test inference enter.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np

from speechocean_audit import FILES, mapping, pinned_bytes
from speechocean_r_age_diagnostics import age_band
from speechocean_r_label_audit import derive_one_r, selected_json_objects
from speechocean_r_oof_diagnostics import sha256_file, write_json
from speechocean_r_rater_cv import AUTHORITY, probabilistic_metrics, require
from speechocean_train_cv import inner_validation_speakers, outer_speaker_folds


HERE = Path(__file__).resolve().parent
METADATA = HERE / "outputs/speechocean762-metadata-v1"
RECIPE = HERE / "experiments/speechocean-r-word-age-negative-control-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-word-age-negative-control-v1"
PREDECLARED_RECIPE_SHA256 = "aac76c623d9b53338b7fc059b082c027114fde91180e375a4e1f957476304802"
REFERENCE_METHODS = ("wav2vec2-base", "wavlm-base-plus", "trainPrior", "targetWord")
FALSE_FLAGS = (*AUTHORITY, "authorTestUsedForSettings", "authorTestInferencePerformed")
REFERENCE_HASHES = {
    "referenceRecipeSha256": "f17a024acb7837679a0818d7fbd5f617c0b1ba0ec3cb56c127531adabe22c5f5",
    "referenceReportSha256": "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa",
    "referenceOutOfFoldSha256": "e1f90b49529ff3daabf546794c672a0c62e3001fe85933eddcf12ef906e7546c",
}


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Control recipe path differs from lock")
    require(sha256_file(path) == PREDECLARED_RECIPE_SHA256,
            "Control recipe SHA-256 differs from predeclaration")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-word-age-negative-control-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("referenceRecipe") == "experiments/speechocean-r-rater-cv-convergence-v2.json" and
            recipe.get("referenceReport") == "outputs/speechocean-r-rater-cv-convergence-v2/report.json" and
            recipe.get("referenceOutOfFold") == "outputs/speechocean-r-rater-cv-convergence-v2/out-of-fold.json" and
            all(recipe.get(key) == value for key, value in REFERENCE_HASHES.items()) and
            recipe.get("selectedTrainIdsSha256") ==
                "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3" and
            recipe.get("sourceMetadataSha256") == {name: FILES[name][1] for name in
                ("train/utt2spk", "train/spk2age", "resource/scores.json",
                 "resource/scores-detail.json")} and
            recipe.get("ageMap") == "train/spk2age" and
            recipe.get("ageBands") == {"child": "age <= 15", "adult": "age >= 19"} and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("expectedBandClips") == {"child": 349, "adult": 417} and
            recipe.get("expectedRaterScoresPerClip") == 5 and
            recipe.get("outerFolds") == 5 and recipe.get("outerSeed") == 20260923 and
            recipe.get("innerFractionOfOuterTrainSpeakers") == 0.2 and
            recipe.get("classes") == [0, 1, 2] and
            recipe.get("predictors") == ["canonicalTargetWord", "corpusAgeBand"] and
            recipe.get("globalPriorPseudocountPerClass") == 1.0 and
            recipe.get("wordSmoothingCandidates") == [1.0, 5.0, 20.0] and
            recipe.get("ageSmoothingCandidates") == [1.0, 5.0, 20.0] and
            recipe.get("cellSmoothingCandidates") == [5.0, 20.0, 100.0] and
            recipe.get("wordAgeBackoffWeights") == {"word": 0.5, "age": 0.5} and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("probabilitiesClippedForEvaluationOnly") is True and
            recipe.get("outputDirectory") == "outputs/speechocean-r-word-age-negative-control-v1" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Control recipe differs from predeclaration")
    for path_key, hash_key in (("referenceRecipe", "referenceRecipeSha256"),
                               ("referenceReport", "referenceReportSha256"),
                               ("referenceOutOfFold", "referenceOutOfFoldSha256")):
        require(sha256_file(HERE / recipe[path_key]) == recipe[hash_key],
                f"Pinned {path_key} SHA-256 mismatch")
    return recipe


def load_train_rows(recipe: dict) -> tuple[list[dict], np.ndarray, dict, list[dict]]:
    """Rebuild categorical rows from selected train metadata and verify saved OOF."""
    report = json.loads((HERE / recipe["referenceReport"]).read_text(encoding="utf-8"))
    oof = json.loads((HERE / recipe["referenceOutOfFold"]).read_text(encoding="utf-8"))
    require(report.get("authorPartition") == "train" and
            report.get("outOfFoldSha256") == recipe["referenceOutOfFoldSha256"] and
            report.get("recipeSha256") == recipe["referenceRecipeSha256"] and
            report.get("outOfFoldClips") == 766 and
            report.get("outOfFoldRaterScores") == 3830 and
            report.get("outOfFoldSpeakers") == 124 and
            report.get("authorTestUsedForSettings") is False and
            all(report.get(flag) is False for flag in AUTHORITY) and
            isinstance(oof, list) and len(oof) == 766,
            "Reference is not the pinned train-only OOF result")
    ids = [row["id"] for row in oof]
    require(len(set(ids)) == 766 and
            hashlib.sha256(("\n".join(sorted(ids)) + "\n").encode()).hexdigest() ==
                recipe["selectedTrainIdsSha256"], "OOF IDs differ from pinned train IDs")
    train_map = mapping(pinned_bytes(METADATA, "train/utt2spk"), r"\d{9}", r"\d{4}")
    ages = {speaker: int(age) for speaker, age in mapping(
        pinned_bytes(METADATA, recipe["ageMap"]), r"\d{4}", r"\d{1,3}").items()}
    require(len(train_map) == 2500 and len(ages) == 125 and set(ids) <= set(train_map),
            "Expected pinned author-training speaker and age maps")
    selected = set(ids)
    aggregate = selected_json_objects(pinned_bytes(METADATA, "resource/scores.json"), selected)
    detailed = selected_json_objects(pinned_bytes(METADATA, "resource/scores-detail.json"), selected)
    rows = []
    counts = []
    for saved in oof:
        clip_id, speaker = saved["id"], saved["speaker"]
        result = derive_one_r(aggregate[clip_id], detailed[clip_id])
        require(result is not None and speaker == train_map[clip_id] and speaker in ages,
                "OOF row differs from selected author-training metadata")
        canonical = [word["text"] for word in aggregate[clip_id]["words"]
                     if "R" in word["phones"]]
        require(len(canonical) == 1 and type(canonical[0]) is str and canonical[0],
                "Expected one canonical target word")
        vector = [result[1].count(score) for score in (0, 1, 2)]
        require(set(saved) == {"id", "speaker", "outerFold", "fiveRaterCounts", "probabilities"} and
                saved["fiveRaterCounts"] == vector and
                set(saved["probabilities"]) == set(REFERENCE_METHODS),
                "OOF rating or predictor fields differ from pinned metadata")
        rows.append({"id": clip_id, "speaker": speaker, "targetWord": canonical[0],
                     "ageBand": age_band(ages[speaker])})
        counts.append(vector)
    counts_array = np.asarray(counts, dtype=np.int64)
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    require(len(assignments) == 124 and
            all(saved["outerFold"] == assignments[row["speaker"]]
                for saved, row in zip(oof, rows)) and
            all(set(fold["holdoutSpeakerIds"]) ==
                {speaker for speaker, assignment in assignments.items() if assignment == fold["fold"]}
                for fold in report["folds"]) and
            {band: sum(row["ageBand"] == band for row in rows) for band in ("child", "adult")} ==
                recipe["expectedBandClips"], "Reference folds or age bands differ from lock")
    for method in REFERENCE_METHODS:
        probabilities = np.asarray([saved["probabilities"][method] for saved in oof], dtype=float)
        computed = probabilistic_metrics(probabilities, counts_array, recipe["logLossEpsilon"])
        require(all(abs(computed[key] - report["pooledOutOfFold"][method][key]) < 1e-12
                    for key in computed), f"Reference {method} metrics differ from OOF rows")
    return rows, counts_array, report, oof


def categorical_probabilities(fit_rows: list[dict], fit_counts: np.ndarray,
                              predict_rows: list[dict], word_smoothing: float,
                              age_smoothing: float, cell_smoothing: float,
                              prior_pseudocount: float = 1.0) -> np.ndarray:
    """Use only fit-row counts; unseen word/age cells follow the declared backoff."""
    require(len(fit_rows) == len(fit_counts) and len(fit_rows) > 0 and
            fit_counts.shape == (len(fit_rows), 3) and
            np.all(fit_counts >= 0) and np.all(fit_counts.sum(axis=1) == 5) and
            min(word_smoothing, age_smoothing, cell_smoothing, prior_pseudocount) > 0,
            "Invalid categorical fit inputs")
    totals = fit_counts.sum(axis=0).astype(float)
    global_prior = (totals + prior_pseudocount) / (totals.sum() + 3 * prior_pseudocount)
    word_counts: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(3))
    age_counts: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(3))
    cell_counts: dict[tuple[str, str], np.ndarray] = defaultdict(lambda: np.zeros(3))
    for row, vector in zip(fit_rows, fit_counts):
        word_counts[row["targetWord"]] += vector
        age_counts[row["ageBand"]] += vector
        cell_counts[(row["targetWord"], row["ageBand"])] += vector
    probabilities = []
    for row in predict_rows:
        word, age = row["targetWord"], row["ageBand"]
        word_vector, age_vector = word_counts[word], age_counts[age]
        word_prior = (word_vector + word_smoothing * global_prior) / (word_vector.sum() + word_smoothing)
        age_prior = (age_vector + age_smoothing * global_prior) / (age_vector.sum() + age_smoothing)
        backoff = 0.5 * (word_prior + age_prior)
        cell = cell_counts[(word, age)]
        probabilities.append((cell + cell_smoothing * backoff) / (cell.sum() + cell_smoothing))
    return np.asarray(probabilities, dtype=float).reshape(-1, 3)


def choose_smoothing(rows: list[dict], counts: np.ndarray, fit_indices: np.ndarray,
                     validation_indices: np.ndarray, recipe: dict) -> tuple[dict, list[dict]]:
    require(len(set(fit_indices) & set(validation_indices)) == 0 and
            len(fit_indices) > 0 and len(validation_indices) > 0,
            "Inner fit and validation must be disjoint")
    trials = []
    for word, age, cell in itertools.product(recipe["wordSmoothingCandidates"],
                                              recipe["ageSmoothingCandidates"],
                                              recipe["cellSmoothingCandidates"]):
        probabilities = categorical_probabilities(
            [rows[i] for i in fit_indices], counts[fit_indices],
            [rows[i] for i in validation_indices], word, age, cell,
            recipe["globalPriorPseudocountPerClass"])
        trials.append({"wordSmoothing": word, "ageSmoothing": age, "cellSmoothing": cell,
                       **probabilistic_metrics(probabilities, counts[validation_indices],
                                               recipe["logLossEpsilon"])})
    winner = min(trials, key=lambda trial: (trial["perRaterLogLoss"],
                                            trial["wordSmoothing"], trial["ageSmoothing"],
                                            trial["cellSmoothing"]))
    return {key: winner[key] for key in
            ("wordSmoothing", "ageSmoothing", "cellSmoothing")}, trials


def evaluate(rows: list[dict], counts: np.ndarray, reference_oof: list[dict],
             recipe: dict) -> tuple[dict, list[dict]]:
    require(len(rows) == len(reference_oof) == recipe["expectedTrainClips"] and
            counts.shape == (len(rows), 3), "Expected exact paired train rows")
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    predicted = np.full((len(rows), 3), np.nan)
    folds = []
    for fold in range(recipe["outerFolds"]):
        outer_fit = np.asarray([i for i, row in enumerate(rows)
                                if assignments[row["speaker"]] != fold], dtype=int)
        outer_holdout = np.asarray([i for i, row in enumerate(rows)
                                    if assignments[row["speaker"]] == fold], dtype=int)
        fit_speakers = {rows[i]["speaker"] for i in outer_fit}
        holdout_speakers = {rows[i]["speaker"] for i in outer_holdout}
        inner_speakers = inner_validation_speakers(
            fit_speakers, fold, recipe["innerFractionOfOuterTrainSpeakers"], recipe["outerSeed"])
        inner_fit = np.asarray([i for i in outer_fit if rows[i]["speaker"] not in inner_speakers], dtype=int)
        inner_val = np.asarray([i for i in outer_fit if rows[i]["speaker"] in inner_speakers], dtype=int)
        require(fit_speakers.isdisjoint(holdout_speakers) and
                inner_speakers.isdisjoint({rows[i]["speaker"] for i in inner_fit}),
                "Nested speaker leakage")
        selected, trials = choose_smoothing(rows, counts, inner_fit, inner_val, recipe)
        fold_predictions = categorical_probabilities(
            [rows[i] for i in outer_fit], counts[outer_fit],
            [rows[i] for i in outer_holdout], selected["wordSmoothing"],
            selected["ageSmoothing"], selected["cellSmoothing"],
            recipe["globalPriorPseudocountPerClass"])
        predicted[outer_holdout] = fold_predictions
        fit_cells = {(rows[i]["targetWord"], rows[i]["ageBand"]) for i in outer_fit}
        folds.append({"fold": fold, "outerTrainClips": len(outer_fit),
                      "holdoutClips": len(outer_holdout),
                      "outerTrainSpeakerIds": sorted(fit_speakers),
                      "holdoutSpeakerIds": sorted(holdout_speakers),
                      "innerFitSpeakerIds": sorted({rows[i]["speaker"] for i in inner_fit}),
                      "innerValidationSpeakerIds": sorted(inner_speakers),
                      "selectedSmoothing": selected, "innerTrials": trials,
                      "unseenWordAgeHoldoutClips": sum(
                          (rows[i]["targetWord"], rows[i]["ageBand"]) not in fit_cells
                          for i in outer_holdout),
                      "metrics": probabilistic_metrics(fold_predictions, counts[outer_holdout],
                                                       recipe["logLossEpsilon"])})
    require(np.isfinite(predicted).all(), "Missing categorical OOF probabilities")
    oof = [{"id": row["id"], "speaker": row["speaker"],
            "outerFold": reference_oof[i]["outerFold"],
            "fiveRaterCounts": counts[i].tolist(),
            "probabilities": predicted[i].tolist()}
           for i, row in enumerate(rows)]
    summary = {"folds": folds,
            "pooledOutOfFold": probabilistic_metrics(predicted, counts, recipe["logLossEpsilon"]),
            "outOfFoldClips": len(rows), "outOfFoldRaterScores": int(counts.sum()),
            "outOfFoldSpeakers": len(assignments),
            "unseenWordAgeHoldoutClips": sum(fold["unseenWordAgeHoldoutClips"] for fold in folds),
            "probabilityBounds": {"minimum": float(predicted.min()),
                                  "maximum": float(predicted.max()),
                                  "maximumSimplexDeviation": float(np.max(np.abs(predicted.sum(axis=1) - 1)))}}
    return summary, oof


def run(output: Path = OUTPUT) -> dict:
    started = time.perf_counter()
    require(output.resolve() == OUTPUT.resolve() and not output.exists(),
            "Control output must be the unused locked research directory")
    recipe = load_recipe()
    rows, counts, reference, reference_oof = load_train_rows(recipe)
    summary, oof = evaluate(rows, counts, reference_oof, recipe)
    output.mkdir(parents=True)
    write_json(output / "out-of-fold.json", oof)
    source_hashes = {name: sha256_file(HERE / name) for name in (
        "speechocean_r_word_age_negative_control.py", "speechocean_r_label_audit.py",
        "speechocean_r_age_diagnostics.py", "speechocean_r_oof_diagnostics.py",
        "speechocean_r_rater_cv.py", "speechocean_train_cv.py", "speechocean_audit.py")}
    provenance = {"experiment": recipe["experiment"],
                  "recipeSha256": sha256_file(RECIPE),
                  "referenceHashes": REFERENCE_HASHES,
                  "selectedTrainIdsSha256": recipe["selectedTrainIdsSha256"],
                  "sourceMetadataSha256": recipe["sourceMetadataSha256"],
                  "sourceCodeSha256": source_hashes,
                  "authorPartition": "train", "knownAuthorTest": True,
                  **{flag: False for flag in FALSE_FLAGS}}
    write_json(output / "provenance.json", provenance)
    comparison = {}
    for method in REFERENCE_METHODS:
        metrics = reference["pooledOutOfFold"][method]
        comparison[method] = {"reference": metrics,
                              "controlMinusReference": {
                                  key: summary["pooledOutOfFold"][key] - metrics[key]
                                  for key in ("perRaterLogLoss", "perRaterBrier")}}
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": sha256_file(RECIPE),
              "provenanceSha256": sha256_file(output / "provenance.json"),
              "outOfFoldSha256": sha256_file(output / "out-of-fold.json"),
              **summary, "comparisonToSavedV2OnIdenticalRows": comparison,
              "method": recipe["method"],
              "interpretation": "Categorical corpus-confound probe only. Word and age are not proposed product inference inputs or clinically appropriate attributes.",
              "limitations": [
                  "Corpus age bands and canonical prompt words can reflect dataset construction, task difficulty, and rating prevalence; they do not isolate phonetic or acoustic /R/ information.",
                  "Most child-band clips have unanimous top ratings (301 of 349), so class imbalance can dominate pooled scores.",
                  "The five subjective ratings are not verified produced-phone or target-time labels.",
                  "This reuses the same author-training speakers and fixed folds as the saved acoustic results; it is not independent or clinical validation.",
                  "Only a small predeclared smoothing grid was searched on inner speakers; this does not exhaust non-acoustic baselines."],
              "elapsedSeconds": time.perf_counter() - started,
              "authorPartition": "train", "knownAuthorTest": True,
              **{flag: False for flag in FALSE_FLAGS}}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"control": result["pooledOutOfFold"],
                      "comparison": result["comparisonToSavedV2OnIdenticalRows"]},
                     sort_keys=True))
