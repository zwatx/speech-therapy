"""Fresh 40-component evaluation of immutable quality models; never refit."""
import argparse
import copy
import json
from pathlib import Path

import numpy as np

from nisqa_ingest import selected_recovery
from nisqa_ingest.discovery import (binding, read, write, require, guard,
    checked_review, fresh, check_ledger, transport_snapshot)
from nisqa_ingest.waveform_audit import audit_wav
from nisqa_quality import (ingestion, selection as selector, training, regression,
    extraction, audio_features, feature_study, replication_support as support,
    replication_transport)

HERE = ingestion.HERE
PROTOCOL = ingestion.ROOT/'docs/model/nisqa-quality-replication-v1.md'
OLD = ingestion.BASE/'quality-training-v1'
OLD_SHA = '797361b0a979a739f6d42d4d270c507d1a8e3a9de9172d613b7b6e3f2f71ebc5'
MODEL_SHA = '06658f6617bdef7370864e98251eafbb4e61d72cbd7d244c6d8dee12c6f201b6'
CONFIRM_SHA = '257b654819760c280117ed455b38c684194cd12c8b27bf86c3715d74612ef821'
METHOD = ingestion.ROOT/'work/nisqa-quality-20260927/opus-results-review.json'
POLICY = dict(version='nisqa-quality-replication-v1', count=40, device='cpu',
    phases=['selection','audio','waveforms','predict','confirm'], parityOriginalFitRows=4,
    refitting=False, lambdaChanges=False, models='unchanged saved160-row states',
    predictionControls=['candidate','acoustic','mean','conditionMean'],
    confirmationReview='exact predictionFreezeSha256 and confirmationAuthorized true before start or labels',
    noReplacement=True, implicitRestart=False, clipping=False, pooledPassDecision=False,
    bootstrapIndicesSha256='5eeaf74ea206f3bd6ceb0357fa0381fe1f984fbb1066d01cf6d6633fb91c79e2',
    outcomeTiers=['replicated','directional, not replicated','not replicated','inconclusive'],
    clinicalUseEligible=False, learnerJudgmentsEnabled=False)
QUALITY_NAMES = ('__init__.py','ingestion.py','selection.py','targets.py','audio_features.py',
    'extraction.py','feature_study.py','training.py','regression.py','replication.py',
    'test_replication.py','replication_support.py','test_replication_support.py',
    'replication_transport.py','test_replication_transport.py')


def _old_inputs():
    old, old_pin = training.load(OLD/'plan.json', OLD_SHA)
    model_pin, model_freeze = training._phase(OLD/'refit-predict-freeze.json', MODEL_SHA, old_pin, 'refit-predict')
    confirm_pin = binding(OLD/'confirm-freeze.json', CONFIRM_SHA)
    confirmed = read(confirm_pin)
    require(confirmed['plan'] == old_pin and confirmed['predictionFreeze'] == model_pin
        and confirmed['complete'] is True and confirmed['completeTargets'] is True,
        'Completed original fixed study required')
    method_pin = checked_review(METHOD, OLD_SHA)
    require(read(method_pin)['confirmationFreezeSha256'] == CONFIRM_SHA, 'Original result review differs')
    models = training.decode(read(model_freeze['artifacts']['models']))
    require(set(models) == set(POLICY['predictionControls'])
        and all(models[k]['model']['fitRows'] == 160 and models[k]['model']['lambda'] == .01
                for k in ('candidate','acoustic'))
        and models['conditionMean']['fitCounts'] == {'phone':80,'Skype':80}, 'Saved fixed model recipe differs')
    old_feature = read(old['inputs']['featureFreeze'])
    records = read(old_feature['records'])
    refs = [r for r in records if r['partition'] == 'fit'][:4]
    require(len(refs) == 4, 'Four original fitting references required')
    for ref in refs:
        guard({name:ref[name] for name in ('original','featureFile','scalarsFile','metadataFile')})
    old_selection = read(old['inputs']['selectionFreeze'])
    acquired = read(old['inputs']['audioFreeze'])
    previous = acquired['transport']
    guard({name:previous[name] for name in ('state','journal')})
    inputs = dict(oldTrainingPlan=old_pin, oldModelFreeze=model_pin, oldConfirmationFreeze=confirm_pin,
        methodReview=method_pin, models=model_freeze['artifacts']['models'],
        oldSelectionFreeze=old['inputs']['selectionFreeze'], oldSelected=old_selection['selected'],
        oldFeatureFreeze=old['inputs']['featureFreeze'], oldFeatureRecords=old_feature['records'],
        ingestionPlan=old['inputs']['ingestionPlan'], combinedCSV=old['inputs']['combinedCSV'])
    inherited = read(inputs['ingestionPlan'])
    inputs.update(members=inherited['inputs']['members'], lineageInventory=inherited['inputs']['lineageInventory'],
                  pilotSelected=inherited['inputs']['pilotSelected'])
    guard(inputs)
    return inputs, previous, refs, inherited, old_feature['encoder']


