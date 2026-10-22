"""Exploratory author-train /R/ rater CV with unseen speakers and target words.

Each existing speaker holdout stays intact. Clips with its canonical target words
are removed from that fold's fit set, with the same purge applied for inner
selection. Published author-test rows in the shared cache index are not
selected, fit, or scored here.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import time

import numpy as np
import torch

from speechocean_r_rater_cv import (
    AUTHORITY, V2_RECIPE, choose_softmax, fit_softmax, load_rater_counts,
    load_recipe as load_reference_recipe, load_train_features, predict_softmax,
    prior_probabilities, probabilistic_metrics, require,
)
from speechocean_train_cv import (
    HERE, inner_validation_speakers, outer_speaker_folds, sha256_file, write_json,
)


RECIPE = HERE / "experiments/speechocean-r-speaker-word-purged-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-speaker-word-purged-v1"
METHODS = ("wav2vec2-base", "wavlm-base-plus", "trainPrior")


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Recipe path differs from predeclaration")
    recipe = json.loads(path.read_text())
    reference = load_reference_recipe(V2_RECIPE)
    changed = {"experiment", "purpose", "head", "label", "innerAssignment",
               "outerAssignment", "selectionMetric", "outputDirectory"}
    added = {"authorTestInferencePerformed", "outerPurge", "innerPurge", "baseline"}
    removed = {"targetWordSmoothingCandidates"}
    require(set(recipe) == (set(reference) - removed) | added and
            all(recipe[key] == reference[key] for key in reference
                if key not in changed | removed) and
            recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-speaker-word-purged-v1" and
            recipe.get("purpose") ==
                "Exploratory author-train stress test of unseen speakers and canonical /R/ target words" and
            recipe.get("outerAssignment") ==
                "Reuse speaker assignment from speechocean-r-rater-cv-convergence-v2" and
            recipe.get("head") ==
                "Linear softmax on fit-standardized frozen full-clip pooled features with L2 weight penalty and unpenalized intercept" and
            recipe.get("label") ==
                "Five individual rater scores per clip represented as a three-class empirical distribution" and
            recipe.get("outerPurge") ==
                "Hold out all clips of the assigned speakers; remove from outer fit every clip whose exact canonical /R/ target word occurs in the heldout clips" and
            recipe.get("innerPurge") ==
                "Within retained outer fit, remove from inner fit every clip whose exact canonical /R/ target word occurs in inner validation clips" and
            recipe.get("innerAssignment") ==
                "Select inner validation speakers from retained outer fit speakers with the existing seeded hash rule" and
            recipe.get("selectionMetric") ==
                "Inner speaker-and-word-disjoint per-rater natural-log loss; lowest candidate breaks ties" and
            recipe.get("baseline") == "Fit-only three-class prior with one pseudocount per class" and
            recipe.get("authorTestInferencePerformed") is False and
            recipe.get("outputDirectory") == "outputs/speechocean-r-speaker-word-purged-v1" and
            all(recipe[key] is False for key in AUTHORITY),
            "Recipe differs from predeclaration")
    return recipe


def purge_split(rows: list[dict], fit: np.ndarray, holdout: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Remove from fit all exact target words occurring in the holdout."""
    require(len(fit) > 0 and len(holdout) > 0 and
            len(set(fit.tolist())) == len(fit) and
            len(set(holdout.tolist())) == len(holdout) and
            set(fit.tolist()).isdisjoint(holdout.tolist()), "Invalid split indices")
    holdout_speakers = {rows[i]["speaker"] for i in holdout}
    holdout_words = {rows[i]["targetWord"] for i in holdout}
    require(all(type(word) is str and word for word in holdout_words) and
            holdout_speakers.isdisjoint({rows[i]["speaker"] for i in fit}),
            "Fit and holdout share speakers or invalid target words")
    retained = np.asarray([i for i in fit if rows[i]["targetWord"] not in holdout_words], dtype=int)
    removed = np.asarray([i for i in fit if rows[i]["targetWord"] in holdout_words], dtype=int)
    require(len(retained) > 0 and
            len(retained) + len(removed) == len(fit) and
            holdout_words.isdisjoint({rows[i]["targetWord"] for i in retained}) and
            holdout_speakers.isdisjoint({rows[i]["speaker"] for i in retained}),
            "Purge did not create speaker-and-word-disjoint fit")
    return retained, removed


