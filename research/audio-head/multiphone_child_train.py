"""Child-selected, frozen-encoder rating probes on fixed inner speaker splits.

These models predict subjective three-class rater distributions. Global class
weight correction is an objective correction, not evidence of calibration or
clinical pronunciation judgment. No author-test or outer-holdout inference runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time

import numpy as np
import torch

from encoders import Wav2VecEncoder, WavLMEncoder
from multiphone_cache import atomic_json, digest
from multiphone_data import TARGETS
from multiphone_models import MeanPoolPhoneRatingHead
from multiphone_train import StudyData, distribution_metrics, save_checkpoint, valid_counts, verify_partitions
from multiphone_verify import discrimination, target_discrimination

HERE = Path(__file__).resolve().parent
RECIPE = HERE/'experiments/multiphone-child-heads-v1.json'
REGIMES = ('child-only', 'balanced-all-age')
IDENTITIES = {'wav2vec2-base': Wav2VecEncoder.identity, 'wavlm-base-plus': WavLMEncoder.identity}
SOURCES = ('multiphone_child_train.py', 'multiphone_train.py', 'multiphone_models.py',
           'multiphone_cache.py', 'multiphone_verify.py', 'multiphone_data.py', 'encoders.py')


def is_child(row: dict) -> bool:
    return 6 <= row['age'] <= 12


def select_rows(cohort: dict, splits: dict, fold_index: int, regime: str):
    if regime not in REGIMES:
        raise ValueError('Unknown child-focused regime')
    canonical = hashlib.sha256(json.dumps(cohort, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if splits['cohortCanonicalSha256'] != canonical:
        raise ValueError('Speaker splits are not bound to this exact cohort')
    fold = splits['folds'][fold_index]
    verify_partitions(cohort, fold)
    fit = [index for index in fold['innerFitRows'] if regime != 'child-only' or is_child(cohort['rows'][index])]
    validation = fold['innerValidationRows']
    children = [index for index in validation if is_child(cohort['rows'][index])]
    if not fit or not children:
        raise ValueError('The regime requires fit rows and child inner-validation rows')
    for index in fit+validation:
        row = cohort['rows'][index]
        if (row['trainingEligible'] is not True or type(row['targetId']) is not int
                or not 0 <= row['targetId'] < 23 or row['targetPhone'] != TARGETS[row['targetId']]
                or not valid_counts(np.asarray([row['raterCounts']], dtype=float))):
            raise ValueError('Invalid eligible target or five-rater label')
    return fit, validation, children


def fit_class_weights(rows: list[dict], regime: str) -> dict:
    counts = np.asarray([row['raterCounts'] for row in rows], dtype=float)
    if not valid_counts(counts) or not len(rows) or regime not in REGIMES:
        raise ValueError('Invalid fit labels or regime')
    observed = counts.sum(0)
    prevalence = observed/observed.sum()
    if regime == 'balanced-all-age':
        if (observed == 0).any():
            raise ValueError('Class weighting requires observed fit ratings in every class; no pseudocounts are added')
        weights = 1/np.sqrt(prevalence)
        weights = np.minimum(weights, weights.min()*10)
        weights /= np.dot(prevalence, weights)
    else:
        weights = np.ones(3)
    return {'observedRaterCounts': observed.astype(int).tolist(), 'observedPrevalence': prevalence.tolist(),
            'weights': weights.tolist(), 'weightNormalization': 'fit-prevalence-weighted mean equals one',
            'maximumWeightRatio': 10., 'trainingPseudocounts': 0,
            'predictionCorrection': 'subtract log(class weight) from logits before unweighted softmax'}


def corrected_probabilities(logits: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
    if (weights.shape != (3,) or logits.shape[-1] != 3 or not torch.isfinite(weights).all()
            or not (weights > 0).all() or not torch.isfinite(logits).all()):
        raise ValueError('Finite logits and positive class weights are required')
    return (logits-weights.log()).softmax(-1)


def weighted_loss(logits: torch.Tensor, targets: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
    # Do not normalize each row's weighted target distribution. That would
    # change the objective and invalidate the global log-weight correction.
    return -(targets*weights*logits.log_softmax(-1)).sum(-1)


def fit_priors(rows: list[dict]) -> dict:
    result = {}
    for phone in TARGETS[:23]:
        counts = np.asarray([row['raterCounts'] for row in rows if row['targetPhone'] == phone], dtype=float)
        observed = counts.sum(0) if len(counts) else np.zeros(3)
        result[phone] = {'observedRaterCounts': observed.astype(int).tolist(),
                         'observedRows': len(counts), 'pseudocountPerClass': 1.,
                         'probabilities': ((observed+1)/(observed.sum()+3)).tolist()}
    return result


def score_slice(probabilities: np.ndarray, rows: list[dict]) -> dict | None:
    if not rows:
        return None
    counts = np.asarray([row['raterCounts'] for row in rows], dtype=float)
    phones = [row['targetPhone'] for row in rows]
    metrics = distribution_metrics(probabilities, counts)
    per_phone = {}
    for phone in sorted(set(phones)):
        mask = np.asarray([value == phone for value in phones])
        selected = [row for row, keep in zip(rows, mask, strict=True) if keep]
        per_phone[phone] = distribution_metrics(probabilities[mask], counts[mask])
        per_phone[phone].update(observedRaterCounts=counts[mask].sum(0).astype(int).tolist(),
                               speakers=len({row['speakerId'] for row in selected}))
    metrics.update(perTarget=per_phone,
                   macroTargetLogLoss=float(np.mean([entry['perRaterLogLoss'] for entry in per_phone.values()])),
                   macroTargetPhones=sorted(per_phone), observedRaterCounts=counts.sum(0).astype(int).tolist(),
                   speakers=len({row['speakerId'] for row in rows}),
                   discrimination=discrimination(probabilities, counts),
                   targetDiscrimination=target_discrimination(probabilities, counts, phones))
    return metrics


def score_predictions(probabilities: np.ndarray, rows: list[dict]) -> dict:
    result = {'allAges': score_slice(probabilities, rows)}
    for name, condition in [('ages6to12', is_child), ('ages13plus', lambda row: row['age'] >= 13)]:
        mask = np.asarray([condition(row) for row in rows])
        result[name] = score_slice(probabilities[mask], [row for row, keep in zip(rows, mask, strict=True) if keep])
    return result


@torch.no_grad()
def evaluate(model, data, selected_rows, mean, std, weights, device, batch_size):
    model.eval()
    clips = sorted({data.rows[index]['clipIndex'] for index in selected_rows})
    outputs = {}
    for offset in range(0, len(clips), batch_size):
        features, mask, phones, target_mask, _, indices = data.batch(
            clips[offset:offset+batch_size], set(selected_rows), mean, std, device)
        logits = model(features, mask, phones, target_mask)
        values = corrected_probabilities(logits, weights)[target_mask].cpu().numpy()
        outputs.update(zip(indices, values, strict=True))
    ordered = sorted(outputs)
    if set(ordered) != set(selected_rows):
        raise ValueError('Evaluation must cover every selected row exactly once')
    probabilities = np.asarray([outputs[index] for index in ordered], dtype=float)
    return score_predictions(probabilities, [data.rows[index] for index in ordered]), {
        'rowIndices': ordered, 'probabilities': probabilities.tolist(),
        'probabilityScale': 'unweighted after subtracting fit-derived log class weights'}


def setup(args):
    recipe = json.loads(RECIPE.read_text())
    required = {'hidden': 'hiddenWidth', 'dropout': 'dropout', 'weight_decay': 'weightDecay',
                'batch_size': 'batchSizeClips', 'epochs': 'maximumEpochs', 'patience': 'patienceEpochs'}
    if (args.regime not in recipe['regimes'] or args.encoder not in recipe['encoders']
            or args.fold not in recipe['folds'] or args.seed not in recipe['initializationSeeds']
            or args.lr not in recipe['learningRates']
            or any(getattr(args, name) != recipe[key] for name, key in required.items())
            or digest(args.cohort) != recipe['cohortSha256'] or digest(args.splits) != recipe['splitsSha256']):
        raise ValueError('Arguments or study inputs differ from the declared child-focused recipe')
    cohort, splits = json.loads(args.cohort.read_text()), json.loads(args.splits.read_text())
    fit_rows, validation_rows, child_rows = select_rows(cohort, splits, args.fold, args.regime)
    data = StudyData(cohort, args.cache, fit_rows+validation_rows)
    if (data.config['cohortSha256'] != digest(args.cohort)
            or data.config['encoder'] != IDENTITIES[args.encoder]):
        raise ValueError('Frozen encoder cache identity differs')
    fit_clips = sorted({data.rows[index]['clipIndex'] for index in fit_rows})
    mean, std = data.normalization(fit_clips)
    fit = [data.rows[index] for index in fit_rows]
    class_state = fit_class_weights(fit, args.regime)
    prior_state = fit_priors(fit)
    return data, fit_rows, validation_rows, child_rows, fit_clips, mean, std, class_state, prior_state


def source_guard(config):
    if (digest(RECIPE) != config['recipeSha256']
            or any(digest(HERE/name) != value for name, value in config['sourceSha256'].items())):
        raise ValueError('Child-probe recipe or implementation changed during the run')


def train(args) -> dict:
    if args.output.exists() or not args.output.resolve().is_relative_to((HERE/'outputs').resolve()):
        raise ValueError('Choose a fresh run directory inside ignored research outputs')
    if args.device == 'mps' and not torch.backends.mps.is_available():
        raise ValueError('MPS unavailable')
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    started = time.perf_counter()
    data, fit_rows, validation_rows, child_rows, fit_clips, mean, std, class_state, priors = setup(args)
    weights = torch.tensor(class_state['weights'], dtype=torch.float32, device=args.device)
    model = MeanPoolPhoneRatingHead(hidden_dim=args.hidden, dropout=args.dropout).to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    config = {name: str(value.resolve()) if isinstance(value, Path) else value
              for name, value in vars(args).items() if name != 'replay'}
    config.update({'recipeSha256': digest(RECIPE), 'cohortSha256': digest(args.cohort),
                   'splitsSha256': digest(args.splits), 'cacheIndexSha256': data.index_sha256,
                   'encoderIdentity': IDENTITIES[args.encoder], 'classWeightState': class_state, 'priorState': priors,
                   'fitRows': fit_rows, 'validationRows': validation_rows, 'childSelectionRows': child_rows,
                   'fitClips': fit_clips, 'fitSpeakers': len({data.rows[index]['speakerId'] for index in fit_rows}),
                   'childSelectionPhones': sorted({data.rows[index]['targetPhone'] for index in child_rows}),
                   'validationTargetsWithoutFitRows': sorted({data.rows[index]['targetPhone'] for index in validation_rows}
                                                               -{data.rows[index]['targetPhone'] for index in fit_rows}),
                   'sourceSha256': {name: digest(HERE/name) for name in SOURCES},
                   'selection': 'ages 6–12 inner-validation macro-target unweighted per-rater log loss',
                   'phase': 'inner', 'authorPartition': 'train', 'authorTestInferencePerformed': False,
                   'torch': str(torch.__version__), 'numpy': np.__version__,
                   'clinicalUseEligible': False, 'learnerFeedbackEligible': False})
    args.output.mkdir(parents=True)
    atomic_json(args.output/'config.json', config)
    prior_probabilities = np.asarray([priors[data.rows[index]['targetPhone']]['probabilities']
                                     for index in sorted(validation_rows)], dtype=float)
    prior_metrics = score_predictions(prior_probabilities, [data.rows[index] for index in sorted(validation_rows)])
    atomic_json(args.output/'prior.json', {'fit': priors, 'evaluation': prior_metrics,
        'rowIndices': sorted(validation_rows), 'probabilities': prior_probabilities.tolist(),
        'description': 'Per-phone +1/class prior fitted on exactly this regime and fold fit rows; observed counts kept separately'})
    best_epoch, best_loss, history = 0, math.inf, []
    for epoch in range(1, args.epochs+1):
        model.train()
        order = generator.permutation(fit_clips).tolist()
        loss_sum, target_count = 0., 0
        for offset in range(0, len(order), args.batch_size):
            features, mask, phones, target_mask, targets, _ = data.batch(
                order[offset:offset+args.batch_size], set(fit_rows), mean, std, args.device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(features, mask, phones, target_mask)
            losses = weighted_loss(logits, targets, weights)[target_mask]
            loss = losses.mean()
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite child-probe training objective')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(losses.detach().sum().cpu())
            target_count += len(losses)
        metrics, _ = evaluate(model, data, validation_rows, mean, std, weights, args.device, args.batch_size)
        value = metrics['ages6to12']['macroTargetLogLoss']
        record = {'epoch': epoch, 'trainWeightedPerRaterObjective': loss_sum/target_count,
                  'validation': metrics, 'elapsedSeconds': time.perf_counter()-started}
        history.append(record)
        improved = value < best_loss-1e-7
        if improved:
            best_epoch, best_loss = epoch, value
        saved = {'model': model.state_dict(), 'optimizer': optimizer.state_dict(), 'mean': mean, 'std': std,
                 'classWeights': weights.detach().cpu(), 'classWeightState': class_state,
                 'epoch': epoch, 'bestEpoch': best_epoch, 'bestLoss': best_loss,
                 'torchRng': torch.get_rng_state(), 'numpyRng': generator.bit_generator.state,
                 'pythonRng': random.getstate(), 'configSha256': digest(args.output/'config.json')}
        if args.device == 'mps':
            saved['mpsRng'] = torch.mps.get_rng_state()
        if improved:
            save_checkpoint(args.output/'best.pt', saved)
        save_checkpoint(args.output/'last.pt', saved)
        atomic_json(args.output/'history.json', history)
        atomic_json(args.output/'status.json', {'pid': os.getpid(), 'epoch': epoch, 'bestEpoch': best_epoch,
                                              'complete': False, 'elapsedSeconds': time.perf_counter()-started})
        source_guard(config)
        print(json.dumps({'epoch': epoch, 'childMacroLogLoss': value, 'bestEpoch': best_epoch,
                          'allAgeLogLoss': metrics['allAges']['perRaterLogLoss']}), flush=True)
        if epoch-best_epoch >= args.patience:
            break
    saved = torch.load(args.output/'best.pt', map_location=args.device, weights_only=True)
    model.load_state_dict(saved['model'], strict=True)
    metrics, predictions = evaluate(model, data, validation_rows, mean, std, weights, args.device, args.batch_size)
    source_guard(config)
    atomic_json(args.output/'predictions.json', predictions)
    report = {'complete': True, 'configSha256': digest(args.output/'config.json'),
              'checkpointSha256': digest(args.output/'best.pt'), 'priorSha256': digest(args.output/'prior.json'),
              'bestEpoch': best_epoch, 'bestChildMacroLogLoss': best_loss, 'epochsRun': len(history),
              'evaluation': metrics, 'sameFitPriorEvaluation': prior_metrics,
              'childMacroLogLossMinusPrior': metrics['ages6to12']['macroTargetLogLoss']-prior_metrics['ages6to12']['macroTargetLogLoss'],
              'evaluationRole': 'child inner-speaker selection', 'elapsedSeconds': time.perf_counter()-started,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    atomic_json(args.output/'report.json', report)
    atomic_json(args.output/'status.json', {'complete': True, 'bestEpoch': best_epoch, 'epochsRun': len(history),
                                          'elapsedSeconds': report['elapsedSeconds']})
    return report


def replay(output: Path, device: str = 'cpu') -> dict:
    config = json.loads((output/'config.json').read_text())
    source_guard(config)
    args = argparse.Namespace(**config)
    for name in ('cohort', 'splits', 'cache', 'output'):
        setattr(args, name, Path(getattr(args, name)))
    args.device = device
    data, fit, validation, children, clips, mean, std, state, priors = setup(args)
    if (fit != config['fitRows'] or validation != config['validationRows'] or children != config['childSelectionRows']
            or clips != config['fitClips'] or state != config['classWeightState'] or priors != config['priorState']
            or data.index_sha256 != config['cacheIndexSha256']):
        raise ValueError('Replay fit statistics or split/cache binding changed')
    report = json.loads((output/'report.json').read_text())
    if (report['checkpointSha256'] != digest(output/'best.pt')
            or report['configSha256'] != digest(output/'config.json')
            or report['priorSha256'] != digest(output/'prior.json')):
        raise ValueError('Replay checkpoint differs from the completed report')
    saved = torch.load(output/'best.pt', map_location='cpu', weights_only=True)
    if (saved['configSha256'] != digest(output/'config.json') or saved['classWeightState'] != state
            or not torch.equal(saved['mean'], mean) or not torch.equal(saved['std'], std)
            or not torch.equal(saved['classWeights'], torch.tensor(state['weights'], dtype=torch.float32))):
        raise ValueError('Replay checkpoint normalization or class-weight correction changed')
    model = MeanPoolPhoneRatingHead(hidden_dim=args.hidden, dropout=args.dropout).to(device)
    model.load_state_dict(saved['model'], strict=True)
    metrics, predictions = evaluate(model, data, validation, mean, std, saved['classWeights'].to(device), device, args.batch_size)
    previous = json.loads((output/'predictions.json').read_text())
    if previous['rowIndices'] != predictions['rowIndices']:
        raise ValueError('Replay prediction rows changed')
    difference = float(np.abs(np.asarray(previous['probabilities'])-np.asarray(predictions['probabilities'])).max())
    result = {'checkpointSha256': digest(output/'best.pt'), 'evaluation': metrics,
              'maximumAbsoluteProbabilityDifference': difference, 'device': device,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    atomic_json(output/'replay.json', result)
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ('cohort', 'splits', 'cache', 'output'):
        result.add_argument('--'+name, type=Path, required=True)
    result.add_argument('--encoder', choices=list(IDENTITIES), required=True)
    result.add_argument('--regime', choices=REGIMES, required=True)
    result.add_argument('--fold', type=int, choices=range(5), required=True)
    result.add_argument('--lr', type=float, choices=[0.001, 0.0003], required=True)
    result.add_argument('--seed', type=int, default=7)
    result.add_argument('--hidden', type=int, default=128)
    result.add_argument('--dropout', type=float, default=0.1)
    result.add_argument('--weight-decay', type=float, default=0.01)
    result.add_argument('--batch-size', type=int, default=16)
    result.add_argument('--epochs', type=int, default=100)
    result.add_argument('--patience', type=int, default=15)
    result.add_argument('--device', choices=['cpu', 'mps'], default='cpu')
    result.add_argument('--threads', type=int, default=2)
    result.add_argument('--replay', action='store_true')
    return result


if __name__ == '__main__':
    arguments = parser().parse_args()
    print(json.dumps(replay(arguments.output, arguments.device) if arguments.replay else train(arguments), allow_nan=False), flush=True)
