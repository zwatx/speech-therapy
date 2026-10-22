"""Seeded PCA16/scalar heads with a fixed rating-zero proper loss."""
import hashlib
import json
from pathlib import Path

import torch

from lexical_compact import core as compact
from lexical_seed_replication import core as seeded
from multiphone_local_head import batch

SEEDS = (17, 29, 43)
FAMILY = 'pca16-scalars'
COEFFICIENT = 1.
OBJECTIVE = 'five-vote NLL plus rating-0 Bernoulli NLL'
require, binding, _json, _history_snapshot = compact.require, compact.binding, compact._json, compact._history_snapshot


def loss_terms(logits, targets, *, coefficient=COEFFICIENT):
    """Return (composite, categorical, binary) means over canonical positions.

    The zero branch exactly follows the historical unweighted expression.
    """
    require(type(coefficient) in (int, float) and coefficient in (0, 1),
            'Coefficient must be exactly zero (parity probe) or one')
    require(logits.dtype == targets.dtype == torch.float32
            and logits.device.type == targets.device.type == 'cpu'
            and logits.ndim == 2 and logits.shape[1] == 3 and targets.shape == logits.shape
            and len(logits) > 0 and bool(torch.isfinite(logits).all())
            and bool(torch.isfinite(targets).all()) and bool((targets >= 0).all())
            and bool(torch.allclose(targets.sum(1), torch.ones(len(logits)), rtol=0, atol=1e-6)),
            'Invalid loss arrays')
    logp = logits.log_softmax(-1)
    categorical = -(targets * logp).sum(1).mean()
    if coefficient == 0:
        return categorical, categorical, categorical.new_zeros(())
    # This remains stable when p0 rounds to one in float32 softmax.
    log_not_p0 = torch.logsumexp(logp[:, 1:], dim=-1)
    q0 = targets[:, 0]
    binary = -(q0 * logp[:, 0] + (1 - q0) * log_not_p0).mean()
    return categorical + binary, categorical, binary


def prepare(bundle, fitRows):
    return compact.prepare(bundle, FAMILY, fitRows)


def initialize(seed):
    require(seed in SEEDS and type(seed) is int, 'Unknown fixed seed')
    return seeded.initialize(29, seed)


def _checked(data):
    require(data.get('family') == FAMILY and data['values'].shape[1] == 29,
            'Expected 29-dimensional compact features')
    compact._indices(data, data['fit'])
    require(data['transform']['fitRows'] == data['fit'], 'Transform was not fitted on fitting rows')


def _row_binding(data, rows):
    """Bind prepared features and canonical labels used by this training phase."""
    digest = hashlib.sha256()
    for index in rows:
        row = data['cohort']['rows'][index]
        digest.update(json.dumps((index, data['positions'][index], row['targetId'],
                                  row['targetPhone'], row['raterCounts']),
                                 separators=(',', ':')).encode())
        digest.update(data['values'][data['positions'][index]].tobytes())
    return digest.hexdigest()


def _reserved(data, selectionRows, seed, epochs, pilot=False):
    return dict(objective=OBJECTIVE, binaryCoefficient=COEFFICIENT, seed=seed,
                recipe=seeded.recipe(seed), transformRecipe=compact.TRANSFORM_RECIPE,
                family=FAMILY, fitRows=data['fit'], selectionRows=list(selectionRows),
                fitDataSha256=_row_binding(data, data['fit']),
                selectionDataSha256=_row_binding(data, selectionRows),
                priorState=data['priors'], featureWidth=29,
                phase='pilot' if pilot else ('inner' if epochs is None else 'outer-refit'), fixedEpochs=epochs,
                selectionObjective='equal-position five-vote NLL' if epochs is None else None,
                authorTestRead=False, encoderInferencePerformed=False,
                clinicalUseEligible=False, learnerFeedbackEligible=False, outerPredictionsRead=False)


