import math
import unittest

import numpy as np

import vote_headroom as h


class HeadroomTests(unittest.TestCase):
    def test_unanimous_and_mixed_exact_decompositions(self):
        counts = [[0, 0, 5], [1, 2, 2]]
        values = h.terms(counts, np.log([[.1, .2, .7], [.2, .3, .5]]))
        self.assertEqual(values['empiricalEntropy'][0], 0)
        self.assertAlmostEqual(values['empiricalEntropy'][1], -(.2*math.log(.2)+.8*math.log(.4)))
        self.assertEqual(values['empiricalBrierFloor'][0], 0)
        np.testing.assert_allclose(values['nll'], values['empiricalEntropy']+values['nllExcess'], rtol=0, atol=1e-12)
        np.testing.assert_allclose(values['brier'], values['empiricalBrierFloor']+values['brierExcess'], rtol=0, atol=1e-12)

    def test_matching_empirical_distribution_has_zero_gap(self):
        value = h.terms([[1, 1, 3]], np.log([[.2, .2, .6]]))
        self.assertEqual(value['nllExcess'][0], 0)
        self.assertEqual(value['brierExcess'][0], 0)

    def test_extreme_finite_logs_preserved_without_clipping(self):
        value = h.terms([[1, 0, 4]], [[-1000, -1000, 0]])
        self.assertEqual(value['nll'][0], 200)
        self.assertTrue(np.isfinite(value['nllExcess'][0]))

    def test_invalid_votes_and_probabilities_rejected(self):
        for counts, logs in [([[0, 0, 4]], [[-1, -1, -1]]), ([[.5, .5, 4]], [[-1, -1, -1]]),
                             ([[-1, 1, 5]], [[-1, -1, -1]]), ([[0, 0, 5]], [[0, 0, 0]]),
                             ([[0, 0, 5]], [[float('nan'), -1, -1]])]:
            with self.subTest(counts=counts, logs=logs), self.assertRaises(ValueError):
                h.terms(counts, logs)

    def test_repeated_child_support_and_mixed_count(self):
        rows = [dict(raterCounts=[0, 0, 5], speakerId='a', clipId='x'),
                dict(raterCounts=[1, 1, 3], speakerId='a', clipId='y')]
        value = h.view(rows, np.log([[.1, .1, .8], [.2, .2, .6]]))
        self.assertEqual(value['support'], dict(positions=2, recordings=2, children=1, votes=[1, 1, 8], unanimousPositions=1, mixedVotePositions=1))

    def test_late_payload_mutation_guard(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'payload';path.write_text('original')
            plan = dict(inputs=dict(payload=h.binding(path)), sources={})
            path.write_text('mutated')
            with self.assertRaises(ValueError):h.guards(plan)


if __name__ == '__main__':
    unittest.main()
