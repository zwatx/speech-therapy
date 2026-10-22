import unittest

class PolicyTests(unittest.TestCase):
    def test_exact_single_word_allows_only_declared_yoyo_alias_and_rejects_extra_repetition(self):
        from admission import decide
        from admission.policy import CLAIMS,POLICY_SHA,digest
        from admission.models import MODEL_MANIFEST_SHA
        evidence={'schemaVersion':1,'runtime':{'elapsedSeconds':0.01,'peakRssKiB':100000,'workerExitCode':0,'timedOut':False,'acousticCalls':1},'claimLimits':dict(CLAIMS),'status':'recognized','reason':None,
                  'capture':{'audioSha256':'a'*64,'valid':True,'metrics':{'sampleCount':3200,'durationMilliseconds':200,'rms':0.03,'peak':0.04,'railSamples':0}},'speechEvidence':{'method':'silero-vad','speechPresenceVerified':False,'passed':True,'positiveSamples':3200,'maximumConsecutivePositiveSamples':3200,'windowCount':7,'probabilities':[0.9]*7},
                  'recognition':{'method':'whisper-base.en','requestedWordVerified':False,'endTokenId':50256,'generatedTokenCount':2,'selectedTokenPosteriors':[{'tokenId':100,'selectedLogProbability':-0.2}],'transcript':'Yo-yo.','meanTokenLogProbability':-0.2,'noSpeechProbability':0.1,'complete':True},
                  'binding':{'audioSha256':'a'*64,'modelManifestSha256':MODEL_MANIFEST_SHA,'policySha256':POLICY_SHA}}
        def seal():
            evidence['evidenceSha256']=digest({k:v for k,v in evidence.items() if k!='evidenceSha256'})
        seal()
        self.assertTrue(decide(evidence,'yoyo')['admitted'])
        evidence['recognition']['transcript']='banana banana'
        seal()
        self.assertFalse(decide(evidence,'banana')['admitted'])
        evidence['recognition']['transcript']='please banana'
        seal()
        self.assertFalse(decide(evidence,'banana')['admitted'])
        evidence['recognition']['transcript']='thumb'
        seal()
        self.assertFalse(decide(evidence,'rabbit')['admitted'])

    def test_uncertainty_truncation_and_evidence_drift_abstain(self):
        from copy import deepcopy
        from admission.adapter import recognize
        from admission import decide
        from admission.policy import digest
        from test_adapter import wav
        def worker(raw):
            return {'speechEvidence':{'method':'silero-vad','speechPresenceVerified':False,'passed':True,'positiveSamples':3200,'maximumConsecutivePositiveSamples':3200,'windowCount':7,'probabilities':[0.9]*7},
              'recognition':{'method':'whisper-base.en','requestedWordVerified':False,'endTokenId':50256,'generatedTokenCount':2,'selectedTokenPosteriors':[{'tokenId':100,'selectedLogProbability':-0.2}],'transcript':'rabbit','meanTokenLogProbability':-0.2,'noSpeechProbability':0.1,'complete':True},'status':'recognized','reason':None,'runtime':{'elapsedSeconds':0.01,'peakRssKiB':100000,'workerExitCode':0,'timedOut':False,'acousticCalls':1}}
        original=recognize(wav(),acoustic_worker=worker)
        for key,value in (('complete',False),('meanTokenLogProbability',-0.81),('noSpeechProbability',0.61),('meanTokenLogProbability',True)):
            changed=deepcopy(original);changed['recognition'][key]=value
            changed['evidenceSha256']=digest({k:v for k,v in changed.items() if k!='evidenceSha256'})
            with self.subTest(key=key):self.assertFalse(decide(changed,'rabbit')['admitted'])
        changed=deepcopy(original);changed['recognition']['transcript']='thumb'
        self.assertEqual(decide(changed,'rabbit')['reason'],'invalid_evidence')
        changed=deepcopy(original);changed['speechEvidence']['positiveSamples']=0
        changed['evidenceSha256']=digest({k:v for k,v in changed.items() if k!='evidenceSha256'})
        self.assertFalse(decide(changed,'rabbit')['admitted'])

    def test_punctuation_does_not_hide_numbers_extra_words_or_undeclared_aliases(self):
        from admission.policy import normalized_word
        self.assertEqual(normalized_word('Rabbit!'),'rabbit')
        self.assertEqual(normalized_word('yo-yo.'),'yoyo')
        for text in ('rabbit 2','rabbit2','yo yo','rabbit,rabbit','rabbit rabbit','please rabbit'):
            with self.subTest(text=text):self.assertIsNone(normalized_word(text))

    def test_rehashed_capture_and_token_aggregate_contradictions_never_admit(self):
        from copy import deepcopy
        from admission import decide
        from admission.adapter import recognize
        from admission.policy import digest
        from test_adapter import wav
        def worker(raw):
            return {'speechEvidence':{'method':'silero-vad','speechPresenceVerified':False,'passed':True,'positiveSamples':3200,'maximumConsecutivePositiveSamples':3200,'windowCount':7,'probabilities':[0.9]*7},
              'recognition':{'method':'whisper-base.en','requestedWordVerified':False,'endTokenId':50256,'generatedTokenCount':2,'selectedTokenPosteriors':[{'tokenId':100,'selectedLogProbability':-0.2}],'transcript':'rabbit','meanTokenLogProbability':-0.2,'noSpeechProbability':0.1,'complete':True},'status':'recognized','reason':None,'runtime':{'elapsedSeconds':0.01,'peakRssKiB':100000,'workerExitCode':0,'timedOut':False,'acousticCalls':1}}
        original=recognize(wav(),acoustic_worker=worker)
        for field,value in (('rms',0),('railSamples',1)):
            changed=deepcopy(original);changed['capture']['metrics'][field]=value
            changed['evidenceSha256']=digest({k:v for k,v in changed.items() if k!='evidenceSha256'})
            with self.subTest(field=field):self.assertFalse(decide(changed,'rabbit')['admitted'])
        changed=deepcopy(original)
        changed['recognition']['selectedTokenPosteriors']=[{'tokenId':100,'selectedLogProbability':-3.0}]
        changed['evidenceSha256']=digest({k:v for k,v in changed.items() if k!='evidenceSha256'})
        self.assertFalse(decide(changed,'rabbit')['admitted'])