def train(data, selectionRows, output, config, *, seed, epochs=None, pilot=False):
    """Fit the fixed objective; select only by ordinary five-vote NLL."""
    require(seed in SEEDS and type(seed) is int, 'Unknown fixed seed')
    settings = seeded.recipe(seed)
    _checked(data)
    compact._indices(data, selectionRows, empty=epochs is not None)
    require(not set(data['fit']) & set(selectionRows), 'Selection rows overlap fitting rows')
    require(type(pilot) is bool, 'Pilot flag must be boolean')
    if pilot:
        require(epochs == 10 and type(epochs) is int and not selectionRows,
                'Pilot requires exactly ten fitting epochs and no selection rows')
    elif epochs is None:
        require(bool(selectionRows), 'Inner training requires selection rows')
    else:
        require(type(epochs) is int and 1 <= epochs <= settings['maximumEpochs'] and not selectionRows,
                'Refit requires 1..100 fixed epochs and no selection rows')
    output = Path(output)
    require(not output.exists(), 'Training requires a fresh output directory')
    reserved = _reserved(data, selectionRows, seed, epochs, pilot)
    require(isinstance(config, dict) and all(k not in config or config[k] == v for k, v in reserved.items()),
            'Caller configuration conflicts with fixed training recipe')
    model, generator = initialize(seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings['lr'], weight_decay=settings['weightDecay'])
    output.mkdir(parents=True, mode=0o700)
    with (output/'transform.pt').open('xb') as stream:
        torch.save(data['transform'], stream)
    transform_pin = binding(output/'transform.pt')
    require('transform' not in config or config['transform'] == transform_pin,
            'Caller transform binding differs')
    config = {**config, **reserved, 'transform': transform_pin}
    _json(output/'config.json', config)
    config_sha = binding(output/'config.json')['sha256']
    _json(output/'prior.json', data['priors'])

    def save(name, epoch, best_epoch, best_loss):
        compact._save(output/name, model, optimizer, data, generator, config_sha,
                      epoch, best_epoch, best_loss, transform_pin['sha256'])

    best_loss, best_epoch, history, total_updates = None, 0, [], 0
    save('initial.pt', 0, 0, None)
    for epoch in range(1, (settings['maximumEpochs'] if epochs is None else epochs) + 1):
        model.train()
        order = generator.permutation(data['fit']).tolist()
        sums = [0., 0., 0.]
        updates = 0
        for offset in range(0, len(order), settings['batchSize']):
            indices = order[offset:offset + settings['batchSize']]
            values, phones, mask, targets = batch(data, indices, 'cpu')
            optimizer.zero_grad(set_to_none=True)
            logits = model(values, mask, phones, mask)[:, 0]
            terms = loss_terms(logits, targets)
            require(all(bool(torch.isfinite(term)) for term in terms), 'Nonfinite training loss')
            terms[0].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), settings['clipNorm'], error_if_nonfinite=True)
            optimizer.step()
            for i, term in enumerate(terms):
                sums[i] += float(term.detach()) * len(indices)
            updates += 1
        total_updates += updates
        row = dict(epoch=epoch, trainLoss=sums[0]/len(order), trainCategoricalNLL=sums[1]/len(order),
                   trainRating0BinaryNLL=sums[2]/len(order), updates=updates, totalUpdates=total_updates,
                   orderSha256=hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest())
        if epochs is None:
            selection = compact.predict(model, data, selectionRows)
            row['selection'] = selection
            if best_loss is None or selection['NLL'] < best_loss - settings['minimumImprovement']:
                best_loss, best_epoch = selection['NLL'], epoch
                save('best.pt', epoch, best_epoch, best_loss)
        elif not pilot:
            best_epoch = epoch
        history.append(row)
        _history_snapshot(output/'history.json', history)
        save('last.pt', epoch, best_epoch, best_loss)
        if epochs is None and epoch - best_epoch >= settings['patience']:
            break
    if pilot:
        require(replay(output, data, data['fit'], seed=seed, checkpoint='last.pt')
                == compact.predict(model, data, data['fit']), 'Pilot last checkpoint does not replay exactly')
    elif epochs is not None:
        save('best.pt', epoch, epoch, None)
    else:
        selected = history[best_epoch - 1]['selection']
        _json(output/'selection.json', selected)
        require(replay(output, data, selectionRows, seed=seed) == selected,
                'Selected checkpoint does not replay exactly')
    summary = dict(complete=True, phase=config['phase'], mode=config['phase'], objective=OBJECTIVE,
                   seed=seed, fitRows=data['fit'], selectionRows=list(selectionRows), epochsRun=epoch,
                   bestEpoch=best_epoch, bestLoss=best_loss, totalUpdates=total_updates,
                   exactSelectionReplay=epochs is None, exactPilotReplay=pilot, configSha256=config_sha,
                   artifacts={name: binding(output/name) for name in
                              (('config.json', 'transform.pt', 'prior.json', 'initial.pt', 'last.pt', 'history.json')
                               if pilot else ('config.json', 'transform.pt', 'prior.json', 'initial.pt', 'best.pt', 'last.pt', 'history.json'))})
    if epochs is None:
        summary['artifacts']['selection.json'] = binding(output/'selection.json')
    _json(output/'report.json', summary)
    return {**summary, 'report': binding(output/'report.json')}


def replay(directory, data, indices, *, seed, checkpoint='best.pt'):
    """Verify source bindings and replay a saved seeded compact state."""
    require(checkpoint in ('best.pt', 'last.pt', 'initial.pt'), 'Unknown checkpoint')
    require(seed in SEEDS and type(seed) is int, 'Unknown fixed seed')
    _checked(data)
    compact._indices(data, indices)
    directory = Path(directory)
    config = json.loads((directory/'config.json').read_text())
    expected = _reserved(data, config.get('selectionRows', []), seed, config.get('fixedEpochs'),
                         config.get('phase') == 'pilot')
    require(config.get('phase') in ('inner', 'outer-refit', 'pilot')
            and config.get('phase') == expected['phase']
            and all(config.get(k) == v for k, v in expected.items()),
            'Replay training configuration differs')
    transform_pin = binding(directory/'transform.pt')
    require(config.get('transform') == transform_pin, 'Replay transform binding differs')
    saved_transform = torch.load(directory/'transform.pt', map_location='cpu', weights_only=True)
    require(compact.same_transform(saved_transform, data['transform']), 'Replay fit-only PCA state differs')
    state = torch.load(directory/checkpoint, map_location='cpu', weights_only=True)
    require(state.get('transformSha256') == transform_pin['sha256']
            and state.get('configSha256') == binding(directory/'config.json')['sha256']
            and torch.equal(state['mean'], data['mean']) and torch.equal(state['std'], data['std'])
            and state.get('priorState') == data['priors'], 'Replay normalization/config state differs')
    model, _ = initialize(seed)
    model.load_state_dict(state['model'], strict=True)
    value = compact.predict(model, data, indices)
    if checkpoint == 'best.pt' and config['phase'] == 'inner' and indices == config['selectionRows']:
        selected = json.loads((directory/'selection.json').read_text())
        require(state['epoch'] == state['bestEpoch'] and state['bestLoss'] == value['NLL']
                and value == selected, 'Selected state or predictions differ')
    return value


def validate_run(directory, cohort, *, seed, phase, fit_rows, selection_rows):
    """Independently audit a completed inner, refit, or fit-only pilot run."""
    from rare0_proper_loss.validation import run
    return run(directory, cohort, seed=seed, phase=phase,
               fit_rows=fit_rows, selection_rows=selection_rows)
