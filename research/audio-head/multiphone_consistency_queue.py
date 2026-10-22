"""Six fixed CPU consistency arms; a separate exact replay verifies each arm.

Use a fresh ignored output directory. Every child waits until its PID is in
the durable ledger; failed or interrupted runs require explicit recovery.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np
import torch

import multiphone_consistency_train as trainer
from multiphone_cache import atomic_json, digest
from multiphone_local_head_queue import run_child

HERE = Path(__file__).resolve().parent
TRAINER_SHA = '7058da214a4f072eb008be5975c9c50786fff4ee4d5528d48bf0ee71286d116f'
RECIPE_SHA = '0a6207886c1d0a528f42c1c3266a30aed015aa323da7a4362208cde76edc02e0'
FIT_FILES = ('config.json', 'teacher-fit.npy', 'best.pt', 'last.pt', 'history.json',
             'predictions.json', 'status.json')
read_json, require = trainer.read_json, trainer.require


def contract():
    require(digest(HERE / 'multiphone_consistency_train.py') == TRAINER_SHA
            and digest(trainer.RECIPE) == RECIPE_SHA, 'Reviewed consistency trainer or recipe changed')
    return {'trainerSha256': TRAINER_SHA, 'recipeSha256': RECIPE_SHA,
        'sourceSha256': trainer.source_hashes(), 'runnerSha256': digest(Path(__file__)),
        'launchHelperSha256': digest(HERE / 'multiphone_local_head_queue.py'),
        'python': sys.executable, 'torch': str(torch.__version__), 'numpy': np.__version__,
        'device': 'cpu', 'threads': 2}


def jobs(base):
    return [{'regime': regime, 'coefficient': coefficient,
             'output': str((base / f'{regime}-coefficient-{suffix}').resolve()), 'state': 'pending'}
            for regime in ('all-age', 'child-only')
            for coefficient, suffix in ((0., '0'), (.1, '0p1'), (1., '1'))]


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def declare(features, features_sha, base):
    require(not base.exists() and base.resolve().is_relative_to((HERE / 'outputs').resolve()),
            'Choose a fresh consistency directory in ignored outputs')
    pinned_contract = contract()
    require(digest(features) == features_sha, 'Caller-pinned noisy features differ')
    base.mkdir(parents=True, mode=0o700)
    training_path = base / 'training-plan.json'
    try:
        training = trainer.declare(features, features_sha, training_path)
        training_sha = digest(training_path)
        require(read_json(training_path) == training, 'Saved training declaration differs')
        trainer.plan_guard(training, training_path, training_sha)
        require(contract() == pinned_contract and digest(features) == features_sha,
                'Consistency inputs changed during declaration')
        value = {'complete': True, 'base': str(base.resolve()), 'contract': pinned_contract,
            'trainingPlan': {'path': str(training_path.resolve()), 'sha256': training_sha},
            'noisyFeatures': {'path': str(features.resolve()), 'sha256': features_sha},
            'jobs': jobs(base), 'plannedTrials': 6, 'allSixArmsFixed': True,
            'implicitResumeAllowed': False, 'outcomesCanChangeOrderOrCoverage': False,
            **{key: False for key in trainer.FALSE_FLAGS}}
        write_new(base / 'queue-plan.json', value)
        return value
    except BaseException as error:
        atomic_json(base / 'declaration-failure.json', {'complete': False, 'failure': repr(error)})
        raise


def guard_plan(plan, path, expected_sha):
    base = Path(plan['base'])
    require(digest(path) == expected_sha and plan['complete'] is True
            and plan['contract'] == contract() and base.resolve().is_relative_to((HERE / 'outputs').resolve())
            and plan['jobs'] == jobs(base) and plan['plannedTrials'] == 6 and plan['allSixArmsFixed'] is True
            and plan['implicitResumeAllowed'] is False and plan['outcomesCanChangeOrderOrCoverage'] is False
            and all(plan[key] is False for key in trainer.FALSE_FLAGS), 'Consistency queue declaration changed')
    pinned = plan['trainingPlan']
    require(Path(pinned['path']) == base / 'training-plan.json', 'Training plan location differs')
    training = read_json(Path(pinned['path']))
    trainer.plan_guard(training, Path(pinned['path']), pinned['sha256'])
    require(training['sourceSha256'] == plan['contract']['sourceSha256']
            and training['recipeSha256'] == plan['contract']['recipeSha256']
            and training['noisyFeatures'] == plan['noisyFeatures']['path']
            and training['noisyFeaturesSha256'] == plan['noisyFeatures']['sha256']
            and digest(Path(plan['noisyFeatures']['path'])) == plan['noisyFeatures']['sha256'],
            'Training declaration and noisy feature binding differ')
    return training


def command(job, plan, replay=False):
    prefix = [sys.executable, str(HERE / 'multiphone_consistency_train.py')]
    if replay:
        return prefix + ['replay', '--output', job['output']]
    return prefix + ['fit', '--plan', plan['trainingPlan']['path'],
        '--plan-sha256', plan['trainingPlan']['sha256'], '--regime', job['regime'],
        '--coefficient', str(job['coefficient']), '--output', job['output']]


def verify_fitted(job, plan, training):
    output = Path(job['output'])
    report_sha = digest(output / 'report.json')
    config, report = read_json(output / 'config.json'), read_json(output / 'report.json')
    population = training['populations'][job['regime']]
    require(config['planPath'] == plan['trainingPlan']['path']
            and config['planSha256'] == plan['trainingPlan']['sha256']
            and all(config[key] == job[key] for key in ('regime', 'coefficient'))
            and config['sourceSha256'] == plan['contract']['sourceSha256']
            and config['recipeSha256'] == plan['contract']['recipeSha256']
            and all(config[key] == population[key] for key in ('fitRows', 'validationRows', 'selectionRows'))
            and all(training['inputFiles'].get(key) == value for key, value in config['inputFiles'].items())
            and config['studentTrainingMode'] == 'eval-with-gradients'
            and config['teacherFitSha256'] == digest(output / 'teacher-fit.npy'),
            'Fitted arm configuration differs from its declaration')
    require(report['complete'] is False and report['fitComplete'] is True
            and report['state'] == 'fitted-awaiting-independent-replay'
            and all(config[key] is False and report[key] is False for key in trainer.FALSE_FLAGS)
            and set(report['filesSha256']) == set(FIT_FILES)
            and all(digest(output / name) == sha for name, sha in report['filesSha256'].items()),
            'Fitted artifact state or checksum differs')
    expected_status = {'complete': False, 'fitComplete': True, 'state': 'fitted-awaiting-independent-replay',
                       'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun']}
    require(read_json(output / 'status.json') == expected_status, 'Fitted status differs')
    initial = trainer.baseline.selection_loss(report['warmCleanEvaluation'], job['regime'])
    best, epoch = trainer.validate_history(read_json(output / 'history.json'), initial)
    require(best == report['bestCleanSelectionNLL'] and epoch == report['bestEpoch']
            and best == trainer.baseline.selection_loss(report['cleanEvaluation'], job['regime'])
            and len(read_json(output / 'history.json')) - 1 == report['epochsRun'], 'Fitted clean selection differs')
    saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == report['filesSha256']['config.json']
            and saved['epoch'] == saved['bestEpoch'] == epoch and saved['bestLoss'] == best,
            'Fitted selected checkpoint differs')
    predictions = read_json(output / 'predictions.json')
    require(predictions['rowIndices'] == population['validationRows']
            and predictions['noisyHumanLabelsAvailable'] is False, 'Fitted prediction population differs')
    require(digest(output / 'report.json') == report_sha
            and all(digest(output / name) == sha for name, sha in report['filesSha256'].items()),
            'Fitted artifacts changed while verifying')
    return {'files': {**report['filesSha256'], 'report.json': report_sha},
            'bestEpoch': epoch, 'epochsRun': report['epochsRun'], 'cleanSelectionMacroNLL': best,
            'validationRows': len(population['validationRows'])}


def guard_fitted(job):
    require(all(digest(Path(job['output']) / name) == sha for name, sha in job['verified']['files'].items()),
            'Previously verified consistency artifact changed')


def verify_replay(job):
    guard_fitted(job)
    path = Path(job['output']) / 'replay.json'
    replay_sha = digest(path)
    replay = read_json(path)
    require(replay['complete'] is True and replay['exact'] is True and replay['state'] == 'verified'
            and replay['noisyAccuracyMeasured'] is False and replay['rows'] == job['verified']['validationRows']
            and replay['checkpointSha256'] == job['verified']['files']['best.pt']
            and replay['reportSha256'] == job['verified']['files']['report.json'], 'Independent exact replay differs')
    guard_fitted(job)
    require(digest(path) == replay_sha, 'Replay changed while verifying')
    return replay_sha


def guard_outputs(job):
    require(job['state'] == 'complete' and job['replayVerifiedExact'] is True, 'Arm has not completed exact replay')
    guard_fitted(job)
    require(digest(Path(job['output']) / 'replay.json') == job['replaySha256'], 'Verified replay artifact changed')
    for key in ('fitProcess', 'replayProcess'):
        process = job[key]
        require(process['state'] == 'complete' and process['exitCode'] == 0
                and digest(Path(process['logPath'])) == process['logSha256'], 'Verified process or log changed')


def run(plan_path, expected_sha):
    require(digest(plan_path) == expected_sha, 'Caller-pinned queue declaration differs')
    plan = read_json(plan_path)
    training = guard_plan(plan, plan_path, expected_sha)
    base = Path(plan['base'])
    ledger_path = base / 'queue-ledger.json'
    with (base / 'queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not ledger_path.exists() and all(not Path(job['output']).exists() for job in plan['jobs']),
                'Existing queue or arm output requires explicit recovery')
        ledger = {'pid': os.getpid(), 'parentPid': os.getppid(), 'processSessionId': os.getsid(0),
            'startedAt': time.time(), 'complete': False, 'planPath': str(plan_path.resolve()),
            'planSha256': expected_sha, 'contract': plan['contract'], 'jobs': deepcopy(plan['jobs'])}

        def save():
            atomic_json(ledger_path, ledger)
            with ledger_path.open('rb') as stream:
                os.fsync(stream.fileno())

        save()
        try:
            for job in ledger['jobs']:
                guard_plan(plan, plan_path, expected_sha)
                job.update(state='fitting', fitProcess={})
                run_child(command(job, plan), job['fitProcess'], base / (Path(job['output']).name + '-fit.log'), save)
                job['fitProcess']['logSha256'] = digest(Path(job['fitProcess']['logPath']))
                job['verified'] = verify_fitted(job, plan, training)
                guard_plan(plan, plan_path, expected_sha)
                job.update(state='replaying', replayProcess={})
                run_child(command(job, plan, replay=True), job['replayProcess'],
                          base / (Path(job['output']).name + '-replay.log'), save)
                job['replayProcess']['logSha256'] = digest(Path(job['replayProcess']['logPath']))
                job.update(replaySha256=verify_replay(job), replayVerifiedExact=True, state='complete')
                guard_outputs(job)
                save()
                print(json.dumps({key: job[key] for key in ('regime', 'coefficient', 'state')}), flush=True)
            guard_plan(plan, plan_path, expected_sha)
            for job in ledger['jobs']:
                guard_outputs(job)
            guard_plan(plan, plan_path, expected_sha)
            ledger.update(complete=True, finishedAt=time.time())
            save()
            return ledger
        except BaseException as error:
            if 'job' in locals():
                job.update(state='failed', failure=repr(error))
            ledger.update(complete=False, stoppedAt=time.time(), failure=repr(error))
            save()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    declaration = commands.add_parser('declare')
    declaration.add_argument('--features', type=Path, required=True)
    declaration.add_argument('--features-sha256', required=True)
    declaration.add_argument('--base', type=Path, required=True)
    launch = commands.add_parser('run')
    launch.add_argument('--plan', type=Path, required=True)
    launch.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    result = declare(args.features, args.features_sha256, args.base) if args.command == 'declare' else run(args.plan, args.plan_sha256)
    print(json.dumps({'complete': result['complete']}), flush=True)
