"""Inner-only phone-conditioned heads on estimated local WavLM windows.

The pooled vectors come from forced canonical CTC occupancy plus fixed context,
not reviewed phonetic boundaries. No encoder is updated and no outer predictions
are produced. Target rows, rather than clips or frames, define this objective.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

from encoders import WavLMEncoder
from multiphone_cache import atomic_json
from multiphone_child_train import fit_priors, is_child, score_predictions
from multiphone_data import TARGETS
from multiphone_local_train import SCALAR_NAMES, digest, load_inputs, read_json, require
from multiphone_models import MeanPoolPhoneRatingHead
from multiphone_train import save_checkpoint, valid_counts

HERE = Path(__file__).resolve().parent
RECIPE = HERE/'experiments/multiphone-local-heads-v1.json'
FAMILIES = ('embedding', 'embedding-scalars')
REGIMES = ('all-age', 'child-only')
SOURCES = ('multiphone_local_head.py', 'multiphone_local_train.py', 'multiphone_controls.py',
           'multiphone_child_train.py', 'multiphone_train.py', 'multiphone_models.py',
           'multiphone_cache.py', 'multiphone_verify.py', 'multiphone_data.py',
           'encoders.py', 'speechocean_r_rater_cv.py')


def load_local_inputs(cohort_path: Path, splits_path: Path, feature_path: Path):
    """Extend the reviewed scalar loader with strict pooled-vector provenance."""
    cohort, splits, scalars, positions, binding = load_inputs(cohort_path, splits_path, feature_path)
    metadata = read_json(feature_path)
    directory = feature_path.parent.resolve()
    asset = metadata.get('pooledFeatures')
    require(isinstance(asset, dict), 'Estimated pooled WavLM features are required')
    path = (directory/asset['path']).resolve()
    require(path.is_relative_to(directory) and digest(path) == asset['sha256']
            and metadata.get('pooledFeaturesSha256') == asset['sha256'], 'Pooled feature path/digest differs')
    pooled = np.load(path, mmap_mode='r', allow_pickle=False)
    require(asset['dtype'] == 'float32' and asset['shape'] == [len(positions), 768]
            and pooled.dtype == np.float32 and list(pooled.shape) == asset['shape']
            and np.isfinite(pooled).all(), 'Invalid pooled matrix shape/dtype/values')
    require('wavlmIndex' in binding['upstream'], 'Pooled vectors require a pinned WavLM cache')
    index_path = Path(binding['upstream']['wavlmIndex']['path'])
    index = read_json(index_path)
    config_path = index_path.parent/'config.json'
    config = read_json(config_path)
    require(index.get('complete') is True and index['configSha256'] == digest(config_path)
            and config['encoder'] == WavLMEncoder.identity
            and config['cohortSha256'] == binding['cohortSha256']
            and config['authorPartition'] == 'train' and config['dtype'] == 'float32'
            and metadata['inputSha256']['wavlmConfig'] == digest(config_path),
            'Pooled WavLM cache identity/config differs')
    extraction_recipe = read_json(Path(binding['upstream']['recipe']['path']))
    context = extraction_recipe['poolingContextFrames']
    ctc_index = read_json(Path(binding['upstream']['ctcIndex']['path']))
    require(type(context) is int and context == 2, 'Unexpected estimated-window context recipe')
    for position, (row_index, row) in enumerate(zip(metadata['rowIndices'], metadata['rows'], strict=True)):
        clip = cohort['clips'][cohort['rows'][row_index]['clipIndex']]
        entry = index['entries'][clip['id']]
        ctc_entry = ctc_index['entries'][clip['id']]
        interval, window = row['intervalFrames'], row['estimatedPoolingWindowFrames']
        require(type(row.get('pooledFeatureIndex')) is int and row['pooledFeatureIndex'] == position
                and positions[row_index] == position
                and len(interval) == len(window) == 2
                and all(type(value) is int for value in interval+window)
                and 0 <= window[0] <= interval[0] < interval[1] <= window[1] <= entry['frames']
                and window == [max(0, interval[0]-context), min(entry['frames'], interval[1]+context)]
                and ctc_entry['frames'] == entry['frames']
                and ctc_entry['audioSha256'] == entry['audioSha256'] == clip['audioSha256'],
                'Pooled row mapping or window geometry differs')
    binding.update(pooledPath=str(path), pooledSha256=digest(path),
                   wavlmConfigPath=str(config_path), wavlmConfigSha256=digest(config_path),
                   ctcConfigPath=str(Path(binding['upstream']['ctcIndex']['path']).parent/'config.json'))
    return cohort, splits, scalars, pooled, positions, binding


def select_rows(cohort, splits, fold_index, regime):
    require(regime in REGIMES, 'Unknown fitting regime')
    fold = splits['folds'][fold_index]
    fit = [index for index in fold['innerFitRows'] if regime == 'all-age' or is_child(cohort['rows'][index])]
    validation = fold['innerValidationRows']
    children = [index for index in validation if is_child(cohort['rows'][index])]
    require(fit and children, 'Fit rows and child inner-validation rows are required')
    for index in fit+validation:
        row = cohort['rows'][index]
        require(row['trainingEligible'] is True and type(row['targetId']) is int
                and 0 <= row['targetId'] < 23 and row['targetPhone'] == TARGETS[row['targetId']]
                and valid_counts(np.asarray([row['raterCounts']], dtype=float)),
                'Invalid eligible phone or five-rater label')
    return fit, validation, children if regime == 'child-only' else validation


def setup(args):
    recipe = read_json(RECIPE)
    exact = {'hidden': 'hiddenWidth', 'dropout': 'dropout', 'weight_decay': 'weightDecay',
             'batch_size': 'batchSizeTargetRows', 'epochs': 'maximumEpochs', 'patience': 'patienceEpochs'}
    require(args.family in recipe['families'] and args.regime in recipe['regimes']
            and args.fold in recipe['folds'] and args.seed in recipe['initializationSeeds']
            and args.lr in recipe['learningRates']
            and all(getattr(args, name) == recipe[key] for name, key in exact.items())
            and digest(args.cohort) == recipe['cohortSha256'] and digest(args.splits) == recipe['splitsSha256']
            and digest(args.features) == recipe['featuresSha256'], 'Arguments or inputs differ from the local-head recipe')
    cohort, splits, scalars, pooled, positions, binding = load_local_inputs(args.cohort, args.splits, args.features)
    require(binding['featuresSha256'] == recipe['featuresSha256'] and digest(args.features) == binding['featuresSha256'],
            'Pinned local features changed while loading')
    fit, validation, selection = select_rows(cohort, splits, args.fold, args.regime)
    values = np.asarray(pooled) if args.family == 'embedding' else np.concatenate((pooled, scalars), axis=1)
    fit_values = np.asarray(values[[positions[index] for index in fit]], dtype=np.float64)
    mean, std = fit_values.mean(0), fit_values.std(0)
    std = np.where(std < 1e-6, 1., std)
    require(np.isfinite(mean).all() and np.isfinite(std).all(), 'Nonfinite fit-only moments')
    return {'cohort': cohort, 'values': values, 'positions': positions, 'binding': binding,
            'fit': fit, 'validation': validation, 'selection': selection,
            'mean': torch.tensor(mean, dtype=torch.float32), 'std': torch.tensor(std, dtype=torch.float32),
            'priors': fit_priors([cohort['rows'][index] for index in fit])}


def source_guard(config):
    require(digest(RECIPE) == config['recipeSha256'] and all(
        digest(HERE/name) == value for name, value in config['sourceSha256'].items()),
        'Local-head recipe or implementation changed')


def binding_guard(binding):
    for name in ('cohort', 'splits', 'features', 'scalar', 'pooled', 'ctcConfig', 'wavlmConfig'):
        require(digest(Path(binding[name+'Path'])) == binding[name+'Sha256'], 'Local-head input binding changed')
    for entry in binding['upstream'].values():
        require(digest(Path(entry['path'])) == entry['sha256'], 'Local-head upstream input changed')
    require(all(digest(HERE/name) == value for name, value in binding['extractionSourceSha256'].items()),
            'Local feature extraction source changed')


def batch(data, indices, device):
    rows = [data['cohort']['rows'][index] for index in indices]
    values = torch.tensor(data['values'][[data['positions'][index] for index in indices]], dtype=torch.float32)
    values = ((values-data['mean'])/data['std']).to(device)[:, None, :]
    phones = torch.tensor([[row['targetId']] for row in rows], dtype=torch.long, device=device)
    mask = torch.ones(phones.shape, dtype=torch.bool, device=device)
    targets = torch.tensor([row['raterCounts'] for row in rows], dtype=torch.float32, device=device)/5
    return values, phones, mask, targets


@torch.no_grad()
def evaluate(model, data, selected, device, batch_size):
    model.eval()
    probabilities = []
    for offset in range(0, len(selected), batch_size):
        values, phones, mask, _ = batch(data, selected[offset:offset+batch_size], device)
        probabilities.extend(model(values, mask, phones, mask)[:, 0].softmax(-1).cpu().numpy())
    probabilities = np.asarray(probabilities, dtype=np.float64)
    return score_predictions(probabilities, [data['cohort']['rows'][index] for index in selected]), {
        'rowIndices': selected, 'probabilities': probabilities.tolist(),
        'probabilityScale': 'ordinary unweighted softmax; no class correction'}


def selection_loss(metrics, regime):
    return metrics['ages6to12' if regime == 'child-only' else 'allAges']['macroTargetLogLoss']


def make_model(args, width):
    # A singleton frame reuses the established phone-conditioned MLP exactly;
    # pooling occurred once during audited feature extraction, before fitting.
    return MeanPoolPhoneRatingHead(feature_dim=width, hidden_dim=args.hidden, dropout=args.dropout).to(args.device)


def train(args):
    require(not args.output.exists() and args.output.resolve().is_relative_to((HERE/'outputs').resolve()),
            'Choose a fresh run directory inside ignored research outputs')
    require(args.device != 'mps' or torch.backends.mps.is_available(), 'MPS unavailable')
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    started = time.perf_counter()
    data = setup(args)
    model = make_model(args, data['values'].shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    config = {name: str(value.resolve()) if isinstance(value, Path) else value
              for name, value in vars(args).items() if name != 'replay'}
    config.update(recipeSha256=digest(RECIPE), sourceSha256={name: digest(HERE/name) for name in SOURCES},
                  binding=data['binding'], fitRows=data['fit'], validationRows=data['validation'],
                  selectionRows=data['selection'], priorState=data['priors'],
                  featureWidth=data['values'].shape[1], encoderIdentity=WavLMEncoder.identity,
                  fitObservedRaterCounts=np.asarray([data['cohort']['rows'][i]['raterCounts'] for i in data['fit']]).sum(0).tolist(),
                  fitSpeakers=len({data['cohort']['rows'][i]['speakerId'] for i in data['fit']}),
                  validationTargetsWithoutFitRows=sorted({data['cohort']['rows'][i]['targetPhone'] for i in data['validation']}
                      -{data['cohort']['rows'][i]['targetPhone'] for i in data['fit']}),
                  selection='child macro-phone NLL' if args.regime == 'child-only' else 'all-age macro-phone NLL',
                  normalization='column moments from actual fit target rows; SD below 1e-6 becomes 1',
                  featureColumns=[f'estimatedWavlm:{i}' for i in range(768)]+(SCALAR_NAMES if args.family == 'embedding-scalars' else []),
                  trainableParameters=sum(value.numel() for value in model.parameters()),
                  phase='inner', authorPartition='train', authorTestInferencePerformed=False,
                  frameTimesValidated=False, clinicalUseEligible=False, learnerFeedbackEligible=False,
                  classWeighting=False, probabilityCorrection=False, outerOutcomesUsed=False,
                  torch=str(torch.__version__), numpy=np.__version__)
    source_guard(config)
    binding_guard(config['binding'])
    args.output.mkdir(parents=True)
    atomic_json(args.output/'config.json', config)
    validation_rows = [data['cohort']['rows'][i] for i in data['validation']]
    prior = np.asarray([data['priors'][row['targetPhone']]['probabilities'] for row in validation_rows])
    prior_metrics = score_predictions(prior, validation_rows)
    atomic_json(args.output/'prior.json', {'state': data['priors'], 'evaluation': prior_metrics,
                                         'rowIndices': data['validation'], 'probabilities': prior.tolist()})
    best_loss, best_epoch, history = float('inf'), 0, []
    for epoch in range(1, args.epochs+1):
        model.train()
        order = generator.permutation(data['fit']).tolist()
        loss_sum = 0.
        for offset in range(0, len(order), args.batch_size):
            indices = order[offset:offset+args.batch_size]
            values, phones, mask, targets = batch(data, indices, args.device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(values, mask, phones, mask)[:, 0]
            losses = -(targets*logits.log_softmax(-1)).sum(-1)
            require(bool(torch.isfinite(losses).all()), 'Nonfinite local-head loss')
            losses.mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(losses.detach().sum().cpu())
        metrics, _ = evaluate(model, data, data['validation'], args.device, args.batch_size)
        value = selection_loss(metrics, args.regime)
        require(np.isfinite(value), 'Nonfinite inner-selection loss')
        record = {'epoch': epoch, 'trainPerRaterLogLoss': loss_sum/len(order),
                  'selectionMacroTargetLogLoss': value, 'evaluation': metrics}
        history.append(record)
        improved = value < best_loss-1e-7
        if improved:
            best_loss, best_epoch = value, epoch
        checkpoint = {'model': model.state_dict(), 'mean': data['mean'], 'std': data['std'],
                      'optimizer': optimizer.state_dict(), 'epoch': epoch,
                      'bestEpoch': best_epoch, 'bestLoss': best_loss,
                      'configSha256': digest(args.output/'config.json')}
        source_guard(config)
        save_checkpoint(args.output/'last.pt', checkpoint)
        if improved:
            save_checkpoint(args.output/'best.pt', checkpoint)
        atomic_json(args.output/'history.json', history)
        atomic_json(args.output/'status.json', {'complete': False, 'epoch': epoch, 'bestEpoch': best_epoch,
                    'selectionMacroTargetLogLoss': best_loss, 'elapsedSeconds': time.perf_counter()-started})
        print(json.dumps({'epoch': epoch, 'selectionMacroTargetLogLoss': value, 'bestEpoch': best_epoch}), flush=True)
        if epoch-best_epoch >= args.patience:
            break
    saved = torch.load(args.output/'best.pt', map_location='cpu', weights_only=True)
    model.load_state_dict(saved['model'], strict=True)
    metrics, predictions = evaluate(model, data, data['validation'], args.device, args.batch_size)
    require(selection_loss(metrics, args.regime) == best_loss, 'Selected checkpoint score differs')
    source_guard(config)
    binding_guard(config['binding'])
    atomic_json(args.output/'predictions.json', predictions)
    report = {'complete': True, 'configSha256': digest(args.output/'config.json'),
              'checkpointSha256': digest(args.output/'best.pt'), 'predictionsSha256': digest(args.output/'predictions.json'),
              'historySha256': digest(args.output/'history.json'), 'priorSha256': digest(args.output/'prior.json'),
              'bestEpoch': best_epoch, 'epochsRun': len(history), 'bestSelectionMacroLogLoss': best_loss,
              'evaluation': metrics, 'sameFitPriorEvaluation': prior_metrics,
              'selectionMacroLogLossMinusPrior': best_loss-selection_loss(prior_metrics, args.regime),
              'elapsedSeconds': time.perf_counter()-started, 'evaluationRole': config['selection']+' inner-speaker selection',
              'outerOutcomesUsed': False, 'frameTimesValidated': False,
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    atomic_json(args.output/'report.json', report)
    atomic_json(args.output/'status.json', {'complete': True, 'bestEpoch': best_epoch, 'epochsRun': len(history),
                                          'elapsedSeconds': report['elapsedSeconds']})
    return report


def replay(output: Path, device='cpu'):
    config = read_json(output/'config.json')
    source_guard(config)
    binding_guard(config['binding'])
    args = argparse.Namespace(**config)
    for name in ('cohort', 'splits', 'features', 'output'):
        setattr(args, name, Path(getattr(args, name)))
    args.device = device
    torch.set_num_threads(args.threads)
    data = setup(args)
    require(data['binding'] == config['binding'] and data['fit'] == config['fitRows']
            and data['validation'] == config['validationRows'] and data['selection'] == config['selectionRows']
            and data['priors'] == config['priorState'], 'Replay row/statistic/input binding differs')
    report = read_json(output/'report.json')
    require(report['complete'] is True and report['configSha256'] == digest(output/'config.json')
            and all(report[key+'Sha256'] == digest(output/filename) for key, filename in
                    [('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json')]),
            'Replay artifact differs from completed report')
    saved = torch.load(output/'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == digest(output/'config.json') and saved['epoch'] == report['bestEpoch']
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']),
            'Replay checkpoint or fit-only normalization differs')
    model = make_model(args, data['values'].shape[1])
    model.load_state_dict(saved['model'], strict=True)
    metrics, predictions = evaluate(model, data, data['validation'], device, args.batch_size)
    reference = read_json(output/'predictions.json')
    require(reference['rowIndices'] == predictions['rowIndices'], 'Replay prediction rows differ')
    difference = float(np.abs(np.asarray(reference['probabilities'])-np.asarray(predictions['probabilities'])).max())
    if device == config['device'] == 'cpu':
        require(difference == 0. and metrics == report['evaluation'], 'CPU checkpoint replay is not exact')
    result = {'checkpointSha256': digest(output/'best.pt'), 'device': device, 'evaluation': metrics,
              'maximumAbsoluteProbabilityDifference': difference, 'rows': len(data['validation']),
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    source_guard(config)
    binding_guard(config['binding'])
    atomic_json(output/'replay.json', result)
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ('cohort', 'splits', 'features', 'output'):
        result.add_argument('--'+name, type=Path, required=True)
    result.add_argument('--family', choices=FAMILIES, required=True)
    result.add_argument('--regime', choices=REGIMES, required=True)
    result.add_argument('--fold', type=int, choices=range(5), required=True)
    result.add_argument('--lr', type=float, choices=[.001, .0003], required=True)
    result.add_argument('--seed', type=int, default=7)
    result.add_argument('--hidden', type=int, default=128)
    result.add_argument('--dropout', type=float, default=.1)
    result.add_argument('--weight-decay', type=float, default=.01)
    result.add_argument('--batch-size', type=int, default=64)
    result.add_argument('--epochs', type=int, default=100)
    result.add_argument('--patience', type=int, default=15)
    result.add_argument('--device', choices=['cpu', 'mps'], default='cpu')
    result.add_argument('--threads', type=int, default=2)
    result.add_argument('--replay', action='store_true')
    return result


if __name__ == '__main__':
    arguments = parser().parse_args()
    print(json.dumps(replay(arguments.output, arguments.device) if arguments.replay else train(arguments), allow_nan=False), flush=True)
