"""Synthetic paired-reference, population, and across-seed aggregation checks."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from lexical_expanded_heads.test_evaluation import fixture
from lexical_seed_replication import analysis as a


def small_summary(prediction, rows):
    # Only pooled/fold NLL is needed for pairing/response reconciliation. The unchanged
    # complete metric implementation is separately verified; avoid its reliability bins here.
    nll = float(-(np.asarray([r['raterCounts'] for r in rows]) * np.asarray(prediction['logProbabilities'])).sum() / (5 * len(rows))) if rows else 0.
    metrics = dict(perRaterLogLoss=nll, macroTargetLogLoss=nll, perRaterBrier=.5,
                   discrimination=dict(rating0=dict(averagePrecision=.2), ratingBelow2=dict(averagePrecision=.4)))
    return dict(measures=dict(allWords=dict(metrics=dict(ages6to12=metrics))))


def values():
    rows, original, jobs, records, _ = fixture()
    changed = copy.deepcopy(records)
    for record in changed.values():
        prediction = record['prediction']
        probabilities = np.tile([.18, .25, .57], (len(prediction['rowIndices']), 1))
        prediction.update(probabilities=probabilities.tolist(), logProbabilities=np.log(probabilities).tolist(),
                          rawProbabilities=probabilities.astype(np.float32).tolist())
        prediction['NLL'] = a.e.mixture.mixture(prediction, prediction, [rows[i] for i in prediction['rowIndices']])['NLL']
    with patch.object(a.e, 'summarize', side_effect=small_summary):
        models = {objective: a.models(rows, original, jobs, source)
                  for objective, source in zip(a.OBJECTIVES, (records, changed), strict=True)}
    corrected = {regime: copy.deepcopy(models['unweighted'][regime]['equal-mixture']['original']) for regime in a.e.REGIMES}
    return rows, original, jobs, records, models, corrected


class AnalysisTests(unittest.TestCase):
    def test_both_populations_and_fixed_mixtures_preserve_original_index_gaps(self):
        rows, original, jobs, records, models, corrected = values()
        view = models['unweighted']['all-age']['scalars']
        self.assertEqual(view['original']['rowIndices'], list(range(1, 50, 2)))
        self.assertEqual(view['added']['rowIndices'], [25])
        self.assertEqual(view['all']['rowIndices'], list(range(26)))
        for objective in a.OBJECTIVES:
            families = models[objective]['all-age']
            for left, right, mixture in zip(families['scalars']['original']['probabilities'],
                    families['pca16-scalars']['original']['probabilities'], families['equal-mixture']['original']['probabilities'], strict=True):
                np.testing.assert_allclose(mixture, (np.asarray(left) + right) / 2, rtol=1e-14, atol=0)
        result = a.paired(models, corrected, original)
        self.assertEqual(len(result['childLossResponses']), 10)
        for regime in a.e.REGIMES:
            comparisons = result['comparisons'][regime]
            self.assertEqual(set(comparisons['primary']), set(a.NEURAL))
            self.assertEqual(set(comparisons['secondaryVsCorrectedSeed7']), set(a.OBJECTIVES))
            for family in a.NEURAL:
                expected = models['unit-weighted'][regime][family]['original']['pooled']['measures']['allWords']['metrics']['ages6to12']['perRaterLogLoss'] - models['unweighted'][regime][family]['original']['pooled']['measures']['allWords']['metrics']['ages6to12']['perRaterLogLoss']
                self.assertEqual(comparisons['primary'][family]['childDelta']['NLL'], expected)
            for objective in a.OBJECTIVES:
                response = result['childLossResponses'][regime + '/secondary/' + objective]
                self.assertAlmostEqual(response['pooled']['meanNLLDelta'], comparisons['secondaryVsCorrectedSeed7'][objective]['childDelta']['NLL'])
                self.assertEqual(len(response['perPhone']), 23)

    def test_pairing_rejects_wrong_reference_and_incomplete_job_matrix(self):
        rows, original, jobs, records, models, corrected = values()
        wrong = copy.deepcopy(corrected)
        wrong['all-age']['rowIndices'].reverse()
        with self.assertRaises(ValueError):
            a.paired(models, wrong, original)
        wrong_models = copy.deepcopy(models)
        wrong_models['unit-weighted']['child-only']['scalars']['original']['rowFolds'].reverse()
        with self.assertRaises(ValueError):
            a.paired(wrong_models, corrected, original)
        with self.assertRaises(ValueError):
            a.models(rows, original, jobs[:-1], records)

    def test_three_seed_ranges_keep_failures_and_reject_missing_seed_or_changed_support(self):
        _, original, _, _, models, corrected = values()
        paired = a.paired(models, corrected, original)
        results = []
        for seed, value in zip(a.SEEDS, (-.2, .1, .4), strict=True):
            one = dict(seed=seed, childLossResponses=copy.deepcopy(paired['childLossResponses']))
            for response in one['childLossResponses'].values():
                response['consistencyDecision']['childDelta']['NLL'] = value
                response['consistencyDecision']['consistentDevelopmentGain'] = seed == 17
                for phone in response['perPhone'].values():
                    phone['meanNLLDelta'] = value
            results.append(one)
        summary = a.across_seeds(results)
        self.assertEqual(summary['seeds'], [17, 29, 43])
        self.assertFalse(summary['seed7Included'])
        self.assertFalse(summary['seedSelectionPerformed'])
        for contrast in summary['contrasts'].values():
            self.assertFalse(contrast['everySeedPasses'])
            self.assertEqual(contrast['pooledDelta']['NLL']['minimum'], -.2)
            self.assertEqual(contrast['pooledDelta']['NLL']['maximum'], .4)
            self.assertAlmostEqual(contrast['pooledDelta']['NLL']['mean'], .1)
            self.assertEqual(set(contrast['perSeedDecisions']), {'17', '29', '43'})
            self.assertEqual(len(contrast['perPhone']), 23)
        for mutated in (results[:2], [results[0], results[0], results[2]], list(reversed(results))):
            with self.assertRaises(ValueError):
                a.across_seeds(mutated)
        changed = copy.deepcopy(results)
        changed[1]['childLossResponses']['all-age/primary/scalars']['perPhone']['B']['support']['positions'] += 1
        with self.assertRaises(ValueError):
            a.across_seeds(changed)
        self.assertIsNone(a.describe([None, None, None]))
        with self.assertRaises(ValueError):
            a.describe([None, .1, .2])


if __name__ == '__main__':
    unittest.main()
