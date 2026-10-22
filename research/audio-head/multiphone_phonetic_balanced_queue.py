"""Declared CPU queue for20 inner weighted-objective fits and exact replay.

Each weighted family/regime/fold is compared with the already completed,
immutable unweighted family/regime/fold. Outer outcomes are never opened.
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

import multiphone_phonetic_balanced as trainer
from multiphone_cache import atomic_json, digest
from multiphone_local_head_queue import run_child

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
TRAINER_SHA = 'a4b445ce3746b63abea79dc490d0f7fa182f4e75b2b734595c199aff96a2febc'
RECIPE_SHA = 'aca83d80fb1cbd9b43465b151494902535302a2b453db7c1d99d00b42d6f4437'
ARTIFACTS = ('config.json', 'report.json', 'best.pt', 'predictions.json', 'prior.json', 'history.json', 'replay.json')
read_json, require = trainer.read_json, trainer.require


def plan_jobs(base, recipe):
    rows = []
    for fold in recipe['folds']:
        for regime in recipe['regimes']:
            for rate in recipe['learningRates']:
                suffix = {0.001: '001', 0.0003: '0003'}[rate]
                rows.append({'fold': fold, 'regime': regime, 'lr': rate, 'family': 'target-scalars',
                    'output': str((base / f'phonetic-balanced-{regime}-f{fold}-s7-lr{suffix}').resolve()), 'state': 'pending',
                    'baselineOutput': str((base / f'phonetic-head-target-scalars-{regime}-f{fold}-s7-lr{suffix}').resolve())})
    require(len(rows) == recipe['plannedTrials'] == 20 and len({j['output'] for j in rows}) == 20, 'Weighted matrix differs')
    return rows


def contract():
    require(digest(HERE / 'multiphone_phonetic_balanced.py') == TRAINER_SHA and digest(trainer.RECIPE) == RECIPE_SHA,
            'Reviewed weighted trainer/recipe changed')
    return {'trainerSha256': TRAINER_SHA, 'recipeSha256': RECIPE_SHA, 'sourceSha256': trainer.source_hashes(),
            'runnerSha256': digest(Path(__file__)), 'launchHelperSha256': digest(HERE / 'multiphone_local_head_queue.py'),
            'python': sys.executable, 'torch': str(torch.__version__), 'numpy': np.__version__, 'device': 'cpu', 'threads': 2}


def pin_baseline(job):
    output = Path(job['baselineOutput'])
    config, report, replay = [read_json(output / name) for name in ('config.json', 'report.json', 'replay.json')]
    require(all(config[key] == job[key] for key in ('family', 'regime', 'fold', 'lr'))
            and config['seed'] == 7 and config['phase'] == report['phase'] == 'inner'
            and config['sourceSha256'] == trainer.baseline.source_hashes()
            and config['recipeSha256'] == read_json(trainer.RECIPE)['baselineRecipeSha256']
            and config['bindingSha256'] == read_json(trainer.RECIPE)['featureBindingSha256']
            and config['outerOutcomesUsed'] is False and report['complete'] is True and replay['exact'] is True
            and replay['checkpointSha256'] == report['checkpointSha256'] == digest(output / 'best.pt')
            and report['configSha256'] == digest(output / 'config.json')
            and replay['evaluation'] == report['evaluation'], 'Immutable unweighted comparator differs')
    require(all(report[key + 'Sha256'] == digest(output / name) for key, name in
                (('predictions', 'predictions.json'), ('prior', 'prior.json'), ('history', 'history.json'))),
            'Unweighted comparator artifacts differ')
    return {'output': str(output.resolve()), 'files': {name: digest(output / name) for name in ARTIFACTS},
            'selectionMacroNLL': report['bestSelectionMacroLogLoss'], 'bestEpoch': report['bestEpoch']}


def declare_plan(base, binding, output):
    require(base.resolve().is_relative_to((HERE / 'outputs').resolve()) and output.resolve().is_relative_to((HERE / 'outputs').resolve())
            and not output.exists(), 'Declare a fresh weighted plan in ignored outputs')
    recipe = read_json(trainer.RECIPE)
    require(digest(binding) == recipe['featureBindingSha256'], 'Weighted feature binding differs')
    jobs = plan_jobs(base, recipe)
    baseline_ledger_path = base / 'phonetic-head-queue-v1.json'
    original = read_json(baseline_ledger_path)
    require(original['complete'] is True and len(original['jobs']) == 80, 'Original unweighted matrix is incomplete')
    verified_original = {job['output']: job for job in original['jobs']}
    baselines = {j['baselineOutput']: pin_baseline(j) for j in jobs}
    for path, pinned in baselines.items():
        verified = verified_original[path]
        require(verified['state'] == 'complete' and verified['replay']['verifiedExact'] is True
                and verified['verified']['reportSha256'] == pinned['files']['report.json']
                and verified['verified']['configSha256'] == pinned['files']['config.json']
                and verified['verified']['checkpointSha256'] == pinned['files']['best.pt']
                and verified['replay']['sha256'] == pinned['files']['replay.json'], 'Comparator differs from the completed original matrix')
    value = {'complete': True, 'contract': contract(), 'base': str(base.resolve()), 'binding': str(binding.resolve()),
        'bindingSha256': digest(binding), 'jobs': jobs, 'baselines': baselines,
        'baselineLedger': {'path': str(baseline_ledger_path.resolve()), 'sha256': digest(baseline_ledger_path)},
        'plannedTrials': 20, 'phase': 'inner', 'outerOutcomesUsed': False, 'authorTestInferencePerformed': False,
        'selectionRule': recipe['selection'], 'implicitResumeAllowed': False,
        'comparison': 'Same frozen target-scalars family, fit population and selection population. Independent LR choice per objective; all candidates retained.'}
    with output.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return value


def guard_plan(plan, plan_path, expected_sha):
    require(digest(plan_path) == expected_sha and plan['contract'] == contract()
            and digest(Path(plan['binding'])) == plan['bindingSha256'], 'Weighted declaration/source/binding changed')
    require(set(plan['baselines']) == {job['baselineOutput'] for job in plan['jobs']}
            and digest(Path(plan['baselineLedger']['path'])) == plan['baselineLedger']['sha256'], 'Unweighted comparator coverage/ledger changed')
    for baseline in plan['baselines'].values():
        require(all(digest(Path(baseline['output']) / name) == sha for name, sha in baseline['files'].items()),
                'Immutable unweighted baseline changed')


def command(job, binding):
    return [sys.executable, str(HERE / 'multiphone_phonetic_balanced.py'), 'train', '--binding', str(binding),
            '--output', job['output'], '--regime', job['regime'], '--fold', str(job['fold']), '--lr', str(job['lr'])]


def verify_history(history, report, regime, recipe):
    require(history and len(history) == report['epochsRun'] <= recipe['maximumEpochs'], 'Weighted epoch coverage differs')
    best_loss, best_epoch = math.inf, 0
    for epoch, row in enumerate(history, 1):
        value = trainer.baseline.selection_loss(row['evaluation'], regime)
        require(row['epoch'] == epoch and value == row['selectionMacroTargetLogLoss'] and math.isfinite(value)
                and math.isfinite(row['trainWeightedObjective']) and row['trainWeightedObjective'] >= 0,
                'Weighted history metric differs')
        if value < best_loss - recipe['minimumImprovement']:
            best_loss, best_epoch = value, epoch
        require(epoch == len(history) or epoch - best_epoch < recipe['patienceEpochs'], 'Weighted fit continued past patience')
    require(best_epoch == report['bestEpoch'] and best_loss == report['bestSelectionMacroLogLoss']
            and (len(history) == recipe['maximumEpochs'] or len(history) - best_epoch == recipe['patienceEpochs']),
            'Weighted stopping/selected epoch differs')


def verify_completed(job, plan):
    output = Path(job['output'])
    config, report = [read_json(output / name) for name in ('config.json', 'report.json')]
    trainer.guard(config, report['configSha256'])
    baseline_recipe = read_json(trainer.baseline.RECIPE)
    exact = {'hidden': 'hiddenWidth', 'dropout': 'dropout', 'weight_decay': 'weightDecay', 'batch_size': 'batchSizeTargetRows',
             'epochs': 'maximumEpochs', 'patience': 'patienceEpochs', 'threads': 'threads', 'device': 'device'}
    require(all(config[key] == job[key] for key in ('family', 'regime', 'fold', 'lr', 'output'))
            and all(config[key] == baseline_recipe[value] for key, value in exact.items()) and config['seed'] == 7
            and config['sourceSha256'] == plan['contract']['sourceSha256'] and config['recipeSha256'] == plan['contract']['recipeSha256']
            and config['binding'] == plan['binding'] and config['bindingSha256'] == plan['bindingSha256']
            and config['phase'] == 'inner' and config['outerOutcomesUsed'] is False
            and config['authorTestInferencePerformed'] is False and config['empiricalCalibrationEstablished'] is False,
            'Weighted run differs from its declaration')
    args = argparse.Namespace(**config)
    args.output, args.binding = output, Path(config['binding'])
    data = trainer.setup(args)
    require(config['fitRows'] == data['fit'] and config['validationRows'] == data['validation']
            and config['selectionRows'] == data['selection'] and config['classWeightState'] == data['classWeightState']
            and config['priorState'] == data['priors'] and config['inputFiles'] == data['bindings'], 'Weighted actual-fit statistics differ')
    require(report['complete'] is True and report['phase'] == 'inner'
            and all(report[name] is False for name in ('outerOutcomesUsed', 'authorTestInferencePerformed', 'clinicalUseEligible',
                                                      'learnerFeedbackEligible', 'empiricalCalibrationEstablished'))
            and all(report[key + 'Sha256'] == digest(output / name) for key, name in
                (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json'))),
            'Weighted output publication differs')
    prediction = read_json(output / 'predictions.json')
    require(prediction['rowIndices'] == data['validation'], 'Weighted prediction row order differs')
    rows = [data['cohort']['rows'][i] for i in data['validation']]
    metrics = trainer.score_predictions(np.asarray(prediction['probabilities']), rows)
    require(metrics == report['evaluation'] and trainer.baseline.selection_loss(metrics, job['regime']) == report['bestSelectionMacroLogLoss'],
            'Weighted corrected probabilities do not reproduce scores')
    prior = read_json(output / 'prior.json')
    expected_prior = np.asarray([data['priors'][row['targetPhone']]['probabilities'] for row in rows])
    prior_metrics = trainer.score_predictions(expected_prior, rows)
    require(prior['state'] == data['priors'] and prior['rowIndices'] == data['validation']
            and np.array_equal(prior['probabilities'], expected_prior)
            and prior['evaluation'] == report['sameFitPriorEvaluation'] == prior_metrics, 'Weighted same-fit prior differs')
    original = read_json(Path(job['baselineOutput']) / 'config.json')
    require(all(original[key] == config[key] for key in ('fitRows', 'validationRows', 'selectionRows', 'priorState', 'inputFiles')),
            'Weighted and immutable unweighted populations/features differ')
    verify_history(read_json(output / 'history.json'), report, job['regime'], baseline_recipe)
    saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == report['configSha256'] and saved['epoch'] == saved['bestEpoch'] == report['bestEpoch']
            and saved['bestLoss'] == report['bestSelectionMacroLogLoss'] and saved['classWeightState'] == data['classWeightState']
            and all(torch.equal(saved[key], data[key]) for key in ('mean', 'std', 'classWeights')), 'Weighted checkpoint fit statistics differ')
    return {'configSha256': report['configSha256'], 'reportSha256': digest(output / 'report.json'),
            'checkpointSha256': report['checkpointSha256'], 'selectionMacroNLL': report['bestSelectionMacroLogLoss'],
            'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun']}


def selections(jobs, plan):
    result = []
    for fold in range(5):
        for regime in ('all-age', 'child-only'):
            candidates = [j for j in jobs if (j['fold'], j['regime']) == (fold, regime)]
            require(len(candidates) == 2 and {j['lr'] for j in candidates} == {.001, .0003}, 'Incomplete LR candidate group')
            if not all(j.get('replay', {}).get('verifiedExact') is True for j in candidates):
                continue
            chosen = min(candidates, key=lambda j: (j['verified']['selectionMacroNLL'], j['lr'], j['verified']['bestEpoch']))
            baseline = min(candidates, key=lambda j: (plan['baselines'][j['baselineOutput']]['selectionMacroNLL'], j['lr']))
            report = read_json(Path(chosen['output']) / 'report.json')
            original = read_json(Path(baseline['baselineOutput']) / 'report.json')
            require(digest(Path(chosen['output']) / 'report.json') == chosen['verified']['reportSha256'], 'Selected weighted report changed')
            result.append({'fold': fold, 'regime': regime, 'lr': chosen['lr'], 'output': chosen['output'], 'verified': chosen['verified'],
                'unweightedLR': baseline['lr'], 'unweightedOutput': baseline['baselineOutput'],
                'unweightedPins': plan['baselines'][baseline['baselineOutput']], 'evaluation': report['evaluation'],
                'unweightedEvaluation': original['evaluation'], 'sameFitPriorEvaluation': report['sameFitPriorEvaluation'],
                'selectionMacroNLLMinusUnweighted': chosen['verified']['selectionMacroNLL'] - original['bestSelectionMacroLogLoss']})
    return {'complete': len(result) == 10, 'selectedGroups': len(result), 'expectedGroups': 10, 'selections': result,
            'phase': 'inner', 'outerOutcomesUsed': False, 'empiricalCalibrationEstablished': False,
            'interpretation': 'Conditional inner-selection diagnostics; no independent generalization or clinical claim. No cross-fold prediction pooling.'}


def guard_outputs(job):
    output = Path(job['output'])
    require(all(digest(output / name) == job['verified'][key] for key, name in
                (('configSha256', 'config.json'), ('reportSha256', 'report.json'), ('checkpointSha256', 'best.pt')))
            and digest(output / 'replay.json') == job['replay']['sha256'], 'Previously verified weighted output changed')
    report = read_json(output / 'report.json')
    require(all(report[key + 'Sha256'] == digest(output / name) for key, name in
                (('predictions', 'predictions.json'), ('prior', 'prior.json'), ('history', 'history.json'))),
            'Previously verified weighted artifact changed')


def run(plan_path, expected_sha):
    require(digest(plan_path) == expected_sha, 'Weighted plan SHA differs from the approved declaration')
    plan = read_json(plan_path)
    base = Path(plan['base'])
    require(base.resolve().is_relative_to((HERE / 'outputs').resolve()) and plan['jobs'] == plan_jobs(base, read_json(trainer.RECIPE)),
            'Weighted job inventory differs from the fixed recipe')
    guard_plan(plan, plan_path, expected_sha)
    ledger_path, summary_path = base / 'phonetic-balanced-queue-v1.json', base / 'phonetic-balanced-selection-v1.json'
    with (base / 'phonetic-balanced-queue.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not ledger_path.exists() and not summary_path.exists() and all(not Path(j['output']).exists() for j in plan['jobs']),
                'Existing weighted queue/output requires explicit recovery')
        ledger = {'pid': os.getpid(), 'startedAt': time.time(), 'complete': False, 'planPath': str(plan_path.resolve()),
                  'planSha256': expected_sha, 'contract': plan['contract'], 'jobs': plan['jobs']}
        def save():
            atomic_json(ledger_path, ledger)
            with ledger_path.open('rb') as stream:
                os.fsync(stream.fileno())
        save()
        try:
            for job in ledger['jobs']:
                guard_plan(plan, plan_path, expected_sha)
                run_child(command(job, plan['binding']), job, base / (Path(job['output']).name + '.log'), save)
                job['verified'] = verify_completed(job, plan)
                job['replay'] = {}
                run_child([sys.executable, str(HERE / 'multiphone_phonetic_balanced.py'), 'replay', '--output', job['output']],
                          job['replay'], base / (Path(job['output']).name + '-replay.log'), save)
                replay_path = Path(job['output']) / 'replay.json'
                replay = read_json(replay_path)
                require(replay['exact'] is True and replay['checkpointSha256'] == job['verified']['checkpointSha256']
                        and replay['evaluation'] == read_json(Path(job['output']) / 'report.json')['evaluation'], 'Weighted exact replay failed')
                job['replay'].update(verifiedExact=True, sha256=digest(replay_path))
                save()
                guard_plan(plan, plan_path, expected_sha)
                current = selections(ledger['jobs'], plan)
                current['complete'] = False  # Completion requires the final whole-queue guard below.
                atomic_json(summary_path, current)
                print(json.dumps({key: job[key] for key in ('fold', 'regime', 'lr', 'verified')}), flush=True)
            for job in ledger['jobs']:
                guard_outputs(job)
            final = selections(ledger['jobs'], plan)
            require(final['complete'] is True, 'Weighted selection groups are incomplete')
            guard_plan(plan, plan_path, expected_sha)
            for job in ledger['jobs']:
                guard_outputs(job)
            atomic_json(summary_path, final)
            ledger.update(complete=True, finishedAt=time.time(), summarySha256=digest(summary_path))
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
    declare.add_argument('--base', type=Path, default=BASE)
    declare.add_argument('--binding', type=Path, default=BASE / 'phonetic-head-binding-v1.json')
    declare.add_argument('--output', type=Path, required=True)
    launch = commands.add_parser('run')
    launch.add_argument('--plan', type=Path, required=True)
    launch.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if args.command == 'plan':
        declare_plan(args.base, args.binding, args.output)
    else:
        run(args.plan, args.plan_sha256)
