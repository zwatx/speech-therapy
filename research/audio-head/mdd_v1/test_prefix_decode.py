"""Independent alignment enumeration checks; no model or data access."""
import itertools
import math
import unittest

from .prefix_decode import greedy_decode, prefix_beam_decode, sequence_log_probability


def logs(rows):
    return [[math.log(p) if p else -math.inf for p in row] for row in rows]


def enumerated(rows, blank):
    masses = {}
    width = len(rows[0]) if rows else 1
    for path in itertools.product(range(width), repeat=len(rows)):
        probability = math.prod(rows[t][token] for t, token in enumerate(path))
        # Group adjacent equal alignment tokens, then remove blank groups.
        tokens = tuple(token for token, _ in itertools.groupby(path) if token != blank)
        if probability:
            masses[tokens] = masses.get(tokens, 0.0) + probability
    return masses


class PrefixDecodeTests(unittest.TestCase):
    def test_exhaustive_small_vocabularies_and_all_intermediate_frames(self):
        for width in (2, 3):
            for blank in range(width):
                for frames in range(5):
                    rows = []
                    for frame in range(frames):
                        weights = [1 + ((frame + 2) * (token + 1)) % 7 for token in range(width)]
                        rows.append([w / sum(weights) for w in weights])
                    with self.subTest(width=width, blank=blank, frames=frames):
                        expected = enumerated(rows, blank)
                        actual = {h.tokens: math.exp(h.log_probability) for h in
                                  prefix_beam_decode(logs(rows), blank_id=blank, beam_width=256)}
                        self.assertEqual(actual.keys(), expected.keys())
                        for tokens in expected:
                            self.assertAlmostEqual(actual[tokens], expected[tokens], places=13)
                        self.assertAlmostEqual(sum(actual.values()), 1.0, places=13)

    def test_repeat_requires_intervening_blank(self):
        for rows, expected in [([[0, 1], [0, 1]], (1,)),
                               ([[0, 1], [1, 0], [0, 1]], (1, 1)),
                               ([[1, 0]] * 4, ())]:
            result = prefix_beam_decode(logs(rows), blank_id=0)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].tokens, expected)
            self.assertEqual(result[0].log_probability, 0)
            self.assertEqual(greedy_decode(logs(rows), blank_id=0), expected)

    def test_sequence_winner_can_differ_from_greedy(self):
        rows = [[0.6, 0.4], [0.6, 0.4]]
        self.assertEqual(greedy_decode(logs(rows), blank_id=0), ())
        best = prefix_beam_decode(logs(rows), blank_id=0)[0]
        self.assertEqual(best.tokens, (1,))
        self.assertAlmostEqual(math.exp(best.log_probability), 0.64)

    def test_ties_and_native_ids(self):
        result = prefix_beam_decode(logs([[0.5, 0.5, 0]]), blank_id=2)
        self.assertEqual([h.tokens for h in result], [(0,), (1,)])
        self.assertEqual(greedy_decode(logs([[0.5, 0.5, 0]]), blank_id=2), (0,))
        self.assertEqual([h.tokens for h in prefix_beam_decode(logs([[0.5, 0.5]]), blank_id=0)],
                         [(), (1,)])

    def test_pruned_mass_is_a_lower_bound_and_is_not_renormalized(self):
        rows = [[0.4, 0.35, 0.25], [0.2, 0.5, 0.3], [0.4, 0.1, 0.5]]
        exact = enumerated(rows, 0)
        result = prefix_beam_decode(logs(rows), blank_id=0, beam_width=2)
        self.assertEqual(len(result), 2)
        self.assertLess(sum(math.exp(h.log_probability) for h in result), 1)
        for hypothesis in result:
            self.assertLessEqual(math.exp(hypothesis.log_probability), exact[hypothesis.tokens] + 1e-15)

    def test_empty(self):
        result = prefix_beam_decode([], blank_id=0)
        self.assertEqual([(h.tokens, h.log_probability) for h in result], [((), 0)])
        self.assertEqual(greedy_decode([], blank_id=0), ())

    def test_array_shape_contract_without_array_dependency(self):
        class Matrix(list):
            pass

        matrix = Matrix([])
        matrix.shape = (0, 3)
        self.assertEqual(prefix_beam_decode(matrix, blank_id=2)[0].tokens, ())
        with self.assertRaises(ValueError):
            prefix_beam_decode(matrix, blank_id=3)
        for shape in ((0, 0), (3,), (1, 1, 1)):
            matrix.shape = shape
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                prefix_beam_decode(matrix, blank_id=0)

    def test_invalid_inputs(self):
        cases = [([[]], {}), ([[0], [0, 0]], {}), ([0, 1], {}),
                 ([[math.nan, 0]], {}), ([[math.inf, 0]], {}),
                 ([[-math.inf, -math.inf]], {}), ([[0, 0]], {}),
                 ([[0]], {'blank_id': 1}), ([], {'blank_id': -1}),
                 ([], {'blank_id': True}), ([], {'blank_id': 0.5}),
                 ([], {'beam_width': 0}), ([], {'beam_width': -1}),
                 ([], {'beam_width': True}), ([], {'beam_width': 1.5}),
                 ([], {'normalization_tolerance': -1}),
                 ([], {'normalization_tolerance': math.nan}),
                 ([], {'normalization_tolerance': math.inf})]
        for matrix, kwargs in cases:
            with self.subTest(matrix=matrix, kwargs=kwargs), self.assertRaises(ValueError):
                prefix_beam_decode(matrix, **({'blank_id': 0} | kwargs))

    def test_normalization_tolerance_is_explicit(self):
        prefix_beam_decode([[0.0001]], blank_id=0, normalization_tolerance=0.001)
        with self.assertRaises(ValueError):
            prefix_beam_decode([[0.0001]], blank_id=0, normalization_tolerance=0.00001)


