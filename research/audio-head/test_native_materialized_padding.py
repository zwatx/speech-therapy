"""Materialization, fixed numerical gates and MIL metadata; no model execution."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-positional-materialized-20261015'))
import materialized_probe as subject


def program_fixture():
    dtype = NS(__name__='fp32')

    def var(name, shape, op=None): return NS(name=name, shape=shape, dtype=dtype, op=op)
    def constant(value): return NS(val=value)

    def operation(kind, inputs, name, shape):
        op = NS(op_type=kind, inputs=inputs, blocks=[])
        op.outputs = [var(name, shape, op)]
        return op

    padded = var('paddedChannels', subject.INPUT_SHAPE)
    raw = operation('conv', {'x': padded, 'weight': var('weight', (1024, 64, 128)), 'groups': constant(16),
        'strides': constant([1]), 'dilations': constant([1]), 'pad_type': constant('valid'), 'pad': constant([0, 0])}, 'raw', (1, 1024, 200))
    trimmed = operation('slice_by_index', {'x': raw.outputs[0]}, 'trim', (1, 1024, 199))
    activated = operation('gelu', {'x': trimmed.outputs[0], 'mode': constant('EXACT')}, 'act', (1, 1024, 199))
    outputs = [operation('transpose', {'x': source.outputs[0], 'perm': constant([0, 2, 1])}, name, shape)
               for source, (name, shape) in zip((raw, trimmed, activated), subject.OUTPUTS.items())]
    return NS(functions={'main': NS(inputs={'paddedChannels': padded}, outputs=[op.outputs[0] for op in outputs],
        operations=[raw, trimmed, activated, *outputs])})


class MaterializedPaddingControls(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def original(self):
        values = self.np.arange(199 * 1024, dtype=self.np.float32).reshape(subject.ORIGINAL_SHAPE)
        values[0, 0, 0] = self.np.float32(-0.0)
        return values

    def test_materialized_center_preserves_bytes_and_signed_zero(self):
        original = self.original()
        expected_sha = hashlib.sha256(original.tobytes()).hexdigest()
        padded = subject.materialize(original)
        proof = subject.validate_padding(padded, original, expected_sha)
        self.assertEqual(padded.shape, (1, 1024, 327))
        self.assertEqual(padded.nbytes, 1339392)
        self.assertEqual(proof['centerSHA256'], expected_sha)
        self.assertEqual(padded[0, 0, 64:65].view('<u4')[0], 0x80000000)
        self.assertTrue((padded[:, :, :64].view('<u4') == 0).all())

    def test_border_signed_zero_center_and_hash_tampering_rejected(self):
        original = self.original()
        expected_sha = hashlib.sha256(original.tobytes()).hexdigest()
        for kind in ('negative-zero-border', 'nonzero-border', 'center-sign', 'hash'):
            padded = subject.materialize(original)
            sha = expected_sha
            if kind == 'negative-zero-border': padded[0, 0, 0] = -0.0
            elif kind == 'nonzero-border': padded[0, 0, 326] = 1
            elif kind == 'center-sign': padded[0, 0, 64] = 0.0
            else: sha = '0' * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError): subject.validate_padding(padded, original, sha)

    def test_order_preparation_contract_and_plan_cannot_change(self):
        plan = subject.shared.read_json(subject.PLAN)
        subject.validate_plan(plan)
        rows = [{'id': name, 'sampleCount': 64000} for name in subject.CASE_IDS]
        subject.validate_rows(rows)
        for invalid in (rows[:1], list(reversed(rows)), [rows[0], rows[0]]):
            with self.assertRaises(ValueError): subject.validate_rows(invalid)
        for key, value in (('preparationIsInference', True), ('comparisonBudgets', {}), ('inputShape', [1, 199, 1024]),
                           ('zeroBorderBits', 0x80000000), ('defaultPassPipeline', False)):
            wrong = copy.deepcopy(plan)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): subject.validate_plan(wrong)

    def test_no_pad_mil_direct_input_and_wrong_connection_failures(self):
        observed = subject.inspect_structure(program_fixture())
        subject.validate_structure(observed)
        for key, value in (('padCount', 1), ('convCount', 2), ('convPadType', 'custom'), ('convInternalPad', [64, 64]),
                           ('convInputIsExternalInput', False), ('convWeightShape', [1024, 1024, 128]),
                           ('activationMode', 'TANH_APPROXIMATION')):
            wrong = copy.deepcopy(observed)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): subject.validate_structure(wrong)
        program = program_fixture()
        conv = program.functions['main'].operations[0]
        conv.inputs['x'] = copy.copy(conv.inputs['x'])
        with self.assertRaisesRegex(ValueError, 'convInputIsExternalInput'):
            subject.validate_structure(subject.inspect_structure(program))

    def test_direct_original_reference_binding_for_both_negative_records(self):
        reference_pin = {'path': '/old/reference.json', 'bytes': 100, 'sha256': '1' * 64}
        metrics = {name: {'budget': 'nativeVsBackend', 'limits': subject.BUDGETS['nativeVsBackend'], 'passed': False}
                   for name in subject.ORDER}
        for schema in ('NativePositionalSplitComparisonV1', 'NativePositionalPaddingComparisonV1'):
            negative = {'schema': schema, 'complete': True, 'comparisonPassed': False, 'budgets': subject.BUDGETS,
                'inputs': {'reference': reference_pin}, 'comparisonReference': reference_pin,
                'cases': [{'id': name, 'sampleCount': 64000, 'passed': False, 'outputs': metrics} for name in subject.CASE_IDS]}
            subject.validate_negative(negative, schema, reference_pin)
            wrong = copy.deepcopy(negative)
            if schema == 'NativePositionalSplitComparisonV1': wrong['inputs']['reference']['sha256'] = '2' * 64
            else: wrong['comparisonReference']['sha256'] = '2' * 64
            with self.subTest(schema=schema), self.assertRaisesRegex(ValueError, 'binding differs'):
                subject.validate_negative(wrong, schema, reference_pin)

    def test_variable_output_dtype_finite_shape_and_mean_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.OUTPUTS.items()}
            targets = {name: subject.shared.save_array(base / (name + '.f32'), value, value.shape, base)
                       for name, value in reference.items()}
            for name in subject.ORDER:
                values = {key: value.copy() for key, value in reference.items()}
                values[name].fill(2e-4)
                metrics = subject.compare_outputs(targets, values, 'nativeVsBackend', base)
                self.assertLess(metrics[name]['maximumAbsoluteError'], 1e-3)
                self.assertFalse(metrics[name]['passed'])
                self.assertFalse(subject.passed(metrics))
                for kind in ('shape', 'finite', 'dtype'):
                    values = {key: value.copy() for key, value in reference.items()}
                    if kind == 'shape': values[name] = values[name][:, :-1]
                    elif kind == 'finite': values[name][0, 0, 0] = self.np.inf
                    else: values[name] = values[name].astype(self.np.float64)
                    with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                        subject.compare_outputs(targets, values, 'nativeVsBackend', base)

    def test_failure_source_tamper_and_no_overwrite(self):
        source = subject.shared.pin(Path(subject.__file__))
        source['sha256'] = '0' * 64
        bindings = {'source': source, 'plan': {}, 'runtime': {}, 'oldSource': {}, 'oldPlan': {}, 'oldBackend': {},
                    'oldOperatorSources': [], 'converterBackend': None, **{key: {} for key in subject.UPSTREAM}}
        with self.assertRaisesRegex(ValueError, 'source pin differs'): subject.verify_bindings(bindings)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            output = root / 'work' / 'prepared'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'prepare_stage', side_effect=ValueError('prepare gate failed')):
                self.assertEqual(subject.main(['prepare', '--output', str(output)]), 1)
                result = subject.shared.read_json(output / 'outcome.json')
                self.assertFalse(result['complete'])
                self.assertEqual(result['forwardsCompleted'], 0)
                self.assertEqual(result['failureMessage'], 'prepare gate failed')
                with self.assertRaises(FileExistsError): subject.main(['prepare', '--output', str(output)])


if __name__ == '__main__': unittest.main()
