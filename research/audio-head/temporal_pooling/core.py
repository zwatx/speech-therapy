"""Seeded fresh heads for both fixed expanded fitting objectives.

Frozen feature geometry, unweighted moments/PCA/priors, optimizer, partial
batches and unweighted selection are reused unchanged; only the training seed
and the fixed fitting-row weights differ between runs.
"""
import hashlib
import json
from pathlib import Path
import random

import numpy as np
import torch

from temporal_pooling import compact
from lexical_heads import core as scalar
from lexical_unit_weights import core as unitcore
from lexical_unit_weights import weights
from multiphone_local_head import batch
from multiphone_models import MeanPoolPhoneRatingHead

OBJECTIVES = ('unweighted', 'unit-weighted')
SEEDS = (17, 29, 43)
FAMILIES = ('scalars', 'pca16-scalars')
WIDTHS = {'scalars': 13, 'pca16-scalars': 29}
UNWEIGHTED_RECIPE = dict(raw='uniform weight 1 for every complete supported canonical position',
                         normalization='none; every fit weight is exactly 1.0',
                         scope='complete supported canonical positions in selected recordings',
                         batchReduction='mean of five-vote NLL over batch positions',
                         selection='unweighted original selection rows', classWeighting=False)

require, binding, _json, _history_snapshot = scalar.require, scalar.binding, scalar._json, scalar._history_snapshot
# Frozen pure loss and seed-agnostic checkpoint writer from the seed-7 unit-weight trainer.
weighted_loss, _save = unitcore.weighted_loss, unitcore._save

require(compact.RECIPE == scalar.RECIPE, 'Frozen scalar and compact head recipes differ')


def recipe(seed):
    """Copy of the frozen head recipe with only the training seed replaced."""
    require(type(seed) is int and 0 <= seed < 2**32, 'Seed must be an int in [0, 2**32)')
    return {**scalar.RECIPE, 'seed': seed}


def implementation(family):
    require(family in FAMILIES, 'Unknown seed-replication family')
    return scalar if family == 'scalars' else compact


def fitting_weights(cohort, fitRows, objective):
    """Canonical complete fitting geometry; unit weights, or all-one weights for the control."""
    require(type(objective) is str and objective in OBJECTIVES, 'Unknown fitting objective')
    state = weights.fit_weights(cohort, fitRows)
    if objective == 'unit-weighted':
        return state
    return dict(recipe=dict(UNWEIGHTED_RECIPE), fitRows=state['fitRows'], canonicalCounts=state['canonicalCounts'],
                unitCount=state['unitCount'], normalization=1., weights=[1.] * len(state['fitRows']))


def prepare(bundle, family, fitRows, objective):
    """Frozen unweighted moments/PCA/priors plus the bound fitting weight state."""
    backend = implementation(family)
    state = fitting_weights(bundle['cohort'], fitRows, objective)
    data = backend.prepare(bundle, family, fitRows)
    data.update(objective=objective, weightState=state)
    return data


def initialize(width, seed):
    """Reset every training random stream to seed and create the frozen fresh head."""
    settings = recipe(seed)
    require(type(width) is int and width in (13, 29), 'Unexpected feature width')
    torch.set_num_threads(settings['threads'])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    model = MeanPoolPhoneRatingHead(feature_dim=width, num_phones=settings['numPhones'],
                                    hidden_dim=settings['hidden'], dropout=settings['dropout']).cpu()
    return model, np.random.default_rng(seed)


def _checked(data):
    """Frozen row checks plus an exact re-derivation of the bound fitting weight state."""
    backend = implementation(data['family'])
    require(data['values'].shape[1] == WIDTHS[data['family']], 'Unexpected feature width')
    backend._indices(data, data['fit'])
    state = fitting_weights(data['cohort'], data['fit'], data['objective'])
    require(data['weightState'] == state, 'Fitting weight state differs')
    require(data['family'] == 'scalars' or data['transform']['fitRows'] == data['fit'],
            'Transform was not fitted on the fitting rows')
    return backend, state


