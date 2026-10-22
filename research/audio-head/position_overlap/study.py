"""Full-position VAD overlap diagnostic; no new withholding rule or labels."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
import torch
import multiphone_short_vad_filter as f
from position_inference import audio as a
from position_inference import verify as position

BASE=position.BASE
DIRECTORY=Path(__file__).resolve().parent
PROTOCOL=a.HERE/'../../docs/model/multiphone-position-overlap-protocol.md'
POLICIES={'short100':100,'default250':250}
NEW_IDS=['001040026','005600146','010420047','096110011']
STATES=('all','anyCenterInside','zeroCentersInside','occupancyFootprintDisjoint','poolingFootprintDisjoint')
read=position.read


def frontend_geometry(recipe):
    jump,receptive=1,1
    a.require(len(recipe['convKernel'])==len(recipe['convStride'])>0,'Missing convolution geometry')
    for kernel,stride in zip(recipe['convKernel'],recipe['convStride'],strict=True):
        a.require(type(kernel) is int and kernel>0 and type(stride) is int and stride>0,'Invalid convolution geometry')
        receptive+=(kernel-1)*jump;jump*=stride
    a.require((jump,receptive)==(320,400),'Unsupported frozen frontend geometry')
    return jump,receptive


def interval_overlap(interval,segments):
    start,end=interval
    return sum(max(0,min(end,s['end'])-max(start,s['start'])) for s in segments)


def measure(interval,pooling,samples,recipe,segments):
    f.study.validate_timestamps(segments,samples)
    jump,receptive=frontend_geometry(recipe);frames=a.local.convolution_frames(samples,recipe)
    a.require(isinstance(interval,list) and len(interval)==2 and all(type(x) is int for x in interval)
              and 0<=interval[0]<interval[1]<=frames,'Invalid occupied frame interval')
    start,end=interval
    a.require(pooling==[max(0,start-2),min(frames,end+2)] and all(type(x) is int for x in pooling),'Pooling context differs')
    # Double sample coordinates retain the exact half-sample centers.
    centers=[2*jump*i+receptive-1 for i in range(start,end)]
    inside=sum(any(2*s['start']<=c<2*s['end'] for s in segments) for c in centers)
    occupancy=[start*jump,(end-1)*jump+receptive]
    pooled=[pooling[0]*jump,(pooling[1]-1)*jump+receptive]
    a.require(0<=occupancy[0]<occupancy[1]<=samples and 0<=pooled[0]<pooled[1]<=samples,'Frontend footprint exceeds WAV')
    overlap=interval_overlap(occupancy,segments);pool_overlap=interval_overlap(pooled,segments)
    return dict(occupiedFrames=end-start,centersInside=inside,centerFraction=inside/(end-start),
        anyCenterInside=inside>0,zeroCentersInside=inside==0,
        occupancyFootprintSamples=occupancy,occupancyOverlapSamples=overlap,occupancyOverlapFraction=overlap/(occupancy[1]-occupancy[0]),
        occupancyFootprintDisjoint=overlap==0,poolingFootprintSamples=pooled,poolingOverlapSamples=pool_overlap,
        poolingOverlapFraction=pool_overlap/(pooled[1]-pooled[0]),poolingFootprintDisjoint=pool_overlap==0)


def inputs():
    pins={**{'approved/'+k:v for k,v in f.approved_context().items()},
        'geometryReport':a.binding(BASE/'position-scalars-v1/report.json',position.SCALAR_SHA),
        'positionFilter':a.binding(BASE/'position-filter-v1/report.json','4e34bc966f147c8d754c400c6de177f80353da42a36b3a8bc65f69baf745ae72'),
        'protocol':a.binding(PROTOCOL),'recipe':a.binding(a.local.RECIPE)}
    geometry=read(pins['geometryReport']);pins['cohort']=geometry['inputs']['cohort'];cohort=read(pins['cohort'])
    a.require(cohort['authorPartition']=='train' and len(cohort['clips'])==2500 and len(cohort['rows'])==28227
              and len({c['id'] for c in cohort['clips']})==2500 and len({r['id'] for r in cohort['rows']})==28227
              and set(geometry['clipArtifacts'])=={c['id'] for c in cohort['clips']}
              and geometry['complete'] is True and geometry['rowIds']==[r['id'] for r in cohort['rows']], 'Complete occurrence cohort required')
    recipe=read(pins['recipe']);frontend_geometry(recipe)
    baseline=read(pins['approved/approvedStudy']);filters=read(pins['positionFilter'])
    extra=next(r for r in filters['records'] if r['id']=='000530027')['default250Report'];pins['extraVAD']=extra
    extra_report=read(extra)
    a.require(extra_report['complete'] is True and extra_report['vad']['parameters']==f.study.PARAMS
              and extra_report['runtime']==f.study.runtime(),'Extra VAD provenance differs')
    # Include the waveform/model/source/job bindings behind this reused VAD report.
    pins.update({'extraInput/'+k:v for k,v in extra_report['inputBindings'].items()})
    reuse={};new=[]
    for clip in cohort['clips']:
        cid=clip['id'];audio=a.binding(clip['audioPath'],clip['audioSha256']);pins['audio/'+cid]=audio
        pins['geometry/'+cid]=geometry['clipArtifacts'][cid]
        if 'corpus/'+cid in baseline['records']:
            record=baseline['records']['corpus/'+cid];pin=baseline['recordBindings']['corpus/'+cid]
            a.require(read(pin)==record and record['clip']['audio']==audio and record['clip']['sampleCount']==clip['sampleCount'],
                      'Historical VAD record/audio differs')
            pins['vad/'+cid]=pin;reuse[cid]=dict(kind='historical',record=pin)
        elif cid=='000530027':
            a.require(extra_report['inputBindings']['audio']==audio and extra_report['vad']['sampleCount']==clip['sampleCount'],
                      'Extra VAD audio differs')
            reuse[cid]=dict(kind='position-filter',record=extra)
        else:new.append(cid)
    a.require(sorted(new)==NEW_IDS and len(reuse)==2496
              and sum(v['kind']=='historical' for v in reuse.values())==2495
              and sum(v['kind']=='position-filter' for v in reuse.values())==1,'Unexpected new/reused VAD coverage')
    for path in sorted(DIRECTORY.glob('*.py')):pins['source/'+path.name]=a.binding(path)
    pins['runtime/python']=a.binding(__import__('sys').executable)
    a.guard(pins);return pins,reuse,new


def declare(output):
    a.require(not output.exists() and output.resolve().is_relative_to(a.HERE/'outputs'),'Fresh ignored output required')
    pins,reuse,new=inputs();output.mkdir(mode=0o700,parents=True)
    plan=dict(inputs=pins,reuse=reuse,newIds=new,policies=POLICIES,frameStrideSamples=320,frameReceptiveFieldSamples=400,
        centerSampleFormula='320*i+199.5',intervalConvention='half-open samples',runtime=f.study.runtime(),
        diagnosticOnly=True,withholdingRuleChanged=False,learnerFeedbackEligible=False)
    a.write_json(output/'plan.json',plan);return a.binding(output/'plan.json')


def load(path,sha):
    pin=a.binding(path,sha);plan=read(pin);pins,reuse,new=inputs()
    a.require(plan['inputs']==pins and plan['reuse']==reuse and plan['newIds']==new and plan['policies']==POLICIES
              and plan['frameStrideSamples']==320 and plan['frameReceptiveFieldSamples']==400
              and plan['centerSampleFormula']=='320*i+199.5' and plan['intervalConvention']=='half-open samples'
              and plan['runtime']==f.study.runtime() and plan['diagnosticOnly'] is True
              and plan['withholdingRuleChanged'] is False and plan['learnerFeedbackEligible'] is False,'Declaration differs')
    return plan,pin


def support(rows):
    votes=[sum(r['raterCounts'][i] for r in rows) for i in range(3)]
    return dict(positions=len(rows),clips=len({r['clipId'] for r in rows}),speakers=len({r['speakerId'] for r in rows}),
        raterVotes=votes,rating0Positions=sum(r['raterCounts'][0]>0 for r in rows),
        below2Positions=sum(sum(r['raterCounts'][:2])>0 for r in rows),allTopPositions=sum(r['raterCounts']==[0,0,5] for r in rows))


def tables(rows):
    result={}
    for policy in POLICIES:
        populations={}
        for population in ('all','original','added'):
            selected=[r for r in rows if population=='all' or (r['legacyRowIndex'] is not None)==(population=='original')]
            ages={}
            for age in ('allAges','ages6to12','ages13plus'):
                age_rows=[r for r in selected if age=='allAges' or (6<=r['age']<=12 if age=='ages6to12' else r['age']>=13)]
                cells={}
                for phone in ('aggregate',*a.inference.TARGETS[:23]):
                    phone_rows=[r for r in age_rows if phone=='aggregate' or r['targetPhone']==phone]
                    cells[phone]={state:support([r for r in phone_rows if state=='all' or r['policies'][policy][state]]) for state in STATES}
                    fractions={key:None if not phone_rows else float(np.mean([r['policies'][policy][key] for r in phone_rows]))
                               for key in ('centerFraction','occupancyOverlapFraction','poolingOverlapFraction')}
                    cells[phone]['meanFractions']=fractions
                ages[age]=cells
            populations[population]=ages
        result[policy]=populations
        # Only disjoint position/vote counts add. Clips/speakers can span both populations.
        for age in populations['all']:
            for phone in populations['all'][age]:
                for state in STATES:
                    total=populations['all'][age][phone][state]
                    original=populations['original'][age][phone][state]
                    added=populations['added'][age][phone][state]
                    a.require(all(total[k]==original[k]+added[k] for k in
                                  ('positions','rating0Positions','below2Positions','allTopPositions'))
                              and total['raterVotes']==[x+y for x,y in zip(original['raterVotes'],added['raterVotes'],strict=True)],
                              'Original/added position or vote support does not reconcile')
    return result


def calculate(plan,root):
    pins=plan['inputs'];cohort=read(pins['cohort']);recipe=read(pins['recipe']);helper=f.study.load_helper(pins['approved/vendor/utils_vad.py'])
    clips={c['id']:c for c in cohort['clips']};by_clip=defaultdict(list)
    for row in cohort['rows']:by_clip[row['clipId']].append(row)
    measurements={};clip_records={};fresh_pins={}
    for cid,clip in clips.items():
        if cid in plan['reuse']:
            ref=plan['reuse'][cid];record=read(ref['record']);vad=record if ref['kind']=='historical' else record['vad'];pin=ref['record']
        else:
            pin=a.binding(root/'vad'/f'{cid}.json');record=read(pin);fresh_pins[cid]=pin
            a.require(record['audio']==pins['audio/'+cid] and record['sampleCount']==clip['sampleCount']
                      and record['runtime']==f.study.runtime() and record['parameters']==f.study.PARAMS,'New VAD binding differs')
            vad=record['vad']
        f.study.validate_probabilities(vad['probabilities'],clip['sampleCount'])
        segments={policy:f.short.segment(helper,vad['probabilities'],clip['sampleCount'],minimum) for policy,minimum in POLICIES.items()}
        a.require(segments['default250']==vad['timestamps'] and bool(segments['default250'])==vad['vad'],'Baseline probability segmentation differs')
        geometry=read(pins['geometry/'+cid]);expected=by_clip[cid]
        a.require(geometry['clipId']==cid and len(geometry['rows'])==len(expected),'Geometry coverage differs')
        clip_records[cid]=dict(audio=pins['audio/'+cid],sampleCount=clip['sampleCount'],vadRecord=pin,segments=segments,
                               source=plan['reuse'][cid]['kind'] if cid in plan['reuse'] else 'new')
        for row,g in zip(expected,geometry['rows'],strict=True):
            a.require(all(row[k]==g[k] for k in ('id','clipId','wordIndex','phoneIndex','canonicalIndex','targetPhone','legacyRowIndex')),
                      'Occurrence/geometry row identity differs')
            a.require(row['trainingEligible'] is True and row['targetPhone'] in a.inference.TARGETS[:23]
                      and len(row['raterCounts'])==3 and all(type(v) is int and v>=0 for v in row['raterCounts'])
                      and sum(row['raterCounts'])==5 and row['age']>=6,'Unsupported occurrence labels/age')
            start,end=g['intervalFrames']
            a.require(g['estimatedFrameCenterSeconds']==[(start*320+199.5)/16000,((end-1)*320+199.5)/16000],'Saved frame center mapping differs')
            measurements[row['id']]={**{k:row[k] for k in ('id','clipId','speakerId','age','targetPhone','wordIndex','phoneIndex',
                                                            'canonicalIndex','legacyRowIndex','raterCounts')},
                'intervalFrames':g['intervalFrames'],'poolingWindowFrames':g['estimatedPoolingWindowFrames'],
                'policies':{policy:measure(g['intervalFrames'],g['estimatedPoolingWindowFrames'],clip['sampleCount'],recipe,seg)
                            for policy,seg in segments.items()}}
    rows=[measurements[r['id']] for r in cohort['rows']]
    a.require(len(rows)==28227 and len(measurements)==28227 and set(clips)==set(clip_records),'Incomplete output coverage')
    return dict(complete=True,clips=clip_records,rows=rows,summary=tables(rows),freshVAD=fresh_pins,
        newVADInferences=4,reusedVADRecords=2496,frameTimesValidated=False,speechAtTargetValidated=False,
        diagnosticOnly=True,withholdingRuleChanged=False,trainingPerformed=False,thresholdFitted=False,authorTestRead=False,
        clinicalUseEligible=False,learnerFeedbackEligible=False)


def run(path,sha):
    torch.set_num_threads(2);plan,pin=load(path,sha);root=Path(path).resolve().parent
    a.write_json(root/'started.json',dict(plan=pin))
    try:
        cohort=read(plan['inputs']['cohort']);clips={c['id']:c for c in cohort['clips']};(root/'vad').mkdir(mode=0o700)
        helper=f.study.load_helper(plan['inputs']['approved/vendor/utils_vad.py'])
        model=torch.jit.load(plan['inputs']['approved/vendor/silero_vad.jit']['path'],map_location='cpu').eval()
        for cid in plan['newIds']:
            audio=plan['inputs']['audio/'+cid];samples=a.read_rating_pcm(Path(audio['path']),audio['sha256'])
            a.require(len(samples)==clips[cid]['sampleCount'],'New waveform length differs')
            with torch.inference_mode():vad=f.study.infer(helper,model,samples)
            a.write_json(root/'vad'/f'{cid}.json',dict(audio=audio,sampleCount=len(samples),vad=vad,
                parameters=f.study.PARAMS,runtime=f.study.runtime()))
            print(json.dumps(dict(newVAD=cid,frames=len(vad['probabilities']))),flush=True)
        report=calculate(plan,root);report['plan']=pin;a.guard(plan['inputs'])
        a.write_json(root/'report.json',report);return a.binding(root/'report.json')
    except Exception as error:
        a.write_json(root/'failure.json',dict(error=f'{type(error).__name__}: {error}'));raise


def verify(path,sha):
    torch.set_num_threads(2);plan,pin=load(path,sha);root=Path(path).resolve().parent
    expected=calculate(plan,root);expected['plan']=pin
    a.require(read(a.binding(root/'report.json'))==expected,'Saved overlap report differs')
    a.guard(plan['inputs']);return dict(verified=True,clips=2500,positions=28227,acousticInferencePerformed=False,
                                      report=a.binding(root/'report.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('declare','run','verify'))
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256')
    args=parser.parse_args();result=declare(args.output) if args.command=='declare' else globals()[args.command](args.plan,args.plan_sha256)
    print(json.dumps(result),flush=True)
