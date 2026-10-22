"""Private, unlabeled full-clip frozen frames for the 40 author-train /R/ pilot WAVs.

These contextual states are extraction artifacts, not reviewed target intervals,
target-only acoustics, labels, or permission to train a segment head.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

import numpy as np
import torch

from encoders import Wav2VecEncoder, WavLMEncoder
from speechocean_r_annotation_pack import source_rows
from speechocean_r_annotation_sample import (AUTHORITY, OUTPUT as SAMPLE, RECIPE,
                                             require_real_generated_path, sha256_file)
from speechocean_r_probe import CACHE as MODEL_CACHE, read_rating_pcm
from target_pool import conv_geometry


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "outputs/speechocean-r-frozen-frames-v1"
ENCODERS = {"wav2vec2-base": Wav2VecEncoder, "wavlm-base-plus": WavLMEncoder}
KERNELS = [10, 3, 3, 3, 3, 2, 2]
STRIDES = [5, 2, 2, 2, 2, 2, 2]
FILES = {"frames.npy", "index.json"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_private_file(path: Path) -> None:
    require(path.is_file() and not path.is_symlink() and
            stat.S_IMODE(path.stat().st_mode) == 0o600,
            f"Cache file missing, redirected, or not owner-only: {path.name}")


def require_private_directory(path: Path) -> None:
    require(path.is_dir() and not path.is_symlink() and
            stat.S_IMODE(path.stat().st_mode) == 0o700,
            f"Cache directory missing, redirected, or not owner-only: {path.name}")


def prepared_inputs(rows: list[dict]) -> tuple[list[torch.Tensor], list[dict]]:
    """Load only verified train WAVs; retain no source metadata in the index."""
    require(len(rows) == 40 and len({row["reviewerId"] for row in rows}) == 40,
            "Expected exactly forty distinct opaque pilot clips")
    samples = []
    index_rows = []
    offset = 0
    for row in rows:
        pcm = read_rating_pcm(Path(row["wavPath"]), row["wavSha256"])
        sample_count = len(pcm)
        receptive, hop, frame_count = conv_geometry(KERNELS, STRIDES, sample_count)
        require((receptive, hop) == (400, 320), "Unexpected frozen encoder frame geometry")
        index_rows.append({"clipId": row["reviewerId"], "wavSha256": row["wavSha256"],
                           "sampleCount": sample_count, "frameOffset": offset,
                           "frameCount": frame_count})
        samples.append(pcm)
        offset += frame_count
    return samples, index_rows


def expected_index(kind: str, rows: list[dict]) -> dict:
    require(kind in ENCODERS, "Unsupported frozen encoder")
    require(len(rows) == 40 and len({row["clipId"] for row in rows}) == 40,
            "Expected forty unique opaque clip IDs")
    offset = 0
    for row in rows:
        require(set(row) == {"clipId", "wavSha256", "sampleCount", "frameOffset", "frameCount"}
                and type(row["clipId"]) is str and len(row["clipId"]) == 16
                and type(row["wavSha256"]) is str and len(row["wavSha256"]) == 64
                and type(row["sampleCount"]) is int and type(row["frameCount"]) is int
                and type(row["frameOffset"]) is int and row["frameOffset"] == offset
                and conv_geometry(KERNELS, STRIDES, row["sampleCount"])[2] == row["frameCount"],
                "Invalid frame cache row geometry or ordering")
        offset += row["frameCount"]
    return {"schemaVersion": 1, "purpose": "private unlabeled author-train full-clip frozen frames",
            "authorPartition": "train", "sampleRecipeSha256": sha256_file(RECIPE),
            "sampleManifestSha256": sha256_file(SAMPLE / "internal-manifest.json"),
            "encoder": ENCODERS[kind].identity,
            "preprocessingCodeSha256": {name: sha256_file(HERE / name) for name in
                                        ("encoders.py", "speechocean_r_probe.py", "target_pool.py",
                                         "speechocean_r_frame_cache.py")},
            "sampleRate": 16000, "dtype": "float32", "width": 768,
            "convKernels": KERNELS, "convStrides": STRIDES,
            "receptiveFieldSamples": 400, "frameHopSamples": 320,
            "frameCount": offset, "rows": rows,
            "contextualStatesCanAttendOutsideFutureInterval": True,
            "annotationComplete": False, "trainingEligible": False, **AUTHORITY}


def validate_existing(directory: Path, expected: dict) -> dict:
    require_private_directory(directory)
    require({path.name for path in directory.iterdir()} == FILES,
            "Partial or unexpected frozen-frame cache contents")
    frame_path, index_path = directory / "frames.npy", directory / "index.json"
    require_private_file(frame_path)
    require_private_file(index_path)
    index = json.loads(index_path.read_text())
    require(type(index) is dict and set(index) == set(expected) | {"frameArraySha256"},
            "Frozen-frame index schema changed")
    digest = index.pop("frameArraySha256")
    require(index == expected, "Frozen-frame cache provenance changed")
    require(type(digest) is str and digest == sha256_file(frame_path),
            "Frozen-frame array SHA-256 mismatch")
    frames = np.load(frame_path, mmap_mode="r", allow_pickle=False)
    require(frames.shape == (expected["frameCount"], 768) and
            frames.dtype == np.dtype("float32") and np.isfinite(frames).all(),
            "Frozen-frame array shape, dtype, or values changed")
    return {"encoder": expected["encoder"]["kind"], "clips": 40,
            "frames": expected["frameCount"], "frameArraySha256": digest,
            "reused": True, "trainingEligible": False}


def write_private_json(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write((json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        target.flush()
        os.fsync(target.fileno())


def publish_frames(directory: Path, expected: dict, samples: list[torch.Tensor],
                   encoder: object) -> dict:
    """Publish a complete cache directory in one rename or leave none behind."""
    require(not directory.exists() and not directory.is_symlink(),
            "Frozen-frame destination already exists")
    config = encoder.model.config
    require(list(config.conv_kernel) == KERNELS and list(config.conv_stride) == STRIDES,
            "Loaded pinned encoder convolution differs from frame geometry")
    require(encoder.identity == expected["encoder"], "Loaded encoder identity changed")
    temporary = Path(tempfile.mkdtemp(prefix=".frozen-frames-", dir=directory.parent))
    try:
        temporary.chmod(0o700)
        frame_path = temporary / "frames.npy"
        frames = np.empty((expected["frameCount"], 768), dtype=np.float32)
        for row, pcm in zip(expected["rows"], samples, strict=True):
            produced = encoder(pcm)
            require(produced.ndim == 2 and tuple(produced.shape) == (row["frameCount"], 768)
                    and produced.is_floating_point() and torch.isfinite(produced).all(),
                    "Frozen encoder frame shape or values changed")
            start = row["frameOffset"]
            frames[start:start + row["frameCount"]] = produced.numpy().astype(np.float32)
        descriptor = os.open(frame_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            np.save(target, frames, allow_pickle=False)
            target.flush()
            os.fsync(target.fileno())
        digest = sha256_file(frame_path)
        write_private_json(temporary / "index.json", {**expected, "frameArraySha256": digest})
        # Validate our own published bytes before exposing the directory.
        validate_existing(temporary, expected)
        os.rename(temporary, directory)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"encoder": expected["encoder"]["kind"], "clips": 40,
            "frames": expected["frameCount"], "frameArraySha256": digest,
            "reused": False, "trainingEligible": False}


def run(kind: str) -> dict:
    require(kind in ENCODERS, "Unsupported frozen encoder")
    require_real_generated_path(OUTPUT, HERE)
    rows, _key = source_rows()  # Rebuilds the exact train sample and checks WAVs against the archive.
    samples, index_rows = prepared_inputs(rows)
    expected = expected_index(kind, index_rows)
    if OUTPUT.exists():
        require_private_directory(OUTPUT)
        require({path.name for path in OUTPUT.iterdir()} <= set(ENCODERS),
                "Unexpected or partial frozen-frame output")
    else:
        OUTPUT.mkdir(mode=0o700)
    directory = OUTPUT / kind
    if directory.exists() or directory.is_symlink():
        return validate_existing(directory, expected)
    encoder = ENCODERS[kind](MODEL_CACHE, allow_download=False)
    return publish_frames(directory, expected, samples, encoder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", choices=tuple(ENCODERS) + ("both",), default="both")
    arguments = parser.parse_args()
    kinds = ENCODERS if arguments.encoder == "both" else (arguments.encoder,)
    print(json.dumps([run(kind) for kind in kinds], indent=2))
