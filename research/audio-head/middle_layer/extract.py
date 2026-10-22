"""Declare, run, and verify the single preregistered CPU extraction.

Declaration reads cohort metadata to export a rating-free manifest. The runner
only reads that manifest, cached reference vectors, and pinned audio/model files.
"""
from __future__ import annotations

import argparse
import platform
import tempfile
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from multiphone_phonetic_features import (PhoneticEncoder, atomic_json, file_binding,
    guard, pooled_vectors, read_json, require, digest)
from speechocean_r_probe import read_rating_pcm

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
BASE = HERE / 'outputs/multiphone-20260927'
PINS = {'expanded': (BASE / 'lexical-expanded-heads-v1/plan.json', '8acf9c21ac69ef8c1aec9518ab4a8a75b27049322d6d8fe7733a5373fb97154c'),
        'positions': (BASE / 'position-phonetic-v1/plan.json', 'b3f1884a54b1fa25777eb9578155b9923eed9ce61ff1762e05301f6211c7f29c'),
        'referenceReport': (BASE / 'position-phonetic-v1/report.json', '80a0dd901f026deebd74ea9fb66d234f14e80ca44d03ab8c0816e0d8494341be')}
SOURCE_NAMES = ('middle_layer/__init__.py', 'middle_layer/extract.py', 'middle_layer/test_extract.py',
                'multiphone_phonetic_features.py', 'multiphone_cache.py', 'multiphone_local_features.py',
                'alignment_pilot.py', 'encoders.py', 'speechocean_audit.py', 'speechocean_r_probe.py')
RUNTIME = {'torch': '2.8.0', 'transformers': '4.57.6', 'numpy': '2.2.6', 'threads': 2,
           'device': 'cpu', 'deterministic': True}


def sources():
    # Resolve the modules actually imported by this environment, not a guessed
    # installation path or version string. Importing them performs no inference.
    from transformers.models.wav2vec2 import modeling_wav2vec2, feature_extraction_wav2vec2
    evidence = ROOT / 'work/model-quality-goal-20260927'
    bindings = {name: file_binding(HERE / name) for name in SOURCE_NAMES} | {
        'protocol': file_binding(ROOT / 'docs/model/middle-layer-protocol.md'),
        'implementation/modeling': file_binding(Path(modeling_wav2vec2.__file__)),
        'implementation/preprocessing': file_binding(Path(feature_extraction_wav2vec2.__file__)),
        'probe/source': file_binding(evidence / 'encoder-layer-probe.py'),
        'probe/result': file_binding(evidence / 'encoder-layer-probe-result.json')}
    probe = read_json(Path(bindings['probe/result']['path']))
    require(bindings['implementation/modeling']['sha256'] == probe['modelingSourceSha256']
            == '1c19d14f99c623c71aa8a058235978a06a8af4defb5e1f54321f7a6b7984e572'
            and bindings['probe/source']['sha256'] == probe['sourceSha256'], 'Probe implementation/source differs')
    require(probe['complete'] is True and probe['syntheticOnly'] is True and probe['actualAudioRead'] is False
            and probe['hiddenStateCount'] == 25 and probe['shape'] == [1, 49, 1024]
            and probe['layer12EqualsTwelfthBlockOutput'] is True and probe['layer24EqualsLastHiddenState'] is True,
            'Synthetic layer semantics evidence differs')
    return bindings


def array(path, shape, dtype):
    value = np.load(path, allow_pickle=False)
    require(value.shape == shape and value.dtype == dtype and np.isfinite(value).all(), 'Invalid array: ' + str(path))
    return value


