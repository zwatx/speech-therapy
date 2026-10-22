"""Supervised projection correction with immutable PCA features and frozen head."""
import hashlib
import json
from pathlib import Path
import random
import numpy as np
import torch
from lexical_heads.core import require, binding, _json, _history_snapshot, _indices, _rng, stable_outputs
from lexical_compact import core as original
from multiphone_child_train import fit_priors

RECIPE = dict(seed=7, threads=2, batchSize=64, lr=1e-4, weightDecay=.01, clipNorm=5.,
              maximumEpochs=20, patience=5, minimumImprovement=1e-7, epochZeroEligible=True,
              correctionShape=[1024,16], correctionDtype='float64', frozenHeadMode='eval', device='cpu')


def guard(data):
    for pin in data['sourceBindings'].values():
        require(binding(pin['path']) == pin, 'Source binding changed')
    require(not data['model'].training and all(not p.requires_grad for p in data['model'].parameters()), 'Head must remain frozen/eval')
    require(all(torch.equal(v, data['headState'][k]) for k,v in data['model'].state_dict().items()), 'Frozen head changed')


def prepare(bundle, sourceCheckpointPin, sourceTransformPin, sourceConfigPin, fitRows):
    torch.set_num_threads(2); torch.use_deterministic_algorithms(True)
    pins=dict(checkpoint=sourceCheckpointPin, transform=sourceTransformPin, config=sourceConfigPin)
    for pin in pins.values(): require(binding(pin['path']) == pin, 'Source binding changed')
    cfg=json.loads(Path(sourceConfigPin['path']).read_text())
    state=torch.load(sourceCheckpointPin['path'],map_location='cpu',weights_only=True)
    t=torch.load(sourceTransformPin['path'],map_location='cpu',weights_only=True)
    require(cfg['recipe']==original.RECIPE and cfg['transformRecipe']==original.TRANSFORM_RECIPE and cfg['family']=='pca16-scalars'
            and cfg['featureWidth']==29 and cfg['phase'] in ('inner','outer-refit') and cfg['fitRows']==fitRows
            and cfg['transform']==sourceTransformPin and state['configSha256']==sourceConfigPin['sha256']
            and state['transformSha256']==sourceTransformPin['sha256'], 'Source configuration differs')
    require(t['fitRows']==fitRows and t['rank']==16 and t['center'].shape==(1024,) and t['basis'].shape==(1024,16)
            and t['eigenvalues'].shape==(1024,) and all(t[k].dtype==torch.float64 and bool(torch.isfinite(t[k]).all()) for k in ('center','basis','eigenvalues')), 'Invalid source transform')
    scalars,target=np.asarray(bundle['scalars']),np.asarray(bundle['target'])
    require(scalars.ndim==2 and scalars.shape[1]==13 and target.shape==(len(scalars),1024)
            and scalars.dtype==target.dtype==np.float32 and np.isfinite(scalars).all() and np.isfinite(target).all(), 'Invalid features')
    positions=dict(bundle['positions'])
    require(all(type(k) is int and type(v) is int and 0<=v<len(scalars) for k,v in positions.items()) and len(set(positions.values()))==len(positions),'Invalid positions')
    data=dict(cohort=bundle['cohort'],positions=positions,fit=list(fitRows),sourceBindings=pins,sourceConfig=cfg)
    _indices(data,data['fit'])
    centered=torch.tensor(target,dtype=torch.float64)-t['center']
    projected=(centered@t['basis']).numpy().astype(np.float32)
    values=np.concatenate((projected,scalars),axis=1)
    ix=[positions[i] for i in fitRows];selected=values[ix].astype(np.float64)
    mean=torch.tensor(selected.mean(0),dtype=torch.float32);std=selected.std(0);std=torch.tensor(np.where(std<1e-6,1.,std),dtype=torch.float32)
    priors=fit_priors([data['cohort']['rows'][i] for i in fitRows])
    require(torch.equal(mean,state['mean']) and torch.equal(std,state['std']) and priors==state['priorState']==cfg['priorState'], 'Source fit moments/priors differ')
    require(torch.equal(torch.tensor(target[ix],dtype=torch.float64).mean(0),t['center']), 'Source center differs from fit rows')
    model,_=original.initialize(29);model.load_state_dict(state['model'],strict=True);model.eval();model.requires_grad_(False)
    data.update(values=values,centered=centered,mean=mean,std=std,priors=priors,model=model,
                headState={k:v.clone() for k,v in model.state_dict().items()})
    guard(data);return data


