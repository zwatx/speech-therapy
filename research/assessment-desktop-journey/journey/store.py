"""Private bounded hash-linked intents; terminal and forgetting capacity reserved."""
from copy import deepcopy
import json
import os

from recording_access.files import Files
from journey.models import JourneyError, exact, integer, identifier, opaque, TERMINALS, REASONS, validate_setup, prompt_request
from recording_access.models import strict_json
from workbench.domain import semantic_digest

MAX_EVENTS = 1024
MAX_BYTES = 8 * 1024 * 1024
ORDINARY_EVENTS = 384
ORDINARY_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 65536
ORDINARY = {'journey', 'planned', 'started', 'practice'}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'


def apply(state, kind, payload):
    if kind == 'journey':
        exact(payload, ('schemaVersion', 'projectId', 'createdAt', 'prompts', 'inventory', 'pipeline', 'retentionSeconds', 'maxAttempts', 'contentSha256'), 'journey_quarantined')
        opaque(payload['contentSha256'], 64); integer(payload['schemaVersion'], 1, 1); identifier(payload['projectId']); integer(payload['createdAt'])
        integer(payload['retentionSeconds'], 1, 86400); integer(payload['maxAttempts'], 1, 128)
        validate_setup(payload['prompts'], payload['inventory'], payload['pipeline'])
        if state['header'] is not None: raise JourneyError('journey_quarantined')
        state['header'] = deepcopy(payload); state['lastAt'] = payload['createdAt']; return
    if state['header'] is None or type(payload) is not dict or 'at' not in payload: raise JourneyError('journey_quarantined')
    integer(payload['at'])
    if payload['at'] < state['lastAt']: raise JourneyError('clock_unavailable')
    state['lastAt'] = payload['at']
    if kind in ('practice','cancel_action','clear_action'):
        exact(payload.get('actor'), ('accountId','generation'), 'journey_quarantined'); identifier(payload['actor']['accountId']); integer(payload['actor']['generation'], 1)
        identifier(payload.get('idempotencyKey')); opaque(payload.get('actionSha256'), 64)
    attempts = state['attempts']
    if kind == 'planned':
        exact(payload, ('at', 'id', 'actor', 'promptId', 'itemId', 'repeatOf', 'idempotencyKey', 'actionSha256', 'bindings', 'retainUntil'), 'journey_quarantined')
        opaque(payload['id']); exact(payload['actor'], ('accountId', 'generation')); identifier(payload['actor']['accountId']); integer(payload['actor']['generation'], 1)
        identifier(payload['idempotencyKey']); opaque(payload['actionSha256'], 64); integer(payload['retainUntil'], payload['at'] + 1)
        if type(payload['promptId']) is not str or payload['promptId'] not in {p['id'] for p in state['header']['prompts']} or type(payload['itemId']) is not str or payload['itemId'] not in {i['id'] for i in state['header']['inventory']}:
            raise JourneyError('journey_quarantined')
        exact(payload['bindings'], ('audioSha256', 'contentSha256', 'pipelineSha256', 'requestSha256'))
        for value in payload['bindings'].values(): opaque(value, 64)
        prompt = next(p for p in state['header']['prompts'] if p['id'] == payload['promptId'])
        item = next(i for i in state['header']['inventory'] if i['id'] == payload['itemId'])
        expected = {'audioSha256':item['sha256'], 'contentSha256':state['header']['contentSha256'], 'pipelineSha256':semantic_digest(state['header']['pipeline']),
                    'requestSha256':semantic_digest({'prompt':prompt_request(prompt),'ageYears':9,'pipeline':state['header']['pipeline'],'audioSha256':item['sha256']})}
        if payload['bindings'] != expected or payload['retainUntil'] != payload['at'] + state['header']['retentionSeconds']:raise JourneyError('journey_quarantined')
        parent = attempts.get(payload['repeatOf']) if type(payload['repeatOf']) is str else None
        if payload['repeatOf'] is not None and (not parent or parent['actor'] != payload['actor'] or parent['status'] == 'pending'):
            raise JourneyError('journey_quarantined')
        key = (payload['actor']['accountId'], payload['idempotencyKey'])
        if payload['id'] in attempts or key in state['actions'] or len(attempts) >= state['header']['maxAttempts']:
            raise JourneyError('journey_capacity')
        attempts[payload['id']] = {**deepcopy(payload), 'status': 'pending', 'reason': None, 'started': False, 'resultSha256': None, 'deletePending': False, 'cancelRequested': False, 'clearRequested': False}
        state['actions'][key] = {'kind': 'start', 'sha256': payload['actionSha256'], 'attemptId': payload['id']}
    elif kind == 'started':
        exact(payload, ('at', 'id'), 'journey_quarantined')
        attempt = attempts.get(payload['id'])
        if not attempt or attempt['status'] != 'pending' or attempt['started']: raise JourneyError('journey_quarantined')
        attempt['started'] = True
    elif kind == 'terminal':
        exact(payload, ('at', 'id', 'status', 'reason', 'resultSha256'), 'journey_quarantined')
        attempt = attempts.get(payload['id'])
        if not attempt or attempt['status'] != 'pending' or payload['status'] not in TERMINALS: raise JourneyError('journey_quarantined')
        if attempt['clearRequested'] and (payload['status'] != 'cancelled' or payload['reason'] != 'history_cleared'):raise JourneyError('journey_quarantined')
        if attempt['cancelRequested'] and not attempt['clearRequested'] and (payload['status'] != 'cancelled' or payload['reason'] != 'cancelled'):raise JourneyError('journey_quarantined')
        if payload['resultSha256'] is not None and payload['at'] >= attempt['retainUntil']:raise JourneyError('journey_quarantined')
        if payload['status'] == 'available':
            opaque(payload['resultSha256'], 64)
            if payload['reason'] is not None: raise JourneyError('journey_quarantined')
        elif payload['reason'] not in REASONS or (payload['resultSha256'] is not None and payload['status'] != 'unavailable'):
            raise JourneyError('journey_quarantined')
        if payload['resultSha256'] is not None: opaque(payload['resultSha256'], 64)
        attempt.update({'status': payload['status'], 'reason': payload['reason'], 'resultSha256': payload['resultSha256']})
    elif kind == 'practice':
        exact(payload, ('at', 'actor', 'promptId', 'attemptId', 'idempotencyKey', 'actionSha256'), 'journey_quarantined')
        key = (payload['actor']['accountId'], payload['idempotencyKey'])
        identifier(payload['idempotencyKey']); opaque(payload['actionSha256'], 64)
        if key in state['actions'] or payload['promptId'] not in {p['id'] for p in state['header']['prompts']}: raise JourneyError('journey_quarantined')
        if payload['attemptId'] is not None:
            attempt = attempts.get(payload['attemptId'])
            if not attempt or attempt['actor']['accountId'] != payload['actor']['accountId']: raise JourneyError('journey_quarantined')
        state['practice'].append(deepcopy(payload))
        state['actions'][key] = {'kind': 'practice', 'sha256': payload['actionSha256']}
    elif kind == 'cancel_action':
        exact(payload, ('at', 'actor', 'attemptId', 'idempotencyKey', 'actionSha256'), 'journey_quarantined')
        attempt = attempts.get(payload['attemptId']); key = (payload['actor']['accountId'], payload['idempotencyKey'])
        if not attempt or attempt['actor'] != payload['actor'] or key in state['actions']: raise JourneyError('journey_quarantined')
        identifier(payload['idempotencyKey']); opaque(payload['actionSha256'], 64)
        if attempt['status'] != 'pending' or attempt['cancelRequested']: raise JourneyError('journey_quarantined')
        attempt['cancelRequested'] = True
        state['actions'][key] = {'kind': 'cancel', 'sha256': payload['actionSha256'], 'attemptId': payload['attemptId']}
    elif kind == 'discard':
        exact(payload, ('at', 'id', 'reason'), 'journey_quarantined')
        attempt = attempts.get(payload['id'])
        if not attempt or attempt['status'] == 'pending' or attempt['deletePending'] or payload['reason'] not in REASONS: raise JourneyError('journey_quarantined')
        attempt.update({'status': 'forgotten' if payload['reason'] == 'history_cleared' else 'suppressed', 'reason': payload['reason'], 'resultSha256': None, 'deletePending': True})
    elif kind == 'forget_complete':
        exact(payload, ('at', 'id'), 'journey_quarantined')
        attempt = attempts.get(payload['id'])
        if not attempt or not attempt['deletePending']: raise JourneyError('journey_quarantined')
        attempt['deletePending'] = False
    elif kind == 'clear_action':
        exact(payload, ('at', 'actor', 'idempotencyKey', 'actionSha256', 'targets'), 'journey_quarantined')
        key = (payload['actor']['accountId'], payload['idempotencyKey'])
        if key in state['actions'] or type(payload['targets']) is not list or len(payload['targets']) > 128: raise JourneyError('journey_quarantined')
        for target in payload['targets']: opaque(target)
        if len(set(payload['targets'])) != len(payload['targets']): raise JourneyError('journey_quarantined')
        for target in payload['targets']:
            attempt = attempts.get(target)
            if not attempt or attempt['actor']['accountId'] != payload['actor']['accountId'] or attempt['clearRequested'] or attempt['status'] in ('forgotten','suppressed'): raise JourneyError('journey_quarantined')
            attempt['clearRequested'] = True
        state['actions'][key] = {'kind': 'clear', 'sha256': payload['actionSha256']}
    else: raise JourneyError('journey_quarantined')


