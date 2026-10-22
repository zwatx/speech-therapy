"""Synthetic public artifact audit checks; no corpus or model inputs."""
import copy
import unittest
from r_confirmatory.evaluate import evaluate
from r_confirmatory.evaluation_audit import audit_evaluation


def payload():
    keys = [{'childId': 'child-a', 'tokenId': 'one'}, {'childId': 'child-a', 'tokenId': 'two'}]
    return {'children': [{'childId': 'child-a'}, {'childId': 'empty'}], 'selectedTokens': keys,
            'arms': {name: [{**key, 'status': 'processed', 'probability': probability}
                           for key, probability in zip(keys, [.1, .9])]
                     for name in ('candidate', 'retained', 'calibration')},
            'ratings': [{**key, 'status': 'available', 'positiveVotes': positive, 'negativeVotes': negative}
                        for key, positive, negative in [(keys[0], 1, 3), (keys[1], 3, 1)]]}


class EvaluationAuditTests(unittest.TestCase):
    def test_replays_mixed_vote_report_and_rejects_changed_metric(self):
        data = payload()
        report = evaluate(data)
        audit = audit_evaluation(data, report)
        self.assertEqual(audit['outcome'], 'verified')
        self.assertEqual(audit['fullChildDenominator'], 2)
        self.assertEqual(audit['selectedTokenDenominator'], 2)
        changed = copy.deepcopy(report)
        changed['children'][0]['arms']['candidate']['auroc'] = .8
        with self.assertRaises(ValueError): audit_evaluation(data, changed)

    def test_replays_multichild_bootstrap_gains_and_empty_denominators(self):
        data = payload()
        # Different raw ranking gains; a whole-child bootstrap has a real distribution.
        for child, candidate, retained, calibration in [
                ('child-b', [.9, .1], [.1, .9], [.3, .7]),
                ('child-c', [.1, .9], [.9, .1], [.5, .5])]:
            data['children'].append({'childId': child, 'descriptors': {'age': None}})
            for index, (pos, neg) in enumerate([(1, 3), (3, 1)]):
                key = {'childId': child, 'tokenId': str(index)}
                data['selectedTokens'].append(key)
                data['ratings'].append({**key, 'status': 'available', 'positiveVotes': pos, 'negativeVotes': neg})
                for arm, scores in [('candidate', candidate), ('retained', retained), ('calibration', calibration)]:
                    data['arms'][arm].append({**key, 'status': 'processed', 'probability': scores[index]})
        report = evaluate(data)
        self.assertEqual(audit_evaluation(data, report)['fullChildDenominator'], 4)
        self.assertEqual(report['pairedSummary']['candidateVsRetained']['auroc']['meanGain'], 0)
        self.assertEqual(report['pairedSummary']['candidateVsRetained']['auroc']['bootstrap']['interval95'], [-.5, .5])
        changed = copy.deepcopy(report)
        changed['pairedSummary']['candidateVsRetained']['auroc']['bootstrap']['interval95'][1] = .4
        with self.assertRaises(ValueError): audit_evaluation(data, changed)
        empty = {'children': [], 'selectedTokens': [], 'arms': {name: [] for name in data['arms']}, 'ratings': []}
        self.assertEqual(audit_evaluation(empty, evaluate(empty))['fullChildDenominator'], 0)

    def test_full_coverage_failures_and_paired_intersections_are_checked(self):
        data = payload()
        data['arms']['candidate'][0] = {**data['selectedTokens'][0], 'status': 'failed', 'reason': 'synthetic_model_failure'}
        data['arms']['calibration'][1] = {**data['selectedTokens'][1], 'status': 'unavailable', 'reason': 'synthetic_unsupported'}
        data['ratings'][0] = {**data['selectedTokens'][0], 'status': 'unavailable', 'reason': 'synthetic_missing_rating'}
        report = evaluate(data)
        audit_evaluation(data, report)
        mutations = [
            lambda r: r.update(fullChildDenominator=1),
            lambda r: r.update(learnerFeedbackEligible=True),
            lambda r: r['children'][0]['arms']['candidate']['coverage'].update(failed=0),
            lambda r: r['children'][0]['paired']['candidateVsCalibration'].update(tokenIds=['fake']),
            lambda r: r['children'][0]['arms']['candidate']['exclusions'][0].update(reasons=[]),
            lambda r: r['pairedSummary']['candidateVsCalibration']['brier']['excludedChildren'].pop(),
            lambda r: r['terminalOutcomes']['ratings'][0].update(reason='changed'),
        ]
        for index, mutation in enumerate(mutations):
            changed = copy.deepcopy(report); mutation(changed)
            with self.subTest(index=index), self.assertRaises(ValueError): audit_evaluation(data, changed)

    def test_invalid_inputs_and_nonfinite_reports_fail_closed(self):
        data = payload(); report = evaluate(data)
        mutations = [lambda p: p['ratings'].pop(), lambda p: p['arms']['retained'].pop(),
                     lambda p: p['selectedTokens'].append(copy.deepcopy(p['selectedTokens'][0])),
                     lambda p: p['arms']['candidate'][0].update(probability=True),
                     lambda p: p['arms']['candidate'][0].update(probability=10**400),
                     lambda p: p['ratings'][0].update(positiveVotes=True),
                     lambda p: p['children'][0].update(childId=' '),
                     lambda p: p['children'][0].update(descriptors={'age': float('nan')}),
                     lambda p: p.update(extra=True)]
        for index, mutation in enumerate(mutations):
            changed = copy.deepcopy(data); mutation(changed)
            with self.subTest(index=index), self.assertRaises(ValueError): audit_evaluation(changed, report)
        changed = copy.deepcopy(report)
        changed['children'][0]['arms']['candidate']['brier'] = float('nan')
        with self.assertRaises(ValueError): audit_evaluation(data, changed)

    def test_clipped_probabilities_undefined_votes_and_permutations_replay(self):
        data = payload()
        for arm in data['arms'].values():
            arm[0]['probability'] = 0.0; arm[1]['probability'] = 1.0
        data['ratings'][0].update(positiveVotes=0, negativeVotes=4)
        data['ratings'][1].update(positiveVotes=0, negativeVotes=4)
        report = evaluate(data)
        self.assertIsNone(report['children'][0]['arms']['candidate']['auroc'])
        audit_evaluation(data, report)
        reordered = copy.deepcopy(data)
        for key in ('children', 'selectedTokens', 'ratings'): reordered[key].reverse()
        for rows in reordered['arms'].values(): rows.reverse()
        self.assertEqual(audit_evaluation(data, report), audit_evaluation(reordered, report))

    def test_small_proper_score_differences_keep_reported_sign_accounting(self):
        import math
        data = payload()
        data['arms']['calibration'][0]['probability'] = math.nextafter(.1, 1)
        audit_evaluation(data, evaluate(data))

    def test_mixed_coverage_and_near_zero_signs_across_sixty_synthetic_cases(self):
        import random
        rng = random.Random(20261003)
        for trial in range(60):
            data = {'children': [], 'selectedTokens': [],
                    'arms': {arm: [] for arm in ('candidate', 'retained', 'calibration')}, 'ratings': []}
            for child in range(rng.randrange(1, 8)):
                identity = f'synthetic-{child}'
                data['children'].append({'childId': identity})
                for token in range(rng.randrange(0, 8)):
                    key = {'childId': identity, 'tokenId': f't{token}'}
                    data['selectedTokens'].append(key)
                    pos, neg = rng.randrange(0, 6), rng.randrange(0, 6)
                    if pos + neg == 0: pos = 1
                    if rng.random() < .1:
                        data['ratings'].append({**key, 'status': 'unavailable', 'reason': 'synthetic_missing'})
                    else:
                        data['ratings'].append({**key, 'status': 'available', 'positiveVotes': pos, 'negativeVotes': neg})
                    for arm in data['arms']:
                        if rng.random() < .1:
                            data['arms'][arm].append({**key, 'status': 'failed', 'reason': 'synthetic_failure'})
                        else:
                            data['arms'][arm].append({**key, 'status': 'processed',
                                                      'probability': rng.choice([0.0, .1, .5, .9, 1.0])})
            with self.subTest(trial=trial): audit_evaluation(data, evaluate(data))

    def test_gain_arithmetic_and_raw_terminal_values_are_bound_exactly(self):
        import math
        data = payload(); data['children'][0]['descriptors'] = {'age': 6.0}
        report = evaluate(data)
        changed = copy.deepcopy(report)
        changed['children'][0]['paired']['candidateVsCalibration']['logLossGain'] = 1e-16
        with self.assertRaises(ValueError): audit_evaluation(data, changed)
        changed = copy.deepcopy(report)
        changed['terminalOutcomes']['arms']['candidate'][0]['probability'] = math.nextafter(.1, 1)
        with self.assertRaises(ValueError): audit_evaluation(data, changed)
        changed = copy.deepcopy(report)
        changed['children'][0]['descriptors']['age'] = math.nextafter(6.0, 7)
        with self.assertRaises(ValueError): audit_evaluation(data, changed)
        changed = copy.deepcopy(report)
        changed['pairedSummary']['candidateVsCalibration']['logLoss']['improvedChildren'] = 1
        with self.assertRaises(ValueError): audit_evaluation(data, changed)


if __name__ == '__main__': unittest.main()
