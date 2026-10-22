"""Five fixed child ranking fits, gated by exact NLL-control equivalence.

The immutable declaration binds the actual preflight, not a promise to run it.
Every fit requires a separate exact replay; incomplete runs are never reused.
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

import multiphone_ranking_train as trainer
from multiphone_cache import atomic_json, digest
from multiphone_child_train import score_predictions
from multiphone_local_head_queue import run_child

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-ranking-objective-protocol.md'
PROTOCOL_SHA = 'dc94968abf6497516e67cea3df764fe5d0c47c40c9005345336765dba8aad2ac'
FIT_FILES = ('config.json', 'best.pt', 'last.pt', 'history.json', 'status.json', 'predictions.json', 'support.json')
CHECKS = ('NLL', 'model', 'optimizer', 'moments', 'targetIDs', 'rowOrder', 'pairRNGUntouched')
read_json, require = trainer.read_json, trainer.require


def contract():
    require(digest(PROTOCOL) == PROTOCOL_SHA and tuple(trainer.FOLDS) == tuple(range(5))
            and trainer.COEFFICIENT == .1 and trainer.REGIME == 'child-only', 'Fixed ranking scope changed')
    return {'trainerSha256': digest(Path(trainer.__file__)), 'recipeSha256': digest(trainer.RECIPE),
        'sourceSha256': trainer.source_hashes(), 'runnerSha256': digest(Path(__file__)),
        'launchHelperSha256': digest(HERE / 'multiphone_local_head_queue.py'),
        'protocolSha256': PROTOCOL_SHA, 'python': sys.executable, 'torch': str(torch.__version__),
        'numpy': np.__version__, 'device': 'cpu', 'threads': 2}


def jobs(base):
    return [{'fold': fold, 'regime': 'child-only', 'coefficient': .1,
             'output': str((base / f'fold-{fold}-child-only-ranking-0p1').resolve()), 'state': 'pending'}
            for fold in range(5)]


def checked_preflight(path, expected_sha, declared):
    require(digest(path) == expected_sha, 'Caller-pinned equivalence preflight changed')
    value = trainer.validate_preflight(path, expected_sha)
    require(value['complete'] is True and value['exact'] is True and value['fitOnly'] is True
            and value['validationInferencePerformed'] is False and value['coefficient'] == 0
            and value['fold'] == 0 and value['regime'] == 'child-only'
            and type(value['comparedUpdates']) is int and value['comparedUpdates'] > 0
            and set(value['exactChecks']) == set(CHECKS) and all(value['exactChecks'][k] is True for k in CHECKS)
            and value['sourceSha256'] == declared['sourceSha256']
            and value['recipeSha256'] == declared['recipeSha256'], 'Actual exact control-equivalence evidence differs')
    require(digest(path) == expected_sha, 'Equivalence preflight changed while checking')
    return value


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def declare(preflight_path, preflight_sha, base):
    require(not base.exists() and base.resolve().is_relative_to((HERE / 'outputs').resolve()),
            'Choose a fresh ranking directory in ignored outputs')
    declared = contract()
    checked_preflight(preflight_path, preflight_sha, declared)
    base.mkdir(parents=True, mode=0o700)
    training_path = base / 'training-plan.json'
    try:
        training = trainer.declare(preflight_path, preflight_sha, training_path)
        training_sha = digest(training_path)
        require(read_json(training_path) == training, 'Saved ranking training declaration differs')
        trainer.plan_guard(training, training_path, training_sha)
        checked_preflight(preflight_path, preflight_sha, declared)
        require(contract() == declared, 'Ranking source changed during declaration')
        value = {'complete': True, 'base': str(base.resolve()), 'contract': declared,
            'trainingPlan': {'path': str(training_path.resolve()), 'sha256': training_sha},
            'preflight': {'path': str(preflight_path.resolve()), 'sha256': preflight_sha},
            'jobs': jobs(base), 'plannedTrials': 5, 'allFiveArmsFixed': True,
            'controlRefitsPerformed': False, 'implicitResumeAllowed': False,
            'outcomesCanChangeOrderOrCoverage': False, **{k: False for k in trainer.FALSE_FLAGS}}
        guard_plan(value, None, None)
        write_new(base / 'queue-plan.json', value)
        return value
    except BaseException as error:
        atomic_json(base / 'declaration-failure.json', {'complete': False, 'failure': repr(error)})
        raise


def guard_plan(plan, path, expected_sha):
    base = Path(plan['base'])
    require((path is None and expected_sha is None or path is not None and digest(path) == expected_sha)
            and plan['complete'] is True and plan['contract'] == contract()
            and base.resolve().is_relative_to((HERE / 'outputs').resolve()) and plan['jobs'] == jobs(base)
            and plan['plannedTrials'] == 5 and plan['allFiveArmsFixed'] is True
            and plan['controlRefitsPerformed'] is False and plan['implicitResumeAllowed'] is False
            and plan['outcomesCanChangeOrderOrCoverage'] is False
            and all(plan[k] is False for k in trainer.FALSE_FLAGS), 'Ranking queue declaration changed')
    checked_preflight(Path(plan['preflight']['path']), plan['preflight']['sha256'], plan['contract'])
    pinned = plan['trainingPlan']
    require(Path(pinned['path']) == base / 'training-plan.json', 'Training plan location differs')
    training = read_json(Path(pinned['path']))
    trainer.plan_guard(training, Path(pinned['path']), pinned['sha256'])
    require(training['sourceSha256'] == plan['contract']['sourceSha256']
            and training['recipeSha256'] == plan['contract']['recipeSha256']
            and training['preflight'] == plan['preflight']
            and training['arms'] == [{k: j[k] for k in ('fold', 'regime', 'coefficient')} for j in plan['jobs']]
            and set(training['populations']) == {str(f) for f in range(5)},
            'Training declaration or verified preflight binding differs')
    return training


def command(job, plan, replay=False):
    prefix = [sys.executable, str(HERE / 'multiphone_ranking_train.py')]
    if replay:
        return prefix + ['replay', '--output', job['output']]
    return prefix + ['fit', '--plan', plan['trainingPlan']['path'],
        '--plan-sha256', plan['trainingPlan']['sha256'], '--fold', str(job['fold']), '--output', job['output']]


def verify_history(history, report):
    require(3 <= len(history) <= 7 and history[0]['evaluation'] == report['warmEvaluation'],
            'Ranking epoch-zero/history coverage differs')
    best, best_epoch = float('inf'), 0
    for epoch, item in enumerate(history):
        loss = item['evaluation']['ages6to12']['macroTargetLogLoss']
        require(item['epoch'] == epoch and np.isfinite(loss) and item['selectionMacroNLL'] == loss,
                'Ranking history clean selection metric differs')
        if loss < best - 1e-7:
            best, best_epoch = loss, epoch
        require(epoch == len(history) - 1 or epoch - best_epoch < 2, 'Ranking continued beyond fixed patience')
    require(report['epochsRun'] == len(history) - 1 and report['bestEpoch'] == best_epoch
            and report['bestCleanSelectionNLL'] == best
            and (len(history) == 7 or len(history) - 1 - best_epoch == 2), 'Ranking stopping or selected epoch differs')
    return best, best_epoch


def checked_probabilities(saved, indices, key):
    p = np.asarray(saved[key], dtype=np.float64)
    require(saved['rowIndices'] == indices and len(set(indices)) == len(indices)
            and p.shape == (len(indices), 3) and np.isfinite(p).all() and (p >= 0).all()
            and (p <= 1).all() and np.allclose(p.sum(1), 1, rtol=0, atol=1e-6), 'Invalid complete ranking probabilities')
    return p


def verify_fitted(job, plan, training):
    output = Path(job['output']); report_sha = digest(output / 'report.json')
    config, report = read_json(output / 'config.json'), read_json(output / 'report.json')
    population = training['populations'][str(job['fold'])]
    require(config['planPath'] == plan['trainingPlan']['path'] and config['planSha256'] == plan['trainingPlan']['sha256']
            and all(config[k] == report[k] == job[k] for k in ('fold', 'regime', 'coefficient'))
            and config['sourceSha256'] == plan['contract']['sourceSha256']
            and config['recipeSha256'] == plan['contract']['recipeSha256']
            and all(config[k] == population[k] for k in
                    ('fitRows', 'validationRows', 'selectionRows', 'inputFiles', 'meanDigest', 'stdDigest'))
            and config['studentTrainingMode'] == 'eval-with-gradients' and config['nllSeed'] == 7
            and config['pairSeed'] == 20260926 and config['pairsPerUpdate'] == 64,
            'Ranking configuration differs from its declaration')
    require(report['complete'] is False and report['fitComplete'] is True
            and report['state'] == 'fitted-awaiting-independent-replay'
            and all(config[k] is False and report[k] is False for k in trainer.FALSE_FLAGS)
            and set(report['filesSha256']) == set(FIT_FILES)
            and all(digest(output / name) == sha for name, sha in report['filesSha256'].items()), 'Ranking fitted artifacts differ')
    require(read_json(output / 'status.json') == dict(complete=False, fitComplete=True,
            state='fitted-awaiting-independent-replay', bestEpoch=report['bestEpoch'], epochsRun=report['epochsRun']),
            'Ranking fitted status differs')
    require(read_json(output / 'support.json') == population['support'], 'Declared fitting-pair support differs')
    history = read_json(output / 'history.json')
    best, epoch = verify_history(history, report)
    require(history[epoch]['evaluation'] == report['evaluation'], 'Selected history evaluation differs')
    saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == report['filesSha256']['config.json']
            and saved['epoch'] == saved['bestEpoch'] == epoch and saved['bestLoss'] == best
            and trainer.tensor_digest(saved['mean']) == population['meanDigest']
            and trainer.tensor_digest(saved['std']) == population['stdDigest'],
            'Selected ranking checkpoint differs')
    cohort_pin = config['inputFiles']['clean/cohort']
    require(digest(Path(cohort_pin['path'])) == cohort_pin['sha256'], 'Ranking cohort changed')
    cohort = read_json(Path(cohort_pin['path'])); indices = config['validationRows']
    rows = [cohort['rows'][i] for i in indices]
    predictions = read_json(output / 'predictions.json')
    for key, metric in (('probabilities', 'evaluation'), ('warmProbabilities', 'warmEvaluation')):
        require(score_predictions(checked_probabilities(predictions, indices, key), rows) == report[metric],
                'Ranking probabilities do not reproduce recorded metrics')
    require(report['evaluation']['ages6to12']['macroTargetLogLoss'] == best, 'Ranking selected metric differs')
    require(digest(output / 'report.json') == report_sha and digest(Path(cohort_pin['path'])) == cohort_pin['sha256']
            and all(digest(output / name) == sha for name, sha in report['filesSha256'].items()),
            'Ranking artifact changed while verifying')
    return {'files': {**report['filesSha256'], 'report.json': report_sha}, 'bestEpoch': epoch,
            'epochsRun': report['epochsRun'], 'cleanSelectionMacroNLL': best, 'validationRows': len(indices)}


def guard_fitted(job):
    require(all(digest(Path(job['output']) / name) == sha for name, sha in job['verified']['files'].items()),
            'Previously verified ranking artifact changed')


def verify_replay(job):
    guard_fitted(job)
    path = Path(job['output']) / 'replay.json'; sha = digest(path); replay = read_json(path)
    require(replay['complete'] is True and replay['exact'] is True and replay['state'] == 'verified'
            and all(replay[k] == job[k] for k in ('fold', 'regime', 'coefficient'))
            and replay['rows'] == job['verified']['validationRows']
            and replay['checkpointSha256'] == job['verified']['files']['best.pt']
            and replay['reportSha256'] == job['verified']['files']['report.json'], 'Independent exact ranking replay differs')
    guard_fitted(job)
    require(digest(path) == sha, 'Ranking replay changed while verifying')
    return sha


def guard_outputs(job):
    require(job['state'] == 'complete' and job['replayVerifiedExact'] is True, 'Ranking arm has not completed exact replay')
    guard_fitted(job)
    require(digest(Path(job['output']) / 'replay.json') == job['replaySha256'], 'Verified ranking replay changed')
    for key in ('fitProcess', 'replayProcess'):
        process = job[key]
        require(process['state'] == 'complete' and process['exitCode'] == 0
                and digest(Path(process['logPath'])) == process['logSha256'], 'Verified ranking process or log changed')


def run(plan_path, expected_sha):
    require(digest(plan_path) == expected_sha, 'Caller-pinned queue declaration differs')
    plan = read_json(plan_path); training = guard_plan(plan, plan_path, expected_sha)
    base = Path(plan['base']); ledger_path = base / 'queue-ledger.json'
    with (base / 'queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not ledger_path.exists() and all(not Path(j['output']).exists() for j in plan['jobs']),
                'Existing ranking queue or output requires explicit recovery')
        ledger = {'pid': os.getpid(), 'parentPid': os.getppid(), 'processSessionId': os.getsid(0),
            'startedAt': time.time(), 'complete': False, 'planPath': str(plan_path.resolve()),
            'planSha256': expected_sha, 'contract': plan['contract'], 'preflight': plan['preflight'], 'jobs': deepcopy(plan['jobs'])}

        def save():
            atomic_json(ledger_path, ledger)
            with ledger_path.open('rb') as stream: os.fsync(stream.fileno())

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
                run_child(command(job, plan, replay=True), job['replayProcess'], base / (Path(job['output']).name + '-replay.log'), save)
                job['replayProcess']['logSha256'] = digest(Path(job['replayProcess']['logPath']))
                job.update(replaySha256=verify_replay(job), replayVerifiedExact=True, state='complete')
                guard_outputs(job); save()
                print(json.dumps({k: job[k] for k in ('fold', 'regime', 'coefficient', 'state')}), flush=True)
            guard_plan(plan, plan_path, expected_sha)
            for job in ledger['jobs']: guard_outputs(job)
            guard_plan(plan, plan_path, expected_sha)
            ledger.update(complete=True, finishedAt=time.time()); save()
            return ledger
        except BaseException as error:
            if 'job' in locals(): job.update(state='failed', failure=repr(error))
            ledger.update(complete=False, stoppedAt=time.time(), failure=repr(error)); save()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    declaration = commands.add_parser('declare')
    declaration.add_argument('--preflight', type=Path, required=True)
    declaration.add_argument('--preflight-sha256', required=True)
    declaration.add_argument('--base', type=Path, required=True)
    launch = commands.add_parser('run'); launch.add_argument('--plan', type=Path, required=True)
    launch.add_argument('--plan-sha256', required=True)
    args = parser.parse_args(); signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    value = declare(args.preflight, args.preflight_sha256, args.base) if args.command == 'declare' else run(args.plan, args.plan_sha256)
    print(json.dumps({'complete': value['complete']}), flush=True)
