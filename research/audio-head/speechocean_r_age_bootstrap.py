"""Descriptive speaker-resampled uncertainty for saved author-train age slices.

This resamples fixed out-of-fold predictions. It does not refit a model, measure
training uncertainty, or validate pronunciation feedback for children.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from speechocean_audit import FILES, mapping, pinned_bytes
from speechocean_r_age_diagnostics import METADATA, age_band
from speechocean_r_oof_diagnostics import (HERE, load_predictions, per_clip_scores,
                                           require, safe_relative, sha256_file,
                                           speaker_bootstrap, write_json)


RECIPE = HERE / "experiments/speechocean-r-age-bootstrap-v1.json"
FALSE_FLAGS = ("modelFitPerformed", "modelSelectionPerformed", "productionEligible",
               "calibrationEligible", "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished", "authorTestUsedForSettings")
METHODS = ("wav2vec2-base", "wavlm-base-plus", "trainPrior")
COMPARISONS = [["wav2vec2-base", "trainPrior"],
               ["wavlm-base-plus", "trainPrior"]]


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Age bootstrap recipe path differs from lock")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-age-bootstrap-v1" and
            recipe.get("purpose") == "Descriptive paired speaker-resampling of fixed author-train age-slice out-of-fold predictions" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            recipe.get("inputReport") ==
                "outputs/speechocean-r-rater-cv-convergence-v2/report.json" and
            recipe.get("inputOutOfFold") ==
                "outputs/speechocean-r-rater-cv-convergence-v2/out-of-fold.json" and
            recipe.get("inputReportSha256") ==
                "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa" and
            recipe.get("inputOutOfFoldSha256") ==
                "e1f90b49529ff3daabf546794c672a0c62e3001fe85933eddcf12ef906e7546c" and
            recipe.get("ageMap") == "train/spk2age" and
            recipe.get("expectedClips") == 766 and
            recipe.get("expectedSpeakers") == 124 and
            recipe.get("expectedBandClips") == {"child": 349, "adult": 417} and
            recipe.get("expectedBandSpeakers") == {"child": 57, "adult": 67} and
            recipe.get("metric") == "Equal-clip per-rater natural-log loss from five saved ratings; first minus prior" and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("bootstrap") == {
                "unit": "speaker within age band", "seed": 20260925,
                "resamples": 2000, "percentiles": [2.5, 97.5],
                "comparisons": COMPARISONS} and
            recipe.get("outputDirectory") == "outputs/speechocean-r-age-bootstrap-v1" and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Age bootstrap recipe differs from predeclaration")
    return recipe


def summarize(rows: list[dict], ages: dict[str, int], recipe: dict) -> dict:
    require(len(rows) == sum(recipe["expectedBandClips"].values()) and
            len({row["speaker"] for row in rows}) ==
                sum(recipe["expectedBandSpeakers"].values()) and
            set(row["speaker"] for row in rows) <= set(ages),
            "Saved OOF speakers differ from pinned age map")
    output = {}
    for band in ("child", "adult"):
        selected = [row for row in rows if age_band(ages[row["speaker"]]) == band]
        speakers = [row["speaker"] for row in selected]
        require(len(selected) == recipe["expectedBandClips"][band] and
                len(set(speakers)) == recipe["expectedBandSpeakers"][band],
                f"Unexpected {band} age cohort")
        counts = np.asarray([row["fiveRaterCounts"] for row in selected], dtype=np.int64)
        losses = {method: per_clip_scores(
            np.asarray([row["probabilities"][method] for row in selected], dtype=np.float64),
            counts, recipe["logLossEpsilon"])[0] for method in METHODS}
        comparisons, draws = speaker_bootstrap(
            losses, speakers, COMPARISONS, recipe["bootstrap"]["seed"],
            recipe["bootstrap"]["resamples"], recipe["bootstrap"]["percentiles"])
        require(draws.shape == (2000, len(set(speakers))) and
                all(np.isfinite(loss).all() for loss in losses.values()),
                "Invalid bootstrap result")
        output[band] = {
            "clips": len(selected), "speakers": len(set(speakers)),
            "raterScores": int(counts.sum()),
            "methodLogLoss": {method: float(loss.mean()) for method, loss in losses.items()},
            "comparisons": {key: {name: value for name, value in result.items()
                                  if name != "replicateDifferences"}
                            for key, result in comparisons.items()}}
    return output


def run(recipe_path: Path = RECIPE) -> dict:
    recipe = load_recipe(recipe_path)
    _source, rows = load_predictions(HERE, recipe)
    age_text = pinned_bytes(METADATA, recipe["ageMap"])
    require(sha256_file(METADATA / recipe["ageMap"]) == FILES["train/spk2age"][1],
            "Pinned age map SHA-256 mismatch")
    ages = {speaker: int(age) for speaker, age in
            mapping(age_text, r"\d{4}", r"\d{1,3}").items()}
    require(len(ages) == 125, "Unexpected author-train age map")
    bands = summarize(rows, ages, recipe)
    report = {"experiment": recipe["experiment"],
              "recipeSha256": sha256_file(recipe_path),
              "inputReportSha256": recipe["inputReportSha256"],
              "inputOutOfFoldSha256": recipe["inputOutOfFoldSha256"],
              "ageMapSha256": FILES["train/spk2age"][1],
              "authorPartition": "train", "knownAuthorTest": True,
              "bootstrapUnit": "speaker within age band",
              "bootstrapResamplesPerBand": recipe["bootstrap"]["resamples"],
              "differenceDirection": "first minus prior; negative favors the acoustic head",
              "ageBands": bands,
              "limitations": [
                  "Fixed saved train-side out-of-fold predictions only; no refitting or independent test.",
                  "Percentile intervals omit training and model-selection uncertainty and do not describe a clinical population.",
                  "The public child age band is not a child speech-sound-disorder reference cohort.",
                  "This is an exploratory follow-up to inspected age-slice results, not a confirmatory interval or model selection."],
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
    print(json.dumps(result["ageBands"], indent=2, sort_keys=True))