def join_rows(cohort, clips, row_ids):
    """Identity-checked join; output order is original cached global row order."""
    require(len(row_ids) == len(set(row_ids)) == len(cohort), 'Duplicate cached identities')
    candidates = {}
    for clip in clips:
        for row in clip['rows']:
            index = row['rowIndex']
            require(type(index) is int and 0 <= index < len(cohort) and index not in candidates,
                    'Duplicate or invalid global row index')
            source = cohort[index]
            require(row['id'] == row_ids[index] == source['id'] and row['clipId'] == clip['id'] == source['clipId']
                    and row['targetId'] == source['targetId'], 'Row identity/order mismatch')
            if source['ageBand'] == 'child' and 6 <= source['age'] <= 12:
                require(6 <= source['age'] <= 12 and source['trainingEligible'] is True, 'Child scope mismatch')
                candidates[index] = {k: row[k] for k in ('rowIndex', 'id', 'clipId', 'targetId', 'estimatedPoolingWindowFrames')}
            else:
                candidates[index] = None
    require(set(candidates) == set(range(len(cohort))), 'Incomplete global identity coverage')
    return [candidates[i] for i in sorted(candidates) if candidates[i] is not None]


def declare(out):
    require(not out.exists(), 'Declaration output already exists')
    inputs = {name: {'path': str(path), 'sha256': sha} for name, (path, sha) in PINS.items()}
    guard(inputs)
    expanded, positions, report = (read_json(PINS[k][0]) for k in ('expanded', 'positions', 'referenceReport'))
    require(report['plan'] == inputs['positions'], 'Reference report/plan link differs')
    require(positions['recipe']['modelId'] == 'facebook/wav2vec2-lv-60-espeak-cv-ft'
            and positions['recipe']['revision'] == 'ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4', 'Pinned encoder identity differs')
    inputs['cohort'] = expanded['inputs']['cohort']
    inputs['combined'] = {k: report['matrices']['combined'][k] for k in ('path', 'sha256')}
    guard(inputs)
    cohort = read_json(Path(inputs['cohort']['path']))
    require(report['complete'] is True and report['positions'] == 28227, 'Incomplete reference extraction')
    rows = join_rows(cohort['rows'], positions['clips'], report['rowIds'])
    indices = np.array([r['rowIndex'] for r in rows], dtype=np.int64)
    require(len(rows) == 9891, 'Expected 9891 child positions')
    by_clip = {}
    for i, row in enumerate(rows):
        by_clip.setdefault(row['clipId'], []).append(dict(row, outputIndex=i))
    clips = [{**{k: c[k] for k in ('id', 'audioPath', 'audioSha256', 'sampleCount', 'frames')},
              'rows': by_clip[c['id']]} for c in positions['clips'] if c['id'] in by_clip]
    require(len({c['id'] for c in clips}) == len(clips), 'Duplicate clip identities')
    speakers = {cohort['rows'][i]['speakerId'] for i in indices}
    require(len(clips) == len(by_clip) == 1040 and len(speakers) == 52, 'Expected 1040 clips / 52 children')
    model_record = ROOT / 'work/model-quality-goal-20260927/encoder-file-bindings.json'
    inputs['modelRecord'] = file_binding(model_record)
    model = read_json(model_record)
    require(set(model) == {'config.json', 'preprocessor_config.json', 'pytorch_model.bin', 'vocab.json'}, 'Model file set differs')
    require({k: v['sha256'] for k, v in model.items()} == positions['recipe']['artifactSha256'], 'Original checkpoint hash bindings differ')
    guard(model)
    probe = read_json(ROOT / 'work/model-quality-goal-20260927/encoder-layer-probe-result.json')
    require(probe['modelFiles'] == model, 'Probe checkpoint bindings differ')
    require(len({cohort['rows'][i]['targetId'] for i in indices}) == 23, 'Expected all 23 consonants')
    combined = array(Path(inputs['combined']['path']), (28227, 1037), np.float32)
    out.mkdir(parents=True)
    np.save(out / 'reference.npy', combined[indices, :1024])
    np.save(out / 'scalars.npy', combined[indices, 1024:])
    np.save(out / 'row-indices.npy', indices)
    manifest = {'clips': clips, 'rowIds': [r['id'] for r in rows], 'rowIndices': indices.tolist()}
    atomic_json(out / 'manifest.json', manifest)
    artifacts = {name: file_binding(out / filename) for name, filename in
                 [('manifest', 'manifest.json'), ('reference', 'reference.npy'), ('scalars', 'scalars.npy'), ('rowIndices', 'row-indices.npy')]}
    plan = {'recipe': 'normalized-middle-layer-12-v1', 'sources': sources(), 'inputs': inputs,
            'model': model, 'artifacts': artifacts, 'runtime': RUNTIME,
            'support': {'positions': 9891, 'clips': 1040, 'children': 52},
            'firstClipId': clips[0]['id'], 'longestClipId': max(clips, key=lambda c: c['sampleCount'])['id'],
            'encoderInferencePerformed': False, 'labelsUsedForExtraction': False}
    guard(inputs); guard(model)
    atomic_json(out / 'plan.json', plan)
    return file_binding(out / 'plan.json')


