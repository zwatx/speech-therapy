from copy import deepcopy
import unittest

import numpy as np

import multiphone_ranking_report as report


class RankingReportTests(unittest.TestCase):
    def arms(self, absent_event=False):
        rows = [dict(id=f'row{i}', speakerId=f'child{i}', clipId=f'clip{i}', targetPhone=phone,
                     targetId=target, age=age, raterCounts=[0, 0, 5] if absent_event else counts)
                for i, (phone, target, age, counts) in enumerate([
                    ('B', 0, 8, [1, 1, 3]), ('B', 0, 10, [0, 0, 5]),
                    ('D', 4, 11, [2, 1, 2]), ('D', 4, 20, [1, 0, 4]), ('B', 0, 22, [0, 0, 5])])]
        arms = []
        for fold in range(5):
            arm = {'fold': fold, 'bestEpoch': 0, 'epochsRun': 2,
                   'controlBestEpoch': 0, 'controlEpochsRun': 2}
            for name, value in [('original', .08), ('control', .09), ('selected', .1)]:
                p = np.tile([value + .002 * fold, .1, .9 - value - .002 * fold], (len(rows), 1))
                arm[name] = {'evaluation': report.controls.first_report.score_predictions(p, rows),
                             'confidence': report.confidence(p, rows)}
            arms.append(arm)
        return arms

    def test_retains_five_signed_differences_and_exact_equal_fold_means(self):
        arms = self.arms(); summaries = report.describe(arms)
        self.assertEqual(set(summaries), set(report.AGES))
        cell = summaries['ages6to12']['macroNLL']
        expected = [a['selected']['evaluation']['ages6to12']['macroTargetLogLoss']
                    - a['control']['evaluation']['ages6to12']['macroTargetLogLoss'] for a in arms]
        self.assertEqual(cell['differenceVsControl']['perFold'], expected)
        self.assertEqual(cell['differenceVsControl']['equalFoldMean'], float(np.mean(expected)))
        self.assertEqual(sum(cell['differenceVsControl']['directionCounts'].values()), 5)
        self.assertEqual(summaries['ages6to12']['meanClass2Probability']['differenceVsControl']['directionCounts']['lower'], 5)

    def test_undefined_ranking_is_preserved_without_dropping_folds(self):
        summaries = report.describe(self.arms(absent_event=True))
        for event in ('rating0AUROC', 'rating0AP', 'below2AUROC', 'below2AP'):
            self.assertEqual(summaries['ages6to12'][event]['selected']['perFold'], [None] * 5)
            self.assertIsNone(summaries['ages6to12'][event]['selected']['equalFoldMean'])
            self.assertEqual(summaries['ages6to12'][event]['selected']['undefinedFolds'], list(range(5)))

    def test_population_and_ranking_support_must_match(self):
        arms = self.arms(); arms[0]['control']['evaluation']['ages6to12']['speakers'] += 1
        with self.assertRaisesRegex(ValueError, 'support differs'):
            report.describe(arms)
        arms = self.arms(); arms[0]['control']['evaluation']['ages6to12']['targetDiscrimination']['macroTarget']['rating0']['excludedPhones'] = ['B']
        with self.assertRaisesRegex(ValueError, 'ranking support differs'):
            report.describe(arms)

    def test_fixed_order_and_complete_probabilities_are_required(self):
        arms = self.arms(); arms[0]['fold'] = 1
        with self.assertRaisesRegex(ValueError, 'five ordered'):
            report.describe(arms)
        for invalid in ([[.1, .1, .7]], [[-.1, .2, .9]], [[np.nan, .1, .9]], [[.1, .9]]):
            with self.assertRaises(ValueError):
                report.checked_probabilities(invalid, 1)
        self.assertTrue(np.array_equal(report.checked_probabilities([[.1, .2, .7]], 1), [[.1, .2, .7]]))

    def test_confidence_and_markdown_keep_original_control_and_selected(self):
        arms = self.arms(); cell = arms[0]['selected']['confidence']['ages6to12']
        self.assertEqual(cell['argmaxCounts'], [0, 0, 3])
        self.assertAlmostEqual(cell['meanEntropy'], -sum(p * np.log(p) for p in [.1, .1, .8]))
        value = {'arms': deepcopy(arms), 'descriptiveSummaries': report.describe(arms),
                 'support': {'ages6to12': {'deduplicated': {'speakers': 27, 'targets': 2954},
                                          'foldMembershipSums': {'speakers': 39, 'targets': 4245}}}}
        content = report.markdown(value)
        self.assertIn('27 distinct children in 39 fold memberships', content)
        self.assertIn('Original | NLL continuation | NLL + .1 ranking', content)
        self.assertIn('no independent-fold confidence interval', content)
        self.assertIn('No final research bundle or learner feedback policy is changed', content)


if __name__ == '__main__':
    unittest.main()
