"""Serial CPU execution of the approved forty-trial local-head recipe.

Fresh queues only: any previous ledger/output requires explicit human recovery.
The child waits at a launch gate until its PID has been durably recorded.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import numpy as np
import torch

import multiphone_local_head as trainer
from multiphone_cache import atomic_json, digest

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
APPROVED_TRAINER_SHA = '6c4eccd1df859f2f690b80afb839dd42f0628f80e5db54d67a6f374b362e128d'
APPROVED_RECIPE_SHA = '95a3f40da66f20beee4d563b12a790a7dc3b2a702a76d601a63ffc2d0ebb9283'
LAUNCH_GATE = "import os,sys\nif sys.stdin.buffer.read(1)!=b'1': raise SystemExit(125)\nos.execv(sys.argv[1],sys.argv[1:])\n"


def plan(recipe, base):
    jobs = []
    # Each fold exposes every family/regime before the next fold starts.
    for fold in recipe['folds']:
        for family in recipe['families']:
            for regime in recipe['regimes']:
                for seed in recipe['initializationSeeds']:
                    for rate in recipe['learningRates']:
                        suffix = '001' if rate == .001 else '0003'
                        output = base/f'local-head-{family}-{regime}-f{fold}-s{seed}-lr{suffix}'
                        jobs.append({'family': family, 'regime': regime, 'fold': fold, 'seed': seed,
                                     'lr': rate, 'output': str(output.resolve()), 'state': 'pending'})
    trainer.require(len(jobs) == recipe['plannedInnerTrials'] == 40, 'Declared trial matrix differs')
    return jobs


def guard(contract):
    trainer.require(digest(Path(__file__)) == contract['runnerSha256'], 'Queue implementation changed')
    trainer.source_guard(contract)
    trainer.binding_guard(contract['binding'])


def command(job, base, recipe):
    result = [sys.executable, str(HERE/'multiphone_local_head.py'),
              '--cohort', str(base/'cohort.json'), '--splits', str(base/'splits.json'),
              '--features', str(base/'ctc-local-full/features/features.json'), '--output', job['output'],
              '--family', job['family'], '--regime', job['regime'], '--fold', str(job['fold']),
              '--seed', str(job['seed']), '--lr', str(job['lr']), '--device', 'cpu', '--threads', '2']
    for argument, field in [('hidden', 'hiddenWidth'), ('dropout', 'dropout'), ('weight-decay', 'weightDecay'),
                            ('batch-size', 'batchSizeTargetRows'), ('epochs', 'maximumEpochs'), ('patience', 'patienceEpochs')]:
        result.extend(['--'+argument, str(recipe[field])])
    return result


def run_child(command_line, record, log_path, save):
    process = None
    record.update(state='launching', startedAt=time.time(), command=command_line, logPath=str(log_path))
    save()
    try:
        with log_path.open('x') as log:
            process = subprocess.Popen([sys.executable, '-c', LAUNCH_GATE, *command_line],
                                       stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
            record.update(pid=process.pid, state='running')
            save()  # No model fitting can begin before this exact PID is recorded.
            process.stdin.write(b'1')
            process.stdin.close()
            code = process.wait()
        record.update(exitCode=code, finishedAt=time.time(), state='complete' if code == 0 else 'failed')
        save()
        if code:
            raise RuntimeError(f'Child exited {code}; inspect {log_path}')
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        record.update(state='failed', finishedAt=time.time(), exitCode=process.returncode if process else None)
        save()
        raise
    finally:
        if process is not None and process.stdin is not None and not process.stdin.closed:
            process.stdin.close()


def verify_complete(job, contract):
    output = Path(job['output'])
    config, report = [trainer.read_json(output/name) for name in ('config.json', 'report.json')]
    trainer.require(all(config.get(key) == job[key] for key in ('family', 'regime', 'fold', 'seed', 'lr', 'output'))
                    and config['device'] == 'cpu' and config['threads'] == 2
                    and config['phase'] == 'inner' and config['binding'] == contract['binding']
                    and config['sourceSha256'] == contract['sourceSha256']
                    and config['recipeSha256'] == contract['recipeSha256'], 'Completed run differs from queue contract')
    trainer.require(report['complete'] is True and report['configSha256'] == digest(output/'config.json')
                    and all(report[key+'Sha256'] == digest(output/filename) for key, filename in
                    [('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json')]),
                    'Completed artifact digest differs')
    predictions = trainer.read_json(output/'predictions.json')
    trainer.require(predictions['rowIndices'] == config['validationRows'], 'Completed prediction row set differs')
    cohort = trainer.read_json(Path(config['cohort']))
    rows = [cohort['rows'][index] for index in predictions['rowIndices']]
    metrics = trainer.score_predictions(np.asarray(predictions['probabilities']), rows)
    trainer.require(metrics == report['evaluation']
                    and trainer.selection_loss(metrics, job['regime']) == report['bestSelectionMacroLogLoss'],
                    'Completed metrics differ from saved probabilities')
    return {'configSha256': digest(output/'config.json'), 'reportSha256': digest(output/'report.json'),
            'checkpointSha256': report['checkpointSha256'], 'epochsRun': report['epochsRun'],
            'bestEpoch': report['bestEpoch'], 'selectionMacroLogLoss': report['bestSelectionMacroLogLoss']}


def run(base):
    base = base.resolve()
    trainer.require(base.is_relative_to((HERE/'outputs').resolve()), 'Use ignored local outputs')
    ledger_path = base/'local-head-queue-v1.json'
    with (base/'local-head-queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        trainer.require(not ledger_path.exists(), 'Existing ledger requires explicit recovery; no silent reuse')
        trainer.require(digest(HERE/'multiphone_local_head.py') == APPROVED_TRAINER_SHA
                        and digest(trainer.RECIPE) == APPROVED_RECIPE_SHA, 'Approved trainer or recipe changed')
        recipe = trainer.read_json(trainer.RECIPE)
        jobs = plan(recipe, base)
        trainer.require(all(not Path(job['output']).exists() for job in jobs), 'Existing output requires explicit recovery')
        _, _, _, _, _, binding = trainer.load_local_inputs(base/'cohort.json', base/'splits.json',
                                                          base/'ctc-local-full/features/features.json')
        trainer.require(all(binding[key+'Sha256'] == recipe[key+'Sha256'] for key in ('cohort', 'splits', 'features')),
                        'Approved recipe input digests differ')
        contract = {'recipePath': str(trainer.RECIPE), 'recipeSha256': APPROVED_RECIPE_SHA,
                    'sourceSha256': {name: digest(HERE/name) for name in trainer.SOURCES}, 'binding': binding,
                    'runnerSha256': digest(Path(__file__)), 'device': 'cpu', 'threads': 2,
                    'python': sys.executable, 'torch': str(torch.__version__), 'numpy': np.__version__}
        ledger = {'contract': contract, 'pid': os.getpid(), 'startedAt': time.time(), 'complete': False, 'jobs': jobs}
        def save():
            atomic_json(ledger_path, ledger)
        save()
        try:
            for job in jobs:
                guard(contract)
                run_child(command(job, base, recipe), job, base/(Path(job['output']).name+'.log'), save)
                job['verified'] = verify_complete(job, contract)
                if job['fold'] == 0:
                    job['replay'] = {}
                    run_child(command(job, base, recipe)+['--replay'], job['replay'],
                              base/(Path(job['output']).name+'-replay.log'), save)
                    replay_path = Path(job['output'])/'replay.json'
                    replay = trainer.read_json(replay_path)
                    trainer.require(replay['maximumAbsoluteProbabilityDifference'] == 0.
                                    and replay['checkpointSha256'] == job['verified']['checkpointSha256'],
                                    'Fold-zero checkpoint replay is not exact')
                    job['replay']['sha256'] = digest(replay_path)
                save()
                print(json.dumps({key: job[key] for key in ('family', 'regime', 'fold', 'lr', 'state', 'verified')}), flush=True)
            guard(contract)
            ledger.update(complete=True, finishedAt=time.time())
            save()
        except BaseException as error:
            if 'job' in locals():
                job.update(state='failed', failure=repr(error))
            ledger.update(complete=False, stoppedAt=time.time(), failure=repr(error))
            save()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=BASE)
    arguments = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    run(arguments.base)
