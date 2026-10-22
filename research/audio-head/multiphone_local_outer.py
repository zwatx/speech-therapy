"""Freeze a scalar refit before separately opening its outer speaker holdout.

This reuses the exact inner scalar design and optimizer. Outer outcomes cannot
select the regularization or optimizer budget. All evidence remains exploratory
author-training-corpus research, not an independent clinical validation cohort.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import time

import numpy as np
import torch

import multiphone_local_train as inner
from multiphone_child_train import score_predictions

HERE = Path(__file__).resolve().parent
SOURCES = ("multiphone_local_outer.py", "multiphone_child_train.py", "multiphone_verify.py",
           "multiphone_data.py", "multiphone_models.py", "multiphone_cache.py", "encoders.py",
           *inner.SOURCE_FILES)


def source_hashes():
    return {name: inner.digest(HERE / name) for name in sorted(set(SOURCES))}


def fresh_directory(path: Path):
    inner.require(path.resolve().is_relative_to((HERE / "outputs").resolve()) and not path.exists(),
                  "Choose a fresh directory inside ignored research outputs")
    path.mkdir(parents=True, mode=0o700)


def checked_file(directory: Path, name: str, sha: str):
    path = (directory / name).resolve()
    inner.require(path.is_relative_to(directory.resolve()) and inner.digest(path) == sha,
                  "Pinned artifact path or digest differs")
    return path


def checked_selection(directory, cohort, splits, scalars, positions, binding, fold_number):
    """Recompute every inner candidate score, then enforce the original choice."""
    config_path, selection_path = directory / "config.json", directory / "selection.json"
    config, selection = inner.read_json(config_path), inner.read_json(selection_path)
    fold = splits["folds"][fold_number]
    inner.require(config["phase"] == selection["phase"] == "inner" and selection["complete"] is True
                  and config["fold"] == fold_number and config["recipe"] == inner.TRAINING_RECIPE
                  and config["binding"] == binding and config["sourceSha256"] == inner.source_hashes()
                  and config["fitRows"] == fold["innerFitRows"]
                  and config["validationRows"] == fold["innerValidationRows"]
                  and config["design"] == inner.design_for(cohort)
                  and selection["configSha256"] == inner.digest(config_path)
                  and selection["outerOutcomesUsed"] is False, "Inner selection binding or scope differs")
    artifacts = {str(config_path.resolve()): inner.digest(config_path),
                 str(selection_path.resolve()): inner.digest(selection_path)}
    rows = [cohort["rows"][i] for i in fold["innerValidationRows"]]
    values = np.asarray(scalars[[positions[i] for i in fold["innerValidationRows"]]])
    for trial in selection["trials"]:
        checkpoint = checked_file(directory, trial["checkpointPath"], trial["checkpointSha256"])
        prediction = checked_file(directory, trial["predictionsPath"], trial["predictionsSha256"])
        state, saved = inner.read_json(checkpoint), inner.read_json(prediction)
        inner.require(state["phase"] == "inner" and state["configSha256"] == inner.digest(config_path)
                      and state["state"]["design"] == config["design"]
                      and state["state"]["head"]["alpha"] == trial["alpha"]
                      and saved["rowIndices"] == fold["innerValidationRows"], "Inner candidate partition differs")
        probabilities = np.asarray(saved["probabilities"], dtype=float)
        inner.require(probabilities.shape == (len(rows), 3) and np.isfinite(probabilities).all()
                      and (probabilities >= 0).all() and np.allclose(probabilities.sum(1), 1),
                      "Invalid inner candidate probabilities")
        replay = inner.predict_state(state["state"], rows, values)
        inner.require(np.array_equal(replay, probabilities),
                      "Inner checkpoint does not exactly replay its saved predictions")
        measured = inner.score_predictions(probabilities, rows)
        inner.require(abs(measured["macroTargetLogLoss"] - trial["metrics"]["macroTargetLogLoss"]) < 1e-10,
                      "Inner candidate selection score differs from predictions")
        artifacts.update({str(checkpoint): inner.digest(checkpoint), str(prediction): inner.digest(prediction)})
    choice = inner.choose_trial(selection["trials"])
    inner.require(selection["selected"] == choice, "Selected setting differs from the locked inner rule")
    return choice["alpha"], artifacts


def verify_unchanged(args, binding, sources, artifacts):
    inner.require(source_hashes() == sources and inner.load_inputs(args.cohort, args.splits, args.features)[-1] == binding
                  and all(inner.digest(Path(path)) == sha for path, sha in artifacts.items()),
                  "Sources or pinned inputs changed during the operation")


def run_refit(args):
    inner.require(type(args.fold) is int and 0 <= args.fold < 5, "Invalid fold")
    torch.set_num_threads(inner.TRAINING_RECIPE["cpuThreads"])
    cohort, splits, scalars, positions, binding = inner.load_inputs(args.cohort, args.splits, args.features)
    alpha, artifacts = checked_selection(args.input, cohort, splits, scalars, positions, binding, args.fold)
    sources = source_hashes()
    indices = splits["folds"][args.fold]["outerFitRows"]
    rows = [cohort["rows"][i] for i in indices]
    values = np.asarray(scalars[[positions[i] for i in indices]])
    design = inner.design_for(cohort)
    fresh_directory(args.output)
    config = {"phase": "outer-refit", "fold": args.fold, "recipe": inner.TRAINING_RECIPE,
              "binding": binding, "sourceSha256": sources, "innerArtifactsSha256": artifacts,
              "fitRows": indices, "design": design, "alpha": alpha,
              "maxOptimizerIterations": inner.TRAINING_RECIPE["maxOptimizerIterations"],
              "clinicalUseEligible": False, "learnerFeedbackEligible": False,
              "outerOutcomesUsed": False, "authorTestInferencePerformed": False}
    inner.write_json(args.output / "config.json", config)
    started = time.perf_counter()
    state, diagnostics = inner.fit_state(design, rows, values, alpha, config["maxOptimizerIterations"])
    inner.write_json(args.output / "checkpoint.json", {"configSha256": inner.digest(args.output / "config.json"),
                                                       "phase": "outer-refit", "state": state})
    report = {"complete": True, "configSha256": inner.digest(args.output / "config.json"),
              "checkpointSha256": inner.digest(args.output / "checkpoint.json"),
              "elapsedSeconds": time.perf_counter() - started, "optimizer": diagnostics,
              "outerOutcomesUsed": False, "holdoutPredictionsComputed": False}
    verify_unchanged(args, binding, sources, artifacts)
    inner.write_json(args.output / "frozen.json", report)
    return report


def run_evaluate(args):
    torch.set_num_threads(inner.TRAINING_RECIPE["cpuThreads"])
    cohort, splits, scalars, positions, binding = inner.load_inputs(args.cohort, args.splits, args.features)
    config_path, frozen_path = args.input / "config.json", args.input / "frozen.json"
    config, frozen = inner.read_json(config_path), inner.read_json(frozen_path)
    inner.require(config["phase"] == "outer-refit" and config["fold"] == args.fold
                  and config["binding"] == binding and config["sourceSha256"] == source_hashes()
                  and config["recipe"] == inner.TRAINING_RECIPE
                  and config["outerOutcomesUsed"] is False and config["authorTestInferencePerformed"] is False
                  and config["clinicalUseEligible"] is False and config["learnerFeedbackEligible"] is False
                  and config["fitRows"] == splits["folds"][args.fold]["outerFitRows"]
                  and frozen["complete"] is True and frozen["outerOutcomesUsed"] is False
                  and frozen["holdoutPredictionsComputed"] is False
                  and frozen["configSha256"] == inner.digest(config_path), "Frozen outer refit binding differs")
    checkpoint_path = checked_file(args.input, "checkpoint.json", frozen["checkpointSha256"])
    checkpoint = inner.read_json(checkpoint_path)
    inner.require(checkpoint["phase"] == "outer-refit" and checkpoint["configSha256"] == inner.digest(config_path)
                  and checkpoint["state"]["design"] == config["design"] == inner.design_for(cohort)
                  and checkpoint["state"]["head"]["alpha"] == config["alpha"],
                  "Frozen checkpoint design or binding differs")
    artifacts = {**config["innerArtifactsSha256"], str(config_path.resolve()): inner.digest(config_path),
                 str(frozen_path.resolve()): inner.digest(frozen_path), str(checkpoint_path): inner.digest(checkpoint_path)}
    verify_unchanged(args, binding, config["sourceSha256"], artifacts)
    fresh_directory(args.output)
    indices = splits["folds"][args.fold]["outerHoldoutRows"]
    rows = [cohort["rows"][i] for i in indices]
    values = np.asarray(scalars[[positions[i] for i in indices]])
    probabilities = inner.predict_state(checkpoint["state"], rows, values)
    metrics = score_predictions(probabilities, rows)
    inner.write_json(args.output / "predictions.json", {"rowIndices": indices, "probabilities": probabilities.tolist()})
    report = {"phase": "outer-evaluation", "complete": True, "fold": args.fold, "alpha": config["alpha"],
              "frozenArtifactsSha256": artifacts, "sourceSha256": config["sourceSha256"],
              "evaluationRows": indices, "evaluation": metrics,
              "predictionsSha256": inner.digest(args.output / "predictions.json"),
              "interpretation": "Exploratory outer speaker holdout; no selection on these outcomes",
              "authorTestInferencePerformed": False, "clinicalUseEligible": False, "learnerFeedbackEligible": False}
    verify_unchanged(args, binding, config["sourceSha256"], artifacts)
    inner.write_json(args.output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("refit", "evaluate"))
    for name in ("cohort", "splits", "features", "input", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--fold", type=int, choices=range(5), required=True)
    arguments = parser.parse_args()
    result = (run_refit if arguments.phase == "refit" else run_evaluate)(arguments)
    print(f"{arguments.phase}: complete={result['complete']}; {arguments.output}")
