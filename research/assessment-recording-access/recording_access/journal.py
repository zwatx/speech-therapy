"""Validated private hash-linked lifecycle; hashes are not signatures."""
from copy import deepcopy
import json
import os

from workbench.domain import semantic_digest

from .models import (VaultError, PURPOSES, MAX_JSON_BYTES, MAX_WAV_BYTES, MAX_FRAMES,
                     exact, integer, identifier, recording_id, sha, text, strict_json,
                     validate_declaration, permission_allowed)

MAX_EVENTS = 4096
MAX_RECORDINGS = 256
# 256 subjects + 5 restrictions/record + two purge events/record +
# two orphan events/stage fit in the remaining 2560 event slots.
# Their bounded UTF-8 payloads fit inside the remaining 6 MiB.
ORDINARY_MAX_EVENTS = 1536
ORDINARY_MAX_BYTES = 2 * 1024 * 1024
CONTROL_KINDS = frozenset(('restriction', 'withdrawal', 'purge_intent', 'purge_complete',
                           'orphan_delete_intent', 'orphan_delete_complete'))


def eligible(record, state, now):
    reasons = []
    if record['lifecycle'] not in ('available', 'import_pending'):
        return reasons
    declaration = record['declaration']
    if declaration['subject']['id'] in state['withdrawn']:
        reasons.append('subject_withdrawn')
    if now >= declaration['retainUntil']:
        reasons.append('retention_expired')
    if 'storage' in record['restrictions'] or not permission_allowed(declaration, 'storage', now):
        reasons.append('storage_unavailable')
    return reasons


def available(record, state, purpose, now):
    return (record['lifecycle'] == 'available' and not eligible(record, state, now)
            and purpose not in record['restrictions'] and permission_allowed(record['declaration'], purpose, now))


def _actor(value, coordinator=False):
    exact(value, ('accountId', 'generation', 'role'))
    identifier(value['accountId'])
    integer(value['generation'], 1)
    if type(value['role']) is not str or value['role'] not in ('coordinator', 'reviewer-a', 'reviewer-b', 'adjudicator'):
        raise VaultError('vault_quarantined')
    if coordinator and value['role'] != 'coordinator':
        raise VaultError('vault_quarantined')


def apply(state, kind, payload):
    if kind == 'vault':
        exact(payload, ('schemaVersion', 'vaultId', 'projectId', 'createdAt'))
        integer(payload['schemaVersion'], 1, 1)
        recording_id(payload['vaultId'])
        identifier(payload['projectId'])
        integer(payload['createdAt'])
        if state['header'] is not None:
            raise VaultError('vault_quarantined')
        state['header'] = deepcopy(payload)
        state['lastAt'] = payload['createdAt']
        return
    if state['header'] is None or type(payload) is not dict or 'at' not in payload:
        raise VaultError('vault_quarantined')
    integer(payload['at'])
    if payload['at'] < state['lastAt']:
        raise VaultError('clock_unavailable')
    state['lastAt'] = payload['at']
    records = state['recordings']
    if kind == 'import_intent':
        exact(payload, ('at', 'recordingId', 'sha256', 'byteLength', 'frames', 'declaration'))
        rid = payload['recordingId']
        recording_id(rid)
        sha(payload['sha256'])
        integer(payload['byteLength'], 44, MAX_WAV_BYTES)
        integer(payload['frames'], 1, MAX_FRAMES)
        if payload['byteLength'] < 44 + payload['frames'] * 2:
            raise VaultError('invalid_wav')
        declaration = validate_declaration(payload['declaration'])
        if declaration['expectedSha256'] != payload['sha256']:
            raise VaultError('vault_quarantined')
        subject = declaration['subject']
        if (rid in records or rid in state['orphans'] or len(records) >= MAX_RECORDINGS
                or subject['id'] in state['withdrawn'] or declaration['retainUntil'] <= payload['at']
                or not permission_allowed(declaration, 'storage', payload['at'])):
            raise VaultError('vault_quarantined')
        previous = state['subjects'].get(subject['id'])
        if previous is not None and semantic_digest(previous) != semantic_digest(subject):
            raise VaultError('subject_declaration_conflict')
        state['subjects'][subject['id']] = deepcopy(subject)
        records[rid] = {**deepcopy(payload), 'lifecycle': 'import_pending', 'restrictions': set(), 'completedImport': False}
    elif kind == 'import_complete':
        exact(payload, ('at', 'recordingId', 'recovered'))
        record = records.get(payload['recordingId'])
        if not record or record['lifecycle'] != 'import_pending' or type(payload['recovered']) is not bool:
            raise VaultError('vault_quarantined')
        if eligible(record, state, payload['at']):
            raise VaultError('vault_quarantined')
        record['lifecycle'] = 'available'
        record['completedImport'] = True
    elif kind == 'restriction':
        exact(payload, ('at', 'recordingId', 'purpose', 'reason', 'actor'))
        _actor(payload['actor'], coordinator=True)
        text(payload['reason'], 500)
        record = records.get(payload['recordingId'])
        if (not record or record['lifecycle'] not in ('available', 'import_pending') or type(payload['purpose']) is not str
                or payload['purpose'] not in PURPOSES or payload['purpose'] in record['restrictions']):
            raise VaultError('vault_quarantined')
        record['restrictions'].add(payload['purpose'])
    elif kind == 'withdrawal':
        exact(payload, ('at', 'subjectId', 'reason', 'actor'))
        _actor(payload['actor'], coordinator=True)
        identifier(payload['subjectId'])
        text(payload['reason'], 500)
        if payload['subjectId'] not in state['subjects'] or payload['subjectId'] in state['withdrawn']:
            raise VaultError('vault_quarantined')
        state['withdrawn'].add(payload['subjectId'])
    elif kind == 'access':
        exact(payload, ('at', 'recordingId', 'purpose', 'actor'))
        _actor(payload['actor'])
        purpose = payload['purpose']
        record = records.get(payload['recordingId'])
        if (type(purpose) is not str or purpose not in ('review', 'research', 'inference')
                or (payload['actor']['role'] != 'coordinator' and purpose != 'review')
                or not record or not available(record, state, purpose, payload['at'])):
            raise VaultError('vault_quarantined')
        state['accessCount'] += 1
    elif kind == 'metadata_export':
        exact(payload, ('at', 'actor'))
        _actor(payload['actor'], coordinator=True)
        state['exportCount'] += 1
    elif kind == 'purge_intent':
        exact(payload, ('at', 'recordingId', 'planSha256'))
        sha(payload['planSha256'])
        record = records.get(payload['recordingId'])
        if not record or not eligible(record, state, payload['at']):
            raise VaultError('vault_quarantined')
        record['lifecycle'] = 'pending_delete'
        record['deletionPlanSha256'] = payload['planSha256']
    elif kind == 'purge_complete':
        exact(payload, ('at', 'recordingId', 'recovered'))
        record = records.get(payload['recordingId'])
        if not record or record['lifecycle'] != 'pending_delete' or type(payload['recovered']) is not bool:
            raise VaultError('vault_quarantined')
        record['lifecycle'] = 'purged'
    elif kind == 'orphan_delete_intent':
        exact(payload, ('at', 'recordingId', 'sha256', 'byteLength', 'planSha256'))
        recording_id(payload['recordingId'])
        sha(payload['sha256'])
        sha(payload['planSha256'])
        integer(payload['byteLength'], 0, MAX_WAV_BYTES)
        rid = payload['recordingId']
        if rid in records or rid in state['orphans'] or len(state['orphans']) >= MAX_RECORDINGS:
            raise VaultError('vault_quarantined')
        state['orphans'][rid] = {**deepcopy(payload), 'lifecycle': 'pending_delete'}
    elif kind == 'orphan_delete_complete':
        exact(payload, ('at', 'recordingId', 'recovered'))
        orphan = state['orphans'].get(payload['recordingId'])
        if not orphan or orphan['lifecycle'] != 'pending_delete' or type(payload['recovered']) is not bool:
            raise VaultError('vault_quarantined')
        orphan['lifecycle'] = 'purged'
    else:
        raise VaultError('vault_quarantined')


