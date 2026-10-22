"""Independent saved-state audit for the fixed coefficient-one trainer."""
import hashlib
import json
import math
from pathlib import Path
import random

import numpy as np
import torch
import torch.nn.functional as F

from lexical_expanded_heads import evaluation
from multiphone_child_train import fit_priors
from rare0_proper_loss import core

require = core.require


def _read(path):
    return json.loads(Path(path).read_text())


def run(directory, cohort, *, seed, phase, fit_rows, selection_rows):
    """Validate every epoch and saved checkpoint without fitting or inference."""
    require(phase in ('inner', 'outer-refit', 'pilot') and type(seed) is int and seed in core.SEEDS,
            'Unknown run phase or seed')
    require(isinstance(fit_rows, list) and fit_rows and isinstance(selection_rows, list)
            and len(fit_rows) == len(set(fit_rows)) and len(selection_rows) == len(set(selection_rows))
            and not set(fit_rows) & set(selection_rows)
            and all(type(i) is int and 0 <= i < len(cohort['rows']) for i in fit_rows + selection_rows)
            and (bool(selection_rows) is (phase == 'inner')), 'Invalid run rows or selection phase')
    directory = Path(directory)
    names = {'config.json', 'transform.pt', 'prior.json', 'initial.pt', 'last.pt', 'history.json'}
    if phase != 'pilot':
        names.add('best.pt')
    if phase == 'inner':
        names.add('selection.json')
    require(all((directory/name).is_file() for name in names) and (directory/'report.json').is_file(),
            'Missing required run artifact')
    require(phase != 'pilot' or not any((directory/name).exists() for name in ('best.pt', 'selection.json')),
            'Pilot has a selected artifact')
    cfg, report, history = (_read(directory/name) for name in ('config.json', 'report.json', 'history.json'))
    artifacts = {name: core.binding(directory/name) for name in names}
    require(report.get('artifacts') == artifacts and report.get('configSha256') == artifacts['config.json']['sha256'],
            'Run report artifact binding differs')
    priors = fit_priors([cohort['rows'][i] for i in fit_rows])
    require(cfg.get('objective') == core.OBJECTIVE and cfg.get('binaryCoefficient') == core.COEFFICIENT
            and cfg.get('seed') == seed and cfg.get('recipe') == core.seeded.recipe(seed)
            and cfg.get('transformRecipe') == core.compact.TRANSFORM_RECIPE
            and cfg.get('family') == core.FAMILY and cfg.get('featureWidth') == 29
            and cfg.get('phase') == phase and cfg.get('fitRows') == fit_rows
            and cfg.get('selectionRows') == selection_rows and cfg.get('priorState') == priors
            and cfg.get('transform') == artifacts['transform.pt']
            and cfg.get('selectionObjective') == ('equal-position five-vote NLL' if phase == 'inner' else None)
            and all(cfg.get(k) is False for k in ('authorTestRead', 'encoderInferencePerformed',
                         'clinicalUseEligible', 'learnerFeedbackEligible', 'outerPredictionsRead'))
            and all(isinstance(cfg.get(k), str) and len(cfg[k]) == 64
                    for k in ('fitDataSha256', 'selectionDataSha256'))
            and _read(directory/'prior.json') == priors, 'Training configuration, objective, or priors differ')
    transform = torch.load(directory/'transform.pt', map_location='cpu', weights_only=True)
    require(transform.get('fitRows') == fit_rows and transform.get('rank') == 16,
            'PCA fitting membership differs')
    require(report.get('complete') is True and report.get('phase') == report.get('mode') == phase
            and report.get('objective') == core.OBJECTIVE and report.get('seed') == seed
            and report.get('fitRows') == fit_rows and report.get('selectionRows') == selection_rows
            and report.get('exactSelectionReplay') is (phase == 'inner')
            and report.get('exactPilotReplay') is (phase == 'pilot'), 'Run report identity differs')
    require(isinstance(history, list) and 1 <= len(history) <= 100
            and report.get('epochsRun') == len(history), 'Incomplete epoch history')
    if phase == 'pilot':
        require(cfg.get('fixedEpochs') == len(history) == 10, 'Pilot duration differs')
    elif phase == 'outer-refit':
        require(type(cfg.get('fixedEpochs')) is int and cfg['fixedEpochs'] == len(history),
                'Refit duration differs')
    else:
        require(cfg.get('fixedEpochs') is None, 'Inner duration differs')
    model, generator = core.initialize(seed)
    fresh = model.state_dict()
    initial_rng = torch.get_rng_state().clone()
    states = {0: (0, None, generator.bit_generator.state, initial_rng)}
    updates = math.ceil(len(fit_rows) / 64)
    best_epoch, best_loss = 0, None
    for epoch, entry in enumerate(history, 1):
        order = generator.permutation(fit_rows).tolist()
        order_sha = hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest()
        losses = [entry.get(k) for k in ('trainLoss', 'trainCategoricalNLL', 'trainRating0BinaryNLL')]
        require(entry.get('epoch') == epoch and entry.get('orderSha256') == order_sha
                and entry.get('updates') == updates and entry.get('totalUpdates') == epoch * updates
                and all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in losses)
                and abs(losses[0] - losses[1] - losses[2]) < 1e-5,
                'Training update, order, or objective-term history differs')
        for start in range(0, len(fit_rows), 64):
            F.dropout(torch.ones(min(64, len(fit_rows) - start), 1, 128), p=.1, training=True)
        if phase == 'inner':
            prediction = entry.get('selection')
            require(isinstance(prediction, dict), 'Missing inner selection')
            evaluation.checked_prediction(prediction, selection_rows,
                                          [cohort['rows'][i] for i in selection_rows])
            counts = np.asarray([cohort['rows'][i]['raterCounts'] for i in selection_rows])
            loss = float(-(counts * np.asarray(prediction['logProbabilities'])).sum() / (5 * len(selection_rows)))
            require(prediction['NLL'] == loss, 'Selection NLL differs from votes and stable logs')
            if best_loss is None or loss < best_loss - 1e-7:
                best_epoch, best_loss = epoch, loss
            require(epoch == len(history) or epoch - best_epoch < 15,
                    'Training continued past patience')
        else:
            require('selection' not in entry, 'Fit-only run used selection')
            if phase == 'outer-refit':
                best_epoch = epoch
        states[epoch] = best_epoch, best_loss, generator.bit_generator.state, torch.get_rng_state().clone()
    require(report.get('totalUpdates') == len(history) * updates
            and report.get('bestEpoch') == best_epoch and report.get('bestLoss') == best_loss,
            'Final selected epoch or update count differs')
    if phase == 'inner':
        require(len(history) == 100 or len(history) - best_epoch == 15,
                'Inner stopping differs')
        require(_read(directory/'selection.json') == history[best_epoch - 1]['selection'],
                'Selected prediction differs from history')
    expected_numpy = np.random.RandomState(seed).get_state()
    numpy_state = dict(algorithm=expected_numpy[0], keys=expected_numpy[1].tolist(),
                       position=expected_numpy[2], hasGaussian=expected_numpy[3],
                       cachedGaussian=expected_numpy[4])
    checkpoints = [('initial.pt', 0), ('last.pt', len(history))]
    if phase != 'pilot':
        checkpoints.append(('best.pt', best_epoch))
    initial = torch.load(directory/'initial.pt', map_location='cpu', weights_only=True)
    for name, epoch in checkpoints:
        saved = torch.load(directory/name, map_location='cpu', weights_only=True)
        selected_epoch, selected_loss, permutation_rng, torch_rng = states[epoch]
        require(saved.get('epoch') == epoch and saved.get('bestEpoch') == selected_epoch
                and saved.get('bestLoss') == selected_loss
                and saved.get('configSha256') == artifacts['config.json']['sha256']
                and saved.get('transformSha256') == artifacts['transform.pt']['sha256']
                and saved.get('priorState') == priors, 'Checkpoint epoch or lineage differs')
        require(saved['mean'].shape == saved['std'].shape == (29,)
                and saved['mean'].dtype == saved['std'].dtype == torch.float32
                and bool(torch.isfinite(saved['mean']).all()) and bool(torch.isfinite(saved['std']).all())
                and bool((saved['std'] > 0).all())
                and torch.equal(saved['mean'], initial['mean'])
                and torch.equal(saved['std'], initial['std']), 'Invalid checkpoint normalization')
        require(list(saved['model']) == list(fresh), 'Checkpoint parameter keys differ')
        for key, value in saved['model'].items():
            require(value.shape == fresh[key].shape and value.dtype == fresh[key].dtype
                    and bool(torch.isfinite(value).all()), 'Invalid checkpoint parameter')
            if epoch == 0:
                require(torch.equal(value, fresh[key]), 'Fresh initialization differs')
        rng = saved['rng']
        require(rng['python'] == random.Random(seed).getstate()
                and rng['numpyGlobal'] == numpy_state
                and rng['numpyPermutation'] == permutation_rng
                and torch.equal(rng['torch'], torch_rng), 'Checkpoint RNG differs')
        optimizer = saved['optimizer']
        groups = optimizer['param_groups']
        require(len(groups) == 1 and groups[0]['params'] == list(range(len(fresh)))
                and groups[0]['lr'] == .0003 and groups[0]['weight_decay'] == .01
                and groups[0]['betas'] == (.9, .999) and groups[0]['eps'] == 1e-8
                and groups[0]['amsgrad'] is False and groups[0]['maximize'] is False,
                'Checkpoint optimizer recipe differs')
        moments = optimizer['state']
        require(set(moments) == (set() if epoch == 0 else set(range(len(fresh)))),
                'Checkpoint optimizer coverage differs')
        for index, value in moments.items():
            require(set(value) == {'step', 'exp_avg', 'exp_avg_sq'}
                    and value['step'].numel() == 1 and value['step'].item() == epoch * updates,
                    'Optimizer update count differs')
            for key in ('exp_avg', 'exp_avg_sq'):
                require(value[key].shape == list(fresh.values())[index].shape
                        and value[key].dtype == torch.float32 and bool(torch.isfinite(value[key]).all()),
                        'Invalid optimizer moment')
            require(bool((value['exp_avg_sq'] >= 0).all()), 'Negative optimizer second moment')
    return report
