"""Fresh deterministic heads with a fixed fitting-only recording/sound objective."""
import hashlib
import json
from pathlib import Path
import torch
from lexical_heads import core as scalar
from lexical_compact import core as compact
from lexical_unit_weights import weights
from multiphone_local_head import batch

RECIPE = scalar.RECIPE
require, binding, _json, _history_snapshot = scalar.require, scalar.binding, scalar._json, scalar._history_snapshot


def implementation(family):
    require(family in ('scalars','pca16-scalars'), 'Unknown unit-weight family')
    return scalar if family == 'scalars' else compact


def prepare(bundle, family, fitRows):
    state = weights.fit_weights(bundle['cohort'], fitRows)
    data = implementation(family).prepare(bundle, family, fitRows)
    data['weightState'] = state
    return data


def weighted_loss(logits, targets, row_weights):
    require(logits.dtype == targets.dtype == row_weights.dtype == torch.float32
            and logits.device.type == targets.device.type == row_weights.device.type == 'cpu'
            and logits.ndim == 2 and logits.shape[1] == 3 and targets.shape == logits.shape
            and row_weights.shape == (len(logits),) and len(logits) > 0
            and torch.isfinite(logits).all() and torch.isfinite(targets).all()
            and torch.isfinite(row_weights).all() and (row_weights > 0).all()
            and (targets >= 0).all() and torch.allclose(targets.sum(1),torch.ones(len(logits)),rtol=0,atol=1e-6),
            'Invalid weighted-loss arrays')
    # The fitting normalization is fixed across batches; no batch-mass ratio.
    return (-(targets * logits.log_softmax(-1)).sum(1) * row_weights).mean()


def _save(path, model, optimizer, data, generator, config_sha, epoch, best_epoch, best_loss, weight_sha, transform_sha):
    payload = dict(model=model.state_dict(), optimizer=optimizer.state_dict(),
                   mean=data['mean'].clone(), std=data['std'].clone(), priorState=data['priors'],
                   epoch=epoch, bestEpoch=best_epoch, bestLoss=best_loss, configSha256=config_sha,
                   rng=scalar._rng(generator), weightsSha256=weight_sha)
    if transform_sha is not None:
        payload['transformSha256'] = transform_sha
    temporary = Path(path).with_suffix('.writing')
    with temporary.open('xb') as stream:
        torch.save(payload,stream)
    temporary.replace(path)


