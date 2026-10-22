"""Authorized asynchronous engineering attempts and private neutral participation."""
from copy import deepcopy
import hashlib
import math
import secrets
import threading
import time

from review_service.auth import SessionManager
from recording_access.journal import available
from workbench.domain import ValidationError, semantic_digest
from .models import JourneyError, CLAIMS, exact, identifier, opaque, integer, prompt_request, public_result, reason, validate_setup, validate_result_binding
from .store import Store


class Journey:
    @classmethod
    def create(cls, root, sessions, vault, prompts, inventory, adapter, *, utc_clock=time.time,
               retention_seconds=86400, max_attempts=128, content_sha256=None):
        instance = cls(root, sessions, vault, adapter, utc_clock=utc_clock)
        pipeline = adapter.declaration()
        validate_setup(prompts, inventory, pipeline)
        with instance.auth.lock():
            vault.reconcile()
            _, source = vault.journal.load()
            for item in inventory:
                record = source['recordings'].get(item['recordingId'])
                if (not record or record['sha256'] != item['sha256']
                        or record['declaration']['source']['kind'] != item['kind']
                        or record['declaration']['subject']['ageYears'] is not None):
                    raise JourneyError('invalid_setup')
            header = {'schemaVersion': 1, 'projectId': vault.project_id, 'createdAt': instance._now(),
                      'prompts': deepcopy(prompts), 'inventory': deepcopy(inventory), 'pipeline': deepcopy(pipeline),
                      'retentionSeconds': retention_seconds, 'maxAttempts': max_attempts, 'contentSha256': content_sha256 or semantic_digest(prompts)}
            instance.store.create(header)
        instance._load_header()
        return instance

    @classmethod
    def open(cls, root, sessions, vault, adapter, *, utc_clock=time.time):
        instance = cls(root, sessions, vault, adapter, utc_clock=utc_clock)
        instance._load_header()
        with instance.auth.lock():
            _, state = instance._refresh()
            for attempt in list(state['attempts'].values()):
                if attempt['status'] == 'pending':
                    instance._terminal(attempt['id'], 'interrupted', 'interrupted')
                    instance.store.delete_result(attempt['id'])
            instance._refresh()
        return instance

    def __init__(self, root, sessions, vault, adapter, *, utc_clock=time.time):
        if not isinstance(sessions, SessionManager) or vault.auth.root != sessions.auth.root or vault.project_id is None:
            raise JourneyError('authentication_required')
        self.sessions, self.auth, self.vault, self.adapter = sessions, sessions.auth, vault, adapter
        self.store, self.utc_clock = Store(root, self.auth), utc_clock
        self._last_now = None
        self._active_attempt = None
        self._worker_lock = threading.Lock()
        self._idle = threading.Event(); self._idle.set()

    def _load_header(self):
        with self.auth.lock():
            _, state = self.store.load()
            self.header = deepcopy(state['header'])
            if self.header['projectId'] != self.vault.project_id: raise JourneyError('project_mismatch')
            self.prompts = {prompt['id']: prompt for prompt in self.header['prompts']}
            self.inventory = {item['id']: item for item in self.header['inventory']}
            self._now(state)

    def _now(self, state=None):
        value = self.utc_clock()
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise JourneyError('clock_unavailable')
        now = int(value)
        integer(now)
        if (self._last_now is not None and now < self._last_now) or (state and now < state['lastAt']):
            raise JourneyError('clock_unavailable')
        self._last_now = now
        return now

    def _actor(self, token, csrf=None, coordinator=False):
        if csrf is not None: self.sessions.verify_csrf(token, csrf)
        actor = self.sessions.actor(token)
        role = self.auth.authorize(actor['accountId'], self.header['projectId'], actor['generation'])
        if coordinator and role != 'coordinator': raise JourneyError('authorization_required')
        return actor, role

    def _pipeline_current(self):
        try:
            return semantic_digest(self.adapter.declaration()) == semantic_digest(self.header['pipeline'])
        except Exception:
            return False

    def _source_available(self, attempt, source, now):
        item = self.inventory[attempt['itemId']]
        record = source['recordings'].get(item['recordingId'])
        return bool(record and record['sha256'] == item['sha256'] and available(record, source, 'inference', now) and available(record, source, 'research', now))

    def _auth_current(self, attempt):
        try:
            actor = attempt['actor']
            return self.auth.authorize(actor['accountId'], self.header['projectId'], actor['generation']) == 'coordinator'
        except ValidationError:
            return False

    def _terminal(self, attempt_id, status, why, result_sha=None):
        event = self.store.append('terminal', {'at': self._now(), 'id': attempt_id, 'status': status,
                                              'reason': why, 'resultSha256': result_sha})
        if result_sha is None:self.store.delete_result(attempt_id)
        if status in ('cancelled','suppressed','interrupted') and self._active_attempt == attempt_id and hasattr(self.adapter,'cancel'):
            self.adapter.cancel()
        return event

    def _discard(self, attempt, why):
        self.store.append('discard', {'at': self._now(), 'id': attempt['id'], 'reason': why})
        self.store.delete_result(attempt['id'])
        self.store.append('forget_complete', {'at': self._now(), 'id': attempt['id']})

    def _refresh(self):
        self.vault.reconcile()
        _, source = self.vault.journal.load()
        records, state = self.store.load()
        pipeline_current = self._pipeline_current()
        now = self._now(state)
        expected = {attempt['id'] + '.json' for attempt in state['attempts'].values()}
        if self.store.files.names('journey-results') - expected: raise JourneyError('journey_quarantined')
        for attempt in list(state['attempts'].values()):
            if attempt['deletePending']:
                self.store.delete_result(attempt['id'])
                self.store.append('forget_complete', {'at': now, 'id': attempt['id']})
                attempt = self.store.load()[1]['attempts'][attempt['id']]
            if attempt['clearRequested']:
                if attempt['status'] == 'pending': self._terminal(attempt['id'], 'cancelled', 'history_cleared')
                if attempt['status'] != 'forgotten': self._discard(attempt, 'history_cleared')
                continue
            if attempt['cancelRequested'] and attempt['status'] == 'pending':
                self._terminal(attempt['id'], 'cancelled', 'cancelled')
                continue
            if attempt['status'] == 'pending':
                why = ('retention_expired' if now >= attempt['retainUntil'] else
                       'pipeline_changed' if not pipeline_current else
                       'authorization_changed' if not self._auth_current(attempt) else
                       'recording_unavailable' if not self._source_available(attempt, source, now) else None)
                if why:
                    self._terminal(attempt['id'], 'suppressed', why)
                    continue
            if attempt['resultSha256'] is not None:
                why = ('retention_expired' if now >= attempt['retainUntil'] else
                       'pipeline_changed' if not pipeline_current else
                       'authorization_changed' if not self._auth_current(attempt) else
                       'recording_unavailable' if not self._source_available(attempt, source, now) else None)
                if why: self._discard(attempt, why)
                else:
                    value = self.store.result(attempt['id'])
                    if semantic_digest(value) != attempt['resultSha256']: raise JourneyError('journey_quarantined')
                    public_result(value)
            elif attempt['status'] != 'pending':
                # Unpublished interrupted results never become historical outputs.
                self.store.delete_result(attempt['id'])
        return self.store.load()

    @staticmethod
    def _action(state, actor, key, kind, body):
        identifier(key)
        previous = state['actions'].get((actor['accountId'], key))
        digest = semantic_digest(body)
        if previous and (previous['kind'] != kind or previous['sha256'] != digest): raise JourneyError('idempotency_conflict')
        return previous, digest

    def start(self, token, csrf, body):
        exact(body, ('idempotencyKey', 'promptId', 'itemId', 'repeatOf'))
        with self.auth.lock():
            self.sessions.verify_csrf(token, csrf)
            actor, _ = self._actor(token, coordinator=True)
            records, state = self._refresh()
            previous, action_sha = self._action(state, actor, body['idempotencyKey'], 'start', body)
            if previous:
                self.sessions.touch(token)
                return {'attemptId': previous['attemptId'], 'status': state['attempts'][previous['attemptId']]['status']}
            if type(body['promptId']) is not str or body['promptId'] not in self.prompts or type(body['itemId']) is not str or body['itemId'] not in self.inventory:
                raise JourneyError('request_fields')
            if hasattr(self.adapter, 'assert_cleanup'): self.adapter.assert_cleanup()
            if not self._pipeline_current(): raise JourneyError('pipeline_changed')
            if body['repeatOf'] is not None:
                parent = state['attempts'].get(body['repeatOf']) if type(body['repeatOf']) is str else None
                if not parent or parent['actor'] != actor or parent['status'] == 'pending': raise JourneyError('repeat_unavailable')
            if not self._worker_lock.acquire(blocking=False): raise JourneyError('assessment_busy')
            self._idle.clear()
            try:
                prompt, item = self.prompts[body['promptId']], self.inventory[body['itemId']]
                request = prompt_request(prompt)
                bindings = {'audioSha256': item['sha256'], 'contentSha256': self.header['contentSha256'],
                            'pipelineSha256': semantic_digest(self.header['pipeline']),
                            'requestSha256': semantic_digest({'prompt': request, 'ageYears': 9, 'pipeline': self.header['pipeline'], 'audioSha256': item['sha256']})}
                attempt_id = secrets.token_hex(16); now = self._now(state)
                planned = {'at': now, 'id': attempt_id, 'actor': actor, 'promptId': prompt['id'], 'itemId': item['id'],
                           'repeatOf': body['repeatOf'], 'idempotencyKey': body['idempotencyKey'], 'actionSha256': action_sha,
                           'bindings': bindings, 'retainUntil': now + self.header['retentionSeconds']}
                self.store.reserve(records, [('planned', planned), ('started', {'at': now, 'id': attempt_id})])
                self.store.append('planned', planned)
                try:
                    _, source = self.vault.journal.load()
                    if not self._source_available(planned, source, self._now()): raise JourneyError('recording_unavailable')
                    if not prompt['supported']:
                        self._terminal(attempt_id, 'unavailable', 'unsupported_target')
                        self._worker_lock.release(); self._idle.set()
                        return {'attemptId': attempt_id, 'status': 'unavailable'}
                    raw = self.vault.read_recording(token, csrf, item['recordingId'], 'inference')
                    if self.vault.read_recording(token, csrf, item['recordingId'], 'research') != raw: raise JourneyError('recording_unavailable')
                    if hashlib.sha256(raw).hexdigest() != item['sha256']: raise JourneyError('recording_unavailable')
                    self.store.append('started', {'at': self._now(), 'id': attempt_id})
                except ValidationError:
                    self._terminal(attempt_id, 'unavailable', 'recording_unavailable')
                    self._worker_lock.release(); self._idle.set()
                    return {'attemptId': attempt_id, 'status': 'unavailable'}
                self._active_attempt = attempt_id
                if hasattr(self.adapter,'prepare'): self.adapter.prepare()
                threading.Thread(target=self._compute, args=(attempt_id, actor, token, csrf, raw, request), daemon=True).start()
                self.sessions.touch(token)
                return {'attemptId': attempt_id, 'status': 'pending'}
            except BaseException:
                if self._worker_lock.locked(): self._worker_lock.release()
                self._idle.set(); raise

    def _compute(self, attempt_id, actor, token, csrf, raw, request):
        try:
            try:
                result = self.adapter.assess(raw, request, age_years=9)
                validate_result_binding(result, raw, request, self.header['pipeline'])
                outcome, why = ('available', None) if result['status'] == 'processed' else ('unavailable', reason(result['reason']))
            except Exception:
                result, outcome, why = None, 'unavailable', 'assessment_unavailable'
            with self.auth.lock():
                _, state = self._refresh(); attempt = state['attempts'][attempt_id]
                if attempt['status'] != 'pending': return
                try:
                    current, _ = self._actor(token, csrf, coordinator=True)
                    if current != actor: raise JourneyError('authorization_required')
                    current_raw = self.vault.read_recording(token, csrf, self.inventory[attempt['itemId']]['recordingId'], 'inference')
                    if self.vault.read_recording(token, csrf, self.inventory[attempt['itemId']]['recordingId'], 'research') != current_raw: raise JourneyError('recording_unavailable')
                    if hashlib.sha256(current_raw).hexdigest() != attempt['bindings']['audioSha256']: raise JourneyError('recording_unavailable')
                    if not self._pipeline_current():
                        self._terminal(attempt_id, 'suppressed', 'pipeline_changed'); return
                except ValidationError:
                    self._terminal(attempt_id, 'suppressed', 'authorization_changed'); return
                _, source = self.vault.journal.load()
                try:
                    current, _ = self._actor(token, csrf, coordinator=True)
                except ValidationError:
                    self._terminal(attempt_id, 'suppressed', 'authorization_changed'); return
                now = self._now()
                if current != actor:
                    self._terminal(attempt_id, 'suppressed', 'authorization_changed'); return
                if now >= attempt['retainUntil']:
                    self._terminal(attempt_id, 'suppressed', 'retention_expired'); return
                if not self._source_available(attempt, source, now):
                    self._terminal(attempt_id, 'suppressed', 'recording_unavailable'); return
                result_sha = self.store.result(attempt_id, result) if result is not None else None
                self._terminal(attempt_id, outcome, why, result_sha)
        except Exception:
            # Durable pending intent is recoverable on reopen, never fabricated.
            pass
        finally:
            self._active_attempt = None
            self._worker_lock.release(); self._idle.set()

    def wait_idle(self, timeout=0): return self._idle.wait(timeout)

    def _row(self, attempt):
        parent = None
        if attempt['repeatOf']:
            _, state = self.store.load(); parent = state['attempts'][attempt['repeatOf']]
        replay = None
        if parent:
            same = {key: attempt['bindings'][key] == parent['bindings'][key] for key in attempt['bindings']}
            replay = {'kind': 'same_bytes_replay' if same['audioSha256'] else 'linked_repeat',
                      'sameAudio': same['audioSha256'], 'sameContent': same['contentSha256'],
                      'samePipeline': same['pipelineSha256'], 'sameRequest': same['requestSha256'], 'independentReassessment': False}
        return {'id': attempt['id'], 'promptId': attempt['promptId'], 'itemId': attempt['itemId'],
                'status': attempt['status'], 'reason': attempt['reason'], 'createdAt': attempt['at'],
                'repeatOf': attempt['repeatOf'], 'replay': replay, 'bindings': deepcopy(attempt['bindings']),
                'result': public_result(self.store.result(attempt['id'])) if attempt['resultSha256'] is not None else None}

    def attempt(self, token, attempt_id):
        opaque(attempt_id)
        with self.auth.lock():
            actor, _ = self._actor(token); _, state = self._refresh()
            attempt = state['attempts'].get(attempt_id)
            if not attempt or attempt['actor']['accountId'] != actor['accountId']: raise JourneyError('unknown_attempt')
            self.sessions.touch(token); return self._row(attempt)

    def state(self, token):
        with self.auth.lock():
            actor, role = self._actor(token); _, state = self._refresh()
            attempts = [a for a in state['attempts'].values() if a['actor']['accountId'] == actor['accountId']]
            _, source = self.vault.journal.load(); now = self._now(state)
            projected = [{key: item[key] for key in ('id', 'label', 'kind', 'sourceWord')} |
                         {'ageKnown': False, 'available': role == 'coordinator' and available(source['recordings'][item['recordingId']], source, 'inference', now) and available(source['recordings'][item['recordingId']], source, 'research', now)}
                         for item in self.inventory.values()]
            result = {'schemaVersion': 1, 'projectId': self.header['projectId'], 'accountId': actor['accountId'], 'role': role,
                      'inventory': projected, 'history': [self._row(a) for a in attempts],
                      'participation': {'planned': len(attempts), 'started': sum(a['started'] for a in attempts),
                                        'terminal': sum(a['status'] != 'pending' for a in attempts),
                                        'manualPractice': sum(p['actor']['accountId'] == actor['accountId'] for p in state['practice']),
                                        'replays': sum(a['repeatOf'] is not None for a in attempts)}, 'claimLimits': deepcopy(CLAIMS)}
            self.sessions.touch(token); return result

    def practice(self, token, csrf, body):
        exact(body, ('idempotencyKey', 'promptId', 'attemptId'))
        with self.auth.lock():
            self.sessions.verify_csrf(token, csrf)
            actor, _ = self._actor(token); _, state = self._refresh()
            previous, digest = self._action(state, actor, body['idempotencyKey'], 'practice', body)
            if not previous:
                if type(body['promptId']) is not str or body['promptId'] not in self.prompts: raise JourneyError('request_fields')
                if body['attemptId'] is not None:
                    attempt = state['attempts'].get(body['attemptId']) if type(body['attemptId']) is str else None
                    if not attempt or attempt['actor']['accountId'] != actor['accountId'] or attempt['promptId'] != body['promptId']: raise JourneyError('unknown_attempt')
                self.store.append('practice', {'at': self._now(), 'actor': actor, **body, 'actionSha256': digest})
            self.sessions.touch(token); return {'ok': True, 'participationOnly': True}

    def cancel(self, token, csrf, body):
        exact(body, ('idempotencyKey', 'attemptId')); opaque(body['attemptId'])
        with self.auth.lock():
            self.sessions.verify_csrf(token, csrf)
            actor, _ = self._actor(token); _, state = self._refresh()
            previous, digest = self._action(state, actor, body['idempotencyKey'], 'cancel', body)
            attempt = state['attempts'].get(body['attemptId'])
            if not attempt or attempt['actor'] != actor: raise JourneyError('unknown_attempt')
            if not previous:
                if attempt['status'] != 'pending': raise JourneyError('attempt_finished')
                self.store.append('cancel_action', {'at': self._now(), 'actor': actor, **body, 'actionSha256': digest})
                self._terminal(attempt['id'], 'cancelled', 'cancelled')
            self.sessions.touch(token)
            return self._row(self.store.load()[1]['attempts'][attempt['id']])

    def clear_history(self, token, csrf, body):
        exact(body, ('idempotencyKey',))
        with self.auth.lock():
            self.sessions.verify_csrf(token, csrf)
            actor, _ = self._actor(token); _, state = self._refresh()
            previous, digest = self._action(state, actor, body['idempotencyKey'], 'clear', body)
            own = [a for a in state['attempts'].values() if a['actor']['accountId'] == actor['accountId'] and a['status'] not in ('forgotten', 'suppressed')]
            if not previous:
                self.store.append('clear_action', {'at': self._now(), 'actor': actor, **body, 'actionSha256': digest, 'targets': [a['id'] for a in own]})
            self._refresh()
            self.sessions.touch(token)
            return {'ok': True, 'derivedHistoryForgotten': True, 'denominatorRetained': True, 'secureEraseClaim': False}

    def cleanup(self):
        with self.auth.lock():
            self._refresh()
            return {'ok': True}

    def export(self, token):
        state = self.state(token)
        return {'schemaVersion': 1, 'projectId': state['projectId'], 'accountId': state['accountId'],
                'history': state['history'], 'participation': state['participation'], 'claimLimits': deepcopy(CLAIMS)}

    def private_reference(self, token, csrf, item_id):
        opaque(item_id, 24)
        with self.auth.lock():
            self._actor(token)
            item = self.inventory.get(item_id)
            if not item: raise JourneyError('recording_unavailable')
            return self.vault.read_recording(token, csrf, item['recordingId'], 'review')
