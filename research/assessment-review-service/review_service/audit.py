"""Private attribution journal, called under the parent's shared auth.lock.

Recovery reconciles two fsynced files; it does not make their writes atomic.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import re
import stat
import uuid

from workbench.domain import ValidationError, semantic_digest
from workbench.store import parse_json, Store

_ROLES = {'coordinator', 'reviewer-a', 'reviewer-b', 'adjudicator'}
_KINDS = {'review', 'seal', 'adjudication', 'content_review', 'prediction_lock', 'withdrawal'}
_ACTIONS = {'reviews', 'seal', 'adjudications', 'content-reviews', 'prediction-lock', 'withdraw',
            'login', 'logout', 'state_read', 'media_request', 'export', 'access_denied'}


def _id(value, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) is None:
        raise ValidationError('access_audit_invalid')


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValidationError('access_audit_invalid')


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValidationError('access_audit_invalid')


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValidationError('access_audit_invalid')


class Audit:
    def __init__(self, root):
        self.root = Path(root)

    @classmethod
    def create(cls, root, project_heads):
        instance = cls(root)
        try:
            payload = {'schemaVersion': 1, 'projects': deepcopy(project_heads)}
            instance._record([], 'audit', payload)
            fd = instance._fd(os.O_RDWR | os.O_CREAT | os.O_EXCL)
            try:
                instance._write(fd, [], 'audit', payload)
            finally:
                os.close(fd)
        except (ValueError, TypeError, OSError, RecursionError):
            raise ValidationError('access_audit_invalid') from None
        return instance

    def _fd(self, flags=os.O_RDWR | os.O_APPEND):
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            root = os.fstat(directory)
            if (not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid()
                    or stat.S_IMODE(root.st_mode) != 0o700):
                raise ValidationError('access_audit_invalid')
            fd = os.open('access.jsonl', flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise ValidationError('access_audit_invalid')
            except BaseException:
                os.close(fd)
                raise
            return fd
        finally:
            os.close(directory)

    def records(self):
        try:
            fd = self._fd()
            try:
                return self._load(fd)
            finally:
                os.close(fd)
        except (ValueError, TypeError, OSError, RecursionError):
            raise ValidationError('access_audit_invalid') from None

    @classmethod
    def _load(cls, fd):
        os.lseek(fd, 0, os.SEEK_SET)
        data = bytearray()
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 8 * 1024 * 1024:
                raise ValidationError('access_audit_invalid')
        if not data or not data.endswith(b'\n'):
            raise ValidationError('access_audit_invalid')
        records = [parse_json(bytes(line).decode('utf-8')) for line in data.splitlines()]
        return cls._validate_records(records)

    @staticmethod
    def _validate_records(records):
        previous = None
        intents = {}
        results = set()
        for seq, record in enumerate(records):
            _exact(record, {'seq', 'previousSha256', 'kind', 'payload', 'sha256'})
            if (type(record['seq']) is not int or record['seq'] != seq
                    or record['previousSha256'] != previous
                    or record['sha256'] != semantic_digest({k: v for k, v in record.items() if k != 'sha256'})):
                raise ValidationError('access_audit_invalid')
            p = record['payload']
            if seq == 0:
                if record['kind'] != 'audit':
                    raise ValidationError('access_audit_invalid')
                _exact(p, {'schemaVersion', 'projects'})
                if type(p['schemaVersion']) is not int or p['schemaVersion'] != 1 or type(p['projects']) is not dict:
                    raise ValidationError('access_audit_invalid')
                for project, head in p['projects'].items():
                    _id(project)
                    _hash(head)
            elif record['kind'] == 'intent':
                _exact(p, {'operationId', 'accountId', 'generation', 'projectId', 'role', 'action', 'objectId',
                           'priorSeq', 'priorSha256', 'expectedKind', 'expectedPayloadSha256'})
                for key in ('operationId', 'accountId', 'projectId', 'objectId'):
                    _id(p[key])
                if (p['operationId'] in intents or type(p['generation']) is not int or p['generation'] < 1
                        or type(p['priorSeq']) is not int or p['priorSeq'] < 0):
                    raise ValidationError('access_audit_invalid')
                _enum(p['role'], _ROLES)
                _enum(p['action'], _ACTIONS)
                _enum(p['expectedKind'], _KINDS)
                _hash(p['priorSha256'])
                _hash(p['expectedPayloadSha256'])
                intents[p['operationId']] = p
            elif record['kind'] == 'result':
                _exact(p, {'operationId', 'status', 'eventSha256', 'recovered'})
                _id(p['operationId'])
                _enum(p['status'], ('applied', 'not_applied'))
                if (p['operationId'] not in intents or p['operationId'] in results
                        or type(p['recovered']) is not bool):
                    raise ValidationError('access_audit_invalid')
                if p['status'] == 'applied':
                    _hash(p['eventSha256'])
                elif p['eventSha256'] is not None:
                    raise ValidationError('access_audit_invalid')
                results.add(p['operationId'])
            elif record['kind'] == 'access':
                _exact(p, {'accountId', 'projectId', 'role', 'action', 'objectId', 'outcome'})
                for key in ('accountId', 'projectId', 'objectId'):
                    _id(p[key], nullable=True)
                if p['role'] is not None:
                    _enum(p['role'], _ROLES)
                _enum(p['action'], _ACTIONS)
                _enum(p['outcome'], ('authorized', 'denied'))
            else:
                raise ValidationError('access_audit_invalid')
            previous = record['sha256']
        return records

    @staticmethod
    def _record(records, kind, payload):
        record = {'seq': len(records), 'previousSha256': records[-1]['sha256'] if records else None,
                  'kind': kind, 'payload': deepcopy(payload)}
        record['sha256'] = semantic_digest(record)
        Audit._validate_records([*records, record])
        return record

    @staticmethod
    def _write(fd, records, kind, payload):
        record = Audit._record(records, kind, payload)
        encoded = json.dumps(record, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
        if os.fstat(fd).st_size + len(encoded) > 8 * 1024 * 1024:
            raise ValidationError('access_audit_invalid')
        Store._write(fd, record)
        return record

    def append(self, kind, payload):
        try:
            fd = self._fd()
            try:
                record = self._write(fd, self._load(fd), kind, payload)
            finally:
                os.close(fd)
        except (ValueError, TypeError, OSError, RecursionError):
            raise ValidationError('access_audit_invalid') from None
        return record

    def access(self, actor=None, project=None, role=None, action='access_denied', object_id=None, allowed=False):
        return self.append('access', {'accountId': actor['accountId'] if actor else None,
            'projectId': project, 'role': role, 'action': action, 'objectId': object_id,
            'outcome': 'authorized' if allowed else 'denied'})

    def intent(self, actor, project, role, action, object_id, head, kind, payload):
        return self.append('intent', {'operationId': uuid.uuid4().hex, 'accountId': actor['accountId'],
            'generation': actor['generation'], 'projectId': project, 'role': role, 'action': action,
            'objectId': object_id, 'priorSeq': head['seq'], 'priorSha256': head['sha256'],
            'expectedKind': kind, 'expectedPayloadSha256': semantic_digest(payload)})['payload']

    def result(self, intent, event=None, recovered=False):
        return self.append('result', {'operationId': intent['operationId'],
            'status': 'applied' if event else 'not_applied', 'eventSha256': event['sha256'] if event else None,
            'recovered': recovered})

    def reconcile(self, stores):
        """Resolve known interruptions, then reject all unaccounted Store history."""
        try:
            return self._reconcile(stores)
        except (ValueError, TypeError, OSError, KeyError, IndexError, RecursionError):
            raise ValidationError('project_quarantined') from None

    def _reconcile(self, stores):
        if type(stores) is not dict or any(not isinstance(store, Store) for store in stores.values()):
            raise ValidationError('project_quarantined')
        records = self.records()
        sources = {project: store.export_bundle()['events'] for project, store in stores.items()}
        heads = records[0]['payload']['projects']
        if set(heads) != set(sources) or any(heads[p] != sources[p][0]['sha256'] for p in sources):
            raise ValidationError('project_quarantined')
        results = {r['payload']['operationId']: r['payload'] for r in records if r['kind'] == 'result'}
        accounted = {p: 0 for p in sources}
        recoveries = []
        for record in records:
            if record['kind'] != 'intent':
                continue
            intent = record['payload']
            project = intent['projectId']
            events = sources.get(project)
            seq = intent['priorSeq']
            if (events is None or seq != accounted[project] or seq >= len(events)
                    or intent['priorSha256'] != events[seq]['sha256']):
                raise ValidationError('project_quarantined')
            event = events[seq + 1] if seq + 1 < len(events) else None
            result = results.get(intent['operationId'])
            if result is None:
                if event is not None and not self._matches(intent, event):
                    raise ValidationError('project_quarantined')
                recoveries.append((intent, event))
                result = {'status': 'applied' if event else 'not_applied',
                          'eventSha256': event['sha256'] if event else None}
            if result['status'] == 'applied':
                if (event is None or not self._matches(intent, event)
                        or event['sha256'] != result['eventSha256']):
                    raise ValidationError('project_quarantined')
                accounted[project] += 1
        if any(accounted[p] != len(events) - 1 for p, events in sources.items()):
            raise ValidationError('project_quarantined')
        # Check every source and completed receipt before writing recovery evidence.
        # A failure between these appends leaves valid receipts and retryable omissions.
        for intent, event in recoveries:
            self.result(intent, event, recovered=True)
        return {'verified': True, 'sourceRevisions': accounted, 'authenticityEstablished': False}

    @staticmethod
    def _matches(intent, event):
        return (event['seq'] == intent['priorSeq'] + 1 and event['previousSha256'] == intent['priorSha256']
                and event['kind'] == intent['expectedKind']
                and semantic_digest(event['payload']) == intent['expectedPayloadSha256'])