def train(data, selectionRows, output, config, epochs=None):
    """Fresh initialization; inner selection or fixed-epoch refit, never both."""
    backend = implementation(data['family'])
    backend._indices(data, data['fit'])
    require(data['weightState'] == weights.fit_weights(data['cohort'], data['fit']), 'Fitting weight state differs')
    backend._indices(data, selectionRows, empty=epochs is not None)
    require(not set(data['fit']) & set(selectionRows), 'Selection rows overlap fitting rows')
    if epochs is not None:
        require(type(epochs) is int and 1 <= epochs <= 100 and not selectionRows,
                'Refit requires 1..100 fixed epochs and no selection rows')
    else:
        require(bool(selectionRows), 'Inner training requires selection rows')
    output = Path(output)
    require(not output.exists(), 'Training requires a fresh output directory')
    model, generator = backend.initialize(data['values'].shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0003, weight_decay=.01)
    reserved = dict(weightRecipe=weights.RECIPE, recipe=RECIPE, family=data['family'], fitRows=data['fit'], selectionRows=list(selectionRows),
                    priorState=data['priors'], featureWidth=data['values'].shape[1],
                    phase='inner' if epochs is None else 'outer-refit', fixedEpochs=epochs,
                    selectionObjective='equal-position five-vote NLL' if epochs is None else None,
                    authorTestRead=False, encoderInferencePerformed=False,
                    clinicalUseEligible=False, learnerFeedbackEligible=False, outerPredictionsRead=False)
    if data['family'] == 'pca16-scalars':
        reserved['transformRecipe'] = compact.TRANSFORM_RECIPE
    require(isinstance(config, dict) and all(k not in config or config[k] == v for k, v in reserved.items()),
            'Caller configuration conflicts with fixed training recipe')
    config = {**config, **reserved}
    output.mkdir(parents=True, mode=0o700)
    _json(output/'weights.json', data['weightState'])
    weight_pin = binding(output/'weights.json')
    require('weights' not in config or config['weights'] == weight_pin, 'Caller weight binding differs')
    config['weights'] = weight_pin
    config['weightRecipe'] = weights.RECIPE
    transform_pin = None
    if data['family'] == 'pca16-scalars':
        with (output/'transform.pt').open('xb') as stream:
            torch.save(data['transform'], stream)
        transform_pin = binding(output/'transform.pt')
        require('transform' not in config or config['transform'] == transform_pin, 'Caller transform binding differs')
        config['transform'] = transform_pin
        config['transformRecipe'] = compact.TRANSFORM_RECIPE
    _json(output/'config.json', config)
    config_sha = binding(output/'config.json')['sha256']
    _json(output/'prior.json', data['priors'])
    best_loss, best_epoch, history = None, 0, []
    _save(output/'initial.pt', model, optimizer, data, generator, config_sha, 0, 0, None, weight_pin['sha256'], None if transform_pin is None else transform_pin['sha256'])
    row_weights = dict(zip(data['fit'],data['weightState']['weights'],strict=True))
    total_updates = 0
    for epoch in range(1, (100 if epochs is None else epochs) + 1):
        model.train()
        order = generator.permutation(data['fit']).tolist()
        total_loss = 0.
        updates = 0
        for offset in range(0, len(order), 64):
            indices = order[offset:offset+64]
            values, phones, mask, targets = batch(data, indices, 'cpu')
            optimizer.zero_grad(set_to_none=True)
            logits = model(values, mask, phones, mask)[:, 0]
            loss = weighted_loss(logits, targets, torch.tensor([row_weights[i] for i in indices], dtype=torch.float32))
            require(bool(torch.isfinite(loss)), 'Nonfinite training loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            total_loss += float(loss.detach()) * len(indices)
            updates += 1
        total_updates += updates
        row = dict(epoch=epoch, trainLoss=total_loss/len(order), updates=updates, totalUpdates=total_updates,
                   orderSha256=hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest())
        if epochs is None:
            selection = backend.predict(model, data, selectionRows)
            row['selection'] = selection
            if best_loss is None or selection['NLL'] < best_loss - 1e-7:
                best_loss, best_epoch = selection['NLL'], epoch
                _save(output/'best.pt', model, optimizer, data, generator, config_sha, epoch, best_epoch, best_loss, weight_pin['sha256'], None if transform_pin is None else transform_pin['sha256'])
        else:
            best_epoch = epoch
        history.append(row)
        _history_snapshot(output/'history.json', history)
        _save(output/'last.pt', model, optimizer, data, generator, config_sha, epoch, best_epoch, best_loss, weight_pin['sha256'], None if transform_pin is None else transform_pin['sha256'])
        if epochs is None and epoch - best_epoch >= 15:
            break
    if epochs is not None:
        _save(output/'best.pt', model, optimizer, data, generator, config_sha, epoch, epoch, None, weight_pin['sha256'], None if transform_pin is None else transform_pin['sha256'])
    if epochs is None:
        selected = history[best_epoch-1]['selection']
        _json(output/'selection.json', selected)
        require(replay(output, data, selectionRows) == selected, 'Selected checkpoint does not replay exactly')
    summary = dict(complete=True, phase=config['phase'], mode=config['phase'],
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



def replay(directory, data, indices, checkpoint='best.pt'):
    require(checkpoint in ('best.pt','last.pt','initial.pt'), 'Unknown checkpoint')
    directory = Path(directory)
    expected = weights.fit_weights(data['cohort'], data['fit'])
    require(data['weightState'] == expected, 'Replay fitting weight state differs')
    config = json.loads((directory/'config.json').read_text())
    weight_pin = binding(directory/'weights.json')
    require(config['weightRecipe'] == weights.RECIPE and config['weights'] == weight_pin
            and json.loads((directory/'weights.json').read_text()) == expected, 'Replay weight binding differs')
    state = torch.load(directory/checkpoint, map_location='cpu', weights_only=True)
    require(state['weightsSha256'] == weight_pin['sha256'], 'Checkpoint weight binding differs')
    return implementation(data['family']).replay(directory,data,indices,checkpoint)
