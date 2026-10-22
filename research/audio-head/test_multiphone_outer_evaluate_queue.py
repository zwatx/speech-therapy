"""Synthetic publication/queue tests; no speech inference or outer scoring."""
import contextlib
import fcntl
import io
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import multiphone_outer_evaluate_queue as queue
from test_multiphone_controls import synthetic_study


class EvaluationQueueTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=queue.HERE / "outputs", prefix="test-eval-queue-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.cohort, self.splits = synthetic_study()
        self.save(self.base / "cohort.json", self.cohort)
        self.save(self.base / "splits.json", self.splits)
        self.path = self.base / "release.json"
        self.jobs = queue.release.expected_jobs(self.base)
        self.files = {str((queue.HERE / name).resolve()): queue.digest(queue.HERE / name) for name in queue.QUEUE_SOURCES}
        self.files.update({str(self.base / name): queue.digest(self.base / name) for name in ("cohort.json", "splits.json")})
        # Full mandatory 85-job catalog, fabricated checkpoints, real release guards.
        for job in self.jobs:
            directory = Path(job["input"])
            directory.mkdir(parents=True)
            config = {"sourceSha256": {}, "alpha": .01, "mask": [True, False]}
            self.save(directory / "config.json", config)
            self.save(directory / "frozen.json", {"fixture": True})
            names = ["config.json", "frozen.json"]
            if job["kind"] == "controls":
                self.save(directory / "verified.json", {"sourceSha256": {}})
                names += ["verified.json", *[family + ".json" for family in queue.release.controls.FAMILIES]]
            elif job["kind"] in ("head", "global"):
                names += ["checkpoint.pt", "history.json"]
            else:
                names += ["checkpoint.json"]
            for name in names:
                path = directory / name
                if not path.exists():
                    path.write_text("synthetic checkpoint, never loaded for inference")
                self.files[str(path)] = queue.digest(path)
        self.manifest = {"complete": True, "phase": "frozen-development-release", "holdoutPredictionsAllowed": True,
                         "authorTestInferenceAllowed": False, "base": str(self.base), "jobs": self.jobs,
                         "filesSha256": self.files, "eligibleRows": list(range(len(self.cohort["rows"]))),
                         "expectedEvaluationRowsByFold": {str(f["fold"]): f["outerHoldoutRows"] for f in self.splits["folds"]}}
        self.commit_release()
        self.fixed_patch = patch.object(queue.release, "fixed_files", return_value=[])
        self.fixed_patch.start()
        self.addCleanup(self.fixed_patch.stop)

    def save(self, path, value):
        queue.atomic_json(path, value)

    def commit_release(self):
        self.save(self.path, self.manifest)
        self.sha = queue.digest(self.path)

    def publish(self, job):
        output, directory = Path(job["output"]), Path(job["input"])
        output.mkdir(parents=True)
        expected = self.manifest["expectedEvaluationRowsByFold"][str(job["fold"]) ]
        prediction = {"rowIndices": expected, "probabilities": [[.2, .1, .7] for _ in expected]}
        flags = {key: False for key in ("authorTestInferencePerformed", "clinicalUseEligible", "learnerFeedbackEligible")}
        frozen = {path: sha for path, sha in self.files.items() if Path(path).is_relative_to(directory)}
        report = {**flags, "complete": True, "phase": "outer-evaluation", "fold": job["fold"],
                  "sourceSha256": {}, "frozenArtifactsSha256": frozen, "evaluationRows": expected,
                  "alpha": .01, "mask": [True, False]}
        if job["kind"] == "controls":
            config = {"phase": "evaluate", "fold": job["fold"], "evaluationRows": expected,
                      "frozenPath": str(directory / "frozen.json"), "frozenSha256": self.files[str(directory / "frozen.json")]}
            self.save(output / "config.json", config)
            report = {**flags, "evaluationPartition": "outerHoldoutRows", "configSha256": queue.digest(output / "config.json"),
                      "results": {family: {} for family in queue.release.controls.FAMILIES}}
            self.save(output / "report.json", report)
            paths = []
            for family in queue.release.controls.FAMILIES:
                path = output / f"{family}-predictions.json"
                self.save(path, prediction)
                paths.append(path)
            self.save(output / "verified.json", {**flags, "complete": True, "phase": "evaluate", "sourceSha256": {},
                      "frozenInputArtifactsSha256": frozen, "reportSha256": queue.digest(output / "report.json"),
                      "predictionArtifactsSha256": {str(path): queue.digest(path) for path in paths}})
        else:
            self.save(output / "predictions.json", prediction)
            report["predictionsSha256"] = queue.digest(output / "predictions.json")
            if job["kind"] == "head":
                report.update(kind=job["encoderKind"], family=job["family"], regime=job["regime"])
            elif job["kind"] == "global":
                report.update(encoder="wavlm-base-plus", head="mean", seed=7)
            elif job["kind"] == "variant":
                report["variant"] = job["variant"]
            if job["kind"] in ("head", "global"):
                self.save(output / "prior.json", prediction)
                report["priorSha256"] = queue.digest(output / "prior.json")
            self.save(output / "report.json", report)

    def fake_child(self, command, record, log, save):
        original = next(job for job in self.jobs if job["output"] == record["output"])
        self.assertEqual(command, queue.release.evaluation_command(original, self.base))
        self.assertNotIn("command", self.manifest["jobs"][0])
        record.update(pid=1234, startedAt=time.time(), command=command, logPath=str(log), state="running")
        log.write_text("synthetic helper")
        save()
        self.publish(record)
        record.update(exitCode=0, finishedAt=time.time(), state="complete")
        save()

    def run_queue(self, child=None):
        with patch.object(queue, "run_child", side_effect=child or self.fake_child), contextlib.redirect_stdout(io.StringIO()):
            return queue.run(self.path, self.sha)

    def test_all85_helpers_publish_verified_artifact_ledger(self):
        ledger = self.run_queue()
        self.assertTrue(ledger["complete"])
        self.assertEqual(ledger["releaseSha256"], self.sha)
        self.assertEqual(ledger["releasePath"], str(self.path))
        self.assertEqual(len(ledger["jobs"]), 85)
        for record in ledger["jobs"]:
            self.assertEqual(record["state"], "complete")
            self.assertEqual(record["exitCode"], 0)
            pins = record["verified"]["artifactSha256"]
            self.assertIn(str(Path(record["output"]) / "report.json"), pins)
            queue.hashes_match(pins)
        with self.assertRaisesRegex(ValueError, "no implicit resume"):
            self.run_queue()

    def test_release_digest_partial_inventory_and_unpinned_queue_block_launch(self):
        with patch.object(queue, "run_child") as child:
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                queue.run(self.path, "0" * 64)
            self.manifest["jobs"] = self.jobs[:-1]
            self.commit_release()
            with self.assertRaisesRegex(ValueError, "inventory"):
                queue.run(self.path, self.sha)
            self.manifest["jobs"] = self.jobs
            del self.files[str(queue.HERE / queue.QUEUE_SOURCES[0])]
            self.commit_release()
            with self.assertRaisesRegex(ValueError, "pin queue"):
                queue.run(self.path, self.sha)
            child.assert_not_called()

    def test_any_existing_destination_blocks_every_launch(self):
        Path(self.jobs[-1]["output"]).mkdir(parents=True)
        with patch.object(queue, "run_child") as child, self.assertRaisesRegex(ValueError, "no implicit resume"):
            queue.run(self.path, self.sha)
        child.assert_not_called()

    def test_child_failure_stops_and_retains_failed_ledger_without_retry(self):
        calls = []
        def fail(command, record, log, save):
            calls.append(command)
            record.update(pid=1234, state="failed", exitCode=4)
            save()
            raise RuntimeError("synthetic child failure")
        with self.assertRaisesRegex(RuntimeError, "child failure"):
            self.run_queue(fail)
        ledger = queue.read_json(self.base / "outer-evaluate-queue-v1.json")
        self.assertFalse(ledger["complete"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(ledger["jobs"][0]["state"], "failed")
        self.assertFalse(Path(self.jobs[1]["output"]).exists())

    def test_prediction_rows_probability_integrity_and_digest_are_independent_checks(self):
        job = self.jobs[0]
        self.publish(job)
        output = Path(job["output"])
        path = output / "predictions.json"
        original = queue.read_json(path)
        report = queue.read_json(output / "report.json")
        for data, message in (({**original, "rowIndices": original["rowIndices"][::-1]}, "outer rows"),
                              ({**original, "probabilities": [[2., -1., 0.] for _ in original["rowIndices"]]}, "probabilities")):
            self.save(path, data)
            report["predictionsSha256"] = queue.digest(path)
            self.save(output / "report.json", report)
            with self.assertRaisesRegex(ValueError, message):
                queue.verify_output(job, self.manifest, self.cohort)
        self.save(path, original)
        with self.assertRaisesRegex(ValueError, "digest"):
            queue.verify_output(job, self.manifest, self.cohort)

    def test_control_verification_and_complete_family_coverage_are_required(self):
        job = next(j for j in self.jobs if j["kind"] == "controls")
        self.publish(job)
        output = Path(job["output"])
        verified = queue.read_json(output / "verified.json")
        verified["complete"] = False
        self.save(output / "verified.json", verified)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            queue.verify_output(job, self.manifest, self.cohort)
        verified["complete"] = True
        verified["predictionArtifactsSha256"].popitem()
        self.save(output / "verified.json", verified)
        with self.assertRaisesRegex(ValueError, "coverage or digest"):
            queue.verify_output(job, self.manifest, self.cohort)

    def test_changed_frozen_artifact_during_child_stops_completion(self):
        def mutate(*args):
            self.fake_child(*args)
            path = Path(args[1]["input"]) / "checkpoint.pt"
            path.write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.run_queue(mutate)
        self.assertFalse(queue.read_json(self.base / "outer-evaluate-queue-v1.json")["complete"])

    def test_final_guard_rechecks_previously_verified_outputs(self):
        calls = 0
        def mutate(*args):
            nonlocal calls
            self.fake_child(*args)
            calls += 1
            if calls == 85:
                path = Path(self.jobs[0]["output"]) / "report.json"
                path.write_text(path.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.run_queue(mutate)
        self.assertFalse(queue.read_json(self.base / "outer-evaluate-queue-v1.json")["complete"])

    def test_exclusive_lock_prevents_second_queue(self):
        with (self.base / "outer-evaluate-queue.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(queue, "run_child") as child, self.assertRaises(BlockingIOError):
                queue.run(self.path, self.sha)
            child.assert_not_called()

    def test_real_tiny_process_cannot_start_until_pid_is_persisted(self):
        ledger = self.base / "gate-ledger.json"
        marker = self.base / "gate-marker.txt"
        record = {}
        def save():
            self.save(ledger, record)
        script = "import json,os,pathlib,sys; d=json.loads(pathlib.Path(sys.argv[1]).read_text()); assert d['pid']==os.getpid(); pathlib.Path(sys.argv[2]).write_text('PID recorded before execution')"
        queue.run_child([sys.executable, "-c", script, str(ledger), str(marker)], record, self.base / "gate.log", save)
        self.assertEqual(record["exitCode"], 0)
        self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
