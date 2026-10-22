"""Locked author-train cross-age transfer diagnostic for public /R/ ratings.

These corpus age bands and five subjective rater scores are not child clinical
productions or verified /R/ phone targets. Published author test is untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from speechocean_audit import FILES, mapping, pinned_bytes
import speechocean_r_rater_cv as trainer
from speechocean_r_age_diagnostics import age_band
from speechocean_r_rater_final_fit import load_recipe as load_final_recipe
from speechocean_train_cv import ENCODERS, HERE, METADATA, sha256_file, write_json


RECIPE = HERE / "experiments/speechocean-r-cross-age-transfer-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-cross-age-transfer-v1"
SOURCE_RECIPE_SHA = "48c738d934d992d54b4249bf644e1faa86fd75d7672b41eb5b022766281f18ee"
GROUP_PINS = {
    "child": (349, 57, "2e85218d64a0041cdabc809d9a7b27f5937407e3889befabb0357288ce030839",
              "54804cdabbd45ddfcac8ea6e2c367f36d06e81f55edcdd2a6621b8c3a6ca274f"),
    "adult": (417, 67, "47a5c52a6becd51227b95a41f78ba7c5dc0a649b30ad6363aa92e5153d2f2a59",
              "e1be94668fa0491fad06ba62d71f62b5a048cd6d0316e08a654f9de160db310a"),
}
FALSE_FLAGS = ("authorTestUsedForSettings", "authorTestInferencePerformed",
               "selectionSearchPerformed", "productionEligible", "calibrationEligible",
               "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest_names(names: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(set(names))) + "\n").encode()).hexdigest()


def load_recipe(path: Path = RECIPE) -> tuple[dict, dict]:
    require(path.resolve() == RECIPE.resolve(), "Transfer recipe path differs from lock")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-cross-age-transfer-v1" and
            recipe.get("sourceRecipe") == "experiments/speechocean-r-rater-final-fit-v1.json" and
            recipe.get("sourceRecipeSha256") == SOURCE_RECIPE_SHA and
            recipe.get("authorPartition") == "train" and
            recipe.get("ageMap") == "train/spk2age" and
            recipe.get("ageMapSha256") == FILES["train/spk2age"][1] and
            recipe.get("ageBands") == {"child": "age <= 15", "adult": "age >= 19"} and
            recipe.get("groups") == {name: dict(zip(("clips", "speakers", "idsSha256", "speakersSha256"), pin))
                                     for name, pin in GROUP_PINS.items()} and
            recipe.get("directions") == [["adult", "child"], ["child", "adult"]] and
            recipe.get("encoders") == list(ENCODERS) and
            recipe.get("classes") == [0, 1, 2] and
            recipe.get("fixedSoftmaxL2") == 0.1 and
            recipe.get("optimizer") ==
                "Torch CPU float64 LBFGS strong_wolfe, zero initialization, max 400 iterations, history 10" and
            recipe.get("maxOptimizerIterations") == 400 and
            recipe.get("maxCpuMathThreads") == 4 and
            recipe.get("randomSeed") == 20260923 and
            recipe.get("priorPseudocountPerClass") == 1.0 and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("outputDirectory") == "outputs/speechocean-r-cross-age-transfer-v1" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Cross-age transfer recipe differs from predeclaration")
    source_path = HERE / recipe["sourceRecipe"]
    require(sha256_file(source_path) == SOURCE_RECIPE_SHA, "Pinned source recipe SHA-256 mismatch")
    source_recipe = load_final_recipe(source_path)
    require(all(alpha == recipe["fixedSoftmaxL2"] for alpha in source_recipe["fixedSoftmaxL2"].values()) and
            source_recipe["maxOptimizerIterations"] == recipe["maxOptimizerIterations"] and
            source_recipe["authorPartition"] == "train", "Source fit settings differ")
    return recipe, source_recipe


def group_indices(rows: list[dict], ages: dict[str, int], groups: dict) -> dict[str, np.ndarray]:
    require(len(rows) == 766 and len({row["id"] for row in rows}) == 766 and
            len({row["speaker"] for row in rows}) == 124 and
            set(row["speaker"] for row in rows) <= set(ages),
            "Expected exact author-training rows and ages")
    bands = [age_band(ages[row["speaker"]]) for row in rows]
    indices = {band: np.flatnonzero(np.asarray(bands) == band) for band in GROUP_PINS}
    for band, selected in indices.items():
        selected_rows = [rows[int(i)] for i in selected]
        pin = groups[band]
        require(len(selected_rows) == pin["clips"] and
                len({row["speaker"] for row in selected_rows}) == pin["speakers"] and
                digest_names([row["id"] for row in selected_rows]) == pin["idsSha256"] and
                digest_names([row["speaker"] for row in selected_rows]) == pin["speakersSha256"],
                f"{band} author-training cohort differs from pin")
    require(len(set(indices["child"]) & set(indices["adult"])) == 0 and
            len(indices["child"]) + len(indices["adult"]) == len(rows),
            "Age groups overlap or omit train clips")
    return indices


def evaluate_transfer(x: np.ndarray, counts: np.ndarray, fit_indices: np.ndarray,
                      evaluate_indices: np.ndarray, recipe: dict) -> dict:
    require(x.ndim == 2 and len(x) == len(counts) and
            counts.shape == (len(x), 3) and np.issubdtype(counts.dtype, np.integer) and
            np.all(counts >= 0) and np.all(counts.sum(axis=1) == 5) and
            np.isfinite(x).all() and len(fit_indices) >= 2 and
            len(evaluate_indices) >= 1 and
            len(set(fit_indices)) == len(fit_indices) and
            len(set(evaluate_indices)) == len(evaluate_indices) and
            min(fit_indices) >= 0 and min(evaluate_indices) >= 0 and
            max(fit_indices) < len(x) and max(evaluate_indices) < len(x) and
            not (set(fit_indices) & set(evaluate_indices)),
            "Invalid or overlapping transfer inputs")
    head, fit = trainer.fit_softmax(x[fit_indices], counts[fit_indices],
                                    recipe["fixedSoftmaxL2"], recipe["maxOptimizerIterations"])
    predicted = trainer.predict_softmax(head, x[evaluate_indices])
    train_prior = trainer.prior_probabilities(counts[fit_indices],
                                               recipe["priorPseudocountPerClass"])
    baseline = np.repeat(train_prior[None, :], len(evaluate_indices), axis=0)
    model_metrics = trainer.probabilistic_metrics(predicted, counts[evaluate_indices],
                                                   recipe["logLossEpsilon"])
    baseline_metrics = trainer.probabilistic_metrics(baseline, counts[evaluate_indices],
                                                      recipe["logLossEpsilon"])
    return {"fitDiagnostics": fit, "sourceTrainPrior": train_prior.tolist(),
            "head": model_metrics, "sourceTrainPriorBaseline": baseline_metrics,
            "headMinusPriorLogLoss": model_metrics["perRaterLogLoss"] -
                                     baseline_metrics["perRaterLogLoss"]}


def run(output: Path = OUTPUT) -> dict:
    started = time.perf_counter()
    recipe, source = load_recipe()
    require(output.resolve() == OUTPUT.resolve(), "Transfer output differs from lock")
    torch.manual_seed(recipe["randomSeed"])
    torch.set_num_threads(recipe["maxCpuMathThreads"])
    rows, matrices, cache_evidence = trainer.load_train_features(source)
    counts = trainer.load_rater_counts(rows, source["selectedTrainIdsSha256"])
    require(sha256_file(METADATA / recipe["ageMap"]) == recipe["ageMapSha256"],
            "Pinned author-training age map SHA-256 mismatch")
    ages = {speaker: int(age) for speaker, age in mapping(
        pinned_bytes(METADATA, recipe["ageMap"]), r"\d{4}", r"\d{1,3}").items()}
    require(len(ages) == 125, "Expected full author-training age map")
    indices = group_indices(rows, ages, recipe["groups"])
    directions = {}
    for train_band, eval_band in recipe["directions"]:
        direction = f"{train_band}-to-{eval_band}"
        directions[direction] = {
            "trainGroup": train_band, "evaluateGroup": eval_band,
            "trainClips": len(indices[train_band]), "evaluateClips": len(indices[eval_band]),
            "trainSpeakers": recipe["groups"][train_band]["speakers"],
            "evaluateSpeakers": recipe["groups"][eval_band]["speakers"],
            "trainRaterJudgments": int(counts[indices[train_band]].sum()),
            "evaluateRaterJudgments": int(counts[indices[eval_band]].sum()),
            "encoders": {kind: evaluate_transfer(matrix, counts, indices[train_band],
                                                  indices[eval_band], recipe)
                         for kind, matrix in matrices.items()},
        }
    report = {"experiment": recipe["experiment"], "recipeSha256": sha256_file(RECIPE),
              "sourceRecipeSha256": SOURCE_RECIPE_SHA,
              "trainerSha256": sha256_file(Path(trainer.__file__)),
              "codeSha256": sha256_file(Path(__file__)),
              "sourceArchiveSha256": source["sourceArchiveSha256"],
              "sourceMetadataSha256": source["sourceMetadataSha256"],
              "selectedTrainIdsSha256": source["selectedTrainIdsSha256"],
              "ageMapSha256": recipe["ageMapSha256"], "featureCaches": cache_evidence,
              "groups": recipe["groups"], "directions": directions,
              "authorPartition": "train", "knownAuthorTest": True,
              "elapsedSeconds": time.perf_counter() - started,
              "limitations": [
                  "Exploratory transfer on disjoint age groups within one public corpus, not independent child clinical validation.",
                  "Five ratings describe subjective judgments; they do not label the produced /R/ phone or its timing.",
                  "Frozen mean-pooled features cover whole utterances; age, word, speaker, and recording differences may confound transfer.",
                  "Class ceiling is high, especially in the child group; no uncertainty interval or threshold is established.",
                  "Feature-index metadata is parsed for cache integrity; only author-train features and score objects enter the experiment, with no author-test inference.",
                  "Patient recordings and product feedback are excluded."],
              **{flag: False for flag in FALSE_FLAGS}}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = run()
    print(json.dumps({name: {kind: item["headMinusPriorLogLoss"]
                            for kind, item in direction["encoders"].items()}
                      for name, direction in result["directions"].items()}, indent=2))
