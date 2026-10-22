from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import torch

import cmu_arctic_r_crop_preflight as preflight
from data import digest
from encoders import Wav2VecEncoder
from labels import parse_alignment, parse_timed_alignment


class FakeEncoder:
    identity = Wav2VecEncoder.identity

    def __init__(self):
        self.model = type("Model", (), {"config": type("Config", (), {
            "conv_kernel": preflight.KERNELS,
            "conv_stride": preflight.STRIDES,
        })()})()
        self.crops = []

    def __call__(self, samples):
        self.crops.append(samples.clone())
        count = preflight.conv_geometry(preflight.KERNELS, preflight.STRIDES, len(samples))[2]
        return torch.ones((count, 768), dtype=torch.float32)


class ArcticRCropPreflightTests(unittest.TestCase):
    def test_timed_parser_preserves_decimal_boundaries_and_token_wrapper(self):
        source = b"#\n0.040000 125 pau\n0.100000 125 r\n0.200000 125 aa\n"
        timed = parse_timed_alignment(source, 0.2)
        self.assertEqual(timed[1], (Decimal("0.040000"), Decimal("0.100000"), "r"))
        self.assertEqual(parse_alignment(source, 0.2), ["pau", "r", "aa"])

    def test_timed_parser_rejects_bad_times_and_format(self):
        sources = [b"#\n0.1 125 r\n0.09 125 aa\n", b"#\nNaN 125 r\n",
                   b"#\n0.2 125 r\n0.3 125 aa\n", b"#\n0.1 124 r\n",
                   b"#\n0.1 125 r\n0.2 125 unknown\n", b"#\nnot-a-time 125 r\n"]
        for source in sources:
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_timed_alignment(source, 0.2)
        for duration in (0, float("nan"), float("inf")):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                parse_timed_alignment(b"#\n0.1 125 r\n", duration)

    def test_only_train_rows_reach_timed_parser(self):
        rows = ([{"split": "train", "alignmentPath": "bdl/a.lab"} for _ in range(192)] +
                [{"split": "calibration", "alignmentPath": "rms/a.lab"} for _ in range(12)] +
                [{"split": "test", "alignmentPath": "slt/a.lab"} for _ in range(12)])
        self.assertEqual(len(preflight.train_rows(rows)), 192)
        self.assertTrue(all(row["split"] == "train" for row in preflight.train_rows(rows)))
        with self.assertRaisesRegex(ValueError, "Non-training"):
            preflight.interval_rows([rows[-1]], Path("/unused"))
        rows[0] = {"split": "test", "alignmentPath": "bdl/a.lab"}
        with self.assertRaisesRegex(ValueError, "split counts"):
            preflight.train_rows(rows)

    def test_crop_inference_is_local_and_short_intervals_are_excluded(self):
        samples = torch.arange(16000, dtype=torch.float32)
        intervals = [
            {"clipId": "train-a", "phoneIndex": 1, "startSeconds": "0.100000",
             "endSeconds": "0.200000", "samples": samples},
            {"clipId": "train-a", "phoneIndex": 2, "startSeconds": "0.200000",
             "endSeconds": "0.220000", "samples": samples},
        ]
        encoder = FakeEncoder()
        result = preflight.inspect_crops(intervals, encoder)
        self.assertEqual([row["status"] for row in result], ["valid", "tooShortForEncoder"])
        self.assertEqual((result[0]["startSample"], result[0]["endSample"]), (1600, 3200))
        self.assertTrue(torch.equal(encoder.crops[0], samples[1600:3200]))
        self.assertEqual(len(encoder.crops), 1)

    def test_out_of_bounds_interval_and_invalid_encoder_output_fail(self):
        interval = {"clipId": "train-a", "phoneIndex": 0,
                    "startSeconds": "0.9", "endSeconds": "1.1", "samples": torch.zeros(16000)}
        with self.assertRaisesRegex(ValueError, "outside verified audio"):
            preflight.inspect_crops([interval], FakeEncoder())
        interval["startSeconds"], interval["endSeconds"] = "0.1", "0.2"
        class BadEncoder(FakeEncoder):
            def __call__(self, samples):
                return torch.full((4, 768), float("nan"))
        with self.assertRaisesRegex(ValueError, "invalid crop frames"):
            preflight.inspect_crops([interval], BadEncoder())

    def test_pinned_source_tampering_is_rejected_before_inference(self):
        real_hash = preflight.sha256_file
        manifest = preflight.HERE / preflight.SOURCE_FILES["manifest"][0]
        with patch.object(preflight, "sha256_file", side_effect=lambda path:
                          "0" * 64 if path == manifest else real_hash(path)):
            with self.assertRaisesRegex(ValueError, "Pinned manifest"):
                preflight.load_recipe()

    def test_alignment_changed_after_manifest_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "train.lab").write_bytes(b"#\n0.2 125 r\n")
            row = {"split": "train", "samples": torch.zeros(3200),
                   "alignmentPath": "train.lab", "alignmentSha256": digest(b"original"),
                   "pseudoPhones": ["r"], "id": "train-a"}
            with self.assertRaisesRegex(ValueError, "changed after source validation"):
                preflight.interval_rows([row], root)

    def test_owner_only_one_shot_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result"
            with patch.object(preflight, "OUTPUT", output):
                preflight.publish({"schemaVersion": 1})
                self.assertEqual(output.stat().st_mode & 0o777, 0o700)
                self.assertEqual((output / "report.json").stat().st_mode & 0o777, 0o600)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    preflight.publish({"schemaVersion": 1})


if __name__ == "__main__":
    unittest.main()
