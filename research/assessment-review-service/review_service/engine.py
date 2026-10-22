"""Compose unchanged assessment stores with current authenticated access and attribution."""
from copy import deepcopy
from pathlib import Path
import json
import os
import secrets
import stat

from workbench.content import prepare_content_manifest
from workbench.demo import make_predictions
from workbench.domain import ValidationError, semantic_digest
from workbench.review import item_id, recording_available, validate_prediction_lock
from workbench.store import Store, parse_json

from .auth import AuthStore
from .audit import Audit
from .fixtures import fixture_manifest, validate_manifest_origin
from .media import create_media, read_fixture

CONTENT_PROJECT = 'content-preparation-a957a9e3291f0d90'
UNAVAILABLE_ANSWER = {'speech': 'unavailable', 'promptMatch': 'unavailable', 'occurrence': 'unavailable',
                      'target': 'unscorable', 'quality': 'unusable', 'notes': ''}
_DIRECTORIES = {'demo-review': 'demo-review', CONTENT_PROJECT: 'content-preparation'}
_PERMISSIONS = {'reviews': {'reviewer-a', 'reviewer-b'}, 'seal': {'reviewer-a', 'reviewer-b'},
    'adjudications': {'adjudicator'}, 'content-reviews': {'coordinator'},
    'prediction-lock': {'coordinator'}, 'withdraw': {'coordinator'}}


def _media_id(manifest, role, attempt_id):
    """Separate playback identifiers from the frozen reviewer-only item namespace."""
    return semantic_digest({'namespace': 'review-service-media-v1',
                            'manifestSha256': semantic_digest(manifest),
                            'role': role, 'attemptId': attempt_id})[:24]


def public_pack_bytes():
    return (Path(__file__).resolve().parents[3] / 'docs/consumer-assessment/proposed-engineering-pack.json').read_bytes()


def _private_directory(path):
    info = Path(path).lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValidationError('unsafe_service_directory')


def _fields(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValidationError('request_fields')


def create_fixture_service(root):
    """Trusted local creation only; invented passwords are written privately, never emitted."""
    root = Path(os.path.abspath(root))
    root.mkdir(mode=0o700, exist_ok=False)
    auth = AuthStore.create(root)
    (root / 'projects').mkdir(mode=0o700)
    stores = {}
    manifest = fixture_manifest()
    for project, directory in _DIRECTORIES.items():
        initial = manifest if project == 'demo-review' else prepare_content_manifest(public_pack_bytes())
        stores[project] = Store.create(root / 'projects' / directory, initial)
    create_media(root / 'projects' / 'demo-review', manifest)
    credentials = {}
    for role in ('coordinator', 'reviewer-a', 'reviewer-b', 'adjudicator'):
        account = 'fixture-' + role
        password = secrets.token_urlsafe(32)
        auth.add_account(account, password)
        auth.assign(account, 'demo-review', role)
        credentials[account] = password
    auth.assign('fixture-coordinator', CONTENT_PROJECT, 'coordinator')
    with auth.lock():
        Audit.create(root, {project: store.export_bundle()['events'][0]['sha256'] for project, store in stores.items()})
    for name, payload in [('fixture-credentials.json', credentials),
                          ('fixture-predictions.json', make_predictions(manifest))]:
        fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            data = json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2).encode() + b'\n'
            remaining = memoryview(data)
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError('private_write_failed')
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
    return Service.open(root)


