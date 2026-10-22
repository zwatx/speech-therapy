"""Label-free fixed temporal pooling; cached CTC intervals are estimates, not phone boundaries."""
from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import numpy as np

from middle_layer import extract as base
from multiphone_phonetic_features import PhoneticEncoder, atomic_json, digest, file_binding, guard, read_json, require
from speechocean_r_probe import read_rating_pcm

RECIPE = {'name': 'final-temporal-pre-interval-post-v1', 'contextFrames': 2,
          'emptyContext': 'interval-mean-with-zero-count', 'accumulation': 'float64',
          'persisted': 'float32', 'reconstructionFloat64Atol': 1e-10,
          'cachedFinalReuse': 'array-equal-all-rows', 'device': 'cpu'}
NAMES = ('temporal', 'final', 'counts')


def sources():
    return base.sources() | {name: file_binding(base.HERE / name) for name in
        ('temporal_pooling/__init__.py', 'temporal_pooling/extract.py', 'temporal_pooling/test_extract.py')} | {
        'temporalProtocol': file_binding(base.ROOT / 'docs/model/temporal-pooling-protocol.md')}


def windows(row, frames):
    interval, padded = row['intervalFrames'], row['estimatedPoolingWindowFrames']
    require(len(interval) == len(padded) == 2 and all(type(v) is int for v in interval + padded), 'Invalid interval types')
    s, e = interval
    require(0 <= s < e <= frames and padded == [max(0, s - 2), min(frames, e + 2)], 'Invalid cached interval/padded window')
    return ((padded[0], s), (s, e), (e, padded[1]))


def pool(frames, rows, expected_frames):
    require(frames.dtype == np.float32 and frames.shape == (expected_frames, 1024)
            and 0 < expected_frames <= 1500 and np.isfinite(frames).all() and bool(rows), 'Invalid final hidden grid')
    temporal, final, counts = [], [], []
    residual64 = residual32 = 0.0
    for row in rows:
        bins = windows(row, expected_frames)
        count = np.array([b-a for a, b in bins], np.int64)
        interval = frames[bins[1][0]:bins[1][1]].mean(0, dtype=np.float64)
        means = np.stack([frames[a:b].mean(0, dtype=np.float64) if a < b else interval for a, b in bins])
        padded = frames[bins[0][0]:bins[2][1]].mean(0, dtype=np.float64)
        reconstruction = (means * count[:, None]).sum(0) / count.sum()
        residual64 = max(residual64, float(np.abs(reconstruction-padded).max()))
        require(residual64 <= RECIPE['reconstructionFloat64Atol'], 'Float64 reconstruction failed')
        persisted, control = means.astype(np.float32), padded.astype(np.float32)
        residual32 = max(residual32, float(np.abs((persisted.astype(np.float64)*count[:, None]).sum(0)/count.sum()-control).max()))
        temporal.append(persisted.reshape(3072)); final.append(control); counts.append(count)
    return dict(temporal=np.stack(temporal), final=np.stack(final), counts=np.stack(counts)), {
        'float64MaxAbs': residual64, 'persistedFloat32MaxAbs': residual32}


def exact_parity(fresh, reference):
    residual = float(np.max(np.abs(fresh.astype(np.float64)-reference.astype(np.float64)))) if fresh.shape == reference.shape and fresh.size else None
    require(fresh.shape == reference.shape and fresh.dtype == reference.dtype == np.float32
            and np.isfinite(fresh).all() and np.array_equal(fresh, reference),
            f'Fresh padded mean differs from cached final (maxAbs={residual}): reuse forbidden; separately declare fresh-control route')


def declare(out):
    # Existing metadata-only export already pins cohort, model, scalar cache and
    # original train-only audio lineage. No frozen source/artifact is modified.
    base.declare(out)
    plan = read_json(out / 'plan.json')
    manifest = read_json(out / 'manifest.json')
    original = read_json(base.PINS['positions'][0])
    intervals = {row['rowIndex']: row for clip in original['clips'] for row in clip['rows']}
    for clip in manifest['clips']:
        for row in clip['rows']:
            source = intervals[row['rowIndex']]
            require(all(source[k] == row[k] for k in ('id', 'clipId', 'targetId', 'estimatedPoolingWindowFrames')), 'Interval identity differs')
            row['intervalFrames'] = source['intervalFrames']
            windows(row, clip['frames'])
    atomic_json(out / 'manifest.json', manifest)
    plan.update(recipe=RECIPE, sources=sources())
    plan['artifacts']['manifest'] = file_binding(out / 'manifest.json')
    atomic_json(out / 'plan.json', plan)
    return file_binding(out / 'plan.json')


