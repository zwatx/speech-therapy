"""Fixed remaining-four-fold replication of the recording-consistency pilot.

Only clean inner ratings supervise or select. Shared noisy author-training
features include other folds' outer waveforms; this is not a new outer model
performance evaluation. No noisy ratings or deployment eligibility are created.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time

import numpy as np
import torch

import multiphone_consistency_train as pilot
import multiphone_consistency_extension as producer
import multiphone_phonetic_head as baseline
from multiphone_cache import atomic_json, digest
from multiphone_child_train import score_predictions
from multiphone_train import save_checkpoint, verify_partitions

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'experiments/multiphone-consistency-replication-v1.json'
FOLDS = (1, 2, 3, 4)
REGIMES, COEFFICIENTS = pilot.REGIMES, pilot.COEFFICIENTS
FALSE_FLAGS = ('outerPerformanceEvaluationPerformed', 'authorTestInferencePerformed', 'labelsTransferred',
               'noisyAccuracyMeasured', 'encoderUpdated', 'clinicalUseEligible', 'learnerFeedbackEligible')
PILOT_SHA = '7058da214a4f072eb008be5975c9c50786fff4ee4d5528d48bf0ee71286d116f'
PROTOCOL_SHA = '21fbf98b3d778ae333a87aab9ca17c8ee5a36b1d64a3dc5903c11aec0d15de87'
read_json, require, guard_files = pilot.read_json, pilot.require, pilot.guard_files
model, logits, predict = pilot.model, pilot.logits, pilot.predict
train_epoch, selection_value = pilot.train_epoch, pilot.selection_value
validate_history, sensitivity, clean_prediction = pilot.validate_history, pilot.sensitivity, pilot.clean_prediction


def arms():
    return [dict(fold=f, regime=r, coefficient=c) for f in FOLDS for r in REGIMES for c in COEFFICIENTS]


def population_key(fold, regime):
    return f'fold-{fold}/{regime}'


def source_hashes():
    require(digest(HERE / 'multiphone_consistency_train.py') == PILOT_SHA, 'Frozen pilot trainer changed')
    names = set(pilot.source_hashes()) | set(producer.SOURCES) | {'multiphone_consistency_replication.py'}
    return {name: digest(HERE / name) for name in sorted(names)}


def validate_recipe(recipe):
    expected = dict(schemaVersion=1, experiment='multiphone-consistency-replication-v1', folds=list(FOLDS),
        regimes=list(REGIMES), coefficients=list(COEFFICIENTS), seed=7, learningRate=3e-5,
        weightDecay=.01, batchSizeTargetRows=64, maximumEpochs=6, patienceEpochs=2,
        gradientNormLimit=5, dropoutEnabled=False, studentGradientsEnabled=True,
        epochZeroEligible=True, noiseSNRdB=20, noiseConditionCount=1, device='cpu', threads=2,
        sharedFeaturesIncludeOtherFoldsOuterWaveforms=True, pilotTrainerSha256=PILOT_SHA,
        protocolSha256=PROTOCOL_SHA)
    require(all(recipe[k] == v for k, v in expected.items())
            and all(recipe[k] is False for k in FALSE_FLAGS), 'Recipe differs from the fixed24-arm replication')
    require(digest(Path(recipe['protocolPath'])) == PROTOCOL_SHA, 'Declared replication protocol changed')
    require(set(recipe['warmHeads']) == {population_key(f,r) for f in FOLDS for r in REGIMES},
            'Warm population coverage differs')
    guard_files(recipe['retainedPilot'])


def feature_matrix(features, expected_sha, bound):
    # Producer verification checks both old/new plans, audio/CTC lineage and
    # every clip-unit-to-matrix join. Independently bind that result to this
    # training study, rather than trusting a merely self-consistent producer.
    report, target, scalars, pins = producer.validate_features(features, expected_sha)
    recipe = read_json(RECIPE)
    expected = [i for i, row in enumerate(bound['cohort']['rows']) if row['trainingEligible']]
    require(report['complete'] is True and report['completeCoverage'] is True
            and report['authorPartition'] == 'train' and report['partition'] == 'all-eligible-author-training-rows'
            and report['rowIndices'] == expected and report['expectedRows'] == len(expected)
            and report['expectedClips'] == len({bound['cohort']['rows'][i]['clipId'] for i in expected})
            and report['failedRows'] == report['unmappableRows'] == []
            and report['condition'] == 'noise20db' and report['snrDb'] == 20
            and report['cleanFeatureBindingSha256'] == report['featureSourceBindingSha256']
                == recipe['cleanFeatureBindingSha256']
            and report['scalarFeatureNames'] == baseline.SCALAR_NAMES
            and report['originalParityComplete'] is True and all(report[key] is False for key in producer.FLAGS),
            'Full noisy coverage, condition or study binding differs')
    binding = report['inputFiles']['cleanFeatureBinding']
    require(binding['sha256'] == recipe['cleanFeatureBindingSha256']
            and digest(Path(binding['path'])) == binding['sha256']
            and read_json(Path(binding['path']))['files'] == bound['bindings']
            and Path(report['inputFiles']['protocol']['path']).resolve() == Path(recipe['protocolPath']).resolve()
            and report['inputFiles']['protocol']['sha256'] == PROTOCOL_SHA,
            'Full noisy clean-study or replication protocol identity differs')
    require(len(report['rows']) == len(expected), 'Full noisy target metadata count differs')
    for row_index, metadata in zip(expected, report['rows'], strict=True):
        row = bound['cohort']['rows'][row_index]
        require(metadata['rowIndex'] == row_index and metadata['rowId'] == row['id']
                and 0 <= row['targetId'] < 23 and all(metadata[key] == row[key]
                    for key in ('clipId', 'targetId', 'targetPhone', 'wordIndex', 'phoneIndex')),
                'Full noisy canonical target identity differs')
    for key, name, array, width in (('targetFeatures', 'target', target, 1024),
                                    ('scalarFeatures', 'scalars', scalars, 13)):
        descriptor = report[key]
        path = features.parent / (name + '.npy')
        require(descriptor['path'] == path.name and descriptor['dtype'] == 'float32'
                and descriptor['shape'] == [len(expected), width] and digest(path) == descriptor['sha256']
                and array.dtype == np.float32 and array.shape == (len(expected), width)
                and np.isfinite(array).all() and np.array_equal(np.load(path, allow_pickle=False), array),
                'Full noisy feature matrix geometry or values differ')
        require(pins['matrix/' + name] == {'path': str(path.absolute()), 'sha256': descriptor['sha256']},
                'Full noisy feature matrix authoritative pin differs')
    guard_files(pins)
    require(digest(features) == expected_sha, 'Full noisy report changed while loading')
    return np.concatenate((target, scalars), axis=1), {i: p for p, i in enumerate(expected)}, {
        'noisy/' + name: pin for name, pin in pins.items()}


def load_data(fold, regime, noisy_path, noisy_sha, recipe):
    require(fold in FOLDS and regime in REGIMES, 'Undeclared fit population')
    warm = recipe['warmHeads'][population_key(fold, regime)]
    directory = Path(warm['directory'])
    guard_files({name: {'path': str(directory / name), 'sha256': sha} for name, sha in warm['files'].items()})
    config = read_json(directory / 'config.json')
    require(config['family'] == 'target-scalars' and config['regime'] == regime and config['fold'] == fold
            and config['lr'] == .0003 and config['seed'] == 7 and config['phase'] == 'inner'
            and config['bindingSha256'] == recipe['cleanFeatureBindingSha256'], 'Warm head identity differs')
    baseline.source_guard(config)
    args = argparse.Namespace(**config)
    args.binding = Path(args.binding)
    data = baseline.setup(args)
    verify_partitions(data['cohort'], data['splits']['folds'][fold])
    require(data['fit'] == config['fitRows'] and data['validation'] == config['validationRows']
            and data['selection'] == config['selectionRows'] and data['bindings'] == config['inputFiles'],
            'Warm fit/validation binding differs')
    saved = torch.load(directory / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == digest(directory / 'config.json') and saved['epoch'] == warm['selectedEpoch']
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']),
            'Warm checkpoint or clean fitting moments differ')
    warm_report = read_json(directory / 'report.json')
    warm_replay = read_json(directory / 'replay.json')
    require(warm_report['bestEpoch'] == saved['epoch'] == saved['bestEpoch']
            and warm_report['complete'] is True and warm_report['phase'] == 'inner'
            and warm_report['configSha256'] == digest(directory / 'config.json')
            and warm_report['bestSelectionMacroLogLoss'] == saved['bestLoss']
            and all(warm_report[key + 'Sha256'] == digest(directory / name) for key, name in
                (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'),
                 ('history', 'history.json'), ('prior', 'prior.json')))
            and warm_replay['exact'] is True and warm_replay['rows'] == len(data['validation'])
            and warm_replay['checkpointSha256'] == digest(directory / 'best.pt')
            and config['priorState'] == data['priors'],
            'Warm selected epoch differs from its verified report')
    noisy, noise_positions, files = feature_matrix(noisy_path, noisy_sha, data)
    selected = data['fit'] + data['validation']
    clean_tensor = torch.from_numpy(data['values'][[data['positions'][i] for i in selected]].copy())
    noisy_tensor = torch.from_numpy(noisy[[noise_positions[i] for i in selected]].copy())
    clean_tensor = (clean_tensor - data['mean']) / data['std']
    noisy_tensor = (noisy_tensor - data['mean']) / data['std']
    ids = torch.tensor([data['cohort']['rows'][i]['targetId'] for i in selected], dtype=torch.long)
    fit_count = len(data['fit'])
    teacher = model()
    teacher.load_state_dict(saved['model'], strict=True)
    teacher.requires_grad_(False)
    warm_p = predict(teacher, clean_tensor[fit_count:], ids[fit_count:])
    original_predictions = read_json(directory / 'predictions.json')
    require(original_predictions['rowIndices'] == data['validation']
            and np.array_equal(warm_p, original_predictions['probabilities']), 'Original warm predictions do not replay exactly')
    teacher_fit = predict(teacher, clean_tensor[:fit_count], ids[:fit_count])
    files.update({f'warm/{fold}/{regime}/{name}': {'path': str((directory / name).resolve()), 'sha256': sha}
                  for name, sha in warm['files'].items()})
    files.update({f'clean/{key}': value for key, value in data['bindings'].items()})
    files['cleanHeadRecipe'] = {'path': str(baseline.RECIPE.absolute()), 'sha256': digest(baseline.RECIPE)}
    files['cleanHeadBinding'] = {'path': str(args.binding.absolute()), 'sha256': config['bindingSha256']}
    return {**data, 'clean': clean_tensor, 'noisy': noisy_tensor, 'ids': ids, 'fitCount': fit_count,
        'teacherFit': teacher_fit, 'warmPredictions': warm_p, 'warmModel': teacher,
        'warmState': copy.deepcopy(saved['model']), 'allBindings': files,
        'labels': torch.tensor([data['cohort']['rows'][i]['raterCounts'] for i in data['fit']], dtype=torch.float32) / 5}

def plan_guard(plan, path, expected_sha):
    require(digest(path) == expected_sha and plan['complete'] is True and plan['sourceSha256'] == source_hashes()
            and plan['recipeSha256'] == digest(RECIPE) and plan['arms'] == arms()
            and plan['sharedFeaturesIncludeOtherFoldsOuterWaveforms'] is True
            and all(plan[key] is False for key in FALSE_FLAGS), 'Replication declaration changed')
    validate_recipe(read_json(RECIPE))
    guard_files(plan['inputFiles'])


def declare(noisy_path, noisy_sha, output):
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Choose a fresh research plan')
    recipe_sha, sources = digest(RECIPE), source_hashes()
    recipe = read_json(RECIPE)
    validate_recipe(recipe)
    torch.set_num_threads(2)
    files = {'declaredReplicationProtocol': {'path': recipe['protocolPath'], 'sha256': recipe['protocolSha256']},
             **{'retainedPilot/' + name: pin for name, pin in recipe['retainedPilot'].items()}}
    populations = {}
    for fold in FOLDS:
        for regime in REGIMES:
            data = load_data(fold, regime, noisy_path, noisy_sha, recipe)
            require(all(k not in files or files[k] == v for k, v in data['allBindings'].items()),
                    'Shared input bindings disagree across fitting populations')
            files.update(data['allBindings'])
            populations[population_key(fold, regime)] = {'fold': fold, 'regime': regime,
                'fitRows': data['fit'], 'validationRows': data['validation'], 'selectionRows': data['selection'],
                'warmCleanSelectionNLL': selection_value(data['warmPredictions'],
                    [data['cohort']['rows'][i] for i in data['validation']], regime)}
    require(sources == source_hashes() and recipe_sha == digest(RECIPE), 'Source changed during declaration')
    guard_files(files)
    result = {'complete': True, 'recipeSha256': recipe_sha, 'sourceSha256': sources, 'arms': arms(),
        'noisyFeatures': str(noisy_path.resolve()), 'noisyFeaturesSha256': noisy_sha,
        'inputFiles': files, 'populations': populations, 'researchOnly': True,
        'sharedFeaturesIncludeOtherFoldsOuterWaveforms': True, **{key: False for key in FALSE_FLAGS}}
    atomic_json(output, result)
    return result


def fit(args):
    require(args.fold in FOLDS and args.regime in REGIMES and args.coefficient in COEFFICIENTS and not args.output.exists()
            and args.output.resolve().is_relative_to(HERE / 'outputs'), 'Choose a declared arm and fresh output')
    plan = read_json(args.plan)
    plan_guard(plan, args.plan, args.plan_sha256)
    torch.set_num_threads(2)
    torch.manual_seed(7)
    data = load_data(args.fold, args.regime, Path(plan['noisyFeatures']), plan['noisyFeaturesSha256'], read_json(RECIPE))
    population = plan['populations'][population_key(args.fold, args.regime)]
    require(all(data[k] == population[k + 'Rows'] for k in ('fit', 'validation', 'selection')),
            'Declared fit or validation membership changed')
    student = model()
    student.load_state_dict(data['warmState'], strict=True)
    optimizer = torch.optim.AdamW(student.parameters(), lr=3e-5, weight_decay=.01)
    generator = np.random.default_rng(7)
    rows = [data['cohort']['rows'][i] for i in data['validation']]
    args.output.mkdir(parents=True, mode=0o700)
    teacher_path = args.output / 'teacher-fit.npy'
    np.save(teacher_path, data['teacherFit'], allow_pickle=False)
    config = {'planPath': str(args.plan.resolve()), 'planSha256': args.plan_sha256,
        'fold': args.fold, 'regime': args.regime, 'coefficient': args.coefficient, 'fitRows': data['fit'],
        'validationRows': data['validation'], 'selectionRows': data['selection'],
        'teacherFitSha256': digest(teacher_path), 'studentTrainingMode': 'eval-with-gradients',
        'teacher': 'Fixed original warm head; clean fitting rows only; detached model probabilities',
        'recipeSha256': plan['recipeSha256'], 'sourceSha256': plan['sourceSha256'],
        'inputFiles': data['allBindings'], 'sharedFeaturesIncludeOtherFoldsOuterWaveforms': True, **{key: False for key in FALSE_FLAGS}}
    atomic_json(args.output / 'config.json', config)
    config_sha = digest(args.output / 'config.json')
    owned_files = {'config.json': config_sha, 'teacher-fit.npy': config['teacherFitSha256']}

    def pin_written(*names):
        for name in names:
            owned_files[name] = digest(args.output / name)

    def output_guard():
        require(all(digest(args.output / name) == sha for name, sha in owned_files.items()),
                'Owned training artifact changed after publication')

    best_loss, best_epoch = selection_value(data['warmPredictions'], rows, args.regime), 0
    history = [{'epoch': 0, 'selectionMacroNLL': best_loss}]
    started = time.perf_counter()

    def checkpoint(epoch):
        return {'model': student.state_dict(), 'optimizer': optimizer.state_dict(), 'epoch': epoch,
                'bestEpoch': best_epoch, 'bestLoss': best_loss, 'mean': data['mean'], 'std': data['std'],
                'configSha256': config_sha}

    save_checkpoint(args.output / 'best.pt', checkpoint(0))
    pin_written('best.pt')
    teacher = torch.from_numpy(data['teacherFit'].astype(np.float32))
    for epoch in range(1, 7):
        objective = train_epoch(student, optimizer, data['clean'][:data['fitCount']],
            data['noisy'][:data['fitCount']], data['ids'][:data['fitCount']], data['labels'], teacher,
            generator.permutation(data['fitCount']), args.coefficient)
        p = clean_prediction(student, data)
        loss = selection_value(p, rows, args.regime)
        require(np.isfinite(loss), 'Nonfinite clean selection loss')
        improved = loss < best_loss - 1e-7
        if improved:
            best_epoch, best_loss = epoch, loss
        history.append({'epoch': epoch, 'selectionMacroNLL': loss, **objective})
        save_checkpoint(args.output / 'last.pt', checkpoint(epoch))
        pin_written('last.pt')
        if improved:
            save_checkpoint(args.output / 'best.pt', checkpoint(epoch))
            pin_written('best.pt')
        require(config_sha == digest(args.output / 'config.json') and source_hashes() == plan['sourceSha256'],
                'Training configuration or source changed')
        atomic_json(args.output / 'history.json', history)
        pin_written('history.json')
        atomic_json(args.output / 'status.json', {'complete': False, 'epoch': epoch, 'bestEpoch': best_epoch})
        print(json.dumps({'epoch': epoch, 'cleanSelectionNLL': loss, 'bestEpoch': best_epoch}), flush=True)
        if epoch - best_epoch >= 2:
            break
    output_guard()
    saved = torch.load(args.output / 'best.pt', map_location='cpu', weights_only=True)
    student.load_state_dict(saved['model'], strict=True)
    p = clean_prediction(student, data)
    require(selection_value(p, rows, args.regime) == best_loss, 'Selected clean checkpoint does not replay')
    # Transformed validation is used only here, after clean-only selection.
    count = data['fitCount']
    noisy = predict(student, data['noisy'][count:], data['ids'][count:])
    warm_noisy = predict(data['warmModel'], data['noisy'][count:], data['ids'][count:])
    predictions = {'rowIndices': data['validation'], 'cleanProbabilities': p.tolist(),
        'noisyProbabilities': noisy.tolist(), 'warmCleanProbabilities': data['warmPredictions'].tolist(),
        'warmNoisyProbabilities': warm_noisy.tolist(), 'noisyHumanLabelsAvailable': False}
    atomic_json(args.output / 'predictions.json', predictions)
    pin_written('predictions.json')
    report = {'complete': False, 'fitComplete': True, 'state': 'fitted-awaiting-independent-replay',
        'fold': args.fold, 'regime': args.regime, 'coefficient': args.coefficient,
        'bestEpoch': best_epoch, 'epochsRun': len(history) - 1,
        'bestCleanSelectionNLL': best_loss, 'cleanEvaluation': score_predictions(p, rows),
        'warmCleanEvaluation': score_predictions(data['warmPredictions'], rows),
        'sensitivity': sensitivity(p, noisy, data['warmPredictions'], rows),
        'warmSensitivity': sensitivity(data['warmPredictions'], warm_noisy, data['warmPredictions'], rows),
        'elapsedSeconds': time.perf_counter() - started, 'sharedFeaturesIncludeOtherFoldsOuterWaveforms': True, **{key: False for key in FALSE_FLAGS}}
    plan_guard(plan, args.plan, args.plan_sha256)
    guard_files(data['allBindings'])
    output_guard()
    atomic_json(args.output / 'status.json', {'complete': False, 'fitComplete': True,
        'state': 'fitted-awaiting-independent-replay', 'bestEpoch': best_epoch, 'epochsRun': len(history) - 1})
    pin_written('status.json')
    output_guard()
    report['filesSha256'] = owned_files.copy()
    atomic_json(args.output / 'report.json', report)
    return report

def replay(output):
    original_report_sha = digest(output / 'report.json')
    config, report = read_json(output / 'config.json'), read_json(output / 'report.json')
    require(report['complete'] is False and report['fitComplete'] is True
            and report['state'] == 'fitted-awaiting-independent-replay'
            and all(report[key] is False and config[key] is False for key in FALSE_FLAGS)
            and all(digest(output / name) == sha for name, sha in report['filesSha256'].items()),
            'Completed consistency artifacts differ')
    plan_path = Path(config['planPath'])
    plan = read_json(plan_path)
    plan_guard(plan, plan_path, config['planSha256'])
    require(config['fold'] in FOLDS and config['regime'] in REGIMES and config['coefficient'] in COEFFICIENTS
            and config['sourceSha256'] == plan['sourceSha256'] and config['recipeSha256'] == plan['recipeSha256'],
            'Replayed arm differs from its declaration')
    torch.set_num_threads(2)
    data = load_data(config['fold'], config['regime'], Path(plan['noisyFeatures']), plan['noisyFeaturesSha256'], read_json(RECIPE))
    population = plan['populations'][population_key(config['fold'], config['regime'])]
    require(all(config[k] == population[k] for k in ('fitRows', 'validationRows', 'selectionRows'))
            and all(report[k] == config[k] for k in ('fold', 'regime', 'coefficient'))
            and config['sharedFeaturesIncludeOtherFoldsOuterWaveforms'] is report['sharedFeaturesIncludeOtherFoldsOuterWaveforms'] is True
            and config['fitRows'] == data['fit'] and config['validationRows'] == data['validation']
            and config['selectionRows'] == data['selection'] and config['inputFiles'] == data['allBindings']
            and digest(output / 'teacher-fit.npy') == config['teacherFitSha256']
            and np.array_equal(np.load(output / 'teacher-fit.npy', allow_pickle=False), data['teacherFit']),
            'Replay teacher or fitting membership differs')
    saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == digest(output / 'config.json') and saved['epoch'] == saved['bestEpoch']
            == report['bestEpoch'] and saved['bestLoss'] == report['bestCleanSelectionNLL']
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']),
            'Selected consistency checkpoint differs')
    student = model()
    student.load_state_dict(saved['model'], strict=True)
    count = data['fitCount']
    p = clean_prediction(student, data)
    noisy = predict(student, data['noisy'][count:], data['ids'][count:])
    warm_noisy = predict(data['warmModel'], data['noisy'][count:], data['ids'][count:])
    predictions = read_json(output / 'predictions.json')
    for key, value in (('cleanProbabilities', p), ('noisyProbabilities', noisy),
                       ('warmCleanProbabilities', data['warmPredictions']), ('warmNoisyProbabilities', warm_noisy)):
        require(np.array_equal(predictions[key], value), 'Saved consistency probabilities do not replay exactly')
    rows = [data['cohort']['rows'][i] for i in data['validation']]
    require(predictions['rowIndices'] == data['validation'] and predictions['noisyHumanLabelsAvailable'] is False
            and report['cleanEvaluation'] == score_predictions(p, rows)
            and report['warmCleanEvaluation'] == score_predictions(data['warmPredictions'], rows)
            and report['sensitivity'] == sensitivity(p, noisy, data['warmPredictions'], rows)
            and report['warmSensitivity'] == sensitivity(data['warmPredictions'], warm_noisy, data['warmPredictions'], rows),
            'Consistency metrics or paired changes differ')
    history = read_json(output / 'history.json')
    best, epoch = validate_history(history, selection_value(data['warmPredictions'], rows, config['regime']))
    require(best == saved['bestLoss'] and epoch == saved['epoch'] and len(history) - 1 == report['epochsRun'],
            'Selected checkpoint violates the clean-only history rule')
    require(read_json(output / 'status.json') == dict(complete=False, fitComplete=True,
            state='fitted-awaiting-independent-replay', bestEpoch=epoch, epochsRun=len(history) - 1),
            'Completion status differs from the selected checkpoint')
    plan_guard(plan, plan_path, config['planSha256'])
    guard_files(data['allBindings'])
    require(digest(output / 'report.json') == original_report_sha
            and all(digest(output / name) == sha for name, sha in report['filesSha256'].items()), 'Output changed during replay')
    result = {'complete': True, 'exact': True, 'state': 'verified', 'rows': len(p),
              'fold': config['fold'], 'regime': config['regime'], 'coefficient': config['coefficient'],
              'checkpointSha256': digest(output / 'best.pt'),
              'reportSha256': digest(output / 'report.json'), 'noisyAccuracyMeasured': False}
    atomic_json(output / 'replay.json', result)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    declaration = commands.add_parser('declare')
    declaration.add_argument('--noisy-features', type=Path, required=True)
    declaration.add_argument('--noisy-sha256', required=True)
    declaration.add_argument('--output', type=Path, required=True)
    train = commands.add_parser('fit')
    train.add_argument('--plan', type=Path, required=True)
    train.add_argument('--plan-sha256', required=True)
    train.add_argument('--fold', type=int, choices=FOLDS, required=True)
    train.add_argument('--regime', choices=REGIMES, required=True)
    train.add_argument('--coefficient', type=float, choices=COEFFICIENTS, required=True)
    train.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('replay')
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = declare(args.noisy_features, args.noisy_sha256, args.output) if args.command == 'declare' else (
        fit(args) if args.command == 'fit' else replay(args.output))
    print(json.dumps({'fitComplete': True, 'replayRequired': True} if args.command == 'fit'
                     else {'complete': result.get('complete', result.get('exact'))}), flush=True)
