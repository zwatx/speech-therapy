"""Synthetic raw phonetic-adaptation checks; no real encoder/audio inference."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch
from torch import nn

import multiphone_phonetic_adapt as adapt


class TinyLayer(nn.Module):
    def __init__(self):
        super().__init__()
        self.scale = nn.Parameter(torch.tensor(.999))
        self.bias = nn.Parameter(torch.tensor(.002))
        self.dropout = nn.Dropout(.5)

    def forward(self, x):
        return self.dropout(x * self.scale + self.bias)


class TinyEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.feature_extractor = TinyLayer()
        self.encoder = nn.Module()
        self.encoder.layers = nn.ModuleList([TinyLayer() for _ in range(24)])
        self.encoder.layer_norm = TinyLayer()

    def forward(self, input_values, attention_mask):
        x = self.feature_extractor(input_values)
        for layer in self.encoder.layers:
            x = layer(x)
        x = self.encoder.layer_norm(x)
        return SimpleNamespace(last_hidden_state=x[:, :, None] * torch.linspace(.2, 1.2, 1024))


class TinyData:
    def __init__(self, clip_ids):
        self.rows = []
        self.grouped = {}
        for clip in range(4):
            self.grouped[clip] = []
            for target in ([0] if clip == 1 else [0, 1]):
                self.grouped[clip].append(len(self.rows))
                self.rows.append({'clipIndex': clip, 'targetId': target, 'targetPhone': ('B', 'P')[target],
                    'speakerId': str(clip), 'age': 8 if clip % 2 else 17, 'raterCounts': [2, 1, 2] if target else [1, 1, 3]})
        self.clip_ids = list(clip_ids)
        self.grouped = {i: self.grouped[i] for i in clip_ids}

    def clip(self, index):
        indices = self.grouped[index]
        inputs = {'input_values': torch.linspace(.1, 1., 5)[None] + index / 10,
                  'attention_mask': torch.ones(1, 5, dtype=torch.long)}
        phones = torch.tensor([self.rows[i]['targetId'] for i in indices])
        windows = [[0, 2] if phone == 0 else [2, 5] for phone in phones]
        scalars = torch.stack([torch.linspace(.05, .2, 13) + int(phone) for phone in phones])
        targets = torch.tensor([self.rows[i]['raterCounts'] for i in indices]).float() / 5
        return inputs, phones, windows, scalars, 5, targets, indices


class PhoneticAdaptTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.temp = tempfile.TemporaryDirectory(prefix='cadence-phonetic-adapt-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fit, self.val = TinyData([0, 1, 2]), TinyData([3])
        self.rows = self.val.grouped[3]
        self.recipe = {'seed': 7, 'maximumEpochs': 3, 'patienceEpochs': 3, 'minimumImprovement': 1e-7,
            'gradientAccumulationClips': 2, 'maximumGradientNorm': 5., 'checkpointEveryUpdates': 1,
            'maximumEpochZeroProbabilityDifference': .001}

    def model(self, upper=1, dropout=.1):
        torch.manual_seed(7)
        return adapt.TargetRatingModel(TinyEncoder(), adapt.MeanPoolPhoneRatingHead(feature_dim=1037, hidden_dim=8, dropout=dropout),
                                       torch.zeros(1037), torch.ones(1037), upper)

    def make_run(self, name, upper=1):
        output = self.root / name
        output.mkdir()
        adapt.atomic_json(output / 'config.json', {'fixture': name})
        model = self.model(upper)
        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=.005)
        _, reference = adapt.evaluate(model, self.val, self.rows)
        args = SimpleNamespace(output=output, resume=False, device='cpu', regime='all-age')
        return model, optimizer, args, reference

    def run_loop(self, run):
        model, optimizer, args, reference = run
        with patch.object(adapt, 'guard'), contextlib.redirect_stdout(io.StringIO()):
            return adapt.fit_loop(model, optimizer, self.fit, self.val, self.rows, args, self.recipe,
                                  adapt.read_json(args.output / 'config.json'), reference)

    def test_allowlisted_last_layer_and_head_update_while_all_frozen_weights_remain_identical(self):
        for upper in (0, 1):
            with self.subTest(upper=upper):
                model = self.model(upper, dropout=0)
                frozen = adapt.frozen_parameter_digest(model.encoder)
                before = {name: value.detach().clone() for name, value in model.named_parameters()}
                model.train()
                self.assertTrue(model.head.training)
                self.assertTrue(all(not module.training for module in model.encoder.modules()))
                optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=.01)
                _, count, norm = adapt.update_group(model, optimizer, self.fit, [0, 1], 5.)
                self.assertEqual(count, 3)
                self.assertGreater(norm, 0)
                self.assertEqual(adapt.frozen_parameter_digest(model.encoder), frozen)
                changed = {name for name, value in model.named_parameters() if not torch.equal(value, before[name])}
                self.assertTrue(any(name.startswith('head.') for name in changed))
                encoder_changes = {name for name in changed if name.startswith('encoder.')}
                self.assertEqual(bool(encoder_changes), bool(upper))
                self.assertTrue(all(name.startswith('encoder.encoder.layers.23.') for name in encoder_changes))
                for name, value in model.named_parameters():
                    if not value.requires_grad:
                        self.assertIsNone(value.grad)
                        self.assertNotIn(name, changed)
                with self.assertRaisesRegex(ValueError, 'allowlist'):
                    model.restore_adapted_state({**model.adapted_state(), 'encoder.layer_norm.scale': torch.tensor(1.)})

    def test_expected_window_scalar_and_phone_order_and_invalid_raw_inputs(self):
        class CaptureHead(nn.Module):
            def forward(self, features, mask, phones, targets):
                self.features, self.phones = features.detach().clone(), phones.clone()
                return features[:, :, :3]
        head = CaptureHead()
        model = adapt.TargetRatingModel(TinyEncoder(), head, torch.zeros(1037), torch.ones(1037), 0)
        inputs, phones, windows, scalars, frames, _, _ = self.fit.clip(0)
        raw = model.encoder(**inputs).last_hidden_state
        model(inputs, phones, windows, scalars, frames)
        self.assertTrue(torch.equal(head.features[:, 0, 1024:], scalars))
        self.assertTrue(torch.equal(head.features[:, 0, :1024], torch.stack([raw[0, a:b].mean(0) for a, b in windows])))
        self.assertTrue(torch.equal(head.phones[:, 0], phones))
        model(inputs, phones.flip(0), windows[::-1], scalars.flip(0), frames)
        self.assertTrue(torch.equal(head.features[:, 0, 1024:], scalars.flip(0)))
        for bad in ([[0, 0], [2, 5]], [[0, 6], [2, 5]], [[0., 2], [2, 5]]):
            with self.assertRaisesRegex(ValueError, 'window'):
                model(inputs, phones, bad, scalars, frames)
        with self.assertRaisesRegex(ValueError, 'grid'):
            model(inputs, phones, windows, scalars, frames + 1)
        with self.assertRaisesRegex(ValueError, 'scalar'):
            model(inputs, phones, windows, scalars.requires_grad_(True), frames)
        scalars = scalars.detach()
        for broken in ({**inputs, 'attention_mask': torch.zeros_like(inputs['attention_mask'])},
                       {**inputs, 'input_values': inputs['input_values'].repeat(2, 1)}):
            with self.assertRaises(ValueError):
                model(broken, phones, windows, scalars, frames)
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            model(inputs, torch.tensor([0, 0]), windows, scalars, frames)

    def test_accumulation_weights_every_target_equally_with_unequal_clip_target_counts(self):
        actual = self.model(dropout=0)
        expected = copy.deepcopy(actual)
        a = torch.optim.SGD([p for p in actual.parameters() if p.requires_grad], lr=.01)
        b = torch.optim.SGD([p for p in expected.parameters() if p.requires_grad], lr=.01)
        actual.train(); expected.train()
        adapt.update_group(actual, a, self.fit, [0, 1], 1e9)
        losses = []
        for clip in (0, 1):
            inputs, phones, windows, scalars, frames, targets, _ = self.fit.clip(clip)
            losses.append(-(targets * expected(inputs, phones, windows, scalars, frames).log_softmax(-1)).sum())
        (sum(losses) / 3).backward()
        b.step()
        for left, right in zip(actual.parameters(), expected.parameters(), strict=True):
            torch.testing.assert_close(left, right, atol=0, rtol=0)

    def test_update_boundary_resume_matches_uninterrupted_weights_optimizer_rng_predictions(self):
        continuous = self.make_run('continuous')
        self.run_loop(continuous)
        resumed = self.make_run('resumed')
        original, calls = adapt.update_group, 0
        def interrupt(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4:
                # No partial optimizer update is committed at this boundary.
                raise RuntimeError('synthetic interruption')
            return original(*args, **kwargs)
        with patch.object(adapt, 'update_group', side_effect=interrupt), self.assertRaisesRegex(RuntimeError, 'interruption'):
            self.run_loop(resumed)
        restored = self.make_run('unused')
        restored[2].output, restored[2].resume = resumed[2].output, True
        self.run_loop(restored)
        for filename in ('best.pt', 'last.pt'):
            left, right = [torch.load(run[2].output / filename, weights_only=True) for run in (continuous, restored)]
            for key in ('head', 'encoder'):
                self.assertEqual(set(left[key]), set(right[key]))
                for name in left[key]:
                    torch.testing.assert_close(left[key][name], right[key][name], atol=0, rtol=0)
            self.assertEqual(left['progress']['updates'], right['progress']['updates'])
            self.assertEqual(left['progress']['bestEpoch'], right['progress']['bestEpoch'])
            self.assertTrue(torch.equal(left['rng']['torch'], right['rng']['torch']))
            for param in left['optimizer']['state']:
                for key, value in left['optimizer']['state'][param].items():
                    torch.testing.assert_close(value, right['optimizer']['state'][param][key], atol=0, rtol=0)
        self.assertEqual(adapt.read_json(continuous[2].output / 'predictions.json'),
                         adapt.read_json(restored[2].output / 'predictions.json'))

    def test_epoch_zero_remains_real_selected_checkpoint_when_continuation_worsens(self):
        run = self.make_run('zero')
        reference = run[3]
        losses = iter([.2, .3, .4, .2])
        def evaluation(*unused):
            return {'allAges': {'macroTargetLogLoss': next(losses)}}, reference
        self.recipe['patienceEpochs'] = 2
        with patch.object(adapt, 'evaluate', side_effect=evaluation):
            progress, _, _ = self.run_loop(run)
        self.assertEqual(progress['bestEpoch'], 0)
        self.assertEqual(len(progress['history']), 3)
        saved = torch.load(run[2].output / 'best.pt', weights_only=True)
        self.assertEqual(saved['progress']['updates'], 0)
        self.assertEqual(saved['progress']['bestEpoch'], 0)
        self.assertEqual(adapt.read_json(run[2].output / 'epoch-zero-predictions.json'), reference)

    def test_epoch_zero_discrepancy_stops_before_any_update_and_preserves_diagnostic(self):
        run = self.make_run('mismatch')
        run[3]['probabilities'][0] = [0., 0., 1.]
        with patch.object(adapt, 'update_group') as update, self.assertRaisesRegex(ValueError, 'discrepancy'):
            self.run_loop(run)
        update.assert_not_called()
        self.assertTrue((run[2].output / 'epoch-zero.json').is_file())
        self.assertFalse((run[2].output / 'last.pt').exists())

    def test_resume_rejects_changed_selected_checkpoint_and_config_or_moments(self):
        run = self.make_run('tamper')
        self.run_loop(run)
        saved = torch.load(run[2].output / 'last.pt', weights_only=True)
        for key, replacement in [('configSha256', 'wrong'), ('mean', torch.ones(1037))]:
            modified = {**saved, key: replacement}
            with self.assertRaisesRegex(ValueError, 'config or fixed'):
                adapt.restore_checkpoint(modified, run[0], run[1], np.random.default_rng(7),
                                         adapt.digest(run[2].output / 'config.json'), 'cpu')
        chosen = run[2].output / saved['progress']['bestCheckpoint']
        with chosen.open('ab') as stream:
            stream.write(b'tampered')
        run[2].resume = True
        with self.assertRaisesRegex(ValueError, 'selected checkpoint changed'):
            self.run_loop(run)

    def test_raw_data_binds_scalar_values_and_original_windows_by_row_identity(self):
        cohort = {'clips': [{'id': '000010011', 'speakerId': '0001', 'sampleCount': 1600,
                             'audioPath': 'synthetic.wav', 'audioSha256': 'synthetic'}], 'rows': []}
        for target in (0, 1):
            cohort['rows'].append({'clipIndex': 0, 'clipId': '000010011', 'speakerId': '0001',
                'targetId': target, 'targetPhone': ('B', 'P')[target], 'trainingEligible': True, 'raterCounts': [1, 1, 3]})
        original = self.root / 'features.json'
        adapt.atomic_json(original, {'rows': [{'rowIndex': 0, 'estimatedPoolingWindowFrames': [0, 2]},
                                              {'rowIndex': 1, 'estimatedPoolingWindowFrames': [2, 4]}]})
        data = {'cohort': cohort, 'scalars': np.stack([np.full(13, 9, np.float32), np.full(13, 4, np.float32)]),
                'positions': {0: 1, 1: 0}, 'originalFeaturesPath': str(original)}
        def processor(x, **unused):
            return {'input_values': torch.tensor(x)[None], 'attention_mask': torch.ones(1, len(x), dtype=torch.long)}
        raw = adapt.RawTargetData(data, [1, 0], processor, 'cpu')
        with patch('multiphone_adapt.read_rating_pcm', return_value=torch.ones(1600)):
            _, phones, windows, scalars, frames, _, indices = raw.clip(0)
        self.assertEqual(indices, [1, 0])
        self.assertEqual(phones.tolist(), [1, 0])
        self.assertEqual(windows, [[2, 4], [0, 2]])
        self.assertEqual(scalars[:, 0].tolist(), [9., 4.])
        self.assertEqual(frames, 4)

    def test_epoch_zero_predictions_cannot_be_changed_after_selection_or_before_resume(self):
        run = self.make_run('zero-tamper')
        self.run_loop(run)
        record = run[2].output / 'epoch-zero-predictions.json'
        with record.open('ab') as stream:
            stream.write(b' ')
        run[2].resume = True
        with self.assertRaisesRegex(ValueError, 'epoch-zero artifacts changed'):
            self.run_loop(run)

    def test_config_byte_mutation_during_update_or_final_evaluation_is_rejected(self):
        self.recipe['maximumEpochs'] = 1
        for stage in ('first-update', 'final-evaluation'):
            with self.subTest(stage=stage):
                run = self.make_run(stage)
                update, evaluation = adapt.update_group, adapt.evaluate
                calls = 0
                def changed_update(*args, **kwargs):
                    result = update(*args, **kwargs)
                    with (run[2].output / 'config.json').open('ab') as stream:
                        stream.write(b' ')
                    return result
                def changed_evaluation(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    result = evaluation(*args, **kwargs)
                    if calls == 3:
                        with (run[2].output / 'config.json').open('ab') as stream:
                            stream.write(b' ')
                    return result
                target, replacement = ('update_group', changed_update) if stage == 'first-update' else ('evaluate', changed_evaluation)
                with patch.object(adapt, target, side_effect=replacement), self.assertRaisesRegex(ValueError, 'configuration changed'):
                    self.run_loop(run)


if __name__ == '__main__':
    unittest.main()
