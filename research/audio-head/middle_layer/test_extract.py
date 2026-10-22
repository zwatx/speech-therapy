"""Synthetic acceptance tests; never load the encoder or corpus audio."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from middle_layer.extract import (array, atomic_json, checked_review, file_binding,
    guard, join_rows, normalize_middle, parity, pooled_vectors, sources)


class ExtractionTests(unittest.TestCase):
    def test_normalize_before_float64_pooling(self):
        frames = torch.arange(4 * 1024, dtype=torch.float32).reshape(1, 4, 1024)
        normalized = normalize_middle(frames, 1e-5)[0].numpy()
        rows = [{'estimatedPoolingWindowFrames': [1, 4]}]
        pooled, _ = pooled_vectors(normalized, rows, 4)
        np.testing.assert_array_equal(pooled[0], normalized[1:4].mean(0, dtype=np.float64).astype(np.float32))
        np.testing.assert_allclose(normalized.mean(1), 0, atol=1e-6)
        np.testing.assert_allclose(normalized.var(1), 1, atol=1e-6)
        with self.assertRaises(ValueError):
            normalize_middle(frames.double(), 1e-5)
        with self.assertRaises(ValueError):
            pooled_vectors(normalized, [{'estimatedPoolingWindowFrames': [4, 4]}], 4)

    def test_identity_join_and_global_order(self):
        cohort = [dict(id=str(i), clipId='clip', targetId=i, ageBand='child', age=6, trainingEligible=True) for i in range(3)]
        rows = [dict(rowIndex=i, id=str(i), clipId='clip', targetId=i, estimatedPoolingWindowFrames=[0, 1]) for i in (2, 0, 1)]
        clips = [{'id': 'clip', 'rows': rows}]
        self.assertEqual([r['rowIndex'] for r in join_rows(cohort, clips, ['0', '1', '2'])], [0, 1, 2])
        with self.assertRaises(ValueError): join_rows(cohort, clips + clips, ['0', '1', '2'])
        with self.assertRaises(ValueError): join_rows(cohort, clips, ['1', '0', '2'])
        with self.assertRaises(ValueError): join_rows(cohort, clips, ['0', '0', '2'])
        with self.assertRaises(ValueError): join_rows(cohort, [{'id': 'clip', 'rows': rows[:2]}], ['0', '1', '2'])

    def test_installed_implementation_and_probe_bindings(self):
        bindings = sources()
        for name in ('implementation/modeling', 'implementation/preprocessing', 'probe/source', 'probe/result'):
            self.assertTrue(Path(bindings[name]['path']).is_file())
        self.assertEqual(bindings['implementation/modeling']['sha256'],
                         '1c19d14f99c623c71aa8a058235978a06a8af4defb5e1f54321f7a6b7984e572')
        guard(bindings)

    def test_parity_failures(self):
        old = np.zeros((2, 1024), np.float32)
        self.assertEqual(parity(old, old), 0)
        with self.assertRaises(ValueError): parity(old + 1e-4, old)
        with self.assertRaises(ValueError): parity(old + np.nan, old)

    def test_review_and_corruption_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.json'
            review = dict(planSha256='sha', verdict='clear', blockingFindings=[], independent=True, reviewer='Independent reviewer')
            atomic_json(path, review)
            checked_review(path, 'sha')
            with self.assertRaises(ValueError): checked_review(path, 'wrong')
            atomic_json(path, review | {'blockingFindings': ['blocker']})
            with self.assertRaises(ValueError): checked_review(path, 'sha')
            binding = file_binding(path)
            path.write_text('changed')
            with self.assertRaises(ValueError): guard({'review': binding})
            path = Path(directory) / 'test.npy'
            np.save(path, np.zeros((3, 2), np.float32))
            with self.assertRaises(ValueError): array(path, (2, 3), np.float32)
            with self.assertRaises(ValueError): array(path, (3, 2), np.float64)


if __name__ == '__main__':
    unittest.main()