def checked_plan(path, sha):
    require(digest(path) == sha, 'Plan SHA-256 mismatch')
    plan = read_json(path)
    require(plan['recipe'] == 'normalized-middle-layer-12-v1' and plan['runtime'] == RUNTIME
            and plan['support'] == {'positions': 9891, 'clips': 1040, 'children': 52}, 'Recipe differs')
    require(plan['sources'] == sources(), 'Current extractor sources differ from declaration')
    for key in ('inputs', 'sources', 'model', 'artifacts'):
        guard(plan[key])
    return plan


def checked_review(path, sha):
    review = read_json(path)
    require(review.get('planSha256') == sha and review.get('verdict') == 'clear'
            and review.get('blockingFindings') == [] and review.get('independent') is True
            and bool(review.get('reviewer')), 'A matching clear independent review is required')


def normalize_middle(frames, eps):
    require(frames.dtype == torch.float32 and frames.ndim == 3 and frames.shape[0] == 1
            and frames.shape[2] == 1024 and torch.isfinite(frames).all().item(), 'Invalid middle hidden state')
    return F.layer_norm(frames, (1024,), eps=eps)


class Encoder(PhoneticEncoder):
    @torch.inference_mode()
    def __call__(self, samples):
        captured = []
        hook = self.model.wav2vec2.encoder.layers[11].register_forward_hook(lambda module, args, output: captured.append(output[0]))
        try:
            inputs = self.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt')
            output = self.model.wav2vec2(**inputs, output_hidden_states=True)
        finally:
            hook.remove()
        states = output.hidden_states
        require(len(states) == 25 and len(captured) == 1 and torch.equal(states[12], captured[0])
                and torch.equal(states[24], output.last_hidden_state), 'Hidden-state index semantics changed')
        require(not self.model.training and all(not p.requires_grad for p in self.model.parameters()), 'Encoder is not frozen')
        return normalize_middle(states[12], self.model.config.layer_norm_eps)[0].numpy(), states[24][0].numpy()


def extract_clip(encoder, clip):
    samples = read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
    require(samples.numel() == clip['sampleCount'], 'Audio sample count changed')
    middle, final = encoder(samples)
    return tuple(pooled_vectors(x, clip['rows'], clip['frames'])[0] for x in (middle, final))


def parity(fresh, reference):
    difference = float(np.max(np.abs(fresh.astype(np.float64) - reference.astype(np.float64))))
    require(np.isfinite(difference) and difference <= 1e-5, 'Fresh-final cached parity failed')
    return difference


def environment():
    import transformers
    observed = {'torch': torch.__version__.split('+')[0], 'numpy': np.__version__, 'transformers': transformers.__version__}
    require(all(observed[k] == RUNTIME[k] for k in observed), 'Local runtime versions differ')
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    return observed | {'python': platform.python_version(), 'platform': platform.platform(), 'threads': torch.get_num_threads(), 'deterministic': torch.are_deterministic_algorithms_enabled()}


