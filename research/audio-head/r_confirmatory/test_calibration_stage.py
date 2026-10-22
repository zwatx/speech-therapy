"""Lifecycle tests use only freshly written made-up input summaries."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from r_confirmatory.calibration_stage import (
    declare_calibration, run_calibration, audit_calibration_stage,
)
from r_confirmatory.test_dev_calibration_inputs import fixture

HERE = Path(__file__).parent.resolve()
PROJECT = HERE.parents[2]


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    return pin(path)


def saved_fixture(directory):
    artifacts, _, expected = fixture()
    bindings = {}
    for name in ("selection", "split"):
        bindings[name] = write(directory / (name + ".json"), artifacts[name])
    artifacts["closedDeclaration"]["inputs"] = copy.deepcopy(bindings)
    bindings["closedDeclaration"] = write(directory / "closedDeclaration.json", artifacts["closedDeclaration"])
    clips = {"declaration": bindings["closedDeclaration"],
             "records": [{"tokenId": "made-up/a", "state": "complete"},
                         {"tokenId": "made-up/b", "state": "complete"}]}
    bindings["clips"] = write(directory / "clips.json", clips)
    retention_path = directory / "retention.json"
    retention_path.write_bytes(b"not parsed: synthetic hash-only retention")
    bindings["retention"] = pin(retention_path)
    for name, upstream in (("extract", ("clips",)), ("predictions", ("extract", "clips")),
                           ("tokens", ("extract", "predictions", "retention"))):
        artifacts[name]["declaration"] = bindings["closedDeclaration"]
        artifacts[name]["upstream"] = {key: bindings[key] for key in upstream}
        bindings[name] = write(directory / (name + ".json"), artifacts[name])
    sources = {"stage": HERE / "calibration_stage.py", "adapter": HERE / "dev_calibration_inputs.py",
               "fit": HERE / "calibrate.py", "auditor": HERE / "calibration_audit.py",
               "packageInit": HERE / "__init__.py",
               "policy": PROJECT / "docs/consumer-assessment/r-confirmatory-decisions-20261003.json",
               "policyDocument": PROJECT / "docs/consumer-assessment/r-confirmatory-decisions-20261003.md",
               "requirements": HERE.parent / "requirements.txt",
               "requirementsLock": HERE.parent / "requirements.lock.txt"}
    return bindings, {name: pin(path) for name, path in sources.items()}, expected


class CalibrationStageTests(unittest.TestCase):
    def test_source_hash_anchor_and_environment_guards_precede_scientific_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            bindings, sources, expected = saved_fixture(directory)
            bad_sources = copy.deepcopy(sources)
            bad_sources["stage"]["sha256"] = "0" * 64
            root = directory / "environment-guard"
            with self.assertRaisesRegex(ValueError, "binding_hash_mismatch"):
                declare_calibration(bindings, bad_sources, root, expected)
            self.assertFalse(root.exists())
            declared = declare_calibration(bindings, sources, root, expected)
            with self.assertRaisesRegex(ValueError, "saved_hash_mismatch"):
                run_calibration(root, "0" * 64)
            self.assertFalse((root / "fit").exists())
            changed = "2" if os.environ.get("OMP_NUM_THREADS") != "2" else "3"
            with patch.dict(os.environ, {"OMP_NUM_THREADS": changed}):
                with self.assertRaisesRegex(ValueError, "environment_changed"):
                    run_calibration(root, declared["declarationSha256"])
            self.assertTrue((root / "fit/started.json").exists())
            self.assertFalse((root / "fit/control.json").exists())

    def test_declared_success_and_started_interruption_cannot_be_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            bindings, sources, expected = saved_fixture(directory)
            root = directory / "retry-stage"
            declared = declare_calibration(bindings, sources, root, expected)
            anchor = declared["declarationSha256"]
            with self.assertRaises(ValueError):
                declare_calibration(bindings, sources, root, expected)
            fitted = run_calibration(root, anchor)
            before = {str(path): path.read_bytes() for path in root.rglob("*.json")}
            with self.assertRaises(ValueError):
                run_calibration(root, anchor)
            self.assertEqual({str(path): path.read_bytes() for path in root.rglob("*.json")}, before)
            audit_calibration_stage(root, anchor, fitted["completionSha256"])
            with self.assertRaises(ValueError):
                audit_calibration_stage(root, anchor, fitted["completionSha256"])
            second = directory / "interrupted-stage"
            declared = declare_calibration(bindings, sources, second, expected)
            (second / "fit").mkdir(mode=0o700)
            write(second / "fit/started.json", {"status": "started"})
            with self.assertRaises(ValueError):
                run_calibration(second, declared["declarationSha256"])
            self.assertFalse((second / "fit/control.json").exists())

    def test_input_tamper_after_declaration_consumes_attempt_before_fit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            bindings, sources, expected = saved_fixture(directory)
            root = directory / "tampered-stage"
            declared = declare_calibration(bindings, sources, root, expected)
            tokens = Path(bindings["tokens"]["path"])
            original = tokens.read_bytes()
            tokens.write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "binding_hash_mismatch"):
                run_calibration(root, declared["declarationSha256"])
            self.assertTrue((root / "fit/started.json").exists())
            self.assertFalse((root / "fit/control.json").exists())
            failure = json.loads((root / "fit/failure.json").read_bytes())
            self.assertEqual(failure["code"], "binding_hash_mismatch")
            self.assertNotIn("made-up", json.dumps(failure))
            tokens.write_bytes(original)
            with self.assertRaises(ValueError):
                run_calibration(root, declared["declarationSha256"])

    def test_numerical_fit_failure_keeps_started_and_safe_failure_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            bindings, sources, expected = saved_fixture(directory)
            tokens = Path(bindings["tokens"]["path"])
            value = json.loads(tokens.read_bytes())
            for row in value["records"]:
                row.update(k=10**12, n=10**12 + (row["tokenId"] == "made-up/a"))
            bindings["tokens"] = write(tokens, value)
            root = directory / "numerical-failure"
            declared = declare_calibration(bindings, sources, root, expected)
            with self.assertRaisesRegex(ValueError, "stage_execution_failed"):
                run_calibration(root, declared["declarationSha256"])
            self.assertTrue((root / "fit/started.json").exists())
            self.assertTrue((root / "fit/failure.json").exists())
            self.assertFalse((root / "fit/control.json").exists())
            failure_text = (root / "fit/failure.json").read_text()
            self.assertNotIn("made-up", failure_text)
            self.assertNotIn("1000000000000", failure_text)
            with self.assertRaises(ValueError):
                run_calibration(root, declared["declarationSha256"])

    def test_audit_rejects_fit_completion_when_a_terminal_failure_also_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            bindings, sources, expected = saved_fixture(directory)
            root = directory / "contradictory-fit"
            declared = declare_calibration(bindings, sources, root, expected)
            fitted = run_calibration(root, declared["declarationSha256"])
            write(root / "fit/failure.json", {"status": "failed"})
            with self.assertRaises(ValueError):
                audit_calibration_stage(root, declared["declarationSha256"], fitted["completionSha256"])
            self.assertTrue((root / "audit/started.json").exists())
            self.assertTrue((root / "audit/failure.json").exists())
            self.assertFalse((root / "audit/audit.json").exists())

    def test_fresh_private_declaration_runs_once_and_audits_saved_boundary_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            bindings, sources, expected = saved_fixture(directory)
            root = directory / "private-stage"
            declared = declare_calibration(bindings, sources, root, expected)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(pin(Path(declared["declarationPath"]))["sha256"], declared["declarationSha256"])
            declaration = json.loads(Path(declared["declarationPath"]).read_bytes())
            self.assertEqual(declaration["expectedCounts"], expected)
            self.assertEqual(declaration["inputBindings"], bindings)
            self.assertEqual(declaration["sourceBindings"], sources)
            self.assertFalse((root / "fit").exists())
            fitted = run_calibration(root, declared["declarationSha256"])
            control = json.loads(Path(fitted["controlPath"]).read_bytes())
            self.assertEqual(control["fullChildDenominator"], 2)
            self.assertEqual(control["selectedTokenDenominator"], 2)
            self.assertEqual(control["coefficients"]["slope"], 0)
            self.assertAlmostEqual(control["coefficients"]["intercept"], math.log(.525 / .475), places=10)
            audited = audit_calibration_stage(root, declared["declarationSha256"], fitted["completionSha256"])
            report = json.loads(Path(audited["auditPath"]).read_bytes())
            self.assertEqual(report["outcome"], "verified")
            self.assertEqual(report["fullChildDenominator"], 2)
            for path in root.rglob("*.json"):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            for stage in ("fit", "audit"):
                self.assertEqual(stat.S_IMODE((root / stage).stat().st_mode), 0o700)

    def test_external_fit_completion_anchor_rejects_rewritten_control_and_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            bindings, sources, expected = saved_fixture(directory)
            root = directory / "rewritten-completion"
            declared = declare_calibration(bindings, sources, root, expected)
            fitted = run_calibration(root, declared["declarationSha256"])
            control_path = Path(fitted["controlPath"])
            control = json.loads(control_path.read_bytes())
            control["coefficients"]["intercept"] += .1
            control_pin = write(control_path, control)
            completion_path = Path(fitted["completionPath"])
            completion = json.loads(completion_path.read_bytes())
            completion["control"] = control_pin
            write(completion_path, completion)
            with self.assertRaisesRegex(ValueError, "saved_hash_mismatch"):
                audit_calibration_stage(root, declared["declarationSha256"], fitted["completionSha256"])
            self.assertFalse((root / "audit/audit.json").exists())


if __name__ == "__main__":
    unittest.main()
