"""Independent audit checks using synthetic supplied calibration inputs only."""
import copy
import unittest
from r_confirmatory.calibrate import fit_calibration
from r_confirmatory.calibration_audit import audit_calibration


def synthetic_payload():
    return {'children': [{'childId': 'a'}, {'childId': 'b'}],
            'selectedTokens': [{'childId': 'a', 'tokenId': 'one'}, {'childId': 'b', 'tokenId': 'two'}],
            'rows': [{'childId': 'a', 'tokenId': 'one', 'retainedProbability': .5,
                      'positiveVotes': 3, 'negativeVotes': 1},
                     {'childId': 'b', 'tokenId': 'two', 'retainedProbability': .5,
                      'positiveVotes': 1, 'negativeVotes': 3}]}


class AuditTests(unittest.TestCase):
    def test_audits_known_constant_prior_and_rejects_changed_coefficients(self):
        payload = synthetic_payload()
        control = fit_calibration(payload)
        report = audit_calibration(payload, control)
        self.assertEqual(report['outcome'], 'verified')
        self.assertAlmostEqual(report['objective'], .6931471805599453, places=13)
        self.assertEqual(report['predictions'], [.5, .5])
        changed = copy.deepcopy(control)
        changed['coefficients']['intercept'] = .1
        with self.assertRaises(ValueError): audit_calibration(payload, changed)

    def test_receipt_tampering_and_eligibility_changes_are_rejected(self):
        payload = synthetic_payload()
        control = fit_calibration(payload)
        mutations = [
            lambda c: c.update(inputDigest='0' * 64),
            lambda c: c.update(membershipDigest='0' * 64),
            lambda c: c.update(learnerFeedbackEligible=True),
            lambda c: c.update(fullChildDenominator=1),
            lambda c: c['source'].update(sha256='0' * 64),
            lambda c: c['recipe'].update(slopeRidge=.01),
            lambda c: c['initialization'].update(weightedTargetMean=.1),
            lambda c: c['canonicalInput']['rows'][0].update(positiveVotes=2),
            lambda c: c['weights'][0].update(weight=.1),
            lambda c: c['fittedPredictions'][0].update(probability=.9),
            lambda c: c['transform'].update(logitScale=2),
            lambda c: c['unconstrained']['diagnostics'].update(newtonSteps=101),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                changed = copy.deepcopy(control)
                mutation(changed)
                with self.assertRaises(ValueError): audit_calibration(payload, changed)

    def test_nonconstant_monotonic_fit_roundtrips_and_replays_independently(self):
        import json
        payload = synthetic_payload()
        payload['rows'][0].update(retainedProbability=.1, positiveVotes=1, negativeVotes=9)
        payload['rows'][1].update(retainedProbability=.9, positiveVotes=9, negativeVotes=1)
        control = json.loads(json.dumps(fit_calibration(payload), allow_nan=False))
        report = audit_calibration(payload, control)
        self.assertLess(report['projectedGradientInfinityNorm'], 1e-8)
        self.assertLess(report['predictions'][0], report['predictions'][1])
        self.assertAlmostEqual(sum(report['predictions']), 1, places=12)
        changed = copy.deepcopy(control)
        changed['unconstrained']['diagnostics']['gradient'][0] += .01
        with self.assertRaises(ValueError): audit_calibration(payload, changed)

    def test_negative_slope_boundary_uses_child_balance_not_pooled_votes(self):
        payload = synthetic_payload()
        payload['rows'][0].update(retainedProbability=.1, positiveVotes=3, negativeVotes=1)
        payload['rows'][1].update(retainedProbability=.9, positiveVotes=1, negativeVotes=3)
        # Replicate votes for one child; that child's mass remains one half.
        payload['rows'][1]['positiveVotes'] *= 100
        payload['rows'][1]['negativeVotes'] *= 100
        control = fit_calibration(payload)
        self.assertTrue(control['boundaryApplied'])
        report = audit_calibration(payload, control)
        self.assertEqual(report['predictions'], [.5, .5])
        self.assertAlmostEqual(report['objective'], .6931471805599453, places=13)

    def test_reordered_supplied_inputs_retain_same_audit_and_missing_rows_fail(self):
        payload = synthetic_payload()
        control = fit_calibration(payload)
        reversed_payload = {key: list(reversed(value)) for key, value in payload.items()}
        self.assertEqual(audit_calibration(payload, control), audit_calibration(reversed_payload, control))
        missing = copy.deepcopy(payload)
        missing['rows'].pop()
        with self.assertRaises(ValueError): audit_calibration(missing, control)

    def test_bool_substitution_is_not_an_equivalent_numeric_receipt(self):
        payload = synthetic_payload()
        control = fit_calibration(payload)
        changed = copy.deepcopy(control)
        changed['recipe']['interceptPenalty'] = False
        with self.assertRaises(ValueError): audit_calibration(payload, changed)
        changed = copy.deepcopy(control)
        changed['canonicalInput']['rows'][0]['negativeVotes'] = True
        with self.assertRaises(ValueError): audit_calibration(payload, changed)

    def test_unrepresentable_numbers_are_validation_failures(self):
        payload = synthetic_payload()
        control = fit_calibration(payload)
        bad_input = copy.deepcopy(payload)
        bad_input['rows'][0]['retainedProbability'] = 10**400
        with self.assertRaises(ValueError): audit_calibration(bad_input, control)
        bad_control = copy.deepcopy(control)
        bad_control['transform']['logitMean'] = 10**400
        with self.assertRaises(ValueError): audit_calibration(payload, bad_control)
        bad_control = copy.deepcopy(control)
        bad_control['unconstrained']['coefficients']['slope'] = 1e308
        with self.assertRaises(ValueError): audit_calibration(payload, bad_control)


if __name__ == '__main__': unittest.main()
