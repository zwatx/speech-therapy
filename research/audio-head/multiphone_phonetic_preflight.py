"""Bounded fit-audio MPS measurements before raw phonetic adaptation.

No validation clips, model checkpoints or changed weights are saved. A success
does not establish full-validation numerical parity or an epoch runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

import multiphone_phonetic_adapt as adapt
from multiphone_cache import digest

HERE = Path(__file__).resolve().parent
APPROVED_TRAINER_SHA = '954f95d60fcad34ca127946d70af498de8171094043bf006801f554470e7debf'
APPROVED_RECIPE_SHA = 'f627ed0f308d2c8953a36c8131d8039d2fba4d8745f51bc1b69dcf2ea707931a'


def source_guard():
    adapt.require(digest(HERE / 'multiphone_phonetic_adapt.py') == APPROVED_TRAINER_SHA
                  and digest(adapt.RECIPE) == APPROVED_RECIPE_SHA, 'Reviewed adaptation source/recipe changed')


def cases(data):
    indices = sorted({data['cohort']['rows'][row]['clipIndex'] for row in data['fit']})
    adapt.require(bool(indices), 'No fit clips for gradient preflight')
    longest = max(indices, key=lambda i: (data['cohort']['clips'][i]['sampleCount'], -i))
    return [('first-fit', indices[0]), ('longest-fit', longest)]


def difference(left, right):
    a, b = left.detach().cpu().numpy(), right.detach().cpu().numpy()
    adapt.require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), 'Nonfinite parity outputs')
    return {'maximumAbsoluteProbabilityDifference': float(np.abs(a - b).max()),
            'meanAbsoluteProbabilityDifference': float(np.abs(a - b).mean())}


def updated_names(before, after):
    adapt.require(set(before) == set(after), 'Preflight parameter allowlist changed')
    adapt.require(all(torch.isfinite(value).all() for value in after.values()), 'Nonfinite updated tensors')
    return [name for name in before if not torch.equal(before[name], after[name])]


def measure(output):
    adapt.require(not output.exists() and output.resolve().is_relative_to((HERE / 'outputs').resolve()),
                  'Use a new measurement artifact in ignored outputs')
    source_guard()
    adapt.require(torch.backends.mps.is_available(), 'MPS is unavailable')
    recipe = adapt.read_json(adapt.RECIPE)
    torch.set_num_threads(recipe['threads'])
    record = {'complete': False, 'trainerSha256': APPROVED_TRAINER_SHA, 'recipeSha256': APPROVED_RECIPE_SHA,
              'sourceSha256': digest(Path(__file__)), 'reusedSources': adapt.source_hashes(), 'cases': [],
              'device': 'mps', 'threads': recipe['threads'], 'validationInferencePerformed': False,
              'changedWeightsPersisted': False, 'outerOutcomesUsed': False, 'authorTestInferencePerformed': False,
              'limitation': 'Two steps on each of four fit-clip cases do not establish full-validation parity, an epoch runtime, or generalization.'}
    started = time.perf_counter()
    with adapt.device_lock('mps'):
        for regime in recipe['regimes']:
            args = argparse.Namespace(regime=regime, arm='upper1-lr1e-6', device='mps')
            data, warm, _, arm = adapt.prepare(args, recipe)
            fit_rows = set(data['fit'])
            for label, clip_index in cases(data):
                random.seed(recipe['seed']); torch.manual_seed(recipe['seed'])
                model, processor = adapt.load_model(data, warm, arm['upperEncoderLayers'])
                indices = [i for i in data['fit'] if data['cohort']['rows'][i]['clipIndex'] == clip_index]
                adapt.require(set(indices) <= fit_rows and bool(indices), 'Preflight row is outside the fit partition')
                raw_cpu = adapt.RawTargetData(data, indices, processor, 'cpu')
                raw_cpu.verify_audio()
                inputs, phones, windows, scalars, frames, _, actual_indices = raw_cpu.clip(clip_index)
                adapt.require(actual_indices == indices, 'Preflight target order differs')
                model.eval()
                with torch.no_grad():
                    values, phone_batch, mask, _ = adapt.frozen.batch(data, indices, 'cpu')
                    cached = model.head(values, mask, phone_batch, mask)[:, 0].softmax(-1)
                    cpu_started = time.perf_counter()
                    raw_reference = model(inputs, phones, windows, scalars, frames).softmax(-1)
                    cpu_seconds = time.perf_counter() - cpu_started
                frozen_before = adapt.frozen_parameter_digest(model.encoder)
                upper_before = model.adapted_state()
                head_before = {name: value.detach().cpu().clone() for name, value in model.head.state_dict().items()}
                model.to('mps').eval()
                raw_mps = adapt.RawTargetData(data, indices, processor, 'mps')
                mps_inputs = raw_mps.clip(clip_index)
                torch.mps.synchronize()
                mps_started = time.perf_counter()
                with torch.no_grad():
                    mps_probabilities = model(*mps_inputs[:5]).softmax(-1)
                torch.mps.synchronize()
                mps_seconds = time.perf_counter() - mps_started
                parity = {'cpuRawVsFrozenCache': difference(raw_reference, cached),
                          'mpsRawVsCpuRaw': difference(mps_probabilities, raw_reference),
                          'mpsRawVsFrozenCache': difference(mps_probabilities, cached)}
                adapt.require(parity['mpsRawVsFrozenCache']['maximumAbsoluteProbabilityDifference'] <= recipe['maximumEpochZeroProbabilityDifference'],
                              'Fit-clip MPS/cache parity exceeds the declared numerical limit')
                optimizer = torch.optim.AdamW([
                    {'params': list(model.head.parameters()), 'lr': recipe['headLearningRate']},
                    {'params': [p for p in model.encoder.parameters() if p.requires_grad], 'lr': arm['backboneLearningRate']},
                ], weight_decay=recipe['weightDecay'])
                times, norms, memories = [], [], []
                model.train()
                for _ in range(2):
                    torch.mps.synchronize()
                    tick = time.perf_counter()
                    _, count, norm = adapt.update_group(model, optimizer, raw_mps, [clip_index], recipe['maximumGradientNorm'])
                    torch.mps.synchronize()
                    times.append(time.perf_counter() - tick)
                    norms.append(norm)
                    memories.append({'allocatedBytes': torch.mps.current_allocated_memory(),
                                     'driverBytes': torch.mps.driver_allocated_memory()})
                    adapt.require(count == len(indices) and norm > 0 and np.isfinite(norm), 'No finite nonzero fit-clip gradient')
                upper_changed = updated_names(upper_before, model.adapted_state())
                head_changed = updated_names(head_before, {n: p.detach().cpu() for n, p in model.head.state_dict().items()})
                adapt.require(bool(upper_changed) and bool(head_changed)
                              and all(n.startswith('encoder.layers.23.') for n in upper_changed), 'Expected trainable tensors did not update')
                adapt.require(adapt.frozen_parameter_digest(model.encoder) == frozen_before, 'Frozen encoder parameters changed')
                clip = data['cohort']['clips'][clip_index]
                record['cases'].append({'regime': regime, 'role': label, 'clipId': clip['id'],
                    'audioSha256': clip['audioSha256'], 'durationSeconds': clip['sampleCount'] / 16000,
                    'rowIndices': indices, 'frames': frames, 'cpuRawForwardSeconds': cpu_seconds,
                    'mpsRawForwardSeconds': mps_seconds, 'parityBeforeUpdates': parity, 'optimizerStepSeconds': times,
                    'gradientNorms': norms, 'memoryAfterSteps': memories, 'changedUpperTensors': upper_changed,
                    'changedHeadTensors': head_changed, 'frozenParametersUnchanged': True,
                    'trainableEncoderParameters': sum(p.numel() for p in model.encoder.parameters() if p.requires_grad)})
                del optimizer, model, raw_mps, raw_cpu, mps_inputs, mps_probabilities, upper_before, head_before
                torch.mps.empty_cache()
        source_guard()
        adapt.require(record['reusedSources'] == adapt.source_hashes() and record['sourceSha256'] == digest(Path(__file__)),
                      'Preflight sources changed during measurement')
        adapt.frozen.extraction.guard(data['bindings'])
        record.update(complete=True, elapsedSeconds=time.perf_counter() - started)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x') as stream:
            stream.write(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return record


def preflight(output):
    adapt.require(not output.exists() and output.resolve().is_relative_to((HERE / 'outputs').resolve()),
                  'Use a new measurement artifact in ignored outputs')
    started = time.perf_counter()
    try:
        return measure(output)
    except BaseException as error:
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('x') as stream:
                stream.write(json.dumps({'complete': False, 'failure': repr(error),
                    'elapsedSeconds': time.perf_counter() - started, 'sourceSha256': digest(Path(__file__)),
                    'changedWeightsPersisted': False, 'validationInferencePerformed': False}, indent=2) + '\n')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({'complete': preflight(args.output)['complete']}), flush=True)
