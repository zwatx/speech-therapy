"""Bounded declarations and supplied PCM bytes; never legal or human verification."""
from copy import deepcopy
import hashlib
import json
import math
import re
import struct

from workbench.domain import ValidationError, semantic_digest

PURPOSES = ('storage', 'review', 'research', 'inference', 'redistribution')
MAX_WAV_BYTES = 132096
MAX_FRAMES = 64000
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_UTC = 253402300799
CLAIM_FIELDS = ('identityVerified', 'consentAuthorityVerified', 'rightsVerified', 'qualifiedApprovalEstablished',
                'learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible', 'authenticProvenanceEstablished')


class VaultError(ValidationError):
    """Fixed safe codes, with no supplied data/path/credential in public errors."""


def exact(value, fields, code='invalid_declaration'):
    if type(value) is not dict or set(value) != set(fields):
        raise VaultError(code)


def integer(value, minimum=0, maximum=MAX_UTC, code='invalid_declaration'):
    if type(value) is not int or not minimum <= value <= maximum:
        raise VaultError(code)


def text(value, maximum=1000, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise VaultError('invalid_declaration')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise VaultError('invalid_declaration') from None


def identifier(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) is None:
        raise VaultError('invalid_declaration')


def recording_id(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{32}', value) is None:
        raise VaultError('recording_unavailable')


def sha(value, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise VaultError('invalid_declaration')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VaultError('invalid_json')
        result[key] = value
    return result


def _reject(value):
    raise VaultError('invalid_json')


def _number(value):
    if len(value) > 128:
        raise VaultError('invalid_json')
    result = float(value)
    if not math.isfinite(result):
        raise VaultError('invalid_json')
    return result


def _int(value):
    if len(value) > 128:
        raise VaultError('invalid_json')
    return int(value)


def strict_json(raw):
    try:
        if type(raw) is bytes:
            if len(raw) > MAX_JSON_BYTES:
                raise VaultError('invalid_json')
            raw = raw.decode('utf-8')
        elif type(raw) is str:
            if len(raw) > MAX_JSON_BYTES or len(raw.encode('utf-8')) > MAX_JSON_BYTES:
                raise VaultError('invalid_json')
        else:
            raise VaultError('invalid_json')
        result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject, parse_int=_int, parse_float=_number)
        semantic_digest(result)
        return result
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise VaultError('invalid_json') from None


def validate_declaration(value):
    exact(value, ('schemaVersion', 'expectedSha256', 'source', 'subject', 'permissions', 'retainUntil'))
    integer(value['schemaVersion'], 1, 1)
    sha(value['expectedSha256'])
    integer(value['retainUntil'])
    source, subject = value['source'], value['subject']
    exact(source, ('kind', 'description', 'originalSha256', 'provenanceEvidenceSha256'))
    if type(source['kind']) is not str or source['kind'] not in ('invented_fixture', 'public_reference', 'private_child'):
        raise VaultError('invalid_declaration')
    text(source['description'], 500)
    sha(source['originalSha256'])
    sha(source['provenanceEvidenceSha256'])
    exact(subject, ('id', 'kind', 'ageYears', 'identityDeclaration', 'identityEvidenceSha256',
                    'consentAuthorityDeclaration', 'consentAuthorityEvidenceSha256'))
    identifier(subject['id'])
    expected_kind = 'invented' if source['kind'] == 'invented_fixture' else source['kind']
    if subject['kind'] != expected_kind or type(subject['kind']) is not str:
        raise VaultError('invalid_declaration')
    if subject['ageYears'] is not None:
        integer(subject['ageYears'], 0, 17)
    for field in ('identityDeclaration', 'consentAuthorityDeclaration'):
        text(subject[field], 1000, nullable=True)
    for field in ('identityEvidenceSha256', 'consentAuthorityEvidenceSha256'):
        sha(subject[field], nullable=True)
    exact(value['permissions'], PURPOSES)
    for permission in value['permissions'].values():
        exact(permission, ('rights', 'consent'))
        for kind in ('rights', 'consent'):
            decision = permission[kind]
            exact(decision, ('status', 'expiresAt', 'evidenceSha256', 'declaration'))
            statuses = ('granted', 'denied', 'unknown') + (('not_applicable_public_reference',) if kind == 'consent' else ())
            if type(decision['status']) is not str or decision['status'] not in statuses:
                raise VaultError('invalid_declaration')
            if decision['expiresAt'] is not None:
                integer(decision['expiresAt'])
            sha(decision['evidenceSha256'], nullable=True)
            text(decision['declaration'], nullable=True)
            if decision['status'] == 'granted' and any(decision[field] is None for field in ('expiresAt', 'evidenceSha256', 'declaration')):
                raise VaultError('invalid_declaration')
            if decision['status'] == 'not_applicable_public_reference':
                if source['kind'] != 'public_reference' or decision['expiresAt'] is None or decision['declaration'] is None:
                    raise VaultError('invalid_declaration')
    if source['kind'] == 'private_child':
        if subject['ageYears'] is None or any(subject[field] is None for field in (
                'identityDeclaration', 'identityEvidenceSha256', 'consentAuthorityDeclaration', 'consentAuthorityEvidenceSha256')):
            raise VaultError('child_records_required')
        if value['permissions']['storage']['consent']['status'] != 'granted':
            raise VaultError('child_records_required')
    try:
        semantic_digest(value)
    except ValidationError:
        raise VaultError('invalid_declaration') from None
    return deepcopy(value)


def permission_allowed(declaration, purpose, now):
    if purpose not in PURPOSES:
        return False
    permission = declaration['permissions'][purpose]
    for kind in ('rights', 'consent'):
        decision = permission[kind]
        accepted = ('granted', 'not_applicable_public_reference') if kind == 'consent' else ('granted',)
        if decision['status'] not in accepted or decision['expiresAt'] is None or now >= decision['expiresAt']:
            return False
    return True


def inspect_wav(raw):
    if type(raw) is not bytes or not 44 <= len(raw) <= MAX_WAV_BYTES:
        raise VaultError('invalid_wav')
    try:
        if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE' or struct.unpack_from('<I', raw, 4)[0] != len(raw) - 8:
            raise VaultError('invalid_wav')
        offset, fmt, data = 12, None, None
        while offset < len(raw):
            if offset + 8 > len(raw):
                raise VaultError('invalid_wav')
            kind, size = raw[offset:offset + 4], struct.unpack_from('<I', raw, offset + 4)[0]
            offset += 8
            end = offset + size
            padded = end + size % 2
            if padded > len(raw):
                raise VaultError('invalid_wav')
            if kind == b'fmt ':
                if fmt is not None or size not in (16, 18) or (size == 18 and raw[end - 2:end] != b'\x00\x00'):
                    raise VaultError('invalid_wav')
                fmt = struct.unpack_from('<HHIIHH', raw, offset)
            elif kind == b'data':
                if data is not None or fmt is None:
                    raise VaultError('invalid_wav')
                data = size
            elif kind not in (b'LIST', b'JUNK'):
                raise VaultError('invalid_wav')
            offset = padded
        if fmt != (1, 1, 16000, 32000, 2, 16) or data is None or data % 2 or not 1 <= data // 2 <= MAX_FRAMES:
            raise VaultError('invalid_wav')
    except (struct.error, ValueError, OverflowError):
        raise VaultError('invalid_wav') from None
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'byteLength': len(raw),
            'frames': data // 2, 'durationMs': (data // 2) * 1000 // 16000}