class Service:
    @classmethod
    def open(cls, root):
        instance = cls(root)
        with instance.auth.lock():
            instance._reconcile()
        return instance

    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        self.auth = AuthStore.open(self.root)
        self.audit = Audit(self.root)
        self.stores = {}
        self.kinds = {}
        _private_directory(self.root / 'projects')
        pack = public_pack_bytes()
        for project, directory in _DIRECTORIES.items():
            path = self.root / 'projects' / directory
            _private_directory(path)
            store = Store.open(path)
            kind = validate_manifest_origin(store.manifest, pack)
            if store.manifest['projectId'] != project:
                raise ValidationError('manifest_origin_invalid')
            self.stores[project] = store
            self.kinds[project] = kind

    def _reconcile(self):
        try:
            _private_directory(self.root / 'projects')
            pack = public_pack_bytes()
            for project, store in self.stores.items():
                _private_directory(store.path)
                if validate_manifest_origin(store.manifest, pack) != self.kinds[project]:
                    raise ValidationError('manifest_origin_invalid')
            return self.audit.reconcile(self.stores)
        except (ValidationError, OSError, KeyError, TypeError) as exc:
            raise ValidationError('project_quarantined') from exc

    def _context(self, actor, project):
        _fields(actor, {'accountId', 'generation'})
        role = self.auth.authorize(actor['accountId'], project, actor['generation'])
        if project not in self.stores or (self.kinds[project] == 'content-preparation' and role != 'coordinator'):
            raise ValidationError('authorization_required')
        self._reconcile()
        return role, self.stores[project]

    def projects(self, actor):
        with self.auth.lock():
            projects = []
            for assignment in self.auth.assignments(actor['accountId']):
                project = assignment['projectId']
                role, store = self._context(actor, project)
                projects.append({'id': project, 'title': store.manifest['title'], 'role': role, 'kind': self.kinds[project]})
            return {'projects': projects}

    def state(self, actor, project):
        with self.auth.lock():
            role, store = self._context(actor, project)
            state = store.snapshot(role)
            aggregate = store.export_bundle()['aggregate']
            attempts = aggregate['manifest']['attempts']
            rows = state['attempts'] if role == 'coordinator' else state['items']
            for row in rows:
                if role in ('reviewer-a', 'reviewer-b'):
                    attempt = next(a for a in attempts if item_id(aggregate['manifest'], role, a['id']) == row['itemId'])
                else:
                    attempt = next(a for a in attempts if a['id'] == row.get('attemptId', row.get('id')))
                available = recording_available(aggregate, attempt)
                row['recordingAvailable'] = available
                row['mediaId'] = _media_id(aggregate['manifest'], role, attempt['id']) if available else None
            state['access'] = {'accountId': actor['accountId'], 'projectId': project, 'role': role,
                              'accountSeparationEnforced': True, 'independentHumansEstablished': False}
            self.audit.access(actor, project, role, 'state_read', allowed=True)
            return state

    def media(self, actor, project, media_id):
        with self.auth.lock():
            try:
                role, store = self._context(actor, project)
                aggregate = store.export_bundle()['aggregate']
                if role == 'adjudicator' and not all(aggregate['seals'].values()):
                    raise ValidationError('fixture_unavailable')
                attempt = next((a for a in aggregate['manifest']['attempts']
                                if _media_id(aggregate['manifest'], role, a['id']) == media_id), None)
                if attempt is None or not recording_available(aggregate, attempt):
                    raise ValidationError('fixture_unavailable')
                data = read_fixture(store.path, aggregate['manifest'], attempt['id'])
                self.audit.access(actor, project, role, 'media_request', attempt['id'], allowed=True)
                return data
            except (ValidationError, OSError, KeyError, TypeError) as exc:
                # No caller-supplied project/item identifiers are copied into failure logs.
                self.audit.access(actor, action='media_request', allowed=False)
                raise ValidationError('fixture_unavailable') from exc

    def export(self, actor, project):
        with self.auth.lock():
            role, store = self._context(actor, project)
            if role != 'coordinator':
                raise ValidationError('authorization_required')
            result = store.export_bundle()
            self.audit.access(actor, project, role, 'export', allowed=True)
            return result

    def preview_predictions(self, actor, project, raw):
        with self.auth.lock():
            role, store = self._context(actor, project)
            if role != 'coordinator':
                raise ValidationError('authorization_required')
            value = parse_json(raw)
            _fields(value, {'synthetic', 'payload', 'expectedSha256'})
            if value['synthetic'] is not True or value != make_predictions(store.manifest) or self.kinds[project] != 'fixture':
                raise ValidationError('fixture_predictions_only')
            validate_prediction_lock(store.manifest, value['payload'], value['expectedSha256'])
            return value

    def mutate(self, actor, project, action, body):
        with self.auth.lock():
            role, store = self._context(actor, project)
            if role not in _PERMISSIONS.get(action, set()):
                raise ValidationError('authorization_required')
            aggregate = store.export_bundle()['aggregate']
            if action == 'reviews':
                _fields(body, {'itemId', 'answer'})
                attempt = next((a for a in aggregate['manifest']['attempts']
                               if item_id(aggregate['manifest'], role, a['id']) == body['itemId']), None)
                if attempt is None:
                    raise ValidationError('review_item_id')
                if not recording_available(aggregate, attempt) and body['answer'] != UNAVAILABLE_ANSWER:
                    raise ValidationError('unavailable_answer_required')
                kind, payload, object_id = 'review', {'reviewerId': role, **deepcopy(body)}, attempt['id']
                operation = lambda: store.submit_review(role, body['itemId'], body['answer'])
            elif action == 'seal':
                _fields(body, set())
                kind, payload, object_id = 'seal', {'reviewerId': role}, role
                operation = lambda: store.seal_reviews(role)
            elif action == 'adjudications':
                _fields(body, {'attemptId', 'answer'})
                attempt = next((a for a in aggregate['manifest']['attempts'] if a['id'] == body['attemptId']), None)
                if attempt is None or not recording_available(aggregate, attempt):
                    raise ValidationError('fixture_unavailable')
                kind, payload, object_id = 'adjudication', deepcopy(body), body['attemptId']
                operation = lambda: store.adjudicate(body['attemptId'], body['answer'])
            elif action == 'content-reviews':
                _fields(body, {'promptId', 'record'})
                _fields(body['record'], {'decision', 'notes', 'reference'})
                record = {**deepcopy(body['record']), 'reviewerId': actor['accountId']}
                kind, payload, object_id = 'content_review', {'promptId': body['promptId'], 'record': record}, body['promptId']
                operation = lambda: store.record_content_review(body['promptId'], record)
            elif action == 'prediction-lock':
                _fields(body, {'payload', 'expectedSha256'})
                expected = make_predictions(store.manifest)
                if self.kinds[project] != 'fixture' or body != {k: expected[k] for k in ('payload', 'expectedSha256')}:
                    raise ValidationError('fixture_predictions_only')
                kind, payload, object_id = 'prediction_lock', deepcopy(body), project
                operation = lambda: store.save_prediction_lock(body['payload'], body['expectedSha256'])
            else:
                _fields(body, {'participantId', 'reason'})
                kind, payload, object_id = 'withdrawal', deepcopy(body), body['participantId']
                operation = lambda: store.withdraw(body['participantId'], body['reason'])
            # Check the inherited transition before creating an intent. This adapter is pinned
            # to the unchanged Store seam; the public mutation validates it again when writing.
            store._apply(deepcopy(aggregate), kind, deepcopy(payload))
            head = store.export_bundle()['events'][-1]
            intent = self.audit.intent(actor, project, role, action, object_id, head, kind, payload)
            try:
                revision = operation()
                event = store.export_bundle()['events'][-1]
                self.audit.result(intent, event)
            except BaseException as exc:
                # A committed source event can survive a missing completion record. The
                # next request/restart reconciles it rather than retrying the write blindly.
                raise ValidationError('operation_outcome_unavailable') from exc
            return {'ok': True, 'revision': revision}
