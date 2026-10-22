"""Declared inner/refit/outer projection-only correction of frozen PCA heads."""
from __future__ import annotations
import argparse
import hashlib
import copy
import json
from pathlib import Path
import sys
import numpy as np
import torch
from lexical_projection import core
from lexical_mixture import study as prior
from lexical_uncertainty import study as storage

ROOT=storage.ROOT;BASE=storage.BASE;DIRECTORY=Path(__file__).resolve().parent
PROTOCOL=ROOT/'docs/model/multiphone-lexical-projection-protocol.md'
require=storage.require;read=storage.read;binding=storage.binding;write=storage.write
FLAGS=dict(authorTestRead=False,encoderInferencePerformed=False,calibrationFittingPerformed=False,
           independentFinalValidation=False,clinicalUseEligible=False,learnerFeedbackEligible=False,promotionEligible=False)


def inputs():
    pins,_=prior.inputs();cp=read(pins['compactPlan'])
    outer=read(pins['compactOuter']);refit=read(outer['refitFreeze']);inner=read(refit['innerFreeze'])
    pins=dict(pins,compactRefit=outer['refitFreeze'],compactInner=refit['innerFreeze'],
        projectionProtocol=binding(PROTOCOL),storageSource=binding(Path(storage.__file__)),
        mixturePlan=binding(BASE/'lexical-mixture-v1/plan.json',storage.PLAN_SHA),
        mixtureReport=binding(storage.MIX_REPORT,storage.REPORT_SHA))
    ir={r['jobId']:r for r in inner['runs']};rr={r['jobId']:r for r in refit['runs']};op={v['jobId']:v['artifact'] for v in outer['predictions']}
    jobs=[]
    for old in cp['jobs']:
        job={k:old[k] for k in ('regime','speakerFold','wordGroup','fitRows','selectionRows','refitRows','outerRows')}
        job.update(id=old['id'].replace('pca16-scalars','projection'),sourceJobId=old['id'],sourceOuter=op[old['id']])
        for phase,runs in [('Inner',ir),('Refit',rr)]:
            artifacts=runs[old['id']]['artifacts']
            job['source'+phase]={key:artifacts[name] for key,name in [('checkpoint','best.pt'),('transform','transform.pt'),('config','config.json')]}
            if phase=='Inner':job['sourceSelection']=artifacts['selection.json']
            for key,pin in job['source'+phase].items():pins[job['id']+'/'+phase+'/'+key]=binding(pin['path'],pin['sha256'])
        pins[job['id']+'/sourceSelection']=binding(job['sourceSelection']['path'],job['sourceSelection']['sha256'])
        jobs.append(job)
    for path in sorted(DIRECTORY.glob('*.py')):pins['projectionSource/'+path.name]=binding(path)
    for pin in pins.values():binding(pin['path'],pin['sha256'])
    return pins,jobs


def plan_value(pins,jobs):
    return dict(inputs=pins,jobs=jobs,recipe=core.RECIPE,**FLAGS,trainingPerformed=False,
                runtime=dict(python=sys.version,numpy=np.__version__,torch=torch.__version__,executable=binding(sys.executable)))


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(BASE),'Fresh ignored output required')
    pins,jobs=inputs();value=plan_value(pins,jobs);output.mkdir(parents=True,mode=0o700);write(output/'plan.json',value)
    return binding(output/'plan.json')


def load_plan(path,sha,bundle=False):
    pin=binding(path,sha);plan=read(pin);pins,jobs=inputs();require(plan==plan_value(pins,jobs),'Projection declaration differs')
    return plan,pin,prior.compact.inputs()[2] if bundle else None


def prepared(bundle,job,phase):
    source=job['sourceInner' if phase=='inner' else 'sourceRefit']
    return core.prepare(bundle,source['checkpoint'],source['transform'],source['config'],job['fitRows' if phase=='inner' else 'refitRows'])


def config_value(job,pin,phase,selection=None):
    return dict(experiment='canonical-lexical-projection-v1',jobId=job['id'],regime=job['regime'],speakerFold=job['speakerFold'],
        wordGroup=job['wordGroup'],plan=pin,innerSelection=selection,**FLAGS)


