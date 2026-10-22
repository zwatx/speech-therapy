"""Reviewed, fresh-only 200-record ingestion; confirmation ratings stay closed."""
import argparse
import json
from pathlib import Path
import platform
import sys

import numpy as np
import requests
import scipy

from nisqa_ingest import selected_pilot, selected_recovery, source_code_selection
from nisqa_ingest.discovery import (binding,read,write,require,guard,checked_review,fresh,
                                    check_ledger,transport_snapshot)
from nisqa_quality import selection as selector, targets as target_parser

HERE,ROOT=selected_pilot.HERE,selected_pilot.ROOT
BASE=selected_pilot.BASE
PROTOCOL=ROOT/'docs/model/nisqa-quality-study-v1.md'
METHOD=ROOT/'work/nisqa-quality-20260927/method-review.md'
RECOVERY=BASE/'selected-audio-recovery-v2'
RECOVERY_SHA='04ea83e99092977bebb10a06f537894297689d543131966d75692d0850617d12'
ACQUISITION_SHA='49e92061bf5fc73c850ce9e0c75d00ac2045e880ebbc03fa24ed3b5f206b9154'
AUDIT_SHA='0118667216a61db46d8c94a333451ff7c23d00844e784e03f3a01fb5854e1b7d'
FLAGS=dict(selector.FLAGS,qualityTargetsInterpreted=False,fullArchiveMd5Verified=False,
           nonspeechTruthAvailable=False,readSpeechOnly=True,gpuUsed=False)
SOURCE_NAMES=('__init__.py','selection.py','test_selection.py','audio_features.py','test_audio_features.py',
              'transport.py','test_transport.py','targets.py','test_targets.py','ingestion.py','test_ingestion.py')


def declaration():
    from nisqa_quality.audio_features import POLICY as FEATURE_POLICY
    from nisqa_quality.transport import POLICY as TRANSPORT_POLICY
    from nisqa_ingest.waveform_audit import POLICY as AUDITOR_POLICY
    old,old_pin=selected_pilot.load(selected_recovery.OLD/'plan.json',selected_recovery.OLD_SHA)
    recovery,recovery_pin=selected_recovery.load(RECOVERY/'plan.json',RECOVERY_SHA)
    acquisition_pin=binding(RECOVERY/'acquisition-freeze.json',ACQUISITION_SHA)
    audit_pin=binding(RECOVERY/'audit-freeze.json',AUDIT_SHA)
    acquired,audited=read(acquisition_pin),read(audit_pin)
    require(acquired['complete'] is True and audited['complete'] is True
            and acquired['plan']==audited['plan']==recovery_pin
            and audited['acquisitionFreeze']==acquisition_pin and audited['allSelectedDecoded'] is True
            and audited['decodedCount']==20 and audited['completeTargets'] is True,
            'Completed corrected pilot recovery required')
    checked_review(acquired['review']['path'],RECOVERY_SHA)
    binding(acquired['records']['path'],acquired['records']['sha256'])
    binding(audited['audits']['path'],audited['audits']['sha256'])
    previous=acquired['transport']; state=read(previous['state'])
    binding(previous['journal']['path'],previous['journal']['sha256'])
    require(state['bytesRead']==previous['bytesRead']==27254714
            and state['metadataRead']==previous['metadataRead']==15438176
            and state['settings']==previous['settings'] and state['validator']==previous['validator']
            and all(state[key]==0 for key in ('reserved','reservedMetadata','uncertainBytes','uncertainMetadata')),
            'Completed pilot transport anchor differs')
    lineage=source_code_selection.declaration()
    eligible=source_code_selection.prepare_inventory(read(lineage['inputs']['lineageInventory']),expected_count=1020)['eligible']
    require(all(row['readerGroup']=='DNS-reader_'+row['readerNumberCode'] for row in eligible),
            'This declaration supports only the frozen atomic nominal source groups')
    inputs=dict(lineage['inputs'],oldPlan=old_pin,recoveryPlan=recovery_pin,
        recoveryAcquisition=acquisition_pin,recoveryAudit=audit_pin,
        pilotSelected=old['inputs']['selected'],directoryFreeze=old['inputs']['directoryFreeze'],
        metadataFreeze=old['inputs']['metadataFreeze'],members=old['inputs']['members'],
        combinedCSV=old['inputs']['combinedCSV'])
    guard(inputs)
    return dict(study='nisqa-quality-ingestion-v1',protocol=binding(PROTOCOL),methodReview=binding(METHOD),
        inputs=inputs,documents=old['documents'],
        sources={name:binding(Path(__file__).parent/name) for name in SOURCE_NAMES},
        requirements={name:binding(HERE/name) for name in
                      ('requirements.txt','requirements.lock.txt','requirements.quality.txt')},
        runtime=dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,
                     scipy=scipy.__version__,requests=requests.__version__),
        policies=dict(selection=selector.POLICY,targets=target_parser.POLICY,
                      features=FEATURE_POLICY,transport=TRANSPORT_POLICY,auditor=AUDITOR_POLICY,
                      supportedNominalGroupForm='atomic DNS-reader_<readerNumberCode>; no verified person identity'),
        archive=old['archive'],discoveryRoot=old['discoveryRoot'],previousTransport=previous,
        phases=['selection','audio','waveforms','fit-selection-targets'],
        confirmationAccess='closed; requires future separately reviewed frozen model and predictions',**FLAGS)