def fold_split(rows: list[dict], assignments: dict[str, int], fold: int,
               recipe: dict) -> dict[str, np.ndarray]:
    require(set(assignments) == {row["speaker"] for row in rows},
            "Fold assignments do not cover all speakers")
    outer_holdout = np.asarray([i for i, row in enumerate(rows)
                                if assignments[row["speaker"]] == fold], dtype=int)
    outer_candidates = np.asarray([i for i, row in enumerate(rows)
                                   if assignments[row["speaker"]] != fold], dtype=int)
    outer_fit, outer_removed = purge_split(rows, outer_candidates, outer_holdout)
    fit_speakers = {rows[i]["speaker"] for i in outer_fit}
    inner_speakers = inner_validation_speakers(
        fit_speakers, fold, recipe["innerFractionOfOuterTrainSpeakers"], recipe["outerSeed"])
    inner_validation = np.asarray([i for i in outer_fit
                                   if rows[i]["speaker"] in inner_speakers], dtype=int)
    inner_candidates = np.asarray([i for i in outer_fit
                                   if rows[i]["speaker"] not in inner_speakers], dtype=int)
    inner_fit, inner_removed = purge_split(rows, inner_candidates, inner_validation)
    require(set(outer_fit.tolist()) ==
            set(inner_fit.tolist()) | set(inner_removed.tolist()) | set(inner_validation.tolist()) and
            len(inner_fit) + len(inner_removed) + len(inner_validation) == len(outer_fit),
            "Inner split does not account for retained outer fit")
    return {"outerHoldout": outer_holdout, "outerCandidates": outer_candidates,
            "outerFit": outer_fit, "outerRemoved": outer_removed,
            "innerValidation": inner_validation, "innerCandidates": inner_candidates,
            "innerFit": inner_fit, "innerRemoved": inner_removed}


def evaluate(rows: list[dict], matrices: dict[str, np.ndarray], counts: np.ndarray,
             recipe: dict) -> tuple[dict, list[dict], dict[str, np.ndarray]]:
    require(len(rows) > 0 and len({row["id"] for row in rows}) == len(rows) and
            counts.shape == (len(rows), 3) and np.all(counts.sum(axis=1) == 5) and
            set(matrices) == set(METHODS) - {"trainPrior"} and
            all(x.shape[0] == len(rows) for x in matrices.values()),
            "Invalid paired author-train input")
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    predictions = {name: np.full((len(rows), 3), np.nan) for name in METHODS}
    coverage = np.zeros(len(rows), dtype=int)
    fold_heads = {}
    folds = []
    for fold in range(recipe["outerFolds"]):
        split = fold_split(rows, assignments, fold, recipe)
        fit, holdout = split["outerFit"], split["outerHoldout"]
        inner_fit, inner_val = split["innerFit"], split["innerValidation"]
        coverage[holdout] += 1
        choices = {}
        fold_predictions = {}
        for kind, x in matrices.items():
            alpha, trials = choose_softmax(x, counts, inner_fit, inner_val, recipe)
            head, diagnostics = fit_softmax(x[fit], counts[fit], alpha,
                                            recipe["maxOptimizerIterations"])
            fold_predictions[kind] = predict_softmax(head, x[holdout])
            choices[kind] = {"alpha": alpha, "innerTrials": trials,
                             "outerFit": diagnostics}
            prefix = ("wav2vec" if kind == "wav2vec2-base" else "wavlm") + f"_fold{fold}_"
            for field, value in head.items():
                fold_heads[prefix + field] = np.asarray(value)
        prior = prior_probabilities(counts[fit], recipe["priorPseudocountPerClass"])
        fold_predictions["trainPrior"] = np.tile(prior, (len(holdout), 1))
        for name, value in fold_predictions.items():
            predictions[name][holdout] = value
        folds.append({
            "fold": fold,
            "holdoutClips": len(holdout),
            "holdoutSpeakers": len({rows[i]["speaker"] for i in holdout}),
            "holdoutTargetWords": len({rows[i]["targetWord"] for i in holdout}),
            "outerCandidateClips": len(split["outerCandidates"]),
            "outerPurgedClips": len(split["outerRemoved"]),
            "outerFitClips": len(fit),
            "outerFitSpeakers": len({rows[i]["speaker"] for i in fit}),
            "outerFitTargetWords": len({rows[i]["targetWord"] for i in fit}),
            "outerFitRaterScoreCounts": {str(k): int(counts[fit, k].sum()) for k in range(3)},
            "innerCandidateClips": len(split["innerCandidates"]),
            "innerPurgedClips": len(split["innerRemoved"]),
            "innerFitClips": len(inner_fit),
            "innerValidationClips": len(inner_val),
            "innerFitSpeakers": len({rows[i]["speaker"] for i in inner_fit}),
            "innerValidationSpeakers": len({rows[i]["speaker"] for i in inner_val}),
            "selection": choices,
            "metrics": {name: probabilistic_metrics(value, counts[holdout],
                                                       recipe["logLossEpsilon"])
                        for name, value in fold_predictions.items()},
        })
        print(f"Completed speaker-and-word-purged fold {fold + 1}/{recipe['outerFolds']}", flush=True)
    require(np.all(coverage == 1) and all(np.isfinite(x).all() for x in predictions.values()),
            "Every author-train clip needs exactly one finite heldout prediction")
    oof = [{"id": row["id"], "speaker": row["speaker"],
            "outerFold": assignments[row["speaker"]],
            "fiveRaterCounts": counts[i].tolist(),
            "probabilities": {name: value[i].tolist() for name, value in predictions.items()}}
           for i, row in enumerate(rows)]
    report = {
        "folds": folds,
        "pooledOutOfFold": {name: probabilistic_metrics(value, counts, recipe["logLossEpsilon"])
                              for name, value in predictions.items()},
        "outOfFoldClips": len(rows),
        "outOfFoldRaterScores": int(counts.sum()),
        "outOfFoldSpeakers": len(assignments),
        "individualRaterScoreCounts": {str(k): int(counts[:, k].sum()) for k in range(3)},
    }
    return report, oof, fold_heads


