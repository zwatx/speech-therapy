"""Independent path enumeration and PyTorch CTC oracles for slot likelihoods."""
import itertools
import unittest

import numpy as np
import torch

from multiphone_sequence_ctc import SequenceCTC, summarize_slot


def collapse(path, blank=0):
    return tuple(token for i, token in enumerate(path) if token != blank and (i == 0 or token != path[i-1]))


def enumerate_probabilities(probabilities, blank=0):
    result = {}
    for path in itertools.product(range(probabilities.shape[1]), repeat=len(probabilities)):
        target = collapse(path, blank)
        probability = float(np.prod([probabilities[t, token] for t, token in enumerate(path)]))
        result[target] = result.get(target, 0.) + probability
    return result


def torch_likelihood(logp, target, blank=0):
    return -float(torch.nn.functional.ctc_loss(torch.tensor(logp, dtype=torch.float64)[:, None],
        torch.tensor(target, dtype=torch.long), torch.tensor([len(logp)]), torch.tensor([len(target)]),
        blank=blank, reduction='sum', zero_infinity=False))


class SequenceTests(unittest.TestCase):
    def assert_likelihood(self, actual, expected):
        if expected == -np.inf:
            self.assertEqual(actual, expected)
        else:
            self.assertAlmostEqual(actual, expected, places=10)

    def test_exhaustive_paths_include_repeated_neighbors_and_impossible_sequences(self):
        rng = np.random.default_rng(19)
        for frames in range(1, 6):
            p = rng.uniform(.01, 1., (frames, 3)); p /= p.sum(1, keepdims=True)
            expected = enumerate_probabilities(p)
            for length in range(1, 4):
                for target in itertools.product((1, 2), repeat=length):
                    sequence = SequenceCTC(np.log(p), list(target))
                    prob = expected.get(target, 0.)
                    self.assert_likelihood(sequence.log_probability, np.log(prob) if prob else -np.inf)
                    for position in range(length):
                        actual = sequence.slot_likelihoods(position, [1, 2])
                        for q, value in zip([1, 2], actual['replacementLogLikelihoods'], strict=True):
                            altered = target[:position]+(q,)+target[position+1:]
                            prob = expected.get(altered, 0.)
                            self.assert_likelihood(value, np.log(prob) if prob else -np.inf)
                        prob = expected.get(target[:position]+target[position+1:], 0.)
                        self.assert_likelihood(actual['deletionLogLikelihood'], np.log(prob) if prob else -np.inf)

    def test_exact_zeros_single_token_deletion_and_nonzero_blank(self):
        p = np.array([[1., 0., 0.], [0., 0., 1.], [1., 0., 0.]])
        with np.errstate(divide='ignore'):
            logp = np.log(p)
        sequence = SequenceCTC(logp, [0, 0], blank=2)
        result = sequence.slot_likelihoods(0, [0, 1])
        self.assertEqual(result['canonicalLogLikelihood'], 0.)
        self.assertEqual(result['replacementLogLikelihoods'][1], -np.inf)
        self.assertEqual(result['deletionLogLikelihood'], -np.inf)
        p = np.array([[.8, .1, .1], [.7, .2, .1]])
        result = SequenceCTC(np.log(p), [1]).slot_likelihoods(0, [1, 2])
        self.assertAlmostEqual(result['deletionLogLikelihood'], np.log(.8*.7))
        self.assertAlmostEqual(SequenceCTC(np.log(p), []).log_probability, np.log(.8*.7))

    def test_pytorch_oracle_long_low_probability_and_residual_mass(self):
        torch.set_num_threads(2)
        rng = np.random.default_rng(123)
        p = rng.dirichlet(np.ones(7), size=220)
        p[:, 1:4] *= 1e-6
        p[:, 0] += 1-p.sum(1)
        logp = np.log(p)
        target = [1, 1, 3, 2, 3, 3]
        sequence = SequenceCTC(logp, target)
        self.assert_likelihood(sequence.log_probability, torch_likelihood(logp, target))
        for position in range(len(target)):
            result = sequence.slot_likelihoods(position, list(range(1, 7)))
            for q, value in zip(range(1, 7), result['replacementLogLikelihoods'], strict=True):
                altered = target.copy(); altered[position] = q
                self.assert_likelihood(value, torch_likelihood(logp, altered))
            self.assert_likelihood(result['deletionLogLikelihood'], torch_likelihood(logp, target[:position]+target[position+1:]))

    def test_denominator_is_sum_of_distinct_sequences_and_not_token_renormalized(self):
        p = np.array([[.2, .3, .1, .4], [.3, .1, .2, .4], [.1, .2, .3, .4]])
        logp = np.log(p)
        result = SequenceCTC(logp, [1, 2]).slot_likelihoods(0, [1, 2])
        scores = summarize_slot(result)
        brute = enumerate_probabilities(p)
        denominator = brute[(1, 2)] + brute.get((2, 2), 0.) + brute[(2,)]
        self.assertAlmostEqual(scores['denominatorLogLikelihood'], np.log(denominator))
        renormalized = p[:, :3]/p[:, :3].sum(1, keepdims=True)
        self.assertNotAlmostEqual(result['canonicalLogLikelihood'], SequenceCTC(np.log(renormalized), [1, 2]).log_probability)

    def test_invalid_inputs_and_undefined_normalized_score_fail(self):
        for invalid in (np.empty((0, 3)), [[np.nan, -.1]], [[0., 0.]], [[-np.inf, -np.inf]]):
            with self.assertRaises(ValueError): SequenceCTC(invalid, [1])
        logp = np.log([[.5, .3, .2]])
        for target in ([0], [3], [True]):
            with self.assertRaises(ValueError): SequenceCTC(logp, target)
        sequence = SequenceCTC(logp, [1])
        for candidates in ([1, 1], [0, 1], [2], [True], []):
            with self.assertRaises(ValueError): sequence.slot_likelihoods(0, candidates)
        for position in (-1, 1, True):
            with self.assertRaises(ValueError): sequence.slot_likelihoods(position, [1, 2])
        impossible = SequenceCTC(logp, [1, 1, 1]).slot_likelihoods(1, [1, 2])
        with self.assertRaises(ValueError): summarize_slot(impossible)


if __name__ == '__main__': unittest.main()
