"""Exercise the unchanged short speech filter with explicit repeated positions."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
import multiphone_short_vad_filter as f
from position_inference import audio as a
from position_inference import verify as position

BASE=position.BASE
DIRECTORY=Path(__file__).resolve().parent
PROTOCOL=a.HERE/'../../docs/model/multiphone-position-filter-protocol.md'
POSITION_SHA='8883aa10bb76701d968a2fee03d61800f14d5470831c0a6bdb0486e98d2cf6c2'
INTEGRATION_SHA='097f7cfe66f7de0a133a8d5745e46f50e0ed706b20b897646539eee354683341'
PROMPT=dict(schemaVersion=2,language='en',transcript='BOB B',
    words=[dict(text='BOB',phones=['B','AA1','B']),dict(text='B',phones=['B'])],
    targets=[dict(id='last-b',wordIndex=1,phoneIndex=0,targetPhone='B'),
             dict(id='first-b',wordIndex=0,phoneIndex=0,targetPhone='B'),
             dict(id='middle-b',wordIndex=0,phoneIndex=2,targetPhone='B')])
read=position.read


def inputs():
    pins={**{'approved/'+k:v for k,v in f.approved_context().items()},
          'positions':a.binding(BASE/'position-audio-v2/report.json',POSITION_SHA),
          'legacyIntegration':a.binding(BASE/'short-filter-integration-v1/verification.json',INTEGRATION_SHA),
          'protocol':a.binding(PROTOCOL)}
    previous=read(pins['positions']);position_plan=read(previous['plan'])
    pins.update({'position/'+k:v for k,v in position_plan['inputs'].items()})
    pins['positionPlan']=previous['plan']
    integration=read(pins['legacyIntegration']);vad=read(pins['approved/approvedStudy'])
    cases=[dict(id=c['clipId'],population='speech',source=c['report'],freshRaw=False) for c in previous['cases']]
    cases.append(dict(id='be-crop',population='short-speech-control',source=integration['cases']['be']['rawReport'],freshRaw=False))
    for name in ('zero','gaussian','sine440','dog','helicopter'):
        reference=vad['inputBindings']['syntheticRaw/'+name] if name in ('zero','gaussian','sine440') else integration['cases'][name]['rawReport']
        original=read(reference)
        cases.append(dict(id=name,population='known-challenge',referenceRaw=reference,
                          audio=original['inputBindings']['audio'],freshRaw=True))
    for case in cases:
        pin=case['referenceRaw'] if case['freshRaw'] else case['source'];r=read(pin)
        pins['raw/'+case['id']]=pin
        pins.update({'rawInput/'+case['id']+'/'+k:v for k,v in r['inputBindings'].items()})
        for name,sha in r['filesSha256'].items():pins['rawArtifact/'+case['id']+'/'+name]=a.binding(Path(pin['path']).parent/name,sha)
    for path in sorted(DIRECTORY.glob('*.py')):pins['source/'+path.name]=a.binding(path)
    a.guard(pins)
    return pins,cases,position_plan


def declare(output):
    a.require(not output.exists() and output.resolve().is_relative_to(a.HERE/'outputs'),'Fresh ignored output required')
    pins,cases,previous=inputs();output.mkdir(mode=0o700,parents=True)
    plan=dict(inputs=pins,cases=cases,prompt=PROMPT,bundle=previous['bundles']['unweighted-all-age'],
              snapshot=previous['snapshot'],node=previous['inputs']['node'],contract=previous['inputs']['contract'],
              researchOnly=True,thresholdAdjustmentPerformed=False,learnerFeedbackEligible=False)
    a.write_json(output/'plan.json',plan);return a.binding(output/'plan.json')


def load(path,sha):
    pin=a.binding(path,sha);plan=read(pin);pins,cases,previous=inputs()
    a.require(plan['inputs']==pins and plan['cases']==cases and plan['prompt']==PROMPT
              and plan['bundle']==previous['bundles']['unweighted-all-age']
              and plan['snapshot']==previous['snapshot'] and plan['node']==previous['inputs']['node']
              and plan['contract']==previous['inputs']['contract'] and plan['researchOnly'] is True
              and plan['thresholdAdjustmentPerformed'] is False and plan['learnerFeedbackEligible'] is False,
              'Declared integration inputs differ')
    return plan,pin


def expected_decision(phone,intervals,policy):
    available=phone['ratingAvailable'] and bool(intervals)
    reasons=list(phone['reasons'])+([] if intervals else ['no-silero-speech-segment'])
    return dict(policyId=policy,ratingAvailable=available,status='research-evidence-present' if available else 'abstain',
                reasons=reasons,speechPresenceValidated=False,promptMatchValidated=False,pronunciationCorrectnessValidated=False)


def check_targets(source,filtered,available):
    a.require(len(source)==len(filtered),'Filtered target count differs')
    for original,result in zip(source,filtered,strict=True):
        expected={k:original[k] for k in ('id','targetPhone','wordIndex','phoneIndex')}
        expected['subjectiveCorpusRatingProbabilities']=original['subjectiveCorpusRatingProbabilities'] if available else None
        a.require(result==expected,'Filtered occurrence identity/order or probability differs')


def check_case(plan,case,source_pin,directory):
    original=read(source_pin);a.guard(original['inputBindings'])
    source_dir=Path(source_pin['path']).parent
    for name,sha in original['filesSha256'].items():a.binding(source_dir/name,sha)
    if case['freshRaw']:
        reference=read(case['referenceRaw'])
        a.require(original['schemaVersion']==2 and original['inputBindings']['audio']==case['audio']
                  and read(original['inputBindings']['prompt'])==PROMPT
                  and original['headManifestSha256']==plan['bundle']['manifest']['sha256']
                  and original['contractSha256']==plan['contract']['sha256']
                  and original['filesSha256']['ctc.f32']==reference['filesSha256']['ctc.f32'],
                  'Repeated-prompt raw provenance or same-WAV CTC parity differs')
    else:a.require(source_pin==case['source'],'Reused raw source differs')
    audio=original['inputBindings']['audio'];samples=a.read_rating_pcm(Path(audio['path']),audio['sha256'])
    ctc=read(a.binding(source_dir/'ctc.json',original['filesSha256']['ctc.json']))
    job=read(a.binding(source_dir/'ctc-job.json',original['filesSha256']['ctc-job.json']))
    a.require(original['complete'] is True and original['researchOnly'] is True
              and original['clinicalUseEligible'] is False and original['learnerFeedbackEligible'] is False
              and original['trainingPerformed'] is False and ctc==original['ctcRuntime']
              and ctc['complete'] is True and ctc['fetchAttempts']==0
              and ctc['jobSha256']==original['filesSha256']['ctc-job.json']
              and ctc['posteriorsSha256']==original['filesSha256']['ctc.f32'] and ctc['posteriorsPath']=='ctc.f32'
              and ctc['audioSha256']==job['audioSha256']==audio['sha256']
              and ctc['sampleCount']==job['sampleCount']==len(samples)
              and ctc['frames']==job['expectedFrames']
              and job['schemaVersion']==1 and job['researchOnly'] is True
              and job['bindings']==original['inputBindings'] and Path(job['audioPath']).absolute()==Path(audio['path']).absolute()
              and ctc['checkpoint']==job['ctcCheckpoint'] and ctc['sessionOptions']==job['sessionOptions'],
              'Raw CTC job/result/audio chain differs')
    payload=(source_dir/'ctc.f32').read_bytes();logp=np.frombuffer(payload,dtype='<f4').reshape(-1,392)
    phone=f.gate.assess(samples.numpy(),logp)
    raw_vocabulary=read(original['inputBindings']['phonetic/vocab.json'])
    raw_mapping=json.loads(a.local.RECIPE.read_text());prompt=read(original['inputBindings']['prompt'])
    frames=a.local.convolution_frames(len(samples),raw_mapping)
    a.require(ctc['frames']==frames,'CTC metadata frame count differs')
    validate=a.validate_prompt if original['schemaVersion']==2 else a.raw.validate_prompt
    canonical=validate(prompt,raw_mapping,raw_vocabulary,a.inference.TARGETS[:23],frames)
    a.require(original['canonicalPrompt']==canonical,'Raw canonical occurrence mapping differs')
    estimates,diagnostic=a.local.local_features(logp,canonical['mappedTokenIds'],[r['canonicalIndex'] for r in canonical['targets']],raw_mapping)
    a.require(original['canonicalPathDiagnostics']==diagnostic,'Raw path diagnostics differ')
    a.require(len(original['targets'])==len(canonical['targets']),'Raw target count differs')
    for target,identity,estimate in zip(original['targets'],canonical['targets'],estimates,strict=True):
        a.require(all(target[k]==v for k,v in identity.items()) and all(target[k]==v for k,v in estimate.items()),'Raw occurrence geometry differs')
        start,end=estimate['intervalFrames']
        a.require(target['estimatedPoolingWindowFrames']==[max(0,start-2),min(frames,end+2)],'Raw pooling window differs')
    features=np.load(source_dir/'features.npy',allow_pickle=False)
    a.require(features.dtype==np.float32 and features.shape==(len(estimates),1037)
              and np.array_equal(features[:,1024:],np.asarray([e['scalarFeatures'] for e in estimates],dtype=np.float32)),
              'Raw feature shape/type or scalar values differ')
    manifest=original['inputBindings']['headManifest'];head=a.inference.load_head(Path(manifest['path']).parent,manifest['sha256'])
    probability=head.predict(features,np.array([t['modelTargetId'] for t in original['targets']],dtype=np.int64))
    a.require(np.array_equal(probability,np.array([t['subjectiveCorpusRatingProbabilities'] for t in original['targets']])),'Raw head replay differs')
    short=read(a.binding(directory/'finalreport.json'));baseline=read(a.binding(directory/'default250/finalreport.json'))
    phone_report=read(a.binding(directory/'default250/phone-evidence.json'))
    a.require(phone_report['decision']==phone and phone_report['sourceReport']==source_pin,'Phone evidence chain differs')
    helper=f.study.load_helper(plan['inputs']['approved/vendor/utils_vad.py'])
    for report,minimum,policy in ((baseline,250,'research-phone-evidence-and-silero-v1'),
                                 (short,100,'research-phone-evidence-and-silero-short100-v1')):
        a.guard(report['inputBindings']);vad=report['vad']
        f.study.validate_probabilities(vad['probabilities'],len(samples))
        segments=f.short.segment(helper,vad['probabilities'],len(samples),minimum)
        a.require(report['schemaVersion']==1 and report['complete'] is True and report['researchOnly'] is True
                  and report['clinicalUseEligible'] is False and report['learnerFeedbackEligible'] is False
                  and report['trainingPerformed'] is False and report['thresholdAdjustmentPerformed'] is False
                  and report['sourceReport']==source_pin and report['inputBindings']['audio']==audio
                  and vad['sampleCount']==len(samples) and vad['parameters']=={**f.study.PARAMS,'min_speech_duration_ms':minimum}
                  and vad['timestamps']==segments and vad['vad']==bool(segments)
                  and report['runtime']==f.study.runtime() and report['phoneEvidenceDecision']==phone
                  and report['decision']==expected_decision(phone,segments,policy),'Filter policy/lineage differs')
        check_targets(original['targets'],report['targets'],report['decision']['ratingAvailable'])
    a.require(short['vad']['probabilities']==baseline['vad']['probabilities'],'Policies used different VAD probabilities')
    a.require(short['inputBindings']['default250Report']==a.binding(directory/'default250/finalreport.json'),'Baseline result binding differs')
    a.binding(source_pin['path'],source_pin['sha256'])
    return dict(id=case['id'],population=case['population'],sourceSchema=original['schemaVersion'],targets=len(original['targets']),
        source=source_pin,report=a.binding(directory/'finalreport.json'),default250Report=a.binding(directory/'default250/finalreport.json'),
        phoneEvidence=phone,short100=short['decision'],default250=baseline['decision'],
        exactOccurrenceOutput=True,sameWavCtcExact=True if case['freshRaw'] else None)


def run(path,sha):
    torch.set_num_threads(2);plan,pin=load(path,sha);root=Path(path).resolve().parent
    a.write_json(root/'started.json',dict(plan=pin));records=[]
    try:
        prompt=root/'repeat-prompt.json';a.write_json(prompt,PROMPT)
        for case in plan['cases']:
            if case['freshRaw']:
                output=root/'raw'/case['id'];bundle=plan['bundle']
                a.run(SimpleNamespace(contract=a.CONTRACT,contract_sha256=plan['contract']['sha256'],
                    wav=Path(case['audio']['path']),wav_sha256=case['audio']['sha256'],prompt=prompt,prompt_sha256=a.digest(prompt),
                    bundle=Path(bundle['directory']),manifest_sha256=bundle['manifest']['sha256'],
                    phonetic_snapshot=Path(plan['snapshot']),output=output,node=plan['node']['path']))
                source=a.binding(output/'report.json')
            else:source=case['source']
            destination=root/'filtered'/case['id']
            f.filter_report(Path(source['path']),source['sha256'],destination)
            records.append(check_case(plan,case,source,destination))
            print(json.dumps(dict(case=case['id'],short100=records[-1]['short100']['ratingAvailable'],default250=records[-1]['default250']['ratingAvailable'])),flush=True)
        a.guard(plan['inputs'])
        a.write_json(root/'report.json',dict(complete=True,plan=pin,records=records,rawInferences=5,vadInferences=len(records),
            independentValidation=False,trainingPerformed=False,thresholdAdjustmentPerformed=False,authorTestRead=False,
            clinicalUseEligible=False,learnerFeedbackEligible=False))
        return a.binding(root/'report.json')
    except Exception as error:
        a.write_json(root/'failure.json',dict(error=f'{type(error).__name__}: {error}',completed=records));raise


def verify(path,sha):
    torch.set_num_threads(2);plan,pin=load(path,sha);root=Path(path).resolve().parent;r=read(a.binding(root/'report.json'))
    a.require(r['complete'] is True and r['plan']==pin and len(r['records'])==len(plan['cases'])
              and r['rawInferences']==5 and r['vadInferences']==13
              and all(r[k] is False for k in ('independentValidation','trainingPerformed','thresholdAdjustmentPerformed',
                                             'authorTestRead','clinicalUseEligible','learnerFeedbackEligible')),'Complete research report required')
    for case,record in zip(plan['cases'],r['records'],strict=True):
        a.require(check_case(plan,case,record['source'],root/'filtered'/case['id'])==record,'Saved regression record differs')
    a.guard(plan['inputs']);return dict(verified=True,cases=len(r['records']),acousticInferencePerformed=False,report=a.binding(root/'report.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('declare','run','verify'))
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256')
    args=parser.parse_args();result=declare(args.output) if args.command=='declare' else globals()[args.command](args.plan,args.plan_sha256)
    print(json.dumps(result),flush=True)
