"""Independent worked examples; all payloads are synthetic."""
import copy
import json
import math
import subprocess
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

from r_confirmatory.evaluate import evaluate


def fixture(probabilities=(0.1, 0.9), votes=((0, 4), (4, 0))):
    keys = [{"childId": "synthetic-child", "tokenId": f"synthetic-{i}"}
            for i in range(len(probabilities))]
    return {
        "children": [{"childId": "synthetic-child", "descriptors": {"age": None}}],
        "selectedTokens": keys,
        "arms": {arm: [{**key, "status": "processed", "probability": p}
                        for key, p in zip(keys, probabilities)]
                 for arm in ("candidate", "retained", "calibration")},
        "ratings": [{**key, "status": "available", "positiveVotes": pos,
                     "negativeVotes": neg}
                    for key, (pos, neg) in zip(keys, votes)],
    }


class EvaluateTests(unittest.TestCase):
    def test_perfect_order_has_literal_auroc_one(self):
        result = evaluate(fixture())
        self.assertEqual(result["children"][0]["arms"]["candidate"]["auroc"], 1.0)

    def test_literal_mixed_votes_and_ties_with_proper_scores(self):
        # Mixed token fractions 1/4 and 3/4: cross win 9; self tie 3; 12/16.
        result = evaluate(fixture(votes=((1, 3), (3, 1))))
        metrics = result["children"][0]["arms"]["candidate"]
        self.assertEqual(metrics["auroc"], 0.75)
        # -(2 log(.1) + 6 log(.9))/8; eight expected vote squared errors.
        self.assertAlmostEqual(metrics["logLoss"], 0.6546666599918811)
        self.assertAlmostEqual(metrics["brier"], 0.21)
        for p, expected in (((0.9, 0.1), 0.0), ((0.5, 0.5), 0.5)):
            self.assertEqual(evaluate(fixture(p))["children"][0]["arms"]["candidate"]["auroc"], expected)

    def test_fail_closed_invalid_terminal_rosters_and_numeric_values(self):
        mutations = [
            lambda p: p["children"].append(copy.deepcopy(p["children"][0])),
            lambda p: p["selectedTokens"].append(copy.deepcopy(p["selectedTokens"][0])),
            lambda p: p["arms"]["candidate"].pop(),
            lambda p: p["arms"].pop("calibration"),
            lambda p: p["arms"].update(extra=[]),
            lambda p: p["arms"]["retained"].append(copy.deepcopy(p["arms"]["retained"][0])),
            lambda p: p["ratings"].pop(),
            lambda p: p["ratings"].append(copy.deepcopy(p["ratings"][0])),
            lambda p: p["selectedTokens"][0].update(childId="unknown"),
            lambda p: p["arms"]["candidate"][0].update(probability=True),
            lambda p: p["arms"]["candidate"][0].update(probability=float("nan")),
            lambda p: p["arms"]["candidate"][0].update(probability=float("inf")),
            lambda p: p["arms"]["candidate"][0].update(probability=-0.1),
            lambda p: p["ratings"][0].update(positiveVotes=True),
            lambda p: p["ratings"][0].update(negativeVotes=-1),
            lambda p: p["ratings"][0].update(positiveVotes=0, negativeVotes=0),
            lambda p: p["ratings"][0].update(positiveVotes=0.5),
            lambda p: p["arms"]["candidate"][0].update(status="failed"),
            lambda p: p["arms"]["candidate"][0].update(status="unavailable", reason=""),
        ]
        for mutate in mutations:
            payload = fixture()
            mutate(payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                evaluate(payload)

    def test_full_roster_and_shared_token_pairs_retain_failures_and_empty_children(self):
        payload = fixture(votes=((1, 3), (3, 1)))
        payload["children"].append({"childId": "empty", "descriptors": {"age": None, "study": "unknown"}})
        payload["arms"]["candidate"][1] = {**payload["selectedTokens"][1], "status": "failed", "reason": "synthetic failure"}
        payload["arms"]["calibration"][0]["probability"] = 0.5
        before = copy.deepcopy(payload)
        result = evaluate(payload)
        empty, child = result["children"]
        self.assertEqual(child["arms"]["retained"]["auroc"], 0.75)
        self.assertEqual(child["arms"]["candidate"]["coverage"], {
            "selected": 2, "processed": 1, "unavailable": 0, "failed": 1,
            "ratingAvailable": 2, "processedAndRated": 1, "positiveVotes": 1, "negativeVotes": 3})
        paired = child["paired"]["candidateVsRetained"]
        self.assertEqual(paired["tokenIds"], ["synthetic-0"])
        self.assertEqual((paired["candidate"]["auroc"], paired["comparator"]["auroc"], paired["aurocGain"]), (0.5, 0.5, 0.0))
        proper = child["paired"]["candidateVsCalibration"]
        self.assertAlmostEqual(proper["logLossGain"], 0.0384805205680642)
        self.assertAlmostEqual(proper["brierGain"], 0.04)
        self.assertEqual(child["arms"]["candidate"]["exclusions"], [{"tokenId": "synthetic-1", "reasons": ["prediction:failed:synthetic failure"]}])
        self.assertEqual(empty["arms"]["candidate"]["metricReasons"]["auroc"], "no_selected_tokens")
        self.assertIsNone(empty["arms"]["candidate"]["auroc"])
        self.assertEqual(empty["descriptors"], {"age": None, "study": "unknown"})
        self.assertEqual(result["fullChildDenominator"], 2)
        self.assertEqual(payload, before)
        result["children"][0]["descriptors"]["age"] = 100
        self.assertEqual(payload, before)

    def test_clipping_is_proper_score_only_and_undefined_metrics_are_explicit(self):
        result = evaluate(fixture((0, 0.00000001), ((0, 1), (1, 0))))
        metrics = result["children"][0]["arms"]["candidate"]
        self.assertEqual(metrics["auroc"], 1.0)
        self.assertAlmostEqual(metrics["logLoss"], 6.907755778982386)
        self.assertAlmostEqual(metrics["brier"], 0.499999000001)
        for votes, reason in ((((1, 0), (3, 0)), "no_negative_votes"),
                              (((0, 1), (0, 3)), "no_positive_votes")):
            child = evaluate(fixture(votes=votes))["children"][0]
            self.assertIsNone(child["arms"]["candidate"]["auroc"])
            self.assertEqual(child["arms"]["candidate"]["metricReasons"]["auroc"], reason)
            self.assertIsNotNone(child["arms"]["candidate"]["brier"])
        payload = fixture()
        payload["ratings"] = [{**key, "status": "unavailable", "reason": "synthetic rating unavailable"} for key in payload["selectedTokens"]]
        child = evaluate(payload)["children"][0]
        self.assertIsNone(child["arms"]["candidate"]["logLoss"])
        self.assertEqual(child["paired"]["candidateVsRetained"]["candidate"]["metricReasons"]["auroc"], "no_shared_processed_rated_tokens")
        payload = fixture((), ())
        result = evaluate(payload)
        self.assertEqual(result["fullChildDenominator"], 1)
        self.assertEqual(result["selectedTokenDenominator"], 0)

    def test_conditional_paired_bootstrap_and_child_balanced_summary(self):
        payload = fixture()
        payload["arms"]["retained"][0]["probability"] = 0.9
        payload["arms"]["retained"][1]["probability"] = 0.1
        second = fixture((0.9, 0.1))
        for collection in (second["children"], second["selectedTokens"], second["ratings"], *second["arms"].values()):
            for row in collection:
                row["childId"] = "synthetic-second"
        second["arms"]["retained"][0]["probability"] = 0.1
        second["arms"]["retained"][1]["probability"] = 0.9
        for field in ("children", "selectedTokens", "ratings"):
            payload[field].extend(second[field])
        for arm in payload["arms"]:
            payload["arms"][arm].extend(second["arms"][arm])
        payload["children"].append({"childId": "empty"})
        result = evaluate(payload)
        summary = result["pairedSummary"]["candidateVsRetained"]["auroc"]
        self.assertEqual(summary["meanGain"], 0.0)
        self.assertEqual(summary["definedChildIds"], ["synthetic-child", "synthetic-second"])
        self.assertEqual(summary["fullChildDenominator"], 3)
        self.assertEqual(summary["improvedChildren"], 1)
        self.assertEqual(summary["worsenedChildren"], 1)
        self.assertEqual(summary["bootstrap"]["interval95"], [-1.0, 1.0])
        self.assertEqual(summary["bootstrap"]["population"], "defined_paired_children_only")
        self.assertEqual(summary["bootstrap"]["generatedReplicates"], 2000)
        self.assertEqual(summary["bootstrap"]["undefinedReplicates"], 0)
        self.assertEqual(result["armSummary"]["candidate"]["auroc"]["mean"], 0.5)
        self.assertEqual(evaluate(payload), result)
        singleton = evaluate(fixture())["pairedSummary"]["candidateVsRetained"]["auroc"]
        self.assertEqual(singleton["bootstrap"]["interval95"], [0.0, 0.0])
        self.assertTrue(singleton["bootstrap"]["degenerate"])
        empty = evaluate(fixture((), ()))["pairedSummary"]["candidateVsRetained"]["auroc"]
        self.assertIsNone(empty["meanGain"])
        self.assertIsNone(empty["bootstrap"]["interval95"])
        self.assertEqual(empty["bootstrap"]["generatedReplicates"], 0)

    def test_cli_serializes_deterministically_and_rejects_duplicate_json_keys(self):
        root = Path(__file__).resolve().parents[3] / "work/assessment-continuation-20261002/evaluator"
        directory = Path(tempfile.mkdtemp(prefix="synthetic-cli-", dir=root))
        self.addCleanup(shutil.rmtree, directory)
        input_path = directory / "synthetic-cli-input.json"
        output_path = directory / "synthetic-cli-output.json"
        input_path.write_text(json.dumps(fixture()), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).with_name("evaluate.py")), str(input_path), "--output", str(output_path)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(output_path.exists())
        exported = output_path.read_text(encoding="utf-8")
        self.assertEqual(json.loads(exported), evaluate(fixture()))
        second_output = directory / "synthetic-cli-second-output.json"
        second = subprocess.run([*command[:-1], str(second_output)], capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second_output.read_text(encoding="utf-8"), exported)
        input_path.write_text('{"children": [], "children": []}', encoding="utf-8")
        malformed = subprocess.run([*command[:-1], str(directory / "malformed-output.json")], capture_output=True, text=True)
        self.assertEqual(malformed.returncode, 2)
        self.assertIn("duplicate JSON key", malformed.stderr)
        self.assertEqual(output_path.read_text(encoding="utf-8"), exported)

    def test_malformed_json_and_descriptors_are_rejected_at_public_seam(self):
        for malformed in (None, [], {}, {"children": None}, {"children": []}):
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                evaluate(malformed)
        mutations = [
            lambda p: p["children"][0].update(descriptors={"age": float("nan")}),
            lambda p: p["children"][0].update(descriptors={"nested": {1: "not a JSON key"}}),
            lambda p: p["children"][0].update(descriptors={"nested": ("not a JSON array",)}),
            lambda p: p["arms"]["candidate"][0].update(probability=1.1),
            lambda p: p["arms"]["candidate"][0].update(status="pending"),
            lambda p: p["arms"]["candidate"][0].update(childId="unknown"),
            lambda p: p["ratings"][0].update(status="unavailable", reason="missing"),
            lambda p: p["ratings"][0].update(positiveVotes=None),
            lambda p: p["arms"]["retained"].__setitem__(0, None),
            lambda p: p["children"][0].update(childId=True),
        ]
        for mutate in mutations:
            payload = fixture()
            mutate(payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                evaluate(payload)

    def test_listener_mass_weights_within_child_and_children_have_equal_weight(self):
        payload = fixture((0.9,), ((1, 0),))
        payload["children"].append({"childId": "synthetic-heavy"})
        key = {"childId": "synthetic-heavy", "tokenId": "synthetic-only"}
        payload["selectedTokens"].append(key)
        payload["ratings"].append({**key, "status": "available", "positiveVotes": 1000, "negativeVotes": 0})
        for arm in payload["arms"]:
            payload["arms"][arm].append({**key, "status": "processed", "probability": 0.1})
        result = evaluate(payload)
        # Equal child weight: [-log(.9) -log(.1)]/2, [.01+.81]/2.
        self.assertAlmostEqual(result["armSummary"]["candidate"]["logLoss"]["mean"], 1.203972804325936)
        self.assertAlmostEqual(result["armSummary"]["candidate"]["brier"]["mean"], 0.41)
        payload["arms"]["retained"][0] = {**payload["selectedTokens"][0], "status": "unavailable", "reason": "synthetic unavailable"}
        result = evaluate(payload)
        self.assertEqual(result["children"][0]["arms"]["retained"]["coverage"]["unavailable"], 1)
        self.assertEqual(result["children"][0]["paired"]["candidateVsRetained"]["sharedProcessedRatedTokens"], 0)
        empty = evaluate({"children": [], "selectedTokens": [], "arms": {arm: [] for arm in ("candidate", "retained", "calibration")}, "ratings": []})
        self.assertEqual(empty["fullChildDenominator"], 0)
        self.assertIsNone(empty["armSummary"]["candidate"]["brier"]["mean"])

    def test_cli_cannot_overwrite_its_input(self):
        directory = Path(__file__).resolve().parents[3] / "work/assessment-continuation-20261002/evaluator"
        input_path = directory / "synthetic-immutable-cli-input.json"
        supplied = json.dumps(fixture())
        input_path.write_text(supplied, encoding="utf-8")
        attempted = subprocess.run([sys.executable, str(Path(__file__).with_name("evaluate.py")), str(input_path), "--output", str(input_path)], capture_output=True, text=True)
        self.assertEqual(attempted.returncode, 2)
        self.assertIn("output must not replace input", attempted.stderr)
        self.assertEqual(input_path.read_text(encoding="utf-8"), supplied)

    def test_equivalent_roster_reordering_has_identical_canonical_export(self):
        payload = fixture()
        payload["children"].insert(0, {"childId": "z-empty"})
        reordered = copy.deepcopy(payload)
        for rows in (reordered["children"], reordered["selectedTokens"], reordered["ratings"], *reordered["arms"].values()):
            rows.reverse()
        first = evaluate(payload)
        self.assertEqual(first, evaluate(reordered))
        self.assertEqual([child["childId"] for child in first["children"]], ["synthetic-child", "z-empty"])

    def test_cli_refuses_existing_output_and_preserves_its_bytes(self):
        root = Path(__file__).resolve().parents[3] / "work/assessment-continuation-20261002/evaluator"
        directory = Path(tempfile.mkdtemp(prefix="synthetic-existing-", dir=root))
        self.addCleanup(shutil.rmtree, directory)
        input_path, output_path = directory / "input.json", directory / "output.json"
        input_path.write_text(json.dumps(fixture()), encoding="utf-8")
        original = "synthetic prior receipt\n"
        output_path.write_text(original, encoding="utf-8")
        attempted = subprocess.run([sys.executable, str(Path(__file__).with_name("evaluate.py")), str(input_path), "--output", str(output_path)], capture_output=True, text=True)
        self.assertEqual(attempted.returncode, 2)
        self.assertIn("output already exists", attempted.stderr)
        self.assertEqual(output_path.read_text(encoding="utf-8"), original)

    def test_identifiers_require_canonical_nonblank_strings(self):
        for identifier in (1, True, "", "   "):
            payload = fixture()
            for collection in (payload["children"], payload["selectedTokens"], payload["ratings"], *payload["arms"].values()):
                for row in collection:
                    row["childId"] = identifier
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                evaluate(payload)
        payload = fixture()
        payload["selectedTokens"][0]["tokenId"] = 1
        with self.assertRaises(ValueError):
            evaluate(payload)

    def test_descriptive_report_never_grants_learner_or_clinical_eligibility(self):
        result = evaluate(fixture())
        self.assertEqual(result["schemaVersion"], 1)
        self.assertTrue(result["researchOnly"])
        self.assertFalse(result["clinicalUseEligible"])
        self.assertFalse(result["learnerFeedbackEligible"])
        self.assertFalse(result["productionUseEligible"])
        self.assertNotIn("passed", result)
        self.assertNotIn("promotion", result)


if __name__ == "__main__":
    unittest.main()
