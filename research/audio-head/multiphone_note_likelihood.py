"""Fixed recognizer diagnostic on selective human notes; no fitting or audio reads."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics

from multiphone_sequence_preflight import binding, guard, read_bound, require, write_new
from speechocean_audit import FILES, mapping, pinned_bytes
from speechocean_r_label_audit import METADATA, selected_json_objects

HERE = Path(__file__).resolve().parent
EXPORT = HERE / 'outputs/multiphone-20260927/sequence-features-v1/features.json'
EXPORT_SHA = '6f7ec75697d2f6502805f5e43965200a2683c49c78aa6208c6287f5eaa025114'
TARGETS = 'B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG'.split()
PROTOCOL = HERE / '../../docs/model/multiphone-note-likelihood-protocol.md'
TOLERANCE = 1e-8


def derive_notes(train, ages, aggregate):
    require(set(train) == set(aggregate) and set(train.values()) == set(ages), 'Train identity differs')
    rows = []
    for clip_id in sorted(train):
        speaker = train[clip_id]
        age = int(ages[speaker])
        require(0 < age < 120, 'Invalid age')
        clip_rows, offset = [], 0
        canonical_phones = [p for word in aggregate[clip_id]['words'] for p in word['phones']]
        for wi, word in enumerate(aggregate[clip_id]['words']):
            phones, scores = word['phones'], word['phones-accuracy']
            require(type(phones) is list and phones and len(phones) == len(scores), 'Invalid word geometry')
            require(all(type(p) is str and re.fullmatch(r'[A-Z]+[012]?', p) for p in phones), 'Invalid phone')
            notes = word.get('mispronunciations', [])
            require(type(notes) is list, 'Invalid note list')
            seen = set()
            for note in notes:
                require(set(note) == {'index', 'canonical-phone', 'pronounced-phone'}, 'Invalid note fields')
                pi = note['index']
                require(type(pi) is int and 0 <= pi < len(phones) and pi not in seen, 'Invalid or duplicate position')
                seen.add(pi)
                canonical = re.sub(r'[012]$', '', phones[pi])
                require(note['canonical-phone'] == canonical, 'Canonical note identity differs')
                raw = note['pronounced-phone']
                require(type(raw) is str and 0 < len(raw) <= 32, 'Invalid production description')
                score = scores[pi]
                require(type(score) in (int, float) and 0 <= score <= 2, 'Invalid note rating')
                clip_rows.append(dict(noteId=f'{clip_id}:{wi}:{pi}', clipId=clip_id, speakerId=speaker,
                    age=age, wordIndex=wi, phoneIndex=pi, canonicalIndex=offset+pi,
                    canonicalRaw=phones[pi], targetPhone=canonical, producedRaw=raw,
                    precedingCanonicalPhone=canonical_phones[offset+pi-1] if offset+pi else None,
                    meanRating=score, belowHalf=score < .5))
            offset += len(phones)
        rows.extend(dict(row, notesInUtterance=len(clip_rows)) for row in clip_rows)
    return rows


def choose_notes(notes, cohort, recipe, vocabulary):
    from multiphone_local_features import canonical_mapping
    indexed = {}
    for ri, row in enumerate(cohort['rows']):
        if not row['trainingEligible']:
            continue
        key = (row['clipId'], row['wordIndex'], row['phoneIndex'])
        require(key not in indexed, 'Duplicate cohort position')
        indexed[key] = (ri, row)
    chosen, excluded = [], []
    known = set(recipe['consonants']) | set(recipe['vowels'])
    for note in notes:
        raw = note['producedRaw']
        reason = None
        if note['targetPhone'] not in TARGETS:
            reason = 'unsupported-canonical-target'
        elif raw == '<unk>':
            reason = 'unknown-production'
        elif '*' in raw:
            reason = 'approximate-production'
        elif raw == '<DEL>':
            reason = 'deletion-description'
        elif len(raw.split()) != 1:
            reason = 'multi-phone-description'
        elif raw not in known:
            reason = 'unsupported-production-description'
        key = (note['clipId'], note['wordIndex'], note['phoneIndex'])
        if reason is None and key not in indexed:
            reason = 'absent-from-single-occurrence-export'
        if reason is not None:
            excluded.append(dict(note, exclusion=reason))
            continue
        ri, row = indexed[key]
        require(all(note[k] == row[k] for k in ('clipId', 'speakerId', 'age', 'wordIndex', 'phoneIndex', 'targetPhone')),
                'Cohort note identity differs')
        prefix = [note['precedingCanonicalPhone']] if note['precedingCanonicalPhone'] is not None else []
        canonical_tokens, canonical_ids, canonical_flags = canonical_mapping(prefix+[note['canonicalRaw']], vocabulary, recipe)
        noted_tokens, noted_ids, noted_flags = canonical_mapping(prefix+[raw], vocabulary, recipe)
        tokens, ids = [canonical_tokens[-1], noted_tokens[-1]], [canonical_ids[-1], noted_ids[-1]]
        flags = sorted(set(canonical_flags+noted_flags))
        if ids[0] == ids[1]:
            excluded.append(dict(note, exclusion='same-decoder-token'))
            continue
        chosen.append(dict(note, rowIndex=ri, rowId=row['id'], targetId=row['targetId'],
            canonicalToken=tokens[0], canonicalTokenId=ids[0], notedToken=tokens[1],
            notedTokenId=ids[1], mappingLimitations=flags))
    require(len(chosen)+len(excluded) == len(notes), 'Incomplete note accounting')
    return chosen, excluded


def score_note(note, artifact):
    import math
    clip, computed = artifact['clip'], artifact['computed']
    require(clip['id'] == note['clipId'] and clip['speakerId'] == note['speakerId'] and
            clip['canonicalPhones'][note['canonicalIndex']] == note['canonicalRaw'], 'Clip note identity differs')
    previous = clip['canonicalPhones'][note['canonicalIndex']-1] if note['canonicalIndex'] else None
    require(previous == note['precedingCanonicalPhone'], 'Preceding canonical phone differs')
    slots = [s for s in computed['slots'] if s['target']['rowIndex'] == note['rowIndex']]
    require(len(slots) == 1, 'Missing or duplicate exported slot')
    slot = slots[0]
    target = slot['target']
    require(all(target[k] == note[k] for k in ('rowIndex', 'rowId', 'targetId', 'targetPhone',
            'canonicalIndex', 'wordIndex', 'phoneIndex')) and target in clip['targetRows'], 'Exported slot differs')
    likelihood = slot['likelihoods']
    candidates, values = likelihood['candidateTokenIds'], likelihood['replacementLogLikelihoods']
    require(candidates == list(range(4, 392)) and len(values) == 388 and
            all(type(v) in (int, float) and math.isfinite(v) for v in values), 'Invalid replacement likelihoods')
    require(likelihood['position'] == note['canonicalIndex'] and
            likelihood['canonicalToken'] == note['canonicalTokenId'] and
            clip['mappedTokenIds'][note['canonicalIndex']] == note['canonicalTokenId'], 'Canonical token differs')
    canonical = likelihood['canonicalLogLikelihood']
    require(math.isfinite(canonical) and abs(canonical-computed['canonicalLogLikelihood']) <= TOLERANCE and
            abs(canonical-values[candidates.index(note['canonicalTokenId'])]) <= TOLERANCE, 'Canonical likelihood differs')
    require(note['notedTokenId'] in candidates, 'Noted token absent')
    observed = values[candidates.index(note['notedTokenId'])]
    margin = observed-canonical
    outcome = 'noted' if margin > TOLERANCE else 'canonical' if margin < -TOLERANCE else 'tie'
    rank, ties = 1+sum(v > observed for v in values), sum(v == observed for v in values)
    return dict(note, canonicalSequenceMappingLimitations=clip['mappingAmbiguities'],
                notedLogLikelihood=observed, canonicalLogLikelihood=canonical,
                notedMinusCanonical=margin, favored=outcome, strictRank=rank,
                exactTieCount=ties, uniqueMaximum=rank == 1 and ties == 1,
                replacementCandidates=388)


def summarize(rows):
    def cell(items):
        outcomes = Counter(r['favored'] for r in items)
        return dict(events=len(items), speakers=len({r['speakerId'] for r in items}),
            clips=len({r['clipId'] for r in items}),
            favored={k: outcomes[k] for k in ('noted', 'canonical', 'tie')},
            medianNotedMinusCanonical=statistics.median(r['notedMinusCanonical'] for r in items) if items else None,
            uniqueMaximum=sum(r['uniqueMaximum'] for r in items))
    result = {}
    for age_band in ('all', 'child6to12', 'olderThan12'):
        age_rows = [r for r in rows if age_band == 'all' or
                    (6 <= r['age'] <= 12 if age_band == 'child6to12' else r['age'] > 12)]
        result[age_band] = {}
        for context in ('all', 'oneNoteInUtterance', 'multipleNotesInUtterance'):
            selected = [r for r in age_rows if context == 'all' or
                        (r['notesInUtterance'] == 1 if context == 'oneNoteInUtterance' else r['notesInUtterance'] > 1)]
            result[age_band][context] = dict(total=cell(selected), byPhone={p: cell([r for r in selected
                if r['targetPhone'] == p]) for p in TARGETS})
    return result


def inputs():
    pins = {'export': binding(EXPORT, EXPORT_SHA)}
    export = read_bound(pins['export'])
    require(export['complete'] is True and export['authorPartition'] == 'train' and
            export['clips'] == 2495 and export['eligibleCohortRows'] == 14837, 'Unexpected completed export')
    for key in ('cohort', 'recipe', 'vocabulary'):
        pins[key] = export['inputBindings'][key]
    cohort, recipe, vocab = (read_bound(pins[k]) for k in ('cohort', 'recipe', 'vocabulary'))
    require(cohort['authorPartition'] == 'train', 'Author train required')
    for name in ('train/utt2spk', 'train/spk2age', 'resource/scores.json', 'README.md'):
        pins['metadata/'+name] = binding(METADATA/name, FILES[name][1])
    train = mapping(pinned_bytes(METADATA, 'train/utt2spk'), r'\d{9}', r'\d{4}')
    ages = mapping(pinned_bytes(METADATA, 'train/spk2age'), r'\d{4}', r'\d{1,3}')
    require(len(train) == 2500 and len(set(train.values())) == 125, 'Unexpected train population')
    aggregate = selected_json_objects(pinned_bytes(METADATA, 'resource/scores.json'), set(train))
    notes = derive_notes(train, ages, aggregate)
    chosen, excluded = choose_notes(notes, cohort, recipe, vocab)
    for clip_id in sorted({n['clipId'] for n in chosen}):
        require(clip_id in export['clipArtifacts'], 'Eligible note has no exported clip')
        pins['clip/'+clip_id] = export['clipArtifacts'][clip_id]
    for name in ('multiphone_note_likelihood.py', 'test_multiphone_note_likelihood.py',
                 'multiphone_sequence_preflight.py', 'multiphone_local_features.py',
                 'speechocean_audit.py', 'speechocean_r_label_audit.py'):
        pins['source/'+name] = binding(HERE/name)
    pins['protocol'] = binding(PROTOCOL)
    guard(pins)
    return chosen, excluded, pins


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh ignored destination required')
    chosen, excluded, pins = inputs()
    output.mkdir(mode=0o700)
    return write_new(output/'plan.json', dict(declaredAt=datetime.now(timezone.utc).isoformat(),
        selected=chosen, excluded=excluded, inputs=pins, tolerance=TOLERANCE, likelihoodsExamined=False))


def calculate(path, sha):
    plan = read_bound(dict(path=str(Path(path).resolve()), sha256=sha))
    chosen, excluded, pins = inputs()
    require(plan['selected'] == chosen and plan['excluded'] == excluded and plan['inputs'] == pins and
            plan['tolerance'] == TOLERANCE and plan['likelihoodsExamined'] is False, 'Declaration differs')
    clips = {clip: read_bound(pins['clip/'+clip]) for clip in sorted({r['clipId'] for r in chosen})}
    rows = [score_note(note, clips[note['clipId']]) for note in chosen]
    guard(pins)
    return dict(complete=True, plan=dict(path=str(Path(path).resolve()), sha256=sha), inputs=pins,
        rows=rows, excluded=excluded, summary=summarize(rows),
        exclusionCounts=dict(sorted(Counter(r['exclusion'] for r in excluded).items())),
        notes=len(chosen)+len(excluded), compared=len(rows),
        authorTestObjectsDecoded=False, audioOpened=False, modelInferencePerformed=False,
        trainingPerformed=False, learnerFeedbackEligible=False, clinicalUseEligible=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare', 'run', 'verify'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        require(args.output is not None, 'Output required')
        result = declare(args.output)
    else:
        require(args.plan is not None and args.plan_sha256 is not None, 'Plan and SHA required')
        path = args.plan.resolve().parent/'report.json'
        if args.command == 'run':
            require(not path.exists(), 'No overwrite')
            result = write_new(path, calculate(args.plan, args.plan_sha256))
        else:
            saved = json.loads(path.read_text())
            require(saved == calculate(args.plan, args.plan_sha256), 'Saved diagnostic differs')
            result = dict(verified=True, report=binding(path))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
