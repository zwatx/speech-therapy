"""Calibration membership, frozen-evaluation ordering and decision regressions."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
from rating_temperature import study as s


class StudyTests(unittest.TestCase):
    def fixture(self, regime='all-age'):
        rows = []
        for speaker, age in [('fit-child', 8), ('fit-adult', 30), ('valid-child', 9), ('valid-adult', 31), ('outer-child', 10), ('outer-adult', 32)]:
            rows.extend(dict(speakerId=speaker, age=age, trainingEligible=True, targetPhone=p) for p in s.metrics.PHONES)
        partition = dict(innerFitRows=list(range(46)), innerValidationRows=list(range(46, 92)), outerHoldoutRows=list(range(92, 138)))
        cfg = dict(fold=0, regime=regime, fitRows=list(range(46 if regime == 'all-age' else 23)), validationRows=list(range(46, 92)), selectionRows=list(range(46, 92 if regime == 'all-age' else 69)))
        return cfg, {'rows': rows}, {'folds': [partition]}

    def test_both_regimes_calibrate_only_on_same_unseen_children(self):
        for regime in s.REGIMES:
            cfg, cohort, splits = self.fixture(regime)
            fit, validation, selected = s.checked_membership(cfg, cohort, splits)
            self.assertEqual(selected, list(range(46, 69)))
            self.assertEqual(validation, list(range(46, 92)))
            self.assertEqual(len(fit), 46 if regime == 'all-age' else 23)

    def test_wrong_fold_boolean_and_rows_rejected(self):
        for key, value in [('fold', True), ('regime', 'other'), ('selectionRows', [46]), ('validationRows', [46])]:
            cfg, cohort, splits = self.fixture(); cfg[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.checked_membership(cfg, cohort, splits)

    def test_speaker_overlap_and_missing_phone_fail(self):
        cfg, cohort, splits = self.fixture(); cohort['rows'][92]['speakerId'] = 'valid-child'
        with self.assertRaisesRegex(ValueError, 'speakers overlap'):
            s.checked_membership(cfg, cohort, splits)
        cfg, cohort, splits = self.fixture(); cohort['rows'][46]['targetPhone'] = cohort['rows'][47]['targetPhone']
        with self.assertRaisesRegex(ValueError, 'phone coverage'):
            s.checked_membership(cfg, cohort, splits)

    def test_no_outer_payload_read_without_verified_freeze(self):
        with patch.object(s, 'check_freeze', side_effect=ValueError('freeze mismatch')), patch.object(s.loader, 'load_predictions') as loader:
            with self.assertRaisesRegex(ValueError, 'freeze mismatch'):
                s.outer_calculation({}, {}, None, 'bad')
            loader.assert_not_called()

    def summary(self, nll=.2, macro=.21, brier=.1, rating0=.3, below2=.4):
        return {'measures': {'allWords': {'metrics': {'ages6to12': {'perRaterLogLoss': nll, 'macroTargetLogLoss': macro, 'perRaterBrier': brier, 'discrimination': {'rating0': {'averagePrecision': rating0}, 'ratingBelow2': {'averagePrecision': below2}}}}}}}

    def test_gain_screen_preserves_ranking_and_every_fold(self):
        base = self.summary(); better = self.summary(nll=.19, macro=.20, brier=.09)
        folds = [{'normalized': base, 'corrected': better} for _ in range(5)]
        self.assertTrue(s.screen(base, better, folds)['consistentDevelopmentGain'])
        worse_fold = copy.deepcopy(folds); worse_fold[2]['corrected'] = self.summary(nll=.2001)
        self.assertFalse(s.screen(base, better, worse_fold)['checks']['everyFoldNLLNoWorse'])
        self.assertFalse(s.screen(base, self.summary(nll=.19, macro=.20, brier=.09, below2=.3999), folds)['consistentDevelopmentGain'])
        self.assertFalse(s.screen(base, base, folds)['checks']['pooledNLLImproves'])
        with self.assertRaisesRegex(ValueError, 'five'):
            s.screen(base, better, folds[:4])

    def test_stable_nll_replaces_legacy_floor_in_all_nested_slices(self):
        raw = np.array([[.99, .009, .001]])
        p = s.core.scaled(raw, 20)
        logs = s.core.log_scaled(raw, 20)
        row = dict(age=8, raterCounts=[0, 0, 5], targetPhone='B', targetWord='BE',
                   speakerId='child', clipId='clip')
        result = s.summarize(p, [row], np.array([False]), logs)
        expected = -logs[0, 2]
        self.assertGreater(expected, 100)
        for word in ('allWords', 'unseenWords'):
            for age in ('allAges', 'ages6to12'):
                value = result['measures'][word]['metrics'][age]
                self.assertAlmostEqual(value['perRaterLogLoss'], expected)
                self.assertAlmostEqual(value['macroTargetLogLoss'], expected)
                self.assertAlmostEqual(value['perTarget']['B']['perRaterLogLoss'], expected)
                for disc in (value['discrimination'], value['targetDiscrimination']['perPhone']['B']):
                    self.assertAlmostEqual(disc['perRaterLogLoss'], expected)
                    self.assertAlmostEqual(disc['classes']['2']['conditionalNLL'], expected)
                    self.assertIsNone(disc['classes']['0']['conditionalNLL'])
        self.assertIsNone(result['measures']['seenWords']['metrics']['allAges'])
        self.assertIsNone(result['measures']['allWords']['metrics']['ages13plus'])


if __name__ == '__main__': unittest.main()
