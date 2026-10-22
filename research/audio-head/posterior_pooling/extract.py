"""Rating-free, source-bound CPU posterior-pooling preflight; no fitting route."""
from __future__ import annotations

import argparse
import ast
import copy
import json
from pathlib import Path
import platform
import resource
import tempfile
import time

import numpy as np

from middle_layer import extract as base
from temporal_pooling import extract as temporal
from lexical_feasibility.study import word_group
import multiphone_local_features as local
from multiphone_phonetic_features import PhoneticEncoder, file_binding, guard, pooled_vectors, read_json, require, digest
from speechocean_r_probe import read_rating_pcm
from posterior_pooling import core

HERE, ROOT, BASE = base.HERE, base.ROOT, base.BASE
PROTOCOL = ROOT/'docs/model/posterior-pooling-preflight-v1.md'
PINS = {
    'temporalPlan': (BASE/'temporal-pooling-v1/plan.json','76ce734cf674c21b4d4e2f2c02c8db57461fb43adf63fedd3380bcc08c7cc88d'),
    'temporalReport': (BASE/'temporal-pooling-v1/features/report.json','33fc0c5b2936f546cdbd20304e58cd2d4e674362543c9458b08a0bc20a4992e0'),
    'temporalStudy': (BASE/'temporal-pooling-heads-v1/plan.json','3dccff741a91de7185484479d467d732dca5cbd100d59b33b7b32b142626a151'),
    'positionPlan': base.PINS['positions'], 'positionReport': base.PINS['referenceReport'],
    'historicalPlan': (BASE/'lexical-seed-replication-v1/plan.json','130992603ce99158345f31ae62f427f0230b0d5503e9ac65d5b8bad55ee6cc26'),
    'scalarPlan': (BASE/'position-scalars-v1/plan.json','d404c3762dc2bb70105dde70b8cc030b6ebda8e4ee74c06d908a251d27643cca'),
    'scalarReport': (BASE/'position-scalars-v1/report.json','5b2828cec062b50c575334c8f4182e1d7a712c869bf6ae90867417a9eb5698b9'),
}
FLAGS = dict(labelsUsedForExtraction=False, trainingPerformed=False, authorTestRead=False,
    clinicalUseEligible=False, learnerJudgmentsEnabled=False, producedPhoneTruth=False,
    newAlignmentPerformed=False, encoderUpdated=False)
RECIPE = dict(version='posterior-pooling-cpu-preflight-v1', core=core.POLICY,
    device='cpu', width=1024, fullVocabulary=392, fitJob='seed17-unweighted-child-only-pca16-scalars-s0-w0',
    durationOrder='sampleCount then clipId; shortest/lower-median/longest distinct fit clips',
    hardwareProbe='global longest of all1040; no labels or fitting',
    repeat='fit-shortest and global-longest start/end candidate and historical hard means bit exact',
    historicalParity='unchanged pooled_vectors; np.array_equal, no tolerance or substitution',
    numericalModels='quantized ONNX CTC weights and original full-precision phonetic hidden states are distinct',
    diagnostics='descriptive only; no kernel, subset, threshold or stopping selection', **FLAGS)
ROW_FIELDS = ('id','clipId','targetId','rowIndex','outputIndex','canonicalIndex','wordIndex','phoneIndex',
              'targetPhone','intervalFrames','estimatedPoolingWindowFrames')


def write_new(path,value):
    with Path(path).open('x') as stream:
        Path(path).chmod(0o600); json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False); stream.write('\n')
    return file_binding(Path(path))


