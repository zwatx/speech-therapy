"""One fresh serial evaluation of the complete, explicitly pinned release.

No command comes from release JSON. All 85 commands use the reviewed fixed
inventory. A failed or interrupted attempt is retained, never implicitly resumed.
"""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import signal
import sys
import time

import multiphone_outer_release as release
from multiphone_cache import atomic_json, digest
from multiphone_local_head_queue import run_child
from multiphone_verify import validate_predictions

HERE = Path(__file__).resolve().parent
QUEUE_SOURCES = ("multiphone_outer_evaluate_queue.py", "multiphone_local_head_queue.py")
read_json, require = release.read_json, release.require


def hashes_match(pins):
    require(all(digest(Path(path)) == sha for path, sha in pins.items()), "Pinned evaluation input changed")


def load_contract(path, expected_sha):
    require(isinstance(expected_sha, str) and len(expected_sha) == 64 and digest(path) == expected_sha,
            "Release SHA-256 differs from the explicitly approved value")
    manifest = read_json(path)
    release.guard_release(manifest)
    base = Path(manifest["base"])
    require(base.resolve().is_relative_to((HERE / "outputs").resolve()), "Use the local ignored research outputs")
    source_paths = [str((HERE / name).resolve()) for name in QUEUE_SOURCES]
    require(all(name in manifest["filesSha256"] for name in source_paths), "Release must pin queue and PID-gate sources")
    require(digest(path) == expected_sha, "Release changed while loading")
    cohort, splits, _ = release.controls.load_study(base / "cohort.json", base / "splits.json")
    expected = {str(fold["fold"]): fold["outerHoldoutRows"] for fold in splits["folds"]}
    require(manifest["expectedEvaluationRowsByFold"] == expected
            and all(rows == sorted(rows) for rows in expected.values())
            and manifest["eligibleRows"] == [i for i, row in enumerate(cohort["rows"]) if row["trainingEligible"]],
            "Release row coverage differs from its bound speaker study")
    return manifest, cohort


def job_guard(manifest, job, release_path, expected_sha):
    require(digest(release_path) == expected_sha, "Release changed during evaluation")
    directory = Path(job["input"]).resolve()
    # The helpers revalidate their full feature bindings themselves. This guard
    # checks every released source/recipe and this job's frozen artifacts; whole
    # release bytes are checked again at completion, avoiding 85 full-cache scans.
    fixed = {str(path.resolve()) for path in release.fixed_files(Path(manifest["base"]))}
    pins = {path: sha for path, sha in manifest["filesSha256"].items()
            if path in fixed or Path(path).suffix == ".py" or Path(path).is_relative_to(directory)}
    require(str(directory / "config.json") in pins and str(directory / "frozen.json") in pins,
            "Missing frozen job pins")
    hashes_match(pins)


def published_pin_map(value, released, required=()):
    require(isinstance(value, dict) and set(required) <= set(value)
            and all(released.get(path) == sha for path, sha in value.items()),
            "Evaluation refers to an unbound or different frozen input")
    hashes_match(value)


def check_predictions(path, expected, cohort):
    saved = read_json(path)
    require(saved["rowIndices"] == expected and len(set(expected)) == len(expected),
            "Predictions do not exactly cover the declared outer rows")
    validate_predictions(saved["probabilities"], [cohort["rows"][i]["raterCounts"] for i in expected])