def checked_plan(path, sha):
    require(digest(path) == sha, 'Plan SHA-256 mismatch')
    plan = read_json(path)
    require(plan['recipe'] == RECIPE and plan['runtime'] == base.RUNTIME
            and plan['support'] == {'positions': 9891, 'clips': 1040, 'children': 52}, 'Recipe differs')
    require(plan['sources'] == sources(), 'Current extractor sources differ from declaration')
    for key in ('inputs', 'sources', 'model', 'artifacts'): guard(plan[key])
    return plan


def extract_clip(encoder, clip):
    samples = read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
    require(samples.numel() == clip['sampleCount'], 'Audio sample count changed')
    return pool(encoder(samples), clip['rows'], clip['frames'])


def same(a, b):
    return all(np.array_equal(a[k], b[k]) for k in NAMES)


def run(path, sha, review, out):
    plan = checked_plan(path, sha)
    base.checked_review(review, sha)
    require(not out.exists(), 'Extraction output reuse forbidden')
    env = base.environment()
    manifest = read_json(Path(plan['artifacts']['manifest']['path']))
    reference = base.array(plan['artifacts']['reference']['path'], (9891, 1024), np.float32)
    out.mkdir(parents=True)
    started = time.monotonic()
    records, probes = [], {}
    try:
        with tempfile.TemporaryDirectory(prefix='temporal-checkpoint-') as directory:
            for name, binding in plan['model'].items(): (Path(directory)/name).symlink_to(binding['path'])
            encoder = PhoneticEncoder(Path(directory), {})
            require(len(encoder.model.wav2vec2.encoder.layers) == 24 and not encoder.model.training
                    and all(not p.requires_grad for p in encoder.model.parameters()), 'Frozen 24-layer encoder required')
            probe_ids = list(dict.fromkeys([plan['firstClipId'], plan['longestClipId']]))
            for clip in manifest['clips']:
                if clip['id'] in probe_ids:
                    values, _ = extract_clip(encoder, clip)
                    exact_parity(values['final'], reference[[r['outputIndex'] for r in clip['rows']]])
                    probes[clip['id']] = values
            matrices = {k: np.empty((9891, 3 if k == 'counts' else 3072 if k == 'temporal' else 1024),
                                   np.int64 if k == 'counts' else np.float32) for k in NAMES}
            for clip in manifest['clips']:
                before = time.monotonic()
                values, residuals = extract_clip(encoder, clip)
                positions = [r['outputIndex'] for r in clip['rows']]
                exact_parity(values['final'], reference[positions])
                if clip['id'] in probes: require(same(values, probes[clip['id']]), 'Preflight replay differs')
                for k in NAMES: matrices[k][positions] = values[k]
                unit = out / (clip['id'] + '.npz')
                np.savez_compressed(unit, **values)
                records.append({'clipId': clip['id'], 'artifact': file_binding(unit), 'residuals': residuals,
                                'seconds': time.monotonic()-before})
                atomic_json(out/'progress.json', {'planSha256': sha, 'completed': len(records), 'records': records})
                if len(records) % 50 == 0: print(f'Completed {len(records)}/1040 clips', flush=True)
            repeats = {}
            for clip in manifest['clips']:
                if clip['id'] in probes:
                    values, _ = extract_clip(encoder, clip)
                    require(same(values, probes[clip['id']]), 'End first/longest replay differs')
                    unit = out / (clip['id'] + '-repeat.npz')
                    np.savez_compressed(unit, **values)
                    repeats[clip['id']] = file_binding(unit)
        checked_plan(path, sha)
        for k in NAMES: np.save(out / (k+'.npy'), matrices[k])
        report = {'complete': True, 'plan': file_binding(path), 'review': file_binding(review), 'environment': env,
                  'matrices': {k: file_binding(out/(k+'.npy')) for k in NAMES}, 'clipRecords': records, 'repeats': repeats,
                  'scalars': plan['artifacts']['scalars'], 'rowIndices': plan['artifacts']['rowIndices'],
                  'cachedFinalExactAllRows': True, 'encoderUpdated': False, 'labelsUsedForExtraction': False,
                  'elapsedSeconds': time.monotonic()-started}
        atomic_json(out/'report.json', report)
        return file_binding(out/'report.json')
    except Exception as error:
        atomic_json(out/'failure.json', {'planSha256': sha, 'error': str(error), 'completedClips': len(records),
                    'elapsedSeconds': time.monotonic()-started})
        raise


