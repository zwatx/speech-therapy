"""Declare, run and replay the fixed child speech-retention comparison."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time
import numpy as np
from yamnet_study import common as c, detector

VENDOR = c.HEAD/'vendor/yamnet-c14bf9ad'
VENDOR_SHA = '130fc1280de87bfe6b140b163501847575a41e29bf0e49e4c2763a953a6c1e54'
SHORT_SHA = '936814170ea54b37addb84211b99d80153e53096b6c8892bc1b0b936710e9bae'
ENVIRONMENT = dict(CUDA_VISIBLE_DEVICES='-1', TF_NUM_INTRAOP_THREADS='2',
                   TF_NUM_INTEROP_THREADS='2', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
                   VECLIB_MAXIMUM_THREADS='2', TF_DETERMINISTIC_OPS='1', TF_ENABLE_ONEDNN_OPTS='0')


def runtime():
    return dict(python=platform.python_version(), versions={name:importlib.metadata.version(name)
                for name in ('tensorflow','tf-keras','numpy')}, device='cpu', environment=ENVIRONMENT)


def declaration():
    vendor_pin=dict(path=str(VENDOR/'manifest.json'), sha256=VENDOR_SHA)
    vendor=c.read(vendor_pin)
    short_pin=dict(path=str(c.BASE/'short-vad-v1/report.json'), sha256=SHORT_SHA)
    short=c.read(short_pin); oldplan=c.read(short['plan'])
    cohort_pin=oldplan['inputBindings']['cohort']; cohort=c.read(cohort_pin)
    c.require(cohort['authorPartition']=='train' and short['complete'] and not short['authorTestRead'], 'Invalid source population')
    rows=[{k:r[k] for k in ('clipId','speakerId','age','targetPhone','raterCounts')}
          for r in cohort['rows'] if r['trainingEligible'] and 6<=r['age']<=12]
    ids={r['clipId'] for r in rows}
    c.require(len(rows)==5654 and len(ids)==1037 and len({r['speakerId'] for r in rows})==52
              and len({r['targetPhone'] for r in rows})==23, 'Incomplete child cohort')
    follow_pin=c.pin(c.BASE/'short-vad-followup-v1/report.json'); follow=c.read(follow_pin)
    c.require(follow['complete'] and len(follow['outcomes'])==24, 'Incomplete known extension reference')
    acquisition_pin=c.pin(c.OUTPUT/'acquisition/complete.json'); acquisition=c.read(acquisition_pin)
    selection=c.read(acquisition['selection'])
    for b in selection['inputs'].values(): c.guard(b)
    c.require(acquisition['complete'] and len(acquisition['clips'])==24, 'Incomplete new acquisition')
    inputs=dict(vendor=vendor_pin, shortReport=short_pin, shortPlan=short['plan'], cohort=cohort_pin,
                knownExtensionReport=follow_pin, acquisition=acquisition_pin, selection=acquisition['selection'],
                protocol=c.pin(c.PROTOCOL), environmentLock=c.pin(c.ROOT/'work/input-quality-next-20260927/setup/requirements.hashes.txt'))
    inputs.update({'vendor/'+name:b for name,b in vendor['files'].items()})
    clips=[]
    for name, record in sorted(short['records'].items()):
        clip=record['clip']; population=clip['population']
        if population=='corpus' and clip['corpusId'] not in ids:
            continue
        if population=='fresh':
            previous=follow['outcomes'][name]
            c.require(previous['clip']==clip and previous['vad']==record['vad'], 'Known extension reference mismatch')
            baseline=previous['combined']['short100']; population='knownExtension'
        else:
            baseline=record['combined']['short100']
        c.require(type(baseline) is bool, 'Baseline decision must be measured or logically determined')
        clips.append(dict(id=name, population=population, audio=clip['audio'], sampleCount=clip['sampleCount'],
                          baseline=baseline, corpusId=clip.get('corpusId'), category=clip.get('category'),
                          sourceClip=clip))
    for item in acquisition['clips']:
        r=item['metadata']
        clips.append(dict(id='new/'+r['filename'], population='new', audio=item['audio'], sampleCount=80000,
                          baseline=None, corpusId=None, category=r['category'], sourceClip=item))
    expected=dict(corpus=1037,crop=17,environment=12,knownExtension=24,synthetic=3,new=24)
    c.require({p:sum(x['population']==p for x in clips) for p in expected}==expected
              and len(clips)==len({x['id'] for x in clips})==1117, 'Incomplete or duplicate input coverage')
    for b in inputs.values(): c.guard(b)
    for clip in clips: c.guard(clip['audio'])
    return dict(inputs=inputs, clips=clips, rows=rows, rule=detector.RULE, runtime=runtime(),
                sourceBindings={str(p):c.sha(p) for p in Path(__file__).parent.glob('*.py')}, **c.FLAGS)


def checked(digest):
    binding=dict(path=str(c.OUTPUT/'plan.json'), sha256=digest); plan=c.read(binding)
    c.require(plan==declaration(), 'Study input/source/runtime declaration changed')
    return plan,binding


def support(rows):
    votes=np.asarray([r['raterCounts'] for r in rows], dtype=np.int64).reshape(-1,3)
    return dict(positions=len(rows), recordings=len({r['clipId'] for r in rows}),
                children=len({r['speakerId'] for r in rows}), votes=votes.sum(0).tolist(),
                rating0Positions=int((votes[:,0]>0).sum()), below2Positions=int((votes[:,:2].sum(1)>0).sum()))


def tables(plan, records):
    c.require(set(records)=={x['id'] for x in plan['clips']}, 'Incomplete recorded coverage')
    decisions={}
    for clip in plan['clips']:
        y=records[clip['id']]['accepted']; b=clip['baseline']
        c.require(type(y) is bool and (b is None or type(b) is bool), 'Invalid decision')
        decisions[clip['id']]=dict(baseline=b,yamnet=y,combined=(b and y) if b is not None else None)
    corpus={clip['corpusId']:clip['id'] for clip in plan['clips'] if clip['population']=='corpus'}
    rows=plan['rows']; retention={}
    for method in ('baseline','yamnet','combined'):
        retained={cid for cid,rid in corpus.items() if decisions[rid][method]}
        def cell(selected):
            return dict(total=support(selected), retained=support([r for r in selected if r['clipId'] in retained]))
        retention[method]=dict(overall=cell(rows),
            phones={ph:cell([r for r in rows if r['targetPhone']==ph]) for ph in sorted({r['targetPhone'] for r in rows})},
            ages={str(age):cell([r for r in rows if r['age']==age]) for age in range(6,13)},
            withheld={cid:support([r for r in rows if r['clipId']==cid]) for cid in sorted(set(corpus)-retained)})
    panels={}
    for population in ('crop','environment','knownExtension','synthetic','new'):
        selected=[clip for clip in plan['clips'] if clip['population']==population]
        panels[population]=dict(records={clip['id']:dict(sampleCount=clip['sampleCount'], category=clip['category'],
            speechScore=records[clip['id']]['speechScore'], decisions=decisions[clip['id']]) for clip in selected},
            categories={str(category):dict(total=sum(x['category']==category for x in selected),
                **{method:(sum(decisions[x['id']][method] for x in selected if x['category']==category)
                            if all(decisions[x['id']][method] is not None for x in selected if x['category']==category) else None)
                   for method in ('baseline','yamnet','combined')}) for category in {x['category'] for x in selected}})
    lost=[clip['id'] for clip in plan['clips'] if clip['population'] in ('corpus','crop')
          and clip['baseline'] and not records[clip['id']]['accepted']]
    return dict(retention=retention, panels=panels, lostPreviouslyRetainedSpeech=lost,
                childAndCropRetentionPass=not lost)


def run(digest, review_path):
    plan,binding=checked(digest);review=json.loads(Path(review_path).read_text())
    c.require(review['status']=='clear' and not review['blockingFindings'] and review['planSha256']==digest,
              'Matching independent source review required')
    for path, expected in review['sourceBindings'].items():c.require(c.sha(path)==expected,'Reviewed source changed')
    dest=c.OUTPUT/'scores';c.require(not dest.exists(),'No implicit restart');dest.mkdir()
    for key,value in ENVIRONMENT.items():os.environ[key]=value
    model=detector.load_model(VENDOR); artifacts=[]; first=None; started=time.monotonic()
    for index,clip in enumerate(plan['clips']):
        wave=detector.read_pcm(clip['audio']['path'],clip['audio']['sha256'],clip['sampleCount'])
        tick=time.monotonic();scores,summary=detector.infer(model,wave)
        if index==0:first=scores.copy()
        array_path=dest/f'{index:04d}.npy';np.save(array_path,scores,allow_pickle=False)
        record=dict(clipId=clip['id'],audio=clip['audio'],scores=c.pin(array_path),**summary,
                    inferenceSeconds=time.monotonic()-tick)
        record_path=dest/f'{index:04d}.json';c.write(record_path,record);artifacts.append(c.pin(record_path))
        if (index+1)%50==0:print(json.dumps(dict(completed=index+1,total=len(plan['clips']))),flush=True)
    clip=plan['clips'][0]
    repeated,_=detector.infer(model,detector.read_pcm(clip['audio']['path'],clip['audio']['sha256'],clip['sampleCount']))
    c.require(np.array_equal(first,repeated),'Repeated first recording changed after intervening inputs')
    repeat_path=dest/'repeat-first.npy';np.save(repeat_path,repeated,allow_pickle=False)
    checked(digest)
    c.write(c.OUTPUT/'inference-freeze.json',dict(complete=True,plan=binding,records=artifacts,
            repeatFirst=c.pin(repeat_path),exactRepeat=True,wallSeconds=time.monotonic()-started,**c.FLAGS))
    print(json.dumps(c.pin(c.OUTPUT/'inference-freeze.json')),flush=True)


def verify(digest, freeze_digest):
    plan,binding=checked(digest)
    freeze_pin=dict(path=str(c.OUTPUT/'inference-freeze.json'),sha256=freeze_digest);freeze=c.read(freeze_pin)
    c.require(freeze['complete'] and freeze['plan']==binding and freeze['exactRepeat'], 'Wrong inference freeze')
    c.require(len(freeze['records'])==len(plan['clips']), 'Incomplete inference')
    records={};first=None
    for clip,record_pin in zip(plan['clips'],freeze['records'],strict=True):
        record=c.read(record_pin);c.guard(record['scores']);scores=np.load(record['scores']['path'],allow_pickle=False)
        expected=detector.validate_scores(scores,clip['sampleCount'])
        c.require(record['clipId']==clip['id'] and record['audio']==clip['audio']
                  and all(record[k]==v for k,v in expected.items()), 'Saved prediction metadata mismatch')
        records[clip['id']]=expected
        if first is None:first=scores
    c.guard(freeze['repeatFirst'])
    c.require(np.array_equal(first,np.load(freeze['repeatFirst']['path'],allow_pickle=False)), 'Repeat artifact mismatch')
    result=dict(complete=True,plan=binding,inferenceFreeze=freeze_pin,**tables(plan,records),**c.FLAGS)
    c.write(c.OUTPUT/'results.json',result)
    print(json.dumps(dict(result=c.pin(c.OUTPUT/'results.json'),retentionPass=result['childAndCropRetentionPass'],
                         lostSpeech=len(result['lostPreviouslyRetainedSpeech']))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['declare','run','verify'])
    p.add_argument('--sha256');p.add_argument('--review');p.add_argument('--freeze-sha256');a=p.parse_args()
    if a.command=='declare':c.write(c.OUTPUT/'plan.json',declaration());print(json.dumps(c.pin(c.OUTPUT/'plan.json')))
    elif a.command=='run':run(a.sha256,a.review)
    else:verify(a.sha256,a.freeze_sha256)