def declare(output):
    output=Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(),'Fresh research output required')
    plan=declaration(); check_ledger(Path(plan['discoveryRoot']),plan['previousTransport'])
    output.mkdir(parents=True,mode=0o700); write(output/'plan.json',plan)
    return binding(output/'plan.json')


def load(path,sha):
    require(Path(path).resolve().is_relative_to(HERE/'outputs') and Path(path).name=='plan.json',
            'Canonical quality ingestion plan required')
    pin=binding(path,sha); plan=read(pin)
    require(plan==declaration(),'Quality source, input, protocol or runtime changed')
    return plan,pin


def _start(path,sha,review,phase):
    plan,pin=load(path,sha); reviewed=checked_review(review,sha); root=Path(pin['path']).parent
    fresh(root,phase); write(root/(phase+'-started.json'),dict(plan=pin,review=reviewed))
    return plan,pin,reviewed,root


def _choices(plan):
    lineage=read(plan['inputs']['lineageInventory'])
    eligible=source_code_selection.prepare_inventory(lineage,expected_count=1020)['eligible']
    pilot=read(plan['inputs']['pilotSelected'])['selected']
    graph=selector.build_components(eligible,pilot)
    return graph,selector.select_study(graph)


def requests_for(selected,members,previous):
    target_parser.validate_selected(selected)
    require(len({r['filename'] for r in members})==len(members),'Duplicate frozen directory member')
    by_name={r['filename']:r for r in members}; requests_value=[]
    for row in selected:
        member=by_name.get(row['archiveMember'])
        require(member is not None and not member['directory'] and member['flags']==0
                and member['compress_type'] in (0,8) and 0<member['compress_size']<=1024**2
                and 0<member['file_size']<=128*1024**2,'Selected member missing or unsupported')
        requests_value.append(dict(path=row['path'],identitySha256=row['identitySha256'],
            partition=row['partition'],componentID=row['componentID'],member=row['archiveMember'],directoryEntry=member))
    compressed=sum(r['directoryEntry']['compress_size'] for r in requests_value)
    plaintext=sum(r['directoryEntry']['file_size'] for r in requests_value)
    headers=sum(30+len(r['member'].encode('utf-8'))+4096 for r in requests_value)
    budget=dict(compressedBytes=compressed,plaintextBytes=plaintext,maxHeaderMetadataBytes=headers,
        projectedBodyBytes=previous['bytesRead']+compressed+headers,
        projectedMetadataBytes=previous['metadataRead']+headers,localExtraLimit=4096)
    require(budget['projectedBodyBytes']<=previous['settings']['maxBytes']
            and budget['projectedMetadataBytes']<=previous['settings']['metadataBytes'],
            'Exact selected transfer exceeds inherited budgets')
    return requests_value,budget


def selection(path,sha,review):
    plan,pin,reviewed,root=_start(path,sha,review,'selection')
    try:
        graph,value=_choices(plan)
        requests_value,budget=requests_for(value['selected'],read(plan['inputs']['members']),plan['previousTransport'])
        write(root/'selection/graph.json',graph); write(root/'selection/selected.json',value)
        write(root/'selection/requests.json',requests_value); write(root/'selection/budget.json',budget)
        load(path,sha)
        write(root/'selection-freeze.json',dict(complete=True,plan=pin,review=reviewed,
            graph=binding(root/'selection/graph.json'),selected=binding(root/'selection/selected.json'),
            requests=binding(root/'selection/requests.json'),budget=binding(root/'selection/budget.json'),
            selectedCount=200,confirmationTargetsAccessed=False,**FLAGS))
        return binding(root/'selection-freeze.json')
    except Exception as error:
        write(root/'selection-failure.json',dict(plan=pin,errorType=type(error).__name__,samplePreserved=True)); raise


