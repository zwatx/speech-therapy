"""Partial encoder adaptation for train-corpus canonical-position rating research.

Every acoustic forward contains one unpadded clip. Only the last one or two
transformer layers and the phone-conditioned head receive updates. The encoder
stays in evaluation mode, disabling backbone dropout, layerdrop and SpecAugment.
Frozen-cache moments are fitted on the current fit speakers and then held fixed.
Neither contextual attention nor these subjective ratings identify produced phones.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import time

import numpy as np
import torch
from torch import nn

from encoders import load_encoder
from multiphone_cache import atomic_json, digest
from multiphone_data import TARGETS
from multiphone_train import (HEADS, StudyData, distribution_metrics, save_checkpoint,
                              valid_counts, verify_partitions)
from speechocean_r_probe import AUDIO, read_rating_pcm

HERE = Path(__file__).resolve().parent
SOURCES = ('multiphone_adapt.py', 'multiphone_models.py', 'multiphone_train.py',
           'multiphone_cache.py', 'multiphone_data.py', 'encoders.py', 'speechocean_r_probe.py')


def configure_upper_layers(encoder: nn.Module, count: int) -> list[str]:
    """Keep the pretrained lower encoder fixed; expose explicit trainable names."""
    layers = encoder.encoder.layers
    if count not in (1, 2) or count > len(layers):
        raise ValueError('Only the upper one or two encoder layers may adapt')
    encoder.requires_grad_(False).eval()
    for layer in layers[-count:]:
        layer.requires_grad_(True)
    names = [name for name, value in encoder.named_parameters() if value.requires_grad]
    if not names:
        raise ValueError('No trainable upper encoder parameters')
    return names


class AdaptedRatingModel(nn.Module):
    def __init__(self, encoder, head, mean: torch.Tensor, std: torch.Tensor, upper_layers: int):
        super().__init__()
        if (mean.shape != (768,) or std.shape != (768,) or not torch.isfinite(mean).all()
                or not torch.isfinite(std).all() or not (std > 0).all()):
            raise ValueError('Invalid fit-only normalization')
        self.encoder = encoder
        self.head = head
        self.register_buffer('mean', mean.clone())
        self.register_buffer('std', std.clone())
        self.trainable_encoder_names = configure_upper_layers(encoder, upper_layers)

    def train(self, mode: bool = True):
        super().train(mode)
        self.encoder.eval()
        return self

    def forward(self, inputs: dict, phones: torch.Tensor) -> torch.Tensor:
        if inputs['input_values'].ndim != 2 or inputs['input_values'].shape[0] != 1:
            raise ValueError('Encoder processing must remain single clip without batch padding')
        if not 1 <= phones.shape[-1] <= 23 or (phones < 0).any() or (phones >= 23).any():
            raise ValueError('Only eligible targets may be scored')
        frames = self.encoder(**inputs).last_hidden_state
        if frames.ndim != 3 or frames.shape[0] != 1 or frames.shape[2] != 768:
            raise ValueError('Unexpected contextual feature shape')
        normalized = (frames-self.mean)/self.std
        mask = torch.ones(frames.shape[:2], dtype=torch.bool, device=frames.device)
        target_mask = torch.ones_like(phones, dtype=torch.bool)
        return self.head(normalized, mask, phones, target_mask)[0]

    def adapted_state(self) -> dict:
        parameters = dict(self.encoder.named_parameters())
        return {name: parameters[name].detach().cpu().clone() for name in self.trainable_encoder_names}

    def restore_adapted_state(self, values: dict) -> None:
        if set(values) != set(self.trainable_encoder_names):
            raise ValueError('Checkpoint changes the allowed encoder parameters')
        parameters = dict(self.encoder.named_parameters())
        with torch.no_grad():
            for name, value in values.items():
                parameter = parameters[name]
                if value.shape != parameter.shape or not torch.isfinite(value).all():
                    raise ValueError('Invalid adapted encoder checkpoint tensor')
                parameter.copy_(value)


class RawStudyData:
    def __init__(self, cohort: dict, selected_rows: list[int], processor, device: str):
        self.rows = cohort['rows']
        self.clips = cohort['clips']
        self.processor = processor
        self.device = device
        self.grouped = defaultdict(list)
        if len(set(selected_rows)) != len(selected_rows):
            raise ValueError('Duplicate supervised rows')
        for index in selected_rows:
            if type(index) is not int or not 0 <= index < len(self.rows):
                raise ValueError('Invalid row index')
            row = self.rows[index]
            target = row['targetId']
            if (row['trainingEligible'] is not True or type(target) is not int
                    or not 0 <= target < 23 or row['targetPhone'] != TARGETS[target]
                    or not valid_counts(np.asarray([row['raterCounts']], dtype=float))):
                raise ValueError('Unsupported target or invalid five-rater label')
            clip = self.clips[row['clipIndex']]
            if row['clipId'] != clip['id'] or row['speakerId'] != clip['speakerId']:
                raise ValueError('Row is not bound to its audio clip and speaker')
            self.grouped[row['clipIndex']].append(index)
        self.clip_ids = sorted(self.grouped)
        for indices in self.grouped.values():
            targets = [self.rows[index]['targetId'] for index in indices]
            if len(set(targets)) != len(targets):
                raise ValueError('Target occurs more than once in a clip')

    def verify_audio(self) -> None:
        # Independently bind selected IDs to the official author-training map.
        from speechocean_audit import pinned_bytes
        mapping = HERE/'outputs/speechocean762-metadata-v1/train/utt2spk'
        pinned_bytes(mapping.parent.parent, 'train/utt2spk')
        train_map = dict(line.split() for line in mapping.read_text().splitlines())
        for index in self.clip_ids:
            clip = self.clips[index]
            clip_id = clip['id']
            if not re.fullmatch(r'\d{9}', clip_id) or train_map.get(clip_id) != clip['speakerId']:
                raise ValueError('Raw audio must belong to the verified author-training partition')
            canonical = AUDIO/'WAVE'/('SPEAKER'+clip['speakerId'])/(clip_id+'.WAV')
            path = Path(clip['audioPath'])
            if path.resolve() != canonical.resolve() or digest(path) != clip['audioSha256']:
                raise ValueError('Raw audio path or source hash differs')

    def clip(self, index: int):
        clip = self.clips[index]
        samples = read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
        processed = self.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt')
        inputs = {name: value.to(self.device) for name, value in processed.items()}
        indices = self.grouped[index]
        phones = torch.tensor([[self.rows[row]['targetId'] for row in indices]],
                              dtype=torch.long, device=self.device)
        targets = torch.tensor([self.rows[row]['raterCounts'] for row in indices],
                               dtype=torch.float32, device=self.device)/5
        return inputs, phones, targets, indices


@torch.no_grad()
def evaluate(model: AdaptedRatingModel, data: RawStudyData, selected_rows: list[int]) -> tuple[dict, dict]:
    model.eval()
    selected = set(selected_rows)
    outputs = {}
    for index in sorted({data.rows[row]['clipIndex'] for row in selected_rows}):
        inputs, phones, _, indices = data.clip(index)
        values = model(inputs, phones).softmax(-1).cpu().numpy()
        outputs.update((row, value) for row, value in zip(indices, values, strict=True) if row in selected)
    ordered = sorted(outputs)
    if set(ordered) != selected:
        raise ValueError('Evaluation did not cover every selected row')
    probabilities = np.asarray([outputs[index] for index in ordered], dtype=np.float64)
    counts = np.asarray([data.rows[index]['raterCounts'] for index in ordered], dtype=np.float64)
    result = distribution_metrics(probabilities, counts)
    per_target = {}
    for phone in sorted({data.rows[index]['targetPhone'] for index in ordered}):
        mask = np.asarray([data.rows[index]['targetPhone'] == phone for index in ordered])
        per_target[phone] = distribution_metrics(probabilities[mask], counts[mask])
    result['perTarget'] = per_target
    result['macroTargetLogLoss'] = float(np.mean([entry['perRaterLogLoss'] for entry in per_target.values()]))
    for name, condition in [('ages6to12', lambda age: 6 <= age <= 12), ('ages13plus', lambda age: age >= 13)]:
        mask = np.asarray([condition(data.rows[index]['age']) for index in ordered])
        result[name] = distribution_metrics(probabilities[mask], counts[mask]) if mask.any() else None
    return result, {'rowIndices': ordered, 'probabilities': probabilities.tolist()}


def update_group(model, optimizer, data, clip_ids: list[int], max_gradient_norm: float) -> tuple[float, int, float]:
    """Accumulate individual clips, weighting every target row equally per update."""
    count = sum(len(data.grouped[index]) for index in clip_ids)
    if not count:
        raise ValueError('Optimizer update has no supervised targets')
    optimizer.zero_grad(set_to_none=True)
    total = 0.0
    for index in clip_ids:
        inputs, phones, targets, _ = data.clip(index)
        loss_sum = -(targets*model(inputs, phones).log_softmax(-1)).sum()
        if not torch.isfinite(loss_sum):
            raise ValueError('Nonfinite training loss')
        (loss_sum/count).backward()
        total += float(loss_sum.detach().cpu())
    parameters = [value for value in model.parameters() if value.requires_grad]
    gradient_norm = torch.nn.utils.clip_grad_norm_(parameters, max_gradient_norm, error_if_nonfinite=True)
    optimizer.step()
    if any(not torch.isfinite(parameter).all() for parameter in parameters):
        raise ValueError('Optimizer produced nonfinite parameters')
    return total, count, float(gradient_norm.detach().cpu())


def read_study(args) -> tuple[dict, list[int], list[int]]:
    cohort = json.loads(args.cohort.read_text())
    splits = json.loads(args.splits.read_text())
    canonical = hashlib.sha256(json.dumps(cohort, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if splits['cohortCanonicalSha256'] != canonical:
        raise ValueError('Splits are not bound to this exact cohort')
    fold = splits['folds'][args.fold]
    verify_partitions(cohort, fold)
    names = ('innerFitRows', 'innerValidationRows') if args.phase == 'inner' else ('outerFitRows', 'outerHoldoutRows')
    return cohort, fold[names[0]], fold[names[1]]


def fit_normalization(cohort, cache: Path, fit_rows: list[int], cohort_path: Path, identity: dict):
    # StudyData reads only fit feature files here. Validation never fits moments.
    frozen = StudyData(cohort, cache, fit_rows)
    if frozen.config['cohortSha256'] != digest(cohort_path) or frozen.config['encoder'] != identity:
        raise ValueError('Frozen-cache moments have a different cohort or encoder')
    mean, std = frozen.normalization(frozen.clip_ids)
    return mean, std, frozen.index_sha256


def initialize_warm_head(path: Path, args, model, cache_index_sha: str) -> dict:
    config_path = path.parent/'config.json'
    source = json.loads(config_path.read_text())
    expected = {'cohortSha256': digest(args.cohort), 'splitsSha256': digest(args.splits),
                'cacheIndexSha256': cache_index_sha, 'fold': args.fold, 'phase': args.phase,
                'head': args.head, 'hidden': args.hidden, 'dropout': args.dropout, 'seed': args.seed}
    if any(source.get(name) != value for name, value in expected.items()):
        raise ValueError('Frozen-head warm start is not bound to the same fold, fit split and architecture')
    assert_sources(source)
    saved = torch.load(path, map_location='cpu', weights_only=True)
    if saved.get('configSha256') != digest(config_path):
        raise ValueError('Frozen-head checkpoint config binding differs')
    report_path = path.parent/'report.json'
    report = json.loads(report_path.read_text())
    if (path.name != 'best.pt' or report.get('configSha256') != digest(config_path)
            or report.get('checkpointSha256') != digest(path) or report.get('bestEpoch') != saved['epoch']):
        raise ValueError('Warm start must use the completed frozen run best checkpoint')
    if not torch.equal(saved['mean'], model.mean.cpu()) or not torch.equal(saved['std'], model.std.cpu()):
        raise ValueError('Frozen-head normalization differs from this fit split')
    model.head.load_state_dict(saved['model'], strict=True)
    return {'path': str(path.resolve()), 'sha256': digest(path), 'configSha256': digest(config_path),
            'reportSha256': digest(report_path), 'epoch': saved['epoch']}


def selected_epochs(args) -> tuple[int, dict | None]:
    if args.phase == 'inner':
        if args.selection is not None:
            raise ValueError('Inner fitting cannot use a selection report')
        return args.epochs, None
    if args.selection is None:
        raise ValueError('Outer refitting requires an explicit completed inner selection report')
    selected = json.loads(args.selection.read_text())
    config_path = args.selection.parent/'config.json'
    source = json.loads(config_path.read_text())
    if (selected.get('configSha256') != digest(config_path) or source.get('phase') != 'inner'
            or selected.get('complete') is not True):
        raise ValueError('Invalid inner selection report')
    assert_sources(source)
    if selected.get('checkpointSha256') != digest(args.selection.parent/'best.pt'):
        raise ValueError('Selected inner checkpoint differs from its report')
    keys = ('encoder', 'fold', 'seed', 'head', 'hidden', 'dropout', 'upper_layers',
            'backbone_lr', 'head_lr', 'weight_decay', 'accumulation_clips', 'max_gradient_norm')
    if (any(source.get(key) != getattr(args, key) for key in keys)
            or source['cohortSha256'] != digest(args.cohort) or source['splitsSha256'] != digest(args.splits)
            or bool(source.get('warm_head')) != bool(args.warm_head)):
        raise ValueError('Outer refit differs from the selected inner configuration')
    epoch = selected['bestEpoch']
    if type(epoch) is not int or epoch < 1:
        raise ValueError('Selected epoch count is invalid')
    if args.warm_head:
        inner_path = Path(source['warmStart']['path'])
        inner_config_path = inner_path.parent/'config.json'
        outer_config_path = args.warm_head.parent/'config.json'
        inner_head = json.loads(inner_config_path.read_text())
        outer_head = json.loads(outer_config_path.read_text())
        recipe_keys = ('head', 'hidden', 'dropout', 'seed', 'fold', 'lr', 'weight_decay', 'batch_size',
                       'sourceSha256', 'cohortSha256', 'splitsSha256', 'cacheIndexSha256')
        if (digest(inner_path) != source['warmStart']['sha256']
                or digest(inner_config_path) != source['warmStart']['configSha256']
                or inner_head.get('phase') != 'inner' or outer_head.get('phase') != 'outer'
                or any(inner_head.get(key) != outer_head.get(key) for key in recipe_keys)
                or outer_head.get('epochs') != source['warmStart']['epoch']):
            raise ValueError('Outer warm head must refit the exact selected inner frozen-head recipe')
    return epoch, {'path': str(args.selection.resolve()), 'sha256': digest(args.selection)}


def rng_state(generator: np.random.Generator, device: str) -> dict:
    state = {'torch': torch.get_rng_state(), 'numpy': generator.bit_generator.state, 'python': random.getstate()}
    if device == 'mps':
        state['mps'] = torch.mps.get_rng_state()
    return state


def restore_rng(state: dict, generator: np.random.Generator, device: str) -> None:
    torch.set_rng_state(state['torch'].cpu())
    generator.bit_generator.state = state['numpy']
    random.setstate(state['python'])
    if device == 'mps':
        torch.mps.set_rng_state(state['mps'].cpu())


def assert_sources(config: dict) -> None:
    if any(digest(HERE/name) != value for name, value in config['sourceSha256'].items()):
        raise ValueError('Implementation changed during the run; choose a new experiment')


def train(args) -> dict:
    if (args.epochs < 1 or args.patience < 1 or args.accumulation_clips < 1 or args.save_every_updates < 1
            or not 0 < args.backbone_lr <= 0.001 or not 0 < args.head_lr <= 0.1
            or not math.isfinite(args.weight_decay) or args.weight_decay < 0
            or not math.isfinite(args.max_gradient_norm) or args.max_gradient_norm <= 0):
        raise ValueError('Invalid adaptation optimizer budget')
    if args.device == 'mps' and not torch.backends.mps.is_available():
        raise ValueError('MPS unavailable')
    if not args.output.resolve().is_relative_to((HERE/'outputs').resolve()):
        raise ValueError('Keep private research artifacts in ignored local outputs')
    if args.output.exists() != args.resume:
        raise ValueError('Use a fresh output directory, or explicitly resume an existing run')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    started = time.perf_counter()
    cohort, fit_rows, eval_rows = read_study(args)
    epochs, selection = selected_epochs(args)
    encoder = load_encoder(args.encoder, HERE/'outputs/model-cache', allow_download=False)
    mean, std, cache_sha = fit_normalization(cohort, args.cache, fit_rows, args.cohort, encoder.identity)
    model = AdaptedRatingModel(encoder.model, HEADS[args.head](hidden_dim=args.hidden, dropout=args.dropout),
                               mean, std, args.upper_layers).to(args.device)
    warm_start = initialize_warm_head(args.warm_head, args, model, cache_sha) if args.warm_head else None
    # Outer evaluation audio/labels are not opened until all fixed fitting epochs finish.
    fit_data = RawStudyData(cohort, fit_rows, encoder.processor, args.device)
    fit_data.verify_audio()
    eval_data = None
    if args.phase == 'inner':
        eval_data = RawStudyData(cohort, eval_rows, encoder.processor, args.device)
        eval_data.verify_audio()
    optimizer = torch.optim.AdamW([
        {'params': [value for value in model.encoder.parameters() if value.requires_grad], 'lr': args.backbone_lr},
        {'params': list(model.head.parameters()), 'lr': args.head_lr},
    ], weight_decay=args.weight_decay)
    config = {name: str(value.resolve()) if isinstance(value, Path) else value
              for name, value in vars(args).items() if name not in ('resume', 'replay')}
    config.update({'epochs': epochs, 'cohortSha256': digest(args.cohort), 'splitsSha256': digest(args.splits),
                   'cacheIndexSha256': cache_sha, 'encoderIdentity': encoder.identity, 'warmStart': warm_start,
                   'selection': selection, 'sourceSha256': {name: digest(HERE/name) for name in SOURCES},
                   'torch': str(torch.__version__), 'numpy': np.__version__,
                   'normalization': 'fixed frame moments from fit speakers only in pinned frozen encoder cache',
                   'encoderMode': 'eval; upper transformer layers receive gradients; lower weights/preprocessor frozen',
                   'authorPartition': 'train', 'authorTestInferencePerformed': False,
                   'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
                   'trainableEncoderNames': model.trainable_encoder_names,
                   'trainableEncoderParameters': sum(value.numel() for value in model.encoder.parameters() if value.requires_grad),
                   'trainableHeadParameters': sum(value.numel() for value in model.head.parameters()),
                   'fitRows': fit_rows, 'evaluationRows': eval_rows})
    config_path = args.output/'config.json'
    progress = {'epoch': 1, 'order': [], 'cursor': 0, 'lossSum': 0., 'targetCount': 0,
                'updates': 0, 'bestLoss': None, 'bestEpoch': 0, 'bestCheckpoint': None,
                'bestCheckpointSha256': None, 'history': [], 'elapsedSeconds': 0.}
    if args.resume:
        if json.loads(config_path.read_text()) != config:
            raise ValueError('Resume configuration or source differs from the saved run')
        saved = torch.load(args.output/'last.pt', map_location='cpu', weights_only=True)
        if saved.get('configSha256') != digest(config_path):
            raise ValueError('Resume checkpoint config binding differs')
        model.restore_adapted_state(saved['encoder'])
        model.head.load_state_dict(saved['head'], strict=True)
        optimizer.load_state_dict(saved['optimizer'])
        progress = saved['progress']
        if progress['bestCheckpoint'] is not None:
            best_path = args.output/progress['bestCheckpoint']
            if (not best_path.resolve().is_relative_to(args.output.resolve())
                    or digest(best_path) != progress['bestCheckpointSha256']):
                raise ValueError('Resume selected checkpoint binding differs')
        restore_rng(saved['rng'], generator, args.device)
        atomic_json(args.output/'history.json', progress['history'])
    else:
        args.output.mkdir(parents=True)
        atomic_json(config_path, config)
    old_elapsed = progress['elapsedSeconds']

    def checkpoint(path: Path):
        progress['elapsedSeconds'] = old_elapsed + time.perf_counter()-started
        save_checkpoint(path, {'schemaVersion': 1, 'encoder': model.adapted_state(),
                              'head': model.head.state_dict(), 'mean': model.mean.detach().cpu(),
                              'std': model.std.detach().cpu(), 'optimizer': optimizer.state_dict(),
                              'rng': rng_state(generator, args.device), 'progress': progress,
                              'configSha256': digest(config_path), 'encoderIdentity': encoder.identity})

    while progress['epoch'] <= epochs:
        epoch = progress['epoch']
        if args.phase == 'inner' and progress['bestEpoch'] and epoch-progress['bestEpoch'] > args.patience:
            break
        if not progress['order']:
            progress['order'] = generator.permutation(fit_data.clip_ids).tolist()
        epoch_started = time.perf_counter()
        model.train()
        while progress['cursor'] < len(progress['order']):
            ids = progress['order'][progress['cursor']:progress['cursor']+args.accumulation_clips]
            loss, count, norm = update_group(model, optimizer, fit_data, ids, args.max_gradient_norm)
            progress['lossSum'] += loss
            progress['targetCount'] += count
            progress['cursor'] += len(ids)
            progress['updates'] += 1
            if progress['updates'] % args.save_every_updates == 0:
                checkpoint(args.output/'last.pt')
                status = {'pid': os.getpid(), 'epoch': epoch, 'clipsDone': progress['cursor'],
                          'clipsTotal': len(progress['order']), 'updates': progress['updates'],
                          'gradientNorm': norm, 'elapsedSeconds': progress['elapsedSeconds'], 'complete': False}
                if args.device == 'mps':
                    status['mpsAllocatedBytes'] = torch.mps.current_allocated_memory()
                    status['mpsDriverBytes'] = torch.mps.driver_allocated_memory()
                atomic_json(args.output/'status.json', status)
                print(json.dumps(status), flush=True)
        record = {'epoch': epoch, 'trainPerRaterLogLoss': progress['lossSum']/progress['targetCount'],
                  'remainingEpochSeconds': time.perf_counter()-epoch_started, 'updates': progress['updates']}
        if args.phase == 'inner':
            record['validation'], _ = evaluate(model, eval_data, eval_rows)
            value = record['validation']['macroTargetLogLoss']
        else:
            value = -float(epoch)
        improved = progress['bestLoss'] is None or value < progress['bestLoss']-1e-7
        if improved:
            progress['bestLoss'], progress['bestEpoch'] = value, epoch
        progress['history'].append(record)
        progress.update({'epoch': epoch+1, 'order': [], 'cursor': 0, 'lossSum': 0., 'targetCount': 0})
        assert_sources(config)
        # A selected checkpoint is immutable before last.pt points to it. A crash
        # on either side leaves last.pt referencing a complete matching selection.
        if improved:
            progress['bestCheckpoint'] = f'selected-epoch-{epoch:04d}.pt'
            progress['bestCheckpointSha256'] = None
            selected_path = args.output/progress['bestCheckpoint']
            checkpoint(selected_path)
            progress['bestCheckpointSha256'] = digest(selected_path)
        checkpoint(args.output/'last.pt')
        atomic_json(args.output/'history.json', progress['history'])
        print(json.dumps(record, allow_nan=False), flush=True)
    selected_path = args.output/progress['bestCheckpoint']
    if digest(selected_path) != progress['bestCheckpointSha256']:
        raise ValueError('Selected checkpoint changed during fitting')
    # best.pt is only a delivery copy; resumability depends on last.pt and its
    # named selection, never on replacing two mutable files simultaneously.
    temporary = args.output/'best.pt.tmp'
    shutil.copyfile(selected_path, temporary)
    temporary.replace(args.output/'best.pt')
    saved = torch.load(selected_path, map_location='cpu', weights_only=True)
    model.restore_adapted_state(saved['encoder'])
    model.head.load_state_dict(saved['head'], strict=True)
    if eval_data is None:
        eval_data = RawStudyData(cohort, eval_rows, encoder.processor, args.device)
        eval_data.verify_audio()
    result, predictions = evaluate(model, eval_data, eval_rows)
    assert_sources(config)
    atomic_json(args.output/'predictions.json', predictions)
    report = {'complete': True, 'configSha256': digest(config_path), 'checkpointSha256': digest(args.output/'best.pt'),
              'bestEpoch': progress['bestEpoch'], 'epochsRun': len(progress['history']), 'updates': progress['updates'],
              'evaluation': result, 'elapsedSeconds': old_elapsed+time.perf_counter()-started,
              'evaluationRole': 'inner selection' if args.phase == 'inner' else 'exploratory outer speaker holdout',
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False}
    atomic_json(args.output/'report.json', report)
    atomic_json(args.output/'status.json', {'complete': True, 'epochsRun': len(progress['history']),
                                          'elapsedSeconds': report['elapsedSeconds']})
    return report


def replay(output: Path, device: str) -> dict:
    """Load pinned base + adapted tensors and regenerate the saved evaluation."""
    config_path = output/'config.json'
    config = json.loads(config_path.read_text())
    assert_sources(config)
    args = argparse.Namespace(**config)
    args.cohort, args.splits = Path(args.cohort), Path(args.splits)
    if digest(args.cohort) != config['cohortSha256'] or digest(args.splits) != config['splitsSha256']:
        raise ValueError('Replay cohort/splits differ')
    cohort, _, eval_rows = read_study(args)
    if eval_rows != config['evaluationRows']:
        raise ValueError('Replay row set differs')
    saved = torch.load(output/'best.pt', map_location='cpu', weights_only=True)
    if saved['configSha256'] != digest(config_path):
        raise ValueError('Replay checkpoint config binding differs')
    report = json.loads((output/'report.json').read_text())
    if report.get('checkpointSha256') != digest(output/'best.pt'):
        raise ValueError('Replay checkpoint differs from the completed run report')
    encoder = load_encoder(config['encoder'], HERE/'outputs/model-cache', allow_download=False)
    if encoder.identity != config['encoderIdentity'] or saved['encoderIdentity'] != encoder.identity:
        raise ValueError('Replay base encoder differs')
    model = AdaptedRatingModel(encoder.model, HEADS[config['head']](hidden_dim=config['hidden'], dropout=config['dropout']),
                               saved['mean'], saved['std'], config['upper_layers']).to(device)
    model.restore_adapted_state(saved['encoder'])
    model.head.load_state_dict(saved['head'], strict=True)
    data = RawStudyData(cohort, eval_rows, encoder.processor, device)
    data.verify_audio()
    metrics, predictions = evaluate(model, data, eval_rows)
    reference = json.loads((output/'predictions.json').read_text())
    if reference['rowIndices'] != predictions['rowIndices']:
        raise ValueError('Replay prediction indices differ')
    maximum = float(np.abs(np.asarray(reference['probabilities'])-np.asarray(predictions['probabilities'])).max())
    result = {'checkpointSha256': digest(output/'best.pt'), 'device': device, 'evaluation': metrics,
              'maximumAbsoluteProbabilityDifference': maximum, 'rows': len(predictions['rowIndices'])}
    atomic_json(output/'replay.json', result)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    for name in ('cohort', 'splits', 'cache', 'output'):
        result.add_argument('--'+name, type=Path, required=True)
    result.add_argument('--encoder', choices=['wav2vec2-base', 'wavlm-base-plus'], required=True)
    result.add_argument('--head', choices=list(HEADS), default='attention')
    result.add_argument('--phase', choices=['inner', 'outer'], default='inner')
    result.add_argument('--fold', type=int, choices=range(5), default=0)
    result.add_argument('--device', choices=['cpu', 'mps'], default='mps')
    result.add_argument('--upper-layers', type=int, choices=[1, 2], default=1)
    result.add_argument('--seed', type=int, default=7)
    result.add_argument('--hidden', type=int, default=128)
    result.add_argument('--dropout', type=float, default=0.1)
    result.add_argument('--backbone-lr', type=float, default=1e-5)
    result.add_argument('--head-lr', type=float, default=3e-4)
    result.add_argument('--weight-decay', type=float, default=0.01)
    result.add_argument('--max-gradient-norm', type=float, default=5.)
    result.add_argument('--accumulation-clips', type=int, default=4)
    result.add_argument('--epochs', type=int, default=12, help='Inner epoch ceiling; outer count comes from selection')
    result.add_argument('--patience', type=int, default=3)
    result.add_argument('--threads', type=int, default=2)
    result.add_argument('--save-every-updates', type=int, default=25)
    result.add_argument('--warm-head', type=Path)
    result.add_argument('--selection', type=Path, help='Completed inner report required for outer refit')
    result.add_argument('--resume', action='store_true')
    result.add_argument('--replay', action='store_true')
    return result


if __name__ == '__main__':
    arguments = parser().parse_args()
    print(json.dumps(replay(arguments.output, arguments.device) if arguments.replay else train(arguments),
                     allow_nan=False), flush=True)