def sources():
    """Bind the transitive local import closure plus actual numerical library sources."""
    paths={Path(__file__),Path(core.__file__),Path(__file__).with_name('test_extract.py'),Path(__file__).with_name('test_core.py'),Path(__file__).with_name('test_rounding.py'),Path(__file__).with_name('__init__.py')}
    queue=list(paths)
    while queue:
        path=queue.pop()
        for node in ast.walk(ast.parse(path.read_text())):
            modules=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            for module in modules:
                root=path.parent if isinstance(node,ast.ImportFrom) and node.level else HERE
                if isinstance(node,ast.ImportFrom):
                    for _ in range(max(0,node.level-1)): root=root.parent
                stem=root.joinpath(*module.split('.')) if module else root
                candidates=[stem.with_suffix('.py'),stem/'__init__.py']
                if isinstance(node,ast.ImportFrom): candidates.extend(stem/(alias.name+'.py') for alias in node.names)
                for candidate in candidates:
                    if candidate.is_file() and candidate.resolve().is_relative_to(HERE) and candidate not in paths:
                        paths.add(candidate); queue.append(candidate)
    import torch, transformers
    from transformers.models.wav2vec2 import modeling_wav2vec2, feature_extraction_wav2vec2
    paths.update(Path(module.__file__) for module in (np,torch,transformers,modeling_wav2vec2,feature_extraction_wav2vec2))
    paths.update(HERE/name for name in ('requirements.txt','requirements.lock.txt'))
    paths.add(PROTOCOL)
    paths.update(ROOT/'work/core-model-next-method-20260927'/name for name in ('opus-method-review.json','advice.md','opus-core-source-review.json'))
    return {str(path.resolve()):file_binding(path.resolve()) for path in sorted(paths)}


def join_clips(manifest,position_clips,scalar_clips,posterior_bindings,posterior_metadata,recipe,vocabulary):
    """Pure exact child identity/full-canonical join; no scalar or rating values."""
    require(len(vocabulary)==392 and set(vocabulary.values())==set(range(392)), 'Full pinned CTC vocabulary required')
    require(recipe['poolingContextFrames']==2, 'Fixed historical context radius differs')
    def indexed(clips):
        require(len({c['id'] for c in clips})==len(clips), 'Duplicate clip identity')
        return {c['id']:c for c in clips}
    old=indexed(manifest['clips']); positions=indexed(position_clips); canonical=indexed(scalar_clips)
    require(set(old)<=set(positions) and set(old)<=set(canonical)
            and set(old)<=set(posterior_bindings) and set(old)<=set(posterior_metadata),'Child clip join incomplete')
    joined=[]; seen=set()
    for clip in manifest['clips']:
        full,phones=positions[clip['id']],canonical[clip['id']]
        require(all(clip[k]==full[k]==phones[k] for k in ('id','audioPath','audioSha256','sampleCount'))
                and 6<=phones['age']<=12 and clip['frames']==full['frames']==local.convolution_frames(clip['sampleCount'],recipe),
                'Child waveform/frame identity differs')
        flattened=[phone for word in phones['words'] for phone in word['phones']]
        require(flattened==phones['canonicalPhones'], 'Full prompt word/phone mapping differs')
        mapped,tokens,ambiguities=local.canonical_mapping(flattened,vocabulary,recipe)
        source_rows={r['rowIndex']:r for r in full['rows']}
        require(len(source_rows)==len(full['rows'])==len(clip['rows']),'Position row coverage differs')
        rows=[]
        offsets=np.cumsum([0]+[len(w['phones']) for w in phones['words']]).tolist()
        for row in clip['rows']:
            ri=row['rowIndex']; require(ri in source_rows and ri not in seen,'Missing or duplicate position identity'); seen.add(ri)
            original=source_rows[ri]
            require(all(row[k]==original[k] for k in ('id','clipId','targetId','intervalFrames','estimatedPoolingWindowFrames')),
                    'Historical position/window join differs')
            wi,pi,ci=original['wordIndex'],original['phoneIndex'],original['canonicalIndex']
            require(type(wi) is int and 0<=wi<len(phones['words']) and type(pi) is int and 0<=pi<len(phones['words'][wi]['phones'])
                    and type(ci) is int and ci==offsets[wi]+pi and flattened[ci]==original['targetPhone']
                    and original['id']==f"{clip['id']}:{wi}:{pi}", 'Full canonical occurrence index differs')
            temporal.windows(row,clip['frames'])
            record={k:(row if k in row else original)[k] for k in ROW_FIELDS}
            record['tokenId']=tokens[ci]; rows.append(record)
        metadata=posterior_metadata[clip['id']]
        require(metadata['frames']==clip['frames'] and metadata['vocabularySize']==392
                and metadata['audioSha256']==clip['audioSha256'] and metadata['sampleCount']==clip['sampleCount'],
                'Quantized CTC geometry or waveform differs')
        joined.append(dict(**{k:clip[k] for k in ('id','audioPath','audioSha256','sampleCount','frames')},
            speakerId=phones['speakerId'],words=[dict(text=w['text'],phones=w['phones']) for w in phones['words']],
            canonicalPhones=flattened,mappedTokens=mapped,fullTokens=tokens,mappingAmbiguities=ambiguities,rows=rows,
            posterior=copy.deepcopy(posterior_bindings[clip['id']]),posteriorMetadata=copy.deepcopy(metadata)))
    ordered=sorted((r for c in joined for r in c['rows']),key=lambda r:r['outputIndex'])
    require([r['outputIndex'] for r in ordered]==list(range(len(ordered)))
            and len({r['id'] for r in ordered})==len(ordered)
            and [r['id'] for r in ordered]==manifest['rowIds'] and [r['rowIndex'] for r in ordered]==manifest['rowIndices'],
            'Exact child reference row order differs')
    return joined