def checked_selection(plan,pin,root,sha):
    freeze_pin=binding(root/'selection-freeze.json',sha); frozen=read(freeze_pin)
    require(frozen['complete'] is True and frozen['plan']==pin,'Matching selection freeze required')
    checked_review(frozen['review']['path'],pin['sha256'])
    graph,value=_choices(plan)
    require(read(frozen['graph'])==graph and read(frozen['selected'])==value,'Frozen selection replay differs')
    requests_value,budget=requests_for(value['selected'],read(plan['inputs']['members']),plan['previousTransport'])
    require(read(frozen['requests'])==requests_value and read(frozen['budget'])==budget,'Frozen requests or budget differs')
    return freeze_pin,value,requests_value


def transport(plan,plan_sha,selected):
    from nisqa_quality.transport import QualityDirectoryZip
    settings=plan['previousTransport']['settings']
    return QualityDirectoryZip(plan['archive']['url'],expected_size=plan['archive']['size'],
        output_directory=Path(plan['discoveryRoot'])/'transport',frozen_members=read(plan['inputs']['members']),
        selected_names=[r['archiveMember'] for r in selected],study_sha256=plan_sha,
        max_bytes=settings['maxBytes'],metadata_bytes=settings['metadataBytes'],allowed_hosts=('zenodo.org',))


def checked_extension(plan):
    prior=plan['previousTransport']; folder=Path(plan['discoveryRoot'])/'transport'
    binding(prior['state']['path'],prior['state']['sha256'])
    binding(prior['journal']['path'],prior['journal']['sha256'])
    require((folder/'request-journal.jsonl').read_bytes().startswith(Path(prior['journal']['path']).read_bytes()),
            'Inherited journal prefix differs')
    state=json.loads((folder/'transport-state.json').read_text())
    require(state['settings']==prior['settings'] and state['validator']==prior['validator']
            and state.get('frozenDirectoryBinding')==prior.get('frozenDirectoryBinding'),
            'Inherited settings, validator or old directory binding differs')
    require(prior['bytesRead']<=state['bytesRead']<=prior['settings']['maxBytes']
            and prior['metadataRead']<=state['metadataRead']<=prior['settings']['metadataBytes']
            and all(state[key]==0 for key in ('reserved','reservedMetadata','uncertainBytes','uncertainMetadata')),
            'Completed acquisition counters differ')


def audio(path,sha,review,selection_sha):
    plan,pin,reviewed,root=_start(path,sha,review,'audio'); remote=None; records=[]
    try:
        selection_pin,value,requests_value=checked_selection(plan,pin,root,selection_sha)
        check_ledger(Path(plan['discoveryRoot']),plan['previousTransport'])
        output=Path(plan['discoveryRoot'])/'transport'
        require(all(not (output/f'quality-audio-{i:03d}.wav').exists()
                    and not (output/f'quality-audio-{i:03d}.wav.partial').exists() for i in range(200)),
                'Preserve existing quality outputs; no overwrite')
        remote=transport(plan,sha,value['selected']); remote.bootstrap()
        require(remote.members()==read(plan['inputs']['members']),'Frozen directory differs')
        allowed=[r['member'] for r in requests_value]
        for index,request in enumerate(requests_value):
            acquired=remote.acquire(request['member'],allowlist=allowed,output_name=f'quality-audio-{index:03d}.wav',
                metadata=False,max_compressed=1024**2,max_uncompressed=128*1024**2)
            record=dict(path=request['path'],identitySha256=request['identitySha256'],
                        partition=request['partition'],componentID=request['componentID'],acquired=acquired)
            selected_recovery.checked_record(record,request,plan['archive'],plan['previousTransport']['validator'])
            write(root/'audio'/f'record-{index:03d}.json',record); records.append(record)
        write(root/'audio/records.json',records); load(path,sha); checked_extension(plan)
        flags=dict(FLAGS,waveformAcquired=True)
        write(root/'audio-freeze.json',dict(complete=True,plan=pin,review=reviewed,selectionFreeze=selection_pin,
            records=binding(root/'audio/records.json'),selectedCount=200,transport=transport_snapshot(remote,root/'audio'),**flags))
        return binding(root/'audio-freeze.json')
    except Exception as error:
        failed=dict(plan=pin,errorType=type(error).__name__,completedCount=len(records),samplePreserved=True)
        if remote is not None: failed['transport']=transport_snapshot(remote,root/'audio')
        write(root/'audio-failure.json',failed); raise
    finally:
        if remote is not None: remote.close()


