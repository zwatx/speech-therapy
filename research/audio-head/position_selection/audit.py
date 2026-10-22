"""Selection-set diagnostics and separately frozen held-out development audit."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
import torch

from position_selection import study as s

p=s.previous
binding,guard,read_bound,require,write_new=s.binding,s.guard,s.read_bound,s.require,s.write_new


def reliability(probabilities, rows):
    """Per-phone marginal prediction bias, not an unbiased calibration estimate."""
    result={};probabilities=np.asarray(probabilities,dtype=np.float64)
    require(probabilities.shape==(len(rows),3),'Reliability prediction count differs')
    for population,pmask in p.populations(rows).items():
        ages={}
        for age,condition in (('allAges',lambda r:True),('ages6to12',p.is_child),('ages13plus',lambda r:r['age']>=13)):
            cells={}
            for phone in p.metrics.PHONES:
                mask=pmask & np.array([condition(r) and r['targetPhone']==phone for r in rows])
                if not mask.any():cells[phone]=None;continue
                selected=[r for r,keep in zip(rows,mask,strict=True) if keep]
                counts=np.array([r['raterCounts'] for r in selected],dtype=np.float64)
                observed=(counts/5).mean(0);predicted=probabilities[mask].mean(0)
                loss=s.distribution_metrics(probabilities[mask],counts)
                cells[phone]=dict(positions=len(selected),speakers=len({r['speakerId'] for r in selected}),
                    votes=counts.sum(0).astype(int).tolist(),observedClassFrequency=observed.tolist(),
                    meanProbability=predicted.tolist(),classMarginalBias=(predicted-observed).tolist(),
                    rating0Bias=float(predicted[0]-observed[0]),below2Bias=float(predicted[:2].sum()-observed[:2].sum()),
                    metrics=loss)
            ages[age]=cells
        result[population]=ages
    return result


def diagnostics(path,sha,freeze_path,freeze_sha,output):
    torch.set_num_threads(2);plan,pin=s.load_plan(path,sha);cohort,values=s.load_data(plan)
    freeze,freeze_pin=s.load_inner(plan,pin,freeze_path,freeze_sha,cohort)
    root=Path(output).resolve();require(root.is_relative_to(s.HERE/'outputs') and not root.exists(),'Fresh diagnostics output required')
    root.mkdir(mode=0o700);records=[]
    write_new(root/'config.json',dict(plan=pin,innerFreeze=freeze_pin,selectionSetDiagnostic=True,independentCalibration=False))
    try:
        for selected in freeze['selected']:
            trial=read_bound(selected['trial']);config=read_bound(trial['config']);job=config['job']
            original=next(o for o in plan['originals'] if o['regime']==job['regime'] and o['fold']==job['fold'])
            held=job['validationRows'];rows=[cohort['rows'][i] for i in held]
            old_vocabulary=[cohort['rows'][i] for i in original['fitRows']]
            common=p.metrics.lexical_mask(rows,old_vocabulary)
            expanded_data=p.prepare(cohort,values,job['fitRows'])
            expanded=s.checked_model(trial['selected']['checkpoint'],trial['config'],pin,expanded_data,job['lr'],trial['bestEpoch'])
            expanded_p=p.predict(expanded,expanded_data,held)
            require(np.array_equal(expanded_p,np.load(trial['selected']['predictions']['path'],allow_pickle=False)), 'Selected inner predictions differ')
            old_data=p.prepare(cohort,values,original['fitRows']);old_config=read_bound(original['files']['config.json'])
            old_report=read_bound(original['files']['report.json'])
            state=torch.load(original['files']['best.pt']['path'],map_location='cpu',weights_only=True)
            require(state['configSha256']==original['files']['config.json']['sha256'] and state['epoch']==old_report['bestEpoch']
                    and torch.equal(state['mean'],old_data['mean']) and torch.equal(state['std'],old_data['std']), 'Original inner lineage/moments differ')
            old_model=p.head.make_model(s.args(old_config['lr']),1037);old_model.load_state_dict(state['model'],strict=True)
            old_saved=read_bound(original['files']['predictions.json'])
            require(old_saved['rowIndices']==old_config['validationRows'] and np.array_equal(
                p.predict(old_model,old_data,original['validationRows']),np.array(old_saved['probabilities'])), 'Original inner replay differs')
            old_p=p.predict(old_model,old_data,held)
            for arm,probabilities,checkpoint in (('original',old_p,original['files']['best.pt']),('expanded',expanded_p,trial['selected']['checkpoint'])):
                prediction=dict(rowIndices=held,probabilities=probabilities.tolist(),seenInFitVocabulary=common.tolist(),checkpoint=checkpoint)
                records.append(write_new(root/f"{job['regime']}-{arm}-f{job['fold']}.json",dict(
                    regime=job['regime'],fold=job['fold'],arm=arm,prediction=prediction,
                    summary=p.summaries(prediction,cohort),reliability=reliability(probabilities,rows))))
            print(json.dumps(dict(innerDiagnostic=job['regime'],fold=job['fold'])),flush=True)
        guard(plan['inputs'])
        return write_new(root/'report.json',dict(complete=True,plan=pin,innerFreeze=freeze_pin,records=records,
            selectionSetDiagnostic=True,overlappingValidationSpeakers=True,independentCalibration=False,
            causalExplanationEstablished=False,learnerFeedbackEligible=False))
    except Exception as error:
        write_new(root/'failure.json',dict(errorType=type(error).__name__,message=str(error)));raise


def load_outer(plan,pin,freeze_path,freeze_sha,cohort):
    freeze_pin=binding(freeze_path,freeze_sha);freeze=read_bound(freeze_pin)
    require(freeze['complete'] is True and freeze['plan']==pin and freeze['outerPredictionsComputed'] is False
            and len(freeze['runs'])==10,'Complete ten-model outer freeze required')
    inner,_=s.load_inner(plan,pin,freeze['innerFreeze']['path'],freeze['innerFreeze']['sha256'],cohort)
    runs=[read_bound(v) for v in freeze['runs']]
    require([(r['regime'],r['fold']) for r in runs]==[(r['regime'],r['fold']) for r in inner['selected']], 'Frozen outer coverage differs')
    for run,selection in zip(runs,inner['selected'],strict=True):
        config=read_bound(run['config']);require(config['plan']==pin and config['selection']==selection
            and config['innerFreeze']==freeze['innerFreeze'] and run['outerPredictionsComputed'] is False,'Outer selection binding differs')
        expected=next(j for j in plan['jobs'] if j['regime']==selection['regime'] and j['fold']==selection['fold'] and j['lr']==selection['lr'])
        require(config['job']==expected,'Outer job differs');guard({k:run[k] for k in ('checkpoint','history')})
    return freeze,freeze_pin,runs


def outer(path,sha,freeze_path,freeze_sha,output):
    torch.set_num_threads(2);plan,pin=s.load_plan(path,sha);cohort,values=s.load_data(plan)
    freeze,freeze_pin,runs=load_outer(plan,pin,freeze_path,freeze_sha,cohort)
    root=Path(output).resolve();require(root.is_relative_to(s.HERE/'outputs') and not root.exists(),'Fresh outer audit output required')
    root.mkdir(mode=0o700);artifacts=[];predictions=defaultdict(list);summaries=defaultdict(list)
    write_new(root/'config.json',dict(plan=pin,outerFreeze=freeze_pin,previouslyUsedDevelopmentCohort=True,learnerFeedbackEligible=False))
    try:
        for run in runs:
            config=read_bound(run['config']);job=config['job'];selection=config['selection']
            selected_data=p.prepare(cohort,values,job['outerFitRows'])
            require(config['prior']==selected_data['priors'],'Outer fit prior differs')
            model=s.checked_model(run['checkpoint'],run['config'],pin,selected_data,job['lr'],selection['epochs'])
            require(len(read_bound(run['history']))==selection['epochs'],'Outer fixed epoch count differs')
            candidates=[('selected',model,selected_data,run['checkpoint'],job['outerFitRows'])]
            for arm in ('original','expanded'):
                control=next(c for c in plan['controls'] if c['job']['regime']==job['regime'] and c['job']['fold']==job['fold'] and c['job']['arm']==arm)
                cj,cr=control['job'],control['run'];cc=read_bound(cr['config'])
                require(cj['holdoutRows']==job['holdoutRows'] and cj['commonVocabularyFitRows']==job['commonVocabularyFitRows'],'Control population/vocabulary differs')
                data=p.prepare(cohort,values,cj['fitRows']);require(cc['prior']==data['priors'],'Control prior differs')
                control_model=s.checked_model(cr['checkpoint'],cr['config'],plan['inputs']['previousPlan'],data,cj['args']['lr'],cj['epochs'])
                if arm=='original':p.historical_parity(cj,data,control_model,read_bound(cr['history']))
                if arm=='expanded' and job['lr']==cj['args']['lr'] and selection['epochs']==cj['epochs']:
                    p.historical_parity({'historical':{'checkpoint.pt':cr['checkpoint'],'history.json':cr['history']}},selected_data,model,read_bound(run['history']))
                candidates.append((arm,control_model,data,cr['checkpoint'],cj['fitRows']))
            held=job['holdoutRows'];rows=[cohort['rows'][i] for i in held]
            common=p.metrics.lexical_mask(rows,[cohort['rows'][i] for i in job['commonVocabularyFitRows']])
            for arm,network,data,checkpoint,fit in candidates:
                probability=p.predict(network,data,held)
                require(np.array_equal(probability,p.predict(network,data,held)),'Repeated outer prediction differs')
                prior=np.array([data['priors'][r['targetPhone']]['probabilities'] for r in rows])
                prediction=dict(rowIndices=held,probabilities=probability.tolist(),seenInFitVocabulary=common.tolist(),
                    seenInActualFitVocabulary=p.metrics.lexical_mask(rows,[cohort['rows'][i] for i in fit]).tolist(),
                    priorProbabilities=prior.tolist(),checkpoint=checkpoint)
                summary=p.summaries(prediction,cohort);key=job['regime']+'/'+arm
                predictions[key].append(prediction);summaries[key].append(summary)
                artifacts.append(write_new(root/f"{job['regime']}-{arm}-f{job['fold']}.json",dict(
                    regime=job['regime'],fold=job['fold'],arm=arm,prediction=prediction,summary=summary,priorSummary=p.summaries(prediction,cohort,prior))))
            print(json.dumps(dict(outerAudit=job['regime'],fold=job['fold'])),flush=True)
        pooled,pins={},{}
        for key,folds in predictions.items():
            prediction=p.metrics.pool_predictions(folds,list(range(28227)));pooled[key]=p.summaries(prediction,cohort)
            prior=p.metrics.pool_predictions([{**f,'probabilities':f['priorProbabilities']} for f in folds],list(range(28227)))
            pins[key]=write_new(root/(key.replace('/','-')+'-pooled.json'),dict(prediction=prediction,summary=pooled[key],
                priorPrediction=prior,priorSummary=p.summaries(prior,cohort)))
        comparisons={}
        for regime in p.REGIMES:
            comparisons[regime]={}
            for left,right in (('selected','original'),('selected','expanded'),('expanded','original')):
                a,b=regime+'/'+left,regime+'/'+right
                contrast={pop:dict(pooled=p.metrics.contrast(pooled[a][pop],pooled[b][pop]),
                    folds=[p.metrics.contrast(x[pop],y[pop]) for x,y in zip(summaries[a],summaries[b],strict=True)]) for pop in ('original','all','added')}
                comparisons[regime][left+'-vs-'+right]=dict(populations=contrast,
                    decision=p.decision(contrast) if right=='original' else None)
        guard(plan['inputs'])
        return write_new(root/'report.json',dict(complete=True,plan=pin,outerFreeze=freeze_pin,folds=artifacts,pooled=pins,
            comparisons=comparisons,previouslyUsedDevelopmentCohort=True,independentValidation=False,
            authorTestRead=False,learnerFeedbackEligible=False,clinicalUseEligible=False))
    except Exception as error:
        write_new(root/'failure.json',dict(errorType=type(error).__name__,message=str(error)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('diagnostics','outer'))
    for name in ('plan','freeze','output'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('plan','freeze'):parser.add_argument('--'+name+'-sha256',required=True)
    a=parser.parse_args();function=diagnostics if a.command=='diagnostics' else outer
    print(json.dumps(function(a.plan,a.plan_sha256,a.freeze,a.freeze_sha256,a.output)),flush=True)
