"""Warm adaptation orchestration tests with synthetic subprocess artifacts."""
import contextlib
from copy import deepcopy
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch
import unittest

import torch
import numpy as np

import multiphone_warm_queue as queue
import test_multiphone_adapt_queue as fixture_module


class WarmQueueTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.AdaptationQueueTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.base = self.fixture.root, self.fixture.base
        # Tiny real cached frames permit exact frozen-head replay without an encoder.
        for row in self.fixture.cohort['rows']:
            row.update(trainingEligible=True, targetId=0)
        queue.atomic_json(self.base/'cohort.json', self.fixture.cohort)
        splits = queue.read_json(self.base/'splits.json')
        splits['cohortCanonicalSha256'] = hashlib.sha256(json.dumps(self.fixture.cohort, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        queue.atomic_json(self.base/'splits.json', splits)
        for encoder in queue.shared.CACHE:
            cache = self.base/queue.shared.CACHE[encoder]
            config = queue.read_json(cache/'config.json')
            config['cohortSha256'] = queue.digest(self.base/'cohort.json')
            queue.atomic_json(cache/'config.json', config)
            index = queue.read_json(cache/'index.json')
            index['configSha256'] = queue.digest(cache/'config.json')
            for number, clip in enumerate(self.fixture.cohort['clips']):
                frames = np.broadcast_to((np.arange(3, dtype=np.float32)+5*number)[:, None], (3, 768)).copy()
                path = cache/index['entries'][clip['id']]['path']
                np.savez(path, frames=frames, audio_sha256=clip['audioSha256'], config_sha256=index['configSha256'])
                index['entries'][clip['id']]['sha256'] = queue.digest(path)
            queue.atomic_json(cache/'index.json', index)
        for name in queue.HELPERS:
            (self.root/name).write_bytes((queue.HERE/name).read_bytes())
        self.recipe_path = self.root/'warm-recipe.json'
        self.recipe = queue.read_json(queue.RECIPE)
        self.recipe.update(cohortSha256=queue.digest(self.base/'cohort.json'),
                           splitsSha256=queue.digest(self.base/'splits.json'))
        self.recipe['sourceSha256'] = {name: queue.digest(self.root/name) for name in self.recipe['sourceSha256']}
        self.ledger = self.base/'warm-ledger.json'
        self.head = queue.adapt.HEADS['mean'](hidden_dim=128, dropout=.1)
        with torch.no_grad():
            for parameter in self.head.parameters():
                parameter.zero_()
            self.head.classifier[-1].bias.copy_(torch.tensor([.1, .2, .7]).log())
        data = queue.frozen.StudyData(self.fixture.cohort, self.base/'wav2vec-frames', [0, 1])
        self.mean, self.std = data.normalization([0])
        self.baseline_metrics, self.baseline_predictions = queue.frozen.evaluate(self.head, data, [1], self.mean, self.std, 'cpu', 16)
        for baseline in self.recipe['baselines']:
            encoder = baseline['encoder']
            directory = self.base/('frozen-'+queue.shared.SHORT[encoder])
            directory.mkdir()
            config = {'cohortSha256': self.recipe['cohortSha256'], 'splitsSha256': self.recipe['splitsSha256'],
                'cacheIndexSha256': queue.digest(self.base/queue.shared.CACHE[encoder]/'index.json'),
                'phase': 'inner', 'fold': 0, 'seed': 7, 'head': 'mean', 'hidden': 128, 'dropout': .1, 'lr': .0003, 'batch_size': 16,
                'sourceSha256': {name: queue.digest(self.root/name) for name in
                                ('multiphone_train.py', 'multiphone_models.py', 'multiphone_cache.py')}}
            queue.atomic_json(directory/'config.json', config)
            saved = {'configSha256': queue.digest(directory/'config.json'), 'epoch': baseline['selectedEpoch'],
                     'mean': self.mean, 'std': self.std, 'model': self.head.state_dict()}
            torch.save(saved, directory/'best.pt')
            queue.atomic_json(directory/'report.json', {'configSha256': queue.digest(directory/'config.json'),
                'checkpointSha256': queue.digest(directory/'best.pt'), 'bestEpoch': baseline['selectedEpoch'],
                'evaluation': self.baseline_metrics})
            queue.atomic_json(directory/'predictions.json', self.baseline_predictions)
            baseline.update(checkpointPath=str(directory/'best.pt'), checkpointSha256=queue.digest(directory/'best.pt'),
                configSha256=queue.digest(directory/'config.json'), reportSha256=queue.digest(directory/'report.json'),
                innerMacroTargetLogLoss=self.baseline_metrics['macroTargetLogLoss'])
        queue.atomic_json(self.recipe_path, self.recipe)
        self.locked = queue.digest(self.recipe_path)
        self.fixture.control['recipe'] = str(self.recipe_path)
        queue.atomic_json(self.root/'child-fixtures.json', self.fixture.control)

    @contextlib.contextmanager
    def environment(self):
        with patch.object(queue, 'HERE', self.root), patch.object(queue, 'RECIPE', self.recipe_path), \
             patch.object(queue, 'LOCKED_RECIPE_SHA', self.locked), contextlib.redirect_stdout(io.StringIO()):
            yield

    def contract(self):
        with self.environment():
            return queue.capture_contract(self.base)

    def prepare(self, arguments, contract, probabilities=None):
        location = self.fixture.fixtures/Path(arguments['output']).name
        location.mkdir()
        encoder = arguments['encoder']
        config = arguments | {'sourceSha256': contract['sourceSha256'], 'cohortSha256': contract['cohortSha256'],
            'splitsSha256': contract['splitsSha256'], 'cacheIndexSha256': contract['caches'][encoder]['indexSha256'],
            'encoderIdentity': queue.shared.IDENTITIES[encoder], 'warmStart': contract['baselines'][encoder]['warmStart'],
            'torch': contract['torch'], 'numpy': contract['numpy'],
            'normalization': 'fixed frame moments from fit speakers only in pinned frozen encoder cache',
            'encoderMode': 'eval; upper transformer layers receive gradients; lower weights/preprocessor frozen',
            'authorPartition': 'train', 'authorTestInferencePerformed': False, 'clinicalUseEligible': False,
            'learnerFeedbackEligible': False, 'fitRows': [0], 'evaluationRows': [1],
            'trainableEncoderNames': ['encoder.layers.11.attention.k_proj.weight'], 'trainableEncoderParameters': 1,
            'trainableHeadParameters': sum(value.numel() for value in self.head.parameters())}
        queue.atomic_json(location/'config.json', config)
        predictions = {'rowIndices': [1], 'probabilities': probabilities or [[.02, .18, .8]]}
        evaluation = queue.metrics_for(predictions, self.fixture.cohort, [1])
        history = [{'epoch': epoch, 'trainPerRaterLogLoss': .6, 'validation': evaluation if epoch == 1 else
                    {'macroTargetLogLoss': evaluation['macroTargetLogLoss']+.1}} for epoch in range(1, 4)]
        progress = {'epoch': 2, 'order': [], 'cursor': 0, 'updates': 1, 'bestEpoch': 1,
                    'bestLoss': evaluation['macroTargetLogLoss'], 'history': history[:1]}
        saved = {'schemaVersion': 1, 'encoder': {'encoder.layers.11.attention.k_proj.weight': torch.ones(1)},
                 'head': self.head.state_dict(), 'mean': self.mean, 'std': self.std,
                 'progress': progress, 'configSha256': queue.digest(location/'config.json'),
                 'encoderIdentity': config['encoderIdentity']}
        torch.save(saved, location/'best.pt')
        queue.atomic_json(location/'predictions.json', predictions)
        queue.atomic_json(location/'history.json', history)
        queue.atomic_json(location/'status.json', {'complete': True})
        queue.atomic_json(location/'report.json', {'complete': True, 'configSha256': queue.digest(location/'config.json'),
            'checkpointSha256': queue.digest(location/'best.pt'), 'bestEpoch': 1, 'epochsRun': 3,
            'evaluation': evaluation, 'evaluationRole': 'inner selection', 'clinicalUseEligible': False,
            'learnerFeedbackEligible': False})
        return location

    def prepared(self):
        contract = self.contract()
        arguments = queue.job_arguments(contract)
        for argument in arguments:
            self.prepare(argument, contract)
        return contract, arguments

    def run_queue(self):
        with self.environment():
            return queue.run(self.base, self.ledger)

    def test_fixed_order_and_each_warm_head_binds_its_matching_encoder(self):
        contract = self.contract()
        jobs = queue.job_arguments(contract)
        self.assertEqual([(job['encoder'], job['backbone_lr']) for job in jobs],
                         [('wav2vec2-base', 1e-6), ('wavlm-base-plus', 1e-6),
                          ('wav2vec2-base', 3e-6), ('wavlm-base-plus', 3e-6)])
        for job in jobs:
            self.assertEqual(job['warm_head'], contract['baselines'][job['encoder']]['warmStart']['path'])
            self.assertEqual((job['head'], job['head_lr'], job['epochs'], job['patience']), ('mean', 3e-5, 6, 2))

    def test_baseline_predictions_and_immutable_checkpoint_digest_are_checked(self):
        path = Path(self.recipe['baselines'][0]['checkpointPath'])
        prediction_path = path.parent/'predictions.json'
        queue.atomic_json(prediction_path, {'rowIndices': [1], 'probabilities': [[.2, .2, .6]]})
        with self.environment(), self.assertRaisesRegex(ValueError, 'proper metrics'):
            queue.capture_contract(self.base)
        queue.atomic_json(prediction_path, self.baseline_predictions)
        path.write_bytes(path.read_bytes()+b'changed baseline')
        with self.environment(), self.assertRaisesRegex(ValueError, 'baseline artifact'):
            queue.capture_contract(self.base)

    def test_four_tiny_children_run_serially_and_keep_external_epoch_zero_comparison(self):
        self.prepared()
        ledger = self.run_queue()
        self.assertTrue(ledger['complete'])
        self.assertEqual(len(self.fixture.launches()), 4)
        for first, second in zip(ledger['jobs'], ledger['jobs'][1:]):
            self.assertLessEqual(first['finishedAt'], second['startedAt'])
        self.assertTrue(all(job['exitCode'] == 0 and job['evidence']['selectedCandidate'] == 'adapted' for job in ledger['jobs']))
        self.assertTrue(all(row['backboneLR'] == 1e-6 for row in ledger['selected'].values()))

    def test_rehashed_baseline_head_or_moments_cannot_replace_epoch_zero_predictions(self):
        baseline = self.recipe['baselines'][0]
        path = Path(baseline['checkpointPath'])
        original = path.read_bytes()
        report_path = path.parent/'report.json'
        original_report = report_path.read_bytes()
        for change, expected_error in [('weights', 'exactly replay'), ('mean', 'fit-only cache')]:
            path.write_bytes(original)
            report_path.write_bytes(original_report)
            saved = torch.load(path, weights_only=True)
            if change == 'weights':
                saved['model']['classifier.3.bias'][0] += 1.
            else:
                saved['mean'][0] += 1.
            torch.save(saved, path)
            report = queue.read_json(report_path)
            report['checkpointSha256'] = queue.digest(path)
            queue.atomic_json(report_path, report)
            baseline.update(checkpointSha256=queue.digest(path), reportSha256=queue.digest(report_path))
            queue.atomic_json(self.recipe_path, self.recipe)
            self.locked = queue.digest(self.recipe_path)
            with self.environment(), self.assertRaisesRegex(ValueError, expected_error):
                queue.capture_contract(self.base)

    def test_exact_ties_and_worse_adaptation_keep_baseline_then_smaller_rate(self):
        contract = self.contract()
        jobs = [{'arguments': argument, 'evidence': {'adaptedMacroNLL': contract['baselines'][argument['encoder']]['evaluation']['macroTargetLogLoss'],
                 'checkpointSha256': 'adapted', 'bestEpoch': 1}} for argument in queue.job_arguments(contract)]
        selected = queue.select_candidates(contract, jobs)
        self.assertTrue(all(row['kind'] == 'frozen-baseline' and row['additionalEpochs'] == 0 for row in selected.values()))
        for job in jobs:
            job['evidence']['adaptedMacroNLL'] += .1
        self.assertTrue(all(row['kind'] == 'frozen-baseline' for row in queue.select_candidates(contract, jobs).values()))
        for job in jobs:
            job['evidence']['adaptedMacroNLL'] = .1
        self.assertTrue(all(row['backboneLR'] == 1e-6 for row in queue.select_candidates(contract, jobs).values()))

    def test_exact_warm_metadata_normalization_and_prediction_metrics_checked(self):
        contract = self.contract()
        arguments = queue.job_arguments(contract)[0]
        location = self.prepare(arguments, contract)
        config_path = location/'config.json'
        original = config_path.read_bytes()
        config = queue.read_json(config_path)
        config['warmStart']['epoch'] += 1
        queue.atomic_json(config_path, config)
        with self.assertRaisesRegex(ValueError, 'warmStart'):
            queue.verify_complete(location, arguments, contract)
        config_path.write_bytes(original)
        prediction_path = location/'predictions.json'
        queue.atomic_json(prediction_path, {'rowIndices': [1], 'probabilities': [[.2, .2, .6]]})
        with self.assertRaisesRegex(ValueError, 'proper metrics'):
            queue.verify_complete(location, arguments, contract)

    def test_partial_or_live_outputs_and_existing_ledger_refuse_launch(self):
        _, arguments = self.prepared()
        output = Path(arguments[0]['output'])
        output.mkdir()
        with self.assertRaisesRegex(ValueError, 'partial warm output'):
            self.run_queue()
        queue.atomic_json(output/'status.json', {'pid': os.getpid()})
        with self.assertRaisesRegex(ValueError, 'live PID'):
            self.run_queue()
        shutil.rmtree(output)
        queue.atomic_json(self.ledger, {'pid': os.getpid(), 'jobs': []})
        with self.assertRaisesRegex(ValueError, 'live PID'):
            self.run_queue()
        self.assertEqual(self.fixture.launches(), [])

    def test_child_failure_stops_before_second_launch(self):
        _, arguments = self.prepared()
        self.fixture.control['modes'][Path(arguments[0]['output']).name] = 'fail'
        queue.atomic_json(self.root/'child-fixtures.json', self.fixture.control)
        with self.assertRaisesRegex(RuntimeError, 'Child exited 3'):
            self.run_queue()
        ledger = queue.read_json(self.ledger)
        self.assertFalse(ledger['complete'])
        self.assertEqual(len(self.fixture.launches()), 1)
        self.assertEqual(ledger['jobs'][0]['exitCode'], 3)

    def test_changed_baseline_or_recipe_and_global_lock_block_launch(self):
        contract = self.contract()
        baseline_path = Path(self.recipe['baselines'][0]['checkpointPath'])
        baseline_path.write_bytes(baseline_path.read_bytes()+b'changed')
        with self.environment(), self.assertRaisesRegex(ValueError, 'baseline changed'):
            queue.guard(contract)
        with queue.shared.exclusive_lock(self.base/'adaptation-mps.lock'):
            with self.assertRaisesRegex(ValueError, 'execution lock'):
                self.run_queue()
        self.assertEqual(self.fixture.launches(), [])


if __name__ == '__main__':
    unittest.main()
