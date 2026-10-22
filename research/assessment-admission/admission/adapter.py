"""Independent byte-only recognition precedes the frozen research bridge."""
import base64,hashlib,json,math,os,resource,select,signal,subprocess,sys,tempfile,time,uuid
from copy import deepcopy
from pathlib import Path
from consumer_assessment import bridge
from .process import supervise
from .models import ROOT,MODEL_MANIFEST_SHA,private_read,readiness
from .policy import AdmissionError,CLAIMS,POLICY,POLICY_SHA,canonical,digest,decide

PYTHON=ROOT/'research/audio-head/.venv/bin/python'
WORK=ROOT/'work/roadmap-completion-20261004/admission'

def declaration():
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}
    return {**readiness(),'sourceSha256':files,'sourceBindingSha256':digest(files),'claimLimits':dict(CLAIMS)}

def _run_worker(raw):
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='blind-',dir=WORK) as directory:
        stage=Path(directory)
        env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
             'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','PYTHONPATH':str(Path(__file__).parents[1]),'TMPDIR':str(stage)}
        runtime=supervise([str(PYTHON),'-m','admission.worker',str(stage)],raw,cwd=ROOT,env=env,timeout_seconds=POLICY['workerTimeoutSeconds'])
        if runtime['timedOut']:return {'status':'unavailable','reason':'worker_timeout','speechEvidence':None,'recognition':None,'runtime':runtime}
        try:
            result=json.loads(private_read(stage/'result.json',100000))
            if (set(result)!=set(('speechEvidence','recognition','status','reason','audioSha256','workerElapsedSeconds'))
                    or result['audioSha256']!=hashlib.sha256(raw).hexdigest()):raise ValueError('worker_result')
            if runtime['workerExitCode']!=0:
                return {'status':'unavailable','reason':'recognition_failed','speechEvidence':None,'recognition':None,'runtime':runtime}
            return {key:result[key] for key in ('status','reason','speechEvidence','recognition')}|{'runtime':runtime}
        except (ValueError,TypeError,KeyError,AdmissionError):
            return {'status':'unavailable','reason':'worker_crash','speechEvidence':None,'recognition':None,'runtime':runtime}


def recognize(raw,*,acoustic_worker=None):
    audio_sha=hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None
    capture={'audioSha256':audio_sha,'valid':False,'metrics':None}
    evidence={'schemaVersion':1,'status':'unavailable','reason':'invalid_audio','capture':capture,
              'speechEvidence':None,'recognition':None,
              'binding':{'audioSha256':audio_sha,'modelManifestSha256':MODEL_MANIFEST_SHA,'policySha256':POLICY_SHA},
              'runtime':{'elapsedSeconds':0,'peakRssKiB':None,'workerExitCode':None,'timedOut':False,'acousticCalls':0},
              'claimLimits':dict(CLAIMS)}
    try:
        if type(raw) is not bytes:raise AdmissionError('invalid_audio')
        metrics=bridge.capture(raw);capture.update(valid=True,metrics=metrics)
        if metrics['railSamples']>POLICY['maximumRailSamples']:raise AdmissionError('clipping')
        if metrics['rms']<POLICY['minimumRms']:raise AdmissionError('silence')
        result=(acoustic_worker or _run_worker)(raw)
        if type(result) is not dict or set(result)!=set(('status','reason','speechEvidence','recognition','runtime')):raise AdmissionError('recognition_failed')
        canonical(result)
        evidence.update(deepcopy(result))
    except bridge.Unavailable as error:evidence['reason']='invalid_audio'
    except AdmissionError as error:evidence['reason']=error.code if error.code in ('clipping','silence','worker_timeout','worker_crash','model_unavailable') else 'recognition_failed'
    except (OSError,ValueError,TypeError,KeyError):evidence['reason']='worker_crash'
    evidence['evidenceSha256']=digest(evidence)
    return evidence


def assess(raw,prompt,age_years=9,*,acoustic_worker=None,research_bridge=None,recognition_evidence=None):
    binding={'audioSha256':hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None,
             'promptSha256':None,'ageYears':age_years if type(age_years) is int else None,
             'policySha256':POLICY_SHA,'modelManifestSha256':MODEL_MANIFEST_SHA,'evidenceSha256':None,'bridgeRequestSha256':None}
    envelope={'schemaVersion':1,'status':'unavailable','reason':'invalid_prompt','capture':None,'speechEvidence':None,
              'wordMatch':None,'research':None,'runtime':None,'binding':binding,'claimLimits':dict(CLAIMS)}
    try:
        bridge.validate_prompt(prompt)
        if len(prompt['words'])!=1 or type(age_years) is not int or not 6<=age_years<=12:return envelope
        binding['promptSha256']=hashlib.sha256(bridge.canonical_bytes(prompt)).hexdigest()
        evidence=deepcopy(recognition_evidence) if recognition_evidence is not None else recognize(raw,acoustic_worker=acoustic_worker)
        if evidence.get('binding',{}).get('audioSha256')!=binding['audioSha256']:
            envelope['reason']='recognition_binding_failed';return envelope
        binding['evidenceSha256']=evidence['evidenceSha256']
        envelope['runtime']=evidence['runtime']
        envelope['capture']=evidence['capture']
        # Window posteriors and transcripts remain private recognition evidence.
        speech=evidence['speechEvidence']
        envelope['speechEvidence']=None if speech is None else {key:value for key,value in speech.items() if key!='probabilities'}
        match=decide(evidence,prompt['transcript']);envelope['wordMatch']=match
        if not match['admitted']:
            envelope['reason']=match['reason'];return envelope
        request=bridge.canonical_bytes({'schemaVersion':1,'attemptId':str(uuid.uuid4()),'ageYears':age_years,
                                       'prompt':deepcopy(prompt),'audioBase64':base64.b64encode(raw).decode('ascii')})
        binding['bridgeRequestSha256']=hashlib.sha256(request).hexdigest()
        response=(research_bridge or bridge.assess)(request)
        if (type(response) is not dict or response.get('binding',{}).get('audioSha256')!=binding['audioSha256']
                or response.get('binding',{}).get('promptSha256')!=binding['promptSha256']
                or response.get('binding',{}).get('requestSha256')!=binding['bridgeRequestSha256']
                or response.get('promptMatch')!='unverified'
                or any(response.get(flag) is not False for flag in ('learnerFeedbackEligible','clinicalUseEligible','productionUseEligible'))):
            envelope['reason']='research_binding_failed';return envelope
        if response.get('outcome')!='processed':
            envelope['reason']='research_unavailable';return envelope
        envelope.update(status='processed',reason=None,research=response)
        return envelope
    except bridge.Unavailable as error:
        envelope['reason']=error.reason if error.reason=='unsupported_target' else 'invalid_prompt';return envelope
    except (AdmissionError,ValueError,TypeError,KeyError,OSError):
        envelope['reason']='assessment_failed';return envelope
