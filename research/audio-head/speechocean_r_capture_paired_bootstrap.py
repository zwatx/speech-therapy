"""Fixed-OOF speaker bootstrap of capture-control versus acoustic rater heads."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from speechocean_r_oof_diagnostics import (HERE, json_file, per_clip_scores,
                                           require, safe_relative, sha256_file,
                                           speaker_bootstrap, write_json)

RECIPE = HERE / "experiments/speechocean-r-capture-paired-bootstrap-v1.json"
RECIPE_SHA256 = "2249fea88a0c681adc6e43136ef837643e92cc4cbf66388c5b403beb8a1e4b1e"
COMPARISONS = [["wordAgeDurationRmsSoftmax", "wav2vec2-base"],
               ["wordAgeDurationRmsSoftmax", "wavlm-base-plus"]]
PATHS = {
    "referenceReport": "outputs/speechocean-r-rater-cv-convergence-v2/report.json",
    "referenceOutOfFold": "outputs/speechocean-r-rater-cv-convergence-v2/out-of-fold.json",
    "controlReport": "outputs/speechocean-r-capture-confound-v1/report.json",
    "controlOutOfFold": "outputs/speechocean-r-capture-confound-v1/out-of-fold.json",
}
PINS = {
    "referenceReportSha256": "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa",
    "referenceOutOfFoldSha256": "e1f90b49529ff3daabf546794c672a0c62e3001fe85933eddcf12ef906e7546c",
    "controlReportSha256": "8e1d6770cff3c467efcbaa15f1b584ab65d496f2ac90c76b11aa33aa091a1461",
    "controlOutOfFoldSha256": "c830ad77cd0b6e09cacb9f6b6be2d723d19b62ef4c5a358d70e19fd5b57b4047",
}
FALSE_FLAGS = ("modelFitPerformed", "modelSelectionPerformed", "authorTestInferencePerformed",
               "productionEligible", "calibrationEligible", "learnerFeedbackEligible",
               "clinicalUseEligible", "clinicalReliabilityEstablished", "authorTestUsedForSettings")


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve() and sha256_file(path) == RECIPE_SHA256,
            "Capture bootstrap recipe differs from predeclaration")
    recipe = json_file(path)
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-capture-paired-bootstrap-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(key) == value for key, value in {**PATHS, **PINS}.items()) and
            recipe.get("expectedClips") == 766 and recipe.get("expectedSpeakers") == 124 and
            recipe.get("metric") ==
                "Equal-clip mean of five-rater natural-log loss; capture control minus acoustic head" and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("bootstrap") == {"unit": "speaker", "seed": 20260924,
                                        "resamples": 2000, "percentiles": [2.5, 97.5],
                                        "comparisons": COMPARISONS} and
            recipe.get("outputDirectory") == "outputs/speechocean-r-capture-paired-bootstrap-v1" and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Capture bootstrap settings differ from predeclaration")
    return recipe


def load_paired_inputs(recipe: dict, base: Path = HERE):
    values = {}
    for key, relative in PATHS.items():
        path = safe_relative(base, recipe[key])
        require(sha256_file(path) == recipe[f"{key}Sha256"], f"Pinned {key} SHA-256 mismatch")
        values[key] = json_file(path)
    acoustic, capture = values["referenceReport"], values["controlReport"]
    require(acoustic.get("experiment") == "speechocean-r-rater-cv-convergence-v2" and
            capture.get("experiment") == "speechocean-r-capture-confound-v1" and
            acoustic.get("outOfFoldSha256") == recipe["referenceOutOfFoldSha256"] and
            capture.get("outOfFoldSha256") == recipe["controlOutOfFoldSha256"] and
            acoustic.get("authorPartition") == capture.get("authorPartition") == "train" and
            acoustic.get("outOfFoldClips") == capture.get("outOfFoldClips") == 766 and
            acoustic.get("outOfFoldSpeakers") == capture.get("outOfFoldSpeakers") == 124 and
            acoustic.get("authorTestUsedForSettings") is False and
            capture.get("authorTestUsedForSettings") is False and
            all(acoustic.get(flag) is False and capture.get(flag) is False
                for flag in ("productionEligible", "calibrationEligible",
                             "learnerFeedbackEligible", "clinicalUseEligible",
                             "clinicalReliabilityEstablished")),
            "Pinned reports are not paired train-only research results")
    return (values["referenceOutOfFold"], values["controlOutOfFold"], acoustic, capture)


def compare_rows(acoustic_rows: list[dict], capture_rows: list[dict],
                 acoustic: dict, capture: dict, recipe: dict):
    require(len(acoustic_rows) == len(capture_rows) == recipe["expectedClips"],
            "Paired OOF row count differs from lock")
    for original, control in zip(acoustic_rows, capture_rows):
        require(all(original.get(key) == control.get(key)
                    for key in ("id", "speaker", "outerFold", "fiveRaterCounts")) and
                set(original.get("probabilities", {})) ==
                    {"wav2vec2-base", "wavlm-base-plus", "trainPrior", "targetWord"} and
                set(control.get("probabilities", {})) ==
                    {"wordAgeSoftmax", "wordAgeDurationRmsSoftmax"},
                "Capture and acoustic OOF rows differ")
    speakers = [row["speaker"] for row in acoustic_rows]
    require(len(set(speakers)) == recipe["expectedSpeakers"] and
            len({row["id"] for row in acoustic_rows}) == len(acoustic_rows) and
            len({(row["speaker"], row["outerFold"]) for row in acoustic_rows}) ==
                len(set(speakers)), "OOF speaker or clip identity differs")
    counts = np.asarray([row["fiveRaterCounts"] for row in acoustic_rows], dtype=np.int64)
    loss = {}
    for name in ("wordAgeDurationRmsSoftmax", "wav2vec2-base", "wavlm-base-plus"):
        source = capture_rows if name == "wordAgeDurationRmsSoftmax" else acoustic_rows
        probabilities = np.asarray([row["probabilities"][name] for row in source],
                                   dtype=np.float64)
        loss[name] = per_clip_scores(probabilities, counts, recipe["logLossEpsilon"])[0]
        expected = (capture["pooledOutOfFold"][name]["perRaterLogLoss"]
                    if name == "wordAgeDurationRmsSoftmax"
                    else acoustic["pooledOutOfFold"][name]["perRaterLogLoss"])
        require(abs(float(loss[name].mean()) - expected) < 1e-10,
                f"Saved {name} loss differs from paired OOF rows")
    return loss, speakers


def run(output: Path | None = None):
    recipe = load_recipe()
    destination = safe_relative(HERE, recipe["outputDirectory"])
    require(output is None or output.resolve() == destination.resolve(),
            "Bootstrap output differs from locked destination")
    require(not destination.exists(), "Bootstrap output already exists")
    acoustic_rows, capture_rows, acoustic, capture = load_paired_inputs(recipe)
    scores, speakers = compare_rows(acoustic_rows, capture_rows, acoustic, capture, recipe)
    bootstrap = recipe["bootstrap"]
    comparisons, draws = speaker_bootstrap(
        scores, speakers, COMPARISONS, bootstrap["seed"], bootstrap["resamples"],
        bootstrap["percentiles"])
    report = {"experiment": recipe["experiment"], "recipeSha256": RECIPE_SHA256,
              **PINS, "sourceCodeSha256": sha256_file(Path(__file__)),
              "authorPartition": "train", "knownAuthorTest": True,
              "clips": len(acoustic_rows), "speakers": len(set(speakers)),
              "bootstrapUnit": "whole speaker", "bootstrapResamples": bootstrap["resamples"],
              "bootstrapDrawsSha256": hashlib.sha256(draws.astype("<i4").tobytes()).hexdigest(),
              "differenceDirection": "capture control minus acoustic; positive favors acoustic",
              "comparisons": {name: {key: value for key, value in result.items()
                                     if key != "replicateDifferences"}
                              for name, result in comparisons.items()},
              "limitations": [
                  "Fixed predictions from previously inspected author-training development folds; no independent test or new fitting.",
                  "Speaker resampling omits retraining, model selection, and corpus-sampling uncertainty.",
                  "The subjective ratings, full-file capture features, and whole-utterance acoustic embeddings do not identify /R/ timing or a phonetic error.",
                  "No child speech-sound-disorder validation, calibration, or learner-feedback authority."],
              **{flag: False for flag in FALSE_FLAGS}}
    destination.mkdir(parents=True)
    write_json(destination / "report.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(run()["comparisons"], indent=2, sort_keys=True))
