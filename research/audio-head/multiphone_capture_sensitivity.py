"""Small, label-free recording perturbation diagnostic for fixed inner heads.

Prepare is metadata/file verification only. Run recomputes q8 CTC locations and
full-precision phonetic features on local derived PCM16 files. No model is fitted,
and original corpus ratings are never assigned to transformed recordings.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
import wave

import numpy as np
import torch

import multiphone_local_features as local
import multiphone_phonetic_features as extraction
import multiphone_phonetic_head as frozen
from multiphone_cache import atomic_json, digest
from multiphone_models import MeanPoolPhoneRatingHead
from speechocean_r_probe import read_rating_pcm

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
RECIPE = HERE / 'experiments/multiphone-capture-sensitivity-v1.json'
CONDITIONS = ('original', 'gain025', 'noise20db', 'noise10db')
REGIMES = ('all-age', 'child-only')
IDENTITY = ('rowIndex', 'rowId', 'clipId', 'targetId', 'targetPhone', 'canonicalIndex', 'wordIndex', 'phoneIndex')
SOURCES = tuple(dict.fromkeys(('multiphone_capture_sensitivity.py', 'multiphone_capture_ctc.ts',
    'multiphone_ctc_cache.ts', 'multiphone_local_features.py', 'alignment_pilot.py', 'speechocean_r_probe.py', 'speechocean_audit.py',
    '../../packages/audio-model-adapter/src/model-cache.ts', '../../packages/audio-model-adapter/src/manifest.ts',
    '../../packages/audio-model-adapter/src/posteriors.ts', '../../pnpm-lock.yaml', 'requirements.lock.txt',
    '../../packages/audio-model-adapter/node_modules/@huggingface/transformers/package.json',
    '../../packages/audio-model-adapter/node_modules/@huggingface/transformers/dist/transformers.node.mjs') + frozen.SOURCES))
FALSE_FLAGS = {name: False for name in ('trainingPerformed', 'modelSelectionPerformed', 'outerInferencePerformed',
    'authorTestInferencePerformed', 'transformedLabelsAvailable', 'accuracyMeasured', 'calibrationMeasured',
    'frameTimesValidated', 'clinicalUseEligible', 'learnerFeedbackEligible')}
require, read_json = extraction.require, extraction.read_json


def pin(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path)}


def guard(bindings):
    checked = {}
    for value in bindings.values():
        path = value['path']
        if path not in checked:
            checked[path] = digest(Path(path))
        require(checked[path] == value['sha256'], 'Diagnostic source, original, model or derived artifact changed')


def rank_key(namespace, value, seed):
    return hashlib.sha256(f'{seed}:{namespace}:{value}'.encode()).hexdigest()


def select_clips(cohort, splits, maximum=8, seed=20260926):
    """Select speakers and then one clip each, using metadata only, not ratings."""
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train', 'Only author training is allowed')
    fold = splits['folds'][0]
    allowed = set(fold['innerValidationRows'])
    candidates = {}
    for index in fold['innerValidationClips']:
        clip = cohort['clips'][index]
        if not 6 <= clip['age'] <= 12:
            continue
        rows = [i for i, row in enumerate(cohort['rows']) if row['clipIndex'] == index and row['trainingEligible']]
        require(rows and set(rows) <= allowed, 'Child candidate is not wholly in inner validation')
        candidates.setdefault(clip['speakerId'], []).append(index)
    require(candidates and maximum == 8, 'Need child inner-validation speakers and the declared cap')
    speakers = sorted(candidates, key=lambda s: (rank_key('speaker', s, seed), s))[:maximum]
    selected = [min(candidates[s], key=lambda i: (rank_key('clip', cohort['clips'][i]['id'], seed),
                                                 cohort['clips'][i]['id'])) for s in speakers]
    fit_speakers = {cohort['rows'][i]['speakerId'] for i in fold['innerFitRows']}
    require(not set(speakers) & fit_speakers, 'Selected speaker appears in model fitting')
    return selected, len(candidates)


def quality(samples):
    x = np.asarray(samples, dtype=np.float64)
    require(x.ndim == 1 and len(x) >= 1600 and np.isfinite(x).all() and np.max(np.abs(x)) <= 1,
            'Expected finite mono PCM16 waveform')
    rms = float(np.sqrt(np.mean(x*x)))
    return {'samples': len(x), 'seconds': len(x)/16000, 'rms': rms,
            'rmsDbFS': float(20*np.log10(rms)) if rms else None,
            'peak': float(np.max(np.abs(x))), 'meanDC': float(x.mean()),
            'railSamples': int(np.count_nonzero((x <= -1) | (x >= 32767/32768))),
            'nearSilenceFractionBelowMinus60dBFS': float(np.mean(np.abs(x) < .001))}


def pcm16_bytes(samples):
    x = np.asarray(samples, dtype=np.float64)
    require(x.ndim == 1 and np.isfinite(x).all() and np.max(np.abs(x)) <= 1, 'Invalid PCM16 input')
    pcm = np.clip(np.rint(x*32768), -32768, 32767).astype('<i2')
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
        stream.writeframes(pcm.tobytes())
    return output.getvalue(), pcm.astype(np.float32)/32768


def transform(samples, condition, audio_sha, seed=20260926):
    x = np.asarray(samples, dtype=np.float64)
    before = quality(x)
    require(condition in CONDITIONS, 'Unknown recording condition')
    nominal = {'original': 1., 'gain025': .25, 'noise20db': 1., 'noise10db': 1.}[condition]
    clean, changed, common_gain, requested = x*nominal, x*nominal, 1., None
    seed_value = int(rank_key('noise', audio_sha, seed)[:16], 16)
    if condition.startswith('noise'):
        requested = 20 if condition == 'noise20db' else 10
        require(before['rms'] > 0, 'Cannot define SNR for a silent source')
        noise = np.random.default_rng(seed_value).normal(size=len(x))
        noise -= noise.mean()
        noise *= before['rms']/np.sqrt(np.mean(noise*noise))/10**(requested/20)
        changed = clean+noise
        common_gain = min(1., .98/float(np.max(np.abs(changed))))
        clean, changed = clean*common_gain, changed*common_gain
    payload, quantized = pcm16_bytes(changed)
    error = quantized.astype(np.float64)-clean
    measured = float(10*np.log10(np.mean(clean*clean)/np.mean(error*error))) if requested is not None else None
    return payload, quantized, {'condition': condition, 'nominalSignalGain': nominal,
        'commonSignalAndNoiseGainBeforeQuantization': common_gain,
        'noiseSeed': seed_value if requested is not None else None,
        'requestedSNRdB': requested, 'measuredSNRdBAfterPCM16': measured,
        'SNRReference': 'Noise residual relative to the identically attenuated clean signal',
        'quantization': 'round-to-nearest ties-to-even PCM16; noise peak limited by common gain, not clipping',
        'quality': quality(quantized)}


def write_variants(source, source_sha, directory, seed):
    """Original copied byte-for-byte; transformations never write to the source."""
    require(digest(source) == source_sha and not directory.exists(), 'Source changed or variant directory exists')
    samples = read_rating_pcm(source, source_sha).numpy()
    directory.mkdir(parents=True, mode=0o700)
    variants = []
    for condition in CONDITIONS:
        payload, decoded, measurement = transform(samples, condition, source_sha, seed)
        if condition == 'original':
            payload = source.read_bytes()
            require(np.array_equal(samples, decoded), 'Original PCM round trip differs')
        target = directory / (condition+'.wav')
        with target.open('xb') as stream:
            target.chmod(0o600); stream.write(payload)
        require(np.array_equal(read_rating_pcm(target, digest(target)).numpy(), decoded), 'Written PCM differs')
        variants.append({'condition': condition, 'audioPath': str(target.resolve()), 'audioSha256': digest(target),
                         'sampleCount': len(samples), 'measurement': measurement})
    require(digest(source) == source_sha and variants[0]['audioSha256'] == source_sha, 'Original source/copy changed')
    return variants


def recipe_inputs(recipe):
    require(recipe['conditions'] == list(CONDITIONS) and set(recipe['heads']) == set(REGIMES)
            and recipe['scalarFeatureNames'] == local.SCALAR_NAMES == frozen.SCALAR_NAMES
            and recipe['phoneticDevice'] == 'cpu' and recipe['phoneticThreads'] == 2,
            'Diagnostic condition, feature order or device contract differs')
    bindings = {'recipe': pin(RECIPE), **{'source/'+name: pin(HERE/name) for name in SOURCES}}
    for name, entry in recipe['inputs'].items():
        bindings[name] = pin(HERE/entry['path'])
        require(bindings[name]['sha256'] == entry['sha256'], 'Declared input differs: '+name)
    for regime, head in recipe['heads'].items():
        for name, sha in head['files'].items():
            bindings['head/'+regime+'/'+name] = pin(HERE/head['directory']/name)
            require(bindings['head/'+regime+'/'+name]['sha256'] == sha, 'Original inner head changed')
    return bindings


def validate_selected_plan(plan, cohort, splits, manifest, original):
    recipe = plan['recipe']
    indices, available = select_clips(cohort, splits, recipe['maximumSpeakers'], recipe['seed'])
    require(plan['availableChildSpeakers'] == available and plan['selectedSpeakers'] == len(indices)
            and plan['variantCount'] == len(indices)*4 and len(plan['clips']) == len(indices), 'Selection support differs')
    by_id = {clip['id']: clip for clip in manifest['clips']}
    by_row = {row['rowIndex']: row for row in original['rows']}
    for clip, index in zip(plan['clips'], indices, strict=True):
        source = cohort['clips'][index]; canonical = by_id[source['id']]
        require(clip['clipIndex'] == index and all(clip[k] == source[k] for k in
                ('id', 'speakerId', 'age', 'audioPath', 'audioSha256', 'sampleCount'))
                and all(clip[k] == canonical[k] for k in ('canonicalPhones', 'mappedTokenIds', 'mappingAmbiguities')),
                'Selected clip identity/canonical prompt differs')
        expected = [{key: by_row[row['rowIndex']][key] for key in IDENTITY} for row in canonical['targetRows']]
        require(clip['targets'] == expected, 'Selected target identity/order/coverage differs')
        require([v['condition'] for v in clip['variants']] == list(CONDITIONS)
                and all(v['sampleCount'] == source['sampleCount'] for v in clip['variants'])
                and clip['variants'][0]['audioSha256'] == source['audioSha256'], 'Variant sample count/order/original differs')
        for variant in clip['variants']:
            require(plan['bindings']['derived/'+clip['id']+'/'+variant['condition']] ==
                    {'path': variant['audioPath'], 'sha256': variant['audioSha256']}, 'Derived waveform binding differs')


def prepare(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE/'outputs'), 'Choose fresh ignored output')
    recipe_sha = digest(RECIPE)
    recipe = read_json(RECIPE)
    bindings = recipe_inputs(recipe)
    require(bindings['recipe']['sha256'] == recipe_sha, 'Recipe changed while preparing')
    bundle = frozen.load_bound(Path(bindings['featureBinding']['path']), read_json(frozen.RECIPE))
    bindings.update({'feature/'+key: value for key, value in bundle['bindings'].items()})
    cohort, splits = bundle['cohort'], bundle['splits']
    indices, available = select_clips(cohort, splits, recipe['maximumSpeakers'], recipe['seed'])
    original = read_json(Path(bindings['originalFeatures']['path']))
    manifest = read_json(Path(original['manifestPath']))
    local.validate_manifest_rows(manifest, cohort)
    selection = read_json(Path(bindings['innerSelection']['path']))
    ledger = read_json(Path(bindings['innerQueue']['path']))
    require(selection['complete'] is True and ledger['complete'] is True and len(ledger['jobs']) == 80,
            'Original inner matrix must be complete')
    for regime, head in recipe['heads'].items():
        directory = (HERE/head['directory']).resolve()
        chosen = [g for g in selection['selections'] if g['family'] == 'target-scalars' and g['regime'] == regime and g['fold'] == 0]
        jobs = [g for g in ledger['jobs'] if Path(g['output']).resolve() == directory]
        require(len(chosen) == len(jobs) == 1 and chosen[0]['output'] == str(directory)
                and chosen[0]['verified']['checkpointSha256'] == head['files']['best.pt']
                and jobs[0]['state'] == 'complete'
                and jobs[0]['verified']['checkpointSha256'] == head['files']['best.pt'],
                'Declared head is not the original verified inner selection')
        config = read_json(directory/'config.json')
        require(config['phase'] == 'inner' and config['family'] == 'target-scalars' and config['fold'] == 0
                and config['regime'] == regime and config['lr'] == .0003 and config['outerOutcomesUsed'] is False,
                'Unexpected head scope')
        frozen.source_guard(config)
    by_id = {c['id']: c for c in manifest['clips']}
    source_rows = {r['rowIndex']: r for r in original['rows']}
    ctc_path = Path(original['ctcIndexPath']); ctc = read_json(ctc_path)
    output.mkdir(parents=True, mode=0o700)
    selected = []
    for index in indices:
        clip = cohort['clips'][index]; original_clip = by_id[clip['id']]
        require(index == original_clip['clipIndex'], 'Canonical manifest clip identity differs')
        targets = [{key: source_rows[t['rowIndex']][key] for key in IDENTITY} for t in original_clip['targetRows']]
        bindings['audio/'+clip['id']] = pin(clip['audioPath'])
        require(bindings['audio/'+clip['id']]['sha256'] == clip['audioSha256'], 'Selected audio differs')
        ctc_entry = ctc['entries'][clip['id']]
        bindings['originalCTC/'+clip['id']] = pin(ctc_path.parent/ctc_entry['path'])
        require(bindings['originalCTC/'+clip['id']]['sha256'] == ctc_entry['sha256'], 'Original CTC cache differs')
        variants = write_variants(Path(clip['audioPath']), clip['audioSha256'], output/'audio'/clip['id'], recipe['seed'])
        for variant in variants:
            bindings['derived/'+clip['id']+'/'+variant['condition']] = pin(variant['audioPath'])
        selected.append({key: clip[key] for key in ('id', 'speakerId', 'age', 'audioPath', 'audioSha256', 'sampleCount')} |
            {'clipIndex': index, 'canonicalPhones': original_clip['canonicalPhones'],
             'mappedTokenIds': original_clip['mappedTokenIds'], 'mappingAmbiguities': original_clip['mappingAmbiguities'],
             'targets': targets, 'variants': variants})
    plan = {'schemaVersion': 1, 'complete': True, 'role': 'metadata-selected capture diagnostic plan',
            'recipe': recipe, 'bindings': bindings, 'availableChildSpeakers': available,
            'selectedSpeakers': len(selected), 'variantCount': len(selected)*len(CONDITIONS),
            'authorPartition': 'train', 'fold': 0, 'partition': 'innerValidationRows', 'clips': selected, **FALSE_FLAGS}
    validate_selected_plan(plan, cohort, splits, manifest, original)
    guard(bindings)
    atomic_json(output/'plan.json', plan)
    return {'planPath': str((output/'plan.json').resolve()), 'planSha256': digest(output/'plan.json'),
            'speakers': len(selected), 'variants': plan['variantCount']}


def load_heads(recipe):
    result = {}
    for regime, head in recipe['heads'].items():
        directory = HERE/head['directory']
        config = read_json(directory/'config.json')
        saved = torch.load(directory/'best.pt', map_location='cpu', weights_only=True)
        require(saved['configSha256'] == digest(directory/'config.json') and saved['epoch'] == 5
                and saved['mean'].shape == saved['std'].shape == (1037,)
                and torch.isfinite(saved['mean']).all() and torch.isfinite(saved['std']).all()
                and (saved['std'] > 0).all(), 'Invalid original checkpoint identity/moments')
        model = MeanPoolPhoneRatingHead(feature_dim=1037, hidden_dim=128, dropout=.1).eval()
        model.load_state_dict(saved['model'], strict=True)
        predictions = read_json(directory/'predictions.json')
        require(predictions['rowIndices'] == config['validationRows'], 'Original prediction rows differ')
        result[regime] = {'model': model, 'mean': saved['mean'], 'std': saved['std'],
                         'predictions': dict(zip(predictions['rowIndices'], predictions['probabilities'], strict=True))}
    return result


@torch.inference_mode()
def probabilities(head, values, targets):
    require(values.dtype == np.float32 and values.shape == (len(targets), 1037) and np.isfinite(values).all(),
            'Expected phonetic1024 then scalar13 features')
    x = ((torch.from_numpy(values)-head['mean'])/head['std'])[:, None, :]
    phones = torch.tensor([[row['targetId']] for row in targets], dtype=torch.long)
    mask = torch.ones_like(phones, dtype=torch.bool)
    p = head['model'](x, mask, phones, mask)[:, 0].softmax(-1).numpy().astype(np.float64)
    require(np.isfinite(p).all() and np.allclose(p.sum(1), 1, atol=1e-6, rtol=0), 'Invalid rating probabilities')
    return p


def assert_parity(actual, expected, tolerance, name):
    a, b = np.asarray(actual), np.asarray(expected)
    require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), 'Invalid original parity shapes: '+name)
    maximum = float(np.max(np.abs(a.astype(np.float64)-b.astype(np.float64))))
    require(maximum <= tolerance, f'Original {name} parity failed: {maximum} > {tolerance}; do not relax post hoc')
    return maximum


def load_posteriors(path, expected_sha):
    payload = path.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == expected_sha, 'Posterior artifact differs')
    values = np.frombuffer(payload, dtype='<f4').reshape((-1, 392))
    # Keep the authoritative index pin; never adopt a newer file digest after checking.
    return values, {'path': str(path.resolve()), 'sha256': expected_sha}


def probability_shift(original, changed):
    a, b = np.asarray(original), np.asarray(changed)
    require(a.shape == b.shape and a.ndim == 2 and a.shape[1] == 3 and len(a) > 0
            and np.isfinite(a).all() and np.isfinite(b).all()
            and (a >= 0).all() and (b >= 0).all()
            and np.allclose(a.sum(1), 1, atol=1e-6) and np.allclose(b.sum(1), 1, atol=1e-6), 'Invalid paired probabilities')
    delta = b-a; tv = np.abs(delta).sum(1)/2; rating = delta@np.arange(3)
    return {'targets': len(a), 'meanTotalVariation': float(tv.mean()), 'maxTotalVariation': float(tv.max()),
            'meanExpectedRatingShift': float(rating.mean()), 'meanAbsoluteExpectedRatingShift': float(np.abs(rating).mean()),
            'maxAbsoluteExpectedRatingShift': float(np.abs(rating).max()),
            'argmaxClassChanges': int(np.count_nonzero(a.argmax(1) != b.argmax(1))),
            'meanRating0ProbabilityShift': float(delta[:, 0].mean()),
            'meanBelow2ProbabilityShift': float(delta[:, :2].sum(1).mean())}


def aligned_features(logp, frames, clip, recipe):
    estimates, diagnostics = local.local_features(logp, clip['mappedTokenIds'],
                                                 [row['canonicalIndex'] for row in clip['targets']], recipe)
    targets = []
    for row, estimate in zip(clip['targets'], estimates, strict=True):
        require(estimate['canonicalIndex'] == row['canonicalIndex'], 'Canonical target order changed')
        start, end = estimate['intervalFrames']
        targets.append({**row, **estimate, 'estimatedPoolingWindowFrames': [max(0, start-2), min(len(logp), end+2)]})
    pooled, _ = extraction.pooled_vectors(frames, targets, len(logp))
    scalars = np.asarray([row['scalarFeatures'] for row in targets], dtype=np.float32)
    require(scalars.shape == (len(targets), 13) and np.isfinite(scalars).all(), 'Invalid scalar feature order')
    return targets, scalars, pooled, diagnostics


def run(plan_path, plan_sha, node='node'):
    require(digest(plan_path) == plan_sha, 'Caller-supplied plan digest differs')
    plan = read_json(plan_path); bindings = dict(plan['bindings'])
    bindings['plan'] = {'path': str(plan_path.resolve()), 'sha256': plan_sha}
    guard(bindings)
    require(plan['recipe'] == read_json(RECIPE) and plan['complete'] is True
            and plan['partition'] == 'innerValidationRows' and plan['fold'] == 0
            and all(plan.get(key) is False for key in FALSE_FLAGS), 'Diagnostic plan scope changed')
    recipe = plan['recipe']; started = time.perf_counter()
    original = read_json(Path(bindings['originalFeatures']['path']))
    validate_selected_plan(plan, read_json(Path(bindings['cohort']['path'])), read_json(Path(bindings['splits']['path'])),
                           read_json(Path(original['manifestPath'])), original)
    output = plan_path.parent/'diagnostic'
    require(not output.exists(), 'No implicit resume; choose a new prepared diagnostic after diagnosis')
    output.mkdir(mode=0o700)
    try:
        subprocess.run([node, str(HERE/'multiphone_capture_ctc.ts'), str(plan_path.resolve()), plan_sha,
                        str((output/'ctc').resolve())], check=True,
                       env={**os.environ, 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'})
        ctc_path = output/'ctc/index.json'
        bindings['newCTCIndex'] = pin(ctc_path)
        ctc = read_json(ctc_path)
        require(ctc['complete'] is True and ctc['planSha256'] == plan_sha and ctc['fetchAttempts'] == 0
                and ctc['sessionOptions'] == recipe['ctcSessionOptions']
                and ctc['checkpoint'] == read_json(Path(original['ctcIndexPath']).parent/'config.json')['checkpoint']
                and set(ctc['entries']) == {c['id']+'/'+v for c in plan['clips'] for v in CONDITIONS}, 'CTC run binding differs')
        torch.set_num_threads(2)
        os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
        phonetic_recipe = read_json(extraction.RECIPE)
        snapshot = HERE/'outputs/model-cache'/('models--'+phonetic_recipe['modelId'].replace('/', '--'))/'snapshots'/phonetic_recipe['revision']
        encoder = extraction.PhoneticEncoder(snapshot, phonetic_recipe)
        heads = load_heads(recipe)
        original_rows = {r['rowIndex']: r for r in original['rows']}
        positions = {index: offset for offset, index in enumerate(original['rowIndices'])}
        baseline_scalars = np.load(Path(bindings['feature/headInput/scalars']['path']), mmap_mode='r', allow_pickle=False)
        baseline_target = np.load(Path(bindings['feature/headInput/target']['path']), mmap_mode='r', allow_pickle=False)
        local_recipe = read_json(local.RECIPE)
        results = []
        for clip in plan['clips']:
            per_condition = {}; original_result = None
            for variant in clip['variants']:
                condition = variant['condition']; key = clip['id']+'/'+condition
                entry = ctc['entries'][key]
                require(entry['clipId'] == clip['id'] and entry['condition'] == condition
                        and entry['audioSha256'] == variant['audioSha256'] and entry['sampleCount'] == clip['sampleCount'],
                        'Transformed posterior source identity differs')
                path = output/'ctc'/entry['path']
                require(path.resolve().is_relative_to((output/'ctc').resolve()), 'Posterior path escaped diagnostic')
                logp, bindings['posterior/'+key] = load_posteriors(path, entry['sha256'])
                expected_frames = local.convolution_frames(clip['sampleCount'], local_recipe)
                local.validate_log_prob(logp, expected_frames)
                samples = read_rating_pcm(Path(variant['audioPath']), variant['audioSha256'])
                t0 = time.perf_counter(); frames = encoder(samples)
                targets, scalars, pooled, diagnostics = aligned_features(logp, frames, clip, local_recipe)
                values = np.concatenate((pooled, scalars), axis=1)
                predicted = {regime: probabilities(head, values, targets) for regime, head in heads.items()}
                parity = None
                if condition == 'original':
                    source = np.fromfile(bindings['originalCTC/'+clip['id']]['path'], dtype='<f4').reshape(logp.shape)
                    offsets = [positions[row['rowIndex']] for row in targets]
                    limits = recipe['originalParityAbsoluteTolerances']
                    parity = {'ctcLogPosterior': assert_parity(logp, source, limits['ctcLogPosterior'], 'CTC'),
                              'scalar': assert_parity(scalars, baseline_scalars[offsets], limits['scalar'], 'scalars'),
                              'phoneticPooled': assert_parity(pooled, baseline_target[offsets], limits['phoneticPooled'], 'phonetic vectors')}
                    for row in targets:
                        previous = original_rows[row['rowIndex']]
                        require(all(row[k] == previous[k] for k in IDENTITY+('intervalFrames', 'estimatedPoolingWindowFrames')),
                                'Original target identity/alignment parity failed')
                    parity['probabilities'] = {regime: assert_parity(p, [heads[regime]['predictions'][row['rowIndex']] for row in targets],
                                                     limits['probability'], regime+' predictions') for regime, p in predicted.items()}
                else:
                    require(original_result is not None, 'Original baseline must run before perturbations')
                result = {'condition': condition, 'waveform': variant, 'targets': targets,
                          'probabilities': {regime: p.tolist() for regime, p in predicted.items()},
                          'canonicalPathDiagnostics': diagnostics, 'originalParity': parity,
                          'phoneticAndHeadSeconds': time.perf_counter()-t0}
                if condition == 'original': original_result = result
                result['shiftsFromOriginal'] = {regime: probability_shift(original_result['probabilities'][regime], p)
                                               for regime, p in predicted.items()}
                result['alignmentMovementFrames'] = [{'rowId': row['rowId'],
                    'startShift': row['intervalFrames'][0]-base['intervalFrames'][0],
                    'endShift': row['intervalFrames'][1]-base['intervalFrames'][1],
                    'poolingStartShift': row['estimatedPoolingWindowFrames'][0]-base['estimatedPoolingWindowFrames'][0],
                    'poolingEndShift': row['estimatedPoolingWindowFrames'][1]-base['estimatedPoolingWindowFrames'][1]}
                    for row, base in zip(targets, original_result['targets'], strict=True)]
                per_condition[condition] = result
            results.append({'clipId': clip['id'], 'speakerId': clip['speakerId'], 'age': clip['age'], 'conditions': per_condition})
            print(f"Completed diagnostic clip {len(results)}/{len(plan['clips'])}", flush=True)
        summary = {}
        for condition in CONDITIONS:
            summary[condition] = {regime: probability_shift(
                np.concatenate([v['conditions']['original']['probabilities'][regime] for v in results]),
                np.concatenate([v['conditions'][condition]['probabilities'][regime] for v in results])) for regime in REGIMES}
        report = {'schemaVersion': 1, 'complete': True, 'planPath': str(plan_path.resolve()), 'planSha256': plan_sha,
                  'bindings': bindings, 'speakers': len(results), 'encodedWaveforms': len(results)*4,
                  'summaryTargetWeighted': summary, 'clips': results, 'elapsedSeconds': time.perf_counter()-started,
                  'ctcRuntime': ctc, 'torch': str(torch.__version__), 'numpy': np.__version__,
                  'interpretation': recipe['limitations'], **FALSE_FLAGS}
        guard(bindings)
        atomic_json(output/'report.json', report)
        return {'report': str(output/'report.json'), 'sha256': digest(output/'report.json'), 'complete': True}
    except Exception as error:
        atomic_json(output/'failure.json', {'complete': False, 'planSha256': plan_sha,
                    'error': f'{type(error).__name__}: {error}', 'elapsedSeconds': time.perf_counter()-started})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('run'); p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--plan-sha256', required=True); p.add_argument('--node', default='node')
    args = parser.parse_args()
    if args.command == 'prepare':
        print(json.dumps(prepare(args.output), indent=2))
    else:
        with (args.plan.parent/'.diagnostic.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(json.dumps(run(args.plan, args.plan_sha256, args.node), indent=2))
