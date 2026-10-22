"""Bounded, deterministic RIFF/WAVE decoding and digital-signal diagnostics.

PCM is decoded using its declared digital scale, not data-dependent normalization.
No measurement here establishes speech quality or verified speaker identity.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import stat
import struct

import numpy as np

MAX_INPUT_BYTES = 134217728
MAX_CHANNELS = 64
MAX_SAMPLE_RATE = 768000
PCM_GUID = bytes.fromhex("0100000000001000800000aa00389b71")
FLOAT_GUID = bytes.fromhex("0300000000001000800000aa00389b71")
POLICY = {
    "schemaVersion": 1,
    "container": "little-endian RIFF/WAVE",
    "encodings": {"PCM": [8, 16, 24, 32], "IEEE-float": [32, 64]},
    "extensible": {"subFormatGuidHex": [PCM_GUID.hex(), FLOAT_GUID.hex()],
                   "pcmValidBits": "1 through container width; left aligned; unused low bits zero",
                   "floatValidBits": "equal container width",
                   "channelMask": "zero or population count equal to channels"},
    "maxInputBytes": MAX_INPUT_BYTES, "maxChannels": MAX_CHANNELS,
    "maxSampleRate": MAX_SAMPLE_RATE,
    "trailingPolicy": "RIFF declared size plus eight equals actual file length",
    "chunkPolicy": "unique fmt and data; bounded chunks; odd-byte padding required with any pad value; unknown chunks and data before fmt permitted",
    "framePolicy": "positive whole frames; exact block alignment and byte rate",
    "samplePolicy": "reject nonfinite floats; preserve finite samples outside digital fullscale",
    "decodedHash": "SHA256 of little-endian float64 interleaved C-order samples",
    "pcmScale": "signed valid-bit integer divided by 2**(validBits-1); unsigned 8-bit centered first",
    "metrics": ["frames", "samples", "channels", "sampleRate", "durationSeconds",
                "peakAbs", "rms", "exactZeroFraction", "absLe1eMinus4Fraction",
                "integerRailFraction", "floatDigitalFullScaleFraction"],
    "nearZeroThreshold": 0.0001,
    "integerRailDefinition": "valid-bit minimum or maximum signed integer",
    "floatDigitalFullScaleDefinition": "absolute amplitude at least one",
    "diagnosticSemantics": "Digital fullscale and level diagnostics; not speech or quality truth.",
    "normalizationApplied": False, "resamplingApplied": False,
    "trimmingApplied": False, "outputDependentExclusion": False,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def audit_wav(path: str | os.PathLike) -> dict:
    """Return JSON-safe format, global metrics, and SHA256 of C-order <f8 samples.

    Fail closed on malformed or unsupported files. The file must be regular,
    bounded, and contain exactly one fmt and data chunk. Unknown chunks and
    data preceding fmt are allowed; required odd-byte padding is consumed.
    """
    path = Path(path)
    with path.open("rb") as handle:
        info = os.fstat(handle.fileno())
        _require(stat.S_ISREG(info.st_mode), "input must be a regular file")
        _require(info.st_size <= MAX_INPUT_BYTES, "input exceeds fixed byte limit")
        raw = handle.read(MAX_INPUT_BYTES + 1)
    _require(len(raw) <= MAX_INPUT_BYTES, "input exceeds fixed byte limit")
    _require(len(raw) >= 12, "truncated RIFF header")
    _require(raw[:4] == b"RIFF" and raw[8:12] == b"WAVE", "expected little-endian RIFF/WAVE")
    _require(struct.unpack_from("<I", raw, 4)[0] + 8 == len(raw), "RIFF declared size must equal file length")
    chunks, found = [], {}
    offset = 12
    while offset < len(raw):
        _require(offset + 8 <= len(raw), "truncated chunk header")
        name, size = struct.unpack_from("<4sI", raw, offset)
        start, end = offset + 8, offset + 8 + size
        _require(end + (size & 1) <= len(raw), "truncated chunk or padding")
        chunks.append({"idHex": name.hex(), "headerOffset": offset, "sizeBytes": size,
                       "paddingBytes": size & 1})
        if name in (b"fmt ", b"data"):
            _require(name not in found, "duplicate fmt or data chunk")
            found[name] = (start, end)
        offset = end + (size & 1)
    _require(b"fmt " in found and b"data" in found, "exactly one fmt and data chunk required")
    fmt_start, fmt_end = found[b"fmt "]
    fmt = raw[fmt_start:fmt_end]
    _require(len(fmt) >= 16, "truncated fmt chunk")
    tag, channels, rate, byte_rate, alignment, bits = struct.unpack_from("<HHIIHH", fmt)
    _require(1 <= channels <= MAX_CHANNELS, "channels outside fixed limits")
    _require(1 <= rate <= MAX_SAMPLE_RATE, "sample rate outside fixed limits")
    valid_bits, mask, guid = bits, None, None
    encoding_tag = tag
    if len(fmt) != 16:
        _require(len(fmt) >= 18, "truncated fmt extension")
        extension = struct.unpack_from("<H", fmt, 16)[0]
        _require(len(fmt) == 18 + extension, "fmt extension length mismatch")
    if tag == 0xFFFE:
        _require(len(fmt) >= 40, "truncated extensible fmt")
        valid_bits, mask = struct.unpack_from("<HI", fmt, 18)
        guid = fmt[24:40]
        _require(guid in (PCM_GUID, FLOAT_GUID), "unsupported extensible subtype GUID")
        encoding_tag = 1 if guid == PCM_GUID else 3
        _require(mask == 0 or mask.bit_count() == channels, "channel mask count mismatch")
    _require(encoding_tag in (1, 3), "unsupported WAV encoding")
    if encoding_tag == 1:
        _require(bits in (8, 16, 24, 32), "unsupported PCM container width")
        _require(1 <= valid_bits <= bits, "invalid PCM valid bits")
    else:
        _require(bits in (32, 64) and valid_bits == bits, "unsupported float width or valid bits")
    _require(alignment == channels * (bits // 8), "block alignment mismatch")
    _require(byte_rate == rate * alignment, "byte rate mismatch")
    data_start, data_end = found[b"data"]
    size = data_end - data_start
    _require(size > 0 and size % alignment == 0, "data must contain positive whole frames")
    payload = memoryview(raw)[data_start:data_end]
    rail_fraction = fullscale_fraction = None
    if encoding_tag == 1:
        if bits == 8:
            integers = np.frombuffer(payload, dtype=np.uint8).astype(np.int64) - 128
        elif bits == 24:
            octets = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
            integers = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
            integers = (integers ^ (1 << 23)) - (1 << 23)
        else:
            integers = np.frombuffer(payload, dtype="<i2" if bits == 16 else "<i4").astype(np.int64)
        padding_bits = bits - valid_bits
        _require(not padding_bits or not np.any(integers & ((1 << padding_bits) - 1)),
                 "nonzero unused PCM low bits")
        integers = integers >> padding_bits
        scale = 1 << (valid_bits - 1)
        rail_fraction = float(np.count_nonzero((integers == -scale) | (integers == scale - 1)) / integers.size)
        decoded = integers.astype("<f8") / scale
    else:
        decoded = np.frombuffer(payload, dtype="<f4" if bits == 32 else "<f8").astype("<f8")
        _require(bool(np.all(np.isfinite(decoded))), "nonfinite float samples")
        fullscale_fraction = float(np.count_nonzero(np.abs(decoded) >= 1) / decoded.size)
    frames = size // alignment
    decoded = np.ascontiguousarray(decoded.reshape(frames, channels), dtype="<f8")
    absolute = np.abs(decoded)
    peak = float(np.max(absolute))
    rms = 0.0 if peak == 0 else peak * math.sqrt(float(np.mean((decoded / peak) ** 2)))
    return {
        "schemaVersion": 1,
        "input": {"sizeBytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
        "limits": {"maxInputBytes": MAX_INPUT_BYTES, "maxChannels": MAX_CHANNELS,
                   "maxSampleRate": MAX_SAMPLE_RATE},
        "format": {"container": "RIFF/WAVE", "formatTag": tag,
                   "encoding": "PCM" if encoding_tag == 1 else "IEEE-float",
                   "extensible": tag == 0xFFFE, "bitsPerSample": bits,
                   "validBitsPerSample": valid_bits, "channelMask": mask,
                   "subFormatGuidHex": None if guid is None else guid.hex(),
                   "blockAlign": alignment, "byteRate": byte_rate,
                   "fmtBytes": len(fmt), "dataOffset": data_start, "dataBytes": size,
                   "pcmScale": None if encoding_tag == 3 else 1 << (valid_bits - 1),
                   "chunks": chunks},
        "decoded": {"dtype": "<f8", "order": "C", "shape": [frames, channels],
                    "sha256": hashlib.sha256(decoded.tobytes(order="C")).hexdigest()},
        "metrics": {"frames": frames, "samples": int(decoded.size), "channels": channels,
                    "sampleRate": rate, "durationSeconds": frames / rate,
                    "peakAbs": peak, "rms": rms,
                    "exactZeroFraction": float(np.count_nonzero(decoded == 0) / decoded.size),
                    "absLe1eMinus4Fraction": float(np.count_nonzero(absolute <= 1e-4) / decoded.size),
                    "integerRailFraction": rail_fraction,
                    "floatDigitalFullScaleFraction": fullscale_fraction},
        "diagnosticSemantics": POLICY["diagnosticSemantics"],
        "normalizationApplied": False, "resamplingApplied": False, "trimmingApplied": False,
    }
