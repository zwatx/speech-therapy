"""Loopback-only synthetic demonstration server. Role views are not authentication."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .domain import ValidationError
from .store import parse_json

_STATIC = Path(__file__).resolve().parent.parent / 'static'
_ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
           '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
           '/style.css': ('style.css', 'text/css; charset=utf-8')}
_MAX_BODY = 1024 * 1024


def make_server(store, port=8770):
    manifest = store.manifest
    if (manifest['mode'] != 'synthetic' or manifest['task']['definitionSource'] != 'synthetic'
            or any(p['source']['kind'] != 'synthetic' for p in manifest['prompts'])
            or any(a['recording'] is not None and a['recording']['origin'] != 'synthetic' for a in manifest['attempts'])):
        raise ValidationError('browser_synthetic_only')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            pass

        def _send(self, status, value, content_type='application/json; charset=utf-8', *, download=False):
            if type(value) is bytes:
                body = value
            else:
                body = json.dumps(value, allow_nan=False, ensure_ascii=True, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="assessment-workbench-export.json"')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def _host(self):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            values = self.headers.get_all('Host', [])
            if len(values) != 1 or values[0] not in allowed:
                raise ValidationError('local_host_required')
            return values[0]

        def do_GET(self):
            try:
                self._host()
                parsed = urlsplit(self.path)
                if parsed.scheme or parsed.netloc or parsed.fragment:
                    raise ValidationError('request_path')
                if parsed.path in _ASSETS and not parsed.query:
                    filename, mime = _ASSETS[parsed.path]
                    self._send(200, (_STATIC / filename).read_bytes(), mime)
                    return
                if parsed.path == '/api/state':
                    values = parse_qs(parsed.query, strict_parsing=True)
                    if set(values) != {'role'} or len(values['role']) != 1:
                        raise ValidationError('view_role')
                    self._send(200, store.snapshot(values['role'][0]))
                elif parsed.path == '/api/demo-predictions' and not parsed.query:
                    from .demo import make_predictions
                    self._send(200, make_predictions(store.manifest))
                elif parsed.path == '/api/export' and not parsed.query:
                    self._send(200, store.export_bundle(), download=True)
                else:
                    self._send(404, {'ok': False, 'error': 'not_found'})
            except ValidationError as exc:
                self._send(400, {'ok': False, 'error': exc.code})
            except (ValueError, UnicodeError, RecursionError):
                self._send(400, {'ok': False, 'error': 'request_path'})
            except (OSError, KeyError, TypeError):
                self._send(500, {'ok': False, 'error': 'local_operation_failed'})

        def do_POST(self):
            try:
                host = self._host()
                origins = self.headers.get_all('Origin', [])
                if origins != [f'http://{host}']:
                    raise ValidationError('same_origin_required')
                if self.headers.get_all('Transfer-Encoding', []):
                    raise ValidationError('request_framing')
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ValidationError('request_length')
                length = int(lengths[0])
                if length <= 0 or length > _MAX_BODY:
                    raise ValidationError('request_size')
                types = self.headers.get_all('Content-Type', [])
                if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
                    raise ValidationError('json_content_type_required')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValidationError('request_length')
                payload = parse_json(raw.decode('utf-8'))
                endpoints = {
                    '/api/reviews': ({'reviewerId', 'itemId', 'answer'}, lambda p: store.submit_review(p['reviewerId'], p['itemId'], p['answer'])),
                    '/api/seal': ({'reviewerId'}, lambda p: store.seal_reviews(p['reviewerId'])),
                    '/api/adjudications': ({'attemptId', 'answer'}, lambda p: store.adjudicate(p['attemptId'], p['answer'])),
                    '/api/content-reviews': ({'promptId', 'record'}, lambda p: store.record_content_review(p['promptId'], p['record'])),
                    '/api/prediction-lock': ({'payload', 'expectedSha256'}, lambda p: store.save_prediction_lock(p['payload'], p['expectedSha256'])),
                    '/api/withdraw': ({'participantId', 'reason'}, lambda p: store.withdraw(p['participantId'], p['reason'])),
                }
                endpoint = endpoints.get(self.path)
                if endpoint is None:
                    self._send(404, {'ok': False, 'error': 'not_found'})
                    return
                fields, operation = endpoint
                if type(payload) is not dict or set(payload) != fields:
                    raise ValidationError('request_fields')
                revision = operation(payload)
                self._send(200, {'ok': True, 'revision': revision})
            except ValidationError as exc:
                conflicts = {'reviews_sealed', 'review_already_saved', 'reviews_incomplete',
                             'reviews_not_sealed', 'adjudication_already_saved', 'predictions_already_locked', 'already_withdrawn'}
                self._send(409 if exc.code in conflicts else 400, {'ok': False, 'error': exc.code})
            except (ValueError, UnicodeError, RecursionError):
                self._send(400, {'ok': False, 'error': 'invalid_json'})
            except (OSError, KeyError, TypeError):
                self._send(500, {'ok': False, 'error': 'local_operation_failed'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)
