"""Build permitted pilot/manual and score-derived manifests without guessing labels.

Run from research/audio-head: python -B -m mdd_v1.manifest
Only four named nested zip payloads are opened; no reserved payload is inspected.
"""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path
import zipfile
from collections import Counter

from l2_arctic_annotations import parse_textgrid, interpret_label
from .inventory import VERSION, normalize_arpabet

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/mdd_v1'
PILOT = ('YDCK', 'ZHAA', 'ASI', 'YBAA')
RESERVED = frozenset('EBVS HQTV HJK ERMS YKWK PNV RRBI SVBI TXHC LXC THV MBMPS NCC NJS SKA HKK TLV TNI ABA BWC'.split())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def l2_record(raw, speaker, utterance, audio_path):
    if speaker not in PILOT or speaker in RESERVED:
        raise ValueError('Speaker is outside the authorized pilot')
    grid = parse_textgrid(raw)
    intervals = next(t['intervals'] for t in grid['tiers'] if t['name'] == 'phones')
    parsed = dict(records=[])
    for interval in intervals:
        fields = [part.strip() for part in interval['rawLabel'].split(',')]
        normalized = []
        for i, value in enumerate(fields):
            if len(fields) == 3 and i == 2:
                value = value.lower()
            elif value.lower() in ('sil', 'sp', 'err', 'err*'):
                value = value.lower()
            else:
                value = re.sub(r'^AX(?=[012*]|$)', 'AH', value.upper())
            normalized.append(value)
        label = ','.join(normalized)
        interpretation = interpret_label(label)
        parsed['records'].append(dict(**interval,
            **{k: v for k, v in interpretation.items() if k != 'rawLabel'},
            normalizedLabel=label))
    canonical, perceived, events = [], [], []
    for row in parsed['records']:
        if row['event'] == 'nonlexical':
            continue
        c = row['canonical']['phone'] if row['canonical'] else None
        p = row['perceived']['phone'] if row['perceived'] else None
        events.append(dict(canonical_index=len(canonical), canonical=c, perceived=p,
                           event=row['event'], raw=row['rawLabel'], start=row['start'], end=row['end'],
                           perceived_detail=row['perceived']))
        if c is not None:
            canonical.append(c)
        if row['perceived'] is not None:
            perceived.append(p)  # None is an unknown identity, not deletion.
    if not canonical:
        raise ValueError('Empty canonical sequence')
    return dict(id=f'l2:{speaker}:{utterance}', source='l2-arctic', speaker=speaker,
                split='l2-eval', age=None, population='adult', audio=str(audio_path),
                canonical=canonical, perceived=perceived, events=events,
                inventory=VERSION, textgrid_sha256=digest(raw), raw_intervals=parsed['records'],
                provenance='L2-ARCTIC v5 manual annotation/ TextGrid; not automatic textgrid/')


def speech_record(item, speaker, utterance, split, age, audio_path):
    canonical, produced, scores, raw = [], [], [], []
    for word in item['words']:
        phones = word['phones'].split() if isinstance(word['phones'], str) else word['phones']
        accuracy = word['phones-accuracy']
        if len(phones) != len(accuracy):
            raise ValueError('Phone/score length mismatch')
        for phone, score in zip(phones, accuracy):
            if not isinstance(score, (int, float)) or not 0 <= score <= 2:
                raise ValueError('Invalid expert phone score')
            normalized = normalize_arpabet(phone)
            raw.append(phone)
            canonical.append(normalized)
            scores.append(score)
            produced.append(normalized if score == 2 else None)
    if not canonical:
        raise ValueError('Empty phone sequence')
    return dict(id=f'so:{utterance}', source='speechocean762', speaker=speaker, split=split,
                age=age, population='child' if age is not None and age < 18 else 'adult' if age else 'unknown',
                audio=str(audio_path), canonical=canonical, perceived=produced, scores=scores,
                raw_phones=raw, inventory=VERSION, all_correct=all(p is not None for p in produced),
                provenance='resource/scores.json; score 2 only, all other identities masked; not phonetic transcription')


