"""Locked research-only final fit of two /R/ rater-distribution heads.

Uses all 766 author-training clips and fixed L2 chosen in prior train-only CV.
It does not load author-test score objects or run test-set inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

import speechocean_r_rater_cv as trainer
from speechocean_train_cv import ENCODERS, HERE, sha256_file, write_json


RECIPE = HERE / "experiments/speechocean-r-rater-final-fit-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-rater-final-fit-v1"
V2_REPORT_SHA256 = "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa"
FALSE_FLAGS = ("authorTestUsedForSettings", "authorTestInferencePerformed",
               "selectionSearchPerformed", "productionEligible", "calibrationEligible",
               "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Final-fit recipe path differs from predeclaration")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    selected = recipe.get("selectionEvidence", {})
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-rater-final-fit-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("classes") == [0, 1, 2] and
            recipe.get("fixedSoftmaxL2") == {kind: 0.1 for kind in ENCODERS} and
            recipe.get("maxOptimizerIterations") == 400 and
            recipe.get("maxCpuMathThreads") == 4 and
            recipe.get("randomSeed") == 20260923 and
            recipe.get("optimizer") ==
                "Torch CPU float64 LBFGS strong_wolfe, zero initialization, max 400 iterations, history 10" and
            recipe.get("outputDirectory") == "outputs/speechocean-r-rater-final-fit-v1" and
            all(recipe.get(key) is False for key in FALSE_FLAGS) and
            selected.get("experiment") == "speechocean-r-rater-cv-convergence-v2" and
            selected.get("reportPath") == "outputs/speechocean-r-rater-cv-convergence-v2/report.json" and
            selected.get("reportSha256") == V2_REPORT_SHA256 and
            selected.get("requiredOuterFolds") == 5 and
            selected.get("expectedSelectedAlphaEachFold") == 0.1,
            "Final-fit recipe differs from locked research-only settings")
    reference = trainer.load_recipe(trainer.V2_RECIPE)
    require(selected.get("recipeSha256") == sha256_file(trainer.V2_RECIPE) and
            all(recipe.get(key) == reference[key] for key in
                ("expectedTrainClips", "expectedTrainSpeakers", "selectedTrainIdsSha256",
                 "sourceArchiveSha256", "sourceMetadataSha256", "inputs", "classes",
                 "maxOptimizerIterations", "maxCpuMathThreads")),
            "Final-fit source, feature, or optimizer pins differ from converged CV")
    return recipe


def verify_cv_selection(recipe: dict, base: Path = HERE) -> dict:
    selected = recipe["selectionEvidence"]
    path = base / selected["reportPath"]
    require(sha256_file(path) == selected["reportSha256"],
            "Pinned v2 selection report SHA-256 mismatch")
    report = json.loads(path.read_text(encoding="utf-8"))
    folds = report.get("folds", [])
    require(report.get("experiment") == selected["experiment"] and
            report.get("recipeSha256") == selected["recipeSha256"] and
            report.get("authorPartition") == "train" and
            report.get("authorTestUsedForSettings") is False and
            report.get("outOfFoldClips") == recipe["expectedTrainClips"] and
            report.get("outOfFoldSpeakers") == recipe["expectedTrainSpeakers"] and
            len(folds) == selected["requiredOuterFolds"] and
            {fold["fold"] for fold in folds} == set(range(5)) and
            all(fold["selection"][kind]["alpha"] == recipe["fixedSoftmaxL2"][kind]
                for fold in folds for kind in ENCODERS),
            "Pinned v2 fold selections differ from fixed final-fit alpha")
    return {"experiment": selected["experiment"],
            "reportSha256": selected["reportSha256"],
            "recipeSha256": selected["recipeSha256"],
            "outerFolds": len(folds),
            "selectedAlphaByFold": {kind: [fold["selection"][kind]["alpha"] for fold in folds]
                                    for kind in ENCODERS}}


def fit_heads(matrices: dict[str, np.ndarray], counts: np.ndarray,
              recipe: dict) -> tuple[dict, dict, dict]:
    require(set(matrices) == set(ENCODERS) and
            counts.ndim == 2 and counts.shape[1] == 3 and
            np.issubdtype(counts.dtype, np.integer) and
            np.all(counts >= 0) and np.all(counts.sum(axis=1) == 5) and
            all(x.ndim == 2 and len(x) == len(counts) and np.isfinite(x).all()
                for x in matrices.values()), "Invalid paired train-only final-fit inputs")
    heads, diagnostics, bounds = {}, {}, {}
    for kind in ENCODERS:
        features = matrices[kind]
        alpha = recipe["fixedSoftmaxL2"][kind]
        head, fit = trainer.fit_softmax(features, counts, alpha,
                                        recipe["maxOptimizerIterations"])
        probabilities = trainer.predict_softmax(head, features)
        expected = probabilities @ np.asarray([0.0, 1.0, 2.0])
        require(probabilities.shape == (len(counts), 3) and
                np.all((probabilities >= 0) & (probabilities <= 1)) and
                np.all((expected >= 0) & (expected <= 2)),
                "Final-fit train probability bounds invalid")
        heads[kind] = head
        diagnostics[kind] = fit
        bounds[kind] = {"minimumProbability": float(probabilities.min()),
                        "maximumProbability": float(probabilities.max()),
                        "maximumSimplexDeviation": float(np.max(np.abs(
                            probabilities.sum(axis=1) - 1))),
                        "expectedRatingMinimum": float(expected.min()),
                        "expectedRatingMaximum": float(expected.max()),
                        "expectedRatingsOutsideZeroToTwo": int(np.count_nonzero(
                            (expected < 0) | (expected > 2)))}
    return heads, diagnostics, bounds


def run(output: Path = OUTPUT) -> dict:
    started = time.perf_counter()
    recipe = load_recipe()
    require(output.resolve() == OUTPUT.resolve(), "Final-fit output differs from locked recipe")
    torch.manual_seed(recipe["randomSeed"])
    torch.set_num_threads(recipe["maxCpuMathThreads"])
    selection = verify_cv_selection(recipe)
    rows, matrices, cache_evidence = trainer.load_train_features(recipe)
    counts = trainer.load_rater_counts(rows, recipe["selectedTrainIdsSha256"])
    require(len(rows) == recipe["expectedTrainClips"] and
            len({row["speaker"] for row in rows}) == recipe["expectedTrainSpeakers"],
            "Expected exact author-training cohort")
    train_ids = sorted(row["id"] for row in rows)
    selected_sha = hashlib.sha256(("\n".join(train_ids) + "\n").encode()).hexdigest()
    require(selected_sha == recipe["selectedTrainIdsSha256"], "Train IDs differ from pin")
    fit_started = time.perf_counter()
    heads, diagnostics, bounds = fit_heads(matrices, counts, recipe)
    fit_seconds = time.perf_counter() - fit_started
    output.mkdir(parents=True, exist_ok=True)
    arrays = {f"{kind}_{field}": np.asarray(value)
              for kind, head in heads.items() for field, value in head.items()}
    np.savez(output / "heads.npz", **arrays)
    provenance = {"experiment": recipe["experiment"],
                  "recipeSha256": sha256_file(RECIPE),
                  "trainerSha256": sha256_file(Path(trainer.__file__)),
                  "finalFitCodeSha256": sha256_file(Path(__file__)),
                  "sourceArchiveSha256": recipe["sourceArchiveSha256"],
                  "sourceMetadataSha256": recipe["sourceMetadataSha256"],
                  "selectedTrainIdsSha256": selected_sha,
                  "cacheEvidence": cache_evidence,
                  "selectionEvidence": selection,
                  "authorPartition": "train", "knownAuthorTest": True,
                  **{flag: False for flag in FALSE_FLAGS}}
    write_json(output / "provenance.json", provenance)
    report = {"experiment": recipe["experiment"],
              "recipeSha256": sha256_file(RECIPE),
              "headsSha256": sha256_file(output / "heads.npz"),
              "provenanceSha256": sha256_file(output / "provenance.json"),
              "fitSeconds": fit_seconds,
              "elapsedSeconds": time.perf_counter() - started,
              "authorPartition": "train", "knownAuthorTest": True,
              "trainClips": len(rows),
              "trainSpeakers": len({row["speaker"] for row in rows}),
              "trainRaterJudgments": int(counts.sum()),
              "fixedAlpha": recipe["fixedSoftmaxL2"],
              "fitDiagnostics": diagnostics,
              "trainProbabilityBounds": bounds,
              "caution": "Train probabilities are numerical checks, not held-out performance or calibration.",
              "limitations": ["Five expert ratings are subjective judgments, not produced-phone truth.",
                              "Whole-utterance frozen features do not localize /R/.",
                              "No independent clinical evaluation or learner-feedback authorization."],
              **{flag: False for flag in FALSE_FLAGS}}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = run()
    print(json.dumps({"trainClips": result["trainClips"],
                      "fitDiagnostics": result["fitDiagnostics"]}, indent=2))
