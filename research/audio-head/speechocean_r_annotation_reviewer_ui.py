"""Provisional, read-only loopback UI for one pinned SpeechOcean /R/ pack.

This tool is disabled unless explicitly enabled. It stores no responses: the
browser keeps draft answers in memory and creates the JSON download locally.
The draft protocol still requires qualified SLP and study-owner signoff before
real annotation.
"""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import stat

from speechocean_r_annotation_intake import (
    HERE, OPAQUE_ID, checked_file, load_schema, load_verified_pack_context,
    require,
)


PAGE = Path(__file__).with_suffix(".html")
MEDIA_PATH = re.compile(r"/media/([0-9a-f]{16})\.wav\Z")


def prepare_review(reviewer: str, base: Path = HERE) -> tuple[dict, dict[str, bytes]]:
    """Preflight the complete locked sample, then expose one pack's public queue."""
    schema = load_schema()
    require(reviewer in schema["reviewers"], "Unknown reviewer")
    sample = base / schema["sampleDirectory"]
    sample_stat = sample.stat()
    require(not sample.is_symlink() and sample.is_dir() and
            sample_stat.st_uid == os.geteuid() and
            stat.S_IMODE(sample_stat.st_mode) & 0o077 == 0,
            "Private sample directory must be owned by the launcher and inaccessible to other accounts")
    durations, orders = load_verified_pack_context(schema, base)
    manifest = checked_file(sample / "internal-manifest.json",
                            schema["internalManifestSha256"])
    expected_audio = {item["reviewerId"]: item["wavSha256"]
                      for item in manifest["clips"]}
    pack = sample / "local-reviewer-packs" / reviewer
    queue = checked_file(pack / "queue.json", schema["reviewerPackQueueSha256"][reviewer])
    require(queue.get("reviewer") == reviewer and type(queue.get("items")) is list and
            len(queue["items"]) == schema["opaqueClips"] == 40,
            "Reviewer queue differs from verified forty-clip pack")
    allowed = {"reviewerId", "audioFile", "targetPrompt", "targetWord",
               "wordIndexZeroBased", "phoneIndexWithinWordZeroBased"}
    items = []
    media = {}
    for item, clip_id in zip(queue["items"], orders[reviewer], strict=True):
        require(type(item) is dict and set(item) == allowed and
                type(item.get("reviewerId")) is str and
                OPAQUE_ID.fullmatch(item["reviewerId"]) and
                item["reviewerId"] == clip_id and
                item["audioFile"] == f"media/{clip_id}.wav",
                "Reviewer queue item differs from verified pack order")
        items.append({**item, "durationSeconds": durations[clip_id]})
        audio = (pack / "media" / f"{clip_id}.wav").read_bytes()
        require(hashlib.sha256(audio).hexdigest() == expected_audio[clip_id],
                "Reviewer WAV changed after verified pack preflight")
        media[clip_id] = audio
    require(len(media) == 40, "Reviewer queue has duplicate opaque IDs")
    return {"reviewer": reviewer, "items": items}, media


def page_bytes(config: dict) -> bytes:
    # An escaped JSON literal cannot close the inline script element.
    payload = json.dumps(config, separators=(",", ":"), ensure_ascii=True)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
    payload = payload.replace("&", "\\u0026")
    template = PAGE.read_text(encoding="utf-8")
    require(template.count("__REVIEW_CONFIG__") == 1, "Reviewer page template changed")
    return template.replace("__REVIEW_CONFIG__", payload).encode("utf-8")


def make_handler(config: dict, media: dict[str, bytes]) -> type[BaseHTTPRequestHandler]:
    page = page_bytes(config)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _respond(self, body: bytes, content_type: str, status: int = 200,
                     extra: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; media-src 'self'; "
                             "connect-src 'none'; form-action 'none'; base-uri 'none'; "
                             "frame-ancestors 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self) -> None:
            # Reject DNS rebinding and never accept a path to arbitrary files.
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{self.server.server_port}",
                            f"localhost:{self.server.server_port}"}:
                self._respond(b"", "text/plain", 403)
                return
            if self.path == "/":
                self._respond(page, "text/html; charset=utf-8")
                return
            match = MEDIA_PATH.fullmatch(self.path)
            if match and match.group(1) in media:
                audio = media[match.group(1)]
                total = len(audio)
                byte_range = self.headers.get("Range")
                if byte_range:
                    selected = re.fullmatch(r"bytes=(\d{1,20})-(\d{0,20})", byte_range)
                    if not selected or int(selected.group(1)) >= total:
                        self._respond(b"", "text/plain", 416,
                                      {"Content-Range": f"bytes */{total}"})
                        return
                    start = int(selected.group(1))
                    end = min(int(selected.group(2)), total - 1) if selected.group(2) else total - 1
                    if end < start:
                        self._respond(b"", "text/plain", 416,
                                      {"Content-Range": f"bytes */{total}"})
                        return
                    self._respond(audio[start:end + 1], "audio/wav", 206,
                                  {"Accept-Ranges": "bytes",
                                   "Content-Range": f"bytes {start}-{end}/{total}"})
                    return
                self._respond(audio, "audio/wav", extra={"Accept-Ranges": "bytes"})
                return
            self._respond(b"", "text/plain", 404)

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_POST(self) -> None:
            self._respond(b"", "text/plain", 405)

        def do_PUT(self) -> None:
            self._respond(b"", "text/plain", 405)

    return Handler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewer", choices=("reviewer-a", "reviewer-b"))
    parser.add_argument("--enable-provisional-review", action="store_true",
                        help="Explicitly enable the local draft page after protocol signoff")
    args = parser.parse_args(argv)
    if not args.enable_provisional_review:
        parser.error("Disabled by default; protocol signoff is required before real annotation")
    try:
        config, media = prepare_review(args.reviewer)
        server = HTTPServer(("127.0.0.1", 0), make_handler(config, media))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f"Pinned reviewer-pack preflight failed: {error}")
    print(f"Provisional local page: http://127.0.0.1:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