def artifacts(directory):
    return {p.name:binding(p) for p in sorted(Path(directory).iterdir()) if p.is_file() and p.name!='report.json'} | {'report.json':binding(Path(directory)/'report.json')}


def history_state(history,cfg,rows):
    require(1<=len(history)<=21 and [h['epoch'] for h in history]==list(range(len(history))),'Invalid epoch history')
    rng=np.random.default_rng(7);updates=(len(cfg['fitRows'])+63)//64;best=0;loss=None;states=[]
    for epoch,entry in enumerate(history):
        if epoch==0:
            require(entry['updates']==entry['totalUpdates']==0 and entry['orderSha256'] is None and entry['trainLoss'] is None,'Invalid epoch zero')
        else:
            order=rng.permutation(cfg['fitRows']).tolist()
            digest=hashlib.sha256(json.dumps(order,separators=(',',':')).encode()).hexdigest()
            require(entry['orderSha256']==digest and entry['updates']==updates and entry['totalUpdates']==epoch*updates
                    and np.isfinite(entry['trainLoss']),'Training order/update history differs')
        if cfg['phase']=='inner':
            p=entry['selection'];ids=cfg['selectionRows'];require(p['rowIndices']==ids,'Selection row identity differs')
            lp=np.asarray(p['logProbabilities'],dtype=float);pp=np.asarray(p['probabilities'],dtype=float);raw=np.asarray(p['rawProbabilities'],dtype=float)
            counts=np.asarray([rows[i]['raterCounts'] for i in ids],dtype=float)
            require(lp.shape==pp.shape==raw.shape==counts.shape and len(ids)>0 and np.isfinite(lp).all() and np.isfinite(pp).all()
                    and np.isfinite(raw).all() and (pp>=0).all() and (raw>=0).all()
                    and np.allclose(np.exp(lp),pp,atol=0,rtol=3e-13) and np.allclose(pp.sum(1),1,atol=1e-12,rtol=0)
                    and np.allclose(raw,pp,atol=2e-7,rtol=2e-6),'Invalid selection probabilities')
            current=float(-(counts*lp).sum()/(5*len(ids)))
            require(p['NLL']==current,'Selection NLL differs from stable logs')
            if loss is None or current<loss-1e-7:best=epoch;loss=current
            require(epoch==len(history)-1 or epoch-best<5,'Training continued beyond patience')
        else:
            require('selection' not in entry,'Refit contains selection');best=epoch
        states.append(dict(bestEpoch=best,bestLoss=loss,permutation=copy.deepcopy(rng.bit_generator.state)))
    if cfg['phase']=='inner':require(len(history)-1==20 or len(history)-1-best==5,'Stopping policy differs')
    else:require(len(history)-1==cfg['fixedEpochs'],'Fixed epoch budget differs')
    return states,updates


