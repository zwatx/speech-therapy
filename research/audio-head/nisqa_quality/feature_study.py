"""Separately declared CPU feature pass; no quality-target access or downloads."""
import argparse
import copy
import json
from pathlib import Path
import platform
import sys

import numpy as np
import requests
import scipy

from nisqa_ingest.discovery import binding, read, write, require, guard, checked_review, fresh
from nisqa_ingest import selected_recovery
from nisqa_quality import ingestion, extraction, audio_features

HERE = ingestion.HERE
SOURCE_PATHS = tuple(Path(__file__).parent / name for name in (
    'feature_study.py','test_feature_study.py','extraction.py','test_extraction.py',
    'audio_features.py','test_audio_features.py')) + (HERE/'encoders.py', HERE/'nisqa_ingest/waveform_audit.py')
POLICY = dict(version='nisqa-quality-cpu-features-v1', device='cpu', selectedCount=200,
              offlineOnly=True, oneClipPerForward=True, replacement=False,
              qualityTargetsInterpreted=False, modelInferencePerformed=False,
              arrays={'ssl':{'shape':[200,1536],'dtype':'<f4'},'scalars':{'shape':[200,6],'dtype':'<f8'}})


def cache_bindings():
    """Verify the three offline cache assets without loading weights into a model."""
    from huggingface_hub import hf_hub_download
    cache=(HERE/'outputs/model-cache').resolve(); result={}
    for name,sha in extraction.POLICY['artifactSha256'].items():
        path=Path(hf_hub_download(extraction.POLICY['modelId'],name,
            revision=extraction.POLICY['revision'],cache_dir=str(cache),local_files_only=True)).absolute()
        require(path.name==name and path.parent.name==extraction.POLICY['revision']
            and path.parent.parent.name=='snapshots' and path.parent.resolve().is_relative_to(cache)
            and path.resolve().is_relative_to(cache) and path.is_file()
            and path.stat().st_size==extraction.POLICY['artifactBytes'][name]
            and extraction._sha_file(path)==sha,'Pinned offline encoder cache differs')
        result[name]=dict(path=str(path),sha256=sha,sizeBytes=path.stat().st_size)
    require(len({Path(pin['path']).parent.resolve() for pin in result.values()})==1,'Encoder cache snapshot differs')
    return result


def _inputs(path,sha):
    """Read completed identity/audit artifacts; never open a ratings CSV."""
    path=Path(path).resolve()
    require(path.name=='plan.json' and path.is_relative_to(HERE/'outputs'),'Canonical ingestion plan required')
    pin=binding(path,sha); plan=read(pin)
    require(plan['study']=='nisqa-quality-ingestion-v1','Quality ingestion plan required')
    require(set(plan['sources'])==set(ingestion.SOURCE_NAMES),'Ingestion source scope differs')
    for name,source in plan['sources'].items():
        require(source==binding(Path(ingestion.__file__).parent/name),'Ingestion source differs')
    guard(plan['requirements']); binding(plan['protocol']['path'],plan['protocol']['sha256'])
    require(plan['runtime']==dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,
        scipy=scipy.__version__,requests=requests.__version__),'Ingestion runtime differs')
    root=path.parent
    selection_pin=binding(root/'selection-freeze.json')
    selection_pin,selected,requests_value=ingestion.checked_selection(plan,pin,root,selection_pin['sha256'])
    audio_pin=binding(root/'audio-freeze.json'); acquired=read(audio_pin)
    waveforms_pin=binding(root/'waveforms-freeze.json'); audited=read(waveforms_pin)
    require(acquired['complete'] is True and acquired['plan']==pin and acquired['selectionFreeze']==selection_pin
        and acquired['selectedCount']==200 and audited['complete'] is True and audited['plan']==pin
        and audited['selectionFreeze']==selection_pin and audited['audioFreeze']==audio_pin
        and audited['selectedCount']==audited['decodedCount']==200 and audited['allSelectedDecoded'] is True,
        'All 200 acquisitions and waveform audits must be complete')
    require(checked_review(acquired['review']['path'],sha)==acquired['review']
        and checked_review(audited['review']['path'],sha)==audited['review'],'Pinned ingestion review differs')
    records=read(acquired['records']); audits=read(audited['audits'])
    require(len(records)==len(audits)==200,'Exactly 200 acquisition and audit records required')
    originals=[]
    for index,(record,audit,request) in enumerate(zip(records,audits,requests_value)):
        require(all(record[key]==audit[key]==request[key] for key in ('path','identitySha256','componentID','partition'))
            and audit['success'] is True,'Original waveform identity/audit join differs')
        selected_recovery.checked_record(record,request,plan['archive'],acquired['transport']['validator'])
        require(Path(record['acquired']['path']).resolve()==
            (Path(plan['discoveryRoot'])/'transport'/f'quality-audio-{index:03d}.wav').resolve(),
            'Original acquisition path or order differs')
        original=binding(record['acquired']['path'],record['acquired']['sha256'])
        require(audit['audit']['input']['sha256']==original['sha256']
            and audit['audit']['input']['sizeBytes']==record['acquired']['size'],'Original waveform audit hash differs')
        originals.append(original)
    return dict(ingestionPlan=pin,selectionFreeze=selection_pin,audioFreeze=audio_pin,
        waveformsFreeze=waveforms_pin,selected=selected['selected'],originals=originals,
        acquisitionRecords=acquired['records'],waveformAudits=audited['audits'])