def run(path, sha, review, out):
    plan = checked_plan(path, sha)
    checked_review(review, sha)
    require(not out.exists(), 'Extraction output reuse is forbidden')
    env = environment()
    manifest = read_json(Path(plan['artifacts']['manifest']['path']))
    clips = manifest['clips']
    reference = array(plan['artifacts']['reference']['path'], (9891, 1024), np.float32)
    out.mkdir(parents=True)
    started = time.monotonic()
    records, timings, parity_results = [], [], {}
    try:
        with tempfile.TemporaryDirectory(prefix='middle-checkpoint-') as temporary:
            for name, binding in plan['model'].items():
                (Path(temporary) / name).symlink_to(binding['path'])
            encoder = Encoder(Path(temporary), {})
            preflight = {}
            for clip_id in dict.fromkeys([plan['firstClipId'], plan['longestClipId']]):
                clip = next(c for c in clips if c['id'] == clip_id)
                values = extract_clip(encoder, clip)
                positions = [r['outputIndex'] for r in clip['rows']]
                parity_results[clip_id] = parity(values[1], reference[positions])
                preflight[clip_id] = values
            middle = np.empty((9891, 1024), np.float32)
            final = np.empty_like(middle)
            for clip in clips:
                before = time.monotonic()
                values = extract_clip(encoder, clip)
                timings.append(time.monotonic() - before)
                positions = [r['outputIndex'] for r in clip['rows']]
                if clip['id'] in preflight:
                    require(all(np.array_equal(a, b) for a, b in zip(values, preflight[clip['id']], strict=True)), 'Preflight/ordinary extraction differs')
                middle[positions], final[positions] = values
                unit = out / (clip['id'] + '.npz')
                np.savez_compressed(unit, middle=values[0], final=values[1], rowIndices=np.array([r['rowIndex'] for r in clip['rows']], np.int64))
                record = {'clip': clip, 'artifact': file_binding(unit), 'seconds': timings[-1]}
                atomic_json(out / (clip['id'] + '.json'), record)
                records.append(file_binding(out / (clip['id'] + '.json')))
                atomic_json(out / 'progress.json', {'planSha256': sha, 'completed': len(records), 'records': records, 'seconds': timings})
                if len(timings) % 50 == 0:
                    print(f'Completed {len(timings)}/{len(clips)} clips', flush=True)
                if len(timings) == 20:
                    projected = sum(timings) / 20 * len(clips)
                    atomic_json(out / 'timing-gate.json', {'projectedSeconds': projected, 'limitSeconds': 2700, 'passed': projected <= 2700})
                    require(projected <= 2700, 'Local projection exceeds 45 minutes; preserve output for separately reviewed fallback')
            repeat = extract_clip(encoder, clips[0])
            require(all(np.array_equal(a, b) for a, b in zip(repeat, preflight[plan['firstClipId']], strict=True)), 'First-clip repeat differs')
            first_positions = [r['outputIndex'] for r in clips[0]['rows']]
            require(np.array_equal(middle[first_positions], repeat[0]) and np.array_equal(final[first_positions], repeat[1]), 'Ordinary first-clip repeat differs')
        np.savez_compressed(out / 'repeat.npz', middle=repeat[0], final=repeat[1])
        checked_plan(path, sha)
        np.save(out / 'middle.npy', middle); np.save(out / 'final.npy', final)
        report = {'complete': True, 'plan': file_binding(path), 'review': file_binding(review), 'environment': env,
                  'matrices': {k: file_binding(out / (k + '.npy')) for k in ('middle', 'final')},
                  'rowIndices': plan['artifacts']['rowIndices'], 'scalars': plan['artifacts']['scalars'],
                  'clipRecords': records, 'parity': parity_results, 'repeatExact': True,
                  'timingGate': file_binding(out / 'timing-gate.json'), 'repeatArtifact': file_binding(out / 'repeat.npz'),
                  'modelRehashedAfter': True, 'encoderUpdated': False, 'labelsUsedForExtraction': False,
                  'elapsedSeconds': time.monotonic() - started}
        atomic_json(out / 'report.json', report)
        return file_binding(out / 'report.json')
    except Exception as error:
        model_unchanged = all(digest(Path(v['path'])) == v['sha256'] for v in plan['model'].values())
        atomic_json(out / 'failure.json', {'planSha256': sha, 'error': str(error), 'completedClips': len(records), 'modelRehashedUnchanged': model_unchanged, 'environment': env, 'elapsedSeconds': time.monotonic() - started})
        raise


