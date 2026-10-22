"""Whole-recording speech evidence from official YAMNet (AudioSet class 0, "Speech").

Recording-level gate only: reports whether the fixed Speech score threshold passed. It says
nothing about which phonemes were produced or whether they were correct. Scores are independent
sigmoid outputs of a multi-label model, not calibrated probabilities. The root driver owns
source/weight/data hashes and environment pins; nothing here downloads, resamples, crops,
rescales, or falls back.
"""
import csv
import hashlib
import io
import os
import re
import sys
import wave
from pathlib import Path

import numpy as np

RULE = {
    "classIndex": 0,
    "classMid": "/m/09x0r",
    "className": "Speech",
    "threshold": 0.5,
    "reduction": "max",
    "sampleRate": 16000,
    "windowSamples": 15600,
    "hopSamples": 7680,
    "threads": 2,
    "device": "cpu",
    "weights": "official yamnet.h5, unmodified",
}
NUM_CLASSES = 521


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return int(value)


def geometry(n):
    """Return (numberOfWindows, paddedSampleCount), mirroring upstream features.pad_waveform."""
    n = _positive_int(n, "sample count")
    hops = -(-max(n - RULE["windowSamples"], 0) // RULE["hopSamples"])
    return 1 + hops, RULE["windowSamples"] + hops * RULE["hopSamples"]


def read_pcm(path, expected_sha256, expected_samples):
    """Return the recording as 1-D float32 in [-1, 1) after verifying its exact bytes and format."""
    expected_samples = _positive_int(expected_samples, "expected_samples")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected_sha256 must be 64 lowercase hex characters")
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError(f"sha256 mismatch for {path}")
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            fmt = (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype())
            frame_count = w.getnframes()
            frames = w.readframes(frame_count)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"{path} is not a readable PCM WAV: {exc}") from exc
    if fmt != (1, 2, RULE["sampleRate"], "NONE"):
        raise ValueError(f"{path} must be mono 16 kHz 16-bit PCM; got (channels, width, rate, comp)={fmt}")
    if frame_count != expected_samples or len(frames) != 2 * expected_samples:
        raise ValueError(f"{path}: header declares {frame_count} frames with {len(frames)} data bytes; "
                         f"expected {expected_samples} samples")
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / np.float32(32768.0)


def validate_scores(scores, n):
    """Summarize frame scores using the Speech column only.

    Rows need not sum to 1 (sigmoid multi-label). No other class, including "Child speech",
    can raise or veto the decision.
    """
    windows, padded = geometry(n)
    if not isinstance(scores, np.ndarray) or scores.dtype != np.float32:
        raise TypeError("scores must be a float32 numpy array")
    if scores.shape != (windows, NUM_CLASSES):
        raise ValueError(f"scores shape {scores.shape} != expected {(windows, NUM_CLASSES)}")
    if not np.all(np.isfinite(scores)) or scores.min() < 0 or scores.max() > 1:
        raise ValueError("scores must be finite and within [0, 1]")
    speech = float(scores[:, RULE["classIndex"]].max())
    return {"sampleCount": int(n), "paddedSampleCount": padded, "windows": windows,
            "speechScore": speech, "accepted": speech >= RULE["threshold"]}


def infer(model, waveform):
    """Call the frames model once on the unmodified waveform; upstream pads internally."""
    if not isinstance(waveform, np.ndarray) or waveform.dtype != np.float32:
        raise TypeError("waveform must be a float32 numpy array")
    if waveform.ndim != 1 or waveform.size == 0:
        raise ValueError("waveform must be 1-D and non-empty")
    if not np.all(np.isfinite(waveform)) or np.abs(waveform).max() > 1:
        raise ValueError("waveform must be finite and within [-1, 1]")
    outputs = model(waveform, training=False)
    if len(outputs) != 3:
        raise ValueError(f"expected (scores, embeddings, spectrogram), got {len(outputs)} outputs")
    scores = outputs[0]
    scores = scores.numpy() if hasattr(scores, "numpy") else np.asarray(scores)
    return scores, validate_scores(scores, waveform.size)


def _check_class_map(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if [r.get("index") for r in rows] != [str(i) for i in range(NUM_CLASSES)]:
        raise RuntimeError(f"{path} must list indices 0..{NUM_CLASSES - 1} in order")
    if (rows[0]["mid"], rows[0]["display_name"]) != (RULE["classMid"], RULE["className"]):
        raise RuntimeError(f"class 0 is {rows[0]}, expected {RULE['classMid']} {RULE['className']}")


def _check_module_origin(name, vendor, required):
    module = sys.modules.get(name)
    if module is None and not required:
        return
    origin = getattr(module, "__file__", None)
    if origin is None or Path(origin).resolve().parent != vendor:
        raise RuntimeError(f"module {name!r} from {origin} would shadow vendored YAMNet in {vendor}")


def load_model(vendor_dir):
    """Build the official YAMNet frames model on CPU from hash-verified vendored source and weights."""
    vendor = Path(vendor_dir).resolve()
    for name in ("params.py", "features.py", "yamnet.py", "yamnet.h5", "yamnet_class_map.csv"):
        if not (vendor / name).is_file():
            raise FileNotFoundError(vendor / name)
    _check_class_map(vendor / "yamnet_class_map.csv")
    for name in ("params", "features", "yamnet"):
        _check_module_origin(name, vendor, required=False)

    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import tensorflow as tf  # lazy: keeps reading/validation and tests TensorFlow-free
    tf.config.set_visible_devices([], "GPU")
    tf.config.threading.set_intra_op_parallelism_threads(RULE["threads"])
    tf.config.threading.set_inter_op_parallelism_threads(RULE["threads"])

    sys.path.insert(0, str(vendor))
    try:
        import params as params_mod
        import yamnet as yamnet_mod
    finally:
        sys.path.remove(str(vendor))
    for name in ("params", "features", "yamnet"):
        _check_module_origin(name, vendor, required=True)

    p = params_mod.Params()
    # int() mirrors upstream's tf.cast truncation in features.pad_waveform.
    window = int((p.patch_window_seconds + p.stft_window_seconds - p.stft_hop_seconds) * p.sample_rate)
    hop = int(p.patch_hop_seconds * p.sample_rate)
    got = (p.sample_rate, window, hop, p.num_classes, p.classifier_activation)
    if got != (RULE["sampleRate"], RULE["windowSamples"], RULE["hopSamples"], NUM_CLASSES, "sigmoid"):
        raise RuntimeError(f"upstream Params defaults differ from RULE: {got}")
    if tf.config.list_logical_devices("GPU"):
        raise RuntimeError("GPU still visible; CPU-only inference required")
    model = yamnet_mod.yamnet_frames_model(p)
    model.load_weights(str(vendor / "yamnet.h5"))
    return model
