"""Exploratory age slices of fixed SpeechOcean /R/ capture and acoustic OOF.

No model fit or author-test inference occurs. Corpus age is a probe of this
public dataset, not a clinical child-speech cohort or a product input.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from speechocean_audit import FILES, mapping, pinned_bytes
from speechocean_r_age_diagnostics import METADATA, age_band
from speechocean_r_capture_paired_bootstrap import (
    COMPARISONS, PATHS, PINS, compare_rows, load_paired_inputs,
)
from speechocean_r_oof_diagnostics import (
    HERE, per_clip_scores, require, safe_relative, sha256_file,
    speaker_bootstrap, write_json,
)

RECIPE = HERE / "experiments/speechocean-r-capture-age-diagnostics-v1.json"
RECIPE_SHA256 = "5c23536a0bf98eb74f60423761c9d71728dc1dd55a1b89e78d358a17fbda0277"
METHODS = ("wordAgeDurationRmsSoftmax", "wav2vec2-base", "wavlm-base-plus")
FALSE_FLAGS = ("modelFitPerformed", "modelSelectionPerformed", "authorTestInferencePerformed",
               "productionEligible", "calibrationEligible", "learnerFeedbackEligible",
               "clinicalUseEligible", "clinicalReliabilityEstablished", "authorTestUsedForSettings")


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve() and sha256_file(path) == RECIPE_SHA256,
            "Capture age recipe differs from lock")
    recipe = json.loads(path.read_text(encoding="utf-8"))
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-capture-age-diagnostics-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(key) == value for key, value in {**PATHS, **PINS}.items()) and
            recipe.get("ageMap") == "train/spk2age" and
            recipe.get("ageMapSha256") == FILES["train/spk2age"][1] and
            recipe.get("expectedClips") == 766 and recipe.get("expectedSpeakers") == 124 and
            recipe.get("expectedBandClips") == {"child": 349, "adult": 417} and
            recipe.get("expectedBandSpeakers") == {"child": 57, "adult": 67} and
            recipe.get("methods") == list(METHODS) and
            recipe.get("metric") ==
                "Equal-clip mean of five-rater natural-log loss and Brier score; capture control minus acoustic head" and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("bootstrap") == {
                "unit": "whole speaker within age band", "seed": 20260926,
                "resamples": 2000, "percentiles": [2.5, 97.5],
                "comparisons": COMPARISONS} and
            recipe.get("outputDirectory") == "outputs/speechocean-r-capture-age-diagnostics-v1" and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Capture age settings differ from lock")
    return recipe


def summarize(acoustic_rows: list[dict], capture_rows: list[dict], ages: dict[str, int],
              recipe: dict, acoustic_report: dict, capture_report: dict) -> dict:
    # The existing pairing check also recomputes all three pooled log losses.
    reference_loss, speakers = compare_rows(acoustic_rows, capture_rows,
                                            acoustic_report, capture_report, recipe)
    require(set(speakers) <= set(ages), "OOF speaker missing from pinned age map")
    counts = np.asarray([row["fiveRaterCounts"] for row in acoustic_rows], dtype=np.int64)
    scores = {}
    for method in METHODS:
        rows = capture_rows if method == "wordAgeDurationRmsSoftmax" else acoustic_rows
        probabilities = np.asarray([row["probabilities"][method] for row in rows],
                                   dtype=np.float64)
        loss, brier = per_clip_scores(probabilities, counts, recipe["logLossEpsilon"])
        source = capture_report if method == "wordAgeDurationRmsSoftmax" else acoustic_report
        require(np.allclose(loss, reference_loss[method], atol=1e-12, rtol=0) and
                abs(float(brier.mean()) - source["pooledOutOfFold"][method]["perRaterBrier"]) < 1e-10,
                f"Saved {method} scores differ from paired rows")
        scores[method] = (loss, brier)

    bands = {}
    for band in ("child", "adult"):
        selected = np.asarray([age_band(ages[speaker]) == band for speaker in speakers])
        selected_speakers = [speaker for speaker, keep in zip(speakers, selected) if keep]
        require(int(selected.sum()) == recipe["expectedBandClips"][band] and
                len(set(selected_speakers)) == recipe["expectedBandSpeakers"][band],
                f"Unexpected {band} age cohort")
        band_scores = {method: (pair[0][selected], pair[1][selected])
                       for method, pair in scores.items()}
        metrics = {method: {"perRaterLogLoss": float(loss.mean()),
                            "perRaterBrier": float(brier.mean())}
                   for method, (loss, brier) in band_scores.items()}
        comparisons = {}
        draw_hashes = {}
        for index, metric in enumerate(("perRaterLogLoss", "perRaterBrier")):
            values = {method: pair[index] for method, pair in band_scores.items()}
            result, draws = speaker_bootstrap(
                values, selected_speakers, COMPARISONS,
                recipe["bootstrap"]["seed"], recipe["bootstrap"]["resamples"],
                recipe["bootstrap"]["percentiles"])
            comparisons[metric] = {key: {name: value for name, value in comparison.items()
                                         if name != "replicateDifferences"}
                                   for key, comparison in result.items()}
            draw_hashes[metric] = hashlib.sha256(draws.astype("<i4").tobytes()).hexdigest()
        require(draw_hashes["perRaterLogLoss"] == draw_hashes["perRaterBrier"],
                "Paired metric bootstraps used different speaker draws")
        bands[band] = {
            "clips": int(selected.sum()), "speakers": len(set(selected_speakers)),
            "raterScores": int(counts[selected].sum()),
            "methods": metrics, "comparisons": comparisons,
            "bootstrapDrawsSha256": draw_hashes["perRaterLogLoss"],
        }
    for method in METHODS:
        source = capture_report if method == "wordAgeDurationRmsSoftmax" else acoustic_report
        for metric in ("perRaterLogLoss", "perRaterBrier"):
            pooled = sum(bands[band]["clips"] * bands[band]["methods"][method][metric]
                         for band in bands) / len(acoustic_rows)
            require(abs(pooled - source["pooledOutOfFold"][method][metric]) < 1e-10,
                    "Age slices do not reconstruct pinned pooled metric")
    return bands


def run() -> dict:
    recipe = load_recipe()
    destination = safe_relative(HERE, recipe["outputDirectory"])
    require(not destination.exists(), "Capture age output already exists")
    acoustic_rows, capture_rows, acoustic_report, capture_report = load_paired_inputs(recipe)
    age_text = pinned_bytes(METADATA, recipe["ageMap"])
    require(sha256_file(METADATA / recipe["ageMap"]) == recipe["ageMapSha256"],
            "Pinned age map SHA-256 mismatch")
    ages = {speaker: int(age) for speaker, age in
            mapping(age_text, r"\d{4}", r"\d{1,3}").items()}
    require(len(ages) == 125, "Unexpected author-train age map")
    bands = summarize(acoustic_rows, capture_rows, ages, recipe,
                      acoustic_report, capture_report)
    report = {
        "experiment": recipe["experiment"], "recipeSha256": RECIPE_SHA256,
        **PINS, "ageMapSha256": recipe["ageMapSha256"],
        "sourceCodeSha256": sha256_file(Path(__file__)),
        "authorPartition": "train", "knownAuthorTest": True,
        "clips": sum(band["clips"] for band in bands.values()),
        "speakers": sum(band["speakers"] for band in bands.values()),
        "bootstrapUnit": "whole speaker within age band",
        "bootstrapResamplesPerBand": recipe["bootstrap"]["resamples"],
        "differenceDirection": "capture control minus acoustic; positive favors acoustic",
        "ageBands": bands,
        "limitations": [
            "Exploratory age slices of previously inspected author-training out-of-fold predictions; no untouched test.",
            "Fixed-prediction speaker intervals omit refitting, model selection, and new-corpus uncertainty.",
            "Corpus age and whole-clip capture features do not establish a child speech-sound-disorder reference cohort or isolate /R/ production.",
            "No target-time validation, clinical threshold, or learner-feedback authority.",
        ],
        **{flag: False for flag in FALSE_FLAGS},
    }
    destination.mkdir(parents=True)
    write_json(destination / "report.json", report)
    return report


if __name__ == "__main__":
    print(json.dumps(run()["ageBands"], indent=2, sort_keys=True))
