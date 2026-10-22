import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import selectors
import subprocess
import sys
import tempfile
import unittest

from workbench.domain import semantic_digest

from review_service.auth import AuthError, AuthStore, SessionManager


class RegistryTests(unittest.TestCase):
    def test_account_assignments_have_distinct_historical_role_holders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = AuthStore.create(root)
            auth.add_account('invented-a', secrets.token_urlsafe(24))
            auth.add_account('invented-b', secrets.token_urlsafe(24))
            auth.assign('invented-a', 'project-a', 'reviewer-a')
            self.assertEqual(AuthStore.open(root).authorize('invented-a', 'project-a', 1), 'reviewer-a')
            with self.assertRaises(AuthError) as error:
                auth.assign('invented-b', 'project-a', 'reviewer-a')
            self.assertEqual(error.exception.code, 'assignment_conflict')
            self.assertEqual(auth.assignments('invented-a'), [{'projectId': 'project-a', 'role': 'reviewer-a'}])
            self.assertEqual((root / 'accounts.jsonl').stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / 'service.lock').stat().st_mode & 0o777, 0o600)

    def test_deactivation_keeps_both_historical_slot_and_account_role_occupied(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            for account in ('invented-a', 'invented-b'):
                auth.add_account(account, secrets.token_urlsafe(24))
            auth.assign('invented-a', 'project-a', 'coordinator')
            auth.deactivate_assignment('invented-a', 'project-a')
            auth = AuthStore.open(directory)
            for account, role in (('invented-b', 'coordinator'), ('invented-a', 'reviewer-a'), ('invented-a', 'coordinator')):
                with self.subTest(account=account, role=role), self.assertRaises(AuthError) as error:
                    auth.assign(account, 'project-a', role)
                self.assertEqual(error.exception.code, 'assignment_conflict')
            self.assertEqual(auth.assignments('invented-a'), [])
            auth.assign('invented-a', 'project-b', 'reviewer-b')
            self.assertEqual(auth.authorize('invented-a', 'project-b', 1), 'reviewer-b')

    def test_revocation_generation_and_missing_project_errors_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            auth.add_account('invented-a', secrets.token_urlsafe(24))
            auth.assign('invented-a', 'project-a', 'reviewer-a')
            for account, project, generation in (('invented-a', 'missing', 1), ('missing', 'project-a', 1),
                                                 ('invented-a', 'project-a', 2), ('invented-a', 'project-a', True)):
                with self.subTest(account=account, project=project, generation=generation), self.assertRaises(AuthError) as error:
                    auth.authorize(account, project, generation)
                self.assertEqual(error.exception.code, 'authorization_required')
            AuthStore.open(directory).revoke_account('invented-a')
            with self.assertRaises(AuthError):
                auth.authorize('invented-a', 'project-a', 1)
            with self.assertRaises(AuthError):
                auth.reset_password('invented-a', secrets.token_urlsafe(24))
            with self.assertRaises(AuthError):
                auth.add_account('invented-a', secrets.token_urlsafe(24))

    def test_registry_rejects_truncation_and_rehashed_invalid_costs(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            auth.add_account('invented-a', secrets.token_urlsafe(24))
            journal = Path(directory) / 'accounts.jsonl'
            original = journal.read_bytes()
            journal.write_bytes(original[:-1])
            with self.assertRaises(AuthError) as error:
                AuthStore.open(directory)
            self.assertEqual(error.exception.code, 'auth_registry_invalid')
            journal.write_bytes(original)
            records = [json.loads(line) for line in original.splitlines()]
            records[1]['payload']['passwordRecord']['n'] = 16
            previous = None
            for record in records:
                record['previousSha256'] = previous
                record['sha256'] = semantic_digest({key: value for key, value in record.items() if key != 'sha256'})
                previous = record['sha256']
            journal.write_text(''.join(json.dumps(record) + '\n' for record in records))
            with self.assertRaises(AuthError) as error:
                AuthStore.open(directory)
            self.assertEqual(error.exception.code, 'auth_registry_invalid')

    def test_private_files_reject_permissions_symlinks_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            AuthStore.create(root)
            journal = root / 'accounts.jsonl'
            journal.chmod(0o640)
            with self.assertRaises(AuthError) as error:
                AuthStore.open(root)
            self.assertEqual(error.exception.code, 'unsafe_auth_file')
            journal.chmod(0o600)
            extra = root / 'hardlink'
            os.link(journal, extra)
            with self.assertRaises(AuthError):
                AuthStore.open(root)
            extra.unlink()
            journal.rename(root / 'saved')
            journal.symlink_to(root / 'saved')
            with self.assertRaises(AuthError):
                AuthStore.open(root)
            journal.unlink()
            (root / 'saved').rename(journal)
            root.chmod(0o750)
            try:
                with self.assertRaises(AuthError) as error:
                    AuthStore.open(root)
                self.assertEqual(error.exception.code, 'unsafe_auth_directory')
            finally:
                root.chmod(0o700)

    def test_nonregular_journal_fails_without_waiting_for_a_fifo_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            AuthStore.create(root)
            (root / 'accounts.jsonl').unlink()
            os.mkfifo(root / 'accounts.jsonl', 0o600)
            code = "from review_service.auth import AuthStore,AuthError; import sys; "
            code += "\ntry: AuthStore.open(sys.argv[1])\nexcept AuthError as error: print(error.code)"
            try:
                result = subprocess.run([sys.executable, '-c', code, directory],
                                        capture_output=True, text=True, timeout=2)
            except subprocess.TimeoutExpired:
                self.fail('Registry open blocked on a nonregular file')
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), 'unsafe_auth_file')

    def test_duplicate_creation_is_exclusive_and_never_clears_existing_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            auth.add_account('invented-a', secrets.token_urlsafe(24))
            auth.assign('invented-a', 'project-a', 'reviewer-a')
            with self.assertRaises(AuthError):
                AuthStore.create(directory)
            self.assertEqual(AuthStore.open(directory).authorize('invented-a', 'project-a', 1), 'reviewer-a')


    def test_utf8_password_bounds_are_bytes_and_never_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            for number, password in enumerate(('é' * 7, 'é' * 513, 'x' * 1025, '\ud800' * 16, True)):
                with self.subTest(case=number), self.assertRaises(AuthError) as error:
                    auth.add_account('invalid-' + str(number), password)
                self.assertEqual(error.exception.code, 'invalid_password')
            password = 'é' * 8
            auth.add_account('minimum', password)
            auth.add_account('maximum', 'é' * 512)
            sessions = SessionManager(auth)
            token, _ = sessions.bootstrap()
            with self.assertRaises(AuthError) as error:
                sessions.login(token, 'minimum', 'é' * 8)
            self.assertEqual(error.exception.code, 'invalid_credentials')
            token, _ = sessions.login(token, 'minimum', password)
            self.assertEqual(sessions.actor(token)['accountId'], 'minimum')
            token, _ = sessions.bootstrap()
            token, _ = sessions.login(token, 'maximum', 'é' * 512)
            self.assertEqual(sessions.actor(token)['accountId'], 'maximum')

    def test_registry_rejects_ambiguous_json_and_non_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            AuthStore.create(directory)
            journal = Path(directory) / 'accounts.jsonl'
            original = journal.read_bytes()
            for number, data in enumerate((original.replace(b'"seq":0', b'"seq":0,"seq":0'),
                                           original.replace(b'"seq":0', b'"seq":NaN'),
                                           original.replace(b'"seq":0', b'"seq":true'),
                                           original.decode().encode('utf-16'),
                                           original.decode().rstrip('\n').encode('utf-16') + b'\n', b'\xff\n')):
                journal.write_bytes(data)
                with self.subTest(case=number), self.assertRaises(AuthError) as error:
                    AuthStore.open(directory)
                self.assertEqual(error.exception.code, 'auth_registry_invalid')
            journal.write_bytes(original)
            AuthStore.open(directory)
            self.assertTrue(journal.read_bytes() == original)

    def test_root_wide_lock_is_reentrant_across_store_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            first = AuthStore.create(directory)
            first.add_account('invented-a', secrets.token_urlsafe(24))
            first.assign('invented-a', 'project-a', 'reviewer-a')
            second = AuthStore.open(directory)
            done = threading.Event()
            outcomes = []
            def nested():
                try:
                    with first.lock(), second.lock():
                        outcomes.append(second.authorize('invented-a', 'project-a', 1))
                except Exception as error:
                    outcomes.append(type(error).__name__)
                finally:
                    done.set()
            thread = threading.Thread(target=nested, daemon=True)
            thread.start()
            self.assertTrue(done.wait(2), 'Nested instance operation deadlocked')
            self.assertEqual(outcomes, ['reviewer-a'])

    def test_concurrent_slot_assignment_has_exactly_one_historical_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            for account in ('invented-a', 'invented-b'):
                auth.add_account(account, secrets.token_urlsafe(24))
            stores = [AuthStore.open(directory), AuthStore.open(directory)]
            barrier = threading.Barrier(2)
            def assign(index):
                barrier.wait(timeout=2)
                try:
                    stores[index].assign(('invented-a', 'invented-b')[index], 'project-a', 'reviewer-a')
                    return 'assigned'
                except AuthError as error:
                    return error.code
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(assign, range(2)))
            self.assertEqual(sorted(outcomes), ['assigned', 'assignment_conflict'])
            reopened = AuthStore.open(directory)
            holders = sum(bool(reopened.assignments(account)) for account in ('invented-a', 'invented-b'))
            self.assertEqual(holders, 1)

    def test_global_kdf_cost_is_serialized_across_different_registry_roots(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            stores = (AuthStore.create(first), AuthStore.create(second))
            passwords = (secrets.token_urlsafe(24), secrets.token_urlsafe(24))
            barrier = threading.Barrier(2)
            def add(index):
                barrier.wait(timeout=2)
                try:
                    stores[index].add_account('invented-a', passwords[index])
                    return 'added'
                except AuthError as error:
                    return error.code
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(add, range(2)))
            self.assertEqual(sorted(outcomes), ['added', 'login_throttled'])

    def test_account_capacity_counts_revoked_accounts_and_rejects_without_append(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            for number in range(64):
                auth.add_account('invented-' + str(number), secrets.token_urlsafe(24))
            auth.revoke_account('invented-0')
            journal = Path(directory) / 'accounts.jsonl'
            before = journal.read_bytes()
            with self.assertRaises(AuthError) as error:
                auth.add_account('invented-extra', secrets.token_urlsafe(24))
            self.assertEqual(error.exception.code, 'auth_capacity')
            self.assertTrue(journal.read_bytes() == before)
            AuthStore.open(directory)

    def test_missing_root_is_not_created_and_replaced_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            missing = parent / 'missing'
            with self.assertRaises(AuthError) as error:
                AuthStore.create(missing)
            self.assertEqual(error.exception.code, 'unsafe_auth_directory')
            self.assertFalse(missing.exists())
            root = parent / 'root'
            root.mkdir(mode=0o700)
            auth = AuthStore.create(root)
            root.rename(parent / 'moved')
            root.mkdir(mode=0o700)
            AuthStore.create(root)
            with self.assertRaises(AuthError) as error:
                auth.assignments('invented-a')
            self.assertEqual(error.exception.code, 'unsafe_auth_directory')

    def test_registry_caps_count_historical_assignments_and_bound_journal_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthStore.create(directory)
            auth.add_account('invented-a', secrets.token_urlsafe(24))
            for number in range(256):
                auth.assign('invented-a', 'project-' + str(number), 'reviewer-a')
            auth.deactivate_assignment('invented-a', 'project-0')
            with self.assertRaises(AuthError) as error:
                auth.assign('invented-a', 'project-extra', 'reviewer-a')
            self.assertEqual(error.exception.code, 'auth_capacity')
            journal = Path(directory) / 'accounts.jsonl'
            with journal.open('ab') as stream:
                stream.write(b' ' * (1024 * 1024))
            with self.assertRaises(AuthError) as error:
                AuthStore.open(directory)
            self.assertEqual(error.exception.code, 'auth_registry_invalid')


class CurrentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.auth = AuthStore.create(self.directory.name)
        self.password = secrets.token_urlsafe(24)
        self.auth.add_account('invented-a', self.password)
        self.auth.assign('invented-a', 'project-a', 'reviewer-a')
        self.auth.assign('invented-a', 'project-b', 'coordinator')
        self.sessions = SessionManager(self.auth)
        token, _ = self.sessions.bootstrap()
        self.token, self.public = self.sessions.login(token, 'invented-a', self.password)

    def test_password_reset_invalidates_existing_cookie_and_old_credentials(self):
        updated = secrets.token_urlsafe(24)
        AuthStore.open(self.directory.name).reset_password('invented-a', updated)
        for operation in (self.sessions.actor, self.sessions.public_session, self.sessions.touch):
            with self.assertRaises(AuthError) as error:
                operation(self.token)
            self.assertEqual(error.exception.code, 'authentication_required')
        with self.assertRaises(AuthError):
            self.sessions.verify_csrf(self.token, self.public['csrfToken'])
        token, _ = self.sessions.bootstrap()
        with self.assertRaises(AuthError) as error:
            self.sessions.login(token, 'invented-a', self.password)
        self.assertEqual(error.exception.code, 'invalid_credentials')
        token, _ = self.sessions.login(token, 'invented-a', updated)
        self.assertEqual(self.sessions.actor(token), {'accountId': 'invented-a', 'generation': 2})
        self.assertEqual(self.auth.authorize('invented-a', 'project-a', 2), 'reviewer-a')

    def test_deactivated_assignment_is_current_while_other_project_actor_survives(self):
        AuthStore.open(self.directory.name).deactivate_assignment('invented-a', 'project-a')
        actor = self.sessions.actor(self.token)
        with self.assertRaises(AuthError) as error:
            self.auth.authorize(actor['accountId'], 'project-a', actor['generation'])
        self.assertEqual(error.exception.code, 'authorization_required')
        self.assertEqual(self.auth.authorize(actor['accountId'], 'project-b', actor['generation']), 'coordinator')
        self.assertEqual(self.auth.assignments('invented-a'), [{'projectId': 'project-b', 'role': 'coordinator'}])

    def test_other_process_revocation_waits_for_complete_protected_operation(self):
        code = "import sys; from review_service.auth import AuthStore; print('ready',flush=True); "
        code += "sys.stdin.readline(); AuthStore.open(sys.argv[1]).revoke_account('invented-a'); print('revoked',flush=True)"
        with self.auth.lock():
            process = subprocess.Popen([sys.executable, '-c', code, self.directory.name],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
                process.stdin.write('go\n')
                process.stdin.flush()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    self.assertFalse(selector.select(timeout=0.2), 'Administration bypassed the protected-operation lock')
                actor = self.sessions.actor(self.token)
                self.assertEqual(self.auth.authorize(actor['accountId'], 'project-a', actor['generation']), 'reviewer-a')
            except BaseException:
                process.kill()
                process.communicate()
                raise
        output, errors = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(errors, '')
        self.assertEqual(output.strip(), 'revoked')
        with self.assertRaises(AuthError) as error:
            self.sessions.actor(self.token)
        self.assertEqual(error.exception.code, 'authentication_required')
        with self.assertRaises(AuthError) as error:
            self.auth.authorize('invented-a', 'project-a', 1)
        self.assertEqual(error.exception.code, 'authorization_required')

    def test_credentials_and_session_secrets_never_enter_registry_or_public_metadata(self):
        journal = (Path(self.directory.name) / 'accounts.jsonl').read_bytes()
        for secret in (self.password, self.token, self.public['csrfToken']):
            self.assertFalse(secret.encode() in journal)
        projection = {'session': self.public, 'actor': self.sessions.actor(self.token),
                      'assignments': self.auth.assignments('invented-a')}
        encoded = json.dumps(projection)
        for secret in (self.password, self.token):
            self.assertFalse(secret in encoded)
        self.assertFalse('passwordRecord' in encoded)
        self.public['accountId'] = 'spoofed'
        self.assertEqual(self.sessions.actor(self.token)['accountId'], 'invented-a')


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.auth = AuthStore.create(cls.root)
        cls.passwords = {account: secrets.token_urlsafe(24) for account in ('invented-a', 'invented-b', 'invented-c', 'invented-d')}
        cls.password = cls.passwords['invented-a']
        for account, password in cls.passwords.items():
            cls.auth.add_account(account, password)
        cls.auth.assign('invented-a', 'project-a', 'reviewer-a')

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.clock = Clock()
        self.sessions = SessionManager(AuthStore.open(self.root), clock=self.clock)

    def login(self):
        token, public = self.sessions.bootstrap()
        self.sessions.verify_csrf(token, public['csrfToken'])
        return self.sessions.login(token, 'invented-a', self.password)

    def test_successful_login_rotates_cookie_and_csrf_into_a_passive_account_actor(self):
        anonymous, before = self.sessions.bootstrap()
        self.assertEqual(before['authenticated'], False)
        self.sessions.verify_csrf(anonymous, before['csrfToken'])
        token, after = self.sessions.login(anonymous, 'invented-a', self.password)
        self.assertTrue(token != anonymous)
        self.assertTrue(after['csrfToken'] != before['csrfToken'])
        self.assertEqual(after['accountId'], 'invented-a')
        self.assertEqual(set(after), {'authenticated', 'accountId', 'csrfToken', 'absoluteTimeoutSeconds', 'idleTimeoutSeconds'})
        self.assertEqual(self.sessions.actor(token), {'accountId': 'invented-a', 'generation': 1})
        with self.assertRaises(AuthError):
            self.sessions.actor(anonymous)
        with self.assertRaises(AuthError):
            self.sessions.verify_csrf(token, before['csrfToken'])
        self.assertTrue(self.sessions.public_session(token) == after)

    def test_wrong_unknown_credentials_have_same_error_and_do_not_rotate_bootstrap(self):
        token, public = self.sessions.bootstrap()
        for account in ('invented-a', 'missing-account'):
            with self.assertRaises(AuthError) as error:
                self.sessions.login(token, account, secrets.token_urlsafe(24))
            self.assertEqual(error.exception.code, 'invalid_credentials')
            self.sessions.verify_csrf(token, public['csrfToken'])
        valid, _ = self.sessions.login(token, 'invented-a', self.password)
        self.assertEqual(self.sessions.actor(valid)['accountId'], 'invented-a')

    def test_passive_and_failed_requests_do_not_extend_idle_expiry(self):
        token, public = self.login()
        self.clock.now = 899
        self.sessions.actor(token)
        self.sessions.public_session(token)
        self.sessions.bootstrap(token)
        self.sessions.verify_csrf(token, public['csrfToken'])
        with self.assertRaises(AuthError):
            self.sessions.login(token, 'invented-a', secrets.token_urlsafe(24))
        self.clock.now = 900
        with self.assertRaises(AuthError) as error:
            self.sessions.actor(token)
        self.assertEqual(error.exception.code, 'authentication_required')

    def test_successful_touch_extends_idle_but_never_absolute_timeout(self):
        token, _ = self.login()
        self.clock.now = 899
        self.sessions.touch(token)
        self.clock.now = 1798
        self.sessions.touch(token)
        self.clock.now = 1799
        self.assertEqual(self.sessions.actor(token)['accountId'], 'invented-a')
        self.clock.now = 1800
        with self.assertRaises(AuthError):
            self.sessions.actor(token)

    def test_anonymous_expiry_invalidates_csrf_and_bootstrap_replaces_old_cookie(self):
        token, public = self.sessions.bootstrap()
        self.clock.now = 119
        self.sessions.verify_csrf(token, public['csrfToken'])
        self.clock.now = 120
        with self.assertRaises(AuthError):
            self.sessions.verify_csrf(token, public['csrfToken'])
        new_token, new_public = self.sessions.bootstrap(token)
        self.assertTrue(new_token != token)
        self.assertTrue(new_public['csrfToken'] != public['csrfToken'])

    def test_restart_and_logout_invalidate_tokens(self):
        token, public = self.login()
        fresh = SessionManager(self.auth, clock=self.clock)
        with self.assertRaises(AuthError):
            fresh.actor(token)
        self.sessions.verify_csrf(token, public['csrfToken'])
        self.sessions.logout(token)
        with self.assertRaises(AuthError):
            self.sessions.actor(token)

    def test_global_login_budget_counts_unknown_accounts_and_successes_without_username_buckets(self):
        token, _ = self.sessions.bootstrap()
        for number in range(4):
            with self.assertRaises(AuthError) as error:
                self.sessions.login(token, 'unknown-' + str(number), secrets.token_urlsafe(24))
            self.assertEqual(error.exception.code, 'invalid_credentials')
        token, _ = self.sessions.login(token, 'invented-a', self.password)
        with self.assertRaises(AuthError) as error:
            self.sessions.login(token, 'invented-a', self.password)
        self.assertEqual(error.exception.code, 'login_throttled')
        self.clock.now = 60
        token, _ = self.sessions.login(token, 'invented-a', self.password)
        self.assertEqual(self.sessions.actor(token)['accountId'], 'invented-a')

    def test_anonymous_and_per_account_session_caps_preserve_existing_actors(self):
        for _ in range(16):
            self.sessions.bootstrap()
        with self.assertRaises(AuthError) as error:
            self.sessions.bootstrap()
        self.assertEqual(error.exception.code, 'session_capacity')
        self.clock.now = 120
        tokens = [self.login()[0] for _ in range(4)]
        with self.assertRaises(AuthError) as error:
            self.login()
        self.assertEqual(error.exception.code, 'session_capacity')
        self.assertTrue(all(self.sessions.actor(token)['accountId'] == 'invented-a' for token in tokens))

    def test_bad_cookie_and_csrf_values_fail_with_safe_fixed_codes(self):
        token, public = self.login()
        for number, bad in enumerate((None, True, [], {}, 'x' * 10000, 'é' * 43)):
            with self.subTest(case=number), self.assertRaises(AuthError) as error:
                self.sessions.actor(bad)
            self.assertEqual(error.exception.code, 'authentication_required')
            with self.subTest(case=number), self.assertRaises(AuthError) as error:
                self.sessions.verify_csrf(token, bad)
            self.assertEqual(error.exception.code, 'csrf_required')
        self.sessions.verify_csrf(token, public['csrfToken'])
        self.assertEqual(self.sessions.actor(token)['accountId'], 'invented-a')

    def test_clock_reversal_or_nonfinite_policy_input_invalidates_existing_sessions(self):
        for number, invalid in enumerate((-1, float('inf'), float('nan'), True)):
            if number:
                self.clock = Clock()
                self.sessions = SessionManager(self.auth, clock=self.clock)
            token, _ = self.login()
            self.clock.now = invalid
            with self.subTest(case=number), self.assertRaises(AuthError) as error:
                self.sessions.actor(token)
            self.assertEqual(error.exception.code, 'authentication_required')
            self.clock.now = 1
            with self.subTest(case=number), self.assertRaises(AuthError):
                self.sessions.actor(token)

    def test_public_timeout_metadata_matches_anonymous_and_authenticated_policies(self):
        token, public = self.sessions.bootstrap()
        self.assertEqual(public['absoluteTimeoutSeconds'], 120)
        self.assertIsNone(public['idleTimeoutSeconds'])
        self.assertIsNone(public['accountId'])
        token, public = self.sessions.login(token, 'invented-a', self.password)
        self.assertEqual(public['absoluteTimeoutSeconds'], 1800)
        self.assertEqual(public['idleTimeoutSeconds'], 900)
        self.assertTrue(public['authenticated'])

    def test_total_session_cap_includes_both_anonymous_and_authenticated_sessions(self):
        count = 0
        for account, password in self.passwords.items():
            for _ in range(4):
                if count and count % 5 == 0:
                    self.clock.now += 60
                token, _ = self.sessions.bootstrap()
                self.sessions.login(token, account, password)
                count += 1
        for _ in range(16):
            self.sessions.bootstrap()
        with self.assertRaises(AuthError) as error:
            self.sessions.bootstrap()
        self.assertEqual(error.exception.code, 'session_capacity')


if __name__ == '__main__':
    unittest.main()