def verify_output(job, manifest, cohort):
    output, directory = Path(job["output"]), Path(job["input"])
    report = read_json(output / "report.json")
    config = read_json(directory / "config.json")
    expected = manifest["expectedEvaluationRowsByFold"][str(job["fold"])]
    released = manifest["filesSha256"]
    require(all(report.get(flag) is False for flag in
                ("authorTestInferencePerformed", "clinicalUseEligible", "learnerFeedbackEligible")),
            "Evaluation research scope differs")
    artifacts = [output / "report.json"]
    if job["kind"] == "controls":
        verified, evaluated = read_json(output / "verified.json"), read_json(output / "config.json")
        require(verified["complete"] is True and verified["phase"] == "evaluate"
                and all(verified.get(flag) is False for flag in
                        ("authorTestInferencePerformed", "clinicalUseEligible", "learnerFeedbackEligible"))
                and report["evaluationPartition"] == "outerHoldoutRows"
                and evaluated["phase"] == "evaluate" and evaluated["fold"] == job["fold"]
                and evaluated["evaluationRows"] == expected
                and evaluated["frozenPath"] == str((directory / "frozen.json").resolve())
                and evaluated["frozenSha256"] == released[str((directory / "frozen.json").resolve())]
                and report["configSha256"] == digest(output / "config.json")
                and verified["reportSha256"] == digest(output / "report.json")
                and set(report["results"]) == set(release.controls.FAMILIES), "Control evaluation is incomplete or differently scoped")
        prior_verified = read_json(directory / "verified.json")
        require(verified["sourceSha256"] == prior_verified["sourceSha256"], "Control verification source differs")
        published_pin_map(verified["frozenInputArtifactsSha256"], released,
                          [str((directory / name).resolve()) for name in
                           ("verified.json", "config.json", "frozen.json", *[family + ".json" for family in release.controls.FAMILIES])])
        predictions = [output / f"{family}-predictions.json" for family in release.controls.FAMILIES]
        actual = {str(path.resolve()): digest(path) for path in predictions}
        require(verified["predictionArtifactsSha256"] == actual
                and {path.name for path in output.glob("*-predictions.json")} == {path.name for path in predictions},
                "Control prediction artifact coverage or digest differs")
        artifacts += [output / "config.json", output / "verified.json", *predictions]
    else:
        require(report["complete"] is True and report["phase"] == "outer-evaluation"
                and report["fold"] == job["fold"] and report["sourceSha256"] == config["sourceSha256"],
                "Evaluation is incomplete or belongs to another refit")
        if "evaluationRows" in report:
            require(report["evaluationRows"] == expected, "Report outer rows differ")
        if job["kind"] == "head":
            require(report["kind"] == job["encoderKind"] and report["family"] == job["family"]
                    and report["regime"] == job["regime"], "Head evaluation identity differs")
        elif job["kind"] == "global":
            require(report["encoder"] == "wavlm-base-plus" and report["head"] == "mean"
                    and report["seed"] == 7, "Global evaluation identity differs")
        elif job["kind"] == "variant":
            require(report["variant"] == job["variant"] and report["mask"] == config["mask"]
                    and report["alpha"] == config["alpha"], "Scalar variant evaluation differs")
        else:
            require(report["alpha"] == config["alpha"], "Full scalar setting differs")
        checkpoint = "checkpoint.pt" if job["kind"] in ("head", "global") else "checkpoint.json"
        required = [str((directory / name).resolve()) for name in ("config.json", "frozen.json", checkpoint)]
        if checkpoint.endswith(".pt"):
            required.append(str((directory / "history.json").resolve()))
        published_pin_map(report["frozenArtifactsSha256"], released, required)
        predictions = [output / "predictions.json"]
        require(report["predictionsSha256"] == digest(predictions[0]), "Prediction digest differs")
        artifacts += predictions
        if job["kind"] in ("head", "global"):
            prior = output / "prior.json"
            require(report["priorSha256"] == digest(prior), "Matched prior digest differs")
            check_predictions(prior, expected, cohort)
            artifacts.append(prior)
    for path in predictions:
        check_predictions(path, expected, cohort)
    return {str(path.resolve()): digest(path) for path in artifacts}


def run(release_path, expected_sha):
    manifest, cohort = load_contract(release_path, expected_sha)
    base = Path(manifest["base"])
    ledger_path = base / "outer-evaluate-queue-v1.json"
    log_directory = base / "outer-evaluation-logs-v1"
    with (base / "outer-evaluate-queue.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not ledger_path.exists() and not log_directory.exists()
                and all(not Path(job["output"]).exists() for job in manifest["jobs"]),
                "Existing ledger, log or output requires explicit recovery; no implicit resume")
        log_directory.mkdir(mode=0o700)
        ledger = {"releasePath": str(release_path.resolve()), "releaseSha256": expected_sha,
                  "phase": "outer-evaluation", "pid": os.getpid(), "startedAt": time.time(),
                  "complete": False, "plannedJobs": len(manifest["jobs"]), "plannedPipelineFolds": 95, "jobs": []}

        def save():
            atomic_json(ledger_path, ledger)
            with ledger_path.open("rb") as stream:
                os.fsync(stream.fileno())

        save()
        try:
            for job in release.expected_jobs(base):
                record = {**job, "state": "pending"}
                ledger["jobs"].append(record)
                save()
                job_guard(manifest, job, release_path, expected_sha)
                require(not Path(job["output"]).exists(), "Evaluation destination appeared before launch")
                command = release.evaluation_command(job, base)
                run_child(command, record, log_directory / f"{job['name']}-f{job['fold']}.log", save)
                record["verified"] = {"artifactSha256": verify_output(job, manifest, cohort)}
                job_guard(manifest, job, release_path, expected_sha)
                record["state"] = "complete"
                save()
                print(f"Verified {job['name']} fold {job['fold']}", flush=True)
            require(digest(release_path) == expected_sha, "Release changed before completion")
            release.guard_release(manifest)
            for record in ledger["jobs"]:
                hashes_match(record["verified"]["artifactSha256"])
            require(len(ledger["jobs"]) == 85 and all(job["state"] == "complete" and job["exitCode"] == 0
                                                     for job in ledger["jobs"]),
                    "Incomplete evaluation job coverage")
            ledger.update(complete=True, finishedAt=time.time())
            save()
        except BaseException as error:
            if "record" in locals():
                record.update(state="failed", failure=repr(error))
            ledger.update(complete=False, stoppedAt=time.time(), failure=repr(error))
            save()
            raise
    return ledger


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    result = run(args.release, args.expected_sha256)
    print(f"Evaluation queue complete={result['complete']}; {len(result['jobs'])} verified jobs")
