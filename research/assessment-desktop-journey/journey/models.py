"""Closed journey metadata and safe codes."""
from copy import deepcopy
import re

from workbench.domain import ValidationError, semantic_digest
from recording_access.models import strict_json, MAX_UTC

CLAIMS = {'learnerFeedbackEligible': False, 'clinicalUseEligible': False, 'productionUseEligible': False}
TERMINALS = {'available', 'unavailable', 'cancelled', 'interrupted', 'suppressed'}
REASONS = {'assessment_unavailable', 'recording_unavailable', 'authorization_changed', 'pipeline_changed',
           'cancelled', 'interrupted', 'retention_expired', 'history_cleared', 'unsupported_target',
           'invalid_audio', 'invalid_wav', 'silence', 'clipping', 'no_speech', 'word_mismatch',
           'requested_word_not_matched', 'recognition_uncertain', 'speech_not_detected', 'recognition_failed', 'worker_timeout', 'worker_crash', 'model_unavailable', 'invalid_evidence', 'research_unavailable', 'recognition_binding_failed', 'research_binding_failed', 'assessment_failed', 'recognition_unavailable', 'single_word_required', 'multiple_or_extra_words', 'speech_not_confirmed', 'prompt_not_matched', 'invalid_response'}


class JourneyError(ValidationError):
    pass


def exact(value, fields, code='request_fields'):
    if type(value) is not dict or set(value) != set(fields):
        raise JourneyError(code)


def identifier(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) is None:
        raise JourneyError('request_fields')


def opaque(value, count=32):
    if type(value) is not str or re.fullmatch('[0-9a-f]{' + str(count) + '}', value) is None:
        raise JourneyError('request_fields')


def integer(value, minimum=0, maximum=MAX_UTC):
    if type(value) is not int or not minimum <= value <= maximum:
        raise JourneyError('request_fields')


def reason(value):
    return value if type(value) is str and value in REASONS else 'assessment_unavailable'


def prompt_request(prompt):
    return {'schemaVersion': 2, 'language': 'en', 'transcript': prompt['word'],
            'words': [{'text': prompt['word'], 'phones': deepcopy(prompt['phones'])}],
            'targets': [{'id': prompt['id'], 'wordIndex': 0, 'phoneIndex': prompt['occurrenceIndex'], 'targetPhone': prompt['targetPhone']}]}


def validate_setup(prompts, inventory, pipeline):
    semantic_digest({'prompts': prompts, 'inventory': inventory, 'pipeline': pipeline})
    if type(prompts) is not list or not 1 <= len(prompts) <= 15 or type(inventory) is not list or not 1 <= len(inventory) <= 32:
        raise JourneyError('invalid_setup')
    for prompt in prompts:
        exact(prompt, ('id', 'word', 'sourceWord', 'targetPhone', 'variantId', 'phones', 'occurrenceIndex', 'supported'), 'invalid_setup')
        for field in ('id', 'sourceWord', 'targetPhone', 'variantId'): identifier(prompt[field])
        if type(prompt['word']) is not str or not prompt['word'].strip() or len(prompt['word']) > 80:
            raise JourneyError('invalid_setup')
        if type(prompt['phones']) is not list or not 1 <= len(prompt['phones']) <= 64:
            raise JourneyError('invalid_setup')
        for phone in prompt['phones']:
            if type(phone) is not str or re.fullmatch('[A-Z]{1,4}', phone) is None: raise JourneyError('invalid_setup')
        integer(prompt['occurrenceIndex'], 0, len(prompt['phones']) - 1)
        if prompt['phones'][prompt['occurrenceIndex']] != prompt['targetPhone'] or type(prompt['supported']) is not bool:
            raise JourneyError('invalid_setup')
    for item in inventory:
        exact(item, ('id', 'recordingId', 'sha256', 'label', 'kind', 'sourceWord', 'ageKnown'), 'invalid_setup')
        opaque(item['id'], 24); opaque(item['recordingId']); opaque(item['sha256'], 64)
        if (type(item['label']) is not str or not item['label'].strip() or len(item['label']) > 120
                or item['kind'] not in ('public_reference', 'invented_fixture') or item['ageKnown'] is not False):
            raise JourneyError('invalid_setup')
        if item['sourceWord'] is not None: identifier(item['sourceWord'])
    if len({p['id'] for p in prompts}) != len(prompts) or len({i['id'] for i in inventory}) != len(inventory):
        raise JourneyError('invalid_setup')
    if type(pipeline) is not dict or len(str(pipeline)) > 16000:
        raise JourneyError('invalid_setup')


