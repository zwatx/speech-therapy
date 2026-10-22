"""Guard the native-boundary report against invalid arrays and false passes."""
import unittest

import numpy as np

from check_native_hidden_padding import compare_hidden, frames


class NativeHiddenPaddingTests(unittest.TestCase):
    def test_hidden_width_and_valid_frame_count_are_required(self):
        reference = np.zeros((4, 1024), dtype=np.float32)
        for candidate in (np.zeros((199, 1024), dtype=np.float32),
                          np.zeros((4, 392), dtype=np.float32), reference.astype(np.float64)):
            with self.subTest(shape=candidate.shape, dtype=candidate.dtype), self.assertRaises(ValueError):
                compare_hidden(reference, candidate, 4)

    def test_nonfinite_inputs_cannot_report_parity(self):
        reference = np.zeros((4, 1024), dtype=np.float32)
        for value in (np.nan, np.inf, -np.inf):
            candidate = reference.copy()
            candidate[0, 0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare_hidden(reference, candidate, 4)
            with self.assertRaises(ValueError):
                compare_hidden(candidate, reference, 4)

    def test_single_frame_error_cannot_be_hidden_by_pooling(self):
        reference = np.zeros((4, 1024), dtype=np.float32)
        candidate = reference.copy()
        candidate[0, 0], candidate[1, 0] = 0.01, -0.01
        result = compare_hidden(reference, candidate, 4)
        self.assertEqual(result['pooledMaximumAbsoluteError'], 0)
        self.assertFalse(result['passed'])

    def test_mean_error_has_an_independent_limit(self):
        reference = np.zeros((4, 1024), dtype=np.float32)
        result = compare_hidden(reference, reference + np.float32(5e-5), 4)
        self.assertLess(result['maximumAbsoluteError'], 1e-4)
        self.assertFalse(result['passed'])

    def test_exact_hidden_arrays_and_convolution_geometry(self):
        reference = np.arange(4096, dtype=np.float32).reshape(4, 1024)
        result = compare_hidden(reference, reference.copy(), 4)
        self.assertTrue(result['passed'])
        self.assertEqual(result['maximumAbsoluteError'], 0)
        self.assertEqual([frames(length) for length in (1600, 16000, 64000)], [4, 49, 199])


if __name__ == '__main__':
    unittest.main()
