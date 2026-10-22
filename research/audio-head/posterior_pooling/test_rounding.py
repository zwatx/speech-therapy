"""Supplemental synthetic checks suggested by the independent core review."""
import unittest

import numpy as np

from posterior_pooling.core import CTCPosterior, POLICY


class RoundingTests(unittest.TestCase):
    def test_long_noninteger_sharp_logits_keep_fixed_invariants(self):
        rng = np.random.default_rng(28092026)
        logits = rng.normal(0, 8, size=(1500, 392))
        shifted = logits-logits.max(axis=1, keepdims=True)
        logp = (shifted-np.log(np.exp(shifted).sum(axis=1, keepdims=True))).astype('<f4')
        tokens = [int(x) for x in rng.integers(1, 392, size=60)]
        tokens[20] = tokens[19]
        posterior = CTCPosterior(logp, tokens)
        self.assertLessEqual(posterior.audit['frameMassMaxAbs'], posterior.tolerance)
        self.assertLessEqual(posterior.audit['forwardBackwardAbs'], posterior.tolerance)
        for j in (0, 19, 20, 59):
            weights = posterior.token_weights(j)
            self.assertAlmostEqual(float(weights['q'].sum()), 1., places=10)
            self.assertAlmostEqual(float(weights['u'].sum()), 1., places=10)
        self.assertEqual(POLICY['fullVocabularyLogNormalizationAtol'], 3e-5)

    def test_positive_log_probability_fails_before_normalization(self):
        bad = np.full((4, 3), -1000., dtype='<f4')
        bad[:, 0] = 1e-5
        with self.assertRaisesRegex(ValueError, 'Positive log probability'):
            CTCPosterior(bad, [1])

    def test_float32_full_vocabulary_normalization_boundary(self):
        uniform = np.full((4, 392), -np.log(392), dtype='<f4')
        for sign in (-1, 1):
            within = (uniform.astype('<f8')+sign*2.9e-5).astype('<f4')
            outside = (uniform.astype('<f8')+sign*3.1e-5).astype('<f4')
            with self.subTest(sign=sign):
                accepted = CTCPosterior(within, [1])
                self.assertLess(accepted.audit['logNormalizationMaxAbs'], 3e-5)
                with self.assertRaisesRegex(ValueError, 'full-vocabulary normalization'):
                    CTCPosterior(outside, [1])


if __name__ == '__main__':
    unittest.main()
