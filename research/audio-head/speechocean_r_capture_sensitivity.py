"""Locked, local capture sensitivity of existing whole-clip /R/ rating heads.

Only the established 40-speaker public author-training sample is processed.
Probability changes are descriptive sensitivity, never pronunciation accuracy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import time

import numpy as np
import torch

import speechocean_r_annotation_sample as sample
from speechocean_r_local_infer import OUTPUT as HEAD_OUTPUT, verified_head
from speechocean_r_probe import CACHE, HERE, read_rating_pcm, sha256_file
from speechocean_r_rater_cv import predict_softmax
from speechocean_r_rater_final_fit import load_recipe as load_head_recipe
from speechocean_train_cv import ENCODERS
from stress import RECIPE as TRANSFORM_RECIPE, transform


RECIPE_PATH = HERE / "experiments/speechocean-r-capture-sensitivity-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-capture-sensitivity-v1/report.json"
FALSE_FLAGS = ("authorTestInferencePerformed", "trainingPerformed", "selectionPerformed",
               "calibrated", "productionEligible", "calibrationEligible",
               "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished")
EXPECTED_RECIPE = {
    "schemaVersion": 1,
    "experiment": "speechocean-r-capture-sensitivity-v1",
    "purpose": "Descriptive capture sensitivity of fixed whole-clip corpus-rating heads",
    "authorPartition": "train",
    "sampleRecipeSha256": "a0f874483c61738d695b3d63da3c74e4697a9b04fd4ff60533b539edd12abcb6",
    "headRecipeSha256": "48c738d934d992d54b4249bf644e1faa86fd75d7672b41eb5b022766281f18ee",
    "headsSha256": "376e387a7a57da7ef1fb94fb0e948f2847a571c194cd05be9ce3a933d5ba7485",
    "expectedClips": 40,
    "expectedSpeakers": 40,
    "encoders": ["wav2vec2-base", "wavlm-base-plus"],
    "conditions": ["original", "gain-minus-6db", "white-noise-20db", "white-noise-10db"],
    "transform": "Reuse stress.transform with its locked seed 17 and whole-recording RMS SNR",
    "maxCpuMathThreads": 2,
    "metrics": ["total-variation-distance", "expected-rating-shift", "argmax-class-change"],
    "grouping": "all clips and the four existing sample strata; no setting or winner selection",
    **{flag: False for flag in FALSE_FLAGS},
}
SOURCE_NAMES = ("speechocean_r_capture_sensitivity.py", "stress.py", "encoders.py",
                "speechocean_r_annotation_sample.py", "speechocean_r_label_audit.py",
                "speechocean_audit.py", "speechocean_r_local_infer.py",
                "speechocean_r_rater_final_fit.py", "speechocean_r_rater_cv.py",
                "speechocean_r_probe.py", "speechocean_train_cv.py", "data.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_recipe(path: Path = RECIPE_PATH) -> dict:
    recipe = json.loads(path.read_text())
    require(recipe == EXPECTED_RECIPE, "Capture-sensitivity recipe differs from locked settings")
    require(sha256_file(sample.RECIPE) == recipe["sampleRecipeSha256"],
            "Annotation sample recipe SHA-256 mismatch")
    require(sha256_file(HERE / "experiments/speechocean-r-rater-final-fit-v1.json") ==
            recipe["headRecipeSha256"], "Saved head recipe SHA-256 mismatch")
    require(sha256_file(HEAD_OUTPUT / "heads.npz") == recipe["headsSha256"],
            "Saved head SHA-256 mismatch")
    require(TRANSFORM_RECIPE["conditions"] == recipe["conditions"] and
            TRANSFORM_RECIPE["noiseSeed"] == 17, "Existing transform settings changed")
    return recipe


def validate_probabilities(probabilities: np.ndarray) -> None:
    require(probabilities.ndim == 2 and probabilities.shape[0] > 0 and
            probabilities.shape[1] == 3 and np.isfinite(probabilities).all() and
            np.all((probabilities >= 0) & (probabilities <= 1)) and
            np.all(np.abs(probabilities.sum(axis=1) - 1) <= 1e-10),
            "Expected nonempty finite three-class probability simplexes")


def summarize(clean: np.ndarray, changed: np.ndarray) -> dict:
    """Paired descriptive probability movement; labels are intentionally absent."""
    validate_probabilities(clean)
    validate_probabilities(changed)
    require(clean.shape == changed.shape, "Paired probability shapes differ")
    delta = changed - clean
    variation = np.abs(delta).sum(axis=1) / 2
    rating_shift = delta @ np.asarray([0.0, 1.0, 2.0])
    return {"clips": len(clean), "meanTotalVariation": float(variation.mean()),
            "maxTotalVariation": float(variation.max()),
            "meanExpectedRatingShift": float(rating_shift.mean()),
            "meanAbsoluteExpectedRatingShift": float(np.abs(rating_shift).mean()),
            "maxAbsoluteExpectedRatingShift": float(np.abs(rating_shift).max()),
            "argmaxClassChanges": int(np.count_nonzero(
                np.argmax(clean, axis=1) != np.argmax(changed, axis=1))),
            "argmaxTieRule": "lowest class index; argmax is not a learner decision"}


def group_summaries(clean: np.ndarray, changed: np.ndarray, rows: list[dict]) -> dict:
    require(len(rows) == len(clean), "Sample and probability counts differ")
    require({row["stratum"] for row in rows} == set(sample.STRATA),
            "Expected all four predeclared sample strata")
    result = {"all": summarize(clean, changed)}
    for stratum in sample.STRATA:
        mask = np.asarray([row["stratum"] == stratum for row in rows])
        result[stratum] = summarize(clean[mask], changed[mask])
    return result


def prepared_sample(recipe: dict) -> tuple[list[dict], list[torch.Tensor]]:
    sample_recipe = sample.load_recipe()
    # This existing reader selects author-training JSON objects only. It does
    # not read reviewer packs, blinding keys, or any published test WAV.
    rows = sample.select_sample(sample.build_candidates(), sample_recipe)
    sample.verify_selected_wavs(rows)
    require(len(rows) == recipe["expectedClips"] and
            len({row["speakerId"] for row in rows}) == recipe["expectedSpeakers"],
            "Sample clip or speaker count differs from predeclaration")
    return rows, [read_rating_pcm(Path(row["wavPath"]), row["wavSha256"]) for row in rows]


def pooled_probabilities(encoder: object, head: dict, waveform: torch.Tensor) -> np.ndarray:
    frames = encoder(waveform)
    require(frames.ndim == 2 and frames.shape[0] > 0 and frames.shape[1] == 768 and
            torch.isfinite(frames).all(), "Encoder returned invalid contextual frames")
    # Match the existing saved-head replay's float32 feature boundary exactly.
    pooled = frames.mean(dim=0).numpy().astype(np.float32).astype(np.float64)
    probabilities = predict_softmax(head, pooled[None, :])
    validate_probabilities(probabilities)
    return probabilities[0]


def run(output: Path = OUTPUT) -> dict:
    started = time.perf_counter()
    output = output.absolute()
    require(output.resolve().is_relative_to(HERE / "outputs"),
            "Report must remain in ignored research outputs")
    sample.require_real_generated_path(output, HERE)
    require(not output.exists(), "Report already exists; choose a new report filename")
    source_evidence = {name: sha256_file(HERE / name) for name in SOURCE_NAMES}
    recipe = load_recipe()
    head_recipe = load_head_recipe()
    heads = {kind: verified_head(kind, head_recipe) for kind in recipe["encoders"]}
    rows, samples = prepared_sample(recipe)
    verification_seconds = time.perf_counter() - started
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    torch.set_num_threads(recipe["maxCpuMathThreads"])
    torch.use_deterministic_algorithms(True)
    results = {}
    waveform_evidence = {}
    for kind in recipe["encoders"]:
        load_started = time.perf_counter()
        encoder = ENCODERS[kind](CACHE, allow_download=False)
        require(encoder.identity == ENCODERS[kind].identity, "Loaded encoder identity changed")
        load_seconds = time.perf_counter() - load_started
        predictions = {}
        conditions = []
        for condition in recipe["conditions"]:
            condition_started = time.perf_counter()
            probabilities, measurements, latencies = [], [], []
            for row, pcm in zip(rows, samples, strict=True):
                waveform, measurement = transform(pcm, condition, row["wavSha256"])
                inference_started = time.perf_counter()
                probabilities.append(pooled_probabilities(encoder, heads[kind], waveform))
                latencies.append(time.perf_counter() - inference_started)
                measurements.append({"sourceId": row["sourceId"], **measurement})
            predictions[condition] = np.asarray(probabilities)
            if condition in waveform_evidence:
                require(waveform_evidence[condition] == measurements,
                        "Encoders did not receive identical transformed waveforms")
            else:
                waveform_evidence[condition] = measurements
            conditions.append({"condition": condition,
                               "summary": group_summaries(predictions["original"],
                                                          predictions[condition], rows),
                               "subjectiveCorpusRatingProbabilities": predictions[condition].tolist(),
                               "inferenceSeconds": latencies,
                               "elapsedSeconds": time.perf_counter() - condition_started})
            print(f"Completed {kind}: {condition}, {len(rows)} public training clips", flush=True)
        results[kind] = {"encoder": encoder.identity, "encoderLoadSeconds": load_seconds,
                         "conditions": conditions}
        del encoder
    require(source_evidence == {name: sha256_file(HERE / name) for name in SOURCE_NAMES},
            "Research source changed during inference")
    report = {"schemaVersion": 1, "experiment": recipe["experiment"], "recipe": recipe,
              "recipeSha256": sha256_file(RECIPE_PATH),
              "createdAtUtc": datetime.now(timezone.utc).isoformat(),
              "authorPartition": "train", "inputSource": "pinned-public-author-training",
              "sourceArchiveSha256": head_recipe["sourceArchiveSha256"],
              "sourceMetadataSha256": sample.load_recipe()["sourceMetadataSha256"],
              "headReportSha256": sha256_file(HEAD_OUTPUT / "report.json"),
              "headProvenanceSha256": sha256_file(HEAD_OUTPUT / "provenance.json"),
              "sourceCodeSha256": source_evidence,
              "requirementsLockSha256": sha256_file(HERE / "requirements.lock.txt"),
              "selectedIdsSha256": hashlib.sha256(
                  ("\n".join(row["sourceId"] for row in rows) + "\n").encode()).hexdigest(),
              "sampleRows": [{key: row[key] for key in
                              ("sourceId", "speakerId", "age", "stratum", "wavSha256")}
                             for row in rows],
              "transformRecipe": TRANSFORM_RECIPE,
              "waveforms": waveform_evidence, "results": results,
              "measurements": {"encodedClips": len(rows) * len(recipe["conditions"]) * len(results),
                               "verificationSeconds": verification_seconds,
                               "totalSeconds": time.perf_counter() - started,
                               "failures": 0},
              "environment": {"python": platform.python_version(), "torch": torch.__version__,
                              "numpy": np.__version__, "machine": platform.machine(),
                              "platform": platform.platform(), "device": "cpu", "threads": 2},
              "limitations": [
                  "All sample clips were used in the fixed heads' training; no generalization claim.",
                  "The balanced 40-speaker sample is not representative of ages 2–12 or child SSD.",
                  "Whole-clip subjective corpus-rating probabilities do not localize or judge /R/.",
                  "No transformed audio was rated by an expert; no accuracy or calibration metrics.",
                  "Whole-recording white-noise SNR includes silence; it is not real-world noise.",
                  "Waveforms and new features remain in memory; no audio or features are exported.",
                  "Argmax changes are descriptive; ties choose the lower index, not an accepted class.",
                  "No model selection, training, downloads, or new clinical evidence."],
              **{flag: False for flag in FALSE_FLAGS}}
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as target:
        json.dump(report, target, indent=2, sort_keys=True, allow_nan=False)
        target.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        result = run(args.output)
        print(json.dumps({"experiment": result["experiment"],
                          **result["measurements"], "output": str(args.output)}, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"Capture-sensitivity run failed without a completed report: {exc}\n")
