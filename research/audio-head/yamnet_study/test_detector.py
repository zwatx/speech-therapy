"""Unit tests for detector.py. No TensorFlow, no real model, no external data."""
import hashlib
import importlib.util
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

_spec = importlib.util.spec_from_file_location("yamnet_detector", Path(__file__).with_name("detector.py"))
detector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(detector)

W, H, C = 15600, 7680, 521


def riff(data, fmt_tag=1, channels=1, rate=16000, width=2):
    block = channels * width
    fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * block, block, width * 8)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def pcm16(values):
    return np.asarray(values, dtype="<i2").tobytes()


def scores(windows, speech=0.0, others=0.0):
    s = np.full((windows, C), others, dtype=np.float32)
    s[:, 0] = speech
    return s


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, blob, name="a.wav"):
        path = self.dir / name
        path.write_bytes(blob)
        return path, hashlib.sha256(blob).hexdigest()


class GeometryTests(unittest.TestCase):
    def test_boundaries(self):
        cases = {1: (1, W), W - 1: (1, W), W: (1, W), W + 1: (2, W + H), W + H: (2, W + H),
                 W + H + 1: (3, W + 2 * H), 160000: (20, W + 19 * H)}
        for n, expected in cases.items():
            self.assertEqual(detector.geometry(n), expected, n)
        self.assertEqual(detector.geometry(np.int64(W + 1)), (2, W + H))

    def test_rejects_bad_counts(self):
        for bad in (True, np.bool_(True), 1.0, "16000", None):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                detector.geometry(bad)
        for bad in (0, -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                detector.geometry(bad)


class ReadPcmTests(Fixture):
    def test_exact_amplitudes(self):
        path, sha = self.write(riff(pcm16([-32768, -1, 0, 1, 32767])))
        out = detector.read_pcm(path, sha, 5)
        self.assertEqual((out.dtype, out.ndim), (np.float32, 1))
        expected = np.array([-1.0, -1 / 32768, 0.0, 1 / 32768, 32767 / 32768], dtype=np.float32)
        np.testing.assert_array_equal(out, expected)

    def test_rejects_hash_and_count_mismatches(self):
        path, sha = self.write(riff(pcm16(range(100))))
        with self.assertRaisesRegex(ValueError, "sha256"):
            detector.read_pcm(path, "0" * 64, 100)
        for bad_sha in (sha.upper(), sha[:-1]):
            with self.assertRaises(ValueError):
                detector.read_pcm(path, bad_sha, 100)
        for n, error in ((99, ValueError), (101, ValueError), (0, ValueError), (True, TypeError), (100.0, TypeError)):
            with self.subTest(n=n), self.assertRaises(error):
                detector.read_pcm(path, sha, n)

    def test_hash_checked_before_parsing(self):
        path, sha = self.write(b"not a wav file at all")
        with self.assertRaisesRegex(ValueError, "sha256"):
            detector.read_pcm(path, "f" * 64, 1)
        with self.assertRaisesRegex(ValueError, "readable PCM WAV"):
            detector.read_pcm(path, sha, 1)

    def test_rejects_wrong_format(self):
        # Each blob holds exactly 100 frames, so only the format can be the failure reason.
        cases = {
            "stereo": (riff(pcm16(range(200)), channels=2), "mono 16 kHz"),
            "8 kHz": (riff(pcm16(range(100)), rate=8000), "mono 16 kHz"),
            "44.1 kHz": (riff(pcm16(range(100)), rate=44100), "mono 16 kHz"),
            "8-bit": (riff(bytes(100), width=1), "mono 16 kHz"),
            "24-bit": (riff(bytes(300), width=3), "mono 16 kHz"),
            "float32": (riff(np.zeros(100, "<f4").tobytes(), fmt_tag=3, width=4), "readable PCM WAV"),
        }
        for label, (blob, pattern) in cases.items():
            with self.subTest(label):
                path, sha = self.write(blob)
                with self.assertRaisesRegex(ValueError, pattern):
                    detector.read_pcm(path, sha, 100)

    def test_rejects_truncated_data(self):
        for cut in (1, 2, 10):
            with self.subTest(cut=cut):
                path, sha = self.write(riff(pcm16(range(100)))[:-cut])
                with self.assertRaisesRegex(ValueError, "expected 100 samples"):
                    detector.read_pcm(path, sha, 100)


class ScoresTests(unittest.TestCase):
    def test_summary_uses_max_speech_window(self):
        s = scores(2)
        s[1, 0] = 0.75
        self.assertEqual(detector.validate_scores(s, W + 1), {
            "sampleCount": W + 1, "paddedSampleCount": W + H, "windows": 2, "speechScore": 0.75, "accepted": True})

    def test_threshold_is_inclusive(self):
        below = np.nextafter(np.float32(0.5), np.float32(0))
        self.assertTrue(detector.validate_scores(scores(1, speech=0.5), W)["accepted"])
        self.assertFalse(detector.validate_scores(scores(1, speech=below), W)["accepted"])

    def test_other_classes_cannot_trigger_speech(self):
        summary = detector.validate_scores(scores(3, speech=0.0, others=1.0), W + 2 * H)
        self.assertEqual((summary["speechScore"], summary["accepted"]), (0.0, False))

    def test_rejects_malformed_scores(self):
        for label, value in {"nan": np.nan, "inf": np.inf, "negative": -0.01, "above one": 1.01}.items():
            s = scores(1)
            s[0, 5] = value
            with self.subTest(label), self.assertRaises(ValueError):
                detector.validate_scores(s, W)
        for shape in ((2, C), (1, C - 1), (1, C + 1), (0, C), (C,), (1, 1, C)):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                detector.validate_scores(np.zeros(shape, np.float32), W)
        for bad in (scores(1).astype(np.float64), scores(1).tolist()):
            with self.assertRaises(TypeError):
                detector.validate_scores(bad, W)


class FakeTensor:
    def __init__(self, array):
        self.array = array

    def numpy(self):
        return self.array


class FakeModel:
    def __init__(self, outputs):
        self.outputs, self.calls = outputs, []

    def __call__(self, waveform, training=None):
        self.calls.append((waveform, training))
        return self.outputs


class InferTests(unittest.TestCase):
    def test_passes_unmodified_waveform_once(self):
        waveform = np.linspace(-1, 1, W + 1, dtype=np.float32)
        original = waveform.copy()
        s = scores(2, speech=0.6)
        model = FakeModel([FakeTensor(s), "embeddings", "spectrogram"])
        out, summary = detector.infer(model, waveform)
        self.assertEqual(len(model.calls), 1)
        self.assertIs(model.calls[0][0], waveform)
        self.assertIs(model.calls[0][1], False)
        np.testing.assert_array_equal(waveform, original)
        self.assertIs(out, s)
        self.assertEqual((summary["windows"], summary["accepted"]), (2, True))

    def test_plain_arrays_and_bad_outputs(self):
        edge = np.array([-1.0, 1.0], np.float32)
        self.assertFalse(detector.infer(FakeModel((scores(1), None, None)), edge)[1]["accepted"])
        with self.assertRaises(TypeError):
            detector.infer(FakeModel((scores(1).astype(np.float64), None, None)), edge)
        with self.assertRaises(ValueError):
            detector.infer(FakeModel((scores(1), None)), edge)
        with self.assertRaises(ValueError):
            detector.infer(FakeModel((scores(2), None, None)), edge)

    def test_rejects_bad_waveforms_without_calling_model(self):
        model = FakeModel((scores(1), None, None))
        cases = [(np.zeros(W, np.float64), TypeError), ([0.0] * W, TypeError),
                 (np.zeros((1, W), np.float32), ValueError), (np.zeros(0, np.float32), ValueError),
                 (np.full(W, np.nan, np.float32), ValueError), (np.full(W, 1.5, np.float32), ValueError)]
        for i, (waveform, error) in enumerate(cases):
            with self.subTest(i), self.assertRaises(error):
                detector.infer(model, waveform)
        self.assertEqual(model.calls, [])


class LoadModelGuardTests(Fixture):
    """Guards that must fail before TensorFlow is imported."""

    def vendor(self, rows):
        for name in ("params.py", "features.py", "yamnet.py", "yamnet.h5"):
            (self.dir / name).write_bytes(b"")
        lines = ["index,mid,display_name"] + [f"{i},{mid},{name}" for i, (mid, name) in enumerate(rows)]
        (self.dir / "yamnet_class_map.csv").write_text("\n".join(lines) + "\n")
        return self.dir

    def good_rows(self):
        return [("/m/09x0r", "Speech")] + [(f"/m/x{i}", f"C{i}") for i in range(1, C)]

    def test_rejects_bad_class_map(self):
        rows = self.good_rows()
        cases = {"520 rows": rows[:-1], "522 rows": rows + [("/m/y", "Extra")],
                 "wrong name": [("/m/09x0r", "Child speech")] + rows[1:], "wrong mid": [("/m/0ytgt", "Speech")] + rows[1:]}
        for label, bad in cases.items():
            with self.subTest(label), self.assertRaises(RuntimeError):
                detector.load_model(self.vendor(bad))

    def test_rejects_shadowing_module(self):
        foreign = types.ModuleType("params")
        foreign.__file__ = str(Path(tempfile.gettempdir()) / "params.py")
        with mock.patch.dict(sys.modules, {"params": foreign}), self.assertRaisesRegex(RuntimeError, "shadow"):
            detector.load_model(self.vendor(self.good_rows()))


if __name__ == "__main__":
    unittest.main()
