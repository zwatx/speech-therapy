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

from lexical_compact import core as compact
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
