"""Synthetic twenty-four-arm orchestration; no corpus inference or real study fits."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import multiphone_consistency_replication_queue as queue
import test_multiphone_consistency_replication as fixtures


@contextmanager
def synthetic_fit(regime='all-age'):
    suite = fixtures.ReplicationTests()
    suite.setUp()
    try:
        args = suite.args(regime=regime)
        with redirect_stdout(io.StringIO()):
            queue.trainer.fit(args)
        job = {'fold': args.fold, 'regime': regime, 'coefficient': args.coefficient, 'output': str(args.output), 'state': 'fitting'}
        plan = {'trainingPlan': {'path': str(suite.plan_path), 'sha256': suite.plan_sha},
                'contract': {key: suite.plan[key] for key in ('sourceSha256', 'recipeSha256')}}
        yield job, plan, suite.plan
    finally:
        suite.doCleanups()


class ConsistencyQueueTests(unittest.TestCase):
    def test_exact_twenty_four_fixed_cpu_arms_and_no_implicit_resume(self):
        jobs = queue.jobs(Path('/tmp/consistency-test'))
        self.assertEqual([(job['fold'], job['regime'], job['coefficient']) for job in jobs],
                         [(fold, regime, c) for fold in (1,2,3,4) for regime in ('all-age','child-only')
                          for c in (0., .1, 1.)])
        self.assertEqual(len({job['output'] for job in jobs}), 24)
        plan = {'trainingPlan': {'path': '/tmp/training-plan.json', 'sha256': 'declared'}}
        for job in jobs:
            command = queue.command(job, plan)
            self.assertEqual(command[2], 'fit')
            self.assertEqual(int(command[command.index('--fold') + 1]), job['fold'])
            self.assertEqual(command[command.index('--regime') + 1], job['regime'])
            self.assertEqual(float(command[command.index('--coefficient') + 1]), job['coefficient'])
            self.assertNotIn('--resume', command)
            self.assertNotIn('mps', command)
            self.assertEqual(queue.command(job, plan, replay=True)[2:], ['replay', '--output', job['output']])
        declared = queue.contract()
        self.assertEqual((declared['device'], declared['threads']), ('cpu', 2))

    def test_actual_synthetic_fit_stays_incomplete_until_separate_exact_replay(self):
        for regime in ('all-age', 'child-only'):
            with self.subTest(regime=regime), synthetic_fit(regime) as (job, plan, training):
                job['verified'] = queue.verify_fitted(job, plan, training)
                self.assertEqual(set(job['verified']['files']), set(queue.FIT_FILES) | {'report.json'})
                output = Path(job['output'])
                self.assertFalse(queue.read_json(output / 'report.json')['complete'])
                with self.assertRaises(FileNotFoundError):
                    queue.verify_replay(job)
                queue.trainer.replay(output)
                self.assertEqual(queue.verify_replay(job), queue.digest(output / 'replay.json'))
                self.assertFalse(queue.read_json(output / 'report.json')['complete'])
                with (output / 'predictions.json').open('ab') as stream:
                    stream.write(b' ')
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    queue.verify_replay(job)

    def test_rehashed_wrong_arm_and_inexact_replay_are_rejected(self):
        with synthetic_fit() as (job, plan, training):
            output = Path(job['output'])
            job['verified'] = queue.verify_fitted(job, plan, training)
            queue.trainer.replay(output)
            replay = queue.read_json(output / 'replay.json'); replay['exact'] = False
            queue.atomic_json(output / 'replay.json', replay)
            with self.assertRaisesRegex(ValueError, 'Independent exact replay'):
                queue.verify_replay(job)
            config = queue.read_json(output / 'config.json'); config['coefficient'] = 1.
            queue.atomic_json(output / 'config.json', config)
            report = queue.read_json(output / 'report.json')
            report['filesSha256']['config.json'] = queue.digest(output / 'config.json')
            queue.atomic_json(output / 'report.json', report)
            with self.assertRaisesRegex(ValueError, 'configuration differs'):
                queue.verify_fitted(job, plan, training)

    def test_report_mutated_after_read_cannot_be_adopted_as_new_verified_pin(self):
        with synthetic_fit() as (job, plan, training):
            original = queue.read_json
            report_path = Path(job['output']) / 'report.json'
            def mutate(path):
                value = original(path)
                if path == report_path:
                    with path.open('ab') as stream:
                        stream.write(b' ')
                return value
            with patch.object(queue, 'read_json', side_effect=mutate):
                with self.assertRaisesRegex(ValueError, 'changed while verifying'):
                    queue.verify_fitted(job, plan, training)

    @contextmanager
    def declaration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / 'outputs').mkdir()
            features = root / 'features.json'; queue.atomic_json(features, {'complete': True})
            declared = {'sourceSha256': {'synthetic': 'fixed'}, 'recipeSha256': 'fixed-recipe',
                        'device': 'cpu', 'threads': 2}
            def training_declare(path, sha, output):
                value = {'complete': True, 'sourceSha256': declared['sourceSha256'],
                    'recipeSha256': declared['recipeSha256'], 'noisyFeatures': str(path.resolve()),
                    'noisyFeaturesSha256': sha, 'inputFiles': {}, 'populations': {}}
                queue.atomic_json(output, value)
                return value
            def training_guard(value, path, sha):
                queue.require(queue.digest(path) == sha and value == queue.read_json(path),
                              'Synthetic training plan changed')
            with patch.object(queue, 'HERE', root), patch.object(queue, 'contract', return_value=declared), \
                 patch.object(queue.trainer, 'declare', side_effect=training_declare), \
                 patch.object(queue.trainer, 'plan_guard', side_effect=training_guard):
                base = root / 'outputs/study'
                plan = queue.declare(features, queue.digest(features), base)
                yield base, base / 'queue-plan.json', plan, features

    def test_fresh_declaration_pins_training_plan_features_and_fixed_inventory(self):
        with self.declaration() as (base, path, plan, features):
            self.assertEqual(plan['jobs'], queue.jobs(base))
            queue.guard_plan(plan, path, queue.digest(path))
            with self.assertRaisesRegex(ValueError, 'fresh consistency directory'):
                queue.declare(features, queue.digest(features), base)
            changed = deepcopy(plan); changed['jobs'].reverse()
            queue.atomic_json(path, changed)
            with self.assertRaisesRegex(ValueError, 'queue declaration changed'):
                queue.guard_plan(changed, path, queue.digest(path))

    def child_runner(self, base, plan, mutation=None, fail_at=None):
        calls = []
        def child(command, record, log_path, save):
            calls.append(command[2])
            if fail_at == len(calls):
                record.update(state='failed', exitCode=9)
                save()
                raise RuntimeError('synthetic child failure')
            output = Path(command[command.index('--output') + 1])
            record.update(state='running', pid=os.getpid(), logPath=str(log_path))
            save()
            log_path.write_text('Synthetic process log.\n')
            if command[2] == 'fit':
                output.mkdir()
                for name in queue.FIT_FILES:
                    (output / name).write_bytes(b'synthetic fit artifact')
                queue.atomic_json(output / 'report.json', {'fitComplete': True, 'complete': False})
            else:
                queue.atomic_json(output / 'replay.json', {'complete': True, 'exact': True, 'state': 'verified',
                    'noisyAccuracyMeasured': False, 'rows': 3,
                    **{key: next(job for job in plan['jobs'] if job['output'] == str(output))[key]
                       for key in ('fold','regime','coefficient')}, 'checkpointSha256': queue.digest(output / 'best.pt'),
                    'reportSha256': queue.digest(output / 'report.json')})
                if len(calls) == 48 and mutation:
                    changed = {'queue-plan': base / 'queue-plan.json', 'training-plan': base / 'training-plan.json',
                        'earlier-output': Path(plan['jobs'][0]['output']) / 'teacher-fit.npy',
                        'earlier-log': base / (Path(plan['jobs'][0]['output']).name + '-fit.log')}[mutation]
                    with changed.open('ab') as stream:
                        stream.write(b' ')
            record.update(state='complete', exitCode=0)
            save()
            ledger = queue.read_json(base / 'queue-ledger.json')
            self.assertFalse(ledger['complete'])
            if command[2] == 'fit':
                current = next(job for job in ledger['jobs'] if job['output'] == str(output))
                self.assertEqual(current['state'], 'fitting')
        def verify(job, *_):
            output = Path(job['output'])
            return {'files': {name: queue.digest(output / name) for name in (*queue.FIT_FILES, 'report.json')},
                    'bestEpoch': 0, 'epochsRun': 2, 'cleanSelectionMacroNLL': .2, 'validationRows': 3}
        return child, verify, calls

    def test_all_twenty_four_replays_required_then_ledger_is_complete_and_rerun_refused(self):
        with self.declaration() as (base, path, plan, _):
            child, verify, calls = self.child_runner(base, plan)
            with patch.object(queue, 'run_child', side_effect=child), \
                 patch.object(queue, 'verify_fitted', side_effect=verify), redirect_stdout(io.StringIO()):
                ledger = queue.run(path, queue.digest(path))
                self.assertTrue(ledger['complete'])
                self.assertEqual(calls, ['fit', 'replay'] * 24)
                self.assertTrue(all(job['replayVerifiedExact'] for job in ledger['jobs']))
                self.assertEqual(ledger['pid'], os.getpid())
                self.assertIn('processSessionId', ledger)
                with self.assertRaisesRegex(ValueError, 'explicit recovery'):
                    queue.run(path, queue.digest(path))

    def test_last_replay_mutations_and_child_failures_preserve_incomplete_ledger(self):
        for mutation in ('queue-plan', 'training-plan', 'earlier-output', 'earlier-log', None):
            with self.subTest(mutation=mutation), self.declaration() as (base, path, plan, _):
                child, verify, calls = self.child_runner(base, plan, mutation=mutation,
                                                        fail_at=2 if mutation is None else None)
                with patch.object(queue, 'run_child', side_effect=child), \
                     patch.object(queue, 'verify_fitted', side_effect=verify), redirect_stdout(io.StringIO()):
                    with self.assertRaises((ValueError, RuntimeError)):
                        queue.run(path, queue.digest(path))
                ledger = queue.read_json(base / 'queue-ledger.json')
                self.assertFalse(ledger['complete'])
                self.assertIn('failure', ledger)
                self.assertEqual(len(calls), 2 if mutation is None else 48)
                self.assertTrue((Path(plan['jobs'][0]['output']) / 'report.json').exists())

    def test_real_launch_gate_records_exact_child_pid_before_child_executes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger_path, sentinel = root / 'ledger.json', root / 'checked.txt'
            record = {}
            def save():
                queue.atomic_json(ledger_path, record)
                with ledger_path.open('rb') as stream:
                    os.fsync(stream.fileno())
            script = ('import json,os,pathlib,sys; '
                'record=json.loads(pathlib.Path(sys.argv[1]).read_text()); '
                'assert record["pid"]==os.getpid() and record["state"]=="running"; '
                'pathlib.Path(sys.argv[2]).write_text("PID recorded before execution")')
            queue.run_child([sys.executable, '-c', script, str(ledger_path), str(sentinel)],
                            record, root / 'child.log', save)
            self.assertEqual(sentinel.read_text(), 'PID recorded before execution')
            self.assertEqual(record['state'], 'complete')
            self.assertEqual(record['exitCode'], 0)


if __name__ == '__main__':
    unittest.main()
