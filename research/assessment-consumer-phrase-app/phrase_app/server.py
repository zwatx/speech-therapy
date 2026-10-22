"""Bounded stdlib HTTP boundary. Only production loopback port 8821 is owned."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import signal
import sys

if __package__ in (None, ""):
    # Reviewed stdlib app boundary only; source guard runs before runtime or
    # listener construction, and no prototype/model module is imported here.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from phrase_app.service import APP, MAX_JSON, SafeError, Service, SourceGuard, canonical, parse, read, require
else:
    from .service import APP, MAX_JSON, SafeError, Service, SourceGuard, canonical, parse, read, require


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, service):
        require(address[0] == "127.0.0.1", "loopback_required")
        # Injectable generated test services may use an ephemeral owned socket.
        service.guard.check()
        self.service = service
        super().__init__(address, Handler)
        self.authority = "127.0.0.1:" + str(self.server_address[1])
        self.origin = "http://" + self.authority

    def handle_error(self, _request, _client_address):
        pass  # No default traceback or request-address logging.


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PhraseLocal"
    sys_version = ""

    def log_message(self, *_args):
        pass  # No filenames, request text, audio or path-bearing HTTP logs.

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def _headers(self, *, mutate=False):
        require(self.headers.get_all("Host", []) == [self.server.authority], "invalid_host", 403)
        origins = self.headers.get_all("Origin", [])
        require(origins == [self.server.origin] if mutate else (not origins or origins == [self.server.origin]), "invalid_origin", 403)
        fetch_sites = self.headers.get_all("Sec-Fetch-Site", [])
        require(not fetch_sites or fetch_sites == ["same-origin"] or fetch_sites == ["none"], "invalid_origin", 403)
        if mutate:
            tokens = self.headers.get_all("X-CSRF-Token", [])
            require(len(tokens) == 1 and tokens[0].isascii() and hmac.compare_digest(tokens[0], self.server.service.csrf), "invalid_csrf", 403)

    def _body(self):
        require(not self.headers.get_all("Transfer-Encoding"), "invalid_request")
        require(self.headers.get_all("Content-Type", []) == ["application/json"], "expected_json", 415)
        lengths = self.headers.get_all("Content-Length", [])
        require(len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit(), "invalid_length")
        count = int(lengths[0])
        require(1 <= count <= MAX_JSON, "request_too_large", 413)
        raw = self.rfile.read(count)
        require(len(raw) == count, "incomplete_request")
        return parse(raw)

    def _send(self, status, value, *, content_type="application/json; charset=utf-8"):
        payload = canonical(value) if content_type.startswith("application/json") else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def _dispatch(self, mutate):
        try:
            self._headers(mutate=mutate)
            if mutate:
                request = self._body()
                if self.path == "/api/check":
                    self._send(202, self.server.service.submit(request))
                elif self.path == "/api/cancel":
                    require(type(request) is dict and set(request) == {"jobId"}, "invalid_request")
                    # Cancellation remains available after source drift so the
                    # owned waiter can stop; it does not expose a usable result.
                    self._send(200, self.server.service.cancel(request["jobId"]))
                else:
                    raise SafeError("not_found", 404)
            elif self.path == "/api/catalog":
                self._send(200, self.server.service.catalog())
            elif self.path.startswith("/api/jobs/") and self.path.count("/") == 3:
                self._send(200, self.server.service.get(self.path.removeprefix("/api/jobs/")))
            else:
                self.server.service.guard.check()
                # No dynamic path joins, directory listing, traversal, query
                # aliases or access to the private runtime/output directories.
                assets = {"/": ("index.html", "text/html; charset=utf-8"),
                          "/index.html": ("index.html", "text/html; charset=utf-8"),
                          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/app.css": ("app.css", "text/css; charset=utf-8")}
                require(self.path in assets, "not_found", 404)
                name, content_type = assets[self.path]
                self._send(200, read(self.server.service.app / "ui" / name, 1_000_000), content_type=content_type)
        except SafeError as error:
            self._send(error.status, {"error": error.tag})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # Client disconnect is never cancellation; the actual wait owner
            # continues collecting this explicitly accepted check.
            self.close_connection = True
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            self._send(500, {"error": "request_failed"})

    def do_GET(self):
        self._dispatch(False)

    def do_POST(self):
        self._dispatch(True)

    def do_OPTIONS(self):
        self._send(405, {"error": "method_not_allowed"})

    def do_HEAD(self):
        self._send(405, {"error": "method_not_allowed"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify source pins only; no runtime, listener or models")
    parser.add_argument("--runtime-root", type=Path, help="New absolute private directory; existing paths are refused")
    parser.add_argument("--port", type=int, default=8821, help="Owned loopback port (8821)")
    args = parser.parse_args(argv)
    try:
        require(args.port == 8821, "owned_port_8821_required")
        guard = SourceGuard(APP)
        if args.check:
            print(json.dumps({"status": "source_verified", "researchOnly": True}))
            return 0
        require(args.runtime_root is not None, "fresh_runtime_required")
        service = Service(args.runtime_root, guard=guard)
        server = Server(("127.0.0.1", args.port), service)
    except (SafeError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"error": "startup_refused"}))
        return 2
    previous = {}
    def stop(_signal, _frame):
        raise KeyboardInterrupt
    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, stop)
        print(json.dumps({"status": "listening", "url": server.origin, "researchOnly": True}), flush=True)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        server.server_close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
