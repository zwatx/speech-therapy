import copy
import unittest

from test_domain import manifest_fixture, ready_aggregate
from workbench.domain import bind_manifest, semantic_digest
from workbench.reports import build_report


class ReportTests(unittest.TestCase):
    def test_every_terminal_attempt_stays_in_denominators_and_breakdowns(self):
        aggregate = ready_aggregate()
        manifest = manifest_fixture()
        for number, terminal in enumerate(('rejected', 'cancelled', 'failed', 'skipped'), 1):
            attempt = copy.deepcopy(manifest['attempts'][0])
            attempt.update({'id': 'attempt-' + str(number), 'terminal': terminal, 'recording': None})
            manifest['attempts'].append(attempt)
        aggregate['manifest'] = bind_manifest(manifest)
        report = build_report(aggregate)
        counts = report['denominators']
        self.assertEqual(counts['attempts'], 5)
        self.assertEqual(counts['terminalCounts'], {
            'processed_unverified': 1, 'rejected': 1, 'cancelled': 1, 'failed': 1, 'skipped': 1})
        self.assertEqual(counts['recordingsPresent'], 1)
        self.assertEqual(counts['engineeringReady'], 1)
        self.assertEqual(report['coverage']['engineeringReady'], {'numerator': 1, 'denominator': 5})
        self.assertEqual(sum(row['attempts'] for row in report['byAge']), 5)
        self.assertEqual(sum(row['attempts'] for row in report['byTarget']), 5)
        self.assertEqual(sum(row['attempts'] for row in report['bySplit']), 5)
        self.assertFalse(report['flags']['clinicalUseEligible'])

    def test_original_agreement_reports_all_pairs_and_conditional_kappa_without_model_lock(self):
        aggregate = ready_aggregate()
        manifest = manifest_fixture()
        manifest['attempts'] = []
        aggregate['reviews'] = {'reviewer-a': {}, 'reviewer-b': {}}
        answer = ready_aggregate()['reviews']['reviewer-a']['attempt-a']['answer']
        pairs = [('expected', 'expected'), ('expected', 'altered'), ('altered', 'altered'),
                 ('omitted', 'omitted'), ('unscorable', 'expected')]
        for index, (target_a, target_b) in enumerate(pairs):
            attempt = copy.deepcopy(manifest_fixture()['attempts'][0])
            attempt['id'] = 'pair-' + str(index)
            manifest['attempts'].append(attempt)
            for role, target in zip(('reviewer-a', 'reviewer-b'), (target_a, target_b)):
                original = dict(answer, target=target)
                aggregate['reviews'][role][attempt['id']] = {'answer': original, 'sha256': str(index)}
        aggregate['manifest'] = bind_manifest(manifest)
        aggregate['predictionLock'] = None
        agreement = build_report(aggregate)['agreement']
        self.assertEqual(agreement['pairedCount'], 5)
        self.assertEqual(agreement['exactAgreement'], 0.6)
        self.assertAlmostEqual(agreement['kappa'], 7 / 11)
        self.assertEqual(agreement['excludedUncertainOrUnscorable'], 1)
        self.assertEqual(agreement['scorablePairs'], {'numerator': 4, 'denominator': 5})
        aggregate['adjudications']['pair-1'] = {'answer': {'target': 'expected'}}
        self.assertEqual(build_report(aggregate)['agreement'], agreement)

    def test_comparison_waits_for_both_review_seals_and_undefined_kappa_is_null(self):
        aggregate = ready_aggregate()
        self.assertIsNone(build_report(aggregate)['agreement']['kappa'])
        aggregate['seals']['reviewer-b'] = False
        report = build_report(aggregate)
        self.assertFalse(report['agreement']['available'])
        self.assertIsNone(report['agreement']['exactAgreement'])
        self.assertFalse(report['referenceComparison']['available'])

    def test_repeatability_keeps_all_declared_pairs_excludes_retries_and_exposes_condition_mismatch(self):
        aggregate = ready_aggregate()
        manifest = manifest_fixture()
        repeat = copy.deepcopy(manifest['attempts'][0])
        repeat.update({'id': 'repeat', 'plannedRepeatOf': 'attempt-a'})
        retry = copy.deepcopy(repeat)
        retry.update({'id': 'retry', 'plannedRepeatOf': None, 'retryOf': 'repeat'})
        mismatch = copy.deepcopy(repeat)
        mismatch.update({'id': 'different-room', 'conditionId': 'room-b'})
        manifest['attempts'].extend([repeat, retry, mismatch])
        aggregate['manifest'] = bind_manifest(manifest)
        base_answer = aggregate['reviews']['reviewer-a']['attempt-a']['answer']
        for identifier in ('repeat', 'retry', 'different-room'):
            for role in ('reviewer-a', 'reviewer-b'):
                aggregate['reviews'][role][identifier] = {'answer': dict(base_answer, target='altered')}
            aggregate['predictionLock']['payload']['rows'].append({
                'attemptId': identifier, 'status': 'processed', 'probabilities': [0.4, 0.2, 0.4]})
        repeatability = build_report(aggregate)['repeatability']
        self.assertEqual(repeatability['declaredPairs'], 2)
        self.assertEqual(repeatability['comparablePairs'], 1)
        self.assertEqual([pair['toAttemptId'] for pair in repeatability['pairs']], ['repeat', 'different-room'])
        matched, mismatched = repeatability['pairs']
        self.assertEqual(matched['originalTargetTransitions']['reviewer-a'], {'from': 'expected', 'to': 'altered'})
        for actual, expected in zip(matched['probabilityDifferences'], (0.2, -0.1, -0.1)):
            self.assertAlmostEqual(actual, expected)
        self.assertIn('condition_mismatch', mismatched['reasons'])
        self.assertIsNone(mismatched['probabilityDifferences'])
        self.assertFalse(repeatability['meaningfulImprovementEstablished'])

    def test_model_reference_comparison_waits_for_lock_and_retains_abstaining_attempt(self):
        aggregate = ready_aggregate()
        aggregate['reviews']['reviewer-b']['attempt-a']['answer']['speech'] = 'uncertain'
        comparison = build_report(aggregate)['referenceComparison']
        self.assertTrue(comparison['available'])
        self.assertEqual(len(comparison['rows']), 1)
        self.assertIsNone(comparison['rows'][0]['engineeringReferenceTarget'])
        aggregate['predictionLock'] = None
        self.assertFalse(build_report(aggregate)['referenceComparison']['available'])

    def test_report_exports_independent_all_attempt_admissions_and_prediction_values(self):
        aggregate = ready_aggregate()
        report = build_report(aggregate)
        self.assertEqual(set(report['admissionByAttemptId']), {'attempt-a'})
        admission = report['admissionByAttemptId']['attempt-a']
        self.assertEqual(admission['status'], 'engineering_ready')
        admission['historicalContext']['taskSha256'] = 'tampered-in-export'
        admission['reasons'].append('tampered-in-export')
        report['referenceComparison']['rows'][0]['probabilities'][0] = 1
        untouched = build_report(aggregate)
        self.assertEqual(untouched['admissionByAttemptId']['attempt-a']['reasons'], [])
        self.assertNotEqual(untouched['admissionByAttemptId']['attempt-a']['historicalContext']['taskSha256'], 'tampered-in-export')
        self.assertEqual(untouched['referenceComparison']['rows'][0]['probabilities'], [0.2, 0.3, 0.5])

    def test_successful_retry_cannot_be_selected_as_a_comparable_repeat_baseline(self):
        aggregate = ready_aggregate()
        manifest = manifest_fixture()
        retry = copy.deepcopy(manifest['attempts'][0])
        retry.update({'id': 'successful-retry', 'retryOf': 'attempt-a'})
        repeat = copy.deepcopy(manifest['attempts'][0])
        repeat.update({'id': 'later-repeat', 'plannedRepeatOf': 'successful-retry'})
        manifest['attempts'][0].update({'terminal': 'failed', 'recording': None})
        manifest['attempts'].extend([retry, repeat])
        aggregate['manifest'] = bind_manifest(manifest)
        answer = aggregate['reviews']['reviewer-a']['attempt-a']['answer']
        aggregate['reviews'] = {role: {
            identifier: {'answer': copy.deepcopy(answer), 'sha256': semantic_digest(answer)}
            for identifier in ('successful-retry', 'later-repeat')}
            for role in ('reviewer-a', 'reviewer-b')}
        payload = aggregate['predictionLock']['payload']
        payload['model']['manifestSha256'] = semantic_digest(aggregate['manifest'])
        payload['rows'] = []
        for attempt in aggregate['manifest']['attempts']:
            row = {'attemptId': attempt['id'], 'contextSha256': semantic_digest(attempt['context'])}
            if attempt['id'] == 'attempt-a':
                row.update({'status': 'failed', 'reason': 'invented_failure'})
            else:
                probabilities = [0.4, 0.2, 0.4] if attempt['id'] == 'successful-retry' else [0.2, 0.3, 0.5]
                row.update({'status': 'processed', 'probabilities': probabilities})
            payload['rows'].append(row)
        aggregate['predictionLock']['sha256'] = semantic_digest(payload)
        report = build_report(aggregate)
        for identifier in ('successful-retry', 'later-repeat'):
            self.assertEqual(report['admissionByAttemptId'][identifier]['status'], 'engineering_ready')
        repeatability = report['repeatability']
        self.assertEqual(repeatability['declaredPairs'], 1)
        self.assertEqual(repeatability['comparablePairs'], 0)
        self.assertEqual(repeatability['retryAttemptsExcluded'], 1)
        pair = repeatability['pairs'][0]
        self.assertEqual(pair['fromAttemptId'], 'successful-retry')
        self.assertEqual(pair['toAttemptId'], 'later-repeat')
        self.assertIn('retry_endpoint', pair['reasons'])
        self.assertFalse(pair['comparable'])
        self.assertIsNone(pair['probabilityDifferences'])
        self.assertEqual(pair['originalTargetTransitions']['reviewer-a'], {'from': 'expected', 'to': 'expected'})


if __name__ == '__main__':
    unittest.main()
