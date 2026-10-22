"""Bounded public projection: no transcripts, probabilities or learner findings."""
import base64
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE = Path(__file__).parent
MAX_BODY = 200_000
MAX_AUDIO = 132_096
MAX_RESPONSE = 16_000
CLAIMS = {key: False for key in (
    'speechPresenceVerified', 'requestedWordVerified', 'promptMatchingValidated',
    'intendedChildAccuracyEstablished', 'qualifiedApprovalEstablished',
    'learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible',
    'authenticProvenanceEstablished')}
REASONS = frozenset((
    'invalid_request', 'invalid_audio', 'silence', 'clipping', 'unsupported_target',
    'invalid_prompt', 'speech_not_detected', 'worker_timeout', 'worker_crash',
    'model_unavailable', 'recognition_failed', 'invalid_evidence',
    'recognition_incomplete', 'recognition_uncertain', 'single_word_required',
    'requested_word_not_matched', 'recognition_binding_failed',
    'research_binding_failed', 'research_unavailable', 'assessment_failed',
    'timeout', 'busy', 'cleanup_unconfirmed', 'source_binding_failed'))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate_key')
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))


def bindings():
    return strict_json((MODULE / 'pins.json').read_bytes())


def source_map(path):
    return {p.name: sha(p.read_bytes()) for p in sorted(path.glob('*.py'))}


def verify_sources():
    pins = bindings()
    actual = {
        'admissionSourceSha256': sha(canonical(source_map(ROOT / 'research/assessment-admission/admission'))),
        'bridgeSourceSha256': sha(canonical(source_map(ROOT / 'research/audio-head/consumer_assessment'))),
        'serviceSourceSha256': sha(canonical(source_map(MODULE))),
        'supervisorSourceSha256': sha((MODULE / 'process.py').read_bytes()),
    }
    if any(pins.get(key) != value for key, value in actual.items()):
        raise ValueError('source_binding_failed')
    return pins


def validate_unsupported_prompt(prompt):
    """Validate structure of a ZH refusal without a proxy or an acoustic call."""
    from consumer_assessment.bridge import PHONES, VOWELS
    def need(condition):
        if not condition: raise ValueError('invalid_prompt')
    need(type(prompt) is dict and set(prompt) == {'schemaVersion', 'language', 'transcript', 'words', 'targets'})
    need(type(prompt['schemaVersion']) is int and prompt['schemaVersion'] == 2 and prompt['language'] == 'en')
    words, targets = prompt['words'], prompt['targets']
    need(type(words) is list and len(words) == 1 and type(targets) is list and 1 <= len(targets) <= 512)
    word = words[0]
    need(type(word) is dict and set(word) == {'text', 'phones'})
    need(type(word['text']) is str and 1 <= len(word['text']) <= 64 and word['text'].isprintable()
         and not any(c.isspace() for c in word['text']) and prompt['transcript'] == word['text'])
    need(type(word['phones']) is list and 1 <= len(word['phones']) <= 512)
    for phone in word['phones']:
        need(type(phone) is str and re.fullmatch(r'[A-Z]+[012]?', phone) is not None
             and (re.sub('[012]$', '', phone) in VOWELS or phone in (*PHONES, 'ZH')))
    ids, positions = set(), set()
    for target in targets:
        need(type(target) is dict and set(target) == {'id', 'wordIndex', 'phoneIndex', 'targetPhone'})
        need(type(target['id']) is str and 1 <= len(target['id']) <= 128 and target['id'].isprintable()
             and target['id'] not in ids and type(target['wordIndex']) is int and target['wordIndex'] == 0)
        index = target['phoneIndex']
        need(type(index) is int and 0 <= index < len(word['phones']) and index not in positions
             and target['targetPhone'] in (*PHONES, 'ZH') and word['phones'][index] == target['targetPhone'])
        ids.add(target['id']); positions.add(index)
    need(any(t['targetPhone'] == 'ZH' for t in targets))


