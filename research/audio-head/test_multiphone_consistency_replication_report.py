from copy import deepcopy
import unittest

import numpy as np

import multiphone_consistency_replication_report as report
from test_multiphone_consistency_report import example


def thirty():
    rows, warm, noise, initial = example()
    result = []
    for fold in range(5):
        for original_arm in initial:
            arm = deepcopy(original_arm)
            arm['fold'] = fold
            c = arm['coefficient']
            clean = (1 - c * .01) * warm + c * .01 / 3
            changed = (1 - c * .2) * noise + c * .2 * clean
            arm['profiles'] = report.profiles(clean, changed, rows)
            arm['original']['profiles'] = report.profiles(warm, noise, rows)
            result.append(arm)
    return result


class ReplicationReportTests(unittest.TestCase):
    def test_thirty_arms_and_six_equal_fold_summaries_keep_controls(self):
        value = report.summarize(thirty())
        self.assertEqual(len(value['arms']), 30)
        self.assertEqual(len(value['descriptiveSummaries']), 6)
        self.assertFalse(value['coefficientSelected'])
        self.assertFalse(value['independentFoldConfidenceIntervalsComputed'])
        for item in value['descriptiveSummaries']:
            metric = item['ages']['ages6to12']['cleanMacroNLL']
            self.assertEqual(len(metric['selected']['perFold']), 5)
            if item['coefficient'] == 0:
                self.assertEqual(metric['differenceVsCoefficientZero']['perFold'], [0.] * 5)
        improvement = value['descriptiveSummaries'][2]['ages']['ages6to12']['meanNoiseTotalVariation']
        self.assertEqual(improvement['differenceVsCoefficientZero']['directionCounts'], {'lower': 5, 'equal': 0, 'higher': 0})

    def test_equal_fold_mean_is_not_row_weighted(self):
        arms = thirty()
        # Each fold's support remains internally paired, but fold-level scores
        # deliberately vary; aggregation must not repeat a large fold's weight.
        for arm in arms:
            if arm['coefficient'] == 1.:
                arm['cleanMetrics']['ages6to12']['macroTargetLogLoss'] = 1. + arm['fold']
        value = report.summarize(arms)
        metric = value['descriptiveSummaries'][2]['ages']['ages6to12']['cleanMacroNLL']['selected']
        self.assertEqual(metric['perFold'], [1., 2., 3., 4., 5.])
        self.assertEqual(metric['equalFoldMean'], 3.)

    def test_missing_reordered_or_duplicate_fold_fails(self):
        original = thirty()
        for arms in (original[:-1], list(reversed(original)), original[:24] + original[:6]):
            with self.assertRaisesRegex(ValueError, '30|original six'):
                report.summarize(arms)

    def test_wrong_original_or_paired_support_fails(self):
        arms = thirty()
        arms[1]['original']['profiles']['ages6to12']['clean']['meanEntropy'] += .1
        with self.assertRaisesRegex(ValueError, 'original differs'):
            report.summarize(arms)
        arms = thirty()
        arms[1]['cleanMetrics']['ages6to12']['speakers'] += 1
        with self.assertRaisesRegex(ValueError, 'support differs'):
            report.summarize(arms)

    def test_undefined_fold_not_silently_dropped(self):
        result = report.describe([.5, None, .3, .4, .2])
        self.assertIsNone(result['equalFoldMean'])
        self.assertEqual(result['undefinedFolds'], [1])
        delta = report.signed_difference([.5, None, .3, .4, .2], [.4] * 5)
        self.assertIsNone(delta['equalFoldMean'])
        self.assertEqual(delta['directionCounts'], {'lower': 2, 'equal': 1, 'higher': 1})
        for values in ([1, 2, 3, 4], [1, 2, float('nan'), 4, 5]):
            with self.assertRaises(ValueError):
                report.describe(values)

    def test_overlapping_memberships_deduplicate_children_and_target_rows(self):
        rows = [dict(age=age, speakerId=speaker, clipId=f'clip-{i}', targetPhone='B', raterCounts=[0, 0, 5])
                for i, (age, speaker) in enumerate([(6, 'a'), (6, 'a'), (8, 'b'), (20, 'c')])]
        indices = [[0, 1, 3], [0, 2, 3], [1, 2, 3], [0, 1, 3], [0, 2, 3]]
        splits = {'authorPartition': 'train', 'folds': [{'innerValidationRows': x} for x in indices]}
        result = report.memberships({'authorPartition': 'train', 'rows': rows}, splits)
        child = result['ages6to12']
        self.assertEqual(child['deduplicated'], {'targets': 3, 'clips': 3, 'speakers': 2, 'raterCounts': [0, 0, 15]})
        self.assertEqual(child['foldMembershipSums'], {'targets': 10, 'clips': 10, 'speakers': 8})
        self.assertEqual(child['speakerFoldMembershipHistogram'], {3: 1, 5: 1})
        self.assertFalse(child['independentFolds'])

    def test_same_argmax_does_not_hide_probability_confidence_changes(self):
        clean = np.array([[.01, .01, .98], [.02, .03, .95]])
        noisy = np.array([[.1, .2, .7], [.15, .1, .75]])
        rows = [{'age': 6}, {'age': 8}]
        value = report.profiles(clean, noisy, rows)['ages6to12']
        self.assertEqual(value['clean']['argmaxCounts'], [0, 0, 2])
        self.assertEqual(value['noisy']['argmaxCounts'], [0, 0, 2])
        self.assertGreater(value['clean']['meanClassProbabilities'][2], value['noisy']['meanClassProbabilities'][2])
        self.assertLess(value['clean']['meanEntropy'], value['noisy']['meanEntropy'])


if __name__ == '__main__':
    unittest.main()
