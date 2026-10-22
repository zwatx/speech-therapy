"""Diagnose saved VAD/alignment disagreement without a new filtering rule."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from position_overlap import study as overlap

a = overlap.a
read = overlap.read
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = a.HERE / '../../docs/model/multiphone-position-context-protocol.md'
PARENT = overlap.BASE / 'position-overlap-v1'
PLAN_SHA = '675815f90b4cc4e99a30582ce88fdf19dbb658601acc545eed0ef3a2ba831407'
REPORT_SHA = 'f4130122ec6267ffa71e313109a47fa1ee1a8090da01d5f2d9f54697b91d71b8'
CATEGORIES = ('centerInside', 'noSegments', 'beforeFirst', 'afterLast',
              'internalGap', 'segmentBetweenCenters')
VIEWS = ('all', 'zeroCenters', *CATEGORIES)
CONTEXT = ('singleFrame', 'targetNotArgmax', 'bothWarnings', 'wordFirst',
           'wordLast', 'promptFirst', 'promptLast')
BASE_FLAG = 'unverified-forced-canonical-location'
SINGLE_FLAG = 'fewer-than-two-target-state-frames'
ARGMAX_FLAG = 'target-is-not-argmax-on-most-occupied-frames'
COUNT_KEYS = ('positions', 'rating0Positions', 'below2Positions', 'allTopPositions',
              *CONTEXT, 'occupancyFootprintDisjoint', 'poolingFootprintDisjoint',
              'nearestDistanceMissing')
FALSE_FLAGS = dict(acousticInferencePerformed=False, trainingPerformed=False,
                   thresholdFitted=False, authorTestRead=False,
                   withholdingRuleChanged=False, frameTimesValidated=False,
                   speechAtTargetValidated=False, clinicalUseEligible=False,
                   learnerFeedbackEligible=False)


def locate(interval, samples, segments):
    """Exact center membership and distance infimum to padded segments."""
    a.require(type(samples) is int and samples >= 400, 'Invalid sample count')
    frames = (samples - 400) // 320 + 1
    a.require(isinstance(interval, list) and len(interval) == 2
              and all(type(v) is int for v in interval)
              and 0 <= interval[0] < interval[1] <= frames, 'Invalid occupied interval')
    overlap.f.study.validate_timestamps(segments, samples)
    centers = [640 * i + 399 for i in range(*interval)]
    inside = any(2 * seg['start'] <= c < 2 * seg['end']
                 for c in centers for seg in segments)
    gap = None
    if inside:
        category = 'centerInside'
    elif not segments:
        category, gap = 'noSegments', [0, samples]
    elif centers[-1] < 2 * segments[0]['start']:
        category, gap = 'beforeFirst', [0, segments[0]['start']]
    elif centers[0] >= 2 * segments[-1]['end']:
        category, gap = 'afterLast', [segments[-1]['end'], samples]
    else:
        category = 'segmentBetweenCenters'
        for left, right in zip(segments, segments[1:]):
            if 2 * left['end'] <= centers[0] and centers[-1] < 2 * right['start']:
                category, gap = 'internalGap', [left['end'], right['start']]
                break
    distance = (None if not segments else min(
        max(2 * seg['start'] - c, c - 2 * seg['end'], 0)
        for c in centers for seg in segments))
    a.require((category == 'centerInside') == inside
              and (distance == 0) == inside, 'Distance/membership inconsistency')
    return dict(category=category, gapSamples=gap, nearestDistanceDoubledSamples=distance,
                nearestDistanceMs=None if distance is None else distance / 32)


def context(row, geometry, clip):
    """Prompt indices and existing warnings; no new confidence cutoff."""
    wi, pi, ci = row['wordIndex'], row['phoneIndex'], row['canonicalIndex']
    words, phones = clip['words'], clip['canonicalPhones']
    a.require(type(wi) is int and 0 <= wi < len(words)
              and type(pi) is int and 0 <= pi < len(words[wi]['phones'])
              and type(ci) is int
              and ci == sum(len(w['phones']) for w in words[:wi]) + pi
              and [p for w in words for p in w['phones']] == phones
              and row['targetPhone'] == words[wi]['phones'][pi] == phones[ci],
              'Invalid canonical prompt position')
    values = geometry['scalarFeatures']
    a.require(len(values) == 13 and all(type(v) in (int, float) for v in values)
              and np.isfinite(values).all() and 0 <= values[1] <= 1
              and 0 <= values[5] <= 1 and 0 <= values[6] <= 1, 'Invalid saved scalars')
    occupied = geometry['intervalFrames'][1] - geometry['intervalFrames'][0]
    single, weak = occupied < 2, values[5] < .5
    expected = [BASE_FLAG] + ([SINGLE_FLAG] if single else []) + ([ARGMAX_FLAG] if weak else [])
    a.require(occupied > 0 and values[10] == occupied and values[9] == occupied * .02
              and geometry['diagnosticFlags'] == expected, 'Saved warning or duration differs')
    return dict(singleFrame=single, targetNotArgmax=weak, bothWarnings=single and weak,
                wordFirst=pi == 0, wordLast=pi == len(words[wi]['phones']) - 1,
                promptFirst=ci == 0, promptLast=ci == len(phones) - 1)


def numeric(values):
    values = [v for v in values if v is not None]
    if not values:
        return dict(count=0, minimum=None, median=None, p90=None, maximum=None)
    a.require(np.isfinite(values).all(), 'Nonfinite diagnostic value')
    q = np.quantile(values, [0, .5, .9, 1], method='linear').tolist()
    return dict(zip(('count', 'minimum', 'median', 'p90', 'maximum'), [len(values), *q]))


def support(rows, policy):
    result = overlap.support(rows)
    result.update({key: sum(r['context'][key] for r in rows) for key in CONTEXT})
    result.update({key: sum(r['policies'][policy][key] for r in rows)
                   for key in ('occupancyFootprintDisjoint', 'poolingFootprintDisjoint')})
    result['nearestDistanceMissing'] = sum(r['policies'][policy]['nearestDistanceMs'] is None for r in rows)
    result['numeric'] = dict(
        nearestDistanceMs=numeric([r['policies'][policy]['nearestDistanceMs'] for r in rows]),
        occupiedFrames=numeric([r['intervalFrames'][1] - r['intervalFrames'][0] for r in rows]),
        targetPosteriorMean=numeric([r['scalarFeatures'][1] for r in rows]),
        blankPosteriorMean=numeric([r['scalarFeatures'][6] for r in rows]))
    return result


def reconcile(total, parts):
    a.require(all(total[k] == sum(part[k] for part in parts) for k in COUNT_KEYS)
              and total['raterVotes'] == [sum(p['raterVotes'][i] for p in parts) for i in range(3)],
              'Disjoint position/vote/context support does not reconcile')


def tables(rows):
    result = {}
    for policy in overlap.POLICIES:
        populations = {}
        for population in ('all', 'original', 'added'):
            selected = [r for r in rows if population == 'all'
                        or (r['legacyRowIndex'] is not None) == (population == 'original')]
            ages = {}
            for age in ('allAges', 'ages6to12', 'ages13plus'):
                age_rows = [r for r in selected if age == 'allAges'
                            or (6 <= r['age'] <= 12 if age == 'ages6to12' else r['age'] >= 13)]
                cells = {}
                for phone in ('aggregate', *a.inference.TARGETS[:23]):
                    pr = [r for r in age_rows if phone == 'aggregate' or r['targetPhone'] == phone]
                    cells[phone] = {view: support([r for r in pr if view == 'all'
                        or (view == 'zeroCenters' and r['policies'][policy]['category'] != 'centerInside')
                        or view == r['policies'][policy]['category']], policy) for view in VIEWS}
                    cell = cells[phone]
                    reconcile(cell['all'], [cell[c] for c in CATEGORIES])
                    reconcile(cell['zeroCenters'], [cell[c] for c in CATEGORIES[1:]])
                ages[age] = cells
            populations[population] = ages
        for age in populations['all']:
            for phone in populations['all'][age]:
                for view in VIEWS:
                    reconcile(populations['all'][age][phone][view],
                              [populations[p][age][phone][view] for p in ('original', 'added')])
        result[policy] = populations
    return result


def inputs():
    parent, parent_pin = overlap.load(PARENT / 'plan.json', PLAN_SHA)
    pins = {'parentPlan': parent_pin, 'parentReport': a.binding(PARENT / 'report.json', REPORT_SHA),
            'protocol': a.binding(PROTOCOL), **{'parent/' + k: v for k, v in parent['inputs'].items()}}
    prior = read(pins['parentReport'])
    a.require(prior['complete'] is True and prior['plan'] == parent_pin and prior['diagnosticOnly'] is True
              and prior['learnerFeedbackEligible'] is False, 'Incomplete or mismatched parent report')
    pins.update({'freshVAD/' + k: v for k, v in prior['freshVAD'].items()})
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['source/' + path.name] = a.binding(path)
    a.guard(pins)
    return pins


def runtime():
    parent = overlap.f.study.runtime()
    return {k: parent[k] for k in ('python', 'executable', 'platform')} | {
        'numpy': np.__version__, 'computation': 'saved JSON and NumPy summaries; no model inference'}


def declare(output):
    a.require(not output.exists() and output.resolve().is_relative_to(a.HERE / 'outputs'), 'Fresh ignored output required')
    pins = inputs()
    recipe = read(pins['parent/recipe'])
    a.require(overlap.frontend_geometry(recipe) == (320, 400)
              and recipe['minimumTargetFramesDiagnostic'] == 2, 'Frozen geometry/diagnostic recipe differs')
    output.mkdir(mode=0o700, parents=True)
    a.write_json(output / 'plan.json', dict(inputs=pins, categories=list(CATEGORIES), views=list(VIEWS),
        runtime=runtime(), quantileMethod='linear', diagnosticOnly=True, **FALSE_FLAGS))
    return a.binding(output / 'plan.json')


def load(path, sha):
    pin = a.binding(path, sha)
    plan = read(pin)
    a.require(plan == dict(inputs=inputs(), categories=list(CATEGORIES), views=list(VIEWS),
                          runtime=runtime(), quantileMethod='linear', diagnosticOnly=True, **FALSE_FLAGS),
              'Declaration differs')
    return plan, pin


def calculate(plan):
    pins = plan['inputs']
    prior = read(pins['parentReport'])
    cohort = read(pins['parent/cohort'])
    a.require(prior['summary'] == overlap.tables(prior['rows']), 'Inherited support differs')
    clips = {c['id']: c for c in cohort['clips']}
    a.require(len(clips) == len(cohort['clips']) == 2500 and set(clips) == set(prior['clips'])
              and len(prior['rows']) == len(cohort['rows']) == 28227
              and len({r['id'] for r in prior['rows']}) == 28227, 'Incomplete clip/row identities')
    geometry, clip_context = {}, {}
    for cid, clip in clips.items():
        g = read(pins['parent/geometry/' + cid])
        a.require(g['clipId'] == cid and prior['clips'][cid]['sampleCount'] == clip['sampleCount'],
                  'Geometry/audio identity differs')
        for row in g['rows']:
            a.require(row['id'] not in geometry and row['clipId'] == cid, 'Duplicate or mismatched geometry identity')
            geometry[row['id']] = row
        clip_context[cid] = dict(mappingAmbiguities=g['mappingAmbiguities'], diagnostics=g['diagnostics'],
                                geometry=pins['parent/geometry/' + cid])
    a.require(set(geometry) == {r['id'] for r in prior['rows']}, 'Geometry row coverage differs')
    rows = []
    for source, old in zip(cohort['rows'], prior['rows'], strict=True):
        a.require(all(source[k] == old[k] for k in ('id', 'clipId', 'speakerId', 'age', 'wordIndex',
                  'phoneIndex', 'canonicalIndex', 'legacyRowIndex', 'targetPhone', 'raterCounts'))
                  and source['trainingEligible'] is True, 'Source row identity differs')
        g, clip = geometry[old['id']], clips[old['clipId']]
        a.require(all(g[k] == old[k] for k in ('id', 'clipId', 'wordIndex', 'phoneIndex', 'canonicalIndex',
                  'targetPhone', 'legacyRowIndex', 'intervalFrames'))
                  and g['estimatedPoolingWindowFrames'] == old['poolingWindowFrames'], 'Saved geometry differs')
        policies = {}
        for policy in overlap.POLICIES:
            found = locate(old['intervalFrames'], clip['sampleCount'], prior['clips'][clip['id']]['segments'][policy])
            a.require((found['category'] == 'centerInside') == old['policies'][policy]['anyCenterInside'],
                      'Parent center membership differs')
            policies[policy] = {**found, **{k: old['policies'][policy][k] for k in
                ('occupancyFootprintDisjoint', 'poolingFootprintDisjoint')}}
        rows.append({**{k: v for k, v in old.items() if k != 'policies'}, 'policies': policies,
                     'diagnosticFlags': g['diagnosticFlags'], 'scalarFeatures': g['scalarFeatures'],
                     'context': context(old, g, clip)})
    return dict(complete=True, rows=rows, clips=clip_context, summary=tables(rows),
                diagnosticOnly=True, **FALSE_FLAGS)


def run(path, sha):
    plan, pin = load(path, sha)
    root = Path(path).resolve().parent
    a.write_json(root / 'started.json', dict(plan=pin))
    try:
        report = calculate(plan)
        report['plan'] = pin
        a.guard(plan['inputs'])
        a.write_json(root / 'report.json', report)
        return a.binding(root / 'report.json')
    except Exception as error:
        a.write_json(root / 'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


def verify(path, sha):
    plan, pin = load(path, sha)
    expected = calculate(plan)
    expected['plan'] = pin
    report_pin = a.binding(Path(path).resolve().parent / 'report.json')
    a.require(read(report_pin) == expected, 'Saved context report differs')
    a.guard(plan['inputs'])
    return dict(verified=True, positions=28227, clips=2500, acousticInferencePerformed=False, report=report_pin)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'verify'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    result = declare(args.output) if args.command == 'declare' else globals()[args.command](args.plan, args.plan_sha256)
    print(json.dumps(result), flush=True)
