"""Declared confirmation stage examples use made-up artifacts exclusively."""
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from r_confirmatory_run.stages import declare_run, lock_predictions, join_outcomes, evaluate_run, audit_run

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
THREADS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
           "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS", "OMP_DYNAMIC", "MKL_DYNAMIC")


def write(path, value):
    path.write_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False).encode())
    path.chmod(0o600)
    return pin(path)


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def profile_fixture(directory):
    children = [{"childId": "1"}, {"childId": "2"}]
    keys = [{"childId": child, "tokenId": f"made-up/{child}/{suffix}"}
            for child in ("1", "2") for suffix in ("a", "b")]
    policy_path = PROJECT / "docs/consumer-assessment/r-confirmatory-decisions-20261003.json"
    policy = json.loads(policy_path.read_bytes())
    prepared = {"children": copy.deepcopy(children),
                "tokens": [{**key, "disposition": "selected"} for key in keys]}
    inputs = {"preparedTokens": write(directory / "prepared.json", prepared), "policy": pin(policy_path)}
    for name in ("candidate", "retained", "calibration"):
        inputs[name] = write(directory / (name + ".json"), {"madeUpModel": name})
    inputs["frozenProtocol"] = write(directory / "synthetic-protocol.json", {"synthetic": True,
                                           "selectedResearchPolicy": policy})
    source_paths = {"stages": HERE / "stages.py", "runPackageInit": HERE / "__init__.py",
                    "locking": HERE.parent / "r_confirmatory/locking.py",
                    "evaluate": HERE.parent / "r_confirmatory/evaluate.py",
                    "evaluationAudit": HERE.parent / "r_confirmatory/evaluation_audit.py",
                    "confirmatoryPackageInit": HERE.parent / "r_confirmatory/__init__.py",
                    "verdict": HERE / "verdict.py", "prediction": HERE / "prediction.py",
                    "execution": HERE / "execution.py", "requests": HERE / "requests.py", "outcomes": HERE / "outcomes.py",
                    "structuralProjection": HERE.parent / "r_confirmatory/structural_projection_v2.py",
                    "retainedLoader": HERE.parent / "ages_6_12_bundle/inference.py",
                    "retainedPackageInit": HERE.parent / "ages_6_12_bundle/__init__.py",
                    "retainedModelSource": HERE.parent / "multiphone_models.py",
                    "calibrationPredict": HERE.parent / "r_confirmatory/calibrate.py",
                    "calibrationPackageInit": HERE.parent / "r_confirmatory/__init__.py"}
    environment = {"python": platform.python_version(), "numpy": importlib.metadata.version("numpy"),
                   "platform": platform.platform(), "threadEnvironment": {key: os.environ.get(key) for key in THREADS}}
    return {"schemaVersion": 1, "mode": "synthetic", "expectedChildren": 2,
            "children": children, "selectedTokens": keys, "policy": policy,
            "inputBindings": inputs, "sourceBindings": {key: pin(path) for key, path in source_paths.items()},
            "environment": environment}


def predictions(profile, declaration):
    payload = {key: copy.deepcopy(profile[key]) for key in ("children", "selectedTokens")}
    payload["arms"] = {arm: [{**key, "status": "processed",
                             "probability": (.1 if key["tokenId"].endswith("a") else .9)
                             if arm == "candidate" else .5}
                            for key in profile["selectedTokens"]]
                       for arm in ("candidate", "retained", "calibration")}
    return {"schemaVersion": 1, "declaration": declaration,
            "predictionSource": profile["sourceBindings"]["prediction"],
            "inputBindings": profile["inputBindings"], "payload": payload}


def ratings(profile):
    return [{**key, "status": "available", "positiveVotes": 0 if key["tokenId"].endswith("a") else 1,
             "negativeVotes": 1 if key["tokenId"].endswith("a") else 0}
            for key in profile["selectedTokens"]]