def declaration():
    inputs, previous, refs, inherited, encoder = _old_inputs()
    # Bind the complete inherited ingestion helper directory rather than leave
    # dynamically imported helper functions outside the execution closure.
    paths = list((HERE/'nisqa_ingest').glob('*.py'))
    paths += [Path(__file__).parent/name for name in QUALITY_NAMES]
    paths += [HERE/'encoders.py', HERE/'data.py']
    return dict(study=POLICY['version'], protocol=binding(PROTOCOL), inputs=inputs,
        previousTransport=previous, parityReferences=refs, encoder=encoder,
        archive=inherited['archive'], discoveryRoot=inherited['discoveryRoot'],
        sources={str(p.relative_to(HERE)):binding(p) for p in sorted(paths)},
        requirements={n:binding(HERE/n) for n in ('requirements.txt','requirements.lock.txt','requirements.quality.txt')},
        cache=feature_study.cache_bindings(), cacheDirectory=str((HERE/'outputs/model-cache').resolve()),
        runtime=extraction.configure_runtime('cpu'), trainingRuntime=training.runtime(),
        policies=dict(stage=POLICY, support=support.POLICY, targets=support.TARGET_POLICY,
                      transport=replication_transport.POLICY, extraction=extraction.POLICY,
                      audio=audio_features.POLICY, regression=regression.POLICY),
        modelInferencePerformed=False, replicationLabelsAccessed=False, refittingPerformed=False,
        clinicalUseEligible=False, learnerJudgmentsEnabled=False)


def declare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE/'outputs') and not output.exists(), 'Fresh replication output required')
    plan = declaration(); check_ledger(Path(plan['discoveryRoot']), plan['previousTransport'])
    output.mkdir(mode=0o700, parents=True); write(output/'plan.json', plan)
    return binding(output/'plan.json')


def load(path, sha):
    path = Path(path).resolve()
    require(path.name == 'plan.json' and path.is_relative_to(HERE/'outputs'), 'Canonical replication plan required')
    pin = binding(path, sha); plan = read(pin)
    require(plan == declaration(), 'Replication source, inputs, policy or runtime changed')
    return plan, pin


def _start(path, sha, review, phase, expected_review=None):
    plan, pin = load(path, sha); reviewed = checked_review(review, sha)
    require(expected_review is None or reviewed == expected_review, 'Reviewed receipt changed')
    root = Path(pin['path']).parent; fresh(root, phase)
    write(root/(phase+'-started.json'), dict(plan=pin, review=reviewed))
    return plan, pin, reviewed, root


def _failure(root, phase, pin, error, **extra):
    write(root/(phase+'-failure.json'), dict(plan=pin, errorType=type(error).__name__,
        partialOutputsPreserved=True, implicitRestart=False, **extra))


def _phase(root, name, sha, pin):
    bound = binding(root/(name+'-freeze.json'), sha); value = read(bound)
    require(value['complete'] is True and value['plan'] == pin
        and value['replicationLabelsAccessed'] is False, 'Matching target-free phase freeze required')
    binding(value['review']['path'], value['review']['sha256'])
    checked_review(value['review']['path'], pin['sha256']); guard(value['artifacts'])
    return bound, value


def _freeze(root, phase, pin, reviewed, artifacts, **extra):
    write(root/(phase+'-freeze.json'), dict(complete=True, plan=pin, review=reviewed,
        artifacts=artifacts, replicationLabelsAccessed=False, refittingPerformed=False,
        clinicalUseEligible=False, learnerJudgmentsEnabled=False, **extra))
    return binding(root/(phase+'-freeze.json'))