def _batch(data, indices, delta):
    ix=[data['positions'][i] for i in indices]
    values=torch.tensor(data['values'][ix],dtype=torch.float32)
    correction=(data['centered'][ix]@delta).float()
    values=torch.cat((values[:,:16]+correction,values[:,16:]),dim=1)
    values=((values-data['mean'])/data['std'])[:,None,:]
    rows=[data['cohort']['rows'][i] for i in indices]
    phones=torch.tensor([[r['targetId']] for r in rows],dtype=torch.long)
    mask=torch.ones(phones.shape,dtype=torch.bool)
    targets=torch.tensor([r['raterCounts'] for r in rows],dtype=torch.float32)/5
    return values,phones,mask,targets


@torch.no_grad()
def predict(data, indices, delta=None):
    _indices(data,indices)
    if delta is None:delta=torch.zeros((1024,16),dtype=torch.float64)
    require(delta.shape==(1024,16) and delta.dtype==torch.float64 and delta.device.type=='cpu' and bool(torch.isfinite(delta).all()), 'Invalid correction')
    require(not data['model'].training,'Head must remain eval')
    logits=[]
    for offset in range(0,len(indices),64):
        v,p,m,_=_batch(data,indices[offset:offset+64],delta);logits.append(data['model'](v,m,p,m)[:,0])
    p,lp,raw,loss=stable_outputs(torch.cat(logits),[data['cohort']['rows'][i]['raterCounts'] for i in indices])
    return dict(rowIndices=list(indices),probabilities=p.tolist(),logProbabilities=lp.tolist(),rawProbabilities=raw.tolist(),NLL=loss)


def _save(path,delta,opt,data,generator,sha,epoch,best_epoch,best_loss,updates):
    value=dict(delta=delta.detach().clone(),optimizer=opt.state_dict(),mean=data['mean'],std=data['std'],
               sourceBindings=data['sourceBindings'],configSha256=sha,epoch=epoch,bestEpoch=best_epoch,
               bestLoss=best_loss,totalUpdates=updates,rng=_rng(generator))
    tmp=Path(path).with_suffix('.writing')
    with tmp.open('xb') as stream:torch.save(value,stream)
    tmp.replace(path)


