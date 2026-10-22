"""Loopback simulator service; no browser origins, request logs or retained audio."""
import fcntl
import os
import shutil
import socket
import stat
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .contract import (ROOT, MAX_BODY, MAX_RESPONSE, canonical, prepare, response,
                       strict_json, verify_sources)
from .process import supervise

PORT = 8778
ENDPOINT = '/v1/admission'
TIMEOUT = 85
RUNTIME = ROOT / 'work/roadmap-completion-20261004/mobile/runtime'
PYTHON = ROOT / 'research/audio-head/.venv/bin/python'


def private_root(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700): raise ValueError('unsafe_runtime')


def block(path, name="cleanup-blocked"):
    """A durable marker survives restart; no automatic recovery after uncertain cleanup."""
    fd = os.open(path / name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, b'cleanup_unconfirmed\n'); os.fsync(fd)
    finally: os.close(fd)
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def save_runtime(path, runtime):
    """One bounded private diagnostic; no request, audio, argv, transcript or environment."""
    fields = ('elapsedSeconds', 'peakRssKiB', 'workerExitCode', 'timedOut', 'cancelled',
              'cleanupConfirmed', 'supervisionFailed', 'descendantsTerminated', 'cleanupFailurePhase', 'cleanupFailureCode',
              'scanCount', 'scanElapsedSeconds', 'scanMaximumSeconds', 'scanRetries')
    safe = {key: runtime[key] for key in fields if key in runtime}
    tracked = runtime.get('tracked', [])
    if type(tracked) is not list or len(tracked) > 128: raise ValueError('invalid_runtime')
    safe['tracked'] = [{key: record[key] for key in ('pid', 'ppid', 'state', 'started')}
                       for record in tracked]
    observed = runtime.get('lastObserved', [])
    if type(observed) is dict: observed = list(observed.values())
    if type(observed) is not list or len(observed) > 128: raise ValueError('invalid_runtime')
    tracked_ids = {record['pid'] for record in safe['tracked']}
    safe['lastObserved'] = [{key: record[key] for key in ('pid', 'ppid', 'state', 'started')}
                            for record in observed if record.get('pid') in tracked_ids]
    payload = canonical({'schemaVersion': 1, 'runtime': safe})
    if len(payload) > 32000: raise ValueError('invalid_runtime')
    temporary = path / f'.diagnostic-{uuid.uuid4()}.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as output: output.write(payload); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path / 'last-runtime.json')
        fd = os.open(path, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if temporary.exists(): temporary.unlink()


class Executor:
    def __init__(self, runtime=RUNTIME):
        self.runtime = runtime
        private_root(runtime)
        self.lock = os.open(runtime / 'service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        info = os.fstat(self.lock)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            os.close(self.lock); raise ValueError('unsafe_lock')
        try: fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException: os.close(self.lock); raise
        # Preserve interruption evidence; never delete unknown or possibly live worker files.
        if any(p.name.startswith('attempt-') for p in runtime.iterdir()): block(runtime)
        self.blocked = (runtime / "cleanup-blocked").exists() or (runtime / "cleanup-required").exists()
        self.slot = threading.BoundedSemaphore(1)

    def close(self): os.close(self.lock)

    def is_blocked(self):
        return (self.blocked or (self.runtime / 'cleanup-blocked').exists()
                or (self.runtime / 'cleanup-required').exists())

    def mark_blocked(self):
        self.blocked = True
        try: block(self.runtime)
        except OSError: pass  # Prelaunch intent or stage already survives restart.

    def execute(self, raw):
        started = time.monotonic()
        try: request, audio = prepare(raw)
        except Exception: return response(raw)
        output = response(raw, request, audio)
        if any(t['targetPhone'] == 'ZH' for t in request['prompt']['targets']):
            output['reason'] = 'unsupported_target'; return output
        if not self.slot.acquire(blocking=False):
            output['reason'] = 'busy'; return output
        stage = None
        cleanup_confirmed = False
        try:
            if self.is_blocked():
                output['reason'] = 'cleanup_unconfirmed'; return output
            try: verify_sources()
            except (ValueError, OSError):
                output['reason'] = 'source_binding_failed'; return output
            stage = Path(tempfile.mkdtemp(prefix='attempt-', dir=self.runtime))
            # Write/fsync intent BEFORE a model or nested worker may start. If any
            # later persistence fails, this intent prevents unsafe restart.
            block(self.runtime, 'cleanup-required')
            env = {**os.environ, 'PYTHONPATH': ':'.join(str(ROOT / p) for p in
                   ('research/assessment-mobile-admission', 'research/assessment-admission', 'research/audio-head')),
                   'TMPDIR': str(stage), 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                   'HF_HUB_DISABLE_TELEMETRY': '1', 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'}
            runtime = supervise([str(PYTHON), '-m', 'mobile_admission.worker', str(stage)], raw,
                                cwd=ROOT, env=env, timeout_seconds=TIMEOUT)
            cleanup_confirmed = runtime.get('cleanupConfirmed') is True
            save_runtime(self.runtime, runtime)
            if not cleanup_confirmed:
                self.mark_blocked(); output['reason'] = 'cleanup_unconfirmed'; return output
            if runtime.get('supervisionFailed') is True or runtime.get('cleanupFailurePhase') is not None:
                output['reason'] = 'assessment_failed'; return output
            if runtime['timedOut']:
                output['reason'] = 'timeout'; return output
            if runtime['workerExitCode'] != 0:
                output['reason'] = 'assessment_failed'; return output
            from admission.models import private_read
            result = strict_json(private_read(stage / 'result.json', MAX_RESPONSE))
            if (type(result) is not dict or set(result) != set(output)
                    or result['binding'] != output['binding'] or result['claimLimits'] != output['claimLimits']
                    or result['researchOnly'] is not True or result['bridgePromptMatch'] != 'unverified'):
                output['reason'] = 'research_binding_failed'; return output
            output = result
        except Exception:
            if stage is not None and not cleanup_confirmed:
                self.mark_blocked(); output['reason'] = 'cleanup_unconfirmed'
            else: output['reason'] = 'assessment_failed'
        finally:
            if stage is not None:
                if cleanup_confirmed:
                    try:
                        shutil.rmtree(stage)
                        (self.runtime / 'cleanup-required').unlink()
                        fd = os.open(self.runtime, os.O_RDONLY)
                        try: os.fsync(fd)
                        finally: os.close(fd)
                    except OSError: self.mark_blocked()
                else: self.mark_blocked()
                if self.is_blocked():
                    output.clear(); output.update(response(raw, request, audio, reason='cleanup_unconfirmed'))
            output['elapsedMilliseconds'] = (time.monotonic() - started) * 1000
            self.slot.release()
        return output


class LocalServer(ThreadingHTTPServer):
    daemon_threads = False
    request_queue_size = 2
    def __init__(self, executor):
        self.executor = executor
        self.handlers = threading.BoundedSemaphore(4)
        super().__init__(('127.0.0.1', PORT), Handler)
    def process_request(self, request, address):
        if not self.handlers.acquire(blocking=False): self.shutdown_request(request); return
        try: super().process_request(request, address)
        except BaseException: self.handlers.release(); raise
    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.handlers.release()
    def handle_error(self, request, address): pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'SimulatorAdmission'
    def setup(self):
        super().setup(); self.connection.settimeout(5)
        self.deadline = threading.Timer(5, self.expire); self.deadline.daemon = True; self.deadline.start()
    def expire(self):
        try: self.connection.shutdown(socket.SHUT_RDWR)
        except OSError: pass
    def finish(self): self.deadline.cancel(); super().finish()
    def log_message(self, *args): pass
    def send_json(self, value, status=200):
        self.deadline.cancel(); payload = canonical(value)
        self.send_response(status); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload))); self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close'); self.end_headers(); self.close_connection = True
        try: self.wfile.write(payload)
        except (OSError, socket.timeout): pass
    def allowed(self):
        return (self.headers.get('Origin') is None and self.headers.get('Host') == f'127.0.0.1:{PORT}'
                and all(len(self.headers.get_all(k, [])) <= 1 for k in
                        ('Host', 'Origin', 'Content-Type', 'Content-Length', 'Transfer-Encoding')))
    def do_GET(self):
        if self.path != '/health' or not self.allowed(): self.send_json({'available': False}, 403); return
        self.send_json({'available': True, 'researchOnly': True, 'modelAvailability': 'checked_per_attempt',
                        'cleanupBlocked': self.server.executor.blocked or (self.server.executor.runtime / 'cleanup-blocked').exists(),
                        'cleanupPending': (self.server.executor.runtime / 'cleanup-required').exists()})
    def do_POST(self):
        length = self.headers.get('Content-Length', '')
        if (self.path != ENDPOINT or not self.allowed() or self.headers.get('Content-Type') != 'application/json'
                or self.headers.get('Transfer-Encoding') is not None or len(length) > 6
                or not length.isascii() or not length.isdigit() or not 0 < int(length) <= MAX_BODY):
            self.send_json(response(b''), 400); return
        try:
            raw = self.rfile.read(int(length))
            if len(raw) != int(length): raise ValueError('short_body')
        except (OSError, ValueError): self.send_json(response(b''), 400); return
        self.deadline.cancel()
        self.send_json(self.server.executor.execute(raw))
    def do_OPTIONS(self): self.send_json({'available': False}, 403)


def main():
    verify_sources()
    executor = Executor()
    try:
        with LocalServer(executor) as server:
            print(f'Simulator research admission listening at http://127.0.0.1:{PORT}', flush=True)
            try: server.serve_forever(poll_interval=0.25)
            except KeyboardInterrupt: pass
    finally: executor.close()


if __name__ == '__main__': main()
