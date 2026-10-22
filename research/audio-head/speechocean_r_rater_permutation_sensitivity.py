"""Repeated, predeclared train-only speaker-block label-permutation sensitivity.

The twenty runs describe this fixed model-development setting. Their rank is
exploratory and is not a confirmatory p-value or clinical validation.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import time

import numpy as np
import torch

from speechocean_r_rater_cv import (AUTHORITY, V2_RECIPE, evaluate,
                                    load_rater_counts, load_recipe as load_cv_recipe,
                                    load_train_features, require)
from speechocean_r_rater_negative_control import (RECIPE as ONE_RECIPE,
                                                  OUTPUT as ONE_OUTPUT,
                                                  permute_rating_blocks)
from speechocean_train_cv import HERE, outer_speaker_folds, sha256_file, write_json


RECIPE = HERE / "experiments/speechocean-r-rater-permutation-sensitivity-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-rater-permutation-sensitivity-v1"
CV_CODE = HERE / "speechocean_r_rater_cv.py"
PERMUTATION_CODE = HERE / "speechocean_r_rater_negative_control.py"
METRICS = ("perRaterLogLoss", "perRaterBrier")
PREDICTORS = ("wav2vec2-base", "wavlm-base-plus", "trainPrior", "targetWord")
FIRST_SEED = 20260924
SEEDS = list(range(FIRST_SEED, FIRST_SEED + 20))
METRIC_COMPARISON_TOLERANCE = 1e-12


def load_sensitivity_recipe(path: Path = RECIPE) -> tuple[dict, dict, dict]:
    require(path.resolve() == RECIPE.resolve(), "Sensitivity recipe path differs from locked recipe")
    recipe = json.loads(path.read_text())
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-rater-permutation-sensitivity-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("referenceRecipe") ==
                "experiments/speechocean-r-rater-cv-convergence-v2.json" and
            recipe.get("referenceReport") ==
                "outputs/speechocean-r-rater-cv-convergence-v2/report.json" and
            recipe.get("referenceRecipeSha256") ==
                "f17a024acb7837679a0818d7fbd5f617c0b1ba0ec3cb56c127531adabe22c5f5" and
            recipe.get("referenceReportSha256") ==
                "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa" and
            recipe.get("referenceOutOfFoldSha256") ==
                "e1f90b49529ff3daabf546794c672a0c62e3001fe85933eddcf12ef906e7546c" and
            recipe.get("oneControlRecipeSha256") ==
                "34ec27cedcfa662594164b138debe020a299b671a675f6a93df0debabb864802" and
            recipe.get("oneControlReportSha256") ==
                "60e188253454099d4e5467232db83b24f859abf431913f96ac86277280b592cf" and
            recipe.get("cvTrainerSha256") ==
                "89d37ce3879ddfea13ab0a5393faf12793a0430c8e3a22a6e97bf53d69bdcd33" and
            recipe.get("permutationCodeSha256") ==
                "8d7c41b58b23b18352cee9f45b147091ece387b6d4ad7222082bfb8f6c8915b4" and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("expectedRaterScoresPerClip") == 5 and
            recipe.get("permutationSeeds") == SEEDS and
            recipe.get("outputDirectory") ==
                "outputs/speechocean-r-rater-permutation-sensitivity-v1" and
            recipe.get("knownAuthorTest") is True and
            recipe.get("authorTestUsedForSettings") is False and
            all(recipe.get(key) is False for key in AUTHORITY),
            "Sensitivity recipe differs from predeclaration")
    one = json.loads(ONE_RECIPE.read_text())
    require(recipe["permutation"] == one["permutation"] and
            recipe["nestedEvaluation"] == one["nestedEvaluation"],
            "Sensitivity control differs from the original one-run control")
    pins = ((V2_RECIPE, "referenceRecipeSha256"),
            (HERE / recipe["referenceReport"], "referenceReportSha256"),
            (ONE_RECIPE, "oneControlRecipeSha256"),
            (ONE_OUTPUT / "report.json", "oneControlReportSha256"),
            (CV_CODE, "cvTrainerSha256"),
            (PERMUTATION_CODE, "permutationCodeSha256"))
    require(all(sha256_file(path_to_check) == recipe[key]
                for path_to_check, key in pins), "Pinned source, code, or reference SHA-256 mismatch")
    reference = json.loads((HERE / recipe["referenceReport"]).read_text())
    require(reference["outOfFoldSha256"] == recipe["referenceOutOfFoldSha256"] and
            reference["authorPartition"] == "train" and
            reference["authorTestUsedForSettings"] is False and
            all(reference[key] is False for key in AUTHORITY),
            "Pinned reference is not the train-only result")
    return recipe, load_cv_recipe(V2_RECIPE), reference


def summarize_replicates(replicates: list[dict], reference: dict) -> dict:
    require(len(replicates) == len(SEEDS) and
            [row["seed"] for row in replicates] == SEEDS and
            len({row["permutation"]["sourceMappingSha256"] for row in replicates}) == len(SEEDS),
            "Expected twenty distinct ordered permutation mappings")
    result = {}
    for name in PREDICTORS:
        result[name] = {}
        for metric in METRICS:
            values = [row["pooledOutOfFold"][name][metric] for row in replicates]
            baseline = reference[name][metric]
            require(all(np.isfinite(values)), "Nonfinite permutation score")
            result[name][metric] = {
                "minimum": min(values), "median": statistics.median(values),
                "maximum": max(values), "unchangedReference": baseline,
                "replicatesBelowReference": sum(value < baseline - METRIC_COMPARISON_TOLERANCE
                                                for value in values),
                "replicatesEqualReference": sum(abs(value - baseline) <=
                                                METRIC_COMPARISON_TOLERANCE for value in values),
                "replicatesAboveReference": sum(value > baseline + METRIC_COMPARISON_TOLERANCE
                                                for value in values),
            }
    moved = [row["permutation"]["fiveScoreVectorsChanged"] for row in replicates]
    result["fiveScoreVectorsChanged"] = {
        "minimum": min(moved), "median": statistics.median(moved), "maximum": max(moved)}
    return result


def run(output: Path = OUTPUT) -> dict:
    started = time.perf_counter()
    require(output.resolve() == OUTPUT.resolve() and not output.exists(),
            "Sensitivity output must be the unused locked research directory")
    recipe, cv_recipe, reference = load_sensitivity_recipe()
    torch.manual_seed(cv_recipe["outerSeed"])
    torch.set_num_threads(cv_recipe["maxCpuMathThreads"])
    rows, matrices, cache_evidence = load_train_features(cv_recipe)
    original_counts = load_rater_counts(rows, cv_recipe["selectedTrainIdsSha256"])
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      cv_recipe["outerFolds"], cv_recipe["outerSeed"])
    require(all(set(fold["holdoutSpeakerIds"]) ==
                {speaker for speaker, number in assignments.items() if number == fold["fold"]}
                for fold in reference["folds"]), "Outer folds differ from pinned reference")

    replicates = []
    for number, seed in enumerate(SEEDS, start=1):
        permuted, source_indices, diagnostics = permute_rating_blocks(
            rows, original_counts, assignments, seed)
        summary, oof, _heads = evaluate(rows, matrices, permuted, cv_recipe)
        require(all(row["fiveRaterCounts"] == permuted[index].tolist()
                    for index, row in enumerate(oof)) and
                all(rows[index]["id"] == row["id"] for index, row in enumerate(oof)) and
                all(assignments[row["speaker"]] == row["outerFold"] for row in oof) and
                summary["outOfFoldClips"] == 766 and
                summary["outOfFoldRaterScores"] == 3830 and
                summary["outOfFoldSpeakers"] == 124 and
                sorted(source_indices) == list(range(766)),
                "Permutation evaluation did not retain exact train-only rows and ratings")
        replicates.append({"seed": seed, "permutation": diagnostics,
                           "pooledOutOfFold": summary["pooledOutOfFold"],
                           "outerFitIterationsAtLimit": {
                               kind: sum(fold["selection"][kind]["outerFit"]["atIterationLimit"]
                                         for fold in summary["folds"])
                               for kind in ("wav2vec2-base", "wavlm-base-plus")},
                           "selectedHyperparameters": [
                               {"fold": fold["fold"],
                                "wav2vecAlpha": fold["selection"]["wav2vec2-base"]["alpha"],
                                "wavlmAlpha": fold["selection"]["wavlm-base-plus"]["alpha"],
                                "wordSmoothing": fold["selection"]["targetWord"]["smoothing"]}
                               for fold in summary["folds"]]})
        print(f"Completed permutation {number}/{len(SEEDS)} (seed {seed})", flush=True)

    summary = summarize_replicates(replicates, reference["pooledOutOfFold"])
    output.mkdir(parents=True)
    provenance = {"experiment": recipe["experiment"], "recipeSha256": sha256_file(RECIPE),
                  "runnerSha256": sha256_file(Path(__file__)),
                  "sourceArchiveSha256": cv_recipe["sourceArchiveSha256"],
                  "sourceMetadataSha256": cv_recipe["sourceMetadataSha256"],
                  "selectedTrainIdsSha256": cv_recipe["selectedTrainIdsSha256"],
                  "cacheEvidence": cache_evidence,
                  **{key: recipe[key] for key in ("referenceRecipeSha256",
                                                  "referenceReportSha256",
                                                  "referenceOutOfFoldSha256",
                                                  "oneControlRecipeSha256",
                                                  "oneControlReportSha256",
                                                  "cvTrainerSha256", "permutationCodeSha256")},
                  "authorPartition": "train", "knownAuthorTest": True,
                  "authorTestUsedForSettings": False, **AUTHORITY}
    write_json(output / "provenance.json", provenance)
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": sha256_file(RECIPE),
              "provenanceSha256": sha256_file(output / "provenance.json"),
              "permutationSeeds": SEEDS, "permutationReplicates": len(SEEDS),
              "metricComparisonTolerance": METRIC_COMPARISON_TOLERANCE,
              "referencePooledOutOfFold": reference["pooledOutOfFold"],
              "replicates": replicates, "summary": summary,
              "elapsedSeconds": time.perf_counter() - started,
              "interpretation": "Exploratory rank of one already-inspected, unchanged train-side result among twenty predeclared speaker-block rating permutations; no confirmatory p-value, clinical claim, or external validation.",
              "limitations": [
                  "This reference and its single earlier permutation were inspected before the twenty seeds were fixed; ranks are exploratory.",
                  "Singleton equal-size speaker strata retain their feature-label pairings; identical rating vectors can also mask source-ID movement.",
                  "The permutation disrupts prompt, recording, and pronunciation associations together, so it cannot isolate an /R/ production cue.",
                  "All runs reuse one public author-train set and speaker folds; no independent clinical validation or uncertainty from corpus sampling is measured."],
              "authorPartition": "train", "knownAuthorTest": True,
              "authorTestUsedForSettings": False, **AUTHORITY}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"summary": result["summary"],
                      "permutationReplicates": result["permutationReplicates"]}))