def supplied_prediction_stage(profile, root, declaration):
    """Explicit invented completion fixture; does not claim genuine generation."""
    phase = root / "prediction-output"
    phase.mkdir(mode=0o700)
    execution_inputs = profile.get("executionInputs") or write(phase / "fixture-inputs.json", {"syntheticFixture": True})
    prediction_pin = write(phase / "predictions.json", predictions(profile, declaration))
    flags = {"researchOnly": True, "clinicalUseEligible": False, "learnerFeedbackEligible": False, "productionUseEligible": False}
    receipt = write(phase / "receipt.json", {"schemaVersion": 1, "executionSource": profile["sourceBindings"]["execution"],
                    "predictionSource": profile["sourceBindings"]["prediction"], "inputBindings": profile["inputBindings"],
                    "executionInputs": execution_inputs, "productionBound": False,
                    "terminalTokens": len(profile["selectedTokens"]), "syntheticFixture": True,
                    "extractorCompletions": [], "predictorProvenance": {"syntheticFixture": True}, **flags})
    started = write(phase / "started.json", {"schemaVersion": 1, "phase": "prediction-output", "status": "started",
                                           "declaration": declaration, **flags})
    completion = write(phase / "completion.json", {"schemaVersion": 1, "artifactType": "phase_completion",
                       "phase": "prediction-output", "status": "completed", "declaration": declaration,
                       "started": started, "artifacts": {"predictions": prediction_pin, "executionInputs": execution_inputs,
                                                          "receipt": receipt}, "syntheticFixture": True, **flags})
    return prediction_pin, completion


def locked_fixture(profile, root, declaration):
    predictions_pin, completion = supplied_prediction_stage(profile, root, declaration)
    return lock_predictions(root, declaration["sha256"], predictions_pin, completion["sha256"])


