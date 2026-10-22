"""Synthetic frozen artifact joins and extraction stubs; no real model or audio."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import platform
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

import numpy as np
import requests
import scipy

from nisqa_ingest.discovery import binding,read,write
from nisqa_quality import feature_study as f
from nisqa_quality.test_targets import chosen


class FeatureStudyTests(unittest.TestCase):
    def fixture(self,directory):
        here=Path(directory).resolve(); (here/'outputs').mkdir()
        root=here/'outputs/ingestion'; root.mkdir()
        selected=chosen(); validator={'etag':'synthetic'}; archive={'url':'synthetic','size':12345}
        (root/'transport').mkdir()
        plan=dict(study='nisqa-quality-ingestion-v1',discoveryRoot=str(root),inputs={'combinedCSV':{'path':'never-read-targets','sha256':'0'*64}},sources={name:binding(Path(f.ingestion.__file__).parent/name)
            for name in f.ingestion.SOURCE_NAMES},requirements={},protocol=binding(f.ingestion.PROTOCOL),
            runtime=dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,
            scipy=scipy.__version__,requests=requests.__version__),archive=archive)
        write(root/'plan.json',plan); pin=binding(root/'plan.json')
        review=root/'review.json'; write(review,dict(planSha256=pin['sha256'],verdict='clear',blockingFindings=[],independent=True,reviewer='synthetic'))
        write(root/'selection-freeze.json',dict(complete=True,plan=pin)); selection_pin=binding(root/'selection-freeze.json')
        requests_value=[]; records=[]; audits=[]
        for index,row in enumerate(selected):
            path=root/'transport'/f'quality-audio-{index:03d}.wav'; body=f'synthetic-{index}'.encode(); path.write_bytes(body)
            member=dict(filename=row['archiveMember'],file_size=len(body),CRC=zlib.crc32(body)&0xffffffff)
            request={key:row[key] for key in ('path','identitySha256','componentID','partition')}
            request.update(directoryEntry=member); requests_value.append(request)
            record={key:row[key] for key in ('path','identitySha256','componentID','partition')}
            record['acquired']=dict(member=member,size=len(body),path=str(path),sha256=binding(path)['sha256'],
                archive=dict(**archive,validator=validator,fullArchiveMd5Verified=False))
            records.append(record)
            audits.append(dict(**{key:row[key] for key in ('path','identitySha256','componentID','partition')},
                success=True,audit=dict(input={'sha256':record['acquired']['sha256'],'sizeBytes':len(body)})))
        write(root/'audio-records.json',records); write(root/'waveform-audits.json',audits)
        write(root/'audio-freeze.json',dict(complete=True,plan=pin,selectionFreeze=selection_pin,selectedCount=200,
            review=binding(review),records=binding(root/'audio-records.json'),transport={'validator':validator}))
        write(root/'waveforms-freeze.json',dict(complete=True,plan=pin,selectionFreeze=selection_pin,
            audioFreeze=binding(root/'audio-freeze.json'),selectedCount=200,decodedCount=200,allSelectedDecoded=True,
            review=binding(review),audits=binding(root/'waveform-audits.json')))
        for name in ('requirements.txt','requirements.lock.txt','requirements.quality.txt'): (here/name).write_text('synthetic pins')
        source=here/'feature-source.py'; source.write_text('synthetic source')
        cache=here/'cache'; cache.write_bytes(b'synthetic model cache')
        cache_pin=dict(binding(cache),sizeBytes=cache.stat().st_size)
        stack=ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(f,'HERE',here)); stack.enter_context(patch.object(f,'SOURCE_PATHS',(source,)))
        stack.enter_context(patch.object(f,'cache_bindings',side_effect=lambda:{'synthetic':dict(binding(cache),sizeBytes=cache.stat().st_size)}))
        stack.enter_context(patch.object(f.ingestion,'checked_selection',return_value=(selection_pin,{'selected':selected},requests_value)))
        output=here/'outputs/features'; feature_pin=f.declare(output,pin['path'],pin['sha256'])
        reviewed=output/'review.json'; write(reviewed,dict(planSha256=feature_pin['sha256'],verdict='clear',blockingFindings=[],independent=True,reviewer='synthetic'))
        feature_plan=read(feature_pin)
        encoder=dict(policy=feature_plan['policies']['extraction'],runtime=feature_plan['runtime'],
            **{key:feature_plan['policies']['extraction'][key] for key in ('modelId','revision','artifactSha256','artifactBytes')},
            parameterDtypes=['torch.float32'],licenseEvidence=copy.deepcopy(f.extraction.WAVLM_LICENSE))
        def extract(path,model,processor,identity,device):
            features=np.arange(1536,dtype='<f4'); scalars=np.arange(6,dtype='<f8')
            return dict(features=features,scalars=scalars,metadata=dict(
                waveform={'originalAudit':{'input':binding(path)}},featuresFloat32Sha256=f.audio_features._sha(features,'<f4'),
                rawScalarsFloat64Sha256=f.audio_features._sha(scalars,'<f8'),validFrames=3,expectedFrames=3,
                model=identity,targetsAccessed=False))
        return output,feature_pin,reviewed,encoder,extract,root,source,cache

    def test_exact200_success_schema_shapes_records_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            output,pin,review,encoder,extract,*_=self.fixture(directory)
            with patch.object(f.extraction,'load_frozen_wavlm',return_value=(object(),object(),encoder)) as loader, \
                 patch.object(f.extraction,'extract_clip',side_effect=extract) as forward:
                freeze=read(f.run(pin['path'],pin['sha256'],review))
            self.assertEqual(loader.call_count,1); self.assertEqual(forward.call_count,200)
            self.assertEqual(set(freeze),{'complete','plan','review','ingestionPlan','selectionFreeze','audioFreeze','waveformsFreeze',
                'features','records','encoder','modelInferencePerformed','qualityTargetsInterpreted','clinicalUseEligible','learnerJudgmentsEnabled'})
            with np.load(freeze['features']['path'],allow_pickle=False) as arrays:
                self.assertEqual(arrays['ssl'].shape,(200,1536)); self.assertEqual(arrays['ssl'].dtype,np.dtype('<f4'))
                self.assertEqual(arrays['scalars'].shape,(200,6)); self.assertEqual(arrays['scalars'].dtype,np.dtype('<f8'))
                records=read(freeze['records'])
                for index,record in enumerate(records):
                    self.assertEqual(record['featureFloat32Sha256'],f.audio_features._sha(arrays['ssl'][index],'<f4'))
                    self.assertEqual(record['rawScalarsFloat64Sha256'],f.audio_features._sha(arrays['scalars'][index],'<f8'))
                    self.assertEqual(read(record['metadataFile']),record['metadata'])
            self.assertTrue(freeze['modelInferencePerformed']); self.assertFalse(freeze['qualityTargetsInterpreted'])
            self.assertEqual(freeze['review'],binding(review))
            review.write_text('{}')
            with self.assertRaises(ValueError): read(freeze['review'])

    def test_original_source_cache_tamper_rejects_before_model_or_forward(self):
        for target in ('original','source','cache'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as directory:
                output,pin,review,encoder,extract,root,source,cache=self.fixture(directory)
                path=root/'transport/quality-audio-000.wav' if target=='original' else source if target=='source' else cache
                path.write_bytes(b'tamper')
                with patch.object(f.extraction,'load_frozen_wavlm') as loader,patch.object(f.extraction,'extract_clip') as forward:
                    with self.assertRaises(ValueError): f.run(pin['path'],pin['sha256'],review)
                    loader.assert_not_called(); forward.assert_not_called()
                self.assertFalse((output/'features-started.json').exists())

    def test_failure_preserves_perrow_outputs_and_no_implicit_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            output,pin,review,encoder,extract,*_=self.fixture(directory); count=[0]
            def fail(*args,**kwargs):
                count[0]+=1
                if count[0]==3: raise ValueError('Synthetic forward failure')
                return extract(*args,**kwargs)
            with patch.object(f.extraction,'load_frozen_wavlm',return_value=(object(),object(),encoder)), \
                 patch.object(f.extraction,'extract_clip',side_effect=fail):
                with self.assertRaises(ValueError): f.run(pin['path'],pin['sha256'],review)
                with self.assertRaisesRegex(ValueError,'no implicit restart'): f.run(pin['path'],pin['sha256'],review)
            failed=read(binding(output/'features-failure.json'))
            self.assertEqual(failed['completedCount'],2); self.assertTrue((output/'features/record-001.json').exists())
            self.assertFalse((output/'feature-freeze.json').exists()); self.assertEqual(count[0],3)

    def test_bad_loaded_identity_rejects_before_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            output,pin,review,encoder,extract,*_=self.fixture(directory)
            encoder=copy.deepcopy(encoder); encoder['runtime']['torch']='other'
            with patch.object(f.extraction,'load_frozen_wavlm',return_value=(object(),object(),encoder)), \
                 patch.object(f.extraction,'extract_clip') as forward:
                with self.assertRaisesRegex(ValueError,'Loaded encoder'): f.run(pin['path'],pin['sha256'],review)
                forward.assert_not_called()

    def test_review_rejects_before_model_and_changed_review_preserves_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            output,pin,review,encoder,extract,*_=self.fixture(directory)
            value=read(binding(review)); value['independent']=False
            review.write_text(json.dumps(value))
            with patch.object(f.extraction,'load_frozen_wavlm') as loader:
                with self.assertRaisesRegex(ValueError,'Independent clear'): f.run(pin['path'],pin['sha256'],review)
                loader.assert_not_called()
            self.assertFalse((output/'features-started.json').exists())
        with tempfile.TemporaryDirectory() as directory:
            output,pin,review,encoder,extract,*_=self.fixture(directory)
            count=[0]
            def changed(*args,**kwargs):
                count[0]+=1
                value=read(binding(review)); value['reviewer']='changed but still semantically clear'
                review.write_text(json.dumps(value))
                return extract(*args,**kwargs)
            with patch.object(f.extraction,'load_frozen_wavlm',return_value=(object(),object(),encoder)), \
                 patch.object(f.extraction,'extract_clip',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'Pinned artifact'): f.run(pin['path'],pin['sha256'],review)
            self.assertEqual(count[0],1)
            self.assertEqual(read(binding(output/'features-failure.json'))['completedCount'],1)
            self.assertTrue((output/'features/record-000.json').exists())
            self.assertFalse((output/'feature-freeze.json').exists())

    def test_cpu_declaration_only_and_no_quality_reader(self):
        with patch.object(f,'_inputs') as inputs:
            with self.assertRaisesRegex(ValueError,'CPU'): f.declaration('unused','unused','cuda')
            inputs.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            *_,root,source,cache=self.fixture(directory)
            # A targets field points to absent forbidden data: declarations do
            # not need any CSV, numerical ratings or ingestion target stage.
            self.assertFalse(hasattr(f,'parse_partition_targets'))
            with patch.object(f.ingestion,'load',side_effect=AssertionError('Would rehash unrelated CSV')):
                pin=binding(root/'plan.json'); f.declaration(pin['path'],pin['sha256'])


if __name__=='__main__': unittest.main()