def _selection(plan):
    eligible = ingestion.source_code_selection.prepare_inventory(read(plan['inputs']['lineageInventory']), expected_count=1020)['eligible']
    graph = selector.build_components(eligible, read(plan['inputs']['pilotSelected'])['selected'])
    return support.select_replication(graph, read(plan['inputs']['oldSelected'])['selected'])


def _requests(selected, members, previous):
    support.validate_selected40(selected)
    require(len({r['filename'] for r in members}) == len(members), 'Duplicate directory member')
    lookup = {m['filename']:m for m in members}; result = []
    for row in selected:
        member = lookup.get(row['archiveMember'])
        require(member is not None and not member['directory'] and member['flags'] == 0
            and member['compress_type'] in (0,8) and 0 < member['compress_size'] <= 1024**2
            and 0 < member['file_size'] <= 128*1024**2, 'Selected member missing or unsupported')
        result.append(dict(path=row['path'], identitySha256=row['identitySha256'], partition='replication',
                           componentID=row['componentID'], member=row['archiveMember'], directoryEntry=member))
    compressed = sum(r['directoryEntry']['compress_size'] for r in result)
    headers = sum(30+len(r['member'].encode('utf-8'))+4096 for r in result)
    budget = dict(compressedBytes=compressed, plaintextBytes=sum(r['directoryEntry']['file_size'] for r in result),
        maxHeaderMetadataBytes=headers, projectedBodyBytes=previous['bytesRead']+compressed+headers,
        projectedMetadataBytes=previous['metadataRead']+headers, localExtraLimit=4096)
    require(budget['projectedBodyBytes'] <= previous['settings']['maxBytes']
        and budget['projectedMetadataBytes'] <= previous['settings']['metadataBytes'], 'Shared transfer budget exceeded')
    return result, budget


def selection(path, sha, review):
    plan, pin, reviewed, root = _start(path, sha, review, 'selection')
    try:
        selected = _selection(plan)
        requests, budget = _requests(selected['selected'], read(plan['inputs']['members']), plan['previousTransport'])
        for name, value in (('selected',selected),('requests',requests),('budget',budget)):
            write(root/'selection'/(name+'.json'), value)
        load(path,sha); binding(reviewed['path'],reviewed['sha256'])
        return _freeze(root,'selection',pin,reviewed,{n:binding(root/'selection'/(n+'.json')) for n in ('selected','requests','budget')},selectedCount=40)
    except BaseException as error:
        _failure(root,'selection',pin,error); raise


def _checked_selection(plan, pin, root, sha):
    bound, frozen = _phase(root,'selection',sha,pin)
    selected = _selection(plan)
    require(read(frozen['artifacts']['selected']) == selected, 'Exact metadata selection replay differs')
    requests, budget = _requests(selected['selected'],read(plan['inputs']['members']),plan['previousTransport'])
    require(read(frozen['artifacts']['requests']) == requests and read(frozen['artifacts']['budget']) == budget,
            'Selected requests or budget differs')
    return bound, selected['selected'], requests


def _extension(plan, expected_binding):
    previous = plan['previousTransport']; folder = Path(plan['discoveryRoot'])/'transport'
    guard({n:previous[n] for n in ('state','journal')})
    require((folder/'request-journal.jsonl').read_bytes().startswith(Path(previous['journal']['path']).read_bytes()),
            'Previous journal prefix differs')
    before = read(previous['state']); state = json.loads((folder/'transport-state.json').read_text())
    require(state.get('replicationDirectoryBinding') == expected_binding
        and all(state.get(k) == before.get(k) for k in ('settings','validator','frozenDirectoryBinding','qualityDirectoryBinding'))
        and all(state[k] == 0 for k in ('reserved','reservedMetadata','uncertainBytes','uncertainMetadata'))
        and before['bytesRead'] <= state['bytesRead'] <= state['settings']['maxBytes']
        and before['metadataRead'] <= state['metadataRead'] <= state['settings']['metadataBytes'], 'Inherited ledger changed or incomplete')


