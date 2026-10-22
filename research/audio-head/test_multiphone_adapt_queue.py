"""Durable queue tests with tiny subprocess fixtures; no acoustic inference."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_adapt_queue as queue


FAKE_TRAINER = '''import json, pathlib, shutil, sys
here = pathlib.Path(__file__).parent
control = json.loads((here/'child-fixtures.json').read_text())
args = sys.argv[1:]
output = pathlib.Path(args[args.index('--output')+1])
mode = control.get('modes', {}).get(output.name, 'complete')
with (here/'launched.jsonl').open('a') as log:
    log.write(json.dumps({'run': output.name, 'args': args})+'\\n')
if mode == 'fail':
    raise SystemExit(3)
shutil.copytree(pathlib.Path(control['fixtures'])/output.name, output, dirs_exist_ok=True)
if mode == 'change-recipe':
    path = pathlib.Path(control['recipe'])
    path.write_text(path.read_text()+' ')
print('synthetic child complete')
'''


class AdaptationQueueTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        self.temporary = tempfile.TemporaryDirectory(prefix='cadence-adapt-queue-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.root/'outputs/study'
        self.base.mkdir(parents=True)
        self.fixtures = self.root/'fixtures'
        self.fixtures.mkdir()
        self.recipe_path = self.root/'recipe.json'
        self.recipe = json.loads(queue.RECIPE.read_text())
        self.cohort = {'clips': [{'id': str(i), 'audioSha256': str(i)*64} for i in range(3)],
                      'rows': [{'clipIndex': i, 'clipId': str(i), 'speakerId': str(i),
                                'raterCounts': [0, 1, 4], 'targetPhone': 'B', 'age': 8} for i in range(3)]}
        queue.atomic_json(self.base/'cohort.json', self.cohort)
        cohort_sha = hashlib.sha256(json.dumps(self.cohort, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        fold = {'innerFitRows': [0], 'innerValidationRows': [1], 'outerFitRows': [0, 1], 'outerHoldoutRows': [2]}
        queue.atomic_json(self.base/'splits.json', {'cohortCanonicalSha256': cohort_sha, 'folds': [fold]*5})
        self.recipe.update(cohortSha256=queue.digest(self.base/'cohort.json'), splitsSha256=queue.digest(self.base/'splits.json'))
        queue.atomic_json(self.recipe_path, self.recipe)
        for name in queue.SOURCES:
            (self.root/name).write_text(FAKE_TRAINER if name == 'multiphone_adapt.py' else '# synthetic source '+name)
        self.control = {'fixtures': str(self.fixtures), 'recipe': str(self.recipe_path), 'modes': {}}
        queue.atomic_json(self.root/'child-fixtures.json', self.control)
        for encoder in queue.CACHE:
            cache = self.base/queue.CACHE[encoder]
            cache.mkdir()
            queue.atomic_json(cache/'config.json', {'encoder': queue.IDENTITIES[encoder],
                                                    'cohortSha256': self.recipe['cohortSha256']})
            entries = {}
            for clip in self.cohort['clips']:
                file = cache/(clip['id']+'.npz')
                file.write_bytes(b'synthetic cached feature')
                entries[clip['id']] = {'path': file.name, 'sha256': queue.digest(file), 'audioSha256': clip['audioSha256']}
            queue.atomic_json(cache/'index.json', {'complete': True, 'configSha256': queue.digest(cache/'config.json'),
                                                  'entries': entries})
        self.locked = queue.digest(self.recipe_path)

    def args(self, **updates):
        value = SimpleNamespace(base=self.base, ledger=self.base/'queue.json', encoders=['wav2vec2-base'],
                                depths=[1], folds=[0], resume_existing=False)
        for name, item in updates.items():
            setattr(value, name, item)
        return value

    @contextlib.contextmanager
    def environment(self):
        with patch.object(queue, 'HERE', self.root), patch.object(queue, 'RECIPE', self.recipe_path), \
             patch.object(queue, 'LOCKED_RECIPE_SHA256', self.locked), contextlib.redirect_stdout(io.StringIO()):
            yield

    def contract(self, args):
        with self.environment():
            return queue.capture_contract(args)[1]

    def prepare(self, args, encoder='wav2vec2-base', depth=1, fold=0, *, existing=False, incomplete=False):
        contract = self.contract(args)
        arguments = queue.job_arguments(self.recipe, contract, encoder, depth, fold, 7)
        output = Path(arguments['output'])
        location = output if existing else self.fixtures/output.name
        location.mkdir()
        config = dict(arguments)
        config.update({'sourceSha256': contract['sourceSha256'], 'cohortSha256': contract['cohortSha256'],
            'splitsSha256': contract['splitsSha256'], 'cacheIndexSha256': contract['caches'][encoder]['indexSha256'],
            'encoderIdentity': queue.IDENTITIES[encoder], 'warmStart': None, 'torch': contract['torch'],
            'numpy': contract['numpy'], 'authorPartition': 'train', 'authorTestInferencePerformed': False,
            'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
            'normalization': 'fixed frame moments from fit speakers only in pinned frozen encoder cache',
            'encoderMode': 'eval; upper transformer layers receive gradients; lower weights/preprocessor frozen',
            'fitRows': [0], 'evaluationRows': [1],
            'trainableEncoderNames': ['encoder.layers.11.attention.k_proj.weight'],
            'trainableEncoderParameters': 1, 'trainableHeadParameters': 1})
        queue.atomic_json(location/'config.json', config)
        scores = queue.distribution_metrics(np.asarray([[0.1, 0.2, 0.7]]), np.asarray([[0, 1, 4]]))
        evaluation = dict(scores, perTarget={'B': scores}, macroTargetLogLoss=scores['perRaterLogLoss'],
                          ages6to12=scores, ages13plus=None)
        history = [{'epoch': epoch, 'trainPerRaterLogLoss': 0.6,
                    'validation': evaluation if epoch == 1 else {'macroTargetLogLoss': scores['perRaterLogLoss']+0.1}}
                   for epoch in range(1, 5)]
        progress = {'epoch': 2, 'order': [], 'cursor': 0, 'lossSum': 0., 'targetCount': 0, 'updates': 1,
                    'bestLoss': scores['perRaterLogLoss'], 'bestEpoch': 1, 'bestCheckpoint': 'selected-epoch-0001.pt',
                    'bestCheckpointSha256': None, 'history': history[:1], 'elapsedSeconds': 1.}
        checkpoint = {'schemaVersion': 1, 'encoder': {'encoder.layers.11.attention.k_proj.weight': torch.ones(1)},
            'head': {'weight': torch.ones(1)}, 'mean': torch.zeros(768), 'std': torch.ones(768),
            'optimizer': {'param_groups': [{}, {}], 'state': {}},
            'rng': {'torch': torch.get_rng_state(), 'mps': torch.zeros(16, dtype=torch.uint8),
                    'python': random.getstate(), 'numpy': np.random.default_rng(7).bit_generator.state},
            'progress': progress, 'configSha256': queue.digest(location/'config.json'),
            'encoderIdentity': config['encoderIdentity']}
        torch.save(checkpoint, location/'selected-epoch-0001.pt')
        shutil.copyfile(location/'selected-epoch-0001.pt', location/'best.pt')
        progress['bestCheckpointSha256'] = queue.digest(location/'selected-epoch-0001.pt')
        progress.update(epoch=5, history=history)
        torch.save(checkpoint, location/'last.pt')
        queue.atomic_json(location/'history.json', history)
        queue.atomic_json(location/'status.json', {'complete': not incomplete})
        queue.atomic_json(location/'predictions.json', {'rowIndices': [1], 'probabilities': [[0.1, 0.2, 0.7]]})
        if not incomplete:
            queue.atomic_json(location/'report.json', {'complete': True, 'configSha256': queue.digest(location/'config.json'),
                'checkpointSha256': queue.digest(location/'best.pt'), 'bestEpoch': 1, 'epochsRun': 4, 'evaluation': evaluation,
                'evaluationRole': 'inner selection', 'clinicalUseEligible': False, 'learnerFeedbackEligible': False})
        return output, location, arguments

    def run_queue(self, args):
        with self.environment():
            return queue.run(args)

    def launches(self):
        file = self.root/'launched.jsonl'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def test_requires_explicit_unique_subsets_and_dedicated_ledger(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            queue.parser().parse_args(['--ledger', 'q.json'])
        for arguments in (self.args(depths=[]), self.args(folds=[0, 0]), self.args(encoders=['unknown'])):
            with self.environment(), self.assertRaisesRegex(ValueError, 'subset'):
                queue.capture_contract(arguments)
        with self.assertRaisesRegex(ValueError, 'dedicated'):
            self.run_queue(self.args(ledger=self.base/'cohort.json'))

    def test_serial_children_get_all_explicit_flags_and_complete_artifact_evidence(self):
        args = self.args(folds=[0, 1])
        for fold in args.folds:
            self.prepare(args, fold=fold)
        ledger = self.run_queue(args)
        self.assertTrue(ledger['complete'])
        self.assertEqual(len(self.launches()), 2)
        first, second = (job['attempts'][0] for job in ledger['jobs'])
        self.assertLessEqual(first['childFinishedAt'], second['childStartedAt'])
        for job, launch in zip(ledger['jobs'], self.launches(), strict=True):
            attempt = job['attempts'][0]
            self.assertEqual((attempt['state'], attempt['exitCode']), ('complete', 0))
            self.assertGreater(attempt['pid'], 0)
            self.assertTrue(Path(attempt['log']).is_file())
            self.assertIn('checkpointSha256', attempt['evidence'])
            for key, value in job['arguments'].items():
                if value is not None:
                    index = launch['args'].index('--'+key.replace('_', '-'))
                    self.assertEqual(launch['args'][index+1], str(value))
        again = self.run_queue(args)
        self.assertEqual(len(self.launches()), 2)
        self.assertTrue(all(job['attempts'][-1]['state'] == 'already-complete' for job in again['jobs']))

    def test_completed_skip_checks_full_hyperparameters_and_checkpoint_digest(self):
        args = self.args()
        output, _, _ = self.prepare(args, existing=True)
        config_path = output/'config.json'
        original = config_path.read_bytes()
        config = json.loads(original)
        config['head_lr'] = 0.001
        queue.atomic_json(config_path, config)
        with self.assertRaisesRegex(ValueError, 'configuration'):
            self.run_queue(args)
        self.assertEqual(self.launches(), [])
        config_path.write_bytes(original)
        (output/'best.pt').write_bytes((output/'best.pt').read_bytes()+b'changed checkpoint')
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.run_queue(args)
        self.assertEqual(self.launches(), [])

    def test_incomplete_requires_explicit_resume_and_valid_checkpoint(self):
        args = self.args()
        output, _, arguments = self.prepare(args, existing=True, incomplete=True)
        self.prepare(args)  # Completed tiny child fixture for the resumed attempt.
        with self.assertRaisesRegex(ValueError, 'resume-existing'):
            self.run_queue(args)
        args.resume_existing = True
        last = (output/'last.pt').read_bytes()
        (output/'last.pt').write_bytes(b'not a checkpoint')
        with self.assertRaises(Exception):
            self.run_queue(args)
        self.assertEqual(self.launches(), [])
        (output/'last.pt').write_bytes(last)
        ledger = self.run_queue(args)
        self.assertEqual(ledger['jobs'][0]['attempts'][-1]['state'], 'complete')
        self.assertIn('--resume', self.launches()[0]['args'])
        self.assertIn('lastCheckpointSha256', ledger['jobs'][0]['attempts'][-1]['resumeEvidence'])

    def test_live_recorded_run_refuses_concurrent_resume(self):
        args = self.args(resume_existing=True)
        output, _, _ = self.prepare(args, existing=True, incomplete=True)
        queue.atomic_json(output/'status.json', {'complete': False, 'pid': os.getpid()})
        with self.assertRaisesRegex(ValueError, 'live recorded'):
            self.run_queue(args)
        self.assertEqual(self.launches(), [])

    def test_child_failure_stops_queue_without_retry_or_next_job(self):
        args = self.args(folds=[0, 1])
        for fold in args.folds:
            output, _, _ = self.prepare(args, fold=fold)
            if fold == 0:
                self.control['modes'][output.name] = 'fail'
        queue.atomic_json(self.root/'child-fixtures.json', self.control)
        with self.assertRaisesRegex(RuntimeError, 'exited 3'):
            self.run_queue(args)
        ledger = queue.load_json(args.ledger)
        self.assertFalse(ledger['complete'])
        self.assertEqual(len(self.launches()), 1)
        self.assertEqual(ledger['jobs'][0]['attempts'][0]['exitCode'], 3)
        self.assertEqual(ledger['jobs'][0]['state'], 'failed')

    def test_recipe_or_sources_changing_between_jobs_stops_before_next_launch(self):
        args = self.args(folds=[0, 1])
        for fold in args.folds:
            output, _, _ = self.prepare(args, fold=fold)
            if fold == 0:
                self.control['modes'][output.name] = 'change-recipe'
        queue.atomic_json(self.root/'child-fixtures.json', self.control)
        with self.assertRaisesRegex(ValueError, 'Recipe or queue source changed'):
            self.run_queue(args)
        self.assertEqual(len(self.launches()), 1)
        self.assertEqual(queue.load_json(args.ledger)['state'], 'failed')

    def test_feature_tampering_and_stale_ledger_contract_are_rejected(self):
        args = self.args()
        self.prepare(args)
        self.run_queue(args)
        feature = self.base/'wav2vec-frames/0.npz'
        original = feature.read_bytes()
        feature.write_bytes(b'changed feature')
        with self.assertRaisesRegex(ValueError, 'cache entry'):
            self.run_queue(args)
        feature.write_bytes(original)
        (self.root/'multiphone_models.py').write_text('changed model source')
        with self.assertRaisesRegex(ValueError, 'immutable execution contract'):
            self.run_queue(args)

    def test_previously_recorded_report_digest_cannot_change_on_later_skip(self):
        args = self.args()
        output, _, _ = self.prepare(args)
        self.run_queue(args)
        report_path = output/'report.json'
        report = queue.load_json(report_path)
        report['changedAfterCompletion'] = True
        queue.atomic_json(report_path, report)
        with self.assertRaisesRegex(ValueError, 'completed artifacts changed'):
            self.run_queue(args)
        self.assertEqual(len(self.launches()), 1)

    def test_prediction_report_and_full_history_metric_tampering_are_rejected(self):
        args = self.args()
        output, _, _ = self.prepare(args, existing=True)
        report_path = output/'report.json'
        original_report = report_path.read_bytes()
        report = queue.load_json(report_path)
        report['evaluation']['perRaterLogLoss'] += 0.1
        queue.atomic_json(report_path, report)
        with self.assertRaisesRegex(ValueError, 'metrics differ'):
            self.run_queue(args)
        report_path.write_bytes(original_report)
        predictions_path = output/'predictions.json'
        original_predictions = predictions_path.read_bytes()
        queue.atomic_json(predictions_path, {'rowIndices': [1], 'probabilities': [[0.2, 0.2, 0.6]]})
        with self.assertRaisesRegex(ValueError, 'metrics differ'):
            self.run_queue(args)
        predictions_path.write_bytes(original_predictions)
        history_path = output/'history.json'
        history = queue.load_json(history_path)
        history[-1]['validation']['macroTargetLogLoss'] = 0.01
        queue.atomic_json(history_path, history)
        with self.assertRaisesRegex(ValueError, 'early-stopping rule disagree'):
            self.run_queue(args)
        self.assertEqual(self.launches(), [])

    def test_child_gate_does_not_start_training_without_durable_pid_record(self):
        args = self.args()
        self.prepare(args)
        original = queue.atomic_json
        def fail_pid_record(path, value):
            if path == args.ledger and value.get('jobs'):
                attempt = value['jobs'][-1]['attempts'][-1]
                if attempt.get('state') == 'running':
                    raise OSError('simulated ledger write failure')
            return original(path, value)
        with patch.object(queue, 'atomic_json', side_effect=fail_pid_record):
            with self.assertRaisesRegex(OSError, 'ledger write failure'):
                self.run_queue(args)
        self.assertEqual(self.launches(), [])
        self.assertEqual(queue.load_json(args.ledger)['state'], 'failed')


if __name__ == '__main__':
    unittest.main()
