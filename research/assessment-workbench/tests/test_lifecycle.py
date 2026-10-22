from pathlib import Path
import tempfile
import unittest

from workbench.__main__ import exercise
from workbench.store import Store, verify_export


class CompleteInventedWorkflowTests(unittest.TestCase):
    def test_full_roster_reconciles_and_adjudication_resolves_only_target(self):
        with tempfile.TemporaryDirectory() as directory:
            store = exercise(Path(directory) / 'project')
            state = Store.open(store.path).snapshot()
            report = state['report']
            counts = report['denominators']
            self.assertEqual((counts['attempts'], counts['participants'], counts['recordingsPresent'], counts['predictionsProcessed'], counts['engineeringReady']), (11, 4, 9, 8, 3))
            self.assertEqual(counts['terminalCounts'], {'processed_unverified': 9, 'rejected': 0, 'cancelled': 0, 'failed': 1, 'skipped': 1})
            self.assertEqual((counts['reviewACount'], counts['reviewBCount'], counts['pairedOriginalReviews'], counts['adjudicated']), (11, 11, 11, 1))
            self.assertEqual(report['agreement']['scorablePairs'], {'numerator': 7, 'denominator': 11})
            self.assertAlmostEqual(report['agreement']['exactAgreement'], 10 / 11)
            self.assertAlmostEqual(report['agreement']['kappa'], 10 / 17)
            self.assertEqual(report['repeatability']['comparablePairs'], 1)
            self.assertEqual(report['repeatability']['retryAttemptsExcluded'], 1)
            attempts = {row['id']: row for row in state['attempts']}
            self.assertEqual(attempts['attempt-10']['admission']['status'], 'engineering_ready')
            self.assertIn('prompt_not_matched', attempts['attempt-05']['admission']['reasons'])
            self.assertIn('household_unknown', attempts['attempt-09']['admission']['reasons'])
            self.assertEqual(state['splitDiagnostics']['joint']['componentCount'], 1)
            self.assertEqual(state['splitDiagnostics']['joint']['threeWayIsolation'], 'infeasible')
            for flag in ('learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible', 'qualifiedReviewEstablished', 'meaningfulImprovementEstablished'):
                self.assertFalse(report['flags'][flag])
            self.assertTrue(verify_export(store.export_bundle())['verified'])

    def test_withdrawal_keeps_denominators_and_originals_but_blocks_current_use(self):
        with tempfile.TemporaryDirectory() as directory:
            store = exercise(Path(directory) / 'project')
            before = store.export_bundle()
            store.withdraw('person-a', 'Invented withdrawal after review.')
            after = Store.open(store.path).export_bundle()
            self.assertEqual(after['aggregate']['manifest'], before['aggregate']['manifest'])
            self.assertEqual(after['aggregate']['reviews'], before['aggregate']['reviews'])
            self.assertEqual(after['report']['denominators']['attempts'], 11)
            self.assertEqual(after['report']['denominators']['engineeringReady'], 1)
            self.assertEqual(after['report']['agreement'], before['report']['agreement'])
            self.assertFalse(store.snapshot('reviewer-a')['items'][0]['recordingAvailable'])
            self.assertIn('current_withdrawal', after['report']['admissionByAttemptId']['attempt-01']['currentRestrictions'])
            self.assertEqual(after['report']['repeatability']['comparablePairs'], 0)
            self.assertTrue(verify_export(after)['verified'])


if __name__ == '__main__':
    unittest.main()