def audio(path, sha, review, selection_sha):
    plan,pin,reviewed,root = _start(path,sha,review,'audio'); remote=None; records=[]
    try:
        selected_pin, selected, requests = _checked_selection(plan,pin,root,selection_sha)
        check_ledger(Path(plan['discoveryRoot']),plan['previousTransport'])
        output = Path(plan['discoveryRoot'])/'transport'; settings=plan['previousTransport']['settings']
        require(all(not (output/f'replication-audio-{i:03d}.wav').exists()
            and not (output/f'replication-audio-{i:03d}.wav.partial').exists() for i in range(40)), 'Preserve previous files')
        remote=replication_transport.ReplicationDirectoryZip(plan['archive']['url'],expected_size=plan['archive']['size'],
            output_directory=output,frozen_members=read(plan['inputs']['members']),selected_names=[r['archiveMember'] for r in selected],
            study_sha256=sha,max_bytes=settings['maxBytes'],metadata_bytes=settings['metadataBytes'],allowed_hosts=('zenodo.org',))
        remote.bootstrap(); require(remote.members()==read(plan['inputs']['members']),'Frozen directory differs')
        for i,request in enumerate(requests):
            binding(reviewed['path'],reviewed['sha256'])
            acquired=remote.acquire(request['member'],allowlist=[r['member'] for r in requests],
                output_name=f'replication-audio-{i:03d}.wav',metadata=False,max_compressed=1024**2,max_uncompressed=128*1024**2)
            record={k:request[k] for k in ('path','identitySha256','partition','componentID')};record['acquired']=acquired
            selected_recovery.checked_record(record,request,plan['archive'],plan['previousTransport']['validator'])
            write(root/'audio'/f'record-{i:03d}.json',record);records.append(record)
        write(root/'audio/records.json',records);load(path,sha);_extension(plan,remote.replication_binding);binding(reviewed['path'],reviewed['sha256'])
        return _freeze(root,'audio',pin,reviewed,{'records':binding(root/'audio/records.json')},selectionFreeze=selected_pin,
                       selectedCount=40,transport=transport_snapshot(remote,root/'audio'))
    except BaseException as error:
        extra={'completedCount':len(records)}
        if remote is not None:extra['transport']=transport_snapshot(remote,root/'audio')
        _failure(root,'audio',pin,error,**extra);raise
    finally:
        if remote is not None:remote.close()


def _checked_audio(plan,pin,root,selection_sha,audio_sha):
    selection_pin,selected,requests=_checked_selection(plan,pin,root,selection_sha)
    audio_pin,frozen=_phase(root,'audio',audio_sha,pin)
    require(frozen['selectionFreeze']==selection_pin and frozen['selectedCount']==40,'Audio selection differs')
    check_ledger(Path(plan['discoveryRoot']),frozen['transport'])
    records=read(frozen['artifacts']['records']);require(len(records)==40,'Exactly40 originals required')
    for i,(record,request) in enumerate(zip(records,requests)):
        require(all(record[k]==request[k] for k in ('path','identitySha256','partition','componentID')),'Audio identity join differs')
        selected_recovery.checked_record(record,request,plan['archive'],frozen['transport']['validator'])
        require(Path(record['acquired']['path']).resolve()==(Path(plan['discoveryRoot'])/'transport'/f'replication-audio-{i:03d}.wav').resolve(),
                'Original audio path/order differs')
        binding(record['acquired']['path'],record['acquired']['sha256'])
    return selection_pin,selected,audio_pin,records


def waveforms(path,sha,review,selection_sha,audio_sha):
    plan,pin,reviewed,root=_start(path,sha,review,'waveforms')
    try:
        selection_pin,selected,audio_pin,records=_checked_audio(plan,pin,root,selection_sha,audio_sha)
        audited=[]
        for i,record in enumerate(records):
            result={k:record[k] for k in ('path','identitySha256','partition','componentID')}
            try:
                audit=audit_wav(record['acquired']['path'])
                require(audit['input']['sha256']==record['acquired']['sha256'] and audit['input']['sizeBytes']==record['acquired']['size'],
                        'Original audit hash/size differs')
                result.update(success=True,audit=audit)
            except ValueError:result.update(success=False,errorType='ValueError',reason='Selected original waveform audit failed')
            binding(record['acquired']['path'],record['acquired']['sha256'])
            write(root/'waveforms'/f'audit-{i:03d}.json',result);audited.append(result)
        write(root/'waveforms/audits.json',audited);load(path,sha);binding(reviewed['path'],reviewed['sha256'])
        return _freeze(root,'waveforms',pin,reviewed,{'audits':binding(root/'waveforms/audits.json')},
            selectionFreeze=selection_pin,audioFreeze=audio_pin,selectedCount=40,decodedCount=sum(r['success'] for r in audited),
            allSelectedDecoded=all(r['success'] for r in audited))
    except BaseException as error:_failure(root,'waveforms',pin,error);raise


