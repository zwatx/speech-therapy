"""Freeze the complete fixed development comparison before any outer scoring.

The release enumerates 85 independent refit directories representing 95 fitted
pipeline/fold combinations, plus the already matched child-prior comparator.
Every evaluation command is generated here from the fixed protocol; manifests
cannot inject commands. This module does not choose models from outer results.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import multiphone_controls as controls
from multiphone_cache import atomic_json, digest
from multiphone_child_train import fit_priors, is_child

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE.parents[1] / "docs/model/multiphone-outer-evaluation-protocol.md"
BASE = HERE / "outputs/multiphone-20260926"
HELPERS = {
    "global": "multiphone_global_outer.py",
    "full13": "multiphone_local_outer.py",
    "variant": "multiphone_scalar_variant_outer.py",
    "head": "multiphone_head_outer.py",
    "controls": "multiphone_control_outer.py",
}
RECIPE_NAMES = ("multiphone-heads-v1.json", "multiphone-local-train-v1.json",
                "multiphone-local-ablation-v1.json", "multiphone-local-heads-v1.json",
                "multiphone-phonetic-heads-v1.json", "multiphone-local-outer-v1.json",
                "multiphone-head-outer-v1.json", "multiphone-control-outer-v1.json",
                "multiphone-local-features-v1.json", "multiphone-phonetic-features-v1.json")
require = controls.require


def read_json(path):
    return json.loads(path.read_text())


def fixed_files(base):
    return [PROTOCOL, Path(__file__), HERE / "multiphone_controls.py", HERE / "multiphone_child_train.py",
            HERE / "multiphone_outer_statistics.py", HERE / "multiphone_outer_report.py",
            HERE / "multiphone_outer_evaluate_queue.py", HERE / "multiphone_local_head_queue.py",
            base / "cohort.json", base / "splits.json"] + \
           [HERE / name for name in HELPERS.values()] + [HERE / "experiments" / name for name in RECIPE_NAMES]


def expected_jobs(base):
    jobs = []

    def append(kind, name, fold, path, regime="all-age", **fields):
        jobs.append({"kind": kind, "name": name, "fold": fold, "regime": regime,
                     "input": str((base / path).resolve()),
                     "output": str((base / "outer-evaluation-v1" / f"{name}-f{fold}").resolve()), **fields})

    for fold in range(5):
        append("global", "global-wavlm-mean", fold, f"global-outer/fold-{fold}-refit")
        append("full13", "scalar-full13", fold, f"local-outer/fold-{fold}-refit")
        for variant in ("target-posterior", "local-scalars"):
            append("variant", "scalar-" + variant, fold, f"scalar-variant-outer/{variant}-f{fold}-refit", variant=variant)
        for encoder, families in (("local", ("embedding", "embedding-scalars")),
                                  ("phonetic", ("target", "target-scalars", "global", "global-scalars"))):
            for family in families:
                for regime in ("all-age", "child-only"):
                    name = f"{encoder}-{family}-{regime}"
                    append("head", name, fold, f"head-outer/{name}-f{fold}-refit", regime,
                           encoderKind=encoder, family=family)
        append("controls", "controls", fold, f"controls-outer/fold-{fold}-refit")
    require(len(jobs) == 85 and len({job["output"] for job in jobs}) == 85, "Incomplete fixed job inventory")
    return jobs


def source_guard(source_pins):
    require(all(digest(HERE / name) == value for name, value in source_pins.items()), "Refit implementation changed")


def pinned_inputs(value):
    """Flatten existing explicit path/hash bindings; never infer a missing hash."""
    result = {}

    def add(path, sha):
        if isinstance(path, str) and Path(path).is_absolute():
            require(isinstance(sha, str) and len(sha) == 64, "Invalid explicit input digest")
            require(path not in result or result[path] == sha, "Conflicting input digest bindings")
            result[path] = sha

    def visit(item):
        if isinstance(item, dict):
            if "path" in item and "sha256" in item:
                add(item["path"], item["sha256"])
            for key, child in item.items():
                if key.endswith("Path") and key[:-4] + "Sha256" in item:
                    add(child, item[key[:-4] + "Sha256"])
                if Path(key).is_absolute() and isinstance(child, str) and len(child) == 64:
                    add(key, child)
                if key.endswith("SourceSha256") or key == "sourceSha256":
                    if isinstance(child, dict):
                        for name, sha in child.items():
                            add(str((HERE / name).resolve()), sha)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    require(all(digest(Path(path)) == sha for path, sha in result.items()), "Pinned refit input changed")
    return result


def checked_refit(job, cohort, splits):
    directory = Path(job["input"])
    config, frozen = read_json(directory / "config.json"), read_json(directory / "frozen.json")
    fold = splits["folds"][job["fold"]]
    expected_fit = [i for i in fold["outerFitRows"] if job["regime"] == "all-age" or is_child(cohort["rows"][i])]
    require(config["fold"] == job["fold"] and config["fitRows"] == expected_fit
            and config["outerOutcomesUsed"] is frozen["outerOutcomesUsed"] is False
            and frozen["configSha256"] == digest(directory / "config.json")
            and config["authorTestInferencePerformed"] is False
            and not list(directory.glob("*predictions.json")), "Refit scope, rows or publication differs")
    source_guard(config["sourceSha256"])
    files = [directory / "config.json", directory / "frozen.json"]
    if job["kind"] == "controls":
        verified = read_json(directory / "verified.json")
        require(config["phase"] == "refit" and verified["phase"] == "refit" and verified["complete"] is True
                and verified["everyInnerCandidateReplayed"] is True
                and verified["holdoutPredictionsComputed"] is False
                and set(frozen["states"]) == set(controls.FAMILIES), "Unverified control refit")
        source_guard(verified["sourceSha256"])
        for path, sha in {**verified["inputArtifactsSha256"], **verified["frozenArtifactsSha256"]}.items():
            require(digest(Path(path)) == sha, "Control refit binding differs")
        for entry in frozen["states"].values():
            controls.checked_checkpoint(directory, entry["statePath"], entry["stateSha256"])
            files.append(directory / entry["statePath"])
        files.append(directory / "verified.json")
    else:
        require(config["phase"] == "outer-refit" and frozen["complete"] is True
                and frozen["holdoutPredictionsComputed"] is False, "Expected complete unscored refit")
        neural = job["kind"] in ("head", "global")
        checkpoint = directory / ("checkpoint.pt" if neural else "checkpoint.json")
        require(digest(checkpoint) == frozen["checkpointSha256"], "Refit checkpoint changed")
        files.append(checkpoint)
        if neural:
            require(config["fixedEpochs"] == config["selected"]["epochs"] == frozen["epochsRun"]
                    and config["learningRate"] == config["selected"]["lr"]
                    and digest(directory / "history.json") == frozen["historySha256"], "Refit fixed budget differs")
            files.append(directory / "history.json")
        if job["kind"] == "head":
            require(config["kind"] == job["encoderKind"] and config["family"] == job["family"]
                    and config["regime"] == job["regime"] and config["seed"] == 7, "Head pipeline identity differs")
        elif job["kind"] == "global":
            require(config["encoder"] == "wavlm-base-plus" and config["head"] == "mean" and config["seed"] == 7,
                    "Global pipeline identity differs")
        elif job["kind"] == "variant":
            require(config["variant"] == job["variant"], "Scalar variant identity differs")
        for path, sha in config["innerArtifactsSha256"].items():
            require(digest(Path(path)) == sha, "Inner setting-selection artifact changed")
    result = {str(path.resolve()): digest(path) for path in files}
    result.update(pinned_inputs(config))
    if job["kind"] == "controls":
        result.update(pinned_inputs(verified))
    return result, config


def guard_release(manifest):
    require(manifest["complete"] is True and manifest["phase"] == "frozen-development-release"
            and manifest["holdoutPredictionsAllowed"] is True and manifest["authorTestInferenceAllowed"] is False
            and manifest["jobs"] == expected_jobs(Path(manifest["base"])), "Release scope or fixed job inventory differs")
    mandatory = fixed_files(Path(manifest["base"]))
    for job in manifest["jobs"]:
        directory = Path(job["input"])
        names = ["config.json", "frozen.json"]
        if job["kind"] == "controls":
            names += ["verified.json"] + [family + ".json" for family in controls.FAMILIES]
        elif job["kind"] in ("head", "global"):
            names += ["checkpoint.pt", "history.json"]
        else:
            names += ["checkpoint.json"]
        mandatory += [directory / name for name in names]
    require({str(path.resolve()) for path in mandatory} <= set(manifest["filesSha256"]),
            "Release omits a mandatory refit, recipe, source or data pin")
    require(all(digest(Path(path)) == sha for path, sha in manifest["filesSha256"].items()),
            "A released refit, source, protocol or input changed")


def freeze(base, output):
    require(output.resolve().is_relative_to((HERE / "outputs").resolve()) and not output.exists(),
            "Choose a new release file inside ignored research outputs")
    cohort, splits, _ = controls.load_study(base / "cohort.json", base / "splits.json")
    jobs = expected_jobs(base)
    require(not any(Path(job["output"]).exists() for job in jobs), "Evaluation destination already exists before release")
    paths = fixed_files(base)
    files = {str(path.resolve()): digest(path) for path in paths}
    selected, child_priors = {}, {}
    for job in jobs:
        pins, config = checked_refit(job, cohort, splits)
        files.update(pins)
        files.update({str((HERE / name).resolve()): sha for name, sha in config["sourceSha256"].items()})
        selected[f"{job['name']}-f{job['fold']}"] = {
            key: config[key] for key in ("selected", "trials", "alpha", "learningRate", "fixedEpochs",
                                        "innerArtifactsSha256", "inputArtifactsSha256", "binding", "inputBinding") if key in config}
        if job["regime"] == "child-only":
            expected = fit_priors([cohort["rows"][i] for i in config["fitRows"]])
            require(config["priorState"] == expected, "Child prior does not match actual fit rows")
            child_priors[str(job["fold"])] = expected
    require(set(child_priors) == {str(i) for i in range(5)}, "Missing child prior comparator")
    result = {"complete": True, "phase": "frozen-development-release", "createdAt": time.time(),
              "base": str(base.resolve()), "fittedPipelineCount": 19, "fittedPipelineFoldCount": 95,
              "additionalComparators": ["child-only-phone-prior"], "jobs": jobs,
              "filesSha256": files, "selectedInnerEvidence": selected, "childPriorStateByFold": child_priors,
              "eligibleRows": [i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"]],
              "expectedEvaluationRowsByFold": {str(f["fold"]): f["outerHoldoutRows"] for f in splits["folds"]},
              "holdoutPredictionsAllowed": True, "authorTestInferenceAllowed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False,
              "interpretation": "Development cross-fit comparison; architecture design used overlapping inner folds"}
    guard_release(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


def evaluation_command(job, base):
    command = [sys.executable, str(HERE / HELPERS[job["kind"]]), "evaluate",
               "--input", job["input"], "--output", job["output"]]
    if job["kind"] in ("full13", "variant", "controls"):
        command += ["--cohort", str(base / "cohort.json"), "--splits", str(base / "splits.json"), "--fold", str(job["fold"])]
    if job["kind"] in ("full13", "variant"):
        command += ["--features", str(base / "ctc-local-full/features/features.json")]
    if job["kind"] == "variant":
        command += ["--variant", job["variant"]]
    return command


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.base, args.output)
    print(f"Frozen {len(result['jobs'])} refit directories for {result['fittedPipelineFoldCount']} comparisons")
