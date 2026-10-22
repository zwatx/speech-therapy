"""Nested, author-train-only lexical/capture controls for multi-phone ratings.

The three CLI phases are deliberately separate. ``inner`` selects settings on
one outer fold's inner validation speakers; ``refit`` freezes controls on that
fold's outer fit speakers; ``evaluate`` scores the frozen outer holdout once.
These predict subjective corpus rating distributions, not pronunciation truth.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import time

import numpy as np

HERE = Path(__file__).resolve().parent
FAMILIES = ("prior", "word-age-backoff", "linear-word-age-capture")
SMOOTHING = (1.0, 5.0, 20.0, 100.0)
L2 = (0.0001, 0.001, 0.01, 0.1)
FALSE_FLAGS = {key: False for key in (
    "authorTestInferencePerformed", "productionEligible", "learnerFeedbackEligible",
    "clinicalUseEligible", "calibrationEligible", "producedPhoneLabelsAvailable")}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def write_json(path: Path, value: object) -> None:
    # Exclusive files make an accidental rerun fail instead of replacing evidence.
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x") as stream:
        os.chmod(path, 0o600)
        stream.write(payload)


def counts_for(rows: list[dict]) -> np.ndarray:
    counts = np.asarray([row["raterCounts"] for row in rows], dtype=np.float64)
    require(counts.shape == (len(rows), 3) and len(rows) > 0 and
            np.isfinite(counts).all() and (counts >= 0).all() and
            (counts == np.floor(counts)).all() and (counts.sum(1) == 5).all(),
            "Expected five integral subjective ratings per example")
    require(all(row.get("trainingEligible") is True for row in rows),
            "Unsupported target is masked out of training and metrics")
    return counts


def validate_study(cohort: dict, splits: dict) -> None:
    require(cohort.get("authorPartition") == splits.get("authorPartition") == "train",
            "Only the author-training partition is permitted")
    require(splits.get("cohortCanonicalSha256") == canonical_sha(cohort),
            "Split indices are not bound to this exact cohort")
    rows, clips = cohort["rows"], cohort["clips"]
    require(len({row["id"] for row in rows}) == len(rows) and
            len({clip["id"] for clip in clips}) == len(clips), "Duplicate row or clip ID")
    for row in rows:
        require(type(row["clipIndex"]) is int and 0 <= row["clipIndex"] < len(clips),
                "Invalid clip index")
        clip = clips[row["clipIndex"]]
        require(row["clipId"] == clip["id"] and row["speakerId"] == clip["speakerId"] and
                row["age"] == clip["age"] and row["ageBand"] == clip["ageBand"],
                "Row and clip identity or age metadata differ")
        require(row["trainingEligible"] == (row["targetId"] in cohort["eligibleTargetIds"]),
                "Target eligibility differs from cohort mask")
        require(type(row["targetId"]) is int and 0 <= row["targetId"] < len(cohort["targetPhones"]) and
                row["targetPhone"] == cohort["targetPhones"][row["targetId"]],
                "Target ID and phone name differ")
    require(len({(row["clipId"], row["targetId"]) for row in rows}) == len(rows),
            "A target occurs more than once within a clip")
    eligible = {i for i, row in enumerate(rows) if row["trainingEligible"]}
    counts_for([rows[i] for i in sorted(eligible)])
    held = []
    for index, fold in enumerate(splits["folds"]):
        require(fold["fold"] == index, "Fold IDs must match their indices")
        for key in ("outerFitRows", "outerHoldoutRows", "innerFitRows", "innerValidationRows"):
            selected = fold[key]
            require(bool(selected) and all(type(i) is int and i in eligible for i in selected) and
                    len(selected) == len(set(selected)), "Invalid or unsupported partition rows")
        for left, right in (("outerFitRows", "outerHoldoutRows"),
                            ("innerFitRows", "innerValidationRows")):
            a, b = fold[left], fold[right]
            require(not set(a) & set(b), "Row crosses split boundary")
            for key in ("speakerId", "clipId"):
                require(not {rows[i][key] for i in a} & {rows[i][key] for i in b},
                        f"{key} crosses split boundary")
            require(not {clips[rows[i]["clipIndex"]]["audioSha256"] for i in a} &
                    {clips[rows[i]["clipIndex"]]["audioSha256"] for i in b},
                    "Duplicate waveform crosses split boundary")
        require(set(fold["outerFitRows"]) | set(fold["outerHoldoutRows"]) == eligible and
                set(fold["innerFitRows"]) | set(fold["innerValidationRows"]) ==
                set(fold["outerFitRows"]), "Partitions do not exhaust their eligible parent")
        held.extend(fold["outerHoldoutRows"])
    require(len(held) == len(eligible) and set(held) == eligible,
            "Outer holdouts must cover each eligible row exactly once")


def load_study(cohort_path: Path, splits_path: Path) -> tuple[dict, dict, dict]:
    cohort = json.loads(cohort_path.read_text())
    splits = json.loads(splits_path.read_text())
    validate_study(cohort, splits)
    binding = {"cohortPath": str(cohort_path.resolve()), "cohortSha256": digest(cohort_path),
               "splitsPath": str(splits_path.resolve()), "splitsSha256": digest(splits_path),
               "cohortCanonicalSha256": canonical_sha(cohort)}
    return cohort, splits, binding


def group_key(*parts: object) -> str:
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":"))


def fit_count_control(rows: list[dict], family: str, smoothing: float = 1.0) -> dict:
    require(family in FAMILIES[:2] and math.isfinite(smoothing) and smoothing > 0,
            "Invalid count-control setting")
    counts = counts_for(rows)
    phone_counts, age_counts, word_counts = (defaultdict(lambda: np.zeros(3)) for _ in range(3))
    for row, count in zip(rows, counts, strict=True):
        phone = row["targetPhone"]
        phone_counts[phone] += count
        if family == "word-age-backoff":
            age_counts[group_key(phone, row["ageBand"])] += count
            word_counts[group_key(phone, row["ageBand"], row["targetWord"])] += count
    return {"family": family, "smoothing": smoothing, "priorPseudocountPerClass": 1.0,
            "phonePriors": {phone: ((count + 1) / (count.sum() + 3)).tolist()
                            for phone, count in sorted(phone_counts.items())},
            "ageCounts": {key: value.tolist() for key, value in sorted(age_counts.items())},
            "wordAgeCounts": {key: value.tolist() for key, value in sorted(word_counts.items())}}


def predict_count_control(state: dict, rows: list[dict]) -> np.ndarray:
    require(state["family"] in FAMILIES[:2], "Expected a count control")
    values = []
    for row in rows:
        phone = row["targetPhone"]
        require(phone in state["phonePriors"], "Target has no fit-side support")
        prior = np.asarray(state["phonePriors"][phone], dtype=np.float64)
        if state["family"] == "word-age-backoff":
            smoothing = state["smoothing"]
            for table, key in (("ageCounts", group_key(phone, row["ageBand"])),
                               ("wordAgeCounts", group_key(phone, row["ageBand"], row["targetWord"]))):
                count = np.asarray(state[table].get(key, [0, 0, 0]), dtype=np.float64)
                prior = (count + smoothing * prior) / (count.sum() + smoothing)
        values.append(prior)
    return np.asarray(values, dtype=np.float64).reshape(-1, 3)


def row_categories(row: dict) -> tuple[str, str, str]:
    phone = row["targetPhone"]
    return (group_key("phone", phone), group_key("age", phone, row["ageBand"]),
            group_key("word", phone, row["targetWord"]))


def fit_feature_design(rows: list[dict]) -> dict:
    counts_for(rows)
    return {"categoricalColumns": sorted({key for row in rows for key in row_categories(row)}),
            "continuousPhones": sorted({row["targetPhone"] for row in rows}),
            "continuousFeatures": ["logDurationSeconds", "logRmsFloor1e-8"],
            "unknownCategory": "all-zero for that category; retain known phone/age/capture terms",
            "normalization": "fit_softmax learns column mean and scale on fit rows only"}


def transform_features(design: dict, rows: list[dict], clips: list[dict]) -> np.ndarray:
    columns = {name: i for i, name in enumerate(design["categoricalColumns"])}
    phones = {name: i for i, name in enumerate(design["continuousPhones"])}
    result = np.zeros((len(rows), len(columns) + 2 * len(phones)), dtype=np.float64)
    for i, row in enumerate(rows):
        phone = row["targetPhone"]
        require(phone in phones, "Target has no fit-side feature support")
        for key in row_categories(row):
            if key in columns:
                result[i, columns[key]] = 1.0
        clip = clips[row["clipIndex"]]
        require(clip["id"] == row["clipId"], "Capture features belong to a different clip")
        duration, rms = clip["durationSeconds"], clip["rms"]
        require(math.isfinite(duration) and duration > 0 and math.isfinite(rms) and rms >= 0,
                "Capture features must be finite with positive duration and nonnegative RMS")
        offset = len(columns) + 2 * phones[phone]
        result[i, offset:offset + 2] = (math.log(duration), math.log(max(rms, 1e-8)))
    return result


def fit_control(rows: list[dict], clips: list[dict], family: str,
                setting: float, max_iterations: int = 200) -> tuple[dict, dict]:
    require(math.isfinite(setting) and setting > 0 and type(max_iterations) is int and
            max_iterations > 0, "Invalid control fitting budget")
    started = time.perf_counter()
    if family in FAMILIES[:2]:
        state = fit_count_control(rows, family, setting)
        diagnostics = {"optimizer": "closed-form smoothed counts"}
    else:
        require(family == FAMILIES[2], "Unknown control family")
        # Reuse the already tested CPU float64 LBFGS implementation; no old data loader runs.
        from speechocean_r_rater_cv import fit_softmax
        design = fit_feature_design(rows)
        features = transform_features(design, rows, clips)
        head, diagnostics = fit_softmax(features, counts_for(rows), setting, max_iterations)
        state = {"family": family, "alpha": setting, "design": design,
                 "head": {key: value.tolist() if isinstance(value, np.ndarray) else value
                          for key, value in head.items()}}
        diagnostics.update({"featureColumns": features.shape[1],
                            "optimizer": "CPU float64 LBFGS strong_wolfe, zero initialization",
                            "maxIterations": max_iterations})
    diagnostics["fitSeconds"] = time.perf_counter() - started
    return state, diagnostics


def predict_control(state: dict, rows: list[dict], clips: list[dict]) -> np.ndarray:
    if state["family"] in FAMILIES[:2]:
        return predict_count_control(state, rows)
    from speechocean_r_rater_cv import predict_softmax
    head = {key: np.asarray(value, dtype=np.float64) if isinstance(value, list) else value
            for key, value in state["head"].items()}
    return predict_softmax(head, transform_features(state["design"], rows, clips))


def score_predictions(probabilities: np.ndarray, rows: list[dict]) -> dict:
    from multiphone_train import distribution_metrics
    counts = counts_for(rows)
    metrics = distribution_metrics(probabilities, counts)
    per_target = {}
    for phone in sorted({row["targetPhone"] for row in rows}):
        mask = np.asarray([row["targetPhone"] == phone for row in rows])
        per_target[phone] = distribution_metrics(probabilities[mask], counts[mask])
        per_target[phone]["raterCounts"] = counts[mask].sum(0).astype(int).tolist()
    metrics["perTarget"] = per_target
    metrics["macroTargetLogLoss"] = float(np.mean([v["perRaterLogLoss"] for v in per_target.values()]))
    for name, predicate in (("ages6to12", lambda r: 6 <= r["age"] <= 12),
                            ("ages13plus", lambda r: r["age"] >= 13)):
        mask = np.asarray([predicate(row) for row in rows])
        metrics[name] = distribution_metrics(probabilities[mask], counts[mask]) if mask.any() else None
    return metrics


def choose_trial(trials: list[dict]) -> dict:
    require(bool(trials) and all(math.isfinite(t["metrics"]["macroTargetLogLoss"]) for t in trials),
            "Cannot select without finite inner macro-target losses")
    # Candidates are declared in increasing order; ties prefer the stronger smoothing/L2.
    return min(trials, key=lambda trial: (trial["metrics"]["macroTargetLogLoss"], -trial["setting"]))


def source_hashes() -> dict:
    return {name: digest(HERE / name) for name in
            ("multiphone_controls.py", "speechocean_r_rater_cv.py", "multiphone_train.py")}


def new_output(path: Path) -> None:
    require(path.resolve().is_relative_to((HERE / "outputs").resolve()),
            "Keep artifacts in ignored research outputs")
    path.mkdir(parents=True, exist_ok=False, mode=0o700)


def base_config(binding: dict, fold: int, phase: str, threads: int) -> dict:
    import torch
    return {"schemaVersion": 1, "experiment": "multiphone-controls-v1", "phase": phase,
            "binding": binding, "fold": fold, "sourceSha256": source_hashes(),
            "numpyVersion": np.__version__, "torchVersion": torch.__version__,
            "cpuThreads": threads, "authorPartition": "train",
            "target": "five-rater subjective canonical-position rating distribution",
            "ageFeature": "corpus metadata nuisance control; no age-specific correctness claim",
            "selectionRule": "minimum macro-phone NLL on this outer fold's inner validation only",
            "finalEvaluationStatus": "exploratory outer folds; independent final cohort still required",
            **FALSE_FLAGS}


def check_binding(config: dict, binding: dict, fold: int) -> None:
    require(config["binding"] == binding and config["fold"] == fold,
            "Checkpoint belongs to another cohort, split, path, or fold")
    require(config["sourceSha256"] == source_hashes(), "Source changed since checkpoint preparation")


def run_inner(args) -> dict:
    cohort, splits, binding = load_study(args.cohort, args.splits)
    fold = splits["folds"][args.fold]
    fit_rows = [cohort["rows"][i] for i in fold["innerFitRows"]]
    validation_rows = [cohort["rows"][i] for i in fold["innerValidationRows"]]
    new_output(args.output)
    config = base_config(binding, args.fold, "inner", args.threads)
    config.update({"families": args.families, "priorPseudocountPerClass": 1.0,
                   "smoothingCandidates": list(SMOOTHING), "l2Candidates": list(L2),
                   "maxOptimizerIterations": args.max_iterations,
                   "fitRows": fold["innerFitRows"], "validationRows": fold["innerValidationRows"],
                   "outerOutcomesUsed": False})
    write_json(args.output / "config.json", config)
    started, selected, all_trials = time.perf_counter(), {}, {}
    for family in args.families:
        candidates = (1.0,) if family == "prior" else SMOOTHING if family == FAMILIES[1] else L2
        trials = []
        for candidate_index, setting in enumerate(candidates):
            state, diagnostics = fit_control(fit_rows, cohort["clips"], family, setting, args.max_iterations)
            metrics = score_predictions(predict_control(state, validation_rows, cohort["clips"]), validation_rows)
            state_path = f"{family}-{candidate_index}.json"
            write_json(args.output / state_path, state)
            trial = {"family": family, "setting": setting, "metrics": metrics,
                     "diagnostics": diagnostics, "statePath": state_path,
                     "stateSha256": digest(args.output / state_path)}
            write_json(args.output / f"{family}-{candidate_index}-metrics.json", trial)
            trials.append(trial)
            print(json.dumps({"phase": "inner", "fold": args.fold, "family": family,
                              "setting": setting, "macroTargetLogLoss": metrics["macroTargetLogLoss"],
                              "fitSeconds": diagnostics["fitSeconds"]}), flush=True)
        winner = choose_trial(trials)
        selected[family] = {"setting": winner["setting"], "innerMacroTargetLogLoss":
                            winner["metrics"]["macroTargetLogLoss"],
                            "statePath": winner["statePath"], "stateSha256": winner["stateSha256"]}
        all_trials[family] = trials
    result = {"configSha256": digest(args.output / "config.json"), "selected": selected,
              "trials": all_trials, "elapsedSeconds": time.perf_counter() - started,
              "selectionPartition": "innerValidationRows", "outerOutcomesUsed": False}
    require(config["sourceSha256"] == source_hashes(), "Source changed during inner selection")
    write_json(args.output / "selection.json", result)
    return result


def checked_checkpoint(directory: Path, name: str, expected_sha: str) -> dict:
    path = (directory / name).resolve()
    require(path.is_relative_to(directory.resolve()) and digest(path) == expected_sha,
            "Frozen state path or digest differs")
    return json.loads(path.read_text())


def run_refit(args) -> dict:
    cohort, splits, binding = load_study(args.cohort, args.splits)
    inner_config = json.loads((args.input / "config.json").read_text())
    selection = json.loads((args.input / "selection.json").read_text())
    require(inner_config["phase"] == "inner" and selection["outerOutcomesUsed"] is False and
            selection["selectionPartition"] == "innerValidationRows" and
            selection["configSha256"] == digest(args.input / "config.json"),
            "Expected completed inner-only selection")
    check_binding(inner_config, binding, args.fold)
    require(set(selection["selected"]) == set(selection["trials"]) == set(inner_config["families"]),
            "Selected control families differ from the inner declaration")
    for family, choice in selection["selected"].items():
        trials = selection["trials"][family]
        expected = [1.0] if family == "prior" else list(SMOOTHING) if family == FAMILIES[1] else list(L2)
        require([trial["setting"] for trial in trials] == expected,
                "Inner candidates differ from the declared settings")
        winner = choose_trial(trials)
        require(choice == {"setting": winner["setting"], "innerMacroTargetLogLoss":
                           winner["metrics"]["macroTargetLogLoss"], "statePath": winner["statePath"],
                           "stateSha256": winner["stateSha256"]},
                "Chosen setting differs from inner-only selection")
    fold = splits["folds"][args.fold]
    fit_rows = [cohort["rows"][i] for i in fold["outerFitRows"]]
    new_output(args.output)
    config = base_config(binding, args.fold, "refit", args.threads)
    config.update({"selectionPath": str((args.input / "selection.json").resolve()),
                   "selectionSha256": digest(args.input / "selection.json"),
                   "fitRows": fold["outerFitRows"], "outerOutcomesUsed": False,
                   "maxOptimizerIterations": inner_config["maxOptimizerIterations"]})
    write_json(args.output / "config.json", config)
    started, states = time.perf_counter(), {}
    for family, choice in selection["selected"].items():
        checked_checkpoint(args.input, choice["statePath"], choice["stateSha256"])
        state, diagnostics = fit_control(fit_rows, cohort["clips"], family, choice["setting"],
                                         inner_config["maxOptimizerIterations"])
        name = f"{family}.json"
        write_json(args.output / name, state)
        states[family] = {"setting": choice["setting"], "statePath": name,
                          "stateSha256": digest(args.output / name), "diagnostics": diagnostics}
    result = {"configSha256": digest(args.output / "config.json"), "states": states,
              "elapsedSeconds": time.perf_counter() - started, "outerOutcomesUsed": False}
    require(config["sourceSha256"] == source_hashes(), "Source changed during outer refit")
    write_json(args.output / "frozen.json", result)
    return result


def run_evaluate(args) -> dict:
    cohort, splits, binding = load_study(args.cohort, args.splits)
    config = json.loads((args.input / "config.json").read_text())
    frozen = json.loads((args.input / "frozen.json").read_text())
    require(config["phase"] == "refit" and frozen["outerOutcomesUsed"] is False and
            frozen["configSha256"] == digest(args.input / "config.json"),
            "Expected frozen outer-fit controls")
    check_binding(config, binding, args.fold)
    indices = splits["folds"][args.fold]["outerHoldoutRows"]
    rows = [cohort["rows"][i] for i in indices]
    new_output(args.output)
    eval_config = base_config(binding, args.fold, "evaluate", args.threads)
    eval_config.update({"frozenPath": str((args.input / "frozen.json").resolve()),
                        "frozenSha256": digest(args.input / "frozen.json"), "evaluationRows": indices})
    write_json(args.output / "config.json", eval_config)
    started, results = time.perf_counter(), {}
    for family, checkpoint in frozen["states"].items():
        state = checked_checkpoint(args.input, checkpoint["statePath"], checkpoint["stateSha256"])
        probabilities = predict_control(state, rows, cohort["clips"])
        results[family] = {"setting": checkpoint["setting"], "metrics": score_predictions(probabilities, rows)}
        write_json(args.output / f"{family}-predictions.json",
                   {"rowIndices": indices, "probabilities": probabilities.tolist()})
    report = {"configSha256": digest(args.output / "config.json"), "results": results,
              "elapsedSeconds": time.perf_counter() - started, "evaluationPartition": "outerHoldoutRows",
              "interpretation": "Exploratory speaker-grouped rating controls; no pronunciation validation",
              **FALSE_FLAGS}
    require(eval_config["sourceSha256"] == source_hashes(), "Source changed during outer evaluation")
    write_json(args.output / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inner", "refit", "evaluate"))
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--fold", type=int, required=True, choices=range(5))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, help="Completed previous-phase artifact directory")
    parser.add_argument("--families", nargs="+", choices=FAMILIES, default=list(FAMILIES))
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    require(args.max_iterations > 0 and 1 <= args.threads <= 8 and
            len(set(args.families)) == len(args.families), "Invalid optimizer or family settings")
    require((args.phase == "inner") == (args.input is None), "Only refit/evaluate require --input")
    import torch
    # Importing the reused numerical helper sets legacy environment thread limits.
    # The explicit torch limit below determines this process's CPU optimizer budget.
    import speechocean_r_rater_cv  # noqa: F401
    torch.set_num_threads(args.threads)
    result = {"inner": run_inner, "refit": run_refit, "evaluate": run_evaluate}[args.phase](args)
    print(json.dumps({"phase": args.phase, "fold": args.fold, "output": str(args.output),
                      "elapsedSeconds": result["elapsedSeconds"]}), flush=True)


if __name__ == "__main__":
    main()
