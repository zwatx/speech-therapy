"""Session-authorized recording lifecycle over one private local auth root."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import math
import os
import secrets
import time

from workbench.domain import semantic_digest
from review_service.auth import SessionManager

from .files import Files
from .journal import Journal, available, eligible
from .models import (VaultError, PURPOSES, CLAIM_FIELDS, MAX_UTC, MAX_WAV_BYTES, exact, integer,
                     identifier, recording_id, sha, text, validate_declaration, permission_allowed, inspect_wav)


class Vault:
    @classmethod
    def create(cls, root, sessions, project_id, *, utc_clock=time.time):
        instance = cls(root, sessions, utc_clock=utc_clock)
        identifier(project_id)
        with instance.auth.lock():
            now = instance._now()
            instance.files.create_directory('recordings')
            instance.files.create_directory('staging')
            instance.journal.create({'schemaVersion': 1, 'vaultId': secrets.token_hex(16),
                                     'projectId': project_id, 'createdAt': now})
        return cls.open(root, sessions, utc_clock=utc_clock)

    @classmethod
    def open(cls, root, sessions, *, utc_clock=time.time):
        instance = cls.open_maintenance(root, sessions, utc_clock=utc_clock)
        with instance.auth.lock():
            instance._reconcile()
        return instance

    @classmethod
    def open_maintenance(cls, root, sessions, *, utc_clock=time.time):
        """Trusted owner recovery handle; protected operations still reconcile."""
        instance = cls(root, sessions, utc_clock=utc_clock)
        with instance.auth.lock():
            _, state = instance.journal.load()
            instance.project_id = state['header']['projectId']
            instance._now(state)
            instance.files.names('recordings')
            instance.files.names('staging')
        return instance

    def __init__(self, root, sessions, *, utc_clock=time.time):
        if not isinstance(sessions, SessionManager):
            raise VaultError('authentication_required')
        self.sessions, self.auth, self.utc_clock = sessions, sessions.auth, utc_clock
        self.files = Files(root, self.auth)
        self.journal = Journal(self.files)
        self._last_now = None

    def _now(self, state=None):
        value = self.utc_clock()
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= MAX_UTC:
            raise VaultError('clock_unavailable')
        now = int(value)
        if (self._last_now is not None and now < self._last_now) or (state and now < state['lastAt']):
            raise VaultError('clock_unavailable')
        self._last_now = now
        return now

    @staticmethod
    def _stage(rid):
        recording_id(rid)
        return rid + '.stage'

    @staticmethod
    def _final(rid):
        recording_id(rid)
        return rid + '.wav'

    def _asset(self, child, name, record, links=(1,)):
        with self.files.file(child, name, os.O_RDONLY, links=links) as fd:
            raw = self.files.read(fd, MAX_WAV_BYTES)
        details = inspect_wav(raw)
        if any(details[field] != record[field] for field in ('sha256', 'frames', 'byteLength')):
            raise VaultError('vault_quarantined')
        return raw

    def _reconcile(self):
        records, state = self.journal.load()
        self._now(state)
        finals, stages = self.files.names('recordings'), self.files.names('staging')
        expected_finals, expected_stages = set(), set()
        for rid, record in state['recordings'].items():
            final, stage = self._final(rid), self._stage(rid)
            if record['lifecycle'] == 'available':
                expected_finals.add(final)
                if final not in finals:
                    raise VaultError('vault_quarantined')
                self._asset('recordings', final, record)
            elif record['lifecycle'] == 'import_pending':
                expected_finals.add(final)
                expected_stages.add(stage)
                if final not in finals and stage not in stages:
                    raise VaultError('vault_quarantined')
            elif record['lifecycle'] == 'pending_delete':
                expected_finals.add(final)
                expected_stages.add(stage)
        for rid, orphan in state['orphans'].items():
            if orphan['lifecycle'] == 'pending_delete':
                expected_stages.add(self._stage(rid))
        if finals - expected_finals or stages - expected_stages:
            raise VaultError('vault_quarantined')
        for rid, record in state['recordings'].items():
            if record['lifecycle'] == 'import_pending':
                final, stage = self._final(rid), self._stage(rid)
                if eligible(record, state, self._now(state)):
                    # Lost storage permission never authorizes a recovered copy.
                    self._validate_pending(record, rid, finals, stages)
                    continue
                if final in finals and stage in stages:
                    with self.files.directory('staging') as a, self.files.directory('recordings') as b:
                        left = os.stat(stage, dir_fd=a, follow_symlinks=False)
                        right = os.stat(final, dir_fd=b, follow_symlinks=False)
                        if (left.st_dev, left.st_ino, left.st_nlink) != (right.st_dev, right.st_ino, 2):
                            raise VaultError('vault_quarantined')
                    self._asset('staging', stage, record, links=(2,))
                    self.files.unlink('staging', stage, links=(2,))
                elif stage in stages:
                    self._asset('staging', stage, record)
                    self.files.promote(stage, final)
                self._asset('recordings', final, record)
                self.journal.append('import_complete', {'at': self._now(state), 'recordingId': rid, 'recovered': True})
            elif record['lifecycle'] == 'pending_delete':
                self._delete_record(rid, record)
                self.journal.append('purge_complete', {'at': self._now(state), 'recordingId': rid, 'recovered': True})
        for rid, orphan in state['orphans'].items():
            if orphan['lifecycle'] == 'pending_delete':
                self._delete_orphan(rid, orphan)
                self.journal.append('orphan_delete_complete', {'at': self._now(state), 'recordingId': rid, 'recovered': True})
        return self.journal.load()

    def reconcile(self):
        with self.auth.lock():
            records, state = self._reconcile()
            return {'reconciled': True, 'revision': records[-1]['seq'], 'recordings': len(state['recordings']),
                    'orphanDeletionAttempts': len(state['orphans']), 'authenticProvenanceEstablished': False}

    def import_recording(self, wav_bytes, declaration):
        details = inspect_wav(wav_bytes)
        declaration = validate_declaration(declaration)
        if details['sha256'] != declaration['expectedSha256']:
            raise VaultError('recording_sha_mismatch')
        with self.auth.lock():
            records, state = self._reconcile()
            now = self._now(state)
            if (declaration['retainUntil'] <= now or declaration['subject']['id'] in state['withdrawn']
                    or not permission_allowed(declaration, 'storage', now)):
                raise VaultError('recording_unavailable')
            rid = secrets.token_hex(16)
            intent = {'at': now, 'recordingId': rid, **{k: details[k] for k in ('sha256', 'frames', 'byteLength')},
                      'declaration': declaration}
            # Validate and reserve before staging. A pre-intent interrupted stage is
            # deliberately quarantined; it has no authority to become an import.
            from .journal import apply
            apply(deepcopy(state), 'import_intent', intent)
            complete = {'at': now, 'recordingId': rid, 'recovered': False}
            self.journal.reserve(records, [('import_intent', intent), ('import_complete', complete)])
            with self.files.file('staging', self._stage(rid), os.O_WRONLY | os.O_CREAT | os.O_EXCL) as fd:
                self.files.write(fd, wav_bytes)
            with self.files.directory('staging') as directory:
                os.fsync(directory)
            self._asset('staging', self._stage(rid), intent)
            self.journal.append('import_intent', intent)
            self.files.promote(self._stage(rid), self._final(rid))
            self._asset('recordings', self._final(rid), intent)
            self.journal.append('import_complete', complete)
            return {'recordingId': rid, **details, 'imported': True}

    @contextmanager
    def _protected(self, token, csrf, *, coordinator=False, assets=True):
        with self.auth.lock():
            self.sessions.verify_csrf(token, csrf)
            actor = self.sessions.actor(token)
            role = self.auth.authorize(actor['accountId'], self.project_id, actor['generation'])
            if coordinator and role != 'coordinator':
                raise VaultError('authorization_required')
            actor = {**actor, 'role': role}
            records, state = self._reconcile() if assets else self.journal.load()
            self._now(state)
            yield actor, records, state
            self.sessions.touch(token)

    def read_recording(self, token, csrf, recording_id, purpose):
        with self._protected(token, csrf) as (actor, _, state):
            if type(purpose) is not str or purpose not in ('review', 'research', 'inference'):
                raise VaultError('recording_unavailable')
            if actor['role'] != 'coordinator' and purpose != 'review':
                raise VaultError('authorization_required')
            record = state['recordings'].get(recording_id) if type(recording_id) is str else None
            now = self._now(state)
            if not record or not available(record, state, purpose, now):
                raise VaultError('recording_unavailable')
            raw = self._asset('recordings', self._final(recording_id), record)
            self.journal.append('access', {'at': now, 'recordingId': recording_id, 'purpose': purpose, 'actor': actor})
            return raw

    def _validate_pending(self, record, rid, finals, stages):
        final, stage = self._final(rid), self._stage(rid)
        both = final in finals and stage in stages
        if both:
            with self.files.directory('staging') as a, self.files.directory('recordings') as b:
                left = os.stat(stage, dir_fd=a, follow_symlinks=False)
                right = os.stat(final, dir_fd=b, follow_symlinks=False)
                if (left.st_dev, left.st_ino, left.st_nlink) != (right.st_dev, right.st_ino, 2):
                    raise VaultError('vault_quarantined')
        for child, name, present in (('recordings', final, final in finals), ('staging', stage, stage in stages)):
            if present:
                self._asset(child, name, record, links=(2,) if both else (1,))

    def _delete_record(self, rid, record):
        finals, stages = self.files.names('recordings'), self.files.names('staging')
        self._validate_pending(record, rid, finals, stages)
        self.files.unlink('recordings', self._final(rid), missing_ok=True, links=(1, 2))
        self.files.unlink('staging', self._stage(rid), missing_ok=True)

    def _plan(self, records, state, now, kind, entries):
        plan = {'schemaVersion': 1, 'kind': kind, 'vaultId': state['header']['vaultId'],
                'projectId': self.project_id, 'headSha256': records[-1]['sha256'],
                'asOf': now, 'eligible': entries}
        return {**plan, 'planSha256': semantic_digest(plan)}

    def _purge_plan(self, records, state, now):
        entries = [{'recordingId': rid, 'reasons': reasons}
                   for rid, record in sorted(state['recordings'].items())
                   if (reasons := eligible(record, state, now))]
        return self._plan(records, state, now, 'recording_purge', entries)

    def purge_report(self):
        """Trusted owner dry run; deliberately writes no journal event."""
        with self.auth.lock():
            records, state = self.journal.load()
            return self._purge_plan(records, state, self._now(state))

    def _check_plan(self, plan, records, state, kind):
        exact(plan, ('schemaVersion', 'kind', 'vaultId', 'projectId', 'headSha256', 'asOf', 'eligible', 'planSha256'))
        integer(plan['asOf'])
        now = self._now(state)
        if plan['kind'] != kind or plan['asOf'] > now:
            raise VaultError('stale_purge_plan')
        expected = (self._purge_plan(records, state, plan['asOf']) if kind == 'recording_purge'
                    else self._orphan_plan(records, state, plan['asOf']))
        if semantic_digest(plan) != semantic_digest(expected):
            raise VaultError('stale_purge_plan')
        return now

    def purge(self, plan):
        """Trusted owner action; durable tombstone precedes managed unlink."""
        with self.auth.lock():
            records, state = self.journal.load()
            now = self._check_plan(plan, records, state, 'recording_purge')
            events = []
            for entry in plan['eligible']:
                rid = entry['recordingId']
                if not eligible(state['recordings'][rid], state, now):
                    raise VaultError('stale_purge_plan')
                events += [('purge_intent', {'at': now, 'recordingId': rid, 'planSha256': plan['planSha256']}),
                           ('purge_complete', {'at': now, 'recordingId': rid, 'recovered': False})]
            self.journal.reserve(records, events)
            for entry in plan['eligible']:
                rid = entry['recordingId']
                self.journal.append('purge_intent', {'at': now, 'recordingId': rid, 'planSha256': plan['planSha256']})
                self._delete_record(rid, state['recordings'][rid])
                self.journal.append('purge_complete', {'at': now, 'recordingId': rid, 'recovered': False})
            return {'purged': len(plan['eligible']), 'planSha256': plan['planSha256'], 'secureErasureEstablished': False}

    def _orphan_plan(self, records, state, now):
        known = {self._stage(rid) for rid in state['recordings']} | {self._stage(rid) for rid in state['orphans']}
        entries = []
        for name in sorted(self.files.names('staging') - known):
            if not name.endswith('.stage'):
                raise VaultError('vault_quarantined')
            rid = name[:-6]
            recording_id(rid)
            with self.files.file('staging', name, os.O_RDONLY) as fd:
                raw = self.files.read(fd, MAX_WAV_BYTES)
            entries.append({'recordingId': rid, 'sha256': hashlib.sha256(raw).hexdigest(), 'byteLength': len(raw)})
        return self._plan(records, state, now, 'orphan_purge', entries)

    def orphan_report(self):
        with self.auth.lock():
            records, state = self.journal.load()
            return self._orphan_plan(records, state, self._now(state))

    def purge_orphans(self, plan):
        with self.auth.lock():
            records, state = self.journal.load()
            now = self._check_plan(plan, records, state, 'orphan_purge')
            if len(state['orphans']) + len(plan['eligible']) > 256:
                raise VaultError('vault_capacity')
            events = []
            for entry in plan['eligible']:
                events += [('orphan_delete_intent', {'at': now, **entry, 'planSha256': plan['planSha256']}),
                           ('orphan_delete_complete', {'at': now, 'recordingId': entry['recordingId'], 'recovered': False})]
            self.journal.reserve(records, events)
            for entry in plan['eligible']:
                self.journal.append('orphan_delete_intent', {'at': now, **entry, 'planSha256': plan['planSha256']})
                self._delete_orphan(entry['recordingId'], entry)
                self.journal.append('orphan_delete_complete', {'at': now, 'recordingId': entry['recordingId'], 'recovered': False})
            return {'purged': len(plan['eligible']), 'planSha256': plan['planSha256'], 'secureErasureEstablished': False}

    def restrict(self, token, csrf, recording_id, purpose, reason):
        with self._protected(token, csrf, coordinator=True, assets=False) as (actor, _, state):
            text(reason, 500)
            record = state['recordings'].get(recording_id) if type(recording_id) is str else None
            if not record or record['lifecycle'] not in ('available', 'import_pending') or type(purpose) is not str or purpose not in PURPOSES or purpose in record['restrictions']:
                raise VaultError('recording_unavailable')
            self.journal.append('restriction', {'at': self._now(state), 'recordingId': recording_id,
                                                'purpose': purpose, 'reason': reason, 'actor': actor})
            return {'restricted': True, 'recordingId': recording_id, 'purpose': purpose}

    def withdraw_subject(self, token, csrf, subject_id, reason):
        with self._protected(token, csrf, coordinator=True, assets=False) as (actor, _, state):
            text(reason, 500)
            if type(subject_id) is not str or subject_id not in state['subjects'] or subject_id in state['withdrawn']:
                raise VaultError('recording_unavailable')
            self.journal.append('withdrawal', {'at': self._now(state), 'subjectId': subject_id, 'reason': reason, 'actor': actor})
            return {'withdrawn': True}

    def export_metadata(self, token, csrf):
        with self._protected(token, csrf, coordinator=True) as (actor, records, state):
            now = self._now(state)
            event = self.journal.append('metadata_export', {'at': now, 'actor': actor})
            projected = []
            for rid, record in sorted(state['recordings'].items()):
                declaration = record['declaration']
                projected.append({'recordingId': rid, 'subjectRef': semantic_digest({'vaultId': state['header']['vaultId'],
                                   'subjectId': declaration['subject']['id']}), 'sourceKind': declaration['source']['kind'],
                                  'sha256': record['sha256'], 'sourceOriginalSha256': declaration['source']['originalSha256'],
                                  'provenanceEvidenceSha256': declaration['source']['provenanceEvidenceSha256'],
                                  'byteLength': record['byteLength'], 'frames': record['frames'],
                                  'durationMs': record['frames'] * 1000 // 16000,
                                  'ageYearsDeclared': declaration['subject']['ageYears'], 'retainUntil': declaration['retainUntil'],
                                  'lifecycle': record['lifecycle'], 'restrictions': sorted(record['restrictions']),
                                  'purgeReasons': eligible(record, state, now),
                                  'permissions': {purpose: {key: {field: declaration['permissions'][purpose][key][field]
                                                      for field in ('status', 'expiresAt')} for key in ('rights', 'consent')}
                                                  for purpose in PURPOSES}})
            return {'schemaVersion': 1, 'projectId': self.project_id, 'vaultId': state['header']['vaultId'],
                    'revision': event['seq'], 'headSha256': event['sha256'], 'asOf': now, 'records': projected,
                    'counts': {'recordingIntentDenominator': len(state['recordings']),
                               'completedImports': sum(record['completedImport'] for record in state['recordings'].values()),
                               'purgedRecordings': sum(record['lifecycle'] == 'purged' for record in state['recordings'].values()),
                               'accessDeliveryAttempts': state['accessCount'], 'metadataExports': state['exportCount'] + 1,
                               'orphanDeletionAttempts': len(state['orphans'])},
                    'claimLimits': {name: False for name in CLAIM_FIELDS},
                    'managedCopiesOnly': True, 'secureErasureEstablished': False}

    def _delete_orphan(self, rid, orphan):
        name = self._stage(rid)
        if name in self.files.names('staging'):
            with self.files.file('staging', name, os.O_RDONLY) as fd:
                raw = self.files.read(fd, MAX_WAV_BYTES)
            if len(raw) != orphan['byteLength'] or hashlib.sha256(raw).hexdigest() != orphan['sha256']:
                raise VaultError('vault_quarantined')
        self.files.unlink('staging', name, missing_ok=True)
