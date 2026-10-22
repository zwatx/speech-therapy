"""Fresh fixed PCA16/scalar heads; every transform uses only fitting features."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random

import numpy as np
import torch

from multiphone_child_train import fit_priors
from multiphone_data import TARGETS
from multiphone_local_head import batch
from multiphone_models import MeanPoolPhoneRatingHead

RECIPE = dict(seed=7, hidden=128, dropout=.1, lr=.0003, weightDecay=.01,
              batchSize=64, clipNorm=5., threads=2, maximumEpochs=100,
              patience=15, minimumImprovement=1e-7, device='cpu', numPhones=24)


TRANSFORM_RECIPE = dict(components=16, input='raw 1024-dimensional target features',
                        centering='fit-row float64 mean', covariance='population Xc.T@Xc/n',
                        dtype='float64', eigensolver='torch.linalg.eigh', order='descending',
                        sign='largest absolute loading coordinate positive; first index breaks ties',
                        whitening=False, rankTolerance=1e-12,
                        rankRule='sixteenth eigenvalue > 1e-12 * max(1, largest eigenvalue)',
                        projectionDtype='float32', scalarColumns=13)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _json(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def _history_snapshot(path, history):
    temporary = Path(path).with_suffix('.writing')
    _json(temporary, history)
    temporary.replace(path)


def _indices(data, indices, *, empty=False):
    require(isinstance(indices, list) and (empty or bool(indices))
            and all(type(i) is int and 0 <= i < len(data['cohort']['rows']) for i in indices)
            and len(indices) == len(set(indices)), 'Expected unique valid row indices')
    require(all(i in data['positions'] for i in indices), 'Missing feature row')
    for i in indices:
        row = data['cohort']['rows'][i]
        c = row['raterCounts']
        require(type(row['targetId']) is int and 0 <= row['targetId'] < 23
                and row['targetPhone'] == TARGETS[row['targetId']]
                and len(c) == 3 and all(type(v) is int and v >= 0 for v in c) and sum(c) == 5,
                'Invalid canonical target or five-vote label')


def prepare(bundle, family, fitRows):
    """Fit the fixed 16-component covariance PCA and normalization on fit rows."""
    require(family == 'pca16-scalars', 'Unknown compact feature family')
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    scalars, target = np.asarray(bundle['scalars']), np.asarray(bundle['target'])
    require(scalars.ndim == 2 and scalars.shape[1] == 13 and scalars.dtype == np.float32
            and np.isfinite(scalars).all(), 'Invalid scalar features')
    require(target.shape == (len(scalars), 1024) and target.dtype == np.float32
            and np.isfinite(target).all(), 'Invalid target features')
    positions = dict(bundle['positions'])
    require(all(type(k) is int and type(v) is int and 0 <= v < len(scalars) for k, v in positions.items())
            and len(set(positions.values())) == len(positions), 'Invalid feature positions')
    data = dict(cohort=bundle['cohort'], positions=positions, family=family, fit=list(fitRows))
    _indices(data, data['fit'])
    x = torch.tensor(target[[positions[i] for i in data['fit']]], dtype=torch.float64)
    center = x.mean(0)
    centered = x - center
    covariance = centered.T @ centered / len(x)
    eigenvalues, vectors = torch.linalg.eigh(covariance)
    eigenvalues, vectors = eigenvalues.flip(0), vectors.flip(1)
    require(bool(torch.isfinite(eigenvalues).all()) and bool(torch.isfinite(vectors).all())
            and eigenvalues[15].item() > 1e-12 * max(1., eigenvalues[0].item()),
            'PCA has fewer than 16 numerically supported components')
    basis = vectors[:, :16].clone()
    for column in range(16):
        anchor = int(basis[:, column].abs().argmax())
        if basis[anchor, column] < 0:
            basis[:, column].neg_()
    fraction = float(eigenvalues[:16].sum() / eigenvalues.sum())
    transform = dict(center=center, basis=basis, eigenvalues=eigenvalues, rank=16,
                     fitRows=list(data['fit']), varianceFraction=fraction)
    projected = ((torch.tensor(target, dtype=torch.float64) - center) @ basis).numpy().astype(np.float32)
    values = np.concatenate((projected, scalars), axis=1)
    require(np.isfinite(values).all(), 'Nonfinite projected features')
    fit_values = values[[positions[i] for i in data['fit']]].astype(np.float64)
    mean, std = fit_values.mean(0), fit_values.std(0)
    std = np.where(std < 1e-6, 1., std)
    require(np.isfinite(mean).all() and np.isfinite(std).all(), 'Nonfinite fit moments')
    data.update(values=values, transform=transform,
                mean=torch.tensor(mean, dtype=torch.float32), std=torch.tensor(std, dtype=torch.float32),
                priors=fit_priors([data['cohort']['rows'][i] for i in data['fit']]))
    return data


def same_transform(saved, expected):
    """Exact state comparison, including fitted row membership and PCA metadata."""
    return (saved.keys() == expected.keys()
            and all(saved[k].dtype == expected[k].dtype == torch.float64
                    and torch.equal(saved[k], expected[k]) for k in ('center', 'basis', 'eigenvalues'))
            and all(saved[k] == expected[k] for k in ('rank', 'fitRows', 'varianceFraction')))


def initialize(width):
    """Reset all training random streams and create a fresh fixed head."""
    require(width == 29, 'Expected 29 compact/scalar features')
    torch.set_num_threads(RECIPE['threads'])
    random.seed(RECIPE['seed'])
    np.random.seed(RECIPE['seed'])
    torch.manual_seed(RECIPE['seed'])
    torch.use_deterministic_algorithms(True)
    model = MeanPoolPhoneRatingHead(feature_dim=width, num_phones=24, hidden_dim=128, dropout=.1).cpu()
    return model, np.random.default_rng(RECIPE['seed'])


def stable_outputs(logits, counts):
    """Canonical float64 probabilities/logs plus raw float32 softmax, without floors."""
    require(logits.dtype == torch.float32 and logits.ndim == 2 and logits.shape[1] == 3
            and torch.isfinite(logits).all(), 'Invalid float32 logits')
    counts = np.asarray(counts, dtype=np.float64)
    require(counts.shape == tuple(logits.shape) and len(counts) and np.isfinite(counts).all()
            and (counts >= 0).all() and (counts == np.floor(counts)).all()
            and (counts.sum(1) == 5).all(), 'Invalid five-vote counts')
    raw = logits.softmax(-1).detach().cpu().numpy()
    logs = logits.double().log_softmax(-1).detach().cpu().numpy()
    p = np.exp(logs)
    require(np.isfinite(logs).all(), 'Nonfinite log probabilities')
    loss = float(-(counts * logs.astype(np.float64)).sum() / (5 * len(counts)))
    return p, logs, raw, loss


@torch.no_grad()
def predict(model, data, indices):
    """CPU prediction only; callers decide which partitions may be opened."""
    _indices(data, indices)
    model.eval()
    logits = []
    for offset in range(0, len(indices), 64):
        values, phones, mask, _ = batch(data, indices[offset:offset+64], 'cpu')
        logits.append(model(values, mask, phones, mask)[:, 0])
    counts = [data['cohort']['rows'][i]['raterCounts'] for i in indices]
    p, logs, raw, loss = stable_outputs(torch.cat(logits), counts)
    return dict(rowIndices=list(indices), probabilities=p.tolist(), rawProbabilities=raw.tolist(),
                logProbabilities=logs.tolist(), NLL=loss)


def _rng(generator):
    numpy_state = np.random.get_state()
    return dict(python=random.getstate(), torch=torch.get_rng_state(),
                numpyGlobal=dict(algorithm=numpy_state[0], keys=numpy_state[1].tolist(),
                                 position=numpy_state[2], hasGaussian=numpy_state[3], cachedGaussian=numpy_state[4]),
                numpyPermutation=generator.bit_generator.state)


def _save(path, model, optimizer, data, generator, config_sha, epoch, best_epoch, best_loss, transform_sha):
    payload = dict(model=model.state_dict(), optimizer=optimizer.state_dict(),
                   mean=data['mean'].clone(), std=data['std'].clone(), priorState=data['priors'],
                   epoch=epoch, bestEpoch=best_epoch, bestLoss=best_loss, configSha256=config_sha,
                   rng=_rng(generator), transformSha256=transform_sha)
    temporary = Path(path).with_suffix('.writing')
    with temporary.open('xb') as stream:
        torch.save(payload, stream)
    temporary.replace(path)


def train(data, selectionRows, output, config, epochs=None):
    """Fresh initialization; inner selection or fixed-epoch refit, never both."""
    _indices(data, data['fit'])
    _indices(data, selectionRows, empty=epochs is not None)
    require(not set(data['fit']) & set(selectionRows), 'Selection rows overlap fitting rows')
    if epochs is not None:
        require(type(epochs) is int and 1 <= epochs <= 100 and not selectionRows,
                'Refit requires 1..100 fixed epochs and no selection rows')
    else:
        require(bool(selectionRows), 'Inner training requires selection rows')
    output = Path(output)
    require(not output.exists(), 'Training requires a fresh output directory')
    model, generator = initialize(data['values'].shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0003, weight_decay=.01)
    reserved = dict(recipe=RECIPE, transformRecipe=TRANSFORM_RECIPE, family=data['family'], fitRows=data['fit'], selectionRows=list(selectionRows),
                    priorState=data['priors'], featureWidth=data['values'].shape[1],
                    phase='inner' if epochs is None else 'outer-refit', fixedEpochs=epochs,
                    selectionObjective='equal-position five-vote NLL' if epochs is None else None,
                    authorTestRead=False, encoderInferencePerformed=False,
                    clinicalUseEligible=False, learnerFeedbackEligible=False, outerPredictionsRead=False)
    require(isinstance(config, dict) and all(k not in config or config[k] == v for k, v in reserved.items()),
            'Caller configuration conflicts with fixed training recipe')
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
    best_loss, best_epoch, history = None, 0, []
    _save(output/'initial.pt', model, optimizer, data, generator, config_sha, 0, 0, None, transform_pin['sha256'])
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
            loss = -(targets * logits.log_softmax(-1)).sum(1).mean()
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
            selection = predict(model, data, selectionRows)
            row['selection'] = selection
            if best_loss is None or selection['NLL'] < best_loss - 1e-7:
                best_loss, best_epoch = selection['NLL'], epoch
                _save(output/'best.pt', model, optimizer, data, generator, config_sha, epoch, best_epoch, best_loss, transform_pin['sha256'])
        else:
            best_epoch = epoch
        history.append(row)
        _history_snapshot(output/'history.json', history)
        _save(output/'last.pt', model, optimizer, data, generator, config_sha, epoch, best_epoch, best_loss, transform_pin['sha256'])
        if epochs is None and epoch - best_epoch >= 15:
            break
    if epochs is not None:
        _save(output/'best.pt', model, optimizer, data, generator, config_sha, epoch, epoch, None, transform_pin['sha256'])
    if epochs is None:
        selected = history[best_epoch-1]['selection']
        _json(output/'selection.json', selected)
        require(replay(output, data, selectionRows) == selected, 'Selected checkpoint does not replay exactly')
    summary = dict(complete=True, phase=config['phase'], mode=config['phase'],
                   fitRows=data['fit'], selectionRows=list(selectionRows), epochsRun=epoch, bestEpoch=best_epoch,
                   bestLoss=best_loss, totalUpdates=total_updates,
                   exactSelectionReplay=epochs is None, configSha256=config_sha,
                   artifacts={name: binding(output/name) for name in
                              ('config.json','transform.pt','prior.json','initial.pt','best.pt','last.pt','history.json')})
    if epochs is None:
        summary['artifacts']['selection.json'] = binding(output/'selection.json')
    _json(output/'report.json', summary)
    return {**summary, 'report': binding(output/'report.json')}


def replay(directory, data, indices, checkpoint='best.pt'):
    """Load a locally trained state after exact config/moment/fit checks."""
    require(checkpoint in ('best.pt', 'last.pt', 'initial.pt'), 'Unknown checkpoint')
    directory = Path(directory)
    config = json.loads((directory/'config.json').read_text())
    require(config['recipe'] == RECIPE and config['transformRecipe'] == TRANSFORM_RECIPE
            and config['family'] == data['family']
            and config['featureWidth'] == data['values'].shape[1] and config['fitRows'] == data['fit']
            and config['priorState'] == data['priors'], 'Replay training configuration differs')
    transform_pin = binding(directory/'transform.pt')
    require(config['transform'] == transform_pin, 'Replay transform binding differs')
    saved_transform = torch.load(directory/'transform.pt', map_location='cpu', weights_only=True)
    require(same_transform(saved_transform, data['transform']), 'Replay fit-only PCA state differs')
    state = torch.load(directory/checkpoint, map_location='cpu', weights_only=True)
    require(state['transformSha256'] == transform_pin['sha256']
            and state['configSha256'] == binding(directory/'config.json')['sha256']
            and torch.equal(state['mean'], data['mean']) and torch.equal(state['std'], data['std'])
            and state['priorState'] == data['priors'], 'Replay normalization/config state differs')
    model, _ = initialize(data['values'].shape[1])
    model.load_state_dict(state['model'], strict=True)
    value = predict(model, data, indices)
    if checkpoint == 'best.pt' and config['phase'] == 'inner' and indices == config['selectionRows']:
        selected = json.loads((directory/'selection.json').read_text())
        require(state['epoch'] == state['bestEpoch'] and state['bestLoss'] == value['NLL']
                and value == selected, 'Selected state or predictions differ')
    return value
