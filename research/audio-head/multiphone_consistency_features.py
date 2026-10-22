"""Fixed fold-zero, label-free paired noise features for six research arms.

Preparation verifies metadata and local files only. Run performs clean parity
first, then one predeclared noisy view per inner fit/validation clip. No human
rating is copied into the derived artifacts, and no head is fitted here.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import torch

import multiphone_capture_sensitivity as capture
import multiphone_phonetic_head as head
import multiphone_phonetic_features as extraction
import multiphone_local_features as local
from multiphone_cache import atomic_json, digest
from multiphone_train import verify_partitions
from speechocean_r_probe import read_rating_pcm

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'experiments/multiphone-consistency-features-v1.json'
FLAGS = {key: False for key in ('trainingPerformed', 'outerInferencePerformed', 'authorTestInferencePerformed',
    'labelsTransferred', 'learnerFeedbackEligible', 'clinicalUseEligible', 'frameTimesValidated')}
IDENTITY = capture.IDENTITY
SOURCES = tuple(dict.fromkeys(capture.SOURCES + ('multiphone_consistency_features.py',
    'multiphone_consistency_ctc.ts', 'multiphone_research_ctc.ts')))
read_json, require = extraction.read_json, extraction.require


def pin(path, expected=None):
    path = Path(path).absolute()
    actual = digest(path)
    require(expected is None or actual == expected, 'Pinned consistency input differs')
    return {'path': str(path), 'sha256': expected or actual}


def read_bound(path, expected=None):
    import json
    payload = Path(path).read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    require(expected is None or sha == expected, 'Pinned consistency JSON differs')
    return json.loads(payload), {'path': str(Path(path).absolute()), 'sha256': expected or sha}


def guard(bindings):
    checked = {}
    for value in bindings.values():
        if value['path'] not in checked:
            checked[value['path']] = digest(Path(value['path']))
        require(checked[value['path']] == value['sha256'], 'Consistency source, input or artifact changed')


def phonetic_snapshot(recipe):
    return HERE / 'outputs/model-cache' / ('models--' + recipe['modelId'].replace('/', '--')) / 'snapshots' / recipe['revision']


def lexical_checkpoint_pins(recipe):
    # Runtime loads these snapshot paths. Pin the symlinks' lexical names too,
    # not merely the previously resolved blob paths inherited from clean data.
    return {'phoneticSnapshot/' + name: pin(phonetic_snapshot(recipe) / name, sha)
            for name, sha in recipe['artifactSha256'].items()}


def select_subset(cohort, splits, original, manifest, recipe):
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train' and recipe['fold'] == 0,
            'Consistency extraction is author-train fold zero only')
    fold = splits['folds'][0]
    verify_partitions(cohort, fold)
    indices = sorted(fold['innerFitRows'] + fold['innerValidationRows'])
    require(len(indices) == len(set(indices)) == recipe['expectedRows'], 'Inner union row coverage differs')
    selected = set(indices)
    source_rows = {row['rowIndex']: row for row in original['rows']}
    canonical = {clip['id']: clip for clip in manifest['clips']}
    clips = []
    for clip_index, source in enumerate(cohort['clips']):
        target_indices = sorted(i for i in selected if cohort['rows'][i]['clipIndex'] == clip_index)
        if not target_indices:
            continue
        full = sorted(i for i, row in enumerate(cohort['rows']) if row['clipIndex'] == clip_index and row['trainingEligible'])
        require(target_indices == full, 'A clip crosses fit/validation/outer row boundaries')
        c = canonical[source['id']]
        require(c['clipIndex'] == clip_index and sorted(row['rowIndex'] for row in c['targetRows']) == full,
                'Canonical clip/target coverage differs')
        targets = [{key: source_rows[i][key] for key in IDENTITY} for i in target_indices]
        for i, target in zip(target_indices, targets, strict=True):
            row = cohort['rows'][i]
            require(target['rowId'] == row['id'] and all(target[key] == row[key] for key in
                    ('clipId', 'targetId', 'targetPhone', 'wordIndex', 'phoneIndex'))
                    and row['trainingEligible'] is True and 0 <= row['targetId'] < 23
                    and c['canonicalPhones'][target['canonicalIndex']] == row['targetPhone'], 'Target identity differs')
        clips.append({**{key: source[key] for key in ('id', 'speakerId', 'age', 'audioPath', 'audioSha256', 'sampleCount')},
            'clipIndex': clip_index, **{key: c[key] for key in ('canonicalPhones', 'mappedTokenIds', 'mappingAmbiguities')},
            'targets': targets})
    clips.sort(key=lambda clip: clip['id'])
    require(len(clips) == recipe['expectedClips'] and {t['rowIndex'] for c in clips for t in c['targets']} == selected,
            'Inner clip coverage differs')
    fit_ids = {cohort['rows'][i]['clipId'] for i in fold['innerFitRows']}
    parity = {}
    for regime in ('all-age', 'child-only'):
        candidates = [c for c in clips if c['id'] in fit_ids and (regime == 'all-age' or 6 <= c['age'] <= 12)]
        require(candidates, 'Missing fitting population for parity')
        for reason, clip in (('first', min(candidates, key=lambda c: c['id'])),
                             ('longest', min(candidates, key=lambda c: (-c['sampleCount'], c['id'])))):
            parity.setdefault(clip['id'], []).append(regime + '/' + reason)
    return indices, clips, [{'clipId': key, 'reasons': value} for key, value in sorted(parity.items())]


def checked_metadata(recipe):
    require(recipe['condition'] == 'noise20db' and recipe['device'] == 'cpu' and recipe['threads'] == 2
            and recipe['partition'] == 'innerFitRows+innerValidationRows'
            and recipe['originalParityAbsoluteTolerances'] == {'ctcLogPosterior': 0., 'scalar': 0., 'phoneticPooled': 2e-6},
            'Unexpected extraction recipe')
    bindings = {'recipe': pin(RECIPE), **{'source/' + name: pin(HERE / name) for name in SOURCES}}
    bindings['protocol'] = pin(HERE / '../../docs/model/multiphone-noise-consistency-protocol.md')
    require(bindings['source/multiphone_capture_sensitivity.py']['sha256'] == recipe['captureSourceSha256'],
            'Fixed perturbation implementation differs')
    bindings['cleanFeatureBinding'] = pin(HERE / recipe['featureBindingPath'], recipe['featureBindingSha256'])
    bound = head.load_bound(Path(bindings['cleanFeatureBinding']['path']), read_json(head.RECIPE))
    bindings.update({'clean/' + name: value for name, value in bound['bindings'].items()})
    evidence = read_json(Path(bindings['cleanFeatureBinding']['path']))
    bindings['cohort'] = pin(evidence['cohortPath'], recipe['cohortSha256'])
    bindings['splits'] = pin(evidence['splitsPath'], recipe['splitsSha256'])
    bindings['localRecipe'] = pin(local.RECIPE, recipe['localRecipeSha256'])
    bindings['phoneticRecipe'] = pin(extraction.RECIPE, recipe['phoneticRecipeSha256'])
    bindings.update(lexical_checkpoint_pins(read_json(extraction.RECIPE)))
    original = read_json(Path(evidence['originalFeaturesPath']))
    manifest = read_json(Path(original['manifestPath']))
    indices, clips, parity = select_subset(bound['cohort'], bound['splits'], original, manifest, recipe)
    ctc_path = Path(original['ctcIndexPath'])
    ctc = read_json(ctc_path)
    for clip in clips:
        bindings['sourceAudio/' + clip['id']] = pin(clip['audioPath'], clip['audioSha256'])
    for item in parity:
        entry = ctc['entries'][item['clipId']]
        bindings['parityCTC/' + item['clipId']] = pin(ctc_path.parent / entry['path'], entry['sha256'])
    return bound, original, indices, clips, parity, bindings, read_json(ctc_path.parent / 'config.json')['checkpoint']


def prepare(output):
    require(not output.exists() and output.absolute().is_relative_to((HERE / 'outputs').absolute()), 'Choose fresh ignored plan directory')
    recipe, recipe_pin = read_bound(RECIPE)
    _, _, indices, clips, parity, inputs, checkpoint = checked_metadata(recipe)
    require(inputs['recipe'] == recipe_pin, 'Recipe changed during preparation')
    plan = {'schemaVersion': 1, 'complete': True, 'recipe': recipe, 'recipeSha256': recipe_pin['sha256'],
        'inputFiles': inputs, 'rowIndices': indices, 'clips': clips, 'parityClips': parity,
        'ctcCheckpoint': checkpoint, 'authorPartition': 'train', 'fold': 0,
        'partition': recipe['partition'], 'expectedRows': len(indices), 'expectedClips': len(clips), **FLAGS}
    guard(inputs)
    output.mkdir(parents=True, mode=0o700)
    atomic_json(output / 'plan.json', plan)
    return {'planPath': str((output / 'plan.json').absolute()), 'planSha256': digest(output / 'plan.json'),
            'rows': len(indices), 'clips': len(clips), 'parityClips': parity}


def validate_plan(plan, plan_pin):
    require(plan['complete'] is True and plan['recipeSha256'] == digest(RECIPE)
            and plan['recipe'] == read_json(RECIPE) and all(plan[key] is False for key in FLAGS), 'Plan recipe or scope differs')
    inputs = {**plan['inputFiles'], 'plan': plan_pin}
    guard(inputs)
    bound = head.load_bound(Path(inputs['cleanFeatureBinding']['path']), read_json(head.RECIPE))
    evidence = read_json(Path(inputs['cleanFeatureBinding']['path']))
    original = read_json(Path(evidence['originalFeaturesPath']))
    indices, clips, parity = select_subset(bound['cohort'], bound['splits'], original,
                                         read_json(Path(original['manifestPath'])), plan['recipe'])
    require(plan['rowIndices'] == indices and plan['clips'] == clips and plan['parityClips'] == parity
            and plan['expectedRows'] == len(indices) and plan['expectedClips'] == len(clips)
            and plan['authorPartition'] == 'train' and plan['fold'] == 0 and plan['partition'] == plan['recipe']['partition'],
            'Prepared metadata or parity selection differs')
    for name in SOURCES:
        require(inputs['source/' + name] == pin(HERE / name), 'Extractor source differs from plan')
    require(all(inputs[name] == value for name, value in lexical_checkpoint_pins(read_json(extraction.RECIPE)).items()),
            'Lexical runtime checkpoint binding differs')
    require(all(inputs['clean/' + name] == value for name, value in bound['bindings'].items()), 'Clean feature binding differs')
    return bound, original, inputs


def make_batch(plan, plan_sha, phase, entries, inputs, directory, node):
    batch = {'schemaVersion': 1, 'sourcePlanSha256': plan_sha, 'authorPartition': 'train', 'fold': 0,
        'partition': plan['partition'], 'phase': phase, 'inputFiles': dict(inputs), 'entries': entries,
        'ctcCheckpoint': plan['ctcCheckpoint'], 'sessionOptions': plan['recipe']['ctcSessionOptions']}
    for entry in entries:
        batch['inputFiles']['audio/' + entry['id']] = {'path': entry['audioPath'], 'sha256': entry['audioSha256']}
    batch_path = directory / (phase + '-ctc-plan.json')
    atomic_json(batch_path, batch)
    batch_pin = pin(batch_path)
    subprocess.run([node, str(HERE / 'multiphone_consistency_ctc.ts'), str(batch_path.absolute()), batch_pin['sha256'],
                    str((directory / (phase + '-ctc')).absolute())], check=True,
                   env={**os.environ, 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'})
    index_path = directory / (phase + '-ctc') / 'index.json'
    index, index_pin = read_bound(index_path)
    require(index['complete'] is True and index['sourcePlanSha256'] == plan_sha
            and index['batchPlanSha256'] == batch_pin['sha256'] and index['phase'] == phase
            and index['checkpoint'] == plan['ctcCheckpoint'] and index['fetchAttempts'] == 0
            and index['sessionOptions'] == plan['recipe']['ctcSessionOptions']
            and set(index['entries']) == {e['id'] for e in entries}, 'CTC batch binding or coverage differs')
    pins = {'batch/' + phase: batch_pin, 'ctcIndex/' + phase: index_pin}
    for entry in entries:
        actual = index['entries'][entry['id']]
        require(all(actual[key] == value for key, value in entry.items()) and actual['path'] == entry['id'] + '.f32'
                and actual['frames'] == local.convolution_frames(entry['sampleCount'], read_json(local.RECIPE)),
                'CTC entry source or frame grid differs')
        pins['ctc/' + phase + '/' + entry['id']] = {'path': str((index_path.parent / actual['path']).absolute()), 'sha256': actual['sha256']}
    guard(pins)
    return index, pins


def load_logp(index, directory, clip_id):
    entry = index['entries'][clip_id]
    values, authoritative = capture.load_posteriors(directory / entry['path'], entry['sha256'])
    local.validate_log_prob(values, entry['frames'])
    return values, authoritative


def parity_checks(plan, clips, index, directory, encoder, bound, original):
    result = []
    old_rows = {row['rowIndex']: row for row in original['rows']}
    for clip in clips:
        logp, _ = load_logp(index, directory / 'parity-ctc', clip['id'])
        old_pin = plan['inputFiles']['parityCTC/' + clip['id']]
        old_logp, _ = capture.load_posteriors(Path(old_pin['path']), old_pin['sha256'])
        frames = encoder(read_rating_pcm(Path(clip['audioPath']), clip['audioSha256']))
        targets, scalars, pooled, _ = capture.aligned_features(logp, frames, clip, read_json(local.RECIPE))
        positions = [bound['positions'][row['rowIndex']] for row in targets]
        limits = plan['recipe']['originalParityAbsoluteTolerances']
        measurements = {'ctcLogPosterior': capture.assert_parity(logp, old_logp, limits['ctcLogPosterior'], 'consistency CTC'),
            'scalar': capture.assert_parity(scalars, bound['scalars'][positions], limits['scalar'], 'consistency scalars'),
            'phoneticPooled': capture.assert_parity(pooled, bound['arrays']['target'][positions], limits['phoneticPooled'], 'consistency vectors')}
        require(all(all(row[key] == old_rows[row['rowIndex']][key] for key in
                    IDENTITY + ('intervalFrames', 'estimatedPoolingWindowFrames')) for row in targets), 'Original window parity differs')
        result.append({'clipId': clip['id'], 'maximumAbsoluteDifferences': measurements, 'windowsExact': True})
    return result


def write_noisy(clip, output, seed):
    samples = read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
    require(len(samples) == clip['sampleCount'], 'Original sample count differs')
    payload, values, measured = capture.transform(samples.numpy(), 'noise20db', clip['audioSha256'], seed)
    with output.open('xb') as stream:
        output.chmod(0o600)
        stream.write(payload)
    sha = hashlib.sha256(payload).hexdigest()
    require(np.array_equal(read_rating_pcm(output, sha).numpy(), values), 'Noisy PCM16 round trip differs')
    return {'id': clip['id'], 'clipId': clip['id'], 'audioPath': str(output.absolute()), 'audioSha256': sha,
            'sampleCount': len(values)}, measured


def save_unit(directory, clip, noisy_entry, recording, rows, target, scalars, ctc_entry, plan_sha):
    directory.mkdir(parents=True, mode=0o700)
    path = directory / 'features.npz'
    with path.open('xb') as stream:
        path.chmod(0o600)
        np.savez(stream, target=target, scalars=scalars)
    with np.load(path, allow_pickle=False) as saved:
        require(np.array_equal(saved['target'], target) and np.array_equal(saved['scalars'], scalars),
                'Saved per-clip vectors differ from the computed features')
    metadata = {'clipId': clip['id'], 'sourceAudioSha256': clip['audioSha256'], 'noisyAudio': noisy_entry,
        'recording': recording, 'rows': [{key: row[key] for key in IDENTITY + ('intervalFrames', 'estimatedPoolingWindowFrames')} for row in rows],
        'frames': ctc_entry['frames'], 'ctcSha256': ctc_entry['sha256'], 'planSha256': plan_sha, 'labelsTransferred': False,
        'featureSha256': digest(path)}
    atomic_json(directory / 'entry.json', metadata)
    return {'path': str(path.absolute()), 'sha256': metadata['featureSha256'],
            'entryPath': str((directory / 'entry.json').absolute()), 'entrySha256': digest(directory / 'entry.json')}


def checked_unit(entry, clip, plan_sha, ctc_entry, audio_entry):
    require(digest(Path(entry['path'])) == entry['sha256'] and digest(Path(entry['entryPath'])) == entry['entrySha256'],
            'Per-clip feature artifact changed')
    metadata = read_json(Path(entry['entryPath']))
    require(metadata['clipId'] == clip['id'] and metadata['sourceAudioSha256'] == clip['audioSha256']
            and metadata['planSha256'] == plan_sha and metadata['featureSha256'] == entry['sha256']
            and metadata['noisyAudio'] == audio_entry and metadata['ctcSha256'] == ctc_entry['sha256']
            and metadata['frames'] == ctc_entry['frames'] and metadata['labelsTransferred'] is False
            and [{key: row[key] for key in IDENTITY} for row in metadata['rows']] == clip['targets'],
            'Per-clip feature source, row or partition binding differs')
    for row in metadata['rows']:
        start, end = row['intervalFrames']
        require(type(start) is int and type(end) is int and 0 <= start < end <= metadata['frames']
                and row['estimatedPoolingWindowFrames'] == [max(0, start - 2), min(metadata['frames'], end + 2)],
                'Noisy estimated window geometry differs')
    with np.load(entry['path'], allow_pickle=False) as arrays:
        require(set(arrays.files) == {'target', 'scalars'}, 'Unexpected per-clip feature columns')
        target, scalars = arrays['target'].copy(), arrays['scalars'].copy()
    require(target.dtype == scalars.dtype == np.float32 and target.shape == (len(clip['targets']), 1024)
            and scalars.shape == (len(clip['targets']), 13) and np.isfinite(target).all() and np.isfinite(scalars).all(),
            'Invalid per-clip feature matrices')
    return target, scalars, metadata


def assemble(plan, plan_sha, entries, noisy, ctc, output):
    positions = {index: offset for offset, index in enumerate(plan['rowIndices'])}
    target = np.empty((len(positions), 1024), dtype=np.float32)
    scalars = np.empty((len(positions), 13), dtype=np.float32)
    rows = [None] * len(positions)
    require(set(entries) == set(noisy) == set(ctc['entries']) == {clip['id'] for clip in plan['clips']}, 'Feature clip coverage differs')
    pins = {}
    for clip in plan['clips']:
        entry = entries[clip['id']]
        t, s, metadata = checked_unit(entry, clip, plan_sha, ctc['entries'][clip['id']], noisy[clip['id']])
        for offset, row in enumerate(metadata['rows']):
            position = positions[row['rowIndex']]
            require(rows[position] is None, 'Duplicate target feature row')
            target[position], scalars[position], rows[position] = t[offset], s[offset], row
        pins['unit/' + clip['id']] = {'path': entry['path'], 'sha256': entry['sha256']}
        pins['unitMeta/' + clip['id']] = {'path': entry['entryPath'], 'sha256': entry['entrySha256']}
    require(all(row is not None for row in rows), 'Incomplete feature target coverage')
    descriptors = {}
    for name, values in (('target', target), ('scalars', scalars)):
        path = output / (name + '.npy')
        with path.open('xb') as stream:
            path.chmod(0o600)
            np.save(stream, values, allow_pickle=False)
        descriptors[name] = {'path': path.name, 'sha256': digest(path), 'dtype': 'float32', 'shape': list(values.shape)}
        pins['matrix/' + name] = pin(path, descriptors[name]['sha256'])
    # Audit bytes reloaded from disk, not only the arrays supplied to np.save.
    saved_target = np.load(output / 'target.npy', mmap_mode='r', allow_pickle=False)
    saved_scalars = np.load(output / 'scalars.npy', mmap_mode='r', allow_pickle=False)
    for clip in plan['clips']:
        t, s, metadata = checked_unit(entries[clip['id']], clip, plan_sha, ctc['entries'][clip['id']], noisy[clip['id']])
        indices = [positions[row['rowIndex']] for row in metadata['rows']]
        require(np.array_equal(saved_target[indices], t) and np.array_equal(saved_scalars[indices], s),
                'Assembled target order differs')
    return rows, descriptors, pins


def run(plan_path, plan_sha, node='node'):
    plan, plan_pin = read_bound(plan_path, plan_sha)
    bound, original, inputs = validate_plan(plan, plan_pin)
    output = plan_path.parent / 'features'
    # Stable paths are needed by the independently pinned per-clip artifacts.
    # features.json is the sole atomic completion marker, written only at the end.
    stage = output
    require(not stage.exists(), 'Fresh extraction only; preserve any prior incomplete run')
    stage.mkdir(mode=0o700)
    started = time.perf_counter()
    try:
        parity_ids = {entry['clipId'] for entry in plan['parityClips']}
        parity_clips = [clip for clip in plan['clips'] if clip['id'] in parity_ids]
        parity_entries = [{key: clip[key] for key in ('id', 'audioPath', 'audioSha256', 'sampleCount')} | {'clipId': clip['id']} for clip in parity_clips]
        parity_ctc, derived = make_batch(plan, plan_sha, 'parity', parity_entries, inputs, stage, node)
        torch.set_num_threads(2)
        os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
        phonetic_recipe = read_json(extraction.RECIPE)
        snapshot = phonetic_snapshot(phonetic_recipe)
        encoder = extraction.PhoneticEncoder(snapshot, phonetic_recipe)
        parity = parity_checks(plan, parity_clips, parity_ctc, stage, encoder, bound, original)
        atomic_json(stage / 'parity.json', {'complete': True, 'planSha256': plan_sha, 'clips': parity,
            'tolerances': plan['recipe']['originalParityAbsoluteTolerances']})
        derived['parity'] = pin(stage / 'parity.json')
        guard({**inputs, **derived})
        print('Original fitting-clip parity passed; starting the fixed noisy extraction', flush=True)
        (stage / 'audio').mkdir(mode=0o700)
        noisy, measurements = {}, {}
        for clip in plan['clips']:
            entry, measurement = write_noisy(clip, stage / 'audio' / (clip['id'] + '.wav'), plan['recipe']['seed'])
            noisy[clip['id']], measurements[clip['id']] = entry, measurement
            derived['noisy/' + clip['id']] = {'path': entry['audioPath'], 'sha256': entry['audioSha256']}
        ctc, ctc_pins = make_batch(plan, plan_sha, 'noise20db', list(noisy.values()), {**inputs, **derived}, stage, node)
        derived.update(ctc_pins)
        entries = {}
        for ordinal, clip in enumerate(plan['clips'], 1):
            waveform = noisy[clip['id']]
            logp, _ = load_logp(ctc, stage / 'noise20db-ctc', clip['id'])
            hidden = encoder(read_rating_pcm(Path(waveform['audioPath']), waveform['audioSha256']))
            rows, scalars, pooled, _ = capture.aligned_features(logp, hidden, clip, read_json(local.RECIPE))
            entries[clip['id']] = save_unit(stage / 'clips' / clip['id'], clip, waveform, measurements[clip['id']],
                                          rows, pooled, scalars, ctc['entries'][clip['id']], plan_sha)
            atomic_json(stage / 'status.json', {'complete': False, 'clips': ordinal, 'expectedClips': len(plan['clips'])})
            if ordinal % 50 == 0:
                print(f'Phonetic {ordinal}/{len(plan["clips"])}', flush=True)
        rows, descriptors, unit_pins = assemble(plan, plan_sha, entries, noisy, ctc, stage)
        derived.update(unit_pins)
        index = {'complete': True, 'planSha256': plan_sha, 'rowIndices': plan['rowIndices'], 'entries': entries,
                 'noisyAudio': noisy, 'recordingMeasurements': measurements, 'clipCount': len(entries), **FLAGS}
        atomic_json(stage / 'index.json', index)
        derived['index'] = pin(stage / 'index.json')
        atomic_json(stage / 'status.json', {'complete': True, 'clips': len(entries), 'rows': len(rows)})
        derived['status'] = pin(stage / 'status.json')
        report = {'schemaVersion': 1, 'complete': True, 'completeCoverage': True, 'failedRows': [], 'unmappableRows': [],
            'authorPartition': 'train', 'fold': 0, 'partition': plan['partition'], 'condition': 'noise20db', 'snrDb': 20,
            'planPath': str(plan_path.absolute()), 'planSha256': plan_sha, 'recipeSha256': plan['recipeSha256'],
            'inputFiles': inputs, 'derivedFiles': derived, 'featureSourceBindingSha256': plan['recipe']['featureBindingSha256'],
            'cleanFeatureBindingSha256': plan['recipe']['featureBindingSha256'],
            'targetFeatures': descriptors['target'], 'scalarFeatures': descriptors['scalars'],
            'scalarFeatureNames': local.SCALAR_NAMES, 'rowIndices': plan['rowIndices'], 'rows': rows,
            'expectedRows': len(rows), 'expectedClips': len(entries), 'indexPath': 'index.json',
            'indexSha256': derived['index']['sha256'], 'originalParity': parity, 'originalParityComplete': True,
            'parityPath': 'parity.json', 'paritySha256': derived['parity']['sha256'],
            'elapsedSeconds': time.perf_counter() - started, 'torch': str(torch.__version__), 'numpy': np.__version__, **FLAGS}
        guard({**inputs, **derived})
        # Publish only the atomic completion marker after every file is bound.
        atomic_json(stage / 'features.json', report)
        return {'complete': True, 'featuresPath': str((stage / 'features.json').absolute()),
                'featuresSha256': digest(stage / 'features.json'), 'rows': len(rows), 'clips': len(entries)}
    except Exception as error:
        atomic_json(stage / 'failure.json', {'complete': False, 'planSha256': plan_sha,
            'error': f'{type(error).__name__}: {error}', 'elapsedSeconds': time.perf_counter() - started})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('run'); p.add_argument('--plan', type=Path, required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--node', default='node')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.output)
    else:
        with (args.plan.parent / '.extraction.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = run(args.plan, args.plan_sha256, args.node)
    import json
    print(json.dumps(result, indent=2), flush=True)
