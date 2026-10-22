"""Reviewed-plan, PID-gated six-arm raw phonetic-adaptation queue.

The parent never holds the shared MPS lock while a child acquires it. A failure
stops the queue; explicit recovery is required for every partial run.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np
import torch

import multiphone_phonetic_adapt as trainer
import multiphone_phonetic_preflight as preflight
from multiphone_cache import atomic_json, digest
from multiphone_local_head_queue import run_child

HERE = Path(__file__).resolve().parent
ORDER = (('all-age', 'head-only'), ('all-age', 'upper1-lr1e-6'),
         ('child-only', 'head-only'), ('child-only', 'upper1-lr1e-6'),
         ('all-age', 'upper1-lr3e-6'), ('child-only', 'upper1-lr3e-6'))


def jobs(base):
    return [{'regime': regime, 'arm': arm, 'device': 'mps',
             'output': str((base / f'phonetic-adapt-{regime}-{arm}-f0-s7').resolve()), 'state': 'pending'}
            for regime, arm in ORDER]


def command(job):
    return [sys.executable, str(HERE / 'multiphone_phonetic_adapt.py'), 'train',
            '--output', job['output'], '--regime', job['regime'], '--arm', job['arm'], '--device', 'mps']


def contract():
    preflight.source_guard()
    return {'trainerSha256': preflight.APPROVED_TRAINER_SHA, 'recipeSha256': preflight.APPROVED_RECIPE_SHA,
            'runnerSha256': digest(Path(__file__)), 'preflightSourceSha256': digest(Path(preflight.__file__)),
            'launchHelperSha256': digest(HERE / 'multiphone_local_head_queue.py'),
            'sources': trainer.source_hashes(), 'python': sys.executable, 'torch': str(torch.__version__),
            'numpy': np.__version__, 'device': 'mps'}


def make_plan(base, output):
    base, output = base.resolve(), output.resolve()
    trainer.require(base.is_relative_to((HERE / 'outputs').resolve())
                    and output.is_relative_to((HERE / 'outputs').resolve()) and not output.exists(),
                    'Declare a new plan in ignored outputs')
    recipe = trainer.read_json(trainer.RECIPE)
    expected = {(regime, arm['name']) for regime in recipe['regimes'] for arm in recipe['arms']}
    trainer.require(set(ORDER) == expected and len(ORDER) == recipe['plannedTrials'] == 6, 'Order differs from the six fixed arms')
    value = {'complete': True, 'role': 'Predeclared six-arm execution plan; does not authorize inference by itself',
        'contract': contract(), 'base': str(base), 'jobs': jobs(base),
        'requiresCompletedPreflight': True, 'preflightBinding': 'Exact successful measurement artifact is bound at launch after review',
        'allSixArmsFixed': True, 'outcomesCanChangeOrderOrCoverage': False, 'implicitResumeAllowed': False,
        'parentHoldsSharedDeviceLock': False, 'outerOutcomesUsed': False, 'authorTestInferencePerformed': False}
    with output.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
    return value


def verify_preflight(value, declared_contract):
    trainer.require(value['complete'] is True and value['trainerSha256'] == declared_contract['trainerSha256']
                    and value['recipeSha256'] == declared_contract['recipeSha256']
                    and value['sourceSha256'] == declared_contract['preflightSourceSha256']
                    and value['reusedSources'] == declared_contract['sources'] and value['device'] == 'mps'
                    and value['validationInferencePerformed'] is False and value['changedWeightsPersisted'] is False,
                    'Completed MPS preflight binding differs')
    expected = {(regime, role) for regime in ('all-age', 'child-only') for role in ('first-fit', 'longest-fit')}
    trainer.require(len(value['cases']) == 4 and {(row['regime'], row['role']) for row in value['cases']} == expected,
                    'Preflight case coverage differs')
    limit = trainer.read_json(trainer.RECIPE)['maximumEpochZeroProbabilityDifference']
    for row in value['cases']:
        parity = row['parityBeforeUpdates']['mpsRawVsFrozenCache']['maximumAbsoluteProbabilityDifference']
        trainer.require(row['frozenParametersUnchanged'] is True and row['trainableEncoderParameters'] == 12596224
                        and row['changedUpperTensors'] and row['changedHeadTensors']
                        and all(name.startswith('encoder.layers.23.') for name in row['changedUpperTensors'])
                        and len(row['optimizerStepSeconds']) == len(row['gradientNorms']) == 2
                        and all(np.isfinite(x) and x > 0 for x in row['optimizerStepSeconds'] + row['gradientNorms'])
                        and np.isfinite(parity) and 0 <= parity <= limit,
                        'Preflight numerical/gradient/frozen-weight checks did not pass')


def verify_history(history, report, regime, recipe):
    trainer.require(history and history[0]['epoch'] == history[0]['updates'] == 0
                    and len(history) - 1 == report['epochsRun'] <= recipe['maximumEpochs'], 'Epoch-zero/history coverage differs')
    best_loss, best_epoch = float('inf'), 0
    for epoch, record in enumerate(history):
        value = trainer.frozen.selection_loss(record['evaluation'], regime)
        trainer.require(record['epoch'] == epoch and value == record['selectionMacroTargetLogLoss']
                        and np.isfinite(value), 'History metric differs')
        if value < best_loss - recipe['minimumImprovement']:
            best_loss, best_epoch = value, epoch
        trainer.require(epoch == len(history) - 1 or epoch - best_epoch < recipe['patienceEpochs'], 'Continued past patience')
    trainer.require(best_epoch == report['bestEpoch'] and best_loss == report['bestSelectionMacroLogLoss']
                    and (report['epochsRun'] == recipe['maximumEpochs']
                         or report['epochsRun'] - best_epoch == recipe['patienceEpochs']), 'Selection/stopping rule differs')


def verify_completed(job, declared_contract):
    output = Path(job['output'])
    config, report = [trainer.read_json(output / name) for name in ('config.json', 'report.json')]
    trainer.guard(config)
    recipe = trainer.read_json(trainer.RECIPE)
    trainer.require(all(config[key] == job[key] for key in ('regime', 'arm', 'device', 'output'))
                    and config['recipeSha256'] == declared_contract['recipeSha256']
                    and config['sourceSha256'] == declared_contract['sources']
                    and config['phase'] == 'inner' and config['authorTestInferencePerformed'] is False
                    and config['outerOutcomesUsed'] is False, 'Completed trial differs from the fixed plan')
    data, _, directory, arm = trainer.prepare(argparse.Namespace(**job), recipe)
    trainer.require(config['fitRows'] == data['fit'] and config['validationRows'] == data['validation']
                    and config['selectionRows'] == data['selection'] and config['inputFiles'] == data['bindings']
                    and config['warmStart'] == recipe['warmStarts'][job['regime']], 'Fit/input/warm binding differs')
    trainer.require(report['complete'] is True and report['frozenParametersUnchanged'] is True
                    and report['phase'] == 'inner' and report['configSha256'] == digest(output / 'config.json')
                    and report['outerOutcomesUsed'] is False and report['authorTestInferencePerformed'] is False
                    and report['clinicalUseEligible'] is False and report['learnerFeedbackEligible'] is False
                    and all(report[key + 'Sha256'] == digest(output / name) for key, name in
                        (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'),
                         ('prior', 'prior.json'), ('epochZero', 'epoch-zero.json'))), 'Completed report artifact digest differs')
    prediction = trainer.read_json(output / 'predictions.json')
    trainer.require(prediction['rowIndices'] == data['validation'], 'Prediction row order differs')
    metrics = trainer.score_predictions(np.asarray(prediction['probabilities']), [data['cohort']['rows'][i] for i in data['validation']])
    trainer.require(metrics == report['evaluation'] and trainer.frozen.selection_loss(metrics, job['regime']) == report['bestSelectionMacroLogLoss'],
                    'Saved predictions do not reproduce the reported metrics')
    prior = trainer.read_json(output / 'prior.json')
    trainer.require(prior == trainer.read_json(directory / 'prior.json') and prior['evaluation'] == report['sameFitPriorEvaluation'],
                    'Same-fit prior differs')
    saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
    trainer.require(saved['configSha256'] == report['configSha256'] and saved['progress']['bestEpoch'] == report['bestEpoch']
                    and saved['progress']['bestLoss'] == report['bestSelectionMacroLogLoss']
                    and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std'])
                    and set(saved['encoder']) == set(config['trainableEncoderNames'])
                    and all(name.startswith('encoder.layers.23.') for name in saved['encoder'])
                    and sum(t.numel() for t in saved['encoder'].values()) == 12596224 * arm['upperEncoderLayers'],
                    'Selected checkpoint allowlist/config/moments differ')
    trainer.verify_epoch_zero(output, saved['progress'])
    verify_history(trainer.read_json(output / 'history.json'), report, job['regime'], recipe)
    return {'configSha256': report['configSha256'], 'reportSha256': digest(output / 'report.json'),
            'checkpointSha256': report['checkpointSha256'], 'bestEpoch': report['bestEpoch'],
            'epochsRun': report['epochsRun'], 'selectionMacroNLL': report['bestSelectionMacroLogLoss']}


def guard_completed_files(job):
    output = Path(job['output'])
    trainer.require(all(digest(output / name) == job['verified'][key] for key, name in
                        (('configSha256', 'config.json'), ('reportSha256', 'report.json'), ('checkpointSha256', 'best.pt')))
                    and digest(output / 'replay.json') == job['replay']['sha256'], 'Previously verified output changed')
    report = trainer.read_json(output / 'report.json')
    trainer.require(all(report[key + 'Sha256'] == digest(output / name) for key, name in
                        (('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json'),
                         ('epochZero', 'epoch-zero.json'))), 'Previously verified output artifact changed')
    zero = trainer.read_json(output / 'epoch-zero.json')
    trainer.require(zero['predictionsSha256'] == digest(output / 'epoch-zero-predictions.json'), 'Previously verified epoch zero changed')


def run(plan_path, preflight_path):
    plan, measured = trainer.read_json(plan_path), trainer.read_json(preflight_path)
    base = Path(plan['base'])
    trainer.require(base.resolve().is_relative_to((HERE / 'outputs').resolve()), 'Use ignored local outputs')
    trainer.require(plan['contract'] == contract() and plan['jobs'] == jobs(base)
                    and plan['allSixArmsFixed'] is True, 'Reviewed plan/source differs')
    verify_preflight(measured, plan['contract'])
    ledger_path = base / 'phonetic-adaptation-queue-v1.json'
    with (base / 'phonetic-adaptation-queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        trainer.require(not ledger_path.exists() and all(not Path(job['output']).exists() for job in plan['jobs']),
                        'Existing queue/run requires explicit recovery; no implicit resume')
        ledger = {'pid': os.getpid(), 'startedAt': time.time(), 'complete': False,
                  'planPath': str(plan_path.resolve()), 'planSha256': digest(plan_path),
                  'preflightPath': str(preflight_path.resolve()), 'preflightSha256': digest(preflight_path),
                  'contract': plan['contract'], 'jobs': plan['jobs']}
        def save():
            atomic_json(ledger_path, ledger)
            with ledger_path.open('rb') as stream:
                os.fsync(stream.fileno())
        def guard_launch():
            trainer.require(contract() == plan['contract'] and digest(plan_path) == ledger['planSha256']
                            and digest(preflight_path) == ledger['preflightSha256'], 'Launch source/plan/preflight changed')
        save()
        try:
            for job in ledger['jobs']:
                guard_launch()
                run_child(command(job), job, base / (Path(job['output']).name + '.log'), save)
                job['verified'] = verify_completed(job, plan['contract'])
                job['replay'] = {}
                run_child([sys.executable, str(HERE / 'multiphone_phonetic_adapt.py'), 'replay', '--output', job['output']],
                          job['replay'], base / (Path(job['output']).name + '-replay.log'), save)
                result_path = Path(job['output']) / 'replay.json'
                result = trainer.read_json(result_path)
                trainer.require(result['exact'] is True and result['device'] == 'mps'
                                and result['checkpointSha256'] == job['verified']['checkpointSha256']
                                and result['evaluation'] == trainer.read_json(Path(job['output']) / 'report.json')['evaluation'],
                                'Exact same-device replay failed')
                job['replay'].update(verifiedExact=True, sha256=digest(result_path))
                save()
                print(json.dumps({key: job[key] for key in ('regime', 'arm', 'verified')}), flush=True)
            guard_launch()
            for job in ledger['jobs']:
                guard_completed_files(job)
            guard_launch()
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
    commands = parser.add_subparsers(dest='command', required=True)
    declare = commands.add_parser('plan')
    declare.add_argument('--base', type=Path, default=trainer.BASE)
    declare.add_argument('--output', type=Path, required=True)
    launch = commands.add_parser('run')
    launch.add_argument('--plan', type=Path, required=True)
    launch.add_argument('--preflight', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if args.command == 'plan':
        make_plan(args.base, args.output)
    else:
        run(args.plan, args.preflight)
