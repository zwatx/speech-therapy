"""Measure one verified engineering head in a fresh process, with downloads disabled."""
import argparse
import json
import math
from pathlib import Path
import platform
import resource
import statistics
import time

import torch

from comparison import load_run
from data import AUTHORITY, SAMPLE_RATE, digest, load_manifest
from encoders import load_encoder
from pipeline import frame_posteriors, load_head


def summary(values):
    ordered = sorted(values)
    return {"count": len(values), "median": statistics.median(values),
            "p95NearestRank": ordered[math.ceil(0.95 * len(ordered)) - 1],
            "minimum": ordered[0], "maximum": ordered[-1]}


def measure(checkpoint: Path, manifest_path: Path, cache: Path, repeats: int = 3):
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError("Use 1–5 fixed measured passes")
    evidence = load_run(checkpoint, manifest_path)
    _, rows = load_manifest(manifest_path)
    clips = sorted((row for row in rows if row["split"] in {"calibration", "test"}),
                   key=lambda row: row["id"])
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    head, metadata = load_head(checkpoint)
    encoder = load_encoder(metadata["encoder"]["kind"], cache, allow_download=False)
    construction_seconds = time.perf_counter() - started

    def execute(row):
        started = time.perf_counter()
        frames = frame_posteriors(head, encoder(row["samples"]), metadata["vocabulary"])
        milliseconds = (time.perf_counter() - started) * 1000
        posterior_sha = digest(json.dumps(frames, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        duration_ms = len(row["samples"]) / SAMPLE_RATE * 1000
        return {"id": row["id"], "audioSha256": row["audioSha256"], "split": row["split"],
                "durationMilliseconds": duration_ms, "frameCount": len(frames),
                "inferenceMilliseconds": milliseconds, "realTimeFactor": milliseconds / duration_ms,
                "posteriorSha256": posterior_sha}

    # Report the first call separately. No feature/posterior cache is retained.
    first_call = execute(clips[0])
    measurements, reference = [], {first_call["id"]: first_call["posteriorSha256"]}
    for pass_index in range(repeats):
        for row in clips:
            result = execute(row)
            if result["posteriorSha256"] != reference.setdefault(row["id"], result["posteriorSha256"]):
                raise ValueError("Repeated inference changed its normalized posterior output")
            measurements.append({"pass": pass_index + 1, **result})
    raw_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB. Other platforms are not supported.
    system = platform.system()
    if system not in {"Darwin", "Linux"}:
        raise ValueError("Peak RSS units are supported only on macOS and Linux")
    return {"schemaVersion": 1, "purpose": "engineering-local-runtime-measurement", **AUTHORITY,
            "calibrated": False, "selectionPerformed": False, "run": evidence,
            "runnerSha256": digest(Path(__file__).read_bytes()), "repeats": repeats,
            "runtimeConstructionSeconds": construction_seconds, "firstInference": first_call,
            "peakProcessResidentBytes": raw_peak if system == "Darwin" else raw_peak * 1024,
            "warmInferenceMilliseconds": summary([row["inferenceMilliseconds"] for row in measurements]),
            "warmRealTimeFactor": summary([row["realTimeFactor"] for row in measurements]),
            "measurements": measurements,
            "environment": {"python": platform.python_version(), "torch": torch.__version__,
                            "platform": platform.platform(), "machine": platform.machine(),
                            "device": "cpu", "threads": 2},
            "limitations": [
                "Fresh process with cached weights; this is not an empty-cache or cold-filesystem measurement.",
                "Timed calls include preprocessing, encoder, head, softmax validation and Python frame dictionaries; exclude audio decoding, JSON encoding and transport.",
                "Peak RSS is the whole process, including imports, manifest validation/decoded audio and checkpoint verification; it is not model-only memory.",
                "Fixed clip order and repeated calls on one machine describe this run, not independent users or a population latency guarantee.",
                "No concurrency, server request queue, mobile device, energy or clinical validation was measured.",
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(__file__).parent / "outputs/model-cache")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; preserve previous measurements")
    report = measure(args.checkpoint, args.manifest, args.cache, args.repeats)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(f"Saved {len(report['measurements'])} timed calls: {args.output}")


if __name__ == "__main__":
    main()
