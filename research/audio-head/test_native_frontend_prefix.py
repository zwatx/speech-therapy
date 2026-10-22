"""Source and numerical controls for the two-case learned frontend diagnostic."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-frontend-prefix-20261015'))
import prefix_probe as subject


class FrontendPrefixControls(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def test_both_bound_controls_are_required_in_order(self):
        rows = [{'id': name, 'sampleCount': 64000} for name in subject.CASE_IDS]
        subject.validate_rows(rows)
        for invalid in (rows[:1], list(reversed(rows)), [rows[0], rows[0]]):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'control order'):
                subject.validate_rows(invalid)

    def test_plan_budgets_and_output_shapes_cannot_change(self):
        plan = subject.shared.read_json(subject.PLAN)
        subject.validate_plan(plan)
        for key, value in (('comparisonBudgets', {}), ('outputOrder', list(reversed(subject.ORDER))),
                           ('outputs', {'features': [1, 199, 1024]})):
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Prefix plan differs'):
                subject.validate_plan(changed)

    def test_all_three_direct_outputs_and_mean_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.OUTPUTS.items()}
            pins = subject.save_outputs(base, 'control', reference, 'reference')
            candidate = {name: value.copy() for name, value in reference.items()}
            candidate['projected'].fill(2e-4)
            metrics = subject.compare_outputs(pins, candidate, base, 'nativeVsBackend')
            self.assertEqual(set(metrics), set(subject.ORDER))
            self.assertTrue(metrics['features']['passed'])
            self.assertTrue(metrics['normalizedFeatures']['passed'])
            self.assertLess(metrics['projected']['maximumAbsoluteError'], 1e-3)
            self.assertFalse(metrics['projected']['passed'])
            self.assertFalse(subject.passed(metrics))
            with self.assertRaisesRegex(ValueError, 'output names'):
                subject.compare_outputs(pins, {'features': candidate['features']}, base, 'nativeVsBackend')

    def test_each_output_rejects_shape_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.OUTPUTS.items()}
            pins = subject.save_outputs(base, 'control', reference, 'reference')
            for name in subject.ORDER:
                for kind in ('shape', 'finite'):
                    candidate = {key: value.copy() for key, value in reference.items()}
                    if kind == 'shape': candidate[name] = candidate[name][:, :198]
                    else: candidate[name][0, 0, 0] = self.np.inf
                    with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                        subject.compare_outputs(pins, candidate, base, 'nativeVsBackend')

    def test_tampered_prefix_source_pin_is_rejected(self):
        source = subject.shared.pin(Path(subject.__file__))
        source['sha256'] = '0' * 64
        bindings = {'backend': {}, 'prefixSource': source, 'prefixPlan': {}, 'upstreamReference': {}, 'upstreamFailure': {}}
        with patch.object(subject.shared, 'verify_provenance'), self.assertRaisesRegex(ValueError, 'prefixSource pin differs'):
            subject.verify_bindings(bindings)

    def test_failure_outcome_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            output = root / 'work' / 'reference'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'reference_stage',
                    side_effect=ValueError('prefix source gate failed')):
                self.assertEqual(subject.main(['reference', '--output', str(output)]), 1)
                result = subject.shared.read_json(output / 'outcome.json')
                self.assertEqual(result['failureMessage'], 'prefix source gate failed')
                self.assertFalse(result['complete'])
                self.assertFalse(result['fullGraphQualified'])
                with self.assertRaises(FileExistsError):
                    subject.main(['reference', '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
