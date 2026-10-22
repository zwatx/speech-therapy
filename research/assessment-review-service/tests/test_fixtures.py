import io
import hashlib
import copy
from pathlib import Path
import struct
import unittest
import wave

from workbench.demo import make_manifest
from workbench.content import prepare_content_manifest
from workbench.domain import ValidationError, validate_manifest

from review_service import fixtures


class FixtureTests(unittest.TestCase):
    def test_wave_is_fixed_low_amplitude_pcm_with_no_attempt_identity(self):
        content = fixtures.fixture_wave()
        self.assertEqual(len(content), 38444)
        self.assertEqual(hashlib.sha256(content).hexdigest(), "defd84856f9d6390d9a0e09ea01331d3b2afc998d84936981521860f0df58a84")
        self.assertEqual(content, fixtures.fixture_wave())
        with wave.open(io.BytesIO(content), "rb") as recording:
            self.assertEqual((recording.getnchannels(), recording.getsampwidth(), recording.getframerate(),
                              recording.getnframes(), recording.getcomptype()), (1, 2, 16000, 19200, "NONE"))
            samples = struct.unpack("<19200h", recording.readframes(19200))
            self.assertLessEqual(max(abs(sample) for sample in samples), 800)
            self.assertGreater(max(samples), 0)
            self.assertLess(min(samples), 0)

    def test_manifest_binds_same_real_wave_for_all_nine_recordings_without_derived_labels(self):
        manifest = fixtures.fixture_manifest()
        self.assertEqual(manifest["projectId"], "demo-review")
        self.assertIn("nonspeech", manifest["title"].lower())
        self.assertEqual(validate_manifest(manifest), manifest)
        present = [attempt["recording"] for attempt in manifest["attempts"] if attempt["recording"]]
        self.assertEqual(len(present), 9)
        self.assertTrue(all(recording["sha256"] == hashlib.sha256(fixtures.fixture_wave()).hexdigest()
                            and recording["durationMs"] == 1200 and recording["origin"] == "synthetic"
                            for recording in present))
        self.assertEqual(manifest["participants"], make_manifest()["participants"])
        self.assertEqual(manifest["prompts"], make_manifest()["prompts"])
        manifest["prompts"][0]["word"] = "Mutation"
        self.assertEqual(fixtures.fixture_manifest()["prompts"][0]["word"], "rabbit")

    def test_origin_accepts_only_exact_generated_fixture_or_fixed_pending_public_pack(self):
        pack_bytes = (Path(__file__).resolve().parents[3] / "docs/consumer-assessment/proposed-engineering-pack.json").read_bytes()
        self.assertEqual(hashlib.sha256(pack_bytes).hexdigest(), fixtures.PUBLIC_PACK_SHA256)
        fixture = fixtures.fixture_manifest()
        self.assertEqual(fixtures.validate_manifest_origin(fixture, pack_bytes), "fixture")
        pending = prepare_content_manifest(pack_bytes)
        self.assertEqual(fixtures.validate_manifest_origin(pending, pack_bytes), "content-preparation")
        self.assertEqual(pending["projectId"], "content-preparation-a957a9e3291f0d90")
        self.assertEqual((len(pending["prompts"]), len(pending["participants"]), len(pending["attempts"])), (15, 0, 0))
        self.assertEqual(sum(len(prompt["variants"]) for prompt in pending["prompts"]), 17)
        self.assertEqual(sum(len(variant["occurrenceIndexes"]) for prompt in pending["prompts"]
                             for variant in prompt["variants"]), 23)
        self.assertTrue(all(prompt["engineeringStatus"] == "pending" for prompt in pending["prompts"]))
        altered = copy.deepcopy(fixture)
        altered["attempts"][0]["recording"]["assetId"] = "../../PRIVATE_SOURCE"
        for manifest, pack in ((make_manifest(), pack_bytes), (altered, pack_bytes),
                               (pending, pack_bytes + b" "), ({**pending, "title": "Other"}, pack_bytes),
                               (pending, b"{}"), ({}, pack_bytes)):
            with self.subTest(manifest=manifest.get("projectId")):
                with self.assertRaises(ValidationError) as error:
                    fixtures.validate_manifest_origin(manifest, pack)
                self.assertEqual(str(error.exception), "manifest_origin_invalid")


if __name__ == "__main__":
    unittest.main()
