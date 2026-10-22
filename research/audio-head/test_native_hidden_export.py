"""Focused controls for the hidden-only exporter; no models or Core ML execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_hidden_export as subject


class HiddenExportControls(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def test_geometry_and_declared_cases(self):
        rows = subject.cases()
        self.assertEqual(len(rows), 27)
        self.assertEqual(len({row['id'] for row in rows}), 27)
        self.assertEqual([subject.frames(n) for n in (1679, 1680, 1681)], [4, 5, 5])
        self.assertEqual([subject.frames(n) for n in (63759, 63760, 63761)], [198, 199, 199])

    def test_plan_cannot_relax_budgets(self):
        plan = subject.read_json(subject.PLAN)
        subject.validate_plan(plan)
        plan = copy.deepcopy(plan)
        plan['comparisonBudgets']['nativeVsBackend']['maximum'] = 1.0
        with self.assertRaisesRegex(ValueError, 'comparisonBudgets'):
            subject.validate_plan(plan)

    def test_mean_budget_is_independent(self):
        reference = self.np.zeros((1, 2, 1024), dtype=self.np.float32)
        candidate = self.np.full_like(reference, 2e-4)
        result = subject.compare_hidden(reference, candidate, reference.shape, 'nativeVsBackend')
        self.assertLess(result['maximumAbsoluteError'], result['limits']['maximum'])
        self.assertGreater(result['meanAbsoluteError'], result['limits']['mean'])
        self.assertFalse(result['passed'])

    def test_hidden_shape_and_finite_controls(self):
        values = self.np.zeros((1, 2, 1024), dtype=self.np.float32)
        with self.assertRaisesRegex(ValueError, 'shape'):
            subject.compare_hidden(values, values[:, :1], values.shape, 'nativeVsBackend')
        candidate = values.copy()
        candidate[0, 0, 0] = self.np.nan
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            subject.compare_hidden(values, candidate, values.shape, 'nativeVsBackend')

    def test_native_must_pass_both_backend_branches(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            full = self.np.zeros((1, 199, 1024), dtype=self.np.float32)
            unpadded = self.np.ones((1, 4, 1024), dtype=self.np.float32)
            row = {'validFrames': 4,
                   'padded': subject.save_array(base / 'padded.f32', full, full.shape, base),
                   'unpadded': subject.save_array(base / 'unpadded.f32', unpadded, unpadded.shape, base)}
            results = subject.backend_comparisons(row, full, 'nativeVsBackend', base)
            self.assertTrue(results['fullPadded']['passed'])
            self.assertFalse(results['validUnpadded']['passed'])

    def test_array_pin_and_byte_shape_failures(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            values = self.np.zeros((1, 4, 1024), dtype=self.np.float32)
            value = subject.save_array(base / 'hidden.f32', values, values.shape, base)
            with self.assertRaisesRegex(ValueError, 'byte count'):
                subject.load_array(value, (1, 5, 1024), base)
            (base / 'hidden.f32').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'pin differs'):
                subject.load_array(value, values.shape, base)

    def test_relative_pin_cannot_escape_owned_directory(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ValueError, 'canonical relative'):
                subject.verify_pin({'path': '../hidden.f32', 'bytes': 0, 'sha256': '0' * 64}, base=Path(name))

    def test_native_deadline_is_exact_decimal_string(self):
        subject.validate_deadline('123456.000000001')
        for value in (123456.0, '1e6', '+1', '-1', 'NaN', 'Infinity', '0', '1..2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                subject.validate_deadline(value)

    def test_failure_is_preserved_and_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'work').mkdir()
            output = root / 'work' / 'failed'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'reference_stage',
                    side_effect=ValueError('prospective gate failed')):
                self.assertEqual(subject.main(['reference', '--output', str(output)]), 1)
                result = json.loads((output / 'outcome.json').read_text())
                self.assertFalse(result['complete'])
                self.assertEqual(result['failureMessage'], 'prospective gate failed')
                with self.assertRaises(FileExistsError):
                    subject.main(['reference', '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
