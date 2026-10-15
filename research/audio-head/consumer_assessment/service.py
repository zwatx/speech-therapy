"""Loopback-only, bounded research endpoint. No HTTP request logging or CORS."""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from consumer_assessment.bridge import MAX_BODY, FLAGS, CleanupUnconfirmed, assess, response_base


def acceptable_headers(headers, port):
    # Origin rejection closes browser initiation; Host pin prevents DNS rebinding.
    if headers.get('Origin') is not None: return ('invalid_request',403)
    if headers.get('Host') not in {f'127.0.0.1:{port}',f'localhost:{port}'}: return ('invalid_request',403)
    if headers.get('Content-Type') != 'application/json': return ('invalid_request',415)
    if headers.get('Transfer-Encoding') is not None: return ('invalid_request',400)
    length = headers.get('Content-Length','')
    if len(length) > 6: return ('request_too_large',413)
    if not length.isascii() or not length.isdigit() or int(length) <= 0: return ('invalid_request',400)
    if int(length) > MAX_BODY: return ('request_too_large',413)
    return None


def status_for(response):
    reason = response['reason']
    if reason is None or reason in ('silence','clipping'): return 200
    if reason == 'request_too_large': return 413
    if reason == 'busy': return 429
    if reason == 'timeout': return 504
    if reason in ('model_unavailable','inference_failed'): return 503
    return 400


class LocalServer(ThreadingHTTPServer):
    daemon_threads = False
    request_queue_size = 2
    def __init__(self, port=8765):
        self.inference_slot = threading.BoundedSemaphore(1)
        self.cleanup_failure = None
        self.handler_slots = threading.BoundedSemaphore(4)
        super().__init__(('127.0.0.1',port),Handler)
    def process_request(self, request, address):
        if not self.handler_slots.acquire(blocking=False):
            # Refuse excess sockets before spawning another thread.
            self.shutdown_request(request); return
        try: super().process_request(request,address)
        except BaseException:
            self.handler_slots.release(); raise
    def process_request_thread(self, request, address):
        try: super().process_request_thread(request,address)
        finally: self.handler_slots.release()
    def handle_error(self, request, address): pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalResearch'
    def setup(self):
        super().setup(); self.connection.settimeout(5)
        self.read_deadline=threading.Timer(5,self.expire_read)
        self.read_deadline.daemon=True; self.read_deadline.start()
    def expire_read(self):
        try: self.connection.shutdown(socket.SHUT_RDWR)
        except OSError: pass
    def finish(self):
        self.read_deadline.cancel(); super().finish()
    def log_message(self,*args): pass
    def send_json(self, value, status):
        self.read_deadline.cancel()
        payload=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store')
        self.send_header('Connection','close'); self.end_headers()
        try: self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError,socket.timeout): pass
        self.close_connection=True
    def do_GET(self):
        if self.path != '/health' or self.headers.get('Origin') is not None or self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
            self.send_json({'available':False,**FLAGS},404); return
        if self.server.cleanup_failure is not None:
            self.send_json({'available':False,**FLAGS},503); return
        # Liveness only, deliberately does not claim a loaded/working model.
        self.send_json({'available':True,'modelAvailability':'checked_per_attempt',**FLAGS},200)
    def do_POST(self):
        if self.path != '/v1/assessment': self.send_json({'error':'not_found',**FLAGS},404); return
        if any(len(self.headers.get_all(name,[])) > 1 for name in ('Host','Origin','Content-Type','Content-Length','Transfer-Encoding')):
            error=('invalid_request',400)
        else: error=acceptable_headers(self.headers,self.server.server_port)
        if error:
            result=response_base(b''); result['reason']=error[0]; self.send_json(result,error[1]); return
        try:
            data=self.rfile.read(int(self.headers['Content-Length']))
            if len(data) != int(self.headers['Content-Length']): raise ValueError('short body')
        except (socket.timeout,OSError,ValueError):
            result=response_base(b''); result['reason']='invalid_request'; self.send_json(result,400); return
        self.read_deadline.cancel()
        if not self.server.inference_slot.acquire(blocking=False):
            result=response_base(data); result['reason']='busy'; self.send_json(result,429); return
        try: result=assess(data)
        finally: self.server.inference_slot.release()
        self.send_json(result,status_for(result))
    def do_OPTIONS(self): self.send_json({'error':'origin_not_supported',**FLAGS},403)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not 1 <= args.port <= 65535: parser.error('port must be in1..65535')
    with LocalServer(args.port) as server:
        print(f'Local research service listening at http://127.0.0.1:{server.server_port}',flush=True)
        try: server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt: pass
