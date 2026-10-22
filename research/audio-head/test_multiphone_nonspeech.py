"""Synthetic signals and mocked extraction only; no model inference."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import wave
import numpy as np
import multiphone_nonspeech as d

class NonSpeechTests(unittest.TestCase):
    def test_fixed_signals(self):
        for name in d.CONDITIONS:
            payload=d.signal_bytes(name);self.assertEqual(payload,d.signal_bytes(name))
            with wave.open(io.BytesIO(payload),'rb') as f:
                self.assertEqual((f.getnchannels(),f.getframerate(),f.getsampwidth(),f.getnframes()),(1,16000,2,32000))
                x=np.frombuffer(f.readframes(32000),dtype='<i2').astype(np.float64)/32768
            self.assertEqual(len(payload),64044);self.assertLess(np.abs(x).max(),1)
            self.assertAlmostEqual(np.sqrt(np.mean(x*x)),0 if name=='zero' else .1,delta=2e-6)
            if name=='sine440':self.assertEqual(np.argmax(np.abs(np.fft.rfft(x)))*.5,440)
        with self.assertRaises(ValueError):d.signal_bytes('another')

    def fixture(self,root):
        d.raw.write_json(root/'prompt.json',d.PROMPT)
        pins={'prompt':d.raw.binding(root/'prompt.json'),'diagnosticSource':d.raw.binding(d.__file__),'protocol':d.raw.binding(d.PROTOCOL)}
        signals=[]
        for name in d.CONDITIONS:
            p=root/(name+'.wav');p.write_bytes(d.signal_bytes(name));pin=d.raw.binding(p);pins['signal/'+name]=pin
            signals.append({'condition':name,**pin,'recordingMeasurements':d.raw.recording_measurements(d.raw.read_rating_pcm(p,pin['sha256']))})
        plan={'schemaVersion':1,'signals':signals,'heads':[{'variant':v,'bundle':str(root/v),'manifestSha256':v} for v in d.VARIANTS],
              'device':'cpu','threads':2,'repeats':1,'inferencePerformed':False,'humanLabelsAvailable':False,'inputFiles':pins,
              'prompt':pins['prompt'],'snapshot':str(root/'unused'),'contractSha256':'synthetic','node':'unused'}
        p=root/'plan.json';d.raw.write_json(p,plan);return plan,p,d.raw.digest(p)

    def test_plan_and_rehashed_signal_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan,p,sha=self.fixture(Path(tmp));d.checked_plan(p,sha)
            wave_path=Path(plan['signals'][0]['path']);wave_path.write_bytes(d.signal_bytes('sine440'))
            with self.assertRaisesRegex(ValueError,'changed'):d.checked_plan(p,sha)
            new=d.raw.digest(wave_path);plan['signals'][0]['sha256']=new;plan['inputFiles']['signal/zero']['sha256']=new;p.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'signal bytes'):d.checked_plan(p,d.raw.digest(p))

    def test_exact_feature_reuse_and_all_four_heads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan,p,sha=self.fixture(root);calls=[];seen=[];features=np.arange(1037,dtype=np.float32)[None,:]
            def adapter(args):
                calls.append(args.wav.name);args.output.mkdir();np.save(args.output/'features.npy',features,allow_pickle=False)
                signal=next(x for x in plan['signals'] if x['path']==str(args.wav))
                report={'complete':True,'canonicalPrompt':{'transcript':'BALL','canonicalPhones':['B','AO1','L']},
                    'targets':[{**d.PROMPT['targets'][0],'modelTargetId':0,'subjectiveCorpusRatingProbabilities':[.125,.25,.625]}],
                    'filesSha256':{'features.npy':d.raw.digest(args.output/'features.npy')},'recordingMeasurements':signal['recordingMeasurements'],
                    'featureSourceBindingSha256':'fixed','featureMatrix':{'columns':['fixed'],'shape':[1,1037]},'canonicalPathDiagnostics':{},
                    'ctcRuntime':{'fetchAttempts':0},'runtime':{'device':'cpu','threads':2},'headManifestSha256':args.manifest_sha256,
                    'contractSha256':args.contract_sha256,'inputBindings':{'audio':d.raw.binding(args.wav),'prompt':plan['prompt']}}
                d.raw.write_json(args.output/'report.json',report)
            class Head:
                feature_source_binding_sha256='fixed';feature_columns=('fixed',)
                def predict(self,values,ids):
                    np.testing.assert_array_equal(values,features);np.testing.assert_array_equal(ids,[0]);seen.append(values.copy())
                    return np.array([[.125,.25,.625]])
            with mock.patch.object(d.raw,'run',side_effect=adapter),mock.patch.object(d.raw.inference,'load_head',return_value=Head()):result=d.run(p,sha)
            report=json.loads(Path(result['report']).read_text());self.assertEqual(len(calls),3);self.assertEqual(len(seen),12)
            self.assertTrue(all(x['firstHeadReplayExact'] for x in report['outcomes']));self.assertFalse(report['semanticAbstentionImplemented'])
            self.assertFalse(report['accuracyMeasured']);self.assertEqual([list(x['probabilitiesByVariant']) for x in report['outcomes']],[sorted(d.VARIANTS)]*3)
            with self.assertRaisesRegex(ValueError,'Fresh'):d.run(p,sha)

    def test_runtime_errors_are_not_abstention_and_changed_input_aborts(self):
        for mutate in (False,True):
            with self.subTest(mutate=mutate),tempfile.TemporaryDirectory() as tmp:
                plan,p,sha=self.fixture(Path(tmp))
                def fail(args):
                    if mutate:args.wav.write_bytes(b'changed')
                    raise RuntimeError('synthetic extraction failure')
                with mock.patch.object(d.raw,'run',side_effect=fail):
                    if mutate:
                        with self.assertRaisesRegex(ValueError,'changed'):d.run(p,sha)
                        self.assertFalse((Path(tmp)/'results/report.json').exists())
                    else:
                        result=d.run(p,sha);report=json.loads(Path(result['report']).read_text());self.assertEqual(len(report['outcomes']),3)
                        self.assertTrue(all(not x['pipelineAccepted'] and not x['semanticAbstentionImplemented'] for x in report['outcomes']))
                        self.assertIn('not a validated',report['outcomes'][0]['errorMeaning'])

if __name__=='__main__':unittest.main()
