"""Six fixed clean-supervision/noisy-distillation arms; no noisy human labels.

The teacher is the original warm head, never updated. Both student branches
disable dropout while retaining gradients. Epoch selection uses clean human
ratings only; noisy validation is opened after selecting the checkpoint.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time

import numpy as np
import torch

import multiphone_phonetic_head as baseline
import multiphone_consistency_features as noise_source
from multiphone_cache import atomic_json, digest
from multiphone_child_train import is_child, score_predictions
from multiphone_train import save_checkpoint, verify_partitions

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'experiments/multiphone-noise-consistency-v1.json'
COEFFICIENTS = (0., .1, 1.)
REGIMES = ('all-age', 'child-only')
FALSE_FLAGS = ('outerInferencePerformed', 'authorTestInferencePerformed', 'labelsTransferred',
               'noisyAccuracyMeasured', 'encoderUpdated', 'clinicalUseEligible', 'learnerFeedbackEligible')
read_json, require = baseline.read_json, baseline.require


def source_hashes():
    return {name: digest(HERE / name) for name in sorted(set(baseline.SOURCES) |
            {'multiphone_consistency_train.py', 'multiphone_consistency_features.py'})}


def validate_recipe(recipe):
    expected = dict(schemaVersion=1, experiment='multiphone-noise-consistency-v1', fold=0,
        regimes=list(REGIMES), coefficients=list(COEFFICIENTS), seed=7, learningRate=3e-5,
        weightDecay=.01, batchSizeTargetRows=64, maximumEpochs=6, patienceEpochs=2,
        gradientNormLimit=5, dropoutEnabled=False, studentGradientsEnabled=True,
        epochZeroEligible=True, noiseSNRdB=20, noiseConditionCount=1, device='cpu', threads=2)
    require(all(recipe[k] == v for k, v in expected.items())
            and all(recipe[k] is False for k in FALSE_FLAGS), 'Recipe differs from the fixed six-arm design')
    require(digest(Path(recipe['protocolPath'])) == recipe['protocolSha256'], 'Declared protocol changed')


def guard_files(files):
    checked = {}
    for entry in files.values():
        if entry['path'] not in checked:
            checked[entry['path']] = digest(Path(entry['path']))
        require(checked[entry['path']] == entry['sha256'], 'Pinned consistency input changed')


def feature_matrix(features, expected_sha, bound):
    require(digest(features) == expected_sha, 'Caller-pinned noisy features differ')
    report = read_json(features)
    fold = bound['splits']['folds'][0]
    expected = sorted(set(fold['innerFitRows']) | set(fold['innerValidationRows']))
    require(report['complete'] is True and report['authorPartition'] == 'train' and report['fold'] == 0
            and report['partition'] == 'innerFitRows+innerValidationRows' and report['rowIndices'] == expected
            and report['completeCoverage'] is True and report['failedRows'] == report['unmappableRows'] == []
            and report['condition'] == 'noise20db' and report['snrDb'] == 20
            and report['cleanFeatureBindingSha256'] == report['featureSourceBindingSha256']
                == read_json(RECIPE)['cleanFeatureBindingSha256']
            and report['scalarFeatureNames'] == baseline.SCALAR_NAMES
            and all(report[key] is False for key in ('trainingPerformed', 'outerInferencePerformed',
                'authorTestInferencePerformed', 'labelsTransferred', 'learnerFeedbackEligible', 'clinicalUseEligible')),
            'Noisy feature scope, row coverage or scalar order differs')
    files = copy.deepcopy(report['inputFiles'])
    files.update({'derived/' + key: value for key, value in report['derivedFiles'].items()})
    files['noisyReport'] = {'path': str(features.resolve()), 'sha256': expected_sha}
    guard_files(files)
    require(report['inputFiles']['recipe']['path'] == str(noise_source.RECIPE.absolute())
            and report['recipeSha256'] == report['inputFiles']['recipe']['sha256'] == digest(noise_source.RECIPE)
            and report['inputFiles']['cleanFeatureBinding']['sha256'] == report['cleanFeatureBindingSha256']
            and report['inputFiles']['plan'] == {'path': report['planPath'], 'sha256': report['planSha256']},
            'Noisy producer recipe, clean binding or plan lineage differs')
    recipe = read_json(RECIPE)
    require(Path(report['inputFiles']['protocol']['path']).resolve() == Path(recipe['protocolPath']).resolve()
            and report['inputFiles']['protocol']['sha256'] == recipe['protocolSha256'], 'Noisy protocol binding differs')
    # Reconstruct the reviewed producer's scope and source pins, without encoder inference.
    producer_plan = read_json(Path(report['planPath']))
    producer_bound, _, producer_inputs = noise_source.validate_plan(producer_plan, report['inputFiles']['plan'])
    require(producer_inputs == report['inputFiles'] and producer_plan['rowIndices'] == expected
            and producer_bound['bindings'] == bound['bindings'], 'Noisy and clean studies differ')
    for key, filename in (('index', 'index.json'), ('parity', 'parity.json')):
        require(report[key + 'Path'] == filename and report['derivedFiles'][key] ==
                {'path': str((features.parent / filename).absolute()), 'sha256': report[key + 'Sha256']},
                'Noisy completion artifact differs')
    feature_index, parity = read_json(features.parent / 'index.json'), read_json(features.parent / 'parity.json')
    clips = {clip['id']: clip for clip in producer_plan['clips']}
    require(feature_index['complete'] is True and feature_index['planSha256'] == report['planSha256']
            and feature_index['rowIndices'] == expected and set(feature_index['entries']) == set(feature_index['noisyAudio']) == set(clips)
            and feature_index['clipCount'] == report['expectedClips'] == len(clips)
            and report['expectedRows'] == len(expected), 'Noisy index scope or coverage differs')
    require(report['originalParityComplete'] is True and parity['complete'] is True
            and parity['planSha256'] == report['planSha256'] and parity['clips'] == report['originalParity']
            and {entry['clipId'] for entry in parity['clips']} == {entry['clipId'] for entry in producer_plan['parityClips']}
            and parity['tolerances'] == {'ctcLogPosterior': 0., 'scalar': 0., 'phoneticPooled': 2e-6},
            'Original parity proof differs')
    for entry in parity['clips']:
        require(entry['windowsExact'] is True and set(entry['maximumAbsoluteDifferences']) == set(parity['tolerances'])
                and all(np.isfinite(value) and 0 <= value <= parity['tolerances'][key]
                        for key, value in entry['maximumAbsoluteDifferences'].items()), 'Original parity failed')
    arrays = []
    for key, filename, width in (('targetFeatures', 'target.npy', 1024), ('scalarFeatures', 'scalars.npy', 13)):
        item = report[key]
        path = features.parent / filename
        require(item['path'] == filename and item['dtype'] == 'float32' and item['shape'] == [len(expected), width]
                and digest(path) == item['sha256'], 'Noisy feature geometry or digest differs')
        value = np.load(path, allow_pickle=False)
        require(value.dtype == np.float32 and value.shape == (len(expected), width) and np.isfinite(value).all(),
                'Noisy feature values invalid')
        arrays.append(value)
        files['noisy/' + filename] = {'path': str(path.resolve()), 'sha256': item['sha256']}
    require(len(report['rows']) == len(expected), 'Noisy row metadata coverage differs')
    for row_index, metadata in zip(expected, report['rows'], strict=True):
        original = bound['cohort']['rows'][row_index]
        require(metadata['rowIndex'] == row_index and metadata['rowId'] == original['id']
                and all(metadata[key] == original[key] for key in
                    ('clipId', 'targetId', 'targetPhone', 'wordIndex', 'phoneIndex')),
                'Noisy canonical target identity differs')
    # Independently rejoin each pinned producer unit into its final matrix rows.
    positions = {row: i for i, row in enumerate(expected)}
    source_index = read_json(Path(report['derivedFiles']['ctcIndex/noise20db']['path']))
    for clip_id, clip in clips.items():
        target, scalars, metadata = noise_source.checked_unit(
            feature_index['entries'][clip_id], clip, report['planSha256'],
            source_index['entries'][clip_id], feature_index['noisyAudio'][clip_id])
        offsets = [positions[row['rowIndex']] for row in metadata['rows']]
        require(np.array_equal(arrays[0][offsets], target) and np.array_equal(arrays[1][offsets], scalars)
                and [report['rows'][i] for i in offsets] == metadata['rows'], 'Noisy assembled matrix differs from its clip units')
    guard_files(files)
    require(digest(features) == expected_sha, 'Noisy report changed while loading')
    return np.concatenate(arrays, axis=1), {i: position for position, i in enumerate(expected)}, files


def model():
    return baseline.make_model(argparse.Namespace(hidden=128, dropout=.1, device='cpu'), 1037).eval()


def logits(network, values, ids):
    mask = torch.ones((len(ids), 1), dtype=torch.bool)
    return network(values[:, None], mask, ids[:, None], mask)[:, 0]


@torch.no_grad()
def predict(network, values, ids, batch_size=64):
    network.eval()
    result = [logits(network, values[start:start + batch_size], ids[start:start + batch_size]).softmax(-1).numpy()
              for start in range(0, len(ids), batch_size)]
    p = np.concatenate(result).astype(np.float64)
    require(np.isfinite(p).all() and (p >= 0).all() and np.allclose(p.sum(1), 1, rtol=0, atol=1e-6),
            'Invalid consistency prediction')
    return p


def load_data(regime, noisy_path, noisy_sha, recipe):
    require(regime in REGIMES, 'Undeclared fit population')
    warm = recipe['warmHeads'][regime]
    directory = Path(warm['directory'])
    guard_files({name: {'path': str(directory / name), 'sha256': sha} for name, sha in warm['files'].items()})
    config = read_json(directory / 'config.json')
    require(config['family'] == 'target-scalars' and config['regime'] == regime and config['fold'] == 0
            and config['lr'] == .0003 and config['seed'] == 7 and config['phase'] == 'inner'
            and config['bindingSha256'] == recipe['cleanFeatureBindingSha256'], 'Warm head identity differs')
    baseline.source_guard(config)
    args = argparse.Namespace(**config)
    args.binding = Path(args.binding)
    data = baseline.setup(args)
    verify_partitions(data['cohort'], data['splits']['folds'][0])
    require(data['fit'] == config['fitRows'] and data['validation'] == config['validationRows']
            and data['selection'] == config['selectionRows'] and data['bindings'] == config['inputFiles'],
            'Warm fit/validation binding differs')
    saved = torch.load(directory / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == digest(directory / 'config.json') and saved['epoch'] == 5
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']),
            'Warm checkpoint or clean fitting moments differ')
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
    files.update({f'warm/{regime}/{name}': {'path': str((directory / name).resolve()), 'sha256': sha}
                  for name, sha in warm['files'].items()})
    files.update({f'clean/{key}': value for key, value in data['bindings'].items()})
    files['cleanHeadRecipe'] = {'path': str(baseline.RECIPE.absolute()), 'sha256': digest(baseline.RECIPE)}
    files['cleanHeadBinding'] = {'path': str(args.binding.absolute()), 'sha256': config['bindingSha256']}
    return {**data, 'clean': clean_tensor, 'noisy': noisy_tensor, 'ids': ids, 'fitCount': fit_count,
        'teacherFit': teacher_fit, 'warmPredictions': warm_p, 'warmModel': teacher,
        'warmState': copy.deepcopy(saved['model']), 'allBindings': files,
        'labels': torch.tensor([data['cohort']['rows'][i]['raterCounts'] for i in data['fit']], dtype=torch.float32) / 5}


def train_epoch(student, optimizer, clean, noisy, ids, labels, teacher, order, coefficient):
    """Only clean has human labels; a zero coefficient never forwards noisy input."""
    require(coefficient in COEFFICIENTS and len(order) == len(labels), 'Undeclared consistency objective')
    student.eval()  # Deliberately disable dropout, without disabling gradients.
    total_clean, total_kl = 0., 0.
    for start in range(0, len(order), 64):
        selected = order[start:start + 64]
        optimizer.zero_grad(set_to_none=True)
        clean_logits = logits(student, clean[selected], ids[selected])
        nll = -(labels[selected] * clean_logits.log_softmax(-1)).sum(-1)
        kl = torch.zeros_like(nll)
        if coefficient:
            fixed = teacher[selected].detach()
            noisy_logits = logits(student, noisy[selected], ids[selected])
            kl = torch.nn.functional.kl_div(noisy_logits.log_softmax(-1), fixed, reduction='none').sum(-1)
        losses = nll + coefficient * kl
        require(bool(torch.isfinite(losses).all()), 'Nonfinite consistency objective')
        losses.mean().backward()
        torch.nn.utils.clip_grad_norm_(student.parameters(), 5., error_if_nonfinite=True)
        optimizer.step()
        total_clean += float(nll.detach().sum())
        total_kl += float(kl.detach().sum())
    return {'cleanSupervisedNLL': total_clean / len(order), 'fixedTeacherKL': total_kl / len(order)}


def selection_value(p, rows, regime):
    return baseline.selection_loss(score_predictions(p, rows), regime)


def validate_history(history, original_loss):
    require([h['epoch'] for h in history] == list(range(len(history))) and 3 <= len(history) <= 7
            and history[0]['selectionMacroNLL'] == original_loss
            and all(np.isfinite(h['selectionMacroNLL']) for h in history), 'Invalid epoch history')
    best, best_epoch = original_loss, 0
    for entry in history[1:]:
        epoch = entry['epoch']
        require(epoch - 1 - best_epoch < 2, 'History continued after declared patience')
        if entry['selectionMacroNLL'] < best - 1e-7:
            best, best_epoch = entry['selectionMacroNLL'], epoch
    require(len(history) - 1 == 6 or len(history) - 1 - best_epoch == 2,
            'History stopped before the declared limit or patience')
    return best, best_epoch


def movement(reference, changed):
    require(reference.shape == changed.shape and reference.ndim == 2 and reference.shape[1] == 3,
            'Paired probability geometry differs')
    tv = np.abs(changed - reference).sum(1) * .5
    shift = (changed - reference) @ np.array([0., 1., 2.])
    entropy = lambda p: -(p * np.log(p.clip(1e-12, 1))).sum(1)
    return {'targets': len(reference), 'meanTotalVariation': float(tv.mean()), 'maxTotalVariation': float(tv.max()),
        'meanExpectedRatingShift': float(shift.mean()), 'meanAbsoluteExpectedRatingShift': float(np.abs(shift).mean()),
        'meanMaximumProbabilityShift': float((changed.max(1) - reference.max(1)).mean()),
        'meanEntropyShift': float((entropy(changed) - entropy(reference)).mean()),
        'argmaxChanges': int((changed.argmax(1) != reference.argmax(1)).sum())}


def sensitivity(clean, noisy, warm_clean, rows):
    subsets = {'allAges': np.ones(len(rows), dtype=bool),
               'ages6to12': np.array([is_child(row) for row in rows])}
    subsets.update({f'phone/{phone}': np.array([row['targetPhone'] == phone for row in rows])
                    for phone in sorted({row['targetPhone'] for row in rows})})
    subsets.update({f'clip/{clip}': np.array([row['clipId'] == clip for row in rows])
                    for clip in sorted({row['clipId'] for row in rows})})
    return {key: {'cleanToNoisy': movement(clean[mask], noisy[mask]),
                  'warmCleanToStudentClean': movement(warm_clean[mask], clean[mask]),
                  'warmCleanToStudentNoisy': movement(warm_clean[mask], noisy[mask])}
            for key, mask in subsets.items() if mask.any()}


def plan_guard(plan, path, expected_sha):
    require(digest(path) == expected_sha and plan['complete'] is True and plan['sourceSha256'] == source_hashes()
            and plan['recipeSha256'] == digest(RECIPE) and plan['arms'] ==
            [{'regime': r, 'coefficient': c} for r in REGIMES for c in COEFFICIENTS], 'Consistency declaration changed')
    validate_recipe(read_json(RECIPE))
    guard_files(plan['inputFiles'])


def declare(noisy_path, noisy_sha, output):
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Choose a fresh research plan')
    recipe_sha, sources = digest(RECIPE), source_hashes()
    recipe = read_json(RECIPE)
    validate_recipe(recipe)
    torch.set_num_threads(2)
    files = {'declaredProtocol': {'path': recipe['protocolPath'], 'sha256': recipe['protocolSha256']}}
    populations = {}
    for regime in REGIMES:
        data = load_data(regime, noisy_path, noisy_sha, recipe)
        require(all(k not in files or files[k] == v for k, v in data['allBindings'].items()),
                'Shared input bindings disagree across fitting populations')
        files.update(data['allBindings'])
        populations[regime] = {'fitRows': data['fit'], 'validationRows': data['validation'],
            'selectionRows': data['selection'], 'warmCleanSelectionNLL': selection_value(data['warmPredictions'],
                [data['cohort']['rows'][i] for i in data['validation']], regime)}
    require(sources == source_hashes() and recipe_sha == digest(RECIPE), 'Source changed during declaration')
    guard_files(files)
    plan = {'complete': True, 'recipeSha256': recipe_sha, 'sourceSha256': sources,
        'arms': [{'regime': r, 'coefficient': c} for r in REGIMES for c in COEFFICIENTS],
        'noisyFeatures': str(noisy_path.resolve()), 'noisyFeaturesSha256': noisy_sha,
        'inputFiles': files, 'populations': populations, 'researchOnly': True,
        **{key: False for key in FALSE_FLAGS}}
    atomic_json(output, plan)
    return plan


def clean_prediction(student, data):
    count = data['fitCount']
    return predict(student, data['clean'][count:], data['ids'][count:])


def fit(args):
    require(args.regime in REGIMES and args.coefficient in COEFFICIENTS and not args.output.exists()
            and args.output.resolve().is_relative_to(HERE / 'outputs'), 'Choose a declared arm and fresh output')
    plan = read_json(args.plan)
    plan_guard(plan, args.plan, args.plan_sha256)
    torch.set_num_threads(2)
    torch.manual_seed(7)
    data = load_data(args.regime, Path(plan['noisyFeatures']), plan['noisyFeaturesSha256'], read_json(RECIPE))
    population = plan['populations'][args.regime]
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
        'regime': args.regime, 'coefficient': args.coefficient, 'fitRows': data['fit'],
        'validationRows': data['validation'], 'selectionRows': data['selection'],
        'teacherFitSha256': digest(teacher_path), 'studentTrainingMode': 'eval-with-gradients',
        'teacher': 'Fixed original warm head; clean fitting rows only; detached model probabilities',
        'recipeSha256': plan['recipeSha256'], 'sourceSha256': plan['sourceSha256'],
        'inputFiles': data['allBindings'], **{key: False for key in FALSE_FLAGS}}
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
        'bestEpoch': best_epoch, 'epochsRun': len(history) - 1,
        'bestCleanSelectionNLL': best_loss, 'cleanEvaluation': score_predictions(p, rows),
        'warmCleanEvaluation': score_predictions(data['warmPredictions'], rows),
        'sensitivity': sensitivity(p, noisy, data['warmPredictions'], rows),
        'warmSensitivity': sensitivity(data['warmPredictions'], warm_noisy, data['warmPredictions'], rows),
        'elapsedSeconds': time.perf_counter() - started, **{key: False for key in FALSE_FLAGS}}
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
    require(config['regime'] in REGIMES and config['coefficient'] in COEFFICIENTS
            and config['sourceSha256'] == plan['sourceSha256'] and config['recipeSha256'] == plan['recipeSha256'],
            'Replayed arm differs from its declaration')
    torch.set_num_threads(2)
    data = load_data(config['regime'], Path(plan['noisyFeatures']), plan['noisyFeaturesSha256'], read_json(RECIPE))
    require(config['fitRows'] == data['fit'] and config['validationRows'] == data['validation']
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
