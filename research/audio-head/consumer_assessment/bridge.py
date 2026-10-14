"""Strict transport/capture boundary, independent of the scientific loaders."""
from __future__ import annotations
import array
import base64
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parent.parent
MAX_BODY = 220_000
MAX_AUDIO_BYTES = 132_096
# Cold extraction can spend ~39 seconds in imports and CTC before the encoder/head.
# Keep an explicit worker-group deadline, with transport timeouts above this budget.
TIMEOUT_SECONDS = 90
TEMP_ROOT = None
CLEANUP_TIMEOUT_SECONDS = 2
INSPECTION_TIMEOUT_SECONDS = 0.5
PHONES = tuple('B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG'.split())
VOWELS = set('AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW'.split())
MANIFEST_SHA = 'bc62f1e4f1727379161d0f3f7d8e6074e645e7578b5c25661fd9da53e4fde1bf'
FLAGS = {'researchOnly': True, 'learnerFeedbackEligible': False,
         'clinicalUseEligible': False, 'productionUseEligible': False}


class Unavailable(Exception):
    def __init__(self, reason): self.reason = reason


def sha(data): return hashlib.sha256(data).hexdigest()


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError('duplicate key')
            out[key] = value
        return out
    def constant(_): raise ValueError('nonfinite JSON')
    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def valid_uuid(value):
    if not isinstance(value, str): return False
    try: return str(uuid.UUID(value)) == value
    except ValueError: return False


def validate_prompt(prompt):
    def need(condition):
        if not condition: raise Unavailable('invalid_request')
    need(isinstance(prompt, dict) and set(prompt) == {'schemaVersion','language','transcript','words','targets'}
         and type(prompt['schemaVersion']) is int and prompt['schemaVersion'] == 2 and prompt['language'] == 'en')
    words, targets = prompt['words'], prompt['targets']
    need(isinstance(words,list) and 1 <= len(words) <= 200 and isinstance(targets,list) and 1 <= len(targets) <= 512)
    # Target support has its own explicit state, including unsupported syllabic ER.
    for target in targets:
        need(isinstance(target,dict) and set(target) == {'id','wordIndex','phoneIndex','targetPhone'})
        if target['targetPhone'] not in PHONES: raise Unavailable('unsupported_target')
    total = 0
    for word in words:
        need(isinstance(word,dict) and set(word) == {'text','phones'} and isinstance(word['text'],str)
             and 1 <= len(word['text']) <= 64 and word['text'].isprintable()
             and not any(c.isspace() for c in word['text']) and isinstance(word['phones'],list) and word['phones'])
        total += len(word['phones'])
        for phone in word['phones']:
            need(isinstance(phone,str) and re.fullmatch(r'[A-Z]+[012]?',phone) is not None
                 and (re.sub('[012]$','',phone) in VOWELS or phone in (*PHONES,'ZH')))
    need(total <= 512 and isinstance(prompt['transcript'],str) and len(prompt['transcript']) <= 4096
         and prompt['transcript'] == ' '.join(w['text'] for w in words))
    seen_ids, seen_positions = set(), set()
    for t in targets:
        need(isinstance(t['id'],str) and 1 <= len(t['id']) <= 128 and t['id'].isprintable()
             and t['id'] not in seen_ids and type(t['wordIndex']) is int and 0 <= t['wordIndex'] < len(words))
        word = words[t['wordIndex']]
        need(type(t['phoneIndex']) is int and 0 <= t['phoneIndex'] < len(word['phones'])
             and (t['wordIndex'],t['phoneIndex']) not in seen_positions
             and word['phones'][t['phoneIndex']] == t['targetPhone'])
        seen_ids.add(t['id']); seen_positions.add((t['wordIndex'],t['phoneIndex']))


def capture(audio):
    if len(audio) > MAX_AUDIO_BYTES: raise Unavailable('audio_too_long')
    try:
        if len(audio) < 44 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE' or struct.unpack('<I',audio[4:8])[0] != len(audio)-8:
            raise ValueError('invalid RIFF')
        position, fmt, data = 12, None, None
        while position + 8 <= len(audio):
            name = audio[position:position+4]
            length = struct.unpack('<I',audio[position+4:position+8])[0]
            start = position + 8
            if start + length > len(audio): raise ValueError('truncated chunk')
            if name == b'fmt ':
                if fmt is not None: raise ValueError('duplicate format')
                fmt = audio[start:start+length]
            if name == b'data':
                if data is not None: raise ValueError('duplicate data')
                data = audio[start:start+length]
            position = start + length + length % 2
        if position != len(audio) or fmt is None or len(fmt) < 16 or data is None:
            raise ValueError('chunk layout')
        if struct.unpack('<HHIIHH',fmt[:16]) != (1,1,16000,32000,2,16) or len(data) % 2:
            raise ValueError('format')
        count = len(data)//2
        if count > 64000: raise Unavailable('audio_too_long')
        if count < 1600: raise ValueError('too short')
        values = array.array('h',data)
        if sys.byteorder != 'little': values.byteswap()
        rms = math.sqrt(sum((v/32768)**2 for v in values)/count)
        return {'sampleCount':count,'durationMilliseconds':count/16,'rms':rms,
                'peak':max(abs(v) for v in values)/32768,'railSamples':sum(v in (-32768,32767) for v in values)}
    except Unavailable: raise
    except Exception: raise Unavailable('invalid_audio') from None


