"""Bind all inner control candidates before the existing separate refit/evaluate.

The small wrapper preserves the numerical implementation and adds replay of
every candidate plus before/after immutable-input checks. Its verified.json is
required release evidence; an underlying result alone is not sufficient.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

import multiphone_controls as controls

HERE = Path(__file__).resolve().parent
SOURCES = ("multiphone_control_outer.py", "multiphone_controls.py", "multiphone_train.py",
           "multiphone_models.py", "multiphone_data.py", "multiphone_cache.py", "encoders.py",
           "speechocean_r_rater_cv.py")


def read_json(path):
    return json.loads(path.read_text())


def sources():
    return {name: controls.digest(HERE / name) for name in SOURCES}


def file_pins(paths):
    return {str(path.resolve()): controls.digest(path) for path in paths}


def guard(source_pins, pins):
    controls.require(sources() == source_pins and all(controls.digest(Path(path)) == sha for path, sha in pins.items()),
                     "Source or pinned artifact changed")


def metrics_equal(left, right):
    if isinstance(left, dict):
        return isinstance(right, dict) and left.keys() == right.keys() and all(metrics_equal(v, right[k]) for k, v in left.items())
    if isinstance(left, list):
        return isinstance(right, list) and len(left) == len(right) and all(metrics_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, (float, int)):
        return isinstance(right, (float, int)) and bool(np.isclose(left, right, rtol=1e-12, atol=1e-12))
    return left == right


def validate_inner(args, cohort, splits, binding):
    config, selection = read_json(args.input / "config.json"), read_json(args.input / "selection.json")
    controls.check_binding(config, binding, args.fold)
    fold = splits["folds"][args.fold]
    controls.require(config["phase"] == "inner" and config["families"] == list(controls.FAMILIES)
                     and config["fitRows"] == fold["innerFitRows"] and config["validationRows"] == fold["innerValidationRows"]
                     and config["outerOutcomesUsed"] is selection["outerOutcomesUsed"] is False
                     and selection["configSha256"] == controls.digest(args.input / "config.json")
                     and selection["selectionPartition"] == "innerValidationRows"
                     and set(selection["trials"]) == set(selection["selected"]) == set(controls.FAMILIES),
                     "Expected all three controls on this exact inner partition")
    fit = [cohort["rows"][i] for i in fold["innerFitRows"]]
    validation = [cohort["rows"][i] for i in fold["innerValidationRows"]]
    pins = file_pins([args.cohort, args.splits, args.input / "config.json", args.input / "selection.json"])
    for family, trials in selection["trials"].items():
        expected = [1.] if family == "prior" else list(controls.SMOOTHING if family == controls.FAMILIES[1] else controls.L2)
        controls.require([trial["setting"] for trial in trials] == expected, "Inner candidate settings differ")
        for trial in trials:
            state = controls.checked_checkpoint(args.input, trial["statePath"], trial["stateSha256"])
            controls.require(state["family"] == trial["family"] == family, "Control family differs")
            if family in controls.FAMILIES[:2]:
                controls.require(state == controls.fit_count_control(fit, family, trial["setting"]),
                                 "Count state differs from actual inner-fit rows")
            else:
                design = controls.fit_feature_design(fit)
                features = controls.transform_features(design, fit, cohort["clips"])
                scale = features.std(0)
                scale = np.where(scale < 1e-6, 1., scale)
                controls.require(state["alpha"] == state["head"]["alpha"] == trial["setting"] and state["design"] == design
                                 and np.array_equal(state["head"]["featureMean"], features.mean(0))
                                 and np.array_equal(state["head"]["featureScale"], scale),
                                 "Linear inner-fit design, moments or setting differs")
            replay = controls.score_predictions(controls.predict_control(state, validation, cohort["clips"]), validation)
            controls.require(metrics_equal(replay, trial["metrics"]), "Inner control checkpoint replay differs")
            pins.update(file_pins([args.input / trial["statePath"]]))
        winner = controls.choose_trial(trials)
        controls.require(selection["selected"][family] == {
            "setting": winner["setting"], "innerMacroTargetLogLoss": winner["metrics"]["macroTargetLogLoss"],
            "statePath": winner["statePath"], "stateSha256": winner["stateSha256"]}, "Inner control winner differs")
    return pins


def run_refit(args):
    torch.set_num_threads(args.threads)
    source_pins = sources()
    cohort, splits, binding = controls.load_study(args.cohort, args.splits)
    pins = validate_inner(args, cohort, splits, binding)
    guard(source_pins, pins)
    result = controls.run_refit(args)
    guard(source_pins, pins)
    controls.require(not any(args.output.glob("*predictions.json")), "Refit unexpectedly produced holdout predictions")
    controls.require(read_json(args.output / "frozen.json") == result
                     and result["configSha256"] == controls.digest(args.output / "config.json")
                     and set(result["states"]) == set(controls.FAMILIES), "Refit publication differs")
    for family, entry in result["states"].items():
        state = controls.checked_checkpoint(args.output, entry["statePath"], entry["stateSha256"])
        controls.require(state["family"] == family and
                         (state["smoothing"] if family in controls.FAMILIES[:2] else state["alpha"]) == entry["setting"],
                         "Refit state family or setting differs")
    frozen_pins = file_pins([args.output / "config.json", args.output / "frozen.json"] +
                           [args.output / entry["statePath"] for entry in result["states"].values()])
    verified = {"complete": True, "phase": "refit", "sourceSha256": source_pins,
                "inputArtifactsSha256": pins, "frozenArtifactsSha256": frozen_pins,
                "everyInnerCandidateReplayed": True, "holdoutPredictionsComputed": False,
                "authorTestInferencePerformed": False, "clinicalUseEligible": False, "learnerFeedbackEligible": False}
    controls.write_json(args.output / "verified.json", verified)
    return verified


def run_evaluate(args):
    torch.set_num_threads(args.threads)
    verified = read_json(args.input / "verified.json")
    controls.require(verified["complete"] is True and verified["phase"] == "refit"
                     and verified["everyInnerCandidateReplayed"] is True
                     and verified["holdoutPredictionsComputed"] is False, "Expected verified frozen controls")
    pins = {**verified["inputArtifactsSha256"], **verified["frozenArtifactsSha256"],
            **file_pins([args.input / "verified.json"])}
    guard(verified["sourceSha256"], pins)
    controls.run_evaluate(args)
    guard(verified["sourceSha256"], pins)
    cohort, splits, _ = controls.load_study(args.cohort, args.splits)
    indices = splits["folds"][args.fold]["outerHoldoutRows"]
    rows = [cohort["rows"][i] for i in indices]
    frozen = read_json(args.input / "frozen.json")
    report = read_json(args.output / "report.json")
    controls.require(set(report["results"]) == set(frozen["states"]) == set(controls.FAMILIES)
                     and {p.name for p in args.output.glob("*-predictions.json")} ==
                         {family + "-predictions.json" for family in controls.FAMILIES}
                     and report["configSha256"] == controls.digest(args.output / "config.json"),
                     "Evaluation publication coverage or config differs")
    for family, entry in frozen["states"].items():
        state = controls.checked_checkpoint(args.input, entry["statePath"], entry["stateSha256"])
        predictions = read_json(args.output / (family + "-predictions.json"))
        replay = controls.predict_control(state, rows, cohort["clips"])
        controls.require(predictions["rowIndices"] == indices and np.array_equal(predictions["probabilities"], replay)
                         and report["results"][family]["setting"] == entry["setting"]
                         and metrics_equal(report["results"][family]["metrics"], controls.score_predictions(replay, rows)),
                         "Evaluation predictions or metrics differ from frozen checkpoint replay")
    result = {"complete": True, "phase": "evaluate", "sourceSha256": verified["sourceSha256"],
              "frozenInputArtifactsSha256": pins, "reportSha256": controls.digest(args.output / "report.json"),
              "predictionArtifactsSha256": file_pins(list(args.output.glob("*-predictions.json"))),
              "interpretation": "Development cross-fit controls; no model choice on outer outcomes",
              "authorTestInferencePerformed": False, "clinicalUseEligible": False, "learnerFeedbackEligible": False}
    controls.require(len(result["predictionArtifactsSha256"]) == len(controls.FAMILIES), "Missing control predictions")
    guard(verified["sourceSha256"], pins)
    controls.write_json(args.output / "verified.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("refit", "evaluate"))
    for name in ("cohort", "splits", "input", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--fold", type=int, choices=range(5), required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    result = run_refit(args) if args.phase == "refit" else run_evaluate(args)
    print(f"{args.phase}: verified={result['complete']}; {args.output}")
