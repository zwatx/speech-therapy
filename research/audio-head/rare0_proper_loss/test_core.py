"""Numerical and replay checks for the fixed rating-zero proper loss."""
import copy
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest

import numpy as np
import torch

from lexical_compact import core as compact
from lexical_seed_replication import core as seeded
from lexical_unit_weights import core as unitcore
from lexical_unit_weights.test_core import bundle
from lexical_unit_weights.test_core import same
from multiphone_local_head import batch
from rare0_proper_loss import core


FIT = list(range(65))
SELECT = list(range(65, 76))


class ProperLossTests(unittest.TestCase):
    def test_coefficient_zero_is_exact_historical_expression(self):
        logits = torch.tensor([[1., -2., 3.], [-4., 5., .5]], requires_grad=True)
        targets = torch.tensor([[.2, .2, .6], [.8, 0., .2]])
        actual, categorical, binary = core.loss_terms(logits, targets, coefficient=0)
        historical = -(targets * logits.log_softmax(-1)).sum(1).mean()
        self.assertTrue(torch.equal(actual, historical))
        self.assertTrue(torch.equal(categorical, historical))
        self.assertEqual(binary.item(), 0.)
        actual.backward(retain_graph=True)
        actual_gradient = logits.grad.clone()
        logits.grad = None
        historical.backward()
        self.assertTrue(torch.equal(actual_gradient, logits.grad))

    def test_coefficient_zero_one_step_matches_historical_trainer(self):
        data = core.prepare(bundle(), FIT)

        def step(historical):
            model, generator = core.initialize(17)
            optimizer = torch.optim.AdamW(model.parameters(), lr=.0003, weight_decay=.01)
            order = generator.permutation(FIT).tolist()
            indices = order[:64]
            values, phones, mask, targets = batch(data, indices, 'cpu')
            model.train()
            optimizer.zero_grad(set_to_none=True)
            logits = model(values, mask, phones, mask)[:, 0]
            if historical:
                loss = unitcore.weighted_loss(logits, targets, torch.ones(len(indices), dtype=torch.float32))
            else:
                loss = core.loss_terms(logits, targets, coefficient=0)[0]
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            return dict(loss=loss.item(), model=copy.deepcopy(model.state_dict()),
                        optimizer=copy.deepcopy(optimizer.state_dict()),
                        orderSha256=hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest(),
                        pythonRng=random.getstate(), numpyRng=np.random.get_state(),
                        torchRng=torch.get_rng_state().clone(), permutationRng=copy.deepcopy(generator.bit_generator.state))

        reference, candidate = step(True), step(False)
        for key in ('loss', 'model', 'optimizer', 'orderSha256', 'pythonRng', 'torchRng', 'permutationRng'):
            same(self, reference[key], candidate[key])
        self.assertEqual(reference['numpyRng'][0], candidate['numpyRng'][0])
        np.testing.assert_array_equal(reference['numpyRng'][1], candidate['numpyRng'][1])
        self.assertEqual(reference['numpyRng'][2:], candidate['numpyRng'][2:])

    def test_extreme_logits_fractional_votes_and_gradient(self):
        logits = torch.tensor([[1000., 0., -1000.], [-1000., 1000., 999.],
                               [0., 0., 0.]], requires_grad=True)
        targets = torch.tensor([[.2, .2, .6], [.8, .2, 0.], [0., .4, .6]])
        total, categorical, binary = core.loss_terms(logits, targets)
        self.assertTrue(all(bool(torch.isfinite(x)) for x in (total, categorical, binary)))
        self.assertAlmostEqual(total.item(), (categorical + binary).item(), places=5)
        total.backward()
        self.assertTrue(bool(torch.isfinite(logits.grad).all()))
        p = logits.detach().softmax(-1)
        # Analytical binary derivative reduces to p0-q0 for z0 and
        # -(p0-q0) softmax(z1,z2) for the two complement logits.
        expected = (p - targets) / len(logits)
        expected[:, 0] += (p[:, 0] - targets[:, 0]) / len(logits)
        conditional = logits.detach()[:, 1:].softmax(-1)
        expected[:, 1:] -= (p[:, 0] - targets[:, 0])[:, None] * conditional / len(logits)
        torch.testing.assert_close(logits.grad, expected, rtol=0, atol=2e-6)

    def test_binary_loss_is_invariant_to_large_common_logit_offset(self):
        targets = torch.tensor([[.2, .2, .6], [.8, .2, 0.]])
        original = torch.zeros((2, 3), dtype=torch.float32, requires_grad=True)
        shifted = torch.full((2, 3), 1e8, dtype=torch.float32, requires_grad=True)
        base_terms = core.loss_terms(original, targets)
        shifted_terms = core.loss_terms(shifted, targets)
        for left, right in zip(base_terms, shifted_terms):
            self.assertTrue(torch.equal(left, right))
        base_terms[0].backward()
        shifted_terms[0].backward()
        self.assertTrue(torch.equal(original.grad, shifted.grad))

    def test_invalid_shapes_and_coefficients(self):
        z = torch.zeros((2, 3), dtype=torch.float32)
        q = torch.tensor([[.2, .2, .6], [0., 0., 1.]])
        for a, b, c in ((z[:1], q, 1), (z.double(), q, 1), (z, q[:, :2], 1),
                        (z, q * 2, 1), (z, q, .5), (z, q, True),
                        (torch.full_like(z, float('inf')), q, 1)):
            with self.subTest(shape=a.shape, coefficient=c), self.assertRaises(ValueError):
                core.loss_terms(a, b, coefficient=c)

    def test_prepare_initialization_and_fit_only_transform(self):
        source = bundle()
        data = core.prepare(source, FIT)
        reference = compact.prepare(source, core.FAMILY, FIT)
        np.testing.assert_array_equal(data['values'], reference['values'])
        self.assertTrue(compact.same_transform(data['transform'], reference['transform']))
        torch.testing.assert_close(data['mean'], reference['mean'], rtol=0, atol=0)
        torch.testing.assert_close(data['std'], reference['std'], rtol=0, atol=0)
        changed = copy.deepcopy(source)
        changed['target'][65:] = 1e5
        changed['scalars'][65:] = -1e5
        for row in changed['cohort']['rows'][65:]:
            row['raterCounts'] = [5, 0, 0]
        hidden = core.prepare(changed, FIT)
        self.assertTrue(compact.same_transform(data['transform'], hidden['transform']))
        self.assertEqual(data['priors'], hidden['priors'])
        torch.testing.assert_close(data['mean'], hidden['mean'], rtol=0, atol=0)
        torch.testing.assert_close(data['std'], hidden['std'], rtol=0, atol=0)
        for seed in core.SEEDS:
            actual, ag = core.initialize(seed)
            old, og = seeded.initialize(29, seed)
            self.assertTrue(all(torch.equal(actual.state_dict()[k], old.state_dict()[k])
                                for k in actual.state_dict()))
            self.assertEqual(ag.bit_generator.state, og.bit_generator.state)

    def test_training_history_selected_replay_and_bindings(self):
        data = core.prepare(bundle(), FIT)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'inner'
            report = core.train(data, SELECT, output, {}, seed=17)
            history = json.loads((output/'history.json').read_text())
            self.assertEqual(report['bestLoss'], history[report['bestEpoch'] - 1]['selection']['NLL'])
            self.assertEqual(report['bestEpoch'], torch.load(output/'best.pt', weights_only=True)['epoch'])
            self.assertEqual(core.replay(output, data, SELECT, seed=17),
                             history[report['bestEpoch'] - 1]['selection'])
            self.assertEqual(core.validate_run(output, data['cohort'], seed=17, phase='inner',
                                               fit_rows=FIT, selection_rows=SELECT),
                             json.loads((output/'report.json').read_text()))
            self.assertTrue(all(set(('trainLoss', 'trainCategoricalNLL', 'trainRating0BinaryNLL',
                                     'orderSha256')) <= row.keys() for row in history))
            expected_order = np.random.default_rng(17).permutation(FIT).tolist()
            import hashlib
            self.assertEqual(history[0]['orderSha256'], hashlib.sha256(
                json.dumps(expected_order, separators=(',', ':')).encode()).hexdigest())
            with self.assertRaises(ValueError):
                core.replay(output, data, SELECT, seed=29)
            tampered = copy.deepcopy(data)
            tampered['cohort']['rows'][0]['raterCounts'] = [5, 0, 0]
            with self.assertRaises(ValueError):
                core.replay(output, tampered, SELECT, seed=17)

            original_history = (output/'history.json').read_bytes()
            original_best = (output/'best.pt').read_bytes()
            original_report = (output/'report.json').read_bytes()

            def rebind(name):
                current = json.loads(original_report)
                current['artifacts'][name] = core.binding(output/name)
                (output/'report.json').write_text(json.dumps(current))

            for change in ('order', 'selection'):
                altered = json.loads(original_history)
                if change == 'order':
                    altered[0]['orderSha256'] = '0' * 64
                else:
                    altered[0]['selection']['NLL'] += .01
                (output/'history.json').write_text(json.dumps(altered))
                rebind('history.json')
                with self.subTest(change=change), self.assertRaises(ValueError):
                    core.validate_run(output, data['cohort'], seed=17, phase='inner',
                                      fit_rows=FIT, selection_rows=SELECT)
                (output/'history.json').write_bytes(original_history)

            for change in ('optimizer', 'rng'):
                altered = torch.load(output/'best.pt', map_location='cpu', weights_only=True)
                if change == 'optimizer':
                    altered['optimizer']['state'][0]['step'] += 1
                else:
                    altered['rng']['numpyPermutation']['state']['state'] += 1
                torch.save(altered, output/'best.pt')
                rebind('best.pt')
                with self.subTest(change=change), self.assertRaises(ValueError):
                    core.validate_run(output, data['cohort'], seed=17, phase='inner',
                                      fit_rows=FIT, selection_rows=SELECT)
                (output/'best.pt').write_bytes(original_best)
            (output/'report.json').write_bytes(original_report)

    def test_fit_only_pilot_has_no_selection_or_best(self):
        data = core.prepare(bundle(), FIT)
        with tempfile.TemporaryDirectory() as temporary:
            for field, value in (('binaryCoefficient', 0.), ('objective', 'other'),
                                 ('fitRows', FIT[:-1]), ('phase', 'outer-refit')):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    core.train(data, [], Path(temporary)/f'bad-{field}', {field: value},
                               seed=17, epochs=10, pilot=True)
            output = Path(temporary)/'pilot'
            report = core.train(data, [], output, {}, seed=17, epochs=10, pilot=True)
            self.assertEqual((report['phase'], report['bestEpoch'], report['epochsRun']), ('pilot', 0, 10))
            self.assertFalse((output/'best.pt').exists())
            self.assertFalse((output/'selection.json').exists())
            self.assertEqual(core.replay(output, data, FIT, seed=17, checkpoint='last.pt')['rowIndices'], FIT)
            self.assertEqual(core.validate_run(output, data['cohort'], seed=17, phase='pilot',
                                               fit_rows=FIT, selection_rows=[]),
                             json.loads((output/'report.json').read_text()))
            with self.assertRaises(ValueError):
                core.train(data, [], Path(temporary)/'bad', {}, seed=17, epochs=2, pilot=True)
            refit = Path(temporary)/'refit'
            core.train(data, [], refit, {}, seed=17, epochs=2)
            self.assertEqual(core.validate_run(refit, data['cohort'], seed=17, phase='outer-refit',
                                               fit_rows=FIT, selection_rows=[])['bestEpoch'], 2)


if __name__ == '__main__':
    unittest.main()
