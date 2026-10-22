"""Metadata-only full crossed speaker/orthographic-word support inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import multiphone_research_audio as files
import multiphone_selection_audit as metrics

HERE = files.HERE
DIRECTORY = Path(__file__).resolve().parent
BASE = HERE / 'outputs/multiphone-20260926'
PROTOCOL = HERE / '../../docs/model/multiphone-lexical-feasibility-protocol.md'
COHORT_SHA = '33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805'
SPLITS_SHA = 'b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf'
SEED = 'cadence-lexical-holdout-v1'
REGIMES = ('all-age', 'child-only')
FLAGS = dict(authorTestRead=False, audioRead=False, predictionsRead=False, modelInferencePerformed=False,
             trainingPerformed=False, independentFinalValidation=False, clinicalUseEligible=False,
             learnerFeedbackEligible=False, promotionEligible=False)
require = files.require


def read(pin):
    return files.read_bound_json(pin['path'], pin['sha256'])[0]


def word_group(word):
    require(isinstance(word, str) and bool(word) and word == word.upper()
            and len(word.split()) == 1 and word.split()[0] == word, 'Expected one uppercase canonical token')
    return int.from_bytes(hashlib.sha256((SEED + '\0' + word).encode('utf-8')).digest(), 'big') % 5


def checked_metadata(cohort, splits):
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train', 'Author-training metadata required')
    clips = {c['id']: c for c in cohort['clips']}
    require(len(clips) == len(cohort['clips']), 'Duplicate clip identity')
    tokens = {}
    for key, clip in clips.items():
        require(isinstance(clip['text'], str) and clip['text'].strip(), 'Empty transcript')
        tokens[key] = clip['text'].upper().split()
    rows = cohort['rows']
    for row in rows:
        require(row['clipId'] in clips and type(row['wordIndex']) is int
                and 0 <= row['wordIndex'] < len(tokens[row['clipId']])
                and tokens[row['clipId']][row['wordIndex']] == row['targetWord'].upper(), 'Canonical row/transcript word identity differs')
        clip = clips[row['clipId']]
        require(row['speakerId'] == clip['speakerId'] and row['age'] == clip['age'], 'Row/clip speaker or age differs')
    require(len(splits['folds']) == 5 and [f['fold'] for f in splits['folds']] == list(range(5)), 'Five ordered speaker folds required')
    outer_seen = []
    for fold in splits['folds']:
        fit, validation, outer = (fold[k] for k in ('innerFitRows', 'innerValidationRows', 'outerHoldoutRows'))
        metrics.check_partitions(rows, fit, validation, outer)
        require(sorted(fit + validation) == sorted(fold['outerFitRows']) and len(set(fold['outerFitRows'])) == len(fold['outerFitRows']),
                'Inner fit/validation do not partition outer fitting rows')
        outer_seen.extend(outer)
    eligible = [i for i, r in enumerate(rows) if r['trainingEligible']]
    require(len(outer_seen) == len(set(outer_seen)) and sorted(outer_seen) == eligible, 'Outer speaker folds do not cover eligible rows once')
    require(all(rows[i]['targetPhone'] in metrics.PHONES and len(rows[i]['raterCounts']) == 3
                and all(type(v) is int and v >= 0 for v in rows[i]['raterCounts'])
                and sum(rows[i]['raterCounts']) == 5 for i in eligible), 'Invalid supported phone or five-vote labels')
    return rows, tokens, eligible


def support_views(rows, indices):
    chosen = [rows[i] for i in indices]
    result = {}
    for age, select in (('allAges', lambda r: True), ('ages6to12', lambda r: 6 <= r['age'] <= 12),
                        ('ages13plus', lambda r: r['age'] >= 13)):
        value = metrics.support([r for r in chosen if select(r)])
        value['missingPhones'] = [phone for phone, p in value['perPhone'].items() if p['positions'] == 0]
        value['missingEventVoteClasses'] = {event: [phone for phone, p in value['perPhone'].items()
            if p['events'][event]['positiveVotes'] == 0 or p['events'][event]['negativeVotes'] == 0]
            for event in ('rating0', 'ratingBelow2')}
        result[age] = value
    return result


def partition(rows, indices, blocked_clips, outer=False, groups=None, group=None):
    require(len(indices) == len(set(indices)), 'Duplicate partition row')
    kept, excluded = [], []
    for i in indices:
        retained = groups[rows[i]['targetWord'].upper()] == group if outer else rows[i]['clipId'] not in blocked_clips
        (kept if retained else excluded).append(i)
    require(sorted(kept + excluded) == sorted(indices) and not set(kept) & set(excluded), 'Partition accounting differs')
    return dict(baseRows=indices, retainedRows=kept, excludedRows=excluded,
                retained=support_views(rows, kept), excluded=support_views(rows, excluded))


def calculate(cohort, splits):
    rows, tokens, eligible = checked_metadata(cohort, splits)
    groups = {word: word_group(word) for word in sorted({w for tt in tokens.values() for w in tt})}
    blocked = {g: {clip: sorted({w for w in tt if groups[w] == g}) for clip, tt in tokens.items()
                   if any(groups[w] == g for w in tt)} for g in range(5)}
    models = {}
    for regime in REGIMES:
        cells = []
        for fold in splits['folds']:
            base = dict(innerFit=[i for i in fold['innerFitRows'] if regime == 'all-age' or 6 <= rows[i]['age'] <= 12],
                        innerValidation=fold['innerValidationRows'],
                        selection=[i for i in fold['innerValidationRows'] if regime == 'all-age' or 6 <= rows[i]['age'] <= 12],
                        outerFit=[i for i in fold['outerFitRows'] if regime == 'all-age' or 6 <= rows[i]['age'] <= 12],
                        outer=fold['outerHoldoutRows'])
            for group in range(5):
                parts = {key: partition(rows, ids, blocked[group], key == 'outer', groups, group) for key, ids in base.items()}
                for key in ('innerFit', 'innerValidation', 'selection', 'outerFit'):
                    require(all(all(groups[w] != group for w in tokens[rows[i]['clipId']]) for i in parts[key]['retainedRows']),
                            'Held-out word remains in supervised fitting/selection transcript')
                require(sorted(parts['innerFit']['retainedRows'] + parts['selection']['retainedRows']) == sorted(parts['outerFit']['retainedRows']),
                        'Purged fit/selection do not partition purged refit')
                cells.append(dict(speakerFold=fold['fold'], wordGroup=group, partitions=parts))
        all_outer = [i for c in cells for i in c['partitions']['outer']['retainedRows']]
        require(len(all_outer) == len(set(all_outer)) and sorted(all_outer) == eligible, 'Crossed cells do not cover original outer rows once')
        unions = {}
        for key in ('innerFit', 'innerValidation', 'selection', 'outerFit', 'outer'):
            ids = sorted({i for c in cells for i in c['partitions'][key]['retainedRows']})
            unions[key] = dict(rowIndices=ids, support=support_views(rows, ids))
        models[regime] = dict(cells=cells, retainedUnions=unions, outerCoverageExactlyOnce=True,
                             requiredHeadsForLaterExperiment=25)
    return dict(wordGroups=groups, blockedClips={str(g): value for g, value in blocked.items()},
                corpusSupport=support_views(rows, eligible), models=models, **FLAGS)


def inputs():
    pins = dict(cohort=files.binding(BASE / 'cohort.json', COHORT_SHA), splits=files.binding(BASE / 'splits.json', SPLITS_SHA),
                protocol=files.binding(PROTOCOL))
    for path in sorted(HERE.glob('*.py')) + sorted(DIRECTORY.glob('*.py')):
        pins['source/' + str(path)] = files.binding(path)
    return pins


def plan_value():
    return dict(inputs=inputs(), seed=SEED, groupCount=5, speakerFolds=list(range(5)), crossing='full Cartesian product',
                regimes=list(REGIMES), runtime=dict(python=sys.version, executable=files.binding(sys.executable), platform=platform.platform()), **FLAGS)


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
    value = plan_value()
    output.mkdir(parents=True, mode=0o700)
    files.write_json(output / 'plan.json', value)
    return files.binding(output / 'plan.json')


def run(path, sha, verify=False):
    pin = files.binding(path, sha)
    plan = read(pin)
    require(plan == plan_value(), 'Frozen declaration differs')
    output = Path(path).resolve().parent
    if not verify:
        files.write_json(output / 'started.json', dict(plan=pin))
    try:
        result = dict(complete=True, plan=pin, **calculate(read(plan['inputs']['cohort']), read(plan['inputs']['splits'])))
        files.guard(plan['inputs'])
        if verify:
            report_pin = files.binding(output / 'report.json')
            require(read(report_pin) == result, 'Saved lexical feasibility reconstruction differs')
            return dict(verified=True, report=report_pin, **FLAGS)
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
