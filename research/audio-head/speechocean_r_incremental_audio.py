"""Locked, author-train-only incremental full-clip audio probe for five /R/ ratings."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "4"

import numpy as np

from speechocean_audit import FILES
from speechocean_r_capture_confound import design_matrix
from speechocean_r_oof_diagnostics import sha256_file, write_json
from speechocean_r_rater_cv import (AUTHORITY, fit_softmax, load_rater_counts,
                                    load_train_features, predict_softmax,
                                    probabilistic_metrics, require)
from speechocean_r_word_age_negative_control import (load_recipe as load_word_age_recipe,
                                                       load_train_rows)
from speechocean_train_cv import HERE, inner_validation_speakers, outer_speaker_folds

RECIPE = HERE / "experiments/speechocean-r-incremental-audio-v1.json"
RECIPE_SHA256 = "e24a8c70cf1a909eac24c4c3bf453b2981a6f0ec00444f39767a8d1185a4bb3a"
OUTPUT = HERE / "outputs/speechocean-r-incremental-audio-v1"
METHODS = ("captureOnly", "wav2vec2AudioOnly", "wav2vec2Combined",
           "wavlmAudioOnly", "wavlmCombined")
FALSE_FLAGS = (*AUTHORITY, "authorTestUsedForSettings", "authorTestInferencePerformed")


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve() and sha256_file(path) == RECIPE_SHA256,
            "Incremental-audio recipe differs from predeclaration")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-incremental-audio-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("selectedTrainIdsSha256") ==
                "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3" and
            recipe.get("sourceArchiveSha256") ==
                "876c34b828c2ebcc35ba2ff1ba5947d50e6b0162fc4a4af91db0942422b3bdd5" and
            recipe.get("sourceMetadataSha256") == {name: FILES[name][1] for name in
                ("train/utt2spk", "train/spk2age", "resource/scores.json",
                 "resource/scores-detail.json")} and
            recipe.get("featureRecipe") ==
                "experiments/speechocean-r-rater-cv-convergence-v2.json" and
            recipe.get("captureRecipe") ==
                "experiments/speechocean-r-capture-confound-v1.json" and
            recipe.get("captureFeatures") ==
                "outputs/speechocean-r-capture-confound-v1/capture-features.json" and
            recipe.get("captureFeaturesSha256") ==
                "a9139c7ecf8e91c78f388f58a8cd21dae6480cdd6bb4cb38f0bf06da49555f12" and
            recipe.get("captureReport") ==
                "outputs/speechocean-r-capture-confound-v1/report.json" and
            recipe.get("captureReportSha256") ==
                "8e1d6770cff3c467efcbaa15f1b584ab65d496f2ac90c76b11aa33aa091a1461" and
            recipe.get("outerFolds") == 5 and recipe.get("outerSeed") == 20260923 and
            recipe.get("innerFractionOfOuterTrainSpeakers") == .2 and
            recipe.get("classes") == [0, 1, 2] and recipe.get("models") == list(METHODS) and
            recipe.get("softmaxL2Candidates") == [.001, .01, .1] and
            recipe.get("maxOptimizerIterations") == 400 and
            recipe.get("maxCpuMathThreads") == 4 and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("outputDirectory") == "outputs/speechocean-r-incremental-audio-v1" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Incremental-audio recipe fields differ from predeclaration")
    for key in ("captureFeatures", "captureReport"):
        location = HERE / recipe[key]
        require(location.resolve().is_relative_to((HERE / "outputs").resolve()) and
                sha256_file(location) == recipe[key + "Sha256"],
                f"Pinned {key} differs")
    return recipe


def load_inputs(recipe: dict):
    feature_recipe = json.loads((HERE / recipe["featureRecipe"]).read_text())
    require(feature_recipe["selectedTrainIdsSha256"] == recipe["selectedTrainIdsSha256"] and
            feature_recipe["sourceArchiveSha256"] == recipe["sourceArchiveSha256"],
            "Frozen feature recipe cohort differs")
    feature_rows, audio, evidence = load_train_features(feature_recipe)
    feature_counts = load_rater_counts(feature_rows, recipe["selectedTrainIdsSha256"])
    rows, counts, reference_report, reference_oof = load_train_rows(load_word_age_recipe())
    require(len(rows) == len(feature_rows) == recipe["expectedTrainClips"] and
            len({row["speaker"] for row in rows}) == recipe["expectedTrainSpeakers"] and
            np.array_equal(counts, feature_counts) and
            all(all(row[key] == feature[key] for key in ("id", "speaker", "targetWord"))
                for row, feature in zip(rows, feature_rows)),
            "Frozen features differ from exact five-rater author-train rows")
    capture_recipe = json.loads((HERE / recipe["captureRecipe"]).read_text())
    require(capture_recipe["selectedTrainIdsSha256"] == recipe["selectedTrainIdsSha256"] and
            capture_recipe["sourceArchiveSha256"] == recipe["sourceArchiveSha256"],
            "Capture recipe cohort differs")
    capture_evidence = json.loads((HERE / recipe["captureFeatures"]).read_text())
    capture_report = json.loads((HERE / recipe["captureReport"]).read_text())
    require(len(capture_evidence) == len(rows) and
            capture_report["outOfFoldClips"] == len(rows) and
            capture_report["authorPartition"] == "train" and
            all(capture_report.get(flag) is False for flag in FALSE_FLAGS) and
            all(set(item) == {"id", "speaker", "audioSha256", "durationSeconds",
                              "rmsPcm16Div32768"} and
                item["id"] == row["id"] and item["speaker"] == row["speaker"] and
                item["audioSha256"] == feature["audioSha256"]
                for item, row, feature in zip(capture_evidence, rows, feature_rows)),
            "Capture features differ from exact hashed audio source rows")
    capture = np.asarray([[item["durationSeconds"], item["rmsPcm16Div32768"]]
                          for item in capture_evidence], dtype=np.float64)
    require(capture.shape == (len(rows), 2) and np.isfinite(capture).all() and
            np.all(capture[:, 0] > 0) and np.all((capture[:, 1] >= 0) &
                                              (capture[:, 1] <= 1)),
            "Invalid pinned duration/RMS values")
    return rows, counts, capture, audio, reference_report, reference_oof, evidence


def design(rows: list[dict], capture: np.ndarray, audio: dict[str, np.ndarray],
           fit: np.ndarray, predict: np.ndarray, method: str):
    require(method in METHODS and len(fit) > 0 and len(predict) > 0 and
            not set(fit).intersection(predict), "Invalid method or design partitions")
    kind = ("wav2vec2-base" if method.startswith("wav2vec2") else
            "wavlm-base-plus" if method.startswith("wavlm") else None)
    if method == "captureOnly":
        return design_matrix(rows, capture, fit, predict, True)
    acoustic = audio[kind]
    require(acoustic.shape == (len(rows), 768) and np.isfinite(acoustic).all(),
            "Invalid frozen audio feature matrix")
    if method.endswith("AudioOnly"):
        return acoustic[fit], acoustic[predict], []
    control_fit, control_predict, words = design_matrix(rows, capture, fit, predict, True)
    return np.column_stack((control_fit, acoustic[fit])), np.column_stack(
        (control_predict, acoustic[predict])), words


def evaluate(rows, counts, capture, audio, reference_report, reference_oof, recipe):
    require(len(rows) == len(reference_oof) == recipe["expectedTrainClips"] and
            counts.shape == (len(rows), 3), "Paired cohort differs from lock")
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    predictions = {method: np.full((len(rows), 3), np.nan) for method in METHODS}
    folds, heads = [], {}
    for fold in range(recipe["outerFolds"]):
        outer_fit = np.asarray([i for i, row in enumerate(rows)
                                if assignments[row["speaker"]] != fold], dtype=int)
        holdout = np.asarray([i for i, row in enumerate(rows)
                              if assignments[row["speaker"]] == fold], dtype=int)
        fit_speakers = {rows[i]["speaker"] for i in outer_fit}
        holdout_speakers = {rows[i]["speaker"] for i in holdout}
        inner_speakers = inner_validation_speakers(
            fit_speakers, fold, recipe["innerFractionOfOuterTrainSpeakers"],
            recipe["outerSeed"])
        inner_fit = np.asarray([i for i in outer_fit
                                if rows[i]["speaker"] not in inner_speakers], dtype=int)
        inner_val = np.asarray([i for i in outer_fit
                                if rows[i]["speaker"] in inner_speakers], dtype=int)
        pinned = reference_report["folds"][fold]
        require(pinned["fold"] == fold and
                set(pinned["holdoutSpeakerIds"]) == holdout_speakers and
                set(pinned["innerValidationSpeakerIds"]) == inner_speakers and
                all(reference_oof[i]["outerFold"] == fold for i in holdout) and
                fit_speakers.isdisjoint(holdout_speakers) and
                inner_speakers.isdisjoint({rows[i]["speaker"] for i in inner_fit}),
                "Saved nested speaker folds differ or leak")
        models = {}
        for method in METHODS:
            x_fit, x_val, _ = design(rows, capture, audio, inner_fit, inner_val, method)
            trials = []
            for alpha in recipe["softmaxL2Candidates"]:
                head, diagnostics = fit_softmax(
                    x_fit, counts[inner_fit], alpha, recipe["maxOptimizerIterations"])
                probability = predict_softmax(head, x_val)
                trials.append({"alpha": alpha,
                               **probabilistic_metrics(probability, counts[inner_val],
                                                       recipe["logLossEpsilon"]),
                               "optimizer": diagnostics})
            chosen = min(trials, key=lambda item: (item["perRaterLogLoss"], item["alpha"]))
            x_train, x_holdout, words = design(rows, capture, audio, outer_fit, holdout, method)
            head, diagnostics = fit_softmax(
                x_train, counts[outer_fit], chosen["alpha"], recipe["maxOptimizerIterations"])
            probability = predict_softmax(head, x_holdout)
            predictions[method][holdout] = probability
            models[method] = {"selectedAlpha": chosen["alpha"], "innerTrials": trials,
                              "outerFit": diagnostics, "fitWordVocabulary": words,
                              "metrics": probabilistic_metrics(probability, counts[holdout],
                                                              recipe["logLossEpsilon"])}
            for key in ("featureMean", "featureScale", "weights", "intercept"):
                heads[f"{method}_fold{fold}_{key}"] = np.asarray(head[key])
        folds.append({"fold": fold, "outerTrainClips": len(outer_fit),
                      "holdoutClips": len(holdout),
                      "outerTrainSpeakerIds": sorted(fit_speakers),
                      "holdoutSpeakerIds": sorted(holdout_speakers),
                      "innerFitSpeakerIds": sorted({rows[i]["speaker"] for i in inner_fit}),
                      "innerValidationSpeakerIds": sorted(inner_speakers),
                      "models": models})
    require(all(np.isfinite(predictions[method]).all() for method in METHODS),
            "Missing incremental-audio OOF predictions")
    oof = [{"id": row["id"], "speaker": row["speaker"],
            "outerFold": reference_oof[i]["outerFold"],
            "fiveRaterCounts": counts[i].tolist(),
            "probabilities": {method: predictions[method][i].tolist() for method in METHODS}}
           for i, row in enumerate(rows)]
    metrics = {method: probabilistic_metrics(predictions[method], counts,
                                             recipe["logLossEpsilon"]) for method in METHODS}
    delta = {method: {key: metrics[method][key] - metrics["captureOnly"][key]
                      for key in metrics[method]} for method in
             ("wav2vec2Combined", "wavlmCombined")}
    summary = {"folds": folds, "pooledOutOfFold": metrics,
               "combinedMinusCapture": delta, "outOfFoldClips": len(rows),
               "outOfFoldSpeakers": len(assignments),
               "outOfFoldRaterScores": int(counts.sum())}
    return summary, oof, heads


def run(output: Path = OUTPUT):
    require(output.resolve() == OUTPUT.resolve() and not output.exists(),
            "Output must be the unused locked research directory")
    started = time.perf_counter()
    recipe = load_recipe()
    rows, counts, capture, audio, reference_report, reference_oof, evidence = load_inputs(recipe)
    summary, oof, heads = evaluate(rows, counts, capture, audio, reference_report,
                                   reference_oof, recipe)
    old_umask = os.umask(0o077)
    try:
        output.mkdir(mode=0o700)
        write_json(output / "out-of-fold.json", oof)
        np.savez(output / "outer-fold-heads.npz", **heads)
        provenance = {"experiment": recipe["experiment"], "recipeSha256": RECIPE_SHA256,
                      "sourceArchiveSha256": recipe["sourceArchiveSha256"],
                      "sourceMetadataSha256": recipe["sourceMetadataSha256"],
                      "selectedTrainIdsSha256": recipe["selectedTrainIdsSha256"],
                      "captureFeaturesSha256": recipe["captureFeaturesSha256"],
                      "captureReportSha256": recipe["captureReportSha256"],
                      "featureCaches": evidence,
                      "sourceCodeSha256": {name: sha256_file(HERE / name) for name in (
                          "speechocean_r_incremental_audio.py",
                          "speechocean_r_capture_confound.py", "speechocean_r_rater_cv.py",
                          "speechocean_r_word_age_negative_control.py")},
                      "outerFoldHeadsSha256": sha256_file(output / "outer-fold-heads.npz"),
                      "authorPartition": "train", "knownAuthorTest": True,
                      **{flag: False for flag in FALSE_FLAGS}}
        write_json(output / "provenance.json", provenance)
        report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
                  "recipeSha256": RECIPE_SHA256,
                  "provenanceSha256": sha256_file(output / "provenance.json"),
                  "outOfFoldSha256": sha256_file(output / "out-of-fold.json"),
                  **summary, "elapsedSeconds": time.perf_counter() - started,
                  "interpretation": "Exploratory incremental full-clip association only; no localized /R/ production claim.",
                  "limitations": [
                      "The author-training speakers and five folds were previously inspected; this is not independent confirmation.",
                      "Five subjective ratings per clip do not give /R/ timing or verified produced-phone labels.",
                      "Whole-clip frozen features may still encode prompt, speaker, content, or capture conditions beyond duration and RMS.",
                      "Only pooled point estimates are reported; no independent child clinical cohort or refitting uncertainty is evaluated."],
                  "authorPartition": "train", "knownAuthorTest": True,
                  **{flag: False for flag in FALSE_FLAGS}}
        write_json(output / "report.json", report)
        for path in output.iterdir():
            path.chmod(0o600)
        return report
    finally:
        os.umask(old_umask)


if __name__ == "__main__":
    result = run()
    print(json.dumps({"pooledOutOfFold": result["pooledOutOfFold"],
                      "combinedMinusCapture": result["combinedMinusCapture"]},
                     sort_keys=True))
