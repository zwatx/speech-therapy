"""Frozen child-disjoint JIBO manifest; session audio is cropped without quantization."""
import csv
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

import numpy as np
from scipy.io import wavfile
from .inventory import JIBO_VERSION, tokenize_jibo
from .manifest import ROOT, OUTPUT, load_manifest

RUN = OUTPUT/'stage-c'
DATA = ROOT/'outputs/jibo-kids'


def split_children(metadata, seed=31):
    """Stratify by released gender + available task set; sessions stay together."""
    children = defaultdict(list)
    for row in metadata:
        children[row['child_id']].append(row)
    strata = defaultdict(list)
    for child, rows in sorted(children.items()):
        genders = {r['gender'] for r in rows}
        if len(genders) != 1:
            raise ValueError('Inconsistent child gender')
        strata[(next(iter(genders)), tuple(sorted({r['task'] for r in rows})))].append(child)
    result = {}
    rng = random.Random(seed)
    # Deal each stratum into globally balanced targets. Prefer underfilled
    # splits proportional to 80/10/10; deterministic randomized order within strata.
    targets = {'train': round(.8*len(children)), 'dev': round(.1*len(children))}
    targets['test'] = len(children)-sum(targets.values())
    counts = Counter()
    for _, group in sorted(strata.items()):
        rng.shuffle(group)
        for child in group:
            split = min(targets, key=lambda s: counts[s]/targets[s])
            result[child] = split; counts[split] += 1
    return result


def read_interval(row):
    rate, audio = wavfile.read(row['audio'], mmap=True)
    if rate != 16000 or audio.ndim != 1:
        raise ValueError('JIBO audio must be mono 16 kHz')
    start = round(row['start_seconds']*16000)
    end = min(round(row['end_seconds']*16000), len(audio))
    samples = audio[start:end].astype(np.float32)
    if audio.dtype == np.int16:
        samples /= 32768
    elif audio.dtype != np.float32:
        raise ValueError('Unsupported JIBO encoding')
    if rate != 16000 or len(samples) < 400 or not np.isfinite(samples).all():
        raise ValueError('Invalid JIBO interval')
    return samples


def build():
    RUN.mkdir(exist_ok=True)
    split_path = RUN/'child-split.json'
    if split_path.exists() or (RUN/'manifest.jsonl').exists():
        raise FileExistsError('Frozen Stage C manifest already exists')
    meta_root = DATA/'transcripts-release'
    with (meta_root/'metadata.csv').open() as source:
        metadata = list(csv.DictReader(source))
    split = split_children(metadata)
    # Persist split BEFORE any audio/model operation or mapping exclusion.
    split_path.write_text(json.dumps(dict(seed=31, method='gender/task-set stratified proportional dealing',
                                          children=split), indent=2))
    rows, excluded, unknown, counts = [], [], Counter(), Counter()
    for meta in metadata:
        for line in (meta_root/meta['transcript_path']).read_text().splitlines():
            raw = json.loads(line)
            text = raw['phonetic_text_normalized']
            reason = None
            if text is None or raw['inexact_transcription']:
                reason = 'null/inexact'
            elif 'xxx' in text.lower() or 'xxx' in raw['orthographic_text_normalized'].lower():
                reason = 'xxx'
            if reason:
                excluded.append(dict(id=raw['utterance_id'], reason=reason)); continue
            counts['candidate_after_xxx'] += 1
            phones, missing = tokenize_jibo(text)
            unknown.update(missing)
            if missing or not phones:
                excluded.append(dict(id=raw['utterance_id'], reason='unmapped', symbols=missing)); continue
            audio = DATA/'audio-release/jibo_release/data'/meta['raw_audio_path']
            rate, signal = wavfile.read(audio, mmap=True)
            overrun = raw['end_seconds']-len(signal)/rate
            # Tolerate <= one rounded millisecond only; reject material overrun.
            if overrun > .001:
                excluded.append(dict(id=raw['utterance_id'], reason='endpoint_overrun', seconds=overrun)); continue
            row = dict(id='jibo:'+raw['utterance_id'], source='jibo', speaker=meta['child_id'],
                       split=split[meta['child_id']], audio=str(audio), task=meta['task'],
                       gender=meta['gender'], age=None, population='child', canonical=None,
                       perceived=phones, inventory=JIBO_VERSION, raw=raw,
                       start_seconds=raw['start_seconds'], end_seconds=raw['end_seconds'],
                       clamped_rounding_seconds=max(0., overrun))
            samples = read_interval(row)
            # Hash cropped float32 samples so same-session intervals are distinct.
            row['audio_sha256'] = hashlib.sha256(samples.tobytes()).hexdigest()
            row['duration_seconds'] = len(samples)/16000
            rows.append(row)
    digest_splits = defaultdict(set)
    for row in rows:
        digest_splits[row['audio_sha256']].add(row['split'])
    if any(len(s) > 1 for s in digest_splits.values()):
        raise ValueError('Identical interval audio crosses split')
    summary = dict(mapping=JIBO_VERSION, unknown_symbols=dict(unknown), excluded=excluded,
                   exclusion_counts=dict(Counter(r['reason'] for r in excluded)), **counts, splits={})
    for name in ('train', 'dev', 'test'):
        selected = [r for r in rows if r['split'] == name]
        summary['splits'][name] = dict(utterances=len(selected), children=len({r['speaker'] for r in selected}),
            hours=sum(r['duration_seconds'] for r in selected)/3600,
            phones=sum(len(r['perceived']) for r in selected), tasks=dict(Counter(r['task'] for r in selected)),
            genders=dict(Counter({r['speaker']: r['gender'] for r in selected}.values())))
    speech = [r for r in load_manifest() if r['source'] == 'speechocean762' and r['split'] == 'test']
    speakers = sorted({r['speaker'] for r in speech})
    random.Random(31).shuffle(speakers)
    detection = dict(calibration_speakers=speakers[:len(speakers)//2], reporting_speakers=speakers[len(speakers)//2:],
                     warning='Both groups previously consumed for round-2 development; no sealed test claim')
    (RUN/'speech-detection-split.json').write_text(json.dumps(detection, indent=2))
    (RUN/'manifest.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
    (RUN/'data-summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({k:v for k,v in summary.items() if k != 'excluded'}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    build()
