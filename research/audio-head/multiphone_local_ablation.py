"""Inner-only scalar ablations of frozen canonical-position CTC evidence.

Each variant keeps phone indicators and zeros excluded columns in a copy.
The source artifact and original thirteen-feature model remain untouched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch

import multiphone_local_train as local
from multiphone_controls import counts_for, fit_count_control, predict_count_control, score_predictions
from multiphone_verify import discrimination, target_discrimination

HERE = local.HERE
RECIPE_PATH = HERE / "experiments/multiphone-local-ablation-v1.json"
VARIANTS = {
    "target-posterior": ["targetMeanPosterior"],
    "local-scalars": local.SCALAR_NAMES[:11],
    "utterance-context": local.SCALAR_NAMES[11:],
}
TRAINING_RECIPE = {
    "experiment": "multiphone-inner-local-scalar-ablation-v1", "phase": "inner",
    "variants": VARIANTS, "l2Candidates": local.TRAINING_RECIPE["l2Candidates"],
    "maxOptimizerIterations": 200, "cpuThreads": 2,
    "optimizer": local.TRAINING_RECIPE["optimizer"], "objective": local.TRAINING_RECIPE["objective"],
    "scaling": "Zero excluded scalars in a copy; fit each design column's mean/SD on inner-fit rows only",
    "selection": "All-age inner-validation macro-phone NLL; exact ties prefer stronger L2",
    "prior": "Same inner-fit rows, per-phone observed counts plus one pseudocount per rating class",
    "comparison": "Replay the existing selected full thirteen-scalar model on identical validation rows",
    "plannedInnerFits": 60, "folds": [0, 1, 2, 3, 4],
    "clinicalUseEligible": False, "learnerFeedbackEligible": False, "outerOutcomesUsed": False,
}
SOURCE_FILES = ("multiphone_local_ablation.py", *local.SOURCE_FILES, "multiphone_verify.py")
require, digest, read_json, write_json = local.require, local.digest, local.read_json, local.write_json


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCE_FILES}


def mask_for(variant):
    require(variant in VARIANTS, "Unknown scalar ablation")
    kept = [name in VARIANTS[variant] for name in local.SCALAR_NAMES]
    return {"variant": variant, "scalarFeatureNames": local.SCALAR_NAMES,
            "keepMask": kept, "retainedScalars": VARIANTS[variant],
            "zeroedScalars": [name for name, keep in zip(local.SCALAR_NAMES, kept) if not keep],
            "phoneIndicatorsRetained": True}


def masked_copy(values, variant):
    values = np.asarray(values)
    require(values.ndim == 2 and values.shape[1] == len(local.SCALAR_NAMES)
            and np.isfinite(values).all(), "Invalid scalar ablation matrix")
    result = values.copy()
    result[:, ~np.asarray(mask_for(variant)["keepMask"])] = 0
    return result


def fit_ablation(design, rows, values, alpha, variant):
    return local.fit_state(design, rows, masked_copy(values, variant), alpha,
                           TRAINING_RECIPE["maxOptimizerIterations"])


def predict_ablation(state, rows, values, variant):
    return local.predict_state(state, rows, masked_copy(values, variant))


def metrics_for(probabilities, rows):
    result = score_predictions(probabilities, rows)
    result["ageGroups"] = {}
    for name, selected in (("allAges", np.ones(len(rows), dtype=bool)),
                           ("ages6to12", np.asarray([6 <= row["age"] <= 12 for row in rows])),
                           ("ages13plus", np.asarray([row["age"] >= 13 for row in rows]))):
        chosen = [row for row, keep in zip(rows, selected, strict=True) if keep]
        if not chosen:
            result["ageGroups"][name] = None
            continue
        p, counts = probabilities[selected], counts_for(chosen)
        proper = score_predictions(p, chosen)
        proper.pop("ages6to12")
        proper.pop("ages13plus")
        result["ageGroups"][name] = {
            **proper, "positions": len(chosen), "speakers": len({row["speakerId"] for row in chosen}),
            "observedRaterCounts": counts.sum(0).astype(int).tolist(),
            "discrimination": discrimination(p, counts),
            "targetDiscrimination": target_discrimination(p, counts, [row["targetPhone"] for row in chosen]),
        }
    return result


def load_recipe(evidence):
    recipe = read_json(RECIPE_PATH)
    require(recipe["training"] == TRAINING_RECIPE and recipe["authorPartition"] == "train"
            and recipe["binding"] == {key: evidence[key] for key in
                ("cohortSha256", "splitsSha256", "featuresSha256", "scalarSha256")},
            "Ablation recipe/data binding differs")
    return {"path": str(RECIPE_PATH.resolve()), "sha256": digest(RECIPE_PATH), "value": recipe}


def full_comparison(directory, fold_number, args, evidence, rows, row_indices):
    location = (directory / f"fold-{fold_number}-inner").resolve()
    config, report = read_json(location / "config.json"), read_json(location / "selection.json")
    require(config["fold"] == fold_number and config["binding"] == evidence
            and config["validationRows"] == row_indices
            and report["complete"] is True and report["phase"] == "inner"
            and report["outerOutcomesUsed"] is False
            and report["configSha256"] == digest(location / "config.json"),
            "Full-feature comparator has different scope/data/rows")
    # Recompute every candidate's selection score before accepting its chosen model.
    for trial in report["trials"]:
        for name in ("checkpoint", "predictions"):
            path = (location / trial[name + "Path"]).resolve()
            require(path.is_relative_to(location) and digest(path) == trial[name + "Sha256"],
                    "Full-feature comparator artifact digest differs")
        saved = read_json(location / trial["predictionsPath"])
        checkpoint = read_json(location / trial["checkpointPath"])
        replay = local.replay_checkpoint(location / trial["checkpointPath"], args.cohort, args.splits, args.features)
        require(checkpoint["state"]["head"]["alpha"] == trial["alpha"] and replay == saved,
                "Full-feature comparator checkpoint/prediction binding differs")
        require(saved["rowIndices"] == row_indices and
                score_predictions(np.asarray(saved["probabilities"]), rows) == trial["metrics"],
                "Full-feature comparator metrics differ")
    chosen = local.choose_trial(report["trials"])
    require(report["selected"] == chosen, "Full-feature selection does not follow declared rule")
    selected_predictions = read_json(location / chosen["predictionsPath"])
    return {"directory": str(location), "configSha256": digest(location / "config.json"),
            "selectionSha256": digest(location / "selection.json"), "alpha": chosen["alpha"],
            "checkpointPath": chosen["checkpointPath"], "checkpointSha256": chosen["checkpointSha256"],
            "sameValidationRows": True, "metrics": metrics_for(np.asarray(selected_predictions["probabilities"]), rows)}


def replay_checkpoint(path, cohort_path, splits_path, feature_path):
    config, checkpoint = read_json(path.parent / "config.json"), read_json(path)
    report = read_json(path.parent / "selection.json")
    matching = [trial for trial in report["trials"] if trial["checkpointPath"] == path.name]
    require(report["complete"] is True and report["phase"] == "inner" and report["outerOutcomesUsed"] is False
            and report["configSha256"] == digest(path.parent / "config.json")
            and len(matching) == 1 and matching[0]["checkpointSha256"] == digest(path),
            "Checkpoint digest differs from completed ablation")
    require(config["phase"] == checkpoint["phase"] == "inner" and config["training"] == TRAINING_RECIPE
            and checkpoint["configSha256"] == digest(path.parent / "config.json")
            and config["sourceSha256"] == source_hashes()
            and config["mask"] == checkpoint["mask"] == mask_for(config["variant"]),
            "Ablation checkpoint scope/source/mask differs")
    cohort, splits, values, positions, evidence = local.load_inputs(cohort_path, splits_path, feature_path)
    fold = splits["folds"][config["fold"]]
    require(config["binding"] == evidence and config["recipe"] == load_recipe(evidence)
            and config["fitRows"] == fold["innerFitRows"] and config["validationRows"] == fold["innerValidationRows"]
            and checkpoint["state"]["design"] == local.design_for(cohort), "Ablation binding/partition differs")
    indices = fold["innerValidationRows"]
    rows = [cohort["rows"][i] for i in indices]
    p = predict_ablation(checkpoint["state"], rows, values[[positions[i] for i in indices]], config["variant"])
    predictions_path = (path.parent / matching[0]["predictionsPath"]).resolve()
    require(predictions_path.is_relative_to(path.parent.resolve())
            and digest(predictions_path) == matching[0]["predictionsSha256"], "Prediction digest differs")
    result = {"rowIndices": indices, "probabilities": p.tolist()}
    require(result == read_json(predictions_path) and metrics_for(p, rows) == matching[0]["metrics"],
            "Checkpoint probabilities or metrics do not replay exactly")
    return result


def run_inner(args):
    require(type(args.fold) is int and args.fold in range(5), "Invalid inner fold")
    mask = mask_for(args.variant)
    require(args.output.resolve().is_relative_to((HERE / "outputs").resolve()) and not args.output.exists(),
            "Choose a new directory in ignored research outputs")
    torch.set_num_threads(TRAINING_RECIPE["cpuThreads"])
    cohort, splits, values, positions, evidence = local.load_inputs(args.cohort, args.splits, args.features)
    recipe = load_recipe(evidence)
    fold = splits["folds"][args.fold]
    fit_indices, validation_indices = fold["innerFitRows"], fold["innerValidationRows"]
    fit_rows, validation_rows = [[cohort["rows"][i] for i in indices] for indices in (fit_indices, validation_indices)]
    fit_values, validation_values = [values[[positions[i] for i in indices]] for indices in (fit_indices, validation_indices)]
    full = full_comparison(args.full_models, args.fold, args, evidence, validation_rows, validation_indices)
    prior = fit_count_control(fit_rows, "prior", 1.0)
    prior_values = predict_count_control(prior, validation_rows)
    prior_metrics = metrics_for(prior_values, validation_rows)
    counts = counts_for(fit_rows)
    observed = {phone: counts[[row["targetPhone"] == phone for row in fit_rows]].sum(0).astype(int).tolist()
                for phone in sorted({row["targetPhone"] for row in fit_rows})}
    config = {"schemaVersion": 1, "phase": "inner", "fold": args.fold, "variant": args.variant, "mask": mask,
              "training": TRAINING_RECIPE, "recipe": recipe, "binding": evidence, "sourceSha256": source_hashes(),
              "fitRows": fit_indices, "validationRows": validation_indices, "design": local.design_for(cohort),
              "numpyVersion": np.__version__, "torchVersion": torch.__version__,
              "fullFeatureComparator": full, "outerOutcomesUsed": False, "clinicalUseEligible": False,
              "learnerFeedbackEligible": False, "frameTimesValidated": False}
    args.output.mkdir(parents=True, mode=0o700)
    write_json(args.output / "config.json", config)
    prior_path = args.output / "prior.json"
    write_json(prior_path, {"fitRows": fit_indices, "observedFitCounts": observed, "state": prior,
                           "rowIndices": validation_indices, "probabilities": prior_values.tolist(), "metrics": prior_metrics})
    started, trials = time.perf_counter(), []
    for alpha in TRAINING_RECIPE["l2Candidates"]:
        trial_started = time.perf_counter()
        state, diagnostics = fit_ablation(config["design"], fit_rows, fit_values, alpha, args.variant)
        p = predict_ablation(state, validation_rows, validation_values, args.variant)
        metrics = metrics_for(p, validation_rows)
        prefix = f"l2-{alpha:g}"
        checkpoint_path, predictions_path = [args.output / f"{prefix}-{name}.json" for name in ("checkpoint", "predictions")]
        write_json(checkpoint_path, {"phase": "inner", "configSha256": digest(args.output / "config.json"),
                                     "mask": mask, "state": state})
        replay = predict_ablation(read_json(checkpoint_path)["state"], validation_rows, validation_values, args.variant)
        require(np.array_equal(p, replay), "Saved ablation state changed predictions")
        write_json(predictions_path, {"rowIndices": validation_indices, "probabilities": p.tolist()})
        trial = {"alpha": alpha, "metrics": metrics, "optimizer": diagnostics,
                 "checkpointPath": checkpoint_path.name, "checkpointSha256": digest(checkpoint_path),
                 "predictionsPath": predictions_path.name, "predictionsSha256": digest(predictions_path),
                 "checkpointReplayExact": True, "elapsedSeconds": time.perf_counter() - trial_started,
                 "macroNLLMinusSameFitPrior": metrics["macroTargetLogLoss"] - prior_metrics["macroTargetLogLoss"],
                 "macroNLLMinusFullFeatures": metrics["macroTargetLogLoss"] - full["metrics"]["macroTargetLogLoss"]}
        trials.append(trial)
        write_json(args.output / f"{prefix}-metrics.json", trial)
        print(json.dumps({"variant": args.variant, "fold": args.fold, "alpha": alpha,
                          "macroTargetLogLoss": metrics["macroTargetLogLoss"]}), flush=True)
    require(local.load_inputs(args.cohort, args.splits, args.features)[-1] == evidence
            and config["sourceSha256"] == source_hashes() and recipe == load_recipe(evidence)
            and full == full_comparison(args.full_models, args.fold, args, evidence, validation_rows, validation_indices),
            "Ablation source/input/comparator changed during fitting")
    report = {"schemaVersion": 1, "phase": "inner", "variant": args.variant,
              "configSha256": digest(args.output / "config.json"), "complete": True,
              "selected": local.choose_trial(trials), "trials": trials,
              "sameFitPrior": {"path": prior_path.name, "sha256": digest(prior_path), "metrics": prior_metrics},
              "fullFeatureComparator": full, "elapsedSeconds": time.perf_counter() - started,
              "outerOutcomesUsed": False, "clinicalUseEligible": False, "learnerFeedbackEligible": False,
              "limitations": ["Forced canonical intervals remain unreviewed hypotheses, not produced-phone labels.",
                              "Local posterior scalars still come from contextual encoders and a whole-utterance forced path.",
                              "This isolates explicit scalar columns, not independence from utterance acoustics.",
                              "Inner-selected results are exploratory; child slices do not select this model."]}
    write_json(args.output / "selection.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cohort", "splits", "features", "full-models", "output", "replay-checkpoint"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--fold", type=int, choices=range(5))
    parser.add_argument("--variant", choices=VARIANTS)
    args = parser.parse_args()
    require(all((args.cohort, args.splits, args.features, args.output)), "Data paths and output are required")
    if args.replay_checkpoint:
        write_json(args.output, replay_checkpoint(args.replay_checkpoint, args.cohort, args.splits, args.features))
    else:
        require(args.full_models and args.fold is not None and args.variant, "Full model directory, fold and variant are required")
        run_inner(args)
