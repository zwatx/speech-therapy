"""Full author-train research exports selected from complete inner matrices only.

No outer evaluation or author-test path is accepted. In-sample probabilities
verify saved artifacts, not generalization, calibration or pronunciation skill.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

import multiphone_phonetic_head as head
import multiphone_phonetic_head_queue as ordinary_queue
import multiphone_phonetic_balanced as balanced
import multiphone_phonetic_balanced_queue as balanced_queue
from multiphone_cache import atomic_json, digest
from multiphone_child_train import corrected_probabilities, fit_class_weights, fit_priors, is_child, weighted_loss
from multiphone_data import TARGETS
from multiphone_train import save_checkpoint, valid_counts

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'experiments/multiphone-phonetic-final-v1.json'
VARIANTS = ('unweighted-all-age', 'unweighted-child-only', 'weighted-all-age', 'weighted-child-only')
ARTIFACTS = ('config.json', 'report.json', 'best.pt', 'predictions.json', 'history.json', 'prior.json', 'replay.json')
FLAGS = {name: False for name in ('outerOutcomesUsed', 'authorTestInferencePerformed', 'encoderUpdated',
    'clinicalUseEligible', 'learnerFeedbackEligible', 'empiricalCalibrationEstablished', 'frameTimesValidated',
    'producedPhoneLabelsAvailable', 'generalizationMeasured')}
read_json, require = head.read_json, head.require


def source_hashes():
    names = set(head.SOURCES) | {'multiphone_phonetic_final.py', 'multiphone_phonetic_head_queue.py',
        'multiphone_phonetic_balanced.py', 'multiphone_phonetic_balanced_queue.py', 'multiphone_local_head_queue.py'}
    return {name: digest(HERE / name) for name in sorted(names)}


def selection(trials):
    """One common LR per objective/population, then median epoch of its five folds."""
    chosen = {}
    require(len(trials) == 40, 'Exactly forty target-scalars inner trials are required')
    for variant in VARIANTS:
        candidates = [trial for trial in trials if trial['variant'] == variant]
        require(len(candidates) == 10 and {(x['fold'], x['lr']) for x in candidates} ==
                {(fold, rate) for fold in range(5) for rate in (.001, .0003)}, 'Missing or duplicate fold/rate candidate')
        summaries = []
        for rate in (.001, .0003):
            selected = sorted((x for x in candidates if x['lr'] == rate), key=lambda x: x['fold'])
            require(all(np.isfinite(x['loss']) and x['loss'] >= 0 and type(x['bestEpoch']) is int
                        and 1 <= x['bestEpoch'] <= 100 for x in selected), 'Invalid inner score or epoch')
            summaries.append({'lr': rate, 'meanInnerMacroNLL': float(np.mean([x['loss'] for x in selected])),
                              'foldLosses': [x['loss'] for x in selected], 'foldBestEpochs': [x['bestEpoch'] for x in selected]})
        winner = min(summaries, key=lambda x: (x['meanInnerMacroNLL'], x['lr']))
        chosen[variant] = {**winner, 'fixedEpochs': int(np.median(winner['foldBestEpochs'])), 'candidates': summaries}
    return chosen


def checked_replay(job, report):
    directory = Path(job['output'])
    record = job.get('replay', {})
    replay = read_json(directory / 'replay.json')
    require(job['state'] == 'complete' and job.get('exitCode') == 0 and record.get('verifiedExact') is True
            and record.get('state') == 'complete' and record.get('exitCode') == 0
            and digest(directory / 'replay.json') == record['sha256'] and replay['exact'] is True
            and replay['checkpointSha256'] == report['checkpointSha256']
            and replay['evaluation'] == report['evaluation']
            and replay['rows'] == len(read_json(directory / 'predictions.json')['rowIndices']),
            'Completed exact checkpoint replay is required for every inner trial')
    return {str((directory / name).resolve()): digest(directory / name) for name in ARTIFACTS}


def check_ledgers(unweighted_path, unweighted_sha, weighted_path, weighted_sha, binding):
    """Trust caller-pinned completed verification ledgers; recheck every artifact.

    Existing exact replay records are retained, not rewritten. The caller's
    ledger hashes anchor those records; selection never consumes outer results.
    """
    require(digest(unweighted_path) == unweighted_sha and digest(weighted_path) == weighted_sha,
            'Caller-pinned inner ledger digest differs')
    recipe = read_json(RECIPE)
    require(digest(head.RECIPE) == recipe['unweightedRecipeSha256']
            and digest(balanced.RECIPE) == recipe['weightedRecipeSha256']
            and digest(binding) == recipe['featureBindingSha256'], 'Final recipe input differs')
    ordinary, weighted = read_json(unweighted_path), read_json(weighted_path)
    require(ordinary['complete'] is True and weighted['complete'] is True, 'Both inner matrices must be complete')
    original_recipe = read_json(head.RECIPE)
    data = head.load_bound(binding, original_recipe)
    ordinary_queue.guard(ordinary['contract'])
    require(ordinary['contract']['binding'] == str(binding.resolve()), 'Original matrix feature binding differs')
    plan_path = Path(weighted['planPath'])
    plan = read_json(plan_path)
    balanced_queue.guard_plan(plan, plan_path, weighted['planSha256'])
    require(weighted['contract'] == plan['contract'] and plan['binding'] == str(binding.resolve())
            and plan['baselineLedger'] == {'path': str(unweighted_path.resolve()), 'sha256': unweighted_sha},
            'Weighted matrix declaration or original ledger differs')
    artifacts = {str(path.resolve()): sha for path, sha in ((unweighted_path, unweighted_sha),
        (weighted_path, weighted_sha), (plan_path, weighted['planSha256']), (binding, digest(binding)),
        (head.RECIPE, digest(head.RECIPE)), (balanced.RECIPE, digest(balanced.RECIPE)))}
    trials = []
    for objective, ledger, expected in (
        ('unweighted', ordinary, ordinary_queue.plan(original_recipe, unweighted_path.parent)),
        ('weighted', weighted, balanced_queue.plan_jobs(Path(plan['base']), read_json(balanced.RECIPE)))):
        jobs = ledger['jobs']
        require(len(jobs) == len(expected) and len({j['output'] for j in jobs}) == len(expected),
                'Inner matrix is partial or contains duplicate outputs')
        for job, declared in zip(jobs, expected, strict=True):
            require(all(job[key] == value for key, value in declared.items() if key != 'state'),
                    'Inner matrix inventory differs from fixed recipe')
            if objective == 'unweighted':
                verified = ordinary_queue.verify_complete(job, ordinary['contract'], data['cohort'], data['splits'],
                                                          original_recipe, data['bindings'])
            else:
                verified = balanced_queue.verify_completed(job, plan)
            require(job['verified'] == verified, 'Inner verification record differs')
            report = read_json(Path(job['output']) / 'report.json')
            artifacts.update(checked_replay(job, report))
            if job['family'] == 'target-scalars':
                trials.append({'variant': objective + '-' + job['regime'], 'fold': job['fold'], 'lr': job['lr'],
                    'bestEpoch': report['bestEpoch'], 'loss': report['bestSelectionMacroLogLoss'], 'output': job['output']})
    return trials, artifacts, data


def guard(plan, plan_path, expected_sha):
    require(digest(plan_path) == expected_sha and plan['sourceSha256'] == source_hashes()
            and plan['recipeSha256'] == digest(RECIPE) and plan['complete'] is True
            and plan['selections'] == selection(plan['trials']) and plan['variants'] == list(VARIANTS),
            'Final declaration, selection, source or recipe changed')
    require(all(digest(Path(path)) == sha for path, sha in plan['artifactsSha256'].items()),
            'Pinned inner artifact changed')
    head.extraction.guard(plan['inputFiles'])


def fresh_output(path):
    require(path.resolve().is_relative_to((HERE / 'outputs').resolve()) and not path.exists()
            and not path.with_name(path.name + '.partial').exists(), 'Choose a fresh ignored output path')


def declare(args):
    fresh_output(args.output)
    sources, recipe_sha = source_hashes(), digest(RECIPE)
    trials, artifacts, data = check_ledgers(args.unweighted_ledger, args.unweighted_sha256,
                                          args.weighted_ledger, args.weighted_sha256, args.binding)
    value = {'complete': True, 'phase': 'final-research-declaration', 'variants': list(VARIANTS),
             'recipeSha256': recipe_sha, 'sourceSha256': sources, 'trials': trials, 'selections': selection(trials),
             'artifactsSha256': artifacts, 'inputFiles': data['bindings'], 'binding': str(args.binding.resolve()),
             'authorPartition': 'train', 'innerTrialsVerified': 100, **FLAGS}
    require(sources == source_hashes() and digest(RECIPE) == recipe_sha
            and all(digest(Path(path)) == sha for path, sha in artifacts.items()),
            'Source, recipe or inner artifact changed during declaration')
    head.extraction.guard(data['bindings'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return value


def full_fit_data(bound, regime, objective):
    require(regime in ('all-age', 'child-only') and objective in ('weighted', 'unweighted')
            and bound['cohort']['authorPartition'] == 'train', 'Invalid final research population')
    rows = bound['cohort']['rows']
    eligible = [i for i, row in enumerate(rows) if row['trainingEligible']]
    require(set(bound['positions']) == set(eligible) and set(bound['positions'].values()) == set(range(len(eligible))),
            'Final feature coverage differs from eligible author training')
    fit = [i for i in eligible if regime == 'all-age' or is_child(rows[i])]
    require(fit and all(type(rows[i]['targetId']) is int and 0 <= rows[i]['targetId'] < 23
            and rows[i]['targetPhone'] == TARGETS[rows[i]['targetId']] for i in fit)
            and valid_counts(np.asarray([rows[i]['raterCounts'] for i in fit], dtype=float)), 'Invalid final fit labels/targets')
    values = np.concatenate((bound['arrays']['target'], bound['scalars']), axis=1)
    require(values.dtype == np.float32 and values.shape == (len(eligible), 1037)
            and np.isfinite(values).all(), 'Final target/scalar feature matrix differs')
    selected = np.asarray(values[[bound['positions'][i] for i in fit]], dtype=np.float64)
    mean, std = selected.mean(0), selected.std(0)
    std = np.where(std < 1e-6, 1., std)
    weights = fit_class_weights([rows[i] for i in fit], 'balanced-all-age' if objective == 'weighted' else 'child-only')
    return {**bound, 'values': values, 'fit': fit, 'mean': torch.tensor(mean, dtype=torch.float32),
            'std': torch.tensor(std, dtype=torch.float32), 'classWeightState': weights,
            'classWeights': torch.tensor(weights['weights'], dtype=torch.float32),
            'priors': fit_priors([rows[i] for i in fit])}


def model_args(rate):
    recipe = read_json(head.RECIPE)
    return argparse.Namespace(seed=7, hidden=recipe['hiddenWidth'], dropout=recipe['dropout'], lr=rate,
        weight_decay=recipe['weightDecay'], batch_size=recipe['batchSizeTargetRows'], threads=2, device='cpu')


@torch.no_grad()
def predict_features(model, mean, std, weights, features, target_ids, batch_size=64):
    """Research-only feature input: raw 1024 target vector + the fixed 13 scalars.

    No audio adapter or correctness threshold is provided. Each row is one
    singleton target; ZH (23), unknown IDs and nonfinite inputs are rejected.
    """
    features, target_ids = np.asarray(features), np.asarray(target_ids)
    require(features.dtype == np.float32 and features.ndim == 2 and features.shape[1] == 1037
            and len(features) > 0 and np.isfinite(features).all()
            and target_ids.shape == (len(features),) and np.issubdtype(target_ids.dtype, np.integer)
            and ((0 <= target_ids) & (target_ids < 23)).all()
            and set(target_ids.tolist()) <= set(getattr(model, 'research_supported_target_ids', range(23)))
            and type(batch_size) is int and batch_size > 0, 'Invalid feature-input contract or unsupported target')
    require(mean.shape == std.shape == (1037,) and torch.isfinite(mean).all()
            and torch.isfinite(std).all() and (std > 0).all(), 'Invalid frozen normalization')
    model.eval()
    probabilities = []
    for offset in range(0, len(features), batch_size):
        values = ((torch.from_numpy(features[offset:offset + batch_size].copy()) - mean) / std)[:, None]
        phones = torch.tensor(target_ids[offset:offset + batch_size, None], dtype=torch.long)
        mask = torch.ones_like(phones, dtype=torch.bool)
        probabilities.extend(corrected_probabilities(model(values, mask, phones, mask)[:, 0], weights).numpy())
    return np.asarray(probabilities, dtype=np.float64)


def fit_epochs(args, data, epochs, progress):
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    model = head.make_model(args, 1037)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        order, total = generator.permutation(data['fit']).tolist(), 0.
        for offset in range(0, len(order), args.batch_size):
            values, phones, mask, targets = head.batch(data, order[offset:offset + args.batch_size], 'cpu')
            optimizer.zero_grad(set_to_none=True)
            losses = weighted_loss(model(values, mask, phones, mask)[:, 0], targets, data['classWeights'])
            require(bool(torch.isfinite(losses).all()), 'Nonfinite final training objective')
            losses.mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            total += float(losses.detach().sum())
        history.append({'epoch': epoch, 'trainObjective': total / len(order)})
        progress(history)
    return model, optimizer, history


def features_for_fit(data):
    indices = data['fit']
    return data['values'][[data['positions'][i] for i in indices]], np.asarray(
        [data['cohort']['rows'][i]['targetId'] for i in indices], dtype=np.int64)


def fit(args):
    fresh_output(args.output)
    plan = read_json(args.plan)
    guard(plan, args.plan, args.plan_sha256)
    require(args.variant in VARIANTS, 'Undeclared final variant')
    objective, regime = args.variant.split('-', 1)
    selected = plan['selections'][args.variant]
    original = model_args(selected['lr'])
    torch.set_num_threads(original.threads)
    data = full_fit_data(head.load_bound(Path(plan['binding']), read_json(head.RECIPE)), regime, objective)
    require(data['bindings'] == plan['inputFiles'], 'Final fit input binding differs')
    rows = [data['cohort']['rows'][i] for i in data['fit']]
    targets = [{'id': i, 'phone': phone, 'supported': i < 23 and data['priors'][phone]['observedRows'] > 0,
                'fitRows': data['priors'][phone]['observedRows'] if i < 23 else 0} for i, phone in enumerate(TARGETS)]
    config = {'phase': 'final-research-refit', 'authorPartition': 'train', 'variant': args.variant,
        'objective': objective, 'regime': regime, 'family': 'target-scalars', 'planPath': str(args.plan.resolve()),
        'planSha256': args.plan_sha256, 'selection': selected, 'hyperparameters': vars(original),
        'fitRows': data['fit'], 'fitSpeakers': sorted({row['speakerId'] for row in rows}),
        'fitAgeRange': [min(row['age'] for row in rows), max(row['age'] for row in rows)],
        'priorState': data['priors'], 'classWeightState': data['classWeightState'], 'targets': targets,
        'sourceSha256': source_hashes(), 'recipeSha256': digest(RECIPE), 'inputFiles': data['bindings'], **FLAGS}
    temporary = args.output.with_name(args.output.name + '.partial')
    temporary.mkdir(parents=True, mode=0o700)
    atomic_json(temporary / 'config.json', config)
    config_sha = digest(temporary / 'config.json')
    started = time.perf_counter()

    def check():
        guard(plan, args.plan, args.plan_sha256)
        require(digest(temporary / 'config.json') == config_sha, 'Final configuration changed')

    def progress(history):
        check()
        atomic_json(temporary / 'history.json', history)
        atomic_json(temporary / 'status.json', {'complete': False, 'epoch': len(history), 'fixedEpochs': selected['fixedEpochs']})

    model, optimizer, history = fit_epochs(original, data, selected['fixedEpochs'], progress)
    save_checkpoint(temporary / 'checkpoint.pt', {'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
        'mean': data['mean'], 'std': data['std'], 'classWeights': data['classWeights'],
        'classWeightState': data['classWeightState'], 'epoch': selected['fixedEpochs'], 'configSha256': config_sha})
    features, ids = features_for_fit(data)
    p = predict_features(model, data['mean'], data['std'], data['classWeights'], features, ids, original.batch_size)
    saved = torch.load(temporary / 'checkpoint.pt', map_location='cpu', weights_only=True)
    reloaded = head.make_model(original, 1037)
    reloaded.load_state_dict(saved['model'], strict=True)
    reproduced = predict_features(reloaded, saved['mean'], saved['std'], saved['classWeights'], features, ids, original.batch_size)
    require(np.array_equal(p, reproduced), 'Saved final checkpoint does not exactly reproduce in-sample probabilities')
    atomic_json(temporary / 'verification.json', {'exactCheckpointReplay': True, 'rowIndices': data['fit'],
        'probabilities': p.tolist(), 'purpose': 'In-sample artifact verification only; not performance evidence', **FLAGS})
    atomic_json(temporary / 'normalization.json', {'mean': data['mean'].tolist(), 'std': data['std'].tolist(),
        'classWeightState': data['classWeightState'], 'priorState': data['priors'], 'fitRows': data['fit']})
    atomic_json(temporary / 'status.json', {'complete': True, 'epoch': len(history),
        'fixedEpochs': selected['fixedEpochs'], 'exactCheckpointReplay': True, 'researchOnly': True})
    manifest = {'complete': True, 'researchOnly': True, 'variant': args.variant, 'targets': targets,
        'predictionMeaning': 'Three-class subjective SpeechOcean rater distribution; not a produced-phone or pronunciation decision',
        'probabilityScale': 'softmax(logits - log(fit class weights)); weights equal one for unweighted variants',
        'featureContract': {'dtype': 'float32', 'shape': ['N', 1037], 'columns':
            [f'targetPhonetic:{i}' for i in range(1024)] + list(head.SCALAR_NAMES),
            'sourceBindingPath': plan['binding'], 'sourceBindingSha256': digest(Path(plan['binding'])),
            'timing': 'Forced canonical CTC occupancy with fixed context; not validated phonetic boundaries',
            'entrypoint': 'load_export(directory, expected_manifest_sha256), then predict_features with raw features and canonical target IDs'},
        'filesSha256': {name: digest(temporary / name) for name in
            ('config.json', 'checkpoint.pt', 'history.json', 'verification.json', 'normalization.json', 'status.json')},
        'epochsRun': len(history), 'elapsedSeconds': time.perf_counter() - started, **FLAGS}
    atomic_json(temporary / 'manifest.json', manifest)
    manifest_sha = digest(temporary / 'manifest.json')
    check()
    # Recheck every exported file immediately before publishing the complete directory.
    require(digest(temporary / 'manifest.json') == manifest_sha
            and all(digest(temporary / name) == sha for name, sha in manifest['filesSha256'].items()),
            'Final export changed before publication')
    temporary.rename(args.output)
    return manifest


def load_export(directory, expected_manifest_sha256):
    require(digest(directory / 'manifest.json') == expected_manifest_sha256, 'Caller-pinned export manifest differs')
    manifest = read_json(directory / 'manifest.json')
    require(manifest['complete'] is True and manifest['researchOnly'] is True
            and all(manifest[name] is False for name in FLAGS)
            and set(manifest['filesSha256']) == {'config.json', 'checkpoint.pt', 'history.json', 'verification.json', 'normalization.json', 'status.json'}
            and all(digest(directory / name) == sha for name, sha in manifest['filesSha256'].items()), 'Research export artifact differs')
    config = read_json(directory / 'config.json')
    plan_path = Path(config['planPath'])
    plan = read_json(plan_path)
    guard(plan, plan_path, config['planSha256'])
    require(config['sourceSha256'] == source_hashes() and config['recipeSha256'] == digest(RECIPE)
            and config['selection'] == plan['selections'][config['variant']]
            and config['targets'] == manifest['targets'] and config['variant'] == manifest['variant']
            and config['variant'] == config['objective'] + '-' + config['regime']
            and config['phase'] == 'final-research-refit' and config['authorPartition'] == 'train'
            and config['family'] == 'target-scalars' and config['inputFiles'] == plan['inputFiles']
            and all(config[name] is False for name in FLAGS), 'Final checkpoint provenance differs')
    feature_contract = manifest['featureContract']
    require(feature_contract['dtype'] == 'float32' and feature_contract['shape'] == ['N', 1037]
            and feature_contract['columns'] == [f'targetPhonetic:{i}' for i in range(1024)] + list(head.SCALAR_NAMES)
            and feature_contract['sourceBindingPath'] == plan['binding']
            and feature_contract['sourceBindingSha256'] == digest(Path(plan['binding']))
            and [(target['id'], target['phone']) for target in manifest['targets']] == list(enumerate(TARGETS))
            and manifest['targets'][23]['supported'] is False, 'Final feature contract or target inventory differs')
    args = model_args(config['selection']['lr'])
    require(config['hyperparameters'] == vars(args), 'Final model hyperparameters differ')
    require(read_json(directory / 'status.json') == {'complete': True, 'epoch': manifest['epochsRun'],
            'fixedEpochs': config['selection']['fixedEpochs'], 'exactCheckpointReplay': True, 'researchOnly': True},
            'Final export completion status differs')
    torch.set_num_threads(args.threads)
    saved = torch.load(directory / 'checkpoint.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == digest(directory / 'config.json') and saved['epoch'] == config['selection']['fixedEpochs']
            == manifest['epochsRun'] and saved['classWeightState'] == config['classWeightState'], 'Final checkpoint binding differs')
    norm = read_json(directory / 'normalization.json')
    require(norm == {'mean': saved['mean'].tolist(), 'std': saved['std'].tolist(),
        'classWeightState': config['classWeightState'], 'priorState': config['priorState'], 'fitRows': config['fitRows']}
        and torch.equal(saved['classWeights'], torch.tensor(config['classWeightState']['weights'], dtype=torch.float32)),
        'Exported fit statistics differ')
    model = head.make_model(args, 1037)
    model.load_state_dict(saved['model'], strict=True)
    model.research_supported_target_ids = tuple(target['id'] for target in config['targets'] if target['supported'])
    return model, saved, config, manifest


def replay(directory, expected_manifest_sha256):
    model, saved, config, manifest = load_export(directory, expected_manifest_sha256)
    plan = read_json(Path(config['planPath']))
    data = full_fit_data(head.load_bound(Path(plan['binding']), read_json(head.RECIPE)), config['regime'], config['objective'])
    require(config['fitRows'] == data['fit'] and config['priorState'] == data['priors']
            and config['classWeightState'] == data['classWeightState'] and config['inputFiles'] == data['bindings']
            and all(torch.equal(saved[key], data[key]) for key in ('mean', 'std', 'classWeights')), 'Full-fit statistics changed')
    features, ids = features_for_fit(data)
    p = predict_features(model, saved['mean'], saved['std'], saved['classWeights'], features, ids,
                         config['hyperparameters']['batch_size'])
    verification = read_json(directory / 'verification.json')
    require(verification['exactCheckpointReplay'] is True and verification['rowIndices'] == data['fit']
            and np.array_equal(p, verification['probabilities']), 'Final in-sample checkpoint replay differs')
    guard(plan, Path(config['planPath']), config['planSha256'])
    require(digest(directory / 'manifest.json') == expected_manifest_sha256
            and all(digest(directory / name) == sha for name, sha in manifest['filesSha256'].items()), 'Export changed during replay')
    return {'exact': True, 'rows': len(p), 'manifestSha256': expected_manifest_sha256, 'performanceClaim': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    declaration = commands.add_parser('declare')
    for name in ('unweighted-ledger', 'weighted-ledger', 'binding', 'output'):
        declaration.add_argument('--' + name, type=Path, required=True)
    for name in ('unweighted-sha256', 'weighted-sha256'):
        declaration.add_argument('--' + name, required=True)
    train = commands.add_parser('fit')
    train.add_argument('--plan', type=Path, required=True)
    train.add_argument('--plan-sha256', required=True)
    train.add_argument('--variant', choices=VARIANTS, required=True)
    train.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('replay')
    check.add_argument('--output', type=Path, required=True)
    check.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    value = declare(args) if args.command == 'declare' else fit(args) if args.command == 'fit' else replay(args.output, args.manifest_sha256)
    print(json.dumps({'complete': value.get('complete', value.get('exact'))}), flush=True)