def check_run(job,run,pin,phase,rows):
    require(run['jobId']==job['id'],'Wrong run ID')
    for asset in run['artifacts'].values():binding(asset['path'],asset['sha256'])
    a=run['artifacts'];cfg=read(a['config.json']);history=read(a['history.json']);report=read(a['report.json'])
    source=job['sourceInner' if phase=='inner' else 'sourceRefit']
    require(cfg['plan']==pin and cfg['jobId']==job['id'] and cfg['recipe']==core.RECIPE
        and cfg['sourceBindings']==source and cfg['fitRows']==job['fitRows' if phase=='inner' else 'refitRows']
        and cfg['selectionRows']==(job['selectionRows'] if phase=='inner' else []) and cfg['phase']==phase
        and all(cfg[k]==job[k] for k in ('regime','speakerFold','wordGroup')),'Run configuration differs')
    states,updates=history_state(history,cfg,rows);best=states[-1]['bestEpoch'];loss=states[-1]['bestLoss'];epochs=len(history)-1
    require(report['complete'] and report['phase']==phase and report['bestEpoch']==run['selectedEpoch']==best
        and report['epochsRun']==epochs and report['bestLoss']==loss and report['totalUpdates']==epochs*updates
        and report['configSha256']==a['config.json']['sha256'] and report['sourceBindings']==source
        and report['fitRows']==cfg['fitRows'] and report['selectionRows']==cfg['selectionRows']
        and all(a.get(name)==asset for name,asset in report['artifacts'].items()),'Run report binding differs')
    if phase=='inner':
        require(history[0]['selection']==read(job['sourceSelection']),'Initial selection does not match compact')
        require(read(a['selection.json'])==history[best]['selection'],'Selected prediction differs')
    original=torch.load(source['checkpoint']['path'],map_location='cpu',weights_only=True)
    for name,epoch in [('initial.pt',0),('best.pt',best),('last.pt',epochs)]:
        state=torch.load(a[name]['path'],map_location='cpu',weights_only=True);expected=states[epoch]
        require(state['configSha256']==a['config.json']['sha256'] and state['epoch']==epoch and state['sourceBindings']==source
            and state['totalUpdates']==epoch*updates and state['bestEpoch']==expected['bestEpoch'] and state['bestLoss']==expected['bestLoss']
            and state['rng']['numpyPermutation']==expected['permutation'] and torch.equal(state['mean'],original['mean'])
            and torch.equal(state['std'],original['std']),'Adaptation checkpoint lineage differs')
        require(state['delta'].shape==(1024,16) and state['delta'].dtype==torch.float64 and torch.isfinite(state['delta']).all(),'Invalid correction state')
        optimizer=state['optimizer'];require(len(optimizer['param_groups'])==1,'Wrong optimizer groups');group=optimizer['param_groups'][0]
        require(group['lr']==.0001 and group['weight_decay']==.01 and group['betas']==(.9,.999) and group['eps']==1e-8 and group['params']==[0],'Optimizer recipe differs')
        if epoch==0:require(torch.count_nonzero(state['delta']).item()==0 and optimizer['state']=={},'Invalid initial correction/optimizer')
        else:
            require(set(optimizer['state'])=={0},'Wrong optimizer state');opt=optimizer['state'][0]
            require(float(opt['step'])==epoch*updates and all(opt[k].shape==(1024,16) and opt[k].dtype==torch.float64 and torch.isfinite(opt[k]).all() for k in ('exp_avg','exp_avg_sq')),'Optimizer counters/moments differ')
    return cfg


def check_freeze(plan,pin,path,sha,phase):
    asset=binding(path,sha);value=read(asset)
    require(value['complete'] and value['plan']==pin and value['phase']==phase
        and [r['jobId'] for r in value['runs']]==[j['id'] for j in plan['jobs']],'Incomplete/wrong phase freeze')
    rows=read(plan['inputs']['cohort'])['rows']
    for job,run in zip(plan['jobs'],value['runs'],strict=True):check_run(job,run,pin,phase,rows)
    if phase=='outer-refit':
        selected,_=check_freeze(plan,pin,value['innerFreeze']['path'],value['innerFreeze']['sha256'],'inner')
        for job,run,old in zip(plan['jobs'],value['runs'],selected['runs'],strict=True):
            require(run['selectedEpoch']==old['selectedEpoch'],'Refit differs from frozen epoch')
            require(read(run['artifacts']['config.json'])['innerSelection']==dict(freeze=value['innerFreeze'],checkpoint=old['artifacts']['best.pt'],epoch=old['selectedEpoch']),'Selection linkage differs')
    return value,asset