def verify(report_path, sha):
    require(digest(report_path) == sha, 'Report SHA-256 mismatch')
    report = read_json(report_path)
    plan = checked_plan(Path(report['plan']['path']), report['plan']['sha256'])
    guard({'review': report['review']})
    checked_review(Path(report['review']['path']), report['plan']['sha256'])
    require(report['complete'] is True and report['repeatExact'] is True and report['modelRehashedAfter'] is True
            and report['encoderUpdated'] is False and report['labelsUsedForExtraction'] is False, 'Extraction is not frozen and complete')
    require(set(report['parity']) == {plan['firstClipId'], plan['longestClipId']}
            and all(np.isfinite(v) and 0 <= v <= 1e-5 for v in report['parity'].values()), 'Missing or failed parity gate')
    require(report['rowIndices'] == plan['artifacts']['rowIndices'] and report['scalars'] == plan['artifacts']['scalars'], 'Row/scalar binding changed')
    require(all(report['environment'].get(k) == RUNTIME[k] for k in ('torch', 'numpy', 'transformers', 'threads', 'deterministic')), 'Recorded environment differs')
    guard({'timingGate': report['timingGate']})
    timing = read_json(Path(report['timingGate']['path']))
    require(timing['passed'] is True and timing['limitSeconds'] == 2700 and 0 < timing['projectedSeconds'] <= 2700, 'Local timing gate failed')
    guard(report['matrices'])
    matrices = {k: array(v['path'], (9891, 1024), np.float32) for k, v in report['matrices'].items()}
    require(set(matrices) == {'middle', 'final'}, 'Unexpected feature families')
    manifest = read_json(Path(plan['artifacts']['manifest']['path']))
    indices = array(report['rowIndices']['path'], (9891,), np.int64)
    require(indices.tolist() == manifest['rowIndices'] and len(set(indices)) == 9891
            and np.all(indices[1:] > indices[:-1]), 'Global row order changed')
    require(len(report['clipRecords']) == len(manifest['clips']) == 1040, 'Clip coverage differs')
    covered = []
    for binding, clip in zip(report['clipRecords'], manifest['clips'], strict=True):
        guard({'record': binding})
        record = read_json(Path(binding['path']))
        require(record['clip'] == clip, 'Per-clip identity/window binding changed')
        guard({'unit': record['artifact']})
        positions = [r['outputIndex'] for r in clip['rows']]
        covered.extend(positions)
        with np.load(record['artifact']['path'], allow_pickle=False) as unit:
            require(set(unit.files) == {'middle', 'final', 'rowIndices'} and np.array_equal(unit['rowIndices'], indices[positions]), 'Per-clip row mapping differs')
            for name in matrices:
                require(unit[name].dtype == np.float32 and np.array_equal(unit[name], matrices[name][positions]), 'Per-clip/final matrix differs')
    require(sorted(covered) == list(range(9891)), 'Missing or duplicate output rows')
    guard({'repeat': report['repeatArtifact']})
    first_positions = [r['outputIndex'] for r in manifest['clips'][0]['rows']]
    with np.load(report['repeatArtifact']['path'], allow_pickle=False) as repeated:
        require(set(repeated.files) == {'middle', 'final'} and all(np.array_equal(repeated[k], matrices[k][first_positions]) for k in matrices), 'Persisted repeat differs')
    reference = array(plan['artifacts']['reference']['path'], (9891, 1024), np.float32)
    array(report['scalars']['path'], (9891, 13), np.float32)
    for clip in manifest['clips']:
        if clip['id'] in report['parity']:
            positions = [r['outputIndex'] for r in clip['rows']]
            require(parity(matrices['final'][positions], reference[positions]) == report['parity'][clip['id']], 'Reported parity differs from frozen features')
    return {'verified': True, 'report': file_binding(report_path), 'positions': 9891}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    declaration = commands.add_parser('declare'); declaration.add_argument('--out', type=Path, required=True)
    runner = commands.add_parser('run'); runner.add_argument('--plan', type=Path, required=True)
    runner.add_argument('--sha256', required=True); runner.add_argument('--review', type=Path, required=True); runner.add_argument('--out', type=Path, required=True)
    verifier = commands.add_parser('verify'); verifier.add_argument('--report', type=Path, required=True); verifier.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.command == 'declare': result = declare(args.out.resolve())
    elif args.command == 'run': result = run(args.plan.resolve(), args.sha256, args.review.resolve(), args.out.resolve())
    else: result = verify(args.report.resolve(), args.sha256)
    print(result)


if __name__ == '__main__':
    main()
