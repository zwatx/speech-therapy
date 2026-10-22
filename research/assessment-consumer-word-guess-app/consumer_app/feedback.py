"""Bounded recording observations and independently validated recognition feedback."""
from copy import deepcopy
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from consumer_assessment import bridge
from admission import policy
from admission.models import MODEL_MANIFEST_SHA
from journey.catalog import PACK_SHA,PACK_PATH,read_owned
from mobile_admission import contract
from . import feedback_contract
from mobile_admission.service import Executor,block,save_runtime,PYTHON,TIMEOUT,ROOT
from mobile_admission.process import supervise

MODULE=Path(__file__).parent
CLAIMS={**contract.CLAIMS,'diagnosisProvided':False,'pronunciationCorrectnessAssessed':False}
FEEDBACK_POLICY={'id':'consumer-recording-feedback-word-guess-v1','rmsDbfsFloor':-120,
                 'metricMeaning':'digital-recording-properties','wordMeaning':'independent-model-recognition',
                 'targetAssessment':'not-performed','maximumSuggestions':3,
                 'requestSchemaVersion':feedback_contract.REQUEST_VERSION,
                 'practiceContexts':feedback_contract.PRACTICE_CONTEXTS,
                 'contextMeaning':'self-declared-practice-context',
                 'responseSchemaVersion':2,'nestedFeedbackSchemaVersion':1,
                 'responseKind':'recording_feedback_with_word_guess',
                 'wordGuessMeaning':'normalized-model-word-hypothesis',
                 'wordGuessProjection':'final-matched-or-mismatched-only-null-otherwise',
                 'normalizerPolicySha256':policy.POLICY_SHA}
FEEDBACK_POLICY_SHA=contract.sha(contract.canonical(FEEDBACK_POLICY))
SUGGESTIONS=frozenset(('record_again','review_recording','reduce_recording_level','listen_to_example',
                      'say_one_word','try_again','retry_later','processing_unavailable','continue_practice'))


def measure_recording(audio):
    metrics=bridge.capture(audio)
    return {**metrics,'rmsDbfs':max(-120,20*math.log10(metrics['rms'])) if metrics['rms'] else -120,
            'clippedFraction':metrics['railSamples']/metrics['sampleCount']}


WORD_FILES=frozenset(('__init__.py','__main__.py','catalog.py','feedback.py','feedback_contract.py','feedback_worker.py','server.py','visual_assets.py'))

def source_snapshot():
    if MODULE.resolve()!=ROOT/'research/assessment-consumer-word-guess-app/consumer_app' or {path.name for path in MODULE.glob('*.py')}!=WORD_FILES:
        raise ValueError('source_binding_failed')
    pins=contract.verify_sources()
    if pins['policySha256']!=policy.POLICY_SHA or pins['modelManifestSha256']!=MODEL_MANIFEST_SHA:
        raise ValueError('source_binding_failed')
    content=contract.strict_json(read_owned(PACK_PATH,1024*1024))
    if contract.sha(contract.canonical(content))!=PACK_SHA:raise ValueError('source_binding_failed')
    names=tuple(sorted(path.name for path in MODULE.glob('*.py')))
    hashes={name:contract.sha(read_owned(MODULE/name,256000)) for name in names}
    return {'pins':pins,'feedbackSourceSha256':contract.sha(contract.canonical({name:hashes[name] for name in ('feedback.py','feedback_worker.py')})),
            'wrapperSourceSha256':contract.sha(contract.canonical(hashes)),
            'feedbackPolicySha256':FEEDBACK_POLICY_SHA,'contentSha256':PACK_SHA}


def _need(condition):
    if not condition:raise ValueError('invalid_evidence')


def _exact(value,keys):return type(value) is dict and set(value)==set(keys)
def _finite(value,low=0,high=None):return type(value) in (int,float) and math.isfinite(value) and value>=low and (high is None or value<=high)


