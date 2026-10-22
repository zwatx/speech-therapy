"""Predeclared engineering policy; no learner or phonetic correctness meaning."""
import hashlib,json,math,re,unicodedata
from copy import deepcopy

POLICY={'id':'offline-admission-v1','sampleRate':16000,'minimumSamples':1600,'maximumSamples':64000,
        'maximumBytes':132096,'minimumRms':0.001,'maximumRailSamples':0,
        'vadWindowSamples':512,'vadThreshold':0.5,'minimumPositiveSamples':2560,
        'minimumConsecutivePositiveSamples':1536,'minimumMeanTokenLogProbability':-0.8,
        'maximumNoSpeechProbability':0.6,'maxNewTokens':24,'workerTimeoutSeconds':60,
        'decoding':'greedy-one-beam-no-context-no-fallback','aliases':{'yo-yo':'yoyo','yoyo':'yoyo'}}
CLAIMS={key:False for key in ('speechPresenceVerified','requestedWordVerified','promptMatchingValidated',
 'intendedChildAccuracyEstablished','qualifiedApprovalEstablished','learnerFeedbackEligible',
 'clinicalUseEligible','productionUseEligible','authenticProvenanceEstablished')}

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
POLICY_SHA=digest(POLICY)

class AdmissionError(ValueError):
    def __init__(self,code):self.code=code;super().__init__(code)

def normalized_word(value):
    if type(value) is not str or len(value)>256:return None
    tokens=value.casefold().split()
    if len(tokens)!=1:return None
    token=tokens[0]
    while token and unicodedata.category(token[0]).startswith('P'):token=token[1:]
    while token and unicodedata.category(token[-1]).startswith('P'):token=token[:-1]
    if re.fullmatch(r'[a-z]+(?:-[a-z]+)*',token) is None:return None
    return POLICY['aliases'].get(token,token)

def finite(value,minimum=None,maximum=None):
    return type(value) in (int,float) and math.isfinite(value) and (minimum is None or value>=minimum) and (maximum is None or value<=maximum)

def exact(value,keys):
    return type(value) is dict and set(value)==set(keys)

