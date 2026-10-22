"""Fresh global WavLM mean refits, with a separate development holdout read.

Only the two same-fold, seed-seven inner candidates select LR and epoch.
The orchestrator freezes the complete release manifest before `evaluate`.
These subjective-rating predictions are research, not pronunciation judgments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

import multiphone_child_train as child
import multiphone_train as trainer
import multiphone_verify as verify
from multiphone_cache import atomic_json, digest

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "experiments/multiphone-heads-v1.json"
PROTOCOL = HERE.parents[1] / "docs/model/multiphone-outer-evaluation-protocol.md"
SOURCES = sorted(set(child.SOURCES + ("multiphone_global_outer.py", "speechocean_r_probe.py")))
ARTIFACTS = ("config.json", "report.json", "best.pt", "predictions.json", "history.jsonl", "status.json")
require, read_json = verify.require, verify.read_json


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCES}


def pins(paths):
    return {str(path.resolve()): digest(path) for path in paths}


def guard(sources, artifacts):
    require(source_hashes() == sources and all(digest(Path(path)) == sha for path, sha in artifacts.items()),
            "Pinned source or artifact changed")


def fresh(path):
    require(path.resolve().is_relative_to((HERE / "outputs").resolve()) and not path.exists(),
            "Choose a fresh directory inside ignored research outputs")
    path.mkdir(parents=True, mode=0o700)


def original_args(config):
    args = argparse.Namespace(**config)
    for name in ("cohort", "splits", "cache", "output"):
        setattr(args, name, Path(config[name]))
    return args


def load_inputs(args, recipe):
    cohort, splits = read_json(args.cohort), read_json(args.splits)
    require(digest(args.cohort) == recipe["cohortSha256"]
            and digest(args.splits) == recipe["splitsSha256"]
            and splits["cohortCanonicalSha256"] == verify.canonical_hash(cohort),
            "Cohort or speaker split binding differs")
    require(type(args.fold) is int and args.fold in range(5), "Use a declared fold")
    fold = splits["folds"][args.fold]
    trainer.verify_partitions(cohort, fold)
    return cohort, fold


def cache_files(args, cohort, indices):
    index = read_json(args.cache / "index.json")
    result = {}
    for clip_id in sorted({cohort["rows"][i]["clipIndex"] for i in indices}):
        entry = index["entries"][cohort["clips"][clip_id]["id"]]
        path = (args.cache / entry["path"]).resolve()
        require(path.is_relative_to(args.cache.resolve()), "Cache path escapes its directory")
        result[str(path)] = entry["sha256"]
    return result


def checked_candidates(candidates):
    require(len(candidates) == 2 and len({path.resolve() for path in candidates}) == 2,
            "Exactly two distinct inner learning-rate candidates are required")
    recipe = verify.load_recipe(RECIPE)
    artifacts = pins([RECIPE, PROTOCOL] + [path / name for path in candidates for name in ARTIFACTS])
    trials, common, shared = [], None, None
    for directory in candidates:
        config, report = read_json(directory / "config.json"), read_json(directory / "report.json")
        args = original_args(config)
        require(args.head == "mean" and args.seed == 7 and args.device == "cpu"
                and Path(config["output"]).resolve() == directory.resolve(), "Use seed-seven global mean CPU candidates")
        cohort, fold = load_inputs(args, recipe)
        if common is None:
            artifacts.update(pins([args.cohort, args.splits, args.cache / "config.json", args.cache / "index.json"]))
            artifacts.update(cache_files(args, cohort, fold["outerFitRows"]))
        base = args.cohort.parent
        cache_sha = verify.checked_cache(base, "wavlm-base-plus", recipe, cohort)
        expected = {"encoder": "wavlm-base-plus", "head": "mean", "fold": args.fold, "seed": 7,
                    "lr": args.lr, "name": f"inner-wavlm-mean-f{args.fold}-s7-lr" + {0.001: "001", 0.0003: "0003"}.get(args.lr, "invalid")}
        verify.verify_config(config, expected, recipe, base, cache_sha)
        require(args.lr in recipe["learningRates"] and report["evaluationRole"] == "inner selection",
                "Candidate is not part of the fixed inner comparison")
        signature = {key: config[key] for key in config if key not in ("lr", "output")}
        require(common is None or signature == common, "Candidates differ beyond learning rate")
        common = signature
        history = [json.loads(line) for line in (directory / "history.jsonl").read_text().splitlines()]
        epoch, loss = verify.verify_history(history, report, recipe)
        status = read_json(directory / "status.json")
        require(status["complete"] is True and status["bestEpoch"] == epoch
                and status["epochsRun"] == len(history), "Inner candidate is not complete")
        saved = verify.checked_checkpoint(directory, report)
        require(saved["bestLoss"] == loss and history[epoch - 1]["validation"] == report["evaluation"],
                "Checkpoint loss or selected history differs")
        if shared is None:
            data = trainer.StudyData(cohort, args.cache, fold["innerFitRows"] + fold["innerValidationRows"])
            mean, std = data.normalization(sorted({cohort["rows"][i]["clipIndex"] for i in fold["innerFitRows"]}))
            shared = data, mean, std
        data, mean, std = shared
        require(torch.equal(mean, saved["mean"]) and torch.equal(std, saved["std"]),
                "Inner normalization differs from fit-only frames")
        torch.set_num_threads(args.threads)
        model = trainer.HEADS["mean"](hidden_dim=args.hidden, dropout=args.dropout)
        model.load_state_dict(saved["model"], strict=True)
        metrics, replay = trainer.evaluate(model, data, fold["innerValidationRows"], mean, std, "cpu", args.batch_size)
        require(replay == read_json(directory / "predictions.json") and metrics == report["evaluation"],
                "Inner checkpoint does not exactly replay predictions and metrics")
        trials.append({"directory": str(directory.resolve()), "lr": args.lr, "epochs": epoch, "loss": loss})
    require({trial["lr"] for trial in trials} == set(recipe["learningRates"]), "Both inner learning rates are required")
    selected = min(trials, key=lambda trial: (trial["loss"], trial["lr"], trial["epochs"]))
    args = original_args(read_json(Path(selected["directory"]) / "config.json"))
    return selected, trials, artifacts, args, recipe


def outer_data(args, recipe, include_holdout=False):
    cohort, fold = load_inputs(args, recipe)
    fit = fold["outerFitRows"]
    data = trainer.StudyData(cohort, args.cache, fit + (fold["outerHoldoutRows"] if include_holdout else []))
    mean, std = data.normalization(sorted({cohort["rows"][i]["clipIndex"] for i in fit}))
    prior = child.fit_priors([cohort["rows"][i] for i in fit])
    return data, fold, mean, std, prior


def fit_epochs(args, data, fit, mean, std, epochs, on_epoch):
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    model = trainer.HEADS["mean"](hidden_dim=args.hidden, dropout=args.dropout)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    fit_clips = sorted({data.rows[i]["clipIndex"] for i in fit})
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        order = generator.permutation(fit_clips).tolist()
        loss_sum, count = 0., 0
        for offset in range(0, len(order), args.batch_size):
            values, frame_mask, phones, mask, targets, _ = data.batch(order[offset:offset + args.batch_size], set(fit), mean, std, "cpu")
            optimizer.zero_grad(set_to_none=True)
            losses = -(targets * model(values, frame_mask, phones, mask).log_softmax(-1)).sum(-1)[mask]
            require(bool(torch.isfinite(losses).all()), "Nonfinite refit loss")
            losses.mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(losses.detach().sum())
            count += len(losses)
        history.append({"epoch": epoch, "trainPerRaterLogLoss": loss_sum / count})
        on_epoch(history)
    return model, history


def run_refit(args):
    sources = source_hashes()
    selected, trials, artifacts, original, recipe = checked_candidates(args.candidates)
    data, fold, mean, std, prior = outer_data(original, recipe)
    inputs = pins([original.cohort, original.splits, original.cache / "config.json", original.cache / "index.json"])
    inputs.update(cache_files(original, data.cohort, fold["outerFitRows"]))
    all_pins = {**artifacts, **inputs}
    guard(sources, all_pins)
    fresh(args.output)
    config = {"phase": "outer-refit", "encoder": "wavlm-base-plus", "head": "mean", "seed": 7,
              "fold": original.fold, "selected": selected, "trials": trials, "fixedEpochs": selected["epochs"],
              "learningRate": selected["lr"], "fitRows": fold["outerFitRows"], "evaluationRows": sorted(fold["outerHoldoutRows"]),
              "priorState": prior, "sourceSha256": sources, "innerArtifactsSha256": artifacts,
              "inputArtifactsSha256": inputs, "innerConfigPath": str(Path(selected["directory"]) / "config.json"),
              "recipeSha256": digest(RECIPE), "protocolSha256": digest(PROTOCOL),
              "torchVersion": str(torch.__version__), "numpyVersion": np.__version__,
              "selectionRule": "same-fold inner macro-phone NLL; exact ties lower LR then earlier epoch",
              "epochRule": "fresh seed-seven initialization and optimizer; selected inner best epoch count",
              "outerOutcomesUsed": False, "authorTestInferencePerformed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False}
    atomic_json(args.output / "config.json", config)
    all_pins.update(pins([args.output / "config.json"]))
    started = time.perf_counter()

    def progress(history):
        guard(sources, all_pins)
        atomic_json(args.output / "history.json", history)
        atomic_json(args.output / "status.json", {"complete": False, "epoch": len(history),
                    "fixedEpochs": selected["epochs"], "holdoutPredictionsComputed": False})

    model, history = fit_epochs(original, data, fold["outerFitRows"], mean, std, selected["epochs"], progress)
    trainer.save_checkpoint(args.output / "checkpoint.pt", {"model": model.state_dict(), "mean": mean, "std": std,
                            "epoch": selected["epochs"], "configSha256": digest(args.output / "config.json")})
    saved = torch.load(args.output / "checkpoint.pt", map_location="cpu", weights_only=True)
    require(all(torch.equal(saved["model"][key], value) for key, value in model.state_dict().items()),
            "Serialized refit state differs")
    frozen = {"complete": True, "configSha256": digest(args.output / "config.json"),
              "checkpointSha256": digest(args.output / "checkpoint.pt"), "historySha256": digest(args.output / "history.json"),
              "epochsRun": len(history), "elapsedSeconds": time.perf_counter() - started,
              "outerOutcomesUsed": False, "holdoutPredictionsComputed": False}
    guard(sources, all_pins)
    atomic_json(args.output / "frozen.json", frozen)
    atomic_json(args.output / "status.json", frozen)
    return frozen


def run_evaluate(args):
    frozen_pins = pins([args.input / name for name in ("config.json", "frozen.json", "checkpoint.pt", "history.json")])
    config, frozen = read_json(args.input / "config.json"), read_json(args.input / "frozen.json")
    require(config["phase"] == "outer-refit" and frozen["complete"] is True
            and config["outerOutcomesUsed"] is frozen["outerOutcomesUsed"] is frozen["holdoutPredictionsComputed"] is False
            and frozen["configSha256"] == digest(args.input / "config.json")
            and frozen["checkpointSha256"] == digest(args.input / "checkpoint.pt")
            and frozen["historySha256"] == digest(args.input / "history.json"), "Frozen refit binding differs")
    all_pins = {**config["innerArtifactsSha256"], **config["inputArtifactsSha256"], **frozen_pins}
    guard(config["sourceSha256"], all_pins)
    recipe = verify.load_recipe(RECIPE)
    original = original_args(read_json(Path(config["innerConfigPath"])))
    require(config["encoder"] == "wavlm-base-plus" and config["head"] == original.head == "mean"
            and config["seed"] == original.seed == 7 and config["fold"] == original.fold
            and config["learningRate"] == config["selected"]["lr"] == original.lr
            and config["recipeSha256"] == digest(RECIPE) and config["protocolSha256"] == digest(PROTOCOL),
            "Frozen settings differ")
    torch.set_num_threads(original.threads)
    data, fold, mean, std, prior = outer_data(original, recipe, include_holdout=True)
    all_pins.update(cache_files(original, data.cohort, fold["outerHoldoutRows"]))
    history = read_json(args.input / "history.json")
    require(config["fitRows"] == fold["outerFitRows"] and config["evaluationRows"] == sorted(fold["outerHoldoutRows"])
            and config["priorState"] == prior and config["fixedEpochs"] == config["selected"]["epochs"] == frozen["epochsRun"] == len(history)
            and all(row["epoch"] == i and np.isfinite(row["trainPerRaterLogLoss"]) and row["trainPerRaterLogLoss"] >= 0
                    and set(row) == {"epoch", "trainPerRaterLogLoss"} for i, row in enumerate(history, 1)),
            "Frozen fit rows, prior or fixed training history differs")
    saved = torch.load(args.input / "checkpoint.pt", map_location="cpu", weights_only=True)
    require(saved["configSha256"] == frozen["configSha256"] and saved["epoch"] == config["fixedEpochs"]
            and torch.equal(mean, saved["mean"]) and torch.equal(std, saved["std"]), "Frozen checkpoint moments or epoch differ")
    model = trainer.HEADS["mean"](hidden_dim=original.hidden, dropout=original.dropout)
    model.load_state_dict(saved["model"], strict=True)
    guard(config["sourceSha256"], all_pins)
    fresh(args.output)
    _, predictions = trainer.evaluate(model, data, fold["outerHoldoutRows"], mean, std, "cpu", original.batch_size)
    require(predictions["rowIndices"] == config["evaluationRows"], "Holdout row coverage differs")
    rows = [data.rows[i] for i in predictions["rowIndices"]]
    probabilities = np.asarray(predictions["probabilities"])
    prior_p = np.asarray([prior[row["targetPhone"]]["probabilities"] for row in rows])
    atomic_json(args.output / "predictions.json", predictions)
    atomic_json(args.output / "prior.json", {"rowIndices": predictions["rowIndices"], "probabilities": prior_p.tolist(),
                "evaluation": child.score_predictions(prior_p, rows)})
    report = {"complete": True, "phase": "outer-evaluation", "encoder": "wavlm-base-plus", "head": "mean", "seed": 7,
              "fold": config["fold"], "evaluationRows": predictions["rowIndices"], "evaluation": child.score_predictions(probabilities, rows),
              "frozenArtifactsSha256": frozen_pins, "sourceSha256": config["sourceSha256"],
              "predictionsSha256": digest(args.output / "predictions.json"), "priorSha256": digest(args.output / "prior.json"),
              "interpretation": "Speaker-disjoint development cross-fit; architecture choices used overlapping inner outcomes",
              "outerOutcomesUsedForSelection": False, "authorTestInferencePerformed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False}
    guard(config["sourceSha256"], all_pins)
    atomic_json(args.output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="phase", required=True)
    refit = commands.add_parser("refit")
    refit.add_argument("--candidates", type=Path, nargs=2, required=True)
    refit.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--input", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = (run_refit if args.phase == "refit" else run_evaluate)(args)
    print(f"{args.phase}: complete={result['complete']}; {args.output}")