def waveforms(path,sha,review,selection_sha,audio_sha):
    from nisqa_ingest.waveform_audit import audit_wav
    plan,pin,reviewed,root=_start(path,sha,review,'waveforms')
    try:
        selection_pin,value,requests_value=checked_selection(plan,pin,root,selection_sha)
        audio_pin=binding(root/'audio-freeze.json',audio_sha); frozen=read(audio_pin)
        require(frozen['complete'] is True and frozen['plan']==pin and frozen['selectionFreeze']==selection_pin,
                'Completed matching audio freeze required')
        check_ledger(Path(plan['discoveryRoot']),frozen['transport'])
        records=read(frozen['records']); require(len(records)==200,'Exactly 200 waveform records required')
        results=[]
        for index,(record,request) in enumerate(zip(records,requests_value)):
            require(record['partition']==request['partition'] and record['componentID']==request['componentID'],
                    'Waveform partition join differs')
            selected_recovery.checked_record(record,request,plan['archive'],frozen['transport']['validator'])
            result=dict(path=record['path'],identitySha256=record['identitySha256'],partition=record['partition'],
                        componentID=record['componentID'])
            try: result.update(success=True,audit=audit_wav(record['acquired']['path']))
            except ValueError: result.update(success=False,errorType='ValueError',reason='Selected waveform audit failed')
            binding(record['acquired']['path'],record['acquired']['sha256'])
            write(root/'waveforms'/f'audit-{index:03d}.json',result); results.append(result)
        write(root/'waveforms/audits.json',results); load(path,sha)
        flags=dict(FLAGS,waveformAcquired=True)
        write(root/'waveforms-freeze.json',dict(complete=True,plan=pin,review=reviewed,selectionFreeze=selection_pin,
            audioFreeze=audio_pin,audits=binding(root/'waveforms/audits.json'),selectedCount=200,
            decodedCount=sum(r['success'] for r in results),allSelectedDecoded=all(r['success'] for r in results),**flags))
        return binding(root/'waveforms-freeze.json')
    except Exception as error:
        write(root/'waveforms-failure.json',dict(plan=pin,errorType=type(error).__name__,samplePreserved=True)); raise


def targets(path,sha,review,selection_sha):
    plan,pin,reviewed,root=_start(path,sha,review,'fit-selection-targets')
    try:
        selection_pin,value,_=checked_selection(plan,pin,root,selection_sha)
        with Path(plan['inputs']['combinedCSV']['path']).open(newline='',encoding='utf-8') as stream:
            result=target_parser.parse_partition_targets(stream,value['selected'],'fit-selection')
        write(root/'fit-selection-targets/targets.json',result); load(path,sha)
        flags=dict(FLAGS,numericTargetsAccessed=True,qualityTargetsInterpreted=True)
        write(root/'fit-selection-targets-freeze.json',dict(complete=True,plan=pin,review=reviewed,
            selectionFreeze=selection_pin,targets=binding(root/'fit-selection-targets/targets.json'),
            completeTargets=result['completeTargets'],selectedCount=160,confirmationTargetsAccessed=False,**flags))
        return binding(root/'fit-selection-targets-freeze.json')
    except Exception as error:
        write(root/'fit-selection-targets-failure.json',dict(plan=pin,errorType=type(error).__name__,samplePreserved=True,
              numericTargetsAccessMayHaveOccurred=True,confirmationTargetsAccessed=False)); raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('declare','selection','audio','waveforms','targets'))
    for name in ('output','plan','review'): parser.add_argument('--'+name,type=Path)
    for name in ('plan-sha256','selection-sha256','audio-sha256'): parser.add_argument('--'+name)
    args=parser.parse_args()
    if args.command=='declare': result=declare(args.output)
    elif args.command=='selection': result=selection(args.plan,args.plan_sha256,args.review)
    elif args.command=='waveforms': result=waveforms(args.plan,args.plan_sha256,args.review,args.selection_sha256,args.audio_sha256)
    else: result=globals()[args.command](args.plan,args.plan_sha256,args.review,args.selection_sha256)
    print(json.dumps(result))


if __name__=='__main__': main()
