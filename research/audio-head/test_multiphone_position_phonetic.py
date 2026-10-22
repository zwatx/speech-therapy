"""Synthetic regressions for occurrence identity, pooling and immutable outputs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import multiphone_position_phonetic as m


class PositionPhoneticTests(unittest.TestCase):
    def row(self, index=0, legacy=7):
        return dict(id=f'clip:0:{index}', rowIndex=index, clipId='clip', targetId=0, targetPhone='B',
                    canonicalIndex=index, wordIndex=0, phoneIndex=index, legacyRowIndex=legacy,
                    intervalFrames=[2, 3], estimatedPoolingWindowFrames=[0, 5])

    def test_repeated_phone_pools_distinct_occurrences(self):
        rows = [self.row(), self.row(1, None)]
        rows[1]['estimatedPoolingWindowFrames'] = [5, 8]
        frames = np.arange(8*1024, dtype=np.float32).reshape(8, 1024)
        target, whole = m.old.pooled_vectors(frames, rows, 8)
        np.testing.assert_array_equal(target[0], frames[:5].mean(0, dtype=np.float64).astype(np.float32))
        np.testing.assert_array_equal(target[1], frames[5:].mean(0, dtype=np.float64).astype(np.float32))
        self.assertFalse(np.array_equal(target[0], target[1]))
        np.testing.assert_array_equal(whole, frames.mean(0, dtype=np.float64).astype(np.float32))

    def test_invalid_frame_arrays_and_windows_rejected(self):
        for frames in (np.zeros((8, 1024), np.float64), np.zeros((8, 1023), np.float32),
                       np.full((8, 1024), np.nan, np.float32)):
            with self.assertRaises(ValueError): m.old.pooled_vectors(frames, [self.row()], 8)
        for window in ([0, 9], [-1, 5], [3, 3], [0., 5]):
            row = self.row(); row['estimatedPoolingWindowFrames'] = window
            with self.assertRaises(ValueError): m.old.pooled_vectors(np.zeros((8, 1024), np.float32), [row], 8)

    def test_legacy_join_rejects_wrong_position_or_window(self):
        row = self.row(); legacy = {7: dict(row)}
        self.assertEqual(m.join_rows([row], legacy), {7})
        for key, value in [('phoneIndex', 3), ('clipId', 'other'), ('estimatedPoolingWindowFrames', [1, 5])]:
            with self.assertRaises(ValueError): m.join_rows([{**row, key: value}], legacy)
        with self.assertRaises(ValueError): m.join_rows([row, row], legacy)
        with self.assertRaises(ValueError): m.join_rows([row], {})

    def test_exact_vector_parity_has_no_tolerance(self):
        target = np.ones((2, 1024), np.float32); whole = np.zeros(1024, np.float32)
        original = target[[1]].copy()
        self.assertEqual(m.legacy_parity(target, whole, [(1, 0)], original, whole), 1)
        target[1, 0] = np.nextafter(np.float32(1), np.float32(2))
        with self.assertRaises(ValueError): m.legacy_parity(target, whole, [(1, 0)], original, whole)
        with self.assertRaises(ValueError): m.legacy_parity(original, whole+1, [(0, 0)], original, whole)

    def test_matrix_uses_row_indices_and_appends_scalars(self):
        scalars = np.arange(26, dtype=np.float32).reshape(2, 13)
        units = [([self.row(1)], np.ones((1, 1024), np.float32)),
                 ([self.row(0)], np.zeros((1, 1024), np.float32))]
        target, combined = m.assemble_matrix(units, 2, scalars)
        np.testing.assert_array_equal(target[:, 0], [0, 1])
        np.testing.assert_array_equal(combined[:, :1024], target)
        np.testing.assert_array_equal(combined[:, 1024:], scalars)
        self.assertEqual(combined.dtype, np.float32)

    def test_matrix_missing_duplicate_bad_values_rejected(self):
        values = np.zeros((1, 1024), np.float32); unit = ([self.row()], values)
        with self.assertRaises(ValueError): m.assemble_matrix([unit], 2, np.zeros((2, 13), np.float32))
        with self.assertRaises(ValueError): m.assemble_matrix([unit, unit], 2, np.zeros((2, 13), np.float32))
        with self.assertRaises(ValueError): m.assemble_matrix([unit], 1, np.zeros((1, 13), np.float64))
        with self.assertRaises(ValueError): m.assemble_matrix([([self.row()], values.astype(np.float64))], 1, np.zeros((1, 13), np.float32))

    def test_saved_unit_corruption_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'clip'; expected = {'synthetic': True, 'rows': [self.row()]}
            target = np.ones((1, 1024), np.float32); whole = np.ones(1024, np.float32)
            m.old.write_unit(directory, expected, target, whole)
            m.old.checked_unit(directory, expected, 1024)
            with self.assertRaises(ValueError): m.old.write_unit(directory, expected, target, whole)
            with self.assertRaises(ValueError): m.old.checked_unit(directory, {**expected, 'synthetic': False}, 1024)
            with (directory/'vectors.npz').open('ab') as f: f.write(b'corruption')
            with self.assertRaises(ValueError): m.old.checked_unit(directory, expected, 1024)

    def test_failure_record_and_second_run_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pin = {'path': str(root/'plan.json'), 'sha256': 'synthetic'}
            with patch.object(m, 'load_plan', return_value=({}, pin)), patch.object(m, 'assemble', side_effect=ValueError('synthetic failure')) as assemble:
                with self.assertRaisesRegex(ValueError, 'synthetic failure'): m.execute(root/'plan.json', 'synthetic', True)
                self.assertTrue((root/'failure.json').exists())
                with self.assertRaises((ValueError, FileExistsError)): m.execute(root/'plan.json', 'synthetic', True)
                self.assertEqual(assemble.call_count, 1)

    def test_checked_matrix_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'matrix.npy'; np.save(path, np.zeros((1, 13), np.float32))
            pin = m.binding(path); m.checked_array(pin, (1, 13))
            np.save(path, np.ones((1, 13), np.float32))
            with self.assertRaises(ValueError): m.checked_array(pin, (1, 13))


if __name__ == '__main__': unittest.main()
