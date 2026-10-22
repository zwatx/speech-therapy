"""Synthetic ranking artifacts and subprocess orchestration; no real fits."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

import multiphone_ranking_queue as queue


class RankingQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); (self.root / 'outputs').mkdir()
        self.base = self.root / 'outputs/study'
        self.preflight = self.root / 'preflight.json'
        self.cohort = self.root / 'cohort.json'
        self.rows = [dict(age=8, speakerId=str(i), clipId=str(i), targetPhone='B' if i % 2 == 0 else 'P',
                          raterCounts=[1, 1, 3] if i % 2 == 0 else [0, 0, 5]) for i in range(6)]
        queue.atomic_json(self.cohort, {'authorPartition': 'train', 'rows': self.rows})
        self.inputs = {'clean/cohort': {'path': str(self.cohort), 'sha256': queue.digest(self.cohort)}}
        self.contract = {'sourceSha256': {'synthetic-source': 'fixed'}, 'recipeSha256': 'recipe', 'device': 'cpu', 'threads': 2}
        self.measurement = {'complete': True, 'exact': True, 'fitOnly': True, 'validationInferencePerformed': False,
            'coefficient': 0, 'fold': 0, 'regime': 'child-only', 'comparedUpdates': 2, 'exactChecks': {k: True for k in queue.CHECKS},
            'sourceSha256': self.contract['sourceSha256'], 'recipeSha256': self.contract['recipeSha256'], 'inputFiles': self.inputs}
        queue.atomic_json(self.preflight, self.measurement)
        self.preflight_sha = queue.digest(self.preflight)
        self.enterContext(patch.object(queue, 'HERE', self.root))
        self.enterContext(patch.object(queue, 'contract', return_value=self.contract))
        self.enterContext(patch.object(queue.trainer, 'validate_preflight', side_effect=lambda path, sha: queue.read_json(path)))
        self.enterContext(patch.object(queue.trainer, 'declare', side_effect=self.training_declare))
        self.enterContext(patch.object(queue.trainer, 'plan_guard', side_effect=self.training_guard))

    def training_declare(self, preflight, sha, output):
        value = {'complete': True, **{k: self.contract[k] for k in ('sourceSha256', 'recipeSha256')},
            'preflight': {'path': str(preflight.resolve()), 'sha256': sha},
            'arms': [dict(fold=f, regime='child-only', coefficient=.1) for f in range(5)],
            'populations': {str(f): {'fitRows': [4, 5], 'validationRows': [0, 1, 2, 3],
                'selectionRows': [0, 1, 2, 3], 'inputFiles': self.inputs, 'support': {'synthetic': True},
                'meanDigest': queue.trainer.tensor_digest(torch.zeros(1)),
                'stdDigest': queue.trainer.tensor_digest(torch.ones(1))} for f in range(5)}}
        queue.atomic_json(output, value)
        return value

    def training_guard(self, value, path, sha):
        queue.require(queue.digest(path) == sha and value == queue.read_json(path), 'Synthetic training plan changed')
        for population in value['populations'].values():
            for pin in population['inputFiles'].values():
                queue.require(queue.digest(Path(pin['path'])) == pin['sha256'], 'Synthetic training input changed')

    def declare(self):
        plan = queue.declare(self.preflight, self.preflight_sha, self.base)
        path = self.base / 'queue-plan.json'
        return plan, path, queue.digest(path), queue.read_json(self.base / 'training-plan.json')

    def fit_files(self, job, plan, training):
        output = Path(job['output']); output.mkdir()
        population = training['populations'][str(job['fold'])]
        config = {'planPath': plan['trainingPlan']['path'], 'planSha256': plan['trainingPlan']['sha256'],
            **{k: job[k] for k in ('fold', 'regime', 'coefficient')}, **deepcopy(population),
            **{k: self.contract[k] for k in ('sourceSha256', 'recipeSha256')},
            'studentTrainingMode': 'eval-with-gradients', 'nllSeed': 7, 'pairSeed': 20260926, 'pairsPerUpdate': 64,
            **{k: False for k in queue.trainer.FALSE_FLAGS}}
        queue.atomic_json(output / 'config.json', config)
        p = np.tile([.1, .1, .8], (4, 1)); evaluation = queue.score_predictions(p, self.rows[:4])
        loss = evaluation['ages6to12']['macroTargetLogLoss']
        history = [dict(epoch=e, selectionMacroNLL=loss, evaluation=evaluation) for e in range(3)]
        queue.atomic_json(output / 'history.json', history)
        queue.atomic_json(output / 'support.json', {'synthetic': True})
        queue.atomic_json(output / 'predictions.json', {'rowIndices': [0, 1, 2, 3],
            'probabilities': p.tolist(), 'warmProbabilities': p.tolist()})
        for name, epoch in (('best.pt', 0), ('last.pt', 2)):
            torch.save({'configSha256': queue.digest(output / 'config.json'), 'epoch': epoch,
                'bestEpoch': 0, 'bestLoss': loss, 'model': {'weight': torch.tensor([1.])},
                'mean': torch.zeros(1), 'std': torch.ones(1)}, output / name)
        queue.atomic_json(output / 'status.json', dict(complete=False, fitComplete=True,
            state='fitted-awaiting-independent-replay', bestEpoch=0, epochsRun=2))
        report = {'complete': False, 'fitComplete': True, 'state': 'fitted-awaiting-independent-replay',
            **{k: job[k] for k in ('fold', 'regime', 'coefficient')},
            'evaluation': evaluation, 'warmEvaluation': evaluation, 'bestEpoch': 0,
            'epochsRun': 2, 'bestCleanSelectionNLL': loss, **{k: False for k in queue.trainer.FALSE_FLAGS},
            'filesSha256': {name: queue.digest(output / name) for name in queue.FIT_FILES}}
        queue.atomic_json(output / 'report.json', report)
        return report

    def replay_file(self, job):
        output = Path(job['output'])
        queue.atomic_json(output / 'replay.json', {'complete': True, 'exact': True, 'state': 'verified',
            **{k: job[k] for k in ('fold', 'regime', 'coefficient')}, 'rows': 4,
            'checkpointSha256': queue.digest(output / 'best.pt'), 'reportSha256': queue.digest(output / 'report.json')})

    def test_five_fixed_child_arms_no_control_refits_and_explicit_preflight(self):
        plan, path, sha, training = self.declare()
        self.assertEqual([(j['fold'], j['regime'], j['coefficient']) for j in plan['jobs']],
                         [(f, 'child-only', .1) for f in range(5)])
        self.assertFalse(plan['controlRefitsPerformed'])
        self.assertEqual(plan['preflight'], training['preflight'])
        self.assertEqual(queue.guard_plan(plan, path, sha), training)
        for job in plan['jobs']:
            command = queue.command(job, plan)
            self.assertEqual(int(command[command.index('--fold') + 1]), job['fold'])
            self.assertNotIn('--resume', command)
            self.assertNotIn('mps', command)
            self.assertNotIn('--coefficient', command)
            self.assertEqual(queue.command(job, plan, True)[2:], ['replay', '--output', job['output']])
        with self.assertRaisesRegex(ValueError, 'fresh ranking'):
            queue.declare(self.preflight, self.preflight_sha, self.base)

    def test_preflight_failure_or_wrong_source_blocks_declaration_before_output(self):
        for field, value in [('complete', False), ('fitOnly', False), ('validationInferencePerformed', True),
                             ('coefficient', .1), ('fold', 1), ('comparedUpdates', 0), ('recipeSha256', 'other')]:
            altered = {**self.measurement, field: value}; queue.atomic_json(self.preflight, altered)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'equivalence'):
                queue.declare(self.preflight, queue.digest(self.preflight), self.base)
            self.assertFalse(self.base.exists())
        altered = deepcopy(self.measurement); altered['exactChecks']['optimizer'] = False
        queue.atomic_json(self.preflight, altered)
        with self.assertRaisesRegex(ValueError, 'equivalence'):
            queue.declare(self.preflight, queue.digest(self.preflight), self.base)
        with self.assertRaisesRegex(ValueError, 'Caller-pinned'):
            queue.declare(self.preflight, self.preflight_sha, self.base)

    def test_selected_history_checkpoint_and_metrics_require_exact_separate_replay(self):
        plan, _, _, training = self.declare(); job = deepcopy(plan['jobs'][0])
        self.fit_files(job, plan, training)
        job['verified'] = queue.verify_fitted(job, plan, training)
        self.assertEqual(set(job['verified']['files']), set(queue.FIT_FILES) | {'report.json'})
        with self.assertRaises(FileNotFoundError): queue.verify_replay(job)
        self.replay_file(job)
        self.assertEqual(queue.verify_replay(job), queue.digest(Path(job['output']) / 'replay.json'))
        p = Path(job['output']) / 'replay.json'; value = queue.read_json(p); value['fold'] = 4
        queue.atomic_json(p, value)
        with self.assertRaisesRegex(ValueError, 'exact ranking replay'): queue.verify_replay(job)

    def test_actual_synthetic_trainer_artifacts_match_queue_contract_and_replay(self):
        from test_multiphone_ranking_train import RankingArtifactTests
        suite = RankingArtifactTests(); suite.setUp()
        try:
            cohort = suite.root / 'cohort.json'; queue.atomic_json(cohort, suite.data['cohort'])
            bindings = {'clean/cohort': {'path': str(cohort), 'sha256': queue.digest(cohort)}}
            suite.data['allBindings'] = bindings
            suite.plan['inputFiles'] = suite.plan['populations']['0']['inputFiles'] = bindings
            queue.atomic_json(suite.path, suite.plan)
            args = suite.args()
            with redirect_stdout(io.StringIO()): queue.trainer.fit(args)
            job = dict(fold=0, regime='child-only', coefficient=.1, output=str(args.output))
            plan = {'trainingPlan': {'path': str(suite.path), 'sha256': queue.digest(suite.path)},
                    'contract': {k: suite.plan[k] for k in ('sourceSha256', 'recipeSha256')}}
            job['verified'] = queue.verify_fitted(job, plan, suite.plan)
            queue.trainer.replay(args.output)
            self.assertEqual(queue.verify_replay(job), queue.digest(args.output / 'replay.json'))
        finally:
            suite.doCleanups()

    def test_rehashed_metrics_configuration_and_history_tampering_rejected(self):
        plan, _, _, training = self.declare()
        for ordinal, mode in enumerate(('prediction', 'history', 'input', 'checkpoint', 'moments')):
            job = deepcopy(plan['jobs'][ordinal]); self.fit_files(job, plan, training)
            out = Path(job['output']); report = queue.read_json(out / 'report.json')
            if mode == 'prediction':
                value = queue.read_json(out / 'predictions.json'); value['probabilities'][0] = [.8, .1, .1]
                queue.atomic_json(out / 'predictions.json', value)
            elif mode == 'history':
                value = queue.read_json(out / 'history.json'); value[1]['selectionMacroNLL'] += .1
                queue.atomic_json(out / 'history.json', value)
            elif mode == 'input':
                value = queue.read_json(out / 'config.json'); value['inputFiles'] = {}
                queue.atomic_json(out / 'config.json', value)
            elif mode == 'checkpoint':
                value = torch.load(out / 'best.pt', weights_only=True); value['epoch'] = 1
                torch.save(value, out / 'best.pt')
            else:
                value = torch.load(out / 'best.pt', weights_only=True); value['mean'] += 1
                torch.save(value, out / 'best.pt')
            report['filesSha256'] = {name: queue.digest(out / name) for name in queue.FIT_FILES}
            queue.atomic_json(out / 'report.json', report)
            with self.subTest(mode=mode), self.assertRaises(ValueError): queue.verify_fitted(job, plan, training)

    def runner(self, plan, training, mutate=None, fail_at=None):
        calls = []
        def run(command, process, log, save):
            calls.append(command[2]); process.update(pid=os.getpid(), state='running', logPath=str(log)); save()
            if len(calls) == fail_at:
                process.update(state='failed', exitCode=9); save(); raise RuntimeError('synthetic child failure')
            output = command[command.index('--output') + 1]
            job = next(j for j in plan['jobs'] if j['output'] == output)
            log.write_text('Synthetic process.\n')
            if command[2] == 'fit': self.fit_files(job, plan, training)
            else: self.replay_file(job)
            if len(calls) == 10 and mutate:
                if mutate == 'queue-source':
                    self.contract['runnerSha256'] = 'changed'
                else:
                    target = {'preflight': self.preflight, 'source-input': self.cohort,
                        'training-plan': self.base / 'training-plan.json', 'queue-plan': self.base / 'queue-plan.json',
                        'earlier-output': Path(plan['jobs'][0]['output']) / 'support.json',
                        'earlier-log': self.base / (Path(plan['jobs'][0]['output']).name + '-fit.log')}[mutate]
                    with target.open('ab') as stream: stream.write(b' ')
            process.update(state='complete', exitCode=0); save()
            self.assertFalse(queue.read_json(self.base / 'queue-ledger.json')['complete'])
        return run, calls

    def test_five_fits_and_replays_then_completion_and_no_implicit_restart(self):
        plan, path, sha, training = self.declare(); runner, calls = self.runner(plan, training)
        with patch.object(queue, 'run_child', side_effect=runner), redirect_stdout(io.StringIO()):
            ledger = queue.run(path, sha)
        self.assertTrue(ledger['complete']); self.assertEqual(calls, ['fit', 'replay'] * 5)
        self.assertTrue(all(j['replayVerifiedExact'] for j in ledger['jobs']))
        self.assertEqual(ledger['preflight'], plan['preflight'])
        with self.assertRaisesRegex(ValueError, 'explicit recovery'): queue.run(path, sha)

    def test_failed_child_halts_queue_and_preserves_attempt(self):
        plan, path, sha, training = self.declare(); runner, calls = self.runner(plan, training, fail_at=2)
        with patch.object(queue, 'run_child', side_effect=runner), redirect_stdout(io.StringIO()), \
             self.assertRaisesRegex(RuntimeError, 'child failure'):
            queue.run(path, sha)
        ledger = queue.read_json(self.base / 'queue-ledger.json')
        self.assertFalse(ledger['complete']); self.assertIn('failure', ledger); self.assertEqual(calls, ['fit', 'replay'])
        self.assertTrue((Path(plan['jobs'][0]['output']) / 'best.pt').exists())

    def test_last_replay_late_mutations_cannot_publish_complete_ledger(self):
        for mode in ('preflight', 'source-input', 'queue-source', 'training-plan', 'queue-plan', 'earlier-output', 'earlier-log'):
            with self.subTest(mode=mode):
                suite = RankingQueueTests(); suite.setUp()
                try:
                    plan, path, sha, training = suite.declare(); runner, calls = suite.runner(plan, training, mutate=mode)
                    with patch.object(queue, 'run_child', side_effect=runner), redirect_stdout(io.StringIO()), \
                         self.assertRaises(ValueError): queue.run(path, sha)
                    ledger = queue.read_json(suite.base / 'queue-ledger.json')
                    self.assertFalse(ledger['complete']); self.assertIn('failure', ledger); self.assertEqual(len(calls), 10)
                finally: suite.doCleanups()

    def test_real_pid_gate_durably_records_child_before_execution(self):
        path, sentinel = self.root / 'pid.json', self.root / 'ran.txt'; record = {}
        def save():
            queue.atomic_json(path, record)
            with path.open('rb') as stream: os.fsync(stream.fileno())
        source = ('import json,os,pathlib,sys; r=json.loads(pathlib.Path(sys.argv[1]).read_text()); '
                  'assert r["pid"]==os.getpid() and r["state"]=="running"; pathlib.Path(sys.argv[2]).write_text("verified")')
        queue.run_child([sys.executable, '-c', source, str(path), str(sentinel)], record, self.root / 'process.log', save)
        self.assertEqual(sentinel.read_text(), 'verified'); self.assertEqual(record['exitCode'], 0)


if __name__ == '__main__': unittest.main()
