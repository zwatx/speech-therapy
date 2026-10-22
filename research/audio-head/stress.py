"""Fixed engineering gain/noise checks on identical, already-inspected holdouts."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import platform
import time

import torch

from comparison import compare_runs, partition_signature
from data import AUTHORITY, digest, load_manifest, read_json
from encoders import load_encoder
from pipeline import load_head, metrics


RECIPE = {
    "schemaVersion": 1,
    "purpose": "engineering-acoustic-stress",
    "conditions": ["original", "gain-minus-6db", "white-noise-20db", "white-noise-10db"],
    "noiseSeed": 17,
    "noiseGenerator": "torch-cpu-float64-normal; seed from sha256(17:audioSha256:white-noise-v1)",
    "snrBasis": "whole-recording RMS, including silence; measured after float32 mixture conversion",
    "peakPolicy": "If mixture peak exceeds 0.99, scale signal and noise together; never hard clip",
    "holdoutStatus": "already-inspected-engineering-holdouts; not fresh confirmatory evidence",
    "reporting": "Every supplied head and condition; no training, tuning, ranking, or winner selection",
    "waveformChanges": "No pitch, time, trim, resample, or label changes",
    "productionEligible": False,
    "learnerFeedbackEligible": False,
}


def transform(samples: torch.Tensor, condition: str, audio_sha256: str) -> tuple[torch.Tensor, dict]:
    if (samples.dtype != torch.float32 or samples.device.type != "cpu" or samples.ndim != 1
            or not samples.numel() or not torch.isfinite(samples).all()
            or float(samples.abs().max()) >= 1 or float(samples.double().square().mean()) <= 0):
        raise ValueError("Stress input must be finite non-silent mono float32 CPU audio below full scale")
    if condition not in RECIPE["conditions"]:
        raise ValueError("Unsupported predeclared stress condition")
    if not isinstance(audio_sha256, str) or len(audio_sha256) != 64 or any(c not in "0123456789abcdef" for c in audio_sha256):
        raise ValueError("Stress noise identity requires a SHA-256")
    scale, target_snr, actual_snr, noise_seed = 1.0, None, None, None
    if condition == "original":
        output = samples.clone()
    elif condition == "gain-minus-6db":
        output = samples * (10 ** (-6 / 20))
    else:
        target_snr = 20 if condition == "white-noise-20db" else 10
        noise_seed = int(digest(f"17:{audio_sha256}:white-noise-v1".encode())[:16], 16) % (2**63)
        generator = torch.Generator(device="cpu").manual_seed(noise_seed)
        signal = samples.double()
        noise = torch.randn(signal.shape, generator=generator, dtype=torch.float64)
        noise *= torch.sqrt(signal.square().mean() / noise.square().mean() / (10 ** (target_snr / 10)))
        mixed = signal + noise
        peak = float(mixed.abs().max())
        scale = min(1.0, 0.99 / peak)
        output = (mixed * scale).float()
        # Measure the delivered waveform's residual against the equally scaled clean signal.
        delivered_signal = (signal * scale).float().double()
        delivered_noise = output.double() - delivered_signal
        actual_snr = 10 * math.log10(float(delivered_signal.square().sum() / delivered_noise.square().sum()))
    if not torch.isfinite(output).all() or float(output.abs().max()) >= 1:
        raise ValueError("Stress transform produced unsafe samples")
    return output, {
        "sampleCount": samples.numel(), "inputPeak": float(samples.abs().max()),
        "outputPeak": float(output.abs().max()), "mixtureScale": scale,
        "gainDb": -6 if condition == "gain-minus-6db" else 0,
        "targetSnrDb": target_snr, "achievedSnrDb": actual_snr, "noiseSeed": noise_seed,
        "waveformSha256": digest(output.numpy().astype("<f4").tobytes()),
    }


def check_original_metrics(observed: dict, stored: dict) -> None:
    for field in ("count", "referenceTokenCount", "tokenEdits", "exactSequenceMatches"):
        if observed[field] != stored[field]:
            raise ValueError("Original-condition recomputation differs from the saved run")
    if not math.isclose(observed["ctcLoss"], stored["ctcLoss"], rel_tol=1e-5, abs_tol=1e-6):
        raise ValueError("Original-condition CTC loss differs from the saved run")


def run_stress(runs: list[tuple[Path, Path]], output: Path, cache: Path, recipe_path: Path) -> dict:
    if output.exists():
        raise ValueError("Output exists; choose a new stress report name")
    recipe_bytes = recipe_path.read_bytes()
    if read_json(recipe_path) != RECIPE:
        raise ValueError("Stress recipe differs from the fixed predeclared protocol")
    comparison = compare_runs(runs)
    reference = comparison["runs"][0]
    manifest, all_rows = load_manifest(runs[0][1])
    if digest(runs[0][1].read_bytes()) != reference["manifestSha256"]:
        raise ValueError("Reference manifest changed during validation")
    rows = [row for row in all_rows if row["split"] in {"calibration", "test"}]
    for split in ("calibration", "test"):
        if partition_signature(rows, split) != reference["partitionSha256"][split]:
            raise ValueError("Holdout membership changed during validation")
    heads = []
    for (directory, _), evidence in zip(runs, comparison["runs"]):
        head, metadata = load_head(directory)
        if any(metadata[field] != evidence[field] for field in ("checkpointSha256", "encoder", "vocabulary", "head")):
            raise ValueError("Checkpoint changed during validation")
        heads.append(head)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    started = time.perf_counter()
    encoder = load_encoder(reference["encoder"]["kind"], cache, allow_download=False)
    if encoder.identity != reference["encoder"]:
        raise ValueError("Loaded encoder differs from all compared checkpoints")
    encoder_seconds = time.perf_counter() - started
    conditions = []
    for condition in RECIPE["conditions"]:
        feature_started = time.perf_counter()
        prepared, waveforms = [], []
        with torch.no_grad():
            for row in rows:
                samples, measurements = transform(row["samples"], condition, row["audioSha256"])
                features = encoder(samples)
                if features.ndim != 2 or features.shape[1] != reference["encoder"]["width"]:
                    raise ValueError("Stress encoder feature width mismatch")
                prepared.append({**row, "features": features})
                waveforms.append({"id": row["id"], "split": row["split"],
                                  "audioSha256": row["audioSha256"], **measurements})
        feature_seconds = time.perf_counter() - feature_started
        evaluations = []
        for head, evidence in zip(heads, comparison["runs"]):
            splits = {split: metrics(head, [r for r in prepared if r["split"] == split], manifest["vocabulary"])
                      for split in ("calibration", "test")}
            if any(not math.isfinite(value["ctcLoss"]) for value in splits.values()):
                raise ValueError("Nonfinite stress evaluation loss")
            if condition == "original":
                for split in splits:
                    check_original_metrics(splits[split], evidence["splits"][split])
            evaluations.append({"name": evidence["name"], "checkpointSha256": evidence["checkpointSha256"],
                                "splits": splits})
        conditions.append({"name": condition, "waveforms": waveforms, "runs": evaluations,
                           "featureExtractionSeconds": feature_seconds})
        del prepared  # Share one condition's frozen features across heads, then release them.
    report = {"schemaVersion": 1, "purpose": RECIPE["purpose"], **AUTHORITY,
              "calibrated": False, "selectionPerformed": False,
              "labelSource": reference["labelSource"], "splitIdentityBasis": reference["splitIdentityBasis"],
              "recipe": RECIPE, "recipeSha256": digest(recipe_bytes),
              "encoder": reference["encoder"], "vocabulary": manifest["vocabulary"],
              "runs": [{k: v for k, v in run.items() if k not in {"splits", "differenceFromFirst"}}
                       for run in comparison["runs"]],
              "conditions": conditions,
              "measurements": {"encoderLoads": 1, "encodedClips": len(rows) * len(conditions),
                               "encoderLoadSeconds": encoder_seconds,
                               "totalSeconds": time.perf_counter() - started},
              "environment": {"python": platform.python_version(), "torch": torch.__version__,
                              "machine": platform.machine(), "device": "cpu", "threads": 2},
              "sourceSha256": {p.name: digest(p.read_bytes()) for p in Path(__file__).parent.glob("*.py")},
              "limitations": ["Descriptive engineering stress only; no training, tuning, winner, or deployment approval.",
                              "These holdouts were already inspected; no independent or population robustness claim.",
                              "Targets remain unchanged corpus labels; automatic alignment agreement is not produced-phone accuracy.",
                              "Whole-recording SNR includes silence and does not represent speech-active or real environmental noise.",
                              "Waveforms and frozen features are held in memory only; no persistent feature cache.",
                              "Gain behavior depends on the exact checkpoint's preprocessing and normalization."]}
    with output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", nargs=2, type=Path, required=True,
                        metavar=("RUN_DIRECTORY", "MANIFEST"))
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path(__file__).parent / "outputs" / "model-cache")
    args = parser.parse_args()
    try:
        result = run_stress(args.run, args.output, args.cache, args.recipe)
        print(f"Saved {len(result['runs'])} heads across {len(result['conditions'])} fixed stress conditions: {args.output}")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Stress report failed: {exc}\n")


if __name__ == "__main__":
    main()
