"""All supported canonical positions from author-train; no inference or fitting."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import wave

import numpy as np

from multiphone_data import FALSE_FLAGS, SOURCE_FILES, TARGETS as LEGACY_TARGETS
from multiphone_data import json_sha, require, sha256_file
from speechocean_audit import ANNOTATED_PHONE, FILES, PHONE, mapping, pinned_bytes
from speechocean_r_label_audit import selected_json_objects
from speechocean_r_annotation_sample import AUDIO, ARCHIVE, ARCHIVE_SHA256, METADATA, verify_selected_wavs

HERE = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
PROTOCOL = HERE / '../../docs/model/multiphone-position-data-protocol.md'
TARGETS = LEGACY_TARGETS[:-1]
GROUPS = ('outerFit', 'outerHoldout', 'innerFit', 'innerValidation')
PINS = {
    'legacyCohort': (BASE/'cohort.json', '33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805'),
    'legacySplits': (BASE/'splits.json', 'b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf'),
}
FLAGS = dict(FALSE_FLAGS, modelInferencePerformed=False, trainingPerformed=False,
             promotedModel=False, authorTestAudioOpened=False)


def binding(path, expected=None):
    path = Path(path).resolve()
    digest = sha256_file(path)
    require(expected is None or digest == expected, 'Pinned input differs: '+str(path))
    return dict(path=str(path), sha256=digest)


def read_bound(pin):
    binding(pin['path'], pin['sha256'])
    return json.loads(Path(pin['path']).read_text())


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()


def write_new(path, value):
    with Path(path).open('x') as stream:
        Path(path).chmod(0o600)
        stream.write(json_bytes(value).decode())
    return binding(path)


def runtime():
    return dict(python=sys.version, executable=binding(sys.executable), numpy=np.__version__,
                numpySource=binding(np.__file__), platform=sys.platform, byteorder=sys.byteorder)


def derive_positions(clip_id, speaker_id, age, aggregate, detailed):
    """Align all five raters by position, ignoring bracketed insertion annotations."""
    require(type(age) is int and (1 <= age <= 15 or 19 <= age < 120), 'Invalid age band')
    require(aggregate.get('text') == detailed.get('text') and
            isinstance(aggregate.get('text'), str) and bool(aggregate['text']) and
            isinstance(aggregate.get('words'), list) and bool(aggregate['words']) and
            isinstance(detailed.get('words'), list) and
            len(aggregate['words']) == len(detailed['words']), 'Utterance structure differs')
    rows, offset = [], 0
    for wi, (word, detail) in enumerate(zip(aggregate['words'], detailed['words'], strict=True)):
        phones = word.get('phones')
        require(isinstance(phones, list) and bool(phones) and
                all(isinstance(p, str) and PHONE.fullmatch(p) for p in phones) and
                isinstance(word.get('text'), str) and bool(word['text']) and
                word['text'] == detail.get('text') and detail.get('ref-phones') == ' '.join(phones) and
                isinstance(word.get('phones-accuracy'), list) and
                len(word['phones-accuracy']) == len(phones) and
                isinstance(detail.get('phones'), list) and len(detail['phones']) == 5,
                'Canonical word or five-rater structure differs')
        raters = []
        for annotation in detail['phones']:
            require(isinstance(annotation, str) and bool(annotation), 'Invalid rater annotation')
            tokens = annotation.split()
            require(all(ANNOTATED_PHONE.fullmatch(t) for t in tokens), 'Malformed rater annotation')
            observed = [t for t in tokens if not t.startswith('[')]
            require([t.strip('{}()') for t in observed] == phones, 'Rater sequence differs')
            raters.append([0 if t.startswith('(') else 1 if t.startswith('{') else 2 for t in observed])
        notes = word.get('mispronunciations', [])
        require(isinstance(notes, list), 'Invalid sparse notes')
        indexed = {}
        for note in notes:
            require(isinstance(note, dict) and set(note) == {'index', 'canonical-phone', 'pronounced-phone'},
                    'Invalid sparse note fields')
            pi = note['index']
            require(type(pi) is int and 0 <= pi < len(phones) and pi not in indexed and
                    note['canonical-phone'] == re.sub(r'[012]$', '', phones[pi]) and
                    isinstance(note['pronounced-phone'], str) and bool(note['pronounced-phone']),
                    'Invalid or duplicate sparse note position')
            indexed[pi] = note
        for pi, raw in enumerate(phones):
            five = [r[pi] for r in raters]
            score = word['phones-accuracy'][pi]
            require(type(score) in (int, float) and 0 <= score <= 2 and abs(sum(five)/5-score) <= 1e-9,
                    'Published aggregate differs from five raters')
            phone = re.sub(r'[012]$', '', raw)
            if phone in TARGETS:
                rows.append(dict(id=f'{clip_id}:{wi}:{pi}', clipId=clip_id, speakerId=speaker_id,
                    age=age, ageBand='child' if age <= 15 else 'adult', targetId=TARGETS.index(phone),
                    targetPhone=phone, canonicalRaw=raw, targetWord=word['text'], wordIndex=wi,
                    phoneIndex=pi, canonicalIndex=offset+pi, raterScores=five,
                    raterCounts=[five.count(i) for i in range(3)], meanRating=score,
                    humanNoteRaw=deepcopy(indexed.get(pi)), trainingEligible=True))
        offset += len(phones)
    return rows


def reconcile_legacy(rows, legacy):
    """Retain original indices (including gaps from unsupported ZH rows)."""
    indexed = {row['id']: row for row in rows}
    require(len(indexed) == len(rows), 'Duplicate position ID')
    for row in rows:
        row.update(legacyRowIndex=None, legacyRowId=None)
    seen = set()
    keys = ('clipId', 'speakerId', 'age', 'ageBand', 'targetId', 'targetPhone',
            'targetWord', 'wordIndex', 'phoneIndex', 'raterCounts', 'trainingEligible')
    for ri, old in enumerate(legacy['rows']):
        if not old['trainingEligible']:
            continue
        identity = f"{old['clipId']}:{old['wordIndex']}:{old['phoneIndex']}"
        require(identity in indexed and identity not in seen, 'Missing or duplicate legacy position')
        row = indexed[identity]
        require(all(row[k] == old[k] for k in keys), 'Legacy label or identity differs')
        require(old['id'] == f"{old['clipId']}:{old['targetPhone']}", 'Legacy row ID differs')
        row.update(legacyRowIndex=ri, legacyRowId=old['id'])
        seen.add(identity)
    return len(seen)


def summarize(rows):
    def counts(items):
        return dict(rows=len(items), clips=len({r['clipId'] for r in items}),
            speakers=len({r['speakerId'] for r in items}),
            raterCounts=[sum(r['raterCounts'][i] for r in items) for i in range(3)],
            notedPositions=sum(r['humanNoteRaw'] is not None for r in items))
    return {age: dict(total=counts(chosen), byPhone={p: counts([r for r in chosen if r['targetPhone'] == p])
            for p in TARGETS}) for age, chosen in (
                ('all', rows), ('child6to12', [r for r in rows if 6 <= r['age'] <= 12]))}


def build_splits(cohort, legacy_splits):
    """Copy declared speaker sets; rebuild only clip/position indexes and support."""
    rows, clips = cohort['rows'], cohort['clips']
    require(cohort['authorPartition'] == legacy_splits['authorPartition'] == 'train', 'Train partition required')
    require(len({c['id'] for c in clips}) == len(clips) and
            len({r['id'] for r in rows}) == len(rows) and
            len({(r['clipId'], r['canonicalIndex']) for r in rows}) == len(rows), 'Duplicate clip or position')
    expected_positions = {f"{c['id']}:{wi}:{pi}" for c in clips
        for wi, word in enumerate(c['words']) for pi, phone in enumerate(word['phones'])
        if re.sub(r'[012]$', '', phone) in TARGETS}
    require({r['id'] for r in rows} == expected_positions, 'Missing or extra supported position')
    speakers = {c['speakerId'] for c in clips}
    assignments = legacy_splits['speakerAssignments']
    require(set(assignments) == speakers, 'Speaker membership differs')
    for row in rows:
        ci = row['clipIndex']
        require(type(ci) is int and 0 <= ci < len(clips), 'Invalid clip index')
        clip = clips[ci]
        wi, pi, position = row['wordIndex'], row['phoneIndex'], row['canonicalIndex']
        require(type(wi) is int and 0 <= wi < len(clip['words']) and type(pi) is int and
                0 <= pi < len(clip['words'][wi]['phones']) and
                position == sum(len(w['phones']) for w in clip['words'][:wi])+pi and
                row['id'] == f"{row['clipId']}:{wi}:{pi}" and
                row['clipId'] == clip['id'] and row['speakerId'] == clip['speakerId'] and
                clip['canonicalPhones'][position] == clip['words'][wi]['phones'][pi] == row['canonicalRaw'] and
                row['targetWord'] == clip['words'][wi]['text'] and
                row['age'] == clip['age'] and row['ageBand'] == clip['ageBand'] and
                row['targetPhone'] == re.sub(r'[012]$', '', row['canonicalRaw']) and
                row['targetPhone'] in TARGETS and row['targetId'] == TARGETS.index(row['targetPhone']) and
                row['trainingEligible'] is True and len(row['raterCounts']) == 3 and
                all(type(v) is int and v >= 0 for v in row['raterCounts']) and sum(row['raterCounts']) == 5,
                'Position identity or ratings differ')
    partitions = []
    fold_ids = [part['fold'] for part in legacy_splits['folds']]
    require(fold_ids == list(range(len(fold_ids))) and len(fold_ids) >= 2 and
            set(assignments.values()) == set(fold_ids), 'Invalid legacy fold identities')
    for original in legacy_splits['folds']:
        fold = original['fold']
        groups = {name: set(original[name+'Speakers']) for name in GROUPS}
        require(all(len(groups[n]) == len(original[n+'Speakers']) for n in GROUPS) and
                groups['outerHoldout'] == {s for s in speakers if assignments[s] == fold} and
                groups['outerFit'] == speakers-groups['outerHoldout'] and
                groups['innerFit'].isdisjoint(groups['innerValidation']) and
                groups['innerFit'] | groups['innerValidation'] == groups['outerFit'] and
                all(groups.values()), 'Legacy speaker partitions differ')
        part = dict(fold=fold, lexicalOverlap={})
        for name, group in groups.items():
            part[name+'Speakers'] = deepcopy(original[name+'Speakers'])
            part[name+'Clips'] = [i for i, c in enumerate(clips) if c['speakerId'] in group]
            part[name+'Rows'] = [i for i, r in enumerate(rows) if r['speakerId'] in group]
            part[name+'TargetRaterCounts'] = {p: [sum(rows[i]['raterCounts'][score]
                for i in part[name+'Rows'] if rows[i]['targetPhone'] == p) for score in range(3)] for p in TARGETS}
        for fit, held, scope in (('outerFit', 'outerHoldout', 'outer'), ('innerFit', 'innerValidation', 'inner')):
            require({clips[i]['audioSha256'] for i in part[fit+'Clips']}.isdisjoint(
                    {clips[i]['audioSha256'] for i in part[held+'Clips']}), 'Duplicate WAV crosses speaker split')
            part['lexicalOverlap'][scope] = dict(exactPromptTexts=len(
                {clips[i]['text'] for i in part[fit+'Clips']} & {clips[i]['text'] for i in part[held+'Clips']}),
                targetWordTypes=len({rows[i]['targetWord'] for i in part[fit+'Rows']} &
                                    {rows[i]['targetWord'] for i in part[held+'Rows']}))
        partitions.append(part)
    require(sorted(i for p in partitions for i in p['outerHoldoutRows']) == list(range(len(rows))),
            'Outer holdout position coverage differs')
    return dict(schemaVersion=1, authorPartition='train', speakerAssignments=deepcopy(assignments),
        folds=partitions, cohortCanonicalSha256=json_sha(cohort), legacySplitsSha256=PINS['legacySplits'][1],
        splitSeed=legacy_splits['splitSeed'], speakerMembershipReselected=False,
        finalEvaluationStatus='Reused author-training development folds; not independent final validation', **FLAGS)


def inputs():
    pins = {name: binding(path, sha) for name, (path, sha) in PINS.items()}
    for name in SOURCE_FILES:
        pins['metadata/'+name] = binding(METADATA/name, FILES[name][1])
    pins['archive'] = binding(ARCHIVE, ARCHIVE_SHA256)
    pins['wavMap'] = binding(AUDIO/'train/wav.scp')
    train = mapping(pinned_bytes(METADATA, 'train/utt2spk'), r'\d{9}', r'\d{4}')
    require(len(train) == 2500 and len(set(train.values())) == 125, 'Train population differs')
    for clip, speaker in sorted(train.items()):
        path = AUDIO/f'WAVE/SPEAKER{speaker}/{clip}.WAV'
        require(path.resolve().is_relative_to((AUDIO/'WAVE').resolve()), 'Audio path escapes corpus')
        pins['audio/'+clip] = binding(path)
    for name in ('multiphone_position_data.py', 'test_multiphone_position_data.py', 'multiphone_data.py',
                 'speechocean_audit.py', 'speechocean_r_label_audit.py', 'speechocean_r_annotation_sample.py'):
        pins['source/'+name] = binding(HERE/name)
    pins['protocol'] = binding(PROTOCOL)
    return pins


def build_cohort(pins):
    legacy = read_bound(pins['legacyCohort'])
    require(legacy['authorPartition'] == 'train' and len(legacy['clips']) == 2495, 'Legacy cohort differs')
    train = mapping(pinned_bytes(METADATA, 'train/utt2spk'), r'\d{9}', r'\d{4}')
    ages = mapping(pinned_bytes(METADATA, 'train/spk2age'), r'\d{4}', r'\d{1,3}')
    require(len(train) == 2500 and len(set(train.values())) == 125 and set(ages) == set(train.values()),
            'Train membership differs')
    aggregate = selected_json_objects(pinned_bytes(METADATA, 'resource/scores.json'), set(train))
    detailed = selected_json_objects(pinned_bytes(METADATA, 'resource/scores-detail.json'), set(train))
    require(set(aggregate) == set(detailed) == set(train), 'Missing author-training metadata')
    rows = [r for clip in sorted(train) for r in derive_positions(clip, train[clip], int(ages[train[clip]]),
                                                               aggregate[clip], detailed[clip])]
    retained = reconcile_legacy(rows, legacy)
    require(len(rows) == 28227 and retained == 14837 and len(rows)-retained == 13390,
            'All-position or legacy cohort count differs')
    source = [dict(sourceId=clip, speakerId=train[clip]) for clip in sorted(train)]
    verify_selected_wavs(source)
    old_clips = {c['id']: c for c in legacy['clips']}
    require(len(old_clips) == len(legacy['clips']) and set(old_clips) <= set(train), 'Legacy clip membership differs')
    clips = []
    for item in source:
        clip, speaker = item['sourceId'], item['speakerId']
        path, digest = item['wavPath'], item['wavSha256']
        require(binding(path) == pins['audio/'+clip] and digest == pins['audio/'+clip]['sha256'],
                'Audio differs from declaration')
        with wave.open(path, 'rb') as wav:
            count = wav.getnframes()
            require((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) ==
                    (1, 2, 16000, 'NONE') and 1600 <= count <= 480000, 'Audio format or sample bounds differ')
            samples = np.frombuffer(wav.readframes(count), dtype='<i2').astype(np.float64)/32768.0
        require(len(samples) == count and np.isfinite(samples).all(), 'Truncated WAV')
        age = int(ages[speaker])
        phones = [p for w in aggregate[clip]['words'] for p in w['phones']]
        fields = dict(id=clip, speakerId=speaker, audioPath=path, audioSha256=digest, age=age,
            ageBand='child' if age <= 15 else 'adult', sampleCount=count, durationSeconds=count/16000,
            rms=float(np.sqrt(np.mean(samples**2))), peak=float(np.max(np.abs(samples))),
            text=aggregate[clip]['text'], canonicalPhoneCount=len(phones))
        if clip in old_clips:
            require(fields == old_clips[clip], 'Legacy audio fields differ')
            fields = deepcopy(old_clips[clip])
        clips.append(dict(fields, canonicalPhones=phones, words=deepcopy(aggregate[clip]['words'])))
    indices = {c['id']: i for i, c in enumerate(clips)}
    for row in rows:
        row['clipIndex'] = indices[row['clipId']]
    require({r['clipId'] for r in rows} == set(train), 'A training clip has no supported positions')
    summary = summarize(rows)
    require(summary['child6to12']['total']['rows'] == 9891, 'Child position count differs')
    return dict(schemaVersion=1, experiment='multiphone-position-data-v1', authorPartition='train',
        targetPhones=list(TARGETS), eligibleTargetIds=list(range(len(TARGETS))), clips=clips, rows=rows,
        labelSummary=dict(eligibleRows=len(rows), legacyEligibleRows=retained, addedRows=len(rows)-retained,
            clips=len(clips), addedClips=len(clips)-len(old_clips), speakers=len(ages)), summary=summary,
        provenance=dict(inputBindings=pins, rowOrder='clip ID, word index, within-word phone index',
            sourceArchiveSha256=ARCHIVE_SHA256, legacyCohortSha256=PINS['legacyCohort'][1]),
        limitations=['Subjective canonical-position ratings; no verified production transcription or timing.',
            'Missing sparse notes are unknown, never correct-phone labels.',
            'Same speakers and reused development folds; no new independent evaluation cohort.',
            'ZH remains unsupported and is not included in this position cohort.'], **FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh ignored output required')
    output.mkdir(parents=True, mode=0o700)
    try:
        pins = inputs()
        return write_new(output/'plan.json', dict(declaredAt=datetime.now(timezone.utc).isoformat(),
            inputBindings=pins, runtime=runtime(), expectedRows=28227, expectedClips=2500,
            targetPhones=list(TARGETS), outputDirectory=str(output), cohortCreated=False, **FLAGS))
    except Exception as error:
        write_new(output/'setup-failure.json', dict(errorType=type(error).__name__, message=str(error)))
        raise


def calculate(plan_path, sha):
    plan_path = Path(plan_path).resolve()
    require(plan_path.is_relative_to(HERE/'outputs'), 'Plan outside ignored outputs')
    plan = read_bound(dict(path=str(plan_path), sha256=sha))
    pins = inputs()
    require(plan['inputBindings'] == pins and plan['runtime'] == runtime() and plan['expectedRows'] == 28227 and
            plan['expectedClips'] == 2500 and plan['targetPhones'] == list(TARGETS) and
            plan['outputDirectory'] == str(plan_path.parent) and plan['cohortCreated'] is False and
            all(plan[k] is False for k in FLAGS), 'Declaration differs')
    cohort = build_cohort(pins)
    splits = build_splits(cohort, read_bound(pins['legacySplits']))
    require(inputs() == pins and runtime() == plan['runtime'], 'Inputs changed during build')
    return cohort, splits


def run(plan_path, sha, verify=False):
    directory = Path(plan_path).resolve().parent
    names = ('cohort.json', 'splits.json', 'report.json')
    if not verify:
        require(all(not (directory/name).exists() for name in names) and not (directory/'failure.json').exists(),
                'No overwrite or retry of failed output')
    try:
        cohort, splits = calculate(plan_path, sha)
        if verify:
            report = json.loads((directory/'report.json').read_text())
            require(read_bound(report['outputs']['cohort']) == cohort and
                    read_bound(report['outputs']['splits']) == splits and
                    (directory/'cohort.json').read_bytes() == json_bytes(cohort) and
                    (directory/'splits.json').read_bytes() == json_bytes(splits),
                    'Saved artifacts differ from offline rebuild')
            outputs = {name: binding(directory/(name+'.json')) for name in ('cohort', 'splits')}
        else:
            outputs = {name: write_new(directory/(name+'.json'), value)
                       for name, value in (('cohort', cohort), ('splits', splits))}
        expected = dict(complete=True, plan=binding(plan_path, sha), outputs=outputs,
            inputBindings=cohort['provenance']['inputBindings'], runtime=runtime(),
            labelSummary=cohort['labelSummary'], summary=cohort['summary'],
            legacySpeakerMembershipExact=True, archiveVerifiedTrainWavs=2500, **FLAGS)
        if verify:
            require(report == expected and (directory/'report.json').read_bytes() == json_bytes(expected),
                    'Saved report differs')
            return dict(verified=True, report=binding(directory/'report.json'))
        return write_new(directory/'report.json', expected)
    except Exception as error:
        if not verify and not (directory/'failure.json').exists():
            write_new(directory/'failure.json', dict(errorType=type(error).__name__, message=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'verify'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        require(args.output is not None, 'Output required')
        result = declare(args.output)
    else:
        require(args.plan is not None and args.plan_sha256 is not None, 'Plan and SHA required')
        result = run(args.plan, args.plan_sha256, args.command == 'verify')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
