"""Generated-only check of the backend hidden-state boundary before native export.

This does not run CoreML, CTC, heads, audio files, or an accuracy study. It uses
the real backend PhoneticEncoder unchanged. Fixed-length padding is a candidate
representation, not an admitted replacement for that encoder.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RECIPE = HERE / 'experiments/multiphone-phonetic-features-v1.json'
SNAPSHOT = HERE / ('outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/'
                   'snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4')
OLD_POLICY = ROOT / ('work/r-inference-checkpoint-20261012/restart-native-ai-v1/coreml-whisper-v1/'
                     'native-phonetic-converter-draft-v4/policy_v1.py')
VERSIONS = {'torch': '2.8.0', 'transformers': '4.57.6', 'numpy': '2.2.6'}
PATTERNS = ('zeros', 'constant', 'impulse', 'alternating', 'periodicRamp', 'lcgNoise')
LENGTHS = (1600, 16000, 64000)
CAPACITY, WIDTH = 64000, 1024
# Existing converter wrapper budget; a numerical engineering check, not a
# speech/clinical threshold. Neither argument nor observed result can change it.
MAX_ERROR, MEAN_ERROR = 1e-4, 1e-5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    with path.open('x') as stream:
        path.chmod(0o600)
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def frames(length):
    for kernel, stride in zip((10, 3, 3, 3, 3, 2, 2), (5, 2, 2, 2, 2, 2, 2)):
        length = (length - kernel) // stride + 1
    return length


def generated_pcm(pattern, length):
    """Same six deterministic PCM16 definitions as the existing converter."""
    require(pattern in PATTERNS and length in LENGTHS, 'Undeclared generated case')
    state, values = 1, []
    for i in range(length):
        if pattern == 'zeros': value = 0
        elif pattern == 'constant': value = 1024
        elif pattern == 'impulse': value = 16384 if i == length // 2 else 0
        elif pattern == 'alternating': value = 8192 if i % 2 == 0 else -8192
        elif pattern == 'periodicRamp': value = ((i % 257) - 128) * 64
        else:
            state = (1664525 * state + 1013904223) % 2**32
            value = ((state >> 16) - 32768) // 4
        values.append(value)
    return values


def compare_hidden(reference, candidate, expected_frames):
    import numpy as np
    expected = (expected_frames, WIDTH)
    require(reference.shape == candidate.shape == expected, 'Hidden shape differs')
    require(reference.dtype == candidate.dtype == np.float32, 'Hidden dtype differs')
    require(np.isfinite(reference).all() and np.isfinite(candidate).all(), 'Nonfinite hidden state')
    delta = np.abs(reference.astype(np.float64) - candidate.astype(np.float64))
    maximum, mean = float(delta.max()), float(delta.mean())
    # Whole-clip pooling is an observation of the actual backend accumulation
    # rule. It adds no independent tolerance or substitute acceptance rule.
    pooled = np.abs(reference.mean(0, dtype=np.float64).astype(np.float32).astype(np.float64)
                    - candidate.mean(0, dtype=np.float64).astype(np.float32).astype(np.float64))
    return {'maximumAbsoluteError': maximum, 'meanAbsoluteError': mean,
            'pooledMaximumAbsoluteError': float(pooled.max()),
            'pooledMeanAbsoluteError': float(pooled.mean()),
            'passed': maximum <= MAX_ERROR and mean <= MEAN_ERROR}


def local_sources():
    """The static local import closure of the unchanged backend encoder."""
    names = ('multiphone_phonetic_features.py', 'multiphone_cache.py', 'multiphone_local_features.py',
             'encoders.py', 'data.py', 'alignment_pilot.py', 'pipeline.py', 'diagnostics.py', 'multiphone_data.py',
             'speechocean_audit.py', 'speechocean_r_probe.py', 'speechocean_r_label_audit.py',
             'speechocean_r_annotation_sample.py')
    return [Path(__file__).resolve(), RECIPE, OLD_POLICY, *(HERE / name for name in names)]


def prepare(output):
    require(output.parent.resolve().is_relative_to((ROOT / 'work').resolve()), 'Keep output in task-local work')
    output.mkdir(mode=0o700)  # No overwrite, resume, or implicit retry.
    recipe = json.loads(RECIPE.read_text())
    require(recipe['device'] == 'cpu' and recipe['threads'] == 2 and recipe['dtype'] == 'float32'
            and recipe['attentionImplementation'] == 'eager' and recipe['hiddenWidth'] == WIDTH,
            'Backend recipe differs')
    paths = local_sources() + [Path(sys.executable).resolve()]
    for name, expected in recipe['artifactSha256'].items():
        path = SNAPSHOT / name
        require(digest(path) == expected, 'Pinned checkpoint differs')
        paths.append(path)
    for package, expected in VERSIONS.items():
        require(importlib.metadata.version(package) == expected, 'Backend runtime version differs')
        dist = importlib.metadata.distribution(package)
        paths.append(Path(dist.locate_file(f'{package}-{expected}.dist-info/METADATA')))
    installed = Path(importlib.metadata.distribution('transformers').locate_file('transformers'))
    paths.extend(installed / name for name in (
        'modeling_utils.py', 'models/wav2vec2/modeling_wav2vec2.py',
        'models/wav2vec2/feature_extraction_wav2vec2.py', 'feature_extraction_sequence_utils.py'))
    pins = {str(path): digest(path) for path in paths}
    plan = {'schemaVersion': 1, 'purpose': 'generated-only hidden padding boundary',
            'reference': 'Unchanged backend PhoneticEncoder(samples), actual unpadded length',
            'candidate': 'Same processor/model, pad to64000, keep first convolution_frames(length) hidden frames',
            'patterns': list(PATTERNS), 'sampleCounts': list(LENGTHS), 'caseCount': 18,
            'plannedForwards': 36, 'maximumAbsoluteError': MAX_ERROR, 'meanAbsoluteError': MEAN_ERROR,
            'budgetSource': str(OLD_POLICY.relative_to(ROOT)), 'budgetName': 'LIMITS.wrapper',
            'cpuThreads': 2, 'dtype': 'float32', 'attention': 'eager',
            'versions': VERSIONS, 'python': platform.python_version(), 'pins': pins,
            'allCasesRequired': True, 'noTuningOrResultDependentRetry': True,
            'privateAudioUsed': False, 'coreMLExecuted': False, 'ctcExecuted': False,
            'headsExecuted': False, 'accuracyClaimed': False, 'appIntegrationClaimed': False}
    write_json(output / 'plan.json', plan)  # Written before framework imports or forwards.
    return recipe, pins


def guard(pins):
    require(all(digest(Path(path)) == expected for path, expected in pins.items()), 'Bound input changed')


def run(output):
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', TOKENIZERS_PARALLELISM='false')
    recipe, pins = prepare(output)
    rows, calls, started = [], 0, time.perf_counter()
    result = {'complete': False, 'comparisonPassed': False, 'forwardsCompleted': 0, 'cases': rows}
    try:
        import numpy as np
        import torch
        import transformers
        from multiphone_phonetic_features import PhoneticEncoder
        require(torch.__version__.split('+')[0] == VERSIONS['torch']
                and np.__version__ == VERSIONS['numpy'] and transformers.__version__ == VERSIONS['transformers'],
                'Imported backend runtime differs')
        torch.set_num_threads(2)
        encoder = PhoneticEncoder(SNAPSHOT, recipe)
        require(torch.get_num_threads() == 2 and not encoder.model.training
                and encoder.model.config._attn_implementation == 'eager'
                and all(p.dtype == torch.float32 and p.device.type == 'cpu' and not p.requires_grad
                        for p in encoder.model.parameters()), 'Encoder configuration differs')
        result['runtime'] = {'torch': torch.__version__, 'numpy': np.__version__,
                             'transformers': transformers.__version__,
                             'cpuThreads': torch.get_num_threads(),
                             'interopThreads': torch.get_num_interop_threads()}
        for length in LENGTHS:
            for pattern in PATTERNS:
                pcm = np.asarray(generated_pcm(pattern, length), dtype='<i2')
                samples = torch.from_numpy(pcm.astype(np.float32) / 32768)
                count = frames(length)
                row = {'id': f'{pattern}-L{length}', 'sampleCount': length, 'validFrames': count,
                       'pcm16Sha256': hashlib.sha256(pcm.tobytes()).hexdigest(), 'comparisons': []}
                rows.append(row)
                unpadded = encoder.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt')
                padded = encoder.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt',
                                           padding='max_length', max_length=CAPACITY, truncation=False,
                                           return_attention_mask=True)
                require(tuple(unpadded.input_values.shape) == (1, length)
                        and tuple(padded.input_values.shape) == (1, CAPACITY)
                        and tuple(unpadded.attention_mask.shape) == (1, length)
                        and tuple(padded.attention_mask.shape) == (1, CAPACITY)
                        and unpadded.input_values.dtype == padded.input_values.dtype == torch.float32
                        and bool(torch.isfinite(unpadded.input_values).all())
                        and bool(torch.isfinite(padded.input_values).all())
                        and torch.equal(unpadded.input_values, padded.input_values[:, :length])
                        and bool((padded.input_values[:, length:] == 0).all())
                        and bool((unpadded.attention_mask == 1).all())
                        and bool((padded.attention_mask[:, :length] == 1).all())
                        and bool((padded.attention_mask[:, length:] == 0).all()), 'Preprocessing control failed')
                row['preprocessingExact'] = True
                reference = encoder(samples)
                calls += 1
                with torch.inference_mode():
                    full = encoder.model.wav2vec2(**padded).last_hidden_state[0].cpu().numpy()
                calls += 1
                require(full.shape == (frames(CAPACITY), WIDTH) and full.dtype == np.float32
                        and np.isfinite(full).all(), 'Padded full hidden state invalid')
                candidate = full[:count].copy()
                row['comparisons'].append(compare_hidden(reference, candidate, count))
                row['passed'] = row['comparisons'][0]['passed']
                row['fullLengthControl'] = length == CAPACITY
                # Each completed case is retained even if a later case fails or crashes.
                write_json(output / (row['id'] + '.json'), row)
        guard(pins)
        result.update(complete=len(rows) == 18 and calls == 36,
                      comparisonPassed=all(row['passed'] for row in rows))
    except Exception as exc:
        # The exception type suffices for local diagnosis without dumping arrays.
        result['failureType'] = type(exc).__name__
        result['failureMessage'] = str(exc) if isinstance(exc, ValueError) else 'Backend execution failed'
    finally:
        try:
            guard(pins)
            result['pinsUnchanged'] = True
        except Exception:
            result['pinsUnchanged'] = False
            result['complete'] = result['comparisonPassed'] = False
        result.update(forwardsCompleted=calls, wallSeconds=time.perf_counter() - started,
                      privateAudioUsed=False, coreMLExecuted=False, ctcExecuted=False, headsExecuted=False,
                      learnerFeedbackEligible=False, clinicalUseEligible=False, productionUseEligible=False)
        write_json(output / 'result.json', result)
    return 0 if result['complete'] and result['comparisonPassed'] else (2 if result['complete'] else 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(run(args.output))
