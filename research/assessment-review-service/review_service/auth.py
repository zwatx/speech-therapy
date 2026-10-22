"""Private local credentials, immutable project role holders and process sessions.

All administration and protected service operations share ``AuthStore.lock``.
Credentials and token digests are private implementation state, never exports.
Local accounts authenticate credentials, not different humans or qualifications.
"""

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
import weakref

from workbench.domain import ValidationError, semantic_digest


ROLES = ('coordinator', 'reviewer-a', 'reviewer-b', 'adjudicator')
SCRYPT_N = 131072
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_MAXMEM = 256 * 1024 * 1024
SALT_BYTES = 16
PASSWORD_MIN_BYTES = 16
PASSWORD_MAX_BYTES = 1024
MAX_ACCOUNTS = 64
MAX_ASSIGNMENTS = 256
MAX_REGISTRY_BYTES = 1024 * 1024
MAX_SESSIONS = 32
MAX_ANONYMOUS_SESSIONS = 16
MAX_SESSIONS_PER_ACCOUNT = 4
MAX_LOGIN_STARTS = 5
LOGIN_WINDOW_SECONDS = 60
ANONYMOUS_TIMEOUT_SECONDS = 120
ABSOLUTE_TIMEOUT_SECONDS = 1800
IDLE_TIMEOUT_SECONDS = 900
TOKEN_BYTES = 32

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
_TOKEN = re.compile(r'[A-Za-z0-9_-]{43}\Z')
_KDF = threading.BoundedSemaphore(1)
_LOCKS_GUARD = threading.Lock()
_LOCKS = weakref.WeakValueDictionary()


class AuthError(ValidationError):
    """A safe fixed code; never carries a credential or attempted username."""


def _identifier(value, code):
    if type(value) is not str or not _ID.fullmatch(value):
        raise AuthError(code)


def _password_bytes(password):
    if type(password) is not str or len(password) > PASSWORD_MAX_BYTES:
        raise AuthError('invalid_password')
    try:
        encoded = password.encode('utf-8')
    except UnicodeError as error:
        raise AuthError('invalid_password') from error
    if not PASSWORD_MIN_BYTES <= len(encoded) <= PASSWORD_MAX_BYTES:
        raise AuthError('invalid_password')
    return encoded


def _derive(password, salt):
    if not _KDF.acquire(blocking=False):
        raise AuthError('login_throttled')
    try:
        return hashlib.scrypt(password, salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                              p=SCRYPT_P, dklen=SCRYPT_DKLEN, maxmem=SCRYPT_MAXMEM)
    except (ValueError, MemoryError, AttributeError) as error:
        raise AuthError('auth_registry_invalid') from error
    finally:
        _KDF.release()


def _password_record(password):
    encoded = _password_bytes(password)
    salt = secrets.token_bytes(SALT_BYTES)
    return {'algorithm': 'scrypt', 'n': SCRYPT_N, 'r': SCRYPT_R, 'p': SCRYPT_P,
            'dklen': SCRYPT_DKLEN, 'saltHex': salt.hex(),
            'digestHex': _derive(encoded, salt).hex()}


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise AuthError('auth_registry_invalid')


def _validate_password_record(record):
    _exact(record, ('algorithm', 'n', 'r', 'p', 'dklen', 'saltHex', 'digestHex'))
    if record['algorithm'] != 'scrypt':
        raise AuthError('auth_registry_invalid')
    for field, expected in (('n', SCRYPT_N), ('r', SCRYPT_R), ('p', SCRYPT_P), ('dklen', SCRYPT_DKLEN)):
        if type(record[field]) is not int or record[field] != expected:
            raise AuthError('auth_registry_invalid')
    for field, size in (('saltHex', SALT_BYTES * 2), ('digestHex', SCRYPT_DKLEN * 2)):
        if type(record[field]) is not str or re.fullmatch('[0-9a-f]{' + str(size) + '}', record[field]) is None:
            raise AuthError('auth_registry_invalid')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuthError('auth_registry_invalid')
        result[key] = value
    return result


