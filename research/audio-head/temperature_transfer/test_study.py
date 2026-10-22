"""Identity, leakage, freeze ordering and vocabulary regression checks."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from temperature_transfer import study as s


class TransferTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(speakerId=k, age=8, trainingEligible=True, targetWord=w)
                for k, w in [('fit', 'BE'), ('validation', 'SAY'), ('outer', 'BE'), ('outer', 'SAY')]]
        job = dict(regime='child-only', fold=0, checkpoint={'path': 'best.pt', 'sha256': 'a'},
                   correction={'path': 'fit.json', 'sha256': 'b'}, predictions={'path': 'inner.json', 'sha256': 'c'},
                   fitRows=[0], validationRows=[1], outerRows=[2, 3])
        value = dict(regime=job['regime'], fold=0, checkpoint=job['checkpoint'], correction=job['correction'],
                     rowIndices=[2, 3], probabilities=[[.1, .2, .7], [.2, .3, .5]], seenInFitVocabulary=[True, False],
                     innerReplay=dict(exact=True, rows=[1], checkpoint=job['checkpoint'], predictions=job['predictions']),
                     headInferencePerformed=True, **s.FLAGS)
        return job, value, rows

    def test_only_actual_inner_fit_words_are_seen(self):
        job, value, rows = self.fixture()
        _, seen = s.validate_prediction(job, value, rows)
        np.testing.assert_array_equal(seen, [True, False])
        value['seenInFitVocabulary'] = [True, True]
        with self.assertRaisesRegex(ValueError, 'vocabulary'):
            s.validate_prediction(job, value, rows)

    def test_wrong_checkpoint_correction_order_shape_and_replay_rejected(self):
        for key, value in [('checkpoint', {}), ('correction', {}), ('rowIndices', [3, 2]),
                           ('probabilities', [[.1, .2, .7]]), ('innerReplay', {})]:
            job, pred, rows = self.fixture(); pred[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.validate_prediction(job, pred, rows)

    def test_speaker_overlap_and_duplicate_rows_rejected(self):
        job, value, rows = self.fixture(); rows[3]['speakerId'] = 'validation'
        with self.assertRaisesRegex(ValueError, 'speakers overlap'):
            s.validate_prediction(job, value, rows)
        job, value, rows = self.fixture(); value['rowIndices'] = job['outerRows'] = [2, 2]
        with self.assertRaisesRegex(ValueError, 'duplicate partition'):
            s.validate_prediction(job, value, rows)

    def test_no_partial_freeze_or_report_on_failed_inference(self):
        job, value, rows = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plan.json'
            plan = dict(jobs=[job, job], inputs={})
            with patch.object(s, 'load_plan', return_value=(plan, {'path': str(path), 'sha256': 'x'})), \
                 patch.object(s, 'infer', side_effect=[value, ValueError('second head failed')]):
                with self.assertRaisesRegex(ValueError, 'second head failed'):
                    s.run(path, 'x')
            self.assertTrue((path.parent / 'failure.json').exists())
            self.assertFalse((path.parent / 'freeze.json').exists())
            self.assertFalse((path.parent / 'report.json').exists())
            self.assertTrue((path.parent / 'outer-child-only-f0.json').exists())

    def test_foreign_or_missing_inference_freeze_stops_before_metrics(self):
        frozen = dict(complete=True, plan={}, predictions=[{}]*9, innerReplayCount=10,
                      outerInferenceCount=10, headInferencePerformed=True, **s.FLAGS)
        with patch.object(s.files, 'binding', return_value={}), patch.object(s, 'read', return_value=frozen), \
             patch.object(s.prior, 'summarize') as summarize:
            with self.assertRaisesRegex(ValueError, 'freeze differs'):
                s.calculate(dict(jobs=[{}]*10), {}, Path('freeze'), 'x')
            summarize.assert_not_called()

    def test_arm_comparison_rejects_different_outer_row_or_fold_identity(self):
        a = dict(rowIndices=[1, 2], rowFolds=[0, 1])
        for key, value in [('rowIndices', [2, 1]), ('rowFolds', [1, 0])]:
            b = copy.deepcopy(a); b[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'alignment differs'):
                s.arm_comparison(a, b)

    def test_corrected_summary_preserves_extreme_unclipped_nll(self):
        row = dict(age=8, raterCounts=[0, 0, 5], targetPhone='B', targetWord='BE', speakerId='c', clipId='x')
        result = s.summary(np.array([[.99, .009, .001]]), [row], [False], 20)
        self.assertGreater(result['corrected']['measures']['allWords']['metrics']['ages6to12']['perRaterLogLoss'], 100)
        self.assertEqual(set(result['corrected']['measures']['unseenWords']['support']['ages6to12']['perPhone']), set(s.metrics.PHONES))


if __name__ == '__main__':
    unittest.main()