def fit(path,sha,phase,freeze_path=None,freeze_sha=None):
    plan,pin,bundle=load_plan(path,sha,True);root=Path(path).resolve().parent
    selected=None;inner_pin=None
    if phase=='outer-refit':selected,inner_pin=check_freeze(plan,pin,freeze_path,freeze_sha,'inner')
    write(root/(phase+'-started.json'),dict(plan=pin,innerFreeze=inner_pin));runs=[]
    try:
        for k,job in enumerate(plan['jobs']):
            data=prepared(bundle,job,phase);source=None;epochs=None
            if selected is not None:
                old=selected['runs'][k];epochs=old['selectedEpoch'];source=dict(freeze=inner_pin,checkpoint=old['artifacts']['best.pt'],epoch=epochs)
            else:require(core.predict(data,job['selectionRows'])==read(job['sourceSelection']),'Zero-delta source selection replay failed')
            dest=root/phase/job['id']
            core.train(data,job['selectionRows'] if phase=='inner' else [],dest,config_value(job,pin,phase,source),epochs=epochs)
            aa=artifacts(dest);report=read(aa['report.json']);run=dict(jobId=job['id'],selectedEpoch=report['bestEpoch'],artifacts=aa)
            check_run(job,run,pin,phase,bundle['cohort']['rows']);runs.append(run)
            print(json.dumps(dict(phase=phase,job=job['id'],selectedEpoch=run['selectedEpoch'],epochsRun=report['epochsRun'])),flush=True)
        for a in plan['inputs'].values():binding(a['path'],a['sha256'])
        write(root/(phase+'-freeze.json'),dict(complete=True,plan=pin,phase=phase,innerFreeze=inner_pin,runs=runs,trainingPerformed=True,outerInferencePerformed=False,**FLAGS))
        return binding(root/(phase+'-freeze.json'))
    except Exception as exc:
        write(root/(phase+'-failure.json'),dict(error=str(exc),completedJobs=[r['jobId'] for r in runs]));raise


def outer(path,sha,freeze_path,freeze_sha):
    plan,pin,bundle=load_plan(path,sha,True);frozen,fp=check_freeze(plan,pin,freeze_path,freeze_sha,'outer-refit')
    root=Path(path).resolve().parent;write(root/'outer-started.json',dict(plan=pin,refitFreeze=fp));values=[]
    try:
        for job,run in zip(plan['jobs'],frozen['runs'],strict=True):
            data=prepared(bundle,job,'outer-refit');source=read(job['sourceOuter'])
            require(core.predict(data,job['outerRows'])==source['prediction'],'Zero-delta outer replay differs')
            pred=core.replay(Path(run['artifacts']['best.pt']['path']).parent,data,job['outerRows'])
            value=dict(jobId=job['id'],prediction=pred,prior=source['prior'],sourceOuter=job['sourceOuter'],
                       checkpoint=run['artifacts']['best.pt'],zeroDeltaSourceReplayExact=True,headInferencePerformed=True,**FLAGS)
            dest=root/'outer'/(job['id']+'.json');dest.parent.mkdir(exist_ok=True);write(dest,value)
            values.append(dict(jobId=job['id'],artifact=binding(dest)));print(json.dumps(dict(outerComplete=job['id'])),flush=True)
        for a in plan['inputs'].values():binding(a['path'],a['sha256'])
        write(root/'outer-freeze.json',dict(complete=True,plan=pin,refitFreeze=fp,predictions=values,trainingPerformed=False,outerInferencePerformed=True,**FLAGS))
        return binding(root/'outer-freeze.json')
    except Exception as exc:
        write(root/'outer-failure.json',dict(error=str(exc),completedJobs=[v['jobId'] for v in values]));raise