def _reject_constant(value):
    raise AuthError('auth_registry_invalid')


def _private_file(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise AuthError('unsafe_auth_file')


class _RootLock:
    def __init__(self):
        self.mutex = threading.RLock()
        self.local = threading.local()

    @contextmanager
    def acquire(self, store):
        with self.mutex:
            depth = getattr(self.local, 'depth', 0)
            if depth:
                store._check_root()
                self.local.depth += 1
                try:
                    yield
                finally:
                    self.local.depth -= 1
                return
            fd = store._open_file('service.lock', os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                self.local.depth = 1
                self.local.fd = fd
                yield
            finally:
                self.local.depth = 0
                self.local.fd = None
                os.close(fd)


class AuthStore:
    """Append-only owner-controlled registry; role occupancy survives revocation."""

    def __init__(self, root):
        self.root = Path(root).absolute()
        fd = self._directory()
        try:
            info = os.fstat(fd)
            self._identity = (info.st_dev, info.st_ino)
        finally:
            os.close(fd)
        with _LOCKS_GUARD:
            manager = _LOCKS.get(self._identity)
            if manager is None:
                manager = _RootLock()
                _LOCKS[self._identity] = manager
            self._lock_manager = manager

    @classmethod
    def create(cls, root):
        instance = cls(root)
        fd = instance._open_file('service.lock', os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.close(fd)
        with instance.lock():
            fd = instance._open_file('accounts.jsonl', os.O_CREAT | os.O_EXCL | os.O_RDWR)
            try:
                record = {'seq': 0, 'previousSha256': None, 'kind': 'registry', 'payload': {'schemaVersion': 1}}
                record['sha256'] = semantic_digest(record)
                instance._write(fd, record)
            finally:
                os.close(fd)
        return cls.open(root)

    @classmethod
    def open(cls, root):
        instance = cls(root)
        with instance.lock():
            instance._read()
        return instance

    def _directory(self):
        try:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as error:
            raise AuthError('unsafe_auth_directory') from error
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or (hasattr(self, '_identity') and (info.st_dev, info.st_ino) != self._identity)):
            os.close(fd)
            raise AuthError('unsafe_auth_directory')
        return fd

    def _check_root(self):
        fd = self._directory()
        os.close(fd)

    def _open_file(self, filename, flags):
        directory = self._directory()
        try:
            try:
                # Nonblocking prevents opening a substituted FIFO from waiting for a writer.
                fd = os.open(filename, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
            except FileExistsError as error:
                raise AuthError('auth_registry_exists') from error
            except OSError as error:
                raise AuthError('unsafe_auth_file') from error
            try:
                _private_file(fd)
            except BaseException:
                os.close(fd)
                raise
            return fd
        finally:
            os.close(directory)

    def lock(self):
        return self._lock_manager.acquire(self)

    @staticmethod
    def _write(fd, record):
        try:
            encoded = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                 allow_nan=False).encode('utf-8') + b'\n'
            if os.fstat(fd).st_size + len(encoded) > MAX_REGISTRY_BYTES:
                raise AuthError('auth_capacity')
            while encoded:
                count = os.write(fd, encoded)
                if count <= 0:
                    raise OSError('write_failed')
                encoded = encoded[count:]
            os.fsync(fd)
        except OSError as error:
            raise AuthError('auth_registry_invalid') from error

    def _read(self):
        fd = self._open_file('accounts.jsonl', os.O_RDONLY)
        try:
            if os.fstat(fd).st_size > MAX_REGISTRY_BYTES:
                raise AuthError('auth_registry_invalid')
            chunks = []
            remaining = MAX_REGISTRY_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b''.join(chunks)
        except OSError as error:
            raise AuthError('auth_registry_invalid') from error
        finally:
            os.close(fd)
        if not data or len(data) > MAX_REGISTRY_BYTES or not data.endswith(b'\n'):
            raise AuthError('auth_registry_invalid')
        state = {'accounts': {}, 'assignments': {}, 'slots': {}}
        previous = None
        try:
            for seq, line in enumerate(data.splitlines()):
                record = json.loads(line.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_reject_constant)
                _exact(record, ('seq', 'previousSha256', 'kind', 'payload', 'sha256'))
                body = {key: value for key, value in record.items() if key != 'sha256'}
                if (type(record['seq']) is not int or record['seq'] != seq
                        or record['previousSha256'] != previous or record['sha256'] != semantic_digest(body)):
                    raise AuthError('auth_registry_invalid')
                if seq == 0:
                    _exact(record['payload'], ('schemaVersion',))
                    if (record['kind'] != 'registry' or type(record['payload']['schemaVersion']) is not int
                            or record['payload']['schemaVersion'] != 1):
                        raise AuthError('auth_registry_invalid')
                else:
                    self._apply(state, record['kind'], record['payload'])
                previous = record['sha256']
        except (ValidationError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
            raise AuthError('auth_registry_invalid') from error
        return state, seq, previous

    @staticmethod
    def _apply(state, kind, payload):
        accounts = state['accounts']
        assignments = state['assignments']
        if kind in ('account_added', 'password_reset'):
            _exact(payload, ('accountId', 'passwordRecord'))
            account = payload['accountId']
            _identifier(account, 'invalid_account_id')
            _validate_password_record(payload['passwordRecord'])
            if kind == 'account_added':
                if account in accounts:
                    raise AuthError('account_exists')
                if len(accounts) >= MAX_ACCOUNTS:
                    raise AuthError('auth_capacity')
                accounts[account] = {'active': True, 'generation': 1,
                                     'passwordRecord': deepcopy(payload['passwordRecord'])}
            else:
                if account not in accounts or not accounts[account]['active']:
                    raise AuthError('account_inactive')
                accounts[account]['passwordRecord'] = deepcopy(payload['passwordRecord'])
                accounts[account]['generation'] += 1
        elif kind == 'account_revoked':
            _exact(payload, ('accountId',))
            account = payload['accountId']
            _identifier(account, 'invalid_account_id')
            if account not in accounts or not accounts[account]['active']:
                raise AuthError('account_inactive')
            accounts[account]['active'] = False
            accounts[account]['generation'] += 1
        elif kind in ('role_assigned', 'role_deactivated'):
            _exact(payload, ('accountId', 'projectId', 'role') if kind == 'role_assigned' else ('accountId', 'projectId'))
            account, project = payload['accountId'], payload['projectId']
            _identifier(account, 'invalid_account_id')
            _identifier(project, 'invalid_project_id')
            if kind == 'role_assigned':
                role = payload['role']
                if type(role) is not str or role not in ROLES:
                    raise AuthError('invalid_role')
                if account not in accounts or not accounts[account]['active']:
                    raise AuthError('account_inactive')
                if (account, project) in assignments or (project, role) in state['slots']:
                    raise AuthError('assignment_conflict')
                if len(assignments) >= MAX_ASSIGNMENTS:
                    raise AuthError('auth_capacity')
                assignments[(account, project)] = {'role': role, 'active': True}
                state['slots'][(project, role)] = account
            else:
                assignment = assignments.get((account, project))
                if not assignment or not assignment['active']:
                    raise AuthError('assignment_inactive')
                assignment['active'] = False
        else:
            raise AuthError('auth_registry_invalid')

    def _append(self, kind, payload):
        with self.lock():
            state, seq, previous = self._read()
            self._apply(state, kind, payload)
            record = {'seq': seq + 1, 'previousSha256': previous, 'kind': kind, 'payload': payload}
            record['sha256'] = semantic_digest(record)
            fd = self._open_file('accounts.jsonl', os.O_WRONLY | os.O_APPEND)
            try:
                self._write(fd, record)
            finally:
                os.close(fd)

    def add_account(self, accountId, password):
        _identifier(accountId, 'invalid_account_id')
        with self.lock():
            state, _, _ = self._read()
            if accountId in state['accounts']:
                raise AuthError('account_exists')
            if len(state['accounts']) >= MAX_ACCOUNTS:
                raise AuthError('auth_capacity')
            record = _password_record(password)
            self._append('account_added', {'accountId': accountId, 'passwordRecord': record})

    def reset_password(self, accountId, password):
        _identifier(accountId, 'invalid_account_id')
        with self.lock():
            state, _, _ = self._read()
            if accountId not in state['accounts'] or not state['accounts'][accountId]['active']:
                raise AuthError('account_inactive')
            record = _password_record(password)
            self._append('password_reset', {'accountId': accountId, 'passwordRecord': record})

    def assign(self, accountId, projectId, role):
        self._append('role_assigned', {'accountId': accountId, 'projectId': projectId, 'role': role})

    def deactivate_assignment(self, accountId, projectId):
        self._append('role_deactivated', {'accountId': accountId, 'projectId': projectId})

    def revoke_account(self, accountId):
        self._append('account_revoked', {'accountId': accountId})

    def authorize(self, accountId, projectId, generation):
        with self.lock():
            state, _, _ = self._read()
            account = state['accounts'].get(accountId) if type(accountId) is str else None
            assignment = state['assignments'].get((accountId, projectId)) if type(accountId) is str and type(projectId) is str else None
            if (not account or not account['active'] or type(generation) is not int
                    or account['generation'] != generation or not assignment or not assignment['active']):
                raise AuthError('authorization_required')
            return assignment['role']

    def assignments(self, accountId):
        with self.lock():
            state, _, _ = self._read()
            account = state['accounts'].get(accountId) if type(accountId) is str else None
            if not account or not account['active']:
                raise AuthError('authorization_required')
            return [{'projectId': project, 'role': value['role']}
                    for (account, project), value in sorted(state['assignments'].items())
                    if account == accountId and value['active']]


class SessionManager:
    """One service's bounded process-memory sessions; HTTP framing stays outside.

    The server verifies Host/Origin and calls ``verify_csrf`` before every POST.
    ``actor`` is passive; successful protected operations explicitly call touch.
    Cookies are represented in memory only by their SHA-256 digests. Public CSRF
    metadata is intentional and never included in registry/audit/project exports.
    """

    def __init__(self, auth, *, clock=time.monotonic):
        self.auth = auth
        self.clock = clock
        self._mutex = threading.RLock()
        self._sessions = {}
        self._login_starts = deque()
        self._last_clock = None
        salt = secrets.token_bytes(SALT_BYTES)
        self._dummy = {'saltHex': salt.hex(), 'digestHex': _derive(secrets.token_bytes(32), salt).hex()}

    def _now(self):
        now = self.clock()
        if (type(now) not in (int, float) or not math.isfinite(now)
                or (self._last_clock is not None and now < self._last_clock)):
            self._sessions.clear()
            raise AuthError('authentication_required')
        self._last_clock = now
        return now

    @staticmethod
    def _token_digest(token):
        if type(token) is not str or not _TOKEN.fullmatch(token):
            raise AuthError('authentication_required')
        return hashlib.sha256(token.encode('ascii')).hexdigest()

    @staticmethod
    def _valid(session, state, now):
        anonymous = session['accountId'] is None
        absolute = ANONYMOUS_TIMEOUT_SECONDS if anonymous else ABSOLUTE_TIMEOUT_SECONDS
        if now - session['created'] >= absolute:
            return False
        if anonymous:
            return True
        account = state['accounts'].get(session['accountId'])
        return bool(now - session['touched'] < IDLE_TIMEOUT_SECONDS and account and account['active']
                    and account['generation'] == session['generation'])

    @contextmanager
    def _state(self):
        # Never invert this order: engine/CLI may already hold the service lock.
        with self.auth.lock():
            state, _, _ = self.auth._read()
            with self._mutex:
                now = self._now()
                for digest, session in list(self._sessions.items()):
                    if not self._valid(session, state, now):
                        del self._sessions[digest]
                yield state, now

    def _get(self, token):
        digest = self._token_digest(token)
        session = self._sessions.get(digest)
        if session is None:
            raise AuthError('authentication_required')
        return digest, session

    @staticmethod
    def _public(session):
        anonymous = session['accountId'] is None
        return {'authenticated': not anonymous, 'accountId': session['accountId'],
                'csrfToken': session['csrfToken'],
                'absoluteTimeoutSeconds': ANONYMOUS_TIMEOUT_SECONDS if anonymous else ABSOLUTE_TIMEOUT_SECONDS,
                'idleTimeoutSeconds': None if anonymous else IDLE_TIMEOUT_SECONDS}

    def _new(self, accountId, generation, now, replacing=None):
        live = [session for digest, session in self._sessions.items() if digest != replacing]
        if len(live) >= MAX_SESSIONS:
            raise AuthError('session_capacity')
        if accountId is None:
            if sum(session['accountId'] is None for session in live) >= MAX_ANONYMOUS_SESSIONS:
                raise AuthError('session_capacity')
        elif sum(session['accountId'] == accountId for session in live) >= MAX_SESSIONS_PER_ACCOUNT:
            raise AuthError('session_capacity')
        raw = secrets.token_urlsafe(TOKEN_BYTES)
        digest = self._token_digest(raw)
        while digest in self._sessions:
            raw = secrets.token_urlsafe(TOKEN_BYTES)
            digest = self._token_digest(raw)
        session = {'accountId': accountId, 'generation': generation,
                   'created': now, 'touched': now, 'csrfToken': secrets.token_urlsafe(TOKEN_BYTES)}
        if replacing is not None:
            del self._sessions[replacing]
        self._sessions[digest] = session
        return raw, self._public(session)

    def bootstrap(self, token=None):
        with self._state() as (_, now):
            try:
                _, session = self._get(token)
            except AuthError:
                return self._new(None, None, now)
            return token, self._public(session)

    def public_session(self, token):
        with self._state():
            _, session = self._get(token)
            return self._public(session)

    def login(self, rawBootstrapToken, accountId, password):
        with self._state() as (state, now):
            old_digest, _ = self._get(rawBootstrapToken)
            while self._login_starts and now - self._login_starts[0] >= LOGIN_WINDOW_SECONDS:
                self._login_starts.popleft()
            if len(self._login_starts) >= MAX_LOGIN_STARTS:
                raise AuthError('login_throttled')
            self._login_starts.append(now)
            account = state['accounts'].get(accountId) if type(accountId) is str and _ID.fullmatch(accountId) else None
            usable = bool(account and account['active'])
            record = account['passwordRecord'] if usable else self._dummy
            try:
                encoded = _password_bytes(password)
                valid_password = True
            except AuthError:
                encoded, valid_password = b'\x00' * 32, False
            digest = _derive(encoded, bytes.fromhex(record['saltHex']))
            matches = secrets.compare_digest(digest, bytes.fromhex(record['digestHex']))
            if not usable or not valid_password or not matches:
                raise AuthError('invalid_credentials')
            # Registry revocation/reset cannot interleave while the service lock is held.
            return self._new(accountId, account['generation'], now, replacing=old_digest)

    def actor(self, token):
        with self._state():
            _, session = self._get(token)
            if session['accountId'] is None:
                raise AuthError('authentication_required')
            return {'accountId': session['accountId'], 'generation': session['generation']}

    def verify_csrf(self, token, header):
        with self._state():
            try:
                _, session = self._get(token)
            except AuthError as error:
                raise AuthError('csrf_required') from error
            if (type(header) is not str or not _TOKEN.fullmatch(header)
                    or not secrets.compare_digest(header, session['csrfToken'])):
                raise AuthError('csrf_required')

    def touch(self, token):
        with self._state() as (_, now):
            _, session = self._get(token)
            if session['accountId'] is None:
                raise AuthError('authentication_required')
            session['touched'] = now

    def logout(self, token):
        with self._state():
            digest, _ = self._get(token)
            del self._sessions[digest]
