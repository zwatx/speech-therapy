"""Fixed full-utterance versus estimated-word-context pipeline sensitivity.

No training or correctness measurement. Canonical occupancy is not word timing;
all fixed cases remain visible, including crop alignment failures.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import torch

import multiphone_capture_sensitivity as capture
import multiphone_research_audio as raw
from multiphone_cache import atomic_json

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'experiments/multiphone-word-context-sensitivity-v1.json'
local, extraction = capture.local, capture.extraction
require, digest, pin, guard, read_bound = raw.require, raw.digest, raw.binding, raw.guard, raw.read_bound_json
read_json = capture.read_json
FLAGS = {k:False for k in ('trainingPerformed','modelSelectionPerformed','outerPerformanceEvaluationPerformed',
    'authorTestInferencePerformed','labelsTransferred','accuracyMeasured','calibrationMeasured','frameTimesValidated',
    'learnerFeedbackEligible','clinicalUseEligible')}
SOURCES = tuple(dict.fromkeys(capture.SOURCES + raw.RUNTIME_SOURCES + ('multiphone_word_context_sensitivity.py',)))
IDENTITY = capture.IDENTITY


class CropAlignmentFailure(ValueError):
    """Expected crop feasibility failure; never used for provenance/runtime errors."""


def convolution_geometry(mapping):
    receptive, stride = 1, 1
    for kernel, step in zip(mapping['convKernel'],mapping['convStride'],strict=True):
        receptive += (kernel-1)*stride; stride *= step
    require((stride,receptive)==(320,400),'Pinned convolution geometry differs')
    return stride,receptive


def crop_samples(interval, sample_count, padding=1600):
    require(padding==1600 and type(sample_count) is int and sample_count>=1600,'Invalid fixed crop policy')
    require(isinstance(interval,list) and len(interval)==2 and all(type(i) is int for i in interval),'Invalid frame interval type')
    start,end=interval
    if not 0<=start<end or (end-1)*320+400>sample_count:
        raise CropAlignmentFailure('Occupied word interval falls outside original convolution support')
    left,right=max(0,start*320-padding),min(sample_count,(end-1)*320+400+padding)
    if not 1600<=right-left<=480000:
        raise CropAlignmentFailure('Fixed crop violates the 0.1–30-second runtime limit')
    return [left,right]


def word_inventory(clip, score, cohort):
    words=score['words'];phones=[p for word in words for p in word['phones']]
    require(phones==clip['canonicalPhones'] and words and all(w['phones'] for w in words),'Canonical word flattening differs')
    offsets=np.cumsum([0]+[len(w['phones']) for w in words]).tolist()
    require(len(clip['targets'])==len({t['rowIndex'] for t in clip['targets']}),'Duplicate original target')
    result=[]
    for word_index in sorted({t['wordIndex'] for t in clip['targets']}):
        require(type(word_index) is int and 0<=word_index<len(words),'Original word index invalid')
        word=words[word_index];targets=[t for t in clip['targets'] if t['wordIndex']==word_index]
        for target in targets:
            row=cohort['rows'][target['rowIndex']]
            require(row['trainingEligible'] is True and row['clipId']==clip['id'] and row['targetWord']==word['text']
                    and target['rowId']==row['id'] and all(target[k]==row[k] for k in
                        ('targetPhone','targetId','wordIndex','phoneIndex'))
                    and type(target['phoneIndex']) is int and 0<=target['phoneIndex']<len(word['phones'])
                    and target['canonicalIndex']==offsets[word_index]+target['phoneIndex']
                    and word['phones'][target['phoneIndex']]==target['targetPhone'],'Word/target canonical identity differs')
        result.append({'wordId':clip['id']+'-word-'+str(word_index),'clipId':clip['id'],'wordIndex':word_index,
            'text':word['text'],'phones':word['phones'],'canonicalRange':[offsets[word_index],offsets[word_index+1]],
            'mappedTokenIds':clip['mappedTokenIds'][offsets[word_index]:offsets[word_index+1]],
            'targets':targets})
    return result


def occupancy(logp,tokens,positions,mapping):
    local.validate_log_prob(logp,len(logp))
    require(tokens and all(type(t) is int and 3<t<392 for t in tokens),'Invalid pinned canonical token sequence')
    minimum=len(tokens)+sum(a==b for a,b in zip(tokens,tokens[1:]))
    if len(logp)<minimum:raise CropAlignmentFailure('Canonical sequence cannot fit available crop CTC frames')
    try:return local.local_features(logp,tokens,positions,mapping)
    except ValueError as error:
        if str(error) in ('No valid CTC path despite sufficient frames','Canonical target state is absent or fragmented'):
            raise CropAlignmentFailure(str(error)) from error
        raise


def declare_geometry(clip,words,logp,mapping):
    convolution_geometry(mapping)
    try:
        states,_=occupancy(logp,clip['mappedTokenIds'],list(range(len(clip['mappedTokenIds']))),mapping)
    except CropAlignmentFailure as error:
        return [{**w,'status':'failed','failureStage':'original-word-alignment','reason':str(error)} for w in words]
    result=[]
    for word in words:
        first,last=word['canonicalRange'];span=[states[first]['intervalFrames'][0],states[last-1]['intervalFrames'][1]]
        try:
            sample_range=crop_samples(span,clip['sampleCount'])
            result.append({**word,'status':'prepared','sourceWordOccupancyFrames':span,'cropSampleRange':sample_range})
        except CropAlignmentFailure as error:
            result.append({**word,'status':'failed','failureStage':'crop-geometry','reason':str(error)})
    return result


def crop_clip(clip,word):
    targets=[{**t,'sourceCanonicalIndex':t['canonicalIndex'],'sourceWordIndex':t['wordIndex'],
              'canonicalIndex':t['phoneIndex'],'wordIndex':0} for t in word['targets']]
    return {'id':word['wordId'],'canonicalPhones':word['phones'],'mappedTokenIds':word['mappedTokenIds'],
            'targets':targets}


def write_crop(source_path,source_sha,sample_range,output):
    samples=capture.read_rating_pcm(source_path,source_sha).numpy()
    left,right=sample_range
    require(type(left) is int and type(right) is int and 0<=left<right<=len(samples),'Crop source sample range invalid')
    cropped=samples[left:right]
    payload,decoded=capture.pcm16_bytes(cropped)
    require(np.array_equal(cropped,decoded),'Crop PCM round trip changes original samples')
    with output.open('xb') as stream:output.chmod(0o600);stream.write(payload)
    output_pin=pin(output)
    require(np.array_equal(capture.read_rating_pcm(output,output_pin['sha256']).numpy(),cropped)
            and digest(source_path)==source_sha,'Saved crop differs or source waveform changed')
    return {'audioPath':output_pin['path'],'audioSha256':output_pin['sha256'],'sampleCount':len(cropped),
            'sourceSampleRange':sample_range,'sourceAudioSha256':source_sha}


def metadata_inputs(recipe):
    require(recipe==read_json(RECIPE) and recipe['paddingSamples']==1600 and recipe['strideSamples']==320
            and recipe['receptiveFieldSamples']==400 and recipe['device']=='cpu' and recipe['threads']==2
            and recipe['conditions']==['full-utterance','estimated-word-context']
            and recipe['originalParityAbsoluteTolerances']=={'ctcLogPosterior':0.,'scalar':0.,'phoneticPooled':2e-6,'probability':2e-6}
            and all(recipe[k] is False for k in FLAGS),'Fixed context diagnostic recipe differs')
    files={'recipe':pin(RECIPE),'protocol':pin(recipe['protocolPath'],recipe['protocolSha256']),
           **{'source/'+n:pin(HERE/n) for n in SOURCES}}
    previous,files['capturePlan']=read_bound(HERE/recipe['capturePlanPath'],recipe['capturePlanSha256'])
    report,files['captureReport']=read_bound(HERE/recipe['captureReportPath'],recipe['captureReportSha256'])
    require(previous['complete'] is True and previous['recipe']==read_json(capture.RECIPE)
            and previous['partition']=='innerValidationRows' and previous['fold']==0 and previous['authorPartition']=='train'
            and report['complete'] is True and report['planSha256']==recipe['capturePlanSha256']
            and all(previous[k] is False and report[k] is False for k in capture.FALSE_FLAGS),'Original capture scope differs')
    files.update({'capturePlan/'+k:v for k,v in previous['bindings'].items()})
    files.update({'captureReport/'+k:v for k,v in report['bindings'].items()})
    files.update({'captureSource/'+k:v for k,v in capture.recipe_inputs(previous['recipe']).items()})
    guard(files)
    binding=Path(previous['bindings']['featureBinding']['path'])
    bound=capture.frozen.load_bound(binding,read_json(capture.frozen.RECIPE))
    require(all(previous['bindings']['feature/'+k]==v for k,v in bound['bindings'].items()),'Original clean feature binding differs')
    original=read_json(Path(previous['bindings']['originalFeatures']['path']))
    manifest=read_json(Path(original['manifestPath']))
    capture.validate_selected_plan(previous,bound['cohort'],bound['splits'],manifest,original)
    phonetic_recipe=read_json(extraction.RECIPE)
    snapshot=HERE/'outputs/model-cache'/('models--'+phonetic_recipe['modelId'].replace('/','--'))/'snapshots'/phonetic_recipe['revision']
    contract,mapping,_,_,contract_pins=raw.load_contract(Path(recipe['rawContractPath']),recipe['rawContractSha256'],snapshot)
    files.update({'raw/'+k:v for k,v in contract_pins.items()})
    convolution_geometry(mapping)
    scores_bytes=local.pinned_bytes(local.METADATA,'resource/scores.json')
    files['canonicalWords']={'path':str((local.METADATA/'resource/scores.json').absolute()),'sha256':hashlib.sha256(scores_bytes).hexdigest()}
    scores=local.selected_json_objects(scores_bytes,{c['id'] for c in previous['clips']})
    words=[]
    for clip in previous['clips']:
        source=bound['cohort']['clips'][clip['clipIndex']]
        require(scores[clip['id']]['text']==source['text'],'Original canonical transcript differs')
        inventory=word_inventory(clip,scores[clip['id']],bound['cohort'])
        posterior=previous['bindings']['originalCTC/'+clip['id']]
        logp,_=capture.load_posteriors(Path(posterior['path']),posterior['sha256'])
        local.validate_log_prob(logp,local.convolution_frames(clip['sampleCount'],mapping))
        words.extend(declare_geometry(clip,inventory,logp,mapping))
    require(len(previous['clips'])==recipe['expectedClips']==5 and len(words)==recipe['expectedWords']==17
            and sum(len(w['targets']) for w in words)==recipe['expectedTargets']==23
            and len({t['rowIndex'] for w in words for t in w['targets']})==23,'Fixed word/target coverage differs')
    guard(files)
    return previous,bound,original,contract,mapping,snapshot,words,files


def prepare(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE/'outputs'),'Choose fresh ignored diagnostic output')
    recipe,recipe_pin=read_bound(RECIPE)
    previous,_,_,_,_,_,words,files=metadata_inputs(recipe)
    require(files['recipe']==recipe_pin,'Recipe changed during context preparation')
    plan={'complete':True,'schemaVersion':1,'recipe':recipe,'recipeSha256':recipe_pin['sha256'],'inputFiles':files,
          'clips':previous['clips'],'words':words,'authorPartition':'train','fold':0,'partition':'innerValidationRows',**FLAGS}
    guard(files);output.mkdir(parents=True,mode=0o700);atomic_json(output/'plan.json',plan)
    return {'planPath':str((output/'plan.json').absolute()),'planSha256':digest(output/'plan.json'),
            'clips':5,'words':len(words),'targets':23,'geometryFailures':sum(w['status']=='failed' for w in words)}


def validate_plan(plan,plan_pin):
    require(plan['complete'] is True and plan['recipeSha256']==digest(RECIPE) and plan['recipe']==read_json(RECIPE)
            and plan['authorPartition']=='train' and plan['fold']==0 and plan['partition']=='innerValidationRows'
            and all(plan[k] is False for k in FLAGS),'Context plan scope differs')
    guard({**plan['inputFiles'],'plan':plan_pin})
    result=metadata_inputs(plan['recipe']);previous,bound,original,contract,mapping,snapshot,words,files=result
    require(plan['clips']==previous['clips'] and plan['words']==words and plan['inputFiles']==files,
            'Prepared crop identities, geometry or source pins differ')
    return previous,bound,original,contract,mapping,snapshot,{**files,'plan':plan_pin}


def ctc_forward(audio,contract,inputs,directory,node):
    directory.mkdir(parents=True,mode=0o700)
    frames=local.convolution_frames(audio['sampleCount'],read_json(local.RECIPE))
    files={**inputs,'audio':{'path':audio['audioPath'],'sha256':audio['audioSha256']}}
    job={'schemaVersion':1,'researchOnly':True,'audioPath':audio['audioPath'],'audioSha256':audio['audioSha256'],
        'sampleCount':audio['sampleCount'],'expectedFrames':frames,'bindings':files,
        'ctcCheckpoint':contract['ctcCheckpoint'],'sessionOptions':contract['ctcSessionOptions']}
    atomic_json(directory/'ctc-job.json',job);job_pin=pin(directory/'ctc-job.json')
    subprocess.run([node,str(HERE/'multiphone_research_ctc.ts'),str((directory/'ctc-job.json').absolute()),job_pin['sha256']],
        check=True,env={**os.environ,'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2'})
    result,result_pin=read_bound(directory/'ctc.json')
    require(result['complete'] is True and result['jobSha256']==job_pin['sha256']
            and result['audioSha256']==audio['audioSha256'] and result['sampleCount']==audio['sampleCount']
            and result['frames']==frames and result['checkpoint']==contract['ctcCheckpoint']
            and result['sessionOptions']==contract['ctcSessionOptions'] and result['fetchAttempts']==0
            and result['posteriorsPath']=='ctc.f32','Context CTC output binding differs')
    logp,posterior=capture.load_posteriors(directory/'ctc.f32',result['posteriorsSha256'])
    local.validate_log_prob(logp,frames)
    return logp,{'job':job_pin,'result':result_pin,'posterior':posterior},result


def confidence(p):
    p=np.asarray(p)
    return {'meanClassProbabilities':p.mean(0).tolist(),'meanMaximumProbability':float(p.max(1).mean()),
            'meanEntropy':float(-(p*np.log(p.clip(1e-12,1))).sum(1).mean()),'argmaxCounts':np.bincount(p.argmax(1),minlength=3).tolist()}


def paired_summary(full,cropped):
    return {**capture.probability_shift(full,cropped),'fullConfidence':confidence(full),'cropConfidence':confidence(cropped)}


def features_for(logp,hidden,clip,mapping):
    # Check feasibility separately so only known alignment failures are retained.
    occupancy(logp,clip['mappedTokenIds'],[t['canonicalIndex'] for t in clip['targets']],mapping)
    return capture.aligned_features(logp,hidden,clip,mapping)


def save_feature_array(path,values):
    require(values.dtype==np.float32 and values.ndim==2 and values.shape[1]==1037 and np.isfinite(values).all(),
            'Invalid context feature matrix')
    with path.open('xb') as stream:path.chmod(0o600);np.save(stream,values,allow_pickle=False)
    require(np.array_equal(np.load(path,allow_pickle=False),values),'Saved context features differ')
    return pin(path)


def alignment_movement(full,crop,offset):
    return {'rowId':full['rowId'],
        'firstOccupiedFrameCenterShiftSamples':offset+(crop['intervalFrames'][0]-full['intervalFrames'][0])*320,
        'lastOccupiedFrameCenterShiftSamples':offset+(crop['intervalFrames'][1]-full['intervalFrames'][1])*320,
        'meaning':'Estimated canonical occupancy movement in source sample coordinates; not true timing error'}


def run(plan_path,plan_sha,node='node'):
    plan,plan_pin=read_bound(plan_path,plan_sha)
    previous,bound,original,contract,mapping,snapshot,inputs=validate_plan(plan,plan_pin)
    output=plan_path.parent/'diagnostic';require(not output.exists(),'Fresh diagnostic only; preserve incomplete evidence')
    output.mkdir(mode=0o700);started=time.perf_counter();derived={}
    try:
        torch.set_num_threads(2);os.environ['HF_HUB_OFFLINE']=os.environ['TRANSFORMERS_OFFLINE']='1'
        encoder=extraction.PhoneticEncoder(snapshot,read_json(extraction.RECIPE));heads=capture.load_heads(previous['recipe'])
        base_rows={r['rowIndex']:r for r in original['rows']};full_results={}
        # Complete all five original parity checks before any cropped-audio forward.
        for clip in plan['clips']:
            directory=output/'full'/clip['id']
            audio={k:clip[k] for k in ('audioPath','audioSha256','sampleCount')}
            logp,pins,runtime=ctc_forward(audio,contract,inputs,directory,node)
            derived.update({'full/'+clip['id']+'/'+k:v for k,v in pins.items()})
            hidden=encoder(capture.read_rating_pcm(Path(audio['audioPath']),audio['audioSha256']))
            targets,scalars,pooled,diagnostic=features_for(logp,hidden,clip,mapping)
            values=np.concatenate((pooled,scalars),axis=1)
            predicted={regime:capture.probabilities(head,values,targets) for regime,head in heads.items()}
            positions=[bound['positions'][r['rowIndex']] for r in targets]
            old_pin=previous['bindings']['originalCTC/'+clip['id']]
            old,_=capture.load_posteriors(Path(old_pin['path']),old_pin['sha256'])
            limits=plan['recipe']['originalParityAbsoluteTolerances']
            parity={'ctcLogPosterior':capture.assert_parity(logp,old,limits['ctcLogPosterior'],'context original CTC'),
                'scalar':capture.assert_parity(scalars,bound['scalars'][positions],limits['scalar'],'context original scalars'),
                'phoneticPooled':capture.assert_parity(pooled,bound['arrays']['target'][positions],limits['phoneticPooled'],'context original vectors'),
                'probabilities':{regime:capture.assert_parity(p,[heads[regime]['predictions'][r['rowIndex']] for r in targets],
                                                            limits['probability'],regime+' context original probabilities') for regime,p in predicted.items()}}
            require(all(all(row[k]==base_rows[row['rowIndex']][k] for k in IDENTITY+('intervalFrames','estimatedPoolingWindowFrames'))
                        for row in targets),'Context original identity/window parity failed')
            parity['windowsExact']=True
            derived['fullFeatures/'+clip['id']]=save_feature_array(directory/'features.npy',values)
            full_results[clip['id']]={'clipId':clip['id'],'speakerId':clip['speakerId'],'age':clip['age'],'targets':targets,
                'probabilities':{k:v.tolist() for k,v in predicted.items()},'parity':parity,'canonicalPathDiagnostics':diagnostic,'ctcRuntime':runtime}
        guard({**inputs,**derived})
        atomic_json(output/'original-parity.json',{'complete':True,'planSha256':plan_sha,'clips':full_results})
        derived['originalParity']=pin(output/'original-parity.json')
        print('All five original context-comparison parity checks passed',flush=True)
        words=[];by_clip={c['id']:c for c in plan['clips']}
        for word in plan['words']:
            clip=by_clip[word['clipId']]
            if word['status']=='failed':words.append({**word,'outcome':'failed'});continue
            directory=output/'words'/word['wordId'];directory.mkdir(parents=True,mode=0o700)
            audio=write_crop(Path(clip['audioPath']),clip['audioSha256'],word['cropSampleRange'],directory/'crop.wav')
            derived['crop/'+word['wordId']]={'path':audio['audioPath'],'sha256':audio['audioSha256']}
            crop=crop_clip(clip,word)
            frames=local.convolution_frames(audio['sampleCount'],mapping)
            minimum=len(crop['mappedTokenIds'])+sum(a==b for a,b in zip(crop['mappedTokenIds'],crop['mappedTokenIds'][1:]))
            if frames<minimum:
                words.append({**word,'outcome':'failed','failureStage':'crop-path-feasibility','reason':'Canonical sequence cannot fit available crop CTC frames','waveform':audio});continue
            logp,pins,runtime=ctc_forward(audio,contract,{**inputs,'cropAudio':derived['crop/'+word['wordId']]},directory/'ctc',node)
            derived.update({'cropCTC/'+word['wordId']+'/'+k:v for k,v in pins.items()})
            hidden=encoder(capture.read_rating_pcm(Path(audio['audioPath']),audio['audioSha256']))
            try:targets,scalars,pooled,diagnostic=features_for(logp,hidden,crop,mapping)
            except CropAlignmentFailure as error:
                words.append({**word,'outcome':'failed','failureStage':'crop-alignment','reason':str(error),'waveform':audio,'ctcRuntime':runtime});continue
            values=np.concatenate((pooled,scalars),axis=1)
            predicted={regime:capture.probabilities(head,values,targets) for regime,head in heads.items()}
            derived['cropFeatures/'+word['wordId']]=save_feature_array(directory/'features.npy',values)
            full=full_results[clip['id']];positions={t['rowIndex']:i for i,t in enumerate(full['targets'])}
            offsets=[positions[t['rowIndex']] for t in targets]
            paired={regime:np.asarray(full['probabilities'][regime])[offsets] for regime in heads}
            words.append({**word,'outcome':'success','waveform':audio,'cropTargets':targets,
                'probabilities':{k:v.tolist() for k,v in predicted.items()},'fullProbabilities':{k:v.tolist() for k,v in paired.items()},
                'shiftsFromFull':{k:paired_summary(paired[k],v) for k,v in predicted.items()},
                'estimatedAlignmentMovement':[alignment_movement(full['targets'][i],t,word['cropSampleRange'][0]) for i,t in zip(offsets,targets,strict=True)],
                'canonicalPathDiagnostics':diagnostic,'ctcRuntime':runtime})
            print('Completed context word '+word['wordId'],flush=True)
        successes=[w for w in words if w['outcome']=='success'];successful_rows=[t['rowIndex'] for w in successes for t in w['targets']]
        require(len(words)==17 and len({w['wordId'] for w in words})==17 and len(successful_rows)==len(set(successful_rows)),
                'Context diagnostic word/target coverage differs')
        summary={regime:paired_summary(np.concatenate([w['fullProbabilities'][regime] for w in successes]),
                                       np.concatenate([w['probabilities'][regime] for w in successes])) for regime in heads} if successes else {}
        clip_summary={cid:{regime:paired_summary(np.concatenate([w['fullProbabilities'][regime] for w in successes if w['clipId']==cid]),
            np.concatenate([w['probabilities'][regime] for w in successes if w['clipId']==cid])) for regime in heads}
            for cid in by_clip if any(w['clipId']==cid for w in successes)}
        report={'schemaVersion':1,'complete':True,'planPath':plan_pin['path'],'planSha256':plan_sha,'recipeSha256':plan['recipeSha256'],
            'inputFiles':inputs,'derivedFiles':derived,'plannedSpeakers':5,'plannedWords':17,'plannedTargets':23,
            'successfulWords':len(successes),'failedWords':17-len(successes),'successfulTargets':len(successful_rows),
            'failedTargets':23-len(successful_rows),'words':words,'originals':full_results,
            'summaryTargetWeighted':summary,'perClipSummary':clip_summary,'confidenceIntervalsComputed':False,
            'elapsedSeconds':time.perf_counter()-started,'interpretation':plan['recipe']['interpretation'],**FLAGS}
        guard({**inputs,**derived});atomic_json(output/'report.json',report)
        return {'complete':True,'reportPath':str((output/'report.json').absolute()),'reportSha256':digest(output/'report.json'),
                'successfulWords':len(successes),'failedWords':17-len(successes),'successfulTargets':len(successful_rows)}
    except Exception as error:
        atomic_json(output/'failure.json',{'complete':False,'planSha256':plan_sha,'error':f'{type(error).__name__}: {error}',
                                          'elapsedSeconds':time.perf_counter()-started})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('prepare');p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('run');p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--node',default='node')
    args=parser.parse_args()
    if args.command=='prepare':result=prepare(args.output)
    else:
        with (args.plan.parent/'.context.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);result=run(args.plan,args.plan_sha256,args.node)
    print(json.dumps(result,indent=2),flush=True)
