"""Read-only diagnostics of the locked SpeechOcean train-side rater OOF predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
RECIPE = HERE / "experiments/speechocean-r-oof-diagnostics-v1.json"
METHODS = ("wav2vec2-base", "wavlm-base-plus", "trainPrior", "targetWord")
GROUPS = ("unanimousTwo", "unanimousZero", "mixed")
FALSE_FLAGS = ("modelFitPerformed", "productionEligible", "calibrationEligible",
               "learnerFeedbackEligible", "clinicalUseEligible",
               "clinicalReliabilityEstablished", "authorTestUsedForSettings")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_file(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def safe_relative(base: Path, value: str) -> Path:
    path = Path(value)
    require(not path.is_absolute() and ".." not in path.parts,
            "Recipe input/output path must stay under the analysis directory")
    return base / path


def validate_recipe(recipe: dict) -> None:
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == "speechocean-r-oof-diagnostics-v1" and
            recipe.get("authorPartition") == "train" and
            recipe.get("knownAuthorTest") is True and
            all(recipe.get(flag) is False for flag in FALSE_FLAGS), "Invalid research-only recipe")
    require(recipe.get("expectedClips") == 766 and recipe.get("expectedSpeakers") == 124 and
            recipe.get("ratersPerClip") == 5 and recipe.get("methods") == list(METHODS) and
            recipe.get("agreementGroups") == list(GROUPS) and
            recipe.get("expectedUnanimousOneClips") == 0 and
            recipe.get("logLossEpsilon") == 1e-12, "Unexpected diagnostic recipe settings")
    bootstrap = recipe.get("bootstrap", {})
    require(bootstrap.get("unit") == "speaker" and bootstrap.get("resamples") == 2000 and
            bootstrap.get("seed") == 20260923 and
            bootstrap.get("confidencePercentiles") == [2.5, 97.5] and
            bootstrap.get("comparisons") == [["wav2vec2-base", "trainPrior"],
                                             ["wav2vec2-base", "targetWord"],
                                             ["wavlm-base-plus", "wav2vec2-base"]],
            "Unexpected bootstrap recipe settings")
    for key in ("inputReportSha256", "inputOutOfFoldSha256"):
        require(isinstance(recipe.get(key), str) and len(recipe[key]) == 64,
                "Missing input SHA-256 pin")


def agreement_group(counts: np.ndarray) -> str:
    require(counts.shape == (3,) and np.issubdtype(counts.dtype, np.integer) and
            np.all(counts >= 0) and counts.sum() == 5, "Invalid five-rater counts")
    if counts[2] == 5:
        return "unanimousTwo"
    if counts[0] == 5:
        return "unanimousZero"
    if counts[1] == 5:
        return "unanimousOne"
    return "mixed"


def per_clip_scores(probabilities: np.ndarray, counts: np.ndarray,
                    epsilon: float) -> tuple[np.ndarray, np.ndarray]:
    require(probabilities.shape == counts.shape and probabilities.ndim == 2 and
            probabilities.shape[1] == 3 and np.isfinite(probabilities).all() and
            np.all((probabilities >= 0) & (probabilities <= 1)) and
            np.allclose(probabilities.sum(axis=1), 1, atol=1e-8) and
            np.issubdtype(counts.dtype, np.integer) and np.all(counts >= 0) and
            np.all(counts.sum(axis=1) == 5), "Invalid probabilities or rater counts")
    fractions = counts / 5.0
    log_loss = -np.sum(fractions * np.log(np.clip(probabilities, epsilon, 1.0)), axis=1)
    brier = np.sum(probabilities * probabilities, axis=1) - 2 * np.sum(
        probabilities * fractions, axis=1) + 1
    return log_loss, brier


def load_predictions(base: Path, recipe: dict) -> tuple[dict, list[dict]]:
    report_path = safe_relative(base, recipe["inputReport"])
    oof_path = safe_relative(base, recipe["inputOutOfFold"])
    require(sha256_file(report_path) == recipe["inputReportSha256"], "Input report SHA-256 mismatch")
    require(sha256_file(oof_path) == recipe["inputOutOfFoldSha256"], "Input OOF SHA-256 mismatch")
    report, rows = json_file(report_path), json_file(oof_path)
    require(report.get("experiment") == "speechocean-r-rater-cv-convergence-v2" and
            report.get("authorPartition") == "train" and
            report.get("knownAuthorTest") is True and
            report.get("authorTestUsedForSettings") is False and
            report.get("outOfFoldSha256") == recipe["inputOutOfFoldSha256"],
            "Source report provenance mismatch")
    require(isinstance(rows, list) and len(rows) == recipe["expectedClips"] and
            report.get("outOfFoldClips") == len(rows) and
            report.get("outOfFoldRaterScores") == 5 * len(rows), "Unexpected OOF row count")
    ids, speakers = set(), set()
    for row in rows:
        require(isinstance(row.get("id"), str) and row["id"] not in ids and
                isinstance(row.get("speaker"), str) and row["speaker"] and
                isinstance(row.get("outerFold"), int) and 0 <= row["outerFold"] < 5 and
                set(row.get("probabilities", {})) == set(METHODS), "Malformed OOF identity")
        ids.add(row["id"])
        speakers.add(row["speaker"])
        require(agreement_group(np.asarray(row["fiveRaterCounts"])) in
                (*GROUPS, "unanimousOne"), "Malformed OOF rater counts")
    require(len(speakers) == recipe["expectedSpeakers"] and
            report.get("outOfFoldSpeakers") == len(speakers), "Unexpected OOF speaker count")
    return report, rows


def speaker_bootstrap(scores: dict[str, np.ndarray], speakers: list[str],
                      comparisons: list[list[str]], seed: int, resamples: int,
                      percentiles: list[float]) -> tuple[dict, np.ndarray]:
    unique = sorted(set(speakers))
    require(len(unique) > 1 and all(len(value) == len(speakers) for value in scores.values()),
            "Invalid speaker bootstrap inputs")
    membership = np.asarray([unique.index(speaker) for speaker in speakers])
    clip_counts = np.bincount(membership, minlength=len(unique))
    draws = np.random.default_rng(seed).integers(0, len(unique), size=(resamples, len(unique)),
                                                 dtype=np.int32)
    denominator = clip_counts[draws].sum(axis=1)
    results = {}
    for first, second in comparisons:
        delta = scores[first] - scores[second]
        cluster_sums = np.bincount(membership, weights=delta, minlength=len(unique))
        replicates = cluster_sums[draws].sum(axis=1) / denominator
        key = f"{first} minus {second}"
        results[key] = {"first": first, "second": second,
                        "pointDifference": float(delta.mean()),
                        "percentileInterval": [float(value) for value in
                                               np.percentile(replicates, percentiles)],
                        "fractionBelowZero": float(np.mean(replicates < 0)),
                        "replicateDifferences": replicates.tolist()}
    return results, draws


def run(recipe_path: Path = RECIPE, base: Path = HERE) -> dict:
    start = time.perf_counter()
    recipe = json_file(recipe_path)
    validate_recipe(recipe)
    source_report, rows = load_predictions(base, recipe)
    counts = np.asarray([row["fiveRaterCounts"] for row in rows], dtype=np.int64)
    groups = np.asarray([agreement_group(value) for value in counts])
    require(np.count_nonzero(groups == "unanimousOne") == recipe["expectedUnanimousOneClips"],
            "Unexpected unanimous-one clips")
    scores = {}
    group_results = {group: {"clips": int(np.count_nonzero(groups == group)),
                             "raterScores": int(5 * np.count_nonzero(groups == group)),
                             "methods": {}} for group in GROUPS}
    pooled = {}
    for method in METHODS:
        probabilities = np.asarray([row["probabilities"][method] for row in rows],
                                   dtype=np.float64)
        loss, brier = per_clip_scores(probabilities, counts, recipe["logLossEpsilon"])
        scores[method] = loss
        pooled[method] = {"perRaterLogLoss": float(loss.mean()),
                          "perRaterBrier": float(brier.mean())}
        for metric in ("perRaterLogLoss", "perRaterBrier"):
            require(abs(pooled[method][metric] -
                        source_report["pooledOutOfFold"][method][metric]) < 1e-10,
                    f"Source pooled {metric} mismatch for {method}")
        for group in GROUPS:
            selected = groups == group
            require(selected.any(), f"Empty agreement group: {group}")
            group_results[group]["methods"][method] = {
                "perRaterLogLoss": float(loss[selected].mean()),
                "perRaterBrier": float(brier[selected].mean())}
    bootstrap, draws = speaker_bootstrap(scores, [row["speaker"] for row in rows],
                                          recipe["bootstrap"]["comparisons"],
                                          recipe["bootstrap"]["seed"],
                                          recipe["bootstrap"]["resamples"],
                                          recipe["bootstrap"]["confidencePercentiles"])
    output = safe_relative(base, recipe["outputDirectory"])
    output.mkdir(parents=True, exist_ok=True)
    bootstrap_path = output / "bootstrap-replicates.json"
    write_json(bootstrap_path, bootstrap)
    report = {"experiment": recipe["experiment"], "recipeSha256": sha256_file(recipe_path),
              "inputReportSha256": recipe["inputReportSha256"],
              "inputOutOfFoldSha256": recipe["inputOutOfFoldSha256"],
              "bootstrapReplicatesSha256": sha256_file(bootstrap_path),
              "bootstrapDrawsSha256": hashlib.sha256(draws.astype("<i4").tobytes()).hexdigest(),
              "bootstrapSeed": recipe["bootstrap"]["seed"],
              "bootstrapResamples": recipe["bootstrap"]["resamples"],
              "bootstrapUnit": "speaker", "bootstrapSpeakerCount": len(set(row["speaker"] for row in rows)),
              "bootstrapInterpretation": "Paired fixed-OOF speaker-cluster resampling preserves each speaker's clips and all five ratings. Intervals ignore retraining and model-selection uncertainty and are exploratory.",
              "differenceDirection": recipe["bootstrap"]["differenceDirection"],
              "overall": pooled, "agreementGroups": group_results,
              "unanimousOneClips": int(np.count_nonzero(groups == "unanimousOne")),
              "comparisons": {key: {name: value for name, value in result.items()
                                    if name != "replicateDifferences"}
                              for key, result in bootstrap.items()},
              "clips": len(rows), "raterScores": int(counts.sum()),
              "authorPartition": "train", "knownAuthorTest": True,
              "limitations": ["Saved train-side OOF predictions only; no new fit or independent confirmation.",
                              "Five rater judgments are not independent clinical ground truth.",
                              "No clinical conclusions, model winner, or learner-feedback use."],
              "elapsedSeconds": time.perf_counter() - start,
              **{flag: False for flag in FALSE_FLAGS}}
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    args = parser.parse_args()
    result = run(args.recipe)
    print(json.dumps({"agreementGroups": {key: value["clips"] for key, value in
                                          result["agreementGroups"].items()},
                      "comparisons": result["comparisons"]}, indent=2))