def _models(plan):
    return training.decode(read(plan['inputs']['models']))


def _predict_fixed(models,ssl,scalars,captures):
    predictions={};clamps={}
    for kind in ('candidate','acoustic'):
        x,clamps[kind]=regression.transform_features(ssl,scalars,models[kind]['transform'],return_diagnostics=True)
        predictions[kind]=regression.predict(x,models[kind]['model'])
    predictions['mean']=np.tile(models['mean'],(len(captures),1))
    predictions['conditionMean']=regression.predict_condition_mean(models['conditionMean'],captures)
    return predictions,clamps


def _save_npz(path,values,specs):
    with path.open('xb') as stream:np.savez(stream,allow_pickle=False,**values)
    return training._npz(binding(path),specs)


def _clip(path,original,model,processor,encoder,audit=None):
    binding(path,original['sha256'])
    result=extraction.extract_clip(path,model,processor,encoder,device='cpu')
    binding(path,original['sha256']);meta=result['metadata'];ssl=result['features'];scalars=result['scalars']
    require(ssl.shape==(1536,) and ssl.dtype==np.dtype('<f4') and np.isfinite(ssl).all()
        and scalars.shape==(6,) and scalars.dtype==np.dtype('<f8') and np.isfinite(scalars).all()
        and meta['featuresFloat32Sha256']==audio_features._sha(ssl,'<f4')
        and meta['rawScalarsFloat64Sha256']==audio_features._sha(scalars,'<f8')
        and meta['validFrames']==meta['expectedFrames']>0 and meta['model']==encoder
        and meta['targetsAccessed'] is False and meta['waveform']['originalAudit']['input']['sha256']==original['sha256'],
        'Encoder feature identity/dtype/hash/frame policy differs')
    require(audit is None or meta['waveform']['originalAudit']==audit,'Frozen original audit differs')
    return result


def _parity(plan,model,processor,encoder):
    evidence=[]
    for ref in plan['parityReferences']:
        result=_clip(ref['original']['path'],ref['original'],model,processor,encoder)
        for kind,key in (('features','featureFile'),('scalars','scalarsFile')):
            binding(ref[key]['path'],ref[key]['sha256'])
            saved=np.load(ref[key]['path'],allow_pickle=False)
            require(saved.dtype==result[kind].dtype and saved.shape==result[kind].shape
                and saved.tobytes()==result[kind].tobytes(),'Bit-identical original FIT CPU parity failed')
        old=ref['metadata'];new=result['metadata']
        keys=('validFrames','expectedFrames','hiddenShape','validInputSamples','inputShape',
              'processorDoNormalize','processorInputFloat32Sha256','attentionMaskDtype',
              'attentionMaskHashEncoding','attentionMaskInt64Sha256','attentionMaskShape',
              'oneClipPerForward','padding')
        require(all(new[k]==old[k] for k in keys) and new['waveform']==old['waveform'],
                'Original FIT preprocessing/frame parity differs')
        evidence.append(dict(path=ref['path'],original=ref['original'],featureSha256=new['featuresFloat32Sha256'],
                             scalarSha256=new['rawScalarsFloat64Sha256'],bitIdentical=True,validFrames=new['validFrames']))
    return evidence


