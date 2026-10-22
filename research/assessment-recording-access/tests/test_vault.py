from copy import deepcopy
import hashlib
import io
from pathlib import Path
import secrets
import tempfile
import unittest
import wave

from review_service.auth import AuthStore, SessionManager, AuthError
from recording_access import Vault, VaultError


def pcm():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\x00\x00' * 3200)
    return stream.getvalue()


def declaration(raw):
    granted = {'status': 'granted', 'expiresAt': 2000000000, 'evidenceSha256': 'a' * 64,
               'declaration': 'Invented test permission statement; no actual authority verified'}
    unknown = {'status': 'unknown', 'expiresAt': None, 'evidenceSha256': None, 'declaration': None}
    return {'schemaVersion': 1, 'expectedSha256': hashlib.sha256(raw).hexdigest(),
            'source': {'kind': 'invented_fixture', 'description': 'Generated silence, invented workflow only',
                       'originalSha256': hashlib.sha256(raw).hexdigest(), 'provenanceEvidenceSha256': 'b' * 64},
            'subject': {'id': 'invented-subject-a', 'kind': 'invented', 'ageYears': None,
                        'identityDeclaration': None, 'identityEvidenceSha256': None,
                        'consentAuthorityDeclaration': None, 'consentAuthorityEvidenceSha256': None},
            'permissions': {purpose: {'rights': deepcopy(granted if purpose in ('storage', 'review') else unknown),
                                     'consent': deepcopy(granted if purpose in ('storage', 'review') else unknown)}
                            for purpose in ('storage', 'review', 'research', 'inference', 'redistribution')},
            'retainUntil': 1900000000}