def calculate(plan,pin,freeze_path,freeze_sha):
    fp=binding(freeze_path,freeze_sha);frozen=read(fp)
    require(frozen['complete'] and frozen['plan']==pin and [v['jobId'] for v in frozen['predictions']]==[j['id'] for j in plan['jobs']],'Incomplete outer freeze')
    refits,_=check_freeze(plan,pin,frozen['refitFreeze']['path'],frozen['refitFreeze']['sha256'],'outer-refit')
    jobs={j['id']:j for j in plan['jobs']};rr={r['jobId']:r for r in refits['runs']}
    corpus=read(plan['inputs']['cohort'])['rows'];eligible=[i for i,r in enumerate(corpus) if r['trainingEligible']]
    compact=read(plan['inputs']['compactReport']);baseline=read(plan['inputs']['baselineReport']);mixture=read(plan['inputs']['mixtureReport'])
    models={};contrasts={}
    for regime in ('all-age','child-only'):
        merged={};cells=[]
        for source in frozen['predictions']:
            job=jobs[source['jobId']]
            if job['regime']!=regime:continue
            v=read(source['artifact']);p=v['prediction'];ids=job['outerRows']
            require(v['jobId']==job['id'] and v['checkpoint']==rr[job['id']]['artifacts']['best.pt'] and p['rowIndices']==ids and v['zeroDeltaSourceReplayExact'],'Outer lineage differs')
            rows=[corpus[i] for i in ids]
            cells.append(dict(speakerFold=job['speakerFold'],wordGroup=job['wordGroup'],rowIndices=ids,summary=prior.compact.summarize(p,rows)))
            for i,prob,log in zip(ids,p['probabilities'],p['logProbabilities'],strict=True):
                require(i not in merged,'Duplicate outer row');merged[i]=(prob,log,job['speakerFold'],job['wordGroup'])
        require(sorted(merged)==eligible and len(cells)==25,'Incomplete outer coverage')
        full=dict(rowIndices=eligible,probabilities=[merged[i][0] for i in eligible],logProbabilities=[merged[i][1] for i in eligible])
        folds=[]
        for fold in range(5):
            ids=[i for i in eligible if merged[i][2]==fold];pred=dict(probabilities=[merged[i][0] for i in ids],logProbabilities=[merged[i][1] for i in ids])
            folds.append(dict(speakerFold=fold,rowIndices=ids,summary=prior.compact.summarize(pred,[corpus[i] for i in ids])))
        candidate=dict(**full,rowFolds=[merged[i][2] for i in eligible],rowWordGroups=[merged[i][3] for i in eligible],cells=cells,speakerFolds=folds,pooled=prior.compact.summarize(full,[corpus[i] for i in eligible]))
        refs=dict(compact=compact['models'][regime],scalar=baseline['models'][regime]['scalars'],mixture=mixture['models'][regime],prior=baseline['models'][regime]['prior'])
        for ref in refs.values():prior.compact.check_reference_identity(candidate,ref)
        models[regime]=candidate;contrasts[regime]={name:prior.compact.consistency(candidate,refs[name]) for name in ('compact','scalar','mixture')}
        contrasts[regime]['minusPrior']=prior.compact.primary_delta(candidate['pooled'],refs['prior']['pooled'])
    for a in plan['inputs'].values():binding(a['path'],a['sha256'])
    return dict(complete=True,plan=pin,outerFreeze=fp,models=models,comparisons=contrasts,trainingPerformed=False,**FLAGS)


def audit(path,sha,freeze_path,freeze_sha,verify=False):
    plan,pin,_=load_plan(path,sha);root=Path(path).resolve().parent
    if not verify:write(root/'audit-started.json',dict(plan=pin))
    report=calculate(plan,pin,freeze_path,freeze_sha)
    if verify:
        require(report==json.loads((root/'report.json').read_text()),'Offline report differs');return dict(verified=True,report=binding(root/'report.json'))
    write(root/'report.json',report);return binding(root/'report.json')


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('declare','inner','refit','outer','audit','verify'));p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--plan-sha256');p.add_argument('--freeze',type=Path);p.add_argument('--freeze-sha256');a=p.parse_args()
    if a.command=='declare':require(a.output is not None,'Output required');result=declare(a.output)
    else:
        require(a.plan is not None and a.plan_sha256 is not None,'Plan required')
        if a.command!='inner':require(a.freeze is not None and a.freeze_sha256 is not None,'Freeze required')
        if a.command in ('inner','refit'):result=fit(a.plan,a.plan_sha256,'inner' if a.command=='inner' else 'outer-refit',a.freeze,a.freeze_sha256)
        elif a.command=='outer':result=outer(a.plan,a.plan_sha256,a.freeze,a.freeze_sha256)
        else:result=audit(a.plan,a.plan_sha256,a.freeze,a.freeze_sha256,a.command=='verify')
    print(json.dumps(result))

if __name__=='__main__':main()