class Store:
    def __init__(self, root, auth): self.files = Files(root, auth)
    def create(self, header):
        state = self.empty(); apply(state, 'journey', header)
        self.files.create_directory('journey-results')
        with self.files.file(None, 'journey.jsonl', os.O_CREAT | os.O_EXCL | os.O_WRONLY) as fd:
            self.files.write(fd, encode(self.event([], 'journey', header)))
    @staticmethod
    def empty(): return {'header': None, 'attempts': {}, 'actions': {}, 'practice': [], 'lastAt': 0}
    @staticmethod
    def event(records, kind, payload):
        event = {'seq': len(records), 'previousSha256': records[-1]['sha256'] if records else None, 'kind': kind, 'payload': deepcopy(payload)}
        return {**event, 'sha256': semantic_digest(event)}
    def load(self):
        try:
            with self.files.file(None, 'journey.jsonl', os.O_RDONLY) as fd: raw = self.files.read(fd, MAX_BYTES)
            if not raw or not raw.endswith(b'\n'): raise JourneyError('journey_quarantined')
            records, state = [], self.empty()
            for line in raw.splitlines():
                event = strict_json(line); exact(event, ('seq', 'previousSha256', 'kind', 'payload', 'sha256'), 'journey_quarantined')
                integer(event['seq'], 0, MAX_EVENTS)
                body = {key: value for key, value in event.items() if key != 'sha256'}
                if (event['seq'] != len(records) or event['previousSha256'] != (records[-1]['sha256'] if records else None)
                        or event['sha256'] != semantic_digest(body) or encode(event)[:-1] != line): raise JourneyError('journey_quarantined')
                apply(state, event['kind'], event['payload']); records.append(event)
            self.reserve(records, []); return records, state
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            raise JourneyError('journey_quarantined') from None
    def reserve(self, records, events):
        anticipated = list(records)
        for kind, payload in events: anticipated.append(self.event(anticipated, kind, payload))
        ordinary = [event for event in anticipated if event['kind'] in ORDINARY or (event['kind'] == 'clear_action' and not event['payload']['targets'])]
        if (len(anticipated) > MAX_EVENTS or len(ordinary) > ORDINARY_EVENTS
                or sum(len(encode(event)) for event in ordinary) > ORDINARY_BYTES
                or sum(len(encode(event)) for event in anticipated) > MAX_BYTES - 1024): raise JourneyError('journey_capacity')
    def append(self, kind, payload):
        records, state = self.load(); apply(state, kind, payload); self.reserve(records, [(kind, payload)])
        event = self.event(records, kind, payload)
        with self.files.file(None, 'journey.jsonl', os.O_WRONLY | os.O_APPEND) as fd: self.files.write(fd, encode(event))
        return event
    def result(self, attempt_id, value=None):
        opaque(attempt_id)
        if value is not None:
            raw = encode(value)
            if len(raw) > MAX_RESULT_BYTES: raise JourneyError('invalid_response')
            with self.files.file('journey-results', attempt_id + '.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL) as fd: self.files.write(fd, raw)
            return semantic_digest(value)
        with self.files.file('journey-results', attempt_id + '.json', os.O_RDONLY) as fd: raw = self.files.read(fd, MAX_RESULT_BYTES)
        return strict_json(raw)
    def delete_result(self, attempt_id):
        opaque(attempt_id); self.files.unlink('journey-results', attempt_id + '.json', missing_ok=True)
