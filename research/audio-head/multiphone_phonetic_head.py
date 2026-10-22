"""Inner-only phone-conditioned heads on verified frozen phonetic embeddings.

Feature binding is a separate explicit step after extraction completes. No
encoder inference, outer evaluation, or modification of shared trainers occurs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

import multiphone_phonetic_features as extraction
from multiphone_cache import atomic_json, digest
from multiphone_child_train import fit_priors
from multiphone_local_head import batch, evaluate, make_model, select_rows, selection_loss
from multiphone_local_train import SCALAR_NAMES, load_inputs as original_inputs
from multiphone_train import save_checkpoint

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
RECIPE = HERE / 'experiments/multiphone-phonetic-heads-v1.json'
EXTRACTION_RECIPE = extraction.RECIPE
FAMILIES = ('target', 'target-scalars', 'global', 'global-scalars')
SOURCES = ('multiphone_phonetic_head.py', 'multiphone_phonetic_features.py', 'multiphone_local_head.py',
           'multiphone_local_train.py', 'multiphone_child_train.py', 'multiphone_controls.py',
           'multiphone_train.py', 'multiphone_models.py', 'multiphone_cache.py', 'multiphone_verify.py',
           'multiphone_data.py', 'encoders.py', 'speechocean_r_rater_cv.py')
read_json, require = extraction.read_json, extraction.require


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCES}


def validate_bundle(cohort_path, splits_path, original_path, feature_path, recipe):
    require(digest(cohort_path) == recipe['cohortSha256'] and digest(splits_path) == recipe['splitsSha256']
            and digest(original_path) == recipe['originalFeaturesSha256'], 'Original study differs from the declared head recipe')
    cohort, splits, scalars, positions, original_binding = original_inputs(cohort_path, splits_path, original_path)
    original = read_json(original_path)
    report = read_json(feature_path)
    directory = feature_path.parent.resolve()
    config_path, index_path = directory / 'config.json', directory / 'index.json'
    config, index = read_json(config_path), read_json(index_path)
    phonetic_recipe = read_json(EXTRACTION_RECIPE)
    expected_identity = {key: phonetic_recipe[key] for key in ('modelId', 'revision', 'artifactSha256', 'hiddenWidth')}
    require(report['complete'] is True and report['fullCohortCoverage'] is True
            and report['failedRows'] == report['unmappableRows'] == []
            and report['eligibleCohortRows'] == phonetic_recipe['expectedEligibleRows'] == len(positions)
            and report['rowIndices'] == original['rowIndices'] and report['originalWindowsUnchanged'] is True
            and report['globalVectorsRepeatedPerTarget'] is True
            and report['encoderIdentity'] == expected_identity and expected_identity['hiddenWidth'] == 1024
            and all(report.get(key) is False for key in extraction.FALSE_FLAGS), 'Incomplete or different phonetic feature scope')
    require(Path(report['configPath']).resolve() == config_path and report['configSha256'] == digest(config_path)
            and config['recipe'] == phonetic_recipe and report['bindings'] == config['bindings']
            and report['indexSha256'] == digest(index_path) and index['complete'] is True
            and index['configSha256'] == report['configSha256'], 'Phonetic config/index binding differs')
    bindings = config['bindings'].copy()
    require(bindings['recipe'] == extraction.file_binding(EXTRACTION_RECIPE), 'Extraction recipe pin differs')
    for name, path in (('cohort', cohort_path), ('splits', splits_path), ('features', original_path)):
        require(bindings[name] == extraction.file_binding(path), 'Phonetic and original study identities differ')
    for name in extraction.SOURCES:
        require(bindings['source/' + name] == extraction.file_binding(extraction.HERE / name), 'Extraction source pin differs')
    for name, sha in phonetic_recipe['artifactSha256'].items():
        require(bindings['checkpoint/' + name]['sha256'] == sha, 'Official phonetic checkpoint pin differs')
    require(bindings['checkpoint/downloadRecord']['sha256'] == phonetic_recipe['downloadRecordSha256'],
            'Checkpoint download provenance differs')
    extraction.guard(bindings)
    rows = [{**{key: row[key] for key in extraction.ROW_FIELDS}, 'outputIndex': position}
            for position, row in enumerate(original['rows'])]
    require(report['rows'] == rows, 'Phonetic row identity/order or estimated windows differ')
    arrays = {}
    for name in ('target', 'global'):
        descriptor = report[name + 'Features']
        path = directory / descriptor['path']
        require(descriptor['path'] == name + '.npy' and descriptor['dtype'] == 'float32'
                and descriptor['shape'] == [len(rows), 1024] and digest(path) == descriptor['sha256'],
                'Phonetic matrix descriptor/digest differs')
        values = np.load(path, mmap_mode='r', allow_pickle=False)
        require(values.dtype == np.float32 and list(values.shape) == descriptor['shape'] and np.isfinite(values).all(),
                'Invalid phonetic matrix shape/dtype/values')
        arrays[name] = values
        bindings['headInput/' + name] = extraction.file_binding(path)
    by_clip = {}
    for row in rows:
        by_clip.setdefault(row['clipId'], []).append(row)
    require(index['clipCount'] == report['clipCount'] == phonetic_recipe['expectedClips'] == len(by_clip)
            and set(index['entries']) == set(by_clip), 'Phonetic clip coverage differs')
    source_clips = {clip['id']: clip for clip in cohort['clips']}
    for clip_id, selected in by_clip.items():
        clip = source_clips[clip_id]
        entry = index['entries'][clip_id]
        frames = extraction.convolution_frames(clip['sampleCount'], phonetic_recipe)
        require(entry['path'] == f'clips/{clip_id}/vectors.npz' and entry['frames'] == frames
                and entry['targets'] == len(selected) and entry['audioSha256'] == clip['audioSha256'],
                'Phonetic clip/window binding differs')
        expected = extraction.expected_entry(clip, selected, report['configSha256'], frames)
        target, global_vector = extraction.checked_unit((directory / entry['path']).parent, expected, 1024, entry)
        output_indices = [row['outputIndex'] for row in selected]
        require(np.array_equal(arrays['target'][output_indices], target)
                and np.array_equal(arrays['global'][output_indices], np.broadcast_to(global_vector, target.shape)),
                'Phonetic assembled vectors or repeated global vector differ from per-clip units')
    for name, path in (('report', feature_path), ('config', config_path), ('index', index_path),
                       ('scalars', Path(original_binding['scalarPath']))):
        bindings['headInput/' + name] = extraction.file_binding(path)
    extraction.guard(bindings)
    return {'cohort': cohort, 'splits': splits, 'scalars': scalars, 'arrays': arrays,
            'positions': positions, 'bindings': bindings, 'rowIndices': report['rowIndices']}


def bind_features(args):
    require(not args.output.exists() and args.output.resolve().is_relative_to((HERE / 'outputs').resolve()),
            'Choose a new binding artifact in ignored research outputs')
    recipe = read_json(RECIPE)
    sources = source_hashes()
    bundle = validate_bundle(args.cohort, args.splits, args.original_features, args.phonetic_features, recipe)
    result = {'schemaVersion': 1, 'complete': True, 'role': 'Immutable phonetic inner-study feature binding',
              'recipeSha256': digest(RECIPE), 'sourceSha256': sources, 'files': bundle['bindings'],
              'cohortPath': str(args.cohort.resolve()), 'splitsPath': str(args.splits.resolve()),
              'originalFeaturesPath': str(args.original_features.resolve()), 'phoneticFeaturesPath': str(args.phonetic_features.resolve()),
              'rowIndices': bundle['rowIndices'], 'allPerClipUnitsAndGlobalRepetitionVerified': True,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False, 'outerOutcomesUsed': False}
    require(source_hashes() == sources, 'Head source changed during binding')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        args.output.chmod(0o600)
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return result


def load_bound(path: Path, recipe):
    evidence = read_json(path)
    require(evidence['complete'] is True and evidence['allPerClipUnitsAndGlobalRepetitionVerified'] is True
            and evidence['recipeSha256'] == digest(RECIPE) and evidence['sourceSha256'] == source_hashes()
            and evidence['outerOutcomesUsed'] is False, 'Feature binding recipe/source/scope differs')
    bundle = validate_bundle(Path(evidence['cohortPath']), Path(evidence['splitsPath']),
                             Path(evidence['originalFeaturesPath']), Path(evidence['phoneticFeaturesPath']), recipe)
    require(bundle['bindings'] == evidence['files'] and bundle['rowIndices'] == evidence['rowIndices'],
            'Feature binding changed since declaration')
    return bundle


def setup(args):
    recipe = read_json(RECIPE)
    exact = {'hidden': 'hiddenWidth', 'dropout': 'dropout', 'weight_decay': 'weightDecay',
             'batch_size': 'batchSizeTargetRows', 'epochs': 'maximumEpochs', 'patience': 'patienceEpochs',
             'threads': 'threads', 'device': 'device'}
    require(args.family in recipe['families'] and args.regime in recipe['regimes'] and args.fold in recipe['folds']
            and args.seed in recipe['initializationSeeds'] and args.lr in recipe['learningRates']
            and all(getattr(args, key) == recipe[value] for key, value in exact.items()), 'Arguments differ from the declared80-trial study')
    data = load_bound(args.binding, recipe)
    fit, validation, selection = select_rows(data['cohort'], data['splits'], args.fold, args.regime)
    acoustic = data['arrays'][args.family.split('-')[0]]
    values = np.concatenate((acoustic, data['scalars']), axis=1) if args.family.endswith('-scalars') else acoustic
    fit_values = np.asarray(values[[data['positions'][index] for index in fit]], dtype=np.float64)
    mean, std = fit_values.mean(0), fit_values.std(0)
    std = np.where(std < 1e-6, 1., std)
    require(np.isfinite(mean).all() and np.isfinite(std).all(), 'Invalid fit-only feature moments')
    return {**data, 'values': values, 'fit': fit, 'validation': validation, 'selection': selection,
            'mean': torch.tensor(mean, dtype=torch.float32), 'std': torch.tensor(std, dtype=torch.float32),
            'priors': fit_priors([data['cohort']['rows'][index] for index in fit])}


def source_guard(config):
    require(digest(RECIPE) == config['recipeSha256'] and config['sourceSha256'] == source_hashes()
            and digest(Path(config['binding'])) == config['bindingSha256'], 'Declared head source/recipe/binding changed')


def train(args):
    require(not args.output.exists() and args.output.resolve().is_relative_to((HERE / 'outputs').resolve()),
            'Choose a new phonetic-head run directory')
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    started = time.perf_counter()
    data = setup(args)
    model = make_model(args, data['values'].shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    config = {name: str(value.resolve()) if isinstance(value, Path) else value
              for name, value in vars(args).items() if name not in ('command', 'replay')}
    config.update(recipeSha256=digest(RECIPE), sourceSha256=source_hashes(), bindingSha256=digest(args.binding),
                  inputFiles=data['bindings'], fitRows=data['fit'], validationRows=data['validation'], selectionRows=data['selection'],
                  priorState=data['priors'], featureWidth=data['values'].shape[1],
                  featureColumns=[f'{args.family.split("-")[0]}Phonetic:{i}' for i in range(1024)] +
                                 (SCALAR_NAMES if args.family.endswith('-scalars') else []),
                  fitSpeakers=len({data['cohort']['rows'][i]['speakerId'] for i in data['fit']}),
                  validationTargetsWithoutFitRows=sorted({data['cohort']['rows'][i]['targetPhone'] for i in data['validation']} -
                                                        {data['cohort']['rows'][i]['targetPhone'] for i in data['fit']}),
                  selection='ages6to12 macro-phone NLL' if args.regime == 'child-only' else 'all-age macro-phone NLL',
                  phase='inner', authorPartition='train', classWeighting=False, encoderUpdated=False,
                  outerOutcomesUsed=False, authorTestInferencePerformed=False, frameTimesValidated=False,
                  clinicalUseEligible=False, learnerFeedbackEligible=False,
                  torch=str(torch.__version__), numpy=np.__version__)
    source_guard(config)
    args.output.mkdir(parents=True, mode=0o700)
    atomic_json(args.output / 'config.json', config)
    rows = [data['cohort']['rows'][i] for i in data['validation']]
    prior = np.asarray([data['priors'][row['targetPhone']]['probabilities'] for row in rows])
    from multiphone_child_train import score_predictions
    prior_metrics = score_predictions(prior, rows)
    atomic_json(args.output / 'prior.json', {'state': data['priors'], 'evaluation': prior_metrics,
                                           'rowIndices': data['validation'], 'probabilities': prior.tolist()})
    best_loss, best_epoch, history = float('inf'), 0, []
    for epoch in range(1, args.epochs + 1):
        model.train()
        order, loss_sum = generator.permutation(data['fit']).tolist(), 0.
        for offset in range(0, len(order), args.batch_size):
            values, phones, mask, targets = batch(data, order[offset:offset + args.batch_size], 'cpu')
            optimizer.zero_grad(set_to_none=True)
            logits = model(values, mask, phones, mask)[:, 0]
            losses = -(targets * logits.log_softmax(-1)).sum(-1)
            require(bool(torch.isfinite(losses).all()), 'Nonfinite phonetic-head loss')
            losses.mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(losses.detach().sum())
        metrics, _ = evaluate(model, data, data['validation'], 'cpu', args.batch_size)
        value = selection_loss(metrics, args.regime)
        require(np.isfinite(value), 'Nonfinite declared selection loss')
        history.append({'epoch': epoch, 'trainPerRaterLogLoss': loss_sum / len(order),
                        'selectionMacroTargetLogLoss': value, 'evaluation': metrics})
        improved = value < best_loss - 1e-7
        if improved:
            best_loss, best_epoch = value, epoch
        checkpoint = {'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                      'mean': data['mean'], 'std': data['std'], 'epoch': epoch, 'bestEpoch': best_epoch,
                      'bestLoss': best_loss, 'configSha256': digest(args.output / 'config.json')}
        source_guard(config)
        save_checkpoint(args.output / 'last.pt', checkpoint)
        if improved:
            save_checkpoint(args.output / 'best.pt', checkpoint)
        atomic_json(args.output / 'history.json', history)
        atomic_json(args.output / 'status.json', {'complete': False, 'epoch': epoch, 'bestEpoch': best_epoch,
                                                'selectionMacroTargetLogLoss': best_loss})
        print(json.dumps({'epoch': epoch, 'selectionMacroTargetLogLoss': value, 'bestEpoch': best_epoch}), flush=True)
        if epoch - best_epoch >= args.patience:
            break
    saved = torch.load(args.output / 'best.pt', map_location='cpu', weights_only=True)
    model.load_state_dict(saved['model'], strict=True)
    metrics, predictions = evaluate(model, data, data['validation'], 'cpu', args.batch_size)
    require(selection_loss(metrics, args.regime) == best_loss, 'Restored checkpoint selection score differs')
    source_guard(config)
    extraction.guard(data['bindings'])
    atomic_json(args.output / 'predictions.json', predictions)
    report = {'complete': True, 'phase': 'inner', 'configSha256': digest(args.output / 'config.json'),
              **{name + 'Sha256': digest(args.output / filename) for name, filename in
                 (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json'))},
              'bestEpoch': best_epoch, 'epochsRun': len(history), 'bestSelectionMacroLogLoss': best_loss,
              'evaluation': metrics, 'sameFitPriorEvaluation': prior_metrics,
              'selectionMacroLogLossMinusPrior': best_loss - selection_loss(prior_metrics, args.regime),
              'evaluationRole': config['selection'] + ' inner-speaker selection',
              'elapsedSeconds': time.perf_counter() - started, 'outerOutcomesUsed': False,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    atomic_json(args.output / 'report.json', report)
    atomic_json(args.output / 'status.json', {'complete': True, 'bestEpoch': best_epoch, 'epochsRun': len(history)})
    return report


def replay(output: Path):
    config = read_json(output / 'config.json')
    source_guard(config)
    args = argparse.Namespace(**config)
    args.binding, args.output = Path(args.binding), Path(args.output)
    torch.set_num_threads(args.threads)
    data = setup(args)
    require(data['bindings'] == config['inputFiles'] and data['fit'] == config['fitRows']
            and data['validation'] == config['validationRows'] and data['selection'] == config['selectionRows']
            and data['priors'] == config['priorState'], 'Replay fitting/input/selection identity differs')
    report = read_json(output / 'report.json')
    require(report['complete'] is True and report['phase'] == 'inner' and report['configSha256'] == digest(output / 'config.json')
            and all(report[key + 'Sha256'] == digest(output / name) for key, name in
                    (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json'))),
            'Replay artifacts differ from completed report')
    saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == digest(output / 'config.json') and saved['epoch'] == saved['bestEpoch'] == report['bestEpoch']
            and saved['bestLoss'] == report['bestSelectionMacroLogLoss']
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']), 'Checkpoint normalization/selection differs')
    model = make_model(args, data['values'].shape[1])
    model.load_state_dict(saved['model'], strict=True)
    metrics, predictions = evaluate(model, data, data['validation'], 'cpu', args.batch_size)
    require(predictions == read_json(output / 'predictions.json') and metrics == report['evaluation'], 'CPU checkpoint replay differs')
    source_guard(config)
    extraction.guard(data['bindings'])
    result = {'exact': True, 'rows': len(data['validation']), 'checkpointSha256': digest(output / 'best.pt'),
              'evaluation': metrics, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    atomic_json(output / 'replay.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    bind = commands.add_parser('bind')
    bind.add_argument('--cohort', type=Path, default=BASE / 'cohort.json')
    bind.add_argument('--splits', type=Path, default=BASE / 'splits.json')
    bind.add_argument('--original-features', type=Path, default=BASE / 'ctc-local-full/features/features.json')
    bind.add_argument('--phonetic-features', type=Path, required=True)
    bind.add_argument('--output', type=Path, required=True)
    fit = commands.add_parser('train')
    fit.add_argument('--binding', type=Path, required=True)
    fit.add_argument('--output', type=Path, required=True)
    fit.add_argument('--family', choices=FAMILIES, required=True)
    fit.add_argument('--regime', choices=['all-age', 'child-only'], required=True)
    fit.add_argument('--fold', type=int, choices=range(5), required=True)
    fit.add_argument('--lr', type=float, choices=[.001, .0003], required=True)
    fit.set_defaults(seed=7, hidden=128, dropout=.1, weight_decay=.01, batch_size=64, epochs=100, patience=15, threads=2, device='cpu')
    check = commands.add_parser('replay')
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = bind_features(args) if args.command == 'bind' else replay(args.output) if args.command == 'replay' else train(args)
    print(json.dumps({'complete': result.get('complete', result.get('exact'))}, allow_nan=False), flush=True)
