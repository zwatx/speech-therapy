"""Seed-aware saved-state and phase validation; no fitting or head inference."""
import hashlib
import json
import math
import random

import numpy as np
import torch
import torch.nn.functional as F

from lexical_expanded_heads import study as prior
from lexical_seed_replication import core

read, require = prior.read, prior.require
JOB_FIELDS = ('id', 'baseJobId', 'seed', 'objective', 'family', 'regime', 'speakerFold', 'wordGroup')


def run(job, record, plan_pin, phase, cohort):
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
    weight_state = core.fitting_weights(cohort, fit, job['objective'])
    priors = prior.scalar.core.fit_priors([cohort['rows'][i] for i in fit])
    require(cfg['experiment'] == 'lexical-seed-replication-v1' and cfg['phase'] == phase
            and cfg['plan'] == plan_pin and cfg['job'] == {k: job[k] for k in JOB_FIELDS}
            and cfg['seed'] == job['seed'] and cfg['objective'] == job['objective']
            and cfg['recipe'] == core.recipe(job['seed']) and cfg['family'] == job['family']
            and cfg['fitRows'] == fit and cfg['selectionRows'] == selection and cfg['featureWidth'] == width
            and cfg['priorState'] == priors == read(artifacts['prior.json'])
            and cfg['addedValidationRowsNotUsedForSelection'] == job['addedValidationRows'], 'Run configuration differs')
    require(all(cfg[k] is v for k, v in prior.FLAGS.items()) and cfg['outerInferencePerformed'] is False,
            'Run scope flags differ')
    require(cfg['weightRecipe'] == weight_state['recipe'] and cfg['weights'] == artifacts['weights.json']
            and read(artifacts['weights.json']) == weight_state, 'Objective-specific fitting weights differ')
    if width == 29:
        require(cfg['transform'] == artifacts['transform.pt']
                and cfg['transformRecipe'] == prior.compact.core.TRANSFORM_RECIPE, 'Transform lineage differs')
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
    model, generator = core.initialize(width, job['seed'])
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
