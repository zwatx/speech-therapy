"""Inner-only raw-audio continuation of pinned expected-window rating heads.

The CTC windows and thirteen scalar features remain fixed estimates. Supervision
is the existing five-rater distribution, never a produced-phone or CTC target.
Only the final transformer layer may adapt; head-only continuation is matched.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import time
import uuid

import numpy as np
import torch
from torch import nn

import multiphone_phonetic_head as frozen
from multiphone_adapt import RawStudyData, rng_state, restore_rng
from multiphone_cache import atomic_json, digest
from multiphone_child_train import score_predictions
from multiphone_models import MeanPoolPhoneRatingHead
from multiphone_train import save_checkpoint

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
RECIPE = HERE / 'experiments/multiphone-phonetic-adaptation-v1.json'
SOURCES = tuple(dict.fromkeys(('multiphone_phonetic_adapt.py', 'multiphone_adapt.py') + frozen.SOURCES))
require, read_json = frozen.require, frozen.read_json


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCES}


def configure_encoder(encoder, upper_layers):
    require(upper_layers in (0, 1) and len(encoder.encoder.layers) == 24,
            'Only head-only or the last of exactly24 layers may adapt')
    encoder.requires_grad_(False).eval()
    if upper_layers:
        encoder.encoder.layers[23].requires_grad_(True)
    names = [name for name, value in encoder.named_parameters() if value.requires_grad]
    require(all(name.startswith('encoder.layers.23.') for name in names)
            and bool(names) == bool(upper_layers), 'Trainable encoder allowlist differs')
    return names


def frozen_parameter_digest(encoder):
    result = hashlib.sha256()
    for name, value in sorted(encoder.named_parameters()):
        if not value.requires_grad:
            result.update(name.encode())
            result.update(str(tuple(value.shape)).encode())
            result.update(value.detach().cpu().contiguous().numpy().tobytes())
    return result.hexdigest()


class TargetRatingModel(nn.Module):
    def __init__(self, encoder, head, mean, std, upper_layers):
        super().__init__()
        require(mean.shape == std.shape == (1037,) and torch.isfinite(mean).all()
                and torch.isfinite(std).all() and (std > 0).all(), 'Invalid fixed fit-row moments')
        self.encoder, self.head = encoder, head
        self.register_buffer('mean', mean.clone())
        self.register_buffer('std', std.clone())
        self.trainable_encoder_names = configure_encoder(encoder, upper_layers)

    def train(self, mode=True):
        super().train(mode)
        self.encoder.eval()
        return self

    def forward(self, inputs, phones, windows, scalars, expected_frames):
        raw = inputs['input_values']
        require(raw.ndim == 2 and raw.shape[0] == 1 and raw.shape[1] > 0 and torch.isfinite(raw).all(),
                'Expected one finite unpadded waveform')
        require('attention_mask' in inputs and inputs['attention_mask'].shape == raw.shape
                and bool((inputs['attention_mask'] == 1).all()), 'Raw waveform must have no padded samples')
        require(phones.ndim == 1 and 1 <= len(phones) <= 23 and phones.dtype == torch.long
                and bool(((phones >= 0) & (phones < 23)).all()) and len(phones.unique()) == len(phones),
                'Invalid or duplicated eligible targets')
        require(scalars.shape == (len(phones), 13) and scalars.dtype == torch.float32
                and torch.isfinite(scalars).all() and not scalars.requires_grad
                and phones.device == scalars.device == raw.device, 'Frozen scalar features differ')
        require(len(windows) == len(phones) and type(expected_frames) is int and expected_frames > 0,
                'Target windows/grid differ')
        for window in windows:
            require(len(window) == 2 and all(type(v) is int for v in window)
                    and 0 <= window[0] < window[1] <= expected_frames, 'Invalid estimated target window')
        frames = self.encoder(**inputs).last_hidden_state
        require(frames.shape == (1, expected_frames, 1024) and frames.dtype == torch.float32
                and torch.isfinite(frames).all(), 'Raw encoder frame grid/dtype differs')
        # MPS has no float64 arithmetic. The frozen cache used float64 sums;
        # raw epoch-zero comparison measures this and device numerical drift.
        pooled = torch.stack([frames[0, start:end].mean(0) for start, end in windows])
        features = (torch.cat((pooled, scalars), -1) - self.mean) / self.std
        mask = torch.ones((len(phones), 1), dtype=torch.bool, device=frames.device)
        return self.head(features[:, None], mask, phones[:, None], mask)[:, 0]

    def adapted_state(self):
        parameters = dict(self.encoder.named_parameters())
        return {name: parameters[name].detach().cpu().clone() for name in self.trainable_encoder_names}

    def restore_adapted_state(self, values):
        require(set(values) == set(self.trainable_encoder_names), 'Checkpoint changes the encoder allowlist')
        parameters = dict(self.encoder.named_parameters())
        with torch.no_grad():
            for name, value in values.items():
                require(value.shape == parameters[name].shape and value.dtype == parameters[name].dtype
                        and torch.isfinite(value).all(), 'Invalid adapted encoder tensor')
                parameters[name].copy_(value)


class RawTargetData(RawStudyData):
    def __init__(self, bundle, selected_rows, processor, device):
        super().__init__(bundle['cohort'], selected_rows, processor, device)
        self.scalars, self.positions = bundle['scalars'], bundle['positions']
        original = read_json(Path(bundle['originalFeaturesPath']))
        self.windows = {row['rowIndex']: row['estimatedPoolingWindowFrames'] for row in original['rows']}
        self.extraction_recipe = read_json(frozen.EXTRACTION_RECIPE)
        require(set(selected_rows) <= set(self.positions) == set(self.windows), 'Raw rows lack original windows/scalars')

    def clip(self, index):
        inputs, phones, targets, indices = super().clip(index)
        clip = self.clips[index]
        require(inputs['input_values'].shape[1] == clip['sampleCount'], 'Waveform sample count differs')
        scalars = torch.tensor(np.asarray(self.scalars[[self.positions[i] for i in indices]]).copy(),
                               dtype=torch.float32, device=self.device)
        windows = [self.windows[i] for i in indices]
        frames = frozen.extraction.convolution_frames(clip['sampleCount'], self.extraction_recipe)
        return inputs, phones[0], windows, scalars, frames, targets, indices


@torch.no_grad()
def evaluate(model, data, rows):
    model.eval()
    values = {}
    for clip in sorted({data.rows[row]['clipIndex'] for row in rows}):
        inputs, phones, windows, scalars, frames, _, indices = data.clip(clip)
        probabilities = model(inputs, phones, windows, scalars, frames).softmax(-1).cpu().numpy()
        values.update(zip(indices, probabilities, strict=True))
    require(set(values) == set(rows) and len(rows) == len(set(rows)), 'Raw evaluation row coverage differs')
    probabilities = np.asarray([values[row] for row in rows], dtype=np.float64)
    return score_predictions(probabilities, [data.rows[row] for row in rows]), {
        'rowIndices': rows, 'probabilities': probabilities.tolist()}


def update_group(model, optimizer, data, clip_ids, maximum_norm):
    count = sum(len(data.grouped[index]) for index in clip_ids)
    require(count > 0, 'Empty supervised update')
    optimizer.zero_grad(set_to_none=True)
    total = 0.
    for index in clip_ids:
        inputs, phones, windows, scalars, frames, targets, _ = data.clip(index)
        loss = -(targets * model(inputs, phones, windows, scalars, frames).log_softmax(-1)).sum()
        require(torch.isfinite(loss), 'Nonfinite human-rating loss')
        (loss / count).backward()
        total += float(loss.detach().cpu())
    require(all(value.grad is None for value in model.encoder.parameters() if not value.requires_grad),
            'Frozen encoder parameter received a gradient')
    parameters = [value for value in model.parameters() if value.requires_grad]
    norm = torch.nn.utils.clip_grad_norm_(parameters, maximum_norm, error_if_nonfinite=True)
    optimizer.step()
    require(all(torch.isfinite(value).all() for value in parameters), 'Nonfinite optimizer output')
    return total, count, float(norm.detach().cpu())


def validate_args(args, recipe):
    arms = {arm['name']: arm for arm in recipe['arms']}
    require(args.regime in recipe['regimes'] and args.arm in arms and args.device in ('cpu', 'mps'),
            'Undeclared adaptation regime/arm/device')
    return arms[args.arm]


def prepare(args, recipe):
    arm = validate_args(args, recipe)
    warm = recipe['warmStarts'][args.regime]
    directory = HERE / warm['directory']
    require(all(digest(directory / name) == sha for name, sha in warm['files'].items()),
            'Pinned frozen warm-start artifact changed')
    require(digest(Path(recipe['featureBindingPath'])) == recipe['featureBindingSha256'], 'Feature binding changed')
    config, report, replay = [read_json(directory / name) for name in ('config.json', 'report.json', 'replay.json')]
    require(config['regime'] == args.regime and config['family'] == 'target-scalars' and config['fold'] == 0
            and config['lr'] == .0003 and report['complete'] is True and report['bestEpoch'] == 5
            and replay['exact'] is True and replay['checkpointSha256'] == warm['files']['best.pt'],
            'Wrong warm-start family/fold/regime/selection')
    setup_args = argparse.Namespace(**config)
    setup_args.binding = Path(setup_args.binding)
    data = frozen.setup(setup_args)
    evidence = read_json(setup_args.binding)
    data['originalFeaturesPath'] = evidence['originalFeaturesPath']
    saved = torch.load(directory / 'best.pt', map_location='cpu', weights_only=True)
    require(saved['configSha256'] == digest(directory / 'config.json') and saved['epoch'] == report['bestEpoch']
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std'])
            and config['fitRows'] == data['fit'] and config['validationRows'] == data['validation']
            and config['selectionRows'] == data['selection'], 'Warm normalization/row selection differs')
    return data, saved, directory, arm


def load_model(data, saved, upper_layers):
    extraction_recipe = read_json(frozen.EXTRACTION_RECIPE)
    # Bindings resolve individual symlinks to blobs, so use the pinned snapshot.
    snapshot = HERE / 'outputs/model-cache' / ('models--' + extraction_recipe['modelId'].replace('/', '--')) / 'snapshots' / extraction_recipe['revision']
    encoder = frozen.extraction.PhoneticEncoder(snapshot, extraction_recipe)
    head = MeanPoolPhoneRatingHead(feature_dim=1037, hidden_dim=128, dropout=.1)
    head.load_state_dict(saved['model'], strict=True)
    model = TargetRatingModel(encoder.model.wav2vec2, head, data['mean'], data['std'], upper_layers)
    return model, encoder.processor


def guard(config):
    require(digest(RECIPE) == config['recipeSha256'] and source_hashes() == config['sourceSha256'],
            'Adaptation source/recipe changed')
    frozen.extraction.guard(config['inputFiles'])
    recipe = read_json(RECIPE)
    require(digest(Path(recipe['featureBindingPath'])) == recipe['featureBindingSha256'], 'Frozen binding changed')
    for warm in recipe['warmStarts'].values():
        require(all(digest(HERE / warm['directory'] / name) == sha for name, sha in warm['files'].items()),
                'Warm-start artifacts changed')


def restore_checkpoint(saved, model, optimizer, generator, config_sha, device):
    require(saved['configSha256'] == config_sha and torch.equal(saved['mean'], model.mean.cpu())
            and torch.equal(saved['std'], model.std.cpu()), 'Checkpoint config or fixed moments differ')
    model.restore_adapted_state(saved['encoder'])
    model.head.load_state_dict(saved['head'], strict=True)
    optimizer.load_state_dict(saved['optimizer'])
    restore_rng(saved['rng'], generator, device)
    return saved['progress']


def verify_epoch_zero(output, progress):
    require(digest(output / 'epoch-zero.json') == progress['epochZeroSha256']
            and digest(output / 'epoch-zero-predictions.json') == progress['epochZeroPredictionsSha256'],
            'Immutable epoch-zero artifacts changed')
    record = read_json(output / 'epoch-zero.json')
    require(record['predictionsSha256'] == progress['epochZeroPredictionsSha256']
            and record['evaluation'] == progress['history'][0]['evaluation'], 'Epoch-zero history differs')


def fit_loop(model, optimizer, fit_data, validation_data, validation_rows, args, recipe, config, reference):
    """Persist only completed optimizer boundaries; resumed updates are identical."""
    generator = np.random.default_rng(recipe['seed'])
    output, config_sha = args.output, digest(args.output / 'config.json')
    require(read_json(output / 'config.json') == config, 'Output configuration differs before fitting')
    started = time.perf_counter()
    progress = {'epoch': 1, 'order': [], 'cursor': 0, 'lossSum': 0., 'targetCount': 0, 'updates': 0,
                'bestEpoch': 0, 'bestLoss': None, 'bestCheckpoint': None, 'bestCheckpointSha256': None,
                'history': [], 'elapsedSeconds': 0., 'configSha256': config_sha}
    if args.resume:
        saved = torch.load(output / 'last.pt', map_location='cpu', weights_only=True)
        progress = restore_checkpoint(saved, model, optimizer, generator, config_sha, args.device)
        chosen = output / progress['bestCheckpoint']
        require(chosen.resolve().is_relative_to(output.resolve())
                and digest(chosen) == progress['bestCheckpointSha256'], 'Resume selected checkpoint changed')
        verify_epoch_zero(output, progress)
    previous_elapsed = progress['elapsedSeconds']

    def checkpoint(path):
        require(digest(output / 'config.json') == config_sha, 'Output configuration changed during fitting')
        progress['elapsedSeconds'] = previous_elapsed + time.perf_counter() - started
        save_checkpoint(path, {'schemaVersion': 1, 'configSha256': config_sha,
            'encoder': model.adapted_state(), 'head': model.head.state_dict(),
            'mean': model.mean.detach().cpu(), 'std': model.std.detach().cpu(),
            'optimizer': optimizer.state_dict(), 'rng': rng_state(generator, args.device), 'progress': progress})

    def select(epoch):
        # Unique immutable names also permit deterministic retry after a crash
        # between selected-checkpoint publication and last.pt publication.
        progress['bestCheckpoint'] = f'selected-epoch-{epoch:04d}-{uuid.uuid4().hex}.pt'
        progress['bestCheckpointSha256'] = None
        selected = output / progress['bestCheckpoint']
        checkpoint(selected)
        progress['bestCheckpointSha256'] = digest(selected)

    if not args.resume:
        metrics, predictions = evaluate(model, validation_data, validation_rows)
        require(predictions['rowIndices'] == reference['rowIndices'], 'Epoch-zero reference rows differ')
        difference = float(np.max(np.abs(np.asarray(predictions['probabilities']) - np.asarray(reference['probabilities']))))
        atomic_json(output / 'epoch-zero-predictions.json', predictions)
        atomic_json(output / 'epoch-zero.json', {'evaluation': metrics, 'referenceMaximumAbsoluteProbabilityDifference': difference,
            'comparison': 'Raw float32 pooling/device arithmetic versus frozen CPU float64-accumulated pooling; before updates',
            'eligibleForSelection': True, 'predictionsSha256': digest(output / 'epoch-zero-predictions.json')})
        require(difference <= recipe['maximumEpochZeroProbabilityDifference'], 'Epoch-zero raw/frozen discrepancy exceeds declared limit')
        progress['bestLoss'] = frozen.selection_loss(metrics, args.regime)
        progress['history'] = [{'epoch': 0, 'evaluation': metrics, 'selectionMacroTargetLogLoss': progress['bestLoss'], 'updates': 0}]
        progress.update(epochZeroSha256=digest(output / 'epoch-zero.json'),
                        epochZeroPredictionsSha256=digest(output / 'epoch-zero-predictions.json'))
        select(0)
        checkpoint(output / 'last.pt')
        atomic_json(output / 'history.json', progress['history'])

    while progress['epoch'] <= recipe['maximumEpochs'] and progress['epoch'] - progress['bestEpoch'] <= recipe['patienceEpochs']:
        epoch = progress['epoch']
        if not progress['order']:
            progress['order'] = generator.permutation(fit_data.clip_ids).tolist()
        model.train()
        while progress['cursor'] < len(progress['order']):
            ids = progress['order'][progress['cursor']:progress['cursor'] + recipe['gradientAccumulationClips']]
            loss, count, norm = update_group(model, optimizer, fit_data, ids, recipe['maximumGradientNorm'])
            progress['lossSum'] += loss
            progress['targetCount'] += count
            progress['cursor'] += len(ids)
            progress['updates'] += 1
            if progress['updates'] % recipe['checkpointEveryUpdates'] == 0:
                checkpoint(output / 'last.pt')
                atomic_json(output / 'status.json', {'complete': False, 'pid': os.getpid(), 'epoch': epoch,
                    'clipsDone': progress['cursor'], 'clipsTotal': len(progress['order']), 'updates': progress['updates'],
                    'gradientNorm': norm, 'elapsedSeconds': progress['elapsedSeconds']})
        metrics, _ = evaluate(model, validation_data, validation_rows)
        value = frozen.selection_loss(metrics, args.regime)
        require(np.isfinite(value), 'Nonfinite validation selection loss')
        improved = value < progress['bestLoss'] - recipe['minimumImprovement']
        progress['history'].append({'epoch': epoch, 'trainPerRaterLogLoss': progress['lossSum'] / progress['targetCount'],
            'evaluation': metrics, 'selectionMacroTargetLogLoss': value, 'updates': progress['updates']})
        progress.update(epoch=epoch + 1, order=[], cursor=0, lossSum=0., targetCount=0)
        if improved:
            progress.update(bestEpoch=epoch, bestLoss=value)
            select(epoch)
        guard(config)
        checkpoint(output / 'last.pt')
        atomic_json(output / 'history.json', progress['history'])
        print(json.dumps({'epoch': epoch, 'selectionMacroTargetLogLoss': value, 'bestEpoch': progress['bestEpoch']}), flush=True)

    chosen = output / progress['bestCheckpoint']
    require(digest(chosen) == progress['bestCheckpointSha256'], 'Selected checkpoint changed')
    temporary = output / 'best.pt.tmp'
    shutil.copyfile(chosen, temporary)
    temporary.replace(output / 'best.pt')
    saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
    model.restore_adapted_state(saved['encoder'])
    model.head.load_state_dict(saved['head'], strict=True)
    metrics, predictions = evaluate(model, validation_data, validation_rows)
    require(frozen.selection_loss(metrics, args.regime) == progress['bestLoss'], 'Restored selected score differs')
    require(digest(output / 'config.json') == config_sha, 'Output configuration changed during fitting')
    atomic_json(output / 'predictions.json', predictions)
    verify_epoch_zero(output, progress)
    progress['elapsedSeconds'] = previous_elapsed + time.perf_counter() - started
    return progress, metrics, predictions


@contextmanager
def device_lock(device):
    if device != 'mps':
        yield
        return
    with (BASE / 'adaptation-mps.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def train(args):
    require(args.output.resolve().is_relative_to((HERE / 'outputs').resolve())
            and args.output.exists() == args.resume, 'Choose a fresh run or explicitly resume it')
    recipe = read_json(RECIPE)
    torch.set_num_threads(recipe['threads'])
    random.seed(recipe['seed'])
    torch.manual_seed(recipe['seed'])
    os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
    started = time.perf_counter()
    with device_lock(args.device):
        data, saved, directory, arm = prepare(args, recipe)
        model, processor = load_model(data, saved, arm['upperEncoderLayers'])
        frozen_before = frozen_parameter_digest(model.encoder)
        model.to(args.device)
        fit_data = RawTargetData(data, data['fit'], processor, args.device)
        validation_data = RawTargetData(data, data['validation'], processor, args.device)
        fit_data.verify_audio()
        validation_data.verify_audio()
        groups = [{'params': list(model.head.parameters()), 'lr': recipe['headLearningRate']}]
        if arm['upperEncoderLayers']:
            groups.append({'params': [p for p in model.encoder.parameters() if p.requires_grad], 'lr': arm['backboneLearningRate']})
        optimizer = torch.optim.AdamW(groups, weight_decay=recipe['weightDecay'])
        config = {'output': str(args.output.resolve()), 'regime': args.regime, 'arm': args.arm, 'device': args.device,
            'recipeSha256': digest(RECIPE), 'sourceSha256': source_hashes(), 'inputFiles': data['bindings'],
            'fitRows': data['fit'], 'validationRows': data['validation'], 'selectionRows': data['selection'],
            'frozenEncoderSha256': frozen_before, 'trainableEncoderNames': model.trainable_encoder_names,
            'trainableEncoderParameters': sum(p.numel() for p in model.encoder.parameters() if p.requires_grad),
            'trainableHeadParameters': sum(p.numel() for p in model.head.parameters()),
            'warmStart': recipe['warmStarts'][args.regime], 'torch': str(torch.__version__), 'numpy': np.__version__,
            'phase': 'inner', 'authorPartition': 'train', 'outerOutcomesUsed': False,
            'authorTestInferencePerformed': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
        guard(config)
        if args.resume:
            require(read_json(args.output / 'config.json') == config, 'Resume configuration differs')
        else:
            args.output.mkdir(parents=True, mode=0o700)
            atomic_json(args.output / 'config.json', config)
        prior = read_json(directory / 'prior.json')
        if args.resume:
            require(read_json(args.output / 'prior.json') == prior, 'Resume same-fit prior changed')
        else:
            atomic_json(args.output / 'prior.json', prior)
        try:
            progress, metrics, _ = fit_loop(model, optimizer, fit_data, validation_data, data['validation'], args,
                                           recipe, config, read_json(directory / 'predictions.json'))
            require(frozen_parameter_digest(model.encoder) == frozen_before, 'Frozen encoder parameters changed')
            guard(config)
            require(digest(args.output / 'config.json') == progress['configSha256'], 'Output configuration changed before publication')
            report = {'complete': True, 'phase': 'inner', 'configSha256': progress['configSha256'],
                **{key + 'Sha256': digest(args.output / name) for key, name in
                   (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'),
                    ('prior', 'prior.json'), ('epochZero', 'epoch-zero.json'))},
                'bestEpoch': progress['bestEpoch'], 'epochsRun': len(progress['history']) - 1,
                'updates': progress['updates'], 'bestSelectionMacroLogLoss': progress['bestLoss'],
                'evaluation': metrics, 'sameFitPriorEvaluation': prior['evaluation'],
                'epochZero': read_json(args.output / 'epoch-zero.json'), 'frozenParametersUnchanged': True,
                'elapsedFitLoopSeconds': progress['elapsedSeconds'], 'currentInvocationSeconds': time.perf_counter() - started,
                'outerOutcomesUsed': False, 'authorTestInferencePerformed': False,
                'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
            atomic_json(args.output / 'report.json', report)
            atomic_json(args.output / 'status.json', {'complete': True, 'bestEpoch': progress['bestEpoch'],
                                                    'epochsRun': report['epochsRun']})
            return report
        except BaseException as error:
            atomic_json(args.output / 'status.json', {'complete': False, 'failure': repr(error), 'pid': os.getpid(),
                'resumeRule': 'Explicit resume from last completed persisted optimizer boundary; no partial update is committed'})
            raise


def replay(output):
    config = read_json(output / 'config.json')
    guard(config)
    recipe = read_json(RECIPE)
    args = argparse.Namespace(**{name: config[name] for name in ('regime', 'arm', 'device')}, output=output, resume=False)
    torch.set_num_threads(recipe['threads'])
    with device_lock(args.device):
        data, warm, _, arm = prepare(args, recipe)
        require(config['fitRows'] == data['fit'] and config['validationRows'] == data['validation']
                and config['selectionRows'] == data['selection'] and config['inputFiles'] == data['bindings'], 'Replay rows/bindings differ')
        model, processor = load_model(data, warm, arm['upperEncoderLayers'])
        require(frozen_parameter_digest(model.encoder) == config['frozenEncoderSha256'], 'Replay frozen encoder differs')
        model.to(args.device)
        report = read_json(output / 'report.json')
        require(report['complete'] is True and report['configSha256'] == digest(output / 'config.json')
                and all(report[key + 'Sha256'] == digest(output / name) for key, name in
                    (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'),
                     ('prior', 'prior.json'), ('epochZero', 'epoch-zero.json'))), 'Replay output digests differ')
        saved = torch.load(output / 'best.pt', map_location='cpu', weights_only=True)
        require(saved['configSha256'] == digest(output / 'config.json') and saved['progress']['bestEpoch'] == report['bestEpoch']
                and saved['progress']['bestLoss'] == report['bestSelectionMacroLogLoss']
                and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']), 'Replay checkpoint selection/moments differ')
        model.restore_adapted_state(saved['encoder'])
        model.head.load_state_dict(saved['head'], strict=True)
        verify_epoch_zero(output, saved['progress'])
        validation = RawTargetData(data, data['validation'], processor, args.device)
        validation.verify_audio()
        metrics, predictions = evaluate(model, validation, data['validation'])
        require(predictions == read_json(output / 'predictions.json') and metrics == report['evaluation'], 'Same-device raw checkpoint replay differs')
        guard(config)
        result = {'exact': True, 'device': args.device, 'checkpointSha256': report['checkpointSha256'],
                  'rows': len(data['validation']), 'evaluation': metrics}
        atomic_json(output / 'replay.json', result)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    fit = commands.add_parser('train')
    fit.add_argument('--output', type=Path, required=True)
    fit.add_argument('--regime', choices=['all-age', 'child-only'], required=True)
    fit.add_argument('--arm', choices=['head-only', 'upper1-lr1e-6', 'upper1-lr3e-6'], required=True)
    fit.add_argument('--device', choices=['cpu', 'mps'], default='mps')
    fit.add_argument('--resume', action='store_true')
    check = commands.add_parser('replay')
    check.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    result = train(arguments) if arguments.command == 'train' else replay(arguments.output)
    print(json.dumps({'complete': result.get('complete', result.get('exact'))}), flush=True)
