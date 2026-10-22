import array,io,unittest,wave
from admission.policy import AdmissionError

def wav():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as out:
        out.setparams((1,2,16000,3200,'NONE','not compressed'))
        out.writeframes(array.array('h',[1000,-1000]*1600).tobytes())
    return stream.getvalue()
PROMPT={'schemaVersion':2,'language':'en','transcript':'rabbit','words':[{'text':'rabbit','phones':['R','AE1','B','AH0','T']}],
        'targets':[{'id':'rabbit-r','wordIndex':0,'phoneIndex':0,'targetPhone':'R'}]}

class AdapterTests(unittest.TestCase):
    def test_prompt_blind_acoustic_seam_sees_only_bytes_and_rejection_never_calls_bridge(self):
        from admission.adapter import assess
        calls=[]
        def worker(raw):
            calls.append(raw)
            return {'speechEvidence':{'method':'silero-vad','speechPresenceVerified':False,'passed':True,'positiveSamples':3200,'maximumConsecutivePositiveSamples':3200,'windowCount':7,'probabilities':[0.9]*7},'recognition':{'method':'whisper-base.en','requestedWordVerified':False,'endTokenId':50256,'generatedTokenCount':2,'selectedTokenPosteriors':[{'tokenId':100,'selectedLogProbability':-0.2}],'transcript':'thumb','meanTokenLogProbability':-0.2,
                'noSpeechProbability':0.1,'complete':True},'status':'recognized','reason':None,'runtime':{'elapsedSeconds':0.01,'peakRssKiB':100000,'workerExitCode':0,'timedOut':False,'acousticCalls':1}}
        def forbidden(request):raise AssertionError('Rejected recognition reached research bridge')
        result=assess(wav(),PROMPT,acoustic_worker=worker,research_bridge=forbidden)
        self.assertEqual(calls,[wav()])
        self.assertEqual(result['reason'],'requested_word_not_matched')
        self.assertIsNone(result['research'])

    def test_timeout_crash_and_invalid_capture_abstain_without_bridge(self):
        from admission.adapter import assess
        for failure in ('worker_timeout','worker_crash','model_unavailable'):
            def unavailable(raw):raise AdmissionError(failure)
            def forbidden(request):raise AssertionError('failed admission reached bridge')
            result=assess(wav(),PROMPT,acoustic_worker=unavailable,research_bridge=forbidden)
            self.assertEqual(result['status'],'unavailable')
            self.assertEqual(result['reason'],failure)
            self.assertIsNone(result['research'])
        def forbidden_worker(raw):raise AssertionError('malformed capture reached worker')
        result=assess(b'not-wav',PROMPT,acoustic_worker=forbidden_worker,research_bridge=forbidden)
        self.assertEqual(result['reason'],'invalid_audio')

    def test_admitted_research_uses_identical_audio_prompt_and_preserves_unverified_match(self):
        import base64,json,hashlib
        from admission.adapter import assess
        from consumer_assessment.bridge import canonical_bytes
        def worker(raw):
            return {'speechEvidence':{'method':'silero-vad','speechPresenceVerified':False,'passed':True,'positiveSamples':3200,'maximumConsecutivePositiveSamples':3200,'windowCount':7,'probabilities':[0.9]*7},
                'recognition':{'method':'whisper-base.en','requestedWordVerified':False,'endTokenId':50256,'generatedTokenCount':2,'selectedTokenPosteriors':[{'tokenId':100,'selectedLogProbability':-0.2}],'transcript':'Rabbit.','meanTokenLogProbability':-0.2,'noSpeechProbability':0.1,'complete':True},
                'status':'recognized','reason':None,'runtime':{'elapsedSeconds':0.01,'peakRssKiB':100000,'workerExitCode':0,'timedOut':False,'acousticCalls':1}}
        seen=[]
        def researcher(raw_request):
            request=json.loads(raw_request);seen.append(request)
            return {'outcome':'processed','promptMatch':'unverified','learnerFeedbackEligible':False,'clinicalUseEligible':False,'productionUseEligible':False,
                    'binding':{'audioSha256':hashlib.sha256(base64.b64decode(request['audioBase64'])).hexdigest(),
                    'promptSha256':hashlib.sha256(canonical_bytes(request['prompt'])).hexdigest(),'requestSha256':hashlib.sha256(raw_request).hexdigest()}}
        result=assess(wav(),PROMPT,acoustic_worker=worker,research_bridge=researcher)
        self.assertEqual(result['status'],'processed')
        self.assertEqual(seen[0]['prompt'],PROMPT)
        self.assertEqual(base64.b64decode(seen[0]['audioBase64']),wav())
        self.assertEqual(result['research']['promptMatch'],'unverified')
        self.assertNotIn('transcript',result['wordMatch'])

    def test_cached_recognition_cannot_be_rebound_to_different_audio_or_prompt_and_no_private_transcript_leaks(self):
        from admission.adapter import assess,recognize
        def worker(raw):
            return {'speechEvidence':{'method':'silero-vad','speechPresenceVerified':False,'passed':True,'positiveSamples':3200,'maximumConsecutivePositiveSamples':3200,'windowCount':7,'probabilities':[0.9]*7},
                'recognition':{'method':'whisper-base.en','requestedWordVerified':False,'endTokenId':50256,'generatedTokenCount':2,'selectedTokenPosteriors':[{'tokenId':100,'selectedLogProbability':-0.2}],'transcript':'rabbit','meanTokenLogProbability':-0.2,'noSpeechProbability':0.1,'complete':True},
                'status':'recognized','reason':None,'runtime':{'elapsedSeconds':0.01,'peakRssKiB':100000,'workerExitCode':0,'timedOut':False,'acousticCalls':1}}
        evidence=recognize(wav(),acoustic_worker=worker)
        def forbidden(request):raise AssertionError('drift reached bridge')
        result=assess(wav()[:-2]+b'\x01\x00',PROMPT,recognition_evidence=evidence,research_bridge=forbidden)
        self.assertEqual(result['reason'],'recognition_binding_failed')
        self.assertIsNone(result['research'])
        def changed_binding(request):return {'outcome':'processed','binding':{},'promptMatch':'unverified'}
        result=assess(wav(),PROMPT,recognition_evidence=evidence,research_bridge=changed_binding)
        self.assertEqual(result['reason'],'research_binding_failed')
        self.assertIsNone(result['research'])
        self.assertNotIn('selectedTokenPosteriors',str(result))
        self.assertNotIn('transcript',str(result))

    def test_invalid_harness_age_and_unsupported_target_cannot_execute_worker(self):
        from copy import deepcopy
        from admission.adapter import assess
        def forbidden(raw):raise AssertionError('invalid prompt reached worker')
        for age in (True,5,13):
            self.assertEqual(assess(wav(),PROMPT,age,acoustic_worker=forbidden)['status'],'unavailable')
        prompt=deepcopy(PROMPT);prompt['targets'][0]['targetPhone']='ZH'
        self.assertEqual(assess(wav(),prompt,acoustic_worker=forbidden)['reason'],'unsupported_target')
