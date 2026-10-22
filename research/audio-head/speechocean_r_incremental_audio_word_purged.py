"""Train-only incremental audio probe with speaker and exact target-word purges."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "4"

import numpy as np

from speechocean_r_incremental_audio import (FALSE_FLAGS, METHODS, design,
                                             load_inputs, load_recipe as load_base_recipe)
from speechocean_r_oof_diagnostics import sha256_file, write_json
from speechocean_r_rater_cv import (fit_softmax, predict_softmax,
                                    probabilistic_metrics, require)
from speechocean_r_speaker_word_purged import fold_split
from speechocean_train_cv import HERE, outer_speaker_folds

RECIPE = HERE / "experiments/speechocean-r-incremental-audio-word-purged-v1.json"
RECIPE_SHA256 = "15b71f160656ca5942f32f1be356514476a6f28a7058fc85b9d7625d06a24ecf"
OUTPUT = HERE / "outputs/speechocean-r-incremental-audio-word-purged-v1"
PINS = {
    "baseRecipe": ("experiments/speechocean-r-incremental-audio-v1.json",
                   "e24a8c70cf1a909eac24c4c3bf453b2981a6f0ec00444f39767a8d1185a4bb3a"),
    "featureRecipe": ("experiments/speechocean-r-rater-cv-convergence-v2.json",
                      "f17a024acb7837679a0818d7fbd5f617c0b1ba0ec3cb56c127531adabe22c5f5"),
    "captureRecipe": ("experiments/speechocean-r-capture-confound-v1.json",
                      "f20ae1201c516a8189b809ed705bb513a2158ea9da3f2b35fe46ea5e7ca6b376"),
    "captureFeatures": ("outputs/speechocean-r-capture-confound-v1/capture-features.json",
                        "a9139c7ecf8e91c78f388f58a8cd21dae6480cdd6bb4cb38f0bf06da49555f12"),
    "purgeRecipe": ("experiments/speechocean-r-speaker-word-purged-v1.json",
                    "f0572ed99158f6d246382a03d6e598094e6a8319e465dade31b56a2a40c88be2"),
    "purgeReport": ("outputs/speechocean-r-speaker-word-purged-v1/report.json",
                    "fdce392dbd1d9ff058bd63066d787199f9adbef94d2ca466e248f2c43fdcca6d"),
}


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve() and sha256_file(path) == RECIPE_SHA256,
            "Word-purged incremental recipe differs from predeclaration")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-incremental-audio-word-purged-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            recipe.get("selectedTrainIdsSha256") ==
                "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3" and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("expectedRaterScores") == 3830 and
            recipe.get("outerFolds") == 5 and recipe.get("outerSeed") == 20260923 and
            recipe.get("innerFractionOfOuterTrainSpeakers") == .2 and
            recipe.get("models") == list(METHODS) and
            recipe.get("softmaxL2Candidates") == [.001, .01, .1] and
            recipe.get("maxOptimizerIterations") == 400 and
            recipe.get("maxCpuMathThreads") == 4 and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("outputDirectory") ==
                "outputs/speechocean-r-incremental-audio-word-purged-v1" and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Word-purged incremental settings differ from predeclaration")
    for key, (relative, digest) in PINS.items():
        require(recipe.get(key) == relative and recipe.get(key + "Sha256") == digest,
                f"{key} path or hash differs from predeclaration")
        location = HERE / relative
        require(location.resolve().is_relative_to(HERE.resolve()) and
                sha256_file(location) == digest, f"Pinned {key} SHA-256 mismatch")
    return recipe


def load_verified_inputs(recipe: dict):
    # Verify the upstream feature recipe bytes before its mutable cache pins are read.
    base = load_base_recipe()
    require(base["selectedTrainIdsSha256"] == recipe["selectedTrainIdsSha256"] and
            base["featureRecipe"] == recipe["featureRecipe"] and
            base["captureRecipe"] == recipe["captureRecipe"] and
            base["captureFeatures"] == recipe["captureFeatures"],
            "Base source recipe differs from word-purged declaration")
    rows, counts, capture, audio, reference_report, reference_oof, evidence = load_inputs(base)
    purge_report = json.loads((HERE / recipe["purgeReport"]).read_text(encoding="utf-8"))
    require(purge_report.get("experiment") == "speechocean-r-speaker-word-purged-v1" and
            purge_report.get("recipeSha256") == recipe["purgeRecipeSha256"] and
            purge_report.get("outOfFoldClips") == len(rows) and
            purge_report.get("outOfFoldSpeakers") == recipe["expectedTrainSpeakers"] and
            purge_report.get("outOfFoldRaterScores") == recipe["expectedRaterScores"] and
            purge_report.get("authorPartition") == "train" and
            purge_report.get("authorTestInferencePerformed") is False,
            "Pinned word-purge report differs from author-train cohort")
    return rows, counts, capture, audio, reference_report, reference_oof, evidence, purge_report


def evaluate(rows, counts, capture, audio, reference_oof, purge_report, recipe):
    require(len(rows) == len(reference_oof) == recipe["expectedTrainClips"] and
            len({row["id"] for row in rows}) == len(rows) and
            counts.shape == (len(rows), 3) and np.all(counts.sum(axis=1) == 5),
            "Expected exact paired author-train rows")
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    require(len(assignments) == recipe["expectedTrainSpeakers"] and
            all(item["outerFold"] == assignments[row["speaker"]]
                for item, row in zip(reference_oof, rows)),
            "Saved speaker fold assignment differs")
    predictions = {method: np.full((len(rows), 3), np.nan) for method in METHODS}
    folds, heads = [], {}
    for fold in range(recipe["outerFolds"]):
        split = fold_split(rows, assignments, fold, recipe)
        outer_fit, holdout = split["outerFit"], split["outerHoldout"]
        inner_fit, inner_val = split["innerFit"], split["innerValidation"]
        expected = purge_report["folds"][fold]
        for key, split_key in (("holdoutClips", "outerHoldout"),
                               ("outerCandidateClips", "outerCandidates"),
                               ("outerPurgedClips", "outerRemoved"),
                               ("outerFitClips", "outerFit"),
                               ("innerCandidateClips", "innerCandidates"),
                               ("innerPurgedClips", "innerRemoved"),
                               ("innerFitClips", "innerFit"),
                               ("innerValidationClips", "innerValidation")):
            require(expected[key] == len(split[split_key]),
                    f"Pinned word-purge {key} differs for fold {fold}")
        for fit, validation in ((outer_fit, holdout), (inner_fit, inner_val)):
            require({rows[i]["speaker"] for i in fit}.isdisjoint(
                        {rows[i]["speaker"] for i in validation}) and
                    {rows[i]["targetWord"] for i in fit}.isdisjoint(
                        {rows[i]["targetWord"] for i in validation}),
                    "Speaker or canonical target-word leakage")
        selected = {}
        for method in METHODS:
            x_fit, x_val, _ = design(rows, capture, audio, inner_fit, inner_val, method)
            trials = []
            for alpha in recipe["softmaxL2Candidates"]:
                head, diagnostics = fit_softmax(
                    x_fit, counts[inner_fit], alpha, recipe["maxOptimizerIterations"])
                p = predict_softmax(head, x_val)
                trials.append({"alpha": alpha,
                               **probabilistic_metrics(p, counts[inner_val],
                                                       recipe["logLossEpsilon"]),
                               "optimizer": diagnostics})
            choice = min(trials, key=lambda item: (item["perRaterLogLoss"], item["alpha"]))
            x_train, x_holdout, words = design(rows, capture, audio, outer_fit, holdout, method)
            head, diagnostics = fit_softmax(
                x_train, counts[outer_fit], choice["alpha"], recipe["maxOptimizerIterations"])
            p = predict_softmax(head, x_holdout)
            predictions[method][holdout] = p
            selected[method] = {"selectedAlpha": choice["alpha"], "innerTrials": trials,
                                "outerFit": diagnostics, "fitWordVocabulary": words,
                                "metrics": probabilistic_metrics(p, counts[holdout],
                                                                recipe["logLossEpsilon"])}
            for key in ("featureMean", "featureScale", "weights", "intercept"):
                heads[f"{method}_fold{fold}_{key}"] = np.asarray(head[key])
        folds.append({"fold": fold, "holdoutClips": len(holdout),
                      "outerCandidateClips": len(split["outerCandidates"]),
                      "outerPurgedClips": len(split["outerRemoved"]),
                      "outerFitClips": len(outer_fit),
                      "outerFitSpeakers": len({rows[i]["speaker"] for i in outer_fit}),
                      "innerCandidateClips": len(split["innerCandidates"]),
                      "innerPurgedClips": len(split["innerRemoved"]),
                      "innerFitClips": len(inner_fit),
                      "innerValidationClips": len(inner_val),
                      "outerFitRaterScoreCounts": {str(k): int(counts[outer_fit, k].sum())
                                                   for k in range(3)},
                      "models": selected})
    require(all(np.isfinite(predictions[method]).all() for method in METHODS),
            "Missing word-purged OOF prediction")
    oof = [{"id": row["id"], "speaker": row["speaker"],
            "outerFold": reference_oof[i]["outerFold"],
            "fiveRaterCounts": counts[i].tolist(),
            "probabilities": {method: predictions[method][i].tolist() for method in METHODS}}
           for i, row in enumerate(rows)]
    pooled = {method: probabilistic_metrics(predictions[method], counts,
                                            recipe["logLossEpsilon"]) for method in METHODS}
    delta = {method: {key: pooled[method][key] - pooled["captureOnly"][key]
                      for key in pooled[method]} for method in
             ("wav2vec2Combined", "wavlmCombined")}
    return {"folds": folds, "pooledOutOfFold": pooled,
            "combinedMinusCapture": delta, "outOfFoldClips": len(rows),
            "outOfFoldSpeakers": len(assignments),
            "outOfFoldRaterScores": int(counts.sum())}, oof, heads


def run(output: Path = OUTPUT):
    require(output.resolve() == OUTPUT.resolve() and not output.exists(),
            "Output must be the unused locked word-purged research directory")
    started = time.perf_counter()
    recipe = load_recipe()
    rows, counts, capture, audio, _reference_report, reference_oof, evidence, purge_report = (
        load_verified_inputs(recipe))
    summary, oof, heads = evaluate(rows, counts, capture, audio, reference_oof,
                                   purge_report, recipe)
    old_umask = os.umask(0o077)
    try:
        output.mkdir(mode=0o700)
        write_json(output / "out-of-fold.json", oof)
        np.savez(output / "outer-fold-heads.npz", **heads)
        provenance = {"experiment": recipe["experiment"], "recipeSha256": RECIPE_SHA256,
                      "inputSha256": {key: digest for key, (_, digest) in PINS.items()},
                      "selectedTrainIdsSha256": recipe["selectedTrainIdsSha256"],
                      "featureCaches": evidence,
                      "sourceCodeSha256": {name: sha256_file(HERE / name) for name in (
                          "speechocean_r_incremental_audio_word_purged.py",
                          "speechocean_r_incremental_audio.py",
                          "speechocean_r_speaker_word_purged.py")},
                      "outerFoldHeadsSha256": sha256_file(output / "outer-fold-heads.npz"),
                      "authorPartition": "train", "knownAuthorTest": True,
                      **{flag: False for flag in FALSE_FLAGS}}
        write_json(output / "provenance.json", provenance)
        inner = [trial["optimizer"] for fold in summary["folds"]
                 for model in fold["models"].values() for trial in model["innerTrials"]]
        chosen = [next(trial["optimizer"] for trial in model["innerTrials"]
                       if trial["alpha"] == model["selectedAlpha"])
                  for fold in summary["folds"] for model in fold["models"].values()]
        outer = [model["outerFit"] for fold in summary["folds"]
                 for model in fold["models"].values()]
        report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
                  "recipeSha256": RECIPE_SHA256,
                  "provenanceSha256": sha256_file(output / "provenance.json"),
                  "outOfFoldSha256": sha256_file(output / "out-of-fold.json"),
                  **summary, "innerFitCount": len(inner),
                  "innerFitsAtIterationLimit": sum(item["atIterationLimit"] for item in inner),
                  "selectedInnerFitsAtIterationLimit": sum(item["atIterationLimit"] for item in chosen),
                  "outerFitCount": len(outer),
                  "outerFitsAtIterationLimit": sum(item["atIterationLimit"] for item in outer),
                  "elapsedSeconds": time.perf_counter() - started,
                  "limitations": [
                      "Previously inspected author-training speakers and target words; no independent validation.",
                      "Word purging removes many fit clips and changes their class mix; differences from the speaker-only experiment do not isolate lexical reliance.",
                      "Five subjective ratings per clip provide no /R/ timing or verified produced-phone label.",
                      "Whole-clip features can retain prompt, speaker, and capture cues; no clinical child cohort or refitting uncertainty is evaluated."],
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
