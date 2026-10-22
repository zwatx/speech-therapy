"""Research-only pooling of frozen encoder positions inside a supplied interval.

This does not establish that the interval contains /R/ or that its label is
approved. Transformer hidden states can attend to the whole utterance, so
position pooling does not isolate target acoustics. A caller must validate
reviewer provenance and use before fitting.
"""

from __future__ import annotations

import math

import torch


def conv_geometry(kernels: list[int], strides: list[int], sample_count: int) -> tuple[int, int, int]:
    """Return receptive-field samples, frame hop samples, and output frames."""
    if not kernels or len(kernels) != len(strides) or sample_count <= 0:
        raise ValueError("Invalid convolution geometry")
    receptive, hop, count = 1, 1, sample_count
    for kernel, stride in zip(kernels, strides):
        if type(kernel) is not int or type(stride) is not int or kernel <= 0 or stride <= 0:
            raise ValueError("Invalid convolution geometry")
        count = (count - kernel) // stride + 1
        if count <= 0:
            raise ValueError("Audio is shorter than the encoder receptive field")
        receptive += (kernel - 1) * hop
        hop *= stride
    return receptive, hop, count


def pool_interval_frames(
    frames: torch.Tensor,
    *,
    sample_count: int,
    sample_rate: int,
    start_seconds: float,
    end_seconds: float,
    conv_kernels: list[int],
    conv_strides: list[int],
) -> tuple[torch.Tensor, tuple[int, int]]:
    """Mean-pool frames whose convolutional centers fall in [start, end).

    Reject intervals with no frame center rather than silently substitute
    off-target frames. The returned half-open frame range makes the
    selected positions inspectable in a later, locked research artifact. For
    contextual transformer states, selected positions can still encode audio
    outside the interval.
    """
    if type(sample_rate) is not int or sample_rate <= 0 or type(sample_count) is not int:
        raise ValueError("Invalid audio geometry")
    if (type(start_seconds) not in (float, int) or type(end_seconds) not in (float, int)
            or not math.isfinite(start_seconds) or not math.isfinite(end_seconds)
            or not 0 <= start_seconds < end_seconds <= sample_count / sample_rate):
        raise ValueError("Interval outside audio duration")
    receptive, hop, expected = conv_geometry(conv_kernels, conv_strides, sample_count)
    if frames.ndim != 2 or frames.shape[0] != expected or frames.shape[1] <= 0:
        raise ValueError("Frame tensor does not match audio and encoder geometry")
    if not frames.is_floating_point():
        raise ValueError("Frame tensor must have a floating dtype")
    if not torch.isfinite(frames).all():
        raise ValueError("Frame tensor contains nonfinite values")
    centers = (torch.arange(expected, dtype=torch.float64) * hop + (receptive - 1) / 2) / sample_rate
    selected = torch.nonzero((centers >= start_seconds) & (centers < end_seconds)).flatten()
    if selected.numel() == 0:
        raise ValueError("No encoder frame center in the supplied interval")
    first, last = int(selected[0]), int(selected[-1]) + 1
    return frames[first:last].mean(dim=0), (first, last)


def crop_audio_interval(
    samples: torch.Tensor,
    *,
    sample_rate: int,
    start_seconds: float,
    end_seconds: float,
    conv_kernels: list[int],
    conv_strides: list[int],
) -> tuple[torch.Tensor, tuple[int, int]]:
    """Return the marked mono audio without an added context window.

    Floor/ceil sample boundaries retain the entire supplied interval; the
    returned range records the at-most-one-sample expansion on either edge.
    This is an alternative input for a frozen encoder, not a validated label.
    """
    if samples.ndim != 1 or not samples.is_floating_point() or not torch.isfinite(samples).all():
        raise ValueError("Expected finite floating mono samples")
    if type(sample_rate) is not int or sample_rate != 16000:
        raise ValueError("Frozen speech encoders require 16 kHz input")
    if (type(start_seconds) not in (float, int) or type(end_seconds) not in (float, int)
            or not math.isfinite(start_seconds) or not math.isfinite(end_seconds)
            or not 0 <= start_seconds < end_seconds <= len(samples) / sample_rate):
        raise ValueError("Interval outside audio duration")
    start = math.floor(start_seconds * sample_rate)
    end = math.ceil(end_seconds * sample_rate)
    conv_geometry(conv_kernels, conv_strides, end - start)
    return samples[start:end].clone(), (start, end)
