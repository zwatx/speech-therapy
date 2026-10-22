"""Fitting-only cached CTC sequence likelihood preflight; no model fitting or inference."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import torch
import multiphone_local_features as local

HERE=Path(__file__).resolve().parent
BASE=HERE/'outputs/multiphone-20260926'
PROTOCOL=HERE/'../../docs/model/multiphone-sequence-ctc-preflight-protocol.md'
CANDIDATES=list(range(4,392))
EXPECTED_IDS=['000050175','000540123','000560117']
TOLERANCE=1e-8
PINS={
    'cohort':(BASE/'cohort.json','33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805'),
    'splits':(BASE/'splits.json','b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf'),
    'manifest':(BASE/'ctc-local-full/manifest.json','65c3118b2ff14e7fcb115a8c0fb2fa195a6811ef14f3523eebd8b8902849e4d5'),
    'index':(BASE/'ctc-local-full/ctc-frames/index.json','ce21dcc8b47b6383509f64282adebe752bb79442231917a4012cb0c30845dc3e'),
    'config':(BASE/'ctc-local-full/ctc-frames/config.json','89854c61a0396090dd934b936a9853440e5e7f5723e61cb2d08d4bebfd7dc76a'),
    'recipe':(local.RECIPE,'6ada55352a010f566ee3ebdcad36d90fd9c5a0da236cf2016bb2f6fc3d473eb0'),
    'warmConfig':(BASE/'phonetic-head-target-scalars-child-only-f0-s7-lr0003/config.json',
                  'e2996d39d97ae371e70b52863132eb247536c604d7c7084d949197c06c0b3cf8')}
require=local.require


def binding(path,expected=None):
    path=Path(path).resolve();sha=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):sha.update(block)
    require(expected is None or sha.hexdigest()==expected,'Pinned input differs: '+str(path))
    return dict(path=str(path),sha256=sha.hexdigest())


def read_bound(pin):
    binding(pin['path'],pin['sha256'])
    return json.loads(Path(pin['path']).read_text())


def guard(pins):
    seen={}
    for pin in pins.values():
        if pin['path'] not in seen:seen[pin['path']]=binding(pin['path'])['sha256']
        require(seen[pin['path']]==pin['sha256'],'Input changed: '+pin['path'])


def serializable(value):
    if isinstance(value,float):
        require(not np.isnan(value) and value!=float('inf'),'Invalid likelihood or timing')
        return '-Infinity' if value==float('-inf') else value
    if isinstance(value,dict):return {k:serializable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [serializable(v) for v in value]
    return value


def write_new(path,value):
    with path.open('x') as stream:
        path.chmod(0o600);json.dump(serializable(value),stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    return binding(path)


def runtime():
    return dict(python=sys.version,executable=binding(sys.executable),numpy=np.__version__,torch=str(torch.__version__),
                device='cpu',threads=2,oracleDtype='float64',oracleChunkHypotheses=32)


def select_clips(cohort,splits,warm,manifest):
    require(cohort['authorPartition']==splits['authorPartition']==manifest['authorPartition']=='train','Author-train required')
    fold=splits['folds'][0]
    fit=[i for i in fold['innerFitRows'] if cohort['rows'][i]['trainingEligible'] and 6<=cohort['rows'][i]['age']<=12]
    require(fit==warm['fitRows'] and warm['fold']==0 and warm['regime']=='child-only','Warm child fit membership differs')
    members=[{cohort['rows'][i]['speakerId'] for i in indices} for indices in
             (fit,fold['innerValidationRows'],fold['outerHoldoutRows'])]
    require(all(not members[i]&members[j] for i in range(3) for j in range(i)),'Same-fold speaker overlap')
    ids={cohort['rows'][i]['clipIndex'] for i in fit}
    require(len(ids)>=3,'Need three fitting clips')
    selected=local.geometry_selection(cohort['clips'],list(ids))
    indexed={c['clipIndex']:c for c in manifest['clips']}
    require(len(indexed)==len(manifest['clips']),'Duplicate manifest clip')
    fit_set=set(fit);clips=[]
    for index in selected:
        clip=indexed[index];source=cohort['clips'][index]
        require(all(clip[k]==source[k] for k in ('id','speakerId','audioPath','audioSha256','sampleCount')),
                'Selected source identity differs')
        targets=clip['targetRows']
        require(bool(targets) and len({r['rowIndex'] for r in targets})==len(targets) and
                len({r['canonicalIndex'] for r in targets})==len(targets) and {r['rowIndex'] for r in targets}==
                {i for i in fit if cohort['rows'][i]['clipIndex']==index},'Selected clip target membership differs')
        for row in targets:
            original=cohort['rows'][row['rowIndex']]
            require(row['rowIndex'] in fit_set and row['rowId']==original['id'] and
                    all(row[k]==original[k] for k in ('targetId','targetPhone','wordIndex','phoneIndex')) and
                    clip['canonicalPhones'][row['canonicalIndex']]==original['targetPhone'], 'Target slot differs')
        # Only identity and geometry leave this reader; rater counts are never copied or consulted.
        clips.append({k:clip[k] for k in ('id','clipIndex','speakerId','sampleCount','audioPath','audioSha256',
                     'canonicalPhones','mappedTokens','mappedTokenIds','mappingAmbiguities','targetRows')})
    return clips


def inputs():
    pins={name:binding(path,sha) for name,(path,sha) in PINS.items()}
    meta={name:read_bound(pin) for name,pin in pins.items()}
    manifest,index,config,recipe=(meta[k] for k in ('manifest','index','config','recipe'))
    require(manifest['cohortSha256']==pins['cohort']['sha256'] and manifest['splitsSha256']==pins['splits']['sha256'] and
            manifest['recipeSha256']==pins['recipe']['sha256'] and config['manifestSha256']==pins['manifest']['sha256'] and
            index['configSha256']==pins['config']['sha256'] and index['complete'] is True and
            config['dtype']=='float32-little-endian-log-softmax' and config['shape']=='frames,392' and
            config['frameStrideSamples']==320 and config['frameReceptiveFieldSamples']==400,'Cache lineage differs')
    pins['vocabulary']=binding(manifest['vocabularyPath'],manifest['vocabularySha256'])
    vocabulary=read_bound(pins['vocabulary'])
    require(len(vocabulary)==392 and vocabulary['<pad>']==0 and
            manifest['vocabularySha256']==config['checkpoint']['vocabularyFileSha256'],'Vocabulary differs')
    clips=select_clips(meta['cohort'],meta['splits'],meta['warmConfig'],manifest)
    require([c['id'] for c in clips]==EXPECTED_IDS and sum(len(c['targetRows']) for c in clips)==18,'Fixed geometry selection differs')
    cache=Path(pins['index']['path']).parent
    for clip in clips:
        mapped,tokens,flags=local.canonical_mapping(clip['canonicalPhones'],vocabulary,recipe)
        require(mapped==clip['mappedTokens'] and tokens==clip['mappedTokenIds'] and flags==clip['mappingAmbiguities'],
                'Canonical mapping differs')
        entry=index['entries'][clip['id']];path=(cache/entry['path']).resolve()
        require(path.is_relative_to(cache) and entry['clipId']==clip['id'] and entry['sampleCount']==clip['sampleCount'] and
                entry['audioSha256']==clip['audioSha256'] and entry['configSha256']==pins['config']['sha256'] and
                entry['vocabularySize']==392 and entry['frames']==local.convolution_frames(clip['sampleCount'],recipe) and
                path.stat().st_size==entry['frames']*392*4,'CTC entry identity or shape differs')
        clip['posterior']=pins['posterior/'+clip['id']]=binding(path,entry['sha256'])
        clip['audio']=pins['audio/'+clip['id']]=binding(clip['audioPath'],clip['audioSha256'])
        clip['frames']=entry['frames'];clip['dtype']='<f4';clip['shape']=[entry['frames'],392]
    for name,sha in config['sourceSha256'].items():pins['upstreamSource/'+name]=binding(HERE/name,sha)
    for name in ('multiphone_local_features.py','alignment_pilot.py','multiphone_sequence_ctc.py',
                 'test_multiphone_sequence_ctc.py','multiphone_sequence_preflight.py','test_multiphone_sequence_preflight.py'):
        pins['source/'+name]=binding(HERE/name)
    require(binding(local.__file__)['sha256']==manifest['generatorSha256'],'Upstream manifest generator differs')
    pins['protocol']=binding(PROTOCOL)
    pins['notes']=binding(PROTOCOL.with_name('multiphone-sequence-ctc-notes.md'))
    guard(pins)
    return clips,pins


def declare(output):
    output=Path(output).resolve()
    require(not output.exists() and output.is_relative_to(HERE/'outputs'),'Fresh ignored output required')
    clips,pins=inputs();output.mkdir(parents=True,mode=0o700)
    return write_new(output/'plan.json',dict(declaredAt=datetime.now(timezone.utc).isoformat(),clips=clips,inputBindings=pins,
        candidateTokenIds=CANDIDATES,oracleAbsoluteTolerance=TOLERANCE,runtime=runtime(),
        selectionRule='fold0 child fitting clips; duration then ID; shortest, upper median, longest; all18target slots',
        featureCalculationPerformed=False,modelInferencePerformed=False,trainingPerformed=False,authorTestRead=False))


def load_plan(path,sha):
    require(Path(path).resolve().is_relative_to(HERE/'outputs'),'Plan must remain in ignored outputs')
    plan=read_bound(dict(path=str(path),sha256=sha));clips,pins=inputs()
    require(plan['clips']==clips and plan['inputBindings']==pins and plan['candidateTokenIds']==CANDIDATES and
            plan['oracleAbsoluteTolerance']==TOLERANCE and plan['runtime']==runtime() and
            plan['featureCalculationPerformed'] is False and plan['modelInferencePerformed'] is False and
            plan['trainingPerformed'] is False and plan['authorTestRead'] is False,'Declaration differs')
    return plan


def torch_ctc(logp,hypotheses,chunk=32):
    """Independent full-sequence oracle; consume stored log probabilities directly."""
    values=np.asarray(logp,dtype=np.float64)
    require(values.ndim==2 and len(values)>0 and values.shape[1]>1 and not np.isnan(values).any() and not np.isposinf(values).any() and
            (values<=1e-6).all() and
            np.allclose(np.logaddexp.reduce(values,axis=1),0,atol=3e-5,rtol=0),'Invalid log posterior matrix')
    require(type(chunk) is int and 1<=chunk<=32 and len(hypotheses)>0,'Invalid oracle chunk')
    require(all(all(type(t) is int and 0<t<values.shape[1] for t in h) for h in hypotheses),'Invalid oracle targets')
    tensor=torch.from_numpy(values);results=[]
    for offset in range(0,len(hypotheses),chunk):
        batch=hypotheses[offset:offset+chunk]
        targets=torch.tensor([t for h in batch for t in h],dtype=torch.long)
        lp=tensor[:,None,:].expand(-1,len(batch),-1).contiguous()
        with torch.no_grad():
            loss=torch.nn.functional.ctc_loss(lp,targets,torch.full((len(batch),),len(values),dtype=torch.long),
                torch.tensor([len(h) for h in batch],dtype=torch.long),blank=0,reduction='none',zero_infinity=False)
        scores=(-loss).tolist()
        require(all(not np.isnan(v) and v!=float('inf') for v in scores),'Invalid oracle likelihood')
        results.extend(scores)
    return results


def difference(left,right):
    require(not np.isnan(left) and not np.isnan(right) and left!=float('inf') and right!=float('inf'),
            'Invalid likelihood comparison')
    if left==float('-inf') or right==float('-inf'):
        require(left==right,'Impossible-path disagreement');return 0.
    return abs(left-right)


def core_clip(logp,clip):
    from multiphone_sequence_ctc import SequenceCTC,summarize_slot
    engine=SequenceCTC(logp,clip['mappedTokenIds'],blank=0)
    slots=[]
    for row in clip['targetRows']:
        likelihoods=engine.slot_likelihoods(row['canonicalIndex'],CANDIDATES)
        require(likelihoods['position']==row['canonicalIndex'] and
                likelihoods['canonicalToken']==clip['mappedTokenIds'][row['canonicalIndex']] and
                likelihoods['candidateTokenIds']==CANDIDATES and len(likelihoods['replacementLogLikelihoods'])==388,
                'Core target/candidate coverage differs')
        slots.append(dict(target=row,likelihoods=likelihoods,summary=summarize_slot(likelihoods)))
    return dict(canonicalLogLikelihood=float(engine.log_probability),slots=slots)


def run(path,sha):
    path=Path(path);plan=load_plan(path,sha);root=path.parent;results=root/'results'
    require(not results.exists() and not (root/'report.json').exists(),'No implicit restart or overwrite')
    results.mkdir(mode=0o700);torch.set_num_threads(2);artifacts={};records=[]
    try:
        for clip in plan['clips']:
            guard(plan['inputBindings'])
            logp=np.fromfile(clip['posterior']['path'],dtype='<f4').reshape(clip['shape'])
            local.validate_log_prob(logp,clip['frames'])
            started=time.perf_counter();computed=core_clip(logp,clip);first_seconds=time.perf_counter()-started
            artifacts[clip['id']+'/core']=write_new(results/(clip['id']+'-core.json'),computed)
            started=time.perf_counter();repeated=core_clip(logp,clip);repeat_seconds=time.perf_counter()-started
            first_bytes=json.dumps(serializable(computed),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            repeat_bytes=json.dumps(serializable(repeated),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            require(first_bytes==repeat_bytes,'Core repeat differs')
            started=time.perf_counter();canonical_oracle=torch_ctc(logp,[clip['mappedTokenIds']])[0]
            differences=[difference(computed['canonicalLogLikelihood'],canonical_oracle)];slots=[]
            for item in computed['slots']:
                position=item['target']['canonicalIndex'];target=clip['mappedTokenIds']
                hypotheses=[target[:position]+[token]+target[position+1:] for token in CANDIDATES]
                hypotheses.append(target[:position]+target[position+1:])
                oracle=torch_ctc(logp,hypotheses)
                core=item['likelihoods'];values=core['replacementLogLikelihoods']+[core['deletionLogLikelihood']]
                diffs=[difference(a,b) for a,b in zip(values,oracle,strict=True)]
                diffs.append(difference(core['canonicalLogLikelihood'],canonical_oracle))
                diffs.append(difference(values[CANDIDATES.index(core['canonicalToken'])],canonical_oracle))
                differences.extend(diffs)
                slots.append({**item,'oracleReplacementLogLikelihoods':oracle[:-1],
                              'oracleDeletionLogLikelihood':oracle[-1],'maximumAbsoluteDifference':max(diffs)})
            record=dict(clip=clip,canonicalLogLikelihood=computed['canonicalLogLikelihood'],
                canonicalOracleLogLikelihood=canonical_oracle,slots=slots,exactRepeat=True,
                coreNumericalSha256=hashlib.sha256(first_bytes).hexdigest(),
                repeatNumericalSha256=hashlib.sha256(repeat_bytes).hexdigest(),
                maximumAbsoluteDifference=max(differences),parityPassed=max(differences)<=TOLERANCE,
                timingSeconds=dict(coreInitial=first_seconds,coreRepeat=repeat_seconds,oracle=time.perf_counter()-started))
            artifacts[clip['id']+'/comparison']=write_new(results/(clip['id']+'-comparison.json'),record)
            require(record['parityPassed'],'CTC oracle differs beyond absolute tolerance')
            records.append(record)
        guard({**plan['inputBindings'],**artifacts,'plan':dict(path=str(path),sha256=sha)})
        report=dict(complete=True,plan=dict(path=str(path.resolve()),sha256=sha),inputBindings=plan['inputBindings'],
            artifacts=artifacts,records=records,clips=3,targetSlots=18,candidatesPerSlot=388,
            deletionHypotheses=18,slotReferenceHypotheses=7002,canonicalReferenceHypotheses=3,maximumAbsoluteDifference=max(r['maximumAbsoluteDifference'] for r in records),
            exactRepeat=True,runtime=runtime(),featureCalculationPerformed=True,modelInferencePerformed=False,
            trainingPerformed=False,labelEvaluationPerformed=False,authorTestRead=False,
            clinicalUseEligible=False,learnerFeedbackEligible=False,
            limitations=['Three fitting-only duration-selected clips; no rating evaluation or validation/outer predictions.',
                'Timings are one initial calculation and one repeat, not a general runtime benchmark.',
                'Provisional canonical mapping; no produced-phone or pronunciation correctness ground truth.'])
        return write_new(root/'report.json',report)
    except Exception as error:
        write_new(root/'failure.json',dict(complete=False,error=f'{type(error).__name__}: {error}',completedClips=len(records),artifacts=artifacts))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['declare','run'])
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256')
    args=parser.parse_args()
    if args.command=='declare':require(args.output is not None,'Output required');result=declare(args.output)
    else:
        require(args.plan is not None and args.plan_sha256,'Plan and SHA required');result=run(args.plan,args.plan_sha256)
    print(json.dumps(result,indent=2))