def verify(path, sha):
    require(digest(path) == sha, 'Report SHA-256 mismatch')
    report = read_json(path)
    plan = checked_plan(Path(report['plan']['path']), report['plan']['sha256'])
    guard({'review': report['review']}); base.checked_review(Path(report['review']['path']), report['plan']['sha256'])
    require(report['complete'] is True and report['cachedFinalExactAllRows'] is True and report['encoderUpdated'] is False
            and report['labelsUsedForExtraction'] is False, 'Incomplete/frozen extraction flags differ')
    require(all(report['environment'].get(k) == base.RUNTIME[k] for k in ('torch', 'numpy', 'transformers', 'threads', 'deterministic')), 'Runtime differs')
    require(report['scalars'] == plan['artifacts']['scalars'] and report['rowIndices'] == plan['artifacts']['rowIndices'], 'Scalar/order binding differs')
    guard(report['matrices']); require(set(report['matrices']) == set(NAMES), 'Matrix set differs')
    matrices = {k: base.array(report['matrices'][k]['path'], (9891, 3 if k == 'counts' else 3072 if k == 'temporal' else 1024),
                             np.int64 if k == 'counts' else np.float32) for k in NAMES}
    exact_parity(matrices['final'], base.array(plan['artifacts']['reference']['path'], (9891, 1024), np.float32))
    base.array(report['scalars']['path'], (9891, 13), np.float32)
    manifest = read_json(Path(plan['artifacts']['manifest']['path']))
    indices = base.array(report['rowIndices']['path'], (9891,), np.int64)
    require(indices.tolist() == manifest['rowIndices'] and np.all(indices[1:] > indices[:-1]), 'Row order differs')
    require(len(report['clipRecords']) == len(manifest['clips']) == 1040, 'Coverage differs')
    covered = []
    for clip, record in zip(manifest['clips'], report['clipRecords'], strict=True):
        require(record['clipId'] == clip['id'], 'Clip identity differs')
        positions = [r['outputIndex'] for r in clip['rows']]; covered.extend(positions)
        guard({'unit': record['artifact']})
        with np.load(record['artifact']['path'], allow_pickle=False) as unit:
            require(set(unit.files) == set(NAMES) and same(unit, {k: matrices[k][positions] for k in NAMES}), 'Per-clip matrix differs')
        count = np.array([[b-a for a,b in windows(r, clip['frames'])] for r in clip['rows']], np.int64)
        require(np.array_equal(count, matrices['counts'][positions]), 'Bin counts differ')
        bins = matrices['temporal'][positions].reshape(-1, 3, 1024)
        for i, c in enumerate(count):
            for j in (0, 2):
                if c[j] == 0: require(np.array_equal(bins[i,j], bins[i,1]), 'Empty context fallback differs')
        residual = float(np.abs((bins.astype(np.float64)*count[:,:,None]).sum(1)/count.sum(1)[:,None]-matrices['final'][positions]).max())
        require(residual == record['residuals']['persistedFloat32MaxAbs'] and
                0 <= record['residuals']['float64MaxAbs'] <= RECIPE['reconstructionFloat64Atol'], 'Reconstruction evidence differs')
    require(sorted(covered) == list(range(9891)), 'Output row coverage differs')
    require(set(report['repeats']) == {plan['firstClipId'], plan['longestClipId']}, 'Replay coverage differs')
    guard(report['repeats'])
    for clip in manifest['clips']:
        if clip['id'] in report['repeats']:
            positions = [r['outputIndex'] for r in clip['rows']]
            with np.load(report['repeats'][clip['id']]['path'], allow_pickle=False) as unit:
                require(set(unit.files) == set(NAMES) and same(unit, {k: matrices[k][positions] for k in NAMES}), 'Replay differs')
    return {'verified': True, 'report': file_binding(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    d = sub.add_parser('declare'); d.add_argument('--out', required=True, type=Path)
    r = sub.add_parser('run'); r.add_argument('--plan', required=True, type=Path); r.add_argument('--sha256', required=True)
    r.add_argument('--review', required=True, type=Path); r.add_argument('--out', required=True, type=Path)
    v = sub.add_parser('verify'); v.add_argument('--report', required=True, type=Path); v.add_argument('--sha256', required=True)
    a = parser.parse_args()
    if a.command == 'declare': result = declare(a.out.resolve())
    elif a.command == 'run': result = run(a.plan.resolve(), a.sha256, a.review.resolve(), a.out.resolve())
    else: result = verify(a.report.resolve(), a.sha256)
    print(result)


if __name__ == '__main__': main()
