"""Synthetic-only WAV fixtures; no corpus or quality targets are read."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from . import waveform_audit as audit


def chunk(name, payload, pad=b"\0"):
    return name + struct.pack("<I", len(payload)) + payload + (pad if len(payload) & 1 else b"")


def fmt(bits=16, tag=1, channels=1, rate=8000, valid=None, guid=None):
    alignment = channels * (bits // 8)
    base = struct.pack("<HHIIHH", tag, channels, rate, rate * alignment, alignment, bits)
    if tag == 0xFFFE:
        return base + struct.pack("<HHI", 22, bits if valid is None else valid, 0) + (guid or audit.PCM_GUID)
    return base


def wave(*chunks):
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.wav"

    def run_wav(self, raw):
        self.path.write_bytes(raw)
        result = audit.audit_wav(self.path)
        json.dumps(result, allow_nan=False)
        return result

    def reject(self, raw, message=None):
        self.path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, message or "."):
            audit.audit_wav(self.path)

    def test_golden_stereo_metrics_and_hash(self):
        values = np.array([[-32768, 0], [16384, 32767]], dtype="<i2")
        raw = wave(chunk(b"fmt ", fmt(channels=2)), chunk(b"data", values.tobytes()))
        result = self.run_wav(raw)
        expected = np.array([[-1., 0.], [.5, 32767 / 32768]], dtype="<f8")
        self.assertEqual(result["decoded"], {"dtype": "<f8", "order": "C", "shape": [2, 2],
                         "sha256": hashlib.sha256(expected.tobytes()).hexdigest()})
        metrics = result["metrics"]
        self.assertEqual(metrics["durationSeconds"], 2 / 8000)
        self.assertEqual(metrics["peakAbs"], 1)
        self.assertAlmostEqual(metrics["rms"], float(np.sqrt(np.mean(expected ** 2))))
        self.assertEqual(metrics["exactZeroFraction"], .25)
        self.assertEqual(metrics["absLe1eMinus4Fraction"], .25)
        self.assertEqual(metrics["integerRailFraction"], .5)
        self.assertIsNone(metrics["floatDigitalFullScaleFraction"])
        self.assertEqual(result["input"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result, audit.audit_wav(self.path))

    def test_policy_is_json_safe_and_declares_fixed_bounds(self):
        json.dumps(audit.POLICY, allow_nan=False)
        self.assertEqual(audit.POLICY["maxInputBytes"], 134217728)
        self.assertEqual(audit.POLICY["maxChannels"], 64)
        self.assertEqual(audit.POLICY["maxSampleRate"], 768000)
        self.assertEqual(audit.POLICY["nearZeroThreshold"], 0.0001)
        self.assertFalse(audit.POLICY["outputDependentExclusion"])

    def test_all_pcm_widths_and_24_bit_sign_extension(self):
        for bits in (8, 16, 24, 32):
            scale = 1 << (bits - 1)
            integers = [-scale, 0, scale - 1]
            if bits == 8:
                payload = bytes(x + 128 for x in integers)
            else:
                payload = b"".join(x.to_bytes(bits // 8, "little", signed=True) for x in integers)
            with self.subTest(bits=bits):
                result = self.run_wav(wave(chunk(b"fmt ", fmt(bits)), chunk(b"data", payload)))
                expected = np.array(integers, dtype="<f8") / scale
                self.assertEqual(result["decoded"]["sha256"], hashlib.sha256(expected.tobytes()).hexdigest())
                self.assertEqual(result["metrics"]["integerRailFraction"], 2 / 3)

    def test_extensible_left_aligned_valid_bits(self):
        for bits, valid in ((8, 4), (16, 12), (24, 20), (32, 24)):
            scale = 1 << (valid - 1)
            ints = [-scale, 0, scale - 1]
            shifted = [x << (bits - valid) for x in ints]
            payload = bytes(x + 128 for x in shifted) if bits == 8 else b"".join(
                x.to_bytes(bits // 8, "little", signed=True) for x in shifted)
            result = self.run_wav(wave(chunk(b"fmt ", fmt(bits, 0xFFFE, valid=valid)), chunk(b"data", payload)))
            expected = np.array(ints, dtype="<f8") / scale
            self.assertEqual(result["decoded"]["sha256"], hashlib.sha256(expected.tobytes()).hexdigest())
            self.assertEqual(result["format"]["validBitsPerSample"], valid)
            self.assertEqual(result["metrics"]["integerRailFraction"], 2 / 3)
        self.reject(wave(chunk(b"fmt ", fmt(16, 0xFFFE, valid=12)), chunk(b"data", b"\x01\0")), "unused")

    def test_float_and_extensible_float_preserve_values_and_signed_zero(self):
        for bits, tag in ((32, 3), (64, 3), (32, 0xFFFE), (64, 0xFFFE)):
            values = np.array([-0., 1e-5, -1., 2.], dtype=f"<f{bits // 8}")
            result = self.run_wav(wave(chunk(b"fmt ", fmt(bits, tag, guid=audit.FLOAT_GUID)), chunk(b"data", values.tobytes())))
            expected = values.astype("<f8")
            self.assertEqual(result["decoded"]["sha256"], hashlib.sha256(expected.tobytes()).hexdigest())
            self.assertEqual(result["metrics"]["floatDigitalFullScaleFraction"], .5)
            self.assertEqual(result["metrics"]["absLe1eMinus4Fraction"], .5)
            self.assertIsNone(result["metrics"]["integerRailFraction"])
            self.assertFalse(result["normalizationApplied"])
        huge = np.array([np.finfo(np.float64).max, 0], dtype="<f8")
        result = self.run_wav(wave(chunk(b"fmt ", fmt(64, 3)), chunk(b"data", huge.tobytes())))
        self.assertTrue(np.isfinite(result["metrics"]["rms"]))

    def test_unknown_chunk_padding_and_data_before_fmt(self):
        result = self.run_wav(wave(chunk(b"JUNK", b"x", pad=b"\xff"), chunk(b"data", b"\x80"), chunk(b"fmt ", fmt(8))))
        self.assertEqual(result["metrics"]["frames"], 1)
        self.assertEqual(result["metrics"]["rms"], 0)
        self.assertEqual(result["format"]["chunks"][0]["paddingBytes"], 1)

    def test_structural_failures(self):
        good_fmt, good_data = chunk(b"fmt ", fmt()), chunk(b"data", b"\0\0")
        good = wave(good_fmt, good_data)
        cases = [b"", good[:-1], good + b"x", b"RIFX" + good[4:], wave(good_data),
                 wave(good_fmt), wave(good_fmt, good_fmt, good_data), wave(good_fmt, good_data, good_data),
                 wave(good_fmt, chunk(b"data", b"")), wave(good_fmt, chunk(b"data", b"x")),
                 wave(good_fmt, b"JUNK"), wave(good_fmt, b"JUNK" + struct.pack("<I", 10) + b"x"),
                 wave(chunk(b"fmt ", fmt(8)), b"data" + struct.pack("<I", 1) + b"\x80")]
        for raw in cases:
            with self.subTest(raw=raw[:24]):
                self.reject(raw)

    def test_format_validation_and_limits(self):
        bad = [fmt(tag=2), fmt(bits=8, tag=3), fmt(channels=0), fmt(channels=65),
               fmt(rate=0), fmt(rate=768001), fmt(bits=16, tag=0xFFFE, valid=0),
               fmt(bits=16, tag=0xFFFE, valid=17), fmt(bits=32, tag=0xFFFE, valid=24, guid=audit.FLOAT_GUID),
               fmt(tag=0xFFFE, guid=b"x" * 16), fmt() + b"x", fmt() + struct.pack("<H", 1)]
        broken_alignment = bytearray(fmt()); struct.pack_into("<H", broken_alignment, 12, 3)
        broken_rate = bytearray(fmt()); struct.pack_into("<I", broken_rate, 8, 1)
        broken_mask = bytearray(fmt(tag=0xFFFE)); struct.pack_into("<I", broken_mask, 20, 3)
        bad.extend((broken_alignment, broken_rate, broken_mask))
        for header in bad:
            with self.subTest(header=header):
                self.reject(wave(chunk(b"fmt ", header), chunk(b"data", b"\0" * 8)))
        boundary = self.run_wav(wave(chunk(b"fmt ", fmt(8, channels=64, rate=768000)), chunk(b"data", b"\x80" * 64)))
        self.assertEqual(boundary["metrics"]["channels"], 64)
        with self.path.open("wb") as handle:
            handle.truncate(audit.MAX_INPUT_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "byte limit"):
            audit.audit_wav(self.path)

    def test_nonfinite_rejected(self):
        for bits in (32, 64):
            for value in (float("nan"), float("inf"), -float("inf")):
                self.reject(wave(chunk(b"fmt ", fmt(bits, 3)), chunk(b"data", np.array([value], dtype=f"<f{bits // 8}").tobytes())), "nonfinite")


if __name__ == "__main__":
    unittest.main()
