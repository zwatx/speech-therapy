import unittest
import numpy as np
import vote_error_states as s


class StateTests(unittest.TestCase):
    def test_exhaustive_states_and_lowest_class_tie(self):
        counts = [[5, 0, 0], [0, 5, 0], [1, 0, 4], [0, 0, 5]]
        logs = np.log([[.6, .2, .2], [.4, .4, .2], [.1, .1, .8], [.1, .2, .7]])
        labels, mode, observed, terms = s.states(counts, logs)
        self.assertEqual(labels.tolist(), [0, 1, 2, 0])
        self.assertEqual(mode.tolist(), [0, 0, 2, 2])

    def test_empty_states_and_unanimous_confusion(self):
        rows = [dict(raterCounts=[0, 0, 5], speakerId='a', clipId='x')]
        value = s.partition(rows, np.log([[.1, .2, .7]]))
        empty = value['states']['unanimousDisagree']
        self.assertEqual(empty['support']['positions'], 0)
        self.assertTrue(all(v is None for v in empty['means'].values()))
        self.assertTrue(all(v == 0 for v in empty['totals'].values()))
        self.assertIsNone(empty['nllShare'])
        self.assertEqual(value['unanimousClassByMode'], [[0, 0, 0], [0, 0, 0], [0, 0, 1]])

    def test_mixed_state_never_uses_observed_class_probability(self):
        rows = [dict(raterCounts=[1, 1, 3], speakerId='a', clipId='x')]
        value = s.partition(rows, np.log([[.2, .2, .6]]))
        self.assertIsNone(value['states']['mixed']['meanUnanimousClassProbability'])
        self.assertEqual(value['states']['mixed']['support']['votes'], [1, 1, 3])

    def test_all_states_recombine_parent_loss(self):
        rows = [dict(raterCounts=c, speakerId='a', clipId=str(i)) for i,c in enumerate([[5, 0, 0], [0, 5, 0], [1, 1, 3]])]
        logs = np.log([[.7, .2, .1], [.6, .3, .1], [.2, .2, .6]])
        value = s.partition(rows, logs)
        for key in s.METRICS:
            self.assertAlmostEqual(sum(v['totals'][key] for v in value['states'].values()), s.h.terms([r['raterCounts'] for r in rows], logs)[key].sum())
        self.assertEqual(sum(v['nllShare'] or 0 for v in value['states'].values()), 1)

    def test_invalid_logs_and_votes_rejected(self):
        for counts, logs in [([[0, 0, 4]], [[-1, -1, -1]]), ([[0, 0, 5]], [[0, 0, 0]])]:
            with self.assertRaises(ValueError):s.states(counts, logs)


if __name__ == '__main__':
    unittest.main()
