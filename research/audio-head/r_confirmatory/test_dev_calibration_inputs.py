"""Pure DEV input adapter examples use made-up saved artifacts exclusively."""
import copy
import json
import math
import unittest

from r_confirmatory.dev_calibration_inputs import prepare_dev_calibration_inputs


def fixture():
    bindings = {name: {"path": "/synthetic/" + name + ".json", "sha256": digit * 64}
                for name, digit in zip(("tokens", "extract", "predictions", "split", "selection",
                                        "closedDeclaration", "clips", "retention"), "12345678")}
    metadata = {"study": "made-up-study", "phase": "PRE", "word": "red",
                "context": "prevocalic", "age": 8}
    selected = [{"tokenId": token, "speakerId": child, **metadata}
                for token, child in (("made-up/a", "2"), ("made-up/b", "10"), ("made-up/x", "2"))]
    excluded = {"unmappable": ["made-up/x"], "belowReaderMinimum": []}
    tokens = [{**selected[1], "k": 3, "n": 4, "scoreBelow2": .75},
              {**selected[0], "k": 1, "n": 5, "scoreBelow2": .25}]
    artifacts = {
        "tokens": {"declaration": bindings["closedDeclaration"],
                   "upstream": {name: bindings[name] for name in ("extract", "predictions", "retention")},
                   "records": tokens, "part1Excluded": excluded,
                   **{flag: False for flag in ("testPartitionTouched", "thresholdSelected", "trainingPerformed",
                                              "clinicalUseEligible", "learnerFeedbackEligible")}},
        "extract": {"declaration": bindings["closedDeclaration"], "upstream": {"clips": bindings["clips"]},
                    "outcomes": [{"tokenId": "made-up/a", "state": "complete"},
                                 {"tokenId": "made-up/b", "state": "complete"},
                                 {"tokenId": "made-up/x", "state": "excluded"}]},
        "predictions": {"declaration": bindings["closedDeclaration"],
                        "upstream": {name: bindings[name] for name in ("extract", "clips")},
                        "ratingsRead": False,
                        "rows": [{"tokenId": "made-up/a", "probabilities": [.125, .125, .75], "scoreBelow2": .25},
                                 {"tokenId": "made-up/b", "probabilities": [.25, .5, .25], "scoreBelow2": .75}]},
        "split": {"dev": ["2", "10"], "test": ["80"]},
        "selection": {"part1": selected, "part1Excluded": excluded},
        "closedDeclaration": {"inputs": {name: bindings[name] for name in ("selection", "split")},
                              "part1": [row["tokenId"] for row in selected], "part1Excluded": excluded},
    }
    expected = {"devChildren": 2, "completeTokens": 2, "excludedTokens": 1,
                "selectedTokens": 3, "testChildren": 1}
    return artifacts, bindings, expected


