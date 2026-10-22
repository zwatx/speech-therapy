"""Exact invented PCM/evidence and real loopback checks; no model execution."""
import base64
from copy import deepcopy
import io
import http.client
import math
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
from mobile_admission import contract
from consumer_app import feedback
from consumer_app.server import Server


def wav_bytes(values):
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
        wav.writeframes(struct.pack('<'+'h'*len(values),*values))
    return output.getvalue()


PROMPT={'schemaVersion':2,'language':'en','transcript':'baby','words':[{'text':'baby','phones':['B','EY1','B','IY0']}],
        'targets':[{'id':'b-beginning-baby','wordIndex':0,'phoneIndex':0,'targetPhone':'B'}]}


def request_bytes(audio):
    return contract.canonical({'schemaVersion':1,'attemptId':'00000000-0000-4000-8000-000000000123','ageYears':9,
                              'prompt':deepcopy(PROMPT),'audioBase64':base64.b64encode(audio).decode()})


def evidence_for(audio,transcript='baby',speech_passed=True):
    from consumer_assessment.bridge import capture
    from admission import policy
    metrics=capture(audio);count=metrics['sampleCount'];windows=(count+511)//512
    evidence={'schemaVersion':1,'status':'recognized' if speech_passed else 'unavailable',
              'reason':None if speech_passed else 'speech_not_detected',
              'capture':{'audioSha256':contract.sha(audio),'valid':True,'metrics':metrics},
              'speechEvidence':{'method':'silero-vad','passed':speech_passed,'positiveSamples':count if speech_passed else 0,
                  'maximumConsecutivePositiveSamples':count if speech_passed else 0,'windowCount':windows,
                  'probabilities':[1.0 if speech_passed else 0.0]*windows,'speechPresenceVerified':False},
              'recognition':{'method':'whisper-base.en','transcript':transcript,'meanTokenLogProbability':-.2,
                  'noSpeechProbability':.1,'complete':True,'endTokenId':50256,'generatedTokenCount':2,
                  'selectedTokenPosteriors':[{'tokenId':100,'selectedLogProbability':-.2}],'requestedWordVerified':False} if speech_passed else None,
              'binding':{'audioSha256':contract.sha(audio),'modelManifestSha256':contract.bindings()['modelManifestSha256'],'policySha256':policy.POLICY_SHA},
              'runtime':{'elapsedSeconds':.2,'peakRssKiB':1000,'workerExitCode':0,'timedOut':False,'acousticCalls':1},
              'claimLimits':dict(contract.CLAIMS)}
    evidence['evidenceSha256']=policy.digest(evidence)
    return evidence


def snapshot():
    return {'pins':contract.bindings(),'feedbackSourceSha256':'a'*64,'wrapperSourceSha256':'b'*64,
            'feedbackPolicySha256':feedback.FEEDBACK_POLICY_SHA,'contentSha256':'c'*64}


