"""Train-only /R/ rating control for full-file duration and capture level."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "4"

import numpy as np

from speechocean_r_probe import (ARCHIVE, ARCHIVE_SHA256, AUDIO, read_rating_pcm,
                                 verify_selected_archive_audio)
from speechocean_r_rater_cv import (AUTHORITY, fit_softmax, predict_softmax,
                                    probabilistic_metrics, require)
from speechocean_r_word_age_negative_control import (HERE, load_recipe as load_word_age_recipe,
                                                       load_train_rows)
from speechocean_r_oof_diagnostics import sha256_file, write_json
from speechocean_train_cv import inner_validation_speakers, outer_speaker_folds

RECIPE = HERE / "experiments/speechocean-r-capture-confound-v1.json"
RECIPE_SHA256 = "f20ae1201c516a8189b809ed705bb513a2158ea9da3f2b35fe46ea5e7ca6b376"
OUTPUT = HERE / "outputs/speechocean-r-capture-confound-v1"
METHODS = ("wordAgeSoftmax", "wordAgeDurationRmsSoftmax")
FALSE_FLAGS = (*AUTHORITY, "authorTestUsedForSettings", "authorTestInferencePerformed")


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve() and sha256_file(path) == RECIPE_SHA256,
            "Capture-confound recipe differs from predeclaration")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-capture-confound-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("sourceArchiveSha256") == ARCHIVE_SHA256 and
            recipe.get("selectedTrainIdsSha256") ==
                "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3" and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("outerFolds") == 5 and recipe.get("outerSeed") == 20260923 and
            recipe.get("innerFractionOfOuterTrainSpeakers") == 0.2 and
            recipe.get("softmaxL2Candidates") == [0.001, 0.01, 0.1] and
            recipe.get("maxOptimizerIterations") == 400 and
            recipe.get("models") == list(METHODS) and
            recipe.get("features") == ["canonicalTargetWord", "corpusAgeBand",
                                       "fullClipDurationSeconds", "fullClipRmsPcm16Div32768"] and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("outputDirectory") == "outputs/speechocean-r-capture-confound-v1" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Capture-confound recipe fields differ from predeclaration")
    for key in ("referenceReport", "referenceOutOfFold", "wordAgeReport", "wordAgeOutOfFold"):
        location = HERE / recipe[key]
        require(location.resolve().is_relative_to((HERE / "outputs").resolve()) and
                sha256_file(location) == recipe[f"{key}Sha256"], f"Pinned {key} differs")
    return recipe


def load_inputs(recipe: dict):
    rows, counts, acoustic_report, acoustic_oof = load_train_rows(load_word_age_recipe())
    word_report = json.loads((HERE / recipe["wordAgeReport"]).read_text(encoding="utf-8"))
    word_oof = json.loads((HERE / recipe["wordAgeOutOfFold"]).read_text(encoding="utf-8"))
    require(word_report.get("authorPartition") == "train" and
            word_report.get("outOfFoldSha256") == recipe["wordAgeOutOfFoldSha256"] and
            word_report.get("outOfFoldClips") == len(rows) and
            word_report.get("authorTestUsedForSettings") is False and
            all(word_report.get(flag) is False for flag in AUTHORITY) and
            len(word_oof) == len(rows), "Word+age reference is not pinned train-only OOF")
    for original, categorical in zip(acoustic_oof, word_oof):
        require(all(original.get(key) == categorical.get(key)
                    for key in ("id", "speaker", "outerFold", "fiveRaterCounts")) and
                set(categorical) == {"id", "speaker", "outerFold", "fiveRaterCounts", "probabilities"},
                "Saved word+age and acoustic OOF rows differ")
    word_prob = np.asarray([item["probabilities"] for item in word_oof], dtype=np.float64)
    word_metric = probabilistic_metrics(word_prob, counts, recipe["logLossEpsilon"])
    require(all(abs(word_metric[key] - word_report["pooledOutOfFold"][key]) < 1e-12
                for key in word_metric), "Word+age metric differs from report")
    require(hashlib.sha256(("\n".join(sorted(row["id"] for row in rows)) + "\n").encode()).hexdigest()
            == recipe["selectedTrainIdsSha256"], "Train IDs differ from lock")
    return rows, counts, acoustic_report, acoustic_oof, word_report


def extract_capture_features(rows: list[dict], recipe: dict):
    require(sha256_file(ARCHIVE) == recipe["sourceArchiveSha256"], "Archive SHA-256 mismatch")
    selected = []
    for row in rows:
        path = AUDIO / "WAVE" / f"SPEAKER{row['speaker']}" / f"{row['id']}.WAV"
        require(path.is_file() and path.resolve().is_relative_to((AUDIO / "WAVE").resolve()),
                "Selected train WAV missing or outside corpus")
        selected.append({"audioPath": str(path)})
    archive_hashes = verify_selected_archive_audio(ARCHIVE, AUDIO, selected)
    values, evidence = [], []
    for row, selected_row in zip(rows, selected):
        path = Path(selected_row["audioPath"])
        member = "speechocean762/" + path.relative_to(AUDIO).as_posix()
        samples = read_rating_pcm(path, archive_hashes[member]).numpy().astype(np.float64)
        duration = len(samples) / 16000.0
        rms = float(np.sqrt(np.mean(samples * samples)))
        require(np.isfinite(duration) and np.isfinite(rms) and duration > 0 and 0 <= rms <= 1,
                "Invalid full-clip duration or RMS")
        values.append((duration, rms))
        evidence.append({"id": row["id"], "speaker": row["speaker"],
                         "audioSha256": archive_hashes[member],
                         "durationSeconds": duration, "rmsPcm16Div32768": rms})
    return np.asarray(values, dtype=np.float64), evidence


def design_matrix(rows: list[dict], capture: np.ndarray, fit_indices: np.ndarray,
                  predict_indices: np.ndarray, include_capture: bool):
    require(capture.shape == (len(rows), 2) and np.isfinite(capture).all() and
            len(fit_indices) > 0 and len(predict_indices) > 0 and
            not (set(fit_indices) & set(predict_indices)), "Invalid design partitions")
    words = sorted({rows[i]["targetWord"] for i in fit_indices})
    lookup = {word: j for j, word in enumerate(words)}

    def transform(indices):
        result = np.zeros((len(indices), len(words) + 1 + (2 if include_capture else 0)), dtype=np.float64)
        for j, index in enumerate(indices):
            word = lookup.get(rows[index]["targetWord"])
            if word is not None:
                result[j, word] = 1
            require(rows[index]["ageBand"] in ("child", "adult"), "Unknown age band")
            result[j, len(words)] = float(rows[index]["ageBand"] == "adult")
        if include_capture:
            result[:, -2:] = capture[indices]
        return result

    return transform(fit_indices), transform(predict_indices), words


def evaluate(rows, counts, capture, reference_oof, reference_report, recipe):
    require(len(rows) == len(reference_oof) == recipe["expectedTrainClips"] and
            counts.shape == (len(rows), 3), "Paired cohort differs from lock")
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    predictions = {name: np.full((len(rows), 3), np.nan) for name in METHODS}
    folds, saved_heads = [], {}
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
        pinned_fold = reference_report["folds"][fold]
        require(set(pinned_fold["holdoutSpeakerIds"]) == holdout_speakers and
                set(pinned_fold["innerValidationSpeakerIds"]) == inner_speakers and
                all(reference_oof[i]["outerFold"] == fold for i in outer_holdout) and
                fit_speakers.isdisjoint(holdout_speakers), "Saved speaker folds differ")
        selections = {}
        for name in METHODS:
            include_capture = name == "wordAgeDurationRmsSoftmax"
            x_fit, x_val, _ = design_matrix(rows, capture, inner_fit, inner_val, include_capture)
            trials = []
            for alpha in recipe["softmaxL2Candidates"]:
                head, diagnostics = fit_softmax(x_fit, counts[inner_fit], alpha,
                                                 recipe["maxOptimizerIterations"])
                probability = predict_softmax(head, x_val)
                trials.append({"alpha": alpha,
                               **probabilistic_metrics(probability, counts[inner_val],
                                                       recipe["logLossEpsilon"]),
                               "optimizer": diagnostics})
            chosen = min(trials, key=lambda trial: (trial["perRaterLogLoss"], trial["alpha"]))
            x_train, x_holdout, words = design_matrix(
                rows, capture, outer_fit, outer_holdout, include_capture)
            head, diagnostics = fit_softmax(x_train, counts[outer_fit], chosen["alpha"],
                                             recipe["maxOptimizerIterations"])
            probability = predict_softmax(head, x_holdout)
            predictions[name][outer_holdout] = probability
            selections[name] = {"selectedAlpha": chosen["alpha"], "innerTrials": trials,
                                "outerFit": diagnostics, "fitWordVocabulary": words,
                                "metrics": probabilistic_metrics(probability, counts[outer_holdout],
                                                                 recipe["logLossEpsilon"])}
            for key in ("featureMean", "featureScale", "weights", "intercept"):
                saved_heads[f"{name}_fold{fold}_{key}"] = np.asarray(head[key])
        folds.append({"fold": fold, "outerTrainClips": len(outer_fit),
                      "holdoutClips": len(outer_holdout),
                      "outerTrainSpeakerIds": sorted(fit_speakers),
                      "holdoutSpeakerIds": sorted(holdout_speakers),
                      "innerFitSpeakerIds": sorted({rows[i]["speaker"] for i in inner_fit}),
                      "innerValidationSpeakerIds": sorted(inner_speakers),
                      "models": selections})
    require(all(np.isfinite(value).all() for value in predictions.values()),
            "Missing paired control OOF predictions")
    oof = [{"id": row["id"], "speaker": row["speaker"],
            "outerFold": reference_oof[i]["outerFold"],
            "fiveRaterCounts": counts[i].tolist(),
            "probabilities": {name: predictions[name][i].tolist() for name in METHODS}}
           for i, row in enumerate(rows)]
    summary = {"folds": folds, "pooledOutOfFold": {
        name: probabilistic_metrics(predictions[name], counts, recipe["logLossEpsilon"])
        for name in METHODS}, "outOfFoldClips": len(rows),
        "outOfFoldSpeakers": len(assignments), "outOfFoldRaterScores": int(counts.sum())}
    return summary, oof, saved_heads


def run(output: Path = OUTPUT):
    require(output.resolve() == OUTPUT.resolve() and not output.exists(),
            "Output must be the unused locked research directory")
    started = time.perf_counter()
    recipe = load_recipe()
    rows, counts, acoustic_report, acoustic_oof, word_report = load_inputs(recipe)
    capture, feature_evidence = extract_capture_features(rows, recipe)
    summary, oof, heads = evaluate(rows, counts, capture, acoustic_oof, acoustic_report, recipe)
    output.mkdir(parents=True)
    write_json(output / "capture-features.json", feature_evidence)
    write_json(output / "out-of-fold.json", oof)
    np.savez(output / "outer-fold-heads.npz", **heads)
    source_hashes = {name: sha256_file(HERE / name) for name in (
        "speechocean_r_capture_confound.py", "speechocean_r_word_age_negative_control.py",
        "speechocean_r_rater_cv.py", "speechocean_r_probe.py", "speechocean_train_cv.py")}
    provenance = {"experiment": recipe["experiment"], "recipeSha256": RECIPE_SHA256,
                  "sourceArchiveSha256": recipe["sourceArchiveSha256"],
                  "selectedTrainIdsSha256": recipe["selectedTrainIdsSha256"],
                  "inputSha256": {key: recipe[f"{key}Sha256"] for key in
                                  ("referenceReport", "referenceOutOfFold", "wordAgeReport",
                                   "wordAgeOutOfFold")},
                  "sourceCodeSha256": source_hashes,
                  "captureFeaturesSha256": sha256_file(output / "capture-features.json"),
                  "outerFoldHeadsSha256": sha256_file(output / "outer-fold-heads.npz"),
                  "authorPartition": "train", "knownAuthorTest": True,
                  **{flag: False for flag in FALSE_FLAGS}}
    write_json(output / "provenance.json", provenance)
    compared = {"wordAge": word_report["pooledOutOfFold"]}
    for name in ("wav2vec2-base", "wavlm-base-plus", "trainPrior"):
        compared[name] = acoustic_report["pooledOutOfFold"][name]
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": RECIPE_SHA256,
              "provenanceSha256": sha256_file(output / "provenance.json"),
              "outOfFoldSha256": sha256_file(output / "out-of-fold.json"),
              **summary, "savedReferencePooledOutOfFold": compared,
              "comparison": {name: {reference: {
                  key: metrics[key] - compared[reference][key]
                  for key in ("perRaterLogLoss", "perRaterBrier")}
                  for reference in compared}
                  for name, metrics in summary["pooledOutOfFold"].items()},
              "captureFeatureRanges": {
                  "durationSeconds": [float(capture[:, 0].min()), float(capture[:, 0].max())],
                  "rmsPcm16Div32768": [float(capture[:, 1].min()), float(capture[:, 1].max())]},
              "interpretation": "Exploratory corpus-capture confound probe only; duration and RMS do not isolate /R/ articulation.",
              "limitations": [
                  "All methods use previously inspected author-training speakers and folds; this is not independent validation.",
                  "The paired softmax fits isolate added duration/RMS columns within that model class; comparison with the older word+age control also changes model class.",
                  "Corpus age, canonical word, duration, and RMS can reflect prompt, speaker, or capture conditions and are not proposed product inference inputs.",
                  "Five subjective ratings per clip are neither target-time nor verified produced-phone labels.",
                  "Class imbalance and speaker dependence limit interpretation; no clinical child cohort is evaluated."],
              "elapsedSeconds": time.perf_counter() - started,
              "authorPartition": "train", "knownAuthorTest": True,
              **{flag: False for flag in FALSE_FLAGS}}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"pooledOutOfFold": result["pooledOutOfFold"],
                      "savedReferencePooledOutOfFold": result["savedReferencePooledOutOfFold"]},
                     sort_keys=True))
