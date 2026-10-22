import unittest

import torch

from target_pool import conv_geometry, crop_audio_interval, pool_interval_frames


KERNELS = [10, 3, 3, 3, 3, 2, 2]
STRIDES = [5, 2, 2, 2, 2, 2, 2]


class TargetPoolTests(unittest.TestCase):
    def test_wav2vec_family_geometry_and_half_open_interval(self):
        receptive, hop, count = conv_geometry(KERNELS, STRIDES, 16000)
        self.assertEqual((receptive, hop, count), (400, 320, 49))
        frames = torch.arange(count, dtype=torch.float32).reshape(-1, 1)
        pooled, selected = pool_interval_frames(
            frames, sample_count=16000, sample_rate=16000,
            start_seconds=0.1, end_seconds=0.2,
            conv_kernels=KERNELS, conv_strides=STRIDES,
        )
        self.assertEqual(selected, (5, 10))
        self.assertEqual(pooled.tolist(), [7.0])

    def test_rejects_empty_interval_on_frame_grid_and_bad_provenance_shape(self):
        frames = torch.ones(49, 3)
        options = dict(sample_count=16000, sample_rate=16000,
                       conv_kernels=KERNELS, conv_strides=STRIDES)
        with self.assertRaisesRegex(ValueError, "No encoder frame"):
            pool_interval_frames(frames, start_seconds=0.100, end_seconds=0.110, **options)
        with self.assertRaisesRegex(ValueError, "does not match"):
            pool_interval_frames(frames[:48], start_seconds=0.1, end_seconds=0.2, **options)
        with self.assertRaisesRegex(ValueError, "floating dtype"):
            pool_interval_frames(frames.long(), start_seconds=0.1, end_seconds=0.2, **options)
        with self.assertRaisesRegex(ValueError, "outside audio"):
            pool_interval_frames(frames, start_seconds=0.9, end_seconds=1.1, **options)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            pool_interval_frames(frames.fill_(float("nan")), start_seconds=0.1,
                                 end_seconds=0.2, **options)

    def test_crop_excludes_off_target_audio_and_records_sample_range(self):
        samples = torch.full((16000,), 10.0)
        samples[1600:3200] = 1.0
        cropped, bounds = crop_audio_interval(
            samples, sample_rate=16000, start_seconds=0.1, end_seconds=0.2,
            conv_kernels=KERNELS, conv_strides=STRIDES,
        )
        self.assertEqual(bounds, (1600, 3200))
        self.assertEqual(tuple(cropped.shape), (1600,))
        self.assertTrue(torch.equal(cropped, torch.ones(1600)))
        cropped[0] = 2.0
        self.assertEqual(samples[1600].item(), 1.0)
        _, fractional_bounds = crop_audio_interval(
            samples, sample_rate=16000, start_seconds=0.10003,
            end_seconds=0.20003, conv_kernels=KERNELS, conv_strides=STRIDES,
        )
        self.assertEqual(fractional_bounds, (1600, 3201))

    def test_crop_rejects_invalid_or_too_short_audio(self):
        options = dict(sample_rate=16000, conv_kernels=KERNELS, conv_strides=STRIDES)
        samples = torch.zeros(16000)
        with self.assertRaisesRegex(ValueError, "shorter than"):
            crop_audio_interval(samples, start_seconds=0.1, end_seconds=0.11, **options)
        with self.assertRaisesRegex(ValueError, "outside audio"):
            crop_audio_interval(samples, start_seconds=0.9, end_seconds=1.1, **options)
        with self.assertRaisesRegex(ValueError, "finite floating"):
            crop_audio_interval(samples.long(), start_seconds=0.1, end_seconds=0.2, **options)
        with self.assertRaisesRegex(ValueError, "16 kHz"):
            crop_audio_interval(samples, sample_rate=8000, start_seconds=0.1,
                                end_seconds=0.2, conv_kernels=KERNELS, conv_strides=STRIDES)


if __name__ == "__main__":
    unittest.main()
