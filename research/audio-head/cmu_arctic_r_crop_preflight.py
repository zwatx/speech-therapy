"""Train-only CMU Arctic automatic /r/ crop and frozen-encoder preflight.

This checks extraction geometry on public adult read speech. Automatic phone
alignments are not verified productions or pronunciation-error labels.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import statistics
import tempfile

import torch

from data import digest, load_manifest, read_json
from encoders import Wav2VecEncoder
from labels import parse_timed_alignment
from speechocean_r_probe import CACHE as MODEL_CACHE
from target_pool import conv_geometry, crop_audio_interval


HERE = Path(__file__).resolve().parent
RECIPE = HERE / "experiments/cmu-arctic-r-crop-preflight-v1.json"
OUTPUT = HERE / "outputs/cmu-arctic-r-crop-preflight-v1"
KERNELS = [10, 3, 3, 3, 3, 2, 2]
STRIDES = [5, 2, 2, 2, 2, 2, 2]
SOURCE_FILES = {
    "manifest": ("outputs/cmu-arctic-four-speaker-v1/manifest.json",
                 "0d0c747d420144c3c03e3b49fe268bf12319763961443ad3fdeeda44c94a4ea0"),
    "sourceLock": ("outputs/cmu-arctic-four-speaker-v1/source-lock.json",
                   "1a933842159c04413f0cd0c27debd72d3d96a1c5d481d0e7a3346effe8b7583e"),
    "corpusExperiment": ("experiments/cmu-arctic-four-speaker-v1.json",
                         "eee46e9984cebe00627c441bdf0db3d055b65125ac65080999450494da522e8f"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    return digest(path.read_bytes())


def load_recipe() -> dict:
    recipe = read_json(RECIPE)
    require(set(recipe) == {
        "schemaVersion", "experiment", "purpose", "manifest", "manifestSha256",
        "sourceLock", "sourceLockSha256", "corpusExperiment", "corpusExperimentSha256",
        "partition", "automaticPhone", "encoder", "encoderRevision", "sampleRate",
        "convKernels", "convStrides", "maxCpuMathThreads", "outputDirectory",
        "labelSource", "fitsModel", "scoresPronunciation", "productionEligible",
        "learnerFeedbackEligible",
    }, "Crop recipe fields changed")
    require(recipe["schemaVersion"] == 1 and
            recipe["experiment"] == "cmu-arctic-r-crop-preflight-v1" and
            recipe["purpose"] == "train-only automatic-timing crop and frozen-encoder engineering preflight" and
            recipe["partition"] == "train" and recipe["automaticPhone"] == "r" and
            recipe["encoder"] == Wav2VecEncoder.identity["kind"] and
            recipe["encoderRevision"] == Wav2VecEncoder.identity["revision"] and
            recipe["sampleRate"] == 16000 and recipe["convKernels"] == KERNELS and
            recipe["convStrides"] == STRIDES and recipe["maxCpuMathThreads"] == 2 and
            recipe["outputDirectory"] == "outputs/cmu-arctic-r-crop-preflight-v1" and
            recipe["labelSource"] == "automatic-phone-alignment" and
            all(recipe[key] is False for key in ("fitsModel", "scoresPronunciation",
                                                  "productionEligible", "learnerFeedbackEligible")),
            "Crop recipe changed its locked engineering scope")
    for key, (relative, expected) in SOURCE_FILES.items():
        require(recipe[key] == relative and recipe[key + "Sha256"] == expected,
                f"Crop recipe changed its pinned {key}")
        path = HERE / relative
        require(path.is_file() and not path.is_symlink() and sha256_file(path) == expected,
                f"Pinned {key} is missing, redirected, or changed")
    return recipe


def train_rows(rows: list[dict]) -> list[dict]:
    """The manifest loader verifies all splits; only train rows reach extraction."""
    require(len(rows) == 216 and sum(row["split"] == "train" for row in rows) == 192,
            "Pinned four-speaker split counts changed")
    selected = [row for row in rows if row["split"] == "train"]
    require(all(row["alignmentPath"].split("/", 1)[0] in {"bdl", "awb", "clb", "jmk"}
                for row in selected), "Unexpected train speaker in automatic alignments")
    return selected


def interval_rows(rows: list[dict], root: Path) -> list[dict]:
    """Read only train LABs after load_manifest has checked their source hashes."""
    selected = []
    for row in rows:
        require(row["split"] == "train", "Non-training row reached timed parser")
        samples = row["samples"]
        alignment = root / row["alignmentPath"]
        alignment_bytes = alignment.read_bytes()
        require(digest(alignment_bytes) == row["alignmentSha256"],
                "Timed alignment changed after source validation")
        timed = parse_timed_alignment(alignment_bytes, len(samples) / 16000)
        require([phone for _, _, phone in timed] == row["pseudoPhones"],
                "Timed alignment differs from verified manifest phones")
        for position, (start, end, phone) in enumerate(timed):
            if phone == "r":
                selected.append({"clipId": row["id"], "phoneIndex": position,
                                 "startSeconds": str(start), "endSeconds": str(end),
                                 "samples": samples})
    return selected


def inspect_crops(intervals: list[dict], encoder: Wav2VecEncoder) -> list[dict]:
    config = encoder.model.config
    require(encoder.identity == Wav2VecEncoder.identity and
            list(config.conv_kernel) == KERNELS and list(config.conv_stride) == STRIDES,
            "Pinned encoder identity or convolution geometry changed")
    records = []
    for interval in intervals:
        start, end = float(interval["startSeconds"]), float(interval["endSeconds"])
        samples = interval["samples"]
        record = {key: interval[key] for key in
                  ("clipId", "phoneIndex", "startSeconds", "endSeconds")}
        require(0 <= start < end <= len(samples) / 16000,
                "Automatic target interval falls outside verified audio")
        try:
            cropped, bounds = crop_audio_interval(
                samples, sample_rate=16000, start_seconds=start, end_seconds=end,
                conv_kernels=KERNELS, conv_strides=STRIDES)
        except ValueError as exc:
            if str(exc) != "Audio is shorter than the encoder receptive field":
                raise
            records.append({**record, "status": "tooShortForEncoder",
                            "startSample": math.floor(start * 16000),
                            "endSample": math.ceil(end * 16000),
                            "receptiveFieldSamples": 400})
            continue
        require(torch.equal(cropped, samples[bounds[0]:bounds[1]]),
                "Crop differs from its exact source sample range")
        expected_frames = conv_geometry(KERNELS, STRIDES, len(cropped))[2]
        produced = encoder(cropped)
        require(produced.ndim == 2 and tuple(produced.shape) == (expected_frames, 768)
                and produced.is_floating_point() and torch.isfinite(produced).all(),
                "Pinned encoder returned invalid crop frames")
        records.append({**record, "status": "valid", "startSample": bounds[0],
                        "endSample": bounds[1], "cropSamples": len(cropped),
                        "encoderFrames": expected_frames})
    return records


def summarize(records: list[dict], recipe: dict) -> dict:
    valid = [row for row in records if row["status"] == "valid"]
    short = [row for row in records if row["status"] == "tooShortForEncoder"]
    require(len(valid) + len(short) == len(records), "Unknown crop status")
    require(len(records) > 0, "No automatic /r/ intervals found")
    return {"schemaVersion": 1, "experiment": recipe["experiment"],
            "purpose": recipe["purpose"], "labelSource": recipe["labelSource"],
            "source": {key + "Sha256": sha for key, (_, sha) in SOURCE_FILES.items()},
            "recipeSha256": sha256_file(RECIPE),
            "codeSha256": {name: sha256_file(HERE / name) for name in
                           ("cmu_arctic_r_crop_preflight.py", "labels.py", "target_pool.py",
                            "data.py", "encoders.py")},
            "encoder": Wav2VecEncoder.identity, "sourcePartitionsValidated":
            ["train", "calibration", "test"], "inferencePartition": "train",
            "automaticTargetPhone": "r", "sampleRate": 16000,
            "receptiveFieldSamples": 400, "frameHopSamples": 320,
            "trainingClips": 192, "trainingClipsWithTarget": len({r["clipId"] for r in records}),
            "automaticTargetIntervals": len(records), "validCrops": len(valid),
            "tooShortForEncoder": len(short),
            "validCropSamples": {"min": min(r["cropSamples"] for r in valid),
                                 "median": statistics.median(r["cropSamples"] for r in valid),
                                 "max": max(r["cropSamples"] for r in valid)},
            "validEncoderFrames": {"min": min(r["encoderFrames"] for r in valid),
                                   "median": statistics.median(r["encoderFrames"] for r in valid),
                                   "max": max(r["encoderFrames"] for r in valid),
                                   "total": sum(r["encoderFrames"] for r in valid)},
            "intervals": records, "fitsModel": False, "scoresPronunciation": False,
            "productionEligible": False, "learnerFeedbackEligible": False}


def publish(report: dict) -> None:
    require(not OUTPUT.exists() and not OUTPUT.is_symlink(), "Preflight output already exists")
    require(OUTPUT.parent.is_dir() and not OUTPUT.parent.is_symlink(),
            "Output parent is missing or redirected")
    temporary = Path(tempfile.mkdtemp(prefix=".arctic-r-crop-", dir=OUTPUT.parent))
    try:
        temporary.chmod(0o700)
        path = temporary / "report.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
            target.flush()
            os.fsync(target.fileno())
        os.rename(temporary, OUTPUT)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run() -> dict:
    require(not OUTPUT.exists() and not OUTPUT.is_symlink(), "Preflight output already exists")
    recipe = load_recipe()
    torch.set_num_threads(recipe["maxCpuMathThreads"])
    # This validates all splits and their source bytes; extraction below uses train only.
    _manifest, rows = load_manifest(HERE / recipe["manifest"])
    intervals = interval_rows(train_rows(rows), (HERE / recipe["manifest"]).parent)
    encoder = Wav2VecEncoder(MODEL_CACHE, allow_download=False)
    report = summarize(inspect_crops(intervals, encoder), recipe)
    publish(report)
    return {key: report[key] for key in
            ("experiment", "trainingClips", "trainingClipsWithTarget",
             "automaticTargetIntervals", "validCrops", "tooShortForEncoder")}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
