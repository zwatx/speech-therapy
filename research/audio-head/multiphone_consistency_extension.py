"""Complete a label-free author-training noise cache without rewriting old units.

Only the missing clips receive encoder inference. Full-cohort waveform extraction
includes old fold-zero outer clips; no rating-head evaluation occurs here.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import torch

import multiphone_consistency_features as original
import multiphone_consistency_train as consumer

HERE = original.HERE
RECIPE = HERE / 'experiments/multiphone-consistency-extension-v1.json'
FLAGS = {key: False for key in ('trainingPerformed', 'outerModelEvaluationPerformed',
    'authorTestInferencePerformed', 'labelsTransferred', 'learnerFeedbackEligible',
    'clinicalUseEligible', 'frameTimesValidated')}
SOURCES = tuple(dict.fromkeys(original.SOURCES + ('multiphone_consistency_train.py',
    'multiphone_consistency_extension.py', 'multiphone_consistency_extension_ctc.ts')))
read_json, read_bound, require, pin, guard = (original.read_json, original.read_bound,
    original.require, original.pin, original.guard)
digest, atomic_json = original.digest, original.atomic_json


def full_metadata(cohort, splits, clean, manifest, recipe, old_plan):
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train', 'Only author training is permitted')
    for fold in splits['folds']:
        original.verify_partitions(cohort, fold)
    indices = [i for i, row in enumerate(cohort['rows']) if row['trainingEligible']]
    clean_rows = {row['rowIndex']: row for row in clean['rows']}
    require(len(clean_rows) == len(clean['rows']) and set(clean_rows) == set(indices), 'Clean row coverage differs')
    canonical = {clip['id']: clip for clip in manifest['clips']}
    require(len(canonical) == len(manifest['clips']), 'Duplicate canonical clip')
    by_clip = {}
    for i in indices:
        by_clip.setdefault(cohort['rows'][i]['clipIndex'], []).append(i)
    clips = []
    for clip_index, target_indices in sorted(by_clip.items()):
        source = cohort['clips'][clip_index]
        c = canonical[source['id']]
        fields = ('id', 'speakerId', 'age', 'audioPath', 'audioSha256', 'sampleCount')
        require(all(c[key] == source[key] for key in fields if key != 'age') and c['clipIndex'] == clip_index
                and sorted(r['rowIndex'] for r in c['targetRows']) == target_indices, 'Canonical clip source differs')
        targets = [{key: clean_rows[i][key] for key in original.IDENTITY} for i in target_indices]
        for i, target in zip(target_indices, targets, strict=True):
            row = cohort['rows'][i]
            require(target['rowId'] == row['id'] and target['rowIndex'] == i
                    and all(target[k] == row[k] for k in ('clipId', 'targetId', 'targetPhone', 'wordIndex', 'phoneIndex'))
                    and type(target['canonicalIndex']) is int and 0 <= target['canonicalIndex'] < len(c['canonicalPhones'])
                    and c['canonicalPhones'][target['canonicalIndex']] == row['targetPhone']
                    and 0 <= row['targetId'] < 23, 'Full canonical target identity differs')
        clips.append({**{key: source[key] for key in fields}, 'clipIndex': clip_index,
            **{key: c[key] for key in ('canonicalPhones', 'mappedTokenIds', 'mappingAmbiguities')}, 'targets': targets})
    clips.sort(key=lambda clip: clip['id'])
    current = {c['id']: c for c in clips}
    old = {c['id']: c for c in old_plan['clips']}
    require(len(current) == len(clips) == recipe['expectedClips'] and len(indices) == recipe['expectedRows']
            and len(old) == recipe['reusedClips'] and len(old_plan['rowIndices']) == recipe['reusedRows']
            and set(old) <= set(current) and all(current[k] == v for k, v in old.items()), 'Original reuse population differs')
    reused, new = sorted(old), sorted(set(current) - set(old))
    new_rows = sorted(t['rowIndex'] for c in clips if c['id'] in set(new) for t in c['targets'])
    require(len(new) == recipe['newClips'] and len(new_rows) == recipe['newRows']
            and set(new_rows).isdisjoint(old_plan['rowIndices'])
            and sorted(new_rows + old_plan['rowIndices']) == indices, 'New/reused coverage differs')
    return indices, clips, reused, new


def original_evidence(recipe):
    require(recipe == read_json(RECIPE) and recipe['condition'] == 'noise20db' and recipe['snrDb'] == 20
            and recipe['seed'] == 20260926 and recipe['device'] == 'cpu' and recipe['threads'] == 2
            and recipe['partition'] == 'all-eligible-author-training-rows'
            and all(recipe[k] is False for k in FLAGS), 'Extension recipe or scope differs')
    # Capture before long validation; never replace caller pins with later file hashes.
    inputs = {'recipe': pin(RECIPE), 'protocol': pin(HERE / recipe['protocolPath'], recipe['protocolSha256']),
              **{'source/' + name: pin(HERE / name) for name in SOURCES}}
    report_path = HERE / recipe['originalFeaturesPath']
    report, report_pin = read_bound(report_path, recipe['originalFeaturesSha256'])
    old_plan, old_plan_pin = read_bound(report['planPath'], recipe['originalPlanSha256'])
    bound, clean, _ = original.validate_plan(old_plan, old_plan_pin)
    _, _, old_pins = consumer.feature_matrix(report_path, report_pin['sha256'], bound)
    require(report['recipeSha256'] == recipe['originalRecipeSha256']
            and report['cleanFeatureBindingSha256'] == recipe['cleanFeatureBindingSha256']
            and old_plan['recipe']['seed'] == recipe['seed']
            and old_plan['recipe']['ctcSessionOptions'] == recipe['ctcSessionOptions'], 'Original transform or clean binding differs')
    inputs.update({'original/' + k: v for k, v in old_pins.items()})
    inputs['originalFeatures'], inputs['originalPlan'] = report_pin, old_plan_pin
    inputs['cleanFeatureBinding'] = report['inputFiles']['cleanFeatureBinding']
    inputs['originalConsumerRecipe'] = pin(consumer.RECIPE)
    inputs.update(original.lexical_checkpoint_pins(read_json(original.extraction.RECIPE)))
    indices, clips, reused, new = full_metadata(bound['cohort'], bound['splits'], clean,
        read_json(Path(clean['manifestPath'])), recipe, old_plan)
    for clip in clips:
        inputs['sourceAudio/' + clip['id']] = pin(clip['audioPath'], clip['audioSha256'])
    old_index = read_json(report_path.parent / report['indexPath'])
    guard(inputs)
    return bound, clean, report, old_plan, old_index, indices, clips, reused, new, inputs


def prepare(output):
    require(not output.exists() and output.absolute().is_relative_to((HERE / 'outputs').absolute()), 'Choose a fresh ignored plan directory')
    recipe, recipe_pin = read_bound(RECIPE)
    _, _, report, old_plan, _, indices, clips, reused, new, inputs = original_evidence(recipe)
    require(inputs['recipe'] == recipe_pin, 'Recipe changed during preparation')
    plan = {'schemaVersion': 1, 'complete': True, 'recipe': recipe, 'recipeSha256': recipe_pin['sha256'],
        'inputFiles': inputs, 'rowIndices': indices, 'clips': clips, 'reusedClipIds': reused, 'newClipIds': new,
        'ctcCheckpoint': old_plan['ctcCheckpoint'], 'authorPartition': 'train', 'partition': recipe['partition'],
        'expectedRows': len(indices), 'expectedClips': len(clips), 'originalParity': report['originalParity'], **FLAGS}
    guard(inputs)
    output.mkdir(parents=True, mode=0o700)
    atomic_json(output / 'plan.json', plan)
    return {'planPath': str((output / 'plan.json').absolute()), 'planSha256': digest(output / 'plan.json'),
            'rows': len(indices), 'clips': len(clips), 'reusedClips': len(reused), 'newClips': len(new)}


def validate_plan(plan, plan_pin):
    require(plan['complete'] is True and plan['recipeSha256'] == digest(RECIPE)
            and plan['recipe'] == read_json(RECIPE) and all(plan[k] is False for k in FLAGS), 'Plan recipe or scope differs')
    guard({**plan['inputFiles'], 'plan': plan_pin})
    evidence = original_evidence(plan['recipe'])
    bound, clean, report, old_plan, old_index, indices, clips, reused, new, inputs = evidence
    require(plan['inputFiles'] == inputs and plan['rowIndices'] == indices and plan['clips'] == clips
            and plan['reusedClipIds'] == reused and plan['newClipIds'] == new
            and plan['expectedRows'] == len(indices) and plan['expectedClips'] == len(clips)
            and plan['originalParity'] == report['originalParity'] and plan['ctcCheckpoint'] == old_plan['ctcCheckpoint']
            and plan['authorPartition'] == 'train' and plan['partition'] == plan['recipe']['partition'], 'Prepared full-cohort metadata differs')
    return bound, clean, report, old_plan, old_index, {**inputs, 'plan': plan_pin}


def make_batch(plan, plan_pin, entries, inputs, directory, node):
    batch = {'schemaVersion': 1, 'sourcePlanSha256': plan_pin['sha256'], 'authorPartition': 'train',
        'partition': plan['partition'], 'phase': 'noise20db', 'inputFiles': dict(inputs), 'entries': entries,
        'ctcCheckpoint': plan['ctcCheckpoint'], 'sessionOptions': plan['recipe']['ctcSessionOptions']}
    for entry in entries:
        batch['inputFiles']['audio/' + entry['id']] = {'path': entry['audioPath'], 'sha256': entry['audioSha256']}
    batch_path = directory / 'noise20db-ctc-plan.json'
    atomic_json(batch_path, batch)
    batch_pin = pin(batch_path)
    subprocess.run([node, str(HERE / 'multiphone_consistency_extension_ctc.ts'), str(batch_path.absolute()),
        batch_pin['sha256'], str((directory / 'noise20db-ctc').absolute())], check=True,
        env={**os.environ, 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'})
    index_path = directory / 'noise20db-ctc/index.json'
    ctc, ctc_pin = read_bound(index_path)
    verify_ctc(ctc, plan, plan_pin['sha256'], entries, batch_pin['sha256'])
    pins = {'ctcBatch': batch_pin, 'ctcIndex': ctc_pin}
    for entry in ctc['entries'].values():
        pins['ctc/' + entry['id']] = pin(index_path.parent / entry['path'], entry['sha256'])
    guard(pins)
    return ctc, pins


def verify_ctc(ctc, plan, plan_sha, audio, batch_sha):
    require(ctc['complete'] is True and ctc['sourcePlanSha256'] == plan_sha and ctc['batchPlanSha256'] == batch_sha
            and ctc['phase'] == 'noise20db' and ctc['checkpoint'] == plan['ctcCheckpoint'] and ctc['fetchAttempts'] == 0
            and ctc['sessionOptions'] == plan['recipe']['ctcSessionOptions']
            and sorted(ctc['entries']) == sorted(e['id'] for e in audio) == plan['newClipIds'], 'Extension CTC scope differs')
    for e in audio:
        item = ctc['entries'][e['id']]
        require(all(item[k] == v for k, v in e.items()) and item['path'] == e['id'] + '.f32'
                and item['frames'] == original.local.convolution_frames(e['sampleCount'], read_json(original.local.RECIPE)),
                'Extension CTC waveform or geometry differs')


def origins_for(plan, plan_pin, old_report, new_ctc_pin):
    old_ctc = old_report['derivedFiles']['ctcIndex/noise20db']
    return {clip['id']: {'origin': 'original' if clip['id'] in set(plan['reusedClipIds']) else 'extension',
        'planPath': old_report['planPath'] if clip['id'] in set(plan['reusedClipIds']) else plan_pin['path'],
        'planSha256': old_report['planSha256'] if clip['id'] in set(plan['reusedClipIds']) else plan_pin['sha256'],
        'ctcIndexPath': old_ctc['path'] if clip['id'] in set(plan['reusedClipIds']) else new_ctc_pin['path'],
        'ctcIndexSha256': old_ctc['sha256'] if clip['id'] in set(plan['reusedClipIds']) else new_ctc_pin['sha256']}
        for clip in plan['clips']}


def audit_units(plan, index, target=None, scalars=None, rows=None):
    """Verify each actual origin, waveform, posterior, target identity and row join."""
    keys = {c['id'] for c in plan['clips']}
    require(all(set(index[k]) == keys for k in ('entries', 'noisyAudio', 'recordingMeasurements', 'originByClip')),
            'Mixed-origin clip coverage differs')
    positions = {i: n for n, i in enumerate(plan['rowIndices'])}
    output_rows = [None] * len(positions)
    matrices = None if target is not None else (np.empty((len(positions), 1024), np.float32), np.empty((len(positions), 13), np.float32))
    pins, ctcs = {}, {}
    for clip in plan['clips']:
        clip_id = clip['id']; origin = index['originByClip'][clip_id]
        ctc_path = origin['ctcIndexPath']
        ctc_pin = {'path': ctc_path, 'sha256': origin['ctcIndexSha256']}
        if ctc_path not in ctcs:
            ctcs[ctc_path], _ = read_bound(ctc_path, ctc_pin['sha256'])
        ctc = ctcs[ctc_path]['entries'][clip_id]
        entry, audio = index['entries'][clip_id], index['noisyAudio'][clip_id]
        require(ctc['audioPath'] == audio['audioPath'] and ctc['audioSha256'] == audio['audioSha256']
                and audio['sampleCount'] == clip['sampleCount'] and audio['id'] == audio['clipId'] == clip_id,
                'Mixed-origin waveform lineage differs')
        t, s, metadata = original.checked_unit(entry, clip, origin['planSha256'], ctc, audio)
        require(metadata['recording'] == index['recordingMeasurements'][clip_id], 'Recording metadata differs')
        offsets = [positions[r['rowIndex']] for r in metadata['rows']]
        require(all(output_rows[i] is None for i in offsets), 'Duplicate feature target row')
        for i, row in zip(offsets, metadata['rows'], strict=True): output_rows[i] = row
        if matrices is not None:
            matrices[0][offsets], matrices[1][offsets] = t, s
        else:
            require(np.array_equal(target[offsets], t) and np.array_equal(scalars[offsets], s)
                    and [rows[i] for i in offsets] == metadata['rows'], 'Full assembled matrix differs from its units')
        pins.update({'unit/' + clip_id: {'path': entry['path'], 'sha256': entry['sha256']},
            'unitMeta/' + clip_id: {'path': entry['entryPath'], 'sha256': entry['entrySha256']},
            'noisy/' + clip_id: {'path': audio['audioPath'], 'sha256': audio['audioSha256']},
            'posterior/' + clip_id: {'path': str((Path(ctc_path).parent / ctc['path']).absolute()), 'sha256': ctc['sha256']},
            'originPlan/' + clip_id: {'path': origin['planPath'], 'sha256': origin['planSha256']},
            'originCTC/' + clip_id: ctc_pin})
    require(all(r is not None for r in output_rows), 'Missing feature row')
    guard(pins)
    return output_rows, matrices, pins


def check_index(plan, plan_pin, index, old_report, old_index, new_ctc_pin):
    require(index['complete'] is True and index['planSha256'] == plan_pin['sha256']
            and index['rowIndices'] == plan['rowIndices'] and index['clipCount'] == plan['expectedClips']
            and index['originByClip'] == origins_for(plan, plan_pin, old_report, new_ctc_pin)
            and all(index[k] is False for k in FLAGS), 'Mixed-origin index or origin identity differs')
    for clip_id in plan['reusedClipIds']:
        require(all(index[k][clip_id] == old_index[k][clip_id] for k in
                    ('entries', 'noisyAudio', 'recordingMeasurements')), 'Reused artifact was relabeled or changed')


def assemble(plan, index, output):
    rows, (target, scalars), pins = audit_units(plan, index)
    descriptors = {}
    for name, values in (('target', target), ('scalars', scalars)):
        path = output / (name + '.npy')
        with path.open('xb') as stream:
            path.chmod(0o600); np.save(stream, values, allow_pickle=False)
        descriptors[name] = {'path': path.name, 'sha256': digest(path), 'dtype': 'float32', 'shape': list(values.shape)}
        pins['matrix/' + name] = pin(path, descriptors[name]['sha256'])
    audit_units(plan, index, np.load(output / 'target.npy', mmap_mode='r', allow_pickle=False),
                np.load(output / 'scalars.npy', mmap_mode='r', allow_pickle=False), rows)
    return rows, descriptors, pins


def validate_features(report_path, expected_sha256):
    report_path = Path(report_path)
    report, report_pin = read_bound(report_path, expected_sha256)
    plan, plan_pin = read_bound(report['planPath'], report['planSha256'])
    _, _, old_report, _, old_index, inputs = validate_plan(plan, plan_pin)
    require(report['complete'] is True and report['completeCoverage'] is True
            and report['failedRows'] == report['unmappableRows'] == [] and report['authorPartition'] == 'train'
            and report['partition'] == plan['partition'] and report['rowIndices'] == plan['rowIndices']
            and report['expectedRows'] == plan['expectedRows'] and report['expectedClips'] == plan['expectedClips']
            and report['condition'] == 'noise20db' and report['snrDb'] == 20
            and report['recipeSha256'] == plan['recipeSha256'] and report['inputFiles'] == inputs
            and report['cleanFeatureBindingSha256'] == report['featureSourceBindingSha256'] == plan['recipe']['cleanFeatureBindingSha256']
            and report['scalarFeatureNames'] == original.local.SCALAR_NAMES
            and report['originalParityComplete'] is True and report['originalParity'] == old_report['originalParity']
            and report['originalParityPin'] == old_report['derivedFiles']['parity']
            and report['reusedClips'] == len(plan['reusedClipIds']) and report['newClips'] == len(plan['newClipIds'])
            and all(report[k] is False for k in FLAGS), 'Full feature report scope differs')
    pins = {**inputs, **{'derived/' + k: v for k, v in report['derivedFiles'].items()}, 'features': report_pin}
    guard(pins)
    require(report['indexPath'] == 'index.json' and report['derivedFiles']['index'] ==
        {'path': str((report_path.parent / 'index.json').absolute()), 'sha256': report['indexSha256']}, 'Full index pin differs')
    index = read_json(report_path.parent / 'index.json')
    new_ctc_pin = report['derivedFiles']['ctcIndex']
    check_index(plan, plan_pin, index, old_report, old_index, new_ctc_pin)
    ctc = read_json(Path(new_ctc_pin['path']))
    verify_ctc(ctc, plan, plan_pin['sha256'], [index['noisyAudio'][i] for i in plan['newClipIds']], report['derivedFiles']['ctcBatch']['sha256'])
    arrays = []
    for key, name, width in (('targetFeatures', 'target', 1024), ('scalarFeatures', 'scalars', 13)):
        descriptor = report[key]; path = report_path.parent / (name + '.npy')
        require(descriptor['path'] == path.name and descriptor['dtype'] == 'float32'
                and descriptor['shape'] == [len(plan['rowIndices']), width], 'Full feature descriptor differs')
        pins['matrix/' + name] = pin(path, descriptor['sha256'])
        a = np.load(path, allow_pickle=False)
        require(a.dtype == np.float32 and a.shape == (len(plan['rowIndices']), width) and np.isfinite(a).all(), 'Invalid full feature matrix')
        arrays.append(a)
    require(len(report['rows']) == len(plan['rowIndices']), 'Full row metadata count differs')
    _, _, unit_pins = audit_units(plan, index, *arrays, report['rows'])
    # Retain captured unit pins as well as the report's claimed derived pins.
    pins.update({'checked/' + k: v for k, v in unit_pins.items()})
    guard(pins)
    return report, arrays[0], arrays[1], pins


def run(plan_path, plan_sha, node='node'):
    plan, plan_pin = read_bound(plan_path, plan_sha)
    _, _, old_report, _, old_index, inputs = validate_plan(plan, plan_pin)
    output = plan_path.parent / 'features'
    require(not output.exists(), 'Fresh extraction only; preserve incomplete runs')
    output.mkdir(mode=0o700); started = time.perf_counter()
    try:
        new_clips = [c for c in plan['clips'] if c['id'] in set(plan['newClipIds'])]
        noisy, measurements = copy.deepcopy(old_index['noisyAudio']), copy.deepcopy(old_index['recordingMeasurements'])
        derived = {}; (output / 'audio').mkdir(mode=0o700)
        for clip in new_clips:
            entry, measurement = original.write_noisy(clip, output / 'audio' / (clip['id'] + '.wav'), plan['recipe']['seed'])
            noisy[clip['id']], measurements[clip['id']] = entry, measurement
            derived['noisy/' + clip['id']] = {'path': entry['audioPath'], 'sha256': entry['audioSha256']}
        ctc, ctc_pins = make_batch(plan, plan_pin, [noisy[c['id']] for c in new_clips], {**inputs, **derived}, output, node)
        derived.update(ctc_pins)
        torch.set_num_threads(2)
        os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
        phonetic_recipe = read_json(original.extraction.RECIPE)
        encoder = original.extraction.PhoneticEncoder(original.phonetic_snapshot(phonetic_recipe), phonetic_recipe)
        entries = copy.deepcopy(old_index['entries'])
        for ordinal, clip in enumerate(new_clips, 1):
            audio = noisy[clip['id']]
            logp, _ = original.load_logp(ctc, output / 'noise20db-ctc', clip['id'])
            hidden = encoder(original.read_rating_pcm(Path(audio['audioPath']), audio['audioSha256']))
            rows, scalars, pooled, _ = original.capture.aligned_features(logp, hidden, clip, read_json(original.local.RECIPE))
            entries[clip['id']] = original.save_unit(output / 'clips' / clip['id'], clip, audio, measurements[clip['id']],
                rows, pooled, scalars, ctc['entries'][clip['id']], plan_sha)
            atomic_json(output / 'status.json', {'complete': False, 'newClips': ordinal, 'expectedNewClips': len(new_clips)})
            if ordinal % 50 == 0: print(f'Phonetic extension {ordinal}/{len(new_clips)}', flush=True)
        index = {'complete': True, 'planSha256': plan_sha, 'rowIndices': plan['rowIndices'], 'entries': entries,
            'noisyAudio': noisy, 'recordingMeasurements': measurements, 'clipCount': len(entries),
            'originByClip': origins_for(plan, plan_pin, old_report, derived['ctcIndex']), **FLAGS}
        check_index(plan, plan_pin, index, old_report, old_index, derived['ctcIndex'])
        rows, descriptors, unit_pins = assemble(plan, index, output); derived.update(unit_pins)
        atomic_json(output / 'index.json', index); derived['index'] = pin(output / 'index.json')
        atomic_json(output / 'status.json', {'complete': True, 'newClips': len(new_clips), 'reusedClips': len(plan['reusedClipIds']),
                                          'clips': len(entries), 'rows': len(rows)})
        derived['status'] = pin(output / 'status.json')
        report = {'schemaVersion': 1, 'complete': True, 'completeCoverage': True, 'failedRows': [], 'unmappableRows': [],
            'authorPartition': 'train', 'partition': plan['partition'], 'condition': 'noise20db', 'snrDb': 20,
            'planPath': plan_pin['path'], 'planSha256': plan_sha, 'recipeSha256': plan['recipeSha256'],
            'inputFiles': inputs, 'derivedFiles': derived,
            'featureSourceBindingSha256': plan['recipe']['cleanFeatureBindingSha256'],
            'cleanFeatureBindingSha256': plan['recipe']['cleanFeatureBindingSha256'],
            'targetFeatures': descriptors['target'], 'scalarFeatures': descriptors['scalars'],
            'scalarFeatureNames': original.local.SCALAR_NAMES, 'rowIndices': plan['rowIndices'], 'rows': rows,
            'expectedRows': len(rows), 'expectedClips': len(entries), 'reusedClips': len(plan['reusedClipIds']), 'newClips': len(new_clips),
            'indexPath': 'index.json', 'indexSha256': derived['index']['sha256'],
            'originalParityComplete': True, 'originalParity': old_report['originalParity'],
            'originalParityPin': old_report['derivedFiles']['parity'],
            'elapsedSeconds': time.perf_counter() - started, 'torch': str(torch.__version__), 'numpy': np.__version__, **FLAGS}
        guard({**inputs, **derived})
        atomic_json(output / 'features.json', report)
        return {'complete': True, 'featuresPath': str((output / 'features.json').absolute()),
                'featuresSha256': digest(output / 'features.json'), 'rows': len(rows), 'clips': len(entries), 'newClips': len(new_clips)}
    except Exception as error:
        atomic_json(output / 'failure.json', {'complete': False, 'planSha256': plan_sha,
            'error': f'{type(error).__name__}: {error}', 'elapsedSeconds': time.perf_counter() - started})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('run'); p.add_argument('--plan', type=Path, required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--node', default='node')
    p = commands.add_parser('inspect'); p.add_argument('--features', type=Path, required=True); p.add_argument('--features-sha256', required=True)
    args = parser.parse_args()
    if args.command == 'prepare': result = prepare(args.output)
    elif args.command == 'inspect':
        report, _, _, pins = validate_features(args.features, args.features_sha256)
        result = {'complete': True, 'rows': report['expectedRows'], 'clips': report['expectedClips'], 'verifiedPins': len(pins)}
    else:
        with (args.plan.parent / '.extraction.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = run(args.plan, args.plan_sha256, args.node)
    import json
    print(json.dumps(result, indent=2), flush=True)
