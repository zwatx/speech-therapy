"""Separate outer refit/evaluation for the two declared CTC scalar variants.

All four inner candidates must replay before their fixed L2 can be reused.
The orchestrator must freeze the complete development release before calling
evaluate; this module never selects settings from an outer outcome.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import time

import numpy as np
import torch

import multiphone_local_ablation as ablation
import multiphone_local_train as local
import multiphone_local_outer as full_outer
from multiphone_child_train import score_predictions

HERE = local.HERE
VARIANTS = ("target-posterior", "local-scalars")
SOURCES = ("multiphone_scalar_variant_outer.py", *full_outer.SOURCES, *ablation.SOURCE_FILES)
require, digest, read_json, write_json = local.require, local.digest, local.read_json, local.write_json


def source_hashes():
    return {name: digest(HERE / name) for name in sorted(set(SOURCES))}


def valid_request(args):
    require(type(args.fold) is int and args.fold in range(5) and args.variant in VARIANTS,
            "Use a declared fold and scalar variant")


def moments_for(cohort, indices, scalars, positions, variant):
    rows = [cohort["rows"][i] for i in indices]
    values = np.asarray(scalars[[positions[i] for i in indices]])
    design = local.transform(local.design_for(cohort), rows, ablation.masked_copy(values, variant))
    mean, scale = design.mean(0), design.std(0)
    return mean, np.where(scale < 1e-6, 1., scale)


def check_moments(state, moments):
    require(np.array_equal(state["head"]["featureMean"], moments[0])
            and np.array_equal(state["head"]["featureScale"], moments[1]),
            "Checkpoint moments differ from the exact masked fit rows")


def checked_selection(directory, cohort, splits, scalars, positions, binding, fold_number, variant):
    config_path, selection_path = directory / "config.json", directory / "selection.json"
    config, selection = read_json(config_path), read_json(selection_path)
    fold, mask = splits["folds"][fold_number], ablation.mask_for(variant)
    recipe = ablation.load_recipe(binding)
    require(config["phase"] == selection["phase"] == "inner" and selection["complete"] is True
            and config["variant"] == selection["variant"] == variant and config["fold"] == fold_number
            and config["training"] == ablation.TRAINING_RECIPE and config["recipe"] == recipe
            and config["mask"] == mask and config["binding"] == binding
            and config["sourceSha256"] == ablation.source_hashes()
            and config["fitRows"] == fold["innerFitRows"]
            and config["validationRows"] == fold["innerValidationRows"]
            and config["design"] == local.design_for(cohort)
            and selection["configSha256"] == digest(config_path)
            and config["outerOutcomesUsed"] is selection["outerOutcomesUsed"] is False,
            "Inner variant selection binding or scope differs")
    # choose_trial enforces the exact ordered four-alpha matrix before any choice.
    choice = local.choose_trial(selection["trials"])
    artifacts = {str(path.resolve()): digest(path) for path in
                 (config_path, selection_path, Path(recipe["path"]))}
    rows = [cohort["rows"][i] for i in fold["innerValidationRows"]]
    values = np.asarray(scalars[[positions[i] for i in fold["innerValidationRows"]]])
    moments = moments_for(cohort, fold["innerFitRows"], scalars, positions, variant)
    for trial in selection["trials"]:
        checkpoint_path = full_outer.checked_file(directory, trial["checkpointPath"], trial["checkpointSha256"])
        prediction_path = full_outer.checked_file(directory, trial["predictionsPath"], trial["predictionsSha256"])
        checkpoint, saved = read_json(checkpoint_path), read_json(prediction_path)
        require(checkpoint["phase"] == "inner" and checkpoint["configSha256"] == digest(config_path)
                and checkpoint["mask"] == mask and checkpoint["state"]["design"] == config["design"]
                and checkpoint["state"]["head"]["alpha"] == trial["alpha"]
                and saved["rowIndices"] == fold["innerValidationRows"], "Inner candidate mask/partition differs")
        check_moments(checkpoint["state"], moments)
        replay = ablation.predict_ablation(checkpoint["state"], rows, values, variant)
        require(np.array_equal(replay, saved["probabilities"]),
                "Inner candidate checkpoint does not exactly replay saved predictions")
        require(ablation.metrics_for(replay, rows) == trial["metrics"],
                "Inner candidate metrics differ from checkpoint replay")
        artifacts.update({str(path): digest(path) for path in (checkpoint_path, prediction_path)})
    require(selection["selected"] == choice, "Selected setting differs from the locked inner rule")
    return choice["alpha"], artifacts, recipe


def verify_unchanged(args, binding, sources, artifacts, recipe):
    require(source_hashes() == sources and local.load_inputs(args.cohort, args.splits, args.features)[-1] == binding
            and ablation.load_recipe(binding) == recipe
            and all(digest(Path(path)) == sha for path, sha in artifacts.items()),
            "Sources or pinned inputs changed during the operation")


def run_refit(args):
    valid_request(args)
    torch.set_num_threads(ablation.TRAINING_RECIPE["cpuThreads"])
    sources = source_hashes()
    cohort, splits, scalars, positions, binding = local.load_inputs(args.cohort, args.splits, args.features)
    alpha, artifacts, recipe = checked_selection(args.input, cohort, splits, scalars, positions, binding,
                                                 args.fold, args.variant)
    indices = splits["folds"][args.fold]["outerFitRows"]
    rows = [cohort["rows"][i] for i in indices]
    values = np.asarray(scalars[[positions[i] for i in indices]])
    design, mask = local.design_for(cohort), ablation.mask_for(args.variant)
    full_outer.fresh_directory(args.output)
    config = {"phase": "outer-refit", "fold": args.fold, "variant": args.variant, "mask": mask,
              "training": ablation.TRAINING_RECIPE, "recipe": recipe, "binding": binding,
              "sourceSha256": sources, "innerArtifactsSha256": artifacts, "fitRows": indices,
              "design": design, "alpha": alpha, "maxOptimizerIterations": ablation.TRAINING_RECIPE["maxOptimizerIterations"],
              "numpyVersion": np.__version__, "torchVersion": str(torch.__version__),
              "outerOutcomesUsed": False, "authorTestInferencePerformed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False, "frameTimesValidated": False}
    write_json(args.output / "config.json", config)
    started = time.perf_counter()
    state, diagnostics = ablation.fit_ablation(design, rows, values, alpha, args.variant)
    check_moments(state, moments_for(cohort, indices, scalars, positions, args.variant))
    write_json(args.output / "checkpoint.json", {"phase": "outer-refit", "configSha256": digest(args.output / "config.json"),
                                                "mask": mask, "state": state})
    require(read_json(args.output / "checkpoint.json")["state"] == state, "Serialized refit state differs")
    result = {"complete": True, "configSha256": digest(args.output / "config.json"),
              "checkpointSha256": digest(args.output / "checkpoint.json"), "variant": args.variant,
              "elapsedSeconds": time.perf_counter() - started, "optimizer": diagnostics,
              "outerOutcomesUsed": False, "holdoutPredictionsComputed": False}
    verify_unchanged(args, binding, sources, artifacts, recipe)
    write_json(args.output / "frozen.json", result)
    return result


def run_evaluate(args):
    valid_request(args)
    torch.set_num_threads(ablation.TRAINING_RECIPE["cpuThreads"])
    cohort, splits, scalars, positions, binding = local.load_inputs(args.cohort, args.splits, args.features)
    config_path, frozen_path = args.input / "config.json", args.input / "frozen.json"
    config, frozen = read_json(config_path), read_json(frozen_path)
    recipe, mask = ablation.load_recipe(binding), ablation.mask_for(args.variant)
    require(config["phase"] == "outer-refit" and config["fold"] == args.fold
            and config["variant"] == frozen["variant"] == args.variant and config["mask"] == mask
            and config["binding"] == binding and config["sourceSha256"] == source_hashes()
            and config["training"] == ablation.TRAINING_RECIPE and config["recipe"] == recipe
            and config["maxOptimizerIterations"] == ablation.TRAINING_RECIPE["maxOptimizerIterations"]
            and config["outerOutcomesUsed"] is False and config["authorTestInferencePerformed"] is False
            and config["clinicalUseEligible"] is False and config["learnerFeedbackEligible"] is False
            and config["fitRows"] == splits["folds"][args.fold]["outerFitRows"]
            and frozen["complete"] is True and frozen["outerOutcomesUsed"] is False
            and frozen["holdoutPredictionsComputed"] is False
            and frozen["configSha256"] == digest(config_path), "Frozen outer variant binding differs")
    checkpoint_path = full_outer.checked_file(args.input, "checkpoint.json", frozen["checkpointSha256"])
    checkpoint = read_json(checkpoint_path)
    require(checkpoint["phase"] == "outer-refit" and checkpoint["configSha256"] == digest(config_path)
            and checkpoint["mask"] == mask and checkpoint["state"]["design"] == config["design"] == local.design_for(cohort)
            and checkpoint["state"]["head"]["alpha"] == config["alpha"], "Frozen checkpoint design/mask differs")
    check_moments(checkpoint["state"], moments_for(cohort, config["fitRows"], scalars, positions, args.variant))
    artifacts = {**config["innerArtifactsSha256"], **{str(path.resolve()): digest(path) for path in
                                                  (config_path, frozen_path, checkpoint_path)}}
    verify_unchanged(args, binding, config["sourceSha256"], artifacts, recipe)
    full_outer.fresh_directory(args.output)
    indices = splits["folds"][args.fold]["outerHoldoutRows"]
    rows = [cohort["rows"][i] for i in indices]
    values = np.asarray(scalars[[positions[i] for i in indices]])
    probabilities = ablation.predict_ablation(checkpoint["state"], rows, values, args.variant)
    metrics = score_predictions(probabilities, rows)
    write_json(args.output / "predictions.json", {"rowIndices": indices, "probabilities": probabilities.tolist()})
    result = {"phase": "outer-evaluation", "complete": True, "fold": args.fold, "variant": args.variant,
              "alpha": config["alpha"], "mask": mask, "evaluationRows": indices, "evaluation": metrics,
              "frozenArtifactsSha256": artifacts, "sourceSha256": config["sourceSha256"],
              "predictionsSha256": digest(args.output / "predictions.json"),
              "interpretation": "Speaker-disjoint development cross-fit; architecture choices used overlapping inner outcomes",
              "outerOutcomesUsedForSelection": False, "authorTestInferencePerformed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False, "frameTimesValidated": False}
    verify_unchanged(args, binding, config["sourceSha256"], artifacts, recipe)
    write_json(args.output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("refit", "evaluate"))
    for name in ("cohort", "splits", "features", "input", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--fold", type=int, choices=range(5), required=True)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    args = parser.parse_args()
    result = (run_refit if args.phase == "refit" else run_evaluate)(args)
    print(f"{args.phase}: complete={result['complete']}; {args.output}")