def declaration(ingestion_plan,ingestion_sha,device='cpu'):
    require(device=='cpu','First local feature declaration requires CPU')
    inputs=_inputs(ingestion_plan,ingestion_sha)
    return dict(study='nisqa-quality-feature-stage-v1',inputs=inputs,
        protocol=binding(ingestion.PROTOCOL),sources={str(path.relative_to(HERE)):binding(path) for path in SOURCE_PATHS},
        requirements={name:binding(HERE/name) for name in ('requirements.txt','requirements.lock.txt','requirements.quality.txt')},
        cache=cache_bindings(),cacheDirectory=str((HERE/'outputs/model-cache').resolve()),
        runtime=extraction.configure_runtime(device),device=device,
        policies=dict(stage=copy.deepcopy(POLICY),extraction=copy.deepcopy(extraction.POLICY),audio=copy.deepcopy(audio_features.POLICY)),
        modelInferencePerformed=False,qualityTargetsInterpreted=False,clinicalUseEligible=False,learnerJudgmentsEnabled=False)


def declare(output,ingestion_plan,ingestion_sha,device='cpu'):
    output=Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(),'Fresh research feature output required')
    value=declaration(ingestion_plan,ingestion_sha,device)
    output.mkdir(parents=True,mode=0o700); write(output/'plan.json',value)
    return binding(output/'plan.json')


def load(path,sha):
    path=Path(path).resolve()
    require(path.name=='plan.json' and path.is_relative_to(HERE/'outputs'),'Canonical feature plan required')
    pin=binding(path,sha); plan=read(pin); inherited=plan['inputs']['ingestionPlan']
    require(plan==declaration(inherited['path'],inherited['sha256'],plan['device']),
            'Feature inputs, source, cache, policy or runtime changed')
    return plan,pin


def _save_array(path,array):
    with Path(path).open('xb') as stream:
        Path(path).chmod(0o600); np.save(stream,array,allow_pickle=False)
    return binding(path)


