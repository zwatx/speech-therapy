"""Frozen phonetic-checkpoint vectors on unchanged author-train target windows.

No ratings enter extraction, no alignment is recomputed, and no complete frame
cache is retained. Each target gets local and whole-clip contextual embeddings.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

import numpy as np
import torch

from multiphone_cache import digest
from multiphone_local_features import convolution_frames, validate_manifest_rows
from speechocean_audit import pinned_bytes
from speechocean_r_probe import AUDIO, METADATA, read_rating_pcm

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
RECIPE = HERE / 'experiments/multiphone-phonetic-features-v1.json'
SOURCES = ('multiphone_phonetic_features.py', 'multiphone_cache.py', 'multiphone_local_features.py',
           'alignment_pilot.py', 'encoders.py', 'speechocean_audit.py', 'speechocean_r_probe.py')
ROW_FIELDS = ('rowIndex', 'rowId', 'clipId', 'targetId', 'targetPhone', 'canonicalIndex',
              'wordIndex', 'phoneIndex', 'intervalFrames', 'estimatedPoolingWindowFrames')
FALSE_FLAGS = {name: False for name in ('labelsUsedForExtraction', 'newAlignmentPerformed', 'encoderUpdated',
    'authorTestInferencePerformed', 'frameTimesValidated', 'producedPhoneLabelsAvailable',
    'clinicalUseEligible', 'learnerFeedbackEligible')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def atomic_json(path: Path, value):
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'
    atomic_bytes(path, payload.encode())


def atomic_bytes(path: Path, payload: bytes):
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def file_binding(path: Path):
    return {'path': str(path.resolve()), 'sha256': digest(path)}


def guard(bindings):
    require(all(digest(Path(value['path'])) == value['sha256'] for value in bindings.values()),
            'Source, checkpoint, recipe or extraction input changed')


def load_inputs(cohort_path: Path, splits_path: Path, feature_path: Path, recipe: dict):
    paths = {'cohort': cohort_path, 'splits': splits_path, 'features': feature_path}
    bindings = {name: file_binding(path) for name, path in paths.items()}
    require(all(bindings[name]['sha256'] == recipe[name + 'Sha256'] for name in paths),
            'Study/feature input differs from the fixed recipe')
    cohort, splits, features = (read_json(path) for path in paths.values())
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train', 'Expected author-train inputs')
    # Splits are carried for provenance only; neither split outcomes nor ratings select features.
    eligible = {i for i, row in enumerate(cohort['rows']) if row['trainingEligible']}
    indices = features['rowIndices']
    require(features['complete'] is True and features['fullCohortCoverage'] is True
            and features['eligibleCohortRows'] == recipe['expectedEligibleRows'] == len(eligible)
            and features['failedRows'] == features['unmappableRows'] == []
            and len(indices) == len(set(indices)) == len(eligible) and set(indices) == eligible
            and all(type(i) is int for i in indices) and len(features['rows']) == len(indices)
            and all(features.get(flag) is False for flag in
                    ('frameTimesValidated', 'producedPhoneLabelsAvailable', 'authorTestInferencePerformed',
                     'clinicalUseEligible', 'learnerFeedbackEligible')),
            'Feature coverage or research scope differs')
    require(features['cohortSha256'] == bindings['cohort']['sha256']
            and features['splitsSha256'] == bindings['splits']['sha256'], 'Feature data/split binding differs')
    for name in ('manifest', 'ctcIndex', 'recipe'):
        path = Path(features[name + 'Path'])
        path = path if path.is_absolute() else feature_path.parent / path
        bindings['original/' + name] = file_binding(path)
        require(bindings['original/' + name]['sha256'] == features[name + 'Sha256'], 'Original feature lineage differs')
    require(set(features['sourceSha256']) == {'multiphone_local_features.py', 'alignment_pilot.py'},
            'Unexpected original extraction sources')
    for name, sha in features['sourceSha256'].items():
        require(digest(HERE / name) == sha, 'Original extraction source changed')
    manifest = read_json(Path(bindings['original/manifest']['path']))
    validate_manifest_rows(manifest, cohort)
    require(manifest['fullCohortCoverage'] is True and manifest['partition'] == 'allEligibleAuthorTrain'
            and manifest['cohortSha256'] == recipe['cohortSha256']
            and manifest['splitsSha256'] == recipe['splitsSha256'], 'Manifest scope/data binding differs')
    ctc_path = Path(bindings['original/ctcIndex']['path'])
    bindings['original/ctcConfig'] = file_binding(ctc_path.parent / 'config.json')
    ctc, ctc_config = read_json(ctc_path), read_json(ctc_path.parent / 'config.json')
    require(ctc['complete'] is True and ctc['configSha256'] == bindings['original/ctcConfig']['sha256']
            and ctc_config['manifestSha256'] == bindings['original/manifest']['sha256'], 'CTC manifest/config binding differs')
    original_recipe = read_json(Path(bindings['original/recipe']['path']))
    require(all(original_recipe[key] == recipe[key] for key in ('convKernel', 'convStride', 'poolingContextFrames')),
            'Original and phonetic frame-grid/window recipes differ')
    manifest_rows = {row['rowIndex']: {**row, 'clipId': clip['id']} for clip in manifest['clips'] for row in clip['targetRows']}
    rows, by_clip = [], {}
    for position, (index, row) in enumerate(zip(indices, features['rows'], strict=True)):
        source = cohort['rows'][index]
        expected = {'rowIndex': index, 'rowId': source['id'], **{key: source[key] for key in
                    ('clipId', 'targetId', 'targetPhone', 'wordIndex', 'phoneIndex')}}
        require(all(row[key] == value for key, value in expected.items())
                and all(row[key] == value for key, value in manifest_rows[index].items()), 'Original target identity/order differs')
        exported = {key: row[key] for key in ROW_FIELDS}
        exported['outputIndex'] = position
        rows.append(exported)
        by_clip.setdefault(row['clipId'], []).append(exported)
    train_bytes = pinned_bytes(METADATA, 'train/utt2spk')
    train_map = dict(line.split() for line in train_bytes.decode().splitlines())
    bindings['authorTrainMap'] = file_binding(METADATA / 'train/utt2spk')
    clips = [clip for clip in cohort['clips'] if clip['id'] in by_clip]
    require(len(clips) == recipe['expectedClips'] == len(by_clip) and len({clip['id'] for clip in clips}) == len(clips)
            and set(ctc['entries']) == set(by_clip), 'Original clip coverage differs')
    for clip in clips:
        clip_id = clip['id']
        canonical = AUDIO / 'WAVE' / ('SPEAKER' + clip['speakerId']) / (clip_id + '.WAV')
        require(re.fullmatch(r'\d{9}', clip_id) and train_map.get(clip_id) == clip['speakerId']
                and Path(clip['audioPath']).resolve() == canonical.resolve(), 'Waveform is not a canonical author-train clip')
        entry = ctc['entries'][clip_id]
        frames = convolution_frames(clip['sampleCount'], recipe)
        require(0 < frames <= 1500 and entry['frames'] == frames and entry['audioSha256'] == clip['audioSha256']
                and entry['configSha256'] == ctc['configSha256'], 'Source waveform/frame grid differs from existing CTC cache')
        for row in by_clip[clip_id]:
            interval, window = row['intervalFrames'], row['estimatedPoolingWindowFrames']
            require(len(interval) == len(window) == 2 and all(type(v) is int for v in interval + window)
                    and 0 <= interval[0] < interval[1] <= frames
                    and window == [max(0, interval[0] - 2), min(frames, interval[1] + 2)],
                    'Original estimated pooling window differs from fixed context recipe')
    guard(bindings)
    return rows, clips, by_clip, bindings


def checkpoint_files(snapshot: Path, download_path: Path, recipe: dict):
    require(digest(download_path) == recipe['downloadRecordSha256'], 'Checkpoint download record changed')
    download = read_json(download_path)
    require(download['repo'] == recipe['modelId'] and download['revision'] == recipe['revision'], 'Checkpoint identity differs')
    bindings = {'checkpoint/downloadRecord': file_binding(download_path)}
    for filename, expected in recipe['artifactSha256'].items():
        path = snapshot / filename
        require(path.is_file(), 'Pinned checkpoint artifact is missing: ' + filename)
        binding = file_binding(path)
        require(binding['sha256'] == download['files'][filename]['sha256'] == expected,
                'Pinned checkpoint artifact differs: ' + filename)
        bindings['checkpoint/' + filename] = binding
    model_config = read_json(snapshot / 'config.json')
    require(model_config['hidden_size'] == recipe['hiddenWidth'] and model_config['vocab_size'] == recipe['vocabularySize']
            and model_config['conv_kernel'] == recipe['convKernel'] and model_config['conv_stride'] == recipe['convStride'],
            'Phonetic checkpoint dimensions/frame grid differ')
    return bindings


class PhoneticEncoder:
    def __init__(self, snapshot: Path, recipe: dict):
        from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(str(snapshot), local_files_only=True)
        require(self.processor.do_normalize is True and self.processor.return_attention_mask is True
                and self.processor.sampling_rate == 16000 and self.processor.feature_size == 1,
                'Pinned phonetic preprocessing differs')
        self.model = Wav2Vec2ForCTC.from_pretrained(str(snapshot), local_files_only=True,
            attn_implementation='eager', use_safetensors=False, weights_only=True).to(device='cpu', dtype=torch.float32)
        self.model.requires_grad_(False).eval()
        require(self.model.config._attn_implementation == 'eager', 'Expected eager attention')

    @torch.inference_mode()
    def __call__(self, samples):
        inputs = self.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt')
        return self.model.wav2vec2(**inputs).last_hidden_state[0].cpu().numpy()


def pooled_vectors(frames: np.ndarray, rows: list[dict], expected_frames: int, width=1024):
    require(frames.dtype == np.float32 and frames.shape == (expected_frames, width)
            and 0 < expected_frames <= 1500 and np.isfinite(frames).all(), 'Invalid full-precision hidden frame grid')
    target = []
    for row in rows:
        window = row['estimatedPoolingWindowFrames']
        require(len(window) == 2 and all(type(v) is int for v in window)
                and 0 <= window[0] < window[1] <= expected_frames, 'Invalid target window')
        target.append(frames[window[0]:window[1]].mean(0, dtype=np.float64).astype(np.float32))
    require(target, 'Every clip must have an eligible target')
    return np.stack(target), frames.mean(0, dtype=np.float64).astype(np.float32)


def expected_entry(clip, rows, config_sha, frames):
    return {'clipId': clip['id'], 'audioSha256': clip['audioSha256'], 'sampleCount': clip['sampleCount'],
            'configSha256': config_sha, 'frames': frames, 'rows': rows}


def checked_unit(directory: Path, expected: dict, width: int, prior_pin=None):
    entry_path, array_path = directory / 'entry.json', directory / 'vectors.npz'
    if prior_pin is not None:
        require(digest(entry_path) == prior_pin['entrySha256'] and digest(array_path) == prior_pin['sha256'],
                'Completed per-clip artifact changed')
    entry = read_json(entry_path)
    require(entry['binding'] == expected and entry['vectorsPath'] == 'vectors.npz'
            and digest(array_path) == entry['sha256'], 'Resumed per-clip binding/checksum differs')
    with np.load(array_path, allow_pickle=False) as archive:
        require(set(archive.files) == {'target', 'global'}, 'Unexpected cached vector fields')
        target, global_vector = archive['target'], archive['global']
    require(target.dtype == global_vector.dtype == np.float32 and target.shape == (len(expected['rows']), width)
            and global_vector.shape == (width,) and np.isfinite(target).all() and np.isfinite(global_vector).all(),
            'Invalid cached vector shape/dtype/values')
    return target, global_vector


def write_unit(directory: Path, expected: dict, target: np.ndarray, global_vector: np.ndarray):
    temporary = Path(tempfile.mkdtemp(prefix='.' + directory.name + '-', dir=directory.parent))
    try:
        with (temporary / 'vectors.npz').open('wb') as stream:
            np.savez_compressed(stream, target=target, **{'global': global_vector})
        atomic_json(temporary / 'entry.json', {'binding': expected, 'vectorsPath': 'vectors.npz',
                                              'sha256': digest(temporary / 'vectors.npz')})
        require(not directory.exists(), 'Per-clip output already exists')
        temporary.rename(directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def atomic_array(path: Path, values: np.ndarray):
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            np.save(stream, values, allow_pickle=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def extract(args):
    require(args.output.resolve().is_relative_to((HERE / 'outputs').resolve()), 'Keep features in ignored research outputs')
    recipe = read_json(RECIPE)
    require(recipe['device'] == 'cpu' and recipe['threads'] == 2 and recipe['dtype'] == 'float32'
            and recipe['attentionImplementation'] == 'eager' and recipe['hiddenWidth'] == 1024,
            'Only the declared CPU full-precision extraction is permitted')
    torch.set_num_threads(2)
    os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
    started = time.perf_counter()
    rows, clips, by_clip, bindings = load_inputs(args.cohort, args.splits, args.features, recipe)
    bindings.update(checkpoint_files(args.snapshot, args.download_record, recipe))
    bindings['recipe'] = file_binding(RECIPE)
    bindings.update({'source/' + name: file_binding(HERE / name) for name in SOURCES})
    import transformers
    config = {'schemaVersion': 1, 'recipe': recipe, 'bindings': bindings,
              'torch': str(torch.__version__), 'numpy': np.__version__, 'transformers': transformers.__version__,
              'authorPartition': 'train', 'device': 'cpu', 'threads': 2, 'dtype': 'float32', **FALSE_FLAGS}
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.output / '.extract.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('This extraction directory is already in use') from error
        return extract_locked(args.output, args.snapshot, config, rows, clips, by_clip, started)


def extract_locked(output, snapshot, config, rows, clips, by_clip, started):
    config_path = output / 'config.json'
    if config_path.exists():
        require(read_json(config_path) == config, 'Existing extraction config differs; choose a fresh directory')
    else:
        require(not (output / 'clips').exists(), 'Orphan clip artifacts lack extraction config')
        atomic_json(config_path, config)
    config_sha = digest(config_path)
    clip_directory = output / 'clips'
    clip_directory.mkdir(exist_ok=True, mode=0o700)
    old_path = output / 'index.json'
    previous = read_json(old_path) if old_path.exists() else None
    complete_path = output / 'features.json'
    previous_report = read_json(complete_path) if complete_path.exists() else None
    if previous_report is not None:
        require(previous_report['complete'] is True and previous_report['configSha256'] == config_sha
                and previous_report['bindings'] == config['bindings'] and previous_report['rows'] == rows
                and previous_report['rowIndices'] == [row['rowIndex'] for row in rows]
                and previous_report['indexSha256'] == digest(old_path), 'Completed report/index binding differs')
    require(previous is None or previous['configSha256'] == config_sha, 'Previous index belongs to another config')
    previous_entries = previous['entries'] if previous else {}
    require(set(previous_entries) <= {clip['id'] for clip in clips}, 'Previous index includes unknown clips')
    recipe, encoder, entries, resumed = config['recipe'], None, {}, 0
    count, width = len(rows), recipe['hiddenWidth']
    target_all, global_all = np.empty((count, width), dtype=np.float32), np.empty((count, width), dtype=np.float32)
    assigned = np.zeros(count, dtype=bool)
    for number, clip in enumerate(clips, 1):
        samples = read_rating_pcm(Path(clip['audioPath']), clip['audioSha256'])
        require(len(samples) == clip['sampleCount'], 'Waveform sample count differs')
        frames = convolution_frames(len(samples), recipe)
        selected = by_clip[clip['id']]
        expected = expected_entry(clip, selected, config_sha, frames)
        directory = clip_directory / clip['id']
        if directory.exists():
            target, global_vector = checked_unit(directory, expected, width, previous_entries.get(clip['id']))
            resumed += 1
        else:
            require(clip['id'] not in previous_entries, 'Previously indexed clip artifact is missing')
            if encoder is None:
                guard(config['bindings'])
                encoder = PhoneticEncoder(snapshot, recipe)
            hidden = encoder(samples)
            target, global_vector = pooled_vectors(hidden, selected, frames, width)
            del hidden
            write_unit(directory, expected, target, global_vector)
            target, global_vector = checked_unit(directory, expected, width)
        output_positions = [row['outputIndex'] for row in selected]
        require(not assigned[output_positions].any(), 'Duplicate output row assignment')
        target_all[output_positions] = target
        global_all[output_positions] = global_vector
        assigned[output_positions] = True
        entries[clip['id']] = {'path': str(directory.relative_to(output) / 'vectors.npz'),
                               'sha256': digest(directory / 'vectors.npz'), 'entrySha256': digest(directory / 'entry.json'),
                               'audioSha256': clip['audioSha256'], 'frames': frames, 'targets': len(selected)}
        if (number % 25 == 0 or number == len(clips)) and previous_report is None:
            atomic_json(old_path, {'configSha256': config_sha, 'complete': False, 'entries': entries})
            status = {'complete': False, 'processedClips': number, 'totalClips': len(clips), 'resumedClips': resumed,
                      'elapsedSeconds': time.perf_counter() - started, 'pid': os.getpid()}
            atomic_json(output / 'status.json', status)
            print(json.dumps(status), flush=True)
    require(assigned.all() and np.isfinite(target_all).all() and np.isfinite(global_all).all(), 'Incomplete/nonfinite assembled features')
    guard(config['bindings'])
    # Revalidate internal checksums and values, not only a hash captured after a
    # prior read. Otherwise a file changed between that read and hash capture
    # could be incorrectly accepted as the authoritative unit.
    for clip in clips:
        selected = by_clip[clip['id']]
        entry = entries[clip['id']]
        expected = expected_entry(clip, selected, config_sha, entry['frames'])
        target, global_vector = checked_unit((output / entry['path']).parent, expected, width, entry)
        output_positions = [row['outputIndex'] for row in selected]
        require(np.array_equal(target_all[output_positions], target)
                and np.array_equal(global_all[output_positions], np.broadcast_to(global_vector, target.shape)),
                'Per-clip vectors changed after assembly')
    if previous_report is not None:
        for name, values in (('target', target_all), ('global', global_all)):
            descriptor = previous_report[name + 'Features']
            path = output / descriptor['path']
            require(descriptor['path'] == name + '.npy' and descriptor['shape'] == list(values.shape)
                    and descriptor['dtype'] == 'float32' and digest(path) == descriptor['sha256']
                    and np.array_equal(np.load(path, allow_pickle=False), values),
                    'Completed feature matrix changed')
        return previous_report
    descriptors = {}
    for name, values in (('target', target_all), ('global', global_all)):
        path = output / (name + '.npy')
        atomic_array(path, values)
        descriptors[name + 'Features'] = {'path': path.name, 'sha256': digest(path), 'shape': list(values.shape), 'dtype': 'float32'}
    atomic_json(old_path, {'configSha256': config_sha, 'complete': True, 'entries': entries, 'clipCount': len(entries)})
    report = {'schemaVersion': 1, 'experiment': recipe['experiment'], 'complete': True, 'fullCohortCoverage': True,
              'configPath': str(config_path.resolve()), 'configSha256': config_sha,
              'indexSha256': digest(old_path), 'bindings': config['bindings'],
              'rowIndices': [row['rowIndex'] for row in rows], 'rows': rows,
              'eligibleCohortRows': count, 'clipCount': len(clips), 'failedRows': [], 'unmappableRows': [],
              'encoderIdentity': {key: recipe[key] for key in ('modelId', 'revision', 'artifactSha256', 'hiddenWidth')},
              'originalWindowsUnchanged': True, 'globalVectorsRepeatedPerTarget': True, **descriptors,
              'elapsedSeconds': time.perf_counter() - started, 'resumedClips': resumed,
              'limitations': recipe['limitations'], **FALSE_FLAGS}
    atomic_json(complete_path, report)
    atomic_json(output / 'status.json', {'complete': True, 'processedClips': len(clips), 'resumedClips': resumed,
                                       'elapsedSeconds': report['elapsedSeconds']})
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, default=BASE / 'cohort.json')
    parser.add_argument('--splits', type=Path, default=BASE / 'splits.json')
    parser.add_argument('--features', type=Path, default=BASE / 'ctc-local-full/features/features.json')
    parser.add_argument('--download-record', type=Path, default=BASE / 'phonetic-torch-download.json')
    parser.add_argument('--snapshot', type=Path, default=HERE / 'outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4')
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    report = extract(arguments)
    print(json.dumps({key: report[key] for key in ('complete', 'eligibleCohortRows', 'clipCount', 'resumedClips')}))