def predict(path,sha,review,selection_sha,audio_sha,waveforms_sha):
    plan,pin,reviewed,root=_start(path,sha,review,'predict');records=[]
    try:
        selection_pin,selected,audio_pin,originals=_checked_audio(plan,pin,root,selection_sha,audio_sha)
        waveform_pin,waveforms=_phase(root,'waveforms',waveforms_sha,pin)
        require(waveforms['selectionFreeze']==selection_pin and waveforms['audioFreeze']==audio_pin
            and waveforms['allSelectedDecoded'] is True and waveforms['decodedCount']==40,'All40 waveform audits required')
        audits=read(waveforms['artifacts']['audits']);require(len(audits)==40,'Exactly40 audits required')
        model,processor,encoder=extraction.load_frozen_wavlm(plan['cacheDirectory'],device='cpu')
        require(encoder==plan['encoder'] and encoder['runtime']==plan['runtime'],'Same pinned original CPU encoder required')
        load(path,sha);parity=_parity(plan,model,processor,encoder);write(root/'predict/parity.json',parity)
        vectors=[];scalars=[]
        for i,(identity,original,audit) in enumerate(zip(selected,originals,audits)):
            binding(reviewed['path'],reviewed['sha256'])
            require(all(identity[k]==original[k]==audit[k] for k in ('path','identitySha256','componentID','partition'))
                and audit['success'] is True,'Selected original/audit join differs')
            result=_clip(original['acquired']['path'],original['acquired'],model,processor,encoder,audit['audit'])
            for key,value in (('ssl',result['features']),('scalars',result['scalars'])):
                feature_study._save_array(root/'predict'/f'{key}-{i:03d}.npy',value)
            write(root/'predict'/f'metadata-{i:03d}.json',result['metadata'])
            record={k:identity[k] for k in ('path','identitySha256','componentID','partition','captureCondition')}
            record.update(original=binding(original['acquired']['path'],original['acquired']['sha256']),metadata=result['metadata'],
                featureFile=binding(root/'predict'/f'ssl-{i:03d}.npy'),scalarsFile=binding(root/'predict'/f'scalars-{i:03d}.npy'),
                metadataFile=binding(root/'predict'/f'metadata-{i:03d}.json'))
            write(root/'predict'/f'record-{i:03d}.json',record);records.append(record)
            vectors.append(result['features']);scalars.append(result['scalars'])
        arrays=_save_npz(root/'predict/features.npz',{'ssl':np.stack(vectors),'scalars':np.stack(scalars)},
                         {'ssl':((40,1536),'<f4'),'scalars':((40,6),'<f8')})
        predictions,clamps=_predict_fixed(_models(plan),arrays['ssl'],arrays['scalars'],[r['captureCondition'] for r in selected])
        _save_npz(root/'predict/predictions.npz',predictions,{n:((40,5),'<f8') for n in POLICY['predictionControls']})
        write(root/'predict/records.json',records);write(root/'predict/clamps.json',clamps)
        for record in records:guard({k:record[k] for k in ('original','featureFile','scalarsFile','metadataFile')})
        load(path,sha);binding(reviewed['path'],reviewed['sha256'])
        return _freeze(root,'predict',pin,reviewed,{n:binding(root/'predict'/f) for n,f in
            (('features','features.npz'),('predictions','predictions.npz'),('records','records.json'),('clamps','clamps.json'),('parity','parity.json'))},
            selectionFreeze=selection_pin,audioFreeze=audio_pin,waveformsFreeze=waveform_pin,models=plan['inputs']['models'],
            oldModelFreeze=plan['inputs']['oldModelFreeze'],predictionRows=40,modelRows=160,
            predictionsFrozenBeforeReplicationLabels=True,encoder=encoder,modelInferencePerformed=True)
    except BaseException as error:_failure(root,'predict',pin,error,completedCount=len(records));raise


def outcome(report):
    if report['passesContinuationScreen']:return 'replicated'
    if report['comparisons']['acoustic']['interval95'][1]<0:return 'directional, not replicated'
    return 'not replicated'


