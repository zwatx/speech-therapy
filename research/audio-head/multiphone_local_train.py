"""Inner-only, regularized rating models for estimated local CTC evidence.

The fixed design contains phone indicators and phone-specific scalar features.
Intervals are forced-path hypotheses, not reviewed productions or phone times.
There is deliberately no outer-refit/evaluation command in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch

from multiphone_controls import (canonical_sha, check_binding, counts_for, predict_control, score_predictions,
                                 validate_study)
from speechocean_r_rater_cv import fit_softmax, predict_softmax

HERE = Path(__file__).resolve().parent
SCALAR_NAMES = ["targetMeanLogPosterior", "targetMeanPosterior", "targetMaxPosterior",
                "meanLogMarginVsBestOtherPhone", "meanLogFractionOfNonblankMass",
                "targetArgmaxFraction", "meanBlankPosterior", "meanSpecialPosterior",
                "meanFullVocabularyEntropy", "ctcTargetOccupancySeconds", "occupiedFrames",
                "utteranceViterbiLogProbabilityPerFrame", "greedyCanonicalTokenErrorRate"]
TRAINING_RECIPE = {
    "experiment": "multiphone-inner-local-scalar-softmax-v1", "phase": "inner",
    "family": "phone-conditioned-estimated-ctc-scalars", "l2Candidates": [0.0001, 0.001, 0.01, 0.1],
    "maxOptimizerIterations": 200, "cpuThreads": 2,
    "optimizer": "CPU float64 LBFGS strong_wolfe, zero initialization, history10",
    "objective": "Mean five-rater distribution NLL + alpha times squared coefficient sum; intercept unpenalized",
    "scaling": "Each full design column uses inner-fit mean/SD; SD below1e-6 becomes1",
    "selection": "Lowest inner-validation macro-phone NLL; exact ties prefer stronger L2",
    "scalarFeatureNames": SCALAR_NAMES,
    "coverage": "Every eligible cohort row exactly once, finite; no exclusion by rating or model support",
    "clinicalUseEligible": False, "learnerFeedbackEligible": False, "outerOutcomesUsed": False,
}
SOURCE_FILES = ("multiphone_local_train.py", "multiphone_controls.py", "multiphone_train.py",
                "speechocean_r_rater_cv.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value):
    with path.open("x") as stream:
        path.chmod(0o600)
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCE_FILES}


def named_input(metadata: dict, name: str, directory: Path) -> tuple[Path, dict]:
    path = Path(metadata[name + "Path"])
    path = (path if path.is_absolute() else directory / path).resolve()
    require(path.is_file() and digest(path) == metadata[name + "Sha256"], f"{name} input digest differs")
    return path, read_json(path)


def load_inputs(cohort_path: Path, splits_path: Path, feature_path: Path):
    cohort, splits, metadata = [read_json(path) for path in (cohort_path, splits_path, feature_path)]
    validate_study(cohort, splits)
    eligible = [i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"]]
    indices = metadata["rowIndices"]
    require(metadata.get("complete") is True and metadata.get("fullCohortCoverage") is True
            and metadata.get("eligibleCohortRows") == len(eligible)
            and metadata.get("failedRows") == [] and metadata.get("unmappableRows") == [],
            "Complete full-cohort coverage is required; partial preflight/exclusions cannot train")
    require(all(type(i) is int for i in indices) and sorted(indices) == eligible
            and len(set(indices)) == len(indices) and len(metadata["rows"]) == len(indices),
            "Feature row coverage/identity differs from eligible cohort")
    require(metadata["cohortSha256"] == digest(cohort_path)
            and metadata["splitsSha256"] == digest(splits_path), "Feature data/split binding differs")
    require(metadata["scalarFeatureNames"] == SCALAR_NAMES
            and metadata["mappingVersion"] == "arpabet-espeak-provisional-v1"
            and all(metadata.get(flag) is False for flag in
                    ("frameTimesValidated", "producedPhoneLabelsAvailable", "authorTestInferencePerformed",
                     "clinicalUseEligible", "learnerFeedbackEligible")), "Feature schema or research scope differs")
    directory = feature_path.parent.resolve()
    upstream = {}
    for name in ("manifest", "ctcIndex", "recipe"):
        upstream[name] = named_input(metadata, name, directory)
    manifest = upstream["manifest"][1]
    require(manifest["authorPartition"] == "train" and manifest["fullCohortCoverage"] is True
            and manifest["partition"] == "allEligibleAuthorTrain"
            and manifest["cohortSha256"] == metadata["cohortSha256"]
            and manifest["splitsSha256"] == metadata["splitsSha256"], "Feature manifest is not the full author-train cohort")
    ctc_path, ctc_index = upstream["ctcIndex"]
    ctc_config_path = ctc_path.parent / "config.json"
    require(ctc_index["complete"] is True and ctc_index["configSha256"] == digest(ctc_config_path)
            and read_json(ctc_config_path)["manifestSha256"] == metadata["manifestSha256"],
            "CTC cache config/manifest binding differs")
    require(upstream["recipe"][1]["mappingVersion"] == metadata["mappingVersion"], "Canonical mapping differs")
    if metadata.get("wavlmIndexSha256") is not None:
        upstream["wavlmIndex"] = named_input(metadata, "wavlmIndex", directory)
    expected_source_names = {"multiphone_local_features.py", "alignment_pilot.py"}
    require(set(metadata["sourceSha256"]) == expected_source_names and all(
        digest(HERE / name) == value for name, value in metadata["sourceSha256"].items()),
        "Extraction source changed since feature generation")
    asset = metadata["scalarFeatures"]
    array_path = (directory / asset["path"]).resolve()
    require(array_path.is_relative_to(directory) and digest(array_path) == asset["sha256"],
            "Scalar feature path/digest differs")
    scalars = np.load(array_path, mmap_mode="r", allow_pickle=False)
    require(asset["dtype"] == "float32" and asset["shape"] == [len(indices), len(SCALAR_NAMES)]
            and scalars.dtype == np.float32 and list(scalars.shape) == asset["shape"]
            and np.isfinite(scalars).all(), "Invalid scalar matrix shape/dtype/values")
    manifest_rows = {}
    for clip in manifest["clips"]:
        for row in clip["targetRows"]:
            require(row["rowIndex"] not in manifest_rows, "Duplicate row in extraction manifest")
            manifest_rows[row["rowIndex"]] = {**row, "clipId": clip["id"]}
    require(set(manifest_rows) == set(eligible), "Extraction manifest omitted eligible rows")
    for position, (index, feature_row) in enumerate(zip(indices, metadata["rows"], strict=True)):
        row = cohort["rows"][index]
        expected = {"rowIndex": index, "rowId": row["id"], **{key: row[key] for key in
                    ("clipId", "targetId", "targetPhone", "wordIndex", "phoneIndex")}}
        require(all(feature_row[key] == value for key, value in expected.items())
                and all(feature_row[key] == value for key, value in manifest_rows[index].items()),
                "Feature row or canonical position belongs to a different target")
        require(np.array_equal(scalars[position], np.asarray(feature_row["scalarFeatures"], dtype=np.float32)),
                "Scalar matrix values differ from named row metadata")
    evidence = {"cohortPath": str(cohort_path.resolve()), "cohortSha256": digest(cohort_path),
                "splitsPath": str(splits_path.resolve()), "splitsSha256": digest(splits_path),
                "cohortCanonicalSha256": canonical_sha(cohort),
                "featuresPath": str(feature_path.resolve()), "featuresSha256": digest(feature_path),
                "scalarPath": str(array_path), "scalarSha256": digest(array_path),
                "upstream": {name: {"path": str(path), "sha256": digest(path)} for name, (path, _) in upstream.items()},
                "ctcConfigSha256": digest(ctc_config_path), "extractionSourceSha256": metadata["sourceSha256"]}
    return cohort, splits, scalars, {index: position for position, index in enumerate(indices)}, evidence


def design_for(cohort: dict) -> dict:
    phones = [cohort["targetPhones"][i] for i in cohort["eligibleTargetIds"]]
    require(phones and len(set(phones)) == len(phones), "Invalid target vocabulary")
    return {"targetPhones": phones, "scalarFeatureNames": SCALAR_NAMES,
            "columns": [f"phone:{phone}" for phone in phones] +
                       [f"phone:{phone}|scalar:{name}" for phone in phones for name in SCALAR_NAMES]}


def transform(design: dict, rows: list[dict], scalars: np.ndarray) -> np.ndarray:
    require(design["scalarFeatureNames"] == SCALAR_NAMES and len(design["targetPhones"]) == len(set(design["targetPhones"]))
            and design["columns"] == [f"phone:{p}" for p in design["targetPhones"]] +
            [f"phone:{p}|scalar:{f}" for p in design["targetPhones"] for f in SCALAR_NAMES],
            "Feature column identity/order differs")
    require(scalars.shape == (len(rows), len(SCALAR_NAMES)) and np.isfinite(scalars).all(), "Invalid local input features")
    phones = {phone: i for i, phone in enumerate(design["targetPhones"])}
    require(all(row["targetPhone"] in phones for row in rows), "Unknown target phone")
    result = np.zeros((len(rows), len(design["columns"])), dtype=np.float64)
    positions = np.arange(len(rows))
    ids = np.asarray([phones[row["targetPhone"]] for row in rows])
    result[positions, ids] = 1
    for column in range(len(SCALAR_NAMES)):
        result[positions, len(phones) + ids * len(SCALAR_NAMES) + column] = scalars[:, column]
    return result


def fit_state(design: dict, rows: list[dict], scalars: np.ndarray, alpha: float, max_iterations=200):
    require(alpha in TRAINING_RECIPE["l2Candidates"] and type(max_iterations) is int and max_iterations > 0,
            "Undeclared regularization or invalid optimizer budget")
    require(set(row["targetPhone"] for row in rows) == set(design["targetPhones"]), "Target lacks inner-fit support")
    features, counts = transform(design, rows, scalars), counts_for(rows)
    head, diagnostics = fit_softmax(features, counts, alpha, max_iterations)
    return {"design": design, "head": {key: value.tolist() if isinstance(value, np.ndarray) else value
                                        for key, value in head.items()}}, diagnostics


def predict_state(state: dict, rows: list[dict], scalars: np.ndarray):
    features = transform(state["design"], rows, scalars)
    head = {key: np.asarray(value, dtype=np.float64) if isinstance(value, list) else value
            for key, value in state["head"].items()}
    width = features.shape[1]
    require(head["weights"].shape == (width, 3) and head["intercept"].shape == (3,)
            and head["featureMean"].shape == head["featureScale"].shape == (width,)
            and all(np.isfinite(head[key]).all() for key in ("weights", "intercept", "featureMean", "featureScale"))
            and (head["featureScale"] > 0).all(), "Invalid saved softmax state")
    return predict_softmax(head, features)


def choose_trial(trials):
    require(len(trials) == len(TRAINING_RECIPE["l2Candidates"])
            and [trial["alpha"] for trial in trials] == TRAINING_RECIPE["l2Candidates"]
            and all(np.isfinite(trial["metrics"]["macroTargetLogLoss"]) for trial in trials), "Incomplete trial matrix")
    return min(trials, key=lambda trial: (trial["metrics"]["macroTargetLogLoss"], -trial["alpha"]))


def control_comparisons(directory: Path, fold_number: int, cohort, splits, evidence) -> dict:
    location = directory / f"fold-{fold_number}-inner"
    config, selection = read_json(location / "config.json"), read_json(location / "selection.json")
    check_binding(config, {key: evidence[key] for key in
                          ("cohortPath", "cohortSha256", "splitsPath", "splitsSha256", "cohortCanonicalSha256")},
                  fold_number)
    fold = splits["folds"][fold_number]
    require(config["phase"] == "inner" and config["fold"] == fold_number
            and config["fitRows"] == fold["innerFitRows"] and config["validationRows"] == fold["innerValidationRows"]
            and selection["configSha256"] == digest(location / "config.json")
            and selection["outerOutcomesUsed"] is False, "Controls use different data/splits or non-inner outcomes")
    result = {}
    rows = [cohort["rows"][i] for i in fold["innerValidationRows"]]
    for family in ("prior", "word-age-backoff", "linear-word-age-capture"):
        choice = selection["selected"][family]
        path = (location / choice["statePath"]).resolve()
        require(path.is_relative_to(location.resolve()) and digest(path) == choice["stateSha256"], "Control state digest differs")
        p = predict_control(read_json(path), rows, cohort["clips"])
        metrics = score_predictions(p, rows)
        require(abs(metrics["macroTargetLogLoss"] - choice["innerMacroTargetLogLoss"]) <= 1e-10,
                "Control checkpoint does not replay recorded inner score")
        result[family] = {"stateSha256": digest(path), "metrics": metrics}
    return {"selectionSha256": digest(location / "selection.json"), "configSha256": digest(location / "config.json"),
            "sameValidationRows": True, "families": result}


def replay_checkpoint(path: Path, cohort_path: Path, splits_path: Path, feature_path: Path):
    config, checkpoint = read_json(path.parent / "config.json"), read_json(path)
    selection = read_json(path.parent / "selection.json")
    matching = [trial for trial in selection["trials"] if trial["checkpointPath"] == path.name]
    require(selection["complete"] is True and selection["phase"] == "inner"
            and selection["configSha256"] == digest(path.parent / "config.json")
            and len(matching) == 1 and matching[0]["checkpointSha256"] == digest(path),
            "Checkpoint digest differs from completed trial evidence")
    require(config["phase"] == checkpoint["phase"] == "inner"
            and checkpoint["configSha256"] == digest(path.parent / "config.json")
            and config["sourceSha256"] == source_hashes() and config["recipe"] == TRAINING_RECIPE,
            "Checkpoint scope/config/source differs")
    cohort, splits, scalars, positions, evidence = load_inputs(cohort_path, splits_path, feature_path)
    require(evidence == config["binding"], "Checkpoint feature/data binding differs")
    fold = splits["folds"][config["fold"]]
    require(config["fitRows"] == fold["innerFitRows"] and config["validationRows"] == fold["innerValidationRows"]
            and checkpoint["state"]["design"] == design_for(cohort), "Checkpoint partition/design differs")
    selected = fold["innerValidationRows"]
    rows = [cohort["rows"][i] for i in selected]
    values = np.asarray(scalars[[positions[i] for i in selected]])
    return {"rowIndices": selected, "probabilities": predict_state(checkpoint["state"], rows, values).tolist()}


def run_inner(args) -> dict:
    require(type(args.fold) is int and 0 <= args.fold < 5, "Invalid inner fold")
    require(args.output.resolve().is_relative_to((HERE / "outputs").resolve()) and not args.output.exists(),
            "Choose a new directory in ignored research outputs")
    torch.set_num_threads(TRAINING_RECIPE["cpuThreads"])
    cohort, splits, scalars, positions, evidence = load_inputs(args.cohort, args.splits, args.features)
    fold = splits["folds"][args.fold]
    fit_indices, validation_indices = fold["innerFitRows"], fold["innerValidationRows"]
    fit_rows = [cohort["rows"][i] for i in fit_indices]
    validation_rows = [cohort["rows"][i] for i in validation_indices]
    fit_values = np.asarray(scalars[[positions[i] for i in fit_indices]])
    validation_values = np.asarray(scalars[[positions[i] for i in validation_indices]])
    design = design_for(cohort)
    config = {"schemaVersion": 1, "phase": "inner", "fold": args.fold, "recipe": TRAINING_RECIPE,
              "binding": evidence, "sourceSha256": source_hashes(), "numpyVersion": np.__version__,
              "torchVersion": torch.__version__, "fitRows": fit_indices, "validationRows": validation_indices,
              "design": design, "clinicalUseEligible": False, "learnerFeedbackEligible": False,
              "outerOutcomesUsed": False, "frameTimesValidated": False}
    comparisons = control_comparisons(args.controls, args.fold, cohort, splits, evidence) if args.controls else None
    args.output.mkdir(parents=True)
    args.output.chmod(0o700)
    write_json(args.output / "config.json", config)
    started, trials = time.perf_counter(), []
    for alpha in TRAINING_RECIPE["l2Candidates"]:
        trial_started = time.perf_counter()
        state, diagnostics = fit_state(design, fit_rows, fit_values, alpha, TRAINING_RECIPE["maxOptimizerIterations"])
        p = predict_state(state, validation_rows, validation_values)
        metrics = score_predictions(p, validation_rows)
        name = f"l2-{alpha:g}"
        checkpoint_path, predictions_path = args.output / f"{name}-checkpoint.json", args.output / f"{name}-predictions.json"
        write_json(checkpoint_path, {"phase": "inner", "configSha256": digest(args.output / "config.json"), "state": state})
        replay = predict_state(read_json(checkpoint_path)["state"], validation_rows, validation_values)
        require(np.array_equal(replay, p), "Saved state changed validation predictions")
        write_json(predictions_path, {"rowIndices": validation_indices, "probabilities": p.tolist()})
        trial = {"alpha": alpha, "metrics": metrics, "optimizer": diagnostics,
                 "checkpointPath": checkpoint_path.name, "checkpointSha256": digest(checkpoint_path),
                 "predictionsPath": predictions_path.name, "predictionsSha256": digest(predictions_path),
                 "checkpointReplayExact": True, "elapsedSeconds": time.perf_counter() - trial_started}
        trials.append(trial)
        write_json(args.output / f"{name}-metrics.json", trial)
        print(json.dumps({"phase": "inner", "fold": args.fold, "alpha": alpha,
                          "macroTargetLogLoss": metrics["macroTargetLogLoss"],
                          "optimizerIterations": diagnostics["optimizerIterations"]}), flush=True)
    selected = choose_trial(trials)
    # Revalidate input values and upstream lineage before publishing completion.
    require(load_inputs(args.cohort, args.splits, args.features)[-1] == evidence
            and config["sourceSha256"] == source_hashes(), "Input/source changed during fitting")
    report = {"schemaVersion": 1, "phase": "inner", "configSha256": digest(args.output / "config.json"),
              "selected": selected, "trials": trials, "controls": comparisons,
              "elapsedSeconds": time.perf_counter() - started, "complete": True,
              "outerOutcomesUsed": False, "clinicalUseEligible": False, "learnerFeedbackEligible": False,
              "limitations": ["Forced canonical target intervals remain unreviewed hypotheses.",
                              "CTC target occupancy, often one spiky frame, is not a measurement of phone duration.",
                              "Two scalar columns summarize utterance context; this is not isolated-phone evidence.",
                              "Inner validation selects settings; results are not independent generalization evidence."]}
    write_json(args.output / "selection.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true", help="Print the fixed training recipe without fitting")
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--splits", type=Path)
    parser.add_argument("--features", type=Path, help="Complete features.json; partial preflight artifacts are refused")
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fold", type=int, choices=range(5), default=0)
    parser.add_argument("--replay-checkpoint", type=Path)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(TRAINING_RECIPE, indent=2, sort_keys=True))
    else:
        require(all((args.cohort, args.splits, args.features)), "Cohort, splits and features are required")
        if args.replay_checkpoint:
            require(args.output is not None, "Replay output JSON path is required")
            write_json(args.output, replay_checkpoint(args.replay_checkpoint, args.cohort, args.splits, args.features))
        else:
            require(args.output is not None, "New run output directory is required")
            run_inner(args)