def check_leakage(records):
    speakers, ids, audio = {}, set(), {}
    for row in records:
        key = row['source'], row['speaker']
        if row['source'] == 'l2-arctic' and row['speaker'] not in PILOT:
            raise ValueError('Unauthorized L2 speaker')
        if key in speakers and speakers[key] != row['split']:
            raise ValueError(f'Speaker leakage: {key}')
        speakers[key] = row['split']
        if row['id'] in ids:
            raise ValueError('Duplicate utterance ID')
        ids.add(row['id'])
        if row['audio'] in audio:
            raise ValueError('Repeated audio path')
        audio[row['audio']] = row['split']
        if row.get('audio_sha256'):
            key = row['audio_sha256']
            if key in audio and audio[key] != row['split']:
                raise ValueError('Identical audio across splits')
            audio[key] = row['split']


def load_manifest(path=OUTPUT/'manifest.jsonl'):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def build(archive, output=OUTPUT):
    output.mkdir(parents=True, exist_ok=True)
    records, excluded = [], []
    with zipfile.ZipFile(archive) as outer:
        for speaker in PILOT:
            # Exact name: never enumerate other nested archive contents.
            with zipfile.ZipFile(io.BytesIO(outer.read(f'{speaker}.zip'))) as inner:
                names = sorted(n for n in inner.namelist()
                               if n.startswith(f'{speaker}/annotation/') and n.endswith('.TextGrid'))
                for member in names:
                    utterance = Path(member).stem
                    dest = output/'l2-pilot'/speaker/f'{utterance}.wav'
                    raw = inner.read(member)
                    try:
                        row = l2_record(raw, speaker, utterance, dest)
                    except ValueError as error:
                        excluded.append(dict(source='l2-arctic', member=member, reason=str(error)))
                        continue
                    audio = inner.read(f'{speaker}/wav/{utterance}.wav')
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(audio)
                    row['audio_sha256'] = digest(audio)
                    records.append(row)
    meta = ROOT/'outputs/speechocean762-metadata-v1'
    scores = json.loads((meta/'resource/scores.json').read_text())
    for split in ('train', 'test'):
        ages = {}
        for line in (meta/split/'spk2age').read_text().splitlines():
            fields = line.split()
            ages[fields[0]] = int(fields[1]) if len(fields) > 1 else None
        for line in (meta/split/'utt2spk').read_text().splitlines():
            utterance, speaker = line.split()
            path = ROOT/f'outputs/speechocean762-audio-v1/speechocean762/WAVE/SPEAKER{speaker}/{utterance}.WAV'
            row = speech_record(scores[utterance], speaker, utterance, split, ages.get(speaker), path)
            row['audio_sha256'] = digest(path.read_bytes())
            records.append(row)
    check_leakage(records)
    (output/'manifest.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records))
    summary = dict(records=len(records), excluded=excluded, groups={})
    for source, split in sorted({(r['source'], r['split']) for r in records}):
        rows = [r for r in records if (r['source'], r['split']) == (source, split)]
        summary['groups'][f'{source}/{split}'] = dict(
            utterances=len(rows), speakers=len({r['speaker'] for r in rows}),
            all_correct_utterances=sum(r.get('all_correct', False) for r in rows),
            phones=sum(len(r['canonical']) for r in rows),
            unknown_phones=sum(p is None for r in rows for p in r['perceived']),
            population_utterances=dict(Counter(r['population'] for r in rows)),
            population_speakers=dict(Counter({r['speaker']: r['population'] for r in rows}.values())),
            ages=sorted({r['age'] for r in rows if r['age'] is not None}))
    (output/'manifest-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, default=Path.home()/'Downloads/l2arctic_release_v5.0.zip')
    args = parser.parse_args()
    build(args.archive)
