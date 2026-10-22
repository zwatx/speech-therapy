"""Synthetic-only audio preparation and pooling checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from nisqa_ingest.test_waveform_audit import chunk, fmt, wave
from nisqa_ingest.waveform_audit import FLOAT_GUID, audit_wav
from nisqa_quality import audio_features as audio


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.wav'

    def write(self, header, payload):
        self.path.write_bytes(wave(chunk(b'fmt ', header), chunk(b'data', payload)))
        return self.path

    def test_pcm_widths_valid_bits_independent_values_and_audit_hash(self):
        for bits, valid in ((8, 8), (16, 16), (24, 24), (32, 32),
                            (8, 4), (16, 12), (24, 20), (32, 24)):
            scale = 1 << (valid - 1)
            values = [-scale, 0, scale - 1]
            encoded = [x << (bits - valid) for x in values]
            payload = bytes(x + 128 for x in encoded) if bits == 8 else b''.join(
                x.to_bytes(bits // 8, 'little', signed=True) for x in encoded)
            header = fmt(bits, tag=1 if bits == valid else 0xFFFE, valid=valid)
            decoded, audit = audio.decoded_audio(self.write(header, payload))
            expected = np.array(values, dtype='<f8').reshape(3, 1) / scale
            with self.subTest(bits=bits, valid=valid):
                np.testing.assert_array_equal(decoded, expected)
                expected_sha = hashlib.sha256(expected.tobytes()).hexdigest()
                self.assertEqual(audit['decoded']['sha256'], expected_sha)
                self.assertEqual(decoded.dtype, np.dtype('<f8'))

    def test_plain_and_extensible_float_preserve_outside_fullscale_signed_zero(self):
        for bits in (32, 64):
            for tag in (3, 0xFFFE):
                original = np.array([[-0., .25], [-2., 1.]], dtype=f'<f{bits // 8}')
                decoded, audit = audio.decoded_audio(self.write(fmt(bits, tag, channels=2, guid=FLOAT_GUID), original.tobytes()))
                expected = original.astype('<f8')
                self.assertEqual(hashlib.sha256(decoded.tobytes()).hexdigest(), hashlib.sha256(expected.tobytes()).hexdigest())
                scalars = audio.raw_descriptors(audit)
                np.testing.assert_allclose(scalars, [np.sqrt(5.0625 / 4), 2., .25, .25, .5, 2 / 8000], rtol=1e-15)

    def test_six_scalar_order_and_three_channel_cancellation_preserve_raw_rms(self):
        original = np.array([[16384, -16384, 0], [0, 0, 0]], dtype='<i2')
        result = audio.prepare_audio(self.write(fmt(channels=3, rate=16000), original.tobytes()))
        np.testing.assert_array_equal(result['samples'], np.zeros(2, dtype='<f4'))
        np.testing.assert_allclose(result['scalars'], [np.sqrt(.5 / 6), .5, 4 / 6, 4 / 6, 0, 2 / 16000])
        self.assertEqual(tuple(result['metadata']['scalarOrder']), audio.SCALAR_NAMES)
        self.assertGreater(result['scalars'][0], 0)
        json.dumps(result['metadata'], allow_nan=False)

    def test_raw_and_decoded_hash_mismatch_rejected(self):
        path = self.write(fmt(), b'\0\0')
        audit = audit_wav(path)
        with patch.object(audio, 'audit_wav', return_value={**audit, 'decoded': {**audit['decoded'], 'sha256': '0' * 64}}):
            with self.assertRaisesRegex(ValueError, 'Decoded waveform hash'):
                audio.decoded_audio(path)
        modified = bytearray(path.read_bytes()); modified[-1] ^= 1; path.write_bytes(modified)
        with patch.object(audio, 'audit_wav', return_value=audit):
            with self.assertRaisesRegex(ValueError, 'changed after audit'):
                audio.decoded_audio(path)

    def test_resample_noop_copy_exact_cast_and_hashes(self):
        original = np.array([-2., -0., 0.000123456789, 2.], dtype='<f8')
        result, metadata = audio.resample_mono(original, 16000)
        np.testing.assert_array_equal(result, original.astype('<f4'))
        self.assertFalse(np.shares_memory(original, result))
        self.assertFalse(metadata['interpolationApplied'])
        self.assertEqual(metadata['sourceMonoFloat64Sha256'], hashlib.sha256(original.tobytes()).hexdigest())
        self.assertEqual(metadata['resampledFloat64Sha256'], metadata['sourceMonoFloat64Sha256'])
        self.assertEqual(metadata['modelInputFloat32Sha256'], hashlib.sha256(original.astype('<f4').tobytes()).hexdigest())
        self.assertEqual(metadata['scipyVersion'], '1.17.1')
        self.assertEqual(result[0], -2.)

    def test_all_declared_rates_ceil_length_and_reduced_ratio(self):
        for rate in audio.ACCEPTED_RATES:
            result, metadata = audio.resample_mono(np.zeros(101, dtype='<f8'), rate)
            self.assertEqual(result.size, (101 * 16000 + rate - 1) // rate)
            self.assertEqual(metadata['up'] * rate, metadata['down'] * 16000)
            self.assertEqual(result.dtype, np.dtype('<f4'))
            self.assertTrue(result.flags.c_contiguous)

    def test_48k_impulse_dc_passband_and_antialias_stopband(self):
        rate = 48000
        dc, _ = audio.resample_mono(np.ones(rate, dtype='<f8'), rate)
        np.testing.assert_allclose(dc[100:-100], 1., atol=.001)
        impulse = np.zeros(2883, dtype='<f8'); impulse[1440] = 1.
        response, _ = audio.resample_mono(impulse, rate)
        self.assertEqual(np.argmax(np.abs(response)), 480)
        self.assertAlmostEqual(float(response.sum()), 1 / 3, delta=.001)
        np.testing.assert_allclose(response[470:480], response[481:491][::-1], atol=1e-9)
        time = np.arange(rate, dtype=np.float64) / rate
        passband, _ = audio.resample_mono(np.sin(2 * np.pi * 1000 * time), rate)
        expected = np.sin(2 * np.pi * 1000 * np.arange(16000, dtype=np.float64) / 16000)
        rms_error = np.sqrt(np.mean((passband[100:-100] - expected[100:-100]) ** 2))
        self.assertLess(rms_error / np.sqrt(np.mean(expected[100:-100] ** 2)), .01)
        stopband, _ = audio.resample_mono(np.sin(2 * np.pi * 12000 * time), rate)
        ratio = np.sqrt(np.mean(stopband[100:-100] ** 2)) / np.sqrt(.5)
        self.assertLess(ratio, .01)
        # 12kHz would alias to 4kHz without antialiasing, so this is not a
        # comparison to an impossible 12kHz waveform at the target rate.

    def test_pool_hand_values_population_std_and_one_frame(self):
        hidden = np.tile(np.array([0., 2., 4.], dtype=np.float32)[:, None], (1, 768))
        pooled = audio.pool_hidden(hidden)
        self.assertEqual(pooled.shape, (1536,))
        self.assertEqual(pooled.dtype, np.dtype('<f4'))
        np.testing.assert_array_equal(pooled[:768], np.full(768, 2., dtype=np.float32))
        np.testing.assert_array_equal(pooled[768:], np.full(768, np.sqrt(8 / 3), dtype=np.float32))
        singleton = np.arange(768, dtype=np.float32)[None, :]
        np.testing.assert_array_equal(audio.pool_hidden(singleton), np.concatenate((singleton[0], np.zeros(768, dtype=np.float32))))

    def test_finiteness_shapes_rates_and_runtime_guards(self):
        for invalid in (np.zeros((0, 768), dtype=np.float32), np.zeros((1, 767), dtype=np.float32),
                        np.zeros((1, 768), dtype=np.float64), np.full((1, 768), np.nan, dtype=np.float32)):
            with self.assertRaises(ValueError):
                audio.pool_hidden(invalid)
        for invalid in (np.zeros(2), np.zeros((0, 1)), np.zeros((1, 65)), np.ones((1, 1), dtype=np.float32), np.full((1, 1), np.inf)):
            with self.assertRaises(ValueError):
                audio.downmix(invalid)
        for rate in (12000, 16000., True, 0):
            with self.assertRaisesRegex(ValueError, 'sample rate'):
                audio.resample_mono(np.zeros(10), rate)
        for invalid in (np.zeros((1, 1)), np.zeros(0), np.ones(1, dtype=np.float32), np.array([np.nan])):
            with self.assertRaises(ValueError):
                audio.resample_mono(invalid, 16000)
        with self.assertRaisesRegex(ValueError, 'conversion overflow'):
            audio.resample_mono(np.array([np.finfo(np.float64).max]), 16000)
        with patch.object(audio.scipy, '__version__', 'other'):
            with self.assertRaisesRegex(ValueError, 'SciPy version'):
                audio.resample_mono(np.zeros(1), 16000)

    def test_policy_matches_inherited_encoder_identity_and_is_json_safe(self):
        from encoders import WAVLM_FILES, WAVLM_MODEL_ID, WAVLM_REVISION
        json.dumps(audio.POLICY, allow_nan=False)
        self.assertEqual(audio.POLICY['encoder']['modelId'], WAVLM_MODEL_ID)
        self.assertEqual(audio.POLICY['encoder']['revision'], WAVLM_REVISION)
        self.assertEqual(audio.POLICY['encoder']['artifactSha256'], WAVLM_FILES)
        self.assertFalse(audio.POLICY['processor']['do_normalize'])
        self.assertTrue(audio.POLICY['processor']['return_attention_mask'])


if __name__ == '__main__':
    unittest.main()