class SequenceProbabilityTests(unittest.TestCase):
    def test_every_tiny_alignment_against_enumeration(self):
        for width in (2, 3):
            for blank in range(width):
                for frames in range(5):
                    rows = []
                    for frame in range(frames):
                        weights = [1 + (frame + token * 3) % 5 for token in range(width)]
                        rows.append([value / sum(weights) for value in weights])
                    expected = enumerated(rows, blank)
                    # Check all target strings up to T, including impossible
                    # repeats, rather than only those seen by the decoder.
                    vocabulary = [token for token in range(width) if token != blank]
                    for length in range(frames + 1):
                        for target in itertools.product(vocabulary, repeat=length):
                            with self.subTest(width=width, blank=blank, frames=frames, target=target):
                                actual = sequence_log_probability(logs(rows), target, blank_id=blank)
                                probability = expected.get(target, 0)
                                if probability:
                                    self.assertAlmostEqual(actual, math.log(probability), places=13)
                                else:
                                    self.assertEqual(actual, -math.inf)

    def test_empty_repeat_and_zero_probability_alignments(self):
        cases = [([], (), 0.0), ([], (1,), -math.inf),
                 ([[0.2, 0.8], [0.3, 0.7]], (), math.log(0.06)),
                 ([[0, 1], [0, 1]], (1, 1), -math.inf),
                 ([[0, 1], [1, 0], [0, 1]], (1, 1), 0.0),
                 ([[1, 0]], (1,), -math.inf), ([[0, 1]], (), -math.inf),
                 ([[1, 0]], (1, 1), -math.inf)]
        for rows, target, expected in cases:
            with self.subTest(rows=rows, target=target):
                self.assertAlmostEqual(sequence_log_probability(logs(rows), target, blank_id=0), expected)

    def test_invalid_targets_and_matrix_validation(self):
        for target in ((-1,), (0,), (2,), (True,), (1.0,), ('1',), None, 1):
            with self.subTest(target=target), self.assertRaises(ValueError):
                sequence_log_probability([[0, -math.inf]], target, blank_id=0)
        with self.assertRaises(ValueError):
            sequence_log_probability([[0, 0]], (), blank_id=0)
        with self.assertRaises(ValueError):
            sequence_log_probability([[0.001]], (), blank_id=0)
        self.assertEqual(sequence_log_probability([[0.001]], (), blank_id=0,
                                                 normalization_tolerance=0.01), 0.001)

        class EmptyMatrix(list):
            shape = (0, 2)

        self.assertEqual(sequence_log_probability(EmptyMatrix(), (1,), blank_id=0), -math.inf)
        with self.assertRaises(ValueError):
            sequence_log_probability(EmptyMatrix(), (2,), blank_id=0)

    def test_exact_score_bounds_every_finite_beam_score(self):
        matrix = logs([[0.4, 0.35, 0.25], [0.2, 0.5, 0.3], [0.4, 0.1, 0.5]])
        strictly_truncated = False
        for beam_width in (1, 2, 4):
            for hypothesis in prefix_beam_decode(matrix, blank_id=0, beam_width=beam_width):
                exact = sequence_log_probability(matrix, hypothesis.tokens, blank_id=0)
                self.assertLessEqual(hypothesis.log_probability, exact + 1e-14)
                strictly_truncated |= hypothesis.log_probability < exact - 1e-10
        self.assertTrue(strictly_truncated)


if __name__ == '__main__':
    unittest.main()
