"""Resumable, train-only contextual features for the multiphone rating study."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import time

import numpy as np
import torch

from encoders import load_encoder
from speechocean_r_probe import AUDIO, read_rating_pcm

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def valid_frames(value: np.ndarray) -> bool:
    return (value.dtype == np.float32 and value.ndim == 2 and 0 < len(value) <= 1500
            and value.shape[1] == 768 and np.isfinite(value).all())


def run(cohort_path: Path, output: Path, encoder_kind: str, device: str) -> dict:
    if not output.resolve().is_relative_to((HERE / 'outputs').resolve()):
        raise ValueError('Feature output must remain in ignored local research outputs')
    if device == 'mps' and not torch.backends.mps.is_available():
        raise ValueError('Requested MPS device is unavailable')
    cohort = json.loads(cohort_path.read_text())
    clips = cohort['clips']
    # Bind IDs to the official author-training map independently of the cohort writer.
    mapping_path = HERE / 'outputs/speechocean762-metadata-v1/train/utt2spk'
    from speechocean_audit import pinned_bytes
    pinned_bytes(mapping_path.parent.parent, 'train/utt2spk')
    train_map = dict(line.split() for line in mapping_path.read_text().splitlines())
    seen = set()
    for clip in clips:
        clip_id = clip['id']
        if (not re.fullmatch(r'\d{9}', clip_id) or clip_id in seen or
                train_map.get(clip_id) != clip['speakerId']):
            raise ValueError('Features must cover unique verified author-training clips')
        canonical = AUDIO / 'WAVE' / ('SPEAKER' + train_map[clip_id]) / (clip_id + '.WAV')
        if Path(clip['audioPath']).resolve() != canonical.resolve():
            raise ValueError('WAV path does not match its official train ID and speaker')
        seen.add(clip_id)
    torch.set_num_threads(2)
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    encoder = load_encoder(encoder_kind, HERE / 'outputs/model-cache', allow_download=False)
    config = {
        'schemaVersion': 1, 'purpose': 'multiphone-subjective-rating-research',
        'cohortSha256': digest(cohort_path), 'encoder': encoder.identity,
        'device': device, 'dtype': 'float32', 'torch': torch.__version__,
        'numpy': np.__version__, 'python': platform.python_version(),
        'sourceSha256': {p.name: digest(p) for p in [Path(__file__), HERE/'encoders.py', HERE/'speechocean_r_probe.py']},
        'authorPartition': 'train', 'clinicalUseEligible': False,
        'learnerFeedbackEligible': False, 'frameTimesValidated': False,
    }
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / 'config.json'
    if config_path.exists():
        if json.loads(config_path.read_text()) != config:
            raise ValueError('Existing cache config differs; choose a fresh output directory')
    else:
        atomic_json(config_path, config)
    encoder.model.to(device).eval()
    started = time.perf_counter()
    index = {}
    old_index_path = output / 'index.json'
    old_entries = json.loads(old_index_path.read_text())['entries'] if old_index_path.exists() else {}
    resumed = 0
    for number, clip in enumerate(clips, 1):
        audio = Path(clip['audioPath'])
        if digest(audio) != clip['audioSha256']:
            raise ValueError(f"Source WAV hash mismatch: {clip['id']}")
        target = output / (clip['id'] + '.npz')
        checksum_path = target.with_suffix('.sha256')
        if target.exists():
            expected = old_entries.get(clip['id'], {}).get('sha256')
            if expected is None and checksum_path.exists():
                expected = checksum_path.read_text().strip()
            if expected is None or digest(target) != expected:
                raise ValueError(f"Existing cache entry has no valid independent checksum: {clip['id']}")
            with np.load(target, allow_pickle=False) as loaded:
                frames = loaded['frames']
                if (not valid_frames(frames) or str(loaded['audio_sha256']) != clip['audioSha256']
                        or str(loaded['config_sha256']) != digest(config_path)):
                    raise ValueError(f"Existing cache entry invalid: {clip['id']}")
            resumed += 1
        else:
            samples = read_rating_pcm(audio, clip['audioSha256'])
            inputs = encoder.processor(samples.numpy(), sampling_rate=16000, return_tensors='pt')
            inputs = {name: value.to(device) for name, value in inputs.items()}
            with torch.inference_mode():
                frames = encoder.model(**inputs).last_hidden_state[0].float().cpu().numpy()
            if not valid_frames(frames):
                raise ValueError(f"Invalid contextual frames: {clip['id']}")
            temporary = target.with_suffix('.npz.tmp')
            with temporary.open('wb') as destination:
                np.savez_compressed(destination, frames=frames, audio_sha256=clip['audioSha256'],
                                    config_sha256=digest(config_path))
            temporary.replace(target)
            checksum_path.write_text(digest(target) + '\n')
        index[clip['id']] = {'path': target.name, 'frames': len(frames), 'sha256': digest(target),
                             'audioSha256': clip['audioSha256']}
        if number % 50 == 0 or number == len(clips):
            elapsed = time.perf_counter() - started
            status = {'processed': number, 'total': len(clips), 'resumed': resumed,
                      'elapsedSeconds': elapsed, 'pid': os.getpid(), 'complete': False}
            atomic_json(output / 'status.json', status)
            print(json.dumps(status), flush=True)
    if digest(cohort_path) != config['cohortSha256'] or any(
            digest(HERE / name) != value for name, value in config['sourceSha256'].items()):
        raise ValueError('Source changed while generating features')
    report = {'configSha256': digest(config_path), 'entries': index, 'clipCount': len(index),
              'elapsedSeconds': time.perf_counter() - started, 'resumed': resumed, 'complete': True}
    atomic_json(output / 'index.json', report)
    atomic_json(output / 'status.json', {'processed': len(index), 'total': len(clips),
                                       'complete': True, 'elapsedSeconds': report['elapsedSeconds']})
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--encoder', choices=['wav2vec2-base', 'wavlm-base-plus', 'hubert-base-ls960'], required=True)
    parser.add_argument('--device', choices=['cpu', 'mps'], default='mps')
    args = parser.parse_args()
    result = run(args.cohort, args.output, args.encoder, args.device)
    print(json.dumps({key: value for key, value in result.items() if key != 'entries'}), flush=True)
