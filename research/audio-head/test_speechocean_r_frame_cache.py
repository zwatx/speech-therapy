import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

from encoders import Wav2VecEncoder
from speechocean_r_frame_cache import (expected_index, prepared_inputs,
                                       publish_frames, validate_existing)


class FakeEncoder:
    identity = Wav2VecEncoder.identity

    def __init__(self):
        self.model = type("Model", (), {"config": type("Config", (), {
            "conv_kernel": [10, 3, 3, 3, 3, 2, 2],
            "conv_stride": [5, 2, 2, 2, 2, 2, 2],
        })()})()

    def __call__(self, pcm):
        return torch.full((1, 768), float(pcm[0]), dtype=torch.float32)


def synthetic_rows():
    return [{"reviewerId": f"{number:016x}", "wavSha256": f"{number:064x}",
             "wavPath": f"/unused/{number}.WAV", "age": 9, "aggregateRScore": 2}
            for number in range(40)]


class FrozenFrameCacheTests(unittest.TestCase):
    def test_unlabeled_index_and_atomic_private_cache_with_verified_reuse(self):
        rows = synthetic_rows()
        with patch("speechocean_r_frame_cache.read_rating_pcm",
                   side_effect=[torch.full((400,), float(i)) for i in range(40)]) as reader:
            samples, index_rows = prepared_inputs(rows)
        self.assertEqual(reader.call_count, 40)
        expected = expected_index("wav2vec2-base", index_rows)
        serialized = json.dumps(expected)
        for forbidden in ("aggregateRScore", "fiveRaterScores", "speakerId", "age",
                          "targetPrompt", "blindingKeyHex", "sourceId", "wavPath"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(expected["frameCount"], 40)
        self.assertFalse(expected["trainingEligible"])
        self.assertFalse(expected["clinicalUseEligible"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "wav2vec2-base"
            result = publish_frames(directory, expected, samples, FakeEncoder())
            self.assertFalse(result["reused"])
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            for name in ("frames.npy", "index.json"):
                self.assertEqual(stat.S_IMODE((directory / name).stat().st_mode), 0o600)
            self.assertEqual(list(root.glob(".frozen-frames-*")), [])
            cached = np.load(directory / "frames.npy", allow_pickle=False)
            self.assertEqual(cached.shape, (40, 768))
            self.assertEqual(cached[39, 0], 39)
            self.assertTrue(validate_existing(directory, expected)["reused"])
            with (directory / "frames.npy").open("r+b") as frame_file:
                frame_file.seek(-1, 2)
                frame_file.write(b"x")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                validate_existing(directory, expected)

    def test_rejects_partial_redirected_and_mismatched_cache(self):
        rows = synthetic_rows()
        with patch("speechocean_r_frame_cache.read_rating_pcm",
                   return_value=torch.zeros(400)):
            samples, index_rows = prepared_inputs(rows)
        expected = expected_index("wav2vec2-base", index_rows)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "wav2vec2-base"
            directory.mkdir(mode=0o700)
            with self.assertRaisesRegex(ValueError, "Partial"):
                validate_existing(directory, expected)
            directory.rmdir()
            publish_frames(directory, expected, samples, FakeEncoder())
            changed = dict(expected, sampleManifestSha256="0" * 64)
            with self.assertRaisesRegex(ValueError, "provenance changed"):
                validate_existing(directory, changed)
            (directory / "index.json").unlink()
            (directory / "index.json").symlink_to(directory / "frames.npy")
            with self.assertRaisesRegex(ValueError, "redirected"):
                validate_existing(directory, expected)

    def test_rejects_bad_frame_shape_without_publishing(self):
        rows = synthetic_rows()
        with patch("speechocean_r_frame_cache.read_rating_pcm",
                   return_value=torch.zeros(400)):
            samples, index_rows = prepared_inputs(rows)
        expected = expected_index("wav2vec2-base", index_rows)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "wav2vec2-base"
            class WrongShape(FakeEncoder):
                def __call__(self, pcm):
                    return torch.zeros((2, 768))
            with self.assertRaisesRegex(ValueError, "frame shape"):
                publish_frames(directory, expected, samples, WrongShape())
            self.assertFalse(directory.exists())
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
