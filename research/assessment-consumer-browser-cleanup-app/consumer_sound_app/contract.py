"""Closed sound-preview wire boundary and private-to-public projection."""
import base64
from copy import deepcopy
import hashlib
import json
import re

PURPOSE='adult-development-preview'
KIND='engineering_sound_observation'
MAX_BODY=200000
MAX_RESPONSE=12000
CLAIMS={key:False for key in ('calibrationValidated','pronunciationCorrectnessAssessed','diagnosisProvided',
    'childAccuracyEstablished','learnerFeedbackEligible','clinicalUseEligible','productionUseEligible')}
PIN_KEYS=('admissionSourceSha256','bridgeSourceSha256','serviceSourceSha256','supervisorSourceSha256','policySha256','modelManifestSha256')
SOURCE_KEYS=('featureSourceSha256','workerSourceSha256','workerReceiptSha256','runtimePinsSha256','contrastSpecSha256',
    'modelFileSha256','vocabularyFileSha256','promptSha256','resourcePolicySha256')
OWNER_KEYS=('sessionId','generation','roundId','roundKind','itemId','takeId','captureId','contextSha256')
POLICY={'id':'adult-development-sound-preview-v1','purpose':PURPOSE,'promptId':'r-middle-bread','practiceMode':'free',
    'minimumSamples':2400,'maximumSamples':64000,'maximumClaims':128,'maximumContexts':8,'encoderInput':'bytes-only',
    'projection':'uncalibrated-model-preference-no-numeric-diagnostics','claimLimits':CLAIMS}
UNAVAILABLE=frozenset(('busy','cancelled','timeout','cleanup_unconfirmed','source_binding_failed','stale_ownership',
    'worker_unavailable','invalid_evidence','capture_already_checked','attempt_already_checked','attempt_limit','context_limit','processing_unavailable'))
WORKER_NULL={'binding_mismatch':'unavailable','invalid_frames':'unavailable','frame_limit':'unavailable','numerical_mass_invalid':'unavailable','insufficient_frames':'inconclusive'}
INCONCLUSIVE=frozenset(('insufficient_frames','zero_candidate_mass','candidate_tie','uncovered_mass_dominates','greedy_tie','decoded_context_outside_candidates','decoded_path_disagreement'))

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def exact(value,keys):return type(value) is dict and set(value)==set(keys)
def need(condition,reason='invalid_request'):
    if not condition:raise ValueError(reason)