def train(data,selectionRows,output,config,epochs=None):
    _indices(data,data['fit']);_indices(data,selectionRows,empty=epochs is not None)
    require(not set(data['fit'])&set(selectionRows),'Selection overlaps fit')
    require((epochs is None and bool(selectionRows)) or (type(epochs) is int and 0<=epochs<=20 and not selectionRows),'Invalid adaptation phase')
    phase='inner' if epochs is None else 'outer-refit'
    require(data['sourceConfig']['phase']==phase,'Source head phase differs')
    if epochs is None:require(selectionRows==data['sourceConfig']['selectionRows'],'Source selection membership differs')
    guard(data);output=Path(output);require(not output.exists(),'Fresh output required')
    reserved=dict(recipe=RECIPE,sourceBindings=data['sourceBindings'],fitRows=data['fit'],selectionRows=selectionRows,
                  priorState=data['priors'],featureWidth=29,phase=phase,fixedEpochs=epochs,
                  selectionObjective='equal-position five-vote NLL' if epochs is None else None,
                  headUpdated=False,transformReestimated=False,outerPredictionsRead=False)
    require(isinstance(config,dict) and all(k not in config or config[k]==v for k,v in reserved.items()),'Conflicting configuration')
    cfg={**config,**reserved};output.mkdir(parents=True,mode=0o700);_json(output/'config.json',cfg);sha=binding(output/'config.json')['sha256']
    random.seed(7);np.random.seed(7);torch.manual_seed(7);generator=np.random.default_rng(7)
    delta=torch.nn.Parameter(torch.zeros((1024,16),dtype=torch.float64));opt=torch.optim.AdamW([delta],lr=1e-4,weight_decay=.01)
    best_epoch=0;best_loss=None;updates=0;history=[]
    row=dict(epoch=0,trainLoss=None,updates=0,totalUpdates=0,orderSha256=None)
    if epochs is None:row['selection']=predict(data,selectionRows,delta);best_loss=row['selection']['NLL']
    history.append(row);_history_snapshot(output/'history.json',history)
    for name in ['initial.pt','best.pt','last.pt']:_save(output/name,delta,opt,data,generator,sha,0,0,best_loss,0)
    epoch=0
    for epoch in range(1,(20 if epochs is None else epochs)+1):
        order=generator.permutation(data['fit']).tolist();loss_sum=0.;local_updates=0
        for offset in range(0,len(order),64):
            ids=order[offset:offset+64];v,p,m,y=_batch(data,ids,delta);opt.zero_grad(set_to_none=True)
            logits=data['model'](v,m,p,m)[:,0];loss=-(y*logits.log_softmax(-1)).sum(1).mean()
            require(bool(torch.isfinite(loss)),'Nonfinite loss');loss.backward()
            torch.nn.utils.clip_grad_norm_([delta],5.,error_if_nonfinite=True);opt.step()
            loss_sum+=float(loss.detach())*len(ids);local_updates+=1
        updates+=local_updates;row=dict(epoch=epoch,trainLoss=loss_sum/len(order),updates=local_updates,totalUpdates=updates,
            orderSha256=hashlib.sha256(json.dumps(order,separators=(',',':')).encode()).hexdigest())
        if epochs is None:
            row['selection']=predict(data,selectionRows,delta)
            if row['selection']['NLL']<best_loss-1e-7:
                best_loss=row['selection']['NLL'];best_epoch=epoch
                _save(output/'best.pt',delta,opt,data,generator,sha,epoch,best_epoch,best_loss,updates)
        else:best_epoch=epoch
        history.append(row);_history_snapshot(output/'history.json',history)
        _save(output/'last.pt',delta,opt,data,generator,sha,epoch,best_epoch,best_loss,updates)
        if epochs is None and epoch-best_epoch>=5:break
    if epochs is not None:_save(output/'best.pt',delta,opt,data,generator,sha,epoch,epoch,None,updates)
    if epochs is None:
        _json(output/'selection.json',history[best_epoch]['selection'])
        require(replay(output,data,selectionRows)==history[best_epoch]['selection'],'Selected replay differs')
    guard(data)
    names=['config.json','history.json','initial.pt','best.pt','last.pt']+(['selection.json'] if epochs is None else [])
    result=dict(complete=True,phase=phase,mode=phase,fitRows=data['fit'],selectionRows=selectionRows,epochsRun=epoch,
                bestEpoch=best_epoch,bestLoss=best_loss,totalUpdates=updates,configSha256=sha,sourceBindings=data['sourceBindings'],
                exactSelectionReplay=epochs is None,artifacts={n:binding(output/n) for n in names})
    _json(output/'report.json',result);return {**result,'report':binding(output/'report.json')}


def replay(directory,data,indices,checkpoint='best.pt'):
    require(checkpoint in ('best.pt','initial.pt','last.pt'),'Unknown checkpoint');guard(data);directory=Path(directory)
    cfg=json.loads((directory/'config.json').read_text());state=torch.load(directory/checkpoint,map_location='cpu',weights_only=True)
    require(cfg['recipe']==RECIPE and cfg['fitRows']==data['fit'] and cfg['sourceBindings']==data['sourceBindings']
            and cfg['priorState']==data['priors'] and cfg['phase']==data['sourceConfig']['phase']
            and state['sourceBindings']==data['sourceBindings'] and state['configSha256']==binding(directory/'config.json')['sha256']
            and torch.equal(state['mean'],data['mean']) and torch.equal(state['std'],data['std']),'Replay source/config differs')
    value=predict(data,indices,state['delta'])
    if checkpoint=='best.pt' and cfg['phase']=='inner' and indices==cfg['selectionRows']:
        require(state['epoch']==state['bestEpoch'] and state['bestLoss']==value['NLL'] and value==json.loads((directory/'selection.json').read_text()),'Selected state differs')
    return value
