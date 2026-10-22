"""Synthetic public-boundary checks for preparation-only local locks."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import stat
import tempfile
import unittest

from r_confirmatory.locking import create_prediction_lock
from r_confirmatory import locking


def fixture():
    key = {"childId": "synthetic-child", "tokenId": "synthetic-token"}
    return {"children": [{"childId": "zero"}, {"childId": "synthetic-child", "descriptors": {"age": None}}],
            "selectedTokens": [key],
            "arms": {arm: [{**key, "status": "processed", "probability": 0}]
                     for arm in ("candidate", "retained", "calibration")}}


def ratings():
    return [{"childId": "synthetic-child", "tokenId": "synthetic-token", "status": "available", "positiveVotes": 1, "negativeVotes": 3}]


class LockingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic-lock-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_freezes_full_predictions_and_empty_children_in_private_files(self):
        supplied = fixture()
        before = copy.deepcopy(supplied)
        result = create_prediction_lock(supplied, self.root / "lock")
        path = Path(result["lockPath"])
        raw = path.read_bytes()
        artifact = json.loads(raw)
        self.assertEqual(result["lockSha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.name, "prediction-lock.json")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(artifact["input"]["children"], [before["children"][1], before["children"][0]])
        self.assertEqual(artifact["input"]["arms"]["candidate"][0]["probability"], 0.0)
        self.assertIn(b'"probability":0.0', raw)
        self.assertEqual(artifact["coverage"]["fullChildDenominator"], 2)
        self.assertEqual(artifact["coverage"]["children"][1]["selectedTokens"], 0)
        self.assertEqual(artifact["status"], "preparation_not_declaration")
        self.assertTrue(artifact["researchOnly"])
        for field in ("clinicalUseEligible", "learnerFeedbackEligible", "productionUseEligible"):
            self.assertFalse(artifact[field])
        self.assertEqual(supplied, before)

    def test_rejects_malformed_or_outcome_contaminated_prediction_rosters_before_export(self):
        changes = [
            lambda p: p.update(ratings=[]),
            lambda p: p["children"].append(copy.deepcopy(p["children"][0])),
            lambda p: p["children"][0].update(childId=" leading"),
            lambda p: p["children"][0].update(childId=True),
            lambda p: p["children"][0].update(ratings=[]),
            lambda p: p["children"][0].update(descriptors={"bad": float("nan")}),
            lambda p: p["children"][0].update(descriptors={"bad": (1, 2)}),
            lambda p: p["children"][0].update(descriptors={1: "bad"}),
            lambda p: p["selectedTokens"].append(copy.deepcopy(p["selectedTokens"][0])),
            lambda p: p["selectedTokens"][0].update(childId="unknown"),
            lambda p: p["selectedTokens"][0].update(tokenId=""),
            lambda p: p["selectedTokens"][0].update(rating=1),
            lambda p: p["arms"].pop("candidate"),
            lambda p: p["arms"].update(extra=[]),
            lambda p: p["arms"]["candidate"].clear(),
            lambda p: p["arms"]["candidate"].append(copy.deepcopy(p["arms"]["candidate"][0])),
            lambda p: p["arms"]["candidate"][0].update(probability=True),
            lambda p: p["arms"]["candidate"][0].update(probability=float("inf")),
            lambda p: p["arms"]["candidate"][0].update(probability=10**1000),
            lambda p: p["arms"]["candidate"][0].update(probability=-0.1),
            lambda p: p["arms"]["candidate"][0].update(status="pending"),
            lambda p: p["arms"]["candidate"][0].update(status="failed", reason=""),
            lambda p: p["arms"]["candidate"][0].update(positiveVotes=1),
        ]
        for index, change in enumerate(changes):
            supplied = fixture()
            change(supplied)
            output = self.root / str(index)
            with self.subTest(index=index), self.assertRaises(ValueError):
                create_prediction_lock(supplied, output)
            self.assertFalse(output.exists())

    def test_join_uses_exact_external_anchor_and_leaves_a_terminal_local_claim(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        raw = Path(lock["lockPath"]).read_bytes()
        result = locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), self.root / "join")
        joined_raw = Path(result["joinedInputPath"]).read_bytes()
        joined = json.loads(joined_raw)
        self.assertEqual(set(joined), {"children", "selectedTokens", "arms", "ratings"})
        self.assertEqual(joined["ratings"], ratings())
        self.assertEqual(result["joinedInputSha256"], hashlib.sha256(joined_raw).hexdigest())
        receipt_raw = Path(result["receiptPath"]).read_bytes()
        receipt = json.loads(receipt_raw)
        self.assertEqual(result["receiptSha256"], hashlib.sha256(receipt_raw).hexdigest())
        self.assertEqual(receipt["lockSha256"], lock["lockSha256"])
        self.assertEqual(receipt["joinedInputSha256"], result["joinedInputSha256"])
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(json.loads(Path(result["claimPath"]).read_bytes())["status"], "succeeded")
        self.assertEqual(Path(lock["lockPath"]).read_bytes(), raw)
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), self.root / "second")
        self.assertFalse((self.root / "second").exists())

    def test_invalid_numeric_rating_is_a_consumed_failed_attempt_without_joined_data(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        supplied = ratings()
        supplied[0]["positiveVotes"] = 10**1000
        with self.assertRaises(ValueError) as raised:
            locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], supplied, self.root / "failed")
        error = raised.exception
        self.assertIsInstance(error, locking.OutcomeJoinError)
        self.assertEqual(error.code, "invalid_rating_votes")
        self.assertFalse((self.root / "failed" / "joined-input.json").exists())
        receipt = json.loads(Path(error.receipt_path).read_bytes())
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failureCode"], "invalid_rating_votes")
        self.assertIsNone(receipt["joinedInputSha256"])
        self.assertIsNone(receipt["ratingsSha256"])
        self.assertEqual(json.loads(Path(error.claim_path).read_bytes())["status"], "failed")
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), self.root / "retry")
        self.assertFalse((self.root / "retry").exists())

    def test_permutations_integer_and_signed_zero_normalize_to_identical_lock_bytes(self):
        supplied = fixture()
        other_key = {"childId": "synthetic-child", "tokenId": "aaa"}
        supplied["selectedTokens"].append(other_key)
        for arm in supplied["arms"]:
            supplied["arms"][arm].append({**other_key, "status": "unavailable", "reason": "synthetic_missing"})
        reordered = copy.deepcopy(supplied)
        reordered["children"].reverse()
        reordered["selectedTokens"].reverse()
        for rows in reordered["arms"].values():
            rows.reverse()
            rows[1]["probability"] = -0.0
        first = create_prediction_lock(supplied, self.root / "first")
        second = create_prediction_lock(reordered, self.root / "second")
        self.assertEqual(Path(first["lockPath"]).read_bytes(), Path(second["lockPath"]).read_bytes())
        self.assertEqual(first["lockSha256"], second["lockSha256"])
        supplied_ratings = ratings() + [{**other_key, "status": "unavailable", "reason": "synthetic_missing"}]
        a = locking.join_locked_outcomes(first["lockPath"], first["lockSha256"], supplied_ratings, self.root / "a")
        b = locking.join_locked_outcomes(second["lockPath"], second["lockSha256"], list(reversed(supplied_ratings)), self.root / "b")
        self.assertEqual(Path(a["joinedInputPath"]).read_bytes(), Path(b["joinedInputPath"]).read_bytes())
        first_receipt = json.loads(Path(a["receiptPath"]).read_bytes())
        second_receipt = json.loads(Path(b["receiptPath"]).read_bytes())
        first_attempt = first_receipt.pop("attemptedRatingsSha256")
        second_attempt = second_receipt.pop("attemptedRatingsSha256")
        self.assertNotEqual(first_attempt, second_attempt)
        self.assertEqual(first_receipt, second_receipt)

    def test_bad_anchor_and_changed_lock_do_not_consume_claim_or_reserve_output(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        path = Path(lock["lockPath"])
        for index, anchor in enumerate((None, True, "A" * 64, "0" * 63, "0" * 64)):
            with self.subTest(index=index), self.assertRaises(ValueError):
                locking.join_locked_outcomes(path, anchor, ratings(), self.root / str(index))
            self.assertFalse((self.root / str(index)).exists())
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(path, lock["lockSha256"], ratings(), self.root / "tampered")
        self.assertFalse((path.parent / "outcome-join-claim.json").exists())
        self.assertFalse((self.root / "tampered").exists())

    def test_trusted_anchor_cannot_mask_internal_tamper_or_duplicate_json_keys(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        path = Path(lock["lockPath"])
        original = path.read_bytes()
        for index, field in enumerate(("inputSha256", "membershipSha256", "sourceSha256", "sourceFiles", "coverage", "researchOnly", "clinicalUseEligible", "schemaVersion")):
            artifact = json.loads(original)
            artifact[field] = "tampered"
            raw = json.dumps(artifact).encode()
            path.write_bytes(raw)
            with self.subTest(field=field), self.assertRaises(ValueError):
                locking.join_locked_outcomes(path, hashlib.sha256(raw).hexdigest(), ratings(), self.root / str(index))
            self.assertFalse((self.root / str(index)).exists())
        duplicate = b'{"schemaVersion":1,' + original[1:]
        path.write_bytes(duplicate)
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(path, hashlib.sha256(duplicate).hexdigest(), ratings(), self.root / "duplicate")
        self.assertFalse((path.parent / "outcome-join-claim.json").exists())

    def test_invalid_rating_rosters_consume_each_physical_lock_and_preserve_data_privacy(self):
        changes = [lambda rows: rows.clear(),
                   lambda rows: rows.append(copy.deepcopy(rows[0])),
                   lambda rows: rows[0].update(tokenId="unknown"),
                   lambda rows: rows[0].update(childId="unknown"),
                   lambda rows: rows[0].update(positiveVotes=True),
                   lambda rows: rows[0].update(negativeVotes=-1),
                   lambda rows: rows[0].update(positiveVotes=0, negativeVotes=0),
                   lambda rows: rows[0].update(positiveVotes=1.5),
                   lambda rows: rows[0].update(probability=0.9),
                   lambda rows: rows[0].update(status="pending"),
                   lambda rows: rows.__setitem__(0, {"childId": "synthetic-child", "tokenId": "synthetic-token", "status": "unavailable", "reason": "  "})]
        for index, change in enumerate(changes):
            lock = create_prediction_lock(fixture(), self.root / f"lock-{index}")
            before = Path(lock["lockPath"]).read_bytes()
            supplied = ratings()
            change(supplied)
            output = self.root / f"join-{index}"
            with self.subTest(index=index), self.assertRaises(locking.OutcomeJoinError) as raised:
                locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], supplied, output)
            raw = Path(raised.exception.receipt_path).read_bytes()
            receipt = json.loads(raw)
            self.assertEqual(receipt["status"], "failed")
            self.assertNotIn(b"positiveVotes", raw)
            self.assertNotIn(b"probability", raw)
            self.assertEqual(Path(lock["lockPath"]).read_bytes(), before)
            self.assertFalse((output / "joined-input.json").exists())
            self.assertEqual(json.loads(Path(raised.exception.claim_path).read_bytes())["status"], "failed")

    def test_existing_outputs_and_symlink_paths_preserve_caller_files_without_consuming_join(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        existing = self.root / "existing"
        existing.mkdir()
        sentinel = existing / "sentinel"
        sentinel.write_text("caller evidence")
        for function in (lambda: create_prediction_lock(fixture(), existing),
                         lambda: locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), existing)):
            with self.assertRaises(ValueError):
                function()
        self.assertEqual(sentinel.read_text(), "caller evidence")
        self.assertFalse((self.root / "lock" / "outcome-join-claim.json").exists())
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            create_prediction_lock(fixture(), alias / "new")
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(alias / "lock" / "prediction-lock.json", lock["lockSha256"], ratings(), self.root / "symlink-join")
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), alias / "new")
        self.assertFalse((self.root / "new").exists())
        path = Path(lock["lockPath"])
        physical = path.with_name("physical.json")
        path.rename(physical)
        path.symlink_to(physical)
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(path, lock["lockSha256"], ratings(), self.root / "file-alias")
        self.assertFalse((self.root / "file-alias").exists())
        self.assertFalse((path.parent / "outcome-join-claim.json").exists())

    def test_hardlinked_or_nonprivate_lock_is_refused_before_claim(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        path = Path(lock["lockPath"])
        link = self.root / "hardlink"
        os.link(path, link)
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(path, lock["lockSha256"], ratings(), self.root / "hardlinked")
        link.unlink()
        for target, mode in ((path, 0o644), (path.parent, 0o755)):
            target.chmod(mode)
            with self.assertRaises(ValueError):
                locking.join_locked_outcomes(path, lock["lockSha256"], ratings(), self.root / f"nonprivate-{mode}")
            target.chmod(0o600 if target == path else 0o700)
        self.assertFalse((path.parent / "outcome-join-claim.json").exists())

    def test_interrupted_or_symlink_claim_blocks_retry_and_only_cleans_own_reservation(self):
        for index, symlink in enumerate((False, True)):
            lock = create_prediction_lock(fixture(), self.root / f"lock-{index}")
            path = Path(lock["lockPath"]).parent / "outcome-join-claim.json"
            if symlink:
                path.symlink_to(self.root / "missing")
            else:
                path.write_text('{"status":"started"}')
            with self.assertRaises(locking.OutcomeJoinError) as raised:
                locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), self.root / f"join-{index}")
            self.assertEqual(raised.exception.code, "join_already_claimed")
            self.assertFalse((self.root / f"join-{index}").exists())
            self.assertTrue(path.is_symlink() if symlink else path.exists())

    def test_empty_cohort_and_failed_predictions_remain_complete_in_join(self):
        for index, supplied in enumerate(({"children": [], "selectedTokens": [], "arms": {arm: [] for arm in ("candidate", "retained", "calibration")}}, fixture())):
            supplied_ratings = []
            if supplied["selectedTokens"]:
                key = supplied["selectedTokens"][0]
                for arm in supplied["arms"]:
                    supplied["arms"][arm][0] = {**key, "status": "failed", "reason": "synthetic_failure"}
                supplied_ratings = [{**key, "status": "unavailable", "reason": "synthetic_unavailable"}]
            lock = create_prediction_lock(supplied, self.root / f"lock-{index}")
            result = locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], supplied_ratings, self.root / f"join-{index}")
            joined = json.loads(Path(result["joinedInputPath"]).read_bytes())
            self.assertEqual(joined["selectedTokens"], supplied["selectedTokens"])
            self.assertEqual(joined["arms"], supplied["arms"])
            self.assertEqual(joined["ratings"], supplied_ratings)
            for path in (result["joinedInputPath"], result["receiptPath"], result["claimPath"]):
                self.assertEqual(stat.S_IMODE(Path(path).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(result["joinedInputPath"]).parent.stat().st_mode), 0o700)

    def test_copied_pristine_artifact_has_its_own_physical_claim_not_a_global_guarantee(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        copy_root = self.root / "copied-lock"
        shutil.copytree(Path(lock["lockPath"]).parent, copy_root)
        first = locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), self.root / "first")
        second = locking.join_locked_outcomes(copy_root / "prediction-lock.json", lock["lockSha256"], ratings(), self.root / "second")
        self.assertEqual(Path(first["joinedInputPath"]).read_bytes(), Path(second["joinedInputPath"]).read_bytes())
        self.assertTrue(Path(first["claimPath"]).exists())
        self.assertTrue(Path(second["claimPath"]).exists())

    def test_generic_descriptors_are_metadata_and_do_not_establish_blinding(self):
        supplied = fixture()
        supplied["children"][0]["descriptors"] = {"callerOutcome": {"votes": [1, 3]}, "unicode": "é"}
        lock = create_prediction_lock(supplied, self.root / "lock")
        raw = Path(lock["lockPath"]).read_bytes()
        self.assertIn("é".encode(), raw)
        self.assertEqual(json.loads(raw)["input"]["children"][1]["descriptors"], supplied["children"][0]["descriptors"])

    def test_two_real_processes_can_only_claim_one_physical_lock(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        rating_file = self.root / "synthetic-ratings.json"
        rating_file.write_text(json.dumps(ratings()))
        gate = self.root / "gate"
        script = """import json, sys, time
