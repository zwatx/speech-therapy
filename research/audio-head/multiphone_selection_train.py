"""Fixed six-epoch trajectories and frozen NLL/AP selections; no outer predictions."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import torch
import multiphone_ranking_train as original

HERE = original.HERE
PROTOCOL = HERE/'../../docs/model/multiphone-selection-policy-protocol.md'
HISTORICAL = HERE/'outputs/multiphone-20260926'
RULES = ('nll', 'ap')
TOLERANCE = 1e-7
require, digest, read_json = original.require, original.digest, original.read_json


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path),sha256=digest(path))


def read_bound(pin):
    require(digest(Path(pin['path'])) == pin['sha256'], 'Bound artifact changed: '+pin['path'])
    return read_json(Path(pin['path']))


def write_new(path, value):
    require(not path.exists(), 'No artifact overwrite')
    original.atomic_json(path,value)
    return binding(path)


def runtime():
    return dict(python=sys.version,executable=binding(sys.executable),torch=str(torch.__version__),
                numpy=np.__version__,device='cpu',threads=2)


def arms(): return [dict(fold=f,coefficient=c) for f in range(5) for c in (0.,.1)]


def arm_id(fold, coefficient):
    require(dict(fold=fold,coefficient=coefficient) in arms(), 'Undeclared arm')
    return f'fold-{fold}-coefficient-{coefficient:g}'


def sources():
    names = set(original.source_hashes()) | {'multiphone_selection_train.py','test_multiphone_selection_train.py',
        'multiphone_selection_audit.py','test_multiphone_selection_audit.py'}
    return {name:binding(HERE/name) for name in sorted(names)}


def metric(entry, rule):
    child=entry['evaluation']['ages6to12']
    value=(child['macroTargetLogLoss'] if rule=='nll' else
           child['targetDiscrimination']['macroTarget']['ratingBelow2']['averagePrecision'])
    require(type(value) in (int,float) and np.isfinite(value), 'Undefined or nonfinite selection metric')
    return value


def selections(history):
    require(len(history)==7 and [h['epoch'] for h in history]==list(range(7)), 'Incomplete chronological history')
    chosen={}
    for rule in RULES:
        best, epoch=metric(history[0],rule),0
        for entry in history[1:]:
            value=metric(entry,rule)
            if (best-value if rule=='nll' else value-best)>TOLERANCE: best,epoch=value,entry['epoch']
        chosen[rule]=dict(epoch=epoch,value=best)
    return chosen


def historical_directory(fold, coefficient):
    if coefficient: return HISTORICAL/'ranking-study-v1'/f'fold-{fold}-child-only-ranking-0p1'
    return (HISTORICAL/'consistency-study-v1'/'child-only-coefficient-0' if fold==0 else
            HISTORICAL/'consistency-replication-v1'/f'fold-{fold}-child-only-coefficient-0')


def historical_bindings(fold, coefficient):
    directory=historical_directory(fold,coefficient)
    report=read_json(directory/'report.json');replay=read_json(directory/'replay.json')
    require(report['fitComplete'] is True and replay['exact'] is True and replay['complete'] is True and
            replay['reportSha256']==digest(directory/'report.json') and
            replay['checkpointSha256']==digest(directory/'best.pt'), 'Historical replay certificate differs')
    pins={name:binding(directory/name) for name in ('report.json','replay.json',*report['filesSha256'])}
    require(all(pins[name]['sha256']==sha for name,sha in report['filesSha256'].items()),'Historical artifacts differ')
    return pins


def population(data, fold):
    original.verify_partitions(data['cohort'],data['splits']['folds'][fold])
    outer=[i for i in data['splits']['folds'][fold]['outerHoldoutRows'] if data['cohort']['rows'][i]['trainingEligible']]
    groups=[data['fit'],data['validation'],outer]
    speakers=[{data['cohort']['rows'][i]['speakerId'] for i in group} for group in groups]
    require(all(not speakers[i]&speakers[j] for i in range(3) for j in range(i)), 'Same-fold speaker leakage')
    require(all(6<=data['cohort']['rows'][i]['age']<=12 for i in data['fit']), 'Nonchild fitting rows')
    return dict(fold=fold,fitRows=data['fit'],validationRows=data['validation'],selectionRows=data['selection'],
        outerRows=outer,inputFiles=data['allBindings'],support=data['support'],
        meanDigest=original.tensor_digest(data['mean']),stdDigest=original.tensor_digest(data['std']))


def declare(output):
    output=Path(output).resolve()
    require(not output.exists() and output.is_relative_to(HERE/'outputs'), 'Fresh ignored declaration directory required')
    recipe=read_json(original.RECIPE);original.validate_recipe(recipe)
    pins=dict(protocol=binding(PROTOCOL),recipe=binding(original.RECIPE),**{'source/'+k:v for k,v in sources().items()})
    populations={}; histories={}
    torch.set_num_threads(2);torch.manual_seed(7)
    for fold in range(5):
        data=original.load_data(fold,recipe)
        populations[str(fold)]=population(data,fold)
        pins.update({f'fold/{fold}/'+k:v for k,v in data['allBindings'].items()})
        for coefficient in (0.,.1):
            name=arm_id(fold,coefficient); histories[name]=historical_bindings(fold,coefficient)
            pins.update({'historical/'+name+'/'+k:v for k,v in histories[name].items()})
    original.guard_files(pins)
    output.mkdir(parents=True,mode=0o700)
    return write_new(output/'declaration.json',dict(schemaVersion=1,complete=True,arms=arms(),epochs=6,
        rules=dict(nll='min child macroTargetLogLoss',ap='max child macroTarget ratingBelow2 averagePrecision'),
        tolerance=TOLERANCE,runtime=runtime(),inputFiles=pins,sourceBindings=sources(),populations=populations,historical=histories,
        researchOnly=True,outerPredictionsPerformed=False,authorTestRead=False,trainingPerformed=False))


def load_declaration(path, sha):
    plan=read_bound(dict(path=str(path),sha256=sha))
    require(plan['complete'] is True and plan['arms']==arms() and plan['epochs']==6 and plan['tolerance']==TOLERANCE
            and plan['sourceBindings']==sources() and plan['runtime']==runtime() and plan['outerPredictionsPerformed'] is False
            and plan['authorTestRead'] is False and plan['trainingPerformed'] is False, 'Declaration differs')
    original.validate_recipe(read_json(original.RECIPE));original.guard_files(plan['inputFiles'])
    require(plan['inputFiles']['protocol']==binding(PROTOCOL) and plan['inputFiles']['recipe']==binding(original.RECIPE),
            'Protocol or recipe changed')
    return plan


def check_prefix(entry, probabilities, state, old, old_history, coefficient):
    epoch=entry['epoch'];checks=[]
    if epoch<len(old_history):
        previous=old_history[epoch]
        for key in ('selectionMacroNLL','cleanSupervisedNLL','updates','nllOrderDigest','pairIdentityDigest','sampledPairs',
                    'pairwiseLossMeanPerUpdate','evaluation','confidence'):
            if key in previous: require(entry.get(key)==previous[key], 'Historical prefix differs: '+key)
        checks.append('history')
    report=read_bound(old['report.json'])
    if epoch==report['bestEpoch']:
        prediction=read_bound(old['predictions.json'])
        key='probabilities' if coefficient else 'cleanProbabilities'
        require(np.array_equal(probabilities,prediction[key]), 'Historical selected predictions differ')
        checks.append('selectedPredictions')
    for filename,expected_epoch in [('best.pt',report['bestEpoch']),('last.pt',report['epochsRun'])]:
        if epoch==expected_epoch:
            require(digest(Path(old[filename]['path']))==old[filename]['sha256'],'Historical checkpoint changed')
            previous=torch.load(old[filename]['path'],map_location='cpu',weights_only=True)
            require(all(original.trees_equal(state[k],previous[k]) for k in ('model','mean','std','optimizer')),
                    'Historical checkpoint model/normalization/optimizer differs')
            checks.append(filename)
    return checks


def fit(plan_path, plan_sha, fold, coefficient):
    plan_path=Path(plan_path);plan=load_declaration(plan_path,plan_sha)
    name=arm_id(fold,coefficient);output=plan_path.parent/'runs'/name
    require(not output.exists(), 'Fresh run required; no implicit resume')
    torch.set_num_threads(2);torch.manual_seed(7)
    data=original.load_data(fold,read_json(original.RECIPE))
    require(population(data,fold)==plan['populations'][str(fold)], 'Declared population differs')
    student=original.model();student.load_state_dict(data['warmState'],strict=True)
    optimizer=torch.optim.AdamW(student.parameters(),lr=3e-5,weight_decay=.01)
    nll_rng,pair_rng=np.random.default_rng(7),np.random.default_rng(20260926)
    rows=[data['cohort']['rows'][i] for i in data['validation']]
    output.mkdir(parents=True,mode=0o700)
    config=write_new(output/'config.json',dict(coefficient=coefficient,regime='child-only',
        declaration=dict(path=str(plan_path.resolve()),sha256=plan_sha),**plan['populations'][str(fold)]))
    old=plan['historical'][name];old_history=read_bound(old['history.json'])
    history=[];epochs=[];owned={'config':config};prefix=[]
    try:
        for epoch in range(7):
            objective=dict(updates=0,sampledPairs=0,nllOrderDigest=original.order_digest([]),
                           pairIdentityDigest=hashlib.sha256().hexdigest()) if epoch==0 else original.train_epoch(student,optimizer,data['clean'][:data['fitCount']],
                data['ids'][:data['fitCount']],data['labels'],nll_rng.permutation(data['fitCount']),data['sampler'],pair_rng,coefficient)
            p=data['warmPredictions'] if epoch==0 else original.clean_prediction(student,data)
            evaluation=original.score_predictions(p,rows)
            entry=dict(epoch=epoch,evaluation=evaluation,confidence=original.confidence(p,rows),
                       selectionMacroNLL=original.baseline.selection_loss(evaluation,'child-only'),**objective)
            for rule in RULES: metric(entry,rule)
            state=dict(model=student.state_dict(),optimizer=optimizer.state_dict(),mean=data['mean'],std=data['std'],
                epoch=epoch,configSha256=config['sha256'],declarationSha256=plan_sha,
                nllRngState=copy.deepcopy(nll_rng.bit_generator.state),pairRngState=copy.deepcopy(pair_rng.bit_generator.state))
            checkpoint=output/f'epoch-{epoch}.pt';original.save_checkpoint(checkpoint,state)
            prediction=write_new(output/f'epoch-{epoch}-predictions.json',dict(rowIndices=data['validation'],probabilities=p.tolist()))
            history.append(entry)
            history_pin=write_new(output/f'epoch-{epoch}-history.json',entry)
            ep=dict(epoch=epoch,checkpoint=binding(checkpoint),predictions=prediction,metrics=history_pin)
            epochs.append(ep);owned.update({f'{epoch}/{k}':v for k,v in ep.items() if k!='epoch'})
            # Persist checkpoint, probabilities and metrics before any prefix assertion can stop the fit.
            prefix.append(dict(epoch=epoch,checks=check_prefix(entry,p,state,old,old_history,coefficient)))
            original.guard_files(owned);load_declaration(plan_path,plan_sha)
            print(json.dumps(dict(arm=name,epoch=epoch,nll=metric(entry,'nll'),ap=metric(entry,'ap'))),flush=True)
        history_pin=write_new(output/'history.json',history)
        selected={rule:{**item,**{k:epochs[item['epoch']][k] for k in ('checkpoint','predictions')}}
                  for rule,item in selections(history).items()}
        result=dict(complete=True,fold=fold,coefficient=coefficient,config=config,history=history_pin,epochs=epochs,
            selections=selected,prefixVerification=prefix,declaration=dict(path=str(plan_path.resolve()),sha256=plan_sha),
            outerPredictionsPerformed=False,authorTestRead=False)
        original.guard_files(owned)
        return write_new(output/'manifest.json',result)
    except Exception as error:
        write_new(output/'failure.json',dict(complete=False,error=f'{type(error).__name__}: {error}',epochsSaved=len(epochs)))
        raise


def validate_run_artifacts(manifest):
    require(manifest['complete'] is True and manifest['outerPredictionsPerformed'] is False
            and manifest['authorTestRead'] is False and len(manifest['epochs'])==7 and
            [e['epoch'] for e in manifest['epochs']]==list(range(7)), 'Incomplete run manifest')
    config=read_bound(manifest['config']);history=read_bound(manifest['history'])
    require((manifest['fold'],manifest['coefficient'])==(config['fold'],config['coefficient']) and
            manifest['declaration']==config['declaration'], 'Run/config identity differs')
    selected=selections(history)
    for epoch in manifest['epochs']:
        index=epoch['epoch'];require(read_bound(epoch['metrics'])==history[index], 'Epoch history differs')
        original.guard_files({k:epoch[k] for k in ('checkpoint','predictions')})
        prediction=read_bound(epoch['predictions'])
        require(prediction['rowIndices']==config['validationRows'], 'Prediction membership differs')
    for rule,item in selected.items():
        expected={**item,**{k:manifest['epochs'][item['epoch']][k] for k in ('checkpoint','predictions')}}
        require(manifest['selections'][rule]==expected,'Selected checkpoint or rule differs')
    require(set(manifest['selections'])==set(RULES), 'Selection coverage differs')
    return config,history


def audit_orders(history,data,coefficient):
    nll_rng,pair_rng=np.random.default_rng(7),np.random.default_rng(20260926)
    states={0:(copy.deepcopy(nll_rng.bit_generator.state),copy.deepcopy(pair_rng.bit_generator.state))}
    n=data['fitCount'];sampler=data['sampler']
    for entry in history[1:]:
        order=nll_rng.permutation(n);sha=hashlib.sha256();updates=(n+63)//64
        if coefficient:
            for _ in range(updates): sha.update(sampler.identities(sampler.sample(pair_rng,64)).tobytes())
        require(entry['updates']==updates and entry['sampledPairs']==(updates*64 if coefficient else 0) and
                entry['nllOrderDigest']==original.order_digest(sampler.row_indices[order]) and
                entry['pairIdentityDigest']==sha.hexdigest(),'Update/order digest differs')
        states[entry['epoch']]=(copy.deepcopy(nll_rng.bit_generator.state),copy.deepcopy(pair_rng.bit_generator.state))
    return states


def validate_run(manifest,plan,plan_sha,data):
    config,history=validate_run_artifacts(manifest)
    fold,coefficient=manifest['fold'],manifest['coefficient']
    pop=population(data,fold)
    require(pop==plan['populations'][str(fold)] and all(config[k]==v for k,v in pop.items()) and
            config['declaration']['sha256']==plan_sha,'Run population/declaration differs')
    rows=[data['cohort']['rows'][i] for i in data['validation']]
    states=audit_orders(history,data,coefficient);prefix=[]
    old=plan['historical'][arm_id(fold,coefficient)];old_history=read_bound(old['history.json'])
    selected_epochs={v['epoch'] for v in manifest['selections'].values()}
    for ep in manifest['epochs']:
        index=ep['epoch'];p=np.array(read_bound(ep['predictions'])['probabilities'])
        require(p.shape==(len(rows),3) and np.isfinite(p).all() and (p>=0).all() and (p<=1).all()
                and np.allclose(p.sum(1),1,atol=1e-6,rtol=0),'Invalid validation probabilities')
        require(history[index]['evaluation']==original.score_predictions(p,rows) and
                history[index]['confidence']==original.confidence(p,rows) and
                history[index]['selectionMacroNLL']==metric(history[index],'nll'),'Saved validation metrics differ')
        state=torch.load(ep['checkpoint']['path'],map_location='cpu',weights_only=True)
        require(state['epoch']==index and state['configSha256']==manifest['config']['sha256'] and
                state['declarationSha256']==plan_sha and torch.equal(state['mean'],data['mean']) and
                torch.equal(state['std'],data['std']) and
                (state['nllRngState'],state['pairRngState'])==states[index],'Checkpoint binding/moments/RNG differs')
        prefix.append(dict(epoch=index,checks=check_prefix(history[index],p,state,old,old_history,coefficient)))
        if index==0: require(np.array_equal(p,data['warmPredictions']),'Warm probabilities differ')
        if index in selected_epochs:
            student=original.model();student.load_state_dict(state['model'],strict=True)
            require(np.array_equal(original.clean_prediction(student,data),p),'Selected predictions do not replay exactly')
    require(prefix==manifest['prefixVerification'],'Prefix certificate differs')
    return dict(selectedPredictionsReplayExact=True,historicalPrefixExact=True,speakerPartitionsVerified=True,
                epochsVerified=7,selectedEpochs=sorted(selected_epochs))


def freeze(plan_path, plan_sha):
    plan_path=Path(plan_path);plan=load_declaration(plan_path,plan_sha)
    destination=plan_path.parent/'freeze.json';require(not destination.exists(),'No frozen manifest overwrite')
    torch.set_num_threads(2)
    runs=[];selected=[]
    for fold in range(5):
        data=original.load_data(fold,read_json(original.RECIPE))
        for coefficient in (0.,.1):
            path=plan_path.parent/'runs'/arm_id(fold,coefficient)/'manifest.json'
            pin=binding(path);manifest=read_bound(pin)
            require(manifest['fold']==fold and manifest['coefficient']==coefficient,'Arm coverage differs')
            verified=validate_run(manifest,plan,plan_sha,data)
            runs.append(dict(fold=fold,coefficient=coefficient,**pin,selections=manifest['selections'],verification=verified))
            selected.extend(dict(fold=fold,coefficient=coefficient,rule=rule,**item) for rule,item in manifest['selections'].items())
    load_declaration(plan_path,plan_sha)
    for run in runs: validate_run_artifacts(read_bound(dict(path=run['path'],sha256=run['sha256'])))
    return write_new(destination,dict(complete=True,declaration=dict(path=str(plan_path.resolve()),sha256=plan_sha),
        declarationPath=str(plan_path.resolve()),declarationSha256=plan_sha,
        runs=runs,selections=selected,outerPredictionsPerformed=False,authorTestRead=False,researchOnly=True))


def validate_freeze(path, sha):
    frozen=read_bound(dict(path=str(path),sha256=sha))
    load_declaration(frozen['declaration']['path'],frozen['declaration']['sha256'])
    require(frozen['complete'] is True and frozen['outerPredictionsPerformed'] is False and
            frozen['authorTestRead'] is False and [{k:r[k] for k in ('fold','coefficient')} for r in frozen['runs']]==arms(),
            'Frozen run coverage differs')
    require(frozen['declarationPath']==frozen['declaration']['path'] and
            frozen['declarationSha256']==frozen['declaration']['sha256'],'Frozen declaration identity differs')
    selected=[]
    for run in frozen['runs']:
        manifest=read_bound(dict(path=run['path'],sha256=run['sha256']));validate_run_artifacts(manifest)
        require((manifest['fold'],manifest['coefficient'])==(run['fold'],run['coefficient']) and
                manifest['declaration']==frozen['declaration'] and run['selections']==manifest['selections'] and
                all(run['verification'][k] is True for k in ('selectedPredictionsReplayExact','historicalPrefixExact','speakerPartitionsVerified')),
                'Frozen run verification differs')
        selected.extend(dict(fold=run['fold'],coefficient=run['coefficient'],rule=rule,**item)
                        for rule,item in run['selections'].items())
    require(len(selected)==20 and selected==frozen['selections'],'Frozen selection coverage differs')
    return frozen


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['declare','fit','freeze'])
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256')
    parser.add_argument('--fold',type=int);parser.add_argument('--coefficient',type=float)
    args=parser.parse_args()
    if args.command=='declare':
        require(args.output is not None,'Output directory required');result=declare(args.output)
    else:
        require(args.plan is not None and args.plan_sha256,'Declaration path/SHA required')
        result=fit(args.plan,args.plan_sha256,args.fold,args.coefficient) if args.command=='fit' else freeze(args.plan,args.plan_sha256)
    print(json.dumps(result,indent=2))