class StageTests(unittest.TestCase):
    def test_reserved_projection_follows_access_start_and_joins_only_once(self):
        from r_confirmatory_run import stages
        from r_confirmatory_run import outcomes
        for projection_fails in (False, True):
            with self.subTest(projection_fails=projection_fails), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary).resolve()
                profile = profile_fixture(directory)
                root = directory / "run"
                declaration = declare_run(profile, root)
                locked = locked_fixture(profile, root, declaration)
                actual_declaration, actual_verify = stages._declaration, stages._verify_profile
                verified = []
                def validated_reserved_fixture(*arguments):
                    # Simulate a validated mode branch, keeping every actual input synthetic.
                    result_root, value, binding = actual_declaration(*arguments)
                    value["profile"]["mode"] = "reserved_test"
                    return result_root, value, binding
                def verify_synthetic_sources(value):
                    self.assertTrue((root / "outcome-access/started.json").exists())
                    fixture = copy.deepcopy(value)
                    fixture["mode"] = "synthetic"
                    actual_verify(fixture)
                    verified.append(True)
                def project(value):
                    self.assertTrue((root / "outcome-access/started.json").exists())
                    self.assertEqual(verified, [True])
                    self.assertEqual(value["sourceBindings"]["outcomes"], pin(HERE / "outcomes.py"))
                    if projection_fails:
                        raise ValueError("private-projection-value")
                    return ratings(profile)
                with patch.object(stages, "_declaration", side_effect=validated_reserved_fixture), \
                        patch.object(stages, "_verify_profile", side_effect=verify_synthetic_sources), \
                        patch.object(outcomes, "project_reserved_outcomes", side_effect=project) as projection:
                    if projection_fails:
                        with self.assertRaises(ValueError) as caught:
                            stages.join_reserved_outcomes(root, declaration["sha256"], locked["lock"]["sha256"])
                        self.assertNotIn("private-projection-value", str(caught.exception))
                        self.assertTrue((root / "outcome-access/failure.json").exists())
                        self.assertFalse((root / "outcome-access/completion.json").exists())
                        self.assertFalse((root / "lock/artifact/outcome-join-claim.json").exists())
                    else:
                        joined = stages.join_reserved_outcomes(root, declaration["sha256"], locked["lock"]["sha256"])
                        self.assertEqual(joined["ratings"], pin(root / "outcome-access/ratings.json"))
                        self.assertEqual(json.loads((root / "outcome-access/ratings.json").read_bytes()), ratings(profile))
                        self.assertTrue((root / "lock/artifact/outcome-join-claim.json").exists())
                        self.assertEqual(json.loads(Path(joined["completion"]["path"]).read_bytes())["artifacts"]["ratings"], joined["ratings"])
                    with self.assertRaises(ValueError):
                        stages.join_reserved_outcomes(root, declaration["sha256"], locked["lock"]["sha256"])
                    self.assertEqual(projection.call_count, 1)

    def test_supplied_ratings_entry_point_rejects_reserved_mode_without_reading_ratings(self):
        from r_confirmatory_run import stages
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            locked = locked_fixture(profile, root, declaration)
            rating_pin = {"path": str(directory / "never-read-ratings.json"), "sha256": "0" * 64}
            actual_declaration = stages._declaration
            def validated_reserved_fixture(*arguments):
                # Explicit branch-only simulation, not a genuine reserved declaration.
                result_root, value, binding = actual_declaration(*arguments)
                value["profile"]["mode"] = "reserved_test"
                return result_root, value, binding
            with patch.object(stages, "_declaration", side_effect=validated_reserved_fixture), \
                    patch.object(stages, "_read", wraps=stages._read) as read:
                with self.assertRaises(ValueError) as caught:
                    join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], rating_pin)
                self.assertEqual(str(caught.exception), "outcome_entry_point_mode_mismatch")
                self.assertNotIn(Path(rating_pin["path"]), [call.args[0] for call in read.call_args_list])
                self.assertFalse((root / "outcome-access").exists())

    def test_reserved_outcome_entry_point_rejects_synthetic_runs_before_access(self):
        from r_confirmatory_run import stages
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            locked = locked_fixture(profile, root, declaration)
            with self.assertRaises(ValueError):
                stages.join_reserved_outcomes(root, declaration["sha256"], locked["lock"]["sha256"])
            self.assertFalse((root / "outcome-access").exists())

    def test_simultaneous_processes_can_complete_only_one_prediction_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            supplied, upstream = supplied_prediction_stage(profile, root, declaration)
            arguments = json.dumps([str(root), declaration["sha256"], supplied, upstream["sha256"]])
            worker = """
import json, sys
from r_confirmatory_run.stages import lock_predictions
print('ready', flush=True)
sys.stdin.readline()
try:
    lock_predictions(*json.loads(sys.argv[1]))
except ValueError:
    print('refused', flush=True)
else:
    print('completed', flush=True)
"""
            environment = dict(os.environ, PYTHONPATH=str(HERE.parent))
            processes = [subprocess.Popen([sys.executable, "-c", worker, arguments], env=environment,
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True) for _ in range(2)]
            try:
                for process in processes:
                    self.assertEqual(process.stdout.readline().strip(), "ready")
                for process in processes:
                    process.stdin.write("go\n")
                    process.stdin.flush()
                outcomes = [process.communicate(timeout=20) for process in processes]
                self.assertEqual(sorted(output.strip() for output, _ in outcomes), ["completed", "refused"])
                self.assertTrue(all(process.returncode == 0 for process in processes))
                self.assertTrue(all(not errors for _, errors in outcomes))
                self.assertTrue((root / "lock/completion.json").exists())
                self.assertFalse((root / "lock/failure.json").exists())
                self.assertFalse((root / "outcome-access").exists())
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()

    def test_ratings_parse_failure_consumes_access_but_invalid_lock_never_reads_ratings(self):
        from r_confirmatory_run import stages
        for content in (b'{"private":"made-up",', b'{"duplicate":1,"duplicate":2}', b'[NaN]'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary).resolve()
                profile = profile_fixture(directory)
                root = directory / "run"
                declaration = declare_run(profile, root)
                locked = locked_fixture(profile, root, declaration)
                rating_path = directory / "ratings.json"
                rating_path.write_bytes(content)
                rating_path.chmod(0o600)
                rating_pin = pin(rating_path)
                with patch.object(stages, "_read", wraps=stages._read) as read:
                    with self.assertRaises(ValueError):
                        join_outcomes(root, declaration["sha256"], "0" * 64, rating_pin)
                    self.assertNotIn(rating_path, [call.args[0] for call in read.call_args_list])
                    self.assertFalse((root / "outcome-access").exists())
                observed_reads = []
                actual_read = stages._read
                def guarded_read(path, private=False):
                    if path == rating_path:
                        self.assertTrue((root / "outcome-access/started.json").exists())
                        observed_reads.append(path)
                    return actual_read(path, private)
                with patch.object(stages, "_read", side_effect=guarded_read):
                    with self.assertRaises(ValueError) as caught:
                        join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], rating_pin)
                self.assertEqual(observed_reads, [rating_path])
                self.assertNotIn("made-up", str(caught.exception))
                self.assertTrue((root / "outcome-access/failure.json").exists())
                self.assertFalse((root / "outcome-access/completion.json").exists())
                self.assertFalse((root / "lock/artifact/outcome-join-claim.json").exists())
                with patch.object(stages, "_read", wraps=stages._read) as read:
                    with self.assertRaises(ValueError):
                        join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], rating_pin)
                    self.assertNotIn(rating_path, [call.args[0] for call in read.call_args_list])

    def test_interrupted_evaluation_records_terminal_failure_and_preserves_interrupt(self):
        for interrupt in (KeyboardInterrupt("private-interruption-value"), SystemExit(23)):
            with self.subTest(kind=type(interrupt).__name__), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary).resolve()
                profile = profile_fixture(directory)
                root = directory / "run"
                declaration = declare_run(profile, root)
                locked = locked_fixture(profile, root, declaration)
                joined = join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"],
                                       write(directory / "ratings.json", ratings(profile)))
                with patch("r_confirmatory.evaluate.evaluate", side_effect=interrupt) as evaluate:
                    with self.assertRaises(type(interrupt)) as caught:
                        evaluate_run(root, declaration["sha256"], joined["completion"]["sha256"])
                    self.assertIs(caught.exception, interrupt)
                    self.assertEqual(evaluate.call_count, 1)
                self.assertTrue((root / "evaluate/started.json").exists())
                failure = json.loads((root / "evaluate/failure.json").read_bytes())
                self.assertEqual(failure["status"], "interrupted")
                self.assertEqual(failure["code"], "phase_interrupted")
                self.assertNotIn("private-interruption-value", json.dumps(failure))
                self.assertFalse((root / "evaluate/completion.json").exists())
                with self.assertRaises(ValueError):
                    evaluate_run(root, declaration["sha256"], joined["completion"]["sha256"])

    def test_failed_audit_saves_only_safe_invalid_decision_and_cannot_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            locked = locked_fixture(profile, root, declaration)
            joined = join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], write(directory / "ratings.json", ratings(profile)))
            evaluated = evaluate_run(root, declaration["sha256"], joined["completion"]["sha256"])
            Path(evaluated["report"]["path"]).write_bytes(b'"made-up-private-outcome"')
            with self.assertRaises(ValueError) as caught:
                audit_run(root, declaration["sha256"], evaluated["completion"]["sha256"])
            self.assertNotIn("made-up-private-outcome", str(caught.exception))
            self.assertTrue((root / "audit/started.json").exists())
            self.assertTrue((root / "audit/failure.json").exists())
            self.assertFalse((root / "audit/audit.json").exists())
            self.assertFalse((root / "audit/completion.json").exists())
            decision = json.loads((root / "audit/invalid-decision.json").read_bytes())
            self.assertEqual(decision["verdict"], "invalid")
            self.assertFalse(decision["auditVerified"])
            self.assertFalse(decision["learnerFeedbackEligible"])
            self.assertEqual(caught.exception.decision, pin(root / "audit/invalid-decision.json"))
            with self.assertRaises(ValueError):
                audit_run(root, declaration["sha256"], evaluated["completion"]["sha256"])

    def test_unlisted_sources_and_wrong_reserved_purposes_are_rejected_before_private_reads(self):
        from r_confirmatory_run import stages
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            private = write(directory / "private-not-a-source.json", {"private": "made-up"})
            profile["sourceBindings"]["unlistedRole"] = private
            with patch.object(stages, "_read", wraps=stages._read) as read:
                with self.assertRaises(ValueError):
                    declare_run(profile, directory / "bad-source")
                self.assertNotIn(Path(private["path"]), [call.args[0] for call in read.call_args_list])
            profile = profile_fixture(directory)
            profile["mode"] = "reserved_test"
            profile["expectedChildren"] = 80
            profile["children"] = [{"childId": str(i)} for i in range(1, 81)]
            profile["selectedTokens"] = [{"childId": "1", "tokenId": f"made-up/{i}"} for i in range(3066)]
            profile["executionInputs"] = {"path": str(directory / "never-read-execution.json"), "sha256": "0" * 64}
            for name, path in stages.OPTIONAL_SOURCE_PATHS.items():
                profile["sourceBindings"][name] = {"path": str(path), "sha256": "0" * 64}
            profile["inputBindings"]["frozenProtocol"] = {"path": str(stages.PROTOCOL_PATH), "sha256": stages.PROTOCOL_SHA}
            # The public protocol is permitted; wrong supplied private paths are not.
            with patch.object(stages, "_read", wraps=stages._read) as read:
                with self.assertRaises(ValueError):
                    declare_run(profile, directory / "bad-purpose")
                self.assertFalse(any(call.args[0].is_relative_to(directory) for call in read.call_args_list))

    def test_independent_saved_audit_precedes_frozen_policy_decision(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            locked = locked_fixture(profile, root, declaration)
            joined = join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], write(directory / "ratings.json", ratings(profile)))
            evaluated = evaluate_run(root, declaration["sha256"], joined["completion"]["sha256"])
            audited = audit_run(root, declaration["sha256"], evaluated["completion"]["sha256"])
            audit = json.loads(Path(audited["audit"]["path"]).read_bytes())
            decision = json.loads(Path(audited["decision"]["path"]).read_bytes())
            self.assertEqual(audit["outcome"], "verified")
            self.assertEqual(audit["reportSha256"], evaluated["report"]["sha256"])
            self.assertEqual(audit["inputSha256"], joined["joinedInput"]["sha256"])
            self.assertEqual(decision["verdict"], "pass_ranking")
            self.assertEqual(decision["coverage"]["fullChildDenominator"], 2)
            self.assertFalse(decision["learnerFeedbackEligible"])
            self.assertFalse(decision["clinicalUseEligible"])
            self.assertTrue(decision["syntheticFixture"])
            with self.assertRaises(ValueError):
                audit_run(root, declaration["sha256"], evaluated["completion"]["sha256"])

    def test_evaluation_uses_only_external_anchored_join_and_saved_report_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            locked = locked_fixture(profile, root, declaration)
            joined = join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], write(directory / "ratings.json", ratings(profile)))
            evaluated = evaluate_run(root, declaration["sha256"], joined["completion"]["sha256"])
            report = json.loads(Path(evaluated["report"]["path"]).read_bytes())
            self.assertEqual(report["fullChildDenominator"], 2)
            self.assertEqual(report["selectedTokenDenominator"], 4)
            self.assertEqual(report["pairedSummary"]["candidateVsRetained"]["auroc"]["meanGain"], .5)
            self.assertEqual(evaluated["report"], pin(Path(evaluated["report"]["path"])))
            self.assertFalse((root / "audit").exists())
            with self.assertRaises(ValueError):
                evaluate_run(root, declaration["sha256"], joined["completion"]["sha256"])

    def test_join_is_once_only_and_preserves_rating_and_lock_byte_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            locked = locked_fixture(profile, root, declaration)
            rating_pin = write(directory / "ratings.json", ratings(profile))
            joined = join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], rating_pin)
            data = json.loads(Path(joined["joinedInput"]["path"]).read_bytes())
            self.assertEqual(data["ratings"], ratings(profile))
            receipt = json.loads(Path(joined["receipt"]["path"]).read_bytes())
            self.assertEqual(receipt["lockSha256"], locked["lock"]["sha256"])
            self.assertTrue((root / "outcome-access/started.json").exists())
            self.assertTrue((root / "lock/artifact/outcome-join-claim.json").exists())
            self.assertEqual(json.loads(Path(joined["completion"]["path"]).read_bytes())["artifacts"]["ratings"], rating_pin)
            with self.assertRaises(ValueError):
                join_outcomes(root, declaration["sha256"], locked["lock"]["sha256"], rating_pin)

    def test_locked_predictions_preserve_declared_roster_and_refuse_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            root = directory / "run"
            declaration = declare_run(profile, root)
            supplied, upstream_completion = supplied_prediction_stage(profile, root, declaration)
            result = lock_predictions(root, declaration["sha256"], supplied, upstream_completion["sha256"])
            locked = json.loads(Path(result["lock"]["path"]).read_bytes())
            self.assertEqual(locked["membership"]["childIds"], ["1", "2"])
            self.assertEqual(locked["coverage"]["selectedTokenDenominator"], 4)
            self.assertEqual(result["lock"], pin(Path(result["lock"]["path"])))
            self.assertTrue((root / "lock/started.json").exists())
            self.assertFalse((root / "outcome-access").exists())
            completion = json.loads(Path(result["completion"]["path"]).read_bytes())
            self.assertEqual(completion["artifacts"]["predictions"], supplied)
            with self.assertRaises(ValueError):
                lock_predictions(root, declaration["sha256"], supplied, upstream_completion["sha256"])

    def test_fresh_synthetic_declaration_binds_full_membership_without_changing_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            profile = profile_fixture(directory)
            before = copy.deepcopy(profile)
            root = directory / "run"
            declared = declare_run(profile, root)
            saved = json.loads(Path(declared["path"]).read_bytes())
            self.assertEqual(declared, pin(Path(declared["path"])))
            self.assertEqual(saved["profile"], profile)
            self.assertEqual(saved["profile"]["policy"]["coverage"]["fullChildDenominator"], 80)
            self.assertEqual(saved["profile"]["expectedChildren"], 2)
            self.assertEqual(profile, before)
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(Path(declared["path"]).stat().st_mode), 0o600)
            self.assertTrue((root / "started.json").exists())
            with self.assertRaises(ValueError):
                declare_run(profile, root)

    def test_invalid_profile_is_rejected_without_creating_a_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "never-created"
            for supplied in ({}, {"schemaVersion": True}, {"unknown": "private-sensitive-value"}, None):
                with self.subTest(profile=supplied), self.assertRaises(ValueError) as caught:
                    declare_run(supplied, root)
                self.assertNotIn("private-sensitive-value", str(caught.exception))
                self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