class RecordingTests(unittest.TestCase):
    def test_exact_sample_properties_and_finite_silence_floor(self):
        metrics=feedback.measure_recording(wav_bytes([8192]*3200))
        self.assertEqual(metrics['sampleCount'],3200);self.assertEqual(metrics['durationMilliseconds'],200)
        self.assertEqual(metrics['rms'],.25);self.assertEqual(metrics['peak'],.25)
        self.assertAlmostEqual(metrics['rmsDbfs'],-12.041199826559248)
        self.assertEqual(metrics['railSamples'],0);self.assertEqual(metrics['clippedFraction'],0)
        silent=feedback.measure_recording(wav_bytes([0]*1600))
        self.assertEqual(silent['rmsDbfs'],-120);self.assertTrue(math.isfinite(silent['rmsDbfs']))

    def test_recognition_match_is_separate_from_target_correctness(self):
        from admission.policy import decide
        audio=wav_bytes([8192]*3200);raw=request_bytes(audio);evidence=evidence_for(audio)
        result=feedback.project_feedback(raw,evidence,decide(evidence,'baby'),snapshot())
        self.assertEqual(result['stages']['word']['state'],'model_matched')
        self.assertEqual(result['stages']['speech']['state'],'model_detected')
        self.assertEqual(result['targetAssessment'],{'state':'not_performed','reason':'not_validated'})
        self.assertTrue(all(value is False for value in result['claimLimits'].values()))
        self.assertNotIn('transcript',contract.canonical(result).decode())

    def test_valid_capture_cannot_claim_invalid_audio_preflight(self):
        from admission.policy import decide,digest
        audio=wav_bytes([8192]*3200);evidence=evidence_for(audio)
        evidence.update(status='unavailable',reason='invalid_audio',speechEvidence=None,recognition=None,
                        runtime={'elapsedSeconds':0,'peakRssKiB':None,'workerExitCode':None,'timedOut':False,'acousticCalls':0})
        evidence['evidenceSha256']=digest({key:value for key,value in evidence.items() if key!='evidenceSha256'})
        result=feedback.project_feedback(request_bytes(audio),evidence,decide(evidence,'baby'),snapshot())
        self.assertEqual(result['reason'],'invalid_evidence')

    def test_rehashed_contradictory_completion_is_not_recognition_uncertainty(self):
        from admission.policy import decide,digest
        audio=wav_bytes([8192]*3200)
        for complete,end in ((True,100),(False,50256)):
            evidence=evidence_for(audio);evidence['recognition'].update(complete=complete,endTokenId=end)
            evidence['evidenceSha256']=digest({key:value for key,value in evidence.items() if key!='evidenceSha256'})
            result=feedback.project_feedback(request_bytes(audio),evidence,decide(evidence,'baby'),snapshot())
            self.assertEqual(result['reason'],'invalid_evidence')

    def test_valid_partial_window_negative_vad_and_rehashed_contradiction(self):
        from admission.policy import decide,digest
        audio=wav_bytes([8192]*3200);evidence=evidence_for(audio,speech_passed=False)
        evidence['speechEvidence'].update(probabilities=[1,0,0,0,0,0,1],positiveSamples=640,maximumConsecutivePositiveSamples=512)
        evidence['evidenceSha256']=digest({k:v for k,v in evidence.items() if k!='evidenceSha256'})
        result=feedback.project_feedback(request_bytes(audio),evidence,decide(evidence,'baby'),snapshot())
        self.assertEqual(result['stages']['speech']['state'],'model_not_detected')
        self.assertEqual(result['stages']['word']['state'],'not_run')
        evidence['speechEvidence']['positiveSamples']=641
        evidence['evidenceSha256']=digest({k:v for k,v in evidence.items() if k!='evidenceSha256'})
        self.assertEqual(feedback.project_feedback(request_bytes(audio),evidence,decide(evidence,'baby'),snapshot())['reason'],'invalid_evidence')

    def test_mismatch_uncertainty_multiple_words_and_private_evidence_never_leak(self):
        from admission.policy import decide,digest
        audio=wav_bytes([8192]*3200)
        for transcript,uncertain,expected in (('door',False,'model_not_matched'),('baby',True,'uncertain'),('baby door',False,'not_single_word')):
            evidence=evidence_for(audio,transcript)
            if uncertain:
                evidence['recognition']['meanTokenLogProbability']=-1
                evidence['recognition']['selectedTokenPosteriors'][0]['selectedLogProbability']=-1
                evidence['evidenceSha256']=digest({k:v for k,v in evidence.items() if k!='evidenceSha256'})
            result=feedback.project_feedback(request_bytes(audio),evidence,decide(evidence,'baby'),snapshot())
            self.assertEqual(result['stages']['speech']['state'],'model_detected')
            self.assertEqual(result['stages']['word']['state'],expected)
            text=contract.canonical(result).decode();self.assertNotIn('transcript',text);self.assertNotIn('probabilities',text)

    def test_silence_clipping_actual_preflight_and_operational_withholding(self):
        from admission import adapter,policy
        for sample,reason in ((0,'silence'),(32767,'clipping')):
            audio=wav_bytes([sample]*3200)
            with patch.object(adapter,'_run_worker',side_effect=AssertionError('acoustics started')):
                evidence=adapter.recognize(audio)
            result=feedback.project_feedback(request_bytes(audio),evidence,policy.decide(evidence,'baby'),snapshot())
            self.assertEqual(result['reason'],reason);self.assertEqual(result['stages']['speech']['state'],'not_run')
            self.assertEqual(result['stages']['capture']['state'],'observed')
        audio=wav_bytes([8192]*3200);raw=request_bytes(audio)
        for reason in ('busy','timeout','source_binding_failed','assessment_failed'):
            result=feedback.project_feedback(raw,None,None,snapshot(),reason=reason)
            self.assertEqual(result['stages']['capture']['state'],'observed')
            self.assertEqual(result['stages']['speech']['state'],'unavailable')
        suppressed=feedback.project_feedback(raw,None,None,snapshot(),reason='cleanup_unconfirmed')
        self.assertIsNone(suppressed['stages']['capture']['rms']);self.assertIsNone(suppressed['binding']['evidenceSha256'])

    def test_rehashed_bool_nonfinite_pin_and_metric_spoofs_reject(self):
        from admission.policy import decide,digest
        audio=wav_bytes([8192]*3200)
        mutations=(lambda e:e['capture']['metrics'].update(railSamples=False),lambda e:e['claimLimits'].update(clinicalUseEligible=0),
                   lambda e:e['binding'].update(audioSha256='0'*64),lambda e:e['capture']['metrics'].update(rms=.4),
                   lambda e:e['runtime'].update(workerExitCode=True),lambda e:e.update(extra='private sentinel'))
        for edit in mutations:
            evidence=evidence_for(audio);edit(evidence)
            evidence['evidenceSha256']=digest({k:v for k,v in evidence.items() if k!='evidenceSha256'})
            result=feedback.project_feedback(request_bytes(audio),evidence,decide(evidence,'baby'),snapshot())
            self.assertEqual(result['reason'],'invalid_evidence')
        evidence=evidence_for(audio);evidence['recognition']['meanTokenLogProbability']=float('nan')
        self.assertEqual(feedback.project_feedback(request_bytes(audio),evidence,{},snapshot())['reason'],'invalid_evidence')

    def test_public_closed_shape_and_no_fabricated_metrics(self):
        raw=request_bytes(wav_bytes([8192]*3200));value=feedback.project_feedback(raw,None,None,snapshot(),reason='busy')
        for edit in (lambda r:r.update(transcript='sentinel'),lambda r:r['stages']['capture'].update(rms=float('inf')),
                     lambda r:r['claimLimits'].update(diagnosisProvided=True),lambda r:r['binding'].update(requestSha256='0'*64)):
            changed=deepcopy(value);edit(changed)
            with self.assertRaises(ValueError):feedback.validate_response(changed,raw,snapshot())

    def test_public_operational_failure_cannot_retain_model_or_cleanup_observations(self):
        raw=request_bytes(wav_bytes([8192]*3200));value=feedback.project_feedback(raw,None,None,snapshot(),reason='busy')
        changed=deepcopy(value);changed.update(reason='cleanup_unconfirmed')
        with self.assertRaises(ValueError):feedback.validate_response(changed,raw,snapshot())
        changed=deepcopy(value);changed['status']='observed'
        with self.assertRaises(ValueError):feedback.validate_response(changed,raw,snapshot())
        changed=deepcopy(value);changed['stages']['speech']={'state':'model_detected','reason':None}
        with self.assertRaises(ValueError):feedback.validate_response(changed,raw,snapshot())


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.executor=feedback.FeedbackExecutor(Path(self.directory.name)/'runtime')
        self.audio=wav_bytes([8192]*3200);self.raw=request_bytes(self.audio)
    def tearDown(self):self.executor.close();self.directory.cleanup()
    def completed(self,command,raw,**kwargs):
        from admission.policy import decide
        self.assertTrue((self.executor.runtime/'cleanup-required').exists())
        evidence=evidence_for(self.audio)
        payload={'schemaVersion':1,'binding':self.executor.declared_snapshot,'evidence':evidence,'decision':decide(evidence,'baby')}
        path=Path(command[-1])/'feedback.json';path.write_bytes(contract.canonical(payload));path.chmod(0o600)
        return {'cleanupConfirmed':True,'supervisionFailed':False,'timedOut':False,'workerExitCode':0}
    def test_intent_precedes_worker_and_success_publishes_after_cleanup(self):
        with patch.object(feedback,'supervise',side_effect=self.completed):result=self.executor.execute_feedback(self.raw)
        self.assertEqual(result['stages']['word']['state'],'model_matched')
        self.assertFalse(list(self.executor.runtime.glob('attempt-*')));self.assertFalse((self.executor.runtime/'cleanup-required').exists())
    def test_late_source_change_suppresses_affirmation(self):
        real=feedback.source_snapshot();changed={**real,'wrapperSourceSha256':'0'*64}
        with patch.object(feedback,'source_snapshot',side_effect=(real,changed)),patch.object(feedback,'supervise',side_effect=self.completed):
            result=self.executor.execute_feedback(self.raw)
        self.assertEqual(result['reason'],'source_binding_failed');self.assertEqual(result['stages']['word']['state'],'unavailable')
        self.assertEqual(result['stages']['capture']['state'],'observed')
    def test_cleanup_failure_withholds_every_measurement_and_blocks_reopen(self):
        with patch.object(feedback,'supervise',side_effect=self.completed),patch.object(feedback.shutil,'rmtree',side_effect=OSError()):
            result=self.executor.execute_feedback(self.raw)
        self.assertEqual(result['reason'],'cleanup_unconfirmed');self.assertIsNone(result['stages']['capture']['sampleCount'])
        self.executor.close();self.executor=feedback.FeedbackExecutor(self.executor.runtime)
        with patch.object(feedback,'supervise') as worker:
            self.assertEqual(self.executor.execute_feedback(self.raw)['reason'],'cleanup_unconfirmed');worker.assert_not_called()
    def test_shared_original_assessment_slot_and_declaration_exact_compatibility(self):
        self.executor.slot.acquire()
        try:
            self.assertEqual(self.executor.execute(self.raw)['reason'],'busy')
            self.assertEqual(self.executor.execute_feedback(self.raw)['reason'],'busy')
        finally:self.executor.slot.release()
        self.assertEqual(set(self.executor.feedback_declaration('opaque')),{'schemaVersion','csrfToken','pins','feedbackPolicy','feedbackSourceSha256','wrapperSourceSha256','contentSha256','processingAvailable'})

    def test_worker_recognizes_once_decides_once_and_never_calls_research(self):
        import sys
        from admission import adapter,policy
        from consumer_assessment import bridge
        from consumer_app import feedback_worker
        stage=Path(self.directory.name)/'worker';stage.mkdir(mode=0o700)
        evidence=evidence_for(self.audio)
        with patch.object(sys,'argv',['feedback_worker',str(stage)]),patch.object(sys,'stdin',io.TextIOWrapper(io.BytesIO(self.raw))),patch.object(adapter,'recognize',return_value=evidence) as recognition,patch.object(policy,'decide',wraps=policy.decide) as decision,patch.object(bridge,'assess') as research:
            feedback_worker.main();recognition.assert_called_once_with(self.audio);self.assertEqual(decision.call_count,1);research.assert_not_called()
        self.assertEqual((stage/'feedback.json').stat().st_mode&0o777,0o600)


