"""Fixed six-epoch sequence-feature fits and NLL-only frozen selections."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
import multiphone_selection_train as retained
import multiphone_sequence_features as exporter
from multiphone_sequence_head import SequenceEvidenceHead, fitting_moments

original=retained.original
HERE=original.HERE
PROTOCOL=exporter.PROTOCOL
CONTROLS=HERE/'outputs/multiphone-20260927/selection-policy-v2'
require,digest,read_json=original.require,original.digest,original.read_json
binding,read_bound,write_new,runtime=retained.binding,retained.read_bound,retained.write_new,retained.runtime


def model(*,enabled=True):return SequenceEvidenceHead(enabled=enabled)


def sources():
    names=set(retained.sources())|{'multiphone_sequence_train.py','test_multiphone_sequence_train.py',
        'multiphone_sequence_head.py','test_multiphone_sequence_head.py','multiphone_sequence_features.py',
        'test_multiphone_sequence_features.py','multiphone_sequence_audit.py','test_multiphone_sequence_audit.py'}
    return {n:binding(HERE/n) for n in sorted(names)}


def load_features(path,sha):
    report=exporter.validate_export(path,sha)
    matrix=np.load(report['matrix']['path'],allow_pickle=False)
    return report,matrix


def prepare_data(data,matrix):
    eligible=[i for i,r in enumerate(data['cohort']['rows']) if r['trainingEligible']]
    require(matrix.dtype==np.float32 and matrix.shape==(len(eligible),4) and
            all(data['positions'][i]==p for p,i in enumerate(eligible)),'Feature/cohort position order differs')
    values=torch.from_numpy(matrix.copy())
    mean,std=fitting_moments(values,[data['positions'][i] for i in data['fit']])
    selected=data['fit'] if len(data['clean'])==len(data['fit']) else data['fit']+data['validation']
    require(len(data['clean'])==len(selected) and len(data['ids'])==len(selected),'Unexpected clean/ID population size')
    indices=[data['positions'][i] for i in selected]
    result=dict(data);result.update(sequenceMean=mean,sequenceStd=std,
        clean=torch.cat((data['clean'],(values[indices]-mean)/std),dim=1))
    return result


def selection(history):
    require(len(history)==7 and [h['epoch'] for h in history]==list(range(7)), 'Incomplete chronological history')
    best,epoch=retained.metric(history[0],'nll'),0
    for entry in history[1:]:
        value=retained.metric(entry,'nll')
        if best-value>1e-7:best,epoch=value,entry['epoch']
    return dict(epoch=epoch,value=best)


def control_path(fold):return CONTROLS/'runs'/retained.arm_id(fold,0.)/'manifest.json'


def declare(featurespath,featuresha,output):
    output=Path(output).resolve()
    require(not output.exists() and output.is_relative_to(HERE/'outputs'),'Fresh ignored declaration directory required')
    report,matrix=load_features(featurespath,featuresha)
    torch.set_num_threads(2);torch.manual_seed(7)
    control_plan_pin=binding(CONTROLS/'declaration.json')
    control_plan=retained.load_declaration(control_plan_pin['path'],control_plan_pin['sha256'])
    pins=dict(protocol=binding(PROTOCOL),recipe=binding(original.RECIPE),features=dict(path=str(Path(featurespath).resolve()),sha256=featuresha),
        controlDeclaration=control_plan_pin,**{'source/'+k:v for k,v in sources().items()})
    populations={};controls={}
    for fold in range(5):
        data=original.load_data(fold,read_json(original.RECIPE));pop=retained.population(data,fold)
        require(pop==control_plan['populations'][str(fold)],'Control population differs')
        augmented=prepare_data(data,matrix)
        populations[str(fold)]={**pop,'sequenceMeanDigest':original.tensor_digest(augmented['sequenceMean']),
            'sequenceStdDigest':original.tensor_digest(augmented['sequenceStd'])}
        pins.update({f'fold/{fold}/'+k:v for k,v in data['allBindings'].items()})
        pin=binding(control_path(fold));control=read_bound(pin)
        require(control['fold']==fold and control['coefficient']==0. and control['declaration']==control_plan_pin,'Matched control differs')
        retained.validate_run_artifacts(control)
        controls[str(fold)]=pin
        pins['control/'+str(fold)]=pin
        pins.update({f'control/{fold}/'+k:control[k] for k in ('config','history')})
        for ep in control['epochs']:
            pins.update({f'control/{fold}/{ep["epoch"]}/'+k:ep[k] for k in ('checkpoint','predictions','metrics')})
    original.guard_files(pins);output.mkdir(parents=True,mode=0o700)
    return write_new(output/'declaration.json',dict(schemaVersion=1,complete=True,folds=list(range(5)),epochs=6,
        rule='min child macroTargetLogLoss',tolerance=1e-7,runtime=runtime(),inputFiles=pins,sourceBindings=sources(),
        features=pins['features'],populations=populations,controls=controls,controlDeclaration=control_plan_pin,
        outerPredictionsPerformed=False,authorTestRead=False,trainingPerformed=False,researchOnly=True))


def load_declaration(path,sha):
    plan=read_bound(dict(path=str(path),sha256=sha))
    require(plan['complete'] is True and plan['folds']==list(range(5)) and plan['epochs']==6 and
            plan['rule']=='min child macroTargetLogLoss' and plan['tolerance']==1e-7 and plan['runtime']==runtime() and
            plan['sourceBindings']==sources() and all(plan[k] is False for k in
                ('outerPredictionsPerformed','authorTestRead','trainingPerformed')),'Declaration differs')
    original.guard_files(plan['inputFiles'])
    require(plan['inputFiles']['protocol']==binding(PROTOCOL) and plan['inputFiles']['recipe']==binding(original.RECIPE) and
            plan['features']==plan['inputFiles']['features'],'Declaration protocol/features differ')
    return plan


def check_population(data,plan,fold):
    pop={**retained.population(data,fold),'sequenceMeanDigest':original.tensor_digest(data['sequenceMean']),
         'sequenceStdDigest':original.tensor_digest(data['sequenceStd'])}
    require(pop==plan['populations'][str(fold)],'Declared sequence population differs')
    return pop


def entry_for(epoch,p,rows,objective):
    evaluation=original.score_predictions(p,rows)
    return dict(epoch=epoch,evaluation=evaluation,confidence=original.confidence(p,rows),
        selectionMacroNLL=original.baseline.selection_loss(evaluation,'child-only'),**objective)


def zero_objective():
    return dict(updates=0,sampledPairs=0,nllOrderDigest=original.order_digest([]),pairIdentityDigest=hashlib.sha256().hexdigest())


def control_order(entry,control_entry):
    for k in ('updates','sampledPairs','nllOrderDigest','pairIdentityDigest'):
        require(entry[k]==control_entry[k],'Matched control supervised order differs: '+k)


def disabled_optimizer_equal(actual,expected):
    # The appended frozen branch has no state; original parameter IDs remain unchanged.
    require(original.trees_equal(actual['state'],expected['state']),'Disabled optimizer state differs')
    a,b=copy.deepcopy(actual['param_groups']),copy.deepcopy(expected['param_groups'])
    require(len(a)==len(b)==1 and a[0]['params']==b[0]['params']+[len(b[0]['params'])],
            'Disabled optimizer parameter coverage differs')
    a[0]['params']=b[0]['params']
    require(original.trees_equal(a,b),'Disabled optimizer settings differ')


def equivalence(plan_path,plan_sha,plan,matrix):
    destination=Path(plan_path).parent/'equivalence.json'
    if destination.exists():
        certificate=read_json(destination)
        require(certificate['complete'] is True and certificate['declaration']==dict(path=str(Path(plan_path).resolve()),sha256=plan_sha)
                and certificate['warmFolds']==list(range(5)) and certificate['disabledEpochExact'] is True,'Equivalence certificate differs')
        original.guard_files(certificate['artifacts'])
        return binding(destination)
    directory=Path(plan_path).parent/'equivalence'
    require(not directory.exists(),'Equivalence failed or interrupted; no implicit restart')
    directory.mkdir(mode=0o700);artifacts={}
    try:
        for fold in range(5):
            data=prepare_data(original.load_data(fold,read_json(original.RECIPE)),matrix);check_population(data,plan,fold)
            student=model();student.load_warm(data['warmState'])
            require(np.array_equal(original.clean_prediction(student,data),data['warmPredictions']),'Active zero-branch warm mismatch')
        torch.manual_seed(7)
        data=prepare_data(original.load_data(0,read_json(original.RECIPE)),matrix)
        student=model(enabled=False);student.load_warm(data['warmState'])
        optimizer=torch.optim.AdamW(student.parameters(),lr=3e-5,weight_decay=.01)
        rng,pair=np.random.default_rng(7),np.random.default_rng(20260926)
        objective=original.train_epoch(student,optimizer,data['clean'][:data['fitCount']],data['ids'][:data['fitCount']],
            data['labels'],rng.permutation(data['fitCount']),data['sampler'],pair,0.)
        state=dict(model=student.state_dict(),optimizer=optimizer.state_dict(),mean=data['mean'],std=data['std'])
        checkpoint=directory/'disabled-epoch-1.pt';original.save_checkpoint(checkpoint,state);artifacts['checkpoint']=binding(checkpoint)
        p=original.clean_prediction(student,data);rows=[data['cohort']['rows'][i] for i in data['validation']]
        entry=entry_for(1,p,rows,objective)
        artifacts['metrics']=write_new(directory/'metrics.json',entry)
        artifacts['predictions']=write_new(directory/'predictions.json',dict(rowIndices=data['validation'],probabilities=p.tolist()))
        control=read_bound(plan['controls']['0']);retained.validate_run_artifacts(control)
        ep=control['epochs'][1];saved=torch.load(ep['checkpoint']['path'],map_location='cpu',weights_only=True)
        require(entry==read_bound(ep['metrics']) and np.array_equal(p,read_bound(ep['predictions'])['probabilities']),
                'Disabled epoch metrics/order/predictions differ')
        require(all(torch.equal(state['model'][k],v) for k,v in saved['model'].items()) and
                torch.count_nonzero(state['model']['sequence_projection.weight'])==0 and
                torch.equal(state['mean'],saved['mean']) and torch.equal(state['std'],saved['std']),
                'Disabled epoch parameters/moments differ')
        disabled_optimizer_equal(state['optimizer'],saved['optimizer'])
        require((rng.bit_generator.state,pair.bit_generator.state)==(saved['nllRngState'],saved['pairRngState']),
                'Disabled epoch RNG differs')
        return write_new(destination,dict(complete=True,declaration=dict(path=str(Path(plan_path).resolve()),sha256=plan_sha),
            warmFolds=list(range(5)),disabledEpochExact=True,artifacts=artifacts))
    except Exception as error:
        write_new(directory/'failure.json',dict(complete=False,error=f'{type(error).__name__}: {error}',artifacts=artifacts));raise


def fit(path,sha,fold):
    path=Path(path).resolve();plan=load_declaration(path,sha)
    require(type(fold) is int and fold in range(5),'Undeclared fold')
    output=path.parent/'runs'/f'fold-{fold}-sequence'
    require(not output.exists(),'Fresh run required; no implicit resume')
    _,matrix=load_features(plan['features']['path'],plan['features']['sha256'])
    torch.set_num_threads(2);torch.manual_seed(7)
    certificate=equivalence(path,sha,plan,matrix)
    torch.manual_seed(7)
    data=prepare_data(original.load_data(fold,read_json(original.RECIPE)),matrix);pop=check_population(data,plan,fold)
    student=model();student.load_warm(data['warmState'])
    optimizer=torch.optim.AdamW(student.parameters(),lr=3e-5,weight_decay=.01)
    rng,pair=np.random.default_rng(7),np.random.default_rng(20260926)
    rows=[data['cohort']['rows'][i] for i in data['validation']]
    control=read_bound(plan['controls'][str(fold)]);_,old=retained.validate_run_artifacts(control)
    output.mkdir(parents=True,mode=0o700)
    config=write_new(output/'config.json',dict(**pop,arm='sequence',coefficient=0.,regime='child-only',
        declaration=dict(path=str(path),sha256=sha),equivalence=certificate,features=plan['features']))
    epochs=[];history=[];owned={'config':config}
    try:
        for epoch in range(7):
            objective=zero_objective() if epoch==0 else original.train_epoch(student,optimizer,data['clean'][:data['fitCount']],
                data['ids'][:data['fitCount']],data['labels'],rng.permutation(data['fitCount']),data['sampler'],pair,0.)
            p=original.clean_prediction(student,data);entry=entry_for(epoch,p,rows,objective)
            state=dict(model=student.state_dict(),optimizer=optimizer.state_dict(),mean=data['mean'],std=data['std'],
                sequenceMean=data['sequenceMean'],sequenceStd=data['sequenceStd'],epoch=epoch,configSha256=config['sha256'],
                declarationSha256=sha,nllRngState=copy.deepcopy(rng.bit_generator.state),pairRngState=copy.deepcopy(pair.bit_generator.state))
            checkpoint=output/f'epoch-{epoch}.pt';original.save_checkpoint(checkpoint,state)
            ep=dict(epoch=epoch,checkpoint=binding(checkpoint),
                predictions=write_new(output/f'epoch-{epoch}-predictions.json',dict(rowIndices=data['validation'],probabilities=p.tolist())),
                metrics=write_new(output/f'epoch-{epoch}-history.json',entry))
            epochs.append(ep);history.append(entry);owned.update({f'{epoch}/'+k:ep[k] for k in ('checkpoint','predictions','metrics')})
            control_order(entry,old[epoch])
            if epoch==0:require(np.array_equal(p,data['warmPredictions']),'Active zero-branch warm mismatch')
            original.guard_files(owned);load_declaration(path,sha)
            print(json.dumps(dict(fold=fold,epoch=epoch,nll=entry['selectionMacroNLL'])),flush=True)
        chosen=selection(history);chosen.update({k:epochs[chosen['epoch']][k] for k in ('checkpoint','predictions')})
        return write_new(output/'manifest.json',dict(complete=True,fold=fold,arm='sequence',coefficient=0.,config=config,
            history=write_new(output/'history.json',history),epochs=epochs,selection=chosen,
            declaration=dict(path=str(path),sha256=sha),outerPredictionsPerformed=False,authorTestRead=False))
    except Exception as error:
        write_new(output/'failure.json',dict(complete=False,error=f'{type(error).__name__}: {error}',epochsSaved=len(epochs)));raise


def validate_run_artifacts(manifest):
    require(manifest['complete'] is True and manifest['arm']=='sequence' and manifest['coefficient']==0. and
            manifest['outerPredictionsPerformed'] is False and manifest['authorTestRead'] is False and
            [e['epoch'] for e in manifest['epochs']]==list(range(7)),'Incomplete candidate manifest')
    config=read_bound(manifest['config']);history=read_bound(manifest['history'])
    require(config['fold']==manifest['fold'] and config['arm']=='sequence' and config['coefficient']==0. and
            config['declaration']==manifest['declaration'],'Candidate config identity differs')
    chosen=selection(history)
    for ep in manifest['epochs']:
        original.guard_files({k:ep[k] for k in ('checkpoint','predictions','metrics')})
        require(read_bound(ep['metrics'])==history[ep['epoch']] and
                read_bound(ep['predictions'])['rowIndices']==config['validationRows'],'Candidate epoch history/membership differs')
    chosen.update({k:manifest['epochs'][chosen['epoch']][k] for k in ('checkpoint','predictions')})
    require(manifest['selection']==chosen,'Candidate NLL selection differs')
    return config,history


def validate_run(manifest,plan,sha,data):
    config,history=validate_run_artifacts(manifest);pop=check_population(data,plan,manifest['fold'])
    require(all(config[k]==v for k,v in pop.items()) and config['declaration']['sha256']==sha and
            config['features']==plan['features'],'Candidate lineage differs')
    cert=read_bound(config['equivalence'])
    require(cert['complete'] is True and cert['disabledEpochExact'] is True and cert['warmFolds']==list(range(5)) and
            cert['declaration']==config['declaration'],'Candidate equivalence differs')
    original.guard_files(cert['artifacts'])
    states=retained.audit_orders(history,data,0.)
    control=read_bound(plan['controls'][str(manifest['fold'])]);_,control_history=retained.validate_run_artifacts(control)
    rows=[data['cohort']['rows'][i] for i in data['validation']]
    for ep in manifest['epochs']:
        index=ep['epoch'];p=np.asarray(read_bound(ep['predictions'])['probabilities']);control_order(history[index],control_history[index])
        require(p.shape==(len(rows),3) and np.isfinite(p).all() and (p>=0).all() and (p<=1).all() and
                np.allclose(p.sum(1),1,atol=1e-6,rtol=0),'Invalid candidate probabilities')
        require(history[index]['evaluation']==original.score_predictions(p,rows) and
                history[index]['confidence']==original.confidence(p,rows) and
                history[index]['selectionMacroNLL']==retained.metric(history[index],'nll'),'Candidate saved metrics differ')
        state=torch.load(ep['checkpoint']['path'],map_location='cpu',weights_only=True)
        require(state['epoch']==index and state['configSha256']==manifest['config']['sha256'] and state['declarationSha256']==sha and
                all(torch.equal(state[k],data[k]) for k in ('mean','std','sequenceMean','sequenceStd')) and
                (state['nllRngState'],state['pairRngState'])==states[index],'Candidate state lineage/moments/RNG differs')
        if index==0:
            require(np.array_equal(p,data['warmPredictions']) and torch.count_nonzero(state['model']['sequence_projection.weight'])==0 and
                    all(torch.equal(state['model'][k],v) for k,v in data['warmState'].items()),'Candidate warm state differs')
        if index==manifest['selection']['epoch']:
            student=model();student.load_state_dict(state['model'],strict=True)
            require(np.array_equal(original.clean_prediction(student,data),p),'Candidate selected replay differs')
    return dict(selectedPredictionsReplayExact=True,speakerPartitionsVerified=True,epochsVerified=7,matchedOrderExact=True)


def freeze(path,sha):
    path=Path(path).resolve();plan=load_declaration(path,sha);destination=path.parent/'freeze.json'
    require(not destination.exists(),'No frozen manifest overwrite');torch.set_num_threads(2)
    _,matrix=load_features(plan['features']['path'],plan['features']['sha256'])
    control_plan=retained.load_declaration(plan['controlDeclaration']['path'],plan['controlDeclaration']['sha256'])
    runs=[];controls=[]
    for fold in range(5):
        base=original.load_data(fold,read_json(original.RECIPE));data=prepare_data(base,matrix)
        pin=binding(path.parent/'runs'/f'fold-{fold}-sequence'/'manifest.json');manifest=read_bound(pin)
        require(manifest['fold']==fold and manifest['declaration']==dict(path=str(path),sha256=sha),'Freeze candidate coverage differs')
        verified=validate_run(manifest,plan,sha,data);runs.append(dict(fold=fold,**pin,verification=verified))
        cp=plan['controls'][str(fold)];control=read_bound(cp)
        require(control['fold']==fold and control['coefficient']==0.,'Freeze control coverage differs')
        verification=retained.validate_run(control,control_plan,plan['controlDeclaration']['sha256'],base)
        controls.append(dict(fold=fold,**cp,verification=verification))
    load_declaration(path,sha)
    return write_new(destination,dict(complete=True,declaration=dict(path=str(path),sha256=sha),runs=runs,controls=controls,
        outerPredictionsPerformed=False,authorTestRead=False,researchOnly=True))


def validate_freeze(path,sha):
    frozen=read_bound(dict(path=str(path),sha256=sha));plan=load_declaration(**dict(path=frozen['declaration']['path'],sha=frozen['declaration']['sha256']))
    require(frozen['complete'] is True and frozen['outerPredictionsPerformed'] is False and frozen['authorTestRead'] is False and
            [r['fold'] for r in frozen['runs']]==list(range(5)) and [r['fold'] for r in frozen['controls']]==list(range(5)),
            'Frozen coverage differs')
    for run,control in zip(frozen['runs'],frozen['controls'],strict=True):
        manifest=read_bound({k:run[k] for k in ('path','sha256')});config,_=validate_run_artifacts(manifest)
        require(all(config[k]==v for k,v in plan['populations'][str(run['fold'])].items()) and
                config['features']==plan['features'],'Frozen candidate population/features differ')
        certificate=read_bound(config['equivalence'])
        require(certificate['complete'] is True and certificate['disabledEpochExact'] is True and
                certificate['warmFolds']==list(range(5)) and certificate['declaration']==frozen['declaration'],
                'Frozen equivalence certificate differs')
        original.guard_files(certificate['artifacts'])
        require(manifest['fold']==run['fold'] and manifest['declaration']==frozen['declaration'] and
                run['verification']==dict(selectedPredictionsReplayExact=True,speakerPartitionsVerified=True,epochsVerified=7,matchedOrderExact=True),
                'Frozen candidate verification differs')
        pin={k:control[k] for k in ('path','sha256')};old=read_bound(pin);retained.validate_run_artifacts(old)
        require(pin==plan['controls'][str(control['fold'])] and old['fold']==control['fold'] and old['coefficient']==0. and
                old['declaration']==plan['controlDeclaration'] and all(control['verification'][k] is True for k in
                ('selectedPredictionsReplayExact','historicalPrefixExact','speakerPartitionsVerified')),'Frozen control verification differs')
    return frozen


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['declare','fit','freeze'])
    parser.add_argument('--features',type=Path);parser.add_argument('--features-sha256');parser.add_argument('--output',type=Path)
    parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256');parser.add_argument('--fold',type=int)
    args=parser.parse_args()
    if args.command=='declare':result=declare(args.features,args.features_sha256,args.output)
    elif args.command=='fit':result=fit(args.plan,args.plan_sha256,args.fold)
    else:result=freeze(args.plan,args.plan_sha256)
    print(json.dumps(result,indent=2))