class VaultTests(unittest.TestCase):
    def test_supplied_fixture_bytes_require_actual_current_session_and_assigned_review_role(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            password = secrets.token_urlsafe(24)
            auth.add_account('invented-reviewer', password)
            auth.assign('invented-reviewer', 'project-a', 'reviewer-a')
            sessions = SessionManager(auth)
            vault = Vault.create(directory, sessions, 'project-a', utc_clock=lambda: 1800000000)
            raw = pcm()
            receipt = vault.import_recording(raw, declaration(raw))
            self.assertTrue(receipt['imported'])
            self.assertEqual(receipt['frames'], 3200)
            self.assertEqual(receipt['durationMs'], 200)
            token, _ = sessions.bootstrap()
            token, public = sessions.login(token, 'invented-reviewer', password)
            returned = vault.read_recording(token, public['csrfToken'], receipt['recordingId'], 'review')
            self.assertTrue(returned == raw)
            asset = Path(directory) / 'recordings' / (receipt['recordingId'] + '.wav')
            self.assertEqual(asset.stat().st_mode & 0o777, 0o600)


    def test_retention_dry_run_and_explicit_purge_preserve_metadata_and_deny_future_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            password = secrets.token_urlsafe(24)
            auth.add_account('invented-coordinator', password)
            auth.assign('invented-coordinator', 'project-a', 'coordinator')
            sessions = SessionManager(auth)
            now = [1800000000]
            vault = Vault.create(directory, sessions, 'project-a', utc_clock=lambda: now[0])
            raw = pcm()
            declared = declaration(raw)
            declared['retainUntil'] = now[0] + 1
            receipt = vault.import_recording(raw, declared)
            before = (Path(directory) / 'vault.jsonl').read_bytes()
            plan = vault.purge_report()
            self.assertEqual(plan['eligible'], [])
            self.assertTrue((Path(directory) / 'vault.jsonl').read_bytes() == before)
            now[0] += 1
            plan = vault.purge_report()
            self.assertEqual(plan['eligible'][0]['recordingId'], receipt['recordingId'])
            self.assertIn('retention_expired', plan['eligible'][0]['reasons'])
            outcome = vault.purge(plan)
            self.assertEqual(outcome['purged'], 1)
            asset = Path(directory) / 'recordings' / (receipt['recordingId'] + '.wav')
            self.assertFalse(asset.exists())
            token, _ = sessions.bootstrap()
            token, public = sessions.login(token, 'invented-coordinator', password)
            with self.assertRaises(VaultError):
                vault.read_recording(token, public['csrfToken'], receipt['recordingId'], 'review')
            exported = vault.export_metadata(token, public['csrfToken'])
            self.assertEqual(exported['counts']['recordingIntentDenominator'], 1)
            self.assertEqual(exported['counts']['purgedRecordings'], 1)
            self.assertEqual(exported['records'][0]['lifecycle'], 'purged')
            self.assertTrue(all(flag is False for flag in exported['claimLimits'].values()))
            self.assertFalse('identityDeclaration' in str(exported))



if __name__ == '__main__':
    unittest.main()

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.auth = AuthStore.create(self.root)
        self.password = secrets.token_urlsafe(24)
        self.auth.add_account('operator', self.password)
        self.auth.assign('operator', 'project-a', 'coordinator')
        self.monotonic, self.now = [0], [1800000000]
        self.sessions = SessionManager(self.auth, clock=lambda: self.monotonic[0])
        self.vault = Vault.create(self.root, self.sessions, 'project-a', utc_clock=lambda: self.now[0])
        self.raw = pcm()
        boot, _ = self.sessions.bootstrap()
        self.token, public = self.sessions.login(boot, 'operator', self.password)
        self.csrf = public['csrfToken']

    def imported(self, declared=None):
        return self.vault.import_recording(self.raw, declared or declaration(self.raw))['recordingId']

    def read(self, rid, purpose='review'):
        return self.vault.read_recording(self.token, self.csrf, rid, purpose)

    def truncate_last(self, count=1):
        journal = self.root / 'vault.jsonl'
        lines = journal.read_bytes().splitlines(keepends=True)
        journal.write_bytes(b''.join(lines[:-count]))

    def test_unknown_denied_expired_storage_never_imports_or_creates_managed_bytes(self):
        for status in ('unknown', 'denied', 'granted'):
            with self.subTest(status=status):
                declared = declaration(self.raw)
                decision = declared['permissions']['storage']['rights']
                decision['status'] = status
                if status == 'granted':
                    decision['expiresAt'] = self.now[0]
                with self.assertRaises(VaultError):
                    self.imported(declared)
        self.assertEqual(list((self.root / 'recordings').iterdir()), [])
        self.assertEqual(self.vault.purge_report()['eligible'], [])

    def test_review_consent_denial_and_separate_research_inference_redistribution_gates(self):
        declared = declaration(self.raw)
        declared['permissions']['review']['consent']['status'] = 'denied'
        rid = self.imported(declared)
        for purpose in ('review', 'research', 'inference', 'redistribution'):
            with self.subTest(purpose=purpose), self.assertRaises(VaultError):
                self.read(rid, purpose)
        self.assertTrue((self.root / 'recordings' / (rid + '.wav')).exists())

    def test_public_reference_no_enrollment_consent_is_explicit_and_age_remains_unknown(self):
        declared = declaration(self.raw)
        declared['source']['kind'] = declared['subject']['kind'] = 'public_reference'
        for purpose in ('storage', 'review'):
            declared['permissions'][purpose]['consent'] = {'status': 'not_applicable_public_reference',
                    'expiresAt': 2000000000, 'evidenceSha256': None,
                    'declaration': 'Public reference only; no enrollment or participant consent verification'}
        rid = self.imported(declared)
        self.assertTrue(self.read(rid) == self.raw)
        exported = self.vault.export_metadata(self.token, self.csrf)
        self.assertIsNone(exported['records'][0]['ageYearsDeclared'])
        declared['source']['kind'] = declared['subject']['kind'] = 'private_child'
        declared['subject']['ageYears'] = 9
        with self.assertRaises(VaultError):
            self.imported(declared)

    def test_incomplete_child_identity_and_authority_never_become_verified(self):
        declared = declaration(self.raw)
        declared['source']['kind'] = declared['subject']['kind'] = 'private_child'
        declared['subject']['ageYears'] = 9
        with self.assertRaises(VaultError) as error:
            self.imported(declared)
        self.assertEqual(error.exception.code, 'child_records_required')
        self.assertFalse(list((self.root / 'recordings').iterdir()))

    def test_restriction_and_withdrawal_retain_history_block_future_reads_and_imports(self):
        rid = self.imported()
        self.vault.restrict(self.token, self.csrf, rid, 'review', 'Invented purpose restriction')
        with self.assertRaises(VaultError):
            self.read(rid)
        self.vault.withdraw_subject(self.token, self.csrf, 'invented-subject-a', 'Invented withdrawal')
        with self.assertRaises(VaultError):
            self.imported()
        self.assertIn('subject_withdrawn', self.vault.purge_report()['eligible'][0]['reasons'])
        self.assertTrue((self.root / 'recordings' / (rid + '.wav')).exists())

    def test_current_generation_assignment_expiry_and_csrf_are_required(self):
        rid = self.imported()
        before = (self.root / 'vault.jsonl').read_bytes()
        with self.assertRaises((AuthError, VaultError)):
            self.vault.read_recording(self.token, 'wrong', rid, 'review')
        self.monotonic[0] = 900
        with self.assertRaises((AuthError, VaultError)):
            self.read(rid)
        self.assertTrue((self.root / 'vault.jsonl').read_bytes() == before)
        self.monotonic[0] = 901
        boot, _ = self.sessions.bootstrap()
        self.token, public = self.sessions.login(boot, 'operator', self.password)
        self.csrf = public['csrfToken']
        self.auth.reset_password('operator', secrets.token_urlsafe(24))
        with self.assertRaises((AuthError, VaultError)):
            self.read(rid)

    def test_deactivated_role_and_foreign_auth_root_cannot_supply_authority(self):
        rid = self.imported()
        self.auth.deactivate_assignment('operator', 'project-a')
        with self.assertRaises((AuthError, VaultError)):
            self.read(rid)
        with tempfile.TemporaryDirectory() as other:
            foreign = SessionManager(AuthStore.create(other))
            with self.assertRaises(VaultError) as error:
                Vault.open(self.root, foreign)
            self.assertEqual(error.exception.code, 'auth_root_mismatch')

    def test_pending_import_recovers_exact_bytes_and_expired_pending_import_never_promotes(self):
        rid = self.imported()
        self.truncate_last()
        final = self.root / 'recordings' / (rid + '.wav')
        stage = self.root / 'staging' / (rid + '.stage')
        final.rename(stage)
        reopened = Vault.open(self.root, self.sessions, utc_clock=lambda: self.now[0])
        self.assertTrue(reopened.read_recording(self.token, self.csrf, rid, 'review') == self.raw)
        self.truncate_last(2)  # recovered completion and read receipt
        final.rename(stage)
        self.now[0] = 1900000000
        reopened = Vault.open(self.root, self.sessions, utc_clock=lambda: self.now[0])
        self.assertFalse(final.exists())
        self.assertTrue(stage.exists())
        plan = reopened.purge_report()
        self.assertEqual(reopened.purge(plan)['purged'], 1)
        self.assertFalse(stage.exists())
        self.assertEqual(reopened.export_metadata(self.token, self.csrf)['counts']['completedImports'], 0)

    def test_pending_delete_recovers_idempotently_and_stale_dry_run_cannot_delete(self):
        rid = self.imported()
        self.now[0] = 1900000000
        stale = self.vault.purge_report()
        self.vault.export_metadata(self.token, self.csrf)
        with self.assertRaises(VaultError):
            self.vault.purge(stale)
        plan = self.vault.purge_report()
        self.vault.purge(plan)
        self.truncate_last()
        reopened = Vault.open(self.root, self.sessions, utc_clock=lambda: self.now[0])
        self.assertEqual(reopened.export_metadata(self.token, self.csrf)['counts']['purgedRecordings'], 1)
        self.assertFalse((self.root / 'recordings' / (rid + '.wav')).exists())
        self.assertTrue(reopened.reconcile()['reconciled'])

    def test_unregistered_stage_quarantines_until_explicit_hashed_orphan_cleanup(self):
        rid = self.imported()
        self.truncate_last(2)
        (self.root / 'recordings' / (rid + '.wav')).rename(self.root / 'staging' / (rid + '.stage'))
        with self.assertRaises(VaultError):
            Vault.open(self.root, self.sessions, utc_clock=lambda: self.now[0])
        maintenance = Vault.open_maintenance(self.root, self.sessions, utc_clock=lambda: self.now[0])
        before = (self.root / 'vault.jsonl').read_bytes()
        plan = maintenance.orphan_report()
        self.assertTrue((self.root / 'vault.jsonl').read_bytes() == before)
        self.assertEqual(plan['eligible'][0]['sha256'], hashlib.sha256(self.raw).hexdigest())
        maintenance.purge_orphans(plan)
        self.assertTrue(maintenance.reconcile()['reconciled'])
        self.assertEqual(maintenance.export_metadata(self.token, self.csrf)['counts']['orphanDeletionAttempts'], 1)

    def test_hash_tamper_symlink_hardlink_and_fifo_fail_without_following_media(self):
        import os
        rid = self.imported()
        asset = self.root / 'recordings' / (rid + '.wav')
        for kind in ('tamper', 'symlink', 'hardlink', 'fifo'):
            with self.subTest(kind=kind):
                asset.unlink()
                outside = self.root / 'outside.wav'
                outside.write_bytes(self.raw)
                outside.chmod(0o600)
                if kind == 'tamper':
                    asset.write_bytes(self.raw[:-2] + b'\x01\x00')
                    asset.chmod(0o600)
                elif kind == 'symlink':
                    asset.symlink_to(outside)
                elif kind == 'hardlink':
                    os.link(outside, asset)
                else:
                    os.mkfifo(asset, 0o600)
                with self.assertRaises(VaultError):
                    self.read(rid)
                self.assertTrue(outside.read_bytes() == self.raw)

    def test_journal_corruption_is_fail_closed_and_export_contains_no_session_or_subject_identity(self):
        rid = self.imported()
        exported = self.vault.export_metadata(self.token, self.csrf)
        for secret in (self.token, self.csrf, self.password, 'invented-subject-a', 'identityDeclaration', 'operator'):
            self.assertNotIn(secret, str(exported))
        journal = self.root / 'vault.jsonl'
        raw = journal.read_bytes()
        journal.write_bytes(raw.replace(b'"seq":0', b'"seq":true', 1))
        with self.assertRaises(VaultError):
            self.read(rid)

    def test_reviewer_role_cannot_export_restrict_or_claim_research_and_revocation_blocks_session(self):
        rid = self.imported()
        password = secrets.token_urlsafe(24)
        self.auth.add_account('reviewer', password)
        self.auth.assign('reviewer', 'project-a', 'reviewer-a')
        boot, _ = self.sessions.bootstrap()
        token, public = self.sessions.login(boot, 'reviewer', password)
        csrf = public['csrfToken']
        self.assertTrue(self.vault.read_recording(token, csrf, rid, 'review') == self.raw)
        for action in (lambda: self.vault.export_metadata(token, csrf),
                       lambda: self.vault.restrict(token, csrf, rid, 'review', 'No permission'),
                       lambda: self.vault.read_recording(token, csrf, rid, 'research')):
            with self.assertRaises(VaultError) as error:
                action()
            self.assertEqual(error.exception.code, 'authorization_required')
        self.auth.revoke_account('reviewer')
        with self.assertRaises(AuthError):
            self.vault.read_recording(token, csrf, rid, 'review')

    def test_interrupted_orphan_delete_and_known_pending_mismatch_never_adopt_unknown_bytes(self):
        rid = self.imported()
        self.truncate_last(2)
        final = self.root / 'recordings' / (rid + '.wav')
        stage = self.root / 'staging' / (rid + '.stage')
        final.rename(stage)
        plan = self.vault.orphan_report()
        self.vault.purge_orphans(plan)
        self.truncate_last()
        reopened = Vault.open(self.root, self.sessions, utc_clock=lambda: self.now[0])
        self.assertTrue(reopened.reconcile()['reconciled'])
        rid = reopened.import_recording(self.raw, declaration(self.raw))['recordingId']
        self.truncate_last()
        final = self.root / 'recordings' / (rid + '.wav')
        changed = self.raw[:-2] + b'\x01\x00'
        final.write_bytes(changed)
        with self.assertRaises(VaultError):
            Vault.open(self.root, self.sessions, utc_clock=lambda: self.now[0])
        self.assertTrue(final.read_bytes() == changed)

    def test_failed_read_does_not_extend_idle_and_absolute_session_deadline_or_restart_remains_closed(self):
        rid = self.imported()
        self.monotonic[0] = 899
        with self.assertRaises(VaultError):
            self.read(rid, 'research')
        self.monotonic[0] = 900
        with self.assertRaises(AuthError):
            self.read(rid)
        boot, _ = self.sessions.bootstrap()
        self.token, public = self.sessions.login(boot, 'operator', self.password)
        self.csrf = public['csrfToken']
        for current in (1500, 2100):
            self.monotonic[0] = current
            self.assertTrue(self.read(rid) == self.raw)
        self.monotonic[0] = 2700
        with self.assertRaises(AuthError):
            self.read(rid)
        restarted = Vault.open(self.root, SessionManager(self.auth), utc_clock=lambda: self.now[0])
        with self.assertRaises(AuthError):
            restarted.read_recording(self.token, self.csrf, rid, 'review')

    def test_full_ordinary_receipt_budget_cannot_block_withdrawal_and_retention_deletion(self):
        import json
        from workbench.domain import semantic_digest
        rid = self.imported()
        self.read(rid)
        journal = self.root / 'vault.jsonl'
        events = [json.loads(line) for line in journal.read_bytes().splitlines()]
        receipt = deepcopy(events[-1]['payload'])
        # Valid historical successful receipts exercise the persistent saturation
        # seam without thousands of live credential operations or mocked storage.
        while len(events) < 1536:
            event = {'seq': len(events), 'previousSha256': events[-1]['sha256'],
                     'kind': 'access', 'payload': deepcopy(receipt)}
            event['sha256'] = semantic_digest(event)
            events.append(event)
        journal.write_bytes(b''.join(json.dumps(event, sort_keys=True, separators=(',', ':')).encode() + b'\n'
                                     for event in events))
        with self.assertRaises(VaultError) as error:
            self.read(rid)
        self.assertEqual(error.exception.code, 'vault_capacity')
        self.vault.withdraw_subject(self.token, self.csrf, 'invented-subject-a', 'Invented withdrawal after saturated reads')
        plan = self.vault.purge_report()
        self.assertEqual(self.vault.purge(plan)['purged'], 1)
        self.assertFalse((self.root / 'recordings' / (rid + '.wav')).exists())
        self.assertTrue(self.vault.reconcile()['reconciled'])
