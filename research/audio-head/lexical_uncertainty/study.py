"""Frozen-prediction, paired whole-speaker descriptive uncertainty."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np
from lexical_uncertainty import core

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'research/audio-head/outputs/multiphone-20260927'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = ROOT / 'docs/model/multiphone-lexical-uncertainty-protocol.md'
MIX_PLAN = BASE / 'lexical-mixture-v1/plan.json'
MIX_REPORT = BASE / 'lexical-mixture-v1/report.json'
PLAN_SHA = '83c31246a295db47d4cc3402e971f8e5d1199fa2bf478378a55ee104f8370bf7'
REPORT_SHA = '8df2508a7af9f728396fea41f2e34317d086cbeca773b662cc1918b37d3ced47'
AUDIT = ROOT / 'work/lexical-mixture-audit-20260927/result.json'
AUDIT_SHA = 'e06f3b34562d5ca880918b6034cdb10351ef1fc9c4130690600c061a11d5b628'
REGIMES = ('all-age', 'child-only')
ENDPOINTS = ('NLL', 'Brier', 'macroNLL', 'rating0AP', 'below2AP')
RECIPE = dict(replicates=2000, seed=20260927, generator='PCG64', strata='original speaker folds',
              samplingUnit='whole child', quantiles=[.025,.975], quantileMethod='linear',
              contrast='mixture minus scalar', macro='fixed 23 phones; null if any absent')
FLAGS = dict(trainingPerformed=False, modelInferencePerformed=False, authorTestRead=False,
             independentFinalValidation=False, clinicalUseEligible=False, promotionEligible=False,
             learnerFeedbackEligible=False)


def require(ok, why):
    if not ok: raise ValueError(why)


def binding(path, expected=None):
    path = Path(path).resolve()
    with path.open('rb') as stream: sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(expected is None or sha == expected, 'Changed input: ' + str(path))
    return dict(path=str(path), sha256=sha)


def read(pin):
    binding(pin['path'], pin['sha256'])
    return json.loads(Path(pin['path']).read_text())


def write(path, value):
    with Path(path).open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def inputs():
    pp = binding(MIX_PLAN, PLAN_SHA)
    parent = read(pp)
    pins = dict(parent['inputs'], mixturePlan=pp, mixtureReport=binding(MIX_REPORT, REPORT_SHA),
                mixtureAudit=binding(AUDIT, AUDIT_SHA), uncertaintyProtocol=binding(PROTOCOL))
    for path in sorted(DIRECTORY.glob('*.py')): pins['uncertaintySource/'+path.name] = binding(path)
    for pin in pins.values(): binding(pin['path'], pin['sha256'])
    return pins


def plan_value(pins):
    return dict(inputs=pins, recipe=RECIPE, **FLAGS,
                runtime=dict(python=sys.version, numpy=np.__version__, platform=platform.platform(),
                             executable=binding(sys.executable)), resamplingPerformed=False)


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(BASE), 'Fresh ignored output required')
    plan = plan_value(inputs())
    output.mkdir(parents=True, mode=0o700)
    write(output/'plan.json', plan)
    return binding(output/'plan.json')


def load_plan(path, sha):
    pin = binding(path, sha); plan = read(pin)
    require(plan == plan_value(inputs()), 'Declaration no longer matches')
    return plan, pin


def interval(values, observed):
    valid = np.asarray([v for v in values if v is not None], dtype=float)
    require(np.isfinite(valid).all(), 'Nonfinite replicate')
    q = np.quantile(valid, RECIPE['quantiles'], method='linear').tolist() if len(valid) else [None,None]
    return dict(observed=observed, interval95=q, validReplicates=len(valid), undefinedReplicates=len(values)-len(valid),
                fractionBelowZero=float(np.mean(valid<0)) if len(valid) else None,
                fractionAboveZero=float(np.mean(valid>0)) if len(valid) else None)


def contributions(rows, folds, groups, class_delta):
    diff = class_delta.sum(1)
    def cell(mask, denominator):
        n = int(mask.sum()); total = float(diff[mask].sum())
        return dict(positions=n, speakers=len({rows[i]['speakerId'] for i in np.flatnonzero(mask)}),
                    raterVotes=np.asarray([rows[i]['raterCounts'] for i in np.flatnonzero(mask)],dtype=int).reshape(-1,3).sum(0).tolist(),
                    NLLDelta=float(total/n) if n else None, additiveNLLContribution=total/denominator)
    all_mask = np.ones(len(rows), dtype=bool)
    fold4 = folds == 4; n4 = int(fold4.sum()); require(n4>0, 'No fold4 positions')
    phones = sorted({r['targetPhone'] for r in rows}); speakers = sorted({r['speakerId'] for r in rows})
    partitions = {}
    for name, labels, values in (
        ('phones',phones,[r['targetPhone'] for r in rows]),
        ('children',sorted({r['speakerId'] for r,k in zip(rows,fold4) if k}),[r['speakerId'] for r in rows]),
        ('wordGroups',list(range(5)),groups)):
        partitions[name] = {str(label):cell(fold4 & (np.asarray(values)==label), n4) for label in labels}
        require(np.isclose(sum(v['additiveNLLContribution'] for v in partitions[name].values()),float(diff[fold4].mean()),atol=1e-14), 'Contribution partition mismatch')
    partitions['ratingClasses'] = {str(k):dict(positionsWithAnyVote=sum(r['raterCounts'][k]>0 for r,f in zip(rows,fold4) if f),
        votes=sum(r['raterCounts'][k] for r,f in zip(rows,fold4) if f),
        additiveNLLContribution=float(class_delta[fold4,k].sum()/n4)) for k in range(3)}
    require(np.isclose(sum(v['additiveNLLContribution'] for v in partitions['ratingClasses'].values()),diff[fold4].mean(),atol=1e-14),'Class sum mismatch')
    loo = {}
    for name, population in [('pooled',all_mask),('fold4',fold4)]:
        loo[name] = {}
        for speaker in speakers:
            removed = population & np.array([r['speakerId']==speaker for r in rows])
            if not removed.any(): continue
            keep = population & ~removed
            loo[name][speaker] = dict(removedPositions=int(removed.sum()), remainingPositions=int(keep.sum()),
                NLLDelta=float(diff[keep].mean()) if keep.any() else None)
    return dict(speakerFolds={str(f):cell(folds==f,int((folds==f).sum())) for f in range(5)},
                fold4=partitions, leaveOneChildOut=loo)


def calculate(plan, pin):
    mix = read(plan['inputs']['mixtureReport']); base = read(plan['inputs']['baselineReport'])
    require(mix['complete'] and mix['plan']==plan['inputs']['mixturePlan'], 'Mixture lineage differs')
    require(base['complete'] and base['plan']==plan['inputs']['baselinePlan'], 'Scalar lineage differs')
    cohort = read(plan['inputs']['cohort'])['rows']
    eligible = [i for i,r in enumerate(cohort) if r['trainingEligible']]
    results = {}; shared = None; shared_identity = None
    for regime in REGIMES:
        m = mix['models'][regime]; b = base['models'][regime]['scalars']
        require(m['rowIndices']==b['rowIndices']==eligible, 'Outer row identity differs')
        require(m['rowFolds']==b['rowFolds'] and m['rowWordGroups']==b['rowWordGroups'], 'Fold/group identity differs')
        keep = [k for k,i in enumerate(eligible) if 6<=cohort[i]['age']<=12]
        ids = [eligible[k] for k in keep]; rows = [cohort[i] for i in ids]
        folds = np.asarray(m['rowFolds'])[keep]; groups = np.asarray(m['rowWordGroups'])[keep]
        phones = [r['targetPhone'] for r in rows]; all_phones = sorted(set(phones)); counts = np.asarray([r['raterCounts'] for r in rows])
        speakers = [r['speakerId'] for r in rows]
        require(len(rows)==5654 and len(set(speakers))==52 and len(all_phones)==23, 'Unexpected child coverage')
        identity = (ids,folds.tolist(),groups.tolist(),speakers)
        if shared is None:
            shared = core.speaker_weights(speakers,folds,RECIPE['replicates'],RECIPE['seed']); shared_identity = identity
        else: require(identity==shared_identity,'Regime child membership differs')
        speaker_index = {s:i for i,s in enumerate(shared['speakerIds'])}
        row_speakers = np.asarray([speaker_index[s] for s in speakers])
        pm,lm,pb,lb = [np.asarray(model[key],dtype=float)[keep] for model,key in (
            (m,'probabilities'),(m,'logProbabilities'),(b,'probabilities'),(b,'logProbabilities'))]
        cm = core.prepare(pm,lm,counts,phones,all_phones); cb = core.prepare(pb,lb,counts,phones,all_phones)
        actual_m,actual_b = core.evaluate(cm,np.ones(len(rows),dtype=int)),core.evaluate(cb,np.ones(len(rows),dtype=int))
        observed = {key:actual_m[key]-actual_b[key] for key in ENDPOINTS}
        for key in ENDPOINTS: require(np.isclose(observed[key],mix['comparisons'][regime]['mixtureVsScalar']['childDelta'][key],atol=2e-12,rtol=2e-11), 'Observed metric mismatch '+key)
        values = {key:[] for key in ENDPOINTS}; per_phone = {phone:[] for phone in all_phones}
        class_delta = -counts*(lm-lb)/5; loss_delta = class_delta.sum(1)
        phone_masks = {phone:np.asarray(phones)==phone for phone in all_phones}
        for weights in shared['weights']:
            rw = weights[row_speakers]; a,c = core.evaluate(cm,rw),core.evaluate(cb,rw)
            for key in ENDPOINTS: values[key].append(a[key]-c[key] if a[key] is not None and c[key] is not None else None)
            for phone,mask in phone_masks.items():
                mass = int(rw[mask].sum()); per_phone[phone].append(float(np.dot(rw[mask],loss_delta[mask])/mass) if mass else None)
        results[regime] = dict(observed=dict(mixture=actual_m,scalar=actual_b),
            pairedIntervals={key:interval(values[key],observed[key]) for key in ENDPOINTS}, replicates=values,
            perPhone={phone:dict(interval(per_phone[phone],float(loss_delta[mask].mean())),
                positions=int(mask.sum()), children=len({r['speakerId'] for r,k in zip(rows,mask) if k}),
                raterVotes=counts[mask].sum(0).tolist(), replicates=per_phone[phone]) for phone,mask in phone_masks.items()},
            contributionDiagnostics=contributions(rows,folds,groups,class_delta))
    for source in plan['inputs'].values(): binding(source['path'],source['sha256'])
    return dict(complete=True, plan=pin, recipe=RECIPE, **FLAGS, resamplingPerformed=True,
        sampling=dict(speakerIds=shared['speakerIds'], speakerFolds=shared['speakerFolds'], weights=shared['weights'].tolist(),
                      rowIndices=shared_identity[0]), regimes=results)


def run(path, sha, verify=False):
    plan,pin = load_plan(path,sha); root = Path(path).resolve().parent
    if not verify: write(root/'started.json',dict(plan=pin))
    try:
        report = calculate(plan,pin)
        if verify:
            require(json.loads((root/'report.json').read_text())==report,'Offline reconstruction differs')
            return dict(verified=True,report=binding(root/'report.json'))
        write(root/'report.json',report)
        return binding(root/'report.json')
    except Exception as exc:
        if not verify and not (root/'failure.json').exists(): write(root/'failure.json',dict(error=type(exc).__name__,message=str(exc)))
        raise


def main():
    p = argparse.ArgumentParser(); p.add_argument('command',choices=('declare','run','verify'))
    p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256')
    a=p.parse_args()
    require(a.output is not None if a.command=='declare' else a.plan is not None and a.plan_sha256 is not None,'Missing required arguments')
    print(json.dumps(declare(a.output) if a.command=='declare' else run(a.plan,a.plan_sha256,a.command=='verify')))

if __name__=='__main__': main()
