"""Generated mathematical and admission controls; no model or corpus calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-q8-kernel-20261015'))
import oracle as subject


class GeneratedKernelControls(unittest.TestCase):
    def test_ulp_budget_handles_signs_zero_and_exact_boundary(self):
        one = np.float32(1)
        two = np.nextafter(np.nextafter(one, np.float32(2)), np.float32(2))
        three = np.nextafter(two, np.float32(2))
        self.assertEqual(subject.ulp_distance([one], [two]).tolist(), [2])
        self.assertEqual(subject.ulp_distance([one], [three]).tolist(), [3])
        self.assertEqual(subject.ulp_distance([0.0], [-0.0]).tolist(), [0])
        self.assertEqual(subject.ulp_distance([-one], [-two]).tolist(), [2])
        with self.assertRaises(ValueError): subject.ulp_distance([np.nan], [1])

    def test_double_budget_is_independent_and_finite(self):
        self.assertTrue(subject.double_close(1 + 5e-11, 1))
        self.assertFalse(subject.double_close(1 + 2e-10, 1))
        with self.assertRaises(ValueError): subject.double_close(float('inf'), 1)
        with self.assertRaises(ValueError): subject.double_close(True, 1)

    def test_exhaustive_tie_and_repeated_minimum_paths(self):
        uniform = np.full((2, 392), np.float32(-6))
        path, score = subject.exhaustive_paths(uniform, [4])
        self.assertEqual(path, [1, 1])
        self.assertEqual(score, -12)
        repeated = np.full((3, 392), np.float32(-6))
        self.assertEqual(subject.exhaustive_paths(repeated, [4, 4])[0], [1, 2, 3])
        with self.assertRaises(ValueError): subject.exhaustive_paths(repeated[:2], [4, 4])

    def test_actual_python_generated_oracles_and_low_support_are_preserved(self):
        recipe, vocab = subject.read(subject.RECIPE), subject.read(subject.VOCAB)
        rows = subject.generated_cases(recipe, vocab)
        self.assertEqual([row['caseID'] for row in rows], list(subject.CASE_IDS))
        complete = []
        for row in rows:
            expected, arrays = subject.oracle_result(row, recipe, vocab)
            if row['error']:
                self.assertEqual(expected['error'], row['error'])
            else:
                complete.append(expected)
                self.assertEqual(arrays['features'].dtype, np.float32)
                self.assertEqual(arrays['features'].shape, (len(row['targets']), 1037))
                self.assertEqual(arrays['features'][:, :1024].tobytes(), arrays['pooled'].tobytes())
                self.assertTrue(np.isfinite(arrays['features']).all())
        self.assertEqual(len(complete), 10)
        self.assertEqual(complete[9]['targets'][0]['modelTargetId'], 23)
        reverse = complete[3]
        self.assertEqual([row['canonicalIndex'] for row in reverse['targets']], [1, 0])
        self.assertEqual([row['intervalFrames'] for row in reverse['targets']], [[6, 7], [0, 1]])
        self.assertEqual([row['estimatedPoolingWindowFrames'] for row in reverse['targets']], [[4, 7], [0, 3]])
        self.assertEqual(complete[4]['greedyTokens'], [1, 4, 2, 3])
        self.assertEqual(complete[5]['greedyTokens'], [4])
        self.assertTrue(all('target-is-not-argmax-on-most-occupied-frames' in row['diagnosticFlags'] for row in complete[6]['targets']))
        self.assertIn('er-stress-collapsed-to-rhotic-schwa', complete[7]['mappingAmbiguities'])

    def fixture(self, directory):
        recipe, vocab = subject.read(subject.RECIPE), subject.read(subject.VOCAB)
        generated = subject.generated_cases(recipe, vocab)[3]
        expected, arrays = subject.oracle_result(generated, recipe, vocab)
        for name, values in arrays.items(): expected[name] = subject.save(directory / (name + '.f32'), values, directory)
        return expected

    def test_compare_binds_target_order_rows_shapes_and_finite(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            expected = self.fixture(base)
            self.assertTrue(subject.compare_case(expected, expected, base, base)['passed'])
            for mutation in ('order', 'scalar', 'shape', 'nonfinite'):
                actual = copy.deepcopy(expected)
                if mutation == 'order': actual['targets'].reverse()
                elif mutation == 'scalar': actual['targets'][0]['scalarFeatures'][0] += .01
                else:
                    values = np.zeros((2, 1036 if mutation == 'shape' else 1037), dtype='<f4')
                    if mutation == 'nonfinite': values[0, 0] = np.nan
                    actual['features'] = subject.save(base / (mutation + '.f32'), values, base)
                with self.subTest(mutation=mutation):
                    try: result = subject.compare_case(actual, expected, base, base)
                    except ValueError: continue
                    self.assertFalse(result['passed'])

    def test_pin_tampering_and_relative_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'file'
            source.write_bytes(b'original')
            value = subject.pin(source, root)
            self.assertEqual(subject.verify(value, root), source)
            source.write_bytes(b'modified')
            with self.assertRaises(ValueError): subject.verify(value, root)
            with self.assertRaises(ValueError): subject.verify(dict(value, path='../file'), root)

    def test_prospective_budgets_and_cases_cannot_drift(self):
        plan = {'budgets': subject.BUDGETS, 'caseIDs': list(subject.CASE_IDS), 'generatedOnly': True, 'modelForwardsPlanned': 0}
        subject.validate_plan(plan)
        for key, replacement in (('budgets', dict(subject.BUDGETS, float32ULP=3)), ('caseIDs', list(reversed(subject.CASE_IDS)))):
            with self.assertRaises(ValueError): subject.validate_plan(dict(plan, **{key: replacement}))

    def test_private_fresh_output_no_overwrite_and_failure_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'work').mkdir()
            output = root / 'work' / 'prepared'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'prepare', side_effect=ValueError('source changed')):
                self.assertEqual(subject.main(['prepare', '--output', str(output)]), 1)
                failure = json.loads((output / 'failure.json').read_text())
                self.assertEqual(failure['failureMessage'], 'source changed')
                with self.assertRaises(FileExistsError): subject.main(['prepare', '--output', str(output)])


if __name__ == '__main__': unittest.main()
