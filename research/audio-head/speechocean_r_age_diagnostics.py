"""Descriptive child/adult slices of locked author-train /R/ rater OOF results.

No model is fit, selected, or evaluated on the published author test here.
Corpus age bands are not a child speech-sound-disorder validation cohort.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from speechocean_audit import FILES, mapping, pinned_bytes
from speechocean_r_oof_diagnostics import (
    HERE, METHODS, load_predictions, per_clip_scores, require, safe_relative,
    sha256_file, write_json,
)


RECIPE = HERE / "experiments/speechocean-r-age-diagnostics-v1.json"
METADATA = HERE / "outputs/speechocean762-metadata-v1"
FALSE_FLAGS = ("modelFitPerformed", "modelSelectionPerformed", "productionEligible",
               "calibrationEligible", "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished", "authorTestUsedForSettings")


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve(), "Age diagnostic recipe path differs from lock")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-age-diagnostics-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            recipe.get("inputReportSha256") ==
                "6464b90cda8f10c9b75324edbf1b4bc459f781e71ea61bad2c2e0766d1bdecaa" and
            recipe.get("inputOutOfFoldSha256") ==
                "e1f90b49529ff3daabf546794c672a0c62e3001fe85933eddcf12ef906e7546c" and
            recipe.get("inputReport") ==
                "outputs/speechocean-r-rater-cv-convergence-v2/report.json" and
            recipe.get("inputOutOfFold") ==
                "outputs/speechocean-r-rater-cv-convergence-v2/out-of-fold.json" and
            recipe.get("ageMap") == "train/spk2age" and
            recipe.get("ageBands") == {"child": "age <= 15", "adult": "age >= 19"} and
            recipe.get("expectedBandClips") == {"child": 349, "adult": 417} and
            recipe.get("expectedClips") == 766 and recipe.get("expectedSpeakers") == 124 and
            recipe.get("methods") == list(METHODS) and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("outputDirectory") == "outputs/speechocean-r-age-diagnostics-v1" and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Age diagnostic recipe differs from predeclaration")
    return recipe


def age_band(age: int) -> str:
    require(type(age) is int and age >= 0, "Invalid corpus age")
    if age <= 15:
        return "child"
    require(age >= 19, "Unspecified corpus age band")
    return "adult"


def summarize(rows: list[dict], ages: dict[str, int], recipe: dict) -> dict:
    require(len(rows) == recipe["expectedClips"] and
            len({row["speaker"] for row in rows}) == recipe["expectedSpeakers"] and
            set(row["speaker"] for row in rows) <= set(ages),
            "OOF speakers differ from pinned author-train ages")
    bands = np.asarray([age_band(ages[row["speaker"]]) for row in rows])
    counts = np.asarray([row["fiveRaterCounts"] for row in rows], dtype=np.int64)
    report = {}
    for band in ("child", "adult"):
        selected = bands == band
        require(int(selected.sum()) == recipe["expectedBandClips"][band],
                f"Unexpected {band} clip count")
        selected_counts = counts[selected]
        methods = {}
        for method in METHODS:
            probabilities = np.asarray([row["probabilities"][method] for row in rows],
                                       dtype=np.float64)
            loss, brier = per_clip_scores(probabilities, counts, recipe["logLossEpsilon"])
            methods[method] = {"perRaterLogLoss": float(loss[selected].mean()),
                               "perRaterBrier": float(brier[selected].mean())}
        report[band] = {
            "clips": int(selected.sum()),
            "speakers": len({row["speaker"] for row, keep in zip(rows, selected) if keep}),
            "raterScores": int(selected_counts.sum()),
            "unanimousTwoClips": int(np.count_nonzero(selected_counts[:, 2] == 5)),
            "unanimousZeroClips": int(np.count_nonzero(selected_counts[:, 0] == 5)),
            "mixedClips": int(np.count_nonzero(np.max(selected_counts, axis=1) < 5)),
            "methods": methods,
            "wav2vecMinusPriorLogLoss": (methods["wav2vec2-base"]["perRaterLogLoss"] -
                                        methods["trainPrior"]["perRaterLogLoss"]),
            "wavlmMinusPriorLogLoss": (methods["wavlm-base-plus"]["perRaterLogLoss"] -
                                      methods["trainPrior"]["perRaterLogLoss"]),
        }
    return report


def run(recipe_path: Path = RECIPE) -> dict:
    recipe = load_recipe(recipe_path)
    source_report, rows = load_predictions(HERE, recipe)
    age_text = pinned_bytes(METADATA, recipe["ageMap"])
    require(sha256_file(METADATA / recipe["ageMap"]) == FILES["train/spk2age"][1],
            "Pinned age map SHA-256 mismatch")
    age_strings = mapping(age_text, r"\d{4}", r"\d{1,3}")
    require(len(age_strings) == 125, "Expected full author-train age map")
    ages = {speaker: int(age) for speaker, age in age_strings.items()}
    bands = summarize(rows, ages, recipe)
    for method in METHODS:
        for metric in ("perRaterLogLoss", "perRaterBrier"):
            pooled = sum(bands[band]["clips"] * bands[band]["methods"][method][metric]
                         for band in bands) / len(rows)
            require(abs(pooled - source_report["pooledOutOfFold"][method][metric]) < 1e-10,
                    "Age slices do not recombine to source OOF metric")
    report = {"experiment": recipe["experiment"],
              "recipeSha256": sha256_file(recipe_path),
              "inputReportSha256": recipe["inputReportSha256"],
              "inputOutOfFoldSha256": recipe["inputOutOfFoldSha256"],
              "ageMapSha256": FILES["train/spk2age"][1],
              "authorPartition": "train", "knownAuthorTest": True,
              "clips": len(rows), "ageBands": bands,
              "limitations": [
                  "Saved speaker-disjoint train-side OOF predictions only; no new fit or untouched test.",
                  "Corpus age does not establish a child speech-sound-disorder cohort.",
                  "Age slices are descriptive, with no uncertainty interval or clinical threshold.",
              ],
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
    print(json.dumps({"ageBands": result["ageBands"]}, indent=2, sort_keys=True))