class Journal:
    def __init__(self, files):
        self.files = files

    @staticmethod
    def encode(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'

    @staticmethod
    def empty():
        return {'header': None, 'lastAt': 0, 'recordings': {}, 'subjects': {}, 'withdrawn': set(),
                'orphans': {}, 'accessCount': 0, 'exportCount': 0}

    @staticmethod
    def event(records, kind, payload):
        event = {'seq': len(records), 'previousSha256': records[-1]['sha256'] if records else None,
                 'kind': kind, 'payload': deepcopy(payload)}
        event['sha256'] = semantic_digest(event)
        return event

    def create(self, header):
        state = self.empty()
        apply(state, 'vault', header)
        with self.files.file(None, 'vault.jsonl', os.O_CREAT | os.O_EXCL | os.O_WRONLY) as fd:
            self.files.write(fd, self.encode(self.event([], 'vault', header)))

    def load(self):
        try:
            with self.files.file(None, 'vault.jsonl', os.O_RDONLY) as fd:
                raw = self.files.read(fd, MAX_JSON_BYTES)
            if not raw or not raw.endswith(b'\n'):
                raise VaultError('vault_quarantined')
            records, state = [], self.empty()
            for line in raw.splitlines():
                if len(records) >= MAX_EVENTS:
                    raise VaultError('vault_quarantined')
                event = strict_json(line)
                exact(event, ('seq', 'previousSha256', 'kind', 'payload', 'sha256'))
                if line != self.encode(event)[:-1]:
                    raise VaultError('vault_quarantined')
                integer(event['seq'], 0, MAX_EVENTS)
                body = {key: value for key, value in event.items() if key != 'sha256'}
                if (event['seq'] != len(records) or event['previousSha256'] != (records[-1]['sha256'] if records else None)
                        or event['sha256'] != semantic_digest(body)):
                    raise VaultError('vault_quarantined')
                apply(state, event['kind'], event['payload'])
                records.append(event)
            if state['header'] is None:
                raise VaultError('vault_quarantined')
            self.reserve(records, [])
            return records, state
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            raise VaultError('vault_quarantined') from None

    def reserve(self, records, events):
        if len(records) + len(events) > MAX_EVENTS:
            raise VaultError('vault_capacity')
        anticipated = list(records)
        for kind, payload in events:
            anticipated.append(self.event(anticipated, kind, payload))
        ordinary = [event for event in anticipated if event['kind'] not in CONTROL_KINDS]
        if (len(ordinary) > ORDINARY_MAX_EVENTS
                or sum(len(self.encode(event)) for event in ordinary) > ORDINARY_MAX_BYTES
                or sum(len(self.encode(event)) for event in anticipated) > MAX_JSON_BYTES - 1024):
            raise VaultError('vault_capacity')

    def append(self, kind, payload):
        records, state = self.load()
        apply(state, kind, payload)
        event = self.event(records, kind, payload)
        self.reserve(records, [(kind, payload)])
        with self.files.file(None, 'vault.jsonl', os.O_WRONLY | os.O_APPEND) as fd:
            self.files.write(fd, self.encode(event))
        return event
