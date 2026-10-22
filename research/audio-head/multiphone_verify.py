"""Independent inner-matrix integrity checks and descriptive rating diagnostics.

No encoder inference, outer evaluation, or author-test reader runs here. Binary
diagnostics distinguish individual expert ratings, not clinical speech errors.
Five raters remain dependent observations; uncertainty resamples speakers.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = HERE / "outputs/multiphone-20260926"
RECIPE = HERE / "experiments/multiphone-heads-v1.json"
RECIPE_SHA256 = "08a456a102fe2b59ef85a9b8564c246975db214edd2baf74cdc329f12fc60d1d"
SOURCE_SHA256 = {
    "multiphone_train.py": "9d026a37216e6ae7e535b94f7b6fc52744e81a3b29ef94a564364b388ff18970",
    "multiphone_models.py": "0e254f967b4c8dc5c5fe0a3bd2cbae05c62c480b6360cdb1912403271568987a",
    "multiphone_cache.py": "15712352cc03bf03ff94dbd6f39f1e3891be10f91e5c138a01ee11a3ee177e4c",
}
CACHE_SOURCE_SHA256 = {
    "multiphone_cache.py": SOURCE_SHA256["multiphone_cache.py"],
    "encoders.py": "9282b37dcb8ee9b1191caab6ed888ec6d6890aa134767f59a0d9ed1bad245a31",
    "speechocean_r_probe.py": "5df3442033c98c972b19021b3e3d3adae9da34dc2bb38f05559e47591241a198",
}
CACHES = {"wav2vec2-base": "wav2vec-frames", "wavlm-base-plus": "wavlm-frames"}
SHORT = {"wav2vec2-base": "wav2vec", "wavlm-base-plus": "wavlm"}
FIRST_RUN = "inner-wav2vec-mean-f0-s7-lr001"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_recipe(path: Path = RECIPE) -> dict:
    require(digest(path) == RECIPE_SHA256, "Original frozen-head recipe changed")
    return read_json(path)


def weighted_binary_metrics(scores, positive, negative) -> dict:
    """Exact weighted rank AUC and grouped-threshold, noninterpolated AP."""
    scores, positive, negative = [np.asarray(x, dtype=np.float64) for x in (scores, positive, negative)]
    require(scores.ndim == 1 and len(scores) and scores.shape == positive.shape == negative.shape
            and all(np.isfinite(x).all() for x in (scores, positive, negative))
            and (positive >= 0).all() and (negative >= 0).all()
            and (positive + negative).sum() > 0, "Invalid binary rating weights")
    order = np.argsort(scores, kind="stable")
    ranked = scores[order]
    starts = np.r_[0, np.flatnonzero(np.diff(ranked)) + 1]
    pos = np.add.reduceat(positive[order], starts)
    neg = np.add.reduceat(negative[order], starts)
    total_pos, total_neg = float(pos.sum()), float(neg.sum())
    auc = (float(np.sum(pos * (np.cumsum(neg) - neg / 2)) / (total_pos * total_neg))
           if total_pos and total_neg else None)
    descending_pos, descending_neg = pos[::-1], neg[::-1]
    cumulative_pos = np.cumsum(descending_pos)
    cumulative_all = cumulative_pos + np.cumsum(descending_neg)
    precision = np.divide(cumulative_pos, cumulative_all, out=np.zeros_like(cumulative_pos),
                          where=cumulative_all > 0)
    ap = float(np.sum(descending_pos * precision) / total_pos) if total_pos else None
    return {"positiveRaterWeight": total_pos, "negativeRaterWeight": total_neg,
            "prevalence": total_pos / (total_pos + total_neg), "auroc": auc,
            "averagePrecision": ap}


def validate_predictions(probabilities, counts):
    p, c = np.asarray(probabilities, dtype=np.float64), np.asarray(counts, dtype=np.float64)
    require(p.ndim == 2 and p.shape == c.shape and p.shape[1] == 3 and len(p)
            and np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all()
            and np.allclose(p.sum(1), 1, atol=1e-6, rtol=0)
            and np.isfinite(c).all() and (c >= 0).all() and (c == np.floor(c)).all()
            and (c.sum(1) == 5).all(), "Invalid probabilities or five-rater counts")
    return p, c


def discrimination(probabilities, counts, row_weights=None) -> dict:
    p, c = validate_predictions(probabilities, counts)
    weights = np.ones(len(p)) if row_weights is None else np.asarray(row_weights, dtype=np.float64)
    require(weights.shape == (len(p),) and np.isfinite(weights).all() and (weights >= 0).all()
            and weights.sum() > 0, "Invalid row weights")
    c = c * weights[:, None]
    support = c.sum(0)
    predicted = p.argmax(1)
    logarithms = np.log(p.clip(1e-12, 1))
    classes = {}
    for label in range(3):
        classes[str(label)] = {
            "raterWeight": float(support[label]),
            "prevalence": float(support[label] / support.sum()),
            "conditionalNLL": float(-(c[:, label] * logarithms[:, label]).sum() / support[label])
            if support[label] else None,
            "argmaxRecall": float(c[predicted == label, label].sum() / support[label])
            if support[label] else None,
        }
    recalls = [value["argmaxRecall"] for value in classes.values() if value["argmaxRecall"] is not None]
    return {"perRaterLogLoss": float(-(c * logarithms).sum() / c.sum()),
            "classes": classes, "balancedArgmaxRecall": float(np.mean(recalls)),
            "predictedArgmaxPositionWeight": np.bincount(predicted, weights=weights, minlength=3).tolist(),
            "rating0": weighted_binary_metrics(p[:, 0], c[:, 0], c[:, 1] + c[:, 2]),
            "ratingBelow2": weighted_binary_metrics(p[:, 0] + p[:, 1], c[:, 0] + c[:, 1], c[:, 2])}


def scalar_metrics(value: dict) -> dict:
    result = {name: value[name] for name in ("perRaterLogLoss", "balancedArgmaxRecall")}
    for label, row in value["classes"].items():
        for name in ("conditionalNLL", "argmaxRecall", "prevalence"):
            result[f"class{label}.{name}"] = row[name]
    for event in ("rating0", "ratingBelow2"):
        for name in ("auroc", "averagePrecision", "prevalence"):
            result[f"{event}.{name}"] = value[event][name]
    return result


def target_discrimination(probabilities, counts, phones, row_weights=None) -> dict:
    p, c = validate_predictions(probabilities, counts)
    phones = np.asarray(phones)
    require(phones.shape == (len(p),), "Phone labels do not match predictions")
    weights = np.ones(len(p)) if row_weights is None else np.asarray(row_weights, dtype=np.float64)
    require(weights.shape == (len(p),) and np.isfinite(weights).all() and (weights >= 0).all(),
            "Invalid target metric weights")
    per_phone = {}
    for phone in np.unique(phones):
        mask = phones == phone
        per_phone[str(phone)] = discrimination(p[mask], c[mask], weights[mask]) if weights[mask].sum() else None
    macro = {}
    for event in ("rating0", "ratingBelow2"):
        # Require both classes for a discrimination summary. AP is mathematically
        # defined for all-positive samples, but those cannot assess separation.
        usable = {phone: value[event] for phone, value in per_phone.items()
                  if value is not None and value[event]["auroc"] is not None}
        excluded = sorted(set(per_phone) - set(usable))
        macro[event] = {"definedTargets": len(usable), "undefinedTargets": len(excluded),
                        "excludedPhones": excluded,
                        **{metric: float(np.mean([value[metric] for value in usable.values()])) if usable else None
                           for metric in ("auroc", "averagePrecision", "prevalence")}}
    return {"perPhone": per_phone, "macroTarget": macro,
            "macroSupportRule": "Equal phone weight; exclude phones without both positive and negative rater support"}


def macro_scalars(value: dict) -> dict:
    return {f"macroTarget.{event}.{metric}": row[metric]
            for event, row in value["macroTarget"].items()
            for metric in ("auroc", "averagePrecision", "prevalence")}


def clustered_bootstrap(probabilities, counts, speakers, *, replicates=500, seed=20260926,
                        reference=None, phones=None) -> dict:
    p, c = validate_predictions(probabilities, counts)
    require(type(replicates) is int and replicates >= 1 and len(speakers) == len(p),
            "Invalid bootstrap dimensions")
    unique, inverse = np.unique(np.asarray(speakers), return_inverse=True)
    require(len(unique) >= 2, "Speaker bootstrap needs at least two speakers")
    baseline = None if reference is None else validate_predictions(reference, counts)[0]
    samples, deltas = {}, {}
    rng = np.random.default_rng(seed)
    for _ in range(replicates):
        multiplicities = np.bincount(rng.integers(len(unique), size=len(unique)), minlength=len(unique))
        weights = multiplicities[inverse]
        current = scalar_metrics(discrimination(p, c, weights))
        comparator = None if baseline is None else scalar_metrics(discrimination(baseline, c, weights))
        if phones is not None:
            current.update(macro_scalars(target_discrimination(p, c, phones, weights)))
            if comparator is not None:
                comparator.update(macro_scalars(target_discrimination(baseline, c, phones, weights)))
        for key, value in current.items():
            samples.setdefault(key, [])
            if value is not None:
                samples[key].append(value)
            if comparator is not None:
                deltas.setdefault(key, [])
                if value is not None and comparator[key] is not None:
                    deltas[key].append(value - comparator[key])

    def intervals(values):
        return {key: {"validReplicates": len(items),
                      "percentile95": np.quantile(items, [0.025, 0.975]).tolist() if items else None}
                for key, items in values.items()}

    return {"method": "Resample speakers with replacement; retain all their positions and five ratings",
            "interpretation": "Descriptive uncertainty conditional on the selected inner run",
            "speakers": len(unique), "replicates": replicates, "seed": seed,
            "model": intervals(samples), "pairedModelMinusPrior": intervals(deltas) if baseline is not None else None,
            "limitations": "Inner outcomes selected epochs and learning rates. These are not independent generalization or selection-adjusted intervals; no multiplicity correction."}


def matrix_runs(recipe: dict, encoders=None):
    for encoder, head, fold, seed, rate in itertools.product(
            encoders or recipe["encoders"], recipe["heads"], recipe["folds"],
            recipe["initializationSeeds"], recipe["learningRates"]):
        label = {0.001: "001", 0.0003: "0003"}[rate]
        yield {"encoder": encoder, "head": head, "fold": fold, "seed": seed, "lr": rate,
               "name": f"inner-{SHORT[encoder]}-{head}-f{fold}-s{seed}-lr{label}"}


def resolved_path(value: str) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else REPO / path).resolve()


def verify_config(config: dict, expected: dict, recipe: dict, base: Path, cache_sha: str) -> None:
    fields = {key: expected[key] for key in ("head", "fold", "seed", "lr")}
    fields.update({"phase": "inner", "device": "cpu", "hidden": recipe["hiddenWidth"],
                   "dropout": recipe["dropout"], "weight_decay": recipe["weightDecay"],
                   "batch_size": recipe["batchSizeClips"], "epochs": recipe["maximumEpochs"],
                   "patience": recipe["patienceEpochs"], "threads": 4 if expected["name"] == FIRST_RUN else 2,
                   "cohortSha256": recipe["cohortSha256"], "splitsSha256": recipe["splitsSha256"],
                   "cacheIndexSha256": cache_sha, "sourceSha256": SOURCE_SHA256,
                   "authorPartition": "train", "clinicalUseEligible": False, "learnerFeedbackEligible": False})
    require(all(config.get(key) == value for key, value in fields.items()), "Run settings or provenance differ from fixed matrix")
    paths = {"cohort": base / "cohort.json", "splits": base / "splits.json",
             "cache": base / CACHES[expected["encoder"]], "output": base / expected["name"]}
    require(all(resolved_path(config[key]) == path.resolve() for key, path in paths.items()),
            "Run paths differ from matrix inputs")


def verify_history(history: list[dict], report: dict, recipe: dict) -> tuple[int, float]:
    require(history and len(history) == report["epochsRun"] <= recipe["maximumEpochs"], "Invalid epoch count")
    best_epoch, best_loss = 0, math.inf
    for epoch, row in enumerate(history, 1):
        value = row["validation"]["macroTargetLogLoss"]
        require(row["epoch"] == epoch and math.isfinite(value) and value >= 0
                and math.isfinite(row["trainPerRaterLogLoss"]) and row["trainPerRaterLogLoss"] >= 0,
                "Invalid learning curve")
        if value < best_loss - recipe["minimumImprovement"]:
            best_epoch, best_loss = epoch, value
        require(epoch == len(history) or epoch - best_epoch < recipe["patienceEpochs"],
                "Training continued past declared stopping rule")
    require(best_epoch == report["bestEpoch"] and
            (len(history) == recipe["maximumEpochs"] or len(history) - best_epoch == recipe["patienceEpochs"]),
            "Saved epoch or early stopping differs from inner rule")
    require(abs(best_loss - report["evaluation"]["macroTargetLogLoss"]) <= 1e-8,
            "Restored report differs from best inner epoch")
    return best_epoch, best_loss


def checked_checkpoint(run: Path, report: dict) -> dict:
    require(report["configSha256"] == digest(run / "config.json")
            and report["checkpointSha256"] == digest(run / "best.pt"), "Checkpoint or config digest mismatch")
    saved = torch.load(run / "best.pt", map_location="cpu", weights_only=True)
    require(saved["configSha256"] == report["configSha256"]
            and saved["epoch"] == saved["bestEpoch"] == report["bestEpoch"], "Checkpoint linkage mismatch")
    require(all(torch.isfinite(value).all() for value in saved["model"].values())
            and saved["mean"].shape == saved["std"].shape == (768,)
            and torch.isfinite(saved["mean"]).all() and torch.isfinite(saved["std"]).all()
            and (saved["std"] > 0).all(), "Nonfinite model or invalid normalization")
    return saved


def checked_predictions(prediction: dict, selected: list[int], rows: list[dict], evaluation: dict):
    require(prediction["rowIndices"] == sorted(selected) and len(set(selected)) == len(selected),
            "Predictions do not exactly cover the inner validation rows")
    chosen = [rows[i] for i in sorted(selected)]
    require(all(row["trainingEligible"] for row in chosen), "Ineligible target in predictions")
    p, c = validate_predictions(prediction["probabilities"], [row["raterCounts"] for row in chosen])
    require(len(p) == len(selected), "Prediction length mismatch")
    nll = -(c / 5 * np.log(p.clip(1e-12, 1))).sum(1)
    phones = np.asarray([row["targetPhone"] for row in chosen])
    macro = np.mean([nll[phones == phone].mean() for phone in np.unique(phones)])
    require(abs(float(nll.mean()) - evaluation["perRaterLogLoss"]) <= 1e-8
            and abs(float(macro) - evaluation["macroTargetLogLoss"]) <= 1e-8,
            "Saved predictions do not reproduce reported proper scores")
    return p, c, chosen


def checked_cache(base: Path, kind: str, recipe: dict, cohort: dict) -> str:
    from encoders import Wav2VecEncoder, WavLMEncoder
    directory = base / CACHES[kind]
    config, index = read_json(directory / "config.json"), read_json(directory / "index.json")
    identity = {"wav2vec2-base": Wav2VecEncoder.identity, "wavlm-base-plus": WavLMEncoder.identity}[kind]
    require(index.get("complete") is True and index["configSha256"] == digest(directory / "config.json")
            and config["cohortSha256"] == recipe["cohortSha256"] and config["encoder"] == identity
            and config["sourceSha256"] == CACHE_SOURCE_SHA256 and config["dtype"] == "float32"
            and config["device"] == ("cpu" if kind == "wav2vec2-base" else "mps")
            and config["authorPartition"] == "train", "Cache identity or provenance differs")
    require(index["clipCount"] == len(cohort["clips"]) == len(index["entries"]), "Incomplete cache index")
    for clip in cohort["clips"]:
        entry = index["entries"][clip["id"]]
        require(entry["path"] == clip["id"] + ".npz" and entry["audioSha256"] == clip["audioSha256"]
                and type(entry["frames"]) is int and 0 < entry["frames"] <= 1500,
                "Cache index clip binding differs")
    return digest(directory / "index.json")


def supplied_prior(directory: Path, fold_number: int, cohort: dict, splits: dict, recipe: dict):
    """Validate an existing inner-fit prior, never fit a new model or read outer results."""
    location = directory / f"fold-{fold_number}-inner"
    config, selection = read_json(location / "config.json"), read_json(location / "selection.json")
    fold = splits["folds"][fold_number]
    require(config["phase"] == "inner" and config["fold"] == fold_number
            and config["binding"]["cohortSha256"] == recipe["cohortSha256"]
            and config["binding"]["splitsSha256"] == recipe["splitsSha256"]
            and config["fitRows"] == fold["innerFitRows"]
            and config["validationRows"] == fold["innerValidationRows"]
            and selection["configSha256"] == digest(location / "config.json")
            and selection["outerOutcomesUsed"] is False, "Prior is not bound to these inner partitions")
    choice = selection["selected"]["prior"]
    state_path = (location / choice["statePath"]).resolve()
    require(state_path.is_relative_to(location.resolve()) and digest(state_path) == choice["stateSha256"],
            "Prior state digest/path differs")
    state = read_json(state_path)
    require(state["family"] == "prior" and state["priorPseudocountPerClass"] == 1.0,
            "Expected the supplied phone-only prior")
    totals = {}
    for index in fold["innerFitRows"]:
        row = cohort["rows"][index]
        totals.setdefault(row["targetPhone"], np.ones(3))
        totals[row["targetPhone"]] += np.asarray(row["raterCounts"])
    require(set(totals) == set(state["phonePriors"]) and all(
        np.allclose(state["phonePriors"][phone], count / count.sum(), atol=1e-12, rtol=0)
        for phone, count in totals.items()), "Supplied prior is not the declared inner-fit count model")
    predictions = np.asarray([state["phonePriors"][cohort["rows"][i]["targetPhone"]]
                              for i in sorted(fold["innerValidationRows"])])
    return predictions, {"configSha256": digest(location / "config.json"),
                         "stateSha256": digest(state_path), "selectionSha256": digest(location / "selection.json")}


def verify_matrix(*, base: Path = BASE, encoders=None, allow_incomplete=False,
                  controls: Path | None = None, replicates=500, seed=20260926,
                  run_names=None, verify_only=False) -> dict:
    recipe = load_recipe()
    chosen_encoders = encoders or recipe["encoders"]
    require(chosen_encoders and set(chosen_encoders) <= set(recipe["encoders"])
            and len(set(chosen_encoders)) == len(chosen_encoders), "Unknown or duplicate encoder")
    all_sources = {**SOURCE_SHA256, **CACHE_SOURCE_SHA256}
    require(all(digest(HERE / name) == value for name, value in all_sources.items()), "Frozen sources changed")
    require(digest(base / "cohort.json") == recipe["cohortSha256"]
            and digest(base / "splits.json") == recipe["splitsSha256"], "Matrix data or split changed")
    cohort, splits = read_json(base / "cohort.json"), read_json(base / "splits.json")
    require(splits["cohortCanonicalSha256"] == canonical_hash(cohort), "Split canonical binding differs")
    expected_runs = list(matrix_runs(recipe, chosen_encoders))
    if run_names is not None:
        require(run_names and len(set(run_names)) == len(run_names)
                and set(run_names) <= {row["name"] for row in expected_runs}, "Unknown or duplicate requested run")
        expected_runs = [row for row in expected_runs if row["name"] in set(run_names)]
    results, missing, cache_pins, priors = [], [], {}, {}
    for expected in expected_runs:
        run = base / expected["name"]
        if not (run / "report.json").is_file():
            missing.append(run.name)
            continue
        artifact_pins = {name: digest(run / name) for name in
                         ("config.json", "best.pt", "report.json", "predictions.json", "history.jsonl")}
        kind = expected["encoder"]
        if kind not in cache_pins:
            cache_pins[kind] = checked_cache(base, kind, recipe, cohort)
        config, report = read_json(run / "config.json"), read_json(run / "report.json")
        verify_config(config, expected, recipe, base, cache_pins[kind])
        require(report["evaluationRole"] == "inner selection" and report["clinicalUseEligible"] is False
                and report["learnerFeedbackEligible"] is False, "Wrong evaluation scope")
        history = [json.loads(line) for line in (run / "history.jsonl").read_text().splitlines()]
        best_epoch, best_loss = verify_history(history, report, recipe)
        saved = checked_checkpoint(run, report)
        require(abs(saved["bestLoss"] - best_loss) <= 1e-8, "Checkpoint best loss differs")
        from multiphone_models import MeanPoolPhoneRatingHead, AttentionPhoneRatingHead
        model_class = {"mean": MeanPoolPhoneRatingHead, "attention": AttentionPhoneRatingHead}[expected["head"]]
        model_class(hidden_dim=config["hidden"], dropout=config["dropout"]).load_state_dict(saved["model"], strict=True)
        fold = splits["folds"][expected["fold"]]
        p, c, rows = checked_predictions(read_json(run / "predictions.json"), fold["innerValidationRows"],
                                         cohort["rows"], report["evaluation"])
        reference, prior_evidence = None, None
        if controls is not None and not verify_only:
            if expected["fold"] not in priors:
                priors[expected["fold"]] = supplied_prior(controls, expected["fold"], cohort, splits, recipe)
            reference, prior_evidence = priors[expected["fold"]]
        result = {**expected, "bestEpoch": best_epoch, "selectionMacroTargetLogLoss": best_loss,
                  "artifactsSha256": artifact_pins}
        if not verify_only:
            phones = np.asarray([row["targetPhone"] for row in rows])
            result.update({"descriptive": discrimination(p, c), **target_discrimination(p, c, phones),
                           "speakerBootstrap": clustered_bootstrap(p, c, [row["speakerId"] for row in rows],
                                                                    replicates=replicates, seed=seed + expected["fold"],
                                                                    reference=reference, phones=phones),
                           "phonePrior": None if reference is None else {
                               "evidence": prior_evidence, "descriptive": discrimination(reference, c),
                               **target_discrimination(reference, c, phones)}})
        require(all(digest(run / name) == pin for name, pin in artifact_pins.items()),
                "Run artifacts changed while verifying")
        results.append(result)
    require(allow_incomplete or not missing, f"Matrix incomplete: {len(missing)} expected runs missing")
    require(digest(RECIPE) == RECIPE_SHA256 and all(digest(HERE / name) == value for name, value in all_sources.items()),
            "Recipe or source changed while verifying")
    require(all(digest(base / CACHES[kind] / "index.json") == pin for kind, pin in cache_pins.items()),
            "Cache index changed while verifying")
    require(digest(base / "cohort.json") == recipe["cohortSha256"]
            and digest(base / "splits.json") == recipe["splitsSha256"], "Study changed while verifying")
    return {"schemaVersion": 1, "scope": "Saved author-train INNER validation only",
            "verifierSha256": digest(Path(__file__)), "numpyVersion": np.__version__, "torchVersion": torch.__version__,
            "recipeSha256": RECIPE_SHA256, "sourceSha256": all_sources, "cacheIndexSha256": cache_pins,
            "verifiedRuns": len(results), "expectedRuns": len(expected_runs),
            "completeForRequestedScope": not missing, "requestedEncoders": chosen_encoders,
            "wholeMatrixVerified": len(results) == len(list(matrix_runs(recipe))),
            "requestedRunNames": run_names, "verificationOnly": verify_only,
            "missingRuns": missing, "runs": results,
            "threadException": f"{FIRST_RUN}: four CPU threads; other frozen-head matrix runs: two",
            "selectionUnchanged": True, "checkpointInferenceReplayed": False, "featureFilesRehashed": False,
            "authorTestInferencePerformed": False, "outerOutcomesUsed": False,
            "clinicalUseEligible": False, "learnerFeedbackEligible": False,
            "limitations": ["Rating discrimination is not clinical pronunciation-error detection.",
                            "Inner results include selection optimism; exploratory bootstrap intervals do not correct it.",
                            "Per-phone estimates have variable support; a missing rating class yields null discrimination.",
                            "Artifact, shape, and saved-score checks do not independently replay every checkpoint."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--encoder", action="append", choices=list(CACHES))
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--run", action="append", help="Exact completed inner run name; repeat to select runs")
    parser.add_argument("--verify-only", action="store_true", help="Integrity/proper-score checks only; skip discrimination/bootstrap")
    parser.add_argument("--controls", type=Path)
    parser.add_argument("--bootstrap-replicates", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260926)
    args = parser.parse_args()
    torch.set_num_threads(2)
    result = verify_matrix(encoders=args.encoder, allow_incomplete=args.allow_incomplete,
                           controls=args.controls, replicates=args.bootstrap_replicates, seed=args.seed,
                           run_names=args.run, verify_only=args.verify_only)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("verifiedRuns", "expectedRuns", "completeForRequestedScope")}))