def public_result(value):
    semantic_digest(value)
    exact(value, ('schemaVersion', 'status', 'reason', 'capture', 'speechEvidence', 'wordMatch', 'research', 'binding', 'claimLimits', 'runtime'), 'invalid_response')
    integer(value['schemaVersion'], 1, 1)
    if value['status'] not in ('processed', 'unavailable') or type(value['status']) is not str:
        raise JourneyError('invalid_response')
    if type(value['claimLimits']) is not dict or any(flag is not False for flag in value['claimLimits'].values()):
        raise JourneyError('invalid_response')
    if not all(value['claimLimits'].get(key) is False for key in CLAIMS):
        raise JourneyError('invalid_response')
    def stage(record):
        if record is None: return None
        if type(record) is not dict: raise JourneyError('invalid_response')
        status = record.get('status')
        if type(status) is not str or status not in ('valid','invalid','detected','not_detected','available','unavailable','processed','rejected','admitted'): status = 'unverified'
        return {'status': status, 'reason': None if record.get('reason') is None else reason(record['reason'])}
    matched = value['wordMatch']
    if matched is not None and (type(matched) is not dict or type(matched.get('admitted')) is not bool):
        raise JourneyError('invalid_response')
    return {'status': value['status'], 'reason': None if value['reason'] is None else reason(value['reason']),
            'capture': None if value['capture'] is None else {'status': 'valid' if value['capture'].get('valid') is True else 'invalid', 'reason': None}, 'speechEvidence': None if value['speechEvidence'] is None else {'status': 'passed' if value['speechEvidence'].get('passed') is True else 'not_passed' if value['speechEvidence'].get('passed') is False else 'unverified', 'reason': None},
            'wordMatch': None if matched is None else {'admitted': matched['admitted'], 'reason': None if matched.get('reason') is None else reason(matched['reason'])},
            'research': stage(None if value['research'] is None else {**value['research'], 'status': value['research'].get('outcome')}), 'claimLimits': deepcopy(CLAIMS)}


def validate_result_binding(value, raw, prompt, pipeline):
    import hashlib
    public_result(value)
    exact(value['binding'], ('audioSha256','promptSha256','ageYears','policySha256','modelManifestSha256','evidenceSha256','bridgeRequestSha256'), 'invalid_response')
    bound = value['binding']
    if (bound['audioSha256'] != hashlib.sha256(raw).hexdigest() or bound['promptSha256'] != semantic_digest(prompt)
            or type(bound['ageYears']) is not int or bound['ageYears'] != 9
            or bound['policySha256'] != pipeline.get('policySha256')
            or bound['modelManifestSha256'] != pipeline.get('modelManifestSha256')):
        raise JourneyError('invalid_response')
    for key in ('evidenceSha256','bridgeRequestSha256'):
        if bound[key] is not None: opaque(bound[key], 64)
    if value['status'] == 'processed':
        opaque(bound['evidenceSha256'],64); opaque(bound['bridgeRequestSha256'],64)
        if type(value['capture']) is not dict or value['capture'].get('valid') is not True:
            raise JourneyError('invalid_response')
        if value['wordMatch'] is None or value['wordMatch'].get('admitted') is not True or type(value['research']) is not dict or value['research'].get('outcome') != 'processed':
            raise JourneyError('invalid_response')
        research = value['research']; binding = research.get('binding', {})
        if (binding.get('audioSha256') != bound['audioSha256'] or binding.get('promptSha256') != bound['promptSha256']
                or binding.get('requestSha256') != bound['bridgeRequestSha256'] or research.get('promptMatch') != 'unverified'
                or any(research.get(key) is not False for key in CLAIMS)):
            raise JourneyError('invalid_response')
    elif value['research'] is not None:
        raise JourneyError('invalid_response')