def prepare(raw):
    from consumer_assessment.bridge import validate_prompt, valid_uuid, Unavailable
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BODY: raise ValueError('invalid_request')
    request = strict_json(raw)
    if type(request) is not dict or set(request) != {
            'schemaVersion', 'attemptId', 'ageYears', 'prompt', 'audioBase64'}:
        raise ValueError('invalid_request')
    if type(request['schemaVersion']) is not int or request['schemaVersion'] != 1:
        raise ValueError('invalid_request')
    if not valid_uuid(request['attemptId']) or request['attemptId'] != request['attemptId'].lower():
        raise ValueError('invalid_request')
    if type(request['ageYears']) is not int or not 6 <= request['ageYears'] <= 12:
        raise ValueError('invalid_request')
    if type(request['audioBase64']) is not str or len(request['audioBase64']) > 176_128:
        raise ValueError('invalid_audio')
    audio = base64.b64decode(request['audioBase64'], validate=True)
    if not 0 < len(audio) <= MAX_AUDIO: raise ValueError('invalid_audio')
    try: validate_prompt(request['prompt'])
    except Unavailable as error:
        if error.reason != 'unsupported_target': raise
        validate_unsupported_prompt(request['prompt'])
    if len(request['prompt']['words']) != 1: raise ValueError('invalid_prompt')
    return request, audio


def response(raw, request=None, audio=None, *, reason='invalid_request'):
    return {
        'schemaVersion': 1, 'researchOnly': True, 'status': 'unavailable', 'reason': reason,
        'speechAdmissionPassed': False, 'wordAdmissionPassed': False,
        'researchProcessed': False, 'bridgePromptMatch': 'unverified',
        'claimLimits': dict(CLAIMS), 'elapsedMilliseconds': 0,
        'binding': {
            'attemptId': request['attemptId'] if request else None,
            'requestSha256': sha(raw), 'audioSha256': sha(audio) if audio else None,
            'promptSha256': sha(canonical(request['prompt'])) if request else None,
            **bindings(),
        },
    }


def project(result, raw, request, audio):
    output = response(raw, request, audio)
    pins = bindings()
    expected = {
        'audioSha256': sha(audio), 'promptSha256': sha(canonical(request['prompt'])),
        'policySha256': pins['policySha256'], 'modelManifestSha256': pins['modelManifestSha256'],
        'ageYears': request['ageYears'],
    }
    if (type(result) is not dict or result.get('claimLimits') != CLAIMS
            or any(result.get('binding', {}).get(k) != v for k, v in expected.items())):
        output['reason'] = 'research_binding_failed'; return output
    if result.get('status') == 'unavailable':
        reason = result.get('reason')
        output['reason'] = reason if reason in REASONS else 'assessment_failed'
        return output
    research = result.get('research')
    from consumer_assessment.bridge import MANIFEST_SHA, canonical_bytes, valid_uuid
    evidence_sha = result['binding'].get('evidenceSha256')
    bridge_sha = result['binding'].get('bridgeRequestSha256')
    def valid_sha(value): return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None
    bridge_id = research.get('binding', {}).get('attemptId') if type(research) is dict else None
    expected_bridge_sha = sha(canonical_bytes({
        'schemaVersion': 1, 'attemptId': bridge_id, 'ageYears': request['ageYears'],
        'prompt': request['prompt'], 'audioBase64': base64.b64encode(audio).decode('ascii'),
    })) if valid_uuid(bridge_id) else None
    if (result.get('status') != 'processed' or result.get('reason') is not None
            or not valid_sha(evidence_sha) or not valid_sha(bridge_sha) or bridge_sha != expected_bridge_sha
            or result.get('capture', {}).get('valid') is not True
            or result.get('capture', {}).get('audioSha256') != sha(audio)
            or result.get('wordMatch', {}).get('evidenceSha256') != evidence_sha
            or result.get('wordMatch', {}).get('policySha256') != pins['policySha256']
            or result.get('wordMatch', {}).get('expectedWordSha256') != sha(canonical(request['prompt']['transcript']))
            or result.get('speechEvidence', {}).get('passed') is not True
            or result.get('wordMatch', {}).get('admitted') is not True
            or type(research) is not dict or research.get('schemaVersion') != 1
            or research.get('outcome') != 'processed' or research.get('reason') is not None
            or research.get('promptMatch') != 'unverified' or research.get('researchOnly') is not True
            or any(research.get(flag) is not False for flag in
                   ('learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible'))
            or research.get('model') != {'id': 'ages-6-12-research-mixture', 'manifestSha256': MANIFEST_SHA}
            or research.get('binding', {}).get('audioSha256') != sha(audio)
            or research.get('binding', {}).get('promptSha256') != expected['promptSha256']
            or research.get('binding', {}).get('requestSha256') != result['binding'].get('bridgeRequestSha256')):
        output['reason'] = 'research_binding_failed'; return output
    output.update(status='processed', reason=None, speechAdmissionPassed=True,
                  wordAdmissionPassed=True, researchProcessed=True)
    return output
