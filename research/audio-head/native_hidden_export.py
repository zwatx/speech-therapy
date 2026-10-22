"""Generated-only FP32 hidden export; never load or predict a Core ML model in Python.

Each invocation owns a new private output directory. Numerical limits and cases
are fixed prospectively; failures cannot be retried into an existing directory.
Heavy frameworks are imported only inside the requested stage.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = ROOT / 'work/native-hidden-export-20261015/PLAN.json'
RECIPE = HERE / 'experiments/multiphone-phonetic-features-v1.json'
SNAPSHOT = HERE / ('outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/'
                   'snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4')
PATTERNS = ('zeros', 'constant', 'impulse', 'alternating', 'periodicRamp', 'lcgNoise')
LENGTHS = (1600, 16000, 64000)
EXTRA = (1679, 1680, 1681, 16079, 16080, 16081, 63759, 63760, 63761)
CAPACITY, WIDTH, FULL_FRAMES = 64000, 1024, 199
BUDGETS = {'backendPadding': {'maximum': 1e-4, 'mean': 1e-5},
           'converterVsBackend': {'maximum': 1e-4, 'mean': 1e-5},
           'traceVsConverter': {'maximum': 1e-5, 'mean': 1e-6},
           'nativeVsBackend': {'maximum': 1e-3, 'mean': 1e-4}}
REFERENCE_VERSIONS = {'torch': '2.8.0', 'transformers': '4.57.6', 'numpy': '2.2.6'}
CONVERTER_VERSIONS = dict(REFERENCE_VERSIONS, torch='2.7.0', coremltools='9.0')
LOCAL_MODULES = ('multiphone_phonetic_features.py', 'multiphone_cache.py', 'multiphone_local_features.py',
                 'encoders.py', 'data.py', 'alignment_pilot.py', 'pipeline.py', 'diagnostics.py',
                 'multiphone_data.py', 'speechocean_audit.py', 'speechocean_r_probe.py',
                 'speechocean_r_label_audit.py', 'speechocean_r_annotation_sample.py')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text())


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def pin(path, base=None):
    path = Path(path).resolve(strict=True)
    require(path.is_file(), 'Expected a regular file: ' + str(path))
    name = str(path) if base is None else str(path.relative_to(Path(base).resolve()))
    return {'path': name, 'bytes': path.stat().st_size, 'sha256': digest(path)}


def verify_pin(value, label='artifact', base=None):
    require(isinstance(value, dict) and set(value) == {'path', 'bytes', 'sha256'}, label + ' pin fields differ')
    require(isinstance(value['path'], str), label + ' path invalid')
    path = Path(value['path'])
    if base is None:
        require(path.is_absolute(), label + ' path must be absolute')
    else:
        require(not path.is_absolute() and '..' not in path.parts and str(path) == value['path'],
                label + ' path must be canonical relative')
        path = Path(base).resolve() / path
        require(path.resolve(strict=True).is_relative_to(Path(base).resolve()), label + ' escaped directory')
    require(type(value['bytes']) is int and value['bytes'] >= 0, label + ' byte count invalid')
    require(pin(path, base) == value, label + ' pin differs')
    return path


def write_json(path, value):
    with Path(path).open('x') as stream:
        Path(path).chmod(0o600)
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def frames(length):
    for kernel, stride in zip((10, 3, 3, 3, 3, 2, 2), (5, 2, 2, 2, 2, 2, 2)):
        length = (length - kernel) // stride + 1
    return length


def cases():
    pairs = [(p, n) for n in LENGTHS for p in PATTERNS] + [('lcgNoise', n) for n in EXTRA]
    return [{'id': f'{p}-L{n}', 'pattern': p, 'sampleCount': n, 'validFrames': frames(n)} for p, n in pairs]


def generated_pcm(pattern, length):
    require(any(c['pattern'] == pattern and c['sampleCount'] == length for c in cases()), 'Undeclared generated case')
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


def validate_plan(plan):
    expected = {'schema': 'NativeHiddenExportPlanV1', 'capacity': CAPACITY, 'caseCount': 27,
                'baseLengths': list(LENGTHS), 'extraLcgLengths': list(EXTRA), 'casePatterns': list(PATTERNS),
                'comparisonBudgets': BUDGETS, 'referenceVersions': REFERENCE_VERSIONS,
                'converterVersions': CONVERTER_VERSIONS, 'threads': 2, 'attention': 'eager',
                'precision': 'FP32', 'computeUnits': 'CPU_ONLY', 'deploymentTarget': 'iOS17',
                'normalizedShape': [1, CAPACITY], 'hiddenShape': [1, FULL_FRAMES, WIDTH], 'lengthShape': [1]}
    for key, value in expected.items():
        require(plan.get(key) == value, 'Prospective plan differs: ' + key)


def provenance(stage):
    plan, recipe = read_json(PLAN), read_json(RECIPE)
    validate_plan(plan)
    require(all(recipe.get(k) == v for k, v in {'device': 'cpu', 'threads': 2, 'dtype': 'float32',
            'attentionImplementation': 'eager', 'hiddenWidth': WIDTH, 'sampleRateHertz': 16000,
            'revision': SNAPSHOT.name, 'convKernel': [10, 3, 3, 3, 3, 2, 2],
            'convStride': [5, 2, 2, 2, 2, 2, 2]}.items()), 'Backend recipe differs')
    sources = [Path(__file__).resolve(), RECIPE, HERE / 'check_native_hidden_padding.py',
               *(HERE / name for name in LOCAL_MODULES)]
    checkpoint = []
    for name, expected in recipe['artifactSha256'].items():
        require(Path(name).name == name, 'Checkpoint filename invalid')
        value = pin(SNAPSHOT / name)
        require(value['sha256'] == expected, 'Pinned checkpoint differs: ' + name)
        checkpoint.append(value)
    versions = REFERENCE_VERSIONS if stage == 'reference' else CONVERTER_VERSIONS
    runtime_pins = [pin(Path(sys.executable).resolve())]
    for package, version in versions.items():
        require(importlib.metadata.version(package) == version, 'Runtime version differs: ' + package)
        dist = importlib.metadata.distribution(package)
        runtime_pins.append(pin(dist.locate_file(f'{package}-{version}.dist-info/METADATA')))
    installed = Path(importlib.metadata.distribution('transformers').locate_file('transformers'))
    runtime_pins.extend(pin(installed / name) for name in ('modeling_utils.py',
        'models/wav2vec2/modeling_wav2vec2.py', 'models/wav2vec2/feature_extraction_wav2vec2.py',
        'feature_extraction_sequence_utils.py'))
    if stage == 'convert':
        # Bind actual conversion/package-writing code, not only its version label.
        coreml = Path(importlib.metadata.distribution('coremltools').locate_file('coremltools'))
        coreml_files = sorted(path for path in coreml.rglob('*')
                              if path.is_file() and path.suffix in {'.py', '.so', '.dylib'})
        required = ('__init__.py', 'converters/_converters_entry.py',
                    'converters/mil/frontend/torch/converter.py', 'converters/mil/frontend/torch/ops.py',
                    'converters/mil/backend/mil/load.py', 'models/model.py',
                    'libmilstoragepython.so', 'libmodelpackage.so', 'libcoremlpython.so')
        require(all(coreml / name in coreml_files for name in required), 'Core ML conversion source closure differs')
        runtime_pins.extend(pin(path) for path in coreml_files)
    return {'plan': pin(PLAN), 'sources': [pin(p) for p in sources], 'checkpoint': checkpoint,
            'runtime': {'versions': versions, 'python': platform.python_version(), 'pins': runtime_pins}}, recipe


def verify_provenance(value):
    verify_pin(value['plan'], 'plan')
    validate_plan(read_json(value['plan']['path']))
    require(value['plan'] == pin(PLAN), 'Plan identity differs')
    require(value['sources'][0] == pin(Path(__file__).resolve()), 'Exporter source identity differs')
    for group in (value['sources'], value['checkpoint'], value['runtime']['pins']):
        for item in group:
            verify_pin(item, 'provenance')


def compare_hidden(reference, candidate, expected_shape, budget_name):
    import numpy as np
    require(budget_name in BUDGETS, 'Unknown comparison budget')
    require(tuple(reference.shape) == tuple(candidate.shape) == tuple(expected_shape), 'Hidden shape differs')
    require(reference.dtype == candidate.dtype == np.float32, 'Hidden dtype differs')
    require(np.isfinite(reference).all() and np.isfinite(candidate).all(), 'Nonfinite hidden state')
    delta = np.abs(reference.astype(np.float64) - candidate.astype(np.float64))
    maximum, mean = float(delta.max()), float(delta.mean())
    budget = BUDGETS[budget_name]
    return {'budget': budget_name, 'limits': dict(budget), 'maximumAbsoluteError': maximum,
            'meanAbsoluteError': mean, 'passed': maximum <= budget['maximum'] and mean <= budget['mean']}


def save_array(path, values, shape, base):
    import numpy as np
    require(tuple(values.shape) == tuple(shape) and values.dtype == np.float32 and np.isfinite(values).all(),
            'Array shape, dtype or finite control failed')
    with Path(path).open('xb') as stream:
        Path(path).chmod(0o600)
        stream.write(values.astype('<f4', copy=False).tobytes(order='C'))
    return pin(path, base)


def load_array(value, shape, base):
    import numpy as np
    path = verify_pin(value, 'array', base)
    count = 1
    for size in shape: count *= size
    require(value['bytes'] == count * 4, 'Array byte count differs from shape')
    values = np.fromfile(path, dtype='<f4').reshape(shape)
    require(values.dtype == np.float32 and np.isfinite(values).all(), 'Nonfinite or non-FP32 array')
    return values


def load_reference(path):
    base = Path(path).resolve().parent
    value = read_json(path)
    require(value['schema'] == 'NativeHiddenReferenceV1' and value['complete'] is True
            and value['comparisonPassed'] is True and value['forwardsCompleted'] == 54,
            'Reference did not complete all required gates')
    require(value['budgets'] == BUDGETS, 'Reference budgets differ')
    require(value['bindings']['runtime']['versions'] == REFERENCE_VERSIONS, 'Reference runtime differs')
    verify_provenance(value['bindings'])
    require(len(value['cases']) == 27, 'Reference case count differs')
    for expected, row in zip(cases(), value['cases']):
        require(all(row.get(k) == v for k, v in expected.items()), 'Reference case identity differs')
        require(row['preprocessingExact'] is True and row['passed'] is True, 'Reference case gate failed')
        n, f = row['sampleCount'], row['validFrames']
        normalized = load_array(row['normalized'], (1, CAPACITY), base)
        require((normalized[:, n:] == 0).all(), 'Normalized padding tail differs')
        load_array(row['unpadded'], (1, f, WIDTH), base)
        load_array(row['padded'], (1, FULL_FRAMES, WIDTH), base)
        require(row['comparison']['budget'] == 'backendPadding'
                and row['comparison']['limits'] == BUDGETS['backendPadding']
                and row['comparison']['passed'] is True, 'Reference comparison budget differs')
    return value


def configure_environment():
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', TOKENIZERS_PARALLELISM='false')


def check_model(torch, model):
    require(torch.get_num_threads() == 2 and not model.training
            and model.config._attn_implementation == 'eager'
            and model.config.hidden_size == WIDTH
            and all(p.dtype == torch.float32 and p.device.type == 'cpu' and not p.requires_grad
                    for p in model.parameters()), 'Model configuration differs')


def reference_stage(output, args, outcome):
    configure_environment()
    bindings, recipe = provenance('reference')
    write_json(output / 'prospective.json', {'stage': 'reference', 'bindings': bindings,
        'cases': cases(), 'budgets': BUDGETS, 'plannedForwards': 54})
    import numpy as np
    import torch
    import transformers
    from multiphone_phonetic_features import PhoneticEncoder
    require(torch.__version__.split('+')[0] == '2.8.0' and np.__version__ == '2.2.6'
            and transformers.__version__ == '4.57.6', 'Imported reference runtime differs')
    torch.set_num_threads(2)
    encoder = PhoneticEncoder(SNAPSHOT, recipe)
    check_model(torch, encoder.model)
    outcome['runtime'] = {'cpuThreads': torch.get_num_threads(), 'interopThreads': torch.get_num_interop_threads()}
    rows = outcome['cases']
    for case in cases():
        row = dict(case)
        n, f = case['sampleCount'], case['validFrames']
        pcm = np.asarray(generated_pcm(case['pattern'], n), dtype='<i2')
        row['pcm16Sha256'] = hashlib.sha256(pcm.tobytes()).hexdigest()
        samples = torch.from_numpy(pcm.astype(np.float32) / 32768)
        unpadded = encoder.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt')
        padded = encoder.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt',
                                   padding='max_length', max_length=CAPACITY, truncation=False,
                                   return_attention_mask=True)
        require(tuple(unpadded.input_values.shape) == (1, n)
                and tuple(padded.input_values.shape) == (1, CAPACITY)
                and tuple(unpadded.attention_mask.shape) == (1, n)
                and tuple(padded.attention_mask.shape) == (1, CAPACITY)
                and unpadded.input_values.dtype == padded.input_values.dtype == torch.float32
                and bool(torch.isfinite(unpadded.input_values).all()) and bool(torch.isfinite(padded.input_values).all())
                and torch.equal(unpadded.input_values, padded.input_values[:, :n])
                and bool((padded.input_values[:, n:] == 0).all())
                and bool((unpadded.attention_mask == 1).all())
                and bool((padded.attention_mask[:, :n] == 1).all())
                and bool((padded.attention_mask[:, n:] == 0).all()), 'Preprocessing control failed: ' + case['id'])
        row['preprocessingExact'] = True
        hidden = encoder(samples)[None, ...]
        outcome['forwardsCompleted'] += 1
        with torch.inference_mode():
            full = encoder.model.wav2vec2(**padded).last_hidden_state.cpu().numpy()
        outcome['forwardsCompleted'] += 1
        row['comparison'] = compare_hidden(hidden, full[:, :f], (1, f, WIDTH), 'backendPadding')
        row['passed'] = row['comparison']['passed']
        case_dir = output / case['id']
        case_dir.mkdir(mode=0o700)
        row['normalized'] = save_array(case_dir / 'normalized.f32', padded.input_values.numpy(), (1, CAPACITY), output)
        row['unpadded'] = save_array(case_dir / 'unpadded-hidden.f32', hidden, (1, f, WIDTH), output)
        row['padded'] = save_array(case_dir / 'padded-hidden.f32', full, (1, FULL_FRAMES, WIDTH), output)
        write_json(case_dir / 'case.json', row)
        rows.append(row)
    verify_provenance(bindings)
    outcome.update(complete=len(rows) == 27 and outcome['forwardsCompleted'] == 54,
                   comparisonPassed=all(row['passed'] for row in rows))
    require(outcome['complete'], 'Reference coverage incomplete')
    write_json(output / 'manifest.json', dict(outcome, schema='NativeHiddenReferenceV1', bindings=bindings, budgets=BUDGETS,
        normalizedShape=[1, CAPACITY], paddedShape=[1, FULL_FRAMES, WIDTH], unpaddedShape='[1,validFrames,1024]'))


def load_converter_model(torch, transformer_class, output):
    model, info = transformer_class.from_pretrained(str(SNAPSHOT), local_files_only=True, trust_remote_code=False,
        use_safetensors=False, weights_only=True, attn_implementation='eager', output_loading_info=True)
    require(set(info) == {'missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs'}
            and all(type(v) is list and not v for v in info.values()), 'Checkpoint loading info differs')
    model = model.to(device='cpu', dtype=torch.float32).requires_grad_(False).eval()
    check_model(torch, model)
    require(model.config.model_type == 'wav2vec2' and model.config.architectures == ['Wav2Vec2ForCTC']
            and model.config.vocab_size == 392 and model.config.add_adapter is False
            and model.config.adapter_attn_dim is None, 'Checkpoint configuration differs')
    checkpoint = torch.load(str(SNAPSHOT / 'pytorch_model.bin'), map_location='meta', weights_only=True)
    require(isinstance(checkpoint, dict) and all(type(k) is str and torch.is_tensor(v)
            for k, v in checkpoint.items()), 'Checkpoint mapping invalid')
    allowed = {'wav2vec2.encoder.pos_conv_embed.conv.weight_g':
                   'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original0',
               'wav2vec2.encoder.pos_conv_embed.conv.weight_v':
                   'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original1'}
    mapped, migrations = {}, []
    for key, value in checkpoint.items():
        target, changed = model._fix_state_dict_key_on_load(key)
        require((target == key and changed is False) or (allowed.get(key) == target and changed is True),
                'Unapproved checkpoint key migration')
        require(target not in mapped, 'Duplicate checkpoint mapping')
        mapped[target] = value
        if changed: migrations.append({'from': key, 'to': target})
    loaded = model.state_dict()
    require(set(mapped) == set(loaded), 'Checkpoint tensor coverage differs')
    for key, value in loaded.items():
        original = mapped[key]
        require(value.dtype == original.dtype == torch.float32 and value.device.type == 'cpu'
                and tuple(value.shape) == tuple(original.shape) and bool(torch.isfinite(value).all()),
                'Checkpoint tensor control failed: ' + key)
    write_json(output / 'loading.json', {'schema': 'NativeHiddenLoadingV1', 'loadingInfo': info,
        'stateTensorCount': len(loaded), 'allStateFP32Finite': True, 'migrations': migrations,
        'checkpoint': pin(SNAPSHOT / 'pytorch_model.bin')})
    return model


def tree_pin(directory, base=None):
    directory = Path(directory).resolve(strict=True)
    require(directory.is_dir() and not directory.is_symlink(), 'Expected artifact directory')
    entries = []
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'Artifact symlink rejected')
        if path.is_file():
            entries.append({'path': str(path.relative_to(directory)), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    require(entries, 'Empty artifact directory')
    payload = json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()
    name = str(directory) if base is None else str(directory.relative_to(Path(base).resolve()))
    return {'path': name, 'sha256': hashlib.sha256(payload).hexdigest(), 'files': entries}


def convert_stage(output, args, outcome):
    configure_environment()
    reference = load_reference(args.reference)
    reference_base = args.reference.resolve().parent
    reference_pin = pin(args.reference)
    bindings, _ = provenance('convert')
    write_json(output / 'prospective.json', {'stage': 'convert', 'bindings': bindings,
        'referenceManifest': reference_pin, 'cases': cases(), 'budgets': BUDGETS})
    import numpy as np
    import torch
    import transformers
    import coremltools as ct
    from transformers import Wav2Vec2ForCTC
    require(torch.__version__.split('+')[0] == '2.7.0' and np.__version__ == '2.2.6'
            and transformers.__version__ == '4.57.6' and ct.__version__ == '9.0', 'Imported converter runtime differs')
    torch.set_num_threads(2)
    model = load_converter_model(torch, Wav2Vec2ForCTC, output)

    class HiddenWrapper(torch.nn.Module):
        def __init__(self, backbone):
            super().__init__()
            self.backbone = backbone
            self.register_buffer('sample_positions', torch.arange(CAPACITY).reshape(1, CAPACITY))

        def forward(self, normalizedWaveform, validSampleCount):
            mask = (self.sample_positions < validSampleCount.reshape(1, 1)).to(torch.long)
            return self.backbone(normalizedWaveform, attention_mask=mask, return_dict=True).last_hidden_state

    wrapper = HiddenWrapper(model.wav2vec2).eval()
    for row in reference['cases']:
        waveform = torch.from_numpy(load_array(row['normalized'], (1, CAPACITY), reference_base))
        count = torch.tensor([row['sampleCount']], dtype=torch.int32)
        with torch.inference_mode():
            actual = wrapper(waveform, count).cpu().numpy()
        outcome['forwardsCompleted'] += 1
        comparisons = backend_comparisons(row, actual, 'converterVsBackend', reference_base)
        result = {'id': row['id'], 'comparisons': comparisons, 'passed': all(x['passed'] for x in comparisons.values())}
        result['converterHidden'] = save_array(output / (row['id'] + '-converter.f32'), actual, (1, FULL_FRAMES, WIDTH), output)
        write_json(output / (row['id'] + '-converter.json'), result)
        outcome['cases'].append(result)
    verify_provenance(bindings)
    verify_pin(reference_pin)
    if not all(row['passed'] for row in outcome['cases']):
        outcome.update(complete=True, comparisonPassed=False, conversionSkipped=True)
        return
    write_json(output / 'pre-trace.json', {'bindings': bindings, 'referenceManifest': reference_pin,
        'loading': pin(output / 'loading.json'), 'prospective': pin(output / 'prospective.json'),
        'converterCases': [pin(output / (row['id'] + '-converter.json')) for row in reference['cases']]})
    first = reference['cases'][0]
    example = (torch.from_numpy(load_array(first['normalized'], (1, CAPACITY), reference_base)),
               torch.tensor([first['sampleCount']], dtype=torch.int32))
    with torch.inference_mode():
        traced = torch.jit.trace(wrapper, example, strict=True, check_trace=False)
    for row, result in zip(reference['cases'], outcome['cases']):
        inputs = (torch.from_numpy(load_array(row['normalized'], (1, CAPACITY), reference_base)),
                  torch.tensor([row['sampleCount']], dtype=torch.int32))
        with torch.inference_mode():
            actual = traced(*inputs).cpu().numpy()
        outcome['forwardsCompleted'] += 1
        baseline = load_array(result['converterHidden'], (1, FULL_FRAMES, WIDTH), output)
        result['traceComparison'] = compare_hidden(baseline, actual, (1, FULL_FRAMES, WIDTH), 'traceVsConverter')
        result['passed'] = result['passed'] and result['traceComparison']['passed']
        write_json(output / (row['id'] + '-trace.json'), result)
    verify_provenance(bindings)
    verify_pin(reference_pin)
    outcome.update(complete=len(outcome['cases']) == 27 and outcome['forwardsCompleted'] == 54,
                   comparisonPassed=all(row['passed'] for row in outcome['cases']))
    if not outcome['comparisonPassed']:
        outcome['conversionSkipped'] = True
        return
    require(outcome['complete'], 'Converter/trace coverage incomplete')
    traced.save(str(output / 'hidden-trace.pt'))
    (output / 'hidden-trace.pt').chmod(0o600)
    write_json(output / 'pre-conversion.json', {'preTrace': pin(output / 'pre-trace.json'),
        'trace': pin(output / 'hidden-trace.pt'), 'bindings': bindings, 'referenceManifest': reference_pin,
        'traceCases': [pin(output / (row['id'] + '-trace.json')) for row in reference['cases']]})
    package = output / 'PhoneticHidden.mlpackage'
    converted = ct.convert(traced, source='pytorch', convert_to='mlprogram',
        minimum_deployment_target=ct.target.iOS17, compute_units=ct.ComputeUnit.CPU_ONLY,
        compute_precision=ct.precision.FLOAT32, skip_model_load=True, package_dir=str(package),
        inputs=[ct.TensorType(name='normalizedWaveform', shape=(1, CAPACITY), dtype=np.float32),
                ct.TensorType(name='validSampleCount', shape=(1,), dtype=np.int32)],
        outputs=[ct.TensorType(name='hidden', dtype=np.float32)])
    # Conversion builds the package with skip_model_load=True. No load/predict follows.
    require(package.is_dir(), 'Conversion did not create the new package')
    del converted
    verify_provenance(bindings)
    verify_pin(reference_pin)
    outcome['conversionSkipped'] = False
    write_json(output / 'export-manifest.json', dict(outcome, schema='NativeHiddenExportV1', budgets=BUDGETS,
        bindings=bindings, referenceManifest=reference_pin, loading=pin(output / 'loading.json'),
        preTrace=pin(output / 'pre-trace.json'), preConversion=pin(output / 'pre-conversion.json'),
        trace=pin(output / 'hidden-trace.pt', output), package=tree_pin(package, output), coreMLPythonPredictionExecuted=False,
        interface={'normalizedWaveform': [1, CAPACITY], 'validSampleCount': [1], 'hidden': [1, FULL_FRAMES, WIDTH]}))


def backend_comparisons(row, actual, budget, base):
    f = row['validFrames']
    full = load_array(row['padded'], (1, FULL_FRAMES, WIDTH), base)
    unpadded = load_array(row['unpadded'], (1, f, WIDTH), base)
    return {'fullPadded': compare_hidden(full, actual, (1, FULL_FRAMES, WIDTH), budget),
            'validUnpadded': compare_hidden(unpadded, actual[:, :f], (1, f, WIDTH), budget)}


def verify_export(path, reference_path):
    base = Path(path).resolve().parent
    value = read_json(path)
    require(value['schema'] == 'NativeHiddenExportV1' and value['complete'] is True
            and value['comparisonPassed'] is True and value['conversionSkipped'] is False
            and value['forwardsCompleted'] == 54 and len(value['cases']) == 27, 'Export gates incomplete')
    require(value['budgets'] == BUDGETS and value['referenceManifest'] == pin(reference_path), 'Export binding differs')
    require(value['bindings']['runtime']['versions'] == CONVERTER_VERSIONS, 'Export runtime differs')
    verify_provenance(value['bindings'])
    for key in ('referenceManifest', 'loading', 'preTrace', 'preConversion'):
        verify_pin(value[key], key)
    verify_pin(value['trace'], 'trace', base)
    require(tree_pin(base / value['package']['path'], base) == value['package'], 'Export package tree differs')
    for expected, row in zip(cases(), value['cases']):
        require(row['id'] == expected['id'] and row['passed'] is True, 'Export case identity or gate differs')
        verify_pin(row['converterHidden'], 'converter hidden', base)
        require(set(row['comparisons']) == {'fullPadded', 'validUnpadded'}, 'Export comparison branches differ')
        require(row['traceComparison']['budget'] == 'traceVsConverter'
                and row['traceComparison']['limits'] == BUDGETS['traceVsConverter']
                and row['traceComparison']['passed'] is True, 'Export trace gate differs')
        for comparison in row['comparisons'].values():
            require(comparison['budget'] == 'converterVsBackend'
                    and comparison['limits'] == BUDGETS['converterVsBackend'] and comparison['passed'] is True,
                    'Export converter gate differs')
    return value


def verify_native(request_path, receipt_path, reference_path, export_path, reference):
    native_dir = Path(request_path).resolve().parent
    output_dir = Path(receipt_path).resolve().parent
    request, receipt = read_json(request_path), read_json(receipt_path)
    require(set(request) == {'schema', 'deadlineMonotonicSeconds', 'bindings', 'compiledModel', 'cases'}
            and request['schema'] == 'NativeHiddenRequestV1', 'Native request schema differs')
    validate_deadline(request['deadlineMonotonicSeconds'])
    bindings = request['bindings']
    require(set(bindings) == {'workerSource', 'exportManifest', 'compilerReceipt', 'referenceManifest'},
            'Native binding fields differ')
    for key, item in bindings.items(): verify_pin(item, key, native_dir)
    require(same_content(bindings['exportManifest'], pin(export_path))
            and same_content(bindings['referenceManifest'], pin(reference_path)), 'Native manifest bindings differ')
    compiled = request['compiledModel']
    require(set(compiled) == {'path', 'files'} and compiled['path'] == 'PhoneticHidden.mlmodelc',
            'Compiled model fields or path differ')
    actual_tree = tree_pin(native_dir / compiled['path'], native_dir)
    expected_files = [dict(item, path=str(Path(compiled['path']) / item['path'])) for item in actual_tree['files']]
    require(compiled['files'] == expected_files, 'Compiled model tree differs')
    for item in compiled['files']: verify_pin(item, 'compiled model', native_dir)
    require(len(request['cases']) == 27, 'Native request case count differs')
    for row, expected in zip(request['cases'], reference['cases']):
        require(set(row) == {'caseID', 'sampleCount', 'validFrames', 'normalized'}
                and row['caseID'] == expected['id'] and row['sampleCount'] == expected['sampleCount']
                and row['validFrames'] == expected['validFrames']
                and same_content(row['normalized'], expected['normalized']),
                'Native request case differs')
        verify_pin(row['normalized'], 'native input', native_dir)
    require(receipt['schema'] == 'NativeHiddenReceiptV1' and receipt['status'] == 'complete'
            and receipt['requestSHA256'] == digest(request_path) and receipt['callsReturned'] == 27
            and receipt['teardownScopesReturned'] is True and receipt['normalExitRequiresParent'] is True
            and all(receipt.get(key) is False for key in ('productionEligible', 'clinicalEligible', 'learnerEligible')),
            'Native receipt incomplete or request differs')
    require(len(receipt['artifacts']) == 27, 'Native artifact count differs')
    for index, item in enumerate(receipt['artifacts']):
        path = verify_pin(item, 'native output', output_dir)
        require(path == output_dir / f'case-{index}-hidden.f32', 'Native output filename or directory differs')
        load_array(item, (1, FULL_FRAMES, WIDTH), output_dir)
    return request, receipt


def same_content(left, right):
    return left['bytes'] == right['bytes'] and left['sha256'] == right['sha256']


def validate_deadline(value):
    require(isinstance(value, str) and re.fullmatch(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', value) is not None,
            'Native deadline must be a decimal string')
    require(Decimal(value).is_finite() and Decimal(value) > 0 and 0 < float(value) < float('inf'),
            'Native deadline invalid')


def compare_stage(output, args, outcome):
    require(importlib.metadata.version('numpy') == '2.2.6', 'Comparison NumPy version differs')
    reference = load_reference(args.reference)
    export = verify_export(args.export, args.reference)
    request, receipt = verify_native(args.request, args.receipt, args.reference, args.export, reference)
    inputs = {key: pin(getattr(args, key)) for key in ('reference', 'export', 'request', 'receipt')}
    write_json(output / 'prospective.json', {'stage': 'compare', 'inputs': inputs, 'budgets': BUDGETS,
        'numpyVersion': '2.2.6', 'numpyMetadata': pin(importlib.metadata.distribution('numpy').locate_file(
            'numpy-2.2.6.dist-info/METADATA'))})
    for row, artifact in zip(reference['cases'], receipt['artifacts']):
        actual = load_array(artifact, (1, FULL_FRAMES, WIDTH), args.receipt.resolve().parent)
        comparisons = backend_comparisons(row, actual, 'nativeVsBackend', args.reference.resolve().parent)
        result = {'id': row['id'], 'comparisons': comparisons, 'passed': all(x['passed'] for x in comparisons.values())}
        write_json(output / (row['id'] + '.json'), result)
        outcome['cases'].append(result)
    for item in inputs.values(): verify_pin(item)
    verify_provenance(reference['bindings'])
    verify_provenance(export['bindings'])
    verify_native(args.request, args.receipt, args.reference, args.export, reference)
    outcome.update(complete=len(outcome['cases']) == 27,
                   comparisonPassed=all(row['passed'] for row in outcome['cases']))
    write_json(output / 'comparison.json', dict(outcome, schema='NativeHiddenComparisonV1', inputs=inputs,
        budgets=BUDGETS, parentTerminalStatusVerified=False,
        limitation='Parent terminal status is separately authoritative; this receipt does not prove process exit.'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('reference', 'convert', 'compare'):
        command = sub.add_parser(name)
        command.add_argument('--output', type=Path, required=True)
        if name != 'reference': command.add_argument('--reference', type=Path, required=True)
        if name == 'compare':
            for key in ('export', 'request', 'receipt'):
                command.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    output = args.output.absolute()
    require(output.parent.resolve().is_relative_to((ROOT / 'work').resolve()), 'Output must be task-local work')
    output.mkdir(mode=0o700)  # Deliberately rejects overwrite, resume and retry.
    outcome = {'stage': args.mode, 'complete': False, 'comparisonPassed': False, 'cases': [],
               'forwardsCompleted': 0, 'learnerFeedbackEligible': False, 'clinicalUseEligible': False,
               'productionUseEligible': False, 'privateAudioUsed': False}
    try:
        {'reference': reference_stage, 'convert': convert_stage, 'compare': compare_stage}[args.mode](output, args, outcome)
    except Exception as exc:
        outcome.update(complete=False, comparisonPassed=False, failureType=type(exc).__name__,
                       failureMessage=str(exc) if isinstance(exc, ValueError) else 'Stage execution failed')
    finally:
        write_json(output / 'outcome.json', outcome)
    return 0 if outcome['complete'] and outcome['comparisonPassed'] else (2 if outcome['complete'] else 1)


if __name__ == '__main__':
    sys.exit(main())
