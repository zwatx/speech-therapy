"""Fixed-OOF paired whole-speaker intervals for both incremental audio runs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from speechocean_r_incremental_audio import METHODS
from speechocean_r_oof_diagnostics import (HERE, json_file, per_clip_scores,
                                           require, safe_relative, sha256_file,
                                           speaker_bootstrap, write_json)
from speechocean_train_cv import outer_speaker_folds

RECIPE = HERE / "experiments/speechocean-r-incremental-audio-paired-bootstrap-v1.json"
RECIPE_SHA256 = "3dc7f5e9579e44396e29cc24e1c9e2311046ea63935bda2db1aea59b5f9d56f4"
OUTPUT = HERE / "outputs/speechocean-r-incremental-audio-paired-bootstrap-v1"
COMPARISONS = [["wav2vec2Combined", "captureOnly"],
               ["wavlmCombined", "captureOnly"]]
RUNS = {
    "speakerOnly": {
        "experiment": "speechocean-r-incremental-audio-v1",
        "recipe": "experiments/speechocean-r-incremental-audio-v1.json",
        "recipeSha256": "e24a8c70cf1a909eac24c4c3bf453b2981a6f0ec00444f39767a8d1185a4bb3a",
        "report": "outputs/speechocean-r-incremental-audio-v1/report.json",
        "reportSha256": "ae5d86860f3182376f85e7133398690d496c6a95e94c17bcbe1451a40b004d94",
        "outOfFold": "outputs/speechocean-r-incremental-audio-v1/out-of-fold.json",
        "outOfFoldSha256": "5cbce3fd58ea5993d4b206c4aaba89e7a1eab619fd12fe6aa63556140ae0d3d1",
    },
    "speakerAndWordPurged": {
        "experiment": "speechocean-r-incremental-audio-word-purged-v1",
        "recipe": "experiments/speechocean-r-incremental-audio-word-purged-v1.json",
        "recipeSha256": "15b71f160656ca5942f32f1be356514476a6f28a7058fc85b9d7625d06a24ecf",
        "report": "outputs/speechocean-r-incremental-audio-word-purged-v1/report.json",
        "reportSha256": "2ab0d25fc7b23683e8f554578e401f63a244b0e7fb8a3d72d9e41fc8bfb7dd75",
        "outOfFold": "outputs/speechocean-r-incremental-audio-word-purged-v1/out-of-fold.json",
        "outOfFoldSha256": "163b6dd91730bc0eb077c1e0d9b0dd71dd7bd326c3ef1ee93e5fd6240f9d8a3d",
    },
}
FALSE_FLAGS = ("authorTestUsedForSettings", "authorTestInferencePerformed",
               "modelFitPerformed", "modelSelectionPerformed", "productionEligible",
               "calibrationEligible", "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished")
SOURCE_FALSE_FLAGS = ("authorTestUsedForSettings", "authorTestInferencePerformed",
                      "productionEligible", "calibrationEligible",
                      "learnerFeedbackEligible", "clinicalUseEligible",
                      "clinicalReliabilityEstablished")


def load_recipe(path: Path = RECIPE) -> dict:
    require(path.resolve() == RECIPE.resolve() and sha256_file(path) == RECIPE_SHA256,
            "Incremental paired-bootstrap recipe differs from predeclaration")
    recipe = json_file(path)
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-incremental-audio-paired-bootstrap-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            recipe.get("runs") == RUNS and
            recipe.get("expectedClips") == 766 and
            recipe.get("expectedSpeakers") == 124 and
            recipe.get("expectedRaterScores") == 3830 and
            recipe.get("selectedTrainIdsSha256") ==
                "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3" and
            recipe.get("outerFolds") == 5 and recipe.get("outerSeed") == 20260923 and
            recipe.get("methods") == list(METHODS) and
            recipe.get("comparisons") == COMPARISONS and
            recipe.get("metrics") == ["perRaterLogLoss", "perRaterBrier"] and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("bootstrap") == {"unit": "whole speaker", "seed": 20260928,
                                        "resamples": 10000,
                                        "percentiles": [2.5, 97.5],
                                        "equalClipWeight": True} and
            recipe.get("outputDirectory") ==
                "outputs/speechocean-r-incremental-audio-paired-bootstrap-v1" and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS),
            "Incremental paired-bootstrap settings differ from predeclaration")
    return recipe


def load_inputs(recipe: dict, base: Path = HERE):
    loaded = {}
    for name, pins in recipe["runs"].items():
        values = {}
        for key in ("recipe", "report", "outOfFold"):
            path = safe_relative(base, pins[key])
            require(sha256_file(path) == pins[key + "Sha256"],
                    f"Pinned {name} {key} SHA-256 mismatch")
            if key != "recipe":
                values[key] = json_file(path)
        report, rows = values["report"], values["outOfFold"]
        require(report.get("experiment") == pins["experiment"] and
                report.get("recipeSha256") == pins["recipeSha256"] and
                report.get("outOfFoldSha256") == pins["outOfFoldSha256"] and
                report.get("authorPartition") == "train" and
                report.get("knownAuthorTest") is True and
                report.get("outOfFoldClips") == recipe["expectedClips"] and
                report.get("outOfFoldSpeakers") == recipe["expectedSpeakers"] and
                report.get("outOfFoldRaterScores") == recipe["expectedRaterScores"] and
                all(report.get(flag) is False for flag in SOURCE_FALSE_FLAGS),
                f"Pinned {name} report is not train-only research OOF")
        loaded[name] = (rows, report)
    return loaded


def validate_rows(loaded: dict, recipe: dict):
    baseline = loaded["speakerOnly"][0]
    require(all(type(rows) is list and len(rows) == recipe["expectedClips"]
                for rows, _ in loaded.values()), "Unexpected OOF row count")
    ids, speakers = [], []
    for index, row in enumerate(baseline):
        require(set(row) == {"id", "speaker", "outerFold", "fiveRaterCounts",
                             "probabilities"} and
                type(row["id"]) is str and len(row["id"]) == 9 and
                row["id"].isdigit() and type(row["speaker"]) is str and
                len(row["speaker"]) == 4 and row["speaker"].isdigit() and
                type(row["outerFold"]) is int and
                0 <= row["outerFold"] < recipe["outerFolds"] and
                type(row["fiveRaterCounts"]) is list and
                len(row["fiveRaterCounts"]) == 3 and
                all(type(value) is int and value >= 0
                    for value in row["fiveRaterCounts"]) and
                sum(row["fiveRaterCounts"]) == 5 and
                set(row["probabilities"]) == set(METHODS),
                f"Malformed speaker-only OOF row {index}")
        ids.append(row["id"])
        speakers.append(row["speaker"])
    require(len(set(ids)) == recipe["expectedClips"] and
            len(set(speakers)) == recipe["expectedSpeakers"] and
            hashlib.sha256(("\n".join(sorted(ids)) + "\n").encode()).hexdigest() ==
                recipe["selectedTrainIdsSha256"],
            "Exact 766 author-train IDs or 124 speakers differ")
    assignments = outer_speaker_folds(set(speakers), recipe["outerFolds"],
                                      recipe["outerSeed"])
    require(all(row["outerFold"] == assignments[row["speaker"]] for row in baseline),
            "Speaker-only outer folds differ from seeded assignment")
    for name, (rows, _) in loaded.items():
        for index, (row, original) in enumerate(zip(rows, baseline)):
            require(set(row) == set(original) and
                    all(row[key] == original[key] for key in
                        ("id", "speaker", "outerFold", "fiveRaterCounts")) and
                    set(row["probabilities"]) == set(METHODS),
                    f"{name} OOF identity, ordering, fold, or ratings differ at row {index}")
    return speakers


def score_run(rows: list[dict], report: dict, recipe: dict):
    counts = np.asarray([row["fiveRaterCounts"] for row in rows], dtype=np.int64)
    scores = {metric: {} for metric in recipe["metrics"]}
    for method in METHODS:
        probabilities = np.asarray([row["probabilities"][method] for row in rows],
                                   dtype=np.float64)
        loss, brier = per_clip_scores(probabilities, counts, recipe["logLossEpsilon"])
        for metric, values in (("perRaterLogLoss", loss), ("perRaterBrier", brier)):
            require(abs(float(values.mean()) -
                        report["pooledOutOfFold"][method][metric]) < 1e-10,
                    f"Saved {method} {metric} differs from OOF probabilities")
            scores[metric][method] = values
    fold_deltas = {}
    require(len(report["folds"]) == recipe["outerFolds"],
            "Unexpected source fold count")
    for fold in range(recipe["outerFolds"]):
        indices = np.asarray([i for i, row in enumerate(rows)
                              if row["outerFold"] == fold], dtype=int)
        source = report["folds"][fold]
        require(source["fold"] == fold and source["holdoutClips"] == len(indices),
                "Source fold identity or count differs")
        fold_deltas[str(fold)] = {metric: {} for metric in recipe["metrics"]}
        for metric in recipe["metrics"]:
            for method in METHODS:
                actual = float(scores[metric][method][indices].mean())
                require(abs(actual - source["models"][method]["metrics"][metric]) < 1e-10,
                        f"Source fold {fold} {method} {metric} differs")
            for first, second in COMPARISONS:
                fold_deltas[str(fold)][metric][f"{first} minus {second}"] = float(
                    (scores[metric][first][indices] -
                     scores[metric][second][indices]).mean())
    return scores, fold_deltas


def analyze(loaded: dict, recipe: dict):
    speakers = validate_rows(loaded, recipe)
    results = {}
    common_draws = None
    for name, (rows, report) in loaded.items():
        scores, fold_deltas = score_run(rows, report, recipe)
        intervals = {}
        for metric in recipe["metrics"]:
            comparisons, draws = speaker_bootstrap(
                scores[metric], speakers, COMPARISONS, recipe["bootstrap"]["seed"],
                recipe["bootstrap"]["resamples"], recipe["bootstrap"]["percentiles"])
            if common_draws is None:
                common_draws = draws
            else:
                require(np.array_equal(common_draws, draws),
                        "Bootstrap speaker draws changed across paired metrics or runs")
            intervals[metric] = {key: {field: value for field, value in result.items()
                                       if field != "replicateDifferences"}
                                 for key, result in comparisons.items()}
        results[name] = {"comparisons": intervals, "foldDifferences": fold_deltas}
    return results, common_draws


def run(output: Path = OUTPUT):
    require(output.resolve() == OUTPUT.resolve() and not output.exists(),
            "Output must be the unused locked paired-bootstrap directory")
    recipe = load_recipe()
    loaded = load_inputs(recipe)
    results, draws = analyze(loaded, recipe)
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": RECIPE_SHA256,
              "inputSha256": {name: {key: pins[key + "Sha256"] for key in
                                    ("recipe", "report", "outOfFold")}
                              for name, pins in RUNS.items()},
              "sourceCodeSha256": sha256_file(Path(__file__)),
              "clips": recipe["expectedClips"],
              "speakers": recipe["expectedSpeakers"],
              "raterScores": recipe["expectedRaterScores"],
              "bootstrapUnit": "whole speaker",
              "bootstrapSeed": recipe["bootstrap"]["seed"],
              "bootstrapResamples": recipe["bootstrap"]["resamples"],
              "bootstrapDrawsSha256": hashlib.sha256(
                  draws.astype("<i4").tobytes()).hexdigest(),
              "differenceDirection": recipe["differenceDirection"],
              "runs": results,
              "limitations": [
                  "Fixed OOF predictions from previously inspected author-training folds; intervals omit refitting, L2 selection, and new-corpus uncertainty.",
                  "Whole-speaker resampling keeps each clip and its five subjective ratings together; these are descriptive intervals, not clinical confidence intervals.",
                  "Full-clip features can encode prompt, speaker, and capture cues, and the ratings give no /R/ timing or verified produced-phone label.",
                  "Word purging changes fit size and class mix; neither run is independent child clinical validation or learner-feedback evidence."],
              "authorPartition": "train", "knownAuthorTest": True,
              **{flag: False for flag in FALSE_FLAGS}}
    old_umask = os.umask(0o077)
    try:
        output.mkdir(mode=0o700)
        write_json(output / "report.json", report)
        (output / "report.json").chmod(0o600)
    finally:
        os.umask(old_umask)
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({name: value["comparisons"] for name, value in result["runs"].items()},
                     sort_keys=True))
