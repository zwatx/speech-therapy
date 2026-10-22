"""Declared complete sound response and fitting-composition diagnostic."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import numpy as np
from lexical_expanded_uncertainty import study as prior
from lexical_phone_response import analysis

ROOT, BASE = prior.ROOT, prior.BASE
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = ROOT/'docs/model/multiphone-lexical-phone-response-protocol.md'
PARENT_SHA = '347070d614db0ad885e072181fe076bbffcd394882a50975b37240fe9fca8ebf'
PARENT_AUDIT_SHA = 'ccb716adfc66058201d04a092af9803768d26e79065a0911e7a69eb8bde63ad7'
PARENT_REPORT_SHA = '5d6e693cfe1ce7bb1b8cd4c5be604524226ead6c21b92def72f5602b99bf3d1c'
AGES = ('allAges', 'ages6to12', 'ages13plus')
ORIGINS = ('original', 'added', 'all')
PARTITIONS = {'innerFit': 'fitRows', 'outerFit': 'refitRows'}
FLAGS = dict(prior.FLAGS, resamplingPerformed=False, newFeatureExtractionPerformed=False)
RECIPE = dict(regimes=list(prior.REGIMES), contrasts=list(prior.CONTRASTS), phones=list(analysis.PHONES),
    fittingPartitions=list(PARTITIONS), origins=list(ORIGINS), ages=list(AGES),
    occurrenceCategories=['single', 'repeated'], occurrenceBasis='Complete canonical same-phone count in recording',
    loss='candidate minus reference five-vote stable NLL',
    partitions=['ratingClasses', 'speakerFolds', 'wordCells', 'children'],
    selection='No exclusions, reweighting, threshold, model selection or causal defect claim')
require, binding, read, write, guard = prior.require, prior.binding, prior.read, prior.write, prior.guard


def inputs():
    pp = binding(BASE/'lexical-expanded-uncertainty-v1/plan.json', PARENT_SHA)
    parent = read(pp)
    pins = dict(parent['inputs'], responseParentPlan=pp,
        responseParentReport=binding(BASE/'lexical-expanded-uncertainty-v1/report.json', PARENT_REPORT_SHA),
        responseProtocol=binding(PROTOCOL))
    path = ROOT/'work/lexical-expanded-uncertainty-audit-20260927/result.json'
    audit_pin = binding(path, PARENT_AUDIT_SHA)
    audit = read(audit_pin)
    require(audit['status'] == 'passed' and audit['plan'] == pp
        and audit['report'] == pins['responseParentReport'] and len(audit['comparisons']) == 8, 'Parent numerical audit differs')
    pins['responseParentAudit'] = audit_pin
    for source, sha in audit['sourceBindings'].items(): pins['responseParentAuditSource/'+source] = binding(source, sha)
    for path in sorted(DIRECTORY.glob('*.py')): pins['responseSource/'+path.name] = binding(path)
    guard(pins)
    return pins


def plan_value(pins):
    # Runtime format and executable provenance stay compatible with the parent.
    return dict(inputs=pins, recipe=RECIPE, runtime=prior.plan_value(pins)['runtime'], **FLAGS)


def checked_inputs(plan):
    data = prior.checked_inputs(plan)
    pins = plan['inputs']; cohort = read(pins['cohort'])
    inventory = read(pins['inventoryReport']); heads = read(pins['expandedHeadsPlan'])
    require(inventory['complete'] is True and inventory['plan'] == pins['inventoryPlan'], 'Inventory lineage')
    parent = read(pins['responseParentReport'])
    require(parent['complete'] is True and parent['plan'] == pins['responseParentPlan'], 'Uncertainty lineage')
    require(parent['sampling']['rowIndices'] == data['rowIndices'] and parent['sampling']['rowFolds'] == data['folds']
        and parent['sampling']['rowWordGroups'] == data['groups'], 'Uncertainty population identity')
    jobs = {}
    for job in heads['jobs']:
        key = job['regime'], job['speakerFold'], job['wordGroup']
        if job['family'] == 'scalars':
            require(key not in jobs, 'Duplicate fitting cell'); jobs[key] = job
    require(set(jobs) == {(r,s,w) for r in prior.REGIMES for s in range(5) for w in range(5)}, 'Complete 50 fitting cells')
    require(set(inventory['corpusByOrigin']) == set(ORIGINS), 'Corpus origin coverage')
    for origin in ORIGINS:
        expected = [i for i,r in enumerate(cohort['rows']) if origin == 'all' or (r['legacyRowIndex'] is not None) == (origin == 'original')]
        require(inventory['corpusByOrigin'][origin]['rowIndices'] == expected, 'Corpus origin identity')
    require(len(heads['jobs']) == 100, 'Complete 100 head jobs')
    other = set()
    for job in heads['jobs']:
        key = job['regime'],job['speakerFold'],job['wordGroup']
        if job['family'] != 'scalars':
            require(key in jobs and key not in other, 'Companion family cell coverage')
            other.add(key)
            require(all(job[field] == jobs[key][field] for field in PARTITIONS.values()), 'Head family fitting mismatch')
    require(other == set(jobs), 'Companion family coverage')
    for regime in prior.REGIMES:
        cells = inventory['models'][regime]['cells']
        require([(c['speakerFold'],c['wordGroup']) for c in cells] == [(s,w) for s in range(5) for w in range(5)], 'Inventory cell order')
        for cell in cells:
            job = jobs[regime,cell['speakerFold'],cell['wordGroup']]
            for part, field in PARTITIONS.items():
                value = cell['partitions'][part]
                require(value['retainedRows'] == job[field], 'Fitting inventory differs from actual job')
                for origin in ORIGINS:
                    expected = [i for i in job[field] if origin == 'all' or (cohort['rows'][i]['legacyRowIndex'] is not None) == (origin == 'original')]
                    require(value['retainedByOrigin'][origin]['rowIndices'] == expected, 'Origin inventory differs')
    return data, cohort, inventory, jobs


def multiplicities(cohort):
    """Validate full canonical geometry; derive categories without audio timing."""
    clips = {c['id']:c for c in cohort['clips']}
    require(len(clips) == len(cohort['clips']), 'Duplicate canonical recording')
    totals = {}
    for clip_id, clip in clips.items():
        canonical = clip['canonicalPhones']
        require([p for w in clip['words'] for p in w['phones']] == canonical
            and len(canonical) == clip['canonicalPhoneCount'], 'Incomplete canonical sequence')
        totals[clip_id] = Counter(re.sub(r'[012]$', '', p) for p in canonical)
    positions = set(); observed = Counter(); result = []
    for row in cohort['rows']:
        clip = clips[row['clipId']]; index = row['canonicalIndex']; wi,pi = row['wordIndex'],row['phoneIndex']
        require(type(index) is int and 0 <= index < len(clip['canonicalPhones']) and (row['clipId'],index) not in positions, 'Canonical row identity')
        require(type(wi) is int and 0 <= wi < len(clip['words']) and type(pi) is int and 0 <= pi < len(clip['words'][wi]['phones']), 'Word/phone geometry')
        require(index == sum(len(w['phones']) for w in clip['words'][:wi])+pi
            and clip['canonicalPhones'][index] == clip['words'][wi]['phones'][pi] == row['canonicalRaw']
            and re.sub(r'[012]$', '', row['canonicalRaw']) == row['targetPhone']
            and row['targetPhone'] in analysis.PHONES
            and clip['speakerId'] == row['speakerId'] and clip['age'] == row['age'], 'Canonical row mapping')
        positions.add((row['clipId'],index)); observed[row['clipId'],row['targetPhone']] += 1
        result.append(totals[row['clipId']][row['targetPhone']])
    expected = Counter({(clip,phone):n for clip,counts in totals.items() for phone,n in counts.items() if phone in analysis.PHONES})
    require(observed == expected, 'Supported canonical positions missing or duplicated')
    return result


def composition(rows, indices, multiples, saved):
    """Add occurrence groups to the existing verified support views."""
    require(len(set(indices)) == len(indices) and all(type(i) is int and 0 <= i < len(rows) for i in indices), 'Invalid composition rows')
    require(len(multiples) == len(rows) and all(type(n) is int and n >= 1 for n in multiples), 'Invalid canonical multiplicities')
    output = {}
    for age in AGES:
        ids = [i for i in indices if age == 'allAges' or (6 <= rows[i]['age'] <= 12 if age == 'ages6to12' else rows[i]['age'] >= 13)]
        cached = saved[age]
        require(cached['positions'] == len(ids) and cached['speakers'] == len({rows[i]['speakerId'] for i in ids})
            and cached['recordings'] == len({rows[i]['clipId'] for i in ids})
            and set(cached['perPhone']) == set(analysis.PHONES), 'Cached support differs')
        by_phone = {}
        for phone in analysis.PHONES:
            selected = [i for i in ids if rows[i]['targetPhone'] == phone]
            support = cached['perPhone'][phone]; n = len(selected)
            votes = np.asarray([rows[i]['raterCounts'] for i in selected],dtype=np.int64).reshape(-1,3).sum(0)
            require(support['positions'] == n and support['speakers'] == len({rows[i]['speakerId'] for i in selected})
                and support['raterVotes'] == votes.tolist(), 'Cached phone support differs')
            def group(chosen):
                c = np.asarray([rows[i]['raterCounts'] for i in chosen],dtype=np.int64).reshape(-1,3).sum(0)
                return dict(positions=len(chosen), speakers=len({rows[i]['speakerId'] for i in chosen}),
                    recordings=len({rows[i]['clipId'] for i in chosen}), raterVotes=c.tolist())
            categories = {label:group([i for i in selected if (multiples[i] == 1) == (label == 'single')]) for label in ('single','repeated')}
            require(sum(v['positions'] for v in categories.values()) == n, 'Occurrence partition differs')
            by_phone[phone] = dict(positions=n,speakers=support['speakers'],raterVotes=support['raterVotes'],
                phoneMassFraction=n/len(ids) if ids else None,
                ratingVoteFractions=(votes/(5*n)).tolist() if n else None,
                recordingPhoneUnits=len({(rows[i]['clipId'],phone) for i in selected}), occurrence=categories)
        output[age] = dict(positions=cached['positions'],speakers=cached['speakers'],recordings=cached['recordings'],perPhone=by_phone)
    return output


def calculate(plan, pin):
    data, cohort, inventory, jobs = checked_inputs(plan)
    rows = cohort['rows']; multiples = multiplicities(cohort)
    corpus = {origin:composition(rows,value['rowIndices'],multiples,value['support']) for origin,value in inventory['corpusByOrigin'].items()}
    models = {}
    for regime in prior.REGIMES:
        cells = []
        for cell in inventory['models'][regime]['cells']:
            parts = {}
            for part in PARTITIONS:
                source = cell['partitions'][part]['retainedByOrigin']
                parts[part] = {origin:composition(rows,v['rowIndices'],multiples,v['support']) for origin,v in source.items()}
            cells.append(dict(speakerFold=cell['speakerFold'],wordGroup=cell['wordGroup'],partitions=parts))
        models[regime] = dict(cells=cells)
    responses = {}
    for name,pair in data['comparisons'].items():
        response = analysis.analyze(data['rows'],data['folds'],data['groups'],pair['candidate']['logProbabilities'],pair['reference']['logProbabilities'])
        require(np.isclose(response['pooled']['meanNLLDelta'],pair['sourceComparison']['childDelta']['NLL'],rtol=2e-11,atol=2e-12),'Pooled response differs')
        for fold, expected in enumerate(pair['sourceComparison']['speakerFoldChildDeltas']):
            selected = np.asarray(data['folds']) == fold
            actual = float(np.asarray(response['rowLossDelta'])[selected].mean())
            require(np.isclose(actual,expected['NLL'],rtol=2e-11,atol=2e-12),'Fold response differs')
        response['originalConsistencyDecision'] = pair['sourceComparison']
        responses[name] = response
    guard(plan['inputs'])
    return dict(complete=True,plan=pin,recipe=RECIPE,**FLAGS,canonicalMultiplicity=multiples,
        corpusComposition=corpus,fittingComposition=models,
        childRows=dict(rowIndices=data['rowIndices'],rowFolds=data['folds'],rowWordGroups=data['groups']),responses=responses)


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(BASE), 'Fresh ignored output required')
    plan = plan_value(inputs()); checked_inputs(plan)
    output.mkdir(parents=True,mode=0o700);write(output/'plan.json',plan)
    return binding(output/'plan.json')


def load_plan(path,sha):
    pin=binding(path,sha);plan=read(pin)
    require(plan == plan_value(inputs()), 'Declaration no longer matches')
    return plan,pin


def run(path,sha,verify=False):
    plan,pin=load_plan(path,sha);folder=Path(path).resolve().parent
    if not verify:write(folder/'started.json',dict(plan=pin))
    try:
        result=calculate(plan,pin)
        if verify:
            require(read(binding(folder/'report.json')) == result, 'Offline reconstruction differs')
            return dict(verified=True,report=binding(folder/'report.json'))
        write(folder/'report.json',result);return binding(folder/'report.json')
    except Exception as error:
        if not verify:write(folder/'failure.json',dict(error=f'{type(error).__name__}: {error}'))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('declare','run','verify'))
    parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256');parser.add_argument('--output',type=Path)
    args=parser.parse_args();require(args.output is not None if args.command=='declare' else args.plan is not None and args.plan_sha256 is not None,'Missing arguments')
    print(json.dumps(declare(args.output) if args.command=='declare' else run(args.plan,args.plan_sha256,args.command=='verify')),flush=True)