class DevCalibrationInputTests(unittest.TestCase):
    def test_explicit_synthetic_counts_can_describe_no_excluded_tokens(self):
        artifacts, bindings, expected = fixture()
        artifacts["selection"]["part1"].pop()
        artifacts["closedDeclaration"]["part1"].pop()
        artifacts["extract"]["outcomes"].pop()
        artifacts["selection"]["part1Excluded"]["unmappable"].clear()
        expected.update(excludedTokens=0, selectedTokens=2)
        result = prepare_dev_calibration_inputs(artifacts, bindings, expected)
        self.assertEqual(result["receipt"]["excludedTokenIds"], [])
        self.assertEqual(result["receipt"]["observedCounts"], expected)

    def test_receipt_retains_full_denominators_provenance_and_safe_preparation_scope(self):
        artifacts, bindings, expected = fixture()
        result = prepare_dev_calibration_inputs(artifacts, bindings, expected)
        receipt = result["receipt"]
        self.assertEqual(receipt["inputBindings"], bindings)
        self.assertEqual(receipt["expectedCounts"], expected)
        self.assertEqual(receipt["children"], ["10", "2"])
        self.assertEqual(receipt["completeTokenIds"], ["made-up/a", "made-up/b"])
        self.assertEqual(receipt["selectedTokenIds"], ["made-up/a", "made-up/b", "made-up/x"])
        self.assertEqual(receipt["childTokenCounts"], {"10": 1, "2": 1})
        self.assertEqual(receipt["frozenExclusions"], {"unmappable": ["made-up/x"], "belowReaderMinimum": []})
        self.assertTrue(receipt["researchOnly"])
        for flag in ("testPartitionTouched", "calibrationFitPerformed", "clinicalUseEligible",
                     "learnerFeedbackEligible", "productionUseEligible", "byteHashesVerifiedByAdapter"):
            self.assertFalse(receipt[flag])
        json.dumps(result, allow_nan=False)
        receipt["inputBindings"]["tokens"]["path"] = "/changed"
        receipt["frozenExclusions"]["unmappable"].clear()
        self.assertEqual(bindings["tokens"]["path"], "/synthetic/tokens.json")
        self.assertEqual(artifacts["selection"]["part1Excluded"]["unmappable"], ["made-up/x"])

    def test_optional_clip_summary_requires_matching_declaration_and_complete_dev_coverage(self):
        artifacts, bindings, expected = fixture()
        artifacts["clips"] = {"declaration": copy.deepcopy(bindings["closedDeclaration"]),
                              "records": [{"tokenId": "made-up/a", "state": "complete"},
                                          {"tokenId": "made-up/b", "state": "complete"},
                                          {"tokenId": "part2-only", "state": "complete"}]}
        result = prepare_dev_calibration_inputs(artifacts, bindings, expected)
        self.assertTrue(result["receipt"]["clipSummarySupplied"])
        for change in (lambda a: a["clips"].update(declaration=bindings["tokens"]),
                       lambda a: a["clips"]["records"].pop(0),
                       lambda a: a["clips"]["records"][0].update(state="failed"),
                       lambda a: a["clips"]["records"].append(copy.deepcopy(a["clips"]["records"][0]))):
            changed = copy.deepcopy(artifacts)
            change(changed)
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(changed, bindings, expected)

    def test_malformed_containers_and_missing_required_summaries_raise_value_error(self):
        changes = [lambda a: a.pop("tokens"), lambda a: a.update(tokens=None),
                   lambda a: a.update(unexpected={}), lambda a: a["split"].pop("dev"),
                   lambda a: a["tokens"].pop("records"), lambda a: a["selection"].pop("part1Excluded"),
                   lambda a: a["closedDeclaration"].pop("inputs")]
        for change in changes:
            artifacts, bindings, expected = fixture()
            change(artifacts)
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)
        for artifacts in (None, [], "invalid"):
            _, bindings, expected = fixture()
            with self.subTest(artifacts=artifacts), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)

    def test_retained_probability_is_original_p0_plus_p1_with_both_saved_score_checks(self):
        artifacts, bindings, expected = fixture()
        artifacts["tokens"]["records"][1]["scoreBelow2"] = .25 + 5e-13
        artifacts["predictions"]["rows"][0]["scoreBelow2"] = .25 - 5e-13
        self.assertEqual(prepare_dev_calibration_inputs(artifacts, bindings, expected)["payload"]["rows"][0]
                         ["retainedProbability"], .25)

    def test_malformed_probabilities_and_saved_score_disagreement_fail_closed(self):
        probabilities = [[.125, .125], [.125, .125, .75, 0], [True, 0, 0],
                         [math.nan, .125, .75], [math.inf, .125, .75],
                         [-.01, .26, .75], [.125, .125, .8], [1.1, 0, -.1],
                         [".125", .125, .75], None, [10**400, .125, .75]]
        for value in probabilities:
            artifacts, bindings, expected = fixture()
            artifacts["predictions"]["rows"][0]["probabilities"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)
        for artifact in ("tokens", "predictions"):
            for score in (.25 + 2e-12, math.nan, math.inf, True, "0.25", -.1, 1.1):
                artifacts, bindings, expected = fixture()
                rows = artifacts[artifact]["records" if artifact == "tokens" else "rows"]
                next(row for row in rows if row["tokenId"] == "made-up/a")["scoreBelow2"] = score
                with self.subTest(artifact=artifact, score=score), self.assertRaises(ValueError):
                    prepare_dev_calibration_inputs(artifacts, bindings, expected)

    def test_listener_counts_and_age_metadata_fail_instead_of_dropping_rows(self):
        changes = [lambda a: a["tokens"]["records"][0].update(k=True),
                   lambda a: a["tokens"]["records"][0].update(n=4.0),
                   lambda a: a["tokens"]["records"][0].update(n=0),
                   lambda a: a["tokens"]["records"][0].update(k=-1),
                   lambda a: a["tokens"]["records"][0].update(k=5),
                   lambda a: a["tokens"]["records"][0].update(n=None),
                   lambda a: a["tokens"]["records"][0].update(age=5),
                   lambda a: a["tokens"]["records"][0].update(age=13),
                   lambda a: a["tokens"]["records"][0].update(age=8.0),
                   lambda a: a["tokens"]["records"][0].update(word="changed"),
                   lambda a: a["tokens"]["records"][0].update(study=""),
                   lambda a: a["tokens"]["records"][0].update(phase=None),
                   lambda a: a["tokens"]["records"][0].update(context="invalid"),
                   lambda a: a["selection"]["part1"][2].update(age=13)]
        for index, change in enumerate(changes):
            artifacts, bindings, expected = fixture()
            change(artifacts)
            with self.subTest(case=index), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)

    def test_selection_extraction_predictions_and_frozen_exclusions_have_exact_coverage(self):
        changes = [lambda a: a["tokens"]["records"].append(copy.deepcopy(a["tokens"]["records"][0])),
                   lambda a: a["predictions"]["rows"].append(copy.deepcopy(a["predictions"]["rows"][0])),
                   lambda a: a["extract"]["outcomes"].append(copy.deepcopy(a["extract"]["outcomes"][0])),
                   lambda a: a["selection"]["part1"].append(copy.deepcopy(a["selection"]["part1"][0])),
                   lambda a: a["extract"]["outcomes"][0].update(state="failed"),
                   lambda a: a["extract"]["outcomes"].pop(),
                   lambda a: a["predictions"]["rows"][0].update(tokenId="unknown"),
                   lambda a: a["tokens"]["records"][0].update(tokenId="unknown"),
                   lambda a: a["selection"]["part1Excluded"]["unmappable"].append("unknown"),
                   lambda a: a["tokens"].update(part1Excluded={"unmappable": [], "belowReaderMinimum": []}),
                   lambda a: a["closedDeclaration"].update(part1Excluded={"unmappable": [], "belowReaderMinimum": []}),
                   lambda a: a["closedDeclaration"]["part1"].pop(),
                   lambda a: a["closedDeclaration"]["part1"].append("made-up/a"),
                   lambda a: a["tokens"]["records"][0].update(speakerId="80"),
                   lambda a: a["selection"]["part1"][2].update(speakerId="80"),
                   lambda a: a["tokens"]["records"][0].update(speakerId="2"),
                   lambda a: a["tokens"]["records"][0].update(tokenId=""),
                   lambda a: a["selection"]["part1Excluded"].update(extra=[])]
        for index, change in enumerate(changes):
            artifacts, bindings, expected = fixture()
            change(artifacts)
            with self.subTest(case=index), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)

    def test_every_required_ancestor_and_closed_flags_match_parent_verified_pins(self):
        locations = [(name, "declaration", None) for name in ("tokens", "extract", "predictions")]
        locations += [(name, "upstream", key) for name, keys in
                      (("tokens", ("extract", "predictions", "retention")),
                       ("extract", ("clips",)), ("predictions", ("extract", "clips"))) for key in keys]
        locations += [("closedDeclaration", "inputs", key) for key in ("selection", "split")]
        for name, field, key in locations:
            artifacts, bindings, expected = fixture()
            if key is None:
                artifacts[name][field] = {"path": "/synthetic/wrong.json", "sha256": "0" * 64}
            else:
                artifacts[name][field] = {**artifacts[name][field], key: bindings["tokens"]}
            with self.subTest(location=(name, field, key)), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)
        for flag in ("testPartitionTouched", "thresholdSelected", "trainingPerformed",
                     "clinicalUseEligible", "learnerFeedbackEligible", "ratingsRead"):
            for value in (True, 0, None):
                artifacts, bindings, expected = fixture()
                artifacts["predictions" if flag == "ratingsRead" else "tokens"][flag] = value
                with self.subTest(flag=flag, value=value), self.assertRaises(ValueError):
                    prepare_dev_calibration_inputs(artifacts, bindings, expected)
        for change in (lambda a, b: b.pop("retention"),
                       lambda a, b: b["clips"].update(sha256="invalid"),
                       lambda a, b: b["tokens"].update(path="relative.json"),
                       lambda a, b: a["tokens"]["upstream"].update(unknown=b["tokens"]),
                       lambda a, b: a["extract"]["upstream"].pop("clips")):
            artifacts, bindings, expected = fixture()
            change(artifacts, bindings)
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)

    def test_full_dev_denominator_and_canonical_disjoint_rosters_are_required(self):
        changes = [lambda a, b, e: a["split"]["dev"].append("2"),
                   lambda a, b, e: a["split"]["test"].append("80"),
                   lambda a, b, e: a["split"].update(test=["2"]),
                   lambda a, b, e: a["split"].update(dev=["02", "10"]),
                   lambda a, b, e: a["split"].update(dev=[2, "10"]),
                   lambda a, b, e: a["split"].update(test=["0"]),
                   lambda a, b, e: a["split"].update(test=["+80"]),
                   lambda a, b, e: a["split"].update(test=["８０"]),
                   lambda a, b, e: e.update(devChildren=3),
                   lambda a, b, e: e.update(completeTokens=3),
                   lambda a, b, e: e.update(excludedTokens=2),
                   lambda a, b, e: e.update(selectedTokens=4),
                   lambda a, b, e: e.update(testChildren=2),
                   lambda a, b, e: e.update(extra=1),
                   lambda a, b, e: e.update(devChildren=True),
                   lambda a, b, e: e.update(testChildren=0)]
        for index, change in enumerate(changes):
            artifacts, bindings, expected = fixture()
            change(artifacts, bindings, expected)
            with self.subTest(case=index), self.assertRaises(ValueError):
                prepare_dev_calibration_inputs(artifacts, bindings, expected)
        artifacts, bindings, _ = fixture()
        with self.assertRaises(ValueError):
            prepare_dev_calibration_inputs(artifacts, bindings)

    def test_all_complete_dev_rows_are_converted_with_original_votes_and_probabilities(self):
        artifacts, bindings, expected = fixture()
        before = copy.deepcopy((artifacts, bindings, expected))
        result = prepare_dev_calibration_inputs(artifacts, bindings, expected)
        self.assertEqual(result["payload"], {
            "children": [{"childId": "10"}, {"childId": "2"}],
            "selectedTokens": [{"childId": "2", "tokenId": "made-up/a"},
                               {"childId": "10", "tokenId": "made-up/b"}],
            "rows": [{"childId": "2", "tokenId": "made-up/a", "retainedProbability": .25,
                      "positiveVotes": 4, "negativeVotes": 1},
                     {"childId": "10", "tokenId": "made-up/b", "retainedProbability": .75,
                      "positiveVotes": 1, "negativeVotes": 3}],
        })
        self.assertEqual((artifacts, bindings, expected), before)
        self.assertEqual(result["receipt"]["observedCounts"], expected)
        self.assertEqual(result["receipt"]["excludedTokenIds"], ["made-up/x"])
        self.assertEqual(result["receipt"]["positiveVotes"], 5)
        self.assertEqual(result["receipt"]["negativeVotes"], 4)


if __name__ == "__main__":
    unittest.main()