def run() -> dict:
    started = time.perf_counter()
    recipe = load_recipe()
    require(not OUTPUT.exists(), "Output already exists; refusing to overwrite locked experiment")
    torch.manual_seed(recipe["outerSeed"])
    torch.set_num_threads(recipe["maxCpuMathThreads"])
    rows, matrices, cache_evidence = load_train_features(recipe)
    counts = load_rater_counts(rows, recipe["selectedTrainIdsSha256"])
    fitting_started = time.perf_counter()
    summary, oof, heads = evaluate(rows, matrices, counts, recipe)
    fit_seconds = time.perf_counter() - fitting_started
    outer_diagnostics = [fold["selection"][kind]["outerFit"] for fold in summary["folds"]
                         for kind in matrices]
    inner_diagnostics = [trial["fit"] for fold in summary["folds"]
                         for kind in matrices
                         for trial in fold["selection"][kind]["innerTrials"]]
    provenance = {"experiment": recipe["experiment"], "recipeSha256": sha256_file(RECIPE),
                  "sourceArchiveSha256": recipe["sourceArchiveSha256"],
                  "sourceMetadataSha256": recipe["sourceMetadataSha256"],
                  "cacheEvidence": cache_evidence, "authorPartition": "train",
                  "knownAuthorTest": True, "authorTestUsedForSettings": False,
                  "authorTestInferencePerformed": False, **AUTHORITY}
    previous_umask = os.umask(0o077)
    try:
        OUTPUT.mkdir(mode=0o700, parents=True)
        write_json(OUTPUT / "out-of-fold.json", oof)
        np.savez(OUTPUT / "outer-fold-heads.npz", **heads)
        write_json(OUTPUT / "provenance.json", provenance)
    finally:
        os.umask(previous_umask)
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": sha256_file(RECIPE),
              "provenanceSha256": sha256_file(OUTPUT / "provenance.json"),
              "outOfFoldSha256": sha256_file(OUTPUT / "out-of-fold.json"),
              "outerFoldHeadsSha256": sha256_file(OUTPUT / "outer-fold-heads.npz"),
              "metricDefinitions": {"logLoss": "Natural-log loss averaged over all five individual scores per clip",
                                    "brier": recipe["brierDefinition"]},
              "selectionMetric": recipe["selectionMetric"],
              "nestedFitSeconds": fit_seconds,
              "elapsedSeconds": time.perf_counter() - started,
              "outerFitCount": len(outer_diagnostics),
              "outerFitsAtIterationLimit": sum(d["atIterationLimit"] for d in outer_diagnostics),
              "innerFitCount": len(inner_diagnostics),
              "innerFitsAtIterationLimit": sum(d["atIterationLimit"] for d in inner_diagnostics),
              "authorPartition": "train", "knownAuthorTest": True,
              "authorTestUsedForSettings": False, "authorTestInferencePerformed": False,
              **summary,
              "interpretation": "Exploratory stress test of speaker and exact target-word novelty. Purging also changes fit size and composition, so this does not isolate lexical reliance or establish a model winner.",
              "limitations": [
                  "The five ratings are subjective judgments of canonical /R/ positions, not produced-phone truth.",
                  "Only 766 author-train clips are available; purging removes many fit clips and class 1 is rare.",
                  "Whole-utterance pooled features may encode prompt context and recording conditions rather than /R/ articulation.",
                  "The author test was not used; this is not independent or clinical validation."
              ], **AUTHORITY}
    previous_umask = os.umask(0o077)
    try:
        write_json(OUTPUT / "report.json", report)
    finally:
        os.umask(previous_umask)
    require(stat.S_IMODE(OUTPUT.stat().st_mode) == 0o700 and
            all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in OUTPUT.iterdir()),
            "Generated research output must be owner-only")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = run()
    print(json.dumps({"pooledOutOfFold": result["pooledOutOfFold"],
                      "outerFitsAtIterationLimit": result["outerFitsAtIterationLimit"]}))
