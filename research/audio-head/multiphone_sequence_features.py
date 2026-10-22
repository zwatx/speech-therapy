"""Complete author-train sequence-feature export from frozen CTC cache; no fitting."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
import multiphone_sequence_preflight as preflight

HERE=preflight.HERE
PROTOCOL=HERE/'../../docs/model/multiphone-sequence-feature-protocol.md'
APPROVED=HERE/'outputs/multiphone-20260927/sequence-ctc-preflight-v1/report.json'
APPROVED_SHA='422bfac1040d3cec900787774908f81a08d5dcd7b3912540114b009f993751c9'
CLIP_COUNT,ROW_COUNT=2495,14837
FEATURE_NAMES=['canonicalVsAlternativesLogRatio','canonicalVsDeletionLogRatio',
               'canonicalVsBestOtherTokenLogRatio','canonicalLogLikelihoodPerFrame']
require,binding,read_bound,guard,write_new=(preflight.require,preflight.binding,preflight.read_bound,
                                         preflight.guard,preflight.write_new)


def numerical_bytes(value):
    return json.dumps(preflight.serializable(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def joined_clips(cohort,manifest,index,recipe,vocabulary):
    """Complete identity join; uses eligibility/canonical metadata, never rating values."""
    require(cohort['authorPartition']==manifest['authorPartition']=='train','Author-train required')
    eligible=[i for i,r in enumerate(cohort['rows']) if r['trainingEligible']]
    expected_clips={cohort['rows'][i]['clipIndex'] for i in eligible}
    require({c['clipIndex'] for c in manifest['clips']}==expected_clips and
            set(index['entries'])=={c['id'] for c in manifest['clips']},'Full clip coverage differs')
    preflight.local.validate_manifest_rows(manifest,cohort)
    clips=[]
    for source in manifest['clips']:
        mapped,tokens,flags=preflight.local.canonical_mapping(source['canonicalPhones'],vocabulary,recipe)
        require(mapped==source['mappedTokens'] and tokens==source['mappedTokenIds'] and
                flags==source['mappingAmbiguities'],'Canonical token mapping differs')
        entry=index['entries'][source['id']]
        require(entry['clipId']==source['id'] and entry['sampleCount']==source['sampleCount'] and
                entry['audioSha256']==source['audioSha256'] and entry['configSha256']==index['configSha256'] and
                entry['vocabularySize']==392 and
                entry['frames']==preflight.local.convolution_frames(source['sampleCount'],recipe),'CTC identity/geometry differs')
        clip={k:source[k] for k in ('id','clipIndex','speakerId','sampleCount','audioPath','audioSha256',
                     'canonicalPhones','mappedTokens','mappedTokenIds','mappingAmbiguities','targetRows')}
        clips.append(dict(**clip,frames=entry['frames'],dtype='<f4',shape=[entry['frames'],392]))
    return eligible,clips


def inputs():
    _,small_pins=preflight.inputs()
    approved_pin=binding(APPROVED,APPROVED_SHA);approved=read_bound(approved_pin)
    require(approved['complete'] is True and approved['exactRepeat'] is True and
            approved['maximumAbsoluteDifference']<=preflight.TOLERANCE and approved['targetSlots']==18 and
            approved['inputBindings']==small_pins and approved['runtime']==preflight.runtime(),
            'Approved preflight/source/runtime differs')
    approved_plan=read_bound(approved['plan'])
    require(approved_plan['inputBindings']==small_pins,'Approved preflight plan differs')
    pins={**small_pins,'approvedPreflight':approved_pin,'approvedPreflightPlan':approved['plan'],
          **{'preflightArtifact/'+k:v for k,v in approved['artifacts'].items()}}
    cohort,manifest,index,recipe,vocabulary=(read_bound(pins[k]) for k in ('cohort','manifest','index','recipe','vocabulary'))
    eligible,clips=joined_clips(cohort,manifest,index,recipe,vocabulary)
    require(len(eligible)==ROW_COUNT and len(clips)==CLIP_COUNT and manifest['fullCohortCoverage'] is True and
            manifest['eligibleCohortRows']==ROW_COUNT and len({cohort['rows'][i]['targetPhone'] for i in eligible})==23,
            'Fixed corpus coverage differs')
    cache=Path(pins['index']['path']).parent
    for clip in clips:
        entry=index['entries'][clip['id']];path=(cache/entry['path']).resolve()
        require(path.is_relative_to(cache) and path.stat().st_size==clip['frames']*392*4,'Posterior path/size differs')
        clip['posterior']=pins['posterior/'+clip['id']]=binding(path,entry['sha256'])
        clip['audio']=pins['audio/'+clip['id']]=binding(clip['audioPath'],clip['audioSha256'])
    pins['exportProtocol']=binding(PROTOCOL)
    pins['exportSource']=binding(__file__)
    pins['exportTests']=binding(HERE/'test_multiphone_sequence_features.py')
    guard(pins)
    return eligible,clips,pins


def declare(output):
    output=Path(output).resolve()
    require(not output.exists() and output.is_relative_to(HERE/'outputs'),'Fresh ignored output required')
    eligible,clips,pins=inputs();output.mkdir(parents=True,mode=0o700)
    return write_new(output/'plan.json',dict(declaredAt=datetime.now(timezone.utc).isoformat(),rowIndices=eligible,
        clips=clips,inputBindings=pins,featureNames=FEATURE_NAMES,candidateTokenIds=preflight.CANDIDATES,
        runtime=preflight.runtime(),featureCalculationPerformed=False,trainingPerformed=False,
        modelInferencePerformed=False,labelEvaluationPerformed=False,authorTestRead=False))


def load_plan(path,sha):
    path=Path(path).resolve();require(path.is_relative_to(HERE/'outputs'),'Plan must remain in ignored outputs')
    plan=read_bound(dict(path=str(path),sha256=sha));eligible,clips,pins=inputs()
    require(plan['rowIndices']==eligible and plan['clips']==clips and plan['inputBindings']==pins and
            plan['featureNames']==FEATURE_NAMES and plan['candidateTokenIds']==preflight.CANDIDATES and
            plan['runtime']==preflight.runtime() and all(plan[k] is False for k in
                ('featureCalculationPerformed','trainingPerformed','modelInferencePerformed','labelEvaluationPerformed','authorTestRead')),
            'Export declaration differs')
    return plan


def feature_rows(computed,clip):
    require(type(clip['frames']) is int and clip['frames']>0 and len(computed['slots'])==len(clip['targetRows']),
            'Invalid frame/slot coverage')
    canonical=computed['canonicalLogLikelihood']
    require(np.isfinite(canonical),'Undefined canonical likelihood')
    rows=[]
    for slot,target in zip(computed['slots'],clip['targetRows'],strict=True):
        require(slot['target']==target and slot['likelihoods']['position']==target['canonicalIndex'] and
                slot['likelihoods']['canonicalToken']==clip['mappedTokenIds'][target['canonicalIndex']] and
                slot['likelihoods']['candidateTokenIds']==preflight.CANDIDATES and
                len(slot['likelihoods']['replacementLogLikelihoods'])==388,'Computed slot identity/coverage differs')
        values=[slot['summary'][name] for name in FEATURE_NAMES[:3]]+[canonical/clip['frames']]
        require(all(type(v) in (int,float) and np.isfinite(v) for v in values),'Undefined/nonfinite feature; no imputation')
        vector=np.asarray(values,dtype=np.float32)
        require(np.isfinite(vector).all(),'Float32 feature conversion overflow')
        rows.append(dict(**target,clipId=clip['id'],tokenId=slot['likelihoods']['canonicalToken'],features=vector.tolist()))
    return rows


def arrange_rows(eligible,rows):
    require(len(rows)==len(eligible) and len(set(eligible))==len(eligible) and
            len({r['rowIndex'] for r in rows})==len(rows) and {r['rowIndex'] for r in rows}==set(eligible),
            'Feature row coverage differs; no duplicate, omission or substitution permitted')
    indexed={r['rowIndex']:r for r in rows};ordered=[indexed[i] for i in eligible]
    matrix=np.asarray([r['features'] for r in ordered],dtype=np.float32)
    require(matrix.shape==(len(eligible),4) and np.isfinite(matrix).all(),'Invalid final feature matrix')
    return ordered,matrix


def read_posterior(clip):
    guard({'posterior':clip['posterior'],'audio':clip['audio']})
    logp=np.fromfile(clip['posterior']['path'],dtype='<f4').reshape(clip['shape'])
    preflight.local.validate_log_prob(logp,clip['frames'])
    return logp


def run(path,sha):
    path=Path(path).resolve();plan=load_plan(path,sha);root=path.parent;results=root/'clips'
    require(not results.exists() and not (root/'features.json').exists() and not (root/'features.npy').exists(),
            'No implicit restart or overwrite')
    results.mkdir(mode=0o700);torch.set_num_threads(2)
    artifacts={};rows=[];preflight_checks={};repeat_checks={};current=None
    try:
        for clip in plan['clips']:
            current=clip['id'];computed=preflight.core_clip(read_posterior(clip),clip)
            # Publish raw evidence first so an undefined derived feature cannot silently discard its clip.
            artifacts[current]=write_new(results/(current+'.json'),dict(clip=clip,computed=computed))
            rows.extend(feature_rows(computed,clip))
            if len(artifacts)%100==0:
                print(json.dumps(dict(clipsSaved=len(artifacts),rowsDerived=len(rows))),flush=True)
            if current in preflight.EXPECTED_IDS:
                approved=read_bound(plan['inputBindings']['preflightArtifact/'+current+'/core'])
                require(numerical_bytes(computed)==numerical_bytes(approved),'Approved three-clip numerical evidence differs')
                preflight_checks[current]=dict(exact=True,numericalSha256=hashlib.sha256(numerical_bytes(computed)).hexdigest())
        ordered,matrix=arrange_rows(plan['rowIndices'],rows)
        require(len(artifacts)==CLIP_COUNT and len(ordered)==ROW_COUNT,'Incomplete export')
        for clip in plan['clips']:
            if clip['id'] not in preflight.EXPECTED_IDS:continue
            current=clip['id'];repeated=preflight.core_clip(read_posterior(clip),clip)
            saved=read_bound(artifacts[current])
            require(numerical_bytes(repeated)==numerical_bytes(saved['computed']),'Fixed three-clip repeat differs')
            repeat_checks[current]=dict(exact=True,numericalSha256=hashlib.sha256(numerical_bytes(repeated)).hexdigest())
        require(set(preflight_checks)==set(repeat_checks)==set(preflight.EXPECTED_IDS),'Preflight/repeat coverage differs')
        with (root/'features.npy').open('xb') as stream:np.save(stream,matrix,allow_pickle=False)
        (root/'features.npy').chmod(0o600)
        matrix_pin=binding(root/'features.npy')
        guard({**plan['inputBindings'],**{'clip/'+k:v for k,v in artifacts.items()},'matrix':matrix_pin,
               'plan':dict(path=str(path),sha256=sha)})
        return write_new(root/'features.json',dict(complete=True,fullCohortCoverage=True,authorPartition='train',
            plan=dict(path=str(path),sha256=sha),inputBindings=plan['inputBindings'],runtime=preflight.runtime(),
            rowIndices=plan['rowIndices'],rows=ordered,featureNames=FEATURE_NAMES,
            matrix=dict(**matrix_pin,dtype='float32',shape=list(matrix.shape)),clipArtifacts=artifacts,
            eligibleCohortRows=len(ordered),clips=len(artifacts),candidateTokenIds=preflight.CANDIDATES,
            preflightVerification=preflight_checks,repeatVerification=repeat_checks,
            featureCalculationPerformed=True,trainingPerformed=False,modelInferencePerformed=False,
            labelEvaluationPerformed=False,authorTestRead=False,clinicalUseEligible=False,learnerFeedbackEligible=False,
            limitations=['Restricted decoder-token likelihood ratios are not pronunciation correctness or produced-phone labels.',
                'Provisional canonical mapping; no encoder inference, fitting or quality evaluation in this export.']))
    except Exception as error:
        write_new(root/'failure.json',dict(complete=False,clipId=current,error=f'{type(error).__name__}: {error}',
            clipsSaved=len(artifacts),rowsDerived=len(rows),clipArtifacts=artifacts))
        raise


def restore_numbers(value):
    if isinstance(value,str) and value=='-Infinity':return float('-inf')
    if isinstance(value,dict):return {k:restore_numbers(v) for k,v in value.items()}
    if isinstance(value,list):return [restore_numbers(v) for v in value]
    return value


def validate_export(path,sha):
    """Read-only byte/row/summary replay; never evaluate SequenceCTC or a model."""
    from multiphone_sequence_ctc import summarize_slot
    report_pin=dict(path=str(Path(path).resolve()),sha256=sha);report=read_bound(report_pin)
    plan=load_plan(report['plan']['path'],report['plan']['sha256'])
    require(report['complete'] is True and report['fullCohortCoverage'] is True and report['authorPartition']=='train' and
            report['inputBindings']==plan['inputBindings'] and report['runtime']==plan['runtime'] and
            report['featureNames']==FEATURE_NAMES and report['candidateTokenIds']==preflight.CANDIDATES and
            report['rowIndices']==plan['rowIndices'] and report['eligibleCohortRows']==ROW_COUNT and report['clips']==CLIP_COUNT and report['featureCalculationPerformed'] is True and
            all(report[k] is False for k in ('trainingPerformed','modelInferencePerformed','labelEvaluationPerformed',
                                             'authorTestRead','clinicalUseEligible','learnerFeedbackEligible')),
            'Completed export metadata differs')
    require(set(report['clipArtifacts'])=={c['id'] for c in plan['clips']},'Clip artifact coverage differs')
    rows=[];checked={}
    for clip in plan['clips']:
        saved=read_bound(report['clipArtifacts'][clip['id']])
        require(saved['clip']==clip,'Saved clip input or mapping differs')
        computed=restore_numbers(saved['computed'])
        for slot in computed['slots']:
            require(slot['summary']==summarize_slot(slot['likelihoods']) and
                    slot['likelihoods']['canonicalLogLikelihood']==computed['canonicalLogLikelihood'],
                    'Stored likelihood summary differs')
        rows.extend(feature_rows(computed,clip))
        if clip['id'] in preflight.EXPECTED_IDS:
            approved=read_bound(plan['inputBindings']['preflightArtifact/'+clip['id']+'/core'])
            require(numerical_bytes(computed)==numerical_bytes(approved),'Stored preflight evidence differs')
            checked[clip['id']]=dict(exact=True,numericalSha256=hashlib.sha256(numerical_bytes(computed)).hexdigest())
    ordered,expected=arrange_rows(plan['rowIndices'],rows)
    matrix_pin={k:report['matrix'][k] for k in ('path','sha256')};guard({'matrix':matrix_pin})
    with Path(matrix_pin['path']).open('rb') as stream:matrix=np.load(stream,allow_pickle=False)
    require(report['matrix']['dtype']=='float32' and report['matrix']['shape']==[ROW_COUNT,4] and
            matrix.dtype==np.float32 and matrix.shape==(ROW_COUNT,4) and np.array_equal(matrix,expected) and
            report['rows']==ordered and report['preflightVerification']==checked and report['repeatVerification']==checked,
            'Matrix/row identity or stored three-clip verification differs')
    guard({**plan['inputBindings'],**{'clip/'+k:v for k,v in report['clipArtifacts'].items()},
           'matrix':matrix_pin,'report':report_pin,'plan':report['plan']})
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['declare','run']);parser.add_argument('--output',type=Path)
    parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256')
    args=parser.parse_args()
    if args.command=='declare':require(args.output is not None,'Output required');result=declare(args.output)
    else:
        require(args.plan is not None and args.plan_sha256,'Plan and SHA required');result=run(args.plan,args.plan_sha256)
    print(json.dumps(result,indent=2))
