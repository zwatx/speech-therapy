"""Closed browser resources and same-origin isolated word-guess transport."""
from copy import deepcopy
import hmac
import io
import math
from pathlib import Path
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import wave
from consumer_assessment.bridge import Unavailable
from journey.catalog import read_owned
from mobile_admission import contract
from mobile_admission.service import Executor
from .catalog import Catalog
from . import feedback_contract

PORT = 8797
ROOT = Path(__file__).resolve().parents[3]
RESERVED_PORTS = (8782, 8788, 8789, 8791, 8793, 8795)
UI = Path(__file__).resolve().parents[1] / 'ui'


def validate_audio(raw):
    """Only bounded nonempty mono PCM16 WAV at 16kHz, at most four seconds."""
    if type(raw) is not bytes or not 0 < len(raw) <= contract.MAX_AUDIO:
        raise ValueError('invalid_audio')
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            frames = wav.getnframes()
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                    or wav.getframerate() != 16000 or wav.getcomptype() != 'NONE'
                    or not 1 <= frames <= 64000 or len(wav.readframes(frames)) != frames * 2):
                raise ValueError('invalid_audio')
    except (wave.Error, EOFError, OSError):
        raise ValueError('invalid_audio') from None


def validate_public_result(value, raw, request, audio):
    """Refuse any private evidence, changed binding, approval, or inconsistent status."""
    expected = contract.response(raw, request, audio)
    if (type(value) is not dict or set(value) != set(expected)
            or type(value['schemaVersion']) is not int or value['schemaVersion'] != 1
            or value['researchOnly'] is not True or value['bridgePromptMatch'] != 'unverified'
            or type(value['claimLimits']) is not dict or set(value['claimLimits']) != set(contract.CLAIMS)
            or any(flag is not False for flag in value['claimLimits'].values())
            or value['binding'] != expected['binding']
            or type(value['elapsedMilliseconds']) not in (int, float)
            or not math.isfinite(value['elapsedMilliseconds']) or value['elapsedMilliseconds'] < 0):
        raise ValueError('assessment_failed')
    flags = [value[key] for key in ('speechAdmissionPassed','wordAdmissionPassed','researchProcessed')]
    if value['status'] == 'processed':
        if value['reason'] is not None or any(flag is not True for flag in flags):
            raise ValueError('assessment_failed')
    elif value['status'] == 'unavailable':
        if type(value['reason']) is not str or value['reason'] not in contract.REASONS or any(flag is not False for flag in flags):
            raise ValueError('assessment_failed')
    else: raise ValueError('assessment_failed')
    return deepcopy(value)


