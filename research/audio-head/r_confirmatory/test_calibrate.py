"""Calibration worked examples use synthetic data exclusively."""
import copy
import hashlib
import json
import math
import unittest

from r_confirmatory.calibrate import CalibrationFitError, fit_calibration, predict_calibration


def fixture(probabilities=(0.5, 0.5), votes=((1, 3), (1, 3))):
    keys = [{"childId": "synthetic-child", "tokenId": f"synthetic-{i}"}
            for i in range(len(probabilities))]
    return {"children": [{"childId": "synthetic-child"}], "selectedTokens": keys,
            "rows": [{**key, "retainedProbability": probability,
                      "positiveVotes": pos, "negativeVotes": neg}
                     for key, probability, (pos, neg) in zip(keys, probabilities, votes)]}


class CalibrationTests(unittest.TestCase):
    def test_complete_membership_is_required_without_dropping_empty_children(self):
        for mutate in (lambda p: p["rows"].pop(),
                       lambda p: p["children"].append({"childId": "synthetic-empty"})):
            payload = fixture()
            mutate(payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                fit_calibration(payload)

    def test_constant_score_has_known_intercept_prior_and_saved_transform(self):
        payload = fixture()
        before = copy.deepcopy(payload)
        control = fit_calibration(payload)
        self.assertAlmostEqual(control["coefficients"]["intercept"], -1.0986122886681098)
        self.assertEqual(control["coefficients"]["slope"], 0.0)
        self.assertEqual(control["transform"], {"logitMean": 0.0, "logitPopulationStd": 0.0,
                                               "logitScale": 1.0, "inputClip": 1e-6})
        self.assertEqual([row["weight"] for row in control["weights"]], [0.5, 0.5])
        for probability in predict_calibration(control, [0, 0.5, 1]):
            self.assertAlmostEqual(probability, 0.25)
        self.assertEqual(payload, before)

    def test_increasing_votes_produce_positive_slope_and_monotone_predictions(self):
        control = fit_calibration(fixture((0.1, 0.9), ((1, 3), (3, 1))))
        self.assertGreater(control["coefficients"]["slope"], 0)
        # Symmetric standardized scores are -1/+1; ridge shifts the logit(3/4)
        # optimum slightly toward zero. These values were worked independently.
        self.assertAlmostEqual(control["coefficients"]["intercept"], 0.0, places=10)
        self.assertAlmostEqual(control["coefficients"]["slope"], 1.092792525142797, places=8)
        predictions = predict_calibration(control, [0, 0.1, 0.5, 0.9, 1])
        self.assertTrue(all(a < b for a, b in zip(predictions, predictions[1:])))
        self.assertAlmostEqual(predictions[1], 0.2510927925251427, places=8)
        self.assertLessEqual(control["unconstrained"]["diagnostics"]["gradientInfinityNorm"], 1e-8)
        self.assertGreater(control["unconstrained"]["diagnostics"]["newtonSteps"], 0)

    def test_negative_unconstrained_slope_uses_exact_boundary_prior(self):
        control = fit_calibration(fixture((0.1, 0.9), ((3, 1), (1, 3))))
        self.assertEqual(control["coefficients"], {"intercept": 0.0, "slope": 0.0})
        self.assertTrue(control["boundaryApplied"])
        self.assertLess(control["unconstrained"]["coefficients"]["slope"], 0)
        self.assertEqual(predict_calibration(control, [0, 0.1, 0.9, 1]), [0.5] * 4)
        self.assertAlmostEqual(control["projected"]["gradient"][1], 0.25)
        self.assertEqual(control["projected"]["projectedGradientInfinityNorm"], 0)

    def test_clipped_boundary_prior_fails_terminally_when_not_stationary(self):
        # Both classes exist, but the weighted prior is far below 1e-6.
        # The frozen clipped boundary intercept cannot meet the 1e-8 gate.
        payload = fixture((0.1, 0.9), ((1, 10**12), (0, 10**12)))
        with self.assertRaisesRegex(CalibrationFitError, "projected stationarity") as caught:
            fit_calibration(payload)
        self.assertTrue(caught.exception.diagnostics["boundaryApplied"])
        self.assertGreater(caught.exception.diagnostics["projected"]["projectedGradientInfinityNorm"], 1e-8)

    def test_receipt_binds_canonical_inputs_and_stays_research_only(self):
        control = fit_calibration(fixture())
        self.assertEqual(control["status"], "supplied_input_fit_preparation_not_study_declaration")
        self.assertTrue(control["researchOnly"])
        for flag in ("clinicalUseEligible", "learnerFeedbackEligible", "productionUseEligible"):
            self.assertFalse(control[flag])
        self.assertEqual(control["fullChildDenominator"], 1)
        self.assertEqual(control["selectedTokenDenominator"], 2)
        self.assertEqual(control["canonicalInput"], fixture())
        serialized = json.dumps(control["canonicalInput"], sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.assertEqual(control["inputDigest"], hashlib.sha256(serialized).hexdigest())
        self.assertEqual(control["recipe"]["slopeRidge"], 0.001)
        self.assertEqual(control["recipe"]["interceptPenalty"], 0)
        self.assertEqual(control["initialization"], {"weightedTargetMean": 0.25,
            "clippedWeightedTargetMean": 0.25, "intercept": -1.0986122886681096, "slope": 0.0})
        self.assertEqual([{"childId": row["childId"], "tokenId": row["tokenId"]}
                          for row in control["fittedPredictions"]], fixture()["selectedTokens"])
        for row in control["fittedPredictions"]:
            self.assertAlmostEqual(row["probability"], 0.25)
        self.assertEqual(control["dependencies"]["dtype"], "float64")
        self.assertEqual(len(control["source"]["sha256"]), 64)
        json.dumps(control, allow_nan=False)

    def test_predict_rejects_malformed_saved_controls_and_probability_values(self):
        control = fit_calibration(fixture())
        mutations = [lambda c: c["coefficients"].update(slope=-1),
                     lambda c: c["transform"].update(logitScale=0),
                     lambda c: c["transform"].update(inputClip=0.01),
                     lambda c: c.update(extra=True),
                     lambda c: c["coefficients"].update(intercept=float("nan")),
                     lambda c: c.update(clinicalUseEligible=True)]
        for mutate in mutations:
            changed = copy.deepcopy(control)
            mutate(changed)
            with self.subTest(control=changed), self.assertRaises(ValueError):
                predict_calibration(changed, [0.2])
        for values in (None, (), [True], [float("nan")], [float("inf")], [-0.1], [1.1], [10**400]):
            with self.subTest(probabilities=values), self.assertRaises(ValueError):
                predict_calibration(control, values)

    def test_listener_mass_within_child_and_equal_child_weight_have_known_prior(self):
        payload = fixture((0.5, 0.5), ((1, 0), (0, 3)))
        key = {"childId": "synthetic-heavy", "tokenId": "synthetic-only"}
        payload["children"].append({"childId": "synthetic-heavy"})
        payload["selectedTokens"].append(key)
        payload["rows"].append({**key, "retainedProbability": 0.5,
                                "positiveVotes": 1000, "negativeVotes": 0})
        control = fit_calibration(payload)
        self.assertEqual([row["weight"] for row in control["weights"]], [0.125, 0.375, 0.5])
        self.assertEqual(control["initialization"]["weightedTargetMean"], 0.625)
        self.assertAlmostEqual(control["coefficients"]["intercept"], 0.5108256237659907)
        self.assertEqual(control["coefficients"]["slope"], 0.0)
        self.assertAlmostEqual(predict_calibration(control, [0.1])[0], 0.625)

    def test_extreme_input_clipping_and_unweighted_population_moments(self):
        control = fit_calibration(fixture((0, 1), ((1, 3), (3, 1))))
        self.assertAlmostEqual(control["transform"]["logitPopulationStd"], 13.815509557949396)
        probabilities = predict_calibration(control, [0, 1e-8, 1e-6, 1 - 1e-6, 1 - 1e-8, 1])
        self.assertEqual(probabilities[:3], [probabilities[0]] * 3)
        self.assertEqual(probabilities[3:], [probabilities[3]] * 3)
        control = fit_calibration(fixture((0.1, 0.9), ((1, 3), (3, 1))))
        self.assertAlmostEqual(control["transform"]["logitMean"], 0.0)
        self.assertAlmostEqual(control["transform"]["logitPopulationStd"], 2.1972245773362196)
        # Unequal listener mass must not turn input moments into weighted moments.
        weighted = fit_calibration(fixture((0.1, 0.9), ((100, 300), (3, 1))))
        self.assertEqual(weighted["transform"], control["transform"])
        tiny = fit_calibration(fixture((0.5, 0.50000001)))
        self.assertGreater(tiny["transform"]["logitPopulationStd"], 0)
        self.assertLess(tiny["transform"]["logitPopulationStd"], 1e-6)
        self.assertEqual(tiny["transform"]["logitScale"], 1.0)

    def test_permuted_rosters_have_identical_receipts_and_membership_digest_excludes_votes(self):
        payload = fixture((0.1, 0.9), ((1, 3), (3, 1)))
        second = fixture((0.2, 0.7), ((1, 4), (4, 1)))
        for field in ("children", "selectedTokens", "rows"):
            for row in second[field]:
                row["childId"] = "synthetic-10"
            payload[field].extend(second[field])
        before = copy.deepcopy(payload)
        permuted = copy.deepcopy(payload)
        for rows in permuted.values():
            rows.reverse()
        control = fit_calibration(payload)
        self.assertEqual(control, fit_calibration(permuted))
        self.assertEqual([row["childId"] for row in control["canonicalInput"]["children"]],
                         ["synthetic-10", "synthetic-child"])
        self.assertEqual(payload, before)
        changed = copy.deepcopy(payload)
        changed["rows"][0]["positiveVotes"] += 1
        refit = fit_calibration(changed)
        self.assertEqual(control["membershipDigest"], refit["membershipDigest"])
        self.assertNotEqual(control["inputDigest"], refit["inputDigest"])
        canonical = control["canonicalInput"]
        membership = {key: canonical[key] for key in ("children", "selectedTokens")}
        serialized = json.dumps(membership, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                allow_nan=False).encode("utf-8")
        self.assertEqual(control["membershipDigest"], hashlib.sha256(serialized).hexdigest())

    def test_strict_payload_and_complete_rosters_fail_closed(self):
        mutations = [
            lambda p: p.update(extra=True), lambda p: p.pop("rows"),
            lambda p: p.update(children=[]), lambda p: p.update(children=None),
            lambda p: p.update(selectedTokens=()), lambda p: p.update(rows={}),
            lambda p: p["children"].append(copy.deepcopy(p["children"][0])),
            lambda p: p["children"][0].update(descriptors={}),
            lambda p: p["children"][0].update(childId=True),
            lambda p: p["children"][0].update(childId="  "),
            lambda p: p["selectedTokens"].append(copy.deepcopy(p["selectedTokens"][0])),
            lambda p: p["selectedTokens"][0].update(extra=True),
            lambda p: p["selectedTokens"][0].update(childId="unknown"),
            lambda p: p["selectedTokens"][0].update(tokenId=1),
            lambda p: p["selectedTokens"][0].update(tokenId=" "),
            lambda p: p["rows"].append(copy.deepcopy(p["rows"][0])),
            lambda p: p["rows"][0].update(extra=True),
            lambda p: p["rows"][0].update(tokenId="unknown"),
            lambda p: p["rows"][0].update(childId="unknown"),
            lambda p: p["rows"][0].update(positiveVotes=True),
            lambda p: p["rows"][0].update(negativeVotes=-1),
            lambda p: p["rows"][0].update(positiveVotes=0.5),
            lambda p: p["rows"][0].update(positiveVotes=float("inf")),
            lambda p: p["rows"][0].update(positiveVotes=0, negativeVotes=0),
            lambda p: p["rows"][0].update(retainedProbability=True),
            lambda p: p["rows"][0].update(retainedProbability=float("nan")),
            lambda p: p["rows"][0].update(retainedProbability=float("inf")),
            lambda p: p["rows"][0].update(retainedProbability=-0.1),
            lambda p: p["rows"][0].update(retainedProbability=1.1),
            lambda p: p["rows"][0].update(retainedProbability=10**400),
            lambda p: p["rows"].__setitem__(0, None),
        ]
        for number, mutate in enumerate(mutations):
            payload = fixture()
            mutate(payload)
            with self.subTest(case=number), self.assertRaises(ValueError):
                fit_calibration(payload)
        for payload in (None, [], {}, fixture(votes=((1, 0), (1, 0))),
                        fixture(votes=((0, 1), (0, 1)))):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                fit_calibration(payload)

    def test_predict_uses_saved_parameters_without_fitting_supplied_probabilities(self):
        control = json.loads(json.dumps(fit_calibration(fixture((0.1, 0.9), ((1, 3), (3, 1))))))
        before = copy.deepcopy(control)
        one = predict_calibration(control, [0.2])
        together = predict_calibration(control, [0.2, 0.9, 0.9, 0.9])
        self.assertEqual(one, together[:1])
        self.assertEqual(predict_calibration(control, []), [])
        self.assertEqual(control, before)


if __name__ == "__main__":
    unittest.main()
