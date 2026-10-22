"""Declared descriptive support audit using frozen refit transforms."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import torch
from lexical_uncertainty import study as storage
from lexical_mixture import study as previous
from lexical_support import core
from multiphone_local_train import SCALAR_NAMES

ROOT=storage.ROOT;BASE=storage.BASE;DIRECTORY=Path(__file__).resolve().parent
PROTOCOL=ROOT/'docs/model/multiphone-lexical-support-protocol.md'
RECIPE=dict(axes=['scalarMaxAbsZ','pcaResidualMSE'],references=['globalPercentile','samePhonePercentile'],
    highTailStrictlyGreaterThan=.99,scalarArithmetic='float64 with saved float32 refit moments',
    residualArithmetic='float64 explicit residual MSE over 1024 raw coordinates',
    rank='(count below + .5 * count equal) / reference count',subjectSelection='all original children')
require=storage.require;binding=storage.binding;read=storage.read;write=storage.write
FLAGS=dict(storage.FLAGS,transformFittingPerformed=False)
REGIMES=storage.REGIMES
KEYS=[a+'/'+r for a in RECIPE['axes'] for r in RECIPE['references']]


def inputs():
    pins,jobs=previous.inputs()
    pins=dict(pins,supportProtocol=binding(PROTOCOL),mixturePlan=binding(previous.BASE/'lexical-mixture-v1/plan.json',storage.PLAN_SHA),
              mixtureReport=binding(storage.MIX_REPORT,storage.REPORT_SHA),
              uncertaintyPlan=binding(BASE/'lexical-uncertainty-v1/plan.json','90995285814308f5cb864045fba25eaba02d1f2e9ac224679b95227b81e85fe4'),
              uncertaintyReport=binding(BASE/'lexical-uncertainty-v1/report.json','bf173f044a9f795be56d8a6d92f91450d463b670e376011c337ff374e205df3c'))
    uncertainty=read(pins['uncertaintyPlan'])
    for name,source in uncertainty['inputs'].items():
        require(name not in pins or pins[name]==source,'Inherited input differs')
        pins[name]=source
    cp=read(pins['compactPlan']);expected={j['id']:j for j in cp['jobs']}
    enriched=[]
    for job in jobs:
        j=dict(job);compact_dir=Path(j['compactCheckpoint']['path']).parent;scalar_dir=Path(j['scalarCheckpoint']['path']).parent
        j.update(transform=binding(compact_dir/'transform.pt'),compactConfig=binding(compact_dir/'config.json'),scalarConfig=binding(scalar_dir/'config.json'))
        cc,sc=read(j['compactConfig']),read(j['scalarConfig']);rows=expected[j['compactJobId']]['refitRows']
        require(cc['fitRows']==sc['fitRows']==rows and cc['transform']==j['transform'],'Refit membership/transform differs')
        j['refitRows']=rows
        for key in ('transform','compactConfig','scalarConfig','compactCheckpoint','scalarCheckpoint'):
            pins[j['id']+'/'+key]=binding(j[key]['path'],j[key]['sha256'])
        enriched.append(j)
    for path in sorted(DIRECTORY.glob('*.py')):pins['supportSource/'+path.name]=binding(path)
    # Reused storage helper implementation must itself be bound.
    pins['storageSource']=binding(Path(storage.__file__))
    for pin in pins.values():binding(pin['path'],pin['sha256'])
    return pins,enriched


def plan_value(pins,jobs):
    return dict(inputs=pins,jobs=jobs,recipe=RECIPE,**FLAGS,diagnosticCalculated=False,
                runtime=dict(python=sys.version,numpy=np.__version__,torch=torch.__version__,executable=binding(sys.executable)))


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(BASE),'Fresh ignored output required')
    pins,jobs=inputs();plan=plan_value(pins,jobs);output.mkdir(parents=True,mode=0o700);write(output/'plan.json',plan)
    return binding(output/'plan.json')


def load_plan(path,sha):
    pin=binding(path,sha);plan=read(pin);pins,jobs=inputs()
    require(plan==plan_value(pins,jobs),'Support declaration differs')
    return plan,pin


def summarize(rows,denominator):
    count=len(rows);diff=np.asarray([r['NLLDelta'] for r in rows],dtype=float)
    result=dict(positions=count,children=len({r['speakerId'] for r in rows}),
        raterVotes=np.asarray([r['raterCounts'] for r in rows],dtype=int).reshape(-1,3).sum(0).tolist(),
        meanNLLDelta=float(diff.mean()) if count else None,additiveNLLContribution=float(diff.sum()/denominator),
        fractionNLLWorse=float(np.mean(diff>0)) if count else None,
        dominantScalarCounts={name:sum(r['dominantScalar']==name for r in rows) for name in SCALAR_NAMES},
        axes={})
    for axis in RECIPE['axes']:
        raw=[r[axis]['value'] for r in rows]
        result['axes'][axis]=dict(mean=float(np.mean(raw)) if count else None,
            median=float(np.median(raw)) if count else None,
            **{ref:dict(mean=float(np.mean([r[axis][ref] for r in rows])) if count else None,
                        highTailPositions=sum(r[axis][ref]>.99 for r in rows),
                        highTailFraction=sum(r[axis][ref]>.99 for r in rows)/count if count else None) for ref in RECIPE['references']})
    return result


def summaries(rows):
    n=len(rows);require(n>0,'Empty child results')
    by={}
    for name,field,labels in [('children','speakerId',sorted({r['speakerId'] for r in rows})),
        ('phones','targetPhone',sorted({r['targetPhone'] for r in rows})),
        ('speakerFolds','speakerFold',range(5)),('wordGroups','wordGroup',range(5))]:
        by[name]={str(v):summarize([r for r in rows if r[field]==v],n) for v in labels}
        require(np.isclose(sum(x['additiveNLLContribution'] for x in by[name].values()),sum(r['NLLDelta'] for r in rows)/n,atol=1e-14),'Partition does not sum')
    tails={}
    for key in KEYS:
        axis,ref=key.split('/')
        tails[key]={str(flag).lower():summarize([r for r in rows if (r[axis][ref]>.99)==flag],n) for flag in (False,True)}
    patterns={}
    for pattern in range(16):
        bits=f'{pattern:04b}'
        patterns[bits]=summarize([r for r in rows if ''.join('1' if r[a][ref]>.99 else '0' for a,ref in (k.split('/') for k in KEYS))==bits],n)
    return dict(pooled=summarize(rows,n),**by,tailPartitions=tails,jointTailPatterns=dict(keyOrder=KEYS,cells=patterns))


def calculate(plan,pin):
    torch.set_num_threads(2)
    _,_,bundle=previous.compact.inputs()
    positions=bundle['positions'];cohort=bundle['cohort']['rows']
    mix=read(plan['inputs']['mixtureReport']);base=read(plan['inputs']['baselineReport'])
    require(mix['complete'] and mix['plan']==plan['inputs']['mixturePlan'] and base['complete'] and base['plan']==plan['inputs']['baselinePlan'],'Prediction report lineage differs')
    expected_ids=[i for i,r in enumerate(cohort) if r['trainingEligible'] and 6<=r['age']<=12]
    expected_set=set(expected_ids)
    regimes={};cells=[]
    for regime in REGIMES:
        m=mix['models'][regime];b=base['models'][regime]['scalars']
        require(all(m[k]==b[k] for k in ('rowIndices','rowFolds','rowWordGroups')),'Prediction membership differs')
        index={i:k for k,i in enumerate(m['rowIndices'])};rows=[]
        for job in [j for j in plan['jobs'] if j['regime']==regime]:
            refit=job['refitRows'];outer=[i for i in job['outerRows'] if i in expected_set]
            require(not set(refit)&set(outer),'Refit/outer overlap')
            transform=torch.load(job['transform']['path'],map_location='cpu',weights_only=True)
            scalar=torch.load(job['scalarCheckpoint']['path'],map_location='cpu',weights_only=False)
            compact=torch.load(job['compactCheckpoint']['path'],map_location='cpu',weights_only=False)
            require(transform['fitRows']==refit and transform['rank']==16 and compact['transformSha256']==job['transform']['sha256'],'Saved transform linkage differs')
            require(torch.equal(scalar['mean'],compact['mean'][-13:]) and torch.equal(scalar['std'],compact['std'][-13:]),'Paired scalar moments differ')
            def measure(ids):
                ix=[positions[i] for i in ids]
                return core.scores(bundle['scalars'][ix],bundle['target'][ix],scalar['mean'].numpy(),scalar['std'].numpy(),
                                   transform['center'].numpy(),transform['basis'].numpy())
            fit=measure(refit);held=measure(outer)
            ranks={axis:core.compare(fit[axis],held[axis],[cohort[i]['targetPhone'] for i in refit],[cohort[i]['targetPhone'] for i in outer]) for axis in RECIPE['axes']}
            cells.append(dict(jobId=job['id'],refitRows=refit,childOuterRows=outer,
                sourceCheckpoints=dict(scalar=job['scalarCheckpoint'],compact=job['compactCheckpoint']),transform=job['transform'],
                referenceScores={axis:fit[axis].tolist() for axis in RECIPE['axes']}))
            for k,i in enumerate(outer):
                r=cohort[i];ix=index[i]
                require(m['rowFolds'][ix]==job['speakerFold'] and m['rowWordGroups'][ix]==job['wordGroup'],'Diagnostic cell differs')
                delta=-float(np.dot(r['raterCounts'],np.asarray(m['logProbabilities'][ix])-np.asarray(b['logProbabilities'][ix]))/5)
                record=dict(rowIndex=i,speakerId=r['speakerId'],age=r['age'],clipId=r['clipId'],targetPhone=r['targetPhone'],
                    wordIndex=r['wordIndex'],phoneIndex=r['phoneIndex'],targetWord=r['targetWord'],raterCounts=r['raterCounts'],
                    speakerFold=job['speakerFold'],wordGroup=job['wordGroup'],jobId=job['id'],NLLDelta=delta,
                    scalarZ=held['scalarZ'][k].tolist(),dominantScalar=SCALAR_NAMES[int(held['dominantScalar'][k])])
                for axis in RECIPE['axes']:
                    record[axis]=dict(value=float(held[axis][k]),referencePositions=len(refit),
                        **{name:int(values[k]) if name=='samePhoneFitPositions' else float(values[k]) for name,values in ranks[axis].items()})
                rows.append(record)
            print(json.dumps(dict(job=job['id'],childPositions=len(outer))),flush=True)
        rows.sort(key=lambda r:r['rowIndex'])
        require([r['rowIndex'] for r in rows]==expected_ids and len(rows)==5654 and len({r['speakerId'] for r in rows})==52 and len({r['targetPhone'] for r in rows})==23,'Incomplete child support')
        result=summaries(rows)
        require(np.isclose(result['pooled']['meanNLLDelta'],mix['comparisons'][regime]['mixtureVsScalar']['childDelta']['NLL'],atol=2e-12),'Pooled difference differs')
        regimes[regime]=dict(rows=rows,summary=result)
    for source in plan['inputs'].values():binding(source['path'],source['sha256'])
    return dict(complete=True,plan=pin,recipe=RECIPE,**FLAGS,diagnosticCalculated=True,
                acousticAlignmentValidated=False,referenceCells=cells,regimes=regimes)


def run(path,sha,verify=False):
    plan,pin=load_plan(path,sha);root=Path(path).resolve().parent
    if not verify:write(root/'started.json',dict(plan=pin))
    try:
        value=calculate(plan,pin)
        if verify:
            require(value==json.loads((root/'report.json').read_text()),'Offline reconstruction differs')
            return dict(verified=True,report=binding(root/'report.json'))
        write(root/'report.json',value);return binding(root/'report.json')
    except Exception as exc:
        if not verify and not (root/'failure.json').exists():write(root/'failure.json',dict(error=type(exc).__name__,message=str(exc)))
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('declare','run','verify'));p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256');a=p.parse_args()
    require(a.output is not None if a.command=='declare' else a.plan is not None and a.plan_sha256 is not None,'Missing arguments')
    print(json.dumps(declare(a.output) if a.command=='declare' else run(a.plan,a.plan_sha256,a.command=='verify')))

if __name__=='__main__':main()