def hex64(value):return type(value) is str and bool(re.fullmatch('[a-f0-9]{64}',value))
def uuid(value):return type(value) is str and bool(re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}',value))
def strict_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate_key')
            result[key]=value
        return result
    try:return json.loads(raw.decode('utf8'),object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    except RecursionError:raise ValueError('invalid_json_depth') from None
def false_claims(value):return exact(value,CLAIMS) and all(type(flag) is bool and flag is False for flag in value.values())

def valid_binding(value):
    return (exact(value,('sources','wordBinding')) and exact(value['sources'],SOURCE_KEYS)
        and all(hex64(v) for v in value['sources'].values())
        and exact(value['wordBinding'],('pins','feedbackSourceSha256','wrapperSourceSha256','feedbackPolicySha256','contentSha256'))
        and exact(value['wordBinding']['pins'],PIN_KEYS)
        and all(hex64(v) for v in value['wordBinding']['pins'].values())
        and all(hex64(value['wordBinding'][key]) for key in ('feedbackSourceSha256','wrapperSourceSha256','feedbackPolicySha256','contentSha256')))

def validate_declaration(value):
    need(exact(value,('schemaVersion','kind','purpose','serverNonce','csrfToken','binding','policy','processingAvailable','claimLimits')))
    need(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['kind']==KIND and value['purpose']==PURPOSE
        and uuid(value['serverNonce']) and hex64(value['csrfToken']) and valid_binding(value['binding'])
        and canonical(value['policy'])==canonical(POLICY) and type(value['processingAvailable']) is bool and false_claims(value['claimLimits']))
    return deepcopy(value)

def valid_expected(value,worker=None):
    if not exact(value,('attemptId','requestSha256','workerRequestSha256','ownership','audio','source')):return False
    audio=value['audio'];owner=value['ownership']
    return (uuid(value['attemptId']) and hex64(value['requestSha256']) and hex64(value['workerRequestSha256'])
        and exact(owner,OWNER_KEYS) and all(type(owner[k]) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}',owner[k]) for k in ('sessionId','roundId','takeId','captureId'))
        and type(owner['generation']) is int and 1<=owner['generation']<=2147483647 and owner['itemId']=='r-middle-bread' and hex64(owner['contextSha256']) and (worker is None or worker.valid_owner(owner)) and owner['roundKind']=='probe'
        and exact(audio,('sha256','bytes','sampleCount','sampleRateHertz')) and hex64(audio['sha256'])
        and type(audio['sampleCount']) is int and 2400<=audio['sampleCount']<=64000
        and type(audio['bytes']) is int and audio['bytes']==44+audio['sampleCount']*2
        and type(audio['sampleRateHertz']) is int and audio['sampleRateHertz']==16000 and valid_binding(value['source']))

def context_payload(request,declaration):
    return {'schemaVersion':1,'serverNonce':declaration['serverNonce'],'purpose':PURPOSE,'adultConfirmed':True,'optIn':True,
        'practiceMode':'free','selectedChildAge':None,'setupGeneration':request['setupGeneration'],
        'sessionId':request['ownership']['sessionId'],'generation':request['ownership']['generation'],
        'promptId':request['promptId'],'promptSha256':sha(canonical(request['prompt'])),'binding':declaration['binding']}

def prepare(raw,declaration,worker,catalog):
    validate_declaration(declaration)
    need(type(raw) is bytes and 0<len(raw)<=MAX_BODY)
    request=strict_json(raw)
    need(exact(request,('schemaVersion','attemptId','purpose','adultConfirmed','optIn','practiceMode','selectedChildAge',
        'setupGeneration','serverNonce','promptId','prompt','ownership','audio','audioBase64','binding')))
    need(type(request['schemaVersion']) is int and request['schemaVersion']==1 and uuid(request['attemptId']))
    need(request['purpose']==PURPOSE and request['adultConfirmed'] is True and request['optIn'] is True
        and request['practiceMode']=='free' and request['selectedChildAge'] is None)
    need(type(request['setupGeneration']) is int and 0<=request['setupGeneration']<=2147483647)
    need(request['serverNonce']==declaration['serverNonce'] and canonical(request['binding'])==canonical(declaration['binding']),'source_binding_failed')
    owner=request['ownership'];need(worker.valid_owner(owner) and owner['roundKind']=='probe')
    need(type(request['promptId']) is str and type(request['prompt']) is dict and catalog.accepts(request['prompt']))
    supported=request['promptId']=='r-middle-bread' and sha(canonical(request['prompt']))==worker.binding()['promptSha256']
    need(owner['itemId']=='r-middle-bread')
    need(owner['contextSha256']==sha(canonical(context_payload(request,declaration))),'stale_ownership')
    need(type(request['audioBase64']) is str and len(request['audioBase64'])<=170728)
    audio=base64.b64decode(request['audioBase64'],validate=True)
    descriptor=worker.descriptor(audio)
    need(exact(request['audio'],('sha256','bytes','sampleCount','sampleRateHertz')) and canonical(request['audio'])==canonical({key:descriptor[key] for key in request['audio']}),'invalid_audio')
    private_request={'schemaVersion':1,'ownership':deepcopy(owner),'audio':descriptor,'contrast':worker.binding(),
        'sourceSnapshotSha256':declaration['binding']['sources']['workerSourceSha256']}
    private_hash=worker.digest(worker.canonical(private_request).encode())
    expected={'attemptId':request['attemptId'],'requestSha256':sha(raw),'workerRequestSha256':private_hash,
        'ownership':deepcopy(owner),'audio':deepcopy(request['audio']),'source':deepcopy(declaration['binding'])}
    return request,audio,private_request,expected,supported

def response(expected,status,reason,preference=None):
    value={'schemaVersion':1,'kind':KIND,'purpose':PURPOSE,'status':status,'reason':reason,'modelPreference':preference,
        'binding':deepcopy(expected),'claimLimits':dict(CLAIMS)}
    return validate_response(value,expected)

def validate_response(value,expected):
    need(valid_expected(expected),'invalid_response')
    need(exact(value,('schemaVersion','kind','purpose','status','reason','modelPreference','binding','claimLimits')),'invalid_response')
    need(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['kind']==KIND and value['purpose']==PURPOSE
        and canonical(value['binding'])==canonical(expected) and false_claims(value['claimLimits']),'invalid_response')
    status,reason,preference=value['status'],value['reason'],value['modelPreference']
    need(type(status) is str and type(reason) is str,'invalid_response')
    if status=='observed_model_preference':need(reason=='model_preferred_candidate' and preference in ('r_path','w_path','other_path'),'invalid_response')
    elif status=='inconclusive':need(reason in INCONCLUSIVE and preference is None,'invalid_response')
    elif status=='unsupported':need(reason=='unsupported_prompt' and preference is None,'invalid_response')
    elif status=='unavailable':need(reason in (*UNAVAILABLE,*[key for key,state in WORKER_NULL.items() if state=='unavailable']) and preference is None,'invalid_response')
    else:raise ValueError('invalid_response')
    need(len(canonical(value))<=MAX_RESPONSE,'invalid_response')
    return deepcopy(value)

def project_worker(outcome,private_request,expected,worker,diagnostic):
    need(exact(outcome,('status','cleanupConfirmed','result','supervisionDiagnostic')) and outcome['status']=='observed' and outcome['cleanupConfirmed'] is True,'invalid_evidence')
    request_hash=worker.digest(worker.canonical(private_request).encode())
    result=worker.validate_result(outcome['result'],private_request,request_hash)
    worker.validate_supervision_diagnostic(diagnostic,private_request,request_hash)
    need(diagnostic['cleanupConfirmed'] is True and diagnostic['workerExitCode']==0 and diagnostic['timedOut'] is False
        and diagnostic['cancelled'] is False and diagnostic['supervisionFailed'] is False,'invalid_evidence')
    reference=outcome['supervisionDiagnostic'];need(exact(reference,('path','sha256','requestSha256')) and reference['requestSha256']==request_hash
        and reference['sha256']==sha(worker.canonical(diagnostic).encode()),'invalid_evidence')
    observation=result['observation']
    # Numeric scores/posteriors/decoded phones/process identities never enter this projection.
    return response(expected,observation['status'],observation['reason'],observation['modelPreference'])
