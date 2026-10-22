import unittest

import numpy as np

import multiphone_rating_reliability as subject


def row(counts=(1, 1, 3), speaker='a', clip='x', phone='B'):
    return {'raterCounts': list(counts), 'speakerId': speaker, 'clipId': clip, 'targetPhone': phone}


class ReliabilityTests(unittest.TestCase):
    def test_exact_bin_boundaries_and_one(self):
        values = [i / 10 for i in range(11)]
        result = subject.reliability([[p, 0, 1 - p] for p in values], [row()] * 11, (0,))
        self.assertEqual([b['support']['positions'] for b in result['bins']], [1] * 9 + [2])
        self.assertEqual(result['bins'][-1]['meanPredicted'], .95)
        self.assertTrue(result['bins'][-1]['upperInclusive'])
        self.assertFalse(result['bins'][8]['upperInclusive'])

    def test_mixed_votes_sign_and_repeated_child(self):
        rows = [row((1, 2, 2)), row((0, 1, 4), clip='y')]
        p = [[.1, .2, .7], [.3, .1, .6]]
        result = subject.reliability(p, rows, (0, 1))
        self.assertEqual(result['support']['positions'], 2)
        self.assertEqual(result['support']['speakers'], 1)
        self.assertEqual(result['support']['clips'], 2)
        self.assertEqual(result['support']['positiveVotes'], 4)
        self.assertEqual(result['support']['negativeVotes'], 6)
        self.assertEqual(result['observedVoteFraction'], .4)
        self.assertAlmostEqual(result['meanPredicted'], .35)
        self.assertAlmostEqual(result['predictionMinusObservation'], -.05)
        self.assertAlmostEqual(result['positionWeightedAbsoluteBinnedResidual'], .25)

    def test_empty_bins_and_absent_positive_votes(self):
        result = subject.reliability([[0, 0, 1]], [row((0, 0, 5))], (0,))
        self.assertEqual(result['bins'][0]['observedVoteFraction'], 0)
        self.assertEqual(result['bins'][0]['predictionMinusObservation'], 0)
        for b in result['bins'][1:]:
            self.assertEqual(b['support']['positions'], 0)
            self.assertIsNone(b['meanPredicted'])
            self.assertIsNone(b['observedVoteFraction'])
            self.assertIsNone(b['predictionMinusObservation'])
        empty = subject.reliability(np.empty((0, 3)), [], (0,))
        self.assertIsNone(empty['positionWeightedAbsoluteBinnedResidual'])

    def test_invalid_inputs(self):
        for p in ([[-.1, 0, 1.1]], [[float('nan'), 0, 1]], [[.2, .3, .4]], [[.2, .8]]):
            with self.subTest(p=p), self.assertRaises(ValueError):
                subject.reliability(p, [row()], (0,))
        for counts in ((1., 1, 3), (True, 1, 3), (1, 1, 2), (-1, 1, 5)):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                subject.reliability([[.2, .2, .6]], [row(counts)], (0,))

    def test_pooled_and_equal_phone_weights_and_fold_inventory(self):
        rows = [row((0, 0, 5), phone='B') for _ in range(9)] + [row((5, 0, 0), phone='P')]
        values = np.asarray([[0, 0, 1]] * 10, dtype=float)
        models = {name: values for name in subject.MODELS}
        result = subject.summarize(models, rows, list(range(5)) * 2)
        event = result[subject.MODELS[0]]['rating0']
        self.assertAlmostEqual(event['pooled']['positionWeightedAbsoluteBinnedResidual'], .1)
        self.assertAlmostEqual(event['equalPhoneMeanAbsoluteBinnedResidual'], .5)
        self.assertEqual(set(event['perFold']), set(map(str, range(5))))
        self.assertEqual(set(event['perPhone']), {'B', 'P'})
        self.assertEqual(sum(v['support']['positions'] for v in event['perFold'].values()), 10)
        with self.assertRaises(ValueError):
            subject.summarize(models, rows, [0] * 10)


if __name__ == '__main__':
    unittest.main()
