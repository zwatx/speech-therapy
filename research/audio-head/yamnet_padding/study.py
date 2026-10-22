"""Test fixed timing shifts without treating silence as additional speech."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import numpy as np
from yamnet_study import common as c, detector, study as previous

OUT=c.BASE/'yamnet-padding-v1'
PARENT_PLAN='bd9dc52af986a24f41beca845226fe73ea87f9b23be623290c8db7a560ed9152'
PARENT_FREEZE='1057a353075b96c30bb964eab92a73bb0e632f52115dbe3912bd77f11be9810c'
VARIANTS=dict(lead240=(3840,0),tail240=(0,3840),lead480=(7680,0),
              tail480=(0,7680),both480=(7680,7680),both960=(15360,15360))


def pad(wave, left, right):
    c.require(isinstance(wave,np.ndarray) and wave.dtype==np.float32 and wave.ndim==1
              and len(wave)>0 and np.isfinite(wave).all() and np.abs(wave).max()<=1, 'Invalid source samples')
    c.require(type(left)is int and type(right)is int and left>=0 and right>=0, 'Invalid padding')
    result=np.zeros(left+len(wave)+right,dtype=np.float32)
    result[left:left+len(wave)]=wave
    return result


def array_sha(values):
    return hashlib.sha256(np.ascontiguousarray(values,dtype='<f4').tobytes()).hexdigest()


def declaration():
    parent,pin=previous.checked(PARENT_PLAN)
    freeze_pin=dict(path=str(c.OUTPUT/'inference-freeze.json'),sha256=PARENT_FREEZE)
    freeze=c.read(freeze_pin)
    c.require(freeze['complete'] and freeze['plan']==pin and len(freeze['records'])==1117, 'Incomplete parent inference')
    return dict(parentPlan=pin,parentFreeze=freeze_pin,variants={k:list(v) for k,v in VARIANTS.items()},
                protocol=c.pin(c.ROOT/'docs/model/yamnet-padding-protocol.md'),
                sources={str(p):c.sha(p) for p in Path(__file__).parent.glob('*.py')},
                clips=1117,inferences=6702,runtime=previous.runtime(),**c.FLAGS)


def checked(digest):
    binding=dict(path=str(OUT/'plan.json'),sha256=digest);plan=c.read(binding)
    c.require(plan==declaration(),'Declaration or source changed')
    parent=c.read(plan['parentPlan']);freeze=c.read(plan['parentFreeze'])
    return plan,binding,parent,freeze


def baseline(clip,binding):
    record=c.read(binding);c.guard(record['scores'])
    scores=np.load(record['scores']['path'],allow_pickle=False)
    summary=detector.validate_scores(scores,clip['sampleCount'])
    c.require(record['clipId']==clip['id'] and record['audio']==clip['audio']
              and all(record[k]==v for k,v in summary.items()), 'Parent result mismatch')
    return scores,summary


def run(digest,review_path):
    plan,binding,parent,freeze=checked(digest);review=json.loads(Path(review_path).read_text())
    c.require(review['status']=='clear' and not review['blockingFindings'] and review['planSha256']==digest,'Matching review required')
    for path,expected in review['sourceBindings'].items():c.require(c.sha(path)==expected,'Reviewed source changed')
    dest=OUT/'records';c.require(not dest.exists(),'No implicit restart');dest.mkdir()
    for k,v in previous.ENVIRONMENT.items():os.environ[k]=v
    model=detector.load_model(previous.VENDOR)
    first=parent['clips'][0];first_wave=detector.read_pcm(first['audio']['path'],first['audio']['sha256'],first['sampleCount'])
    expected,_=baseline(first,freeze['records'][0]);actual,_=detector.infer(model,first_wave)
    c.require(np.array_equal(actual,expected),'Initial parent replay differs')
    records=[];started=time.monotonic()
    for index,(clip,old_binding) in enumerate(zip(parent['clips'],freeze['records'],strict=True)):
        _,old=baseline(clip,old_binding)
        wave=detector.read_pcm(clip['audio']['path'],clip['audio']['sha256'],clip['sampleCount'])
        arrays={};variants={}
        for name,(left,right) in VARIANTS.items():
            transformed=pad(wave,left,right);tick=time.monotonic()
            scores,summary=detector.infer(model,transformed);arrays[name]=scores
            variants[name]=dict(**summary,leftSamples=left,rightSamples=right,
                sourceSpan=[left,left+len(wave)],waveformFloat32Sha256=array_sha(transformed),
                inferenceSeconds=time.monotonic()-tick)
        scores_path=dest/f'{index:04d}.npz';np.savez(scores_path,**arrays)
        path=dest/f'{index:04d}.json'
        c.write(path,dict(clipId=clip['id'],audio=clip['audio'],originalRecord=old_binding,
                         originalSummary=old,scores=c.pin(scores_path),variants=variants))
        records.append(c.pin(path))
        if (index+1)%50==0:print(json.dumps(dict(completedRecordings=index+1,total=1117)),flush=True)
    repeated,_=detector.infer(model,first_wave)
    c.require(np.array_equal(repeated,expected),'Final parent replay differs')
    repeat_path=dest/'repeat-first.npy';np.save(repeat_path,repeated,allow_pickle=False)
    checked(digest)
    c.write(OUT/'inference-freeze.json',dict(complete=True,plan=binding,records=records,
            exactInitialReplay=True,exactFinalReplay=True,repeatFirst=c.pin(repeat_path),
            wallSeconds=time.monotonic()-started,**c.FLAGS))
    print(json.dumps(c.pin(OUT/'inference-freeze.json')))


def summarize(parent,records):
    clips=parent['clips'];rows=parent['rows']
    c.require(set(records)=={x['id'] for x in clips},'Missing recorded coverage')
    result={};risk=[]
    for variant in VARIANTS:
        def decision(clip):return records[clip['id']]['variants'][variant]['accepted']
        def cell(selected):
            return dict(total=len(selected),originalAccepted=sum(records[x['id']]['originalSummary']['accepted'] for x in selected),
                accepted=sum(decision(x) for x in selected),
                acceptedToRejected=[x['id'] for x in selected if records[x['id']]['originalSummary']['accepted'] and not decision(x)],
                rejectedToAccepted=[x['id'] for x in selected if not records[x['id']]['originalSummary']['accepted'] and decision(x)])
        panels={population:cell([x for x in clips if x['population']==population]) for population in sorted({x['population'] for x in clips})}
        corpus={x['corpusId']:x for x in clips if x['population']=='corpus'}
        kept={cid for cid,clip in corpus.items() if decision(clip)}
        def support_cell(selected):
            return dict(total=previous.support(selected),retained=previous.support([r for r in selected if r['clipId'] in kept]))
        child=dict(overall=support_cell(rows),
            phones={ph:support_cell([r for r in rows if r['targetPhone']==ph]) for ph in sorted({r['targetPhone'] for r in rows})},
            ages={str(age):support_cell([r for r in rows if r['age']==age]) for age in range(6,13)},
            withheld={cid:previous.support([r for r in rows if r['clipId']==cid]) for cid in sorted(set(corpus)-kept)})
        crops={x['id']:records[x['id']]['variants'][variant] for x in clips if x['population']=='crop'}
        categories={population:{category:cell([x for x in clips if x['population']==population and x['category']==category])
                     for category in sorted({x['category'] for x in clips if x['population']==population})}
                    for population in ('environment','knownExtension','new','synthetic')}
        for cid,r in crops.items():
            if r['sampleCount']>=detector.RULE['windowSamples'] and not r['accepted']:
                risk.append(dict(clipId=cid,variant=variant,sampleCount=r['sampleCount'],speechScore=r['speechScore']))
        result[variant]=dict(panels=panels,child=child,crops=crops,categories=categories)
    return dict(variants=result,recordingLengthFallbackCounterexamples=risk)


def verify(digest,freeze_digest):
    _,binding,parent,oldfreeze=checked(digest)
    fpin=dict(path=str(OUT/'inference-freeze.json'),sha256=freeze_digest);freeze=c.read(fpin)
    c.require(freeze['complete'] and freeze['plan']==binding and freeze['exactInitialReplay']
              and freeze['exactFinalReplay'] and len(freeze['records'])==1117,'Incomplete inference freeze')
    records={}
    for clip,old_pin,record_pin in zip(parent['clips'],oldfreeze['records'],freeze['records'],strict=True):
        r=c.read(record_pin);_,old=baseline(clip,old_pin)
        c.require(r['clipId']==clip['id'] and r['audio']==clip['audio'] and r['originalRecord']==old_pin
                  and r['originalSummary']==old and set(r['variants'])==set(VARIANTS),'Wrong original/variant binding')
        wave=detector.read_pcm(clip['audio']['path'],clip['audio']['sha256'],clip['sampleCount']);c.guard(r['scores'])
        with np.load(r['scores']['path'],allow_pickle=False) as arrays:
            c.require(set(arrays.files)==set(VARIANTS),'Wrong score coverage')
            for name,(left,right) in VARIANTS.items():
                transformed=pad(wave,left,right);expected=detector.validate_scores(arrays[name],len(transformed))
                expected.update(leftSamples=left,rightSamples=right,sourceSpan=[left,left+len(wave)],
                                waveformFloat32Sha256=array_sha(transformed))
                c.require(all(r['variants'][name][k]==v for k,v in expected.items()),'Derived waveform or score mismatch')
        records[clip['id']]=r
    c.guard(freeze['repeatFirst']);expected,_=baseline(parent['clips'][0],oldfreeze['records'][0])
    c.require(np.array_equal(np.load(freeze['repeatFirst']['path'],allow_pickle=False),expected),'Final repeat artifact differs')
    c.write(OUT/'results.json',dict(complete=True,plan=binding,inferenceFreeze=fpin,
            baselineTransformedInferencePerformed=False,**summarize(parent,records),**c.FLAGS))
    print(json.dumps(c.pin(OUT/'results.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['declare','run','verify'])
    p.add_argument('--sha256');p.add_argument('--review');p.add_argument('--freeze-sha256');a=p.parse_args()
    if a.command=='declare':
        c.require(not OUT.exists(),'Fresh study output required');plan=declaration();OUT.mkdir();c.write(OUT/'plan.json',plan)
        print(json.dumps(c.pin(OUT/'plan.json')))
    elif a.command=='run':run(a.sha256,a.review)
    else:verify(a.sha256,a.freeze_sha256)