class Server(ThreadingHTTPServer):
    daemon_threads = False
    request_queue_size = 2
    def __init__(self, executor, catalog, port=PORT, *, source_check=contract.verify_sources, resource_source_check=None):
        if type(port) is not int or not 0 <= port <= 65535 or port in RESERVED_PORTS: raise ValueError('invalid_port')
        self.executor, self.catalog, self.source_check = executor, catalog, source_check
        self.resource_source_check = resource_source_check
        self.resource_source = resource_source_check() if resource_source_check else None
        self.csrf_token = secrets.token_hex(32)
        self.handlers = threading.BoundedSemaphore(4)
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = f'http://127.0.0.1:{self.server_address[1]}'
    def process_request(self, request, address):
        if not self.handlers.acquire(blocking=False): self.shutdown_request(request); return
        try: super().process_request(request, address)
        except BaseException: self.handlers.release(); raise
    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.handlers.release()
    def handle_error(self, request, address): pass
    def declaration(self):
        available = not self.executor.is_blocked()
        try: pins = self.source_check()
        except (ValueError, OSError): pins = contract.bindings(); available = False
        return {'schemaVersion': 1, 'csrfToken': self.csrf_token,
                'pins': deepcopy(pins), 'processingAvailable': available}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    server_version = 'LocalConsumer'
    sys_version = ''
    def setup(self):
        super().setup(); self.connection.settimeout(5)
        self.deadline = threading.Timer(5, self.expire)
        self.deadline.daemon = True; self.deadline.start()
    def expire(self):
        try: self.connection.shutdown(socket.SHUT_RDWR)
        except OSError: pass
    def finish(self): self.deadline.cancel(); super().finish()
    def log_message(self, *args): pass
    def _one(self, name, optional=False):
        fields = self.headers.get_all(name, [])
        if not fields and optional: return None
        if len(fields) != 1: raise ValueError('invalid_request')
        return fields[0]
    def _guard(self, post=False):
        if len(self.headers) > 40 or self._one('Host') != self.server.origin.removeprefix('http://'):
            raise ValueError('invalid_request')
        if self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Range'):
            raise ValueError('invalid_request')
        if self._one('Sec-Fetch-Site', True) not in (None, 'same-origin', 'none'):
            raise ValueError('invalid_request')
        origin = self._one('Origin', True)
        if origin is not None and origin != self.server.origin: raise ValueError('invalid_request')
        if post and (origin != self.server.origin or not hmac.compare_digest(self._one('X-Consumer-CSRF'),self.server.csrf_token)):
            raise ValueError('invalid_request')
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '%' in parsed.path or '\\' in parsed.path:
            raise ValueError('invalid_request')
        return parsed.path
    def _reply(self, status, value, media='application/json; charset=utf-8'):
        self.deadline.cancel()
        raw = value if type(value) is bytes else contract.canonical(value)
        self.send_response(status)
        for key,val in (('Content-Type',media),('Content-Length',str(len(raw))),('Cache-Control','no-store'),
                        ('Connection','close'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),
                        ('Permissions-Policy','camera=(self), microphone=(self), geolocation=()'),
                        ('Content-Security-Policy',"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self'; img-src 'self'; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" if self.path!='/visual-worker.js' else "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")):
            self.send_header(key,val)
        self.end_headers(); self.close_connection = True
        try: self.wfile.write(raw)
        except (OSError, socket.timeout): pass
    def send_error(self, code, message=None, explain=None):
        self._reply(code, {'error':'invalid_request'})
    def _resource_value(self, read):
        """Only a complete startup-bound source may serve public resources."""
        check = self.server.resource_source_check
        if check is None or contract.canonical(check()) != contract.canonical(self.server.resource_source):
            raise ValueError('source_binding_failed')
        value = read()
        if contract.canonical(check()) != contract.canonical(self.server.resource_source):
            raise ValueError('source_binding_failed')
        return value
    def do_GET(self):
        try: path = self._guard()
        except (ValueError, TypeError): return self._reply(403, {'error':'invalid_request'})
        try:
            if path == '/api/feedback-declaration':
                return self._reply(200,self._resource_value(lambda:self.server.executor.feedback_declaration(self.server.csrf_token)))
            if path == '/api/catalog':
                return self._reply(200,self._resource_value(self.server.catalog.projection))
            if path.startswith('/visual/'):
                from .visual_assets import read_asset
                raw,media=self._resource_value(lambda:read_asset(path))
                return self._reply(200,raw,media)
            match = re.fullmatch('/api/public-references/([a-z]+)',path)
            if match: return self._reply(200,self._resource_value(lambda:self.server.catalog.reference(match[1])),'audio/wav')
            match = re.fullmatch(r'/illustrations/([a-z]+)\.svg',path)
            if match: return self._reply(200,self._resource_value(lambda:self.server.catalog.illustration(match[1])),'image/svg+xml')
        except (ValueError, OSError, KeyError, TypeError):
            return self._reply(503, {'error':'resource_unavailable'})
        self._reply(404, {'error':'not_found'})
    def do_POST(self):
        try: path = self._guard(post=True)
        except (ValueError, TypeError): return self._reply(403, {'error':'invalid_request'})
        if path != '/api/feedback': return self._reply(404, {'error':'not_found'})
        try:
            length = self._one('Content-Length')
            if (re.fullmatch('[0-9]{1,6}',length) is None or not 0 < int(length) <= contract.MAX_BODY
                    or self._one('Content-Type') not in ('application/json','application/json; charset=utf-8')):
                raise ValueError('invalid_request')
            raw = self.rfile.read(int(length))
            if len(raw) != int(length): raise ValueError('invalid_request')
            request,audio = feedback_contract.prepare(raw)
            if not self.server.catalog.accepts(request['prompt']): raise ValueError('invalid_prompt')
            validate_audio(audio)
        except (ValueError, OSError, TypeError, KeyError, RecursionError, Unavailable):
            return self._reply(400,{'error':'invalid_request'})
        self.deadline.cancel()
        try:
            from .feedback import validate_response
            output=validate_response(self._resource_value(lambda:self.server.executor.execute_feedback(raw)),raw,self.server.executor.declared_snapshot)
        except (ValueError,OSError,TypeError,KeyError,RecursionError):return self._reply(503,{'error':'feedback_unavailable'})
        self._reply(200,output)
    def do_OPTIONS(self): self._reply(405, {'error':'method_not_allowed'})
    do_PUT = do_OPTIONS; do_PATCH = do_OPTIONS; do_DELETE = do_OPTIONS; do_HEAD = do_OPTIONS


def main():
    # Direct -m entry cannot silently create an old/fallback runtime or service.
    raise ValueError('explicit_successor_launcher_required')