class FeedbackHTTPTests(unittest.TestCase):
    completed=ExecutorTests.completed
    def setUp(self):
        ExecutorTests.setUp(self)
        class Catalog:
            def accepts(self,prompt):return contract.canonical(prompt)==contract.canonical(PROMPT)
        self.server=Server(self.executor,Catalog(),port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.02});self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();ExecutorTests.tearDown(self)
    def send(self,path='/api/feedback',raw=None,headers=None,method='POST'):
        port=self.server.server_address[1];conn=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
        head={'Origin':self.server.origin,'X-Consumer-CSRF':self.server.csrf_token,'Content-Type':'application/json'}
        if headers:head.update(headers)
        conn.request(method,path,body=self.raw if raw is None and method=='POST' else raw,headers=head)
        response=conn.getresponse();data=response.read();status=response.status;fields=dict(response.getheaders());conn.close()
        return status,data,fields
    def test_actual_http_feedback_and_unchanged_legacy_declaration(self):
        with patch.object(feedback,'supervise',side_effect=self.completed):status,raw,_=self.send()
        self.assertEqual(status,200);result=contract.strict_json(raw)
        self.assertEqual(result['stages']['word']['state'],'model_matched')
        self.assertEqual(len(result['binding']),15)
        original=contract.strict_json(self.send('/api/declaration',method='GET')[1])
        self.assertEqual(set(original),{'schemaVersion','csrfToken','pins','processingAvailable'})
        extended=contract.strict_json(self.send('/api/feedback-declaration',method='GET')[1])
        self.assertEqual(extended['pins'],original['pins']);self.assertEqual(extended['feedbackPolicy']['sha256'],feedback.FEEDBACK_POLICY_SHA)
    def test_feedback_guards_and_client_observation_spoofs_never_launch(self):
        with patch.object(feedback,'supervise') as worker:
            self.assertEqual(self.send(headers={'Origin':'http://other.invalid'})[0],403)
            self.assertEqual(self.send(headers={'X-Consumer-CSRF':'wrong'})[0],403)
            request=contract.strict_json(self.raw);request['rms']=.9
            self.assertEqual(self.send(raw=contract.canonical(request))[0],400)
            self.assertEqual(self.send(raw=self.raw.decode().encode('utf-16'))[0],400)
            self.assertEqual(self.send(raw=b'x'*200001)[0],400);worker.assert_not_called()
    def test_visual_inventory_and_worker_policy(self):
        from consumer_app import visual_assets
        status,raw,headers=self.send('/visual/LICENSE.mediapipe.txt',method='GET')
        self.assertEqual(status,200);self.assertEqual(contract.sha(raw),'8707eef0533987efc5b155d64761eeb6e20793f50b9bd1a68dad1cf4719d0ed8')
        self.assertEqual(headers['Content-Type'],'text/plain; charset=utf-8')
        status,raw,headers=self.send('/visual-worker.js',method='GET');self.assertEqual(status,200)
        self.assertIn("default-src 'none'",headers['Content-Security-Policy']);self.assertIn("worker-src 'self'",headers['Content-Security-Policy'])
        self.assertIn("'wasm-unsafe-eval'",headers['Content-Security-Policy']);self.assertNotIn("'unsafe-eval'",headers['Content-Security-Policy'])
        self.assertEqual(self.send('/visual/source-audit.json',method='GET')[0],404)
        self.assertEqual(self.send('/visual/wasm/unknown.wasm',method='GET')[0],404)
        with tempfile.TemporaryDirectory() as directory:
            temporary=Path(directory);(temporary/'asset-manifest.json').write_bytes((visual_assets.ROOT/'asset-manifest.json').read_bytes())
            (temporary/'LICENSE.mediapipe.txt').write_bytes(b'tampered')
            with patch.object(visual_assets,'ROOT',temporary):
                with self.assertRaises(ValueError):visual_assets.read_asset('/visual/LICENSE.mediapipe.txt')


if __name__=='__main__':unittest.main()
