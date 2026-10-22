"""Closed declared context for whole-word recognition; legacy assessment stays unchanged."""
import base64
from mobile_admission import contract

REQUEST_VERSION = 2
PRACTICE_CONTEXTS = [
    {'kind': 'adult'},
    {'kind': 'child', 'minimumAgeYears': 6, 'maximumAgeYears': 12},
]


def validate_context(value):
    if type(value) is not dict:
        raise ValueError('invalid_request')
    if value == {'kind': 'adult'}:
        return
    if (set(value) == {'kind', 'ageYears'} and value['kind'] == 'child'
            and type(value['ageYears']) is int and 6 <= value['ageYears'] <= 12):
        return
    raise ValueError('invalid_request')


def prepare(raw):
    from consumer_assessment.bridge import validate_prompt, valid_uuid, Unavailable
    if type(raw) is not bytes or not 0 < len(raw) <= contract.MAX_BODY:
        raise ValueError('invalid_request')
    request = contract.strict_json(raw)
    if (type(request) is not dict or set(request) != {
            'schemaVersion', 'attemptId', 'practiceContext', 'prompt', 'audioBase64'}
            or type(request['schemaVersion']) is not int
            or request['schemaVersion'] != REQUEST_VERSION
            or not valid_uuid(request['attemptId'])
            or request['attemptId'] != request['attemptId'].lower()):
        raise ValueError('invalid_request')
    validate_context(request['practiceContext'])
    if type(request['audioBase64']) is not str or len(request['audioBase64']) > 176_128:
        raise ValueError('invalid_audio')
    audio = base64.b64decode(request['audioBase64'], validate=True)
    if not 0 < len(audio) <= contract.MAX_AUDIO:
        raise ValueError('invalid_audio')
    try:
        validate_prompt(request['prompt'])
    except Unavailable as error:
        if error.reason != 'unsupported_target':
            raise
        contract.validate_unsupported_prompt(request['prompt'])
    if len(request['prompt']['words']) != 1:
        raise ValueError('invalid_prompt')
    return request, audio
