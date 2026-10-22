"""Focused controls for saved-input encoder entry; no model or Core ML calls."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-encoder-entry-20261015'))
import encoder_probe as subject


class EncoderEntryControls(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def test_both_saved_controls_are_required_in_order(self):
        rows = [{'id': name, 'sampleCount': 64000} for name in subject.CASE_IDS]
        subject.validate_rows(rows)
        for invalid in (rows[:1], list(reversed(rows)), [rows[0], rows[0]]):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'control order'):
                subject.validate_rows(invalid)

    def test_plan_budgets_shapes_and_mask_contract_are_fixed(self):
        plan = subject.shared.read_json(subject.PLAN)
        subject.validate_plan(plan)
        for key, value in (('comparisonBudgets', {}), ('outputOrder', list(reversed(subject.ORDER))),
                           ('shapeInput', [1, 64000]), ('stableLayerNorm', False),
                           ('attentionMask', 'None'), ('outerEncoderNorm', 'Before first block')):
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Encoder-entry plan differs'):
                subject.validate_plan(changed)

    def test_encoder_contract_rejects_wrong_normalization_mask_mode_or_depth(self):
        config = SimpleNamespace(do_stable_layer_norm=True, num_hidden_layers=24, hidden_size=1024,
                                 _attn_implementation='eager')
        subject.validate_encoder_contract(config, 'Wav2Vec2EncoderStableLayerNorm', 24)
        for key, value in (('do_stable_layer_norm', False), ('num_hidden_layers', 12),
                           ('hidden_size', 512), ('_attn_implementation', 'sdpa')):
            wrong = copy.copy(config)
            setattr(wrong, key, value)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'stable/eager'):
                subject.validate_encoder_contract(wrong, 'Wav2Vec2EncoderStableLayerNorm', 24)
        for name, count in (('Wav2Vec2Encoder', 24), ('Wav2Vec2EncoderStableLayerNorm', 1)):
            with self.subTest(name=name, count=count), self.assertRaises(ValueError):
                subject.validate_encoder_contract(config, name, count)

    def test_three_direct_outputs_independently_enforce_mean_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.OUTPUTS.items()}
            pins = subject.save_outputs(base, 'control', reference, 'reference')
            for changed_name in subject.ORDER:
                candidate = {name: value.copy() for name, value in reference.items()}
                candidate[changed_name].fill(2e-4)
                metrics = subject.compare_outputs(pins, candidate, base, 'nativeVsBackend')
                self.assertEqual(set(metrics), set(subject.ORDER))
                self.assertLess(metrics[changed_name]['maximumAbsoluteError'], 1e-3)
                self.assertFalse(metrics[changed_name]['passed'])
                self.assertFalse(subject.passed(metrics))
                self.assertTrue(all(value['passed'] for key, value in metrics.items() if key != changed_name))
            with self.assertRaisesRegex(ValueError, 'output names'):
                subject.compare_outputs(pins, {'block0': reference['block0']}, base, 'nativeVsBackend')

    def test_every_output_rejects_shape_nonfinite_and_dtype(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.OUTPUTS.items()}
            pins = subject.save_outputs(base, 'control', reference, 'reference')
            for name in subject.ORDER:
                for kind in ('shape', 'finite', 'dtype'):
                    candidate = {key: value.copy() for key, value in reference.items()}
                    if kind == 'shape': candidate[name] = candidate[name][:, :198]
                    elif kind == 'finite': candidate[name][0, 0, 0] = self.np.inf
                    else: candidate[name] = candidate[name].astype(self.np.float64)
                    with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                        subject.compare_outputs(pins, candidate, base, 'nativeVsBackend')

    def test_tampered_encoder_source_pin_is_rejected(self):
        source = subject.shared.pin(Path(subject.__file__))
        source['sha256'] = '0' * 64
        bindings = {'backend': {}, 'encoderSource': source, 'encoderPlan': {}, 'maskHelperSource': {},
                    **{key: {} for key in subject.UPSTREAM}}
        with patch.object(subject.shared, 'verify_provenance'), self.assertRaisesRegex(ValueError, 'encoderSource pin differs'):
            subject.verify_bindings(bindings)

    def test_failure_outcome_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            output = root / 'work' / 'reference'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'reference_stage',
                    side_effect=ValueError('encoder source gate failed')):
                self.assertEqual(subject.main(['reference', '--output', str(output)]), 1)
                result = subject.shared.read_json(output / 'outcome.json')
                self.assertEqual(result['failureMessage'], 'encoder source gate failed')
                self.assertFalse(result['complete'])
                self.assertFalse(result['fullGraphQualified'])
                with self.assertRaises(FileExistsError):
                    subject.main(['reference', '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
