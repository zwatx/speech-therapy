"""Frozen phonetic vectors for every author-train consonant occurrence."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import numpy as np
import torch
import transformers

import multiphone_phonetic_features as old
from multiphone_sequence_preflight import binding, guard, read_bound, require, write_new

HERE = Path(__file__).resolve().parent
BASE = HERE/'outputs/multiphone-20260926'
NEW = HERE/'outputs/multiphone-20260927'
PROTOCOL = HERE/'../../docs/model/multiphone-position-phonetic-protocol.md'
SNAPSHOT = HERE/'outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'
PINS = {
    'baseline': (BASE/'phonetic-head-binding-v1.json', '360c829d179f9c66b66c900fdcf3db2cb0897fdc5724feb642100802d3da4985'),
    'data': (NEW/'position-data-v1/report.json', '49880e24288f09dc135cf6f02286320a057d84f24847e585a6eef5a70e43a0a8'),
    'geometry': (NEW/'position-scalars-v1/report.json', '5b2828cec062b50c575334c8f4182e1d7a712c869bf6ae90867417a9eb5698b9'),
}
FIELDS = ('id', 'rowIndex', 'clipId', 'targetId', 'targetPhone', 'canonicalIndex', 'wordIndex',
          'phoneIndex', 'legacyRowIndex', 'intervalFrames', 'estimatedPoolingWindowFrames')


def runtime():
    return dict(python=sys.version, numpy=np.__version__, torch=str(torch.__version__),
                transformers=transformers.__version__, device='cpu', threads=2, dtype='float32', attention='eager')


def checked_array(pin, shape):
    guard({'array': pin})
    value = np.load(pin['path'], allow_pickle=False)
    require(value.dtype == np.float32 and value.shape == shape and np.isfinite(value).all(), 'Invalid feature matrix')
    return value


def join_rows(rows, legacy):
    """Validate identity before associating new occurrence order with old vectors."""
    seen = set()
    for row in rows:
        li = row['legacyRowIndex']
        if li is None:
            continue
        require(li in legacy and li not in seen, 'Missing or duplicate legacy row')
        previous = legacy[li]
        require(all(row[k] == previous[k] for k in ('clipId', 'targetId', 'targetPhone', 'canonicalIndex',
                'wordIndex', 'phoneIndex', 'intervalFrames', 'estimatedPoolingWindowFrames')),
                'Legacy identity/window differs')
        seen.add(li)
    return seen


def inputs():
    pins = {k: binding(*v) for k, v in PINS.items()}
    base, data, geo = (read_bound(pins[k]) for k in ('baseline', 'data', 'geometry'))
    require(base['complete'] is data['complete'] is geo['complete'] is True, 'Complete reviewed inputs required')
    pins.update({'old/'+k: v for k, v in base['files'].items()})
    pins.update(data['outputs'])
    pins['scalars'] = geo['matrix']
    cohort = read_bound(pins['cohort'])
    require(cohort['authorPartition'] == geo['authorPartition'] == 'train' and len(cohort['rows']) == 28227
            and len(cohort['clips']) == 2500 and geo['legacyParity'] == 14837
            and geo['inputs']['cohort'] == pins['cohort'] and geo['inputs']['splits'] == pins['splits'], 'Data lineage differs')
    report = read_bound(pins['old/headInput/report'])
    config = read_bound(pins['old/headInput/config'])
    index = read_bound(pins['old/headInput/index'])
    recipe = read_bound(pins['old/recipe'])
    require(config['recipe'] == recipe and report['configSha256'] == pins['old/headInput/config']['sha256']
            and report['indexSha256'] == pins['old/headInput/index']['sha256'] and index['complete'] is True
            and all(config[k] == runtime()[k] for k in ('torch', 'numpy', 'transformers', 'device', 'threads', 'dtype')),
            'Original encoder runtime/config differs')
    checkpoint = old.checkpoint_files(SNAPSHOT, Path(pins['old/checkpoint/downloadRecord']['path']), recipe)
    require(all(checkpoint[k] == pins['old/'+k] for k in checkpoint), 'Checkpoint snapshot differs')
    legacy = {r['rowIndex']: r for r in report['rows']}
    old_by_clip = defaultdict(list)
    for r in report['rows']: old_by_clip[r['clipId']].append(r)
    require(len(legacy) == len(report['rows']) == 14837 and set(index['entries']) == set(old_by_clip), 'Legacy coverage differs')
    clips, seen, ordered = [], set(), []
    for source in sorted(cohort['clips'], key=lambda c: c['id']):
        cid = source['id']
        pins['geometry/'+cid] = geo['clipArtifacts'][cid]
        geometry = read_bound(pins['geometry/'+cid])
        rows = [{k: r[k] for k in FIELDS} for r in geometry['rows']]
        for row in rows:
            expected = cohort['rows'][row['rowIndex']]
            require(all(row[k] == expected[k] for k in ('id', 'clipId', 'targetId', 'targetPhone', 'canonicalIndex',
                    'wordIndex', 'phoneIndex', 'legacyRowIndex')), 'Position identity/order differs')
        joined = join_rows(rows, legacy)
        require(not seen.intersection(joined), 'Duplicate original row across clips')
        seen.update(joined); ordered.extend(rows)
        clip = {k: source[k] for k in ('id', 'audioPath', 'audioSha256', 'sampleCount')}
        clip.update(rows=rows, recompute=any(r['legacyRowIndex'] is None for r in rows),
                    frames=old.convolution_frames(source['sampleCount'], recipe))
        for row in rows:
            a, b = row['intervalFrames']; w = row['estimatedPoolingWindowFrames']
            require(0 <= a < b <= clip['frames'] and w == [max(0, a-2), min(clip['frames'], b+2)], 'Invalid window')
        pins['audio/'+cid] = binding(source['audioPath'], source['audioSha256'])
        if cid in index['entries']:
            entry = index['entries'][cid]
            directory = BASE/'phonetic-features-v1/clips'/cid
            pins['oldUnit/'+cid] = binding(directory/'vectors.npz', entry['sha256'])
            pins['oldEntry/'+cid] = binding(directory/'entry.json', entry['entrySha256'])
            expected = old.expected_entry(clip, old_by_clip[cid], report['configSha256'], clip['frames'])
            old.checked_unit(directory, expected, 1024, entry)
        clips.append(clip)
    require(seen == set(legacy) and len(ordered) == 28227 and
            sorted(r['rowIndex'] for r in ordered) == list(range(28227)), 'Incomplete occurrence coverage')
    require(sum(c['recompute'] for c in clips) == 2262 and len(clips) == 2500, 'Recompute partition differs')
    for name in ('multiphone_position_phonetic.py', 'test_multiphone_position_phonetic.py', 'multiphone_sequence_preflight.py'):
        pins['source/'+name] = binding(HERE/name)
    pins['protocol'] = binding(PROTOCOL)
    pins['runtime/python'] = binding(sys.executable)
    guard(pins)
    return clips, pins, recipe, geo['support']


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh ignored output required')
    clips, pins, recipe, support = inputs()
    output.mkdir(mode=0o700)
    return write_new(output/'plan.json', dict(declaredAt=datetime.now(timezone.utc).isoformat(), clips=clips,
        inputs=pins, recipe=recipe, runtime=runtime(), support=support,
        repeatClipId=next(c['id'] for c in clips if c['recompute']), modelInferencePerformed=False))


def load_plan(path, sha):
    pin = binding(path, sha)
    require(Path(pin['path']).is_relative_to(HERE/'outputs'), 'Plan outside ignored research outputs')
    plan = read_bound(pin)
    clips, pins, recipe, support = inputs()
    require(plan['clips'] == clips and plan['inputs'] == pins and plan['recipe'] == recipe
            and plan['runtime'] == runtime() and plan['support'] == support
            and plan['repeatClipId'] == next(c['id'] for c in clips if c['recompute'])
            and plan['modelInferencePerformed'] is False, 'Declaration differs')
    return plan, pin


def old_vectors(clip, plan, old_positions, old_target, old_global):
    selected = [(i, old_positions[r['legacyRowIndex']]) for i, r in enumerate(clip['rows']) if r['legacyRowIndex'] is not None]
    if not selected: return selected, None, None
    positions = [p for _, p in selected]
    global_vector = old_global[positions[0]]
    require(np.array_equal(old_global[positions], np.broadcast_to(global_vector, (len(positions), 1024))),
            'Legacy global repetition differs')
    return selected, old_target[positions], global_vector


def legacy_parity(target, global_vector, selected, original, original_global):
    if selected:
        require(np.array_equal(target[[i for i, _ in selected]], original)
                and np.array_equal(global_vector, original_global), 'Exact legacy encoder-vector parity failed')
    return len(selected)


def assemble_matrix(units, count, scalars):
    target = np.empty((count, 1024), np.float32)
    assigned = np.zeros(count, bool)
    for rows, values in units:
        indices = [r['rowIndex'] for r in rows]
        require(len(set(indices)) == len(indices) and all(type(i) is int and 0 <= i < count for i in indices)
                and not assigned[indices].any() and values.shape == (len(rows), 1024)
                and values.dtype == np.float32 and np.isfinite(values).all(), 'Invalid or duplicate unit rows')
        target[indices] = values; assigned[indices] = True
    require(assigned.all() and scalars.shape == (count, 13) and scalars.dtype == np.float32
            and np.isfinite(scalars).all(), 'Incomplete matrix or invalid scalars')
    return target, np.concatenate((target, scalars), axis=1)


def assemble(plan, pin, root, calculate):
    original = read_bound(plan['inputs']['old/headInput/report'])
    positions = {r['rowIndex']: i for i, r in enumerate(original['rows'])}
    old_target = checked_array(plan['inputs']['old/headInput/target'], (14837, 1024))
    old_global = checked_array(plan['inputs']['old/headInput/global'], (14837, 1024))
    scalars = checked_array(plan['inputs']['scalars'], (28227, 13))
    units, artifacts, encoder, parity = [], {}, None, 0
    if calculate: (root/'clips').mkdir(mode=0o700)
    for number, clip in enumerate(plan['clips'], 1):
        cid = clip['id']; directory = root/'clips'/cid
        expected = old.expected_entry(clip, clip['rows'], pin['sha256'], clip['frames'])
        selected, previous, previous_global = old_vectors(clip, plan, positions, old_target, old_global)
        if calculate:
            if clip['recompute']:
                if encoder is None: encoder = old.PhoneticEncoder(SNAPSHOT, plan['recipe'])
                samples = old.read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
                require(len(samples) == clip['sampleCount'], 'PCM sample count differs')
                target, global_vector = old.pooled_vectors(encoder(samples), clip['rows'], clip['frames'])
            else:
                require(len(selected) == len(clip['rows']), 'Cannot reuse newly added row')
                target, global_vector = previous, previous_global
            legacy_parity(target, global_vector, selected, previous, previous_global)
            old.write_unit(directory, expected, target, global_vector)
        target, global_vector = old.checked_unit(directory, expected, 1024)
        parity += legacy_parity(target, global_vector, selected, previous, previous_global)
        artifacts[cid] = dict(entry=binding(directory/'entry.json'), vectors=binding(directory/'vectors.npz'), recomputed=clip['recompute'])
        units.append((clip['rows'], target))
        if number % 100 == 0: print(json.dumps(dict(clips=number, legacyParity=parity)), flush=True)
    repeated = next(c for c in plan['clips'] if c['id'] == plan['repeatClipId'])
    expected = old.expected_entry(repeated, repeated['rows'], pin['sha256'], repeated['frames'])
    if calculate:
        samples = old.read_rating_pcm(Path(repeated['audioPath']), repeated['audioSha256'])
        target, global_vector = old.pooled_vectors(encoder(samples), repeated['rows'], repeated['frames'])
        old.write_unit(root/'repeat', expected, target, global_vector)
    repeat = old.checked_unit(root/'repeat', expected, 1024)
    first = old.checked_unit(root/'clips'/repeated['id'], expected, 1024)
    require(all(np.array_equal(a, b) for a, b in zip(repeat, first, strict=True)), 'Independent repeat differs')
    targets, combined = assemble_matrix(units, 28227, scalars)
    matrices = {}
    for name, values in (('target', targets), ('combined', combined)):
        path = root/(name+'.npy')
        if calculate: old.atomic_array(path, values)
        matrices[name] = binding(path)
        require(np.array_equal(checked_array(matrices[name], values.shape), values), 'Saved assembled matrix differs')
        matrices[name].update(shape=list(values.shape), dtype='float32')
    guard(plan['inputs'])
    return dict(complete=True, plan=pin, inputs=plan['inputs'], runtime=runtime(), matrices=matrices,
        clipArtifacts=artifacts, repeat=dict(clipId=repeated['id'], entry=binding(root/'repeat/entry.json'),
            vectors=binding(root/'repeat/vectors.npz'), exact=True), positions=28227, clips=2500,
        recomputedClips=2262, reusedClips=238, encoderPasses=2263, legacyParity=parity,
        rowIds=[r['id'] for r in sorted((r for c in plan['clips'] for r in c['rows']), key=lambda r: r['rowIndex'])],
        support=plan['support'], authorPartition='train', **old.FALSE_FLAGS, trainingPerformed=False)


def execute(path, sha, calculate):
    torch.set_num_threads(2)
    os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
    plan, pin = load_plan(path, sha); root = Path(pin['path']).parent
    if calculate:
        # Exclusive marker rejects completed, concurrent and failed invocations.
        write_new(root/'started.json', dict(plan=pin, pid=os.getpid()))
    try:
        report = assemble(plan, pin, root, calculate)
        if calculate: return write_new(root/'report.json', report)
        require(read_bound(binding(root/'report.json')) == report, 'Complete export report differs')
        return dict(verified=True, report=binding(root/'report.json'))
    except Exception as error:
        if calculate: write_new(root/'failure.json', dict(errorType=type(error).__name__, message=str(error), plan=pin))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'verify'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        require(args.output is not None, 'Output required'); result = declare(args.output)
    else:
        require(args.plan is not None and args.plan_sha256, 'Pinned plan required')
        result = execute(args.plan, args.plan_sha256, args.command == 'run')
    print(json.dumps(result), flush=True)