def decide(evidence,expected_word):
    try:word_sha=digest(expected_word) if type(expected_word) is str else None
    except (ValueError,UnicodeError):word_sha=None
    result={'admitted':False,'reason':'invalid_evidence','expectedWordSha256':word_sha,
            'evidenceSha256':None,'policySha256':POLICY_SHA,'method':'independent-asr-single-word',
            'requestedWordVerified':False,'recognitionRejectionIsArticulationError':False}
    try:
        from .models import MODEL_MANIFEST_SHA
        if type(evidence) is not dict or set(evidence)!=set(('schemaVersion','status','reason','capture','speechEvidence','recognition','binding','runtime','claimLimits','evidenceSha256')):return result
        body={key:value for key,value in evidence.items() if key!='evidenceSha256'}
        if evidence['evidenceSha256']!=digest(body):return result
        binding=evidence['binding']
        if not exact(binding,('audioSha256','modelManifestSha256','policySha256')) or type(binding['audioSha256']) is not str or re.fullmatch('[0-9a-f]{64}',binding['audioSha256']) is None:return result
        if (type(evidence['schemaVersion']) is not int or evidence['schemaVersion']!=1 or evidence['claimLimits']!=CLAIMS
            or binding['policySha256']!=POLICY_SHA or binding['modelManifestSha256']!=MODEL_MANIFEST_SHA
            or binding['audioSha256']!=evidence['capture']['audioSha256']):return result
        result['evidenceSha256']=evidence['evidenceSha256']
        if evidence['status']!='recognized':
            result['reason']=evidence['reason'] if evidence['reason'] in ('invalid_audio','silence','clipping','speech_not_detected','worker_timeout','worker_crash','model_unavailable','recognition_failed') else 'recognition_failed'
            return result
        capture=evidence['capture']
        if not exact(capture,('audioSha256','valid','metrics')):return result
        speech=evidence['speechEvidence'];metrics=capture['metrics']
        if not exact(metrics,('sampleCount','durationMilliseconds','rms','peak','railSamples')):return result
        if (not finite(metrics['durationMilliseconds'],100,4000) or not finite(metrics['rms'],POLICY['minimumRms'],1)
            or not finite(metrics['peak'],0,1) or metrics['rms']>metrics['peak']
            or type(metrics['railSamples']) is not int or metrics['railSamples']!=0):return result
        if not exact(speech,('method','passed','positiveSamples','maximumConsecutivePositiveSamples','windowCount','probabilities','speechPresenceVerified')) or speech['method']!='silero-vad' or speech['speechPresenceVerified'] is not False:return result
        sample_count=metrics['sampleCount']
        if type(sample_count) is not int or not 1600<=sample_count<=64000 or evidence['capture']['valid'] is not True:return result
        if metrics['durationMilliseconds']!=sample_count/16:return result
        probabilities=speech['probabilities']
        if type(probabilities) is not list or len(probabilities)!=(sample_count+511)//512 or any(not finite(p,0,1) for p in probabilities):return result
        positive=consecutive=maximum=0
        for index,probability in enumerate(probabilities):
            count=min(512,sample_count-index*512)
            if probability>=POLICY['vadThreshold']:
                positive+=count;consecutive+=count;maximum=max(maximum,consecutive)
            else:consecutive=0
        passed=positive>=POLICY['minimumPositiveSamples'] and maximum>=POLICY['minimumConsecutivePositiveSamples']
        if any(type(speech[key]) is not int for key in ('positiveSamples','maximumConsecutivePositiveSamples','windowCount')) or speech['positiveSamples']!=positive or speech['maximumConsecutivePositiveSamples']!=maximum or speech['windowCount']!=len(probabilities) or speech['passed'] is not passed:return result
        if not passed:
            result['reason']='speech_not_detected';return result
        if evidence['reason'] is not None:return result
        recognition=evidence['recognition']
        if not exact(recognition,('method','transcript','meanTokenLogProbability','noSpeechProbability','complete','endTokenId','generatedTokenCount','selectedTokenPosteriors','requestedWordVerified')) or recognition['method']!='whisper-base.en' or recognition['requestedWordVerified'] is not False:return result
        count=recognition['generatedTokenCount'];posteriors=recognition['selectedTokenPosteriors']
        if type(count) is not int or not 2<=count<=POLICY['maxNewTokens'] or type(posteriors) is not list or len(posteriors)!=count-1:return result
        for token in posteriors:
            if not exact(token,('tokenId','selectedLogProbability')) or type(token['tokenId']) is not int or not 0<=token['tokenId']<50256 or not finite(token['selectedLogProbability'],-100,0):return result
        recomputed=sum(token['selectedLogProbability'] for token in posteriors)/len(posteriors)
        if not finite(recognition['meanTokenLogProbability'],-100,0) or abs(recomputed-recognition['meanTokenLogProbability'])>1e-12:return result
        runtime=evidence['runtime']
        if (not exact(runtime,('elapsedSeconds','peakRssKiB','workerExitCode','timedOut','acousticCalls'))
            or not finite(runtime['elapsedSeconds'],0) or not finite(runtime['peakRssKiB'],0)
            or type(runtime['workerExitCode']) is not int or runtime['workerExitCode']!=0
            or runtime['timedOut'] is not False or type(runtime['acousticCalls']) is not int or runtime['acousticCalls']!=1):return result
        if (recognition['complete'] is not True or type(recognition['endTokenId']) is not int or recognition['endTokenId']!=50256 or not finite(recognition['meanTokenLogProbability'],-100,0)
            or not finite(recognition['noSpeechProbability'],0,1)):
            result['reason']='recognition_incomplete';return result
        if recognition['meanTokenLogProbability']<POLICY['minimumMeanTokenLogProbability'] or recognition['noSpeechProbability']>POLICY['maximumNoSpeechProbability']:
            result['reason']='recognition_uncertain';return result
        actual,expected=normalized_word(recognition['transcript']),normalized_word(expected_word)
        if actual is None or expected is None:
            result['reason']='single_word_required';return result
        if actual!=expected:
            result['reason']='requested_word_not_matched';return result
        result.update(admitted=True,reason=None)
        return result
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):return result