def validate_evidence(evidence,audio,metrics,pins):
    _need(_exact(evidence,('schemaVersion','status','reason','capture','speechEvidence','recognition','binding','runtime','claimLimits','evidenceSha256')))
    _need(type(evidence['schemaVersion']) is int and evidence['schemaVersion']==1)
    _need(evidence['evidenceSha256']==policy.digest({key:value for key,value in evidence.items() if key!='evidenceSha256'}))
    _need(_exact(evidence['claimLimits'],contract.CLAIMS) and all(value is False for value in evidence['claimLimits'].values()))
    _need(_exact(evidence['binding'],('audioSha256','modelManifestSha256','policySha256')))
    _need(evidence['binding']=={'audioSha256':contract.sha(audio),'modelManifestSha256':MODEL_MANIFEST_SHA,'policySha256':policy.POLICY_SHA})
    _need(pins['modelManifestSha256']==MODEL_MANIFEST_SHA and pins['policySha256']==policy.POLICY_SHA)
    capture=evidence['capture'];runtime=evidence['runtime']
    _need(_exact(capture,('audioSha256','valid','metrics')) and capture['audioSha256']==contract.sha(audio))
    _need(_exact(runtime,('elapsedSeconds','peakRssKiB','workerExitCode','timedOut','acousticCalls')))
    _need(_finite(runtime['elapsedSeconds'],0,85) and type(runtime['timedOut']) is bool and type(runtime['acousticCalls']) is int and runtime['acousticCalls'] in (0,1))
    if runtime['acousticCalls']==0:
        _need(runtime['peakRssKiB'] is None and runtime['workerExitCode'] is None and runtime['timedOut'] is False and runtime['elapsedSeconds']==0)
    else:
        _need(_finite(runtime['peakRssKiB']) and type(runtime['workerExitCode']) is int and -127<=runtime['workerExitCode']<=255)
    if metrics is None:
        _need(capture['valid'] is False and capture['metrics'] is None and evidence['status']=='unavailable' and evidence['reason']=='invalid_audio' and runtime['acousticCalls']==0)
    else:
        actual=capture['metrics'];base={key:metrics[key] for key in ('sampleCount','durationMilliseconds','rms','peak','railSamples')}
        _need(capture['valid'] is True and _exact(actual,base))
        _need(type(actual['sampleCount']) is int and type(actual['railSamples']) is int)
        _need(all(_finite(actual[key]) for key in ('durationMilliseconds','rms','peak')) and actual==base)
    speech=evidence['speechEvidence'];recognition=evidence['recognition']
    if evidence['status']=='unavailable' and evidence['reason'] in ('invalid_audio','silence','clipping'):
        _need(speech is None and recognition is None and runtime['acousticCalls']==0)
        if evidence['reason']=='invalid_audio':_need(metrics is None)
        if evidence['reason']=='silence':_need(metrics is not None and metrics['railSamples']==0 and metrics['rms']<policy.POLICY['minimumRms'])
        if evidence['reason']=='clipping':_need(metrics is not None and metrics['railSamples']>policy.POLICY['maximumRailSamples'])
        return
    _need(metrics is not None and metrics['railSamples']==0 and metrics['rms']>=policy.POLICY['minimumRms'] and runtime['acousticCalls']==1)
    if evidence['status']=='unavailable' and evidence['reason'] in ('worker_timeout','worker_crash','model_unavailable','recognition_failed'):
        _need(speech is None and recognition is None)
        if evidence['reason']=='worker_timeout':_need(runtime['timedOut'] is True)
        else:_need(runtime['timedOut'] is False)
        return
    _need(runtime['timedOut'] is False and runtime['workerExitCode']==0)
    _need(_exact(speech,('method','passed','positiveSamples','maximumConsecutivePositiveSamples','windowCount','probabilities','speechPresenceVerified')))
    _need(speech['method']=='silero-vad' and speech['speechPresenceVerified'] is False and type(speech['passed']) is bool)
    count=metrics['sampleCount'];probabilities=speech['probabilities']
    _need(type(probabilities) is list and len(probabilities)==(count+511)//512 and all(_finite(value,0,1) for value in probabilities))
    positive=consecutive=maximum=0
    for index,value in enumerate(probabilities):
        samples=min(512,count-index*512)
        if value>=policy.POLICY['vadThreshold']:positive+=samples;consecutive+=samples;maximum=max(maximum,consecutive)
        else:consecutive=0
    passed=positive>=policy.POLICY['minimumPositiveSamples'] and maximum>=policy.POLICY['minimumConsecutivePositiveSamples']
    _need(all(type(speech[key]) is int for key in ('positiveSamples','maximumConsecutivePositiveSamples','windowCount')))
    _need((speech['positiveSamples'],speech['maximumConsecutivePositiveSamples'],speech['windowCount'],speech['passed'])==(positive,maximum,len(probabilities),passed))
    if not passed:
        _need(evidence['status']=='unavailable' and evidence['reason']=='speech_not_detected' and recognition is None)
        return
    _need(evidence['status']=='recognized' and evidence['reason'] is None)
    _need(_exact(recognition,('method','transcript','meanTokenLogProbability','noSpeechProbability','complete','endTokenId','generatedTokenCount','selectedTokenPosteriors','requestedWordVerified')))
    _need(recognition['method']=='whisper-base.en' and recognition['requestedWordVerified'] is False)
    _need(type(recognition['transcript']) is str and len(recognition['transcript'])<=256)
    recognition['transcript'].encode('utf-8')
    _need(type(recognition['complete']) is bool and type(recognition['endTokenId']) is int and 0<=recognition['endTokenId']<51865)
    _need(recognition['complete'] is (recognition['endTokenId']==50256))
    _need(type(recognition['generatedTokenCount']) is int and 2<=recognition['generatedTokenCount']<=policy.POLICY['maxNewTokens'])
    posteriors=recognition['selectedTokenPosteriors']
    _need(type(posteriors) is list and len(posteriors)==recognition['generatedTokenCount']-1)
    for token in posteriors:
        _need(_exact(token,('tokenId','selectedLogProbability')) and type(token['tokenId']) is int and 0<=token['tokenId']<50256 and _finite(token['selectedLogProbability'],-100,0))
    if recognition['complete'] is False:
        _need(recognition['generatedTokenCount']==policy.POLICY['maxNewTokens'])
        if recognition['endTokenId']<50256:_need(posteriors[-1]['tokenId']==recognition['endTokenId'])
    _need(_finite(recognition['meanTokenLogProbability'],-100,0) and _finite(recognition['noSpeechProbability'],0,1))
    _need(abs(recognition['meanTokenLogProbability']-sum(token['selectedLogProbability'] for token in posteriors)/len(posteriors))<=1e-12)


def _project_base_feedback(raw,evidence,decision,snapshot,*,reason=None,elapsed_ms=0):
    request,audio=feedback_contract.prepare(raw)
    try:metrics=measure_recording(audio)
    except bridge.Unavailable:metrics=None
    stage_capture={'state':'unavailable','reason':'invalid_audio',**{key:None for key in ('sampleCount','durationMilliseconds','rms','rmsDbfs','peak','railSamples','clippedFraction')}}
    if metrics is not None:stage_capture={'state':'observed','reason':None,**metrics}
    speech={'state':'not_run' if reason in (None,'invalid_audio') else 'unavailable','reason':reason}
    word=dict(speech);evidence_sha=None
    if reason is None:
        try:
            validate_evidence(evidence,audio,metrics,snapshot['pins'])
            expected=policy.decide(evidence,request['prompt']['transcript'])
            _need(decision==expected and contract.canonical(decision)==contract.canonical(expected) and expected['reason']!='invalid_evidence')
            evidence_sha=evidence['evidenceSha256'];reason=expected['reason']
            if evidence['status']=='recognized':
                speech={'state':'model_detected','reason':None}
                state={'requested_word_not_matched':'model_not_matched','single_word_required':'not_single_word',
                       'recognition_uncertain':'uncertain','recognition_incomplete':'uncertain'}.get(reason,'model_matched' if expected['admitted'] is True else 'unavailable')
                word={'state':state,'reason':reason}
            elif reason=='speech_not_detected':
                speech={'state':'model_not_detected','reason':reason};word={'state':'not_run','reason':reason}
            elif reason in ('invalid_audio','silence','clipping'):
                speech={'state':'not_run','reason':reason};word=dict(speech)
            else:speech={'state':'unavailable','reason':reason};word=dict(speech)
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            reason='invalid_evidence';speech={'state':'unavailable','reason':reason};word=dict(speech)
    if reason=='cleanup_unconfirmed':
        stage_capture={**stage_capture,'state':'unavailable','reason':reason,**{key:None for key in ('sampleCount','durationMilliseconds','rms','rmsDbfs','peak','railSamples','clippedFraction')}}
        evidence_sha=None
    suggestions={'silence':['review_recording','record_again'],'clipping':['review_recording','reduce_recording_level'],
                 'speech_not_detected':['review_recording','record_again'],'requested_word_not_matched':['listen_to_example','try_again'],
                 'recognition_uncertain':['review_recording','try_again'],'recognition_incomplete':['review_recording','try_again'],
                 'single_word_required':['say_one_word','try_again'],'busy':['retry_later'],'invalid_audio':['record_again']}.get(reason,['continue_practice'] if word['state']=='model_matched' else ['processing_unavailable','retry_later'])
    status='observed' if reason in (None,'silence','clipping','speech_not_detected','requested_word_not_matched','recognition_uncertain','recognition_incomplete','single_word_required') else 'unavailable'
    pins=snapshot['pins']
    binding={'attemptId':request['attemptId'],'requestSha256':contract.sha(raw),'audioSha256':contract.sha(audio),
             'promptSha256':contract.sha(contract.canonical(request['prompt'])),'evidenceSha256':evidence_sha,
             **deepcopy(pins),
             **{key:snapshot[key] for key in ('feedbackSourceSha256','wrapperSourceSha256','feedbackPolicySha256','contentSha256')}}
    result={'schemaVersion':1,'kind':'recording_feedback','status':status,'reason':reason,
            'stages':{'capture':stage_capture,'speech':speech,'word':word},'targetAssessment':{'state':'unsupported','reason':'unsupported_target'} if any(target['targetPhone']=='ZH' for target in request['prompt']['targets']) else {'state':'not_performed','reason':'not_validated'},
            'suggestionCodes':suggestions,'binding':binding,'claimLimits':dict(CLAIMS),'elapsedMilliseconds':elapsed_ms}
    _need(_finite(elapsed_ms) and len(contract.canonical(result))<=contract.MAX_RESPONSE)
    return deepcopy(result)


def _validate_base_response(value,raw,snapshot):
    baseline=_project_base_feedback(raw,None,None,snapshot,reason='assessment_failed')
    _need(_exact(value,baseline) and type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['kind']=='recording_feedback')
    _need(_exact(value['claimLimits'],CLAIMS) and all(flag is False for flag in value['claimLimits'].values()))
    _need(value['targetAssessment']==baseline['targetAssessment'] and _exact(value['targetAssessment'],('state','reason')))
    _need(_finite(value['elapsedMilliseconds']) and value['status'] in ('observed','unavailable'))
    _need(_exact(value['binding'],baseline['binding']))
    expected=baseline['binding'];evidence_sha=value['binding']['evidenceSha256']
    _need(evidence_sha is None or type(evidence_sha) is str and re.fullmatch('[0-9a-f]{64}',evidence_sha) is not None)
    expected['evidenceSha256']=evidence_sha
    _need(value['binding']==expected)
    _need(_exact(value['stages'],('capture','speech','word')))
    capture=value['stages']['capture'];speech=value['stages']['speech'];word=value['stages']['word']
    _need(_exact(capture,baseline['stages']['capture']) and _exact(speech,('state','reason')) and _exact(word,('state','reason')))
    if capture['state']=='observed':_need(contract.canonical(capture)==contract.canonical(baseline['stages']['capture']))
    else:
        _need(capture['state']=='unavailable' and capture['reason'] in ('invalid_audio','cleanup_unconfirmed'))
        _need(all(capture[key] is None for key in capture if key not in ('state','reason')))
        if capture['reason']=='invalid_audio':_need(baseline['stages']['capture']['state']=='unavailable')
    known_reasons=set(contract.REASONS)|{'invalid_evidence'}
    _need(value['reason'] is None or type(value['reason']) is str and value['reason'] in known_reasons)
    _need(all(stage['reason'] is None or type(stage['reason']) is str and stage['reason'] in known_reasons for stage in (speech,word)))
    _need(speech['state'] in ('model_detected','model_not_detected','not_run','unavailable'))
    _need(word['state'] in ('model_matched','model_not_matched','uncertain','not_single_word','not_run','unavailable'))
    if word['state'] in ('model_matched','model_not_matched','uncertain','not_single_word'):
        _need(value['status']=='observed' and speech=={'state':'model_detected','reason':None} and evidence_sha is not None and capture['state']=='observed')
        reasons={'model_matched':(None,),'model_not_matched':('requested_word_not_matched',),
                 'uncertain':('recognition_uncertain','recognition_incomplete'),'not_single_word':('single_word_required',)}
        _need(word['reason'] in reasons[word['state']] and value['reason']==word['reason'])
    if speech['state']=='model_not_detected':_need(value['status']=='observed' and evidence_sha is not None and speech['reason']=='speech_not_detected' and word=={'state':'not_run','reason':'speech_not_detected'})
    if value['status']=='unavailable':_need(speech['state']=='unavailable' and word['state']=='unavailable' or value['reason']=='invalid_audio' and speech['state']=='not_run' and word['state']=='not_run')
    # Validate the complete stage tuple, rather than independent permissive
    # state checks that could turn an operational failure into an observation.
    reason=value['reason']
    lexical={None:'model_matched','requested_word_not_matched':'model_not_matched',
             'recognition_uncertain':'uncertain','recognition_incomplete':'uncertain','single_word_required':'not_single_word'}
    if reason in lexical:
        _need(value['status']=='observed' and capture['state']=='observed' and evidence_sha is not None)
        _need(speech=={'state':'model_detected','reason':None} and word=={'state':lexical[reason],'reason':reason})
    elif reason=='speech_not_detected':
        _need(value['status']=='observed' and capture['state']=='observed' and evidence_sha is not None)
        _need(speech=={'state':'model_not_detected','reason':reason} and word=={'state':'not_run','reason':reason})
    elif reason in ('silence','clipping'):
        _need(value['status']=='observed' and capture['state']=='observed' and evidence_sha is not None)
        _need(speech=={'state':'not_run','reason':reason} and word==speech)
        if reason=='silence':_need(capture['railSamples']==0 and capture['rms']<policy.POLICY['minimumRms'])
        else:_need(capture['railSamples']>0)
    elif reason=='invalid_audio':
        _need(value['status']=='unavailable' and capture['state']=='unavailable' and capture['reason']==reason)
        _need(speech=={'state':'not_run','reason':reason} and word==speech)
    else:
        _need(value['status']=='unavailable' and speech=={'state':'unavailable','reason':reason} and word==speech)
    if reason=='cleanup_unconfirmed':
        _need(capture['state']=='unavailable' and capture['reason']==reason and evidence_sha is None)
    if reason in ('busy','timeout','source_binding_failed','assessment_failed','invalid_evidence'):_need(evidence_sha is None)
    suggestions=value['suggestionCodes']
    _need(type(suggestions) is list and 1<=len(suggestions)<=3 and all(type(code) is str and code in SUGGESTIONS for code in suggestions) and len(suggestions)==len(set(suggestions)))
    _need(len(contract.canonical(value))<=contract.MAX_RESPONSE)
    return deepcopy(value)


RESPONSE_KIND='recording_feedback_with_word_guess'

def _valid_guess(value):
    return type(value) is str and 1<=len(value)<=256 and re.fullmatch('[a-z]+(?:-[a-z]+)*',value) is not None and policy.normalized_word(value)==value

def project_feedback(raw,evidence,decision,snapshot,*,reason=None,elapsed_ms=0):
    """Project one final model token, never a guessed transcript from the prompt."""
    base=_project_base_feedback(raw,evidence,decision,snapshot,reason=reason,elapsed_ms=elapsed_ms)
    guess=None
    if base['stages']['word']['state'] in ('model_matched','model_not_matched'):
        try:
            request,audio=feedback_contract.prepare(raw)
            validate_evidence(evidence,audio,measure_recording(audio),snapshot['pins'])
            expected=policy.decide(evidence,request['prompt']['transcript'])
            _need(contract.canonical(decision)==contract.canonical(expected))
            guess=policy.normalized_word(evidence['recognition']['transcript'])
            _need(_valid_guess(guess))
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            base=_project_base_feedback(raw,None,None,snapshot,reason='invalid_evidence',elapsed_ms=elapsed_ms)
            guess=None
    return validate_response({'schemaVersion':2,'kind':RESPONSE_KIND,'feedback':base,'wordGuess':guess},raw,snapshot)

def validate_response(value,raw,snapshot):
    _need(_exact(value,('schemaVersion','kind','feedback','wordGuess'))
          and type(value['schemaVersion']) is int and value['schemaVersion']==2 and value['kind']==RESPONSE_KIND)
    base=_validate_base_response(value['feedback'],raw,snapshot)
    state=base['stages']['word']['state'];guess=value['wordGuess']
    if state in ('model_matched','model_not_matched'):
        request,_=feedback_contract.prepare(raw)
        expected=policy.normalized_word(request['prompt']['transcript'])
        _need(_valid_guess(guess) and expected is not None)
        _need((guess==expected) is (state=='model_matched'))
    else:_need(guess is None)
    _need(len(contract.canonical(value))<=min(contract.MAX_RESPONSE,16000))
    return deepcopy(value)


class FeedbackExecutor(Executor):
    """Uses the reviewed shared owner/slot/latch; exposes only word-guess feedback."""
    def __init__(self,runtime=None):
        if runtime is None:raise ValueError('explicit_successor_runtime_required')
        self.declared_snapshot=source_snapshot()
        super().__init__(runtime)

    def feedback_declaration(self,csrf_token):
        try:available=source_snapshot()==self.declared_snapshot and not self.is_blocked()
        except (ValueError,OSError):available=False
        snap=self.declared_snapshot
        return {'schemaVersion':2,'csrfToken':csrf_token,'pins':deepcopy(snap['pins']),
                'feedbackPolicy':{'id':FEEDBACK_POLICY['id'],'sha256':FEEDBACK_POLICY_SHA},
                **{key:snap[key] for key in ('feedbackSourceSha256','wrapperSourceSha256','contentSha256')},
                'processingAvailable':available}

    def execute_feedback(self,raw):
        feedback_contract.prepare(raw)
        if not self.slot.acquire(blocking=False):
            return project_feedback(raw,None,None,self.declared_snapshot,reason='busy')
        try:return self._execute_feedback_locked(raw)
        finally:self.slot.release()

    def _execute_feedback_locked(self,raw):
        started=time.monotonic();snapshot=self.declared_snapshot;evidence=decision=None;reason=None
        stage=None;cleanup_confirmed=False
        try:
            if self.is_blocked():reason='cleanup_unconfirmed'
            elif source_snapshot()!=snapshot:reason='source_binding_failed'
            else:
                stage=Path(tempfile.mkdtemp(prefix='attempt-',dir=self.runtime))
                block(self.runtime,'cleanup-required')
                paths=('research/assessment-mobile-admission','research/assessment-admission',
                       'research/assessment-desktop-journey','research/assessment-reference-assets','research/assessment-recording-access',
                       'research/assessment-review-service','research/assessment-workbench','research/audio-head')
                env={**os.environ,'PYTHONPATH':':'.join([str(MODULE.parent),*(str(ROOT/path) for path in paths)]),'TMPDIR':str(stage),
                     'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2'}
                runtime=supervise([str(PYTHON),'-m','consumer_app.feedback_worker',str(stage)],raw,
                                  cwd=ROOT,env=env,timeout_seconds=TIMEOUT)
                cleanup_confirmed=runtime.get('cleanupConfirmed') is True
                save_runtime(self.runtime,runtime)
                if not cleanup_confirmed:self.mark_blocked();reason='cleanup_unconfirmed'
                elif runtime.get('supervisionFailed') is True or runtime.get('cleanupFailurePhase') is not None:reason='assessment_failed'
                elif runtime['timedOut']:reason='timeout'
                elif runtime['workerExitCode']!=0:reason='assessment_failed'
                else:
                    from admission.models import private_read
                    result=contract.strict_json(private_read(stage/'feedback.json',100000))
                    _need(_exact(result,('schemaVersion','requestSha256','binding','evidence','decision')) and type(result['schemaVersion']) is int and result['schemaVersion']==1)
                    _need(result['binding']==snapshot and result['requestSha256']==contract.sha(raw))
                    evidence,decision=result['evidence'],result['decision']
        except (OSError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            if stage is not None and not cleanup_confirmed:self.mark_blocked();reason='cleanup_unconfirmed'
            else:reason='assessment_failed'
        finally:
            if stage is not None:
                if cleanup_confirmed:
                    try:
                        shutil.rmtree(stage);(self.runtime/'cleanup-required').unlink()
                        fd=os.open(self.runtime,os.O_RDONLY)
                        try:os.fsync(fd)
                        finally:os.close(fd)
                    except OSError:self.mark_blocked()
                else:self.mark_blocked()
                if self.is_blocked():reason='cleanup_unconfirmed';evidence=decision=None
        # No affirmative state can escape a late source change or cleanup failure.
        if reason!='cleanup_unconfirmed':
            try:
                if source_snapshot()!=snapshot:reason='source_binding_failed';evidence=decision=None
            except (OSError,ValueError):reason='source_binding_failed';evidence=decision=None
        result=project_feedback(raw,evidence,decision,snapshot,reason=reason,elapsed_ms=(time.monotonic()-started)*1000)
        return validate_response(result,raw,snapshot)
