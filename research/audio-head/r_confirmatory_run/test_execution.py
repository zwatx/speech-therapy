"""Synthetic artifact checks; no reserved corpus or recording access."""
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from r_confirmatory_run.execution import read_extracted_features, generate_predictions, extract_recording, AUDIO, _held_verified, _run, ExtractionFailure
from r_confirmatory_run.test_stages import pin, write, profile_fixture, ratings
from r_confirmatory_run.test_prediction import fixed_fixture
from r_confirmatory_run import stages


class ExecutionTests(unittest.TestCase):
    def test_extracted_features_require_exact_audio_prompt_occurrence_and_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp).resolve()
            b=io.BytesIO(); np.save(b,np.ones((1,1037),dtype=np.float32),allow_pickle=False)
            (d/'features.npy').write_bytes(b.getvalue()); (d/'features.npy').chmod(0o600)
            prompt={'targets':[{'id':'made-up/r','targetPhone':'R','wordIndex':0,'phoneIndex':1}], 'words':[{'phones':['B','R']}], 'transcript':'bar'}
            audio={'path':'/made-up.wav','sha256':'1'*64}; prompt_pin={'path':'/made-up.json','sha256':'2'*64}
            config={'contract':{'sha256':'3'*64},'extractorManifest':{'sha256':'4'*64}}
            parent={'featureSourceBindingSha256':'5'*64,'featureColumns':[str(i) for i in range(1037)]}
            report={'schemaVersion':2,'complete':True,'researchOnly':True,'trainingPerformed':False,'clinicalUseEligible':False,'learnerFeedbackEligible':False,'contractSha256':'3'*64,'headManifestSha256':'4'*64,'featureSourceBindingSha256':'5'*64,'inputBindings':{'audio':audio,'prompt':prompt_pin},'filesSha256':{'features.npy':pin(d/'features.npy')['sha256']},'featureMatrix':{'path':'features.npy','dtype':'float32','shape':[1,1037],'columns':parent['featureColumns']},'canonicalPrompt':{'transcript':'bar','canonicalPhones':['B','R']},'targets':[{'id':'made-up/r','targetPhone':'R','wordIndex':0,'phoneIndex':1,'modelTargetId':16}], 'ctcRuntime':{'fetchAttempts':0}}
            report_pin=write(d/'report.json',report)
            value, bindings=read_extracted_features(d,report_pin,audio,prompt_pin,prompt,config,parent)
            self.assertEqual(value.shape,(1037,))
            self.assertEqual(bindings['features'],pin(d/'features.npy'))
            report['targets'][0]['id']='another/r'; report_pin=write(d/'report.json',report)
            with self.assertRaisesRegex(ValueError,'extractor_output_differs'):
                read_extracted_features(d,report_pin,audio,prompt_pin,prompt,config,parent)

    def test_genuine_synthetic_generation_flows_through_lock_join_evaluation_audit_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp).resolve(); model_dir=d/'models'; model_dir.mkdir()
            profile=profile_fixture(d); models=fixed_fixture(model_dir)
            profile['inputBindings'].update(candidate=models['candidate_binding'],retained=models['retained_manifest_binding'],calibration=models['calibration_binding'])
            protocol_path=Path(models['protocol_binding']['path'])
            protocol=json.loads(protocol_path.read_bytes()); protocol.update(synthetic=True,selectedResearchPolicy=profile['policy'])
            profile['inputBindings']['frozenProtocol']=write(protocol_path,protocol)
            profile['sourceBindings'].update(models['source_bindings'])
            profile['sourceBindings'].update(execution=pin(Path(__file__).with_name('execution.py')),requests=pin(Path(__file__).with_name('requests.py')))
            rows=[{'tokenId':t['tokenId'],'features':[0.]*1037,'ageYears':9} for t in profile['selectedTokens']]
            profile['executionInputs']=write(d/'execution.json',{'schemaVersion':1,'mode':'synthetic','featureRows':rows})
            root=d/'run'; decl=stages.declare_run(profile,root)
            generated=generate_predictions(root,decl['sha256'],profile['executionInputs'])
            envelope=json.loads(Path(generated['predictions']['path']).read_bytes())
            self.assertEqual(len(envelope['payload']['arms']['candidate']),4)
            self.assertTrue(all(r['probability']==.5 for r in envelope['payload']['arms']['candidate']))
            with self.assertRaises(ValueError):
                generate_predictions(root,decl['sha256'],profile['executionInputs'])
            locked=stages.lock_predictions(root,decl['sha256'],generated['predictions'],generated['completion']['sha256'])
            joined=stages.join_outcomes(root,decl['sha256'],locked['lock']['sha256'],write(d/'ratings.json',ratings(profile)))
            evaluated=stages.evaluate_run(root,decl['sha256'],joined['completion']['sha256'])
            audited=stages.audit_run(root,decl['sha256'],evaluated['completion']['sha256'])
            decision=json.loads(Path(audited['decision']['path']).read_bytes())
            self.assertEqual(decision['verdict'],'fail_below_target')
            self.assertFalse(decision['learnerFeedbackEligible'])
            self.assertTrue(decision['syntheticFixture'])

    def test_converter_noop_failure_is_terminal_and_cannot_reuse_clip_destination(self):
        with tempfile.TemporaryDirectory(dir=AUDIO/'outputs',prefix='synthetic-extraction-test-') as tmp:
            root=Path(tmp).resolve(); source=root/'source.wav'; source.write_bytes(b'invented-not-a-recording')
            fake=root/'fake'; fake.write_bytes(b'invented-executable')
            runtime={k:pin(fake) for k in ('python','node','ffmpeg','contract','extractorManifest')}
            runtime['phoneticSnapshot']=str(root)
            token={'tokenId':'made-up/r','startSeconds':0.,'endSeconds':1.}
            with patch('r_confirmatory_run.execution._run') as run:
                with self.assertRaisesRegex(ValueError,'extraction_integrity_failure'):
                    extract_recording(root/'cut',pin(source),token,{},runtime,{})
                self.assertEqual(run.call_count,1)
                self.assertTrue((root/'cut/failure.json').exists())
                with self.assertRaises(ValueError):
                    extract_recording(root/'cut',pin(source),token,{},runtime,{})
                self.assertEqual(run.call_count,1)

    def test_held_source_rejects_replacement_and_runtime_interruptions_propagate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); source=root/'source'; source.write_bytes(b'synthetic')
            original=pin(source)
            with self.assertRaisesRegex(ValueError,'source_identity_changed'):
                with _held_verified(original) as stream:
                    self.assertEqual(stream.read(),b'synthetic')
                    replacement=root/'replacement'; replacement.write_bytes(b'synthetic'); replacement.replace(source)
        with patch('r_confirmatory_run.execution.subprocess.Popen') as popen, patch('r_confirmatory_run.execution.os.killpg') as kill:
            popen.return_value.pid=123
            popen.return_value.wait.side_effect=[KeyboardInterrupt(),0]
            with self.assertRaises(KeyboardInterrupt):
                _run(['/invented-worker'],1)
            kill.assert_called_once()
        with patch('r_confirmatory_run.execution.subprocess.Popen') as popen:
            popen.return_value.wait.return_value=2
            with self.assertRaises(ExtractionFailure):
                _run(['/invented-converter'],1,decoder=True)
            with self.assertRaisesRegex(ValueError,'extractor_worker_failed'):
                _run(['/invented-extractor'],1)
