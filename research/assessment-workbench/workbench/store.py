"""Private append-only project store. Public projections are derived on every read."""
from copy import deepcopy
from pathlib import Path
import fcntl
import json
import os
import stat
import re

from .domain import ValidationError, semantic_digest, validate_manifest


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError('duplicate_json_key')
        result[key] = value
    return result


def parse_json(value):
    try:
        return json.loads(value, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValidationError('nonfinite_json')))
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ValidationError('invalid_json') from exc


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _exact(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise ValidationError('event_fields')


def _safe_id(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) is None:
        raise ValidationError('invalid_id')


def _note(value, required=True):
    if type(value) is not str or (required and not value.strip()) or len(value) > 2000:
        raise ValidationError('invalid_notes')


class Store:
    @classmethod
    def create(cls, path, manifest):
        manifest = validate_manifest(manifest)
        path = Path(path)
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        try:
            fd = os.open(path / 'events.jsonl', os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                record = {'seq': 0, 'previousSha256': None, 'kind': 'project', 'payload': manifest}
                record['sha256'] = semantic_digest(record)
                cls._write(fd, record)
            finally:
                os.close(fd)
        except BaseException:
            # Keep failed creation evidence; never silently reuse or reset a project.
            raise
        return cls.open(path)

    @classmethod
    def open(cls, path):
        instance = cls(path)
        instance._read()
        return instance

    def __init__(self, path):
        self.path = Path(path)

    def _fd(self):
        info = self.path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValidationError('unsafe_project_directory')
        fd = os.open(self.path / 'events.jsonl', os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            os.close(fd)
            raise ValidationError('unsafe_project_journal')
        return fd

    @staticmethod
    def _write(fd, record):
        remaining = _encode(record) + b'\n'
        if os.fstat(fd).st_size + len(remaining) > 16 * 1024 * 1024:
            raise ValidationError('project_journal_too_large')
        while remaining:
            count = os.write(fd, remaining)
            if count <= 0:
                raise OSError('journal_write_failed')
            remaining = remaining[count:]
        os.fsync(fd)

    def _load(self, fd):
        os.lseek(fd, 0, os.SEEK_SET)
        data = b''
        while True:
            part = os.read(fd, 65536)
            if not part:
                break
            data += part
            if len(data) > 16 * 1024 * 1024:
                raise ValidationError('project_journal_too_large')
        if not data or not data.endswith(b'\n'):
            raise ValidationError('corrupt_project_journal')
        events = []
        previous = None
        for seq, line in enumerate(data.splitlines()):
            record = parse_json(line)
            if not isinstance(record, dict) or set(record) != {'seq', 'previousSha256', 'kind', 'payload', 'sha256'}:
                raise ValidationError('corrupt_project_journal')
            if type(record['seq']) is not int or record['seq'] != seq or record['previousSha256'] != previous:
                raise ValidationError('corrupt_project_journal')
            body = {key: value for key, value in record.items() if key != 'sha256'}
            if semantic_digest(body) != record['sha256']:
                raise ValidationError('corrupt_project_journal')
            previous = record['sha256']
            events.append(record)
        if events[0]['kind'] != 'project':
            raise ValidationError('corrupt_project_journal')
        aggregate = {'manifest': validate_manifest(events[0]['payload']),
                     'reviews': {'reviewer-a': {}, 'reviewer-b': {}}, 'seals': {'reviewer-a': False, 'reviewer-b': False},
                     'adjudications': {}, 'contentReviews': [], 'predictionLock': None, 'withdrawals': []}
        for event in events[1:]:
            self._apply(aggregate, event['kind'], event['payload'])
        return aggregate, events

    def _read(self):
        fd = self._fd()
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            return self._load(fd)
        finally:
            os.close(fd)

    @property
    def manifest(self):
        return deepcopy(self._read()[0]['manifest'])

    @property
    def revision(self):
        return self._read()[1][-1]['seq']

    def _apply(self, aggregate, kind, payload):
        from .review import REVIEWERS, item_id, validate_answer, validate_adjudication, validate_prediction_lock
        if kind == 'review':
            _exact(payload, {'reviewerId', 'itemId', 'answer'})
            reviewer = payload['reviewerId']
            if type(reviewer) is not str or reviewer not in REVIEWERS:
                raise ValidationError('reviewer_id')
            if aggregate['seals'][reviewer]:
                raise ValidationError('reviews_sealed')
            attempt_id = next((a['id'] for a in aggregate['manifest']['attempts']
                               if item_id(aggregate['manifest'], reviewer, a['id']) == payload['itemId']), None)
            if attempt_id is None:
                raise ValidationError('review_item_id')
            if attempt_id in aggregate['reviews'][reviewer]:
                raise ValidationError('review_already_saved')
            answer = validate_answer(payload['answer'])
            aggregate['reviews'][reviewer][attempt_id] = {'answer': answer, 'sha256': semantic_digest(answer)}
        elif kind == 'prediction_lock':
            _exact(payload, {'payload', 'expectedSha256'})
            if aggregate['predictionLock'] is not None:
                raise ValidationError('predictions_already_locked')
            aggregate['predictionLock'] = validate_prediction_lock(aggregate['manifest'], payload['payload'], payload['expectedSha256'])
        elif kind == 'withdrawal':
            _exact(payload, {'participantId', 'reason'})
            if not any(p['id'] == payload['participantId'] for p in aggregate['manifest']['participants']):
                raise ValidationError('participant_id')
            _note(payload['reason'])
            if any(p['participantId'] == payload['participantId'] for p in aggregate['withdrawals']):
                raise ValidationError('already_withdrawn')
            aggregate['withdrawals'].append(deepcopy(payload))
        elif kind == 'content_review':
            _exact(payload, {'promptId', 'record'})
            if not any(p['id'] == payload['promptId'] for p in aggregate['manifest']['prompts']):
                raise ValidationError('prompt_id')
            record = payload['record']
            _exact(record, {'decision', 'reviewerId', 'notes', 'reference'})
            if type(record['decision']) is not str or record['decision'] not in ('accepted', 'revise', 'pending'):
                raise ValidationError('content_decision')
            _safe_id(record['reviewerId'])
            _note(record['notes'], required=False)
            reference = record['reference']
            if reference is not None:
                _exact(reference, {'id', 'version', 'sha256', 'rights'})
                _safe_id(reference['id'])
                _safe_id(reference['version'])
                if type(reference['sha256']) is not str or re.fullmatch(r'[0-9a-f]{64}', reference['sha256']) is None:
                    raise ValidationError('reference_sha256')
                if type(reference['rights']) is not str or reference['rights'] not in ('allowed', 'denied', 'unknown'):
                    raise ValidationError('reference_rights')
            aggregate['contentReviews'].append(deepcopy(payload))
        elif kind == 'seal':
            _exact(payload, {'reviewerId'})
            reviewer = payload['reviewerId']
            if type(reviewer) is not str or reviewer not in REVIEWERS:
                raise ValidationError('reviewer_id')
            if aggregate['seals'][reviewer]:
                raise ValidationError('reviews_sealed')
            if set(aggregate['reviews'][reviewer]) != {a['id'] for a in aggregate['manifest']['attempts']}:
                raise ValidationError('reviews_incomplete')
            aggregate['seals'][reviewer] = True
        elif kind == 'adjudication':
            _exact(payload, {'attemptId', 'answer'})
            answer = validate_adjudication(aggregate, payload['attemptId'], payload['answer'])
            if payload['attemptId'] in aggregate['adjudications']:
                raise ValidationError('adjudication_already_saved')
            aggregate['adjudications'][payload['attemptId']] = {'answer': answer, 'sha256': semantic_digest(answer)}
        else:
            raise ValidationError('unknown_event')

    def _mutate(self, kind, payload):
        # The payload is copied before lock acquisition, so callers cannot modify an in-flight write.
        payload = deepcopy(payload)
        semantic_digest(payload)
        fd = self._fd()
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            aggregate, events = self._load(fd)
            self._apply(aggregate, kind, payload)
            record = {'seq': len(events), 'previousSha256': events[-1]['sha256'], 'kind': kind, 'payload': payload}
            record['sha256'] = semantic_digest(record)
            self._write(fd, record)
            return record['seq']
        finally:
            os.close(fd)

    def submit_review(self, reviewerId, itemId, answer):
        return self._mutate('review', {'reviewerId': reviewerId, 'itemId': itemId, 'answer': answer})

    def save_prediction_lock(self, payload, expectedSha):
        return self._mutate('prediction_lock', {'payload': payload, 'expectedSha256': expectedSha})

    def withdraw(self, participantId, reason):
        return self._mutate('withdrawal', {'participantId': participantId, 'reason': reason})

    def record_content_review(self, promptId, record):
        return self._mutate('content_review', {'promptId': promptId, 'record': record})

    def export_bundle(self):
        from .reports import build_report
        from .domain import split_diagnostics
        aggregate, events = self._read()
        body = {'schemaVersion': 1, 'aggregate': aggregate, 'events': events,
                'report': build_report(aggregate), 'splitDiagnostics': split_diagnostics(aggregate['manifest'])}
        return {**deepcopy(body), 'sha256': semantic_digest(body)}

    def seal_reviews(self, reviewerId):
        return self._mutate('seal', {'reviewerId': reviewerId})

    def adjudicate(self, attemptId, answer):
        return self._mutate('adjudication', {'attemptId': attemptId, 'answer': answer})

    def snapshot(self, role='coordinator'):
        from .review import REVIEWERS, reviewer_projection, adjudicator_projection, recording_available
        aggregate, _ = self._read()
        if role in REVIEWERS:
            return reviewer_projection(aggregate, role)
        if role == 'adjudicator':
            return adjudicator_projection(aggregate)
        if role == 'coordinator':
            from .domain import split_diagnostics
            from .reports import build_report
            manifest = aggregate['manifest']
            prompts = {p['id']: p for p in manifest['prompts']}
            report = build_report(aggregate)
            rows = []
            for attempt in manifest['attempts']:
                prompt = prompts[attempt['promptId']]
                rows.append({'id': attempt['id'], 'promptId': prompt['id'], 'word': prompt['word'],
                             'targetPhone': prompt['targetPhone'], 'participantId': attempt['participantId'],
                             'split': attempt['split'], 'terminal': attempt['terminal'], 'admission': report['admissionByAttemptId'][attempt['id']],
                             'reviewA': aggregate['reviews']['reviewer-a'].get(attempt['id']),
                             'reviewB': aggregate['reviews']['reviewer-b'].get(attempt['id']),
                             'adjudication': aggregate['adjudications'].get(attempt['id']),
                             'recordingAvailable': recording_available(aggregate, attempt)})
            lock = aggregate['predictionLock']
            return deepcopy({'project': {'title': manifest['title'], 'mode': manifest['mode'], 'task': manifest['task']},
                             'prompts': manifest['prompts'], 'attempts': rows, 'report': report,
                             'splitDiagnostics': split_diagnostics(manifest), 'contentReviews': aggregate['contentReviews'],
                             'seals': aggregate['seals'], 'predictionLock': {'sha256': lock['sha256'], 'model': lock['payload']['model']} if lock else None})
        raise ValidationError('view_role')


def verify_export(bundle):
    """Verify integrity and replay all exported events; hashes are not signatures."""
    import tempfile
    _exact(bundle, {'schemaVersion', 'aggregate', 'events', 'report', 'splitDiagnostics', 'sha256'})
    if type(bundle['schemaVersion']) is not int or bundle['schemaVersion'] != 1:
        raise ValidationError('export_schema')
    body = {key: value for key, value in bundle.items() if key != 'sha256'}
    if semantic_digest(body) != bundle['sha256'] or type(bundle['events']) is not list or not bundle['events']:
        raise ValidationError('export_integrity')
    with tempfile.TemporaryDirectory(prefix='assessment-export-') as directory:
        path = Path(directory) / 'replay'
        path.mkdir(mode=0o700)
        fd = os.open(path / 'events.jsonl', os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            for record in bundle['events']:
                Store._write(fd, record)
        finally:
            os.close(fd)
        store = Store.open(path)
        if store.export_bundle() != bundle:
            raise ValidationError('export_replay_mismatch')
        return {'verified': True, 'sha256': bundle['sha256'], 'revision': store.revision,
                'attempts': len(store.manifest['attempts']), 'authenticityEstablished': False}
