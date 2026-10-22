"""PID-gated serial CPU queue for the approved80 frozen phonetic-head trials.

Every checkpoint is replayed exactly. Fresh queues only; previous ledgers and
outputs require explicit recovery rather than silent reuse or omitted trials.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np
import torch

import multiphone_phonetic_head as trainer
from multiphone_child_train import score_predictions
from multiphone_local_head_queue import run_child
from multiphone_cache import atomic_json, digest

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
APPROVED_TRAINER_SHA = '1585565d4956a2b116cc2f3d7ff9ff744abfb5070c8473892cb9a72b5b61b9b6'
APPROVED_RECIPE_SHA = '771bdf7c231ff233e6306301aa18c3375f85e26bef29f92a529f1355e65428b3'


def plan(recipe, base):
    jobs = []
    for fold in recipe['folds']:
        for family in recipe['families']:
            for regime in recipe['regimes']:
                for seed in recipe['initializationSeeds']:
                    for rate in recipe['learningRates']:
                        suffix = {0.001: '001', 0.0003: '0003'}[rate]
                        output = base / f'phonetic-head-{family}-{regime}-f{fold}-s{seed}-lr{suffix}'
                        jobs.append({'family': family, 'regime': regime, 'fold': fold, 'seed': seed,
                                     'lr': rate, 'output': str(output.resolve()), 'state': 'pending'})
    trainer.require(len(jobs) == recipe['plannedInnerTrials'] == 80 and len({row['output'] for row in jobs}) == 80,
                    'Declared phonetic matrix differs')
    return jobs


def command(job, binding):
    return [sys.executable, str(HERE / 'multiphone_phonetic_head.py'), 'train', '--binding', str(binding),
            '--output', job['output'], '--family', job['family'], '--regime', job['regime'],
            '--fold', str(job['fold']), '--lr', str(job['lr'])]


def guard(contract):
    trainer.require(digest(Path(__file__)) == contract['runnerSha256']
                    and digest(HERE / 'multiphone_local_head_queue.py') == contract['launchHelperSha256'],
                    'Queue or launch helper changed')
    trainer.source_guard(contract)


def verify_history(history, report, regime, recipe):
    trainer.require(history and len(history) == report['epochsRun'] <= recipe['maximumEpochs'], 'Invalid epoch count')
    best_loss, best_epoch = math.inf, 0
    for epoch, row in enumerate(history, 1):
        value = trainer.selection_loss(row['evaluation'], regime)
        trainer.require(row['epoch'] == epoch and value == row['selectionMacroTargetLogLoss']
                        and math.isfinite(value) and value >= 0 and math.isfinite(row['trainPerRaterLogLoss'])
                        and row['trainPerRaterLogLoss'] >= 0, 'Invalid history/selection metric')
        if value < best_loss - recipe['minimumImprovement']:
            best_loss, best_epoch = value, epoch
        trainer.require(epoch == len(history) or epoch - best_epoch < recipe['patienceEpochs'], 'Continued past declared patience')
    trainer.require(best_epoch == report['bestEpoch'] and best_loss == report['bestSelectionMacroLogLoss']
                    and (len(history) == recipe['maximumEpochs'] or len(history) - best_epoch == recipe['patienceEpochs']),
                    'Best epoch or stopping rule differs')


def verify_complete(job, contract, cohort, splits, recipe, input_files):
    output = Path(job['output'])
    config, report = [trainer.read_json(output / name) for name in ('config.json', 'report.json')]
    exact = {'hidden': 'hiddenWidth', 'dropout': 'dropout', 'weight_decay': 'weightDecay',
             'batch_size': 'batchSizeTargetRows', 'epochs': 'maximumEpochs', 'patience': 'patienceEpochs',
             'threads': 'threads', 'device': 'device'}
    fit, validation, selection = trainer.select_rows(cohort, splits, job['fold'], job['regime'])
    trainer.require(all(config.get(key) == job[key] for key in ('family', 'regime', 'fold', 'seed', 'lr', 'output'))
                    and all(config.get(key) == recipe[value] for key, value in exact.items())
                    and config['sourceSha256'] == contract['sourceSha256'] and config['recipeSha256'] == contract['recipeSha256']
                    and config['binding'] == contract['binding'] and config['bindingSha256'] == contract['bindingSha256']
                    and config['inputFiles'] == input_files and config['fitRows'] == fit
                    and config['validationRows'] == validation and config['selectionRows'] == selection
                    and config['featureWidth'] == (1037 if job['family'].endswith('-scalars') else 1024)
                    and config['phase'] == 'inner' and config['outerOutcomesUsed'] is False
                    and config['classWeighting'] is False, 'Completed run differs from the queue contract')
    trainer.require(report['complete'] is True and report['phase'] == 'inner' and report['outerOutcomesUsed'] is False
                    and report['clinicalUseEligible'] is False and report['learnerFeedbackEligible'] is False
                    and report['configSha256'] == digest(output / 'config.json')
                    and all(report[key + 'Sha256'] == digest(output / filename) for key, filename in
                            (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json'))),
                    'Completed artifact scope/digest differs')
    predictions = trainer.read_json(output / 'predictions.json')
    trainer.require(predictions['rowIndices'] == validation, 'Prediction row order differs')
    rows = [cohort['rows'][index] for index in validation]
    metrics = score_predictions(np.asarray(predictions['probabilities']), rows)
    trainer.require(metrics == report['evaluation']
                    and trainer.selection_loss(metrics, job['regime']) == report['bestSelectionMacroLogLoss'],
                    'Saved predictions do not reproduce proper/ranking metrics')
    priors = trainer.fit_priors([cohort['rows'][index] for index in fit])
    saved_prior = trainer.read_json(output / 'prior.json')
    p = np.asarray([priors[row['targetPhone']]['probabilities'] for row in rows])
    prior_metrics = score_predictions(p, rows)
    trainer.require(config['priorState'] == saved_prior['state'] == priors
                    and saved_prior['rowIndices'] == validation and np.array_equal(p, saved_prior['probabilities'])
                    and saved_prior['evaluation'] == report['sameFitPriorEvaluation'] == prior_metrics
                    and report['selectionMacroLogLossMinusPrior'] == report['bestSelectionMacroLogLoss'] - trainer.selection_loss(prior_metrics, job['regime']),
                    'Same-fit prior or comparator scores differ')
    verify_history(trainer.read_json(output / 'history.json'), report, job['regime'], recipe)
    return {'configSha256': digest(output / 'config.json'), 'reportSha256': digest(output / 'report.json'),
            'checkpointSha256': report['checkpointSha256'], 'bestEpoch': report['bestEpoch'],
            'epochsRun': report['epochsRun'], 'selectionMacroLogLoss': report['bestSelectionMacroLogLoss']}


def selected_groups(jobs, recipe):
    selected = []
    for fold in recipe['folds']:
        for family in recipe['families']:
            for regime in recipe['regimes']:
                for seed in recipe['initializationSeeds']:
                    candidates = [row for row in jobs if (row['fold'], row['family'], row['regime'], row['seed']) ==
                                  (fold, family, regime, seed)]
                    trainer.require(len(candidates) == 2 and {row['lr'] for row in candidates} == set(recipe['learningRates']),
                                    'Group does not contain both declared learning rates')
                    if not all(row['state'] == 'complete' and 'verified' in row and row.get('replay', {}).get('verifiedExact') is True
                               for row in candidates):
                        continue
                    winner = min(candidates, key=lambda row: (row['verified']['selectionMacroLogLoss'], row['lr'], row['verified']['bestEpoch']))
                    selected.append((winner, candidates))
    return selected


def summary(jobs, recipe):
    selections = []
    for job, candidates in selected_groups(jobs, recipe):
        path = Path(job['output']) / 'report.json'
        trainer.require(digest(path) == job['verified']['reportSha256'], 'Verified selected report changed')
        report = trainer.read_json(path)
        selections.append({**{key: job[key] for key in ('family', 'regime', 'fold', 'seed', 'lr', 'output')},
            'verified': job['verified'], 'replaySha256': job['replay']['sha256'],
            'candidates': [{key: row[key] for key in ('lr', 'output', 'verified')} for row in candidates],
            'evaluation': report['evaluation'], 'sameFitPriorEvaluation': report['sameFitPriorEvaluation'],
            'selectionMacroLogLossMinusPrior': report['selectionMacroLogLossMinusPrior']})
    return {'complete': len(selections) == 40, 'selectedGroups': len(selections), 'expectedGroups': 40,
            'verifiedTrials': sum('verified' in row and row.get('replay', {}).get('verifiedExact') is True for row in jobs),
            'expectedTrials': 80, 'selectionRule': recipe['selection'], 'selections': selections,
            'outerOutcomesUsed': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
            'interpretation': 'Conditional inner-selection diagnostics. Ages/splits overlap; do not pool or treat them as independent.',
            'crossFoldPredictionsPooled': False}


def run(base, binding):
    base, binding = base.resolve(), binding.resolve()
    trainer.require(base.is_relative_to((HERE / 'outputs').resolve()), 'Use ignored local outputs')
    ledger_path, summary_path = base / 'phonetic-head-queue-v1.json', base / 'phonetic-head-selection-v1.json'
    with (base / 'phonetic-head-queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        trainer.require(not ledger_path.exists() and not summary_path.exists(), 'Existing ledger/summary requires explicit recovery')
        trainer.require(digest(HERE / 'multiphone_phonetic_head.py') == APPROVED_TRAINER_SHA
                        and digest(trainer.RECIPE) == APPROVED_RECIPE_SHA, 'Approved trainer/recipe changed')
        recipe = trainer.read_json(trainer.RECIPE)
        jobs = plan(recipe, base)
        trainer.require(all(not Path(job['output']).exists() for job in jobs), 'Existing output requires explicit recovery')
        evidence = trainer.read_json(binding)
        trainer.require(evidence['recipeSha256'] == APPROVED_RECIPE_SHA and evidence['sourceSha256'] == trainer.source_hashes()
                        and evidence['complete'] is True, 'Immutable feature binding differs')
        trainer.extraction.guard(evidence['files'])
        cohort, splits = trainer.read_json(Path(evidence['cohortPath'])), trainer.read_json(Path(evidence['splitsPath']))
        contract = {'recipeSha256': APPROVED_RECIPE_SHA, 'sourceSha256': trainer.source_hashes(),
                    'binding': str(binding), 'bindingSha256': digest(binding),
                    'runnerSha256': digest(Path(__file__)), 'launchHelperSha256': digest(HERE / 'multiphone_local_head_queue.py'),
                    'device': 'cpu', 'threads': 2, 'python': sys.executable, 'torch': str(torch.__version__), 'numpy': np.__version__}
        ledger = {'contract': contract, 'pid': os.getpid(), 'startedAt': time.time(), 'complete': False, 'jobs': jobs}

        def save():
            atomic_json(ledger_path, ledger)
            with ledger_path.open('rb') as stream:
                os.fsync(stream.fileno())

        save()
        try:
            for job in jobs:
                guard(contract)
                run_child(command(job, binding), job, base / (Path(job['output']).name + '.log'), save)
                job['verified'] = verify_complete(job, contract, cohort, splits, recipe, evidence['files'])
                job['replay'] = {}
                run_child([sys.executable, str(HERE / 'multiphone_phonetic_head.py'), 'replay', '--output', job['output']],
                          job['replay'], base / (Path(job['output']).name + '-replay.log'), save)
                replay_path = Path(job['output']) / 'replay.json'
                replay = trainer.read_json(replay_path)
                trainer.require(replay['exact'] is True and replay['checkpointSha256'] == job['verified']['checkpointSha256']
                                and replay['evaluation'] == trainer.read_json(Path(job['output']) / 'report.json')['evaluation'],
                                'Checkpoint replay did not verify exactly')
                job['replay'].update(verifiedExact=True, sha256=digest(replay_path))
                save()
                atomic_json(summary_path, summary(jobs, recipe))
                print(json.dumps({key: job[key] for key in ('family', 'regime', 'fold', 'lr', 'state', 'verified')}), flush=True)
            guard(contract)
            trainer.extraction.guard(evidence['files'])
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
    parser.add_argument('--binding', type=Path, default=BASE / 'phonetic-head-binding-v1.json')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    run(args.base, args.binding)