def train(data, selectionRows, output, config, *, seed, epochs=None):
    """Fresh seeded initialization; inner selection or fixed-epoch refit, never both."""
    settings = recipe(seed)
    backend, state = _checked(data)
    backend._indices(data, selectionRows, empty=epochs is not None)
    require(not set(data['fit']) & set(selectionRows), 'Selection rows overlap fitting rows')
    if epochs is not None:
        require(type(epochs) is int and 1 <= epochs <= settings['maximumEpochs'] and not selectionRows,
                'Refit requires 1..100 fixed epochs and no selection rows')
    else:
        require(bool(selectionRows), 'Inner training requires selection rows')
    output = Path(output)
    require(not output.exists(), 'Training requires a fresh output directory')
    compact_family = data['family'] == 'pca16-scalars'
    reserved = dict(objective=data['objective'], seed=seed, recipe=settings, weightRecipe=state['recipe'],
                    family=data['family'], fitRows=data['fit'], selectionRows=list(selectionRows),
                    priorState=data['priors'], featureWidth=data['values'].shape[1],
                    phase='inner' if epochs is None else 'outer-refit', fixedEpochs=epochs,
                    selectionObjective='equal-position five-vote NLL' if epochs is None else None,
                    authorTestRead=False, encoderInferencePerformed=False,
                    clinicalUseEligible=False, learnerFeedbackEligible=False, outerPredictionsRead=False)
    if compact_family:
        reserved['transformRecipe'] = compact.TRANSFORM_RECIPE
    require(isinstance(config, dict) and all(k not in config or config[k] == v for k, v in reserved.items()),
            'Caller configuration conflicts with fixed training recipe')
    config = {**config, **reserved}
    model, generator = initialize(data['values'].shape[1], seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings['lr'], weight_decay=settings['weightDecay'])
    output.mkdir(parents=True, mode=0o700)
    _json(output/'weights.json', state)
    weight_pin = binding(output/'weights.json')
    require('weights' not in config or config['weights'] == weight_pin, 'Caller weight binding differs')
    config['weights'] = weight_pin
    transform_pin = None
    if compact_family:
        with (output/'transform.pt').open('xb') as stream:
            torch.save(data['transform'], stream)
        transform_pin = binding(output/'transform.pt')
        require('transform' not in config or config['transform'] == transform_pin, 'Caller transform binding differs')
        config['transform'] = transform_pin
    _json(output/'config.json', config)
    config_sha = binding(output/'config.json')['sha256']
    _json(output/'prior.json', data['priors'])
    transform_sha = None if transform_pin is None else transform_pin['sha256']

    def save(name, epoch, best_epoch, best_loss):
        _save(output/name, model, optimizer, data, generator, config_sha, epoch, best_epoch, best_loss,
              weight_pin['sha256'], transform_sha)

    best_loss, best_epoch, history = None, 0, []
    save('initial.pt', 0, 0, None)
    row_weights = dict(zip(data['fit'], state['weights'], strict=True))
    total_updates = 0
    for epoch in range(1, (settings['maximumEpochs'] if epochs is None else epochs) + 1):
        model.train()
        order = generator.permutation(data['fit']).tolist()
        total_loss = 0.
        updates = 0
        for offset in range(0, len(order), settings['batchSize']):
            indices = order[offset:offset+settings['batchSize']]
            values, phones, mask, targets = batch(data, indices, 'cpu')
            optimizer.zero_grad(set_to_none=True)
            logits = model(values, mask, phones, mask)[:, 0]
            loss = weighted_loss(logits, targets, torch.tensor([row_weights[i] for i in indices], dtype=torch.float32))
            require(bool(torch.isfinite(loss)), 'Nonfinite training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), settings['clipNorm'], error_if_nonfinite=True)
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
            updates += 1
        total_updates += updates
        row = dict(epoch=epoch, trainLoss=total_loss/len(order), updates=updates, totalUpdates=total_updates,
                   orderSha256=hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest())
        if epochs is None:
            selection = backend.predict(model, data, selectionRows)
            row['selection'] = selection
            if best_loss is None or selection['NLL'] < best_loss - settings['minimumImprovement']:
                best_loss, best_epoch = selection['NLL'], epoch
                save('best.pt', epoch, best_epoch, best_loss)
        else:
            best_epoch = epoch
        history.append(row)
        _history_snapshot(output/'history.json', history)
        save('last.pt', epoch, best_epoch, best_loss)
        if epochs is None and epoch - best_epoch >= settings['patience']:
            break
    if epochs is not None:
        save('best.pt', epoch, epoch, None)
    else:
        selected = history[best_epoch-1]['selection']
        _json(output/'selection.json', selected)
        require(replay(output, data, selectionRows, seed=seed) == selected,
                'Selected checkpoint does not replay exactly')
    summary = dict(complete=True, phase=config['phase'], mode=config['phase'], objective=data['objective'], seed=seed,
                   fitRows=data['fit'], selectionRows=list(selectionRows), epochsRun=epoch, bestEpoch=best_epoch,
                   bestLoss=best_loss, totalUpdates=total_updates,
                   exactSelectionReplay=epochs is None, configSha256=config_sha,
                   artifacts={name: binding(output/name) for name in
                              ('config.json','weights.json','prior.json','initial.pt','best.pt','last.pt','history.json')})
    if transform_pin is not None:
        summary['artifacts']['transform.pt'] = transform_pin
    if epochs is None:
        summary['artifacts']['selection.json'] = binding(output/'selection.json')
    _json(output/'report.json', summary)
    return {**summary, 'report': binding(output/'report.json')}


def replay(directory, data, indices, *, seed, checkpoint='best.pt'):
    """Replay a seeded state only after every objective, config, artifact and moment check."""
    require(checkpoint in ('best.pt', 'last.pt', 'initial.pt'), 'Unknown checkpoint')
    settings = recipe(seed)
    backend, state = _checked(data)
    directory = Path(directory)
    compact_family = data['family'] == 'pca16-scalars'
    config = json.loads((directory/'config.json').read_text())
    expected = dict(objective=data['objective'], seed=seed, recipe=settings, weightRecipe=state['recipe'],
                    family=data['family'], featureWidth=data['values'].shape[1], fitRows=data['fit'],
                    priorState=data['priors'])
    if compact_family:
        expected['transformRecipe'] = compact.TRANSFORM_RECIPE
    require(isinstance(config, dict) and all(k in config and config[k] == v for k, v in expected.items())
            and config.get('phase') in ('inner', 'outer-refit'), 'Replay training configuration differs')
    weight_pin = binding(directory/'weights.json')
    require(config.get('weights') == weight_pin and json.loads((directory/'weights.json').read_text()) == state,
            'Replay weight binding differs')
    transform_sha = None
    if compact_family:
        transform_pin = binding(directory/'transform.pt')
        require(config.get('transform') == transform_pin, 'Replay transform binding differs')
        saved_transform = torch.load(directory/'transform.pt', map_location='cpu', weights_only=True)
        require(compact.same_transform(saved_transform, data['transform']), 'Replay fit-only PCA state differs')
        transform_sha = transform_pin['sha256']
    saved = torch.load(directory/checkpoint, map_location='cpu', weights_only=True)
    require(saved.get('weightsSha256') == weight_pin['sha256'], 'Checkpoint weight binding differs')
    require(saved.get('configSha256') == binding(directory/'config.json')['sha256']
            and ('transformSha256' in saved) == compact_family and saved.get('transformSha256') == transform_sha
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std'])
            and saved.get('priorState') == data['priors'], 'Replay normalization/config state differs')
    model, _ = initialize(data['values'].shape[1], seed)
    model.load_state_dict(saved['model'], strict=True)
    value = backend.predict(model, data, indices)
    if checkpoint == 'best.pt' and config['phase'] == 'inner' and indices == config.get('selectionRows'):
        selected = json.loads((directory/'selection.json').read_text())
        require(saved['epoch'] == saved['bestEpoch'] and saved['bestLoss'] == value['NLL'] and value == selected,
                'Selected state or predictions differ')
    return value


# Frozen saved-state validation, with only the temporal transform recipe routed locally.
import math
import torch.nn.functional as F
from lexical_expanded_heads import study as prior
from lexical_seed_replication.validation import JOB_FIELDS
read = prior.read

def validate_run(job, record, plan_pin, phase, cohort):
    require(phase in ('inner', 'outer-refit') and record['jobId'] == job['id'], 'Wrong run identity or phase')
    artifacts = record['artifacts']
    required = {'config.json', 'weights.json', 'prior.json', 'initial.pt', 'best.pt', 'last.pt', 'history.json', 'report.json'}
    if phase == 'inner':
        required |= {'selection.json', 'selected-replay.json'}
    if job['family'] == 'pca16-scalars':
        required.add('transform.pt')
    require(set(artifacts) == required, 'Exact complete artifact inventory required')
    report = prior.scalar.check_manifest(artifacts)
    cfg = read(artifacts['config.json'])
    fit = job['fitRows' if phase == 'inner' else 'refitRows']
    selection = job['selectionRows'] if phase == 'inner' else []
    width = 13 if job['family'] == 'scalars' else 29
    weight_state = fitting_weights(cohort, fit, job['objective'])
    priors = prior.scalar.core.fit_priors([cohort['rows'][i] for i in fit])
    require(cfg['experiment'] == 'lexical-seed-replication-v1' and cfg['phase'] == phase
            and cfg['plan'] == plan_pin and cfg['job'] == {k: job[k] for k in JOB_FIELDS}
            and cfg['seed'] == job['seed'] and cfg['objective'] == job['objective']
            and cfg['recipe'] == recipe(job['seed']) and cfg['family'] == job['family']
            and cfg['fitRows'] == fit and cfg['selectionRows'] == selection and cfg['featureWidth'] == width
            and cfg['priorState'] == priors == read(artifacts['prior.json'])
            and cfg['addedValidationRowsNotUsedForSelection'] == job['addedValidationRows'], 'Run configuration differs')
    require(all(cfg[k] is v for k, v in prior.FLAGS.items()) and cfg['outerInferencePerformed'] is False,
            'Run scope flags differ')
    require(cfg['weightRecipe'] == weight_state['recipe'] and cfg['weights'] == artifacts['weights.json']
            and read(artifacts['weights.json']) == weight_state, 'Objective-specific fitting weights differ')
    if width == 29:
        require(cfg['transform'] == artifacts['transform.pt']
                and cfg['transformRecipe'] == compact.TRANSFORM_RECIPE, 'Transform lineage differs')
        transform = torch.load(artifacts['transform.pt']['path'], map_location='cpu', weights_only=True)
        require(transform['fitRows'] == fit and transform['rank'] == 16, 'Transform fit membership differs')
    require(report['complete'] is True and report['phase'] == report['mode'] == phase
            and report['objective'] == job['objective'] and report['seed'] == job['seed']
            and report['configSha256'] == artifacts['config.json']['sha256']
            and report['fitRows'] == fit and report['selectionRows'] == selection
            and set(report['artifacts']) == required - {'report.json', 'selected-replay.json'}
            and all(artifacts[name] == value for name, value in report['artifacts'].items()), 'Run report binding differs')
    history = read(artifacts['history.json'])
    require(1 <= len(history) <= 100 and report['epochsRun'] == len(history), 'Incomplete epoch history')
    model, generator = initialize(width, job['seed'])
    fresh = model.state_dict()
    initial_rng = torch.get_rng_state().clone()
    best_epoch, best_loss = 0, None
    states = {0: (0, None, generator.bit_generator.state, initial_rng)}
    updates = math.ceil(len(fit) / 64)
    for epoch, entry in enumerate(history, 1):
        order = generator.permutation(fit).tolist()
        order_sha = hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest()
        require(entry['epoch'] == epoch and entry['orderSha256'] == order_sha and entry['updates'] == updates
                and entry['totalUpdates'] == epoch * updates and math.isfinite(entry['trainLoss'])
                and entry['trainLoss'] >= 0, 'Training update/order history differs')
        for start in range(0, len(fit), 64):
            F.dropout(torch.ones(min(64, len(fit) - start), 1, 128), p=.1, training=True)
        if phase == 'inner':
            prediction = entry['selection']
            prior.evaluation.checked_prediction(prediction, selection, [cohort['rows'][i] for i in selection])
            counts = np.asarray([cohort['rows'][i]['raterCounts'] for i in selection])
            loss = float(-(counts * np.asarray(prediction['logProbabilities'])).sum() / (5 * len(selection)))
            require(prediction['NLL'] == loss, 'Selection NLL differs from votes and stable logs')
            if best_loss is None or loss < best_loss - 1e-7:
                best_epoch, best_loss = epoch, loss
            require(epoch == len(history) or epoch - best_epoch < 15, 'Training continued past patience')
        else:
            require('selection' not in entry, 'Refit used selection')
            best_epoch = epoch
        states[epoch] = best_epoch, best_loss, generator.bit_generator.state, torch.get_rng_state().clone()
    require(report['totalUpdates'] == len(history) * updates and report['bestEpoch'] == record['selectedEpoch'] == best_epoch
            and report['bestLoss'] == best_loss and report['exactSelectionReplay'] is (phase == 'inner'), 'Final selection differs')
    if phase == 'inner':
        require(cfg['fixedEpochs'] is None and cfg['selectionObjective'] == 'equal-position five-vote NLL'
                and (len(history) == 100 or len(history) - best_epoch == 15), 'Inner stopping/objective differs')
        require(read(artifacts['selection.json']) == read(artifacts['selected-replay.json']) == history[best_epoch - 1]['selection'],
                'Selected replay differs from history')
    else:
        require(cfg['fixedEpochs'] == cfg['innerSelection']['epoch'] == len(history)
                and cfg['selectionObjective'] is None, 'Refit duration differs')
    numpy_global = np.random.RandomState(job['seed']).get_state()
    expected_numpy = dict(algorithm=numpy_global[0], keys=numpy_global[1].tolist(), position=numpy_global[2],
                          hasGaussian=numpy_global[3], cachedGaussian=numpy_global[4])
    for filename, epoch in (('initial.pt', 0), ('best.pt', best_epoch), ('last.pt', len(history))):
        state = torch.load(artifacts[filename]['path'], map_location='cpu', weights_only=True)
        be, bl, permutation_rng, torch_rng = states[epoch]
        require(state['epoch'] == epoch and state['bestEpoch'] == be and state['bestLoss'] == bl
                and state['configSha256'] == artifacts['config.json']['sha256']
                and state['weightsSha256'] == artifacts['weights.json']['sha256'] and state['priorState'] == priors,
                'Checkpoint epoch/config/weight/prior differs')
        require(state['mean'].shape == state['std'].shape == (width,)
                and state['mean'].dtype == state['std'].dtype == torch.float32
                and torch.isfinite(state['mean']).all() and torch.isfinite(state['std']).all()
                and (state['std'] > 0).all(), 'Invalid checkpoint normalization')
        if width == 29:
            require(state['transformSha256'] == artifacts['transform.pt']['sha256'], 'Checkpoint PCA lineage differs')
        require(list(state['model']) == list(fresh), 'Parameter keys/order differ')
        for name, value in state['model'].items():
            require(value.shape == fresh[name].shape and value.dtype == fresh[name].dtype
                    and torch.isfinite(value).all(), 'Invalid model parameter')
            if epoch == 0:
                require(torch.equal(value, fresh[name]), 'Fresh seeded initialization differs')
        rng = state['rng']
        require(rng['python'] == random.Random(job['seed']).getstate() and rng['numpyGlobal'] == expected_numpy
                and rng['numpyPermutation'] == permutation_rng and torch.equal(rng['torch'], torch_rng), 'Checkpoint RNG differs')
        optimizer = state['optimizer']
        groups = optimizer['param_groups']
        require(len(groups) == 1 and groups[0]['params'] == list(range(len(fresh)))
                and groups[0]['lr'] == .0003 and groups[0]['weight_decay'] == .01
                and groups[0]['betas'] == (.9, .999) and groups[0]['eps'] == 1e-8
                and groups[0]['amsgrad'] is False and groups[0]['maximize'] is False, 'Optimizer recipe differs')
        moments = optimizer['state']
        require(set(moments) == (set() if epoch == 0 else set(range(len(fresh)))), 'Optimizer parameter coverage differs')
        for index, value in moments.items():
            require(set(value) == {'step', 'exp_avg', 'exp_avg_sq'} and value['step'].numel() == 1
                    and value['step'].item() == epoch * updates, 'Optimizer update counter differs')
            for key in ('exp_avg', 'exp_avg_sq'):
                require(value[key].shape == list(fresh.values())[index].shape and value[key].dtype == torch.float32
                        and torch.isfinite(value[key]).all(), 'Invalid optimizer moment')
            require((value['exp_avg_sq'] >= 0).all(), 'Negative second moment')
    return report
