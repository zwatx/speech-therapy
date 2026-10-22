"""Small numerical, binding and MIL-metadata controls; no model/Core ML calls."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-positional-explicit-pad-20261015'))
import padding_probe as subject


def program_fixture():
    dtype = NS(__name__='fp32')

    def var(name, shape, op=None):
        return NS(name=name, shape=shape, dtype=dtype, op=op)

    def op(kind, inputs, name, shape):
        operation = NS(op_type=kind, inputs=inputs, blocks=[])
        operation.outputs = [var(name, shape, operation)]
        return operation

    def constant(value): return NS(val=value)

    projected = var('projectedHidden', (1, 199, 1024))
    channels = op('transpose', {'x': projected, 'perm': constant([0, 2, 1])}, 'channels', (1, 1024, 199))
    padded = op('pad', {'x': channels.outputs[0], 'pad': constant([64, 64]), 'mode': constant('constant'),
                       'constant_val': constant(0.0)}, 'padded', (1, 1024, 327))
    raw = op('conv', {'x': padded.outputs[0], 'weight': var('weight', (1024, 64, 128)), 'groups': constant(16),
                     'strides': constant([1]), 'dilations': constant([1]), 'pad_type': constant('valid'),
                     'pad': constant([0, 0])}, 'raw', (1, 1024, 200))
    trimmed = op('slice_by_index', {'x': raw.outputs[0]}, 'trim', (1, 1024, 199))
    activated = op('gelu', {'x': trimmed.outputs[0], 'mode': constant('EXACT')}, 'act', (1, 1024, 199))
    outputs = [op('transpose', {'x': source.outputs[0], 'perm': constant([0, 2, 1])}, name, shape)
               for source, (name, shape) in zip((raw, trimmed, activated), subject.OUTPUTS.items())]
    return NS(functions={'main': NS(inputs={'projectedHidden': projected},
        outputs=[item.outputs[0] for item in outputs], operations=[channels, padded, raw, trimmed, activated, *outputs])})


class PositionalPaddingControls(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def test_mil_inspection_and_explicit_pad_structure(self):
        observed = subject.inspect_structure(program_fixture())
        subject.validate_structure(observed)
        self.assertEqual(observed['padWidths'], [0, 0, 0, 0, 64, 64])
        for key, value in (('convPadType', 'custom'), ('convInternalPad', [64, 64]),
                           ('paddedShape', [1, 1024, 326]), ('padValue', 1.0), ('padMode', 'reflect'),
                           ('padWidths', [0, 0, 0, 0, 63, 65]), ('convCount', 2),
                           ('convInputIsPadOutput', False), ('activationMode', 'TANH_APPROXIMATION')):
            wrong = copy.deepcopy(observed)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): subject.validate_structure(wrong)

    def test_inspector_rejects_disconnected_pad_and_nonconstant_zero(self):
        program = program_fixture()
        function = program.functions['main']
        function.operations[2].inputs['x'] = function.operations[0].outputs[0]
        with self.assertRaisesRegex(ValueError, 'convInputIsPadOutput'):
            subject.validate_structure(subject.inspect_structure(program))
        program = program_fixture()
        program.functions['main'].operations[1].inputs['constant_val'].val = None
        with self.assertRaisesRegex(ValueError, 'not constant'): subject.inspect_structure(program)

    def test_plan_control_order_budgets_and_pass_pipeline(self):
        plan = subject.shared.read_json(subject.PLAN)
        subject.validate_plan(plan)
        rows = [{'id': name, 'sampleCount': 64000} for name in subject.CASE_IDS]
        subject.validate_rows(rows)
        with self.assertRaises(ValueError): subject.validate_rows(list(reversed(rows)))
        for key, value in (('defaultPassPipeline', False), ('noPassDisabling', False),
                           ('comparisonBudgets', {}), ('compilerStructure', {})):
            wrong = copy.deepcopy(plan)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): subject.validate_plan(wrong)

    def test_negative_comparison_must_bind_actual_reference(self):
        reference_pin = {'path': '/reference/manifest.json', 'bytes': 100, 'sha256': '1' * 64}
        metric = {'budget': 'nativeVsBackend', 'limits': subject.BUDGETS['nativeVsBackend'], 'passed': False}
        negative = {'schema': 'NativePositionalSplitComparisonV1', 'complete': True, 'comparisonPassed': False,
            'budgets': subject.BUDGETS, 'inputs': {'reference': reference_pin},
            'cases': [{'id': name, 'sampleCount': 64000, 'passed': False, 'outputs': {'convOutput': metric}}
                      for name in subject.CASE_IDS]}
        subject.validate_previous_comparison(negative, reference_pin)
        wrong = copy.deepcopy(negative)
        wrong['inputs']['reference']['sha256'] = '2' * 64
        with self.assertRaisesRegex(ValueError, 'comparison differs'):
            subject.validate_previous_comparison(wrong, reference_pin)

    def test_variable_shapes_finite_dtype_and_mean_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.OUTPUTS.items()}
            pins = subject.save_outputs(base, 'control', reference, 'reference')
            for name in subject.ORDER:
                values = {key: value.copy() for key, value in reference.items()}
                values[name].fill(2e-4)
                metrics = subject.compare_outputs(pins, values, base, 'nativeVsBackend')
                self.assertLess(metrics[name]['maximumAbsoluteError'], 1e-3)
                self.assertFalse(metrics[name]['passed'])
                self.assertFalse(subject.passed(metrics))
                for kind in ('shape', 'finite', 'dtype'):
                    values = {key: value.copy() for key, value in reference.items()}
                    if kind == 'shape': values[name] = values[name][:, :-1]
                    elif kind == 'finite': values[name][0, 0, 0] = self.np.inf
                    else: values[name] = values[name].astype(self.np.float64)
                    with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                        subject.compare_outputs(pins, values, base, 'nativeVsBackend')

    def test_tampered_padding_source_pin_is_rejected(self):
        source = subject.shared.pin(Path(subject.__file__))
        source['sha256'] = '0' * 64
        bindings = {'backend': {}, 'paddingSource': source, 'paddingPlan': {}, 'priorPositionalSource': {},
            'priorPositionalPlan': {}, 'encoderProbeSource': {}, 'operatorSources': [], **{key: {} for key in subject.UPSTREAM}}
        with self.assertRaisesRegex(ValueError, 'paddingSource pin differs'): subject.verify_bindings(bindings)

    def test_failure_receipt_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            output = root / 'work' / 'reference'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'reference_stage',
                    side_effect=ValueError('padding source gate failed')):
                self.assertEqual(subject.main(['reference', '--output', str(output)]), 1)
                result = subject.shared.read_json(output / 'outcome.json')
                self.assertEqual(result['failureMessage'], 'padding source gate failed')
                self.assertFalse(result['complete'])
                with self.assertRaises(FileExistsError): subject.main(['reference', '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