def confirm(path,sha,review,prediction_sha):
    root=Path(path).resolve().parent
    reviewed=checked_review(review,sha);receipt=read(reviewed)
    require(receipt.get('predictionFreezeSha256')==prediction_sha and receipt.get('confirmationAuthorized') is True
        and isinstance(prediction_sha,str) and len(prediction_sha)==64,'Specific independent prediction review required')
    require(not Path(reviewed['path']).resolve().is_relative_to(root/'confirm'),'Review must be outside label-reading outputs')
    binding(root/'predict-freeze.json',prediction_sha)
    plan,pin,reviewed,root=_start(path,sha,review,'confirm',expected_review=reviewed)
    try:
        pred_pin,pred=_phase(root,'predict',prediction_sha,pin)
        require(pred['models']==plan['inputs']['models'] and pred['oldModelFreeze']==plan['inputs']['oldModelFreeze']
            and pred['predictionRows']==40 and pred['modelRows']==160
            and pred['predictionsFrozenBeforeReplicationLabels'] is True,'Saved-model prediction barrier differs')
        _,selected,_=_checked_selection(plan,pin,root,pred['selectionFreeze']['sha256'])
        records=read(pred['artifacts']['records'])
        require(len(records)==40 and all(all(record[k]==identity[k] for k in
            ('path','identitySha256','componentID','partition','captureCondition')) for record,identity in zip(records,selected)),
            'Prediction identity join differs')
        predictions=training._npz(pred['artifacts']['predictions'],{n:((40,5),'<f8') for n in POLICY['predictionControls']})
        csv_pin=plan['inputs']['combinedCSV'];binding(csv_pin['path'],csv_pin['sha256'])
        try:
            with Path(csv_pin['path']).open(newline='',encoding='utf-8') as stream:
                numeric=support.parse_replication_targets(stream,selected)
        except support.ReplicationTargetError as error:
            numeric=dict(completeTargets=False,rows=[],selectedPaths=[r['path'] for r in selected],phase='replication',
                missingCounts=None,invalidCounts=None,reason=error.reason,replicationLabelsAccessed=True)
        if numeric['completeTargets']:
            require(numeric['selectedPaths']==[r['path'] for r in selected] and len(numeric['rows'])==40
                and all(all(a[k]==b[k] for k in ('path','identitySha256','componentID','partition'))
                        for a,b in zip(numeric['rows'],selected)), 'Numerical target identity join differs')
            y=np.array([[r['quality'][n] for n in ('mos','noi','dis','col','loud')] for r in numeric['rows']])
            report=regression.confirmation_report(y,*(predictions[n] for n in POLICY['predictionControls']),
                [r['componentID'] for r in selected],[r['captureCondition'] for r in selected])
            require(report['bootstrap']['indicesSha256']==POLICY['bootstrapIndicesSha256'],'Fixed bootstrap indices differ')
            report.update(status='complete',completeTargets=True,outcome=outcome(report))
        else:
            reason=numeric.get('reason')
            if reason is None:reason='missing and/or invalid selected values'
            report=dict(status='inconclusive',outcome='inconclusive',completeTargets=False,reason=reason,
                missingCounts=numeric['missingCounts'],invalidCounts=numeric['invalidCounts'],passesContinuationScreen=False)
        report.update(clinicalUseEligible=False,learnerJudgmentsEnabled=False,refittingPerformed=False,pooledPassDecision=False)
        write(root/'confirm/targets.json',numeric);write(root/'confirm/results.json',report)
        load(path,sha);binding(reviewed['path'],reviewed['sha256'])
        write(root/'confirm-freeze.json',dict(complete=True,plan=pin,review=reviewed,predictionFreeze=pred_pin,
            artifacts={n:binding(root/'confirm'/f) for n,f in (('targets','targets.json'),('results','results.json'))},
            replicationLabelsAccessed=True,completeTargets=numeric['completeTargets'],refittingPerformed=False,
            clinicalUseEligible=False,learnerJudgmentsEnabled=False))
        return binding(root/'confirm-freeze.json')
    except BaseException as error:_failure(root,'confirm',pin,error,replicationLabelAccessMayHaveOccurred=True);raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('declare',*POLICY['phases']))
    for name in ('output','plan','review','plan-sha','selection-sha','audio-sha','waveforms-sha','prediction-sha'):
        parser.add_argument('--'+name)
    a=parser.parse_args()
    if a.command=='declare':result=declare(a.output)
    elif a.command=='selection':result=selection(a.plan,a.plan_sha,a.review)
    elif a.command=='audio':result=audio(a.plan,a.plan_sha,a.review,a.selection_sha)
    elif a.command=='waveforms':result=waveforms(a.plan,a.plan_sha,a.review,a.selection_sha,a.audio_sha)
    elif a.command=='predict':result=predict(a.plan,a.plan_sha,a.review,a.selection_sha,a.audio_sha,a.waveforms_sha)
    else:result=confirm(a.plan,a.plan_sha,a.review,a.prediction_sha)
    print(json.dumps(result))


if __name__=='__main__':main()