@dataclass
class Prepared:
    request: dict
    audio: bytes
    metrics: dict


def prepare(data):
    try:
        if len(data) > MAX_BODY: raise Unavailable('request_too_large')
        req = strict_json(data)
        if not isinstance(req,dict) or set(req) != {'schemaVersion','attemptId','ageYears','prompt','audioBase64'} or type(req['schemaVersion']) is not int or req['schemaVersion'] != 1 or not valid_uuid(req['attemptId']):
            raise Unavailable('invalid_request')
        if type(req['ageYears']) is not int or not 6 <= req['ageYears'] <= 12: raise Unavailable('age_out_of_range')
        validate_prompt(req['prompt'])
        try:
            if not isinstance(req['audioBase64'],str): raise ValueError('base64 type')
            audio = base64.b64decode(req['audioBase64'],validate=True)
        except Exception: raise Unavailable('invalid_audio') from None
        return Prepared(req,audio,capture(audio))
    except Unavailable: raise
    except Exception: raise Unavailable('invalid_request') from None


def response_base(data):
    binding = {'attemptId':None,'requestSha256':sha(data),'audioSha256':None,'promptSha256':None}
    try:
        if len(data) > MAX_BODY: raise ValueError('oversized')
        req = strict_json(data)
        if isinstance(req,dict):
            if valid_uuid(req.get('attemptId')): binding['attemptId'] = req['attemptId']
            if isinstance(req.get('prompt'),dict): binding['promptSha256'] = sha(canonical_bytes(req['prompt']))
            if isinstance(req.get('audioBase64'),str):
                binding['audioSha256'] = sha(base64.b64decode(req['audioBase64'],validate=True))
    except Exception: pass
    return {'schemaVersion':1, **FLAGS,'binding':binding,'outcome':'unavailable','reason':None,
            'promptMatch':'unverified','captureMetrics':None,'timingMilliseconds':{'total':0,'inference':0},
            'targets':[],'model':None}


def stop_process(process):
    try: os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError: pass
    process.wait()


def run_isolated(prepared, *, artifacts=None):
    # Parent owns cleanup even when its model worker crashes or times out.
    with tempfile.TemporaryDirectory(prefix='speech-assessment-',dir=TEMP_ROOT) as directory:
        stage = Path(directory)
        (stage/'runtime').mkdir(mode=0o700)
        path = stage/'request.json'; path.write_bytes(canonical_bytes(prepared.request)); path.chmod(0o600)
        env = {**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2',
               'PYTHONPATH':str(HERE),'TMPDIR':str(stage/'runtime')}
        process = subprocess.Popen([sys.executable,'-m','consumer_assessment.worker',str(stage)],
                                   cwd=HERE,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,start_new_session=True)
        try:
            try: process.wait(timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                stop_process(process); raise Unavailable('timeout') from None
            result = strict_json((stage/'result.json').read_bytes())
            if process.returncode != 0:
                reason = result.get('reason')
                raise Unavailable(reason if reason in {'model_unavailable','invalid_request','inference_failed'} else 'inference_failed')
            if artifacts is not None:
                # Deliberate CLI artifacts only; HTTP never retains these files.
                import shutil
                for name in ('features.npy','engineering.json'):
                    shutil.copyfile(stage/name,artifacts/name)
            return result
        finally:
            if process.poll() is None: stop_process(process)


def checked_result(result, request):
    if not isinstance(result,dict) or set(result) != {'targets','model'} or result['model'] != {'id':'ages-6-12-research-mixture','manifestSha256':MANIFEST_SHA}:
        raise Unavailable('inference_failed')
    targets = result['targets']
    if not isinstance(targets,list) or len(targets) != len(request['prompt']['targets']): raise Unavailable('inference_failed')
    for actual, expected in zip(targets, request['prompt']['targets'], strict=True):
        if not isinstance(actual,dict) or set(actual) != {*expected,'subjectiveCorpusRatingProbabilities'} or any(actual[k] != v for k,v in expected.items()):
            raise Unavailable('inference_failed')
        p = actual['subjectiveCorpusRatingProbabilities']
        if not isinstance(p,list) or len(p) != 3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 1 for v in p) or abs(sum(p)-1) > 1e-8:
            raise Unavailable('inference_failed')
    return result


def assess(data, *, artifacts=None):
    started = time.perf_counter(); response = response_base(data)
    try:
        p = prepare(data); response['captureMetrics'] = p.metrics
        if p.metrics['rms'] == 0: raise Unavailable('silence')
        if p.metrics['railSamples'] > 0: raise Unavailable('clipping')
        t0 = time.perf_counter()
        try: result = checked_result(run_isolated(p,artifacts=artifacts),p.request)
        finally: response['timingMilliseconds']['inference'] = (time.perf_counter()-t0)*1000
        response.update(outcome='processed',**result)
    except Unavailable as exc: response['reason'] = exc.reason
    except Exception: response['reason'] = 'inference_failed'
    response['timingMilliseconds']['total'] = (time.perf_counter()-started)*1000
    return response
