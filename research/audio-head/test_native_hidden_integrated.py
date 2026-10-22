"""Focused integrated mask, direct-oracle and body metadata controls."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'work/native-hidden-integrated-20261015'))
import integrated_probe as subject


def body_fixture(include_mask=True):
    def var(name, shape, dtype='fp32', op=None): return NS(name=name, shape=shape, dtype=NS(__name__=dtype), op=op)
    masked = var('maskedProjected', subject.SHAPE)
    position = var('positionEmbeddings', subject.SHAPE)
    mask = var('frameMask', (1, 199), 'int32')
    add = NS(op_type='add', inputs={'x': masked, 'y': position}, blocks=[])
    intermediate = var('sum', subject.SHAPE, op=add)
    attention = NS(op_type='attention', inputs={'x': intermediate, **({'mask': mask} if include_mask else {})}, blocks=[])
    hidden = var('hidden', subject.SHAPE, op=attention)
    return NS(functions={'main': NS(inputs={'maskedProjected': masked, 'positionEmbeddings': position, 'frameMask': mask},
        outputs=[hidden], operations=[add, attention])})


class IntegratedHiddenControls(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np

    def test_mask_then_physical_pad_preserves_prefix_signed_zero(self):
        projected = self.np.ones(subject.SHAPE, dtype=self.np.float32)
        projected[0, 0, 0] = -0.0
        masked, padded, mask = subject.make_boundaries(projected, 4)
        subject.validate_boundaries(projected, masked, padded, mask, 4)
        self.assertEqual(masked[0, 0, :1].view('<u4')[0], 0x80000000)
        self.assertTrue((masked[:, 4:].view('<u4') == 0).all())
        self.assertEqual(subject.bytes_pin(padded, '<f4')['bytes'], 1339392)
        self.assertEqual(subject.bytes_pin(mask, '<i4')['bytes'], 796)

    def test_mask_boundary_tampering_and_geometry(self):
        projected = self.np.ones(subject.SHAPE, dtype=self.np.float32)
        for kind in ('tail-sign', 'prefix', 'border', 'mask'):
            masked, padded, mask = subject.make_boundaries(projected, 49)
            if kind == 'tail-sign': masked[0, 49, 0] = -0.0
            elif kind == 'prefix': masked[0, 0, 0] = 2
            elif kind == 'border': padded[0, 0, 0] = -0.0
            else: mask[0, 49] = 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                subject.validate_boundaries(projected, masked, padded, mask, 49)
        for invalid in (0, 200):
            with self.assertRaises(ValueError): subject.make_boundaries(projected, invalid)
        self.assertEqual([subject.shared.frames(n) for n in (1679, 1680, 1681, 63759, 63760)], [4, 5, 5, 198, 199])

    def test_original27_order_counters_and_budgets_are_fixed(self):
        subject.validate_cases(subject.shared.cases())
        with self.assertRaises(ValueError): subject.validate_cases(list(reversed(subject.shared.cases())))
        plan = subject.shared.read_json(subject.PLAN)
        subject.validate_plan(plan)
        for key, value in (('converterExplicitForwards', 81), ('nativeCalls', 27), ('comparisonBudgets', {}),
                           ('reuseExactFrontendAndPositionalArtifacts', False)):
            wrong = copy.deepcopy(plan)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): subject.validate_plan(wrong)

    def test_both_final_direct_references_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            full = self.np.zeros(subject.SHAPE, dtype=self.np.float32)
            valid = full[:, :4].copy()
            row = {'validFrames': 4}
            full_pin = subject.shared.save_array(base / 'full.f32', full, full.shape, base)
            valid_pin = subject.shared.save_array(base / 'valid.f32', valid, valid.shape, base)
            row['padded'] = subject.absolute_pin(full_pin, base)
            row['unpadded'] = subject.absolute_pin(valid_pin, base)
            candidate = full.copy()
            candidate[:, 4] = 0.1
            metrics = subject.final_metrics(row, candidate, 'nativeVsBackend')
            self.assertFalse(metrics['fullPadded']['passed'])
            self.assertTrue(metrics['validUnpadded']['passed'])
            candidate = full.copy()
            candidate[:, :4] = 2e-4
            metrics = subject.final_metrics(row, candidate, 'nativeVsBackend')
            self.assertTrue(metrics['fullPadded']['passed'])
            self.assertFalse(metrics['validUnpadded']['passed'])

    def test_dynamic_mask_reaches_body_output_and_no_conv_or_pad(self):
        observed = subject.inspect_body(body_fixture())
        subject.validate_body(observed)
        with self.assertRaises(ValueError): subject.validate_body(subject.inspect_body(body_fixture(False)))
        for key, value in (('convCount', 1), ('padCount', 1), ('nestedBlocks', 1)):
            wrong = copy.deepcopy(observed)
            wrong[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): subject.validate_body(wrong)

    def test_trace_mean_finite_shape_and_dtype_controls(self):
        reference = {name: self.np.zeros(shape, dtype=self.np.float32) for name, shape in subject.FRONTEND.items()}
        candidate = {name: value.copy() for name, value in reference.items()}
        candidate['projected'].fill(2e-6)
        metrics = subject.tuple_metrics(reference, candidate, subject.FRONTEND)
        self.assertLess(metrics['projected']['maximumAbsoluteError'], 1e-5)
        self.assertFalse(metrics['projected']['passed'])
        for kind in ('shape', 'dtype', 'finite'):
            wrong = {name: value.copy() for name, value in reference.items()}
            if kind == 'shape': wrong['projected'] = wrong['projected'][:, :-1]
            elif kind == 'dtype': wrong['projected'] = wrong['projected'].astype(self.np.float64)
            else: wrong['projected'][0, 0, 0] = self.np.inf
            with self.subTest(kind=kind), self.assertRaises(ValueError): subject.tuple_metrics(reference, wrong, subject.FRONTEND)

    def test_source_failure_is_preserved_and_no_overwrite(self):
        source = subject.shared.pin(Path(subject.__file__))
        source['sha256'] = '0' * 64
        bindings = {'source': source, 'plan': {}, 'originalReference': {}, 'originalBackend': {}, 'reusedPrograms': {},
                    'runtime': {}, 'converterBackend': None, 'extraSources': []}
        with self.assertRaisesRegex(ValueError, 'source pin differs'): subject.guard(bindings)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            output = root / 'work' / 'prepared'
            with patch.object(subject, 'ROOT', root), patch.object(subject, 'prepare_stage', side_effect=ValueError('original binding failed')):
                self.assertEqual(subject.main(['prepare', '--output', str(output)]), 1)
                result = subject.shared.read_json(output / 'outcome.json')
                self.assertFalse(result['complete'])
                self.assertEqual(result['forwardsCompleted'], 0)
                self.assertEqual(result['failureMessage'], 'original binding failed')
                with self.assertRaises(FileExistsError): subject.main(['prepare', '--output', str(output)])


if __name__ == '__main__': unittest.main()
