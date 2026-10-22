"""Synthetic fixed-model and prediction-specific label barrier tests."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from nisqa_ingest import routing
from nisqa_ingest.discovery import binding, read, write
from nisqa_quality import replication as d, regression, audio_features
from nisqa_quality.test_replication_support import selected as selected_fixture


class ReplicationDriverTests(unittest.TestCase):
    def fixture(self,folder,token='3'):
        root=Path(folder)/'replication';root.mkdir();selected=selected_fixture()
        rng=np.random.default_rng(91)
        ssl=np.zeros((160,1536),dtype='<f4');ssl[:,:32]=rng.normal(size=(160,32))
        scalars=rng.uniform(.1,.4,(160,6)).astype('<f8')
        y=np.tile((3+.2*np.tanh(ssl[:,0]))[:,None],(1,5)).astype('<f8')
        models={kind:regression.refit_model(ssl,scalars,y,.01,kind=kind) for kind in ('candidate','acoustic')}
        models.update(mean=y.mean(axis=0),conditionMean=regression.condition_mean(y,['phone']*80+['Skype']*80))
        write(root/'models.json',d.training.encode(models))
        write(root/'old-freeze.json',{'synthetic':True})
        csv_path=root/'combined.csv'
        with csv_path.open('w',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['db','filepath_deg',*routing.TARGETS])
            for row in selected:writer.writerow([routing.TRAIN,row['path'],*[token]*5])
            writer.writerow(['NISQA_TEST_LIVE','NISQA_TEST_LIVE/deg/never.wav','SECRET_TEST_TOKEN'])
        encoder={'runtime':{'device':'cpu'},'identity':'synthetic-frozen-encoder'}
        results={};refs=[];originals=[];audits=[]
        for i in range(44):
            path=root/f'original-{i}.synthetic';path.write_bytes(f'synthetic original {i}'.encode());original=binding(path)
            vector=np.zeros(1536,dtype='<f4');vector[:32]=rng.normal(size=32)
            raw=rng.uniform(.1,.4,6).astype('<f8')
            audit={'input':{'sha256':original['sha256'],'sizeBytes':path.stat().st_size}}
            meta=dict(model=encoder,featuresFloat32Sha256=audio_features._sha(vector,'<f4'),
                rawScalarsFloat64Sha256=audio_features._sha(raw,'<f8'),validFrames=30,expectedFrames=30,
                hiddenShape=[1,30,768],validInputSamples=9600,inputShape=[1,9600],processorDoNormalize=False,
                processorInputFloat32Sha256='a'*64,attentionMaskDtype='torch.int32',attentionMaskHashEncoding='little-endian int64',
                attentionMaskInt64Sha256='b'*64,attentionMaskShape=[1,9600],oneClipPerForward=True,padding=False,
                targetsAccessed=False,waveform={'originalAudit':audit})
            result={'features':vector,'scalars':raw,'metadata':meta};results[str(path)]=result
            if i<4:
                for name,value in (('features',vector),('scalars',raw)):
                    with (root/f'{name}-{i}.npy').open('xb') as stream:np.save(stream,value,allow_pickle=False)
                refs.append(dict(path=f'synthetic-fit-{i}',original=original,metadata=copy.deepcopy(meta),
                    featureFile=binding(root/f'features-{i}.npy'),scalarsFile=binding(root/f'scalars-{i}.npy')))
            else:
                identity=selected[i-4]
                record={k:identity[k] for k in ('path','identitySha256','componentID','partition')}
                acquired=dict(original,size=path.stat().st_size);originals.append(dict(record,acquired=acquired))
                audits.append(dict(record,success=True,audit=audit))
        plan=dict(inputs=dict(models=binding(root/'models.json'),oldModelFreeze=binding(root/'old-freeze.json'),
                              combinedCSV=binding(csv_path)),parityReferences=refs,encoder=encoder,runtime=encoder['runtime'],cacheDirectory='synthetic-offline-cache')
        write(root/'plan.json',plan);pin=binding(root/'plan.json')
        review=root/'source-review.json';write(review,dict(planSha256=pin['sha256'],verdict='clear',blockingFindings=[],independent=True,reviewer='synthetic reviewer'))
        for phase in ('selection','audio','waveforms'):
            (root/phase).mkdir();write(root/phase/'value.json',{'synthetic':True})
            artifacts={'value':binding(root/phase/'value.json')}
            if phase=='waveforms':
                write(root/phase/'audits.json',audits);artifacts['audits']=binding(root/phase/'audits.json')
            extra={}
            if phase=='waveforms':extra.update(selectionFreeze=binding(root/'selection-freeze.json'),audioFreeze=binding(root/'audio-freeze.json'),allSelectedDecoded=True,decodedCount=40)
            d._freeze(root,phase,pin,binding(review),artifacts,**extra)
        self.enterContext(patch.object(d,'load',return_value=(plan,pin)))
        self.enterContext(patch.object(d,'_checked_selection',return_value=(binding(root/'selection-freeze.json'),selected,[])))
        self.enterContext(patch.object(d,'_checked_audio',return_value=(binding(root/'selection-freeze.json'),selected,binding(root/'audio-freeze.json'),originals)))
        self.enterContext(patch.object(d.extraction,'load_frozen_wavlm',return_value=(object(),object(),encoder)))
        self.enterContext(patch.object(d.extraction,'extract_clip',side_effect=lambda path,*args,**kwargs:copy.deepcopy(results[str(path)])))
        return root,pin,review,selected,results

    def predict(self,root,pin,review):
        return d.predict(pin['path'],pin['sha256'],review,*(binding(root/(p+'-freeze.json'))['sha256'] for p in ('selection','audio','waveforms')))

    def reviewed(self,root,pin,predicted,**changes):
        path=root/'specific-review.json'
        value=dict(planSha256=pin['sha256'],predictionFreezeSha256=predicted['sha256'],confirmationAuthorized=True,
                   verdict='clear',blockingFindings=[],independent=True,reviewer='synthetic prediction reviewer')
        value.update(changes);write(path,value);return path

    def test_fixed_models_predict_then_confirm_no_refit_or_prediction_after_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            root,pin,review,selected,results=self.fixture(folder)
            model_sha=read(pin)['inputs']['models']['sha256']
            with patch.object(d.support,'parse_replication_targets',side_effect=AssertionError('labels closed')) as reader, \
                 patch.object(d.regression,'refit_model',side_effect=AssertionError('no refit')), \
                 patch.object(d.regression,'fit_ridge',side_effect=AssertionError('no fitting')):
                predicted=self.predict(root,pin,review);reader.assert_not_called()
            frozen=read(predicted);self.assertFalse(frozen['replicationLabelsAccessed'])
            self.assertTrue(frozen['predictionsFrozenBeforeReplicationLabels'])
            self.assertEqual(frozen['models']['sha256'],model_sha)
            self.assertEqual(len(read(frozen['artifacts']['parity'])),4)
            self.assertEqual(len(read(frozen['artifacts']['records'])),40)
            specific=self.reviewed(root,pin,predicted)
            with patch.object(d.regression,'predict',side_effect=AssertionError('no prediction after labels')), \
                 patch.object(d,'_predict_fixed',side_effect=AssertionError('no prediction after labels')), \
                 patch.object(d.regression,'fit_ridge',side_effect=AssertionError('no fitting')):
                confirmed=d.confirm(pin['path'],pin['sha256'],specific,predicted['sha256'])
            result=read(read(confirmed)['artifacts']['results'])
            self.assertEqual(result['status'],'complete');self.assertFalse(result['refittingPerformed'])
            self.assertEqual(result['bootstrap']['indicesSha256'],d.POLICY['bootstrapIndicesSha256'])
            self.assertNotIn('SECRET_TEST_TOKEN',repr(result))
            with self.assertRaisesRegex(ValueError,'no implicit restart'):d.confirm(pin['path'],pin['sha256'],specific,predicted['sha256'])

    def test_specific_review_rejected_before_start_or_labels(self):
        for change in ({'predictionFreezeSha256':'0'*64},{'confirmationAuthorized':False},{'planSha256':'0'*64}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                root,pin,review,selected,results=self.fixture(folder);predicted=self.predict(root,pin,review)
                wrong=self.reviewed(root,pin,predicted,**change)
                for receipt in (review,wrong):
                    with patch.object(d,'_start',wraps=d._start) as started, \
                         patch.object(d.support,'parse_replication_targets',side_effect=AssertionError('closed')) as reader:
                        with self.assertRaises(ValueError):d.confirm(pin['path'],pin['sha256'],receipt,predicted['sha256'])
                        started.assert_not_called();reader.assert_not_called()
                    self.assertFalse((root/'confirm-started.json').exists())

    def test_tampered_prediction_artifacts_rejected_before_labels(self):
        for name in ('features','predictions','records','clamps','parity'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                root,pin,review,selected,results=self.fixture(folder);predicted=self.predict(root,pin,review)
                specific=self.reviewed(root,pin,predicted);artifact=Path(read(predicted)['artifacts'][name]['path'])
                artifact.write_bytes(artifact.read_bytes()+b'tamper')
                with patch.object(d.support,'parse_replication_targets',side_effect=AssertionError('closed')) as reader:
                    with self.assertRaisesRegex(ValueError,'Pinned artifact'):d.confirm(pin['path'],pin['sha256'],specific,predicted['sha256'])
                    reader.assert_not_called()

    def test_parity_frame_or_input_drift_preserves_failure_before_new40(self):
        for field,value in (('processorInputFloat32Sha256','c'*64),('hiddenShape',[1,31,768])):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as folder:
                root,pin,review,selected,results=self.fixture(folder)
                first=read(pin)['parityReferences'][0]['original']['path'];results[first]['metadata'][field]=value
                with self.assertRaisesRegex(ValueError,'parity'):self.predict(root,pin,review)
                self.assertFalse((root/'predict-freeze.json').exists())
                self.assertTrue((root/'predict-failure.json').exists())
                self.assertFalse((root/'predict/record-000.json').exists())

    def test_incomplete_and_structural_label_failures_remain_inconclusive(self):
        for token in ('','NaN','SECRET_BAD_VALUE'):
            with self.subTest(token=token),tempfile.TemporaryDirectory() as folder:
                root,pin,review,selected,results=self.fixture(folder,token);predicted=self.predict(root,pin,review)
                confirmed=d.confirm(pin['path'],pin['sha256'],self.reviewed(root,pin,predicted),predicted['sha256'])
                frozen=read(confirmed);report=read(frozen['artifacts']['results']);numeric=read(frozen['artifacts']['targets'])
                self.assertEqual(report['outcome'],'inconclusive');self.assertFalse(report['passesContinuationScreen'])
                self.assertEqual(len(numeric['rows']),40);self.assertNotIn('SECRET_BAD_VALUE',repr(numeric))
        for reason in ('parse','coverage','join'):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as folder:
                root,pin,review,selected,results=self.fixture(folder);predicted=self.predict(root,pin,review)
                with patch.object(d.support,'parse_replication_targets',side_effect=d.support.ReplicationTargetError(reason)):
                    confirmed=d.confirm(pin['path'],pin['sha256'],self.reviewed(root,pin,predicted),predicted['sha256'])
                report=read(read(confirmed)['artifacts']['results'])
                self.assertEqual(report['reason'],reason);self.assertEqual(report['outcome'],'inconclusive')

    def test_fixed_prediction_uses_saved_means_and_unbounded_outputs(self):
        models={kind:{'transform':{'kind':kind},'model':{'kind':kind}} for kind in ('candidate','acoustic')}
        models.update(mean=np.full(5,3.),conditionMean={'means':{'phone':np.full(5,2.),'Skype':np.full(5,4.)}})
        with patch.object(d.regression,'transform_features',return_value=(np.zeros((40,6)),{})), \
             patch.object(d.regression,'predict',return_value=np.full((40,5),6.)), \
             patch.object(d.regression,'fitted_mean',side_effect=AssertionError('no recomputation')):
            predicted,_=d._predict_fixed(models,np.zeros((40,1536)),np.zeros((40,6)),['phone']*20+['Skype']*20)
        self.assertTrue(np.all(predicted['candidate']==6.));self.assertTrue(np.all(predicted['mean']==3.))
        self.assertTrue(np.all(predicted['conditionMean'][:20]==2.));self.assertTrue(np.all(predicted['conditionMean'][20:]==4.))

    def test_outcome_tiers_do_not_rescue_or_pool(self):
        self.assertEqual(d.outcome({'passesContinuationScreen':True}),'replicated')
        for upper,name in ((-.01,'directional, not replicated'),(0.,'not replicated'),(.01,'not replicated')):
            self.assertEqual(d.outcome({'passesContinuationScreen':False,'comparisons':{'acoustic':{'interval95':[-.2,upper]}}}),name)

    def test_declaration_source_protocol_runtime_drift_blocks_before_selection(self):
        for kind in ('source','protocol','runtime'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder:
                workspace=Path(folder).resolve()/'workspace';(workspace/'outputs/replication').mkdir(parents=True)
                quality=workspace/'nisqa_quality';quality.mkdir();ingest=workspace/'nisqa_ingest';ingest.mkdir()
                (ingest/'helper.py').write_text('synthetic immutable helper')
                for name in d.QUALITY_NAMES:(quality/name).write_text('synthetic source '+name)
                for name in ('encoders.py','data.py','requirements.txt','requirements.lock.txt','requirements.quality.txt'):
                    (workspace/name).write_text('synthetic dependency '+name)
                protocol=workspace/'protocol.md';protocol.write_text('synthetic prospective protocol')
                inherited={'archive':{'url':'https://invalid.example'},'discoveryRoot':str(workspace/'outputs/discovery')}
                with patch.object(d,'HERE',workspace),patch.object(d,'__file__',str(quality/'replication.py')), \
                     patch.object(d,'PROTOCOL',protocol),patch.object(d,'_old_inputs',return_value=({}, {}, [], inherited, {})), \
                     patch.object(d.feature_study,'cache_bindings',return_value={}), \
                     patch.object(d.extraction,'configure_runtime',return_value={'device':'cpu'}) as runtime, \
                     patch.object(d.training,'runtime',return_value={'synthetic':'fixed'}):
                    plan=d.declaration();path=workspace/'outputs/replication/plan.json';write(path,plan);pin=binding(path)
                    self.assertEqual(plan['sources']['nisqa_ingest/helper.py'],binding(ingest/'helper.py'))
                    if kind=='source':(ingest/'helper.py').write_text('drifted imported helper')
                    elif kind=='protocol':protocol.write_text('drifted protocol')
                    else:runtime.return_value={'device':'drifted'}
                    with patch.object(d,'_selection',side_effect=AssertionError('No actual selection')) as selected:
                        with self.assertRaisesRegex(ValueError,'Replication source'):d.selection(path,pin['sha256'],'unused-review')
                        selected.assert_not_called()
                    self.assertFalse((path.parent/'selection-started.json').exists())

    def test_exact_requests_fail_closed_on_inherited_body_and_metadata_caps(self):
        selected=selected_fixture()
        members=[dict(filename=r['archiveMember'],directory=False,flags=0,compress_type=8,compress_size=100,file_size=1000) for r in selected]
        prior={'bytesRead':1000,'metadataRead':2000,'settings':{'maxBytes':1024**2,'metadataBytes':1024**2}}
        requests,budget=d._requests(selected,members,prior)
        self.assertEqual(len(requests),40);self.assertEqual(budget['compressedBytes'],4000)
        for key,limit in (('maxBytes','projectedBodyBytes'),('metadataBytes','projectedMetadataBytes')):
            changed=copy.deepcopy(prior);changed['settings'][key]=budget[limit]-1
            with self.assertRaisesRegex(ValueError,'Shared transfer budget'):d._requests(selected,members,changed)
        with self.assertRaisesRegex(ValueError,'Duplicate directory'):d._requests(selected,members+[members[0]],prior)


if __name__=='__main__':unittest.main()
