import unittest
import numpy as np
from multiphone_competitor_study import posterior_means, normalize, model

class CompetitorTests(unittest.TestCase):
    def test_full_vocab_mass_and_exact_window(self):
        p = np.full((4, 392), 1/392, dtype=np.float32)
        p[1] *= .5
        p[1, 0] += .5
        result = posterior_means(np.log(p), [1, 2], list(range(4, 28)))
        np.testing.assert_allclose(result, np.full(24, .5/392), rtol=1e-6)
        self.assertLess(float(result.sum()), .04)
    def test_bad_interval_and_duplicate_tokens_rejected(self):
        x = np.full((4,392), -6., dtype=np.float32)
        for window, tokens in [([2,2], list(range(4,28))), ([-1,2], list(range(4,28))), ([0,2], [4]*24)]:
            with self.assertRaises(ValueError):
                posterior_means(x, window, tokens)
    def test_normalization_fit_only_and_constant_zero_padding(self):
        values = np.array([[1.,0.], [3.,0.], [1000., 10.]], dtype=np.float32)
        mean, std = normalize(values, [0,1])
        np.testing.assert_array_equal(mean, [2.,0.])
        np.testing.assert_array_equal(std, [1.,1.])
    def test_matched_head_width(self):
        self.assertEqual(model().feature_dim, 37)

if __name__ == '__main__':
    unittest.main()
