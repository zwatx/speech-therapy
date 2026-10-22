"""Paired speaker bootstrap of saved train-only acoustic and word-age OOF results.

The predictions and fitted settings are fixed. Intervals omit model-training
uncertainty, are exploratory after earlier inspection, and have no clinical use.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from speechocean_r_oof_diagnostics import (HERE, json_file, per_clip_scores,
                                           require, safe_relative, sha256_file,
                                           speaker_bootstrap, write_json)


RECIPE = HERE / "experiments/speechocean-r-word-age-paired-bootstrap-v1.json"
FALSE_FLAGS = ("modelFitPerformed", "modelSelectionPerformed", "productionEligible",
               "calibrationEligible", "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished", "authorTestUsedForSettings")
COMPARISONS = [["wav2vec2-base", "wordAge"], ["wavlm-base-plus", "wordAge"]]
PINS = {
    "referenceReportSha256": "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa",
    "referenceOutOfFoldSha256": "e1f90b49529ff3daabf546794c672a0c62e3001fe85933eddcf12ef906e7546c",
    "controlReportSha256": "a886bb88ddef8d4caab57d5c3425694ebe21fc0b2c5d6eb24f33f8c04c4c7980",
    "controlOutOfFoldSha256": "7acc0754f01a825130d4110ccb4f1546cc812088dba7b9398c77c14ecbe8037b",
}
PATHS = {
    "referenceReport": "outputs/speechocean-r-rater-cv-convergence-v2/report.json",
    "referenceOutOfFold": "outputs/speechocean-r-rater-cv-convergence-v2/out-of-fold.json",
    "controlReport": "outputs/speechocean-r-word-age-negative-control-v1/report.json",
    "controlOutOfFold": "outputs/speechocean-r-word-age-negative-control-v1/out-of-fold.json",
}


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Paired-bootstrap recipe path differs from lock")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-word-age-paired-bootstrap-v1" and
            recipe.get("purpose") ==
                "Exploratory fixed-OOF speaker-resampled acoustic-versus-word-age comparison" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(key) == value for key, value in {**PINS, **PATHS}.items()) and
            recipe.get("expectedClips") == 766 and
            recipe.get("expectedSpeakers") == 124 and
            recipe.get("metric") ==
                "Equal-clip mean of five-rater natural-log loss; acoustic minus categorical" and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("bootstrap") == {
                "unit": "speaker", "seed": 20260926, "resamples": 2000,
                "percentiles": [2.5, 97.5], "comparisons": COMPARISONS} and
            recipe.get("outputDirectory") ==
                "outputs/speechocean-r-word-age-paired-bootstrap-v1" and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Paired-bootstrap recipe differs from predeclaration")
    return recipe


def load_paired_inputs(recipe: dict) -> tuple[list[dict], list[dict], dict, dict]:
    values = {}
    for name, path in PATHS.items():
        location = safe_relative(HERE, recipe[name])
        require(sha256_file(location) == recipe[f"{name}Sha256"],
                f"Pinned {name} SHA-256 mismatch")
        values[name] = json_file(location)
    reference, control = values["referenceReport"], values["controlReport"]
    require(reference.get("experiment") == "speechocean-r-rater-cv-convergence-v2" and
            control.get("experiment") == "speechocean-r-word-age-negative-control-v1" and
            reference.get("outOfFoldSha256") == recipe["referenceOutOfFoldSha256"] and
            control.get("outOfFoldSha256") == recipe["controlOutOfFoldSha256"] and
            reference.get("authorPartition") == control.get("authorPartition") == "train" and
            reference.get("outOfFoldClips") == control.get("outOfFoldClips") == 766 and
            reference.get("outOfFoldSpeakers") == control.get("outOfFoldSpeakers") == 124 and
            reference.get("authorTestUsedForSettings") is False and
            control.get("authorTestUsedForSettings") is False and
            all(reference.get(flag) is False and control.get(flag) is False
                for flag in ("productionEligible", "calibrationEligible",
                             "learnerFeedbackEligible", "clinicalUseEligible",
                             "clinicalReliabilityEstablished")),
            "Pinned reports are not train-only research outputs")
    return (values["referenceOutOfFold"], values["controlOutOfFold"],
            reference, control)


def compare_rows(reference_rows: list[dict], control_rows: list[dict],
                 reference: dict, control: dict, recipe: dict) -> tuple[dict, list[str]]:
    require(len(reference_rows) == len(control_rows) == recipe["expectedClips"],
            "OOF row count differs from lock")
    for original, categorical in zip(reference_rows, control_rows):
        require(all(original.get(field) == categorical.get(field)
                    for field in ("id", "speaker", "outerFold", "fiveRaterCounts")) and
                type(categorical.get("probabilities")) is list and
                set(original.get("probabilities", {})) ==
                    {"wav2vec2-base", "wavlm-base-plus", "trainPrior", "targetWord"},
                "Control and reference OOF rows differ")
    speakers = [row["speaker"] for row in reference_rows]
    require(len(set(speakers)) == recipe["expectedSpeakers"] and
            len({row["id"] for row in reference_rows}) == len(reference_rows) and
            len({(row["speaker"], row["outerFold"]) for row in reference_rows}) ==
                len(set(speakers)), "OOF speaker or clip identity differs from lock")
    counts = np.asarray([row["fiveRaterCounts"] for row in reference_rows], dtype=np.int64)
    loss = {}
    for name in ("wav2vec2-base", "wavlm-base-plus", "wordAge"):
        source = control_rows if name == "wordAge" else reference_rows
        probabilities = np.asarray([
            row["probabilities"] if name == "wordAge" else row["probabilities"][name]
            for row in source], dtype=np.float64)
        loss[name] = per_clip_scores(probabilities, counts, recipe["logLossEpsilon"])[0]
        expected = (control["pooledOutOfFold"]["perRaterLogLoss"] if name == "wordAge"
                    else reference["pooledOutOfFold"][name]["perRaterLogLoss"])
        require(abs(float(loss[name].mean()) - expected) < 1e-10,
                f"Saved {name} loss differs from paired OOF rows")
    return loss, speakers


def run(recipe_path: Path = RECIPE) -> dict:
    recipe = load_recipe(recipe_path)
    reference_rows, control_rows, reference, control = load_paired_inputs(recipe)
    loss, speakers = compare_rows(reference_rows, control_rows, reference, control, recipe)
    comparisons, _draws = speaker_bootstrap(
        loss, speakers, COMPARISONS, recipe["bootstrap"]["seed"],
        recipe["bootstrap"]["resamples"], recipe["bootstrap"]["percentiles"])
    report = {"experiment": recipe["experiment"],
              "recipeSha256": sha256_file(recipe_path),
              **{key: recipe[key] for key in PINS},
              "authorPartition": "train", "knownAuthorTest": True,
              "clips": len(reference_rows), "speakers": len(set(speakers)),
              "bootstrapUnit": "speaker", "bootstrapResamples": 2000,
              "differenceDirection": "acoustic minus word+age; negative favors acoustic",
              "comparisons": {name: {key: value for key, value in result.items()
                                     if key != "replicateDifferences"}
                              for name, result in comparisons.items()},
              "limitations": [
                  "Fixed already-inspected train-side OOF predictions only; no new fit or independent test.",
                  "Speaker resampling omits retraining, smoothing-selection, and corpus-sampling uncertainty.",
                  "This descriptive interval does not isolate /R/ phonetics or establish child clinical validity."],
              **{flag: False for flag in FALSE_FLAGS}}
    output = safe_relative(HERE, recipe["outputDirectory"])
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    args = parser.parse_args()
    result = run(args.recipe)
    print(json.dumps(result["comparisons"], indent=2, sort_keys=True))
