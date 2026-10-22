"""Closed, prompt-blind desktop reference contract; standard library only."""
import hashlib
import math
import struct

CAPACITY, CLASSES, MAX_WAV = 64000, 392, 132096
REVISION = 'ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'
KINDS = {'model_hypothesis', 'input_rejected', 'unavailable', 'cancelled', 'cleanup_unconfirmed'}
PHASES = {'preflight', 'input', 'loading', 'extractor', 'forward', 'decode', 'persist', 'unknown', 'cleanup', 'complete'}
REASONS = {'complete', 'invalid_request', 'invalid_wav', 'identity_mismatch', 'inactive',
           'integrity', 'loadingRejected', 'malformed_output', 'runtime_failure', 'cancelled', 'cleanup_unknown','expired','interrupted'}
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


CALL_STATES = {'not_started','invocation_committed','completed','unknown'}
TIMINGS = {'load','extractor','forward','cold','cleanup'}
ARTIFACTS = {'logits.f32':199*392*4,'normalized.f32':64000*4,
             'hypothesis.json':100000,'loading.json':200000}

def closed_json(raw):
    import json
    def pairs(items):
        out = {}
        for key,value in items:
            require(key not in out,'malformed_output')
            out[key] = value
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x: require(False,'malformed_output'))

def response(value, envelope, identities):
    keys = {'schema','kind','phase','reason','request','duration_seconds','identities',
            'model_called','model_call_state','terminal_owner','valid_frames','gates','timing_seconds','artifacts'}
    require(type(value) is dict and set(value) == keys and value['schema'] == 'PhoneticReferencePreviewV3', 'malformed_output')
    request(value['request'])
    require(value['request'] == envelope and value['identities'] == identities and value['gates'] == FALSE_GATES and
            all(value['gates'][k] is False for k in FALSE_GATES), 'malformed_output')
    require(value['kind'] in KINDS and value['phase'] in PHASES and value['reason'] in REASONS and
            type(value['terminal_owner']) is bool and (type(value['model_called']) is bool or value['model_called'] is None) and
            value['model_call_state'] in CALL_STATES and
            value['model_called'] is (None if value['model_call_state'] == 'unknown' else value['model_call_state'] != 'not_started') and
            type(value['valid_frames']) is int and value['valid_frames'] == frames(envelope['sample_count']) and
            type(value['duration_seconds']) is float and value['duration_seconds'] == envelope['sample_count']/16000, 'malformed_output')
    if value['kind'] == 'cleanup_unconfirmed':
        require(value['phase'] == 'cleanup' and value['reason'] == 'cleanup_unknown' and value['terminal_owner'] is False,'malformed_output')
    elif value['kind'] == 'input_rejected':
        require(value['phase'] == 'input' and value['reason'] in {'invalid_request','invalid_wav','identity_mismatch'} and value['model_called'] is False,'malformed_output')
    elif value['kind'] == 'cancelled':
        require(value['phase'] in {'preflight','complete'} and value['reason'] == 'cancelled','malformed_output')
    elif value['kind'] == 'unavailable':
        require(value['reason'] in {'inactive','integrity','loadingRejected','malformed_output','runtime_failure','expired','interrupted'},'malformed_output')
    t = value['timing_seconds']
    require(type(t) is dict and set(t) == TIMINGS and all(v is None or
            (type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 5000) for v in t.values()), 'malformed_output')
    a = value['artifacts']
    require(type(a) is dict and set(a) <= set(ARTIFACTS), 'malformed_output')
    for name,identity in a.items():
        require(type(identity) is dict and set(identity) == {'bytes','sha256'} and type(identity['bytes']) is int and
                0 < identity['bytes'] <= ARTIFACTS[name] and type(identity['sha256']) is str and
                len(identity['sha256']) == 64 and all(c in '0123456789abcdef' for c in identity['sha256']), 'malformed_output')
        if name.endswith('.f32'):
            require(identity['bytes'] == ARTIFACTS[name], 'malformed_output')
    if value['kind'] == 'model_hypothesis':
        require(value['phase'] == 'complete' and value['reason'] == 'complete' and
                value['model_call_state'] == 'completed' and set(a) == set(ARTIFACTS) and
                all(t[k] is not None for k in ('load','extractor','forward')), 'malformed_output')
    else:
        require(a == {},'malformed_output')
    return value

# V2 replaces the V1 in-memory/private-array envelope with closed artifact identities.
def result(kind, phase, reason, envelope, identities, model_called=False, terminal_owner=False,
           call_state=None):
    request(envelope)
    state = call_state or ('invocation_committed' if model_called else 'not_started')
    value = dict(schema='PhoneticReferencePreviewV3',kind=kind,phase=phase,reason=reason,
                 request=envelope,duration_seconds=envelope['sample_count']/16000,
                 identities=identities,model_called=model_called,model_call_state=state,
                 terminal_owner=terminal_owner,valid_frames=frames(envelope['sample_count']),
                 gates=dict(FALSE_GATES),timing_seconds=dict.fromkeys(TIMINGS),artifacts={})
    if kind != 'model_hypothesis': response(value,envelope,identities)
    return value


