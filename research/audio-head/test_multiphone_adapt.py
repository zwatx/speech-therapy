"""Synthetic adaptation tests; no corpus audio or external weights are loaded."""
import contextlib
import copy
import hashlib
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

import multiphone_adapt as adapt


class TinyLayer(nn.Module):
    def __init__(self):
        super().__init__()
        self.scale = nn.Parameter(torch.tensor(0.8))
        self.bias = nn.Parameter(torch.tensor(0.1))
        self.dropout = nn.Dropout(0.5)

    def forward(self, value):
        return self.dropout(value*self.scale+self.bias)


class TinyEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.feature_extractor = TinyLayer()
        self.encoder = nn.Module()
        self.encoder.layers = nn.ModuleList([TinyLayer() for _ in range(3)])

    def forward(self, input_values):
        value = self.feature_extractor(input_values)
        for layer in self.encoder.layers:
            value = layer(value)
        # Vary dimensions to avoid a constant all-dimension feature fixture.
        frames = value.unsqueeze(-1)*torch.linspace(0.5, 1.5, 768, device=value.device)
        return SimpleNamespace(last_hidden_state=frames)


def processor(samples, **unused):
    return {'input_values': torch.from_numpy(samples.copy()).float().unsqueeze(0)}


def encoder_loader(*unused, **keywords):
    assert keywords['allow_download'] is False
    return SimpleNamespace(model=TinyEncoder(), processor=processor, identity={'kind': 'synthetic-test'})


class AdaptationTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.temporary = tempfile.TemporaryDirectory(prefix='cadence-adaptation-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in adapt.SOURCES:
            (self.root/name).write_bytes((adapt.HERE/name).read_bytes())
        self.cohort = {'clips': [], 'rows': []}
        for index in range(6):
            self.cohort['clips'].append({'id': str(index), 'speakerId': str(index),
                'audioPath': str(self.root/f'{index}.wav'), 'audioSha256': hashlib.sha256(str(index).encode()).hexdigest()})
            for target in (0, 1):
                self.cohort['rows'].append({'clipIndex': index, 'clipId': str(index), 'speakerId': str(index),
                    'targetId': target, 'targetPhone': ('B', 'P')[target], 'trainingEligible': True,
                    'raterCounts': [3, 1, 1] if target == 0 else [0, 1, 4], 'age': 8+index})
        self.fold = {'innerFitRows': list(range(6)), 'innerValidationRows': [6, 7],
                     'outerFitRows': list(range(8)), 'outerHoldoutRows': list(range(8, 12))}
        self.cohort_path = self.root/'cohort.json'
        self.splits_path = self.root/'splits.json'
        self.cache = self.root/'cache'
        self.cache.mkdir()
        self.persist()

    def persist(self):
        adapt.atomic_json(self.cohort_path, self.cohort)
        canonical = hashlib.sha256(json.dumps(self.cohort, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        adapt.atomic_json(self.splits_path, {'cohortCanonicalSha256': canonical, 'folds': [self.fold]})
        adapt.atomic_json(self.cache/'config.json', {'cohortSha256': adapt.digest(self.cohort_path),
                                                   'encoder': {'kind': 'synthetic-test'}})
        config_sha = adapt.digest(self.cache/'config.json')
        entries = {}
        for index, clip in enumerate(self.cohort['clips']):
            frames = np.broadcast_to(np.linspace(0, 1, index+3, dtype=np.float32)[:, None]+index, (index+3, 768)).copy()
            path = self.cache/f'{index}.npz'
            np.savez(path, frames=frames, audio_sha256=clip['audioSha256'], config_sha256=config_sha)
            entries[str(index)] = {'path': path.name, 'sha256': adapt.digest(path)}
        adapt.atomic_json(self.cache/'index.json', {'complete': True, 'configSha256': config_sha, 'entries': entries})

    def args(self, name='inner', **updates):
        result = SimpleNamespace(cohort=self.cohort_path, splits=self.splits_path, cache=self.cache,
            output=self.root/'outputs'/name, encoder='wav2vec2-base', head='attention', phase='inner', fold=0,
            device='cpu', upper_layers=1, seed=7, hidden=8, dropout=0.1, backbone_lr=1e-5, head_lr=3e-4,
            weight_decay=0.01, max_gradient_norm=5., accumulation_clips=2, epochs=3, patience=3,
            threads=2, save_every_updates=1, warm_head=None, selection=None, resume=False, replay=False)
        for key, value in updates.items():
            setattr(result, key, value)
        return result

    @contextlib.contextmanager
    def environment(self):
        def audio(path, checksum):
            index = int(path.stem)
            self.assertEqual(checksum, self.cohort['clips'][index]['audioSha256'])
            return torch.linspace(0, 1, index+3)+index
        with patch.object(adapt, 'HERE', self.root), patch.object(adapt, 'load_encoder', side_effect=encoder_loader), \
             patch.object(adapt.RawStudyData, 'verify_audio'), patch.object(adapt, 'read_rating_pcm', side_effect=audio), \
             contextlib.redirect_stdout(io.StringIO()):
            yield

    def model(self, upper=1):
        return adapt.AdaptedRatingModel(TinyEncoder(), adapt.HEADS['attention'](hidden_dim=8, dropout=0),
                                       torch.zeros(768), torch.ones(768), upper)

    def test_only_upper_layers_and_head_receive_real_updates_with_backbone_dropout_off(self):
        for upper in (1, 2):
            model = self.model(upper)
            before = {name: value.detach().clone() for name, value in model.named_parameters()}
            model.train()
            self.assertTrue(model.head.training)
            self.assertTrue(all(not module.training for module in model.encoder.modules()))
            data = adapt.RawStudyData(self.cohort, list(range(6)), processor, 'cpu')
            optimizer = torch.optim.AdamW([value for value in model.parameters() if value.requires_grad], lr=0.01)
            with self.environment():
                loss, count, norm = adapt.update_group(model, optimizer, data, [0, 1], 5.)
            self.assertEqual(count, 4)
            self.assertGreater(loss, 0)
            self.assertGreater(norm, 0)
            changed = {name for name, value in model.named_parameters() if not torch.equal(value, before[name])}
            self.assertTrue(any(name.startswith('head.') for name in changed))
            self.assertTrue(any(name.startswith('encoder.encoder.layers.2.') for name in changed))
            for name, value in model.named_parameters():
                if not value.requires_grad:
                    self.assertNotIn(name, changed)
                    self.assertIsNone(value.grad)
            saved = model.adapted_state()
            self.assertEqual(set(saved), set(model.trainable_encoder_names))
            with self.assertRaisesRegex(ValueError, 'allowed'):
                model.restore_adapted_state({**saved, 'feature_extractor.scale': torch.tensor(1.)})

    def test_invalid_layers_ineligible_targets_and_padded_audio_are_rejected(self):
        for upper in (0, 3):
            with self.assertRaises(ValueError):
                self.model(upper)
        model = self.model()
        with self.assertRaisesRegex(ValueError, 'single clip'):
            model({'input_values': torch.ones(2, 3)}, torch.tensor([[0], [0]]))
        with self.assertRaisesRegex(ValueError, 'eligible'):
            model({'input_values': torch.ones(1, 3)}, torch.tensor([[23]]))
        duplicate = copy.deepcopy(self.cohort)
        duplicate['rows'][1].update(targetId=0, targetPhone='B')
        with self.assertRaisesRegex(ValueError, 'more than once'):
            adapt.RawStudyData(duplicate, [0, 1], processor, 'cpu')

    def test_accumulation_uses_target_row_weighting_for_unequal_clip_targets(self):
        model = self.model()
        expected = copy.deepcopy(model)
        data = adapt.RawStudyData(self.cohort, [0, 1, 2], processor, 'cpu')
        optimizer = torch.optim.SGD([p for p in model.parameters() if p.requires_grad], lr=0.01)
        expected_optimizer = torch.optim.SGD([p for p in expected.parameters() if p.requires_grad], lr=0.01)
        model.train(); expected.train()
        with self.environment():
            adapt.update_group(model, optimizer, data, [0, 1], 1e9)
            losses = []
            for index in [0, 1]:
                inputs, phones, targets, _ = data.clip(index)
                losses.append(-(targets*expected(inputs, phones).log_softmax(-1)).sum())
            (sum(losses)/3).backward()
            expected_optimizer.step()
        for actual, reference in zip(model.parameters(), expected.parameters(), strict=True):
            torch.testing.assert_close(actual, reference)

    def test_resume_reproduces_uninterrupted_optimizer_rng_and_predictions(self):
        uninterrupted = self.args('continuous')
        resumed = self.args('interrupted')
        with self.environment():
            adapt.train(uninterrupted)
            original = adapt.update_group
            count = 0
            def interrupted(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 4:
                    raise RuntimeError('intentional interruption after saved optimizer update')
                return original(*args, **kwargs)
            with patch.object(adapt, 'update_group', side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, 'intentional'):
                    adapt.train(resumed)
            resumed.resume = True
            adapt.train(resumed)
            replay = adapt.replay(resumed.output, 'cpu')
        self.assertEqual(replay['maximumAbsoluteProbabilityDifference'], 0.)
        for name in ('best.pt', 'last.pt'):
            a = torch.load(uninterrupted.output/name, weights_only=True)
            b = torch.load(resumed.output/name, weights_only=True)
            for key in ('encoder', 'head'):
                for parameter in a[key]:
                    torch.testing.assert_close(a[key][parameter], b[key][parameter], rtol=0, atol=0)
            self.assertEqual(a['progress']['updates'], b['progress']['updates'])
            self.assertEqual(a['progress']['bestEpoch'], b['progress']['bestEpoch'])
        self.assertEqual(json.loads((uninterrupted.output/'predictions.json').read_text()),
                         json.loads((resumed.output/'predictions.json').read_text()))
        resumed.head_lr = 0.001
        with self.environment(), self.assertRaisesRegex(ValueError, 'configuration'):
            adapt.train(resumed)

    def test_inner_stops_on_validation_only_and_never_loads_outer_audio(self):
        args = self.args(epochs=6, patience=2)
        # An invalid outer label must never be inspected by an inner run.
        self.cohort['rows'][8]['raterCounts'] = [-1, 0, 6]
        self.persist()
        values = iter([3., 1., 2., 2.5, 1.])
        observed = []
        def evaluate(model, data, rows):
            observed.append(list(rows))
            self.assertEqual(rows, self.fold['innerValidationRows'])
            return {'macroTargetLogLoss': next(values)}, {'rowIndices': rows}
        with self.environment(), patch.object(adapt, 'evaluate', side_effect=evaluate):
            report = adapt.train(args)
        self.assertEqual((report['bestEpoch'], report['epochsRun']), (2, 4))
        self.assertEqual(len(observed), 5)

    def test_outer_requires_matching_selection_and_defers_holdout_until_after_fit(self):
        inner = self.args(epochs=2)
        with self.environment():
            adapt.train(inner)
        outer = self.args('outer', phase='outer', epochs=99, selection=inner.output/'report.json')
        selected = json.loads(outer.selection.read_text())['bestEpoch']
        calls = []
        def evaluate(model, data, rows):
            calls.append(list(rows))
            self.assertEqual(rows, self.fold['outerHoldoutRows'])
            history = json.loads((outer.output/'history.json').read_text())
            self.assertEqual(len(history), selected)
            self.assertTrue(all('validation' not in record for record in history))
            return {'macroTargetLogLoss': 1000.}, {'rowIndices': rows}
        with self.environment(), patch.object(adapt, 'evaluate', side_effect=evaluate):
            result = adapt.train(outer)
        self.assertEqual(calls, [self.fold['outerHoldoutRows']])
        self.assertEqual(result['epochsRun'], selected)
        outer.backbone_lr = 0.0001
        with self.assertRaisesRegex(ValueError, 'selected inner'):
            adapt.selected_epochs(outer)
        outer.selection = None
        with self.assertRaisesRegex(ValueError, 'requires'):
            adapt.selected_epochs(outer)
        outer.selection = inner.output/'report.json'
        outer.backbone_lr = inner.backbone_lr
        (self.root/'multiphone_adapt.py').write_text('changed implementation')
        with self.environment(), self.assertRaisesRegex(ValueError, 'Implementation changed'):
            adapt.selected_epochs(outer)

    def test_warm_head_rejects_wrong_fold_and_restores_matching_parameters(self):
        args = self.args()
        frozen = adapt.StudyData(self.cohort, self.cache, self.fold['innerFitRows'])
        mean, std = frozen.normalization(frozen.clip_ids)
        model = adapt.AdaptedRatingModel(TinyEncoder(), adapt.HEADS['attention'](hidden_dim=8, dropout=0.1), mean, std, 1)
        directory = self.root/'frozen'
        directory.mkdir()
        config = {'cohortSha256': adapt.digest(args.cohort), 'splitsSha256': adapt.digest(args.splits),
            'cacheIndexSha256': frozen.index_sha256, 'fold': 0, 'phase': 'inner', 'head': 'attention',
            'hidden': 8, 'dropout': 0.1, 'seed': 7,
            'sourceSha256': {name: adapt.digest(adapt.HERE/name) for name in ('multiphone_train.py', 'multiphone_models.py')}}
        adapt.atomic_json(directory/'config.json', config)
        saved_head = copy.deepcopy(model.head.state_dict())
        path = directory/'best.pt'
        adapt.save_checkpoint(path, {'configSha256': adapt.digest(directory/'config.json'),
            'model': saved_head, 'mean': mean, 'std': std, 'epoch': 2})
        adapt.atomic_json(directory/'report.json', {'configSha256': adapt.digest(directory/'config.json'),
                                                   'checkpointSha256': adapt.digest(path), 'bestEpoch': 2})
        with torch.no_grad():
            next(model.head.parameters()).add_(1.)
        adapt.initialize_warm_head(path, args, model, frozen.index_sha256)
        for name, value in model.head.state_dict().items():
            torch.testing.assert_close(value, saved_head[name])
        args.fold = 1
        with self.assertRaisesRegex(ValueError, 'same fold'):
            adapt.initialize_warm_head(path, args, model, frozen.index_sha256)
        args.fold = 0
        path.write_bytes(path.read_bytes()+b'changed checkpoint')
        with self.assertRaisesRegex(ValueError, 'completed frozen'):
            adapt.initialize_warm_head(path, args, model, frozen.index_sha256)

    def test_epoch_selection_and_resume_remain_consistent_across_both_checkpoint_boundaries(self):
        for boundary in ('after-selection', 'after-last'):
            with self.subTest(boundary=boundary):
                args = self.args(boundary, epochs=2)
                save = adapt.save_checkpoint
                crashed = False
                def interrupt(path, value):
                    nonlocal crashed
                    save(path, value)
                    progress = value['progress']
                    trigger = ((boundary == 'after-selection' and path.name == 'selected-epoch-0002.pt')
                               or (boundary == 'after-last' and path.name == 'last.pt'
                                   and len(progress['history']) == 2))
                    if trigger and not crashed:
                        crashed = True
                        raise RuntimeError('checkpoint boundary interruption')
                # Improvement is determined from epoch progress, so a repeated
                # interrupted epoch receives the same controlled validation loss.
                def evaluate(model, data, rows):
                    history_path = args.output/'history.json'
                    completed = len(json.loads(history_path.read_text())) if history_path.exists() else 0
                    return {'macroTargetLogLoss': 3.-min(completed, 1)}, {'rowIndices': rows}
                with self.environment(), patch.object(adapt, 'evaluate', side_effect=evaluate):
                    with patch.object(adapt, 'save_checkpoint', side_effect=interrupt):
                        with self.assertRaisesRegex(RuntimeError, 'boundary'):
                            adapt.train(args)
                    args.resume = True
                    report = adapt.train(args)
                self.assertTrue(crashed)
                best = torch.load(args.output/'best.pt', weights_only=True)
                last = torch.load(args.output/'last.pt', weights_only=True)
                self.assertEqual(report['bestEpoch'], 2)
                self.assertEqual(best['progress']['bestEpoch'], 2)
                self.assertEqual(last['progress']['bestCheckpointSha256'], adapt.digest(args.output/'best.pt'))
                self.assertEqual(len(json.loads((args.output/'history.json').read_text())), 2)

    def test_replay_rejects_replaced_checkpoint_even_when_config_binding_matches(self):
        args = self.args(epochs=1)
        with self.environment():
            adapt.train(args)
            path = args.output/'best.pt'
            path.write_bytes(path.read_bytes()+b'changed checkpoint')
            with self.assertRaisesRegex(ValueError, 'completed run report'):
                adapt.replay(args.output, 'cpu')


if __name__ == '__main__':
    unittest.main()