def select_preflight(clips,fit_rows):
    require(len(fit_rows)==len(set(fit_rows)) and all(type(i) is int for i in fit_rows),'Ordered fit membership invalid')
    fit=set(fit_rows); eligible=[]; coverage=set()
    for clip in clips:
        indices={r['rowIndex'] for r in clip['rows']}
        if indices&fit:
            require(indices<=fit and all(word_group(w['text'].upper())!=0 for w in clip['words']),
                    'Fit membership lacks whole-utterance word purging')
            eligible.append(clip); coverage.update(indices)
    require(coverage==fit and len(eligible)>=3,'Fit row identity coverage or probe support differs')
    ordered=sorted(eligible,key=lambda c:(c['sampleCount'],c['id']))
    chosen=[ordered[0],ordered[(len(ordered)-1)//2],ordered[-1]]
    longest=max(clips,key=lambda c:(c['sampleCount'],c['id']))
    ids=list(dict.fromkeys([c['id'] for c in chosen]+[longest['id']]))
    return dict(fitClipIds=[c['id'] for c in chosen],globalLongestClipId=longest['id'],
        selectedClipIds=ids,repeatClipIds=list(dict.fromkeys([chosen[0]['id'],longest['id']])),
        fitRows=list(fit_rows),fitClipCount=len(eligible),roles={cid:(['fit-duration-probe'] if cid in {c['id'] for c in chosen} else [])+
        (['global-longest-hardware-only'] if cid==longest['id'] else []) for cid in ids})


def passing_reference(plan,report):
    """The original reference and fresh passing export have distinct paths."""
    require(report['complete'] is True and report['cachedFinalExactAllRows'] is True
        and report['matrices']['final']['sha256']==plan['artifacts']['reference']['sha256'],
        'Passing reference content SHA differs')
    return copy.deepcopy(report['matrices']['final'])


def _metadata():
    pins={k:file_binding(Path(path)) for k,(path,sha) in PINS.items()}
    require(all(pins[k]['sha256']==PINS[k][1] for k in pins),'Frozen metadata lineage differs')
    values={k:read_json(Path(pin['path'])) for k,pin in pins.items()}
    tp,tr,sp,sr= (values[k] for k in ('temporalPlan','temporalReport','scalarPlan','scalarReport'))
    require(tr['complete'] is True and tr['cachedFinalExactAllRows'] is True and tr['plan']==pins['temporalPlan']
        and tp['support']=={'positions':9891,'clips':1040,'children':52} and tr['scalars']==tp['artifacts']['scalars']
        and tr['rowIndices']==tp['artifacts']['rowIndices'],
        'Passing9891 temporal parity lineage required')
    require(sr['complete'] is True and sr['positions']==28227 and sr['clips']==2500 and sr['authorPartition']=='train'
        and sr['plan']==pins['scalarPlan'] and values['positionReport']['plan']==pins['positionPlan']
        and values['positionReport']['positions']==28227 and values['positionReport']['complete'] is True,
        'Complete28227 position/scalar lineage required')
    historical=values['historicalPlan']; temporal_study=values['temporalStudy']; hi=temporal_study['inputs']
    require(hi['historicalPlan']==pins['historicalPlan'] and hi['featureReport']==pins['temporalReport']
        and hi['historicalFeatureReport']==pins['positionReport'],'Actual matched historical control lineage differs')
    jobs={j['id']:j for j in historical['jobs']}; job=jobs[RECIPE['fitJob']]
    scalar_id=job['id'].replace('pca16-scalars','scalars'); scalar=jobs[scalar_id]
    candidate=next(j for j in temporal_study['jobs'] if j['seed']==17 and j['speakerFold']==j['wordGroup']==0)
    require(candidate['references']=={'final':job['id'],'scalar':scalar_id}
        and all(job[k]==scalar[k]==candidate[k] for k in ('fitRows','selectionRows','addedValidationRows','refitRows')),
        'Ordered current seed17/s0w0 fit/control memberships differ')
    pins.update({k:tp['artifacts'][k] for k in ('manifest','reference','scalars','rowIndices')})
    pins.update(parentTarget=hi['historicalTarget'],parentScalars=hi['historicalScalars'],passingFinal=passing_reference(tp,tr))
    pins.update({k:sp['inputs'][k] for k in ('mapping','vocabulary','oldIndex','oldConfig','oldManifest')})
    manifest,recipe,vocabulary,index,config=(read_json(Path(pins[k]['path'])) for k in ('manifest','mapping','vocabulary','oldIndex','oldConfig'))
    guard({k:pins[k] for k in ('manifest','mapping','vocabulary','oldIndex','oldConfig','oldManifest')})
    require(pins['vocabulary']['sha256']==local.VOCAB_SHA and index['complete'] is True and len(index['entries'])==2495
        and index['configSha256']==pins['oldConfig']['sha256'] and config['manifestSha256']==pins['oldManifest']['sha256']
        and config['frameStrideSamples']==320 and config['frameReceptiveFieldSamples']==400
        and config['authorPartition']=='train' and config['dtype']=='float32-little-endian-log-softmax'
        and sp['ctcCheckpoint']['revision']=='c69750f5043e5e1f8a71ab95dd3b98338c280c92'
        and sp['ctcCheckpoint']['upstreamRevision']=='ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4',
        'Quantized CTC index/model/mapping lineage differs')
    metadata={}
    cache=Path(pins['oldIndex']['path']).parent
    for cid,entry in index['entries'].items():
        require(entry['clipId']==cid and entry['configSha256']==pins['oldConfig']['sha256'], 'Old CTC entry identity differs')
        path=(cache/entry['path']).resolve(); require(path.is_relative_to(cache), 'Unsafe CTC payload path')
        require(sr['posteriorBindings'][cid]=={'path':str(path),'sha256':entry['sha256']},'Old posterior binding differs')
        metadata[cid]={k:entry[k] for k in ('frames','vocabularySize','audioSha256','sampleCount')}
    missing=set(sr['posteriorBindings'])-set(index['entries'])
    require(missing==set(sp['newCtcIds'])==set(sr['newCtcJobs']) and len(missing)==5,'Five new CTC jobs required')
    for cid,record in sr['newCtcJobs'].items():
        guard(record); result=read_json(Path(record['result']['path'])); new_job=read_json(Path(record['job']['path']))
        source_clip=next(c for c in sp['clips'] if c['id']==cid)
        require(new_job['audioPath']==source_clip['audioPath']
            and new_job['audioSha256']==source_clip['audioSha256']==result['audioSha256']
            and new_job['sampleCount']==source_clip['sampleCount']==result['sampleCount']
            and new_job['expectedFrames']==result['frames']==local.convolution_frames(source_clip['sampleCount'],recipe)
            and new_job['ctcCheckpoint']==sp['ctcCheckpoint'] and new_job['sessionOptions']==sp['ctcSessionOptions'],
            'New CTC job/result waveform or geometry differs')
        require('clipId' not in result or result['clipId']==cid,'New CTC clip identity differs')
        require(result['complete'] is True and result['jobSha256']==record['job']['sha256']
            and result['checkpoint']==sp['ctcCheckpoint'] and result['fetchAttempts']==0 and result['posteriorsPath']=='ctc.f32'
            and result['sessionOptions']==sp['ctcSessionOptions'] and result['node']==config['node'], 'New CTC result lineage differs')
        require(sr['posteriorBindings'][cid]=={'path':str(Path(record['result']['path']).parent/'ctc.f32'),
            'sha256':result['posteriorsSha256']},'New posterior binding differs')
        metadata[cid]=dict(frames=result['frames'],vocabularySize=392,audioSha256=result['audioSha256'],sampleCount=result['sampleCount'])
        pins.update({'newCTC/'+cid+'/'+k:v for k,v in record.items()})
    require(len(sr['posteriorBindings'])==2500 and set(sr['posteriorBindings'])=={c['id'] for c in sp['clips']},'Posterior2500 coverage differs')
    clips=join_clips(manifest,values['positionPlan']['clips'],sp['clips'],sr['posteriorBindings'],metadata,recipe,vocabulary)
    require(len(clips)==1040 and len({c['speakerId'] for c in clips})==52
        and len({r['targetId'] for c in clips for r in c['rows']})==23,'Complete child/all23 support differs')
    probes=select_preflight(clips,job['fitRows'])
    selected=[c for cid in probes['selectedClipIds'] for c in clips if c['id']==cid]
    pins.update({k:v for k,v in hi.items() if k.startswith('control/') and k.split('/')[2] in (job['id'],scalar_id)})
    return pins,selected,probes,tp['model'],tr['environment'],values['positionPlan']['recipe']


def declaration():
    pins,clips,probes,model,passing,encoder_recipe=_metadata()
    require(encoder_recipe['modelId']=='facebook/wav2vec2-lv-60-espeak-cv-ft'
        and encoder_recipe['revision']=='ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'
        and {k:v['sha256'] for k,v in model.items()}==encoder_recipe['artifactSha256'], 'Full precision encoder identity differs')
    return dict(study=RECIPE['version'],recipe=copy.deepcopy(RECIPE),inputs=pins,clips=clips,probes=probes,
        model=model,encoderRecipe=encoder_recipe,runtime=passing,sources=sources(),**FLAGS)


def declare(out):
    out=Path(out).resolve(); require(out.is_relative_to(HERE/'outputs') and not out.exists(),'Fresh preflight declaration required')
    plan=declaration(); out.mkdir(parents=True,mode=0o700)
    return write_new(out/'plan.json',plan)


def checked_plan(path,sha):
    path=Path(path).resolve(); require(path.is_relative_to(HERE/'outputs') and path.name=='plan.json','Canonical preflight plan required')
    require(digest(path)==sha,'Preflight plan SHA differs'); plan=read_json(path)
    require(plan==declaration(),'Preflight source, metadata, recipe or membership changed')
    return plan


def environment(expected):
    observed=base.environment()
    require(observed==expected and expected['platform']=='macOS-27.0-arm64-arm-64bit-Mach-O'
        and expected['python']=='3.13.14','Passing Mac arm64 CPU runtime/platform required; no route substitution')
    return observed


def pool_clip(hidden,logp,clip):
    posterior=core.CTCPosterior(logp,clip['fullTokens'],blank=0)
    return _pool_clip(hidden,logp,clip,posterior)


def _pool_clip(hidden,logp,clip,posterior):
    require(hidden.dtype==np.float32 and hidden.shape==(clip['frames'],1024) and np.isfinite(hidden).all()
        and logp.dtype==np.float32 and logp.shape==(clip['frames'],392),'Hidden/quantized CTC geometry differs')
    for row in clip['rows']:
        temporal.windows(row,clip['frames'])
        ci=row['canonicalIndex']
        require(type(ci) is int and 0<=ci<len(clip['fullTokens']) and row['tokenId']==clip['fullTokens'][ci],
                'Full canonical token index differs')
    hard=pooled_vectors(hidden,clip['rows'],clip['frames'])[0]
    candidate=[]; audit=[]
    for row,control in zip(clip['rows'],hard,strict=True):
        weights=posterior.token_weights(row['canonicalIndex']); vector=core.pool_hidden(hidden,weights['u'])
        candidate.append(vector)
        metadata=weights['metadata']; interval=row['intervalFrames']
        audit.append(dict(id=row['id'],**metadata,displacementFromIntervalCenter=metadata['qCentroidFrame']-(interval[0]+interval[1]-1)/2,
            qMassOutsideViterbiInterval=float(weights['q'].sum()-weights['q'][interval[0]:interval[1]].sum()),
            vectorDistance=core.vector_distance(vector,control)))
    return dict(candidate=np.stack(candidate),hard=hard),dict(ctc=posterior.audit,rows=audit)


def load_encoder(plan):
    from contextlib import contextmanager
    @contextmanager
    def loader():
        guard(plan['model'])
        with tempfile.TemporaryDirectory(prefix='posterior-phonetic-') as folder:
            for name,pin in plan['model'].items(): (Path(folder)/name).symlink_to(pin['path'])
            encoder=PhoneticEncoder(Path(folder),plan['encoderRecipe'])
            require(len(encoder.model.wav2vec2.encoder.layers)==24 and not encoder.model.training
                and all(not p.requires_grad and str(p.dtype)=='torch.float32' and p.device.type=='cpu' for p in encoder.model.parameters()),
                'Original frozen full-precision24-layer CPU encoder required')
            yield encoder
    return loader()


def guard_clip(clip):
    require(digest(Path(clip['audioPath']))==clip['audioSha256'] and digest(Path(clip['posterior']['path']))==clip['posterior']['sha256'],
        'Selected audio/posterior hash differs')
    require(Path(clip['posterior']['path']).stat().st_size==clip['frames']*392*4,'Full-vocabulary posterior byte size differs')


def extract_clip(encoder,clip):
    guard_clip(clip)
    logp=np.fromfile(clip['posterior']['path'],dtype='<f4').reshape(clip['frames'],392)
    posterior=core.CTCPosterior(logp,clip['fullTokens'],blank=0)
    samples=read_rating_pcm(Path(clip['audioPath']),clip['audioSha256'])
    require(samples.numel()==clip['sampleCount'],'Original audio sample count differs')
    # Alignment probabilities are never regenerated from this acoustic encoder.
    hidden=encoder(samples)
    values,audit=_pool_clip(hidden,logp,clip,posterior)
    guard_clip(clip)
    return values,audit


def checked_references(plan):
    pins=plan['inputs']; guard({k:pins[k] for k in ('reference','passingFinal','scalars','rowIndices','parentTarget','parentScalars')})
    reference=base.array(pins['reference']['path'],(9891,1024),np.float32)
    passing=base.array(pins['passingFinal']['path'],(9891,1024),np.float32)
    temporal.exact_parity(reference,passing)
    scalars=base.array(pins['scalars']['path'],(9891,13),np.float32)
    indices=base.array(pins['rowIndices']['path'],(9891,),np.int64)
    parent=np.load(pins['parentTarget']['path'],mmap_mode='r',allow_pickle=False)
    parent_scalars=np.load(pins['parentScalars']['path'],mmap_mode='r',allow_pickle=False)
    require(parent.shape==(28227,1024) and parent_scalars.shape==(28227,13) and parent.dtype==parent_scalars.dtype==np.float32
        and np.all((indices>=0)&(indices<28227)) and np.array_equal(reference,parent[indices]) and np.array_equal(scalars,parent_scalars[indices]),'Exact28227-to9891 reference/scalar lineage differs')
    manifest=read_json(Path(pins['manifest']['path']))
    require(indices.tolist()==manifest['rowIndices'] and np.all(indices[1:]>indices[:-1]),'Exact child reference row order differs')
    return reference


def run(path,sha,review,out):
    # Review comes before payload guards, arrays, audio and any model loading.
    require(digest(Path(path))==sha,'Plan SHA differs'); base.checked_review(Path(review),sha)
    reviewed=file_binding(Path(review)); plan=checked_plan(path,sha); env=environment(plan['runtime'])
    out=Path(out).resolve(); require(out.is_relative_to(HERE/'outputs') and not out.exists(),'Preserve partial preflight; no implicit restart')
    out.mkdir(parents=True,mode=0o700); write_new(out/'started.json',dict(plan=file_binding(Path(path)),review=reviewed,environment=env))
    started=time.monotonic(); records=[]; cached={}
    try:
        reference=checked_references(plan)
        by_id={c['id']:c for c in plan['clips']}; repeat_ids=plan['probes']['repeatClipIds']
        ordered=repeat_ids+[cid for cid in plan['probes']['selectedClipIds'] if cid not in repeat_ids]
        with load_encoder(plan) as encoder:
            for cid in ordered:
                require(file_binding(Path(review))==reviewed,'Review changed during preflight')
                clip=by_id[cid]; before=time.monotonic(); values,audit=extract_clip(encoder,clip)
                temporal.exact_parity(values['hard'],reference[[r['outputIndex'] for r in clip['rows']]])
                unit=out/(cid+'.npz')
                with unit.open('xb') as stream: np.savez(stream,allow_pickle=False,**values)
                record=dict(clipId=cid,artifact=file_binding(unit),audit=audit,seconds=time.monotonic()-before,roles=plan['probes']['roles'][cid])
                write_new(out/(cid+'.json'),record); records.append(record)
                if cid in repeat_ids: cached[cid]=values
            for cid in repeat_ids:
                require(file_binding(Path(review))==reviewed,'Review changed during preflight')
                clip=by_id[cid]; values,_=extract_clip(encoder,clip)
                require(all(np.array_equal(values[k],cached[cid][k]) for k in ('candidate','hard')),'Start/end exact repeat differs')
                with (out/(cid+'-repeat.npz')).open('xb') as stream: np.savez(stream,allow_pickle=False,**values)
        guard(plan['model'])
        for clip in plan['clips']: guard_clip(clip)
        checked_references(plan)
        checked_plan(path,sha); require(file_binding(Path(review))==reviewed,'Review changed during preflight')
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return write_new(out/'report.json',dict(complete=True,plan=file_binding(Path(path)),review=reviewed,environment=env,
            records=records,repeats={cid:file_binding(out/(cid+'-repeat.npz')) for cid in repeat_ids},
            peakMemory=dict(value=peak,units='bytes',method='process lifetime resource.getrusage(RUSAGE_SELF).ru_maxrss on Darwin'),
            elapsedSeconds=time.monotonic()-started,cachedHardExact=True,repeatsExact=True,encoderInferencePerformed=True,**FLAGS))
    except BaseException as error:
        write_new(out/'failure.json',dict(planSha256=sha,errorType=type(error).__name__,completedClips=len(records),
            elapsedSeconds=time.monotonic()-started,partialOutputsPreserved=True,**FLAGS)); raise


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=('declare','run'))
    parser.add_argument('--out',required=True,type=Path); parser.add_argument('--plan',type=Path)
    parser.add_argument('--sha256'); parser.add_argument('--review',type=Path); args=parser.parse_args()
    print(declare(args.out) if args.command=='declare' else run(args.plan,args.sha256,args.review,args.out))


if __name__=='__main__': main()