def private_metadata(hypothesis, loading, vocab, valid, deadline=None):
    require(type(valid) is int and 0 < valid <= 199,'malformed_output')
    require(type(hypothesis) is dict and set(hypothesis) == {'ids','symbols'} and
            type(hypothesis['ids']) is list and len(hypothesis['ids']) <= valid and
            all(type(i) is int and 0 < i < CLASSES for i in hypothesis['ids']) and
            hypothesis['symbols'] == symbols(hypothesis['ids'],vocab),'malformed_output')
    keys = {'schema','missingKeys','unexpectedKeys','mismatchedKeys','errorMessages','stateTensorCount',
            'parameterElementCount','allStateFP32Finite','migrationPolicy','migrations','checkpointMapping'}
    require(type(loading) is dict and set(loading) == keys and loading['schema'] == 'NativePhoneticLoadingV1' and
            loading['allStateFP32Finite'] is True and loading['migrationPolicy'] == 'OnlyPinnedHFPositionalWeightNormNamesV1' and
            all(type(loading[k]) is int and loading[k] == 0 for k in ('missingKeys','unexpectedKeys','mismatchedKeys','errorMessages')) and
            all(type(loading[k]) is int and 0 < loading[k] <= 2000000000 for k in ('stateTensorCount','parameterElementCount')),'malformed_output')
    allowed = {
        'wav2vec2.encoder.pos_conv_embed.conv.weight_g':'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original0',
        'wav2vec2.encoder.pos_conv_embed.conv.weight_v':'wav2vec2.encoder.pos_conv_embed.conv.parametrizations.weight.original1'}
    require(type(loading['migrations']) is list and len(loading['migrations']) == 2 and
            {x['from']:x['to'] for x in loading['migrations'] if type(x) is dict and set(x) == {'from','to'}} == allowed,'malformed_output')
    mapping = loading['checkpointMapping']
    require(type(mapping) is list and len(mapping) == loading['stateTensorCount'],'malformed_output')
    require(len(mapping) <= 10000,'malformed_output')
    originals,targets = set(),set()
    element_count = 0
    for row in mapping:
        if deadline is not None:
            import time
            require(time.monotonic() < deadline,'expired')
        require(type(row) is dict and set(row) == {'checkpointKey','modelKey','shape','dtype'} and
                type(row['checkpointKey']) is str and type(row['modelKey']) is str and
                row['modelKey'] == allowed.get(row['checkpointKey'],row['checkpointKey']) and
                row['dtype'] == 'torch.float32' and type(row['shape']) is list and len(row['shape']) <= 8 and
                all(type(x) is int and 0 < x <= 2000000000 for x in row['shape']) and
                row['checkpointKey'] not in originals and row['modelKey'] not in targets,'malformed_output')
        count = 1
        for dimension in row['shape']:
            require(count <= 2000000000 // dimension,'malformed_output')
            count *= dimension
        element_count += count
        require(element_count <= 2000000000,'malformed_output')
        originals.add(row['checkpointKey']);targets.add(row['modelKey'])

    require(element_count == loading['parameterElementCount'],'malformed_output')


def collect(logits_raw, normalized_raw, hypothesis, loading, vocab, sample_count, deadline):
    """Independently bounded private-byte validation; no framework or array imports."""
    import time
    valid = frames(sample_count)
    require(type(logits_raw) is bytes and len(logits_raw) == ARTIFACTS['logits.f32'] and
            type(normalized_raw) is bytes and len(normalized_raw) == ARTIFACTS['normalized.f32'], 'malformed_output')
    private_metadata(hypothesis, loading, vocab, valid, deadline)
    ids, row, index = [], [], 0
    for (value,) in struct.iter_unpack('<f', logits_raw):
        if index % CLASSES == 0:
            require(time.monotonic() < deadline, 'expired')
        require(math.isfinite(value), 'malformed_output')
        row.append(value)
        index += 1
        if len(row) == CLASSES:
            if index // CLASSES <= valid:
                ids.append(max(range(CLASSES), key=lambda i: row[i]))
            row = []
    require(collapse(ids) == hypothesis['ids'], 'malformed_output')
    for index, (value,) in enumerate(struct.iter_unpack('<f', normalized_raw)):
        if index % 1024 == 0:
            require(time.monotonic() < deadline, 'expired')
        require(math.isfinite(value) and (index < sample_count or value == 0.0), 'malformed_output')
    require(time.monotonic() < deadline, 'expired')
    return {'schema':'PhoneticReferenceCollectionV3','finiteFullLogits':True,
            'finiteNormalized':True,'zeroNormalizedTail':True,'greedyCTCVerified':True,
            'validFrames':valid,'tokenCount':len(hypothesis['ids']),
            'loadingMappingCountVerified':True}