from pathlib import Path
from r_confirmatory.locking import join_locked_outcomes, OutcomeJoinError
lock, anchor, ratings_path, output, ready, gate = sys.argv[1:]
Path(ready).touch()
while not Path(gate).exists():
    time.sleep(0.005)
try:
    join_locked_outcomes(lock, anchor, json.loads(Path(ratings_path).read_text()), output)
except OutcomeJoinError as error:
    print(error.code)
else:
    print('succeeded')
"""
        workers = [subprocess.Popen([sys.executable, "-c", script, lock["lockPath"], lock["lockSha256"],
                                   str(rating_file), str(self.root / f"join-{i}"),
                                   str(self.root / f"ready-{i}"), str(gate)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                   for i in range(2)]
        try:
            deadline = time.monotonic() + 10
            while not all((self.root / f"ready-{i}").exists() for i in range(2)):
                if time.monotonic() > deadline:
                    self.fail("synthetic workers did not reach readiness")
                time.sleep(0.005)
            gate.touch()
            results = [worker.communicate(timeout=10) for worker in workers]
            self.assertEqual(sorted(out.strip() for out, _ in results), ["join_already_claimed", "succeeded"])
            self.assertTrue(all(worker.returncode == 0 for worker in workers))
            self.assertEqual([err for _, err in results], ["", ""])
            self.assertEqual(sum((self.root / f"join-{i}").exists() for i in range(2)), 1)
            self.assertEqual(json.loads((self.root / "lock" / "outcome-join-claim.json").read_bytes())["status"], "succeeded")
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                    worker.communicate()

    def test_oversized_and_malformed_lock_files_fail_before_output_reservation(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        path = Path(lock["lockPath"])
        original = path.read_bytes()
        with path.open("wb") as destination:
            destination.truncate(10 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(path, "0" * 64, ratings(), self.root / "large")
        for index, raw in enumerate((b"{}", b"[]", b'{"input":NaN}', b'\xff', b'{"incomplete":')):
            path.write_bytes(raw)
            with self.subTest(index=index), self.assertRaises(ValueError):
                locking.join_locked_outcomes(path, hashlib.sha256(raw).hexdigest(), ratings(), self.root / str(index))
            self.assertFalse((self.root / str(index)).exists())
        path.write_bytes(original)
        self.assertFalse((path.parent / "outcome-join-claim.json").exists())
        with self.assertRaises(ValueError):
            locking.join_locked_outcomes(path, lock["lockSha256"], ratings(), self.root / "missing" / "join")
        self.assertFalse((path.parent / "outcome-join-claim.json").exists())
        result = locking.join_locked_outcomes(path, lock["lockSha256"], ratings(), self.root / "valid")
        self.assertTrue(Path(result["joinedInputPath"]).exists())

    def test_receipts_bind_canonical_input_membership_ratings_and_current_source(self):
        supplied = fixture()
        lock = create_prediction_lock(supplied, self.root / "lock")
        artifact = json.loads(Path(lock["lockPath"]).read_bytes())
        encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        digest = lambda value: hashlib.sha256(encode(value)).hexdigest()
        self.assertEqual(artifact["inputSha256"], digest(artifact["input"]))
        self.assertEqual(artifact["membership"], {"childIds": ["synthetic-child", "zero"], "selectedTokens": supplied["selectedTokens"]})
        self.assertEqual(artifact["membershipSha256"], digest(artifact["membership"]))
        source = Path(__file__).with_name("locking.py").read_bytes()
        self.assertEqual(artifact["sourceFiles"], {"locking.py": hashlib.sha256(source).hexdigest()})
        self.assertEqual(artifact["sourceSha256"], digest(artifact["sourceFiles"]))
        result = locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], ratings(), self.root / "join")
        receipt = json.loads(Path(result["receiptPath"]).read_bytes())
        self.assertEqual(receipt["ratingsSha256"], digest(ratings()))
        for field in ("inputSha256", "membershipSha256", "sourceFiles", "sourceSha256"):
            self.assertEqual(receipt[field], artifact[field])
        claim = json.loads(Path(result["claimPath"]).read_bytes())
        self.assertEqual(claim["receiptSha256"], result["receiptSha256"])
        self.assertEqual(receipt["preparationStatus"], "preparation_not_declaration")
        for evidence in (receipt, claim):
            self.assertTrue(evidence["researchOnly"])
            for field in ("clinicalUseEligible", "learnerFeedbackEligible", "productionUseEligible"):
                self.assertFalse(evidence[field])

    def test_encoding_and_path_errors_use_fixed_safe_codes_before_export(self):
        supplied = fixture()
        supplied["children"][0]["descriptors"] = {"oversizedInteger": 10**5000}
        with self.assertRaises(ValueError) as raised:
            create_prediction_lock(supplied, self.root / "encoding")
        self.assertEqual(str(raised.exception), "invalid_json_encoding")
        self.assertFalse((self.root / "encoding").exists())
        with self.assertRaises(ValueError) as raised:
            create_prediction_lock(fixture(), str(self.root / "invalid") + "\x00")
        self.assertEqual(str(raised.exception), "invalid_path")

    def test_attempted_ratings_digest_binds_raw_order_separately_from_validated_roster(self):
        lock = create_prediction_lock(fixture(), self.root / "lock")
        supplied = ratings()
        supplied[0]["positiveVotes"] = True
        encoded = json.dumps(supplied, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        with self.assertRaises(locking.OutcomeJoinError) as raised:
            locking.join_locked_outcomes(lock["lockPath"], lock["lockSha256"], supplied, self.root / "failed")
        receipt = json.loads(Path(raised.exception.receipt_path).read_bytes())
        self.assertEqual(receipt["attemptedRatingsSha256"], hashlib.sha256(encoded).hexdigest())
        self.assertIsNone(receipt["ratingsSha256"])
        self.assertIsNone(receipt["joinedInputSha256"])
        self.assertNotIn("positiveVotes", str(raised.exception))
        second = create_prediction_lock(fixture(), self.root / "second-lock")
        impossible = ratings()
        impossible[0]["positiveVotes"] = float("nan")
        with self.assertRaises(locking.OutcomeJoinError) as raised:
            locking.join_locked_outcomes(second["lockPath"], second["lockSha256"], impossible, self.root / "impossible")
        receipt = json.loads(Path(raised.exception.receipt_path).read_bytes())
        self.assertIsNone(receipt["attemptedRatingsSha256"])
        self.assertEqual(receipt["status"], "failed")


if __name__ == "__main__":
    unittest.main()
