"""Declared support inventory for all occurrences under frozen lexical exclusions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from lexical_canonical import study as canonical
import multiphone_position_data as position_data
import multiphone_position_phonetic as features

prior = canonical.prior
files, read, require = prior.files, prior.read, prior.require
HERE = prior.HERE
BASE = HERE / 'outputs/multiphone-20260927'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-lexical-expansion-protocol.md'
OLD_PLAN = 'c4484f79500bcba049a5b192aa8ec3935e01b44e48dbe99526c9b9c7ab097e8e'
OLD_REPORT = '1cb2953ef78cfba10f004598c84f4f1f8a43c66881dee36d5daf506880a731c4'
FEATURE_PLAN = 'b3f1884a54b1fa25777eb9578155b9923eed9ce61ff1762e05301f6211c7f29c'
FEATURE_REPORT = '80a0dd901f026deebd74ea9fb66d234f14e80ca44d03ab8c0816e0d8494341be'
PARTITIONS = ('innerFit', 'innerValidation', 'selection', 'outerFit', 'outer')
FLAGS = dict(prior.FLAGS, featureArraysRead=True, audioRead=True, audioBytesHashed=True,
             audioDecoded=False, newFeatureExtractionPerformed=False)


def canonical_projection(cohort):
    """Include every clip; punctuation in raw transcripts cannot change grouping."""
    require(cohort['authorPartition'] == 'train' and cohort['authorTestObjectsDecoded'] is False,
            'Train-only canonical annotation required')
    clips, tokens = [], {}
    for clip in cohort['clips']:
        require(clip['id'] not in tokens and clip['words'], 'Duplicate or empty canonical clip')
        words = [word['text'].upper() for word in clip['words']]
        for word in words:
            prior.word_group(word)
        require([p for word in clip['words'] for p in word['phones']] == clip['canonicalPhones']
                and len(clip['canonicalPhones']) == clip['canonicalPhoneCount'], 'Incomplete canonical utterance')
        tokens[clip['id']] = words
        clips.append(dict(clip, text=' '.join(words)))
    return dict(cohort, clips=clips), tokens


def legacy_map(original, expanded):
    result = {}
    fields = ('clipId', 'speakerId', 'age', 'wordIndex', 'phoneIndex', 'targetPhone', 'targetWord', 'raterCounts')
    for i, row in enumerate(expanded):
        old = row['legacyRowIndex']
        if old is None:
            require(row['legacyRowId'] is None, 'Added row has a legacy identity')
            continue
        require(type(old) is int and 0 <= old < len(original) and old not in result,
                'Invalid or duplicate legacy row index')
        source = original[old]
        require(source['trainingEligible'] is True and source['id'] == row['legacyRowId']
                and all(source[k] == row[k] for k in fields), 'Original row or votes changed')
        result[old] = i
    require(sorted(result) == [i for i, r in enumerate(original) if r['trainingEligible']], 'Incomplete legacy coverage')
    return result


def strata(rows, indices):
    original = [i for i in indices if rows[i]['legacyRowIndex'] is not None]
    added = [i for i in indices if rows[i]['legacyRowIndex'] is None]
    require(len(original) + len(added) == len(indices), 'Occurrence accounting differs')
    return {name: dict(rowIndices=ids, support=prior.support_views(rows, ids))
            for name, ids in (('original', original), ('added', added), ('all', indices))}


def check_old_partition(old, new, mapping):
    inverse = {value: key for key, value in mapping.items()}
    for key in ('baseRows', 'retainedRows', 'excludedRows'):
        joined = [inverse[i] for i in new[key] if i in inverse]
        require(len(joined) == len(set(joined)) and sorted(joined) == sorted(old[key]),
                'Original lexical partition membership changed')


def collect_pins(value, prefix, pins):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            pins[prefix] = dict(path=value['path'], sha256=value['sha256'])
        else:
            for key, item in value.items():
                collect_pins(item, prefix + '/' + key, pins)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            collect_pins(item, prefix + '/' + str(i), pins)


def inputs():
    pins = dict(oldPlan=files.binding(BASE/'lexical-canonical-v1/plan.json', OLD_PLAN),
                oldReport=files.binding(BASE/'lexical-canonical-v1/report.json', OLD_REPORT),
                featurePlan=files.binding(BASE/'position-phonetic-v1/plan.json', FEATURE_PLAN),
                featureReport=files.binding(BASE/'position-phonetic-v1/report.json', FEATURE_REPORT),
                protocol=files.binding(PROTOCOL), python=files.binding(sys.executable))
    old_plan = read(pins['oldPlan'])
    require(old_plan == canonical.plan_value(), 'Original lexical declaration changed')
    feature_plan = read(pins['featurePlan'])
    report = read(pins['featureReport'])
    require(report['complete'] is True and report['plan'] == pins['featurePlan']
            and report['inputs'] == feature_plan['inputs'], 'Incomplete or mismatched feature lineage')
    for name, value in (('old', old_plan), ('feature', report), ('featurePlan', feature_plan)):
        collect_pins(value, 'upstream/' + name, pins)
    geometry = read(report['inputs']['geometry'])
    data = read(report['inputs']['data'])
    collect_pins(geometry, 'upstream/geometry', pins)
    collect_pins(data, 'upstream/data', pins)
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['source/' + path.name] = files.binding(path)
    files.guard(pins)
    return pins


def plan_value():
    return dict(inputs=inputs(), seed=prior.SEED, regimes=list(prior.REGIMES),
                speakerFolds=list(range(5)), wordGroups=list(range(5)),
                partitions=list(PARTITIONS), strata=['original', 'added', 'all'],
                tokenBasis='Every complete ordered canonical utterance; unchanged word hash',
                runtime=features.runtime(), **FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(HERE/'outputs'), 'Fresh ignored output required')
    plan = plan_value()
    output.mkdir(mode=0o700)
    files.write_json(output/'plan.json', plan)
    return files.binding(output/'plan.json')


def feature_parity(report, expanded, mapping):
    require(report['rowIds'] == [r['id'] for r in expanded], 'Expanded feature row order differs')
    original_report = read(report['inputs']['old/headInput/report'])
    positions = {r['rowIndex']: i for i, r in enumerate(original_report['rows'])}
    require(len(positions) == len(original_report['rows']) and set(positions) == set(mapping), 'Original feature coverage differs')
    target = features.checked_array(report['matrices']['target'], (len(expanded), 1024))
    combined = features.checked_array(report['matrices']['combined'], (len(expanded), 1037))
    scalars = features.checked_array(report['inputs']['scalars'], (len(expanded), 13))
    old_target = features.checked_array(report['inputs']['old/headInput/target'], (len(mapping), 1024))
    old_scalars = features.checked_array(report['inputs']['old/headInput/scalars'], (len(mapping), 13))
    old_ids = sorted(mapping)
    ii, jj = [mapping[i] for i in old_ids], [positions[i] for i in old_ids]
    require(np.array_equal(target, combined[:, :1024]) and np.array_equal(scalars, combined[:, 1024:]),
            'Expanded feature concatenation differs')
    require(np.array_equal(target[ii], old_target[jj]) and np.array_equal(scalars[ii], old_scalars[jj]),
            'Original feature vectors or scalars differ')
    return dict(originalRows=len(mapping), expandedRows=len(expanded),
                targetDimensions=1024, scalarDimensions=13, exact=True)


def calculate(plan):
    pins = plan['inputs']
    original_plan = read(pins['oldPlan'])
    old = read(original_plan['inputs']['cohort'])
    old_splits = read(original_plan['inputs']['splits'])
    feature_report = read(pins['featureReport'])
    expanded = read(feature_report['inputs']['cohort'])
    splits = read(feature_report['inputs']['splits'])
    require(splits == position_data.build_splits(expanded, old_splits), 'Expanded speaker-role reconstruction differs')
    projected_old, projection = canonical.canonical_view(old, expanded)
    previous = read(pins['oldReport'])
    require(previous == dict(complete=True, plan=pins['oldPlan'], canonicalProjection=projection,
                             **prior.calculate(projected_old, old_splits)), 'Original lexical inventory reconstruction differs')
    mapping = legacy_map(old['rows'], expanded['rows'])
    projected, tokens = canonical_projection(expanded)
    inventory = prior.calculate(projected, splits)
    require(all(inventory['wordGroups'][w] == group for w, group in previous['wordGroups'].items()), 'Original word groups changed')
    # Revalidate every saved unit and the matrices, with extraction disabled.
    feature_check = features.execute(pins['featurePlan']['path'], pins['featurePlan']['sha256'], False)
    require(feature_check['report'] == pins['featureReport'], 'Feature reconstruction differs')
    parity = feature_parity(feature_report, expanded['rows'], mapping)
    for regime in prior.REGIMES:
        cells, old_cells = inventory['models'][regime]['cells'], previous['models'][regime]['cells']
        require([(c['speakerFold'], c['wordGroup']) for c in cells] == [(s, w) for s in range(5) for w in range(5)],
                'Incomplete crossed inventory')
        for cell, old_cell in zip(cells, old_cells, strict=True):
            for name in PARTITIONS:
                part = cell['partitions'][name]
                check_old_partition(old_cell['partitions'][name], part, mapping)
                part['retainedByOrigin'] = strata(expanded['rows'], part['retainedRows'])
                part['excludedByOrigin'] = strata(expanded['rows'], part['excludedRows'])
        for value in inventory['models'][regime]['retainedUnions'].values():
            value['byOrigin'] = strata(expanded['rows'], value['rowIndices'])
    extra = []
    for clip in expanded['clips']:
        if clip['id'] not in projection['ignoredAdditionalClips']:
            continue
        extra.append(dict(clipId=clip['id'], speakerId=clip['speakerId'], age=clip['age'],
            canonicalTokens=tokens[clip['id']], wordGroups=[inventory['wordGroups'][w] for w in tokens[clip['id']]],
            rowIndices=[i for i, r in enumerate(expanded['rows']) if r['clipId'] == clip['id']],
            speakerRoles=[dict(fold=f['fold'], roles=[name for name in position_data.GROUPS
                if clip['speakerId'] in f[name+'Speakers']]) for f in splits['folds']]))
    return dict(inventory, canonicalTokens=tokens, originalRowToExpanded={str(k): v for k, v in mapping.items()},
                additionalClips=extra, newWordTypes=sorted(set(inventory['wordGroups'])-set(previous['wordGroups'])),
                corpusByOrigin=strata(expanded['rows'], list(range(len(expanded['rows'])))),
                originalPartitionsExact=True, featureParity=parity, featureVerification=feature_check, **FLAGS)


def run(path, sha, verify=False):
    pin = files.binding(path, sha)
    plan = read(pin)
    require(plan == plan_value(), 'Expansion inventory declaration changed')
    root = Path(path).resolve().parent
    if not verify:
        files.write_json(root/'started.json', dict(plan=pin))
    try:
        result = dict(complete=True, plan=pin, **calculate(plan))
        files.guard(plan['inputs'])
        if verify:
            report = files.binding(root/'report.json')
            require(read(report) == result, 'Expansion inventory reconstruction differs')
            return dict(verified=True, report=report, **FLAGS)
        files.write_json(root/'report.json', result)
        return files.binding(root/'report.json')
    except Exception as error:
        if not verify:
            files.write_json(root/'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'verify'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    print(json.dumps(declare(args.output) if args.command == 'declare'
                     else run(args.plan, args.plan_sha256, args.command == 'verify')), flush=True)
