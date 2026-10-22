"""Bounded loopback transport. Account administration stays in the local CLI."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.cookies import SimpleCookie, CookieError
import json
import re
from urllib.parse import urlsplit

from workbench.domain import ValidationError
from workbench.store import parse_json
from .auth import SessionManager

COOKIE = 'review_service_session'
_STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
           '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
           '/style.css': ('style.css', 'text/css; charset=utf-8')}
_PROJECT = re.compile(r'/api/projects/([A-Za-z0-9][A-Za-z0-9._-]{0,127})/(state|export|reviews|seal|adjudications|content-reviews|prediction-lock|withdraw|prediction-preview|media/[0-9a-f]{24})')


class LocalServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address

    def handle_error(self, request, client_address):
        # Avoid traceback or request material in operator logs.
        pass


def make_server(service, port=8772, sessions=None):
    server = LocalServer(('127.0.0.1', port), Handler)
    server.service = service
    server.sessions = sessions or SessionManager(service.auth)
    return server


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalReview'
    sys_version = ''
    protocol_version = 'HTTP/1.0'

    def log_message(self, *args):
        pass

    def _single(self, name, required=False):
        values = self.headers.get_all(name, [])
        if len(values) > 1 or (required and len(values) != 1):
            raise ValidationError('request_headers')
        return values[0] if values else None

    def _request(self):
        host = self._single('Host', True)
        if host not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            raise ValidationError('request_host')
        url = urlsplit(self.path)
        if url.scheme or url.netloc or url.query or url.fragment or url.path != self.path:
            raise ValidationError('request_path')
        return host

    def _cookie(self):
        raw = self._single('Cookie')
        if not raw:
            return None
        if len(raw) > 4096 or any(ord(c) < 32 or ord(c) > 126 for c in raw):
            raise ValidationError('request_cookie')
        matches = [part.strip() for part in raw.split(';') if part.strip().split('=', 1)[0].strip() == COOKIE]
        if len(matches) > 1:
            raise ValidationError('request_cookie')
        if matches and re.fullmatch(COOKIE + r'=[A-Za-z0-9_-]{43}', matches[0]) is None:
            raise ValidationError('request_cookie')
        try:
            parsed = SimpleCookie()
            parsed.load(raw)
        except CookieError as exc:
            raise ValidationError('request_cookie') from exc
        if not matches:
            return None
        if COOKIE not in parsed or re.fullmatch(r'[A-Za-z0-9_-]{43}', parsed[COOKIE].value) is None:
            raise ValidationError('request_cookie')
        return parsed[COOKIE].value

    def _body(self, host, token):
        if self._single('Origin', True) != 'http://' + host:
            raise ValidationError('csrf_required')
        self.server.sessions.verify_csrf(token, self._single('X-Review-CSRF', True))
        length = self._single('Content-Length', True)
        if self._single('Transfer-Encoding') is not None or not re.fullmatch(r'[0-9]{1,7}', length):
            raise ValidationError('request_framing')
        if self._single('Content-Type', True) != 'application/json' or int(length) > 1024 * 1024:
            raise ValidationError('request_body')
        raw = self.rfile.read(int(length))
        if len(raw) != int(length):
            raise ValidationError('request_body')
        try:
            return parse_json(raw.decode('utf-8'))
        except UnicodeDecodeError as exc:
            raise ValidationError('request_body') from exc

    def _send(self, status, value, content_type='application/json; charset=utf-8', cookie=None, disposition=None):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=True, allow_nan=False).encode()
        self.send_response(status)
        for key, val in {'Content-Type': content_type, 'Content-Length': str(len(body)),
                         'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                         'Cross-Origin-Resource-Policy': 'same-origin', 'Referrer-Policy': 'no-referrer',
                         'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}.items():
            self.send_header(key, val)
        if cookie is not None:
            self.send_header('Set-Cookie', f'{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path=/' + ('; Max-Age=0' if not cookie else ''))
        if disposition:
            self.send_header('Content-Disposition', disposition)
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, post):
        with self.server.service.auth.lock():
            host = self._request()
            token = self._cookie()
            service, sessions = self.server.service, self.server.sessions
            if not post and self.path in _STATIC:
                from pathlib import Path
                name, mime = _STATIC[self.path]
                self._send(200, (Path(__file__).parent.parent / 'static' / name).read_bytes(), mime)
                return
            if not post and self.path == '/api/session':
                token, public = sessions.bootstrap(token)
                self._send(200, public, cookie=token)
                return
            body = self._body(host, token) if post else None
            if post and self.path == '/api/login':
                if type(body) is not dict or set(body) != {'accountId', 'password'}:
                    raise ValidationError('request_fields')
                try:
                    token, public = sessions.login(token, body['accountId'], body['password'])
                except ValidationError:
                    service.audit.access(action='login', allowed=False)
                    raise
                try:
                    service.audit.access(sessions.actor(token), action='login', allowed=True)
                except BaseException:
                    sessions.logout(token)
                    raise
                self._send(200, public, cookie=token)
                return
            actor = sessions.actor(token)
            if post and self.path == '/api/logout':
                if body != {}:
                    raise ValidationError('request_fields')
                sessions.logout(token)
                service.audit.access(actor, action='logout', allowed=True)
                self._send(200, {'ok': True}, cookie='')
                return
            if not post and self.path == '/api/projects':
                result = service.projects(actor)
            else:
                match = _PROJECT.fullmatch(self.path)
                if not match:
                    raise ValidationError('request_path')
                project, action = match.groups()
                if not post and action == 'state':
                    result = service.state(actor, project)
                elif not post and action == 'export':
                    result = service.export(actor, project)
                    sessions.touch(token)
                    self._send(200, result, disposition='attachment; filename="assessment-export.json"')
                    return
                elif not post and action.startswith('media/'):
                    result = service.media(actor, project, action.split('/')[1])
                    sessions.touch(token)
                    self._send(200, result, 'audio/wav', disposition='inline; filename="synthetic-nonspeech.wav"')
                    return
                elif post and action == 'prediction-preview':
                    if type(body) is not dict or set(body) != {'rawJson'} or type(body['rawJson']) is not str or len(body['rawJson'].encode()) > 512 * 1024:
                        raise ValidationError('request_fields')
                    result = service.preview_predictions(actor, project, body['rawJson'])
                elif post and action not in ('state', 'export') and not action.startswith('media/'):
                    result = service.mutate(actor, project, action, body)
                else:
                    raise ValidationError('request_path')
            sessions.touch(token)
            self._send(200, result)

    def _run(self, post):
        try:
            self._dispatch(post)
        except ValidationError as exc:
            code = exc.code
            if code == 'authorization_required':
                try:
                    with self.server.service.auth.lock():
                        try:
                            actor = self.server.sessions.actor(self._cookie())
                        except ValidationError:
                            actor = None
                        self.server.service.audit.access(actor, action='access_denied', allowed=False)
                except (ValidationError, OSError, ValueError, TypeError, KeyError):
                    self._send(503, {'error': 'local_operation_failed'})
                    return
            status = 400
            if code in ('authentication_required', 'invalid_credentials'):
                status = 401
            elif code in ('authorization_required', 'csrf_required', 'fixture_unavailable'):
                status = 403
            elif code in ('login_throttled', 'session_capacity'):
                status = 429
            elif code in ('operation_outcome_unavailable', 'project_quarantined', 'access_audit_invalid', 'auth_registry_invalid'):
                status = 503
            elif code in ('unavailable_answer_required', 'review_sealed', 'prediction_lock_exists'):
                status = 409
            self._send(status, {'error': code})
        except (OSError, ValueError, TypeError, KeyError):
            self._send(503, {'error': 'local_operation_failed'})

    def do_GET(self):
        self._run(False)

    def do_POST(self):
        self._run(True)
