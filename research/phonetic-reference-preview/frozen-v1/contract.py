"""Closed, prompt-blind desktop reference contract; standard library only."""
import hashlib
import math
import struct

CAPACITY, CLASSES, MAX_WAV = 64000, 392, 132096
REVISION = 'ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'
KINDS = {'model_hypothesis', 'input_rejected', 'unavailable', 'cancelled', 'cleanup_unconfirmed'}
PHASES = {'preflight', 'input', 'loading', 'forward', 'decode', 'cleanup', 'complete'}
REASONS = {'complete', 'invalid_request', 'invalid_wav', 'identity_mismatch', 'inactive',
           'integrity', 'loadingRejected', 'malformed_output', 'runtime_failure', 'cancelled', 'cleanup_unknown'}
FALSE_GATES = dict(originalNativeParityAccepted=False, clinical=False,
                   producedPhoneTruth=False, learnerFeedback=False)

class Rejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def require(ok, code):
    if not ok:
        raise Rejected(code)

def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

def request(value):
    require(type(value) is dict and set(value) == {'operation_id', 'request_id', 'wav_identity', 'sample_count'}, 'invalid_request')
    for key in ('operation_id', 'request_id'):
        require(type(value[key]) is str and 1 <= len(value[key]) <= 64 and
                all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in value[key]), 'invalid_request')
    require(type(value['sample_count']) is int and 1600 <= value['sample_count'] <= CAPACITY, 'invalid_request')
    identity = value['wav_identity']
    require(type(identity) is dict and set(identity) == {'bytes', 'sha256'} and
            type(identity['bytes']) is int and 44 <= identity['bytes'] <= MAX_WAV and
            type(identity['sha256']) is str and len(identity['sha256']) == 64 and
            all(c in '0123456789abcdef' for c in identity['sha256']), 'invalid_request')
    return value

def wav_payload(raw, envelope):
    """Strict canonical PCM RIFF: exactly fmt(16) then data, no other chunks."""
    request(envelope)
    require(type(raw) is bytes and 44 <= len(raw) <= MAX_WAV, 'invalid_wav')
    require(pin(raw) == envelope['wav_identity'], 'identity_mismatch')
    require(raw[:4] == b'RIFF' and raw[8:12] == b'WAVE' and raw[12:16] == b'fmt ' and
            raw[36:40] == b'data', 'invalid_wav')
    size, fmt_size = struct.unpack_from('<I', raw, 4)[0], struct.unpack_from('<I', raw, 16)[0]
    fmt = struct.unpack_from('<HHIIHH', raw, 20)
    data_size = struct.unpack_from('<I', raw, 40)[0]
    require(size == len(raw)-8 and fmt_size == 16 and fmt == (1, 1, 16000, 32000, 2, 16) and
            data_size == len(raw)-44 == envelope['sample_count']*2, 'invalid_wav')
    return memoryview(raw)[44:]

def frames(length):
    require(type(length) is int and 1600 <= length <= CAPACITY, 'invalid_request')
    for k, s in zip((10,3,3,3,3,2,2), (5,2,2,2,2,2,2)):
        length = (length-k)//s+1
    return length

def collapse(ids):
    out, previous = [], None
    for token in ids:
        require(type(token) is int and 0 <= token < CLASSES, 'malformed_output')
        if token != 0 and token != previous:
            out.append(token)
        previous = token
    return out

def greedy(rows, valid):
    require(type(valid) is int and 0 < valid <= len(rows), 'malformed_output')
    ids = []
    for row in rows[:valid]:
        require(len(row) == CLASSES and all(type(v) in (int,float) and math.isfinite(v) for v in row), 'malformed_output')
        ids.append(max(range(CLASSES), key=lambda i: row[i]))
    return collapse(ids)

def vocabulary(value):
    require(type(value) is dict and len(value) == CLASSES and
            all(type(k) is str and type(v) is int for k,v in value.items()) and
            set(value.values()) == set(range(CLASSES)), 'integrity')
    return {v:k for k,v in value.items()}

def symbols(ids, vocab):
    return [{'id':i, 'symbol':vocab[i], 'renderable':not (vocab[i].startswith('<') or vocab[i] == '|')}
            for i in ids]

def result(kind, phase, reason, envelope, identities, model_called=False, terminal_owner=False):
    require(kind in KINDS and phase in PHASES and reason in REASONS and
            type(model_called) is bool and type(terminal_owner) is bool, 'malformed_output')
    request(envelope)
    return dict(schema='PhoneticReferencePreviewV1', kind=kind, phase=phase, reason=reason,
                request=envelope, duration_seconds=envelope['sample_count']/16000,
                identities=identities, model_called=model_called, terminal_owner=terminal_owner,
                valid_frames=frames(envelope['sample_count']), gates=dict(FALSE_GATES))
