"""Train-only nested CV of three-class /R/ rater-distribution heads.

The five expert ratings remain five observations of a subjective judgment.
Nothing here trains produced-phone targets or uses the published author test.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import time

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "4"

import numpy as np
import torch

from speechocean_audit import FILES, mapping, pinned_bytes
from speechocean_r_label_audit import derive_one_r, selected_json_objects
from speechocean_train_cv import (ARCHIVE, AUDIO, ENCODERS, HERE, METADATA,
                                  inner_validation_speakers, outer_speaker_folds,
                                  sha256_file, write_json)


RECIPE = HERE / "experiments/speechocean-r-rater-cv-v1.json"
OUTPUT = HERE / "outputs/speechocean-r-rater-cv-v1"
V2_RECIPE = HERE / "experiments/speechocean-r-rater-cv-convergence-v2.json"
V2_OUTPUT = HERE / "outputs/speechocean-r-rater-cv-convergence-v2"
V1_REPORT_SHA256 = "3a074f53ddbac48ab4e210b6c69883f08e6c4d5518eadbad12b54c0bb2d61339"
AUTHORITY = {"productionEligible": False, "calibrationEligible": False,
             "learnerFeedbackEligible": False, "clinicalUseEligible": False,
             "clinicalReliabilityEstablished": False}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_recipe(path: Path = RECIPE) -> dict:
    configurations = {RECIPE.resolve(): ("speechocean-r-rater-cv-v1", 80,
                                         "outputs/speechocean-r-rater-cv-v1"),
                      V2_RECIPE.resolve(): ("speechocean-r-rater-cv-convergence-v2", 400,
                                            "outputs/speechocean-r-rater-cv-convergence-v2")}
    require(path.resolve() in configurations, "Rater CV recipe path differs from predeclarations")
    experiment, iterations, output_directory = configurations[path.resolve()]
    recipe = json.loads(path.read_text())
    require(recipe.get("schemaVersion") == 1 and
            recipe.get("experiment") == experiment and
            recipe.get("authorPartition") == "train" and
            recipe.get("expectedTrainClips") == 766 and
            recipe.get("expectedTrainSpeakers") == 124 and
            recipe.get("selectedTrainIdsSha256") ==
                "57e5a8ee6c74027d2e4c42d3e8a8892013fd2c6a4fca9cf3cbfcf111864e47e3" and
            recipe.get("sourceArchiveSha256") ==
                "876c34b828c2ebcc35ba2ff1ba5947d50e6b0162fc4a4af91db0942422b3bdd5" and
            recipe.get("sourceMetadataSha256") == {name: FILES[name][1] for name in
                ("train/utt2spk", "resource/scores.json", "resource/scores-detail.json")} and
            set(recipe.get("inputs", {})) == set(ENCODERS) and
            recipe.get("knownAuthorTest") is True and recipe.get("authorTestUsedForSettings") is False and
            recipe.get("outerFolds") == 5 and recipe.get("outerSeed") == 20260923 and
            recipe.get("innerFractionOfOuterTrainSpeakers") == 0.2 and
            recipe.get("classes") == [0, 1, 2] and
            recipe.get("softmaxL2Candidates") == [0.001, 0.01, 0.1] and
            recipe.get("targetWordSmoothingCandidates") == [1.0, 5.0, 20.0] and
            recipe.get("priorPseudocountPerClass") == 1.0 and
            recipe.get("maxOptimizerIterations") == iterations and
            recipe.get("optimizer") ==
                f"Torch CPU float64 LBFGS strong_wolfe, zero initialization, max {iterations} iterations, history 10" and
            recipe.get("maxCpuMathThreads") == 4 and
            recipe.get("logLossEpsilon") == 1e-12 and
            recipe.get("outputDirectory") == output_directory and
            all(recipe.get(key) is False for key in AUTHORITY),
            "Rater CV recipe differs from predeclaration")
    if path.resolve() == V2_RECIPE.resolve():
        baseline = json.loads(RECIPE.read_text())
        allowed = {"experiment", "optimizer", "maxOptimizerIterations", "outputDirectory"}
        require(set(recipe) == set(baseline) and
                all(recipe[key] == baseline[key] for key in baseline if key not in allowed),
                "Convergence recipe changed beyond optimizer cap and v2 IDs")
    return recipe


def load_train_features(recipe: dict) -> tuple[list[dict], dict[str, np.ndarray], dict]:
    require(sha256_file(ARCHIVE) == recipe["sourceArchiveSha256"],
            "Official audio archive SHA-256 mismatch")
    rows_by_encoder = {}
    positions_by_encoder = {}
    matrices = {}
    evidence = {}
    for kind, encoder in ENCODERS.items():
        pin = recipe["inputs"][kind]
        directory = HERE / pin["directory"]
        require(directory.resolve().is_relative_to((HERE / "outputs").resolve()),
                "Feature cache directory outside research outputs")
        actual = {"featureIndexSha256": sha256_file(directory / "feature-index.json"),
                  "featureProgressSha256": sha256_file(directory / "feature-progress.json"),
                  "featureArraySha256": sha256_file(directory / "features.npy")}
        require(all(actual[name] == pin[name] for name in actual),
                f"{kind} feature cache differs from predeclared SHA-256")
        index = json.loads((directory / "feature-index.json").read_text())
        progress = json.loads((directory / "feature-progress.json").read_text())
        require(index.get("encoder") == encoder.identity and
                index.get("recipeVersion") == pin["recipeVersion"] and
                index.get("sourceArchiveSha256") == recipe["sourceArchiveSha256"] and
                type(index.get("rows")) is list and
                progress.get("completed") == len(index["rows"]) and
                progress.get("featureIndexSha256") == actual["featureIndexSha256"] and
                progress.get("featureArraySha256") == actual["featureArraySha256"],
                f"{kind} feature cache metadata mismatch")
        train_positions = [i for i, row in enumerate(index["rows"]) if row.get("split") == "train"]
        train_rows = [index["rows"][i] for i in train_positions]
        require(len(train_rows) == recipe["expectedTrainClips"] and
                len({row["speaker"] for row in train_rows}) == recipe["expectedTrainSpeakers"] and
                len({row["id"] for row in train_rows}) == len(train_rows) and
                all(set(row) == {"id", "split", "speaker", "audioPath", "audioSha256", "rating"}
                    for row in train_rows), "Unexpected train feature rows")
        features = np.load(directory / "features.npy", mmap_mode="r", allow_pickle=False)
        require(features.shape == (len(index["rows"]), 768) and
                features.dtype == np.dtype("float32"), "Feature cache shape or dtype changed")
        selected = np.asarray(features[train_positions], dtype=np.float64)
        require(np.isfinite(selected).all(), "Nonfinite author-train feature")
        rows_by_encoder[kind] = train_rows
        positions_by_encoder[kind] = train_positions
        matrices[kind] = selected
        evidence[kind] = {"directory": pin["directory"], "encoder": encoder.identity,
                          "recipeVersion": pin["recipeVersion"], **actual}
    reference = rows_by_encoder["wav2vec2-base"]
    require(rows_by_encoder["wavlm-base-plus"] == reference and
            positions_by_encoder["wavlm-base-plus"] == positions_by_encoder["wav2vec2-base"],
            "Train source row identity or order differs across encoders")
    return reference, matrices, evidence


def load_rater_counts(rows: list[dict], selected_train_ids_sha256: str) -> np.ndarray:
    selected_ids = {row["id"] for row in rows}
    require(len(selected_ids) == 766 and
            hashlib.sha256(("\n".join(sorted(selected_ids)) + "\n").encode()).hexdigest() ==
            selected_train_ids_sha256,
            "Expected exact pinned 766 author-train IDs")
    train_map = mapping(pinned_bytes(METADATA, "train/utt2spk"), r"\d{9}", r"\d{4}")
    require(selected_ids <= set(train_map), "Selected ID outside author train")
    aggregate = selected_json_objects(pinned_bytes(METADATA, "resource/scores.json"), selected_ids)
    detailed = selected_json_objects(pinned_bytes(METADATA, "resource/scores-detail.json"), selected_ids)
    counts = []
    for row in rows:
        result = derive_one_r(aggregate[row["id"]], detailed[row["id"]])
        require(result is not None and abs(result[0] - row["rating"]) < 1e-9 and
                row["speaker"] == train_map[row["id"]],
                "Five-rater score differs from cached author-train row")
        path = Path(row["audioPath"])
        require(path.resolve().is_relative_to((AUDIO / "WAVE").resolve()) and
                sha256_file(path) == row["audioSha256"],
                "Author-train WAV differs from pinned feature source")
        positions = [(word_index, phone_index, word["text"])
                     for word_index, word in enumerate(aggregate[row["id"]]["words"])
                     for phone_index, phone in enumerate(word["phones"])
                     if phone == "R"]
        require(len(positions) == 1, "Expected one canonical R word")
        row["targetWord"] = positions[0][2]
        five = result[1]
        counts.append([five.count(score) for score in (0, 1, 2)])
    array = np.asarray(counts, dtype=np.int64)
    require(array.shape == (766, 3) and np.all(array.sum(axis=1) == 5),
            "Expected all five rater scores for each selected clip")
    return array


def probabilistic_metrics(probabilities: np.ndarray, counts: np.ndarray,
                          epsilon: float = 1e-12) -> dict:
    require(probabilities.shape == counts.shape and probabilities.shape[1] == 3 and
            np.isfinite(probabilities).all() and np.all(probabilities >= 0) and
            np.all(probabilities <= 1) and
            np.allclose(probabilities.sum(axis=1), 1, atol=1e-8) and
            np.all(counts.sum(axis=1) == 5), "Invalid probability or five-rater score array")
    fractions = counts / 5.0
    safe = np.clip(probabilities, epsilon, 1.0)
    log_loss = -np.mean(np.sum(fractions * np.log(safe), axis=1))
    brier = np.mean(np.sum(probabilities ** 2, axis=1) -
                    2 * np.sum(probabilities * fractions, axis=1) + 1)
    return {"perRaterLogLoss": float(log_loss), "perRaterBrier": float(brier)}


def fit_softmax(x: np.ndarray, counts: np.ndarray, alpha: float,
                max_iterations: int) -> tuple[dict, dict]:
    require(x.ndim == 2 and counts.shape == (len(x), 3) and len(x) >= 2 and
            alpha > 0 and max_iterations > 0, "Invalid softmax training inputs")
    mean = x.mean(axis=0)
    scale = np.where(x.std(axis=0) < 1e-6, 1.0, x.std(axis=0))
    standardized = torch.from_numpy(((x - mean) / scale).astype(np.float64, copy=False))
    fractions = torch.from_numpy((counts / 5.0).astype(np.float64, copy=False))
    weights = torch.zeros((x.shape[1], 3), dtype=torch.float64, requires_grad=True)
    intercept = torch.zeros(3, dtype=torch.float64, requires_grad=True)
    optimizer = torch.optim.LBFGS([weights, intercept], lr=1.0, max_iter=max_iterations,
                                  history_size=10, line_search_fn="strong_wolfe",
                                  tolerance_grad=1e-8, tolerance_change=1e-10)
    closure_calls = 0

    def closure():
        nonlocal closure_calls
        closure_calls += 1
        optimizer.zero_grad()
        logits = standardized @ weights + intercept
        loss = -(fractions * torch.log_softmax(logits, dim=1)).sum(dim=1).mean()
        loss = loss + alpha * weights.square().sum()
        loss.backward()
        return loss

    optimizer.step(closure)
    final_loss = float(closure().detach())
    gradient_norm = float(torch.sqrt(weights.grad.square().sum() +
                                     intercept.grad.square().sum()).detach())
    iterations = int(optimizer.state[weights].get("n_iter", 0))
    head = {"featureMean": mean, "featureScale": scale,
            "weights": weights.detach().numpy().copy(),
            "intercept": intercept.detach().numpy().copy(), "alpha": alpha}
    diagnostics = {"optimizerIterations": iterations, "closureCalls": closure_calls,
                   "atIterationLimit": iterations >= max_iterations,
                   "finalObjective": final_loss, "gradientNorm": gradient_norm}
    require(np.isfinite(head["weights"]).all() and np.isfinite(head["intercept"]).all() and
            np.isfinite(final_loss) and np.isfinite(gradient_norm), "Nonfinite softmax fit")
    return head, diagnostics


def predict_softmax(head: dict, x: np.ndarray) -> np.ndarray:
    logits = ((x - head["featureMean"]) / head["featureScale"]) @ head["weights"] + head["intercept"]
    shifted = logits - logits.max(axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
    require(np.isfinite(probabilities).all() and np.allclose(probabilities.sum(axis=1), 1, atol=1e-8),
            "Invalid softmax probability simplex")
    return probabilities


def prior_probabilities(counts: np.ndarray, pseudocount: float) -> np.ndarray:
    require(counts.ndim == 2 and counts.shape[1] == 3 and pseudocount > 0,
            "Invalid train-prior inputs")
    totals = counts.sum(axis=0).astype(np.float64) + pseudocount
    return totals / totals.sum()


def target_word_probabilities(rows: list[dict], counts: np.ndarray,
                              predict_rows: list[dict], smoothing: float,
                              pseudocount: float) -> np.ndarray:
    prior = prior_probabilities(counts, pseudocount)
    groups: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(3, dtype=np.float64))
    for row, vector in zip(rows, counts):
        groups[row["targetWord"]] += vector
    result = []
    for row in predict_rows:
        values = groups[row["targetWord"]]
        result.append((values + smoothing * prior) / (values.sum() + smoothing))
    return np.asarray(result)


def choose_softmax(x: np.ndarray, counts: np.ndarray, inner_fit: np.ndarray,
                   inner_val: np.ndarray, recipe: dict) -> tuple[float, list[dict]]:
    trials = []
    for alpha in recipe["softmaxL2Candidates"]:
        head, diagnostics = fit_softmax(x[inner_fit], counts[inner_fit], alpha,
                                        recipe["maxOptimizerIterations"])
        metric = probabilistic_metrics(predict_softmax(head, x[inner_val]), counts[inner_val],
                                       recipe["logLossEpsilon"])
        trials.append({"alpha": alpha, **metric, "fit": diagnostics})
    return min(trials, key=lambda row: (row["perRaterLogLoss"], row["alpha"]))["alpha"], trials


def choose_word_smoothing(rows: list[dict], counts: np.ndarray, inner_fit: np.ndarray,
                          inner_val: np.ndarray, recipe: dict) -> tuple[float, list[dict]]:
    trials = []
    for smoothing in recipe["targetWordSmoothingCandidates"]:
        probabilities = target_word_probabilities(
            [rows[i] for i in inner_fit], counts[inner_fit],
            [rows[i] for i in inner_val], smoothing,
            recipe["priorPseudocountPerClass"])
        trials.append({"smoothing": smoothing,
                       **probabilistic_metrics(probabilities, counts[inner_val], recipe["logLossEpsilon"])})
    return min(trials, key=lambda row: (row["perRaterLogLoss"], row["smoothing"]))["smoothing"], trials


def evaluate(rows: list[dict], matrices: dict[str, np.ndarray], counts: np.ndarray,
             recipe: dict) -> tuple[dict, list[dict], dict[str, np.ndarray]]:
    require(len(rows) == 766 and counts.shape == (766, 3) and set(matrices) == set(ENCODERS),
            "Expected paired 766-clip train inputs")
    assignments = outer_speaker_folds({row["speaker"] for row in rows},
                                      recipe["outerFolds"], recipe["outerSeed"])
    names = (*ENCODERS, "trainPrior", "targetWord")
    predictions = {name: np.full((len(rows), 3), np.nan) for name in names}
    fold_heads = {}
    folds = []
    for fold in range(recipe["outerFolds"]):
        outer_train = np.asarray([i for i, row in enumerate(rows) if assignments[row["speaker"]] != fold], dtype=int)
        outer_holdout = np.asarray([i for i, row in enumerate(rows) if assignments[row["speaker"]] == fold], dtype=int)
        train_speakers = {rows[i]["speaker"] for i in outer_train}
        holdout_speakers = {rows[i]["speaker"] for i in outer_holdout}
        require(train_speakers.isdisjoint(holdout_speakers), "Outer speaker overlap")
        inner_speakers = inner_validation_speakers(train_speakers, fold,
                                                  recipe["innerFractionOfOuterTrainSpeakers"],
                                                  recipe["outerSeed"])
        inner_fit = np.asarray([i for i in outer_train if rows[i]["speaker"] not in inner_speakers], dtype=int)
        inner_val = np.asarray([i for i in outer_train if rows[i]["speaker"] in inner_speakers], dtype=int)
        require(len(inner_fit) + len(inner_val) == len(outer_train) and
                inner_speakers.isdisjoint({rows[i]["speaker"] for i in inner_fit}),
                "Inner speaker overlap")
        choices = {}
        fold_predictions = {}
        for kind, x in matrices.items():
            alpha, trials = choose_softmax(x, counts, inner_fit, inner_val, recipe)
            head, diagnostics = fit_softmax(x[outer_train], counts[outer_train], alpha,
                                             recipe["maxOptimizerIterations"])
            fold_predictions[kind] = predict_softmax(head, x[outer_holdout])
            choices[kind] = {"alpha": alpha, "innerTrials": trials, "outerFit": diagnostics}
            prefix = ("wav2vec" if kind == "wav2vec2-base" else "wavlm") + f"_fold{fold}_"
            for field, value in head.items():
                fold_heads[prefix + field] = np.asarray(value)
        smoothing, trials = choose_word_smoothing(rows, counts, inner_fit, inner_val, recipe)
        prior = prior_probabilities(counts[outer_train], recipe["priorPseudocountPerClass"])
        fold_predictions["trainPrior"] = np.tile(prior, (len(outer_holdout), 1))
        fold_predictions["targetWord"] = target_word_probabilities(
            [rows[i] for i in outer_train], counts[outer_train],
            [rows[i] for i in outer_holdout], smoothing,
            recipe["priorPseudocountPerClass"])
        choices["targetWord"] = {"smoothing": smoothing, "innerTrials": trials}
        for name, value in fold_predictions.items():
            predictions[name][outer_holdout] = value
        folds.append({"fold": fold, "holdoutClips": len(outer_holdout),
                      "holdoutSpeakerIds": sorted(holdout_speakers),
                      "outerTrainClips": len(outer_train),
                      "outerTrainSpeakerIds": sorted(train_speakers),
                      "innerFitSpeakerIds": sorted({rows[i]["speaker"] for i in inner_fit}),
                      "innerValidationSpeakerIds": sorted(inner_speakers),
                      "selection": choices,
                      "metrics": {name: probabilistic_metrics(value, counts[outer_holdout],
                                                                recipe["logLossEpsilon"])
                                  for name, value in fold_predictions.items()}})
        print(f"Completed outer fold {fold + 1}/{recipe['outerFolds']}", flush=True)
    require(all(np.isfinite(value).all() for value in predictions.values()),
            "Missing out-of-fold probabilities")
    expected = {name: value @ np.asarray([0.0, 1.0, 2.0]) for name, value in predictions.items()}
    bounds = {name: {"minimumProbability": float(value.min()),
                     "maximumProbability": float(value.max()),
                     "maximumSimplexDeviation": float(np.max(np.abs(value.sum(axis=1) - 1))),
                     "expectedRatingMinimum": float(expected[name].min()),
                     "expectedRatingMaximum": float(expected[name].max()),
                     "expectedRatingsOutsideZeroToTwo": int(np.count_nonzero(
                         (expected[name] < -1e-10) | (expected[name] > 2 + 1e-10)))}
              for name, value in predictions.items()}
    require(all(value["expectedRatingsOutsideZeroToTwo"] == 0 for value in bounds.values()),
            "Probabilistic expected rating outside 0–2")
    oof = [{"id": row["id"], "speaker": row["speaker"],
            "outerFold": assignments[row["speaker"]],
            "fiveRaterCounts": counts[i].tolist(),
            "probabilities": {name: value[i].tolist() for name, value in predictions.items()}}
           for i, row in enumerate(rows)]
    summary = {"folds": folds,
               "pooledOutOfFold": {name: probabilistic_metrics(value, counts, recipe["logLossEpsilon"])
                                     for name, value in predictions.items()},
               "probabilityBounds": bounds,
               "outOfFoldClips": len(rows), "outOfFoldRaterScores": int(counts.sum()),
               "outOfFoldSpeakers": len(assignments),
               "individualRaterScoreCounts": {str(i): int(counts[:, i].sum()) for i in range(3)}}
    return summary, oof, fold_heads


def run(output: Path | None = None, recipe_path: Path = RECIPE) -> dict:
    started = time.perf_counter()
    recipe = load_recipe(recipe_path)
    expected_output = V2_OUTPUT if recipe_path.resolve() == V2_RECIPE.resolve() else OUTPUT
    output = output or expected_output
    require(output.resolve() == expected_output.resolve(), "Rater CV output differs from locked recipe")
    torch.manual_seed(recipe["outerSeed"])
    torch.set_num_threads(recipe["maxCpuMathThreads"])
    rows, matrices, cache_evidence = load_train_features(recipe)
    counts = load_rater_counts(rows, recipe["selectedTrainIdsSha256"])
    fitting_started = time.perf_counter()
    summary, oof, heads = evaluate(rows, matrices, counts, recipe)
    fit_seconds = time.perf_counter() - fitting_started
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "out-of-fold.json", oof)
    np.savez(output / "outer-fold-heads.npz", **heads)
    provenance = {"experiment": recipe["experiment"], "recipeSha256": sha256_file(recipe_path),
                  "sourceArchiveSha256": recipe["sourceArchiveSha256"],
                  "sourceMetadataSha256": recipe["sourceMetadataSha256"],
                  "cacheEvidence": cache_evidence,
                  "authorPartition": "train", "knownAuthorTest": True,
                  "authorTestUsedForSettings": False, **AUTHORITY}
    write_json(output / "provenance.json", provenance)
    fit_diagnostics = [selection[kind][phase]
                       for fold in summary["folds"]
                       for kind in ENCODERS
                       for selection in [fold["selection"]]
                       for phase in ("outerFit",)]
    inner_diagnostics = [trial["fit"]
                         for fold in summary["folds"]
                         for kind in ENCODERS
                         for trial in fold["selection"][kind]["innerTrials"]]
    outer_at_limit = sum(item["atIterationLimit"] for item in fit_diagnostics)
    inner_at_limit = sum(item["atIterationLimit"] for item in inner_diagnostics)
    report = {"experiment": recipe["experiment"], "purpose": recipe["purpose"],
              "recipeSha256": sha256_file(recipe_path),
              "provenanceSha256": sha256_file(output / "provenance.json"),
              "outOfFoldSha256": sha256_file(output / "out-of-fold.json"),
              "outerFoldHeadsSha256": sha256_file(output / "outer-fold-heads.npz"),
              "metricDefinitions": {"logLoss": "Natural-log loss averaged over all five individual scores per clip",
                                    "brier": recipe["brierDefinition"]},
              "classes": recipe["classes"], "selectionMetric": recipe["selectionMetric"],
              "authorPartition": "train", "knownAuthorTest": True,
              "authorTestUsedForSettings": False,
              "nestedFitSeconds": fit_seconds, "elapsedSeconds": time.perf_counter() - started,
              "outerFitsAtIterationLimit": outer_at_limit,
              "outerFitCount": len(fit_diagnostics),
              "innerFitsAtIterationLimit": inner_at_limit,
              "innerFitCount": len(inner_diagnostics),
              "maximumOuterGradientNorm": max(item["gradientNorm"] for item in fit_diagnostics),
              "maximumInnerGradientNorm": max(item["gradientNorm"] for item in inner_diagnostics),
              **summary,
              "interpretation": "Exploratory train-only comparison of predictions for subjective expert ratings; no clinical reliability or model-winner claim.",
              "limitations": ["Five ratings per clip are repeated judgments, not independent patient outcomes or objective produced-phone truth.",
                              "Whole-utterance pooled features do not isolate the /R/ interval.",
                              "Speaker-held-out folds do not prove household, prompt, or recording-condition independence.",
                              "Only the public author-train corpus was evaluated; this is not external validation.",
                              f"{outer_at_limit} of {len(fit_diagnostics)} outer softmax fits reached the predeclared {recipe['maxOptimizerIterations']}-iteration cap; numerical convergence was not established for those fits.",
                              f"{inner_at_limit} of {len(inner_diagnostics)} inner softmax fits reached the same cap; stopping below the cap alone does not prove numerical convergence.",
                              "Probability simplex bounds prevent out-of-range expected ratings but do not establish calibration or feedback suitability."],
              **AUTHORITY}
    if recipe_path.resolve() == V2_RECIPE.resolve():
        reference_path = OUTPUT / "report.json"
        require(sha256_file(reference_path) == V1_REPORT_SHA256,
                "Pinned v1 sensitivity reference report SHA-256 mismatch")
        reference = json.loads(reference_path.read_text())
        selections = []
        for earlier, later in zip(reference["folds"], report["folds"]):
            require(earlier["fold"] == later["fold"] and
                    earlier["holdoutSpeakerIds"] == later["holdoutSpeakerIds"] and
                    earlier["outerTrainSpeakerIds"] == later["outerTrainSpeakerIds"] and
                    earlier["innerFitSpeakerIds"] == later["innerFitSpeakerIds"] and
                    earlier["innerValidationSpeakerIds"] == later["innerValidationSpeakerIds"],
                    "V2 speaker partitions differ from v1")
            selections.append({"fold": later["fold"],
                               "wav2vecAlphaChanged": earlier["selection"]["wav2vec2-base"]["alpha"] !=
                                                      later["selection"]["wav2vec2-base"]["alpha"],
                               "wavlmAlphaChanged": earlier["selection"]["wavlm-base-plus"]["alpha"] !=
                                                    later["selection"]["wavlm-base-plus"]["alpha"],
                               "wordSmoothingChanged": earlier["selection"]["targetWord"]["smoothing"] !=
                                                       later["selection"]["targetWord"]["smoothing"]})
        report["sensitivityToV1"] = {
            "v1ReportSha256": V1_REPORT_SHA256,
            "v1OutOfFoldSha256": reference["outOfFoldSha256"],
            "v1OuterFoldHeadsSha256": reference["outerFoldHeadsSha256"],
            "changedSelectionsByFold": selections,
            "pooledMetricDeltaV2MinusV1": {
                name: {metric: report["pooledOutOfFold"][name][metric] -
                        reference["pooledOutOfFold"][name][metric]
                       for metric in ("perRaterLogLoss", "perRaterBrier")}
                for name in report["pooledOutOfFold"]},
            "v1OuterFitsAtIterationLimit": reference["outerFitsAtIterationLimit"],
            "v2OuterFitsAtIterationLimit": outer_at_limit,
            "v2InnerFitsAtIterationLimit": inner_at_limit}
        report["interpretation"] = ("Numerical-convergence sensitivity on the same author-train folds; "
                                    "not fresh validation or model-winner selection.")
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=("v1", "v2"), default="v1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.output, V2_RECIPE if args.experiment == "v2" else RECIPE)
    print(json.dumps({"pooledOutOfFold": result["pooledOutOfFold"],
                      "outerFitsAtIterationLimit": result["outerFitsAtIterationLimit"]}))
