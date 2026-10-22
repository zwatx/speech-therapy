"""Canonical-word revision of the frozen lexical feasibility inventory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lexical_feasibility import study as prior

files, require, read = prior.files, prior.require, prior.read
HERE = prior.HERE
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-lexical-canonical-protocol.md'
CANONICAL = HERE / 'outputs/multiphone-20260927/position-data-v1/cohort.json'
CANONICAL_SHA = '3b70d6822cf02e3d4be50274b99853784a454d8fb80f939ade3940cb7b2a6864'
FAILED_PLAN = HERE / 'outputs/multiphone-20260927/lexical-feasibility-v1/plan.json'
FAILED_PLAN_SHA = '206bd607bb5e553058be65afa9c04088105c71074bd54cad0d0c8a2c5f6fb1f5'


def canonical_view(cohort, annotation):
    require(cohort['authorPartition'] == annotation['authorPartition'] == 'train'
            and annotation['authorTestObjectsDecoded'] is False, 'Train-only canonical annotation required')
    clips = {c['id']: c for c in annotation['clips']}
    require(len(clips) == len(annotation['clips']), 'Duplicate canonical clip')
    projection, differences, canonical_tokens = [], [], {}
    for clip in cohort['clips']:
        require(clip['id'] in clips, 'Missing canonical clip')
        full = clips[clip['id']]
        require(all(clip[k] == full[k] for k in ('id', 'text', 'speakerId', 'age', 'audioSha256', 'canonicalPhoneCount')),
                'Canonical/original clip identity differs')
        require(isinstance(full['words'], list) and full['words'], 'Missing complete canonical word list')
        words = []
        for word in full['words']:
            text = word['text']
            require(isinstance(text, str) and text and text.upper().split() == [text.upper()], 'Malformed canonical word token')
            words.append(text.upper())
        require([p for word in full['words'] for p in word['phones']] == full['canonicalPhones']
                and len(full['canonicalPhones']) == clip['canonicalPhoneCount'], 'Canonical word/phone coverage differs')
        canonical_tokens[clip['id']] = words
        original = clip['text'].upper().split()
        if original != words:
            differences.append(dict(clipId=clip['id'], rawTranscript=clip['text'], rawTokens=original, canonicalTokens=words))
        projection.append(dict(clip, text=' '.join(words)))
    for row in cohort['rows']:
        full = clips[row['clipId']]
        wi, pi = row['wordIndex'], row['phoneIndex']
        require(type(wi) is int and 0 <= wi < len(full['words']) and type(pi) is int
                and 0 <= pi < len(full['words'][wi]['phones'])
                and row['targetWord'].upper() == full['words'][wi]['text'].upper()
                and row['targetPhone'] == full['words'][wi]['phones'][pi], 'Canonical target occurrence differs')
    legacy = {}
    for row in annotation['rows']:
        if row['legacyRowIndex'] is not None:
            i = row['legacyRowIndex']
            require(type(i) is int and i not in legacy and 0 <= i < len(cohort['rows']), 'Duplicate or invalid legacy row')
            old = cohort['rows'][i]
            require(old['trainingEligible'] is True and row['legacyRowId'] == old['id']
                    and all(row[k] == old[k] for k in ('clipId', 'speakerId', 'age', 'wordIndex', 'phoneIndex', 'targetPhone', 'targetWord', 'raterCounts')),
                    'Canonical/legacy row or vote identity differs')
            legacy[i] = row['id']
    require(sorted(legacy) == [i for i, r in enumerate(cohort['rows']) if r['trainingEligible']], 'Canonical legacy coverage differs')
    return dict(cohort, clips=projection), dict(canonicalTokens=canonical_tokens, rawTranscriptDifferences=differences,
        originalClipCount=len(projection), canonicalSourceClipCount=len(clips), legacyRowsChecked=len(legacy),
        ignoredAdditionalClips=sorted(set(clips) - {c['id'] for c in projection}), annotationTokenBasis=True)


def plan_value():
    value = prior.plan_value()
    value['inputs']['failedRawTranscriptPlan'] = files.binding(FAILED_PLAN, FAILED_PLAN_SHA)
    value['inputs']['failedRawTranscriptReceipt'] = files.binding(FAILED_PLAN.parent / 'failure.json')
    value['inputs']['canonicalWords'] = files.binding(CANONICAL, CANONICAL_SHA)
    value['inputs']['canonicalProtocol'] = files.binding(PROTOCOL)
    for path in sorted(DIRECTORY.glob('*.py')):
        value['inputs']['canonicalSource/' + str(path)] = files.binding(path)
    value['tokenBasis'] = 'Complete ordered canonical annotation words; raw transcript retained separately'
    return value


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
    value = plan_value()
    output.mkdir(parents=True, mode=0o700)
    files.write_json(output / 'plan.json', value)
    return files.binding(output / 'plan.json')


def run(path, sha, verify=False):
    pin = files.binding(path, sha)
    plan = read(pin)
    require(plan == plan_value(), 'Canonical lexical declaration differs')
    output = Path(path).resolve().parent
    if not verify:
        files.write_json(output / 'started.json', dict(plan=pin))
    try:
        cohort, projection = canonical_view(read(plan['inputs']['cohort']), read(plan['inputs']['canonicalWords']))
        result = dict(complete=True, plan=pin, canonicalProjection=projection,
                      **prior.calculate(cohort, read(plan['inputs']['splits'])))
        files.guard(plan['inputs'])
        if verify:
            report_pin = files.binding(output / 'report.json')
            require(read(report_pin) == result, 'Canonical lexical reconstruction differs')
            return dict(verified=True, report=report_pin, **prior.FLAGS)
        files.write_json(output / 'report.json', result)
        return files.binding(output / 'report.json')
    except Exception as error:
        if not verify:
            files.write_json(output / 'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'verify'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    print(json.dumps(declare(args.output) if args.command == 'declare' else run(args.plan, args.plan_sha256, args.command == 'verify')), flush=True)
