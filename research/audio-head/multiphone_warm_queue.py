"""Four locked warm-mean adaptation trials, with an external epoch-zero choice.

This fresh-only runner never resumes partial work. The global MPS lock prevents
overlap with other queued adaptation jobs. Standalone replay must finish before
launch. Any gain is joint continued training.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np
import torch

import multiphone_adapt as adapt
import multiphone_adapt_queue as shared
import multiphone_train as frozen
from multiphone_cache import atomic_json, digest
from multiphone_local_head_queue import run_child
from multiphone_local_train import read_json, require

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
RECIPE = HERE/'experiments/multiphone-warm-adaptation-v1.json'
LOCKED_RECIPE_SHA = 'f4439b39e7f9dc28a2f50832b45ac3cac4c0adee198fa5cac567460e120404ef'
HELPERS = ('multiphone_warm_queue.py', 'multiphone_adapt_queue.py', 'multiphone_local_head_queue.py',
           'multiphone_local_train.py')


def metrics_for(predictions, cohort, expected_rows):
    indices = predictions['rowIndices']
    require(indices == sorted(expected_rows), 'Prediction rows differ from the declared inner validation')
    probabilities = np.asarray(predictions['probabilities'], dtype=np.float64)
    rows = [cohort['rows'][index] for index in indices]
    counts = np.asarray([row['raterCounts'] for row in rows], dtype=np.float64)
    result = adapt.distribution_metrics(probabilities, counts)
    per_phone = {}
    for phone in sorted({row['targetPhone'] for row in rows}):
        mask = np.asarray([row['targetPhone'] == phone for row in rows])
        per_phone[phone] = adapt.distribution_metrics(probabilities[mask], counts[mask])
    result['perTarget'] = per_phone
    result['macroTargetLogLoss'] = float(np.mean([value['perRaterLogLoss'] for value in per_phone.values()]))
    for name, condition in [('ages6to12', lambda age: 6 <= age <= 12), ('ages13plus', lambda age: age >= 13)]:
        mask = np.asarray([condition(row['age']) for row in rows])
        result[name] = adapt.distribution_metrics(probabilities[mask], counts[mask]) if mask.any() else None
    return result


def baseline_binding(baseline, contract, cohort):
    path = Path(baseline['checkpointPath'])
    directory = path.parent
    bindings = {name: {'path': str(directory/filename), 'sha256': digest(directory/filename)} for name, filename in
                [('checkpoint', 'best.pt'), ('config', 'config.json'), ('report', 'report.json'), ('predictions', 'predictions.json')]}
    require(path.name == 'best.pt' and all(bindings[name]['sha256'] == baseline[name+'Sha256']
            for name in ('checkpoint', 'config', 'report')), 'Declared frozen baseline artifact differs')
    config, report = read_json(directory/'config.json'), read_json(directory/'report.json')
    recipe = contract['recipe']
    expected = {'cohortSha256': contract['cohortSha256'], 'splitsSha256': contract['splitsSha256'],
                'cacheIndexSha256': contract['caches'][baseline['encoder']]['indexSha256'],
                'phase': 'inner', 'fold': 0, 'seed': 7, 'head': 'mean', 'hidden': recipe['hiddenWidth'],
                'dropout': recipe['headDropout'], 'lr': .0003}
    require(all(config.get(key) == value for key, value in expected.items())
            and all(contract['sourceSha256'].get(name) == sha for name, sha in config['sourceSha256'].items()),
            'Frozen baseline architecture, partition, cache or source differs')
    saved = torch.load(path, map_location='cpu', weights_only=True)
    require(saved['configSha256'] == bindings['config']['sha256']
            and report['configSha256'] == bindings['config']['sha256']
            and report['checkpointSha256'] == bindings['checkpoint']['sha256']
            and saved['epoch'] == report['bestEpoch'] == baseline['selectedEpoch']
            and saved['mean'].shape == saved['std'].shape == (768,)
            and torch.isfinite(saved['mean']).all() and torch.isfinite(saved['std']).all()
            and (saved['std'] > 0).all(), 'Frozen baseline checkpoint/config/normalization binding differs')
    head = adapt.HEADS['mean'](hidden_dim=recipe['hiddenWidth'], dropout=recipe['headDropout'])
    head.load_state_dict(saved['model'], strict=True)
    require(shared.finite_tensors(saved['model']), 'Frozen head contains nonfinite weights')
    predictions = read_json(directory/'predictions.json')
    metrics = metrics_for(predictions, cohort, contract['evaluationRows'])
    require(shared.same_metrics(report['evaluation'], metrics)
            and math.isclose(metrics['macroTargetLogLoss'], baseline['innerMacroTargetLogLoss'], rel_tol=1e-12, abs_tol=1e-12),
            'Frozen baseline proper metrics differ from its saved probabilities')
    data = frozen.StudyData(cohort, Path(contract['base'])/shared.CACHE[baseline['encoder']],
                            contract['fitRows']+contract['evaluationRows'])
    fit_clips = sorted({cohort['rows'][index]['clipIndex'] for index in contract['fitRows']})
    mean, std = data.normalization(fit_clips)
    require(torch.equal(mean, saved['mean']) and torch.equal(std, saved['std']),
            'Frozen baseline moments differ from actual fit-only cache rows')
    replay_metrics, replay_predictions = frozen.evaluate(head, data, contract['evaluationRows'], mean, std,
                                                        'cpu', config['batch_size'])
    require(replay_predictions == predictions and shared.same_metrics(replay_metrics, report['evaluation']),
            'Frozen checkpoint does not exactly replay epoch-zero probabilities')
    warm = {'path': str(path.resolve()), 'sha256': bindings['checkpoint']['sha256'],
            'configSha256': bindings['config']['sha256'], 'reportSha256': bindings['report']['sha256'],
            'epoch': baseline['selectedEpoch']}
    return {'bindings': bindings, 'warmStart': warm, 'evaluation': metrics, 'checkpointReplayExact': True}


def capture_contract(base):
    torch.set_num_threads(2)
    require(base.resolve().is_relative_to((HERE/'outputs').resolve()), 'Keep warm runs in ignored research outputs')
    require(digest(RECIPE) == LOCKED_RECIPE_SHA, 'Locked warm recipe changed')
    recipe = read_json(RECIPE)
    require(recipe['phase'] == 'inner' and recipe['folds'] == [0] and recipe['initializationSeeds'] == [7]
            and recipe['plannedTrials'] == 4 and recipe['head'] == 'mean' and recipe['upperEncoderLayers'] == 1
            and recipe['backboneLearningRates'] == [1e-6, 3e-6], 'Unexpected warm study matrix')
    source = {name: digest(HERE/name) for name in adapt.SOURCES}
    require(all(source.get(name) == sha for name, sha in recipe['sourceSha256'].items()), 'Declared training source changed')
    require(digest(base/'cohort.json') == recipe['cohortSha256'] and digest(base/'splits.json') == recipe['splitsSha256'],
            'Warm cohort or splits differ')
    namespace = argparse.Namespace(cohort=base/'cohort.json', splits=base/'splits.json', phase='inner', fold=0)
    cohort, fit, validation = adapt.read_study(namespace)
    contract = {'recipe': recipe, 'recipePath': str(RECIPE.resolve()), 'recipeSha256': LOCKED_RECIPE_SHA,
                'base': str(base.resolve()), 'sourceSha256': source,
                'helperSourceSha256': {name: digest(HERE/name) for name in HELPERS},
                'cohortSha256': recipe['cohortSha256'], 'splitsSha256': recipe['splitsSha256'],
                'fitRows': fit, 'evaluationRows': validation, 'caches': {}, 'baselines': {},
                'torch': str(torch.__version__), 'numpy': np.__version__, 'device': 'mps', 'threads': 2}
    for encoder in ('wav2vec2-base', 'wavlm-base-plus'):
        cache = base/shared.CACHE[encoder]
        config, index = read_json(cache/'config.json'), read_json(cache/'index.json')
        require(config['encoder'] == shared.IDENTITIES[encoder] and config['cohortSha256'] == recipe['cohortSha256']
                and index['complete'] is True and index['configSha256'] == digest(cache/'config.json')
                and set(index['entries']) == {clip['id'] for clip in cohort['clips']}, 'Warm feature cache identity/coverage differs')
        for clip in cohort['clips']:
            entry = index['entries'][clip['id']]
            path = (cache/entry['path']).resolve()
            require(path.is_relative_to(cache.resolve()) and entry['audioSha256'] == clip['audioSha256']
                    and digest(path) == entry['sha256'], 'Warm cache entry audio/file binding differs')
        contract['caches'][encoder] = {'configSha256': digest(cache/'config.json'), 'indexSha256': digest(cache/'index.json')}
    require({entry['encoder'] for entry in recipe['baselines']} == set(contract['caches'])
            and len(recipe['baselines']) == 2, 'Require one baseline per encoder')
    for baseline in recipe['baselines']:
        contract['baselines'][baseline['encoder']] = baseline_binding(baseline, contract, cohort)
    guard(contract)
    return contract


def guard(contract):
    base = Path(contract['base'])
    require(digest(RECIPE) == contract['recipeSha256']
            and digest(base/'cohort.json') == contract['cohortSha256']
            and digest(base/'splits.json') == contract['splitsSha256']
            and all(digest(HERE/name) == sha for name, sha in (contract['sourceSha256'] | contract['helperSourceSha256']).items()),
            'Warm recipe, source or study input changed')
    for encoder, binding in contract['caches'].items():
        cache = base/shared.CACHE[encoder]
        require(digest(cache/'config.json') == binding['configSha256']
                and digest(cache/'index.json') == binding['indexSha256'], 'Warm cache identity changed')
    require(all(digest(Path(item['path'])) == item['sha256'] for baseline in contract['baselines'].values()
                for item in baseline['bindings'].values()), 'Immutable frozen baseline changed')


def job_arguments(contract):
    recipe, base = contract['recipe'], Path(contract['base'])
    jobs = []
    for rate in (1e-6, 3e-6):
        for encoder in ('wav2vec2-base', 'wavlm-base-plus'):
            label = '1e-6' if rate == 1e-6 else '3e-6'
            arguments = {'cohort': str(base/'cohort.json'), 'splits': str(base/'splits.json'),
                'cache': str(base/shared.CACHE[encoder]), 'output': str(base/f'warm-{shared.SHORT[encoder]}-mean-u1-f0-s7-blr{label}'),
                'encoder': encoder, 'head': 'mean', 'phase': 'inner', 'fold': 0, 'device': 'mps', 'upper_layers': 1,
                'seed': 7, 'hidden': recipe['hiddenWidth'], 'dropout': recipe['headDropout'], 'backbone_lr': rate,
                'head_lr': recipe['headLearningRate'], 'weight_decay': recipe['weightDecay'],
                'max_gradient_norm': recipe['maximumGradientNorm'], 'accumulation_clips': recipe['gradientAccumulationClips'],
                'epochs': recipe['maximumEpochs'], 'patience': recipe['patienceEpochs'], 'threads': 2,
                'save_every_updates': recipe['checkpointEveryUpdates'],
                'warm_head': contract['baselines'][encoder]['warmStart']['path'], 'selection': None}
            jobs.append(arguments)
    return jobs


def verify_config(output, arguments, contract):
    config = read_json(output/'config.json')
    expected = arguments | {'sourceSha256': contract['sourceSha256'], 'cohortSha256': contract['cohortSha256'],
        'splitsSha256': contract['splitsSha256'], 'cacheIndexSha256': contract['caches'][arguments['encoder']]['indexSha256'],
        'encoderIdentity': shared.IDENTITIES[arguments['encoder']],
        'warmStart': contract['baselines'][arguments['encoder']]['warmStart'], 'torch': contract['torch'], 'numpy': contract['numpy'],
        'normalization': 'fixed frame moments from fit speakers only in pinned frozen encoder cache',
        'encoderMode': 'eval; upper transformer layers receive gradients; lower weights/preprocessor frozen',
        'authorPartition': 'train', 'authorTestInferencePerformed': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
        'fitRows': contract['fitRows'], 'evaluationRows': contract['evaluationRows']}
    metadata = {'trainableEncoderNames', 'trainableEncoderParameters', 'trainableHeadParameters'}
    require(set(config) == set(expected) | metadata and all(config.get(key) == value for key, value in expected.items()),
            'Warm configuration or exact warmStart metadata differs')
    names = config['trainableEncoderNames']
    require(names and len(set(names)) == len(names) and all(name.startswith('encoder.layers.11.') for name in names)
            and all(type(config[key]) is int and config[key] > 0 for key in metadata if key != 'trainableEncoderNames'),
            'Invalid warm trainable-parameter inventory')
    return config


def verify_complete(output, arguments, contract):
    config = verify_config(output, arguments, contract)
    report, status = read_json(output/'report.json'), read_json(output/'status.json')
    require(report.get('complete') is True and status.get('complete') is True
            and report['configSha256'] == digest(output/'config.json') and report['checkpointSha256'] == digest(output/'best.pt')
            and report['evaluationRole'] == 'inner selection' and report['clinicalUseEligible'] is False
            and report['learnerFeedbackEligible'] is False, 'Warm completed report/checkpoint binding differs')
    saved = shared.verify_checkpoint(output/'best.pt', config, resume=False)
    frozen = torch.load(Path(arguments['warm_head']), map_location='cpu', weights_only=True)
    require(torch.equal(saved['mean'], frozen['mean']) and torch.equal(saved['std'], frozen['std']),
            'Warm checkpoint normalization differs from immutable baseline')
    require(1 <= report['bestEpoch'] <= report['epochsRun'] <= arguments['epochs'], 'Invalid completed warm epoch count')
    metrics = metrics_for(read_json(output/'predictions.json'), read_json(Path(arguments['cohort'])), config['evaluationRows'])
    require(shared.same_metrics(metrics, report['evaluation']), 'Warm proper metrics differ from saved predictions')
    shared.verify_history(output, arguments, report, saved)
    baseline = contract['baselines'][arguments['encoder']]
    baseline_loss = baseline['evaluation']['macroTargetLogLoss']
    adapted_loss = metrics['macroTargetLogLoss']
    return {'configSha256': digest(output/'config.json'), 'checkpointSha256': digest(output/'best.pt'),
            'reportSha256': digest(output/'report.json'), 'predictionsSha256': digest(output/'predictions.json'),
            'historySha256': digest(output/'history.json'), 'bestEpoch': report['bestEpoch'], 'epochsRun': report['epochsRun'],
            'baselineMacroNLL': baseline_loss, 'adaptedMacroNLL': adapted_loss, 'differenceVsBaseline': adapted_loss-baseline_loss,
            'selectedCandidate': 'adapted' if adapted_loss < baseline_loss else 'frozen-baseline',
            'interpretation': 'joint continued training; no causal encoder-only attribution'}


def select_candidates(contract, jobs):
    selected = {}
    for encoder, baseline in contract['baselines'].items():
        choices = [{'kind': 'frozen-baseline', 'macroNLL': baseline['evaluation']['macroTargetLogLoss'],
                    'checkpointPath': baseline['warmStart']['path'], 'checkpointSha256': baseline['warmStart']['sha256'],
                    'backboneLR': 0., 'additionalEpochs': 0}]
        for job in jobs:
            if job['arguments']['encoder'] == encoder:
                evidence = job['evidence']
                choices.append({'kind': 'adapted', 'macroNLL': evidence['adaptedMacroNLL'],
                    'checkpointPath': str(Path(job['arguments']['output'])/'best.pt'),
                    'checkpointSha256': evidence['checkpointSha256'], 'backboneLR': job['arguments']['backbone_lr'],
                    'additionalEpochs': evidence['bestEpoch']})
        selected[encoder] = min(choices, key=lambda row: (row['macroNLL'], row['kind'] != 'frozen-baseline', row['backboneLR']))
    return selected


def run(base, ledger_path):
    base, ledger_path = base.resolve(), ledger_path.resolve()
    require(ledger_path.is_relative_to(base) and ledger_path.name not in ('cohort.json', 'splits.json'), 'Use a dedicated warm ledger')
    with shared.exclusive_lock(base/'adaptation-mps.lock'):
        if ledger_path.exists():
            old = read_json(ledger_path)
            live = [record.get('pid') for record in [old, *old.get('jobs', [])]
                    if shared.alive(record.get('pid'))]
            require(not live, 'Warm ledger records a live PID')
            raise ValueError('Existing warm ledger requires explicit recovery; no silent reuse')
        contract = capture_contract(base)
        arguments = job_arguments(contract)
        for argument in arguments:
            output = Path(argument['output'])
            if (output/'status.json').exists():
                require(not shared.alive(read_json(output/'status.json').get('pid')), 'Warm output records a live PID')
            require(not output.exists(), 'Existing/partial warm output requires explicit recovery')
        ledger = {'pid': os.getpid(), 'startedAt': time.time(), 'complete': False, 'contract': contract,
                  'jobs': [{'arguments': argument, 'state': 'pending'} for argument in arguments]}
        def save():
            atomic_json(ledger_path, ledger)
        save()
        try:
            for job in ledger['jobs']:
                guard(contract)
                argument = job['arguments']
                command = [sys.executable, str(HERE/'multiphone_adapt.py')]
                for name, value in argument.items():
                    if value is not None:
                        command.extend(['--'+name.replace('_', '-'), str(value)])
                run_child(command, job, base/(Path(argument['output']).name+'.warm.log'), save)
                guard(contract)
                job['evidence'] = verify_complete(Path(argument['output']), argument, contract)
                ledger['currentSelection'] = select_candidates(contract, [item for item in ledger['jobs'] if 'evidence' in item])
                save()
            ledger.update(complete=True, finishedAt=time.time(), selected=select_candidates(contract, ledger['jobs']))
            save()
            return ledger
        except BaseException as error:
            if 'job' in locals():
                job.update(state='failed', failure=repr(error))
            ledger.update(complete=False, finishedAt=time.time(), failure=repr(error))
            save()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=BASE)
    parser.add_argument('--ledger', type=Path, default=BASE/'warm-adaptation-queue-v1.json')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if args.check_only:
        capture_contract(args.base.resolve())
        print('Warm matrix sources, data, caches and baseline artifacts verified; no fitting performed', flush=True)
    else:
        run(args.base, args.ledger)
