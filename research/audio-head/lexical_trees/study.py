"""Run the declared tree comparison with separate selection/refit/outer barriers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
import catboost
import numpy as np
from lexical_trees import core

HEAD=Path(__file__).resolve().parents[1]
ROOT=HEAD.parents[1]
BASE=HEAD/'outputs/multiphone-20260927'
OLD=BASE/'lexical-expanded-heads-v1'
PROTOCOL=ROOT/'docs/model/lexical-trees-protocol.md'
PLAN_SHA='8acf9c21ac69ef8c1aec9518ab4a8a75b27049322d6d8fe7733a5373fb97154c'
OUTER_SHA='6bf403e910d7330db3892c7366c6a4bcd7a694927d9c4c1cd467dad2ab2515df'
FLAGS=dict(learnerFeedbackEligible=False,clinicalUseEligible=False,promotionEligible=False,independentFinalValidation=False)


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def pin(path):return dict(path=str(Path(path).resolve()),sha256=sha(path))


def read(binding):
    require(sha(binding['path'])==binding['sha256'],'Input changed: '+binding['path'])
    return json.loads(Path(binding['path']).read_text())


def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')


def word_group(word):
    require(isinstance(word,str) and word==word.upper() and len(word.split())==1,'Invalid canonical word')
    return int.from_bytes(hashlib.sha256(('cadence-lexical-holdout-v1\0'+word).encode()).digest(),'big')%5


def validate_job(job,rows,tokens):
    roles={k:job[k] for k in ('fitRows','selectionRows','refitRows','outerRows')}
    for role,ids in roles.items():
        require(bool(ids) and len(ids)==len(set(ids)) and all(type(i)is int and 0<=i<len(rows) for i in ids),'Invalid '+role)
        require(all(6<=rows[i]['age']<=12 and rows[i]['trainingEligible'] is True for i in ids),'Non-child/ineligible row')
    fit,sel,refit,outer=(set(roles[k]) for k in ('fitRows','selectionRows','refitRows','outerRows'))
    require(not fit&sel and fit|sel<=refit and not refit&outer,'Partition overlap')
    people=lambda ids:{rows[i]['speakerId'] for i in ids}
    require(not people(fit)&people(sel) and not people(refit)&people(outer),'Speaker leakage')
    require(all(rows[i]['legacyRowIndex'] is not None for i in sel|outer),'Expected original selection/outer')
    for ids in (fit,sel,refit):
        require(all(all(word_group(w)!=job['wordGroup'] for w in tokens[rows[i]['clipId']]) for i in ids),'Lexical leakage')
    require(all(word_group(rows[i]['targetWord'].upper())==job['wordGroup'] for i in outer),'Wrong outer word group')
    for ids in (fit,refit):
        require({rows[i]['targetPhone'] for i in ids}==set(core.PHONES),'Missing fitting phone')
        require(all(sum(rows[i]['raterCounts'][k] for i in ids)>0 for k in range(3)),'Missing fitting class')


def declaration():
    old=read(dict(path=str(OLD/'plan.json'),sha256=PLAN_SHA))
    freeze=read(dict(path=str(OLD/'outer-freeze.json'),sha256=OUTER_SHA))
    cohort=read(old['inputs']['cohort']);feature=read(old['inputs']['featureReport'])
    require(cohort['authorPartition']=='train' and not cohort['authorTestAudioOpened'] and feature['complete'],'Invalid source scope')
    rows=cohort['rows'];tokens={c['id']:[w['text'].upper() for w in c['words']] for c in cohort['clips']}
    jobs=[];oldjobs={j['id']:j for j in old['jobs']};refs={x['jobId']:x['artifact'] for x in freeze['predictions']}
    for depth in (4,6):
        for sf in range(5):
            for wg in range(5):
                a=oldjobs[f'child-only-scalars-s{sf}-w{wg}'];b=oldjobs[f'child-only-pca16-scalars-s{sf}-w{wg}']
                for role in ('fitRows','selectionRows','refitRows','outerRows'):
                    require(set(a[role])==set(b[role]),'Reference family memberships differ')
                job=dict(id=f'd{depth}-s{sf}-w{wg}',depth=depth,speakerFold=sf,wordGroup=wg,
                         **{k:a[k] for k in ('fitRows','selectionRows','refitRows')},
                         outerRows=[i for i in a['outerRows'] if 6<=rows[i]['age']<=12 and rows[i]['legacyRowIndex'] is not None],
                         references={family:refs[f'child-only-{family}-s{sf}-w{wg}'] for family in ('scalars','pca16-scalars')})
                validate_job(job,rows,tokens);jobs.append(job)
    expected={i for i,r in enumerate(rows) if 6<=r['age']<=12 and r['legacyRowIndex'] is not None}
    for d in (4,6):
        gathered=[i for j in jobs if j['depth']==d for i in j['outerRows']]
        require(len(gathered)==len(set(gathered))==5654 and set(gathered)==expected,'Incomplete child outcomes')
    sources={str(p):sha(p) for p in Path(__file__).parent.glob('*.py')}
    return dict(schemaVersion=1,jobs=jobs,recipe=core.RECIPE,stages=list(core.STAGES),
                inputs=dict(parentPlan=dict(path=str(OLD/'plan.json'),sha256=PLAN_SHA),
                            parentOuterFreeze=dict(path=str(OLD/'outer-freeze.json'),sha256=OUTER_SHA),
                            cohort=old['inputs']['cohort'],scalars=feature['inputs']['scalars'],
                            protocol=pin(PROTOCOL),environmentLock=pin(ROOT/'work/model-quality-goal-20260927/trees-requirements.lock.txt')),
                sourceBindings=sources,runtime=dict(python=platform.python_version(),numpy=np.__version__,catboost=catboost.__version__,device='cpu'),
                positions=5654,children=52,materialGain=dict(relativeNllReduction=.05,absoluteRating0ApGain=.01),
                outerSelectedModelAllowed=False,authorTestRead=False,**FLAGS)


def load_plan(path,digest):
    plan=read(dict(path=str(Path(path).resolve()),sha256=digest))
    require(plan==declaration(),'Study declaration/source changed')
    for binding in plan['inputs'].values():require(sha(binding['path'])==binding['sha256'],'Changed declared input')
    cohort=read(plan['inputs']['cohort']);rows=cohort['rows']
    scalars=np.load(plan['inputs']['scalars']['path'],allow_pickle=False)
    ids=np.asarray([r['targetId'] for r in rows],dtype=np.int64)
    x=core.features(scalars,ids);counts=np.asarray([r['raterCounts'] for r in rows],dtype=np.int64)
    core.validate_counts(counts,len(rows))
    return plan,rows,x,counts


def check_review(path,digest):
    review=json.loads(Path(path).read_text())
    require(review['status']=='clear' and not review['blockingFindings'] and review['planSha256']==digest,'Matching review required')
    for p,d in review['sourceBindings'].items():require(sha(p)==d,'Reviewed source changed')


def artifact_files(path):return {p.name:pin(p) for p in sorted(Path(path).iterdir()) if p.is_file()}


def checked_freeze(path,digest,plan_digest,phase,jobs):
    value=read(dict(path=str(path),sha256=digest))
    require(value['complete'] and value['phase']==phase and value['planSha256']==plan_digest,'Wrong phase freeze')
    require([r['jobId'] for r in value['runs']]==[j['id'] for j in jobs],'Incomplete phase freeze')
    for run in value['runs']:
        for binding in run['files'].values():require(sha(binding['path'])==binding['sha256'],'Changed frozen artifact')
    return value


def train_phase(args,phase):
    plan,rows,x,counts=load_plan(args.plan,args.sha256);check_review(args.review,args.sha256)
    out=args.plan.resolve().parent
    require(not (out/phase).exists(),'Phase output exists; preserve partial work and inspect before recovery')
    previous=None
    if phase=='refit':previous=checked_freeze(out/'inner-freeze.json',args.inner_sha256,args.sha256,'inner',plan['jobs'])
    (out/phase).mkdir();runs=[];started=time.monotonic()
    for index,job in enumerate(plan['jobs']):
        ids=job['fitRows'] if phase=='inner' else job['refitRows'];dest=out/phase/job['id']
        trees=400 if phase=='inner' else previous['runs'][index]['selectedTrees']
        print(json.dumps(dict(phase=phase,job=job['id'],number=index+1,of=50,positions=len(ids),trees=trees)),flush=True)
        model,receipt=core.fit_model(x[ids],counts[ids],dest,depth=job['depth'],iterations=trees)
        write(dest/'membership.json',dict(jobId=job['id'],phase=phase,fitRows=ids,planSha256=args.sha256,
                                        originalPositions=len(ids),raterCounts=counts[ids].sum(0).tolist(),**FLAGS))
        run=dict(jobId=job['id'])
        if phase=='inner':
            selection=job['selectionRows'];values=[];losses=[]
            for stage in core.STAGES:
                lp=core.log_probabilities(model,x[selection],trees=stage);values.append(lp)
                losses.append((stage,core.nll(lp,counts[selection])))
            selected=core.choose_stage(losses)
            require(selected in core.STAGES,'Invalid selected tree count')
            np.savez(dest/'selection.npz',rowIndices=np.asarray(selection),raterCounts=counts[selection],
                     stages=np.asarray(core.STAGES),logProbabilities=np.stack(values))
            write(dest/'selection.json',dict(stageLosses=losses,selectedTrees=selected,selectionRows=selection))
            run['selectedTrees']=selected
        else:
            # Saved-state replay on refit inputs, never an efficacy score.
            reloaded=core.load_model(dest/'model.cbm');selected=trees
            for chunk in range(0,len(ids),1024):
                xx=x[ids[chunk:chunk+1024]]
                require(np.array_equal(core.log_probabilities(model,xx),core.log_probabilities(reloaded,xx)),'Refit state replay differs')
            run.update(selectedTrees=selected,exactSavedStateReplay=True)
        run['files']=artifact_files(dest);runs.append(run)
        # A durable progress ledger is not a phase-completion certificate.
        temp=out/(phase+'-progress.tmp');temp.write_text(json.dumps(dict(phase=phase,complete=False,runs=runs)))
        temp.replace(out/(phase+'-progress.json'))
    require(plan==declaration(),'Sources changed during fitting')
    result=dict(complete=True,phase=phase,planSha256=args.sha256,runs=runs,wallSeconds=time.monotonic()-started,
                outerPredictionsRead=False,**FLAGS)
    if previous:result['innerFreeze']=dict(path=str(out/'inner-freeze.json'),sha256=args.inner_sha256)
    write(out/(phase+'-freeze.json'),result);print(json.dumps(pin(out/(phase+'-freeze.json'))),flush=True)


def outer(args):
    plan,rows,x,counts=load_plan(args.plan,args.sha256);out=args.plan.resolve().parent
    previous=checked_freeze(out/'refit-freeze.json',args.refit_sha256,args.sha256,'refit',plan['jobs'])
    require(not(out/'outer').exists(),'Outer outputs already exist');(out/'outer').mkdir();runs=[]
    for job,run in zip(plan['jobs'],previous['runs'],strict=True):
        model=core.load_model(run['files']['model.cbm']['path']);ids=job['outerRows']
        lp=core.log_probabilities(model,x[ids]);path=out/'outer'/(job['id']+'.npz')
        np.savez(path,rowIndices=np.asarray(ids),raterCounts=counts[ids],logProbabilities=lp,probabilities=np.exp(lp))
        runs.append(dict(jobId=job['id'],artifact=pin(path),model=run['files']['model.cbm']))
    write(out/'outer-freeze.json',dict(complete=True,phase='outer',planSha256=args.sha256,
          refitFreeze=dict(path=str(out/'refit-freeze.json'),sha256=args.refit_sha256),runs=runs,**FLAGS))
    print(json.dumps(pin(out/'outer-freeze.json')))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('declare');d.add_argument('--output',type=Path,required=True)
    for name in ('inner','refit','outer'):
        t=sub.add_parser(name);t.add_argument('--plan',type=Path,required=True);t.add_argument('--sha256',required=True)
        if name!='outer':t.add_argument('--review',type=Path,required=True)
        if name=='refit':t.add_argument('--inner-sha256',required=True)
        if name=='outer':t.add_argument('--refit-sha256',required=True)
    a=p.parse_args()
    if a.command=='declare':
        require(not a.output.exists() and a.output.resolve().is_relative_to(BASE),'Fresh research output required')
        value=declaration();a.output.mkdir(parents=True);write(a.output/'plan.json',value);print(json.dumps(pin(a.output/'plan.json')))
    elif a.command=='outer':outer(a)
    else:train_phase(a,a.command)


if __name__=='__main__':main()
