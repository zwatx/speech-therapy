"""Synthetic queue and loopback tests; no reviewer responses are collected."""

import hashlib
from http.server import HTTPServer
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import speechocean_r_annotation_reviewer_ui as ui


class ReviewerUiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.pack = self.base / "sample/local-reviewer-packs/reviewer-a"
        (self.pack / "media").mkdir(parents=True)
        (self.base / "sample").chmod(0o700)
        self.order = tuple(f"{index:016x}" for index in range(40))
        self.items = [{"reviewerId": clip_id, "audioFile": f"media/{clip_id}.wav",
                       "targetPrompt": "Synthetic prompt", "targetWord": "word",
                       "wordIndexZeroBased": 0, "phoneIndexWithinWordZeroBased": 2}
                      for clip_id in self.order]
        for index, clip_id in enumerate(self.order):
            (self.pack / "media" / f"{clip_id}.wav").write_bytes(b"RIFF" + bytes([index]))
        self.manifest_path = self.base / "sample/internal-manifest.json"
        self.manifest_path.write_text(json.dumps({"clips": [
            {"reviewerId": clip_id,
             "wavSha256": hashlib.sha256((self.pack / "media" / f"{clip_id}.wav").read_bytes()).hexdigest()}
            for clip_id in self.order]}))
        self.queue_path = self.pack / "queue.json"
        self.write_queue()

    def write_queue(self):
        self.queue_path.write_text(json.dumps({"reviewer": "reviewer-a", "items": self.items}))
        digest = hashlib.sha256(self.queue_path.read_bytes()).hexdigest()
        self.schema = {"reviewers": ["reviewer-a", "reviewer-b"],
                       "opaqueClips": 40, "sampleDirectory": "sample",
                       "internalManifestSha256": hashlib.sha256(self.manifest_path.read_bytes()).hexdigest(),
                       "reviewerPackQueueSha256": {"reviewer-a": digest}}

    def prepare(self):
        with patch.object(ui, "load_schema", return_value=self.schema), \
             patch.object(ui, "load_verified_pack_context",
                          return_value=({clip_id: 1.0 for clip_id in self.order},
                                        {"reviewer-a": self.order})):
            return ui.prepare_review("reviewer-a", self.base)

    def test_disabled_by_default_before_pack_preflight(self):
        error = io.StringIO()
        with patch.object(ui, "prepare_review") as preflight, \
             redirect_stderr(error), \
             self.assertRaises(SystemExit) as failed:
            ui.main(["reviewer-a"])
        self.assertEqual(failed.exception.code, 2)
        self.assertIn("Disabled by default", error.getvalue())
        preflight.assert_not_called()

    def test_publicly_traversable_sample_is_rejected_before_preflight(self):
        (self.base / "sample").chmod(0o755)
        with patch.object(ui, "load_schema", return_value=self.schema), \
             patch.object(ui, "load_verified_pack_context") as preflight, \
             self.assertRaisesRegex(ValueError, "Private sample directory"):
            ui.prepare_review("reviewer-a", self.base)
        preflight.assert_not_called()

    def test_requires_exact_verified_forty_item_queue(self):
        config, media = self.prepare()
        self.assertEqual(len(config["items"]), 40)
        self.assertEqual(tuple(item["reviewerId"] for item in config["items"]), self.order)
        self.assertEqual(set(media), set(self.order))
        self.items.pop()
        self.write_queue()
        with self.assertRaisesRegex(ValueError, "forty-clip"):
            self.prepare()
        self.items.append(self.items[0].copy())
        self.write_queue()
        with self.assertRaisesRegex(ValueError, "pack order"):
            self.prepare()

    def test_page_escapes_queue_text_and_exposes_only_selected_pack(self):
        self.items[0]["targetPrompt"] = "<script>alert(1)</script>"
        self.write_queue()
        config, media = self.prepare()
        page = ui.page_bytes(config).decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("\\u003cscript\\u003e", page)
        self.assertNotIn("sourceId", page)
        self.assertNotIn("speakerId", page)
        self.assertNotIn("reviewer-b", page)
        self.assertNotIn("__REVIEW_CONFIG__", page)
        self.assertEqual(len(media), 40)

    def test_loopback_routes_audio_range_and_no_label_write(self):
        config, media = self.prepare()
        server = HTTPServer(("127.0.0.1", 0), ui.make_handler(config, media))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        root = f"http://127.0.0.1:{server.server_port}"
        with urlopen(root + "/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"Export ordered JSON", response.read())
            self.assertIn("connect-src 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        audio_url = root + f"/media/{self.order[0]}.wav"
        (self.pack / "media" / f"{self.order[0]}.wav").write_bytes(b"changed")
        with urlopen(Request(audio_url, headers={"Range": "bytes=0-3"})) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], "bytes 0-3/5")
            self.assertEqual(response.read(), b"RIFF")
        with urlopen(audio_url) as response:
            self.assertEqual(response.read(), b"RIFF\x00")
        for request, status in [
            (Request(root + "/queue.json"), 404),
            (Request(root + "/media/../../queue.json"), 404),
            (Request(root + "/", data=b"synthetic label"), 405),
            (Request(root + "/", headers={"Host": "wrong.example"}), 403),
            (Request(audio_url, headers={"Range": "bytes=10-"}), 416),
        ]:
            with self.subTest(request=request.full_url), self.assertRaises(HTTPError) as failed:
                urlopen(request)
            self.assertEqual(failed.exception.code, status)
            failed.exception.close()
        self.assertEqual(set(self.pack.iterdir()), {self.pack / "queue.json", self.pack / "media"})


if __name__ == "__main__":
    unittest.main()
