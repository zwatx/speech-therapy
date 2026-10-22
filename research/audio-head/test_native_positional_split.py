"""Numerical and source controls for the unchanged positional-module split."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-positional-split-20261015'))
import positional_probe as subject


class PositionalSplitControls(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def test_both_saved_controls_are_required_in_order(self):
        rows = [{'id': name, 'sampleCount': 64000} for name in subject.CASE_IDS]
        subject.validate_rows(rows)
        for invalid in (rows[:1], list(reversed(rows)), [rows[0], rows[0]]):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'control order'):
                subject.validate_rows(invalid)

    def test_plan_budgets_shapes_and_no_attention_contract_are_fixed(self):
        plan = subject.shared.read_json(subject.PLAN)
        subject.validate_plan(plan)
        for key, value in (('comparisonBudgets', {}), ('outputOrder', list(reversed(subject.ORDER))),
                           ('outputs', {name: [1, 199, 1024] for name in subject.ORDER}),
                           ('convContract', {}), ('attentionMask', 'None'), ('backendBoundaryScreen', 'Skipped')):
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Positional-split plan differs'):
                subject.validate_plan(changed)

    def test_conv_trim_activation_and_weight_norm_contract(self):
        observed = {'kernelSize': 128, 'padding': 64, 'groups': 16, 'stride': 1, 'dilation': 1,
            'trimLastFrames': 1, 'weightNormDimension': 2, 'inChannels': 1024, 'outChannels': 1024,
            'weightShape': [1024, 64, 128], 'configuredKernel': 128, 'configuredGroups': 16,
            'configuredActivation': 'gelu', 'activationClass': 'GELUActivation', 'usesConfiguredGelu': True,
            'positionalClass': 'Wav2Vec2PositionalConvEmbedding', 'weightNormClass': '_WeightNorm', 'weightNormCount': 1}
        subject.validate_conv_contract(observed)
        for key, value in (('padding', 63), ('kernelSize', 127), ('groups', 1), ('stride', 2), ('dilation', 2),
                           ('trimLastFrames', 0), ('weightNormDimension', 0), ('weightShape', [1024, 1024, 128]),
                           ('configuredActivation', 'gelu_new'), ('usesConfiguredGelu', False)):
            wrong = copy.deepcopy(observed)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'contract differs'):
                subject.validate_conv_contract(wrong)

    def test_independent_native_means_and_both_backend_boundary_screens(self):
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
            failures = []
            for case_id in subject.CASE_IDS:
                encoder = {'encoderOutputs': {'positionEmbeddings': pins['activated']}}
                activated = self.np.full(subject.OUTPUTS['activated'], 2e-5, dtype=self.np.float32)
                metric = subject.boundary_screen(activated, encoder, base)
                self.assertEqual(metric['budget'], 'converterVsBackend')
                self.assertLess(metric['maximumAbsoluteError'], 1e-4)
                self.assertFalse(metric['passed'])
                failures.append(case_id)
            self.assertEqual(failures, list(subject.CASE_IDS))
            with self.assertRaisesRegex(ValueError, 'output names'):
                subject.compare_outputs(pins, {'activated': reference['activated']}, base, 'nativeVsBackend')

    def test_all_variable_length_outputs_reject_shape_finite_and_dtype(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.OUTPUTS.items()}
            pins = subject.save_outputs(base, 'control', reference, 'reference')
            for name in subject.ORDER:
                for kind in ('shape', 'finite', 'dtype'):
                    candidate = {key: value.copy() for key, value in reference.items()}
                    if kind == 'shape': candidate[name] = candidate[name][:, :-1]
                    elif kind == 'finite': candidate[name][0, 0, 0] = self.np.inf
                    else: candidate[name] = candidate[name].astype(self.np.float64)
                    with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                        subject.compare_outputs(pins, candidate, base, 'nativeVsBackend')

    def test_tampered_positional_source_pin_is_rejected(self):
        source = subject.shared.pin(Path(subject.__file__))
        source['sha256'] = '0' * 64
        bindings = {'backend': {}, 'positionalSource': source, 'positionalPlan': {}, 'encoderProbeSource': {},
                    'operatorSources': [], **{key: {} for key in subject.UPSTREAM}}
        with patch.object(subject.shared, 'verify_provenance'), self.assertRaisesRegex(ValueError, 'positionalSource pin differs'):
            subject.verify_bindings(bindings)

    def test_failure_outcome_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            output = root / 'work' / 'reference'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'reference_stage',
                    side_effect=ValueError('positional source gate failed')):
                self.assertEqual(subject.main(['reference', '--output', str(output)]), 1)
                result = subject.shared.read_json(output / 'outcome.json')
                self.assertEqual(result['failureMessage'], 'positional source gate failed')
                self.assertFalse(result['complete'])
                self.assertFalse(result['fullGraphQualified'])
                with self.assertRaises(FileExistsError):
                    subject.main(['reference', '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
