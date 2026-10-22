import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch
import secrets
import subprocess
import sys
import urllib.request
import selectors
import getpass

from review_service.__main__ import main
from review_service.engine import create_fixture_service
from review_service.auth import AuthError, AuthStore, SessionManager
from workbench.store import verify_export


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.template.name) / 'fixture'
        create_fixture_service(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        cls.template.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'service'
        shutil.copytree(self.fixture, self.root)
        self.credentials = json.loads((self.root / 'fixture-credentials.json').read_text())

    def invoke(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = main(arguments)
        return result, output.getvalue(), errors.getvalue()

    def test_verified_operator_export_is_private_replayable_and_exclusive(self):
        result, output, errors = self.invoke(['verify-service', str(self.root)])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        verified = json.loads(output)
        self.assertTrue(verified['verified'])
        self.assertTrue(verified['trustedOperator'])
        demo = next(project for project in verified['projects'] if project['id'] == 'demo-review')
        self.assertEqual((demo['attempts'], demo['participants'], demo['revision']), (11, 4, 0))
        destination = Path(self.directory.name) / 'bundle.json'
        result, output, errors = self.invoke(['export', str(self.root), 'demo-review', str(destination)])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        self.assertTrue(json.loads(output)['trustedOperator'])
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        bundle = json.loads(destination.read_text())
        self.assertEqual(verify_export(bundle)['attempts'], 11)
        original = destination.read_bytes()
        result, output, errors = self.invoke(['export', str(self.root), 'demo-review', str(destination)])
        self.assertEqual(result, 1)
        self.assertEqual(output, '')
        self.assertEqual(errors, 'private_output_exists\n')
        self.assertTrue(destination.read_bytes() == original)
        self.assertTrue(all(secret not in original.decode() for secret in self.credentials.values()))

    def test_hidden_password_reset_and_revocation_change_current_access_without_outputting_secrets(self):
        updated = secrets.token_urlsafe(32)
        account = 'fixture-reviewer-a'
        old = self.credentials[account]
        with patch('getpass.getpass', side_effect=[updated, secrets.token_urlsafe(32)]):
            result, output, errors = self.invoke(['reset-password', str(self.root), account])
        self.assertEqual((result, output, errors), (1, '', 'password_confirmation_mismatch\n'))
        with patch('getpass.getpass', side_effect=[updated, updated]) as prompt:
            result, output, errors = self.invoke(['reset-password', str(self.root), account])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        self.assertEqual(prompt.call_count, 2)
        self.assertTrue(updated not in output + errors)
        self.assertTrue(old not in output + errors)
        auth = AuthStore.open(self.root)
        sessions = SessionManager(auth)
        token, _ = sessions.bootstrap()
        with self.assertRaises(AuthError):
            sessions.login(token, account, old)
        token, _ = sessions.login(token, account, updated)
        self.assertEqual(sessions.actor(token)['generation'], 2)
        result, output, errors = self.invoke(['deactivate-assignment', str(self.root), account, 'demo-review'])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        with self.assertRaises(AuthError):
            auth.authorize(account, 'demo-review', 2)
        result, output, errors = self.invoke(['revoke-account', str(self.root), account])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        with self.assertRaises(AuthError):
            sessions.actor(token)
        self.assertTrue(updated not in output + errors)

    def test_audit_export_preserves_validated_records_without_credential_registry(self):
        destination = Path(self.directory.name) / 'audit.json'
        result, output, errors = self.invoke(['audit-export', str(self.root), str(destination)])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        self.assertTrue(json.loads(output)['written'])
        exported = json.loads(destination.read_text())
        self.assertEqual(exported['schemaVersion'], 1)
        self.assertEqual(exported['records'][0]['kind'], 'audit')
        self.assertFalse(exported['authenticityEstablished'])
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        encoded = destination.read_text()
        self.assertTrue(all(secret not in encoded + output + errors for secret in self.credentials.values()))
        self.assertFalse('passwordRecord' in encoded)
        self.assertFalse('accounts' in exported)

    def test_serve_module_starts_only_loopback_with_no_credentials_in_header(self):
        process = subprocess.Popen([sys.executable, '-u', '-W', 'error', '-m', 'review_service',
                                    'serve', str(self.root), '--port', '0'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=5), 'Server did not publish startup header')
            header = process.stdout.readline()
            self.assertTrue(bool(header), 'Server ended before startup')
            metadata = json.loads(header)
            self.assertTrue(metadata['url'].startswith('http://127.0.0.1:'))
            with urllib.request.urlopen(metadata['url'] + '/api/session', timeout=3) as response:
                public = json.load(response)
            self.assertFalse(public['authenticated'])
            self.assertTrue(metadata['syntheticOnly'])
            self.assertTrue(all(secret not in header for secret in self.credentials.values()))
        finally:
            if process.poll() is None:
                process.terminate()
            trailing, errors = process.communicate(timeout=5)
        self.assertEqual(errors, '')
        self.assertTrue(all(secret not in trailing for secret in self.credentials.values()))

    def test_hidden_password_input_failure_has_no_traceback_or_unconfirmed_reset(self):
        account = 'fixture-reviewer-a'
        with patch('getpass.getpass', side_effect=getpass.GetPassWarning('Cannot control echo')):
            result, output, errors = self.invoke(['reset-password', str(self.root), account])
        self.assertEqual((result, output, errors), (1, '', 'hidden_password_input_required\n'))
        auth = AuthStore.open(self.root)
        self.assertEqual(auth.authorize(account, 'demo-review', 1), 'reviewer-a')

    def test_export_rejects_unsafe_parent_and_symlink_destination_without_overwrite(self):
        output_dir = Path(self.directory.name) / 'unsafe'
        output_dir.mkdir(mode=0o755)
        destination = output_dir / 'bundle.json'
        result, output, errors = self.invoke(['export', str(self.root), 'demo-review', str(destination)])
        self.assertEqual((result, output, errors), (1, '', 'unsafe_output_directory\n'))
        self.assertFalse(destination.exists())
        output_dir.chmod(0o700)
        target = output_dir / 'target'
        target.write_text('invented marker')
        destination.symlink_to(target)
        result, output, errors = self.invoke(['export', str(self.root), 'demo-review', str(destination)])
        self.assertEqual((result, output, errors), (1, '', 'private_output_exists\n'))
        self.assertEqual(target.read_text(), 'invented marker')
        linked = Path(self.directory.name) / 'linked'
        linked.symlink_to(output_dir, target_is_directory=True)
        result, output, errors = self.invoke(['audit-export', str(self.root), str(linked / 'audit.json')])
        self.assertEqual((result, output, errors), (1, '', 'unsafe_output_directory\n'))
        self.assertFalse((output_dir / 'audit.json').exists())

    def test_operator_export_checks_current_coordinator_generation_and_assignment(self):
        auth = AuthStore.open(self.root)
        auth.reset_password('fixture-coordinator', secrets.token_urlsafe(32))
        destination = Path(self.directory.name) / 'bundle.json'
        result, output, errors = self.invoke(['export', str(self.root), 'demo-review', str(destination)])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        auth.deactivate_assignment('fixture-coordinator', 'demo-review')
        rejected = Path(self.directory.name) / 'rejected.json'
        result, output, errors = self.invoke(['export', str(self.root), 'demo-review', str(rejected)])
        self.assertEqual((result, output, errors), (1, '', 'authorization_required\n'))
        self.assertFalse(rejected.exists())
        auth.revoke_account('fixture-coordinator')
        result, output, errors = self.invoke(['export', str(self.root),
                                            'content-preparation-a957a9e3291f0d90', str(rejected)])
        self.assertEqual((result, output, errors), (1, '', 'authorization_required\n'))
        self.assertFalse(rejected.exists())

    def test_pending_content_export_has_no_enrollment_and_all_public_prompts(self):
        destination = Path(self.directory.name) / 'content.json'
        result, output, errors = self.invoke(['export', str(self.root),
                                            'content-preparation-a957a9e3291f0d90', str(destination)])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')
        bundle = json.loads(destination.read_text())
        manifest = bundle['aggregate']['manifest']
        self.assertEqual(manifest['attempts'], [])
        self.assertEqual(manifest['participants'], [])
        self.assertEqual(len(manifest['prompts']), 15)
        self.assertTrue(verify_export(bundle)['verified'])

    def test_corruption_never_produces_a_verified_header_or_export(self):
        journal = self.root / 'accounts.jsonl'
        original = journal.read_bytes()
        journal.write_bytes(original[:-1])
        result, output, errors = self.invoke(['verify-service', str(self.root)])
        self.assertEqual((result, output, errors), (1, '', 'auth_registry_invalid\n'))
        journal.write_bytes(original)
        audit = self.root / 'access.jsonl'
        audit.write_bytes(audit.read_bytes()[:-1])
        destination = Path(self.directory.name) / 'audit.json'
        result, output, errors = self.invoke(['audit-export', str(self.root), str(destination)])
        self.assertEqual((result, output, errors), (1, '', 'project_quarantined\n'))
        self.assertFalse(destination.exists())

    def test_rejected_arguments_paths_and_prompt_cancellation_are_sanitized(self):
        secret = secrets.token_urlsafe(32)
        for arguments in (['reset-password', str(self.root), 'fixture-reviewer-a', '--password', secret],
                          ['serve', str(self.root), '--port', '70000'],
                          ['serve', str(self.root), '--port', secret], ['unknown-' + secret]):
            result, output, errors = self.invoke(arguments)
            self.assertEqual((result, output, errors), (1, '', 'command_arguments\n'))
            self.assertTrue(secret not in output + errors)
        with patch('getpass.getpass', side_effect=EOFError(secret)):
            result, output, errors = self.invoke(['reset-password', str(self.root), 'fixture-reviewer-a'])
        self.assertEqual((result, output, errors), (1, '', 'operator_input_cancelled\n'))
        result, output, errors = self.invoke(['verify-service', str(Path(self.directory.name) / secret)])
        self.assertEqual((result, output, errors), (1, '', 'unsafe_auth_directory\n'))
        self.assertTrue(secret not in output + errors)

    def test_fixture_creation_never_clears_an_existing_service(self):
        credential_path = self.root / 'fixture-credentials.json'
        before = credential_path.read_bytes()
        result, output, errors = self.invoke(['create-fixture', str(self.root)])
        self.assertEqual((result, output, errors), (1, '', 'operator_io_error\n'))
        self.assertTrue(credential_path.read_bytes() == before)
        result, output, errors = self.invoke(['verify-service', str(self.root)])
        self.assertEqual(result, 0)
        self.assertEqual(errors, '')

    def test_create_fixture_emits_safe_header_and_private_invented_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'service'
            output, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                result = main(['create-fixture', str(root)])
            self.assertEqual(result, 0)
            self.assertEqual(errors.getvalue(), '')
            header = json.loads(output.getvalue())
            self.assertTrue(header['created'])
            self.assertTrue(header['syntheticOnly'])
            credentials = json.loads((root / 'fixture-credentials.json').read_text())
            self.assertEqual(len(credentials), 4)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / 'fixture-credentials.json').stat().st_mode & 0o777, 0o600)
            self.assertTrue(all(password not in output.getvalue() + errors.getvalue() for password in credentials.values()))


if __name__ == '__main__':
    unittest.main()
