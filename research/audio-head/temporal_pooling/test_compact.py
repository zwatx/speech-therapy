"""Synthetic temporal-PCA geometry and leakage checks; no corpus inference."""
import copy
import unittest

import numpy as np
import torch

from lexical_compact.test_core import bundle as original_bundle
from temporal_pooling import compact


def bundle():
    b = original_bundle()
    target = np.zeros((40, 3072), np.float32)
    # Distinct eigenvalues spread over all three bins, with known signs.
    columns = np.array([0, 1024, 2048, 1, 1025, 2049, 2, 1026,
                        2050, 3, 1027, 2051, 4, 1028, 2052, 5])
    target[:, columns] = b['target'][:, :16]
    b['target'] = target
    return b, columns


class TemporalPcaTests(unittest.TestCase):
    def test_geometry_fit_only_and_exact_reconstruction(self):
        b, columns = bundle()
        fit = list(range(32))
        result = compact.prepare(b, 'pca16-scalars', fit)
        t = result['transform']
        self.assertEqual(result['values'].shape, (40, 29))
        expected = np.zeros((3072, 16))
        expected[columns[::-1], np.arange(16)] = 1
        np.testing.assert_array_equal(t['basis'], expected)
        np.testing.assert_array_equal(t['center'], np.zeros(3072))
        np.testing.assert_array_equal(t['eigenvalues'],
                                     np.r_[np.arange(16, 0, -1)**2/16, np.zeros(3056)])
        np.testing.assert_array_equal(result['values'][:, :16], b['target'][:, columns[::-1]])
        np.testing.assert_array_equal(result['values'][:, 16:], b['scalars'])
        altered = copy.deepcopy(b)
        altered['target'][32:] = 1e4
        altered['scalars'][32:] = -1e5
        for row in altered['cohort']['rows'][32:]:
            row['raterCounts'] = [5, 0, 0]
        other = compact.prepare(altered, 'pca16-scalars', fit)
        self.assertTrue(compact.same_transform(t, other['transform']))
        self.assertTrue(torch.equal(result['mean'], other['mean']))
        self.assertTrue(torch.equal(result['std'], other['std']))
        self.assertEqual(result['priors'], other['priors'])
        diagnostic = compact.diagnostics(t, b['target'], b['positions'])
        np.testing.assert_allclose(np.sum(diagnostic['componentSquaredLoadingMass'], axis=0), 1)
        self.assertEqual(diagnostic['pca16VarianceFraction'], 1)
        bad = copy.deepcopy(t)
        bad['basis'] = bad['basis'][:1024]
        self.assertFalse(compact.same_transform(t, bad))

    def test_width_nonfinite_and_rank_fail_closed(self):
        b, _ = bundle()
        wrong = dict(b, target=b['target'][:, :1024])
        with self.assertRaisesRegex(ValueError, 'Invalid target'):
            compact.prepare(wrong, 'pca16-scalars', list(range(32)))
        wrong = copy.deepcopy(b)
        wrong['target'][0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, 'Invalid target'):
            compact.prepare(wrong, 'pca16-scalars', list(range(32)))
        b['target'][:] = 0
        with self.assertRaisesRegex(ValueError, 'fewer than 16'):
            compact.prepare(b, 'pca16-scalars', list(range(32)))


if __name__ == '__main__':
    unittest.main()