def run(path,sha,review):
    plan,pin=load(path,sha); reviewed=checked_review(review,sha); root=Path(pin['path']).parent
    fresh(root,'features'); write(root/'features-started.json',dict(plan=pin,review=reviewed))
    records=[]
    try:
        model,processor,encoder=extraction.load_frozen_wavlm(plan['cacheDirectory'],device=plan['device'])
        encoder_policy=plan['policies']['extraction']
        require(encoder['policy']==encoder_policy and encoder['runtime']==plan['runtime']
            and all(encoder[key]==encoder_policy[key] for key in ('modelId','revision','artifactSha256','artifactBytes'))
            and encoder['parameterDtypes']==['torch.float32']
            and encoder['licenseEvidence']==extraction.WAVLM_LICENSE,
                'Loaded encoder policy or runtime differs')
        # Rebind the complete declaration after loading, before the first forward.
        load(path,sha)
        rows=root/'features'
        ssl,scalars=[],[]
        for index,(identity,original) in enumerate(zip(plan['inputs']['selected'],plan['inputs']['originals'])):
            binding(reviewed['path'],reviewed['sha256'])
            binding(original['path'],original['sha256'])
            result=extraction.extract_clip(original['path'],model,processor,encoder,device=plan['device'])
            binding(original['path'],original['sha256'])
            features,raw=result['features'],result['scalars']; metadata=result['metadata']
            require(features.shape==(1536,) and features.dtype==np.dtype('<f4') and np.isfinite(features).all()
                and raw.shape==(6,) and raw.dtype==np.dtype('<f8') and np.isfinite(raw).all(), 'Feature output shape/dtype differs')
            feature_sha=audio_features._sha(features,'<f4'); raw_sha=audio_features._sha(raw,'<f8')
            require(metadata['waveform']['originalAudit']['input']['sha256']==original['sha256']
                and metadata['featuresFloat32Sha256']==feature_sha and metadata['rawScalarsFloat64Sha256']==raw_sha
                and metadata['validFrames']==metadata['expectedFrames']>0 and metadata['model']==encoder
                and metadata['targetsAccessed'] is False,'Feature metadata identity or hash differs')
            feature_pin=_save_array(rows/f'ssl-{index:03d}.npy',features)
            scalar_pin=_save_array(rows/f'scalars-{index:03d}.npy',raw)
            write(rows/f'metadata-{index:03d}.json',metadata)
            record=dict(path=identity['path'],identitySha256=identity['identitySha256'],componentID=identity['componentID'],
                partition=identity['partition'],featureFloat32Sha256=feature_sha,rawScalarsFloat64Sha256=raw_sha,
                validFrames=metadata['validFrames'],metadata=metadata,metadataFile=binding(rows/f'metadata-{index:03d}.json'),
                featureFile=feature_pin,scalarsFile=scalar_pin,original=original)
            write(rows/f'record-{index:03d}.json',record); records.append(record)
            ssl.append(features); scalars.append(raw)
        with (root/'features.npz').open('xb') as stream:
            (root/'features.npz').chmod(0o600)
            np.savez(stream,ssl=np.stack(ssl),scalars=np.stack(scalars),allow_pickle=False)
        with np.load(root/'features.npz',allow_pickle=False) as arrays:
            require(set(arrays.files)=={'ssl','scalars'} and arrays['ssl'].shape==(200,1536)
                and arrays['ssl'].dtype==np.dtype('<f4') and arrays['scalars'].shape==(200,6)
                and arrays['scalars'].dtype==np.dtype('<f8'),'Saved feature matrix differs')
            for index,record in enumerate(records):
                require(audio_features._sha(arrays['ssl'][index],'<f4')==record['featureFloat32Sha256']
                    and audio_features._sha(arrays['scalars'][index],'<f8')==record['rawScalarsFloat64Sha256'],
                    'Saved feature matrix row hash differs')
                guard({name:record[name] for name in ('featureFile','scalarsFile','metadataFile')})
        write(root/'records.json',records); load(path,sha)
        binding(reviewed['path'],reviewed['sha256'])
        write(root/'feature-freeze.json',dict(complete=True,plan=pin,review=reviewed,
            **{name:plan['inputs'][name] for name in ('ingestionPlan','selectionFreeze','audioFreeze','waveformsFreeze')},
            features=binding(root/'features.npz'),records=binding(root/'records.json'),encoder=encoder,
            modelInferencePerformed=True,qualityTargetsInterpreted=False,clinicalUseEligible=False,learnerJudgmentsEnabled=False))
        return binding(root/'feature-freeze.json')
    except Exception as error:
        write(root/'features-failure.json',dict(plan=pin,review=reviewed,errorType=type(error).__name__,
            completedCount=len(records),partialOutputsPreserved=True,qualityTargetsInterpreted=False))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=('declare','run'))
    for name in ('output','ingestion-plan','plan','review'): parser.add_argument('--'+name,type=Path)
    for name in ('ingestion-sha','plan-sha'): parser.add_argument('--'+name)
    args=parser.parse_args()
    result=declare(args.output,args.ingestion_plan,args.ingestion_sha) if args.command=='declare' else run(args.plan,args.plan_sha,args.review)
    print(json.dumps(result))


if __name__=='__main__': main()
