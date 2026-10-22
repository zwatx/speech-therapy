"""Refit fixed local/phonetic heads before a separate development holdout read.

The two learning-rate candidates are selected only on their original inner
speakers. A new model is then trained on outer-fit speakers for exactly the
selected epoch count. No outer prediction is computed until `evaluate`.
These cross-fit results remain development evidence: shared research choices
were informed by overlapping inner folds, not a pristine external cohort.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import random
import time

import numpy as np
import torch

import multiphone_local_head as local
import multiphone_phonetic_head as phonetic
from multiphone_cache import atomic_json, digest
from multiphone_child_train import fit_priors, is_child, score_predictions
from multiphone_local_train import read_json, require
from multiphone_train import save_checkpoint

HERE = Path(__file__).resolve().parent
TRAINERS = {"local": local, "phonetic": phonetic}
ARTIFACTS = ("config.json", "report.json", "best.pt", "predictions.json", "history.json", "prior.json")
SOURCES = sorted(set(local.SOURCES + phonetic.SOURCES + ("multiphone_head_outer.py",)))


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCES}


def fresh(path):
    require(path.resolve().is_relative_to((HERE / "outputs").resolve()) and not path.exists(),
            "Choose a fresh directory inside ignored research outputs")
    path.mkdir(parents=True, mode=0o700)


def original_args(config):
    args = argparse.Namespace(**config)
    for key in ("cohort", "splits", "features", "output", "binding"):
        if isinstance(getattr(args, key, None), str):
            setattr(args, key, Path(getattr(args, key)))
    return args


def verified_epoch(config, report, history):
    """Reconstruct the exact declared stopping rule, including first-best ties."""
    require(0 < len(history) <= config["epochs"] and report["epochsRun"] == len(history),
            "Inner training history length differs")
    best, best_epoch = float("inf"), 0
    for epoch, item in enumerate(history, 1):
        require(item["epoch"] == epoch and (epoch == 1 or epoch - 1 - best_epoch < config["patience"]),
                "Inner training continued beyond its stopping rule")
        value = local.selection_loss(item["evaluation"], config["regime"])
        require(np.isfinite(value) and value == item["selectionMacroTargetLogLoss"],
                "Inner history selection metric differs")
        if value < best - 1e-7:
            best, best_epoch = value, epoch
    require(best_epoch == report["bestEpoch"] and best == report["bestSelectionMacroLogLoss"]
            and history[best_epoch - 1]["evaluation"] == report["evaluation"]
            and (len(history) == config["epochs"] or len(history) - best_epoch >= config["patience"]),
            "Selected epoch or completed stopping rule differs")
    return best_epoch


def checked_candidates(kind, candidates):
    require(kind in TRAINERS and len(candidates) == 2 and len({p.resolve() for p in candidates}) == 2,
            "Exactly two distinct learning-rate candidates are required")
    trainer = TRAINERS[kind]
    trials, artifacts, common = [], {str(trainer.RECIPE.resolve()): digest(trainer.RECIPE)}, None
    for directory in candidates:
        config, report = read_json(directory / "config.json"), read_json(directory / "report.json")
        require(config["phase"] == "inner" and config["device"] == "cpu" and config["seed"] == 7
                and config["outerOutcomesUsed"] is False and config["authorTestInferencePerformed"] is False,
                "Candidate scope is not the declared inner CPU study")
        # A saved prediction file alone cannot establish the selection score.
        trainer.replay(directory)
        args = original_args(config)
        data = trainer.setup(args)
        signature = {key: config[key] for key in
                     ("family", "regime", "fold", "seed", "hidden", "dropout", "weight_decay",
                      "batch_size", "epochs", "patience", "threads", "recipeSha256", "sourceSha256",
                      "fitRows", "validationRows", "selectionRows", "featureWidth", "featureColumns")}
        signature["inputIdentity"] = config["binding"] if kind == "local" else config["inputFiles"]
        require(common is None or signature == common, "Candidates do not belong to the same inner comparison")
        common = signature
        epochs = verified_epoch(config, report, read_json(directory / "history.json"))
        trials.append({"directory": str(directory.resolve()), "lr": config["lr"], "epochs": epochs,
                       "loss": report["bestSelectionMacroLogLoss"]})
        artifacts.update({str((directory / name).resolve()): digest(directory / name) for name in ARTIFACTS})
    require({trial["lr"] for trial in trials} == set(read_json(trainer.RECIPE)["learningRates"]),
            "The full declared learning-rate comparison is required")
    selected = min(trials, key=lambda trial: (trial["loss"], trial["lr"], trial["epochs"]))
    config = read_json(Path(selected["directory"]) / "config.json")
    args = original_args(config)
    return selected, trials, artifacts, args, trainer.setup(args)


def outer_data(kind, args, data):
    splits = read_json(args.splits) if kind == "local" else data["splits"]
    fold = splits["folds"][args.fold]
    outer_fit, held = fold["outerFitRows"], fold["outerHoldoutRows"]
    rows = data["cohort"]["rows"]
    require(len(outer_fit) == len(set(outer_fit)) and len(held) == len(set(held))
            and not set(outer_fit) & set(held)
            and not {rows[i]["speakerId"] for i in outer_fit} & {rows[i]["speakerId"] for i in held}
            and set(fold["innerFitRows"]) | set(fold["innerValidationRows"]) == set(outer_fit),
            "Outer speaker partition or inner nesting differs")
    fit = [i for i in outer_fit if args.regime == "all-age" or is_child(rows[i])]
    require(fit and held, "Outer fit and holdout rows are required")
    values = np.asarray(data["values"][[data["positions"][i] for i in fit]], dtype=np.float64)
    mean, std = values.mean(0), values.std(0)
    std = np.where(std < 1e-6, 1., std)
    require(np.isfinite(mean).all() and np.isfinite(std).all(), "Invalid outer-fit moments")
    return {**data, "fit": fit, "holdout": held,
            "mean": torch.tensor(mean, dtype=torch.float32), "std": torch.tensor(std, dtype=torch.float32),
            "priors": fit_priors([rows[i] for i in fit])}


def guard(sources, artifacts):
    require(source_hashes() == sources and all(digest(Path(path)) == sha for path, sha in artifacts.items()),
            "Pinned source or inner artifacts changed")


def input_guard(kind, data):
    if kind == "local":
        local.binding_guard(data["binding"])
    else:
        phonetic.extraction.guard(data["bindings"])


def fit_epochs(args, data, epochs, on_epoch=None):
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    model = local.make_model(args, data["values"].shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        order = generator.permutation(data["fit"]).tolist()
        loss_sum = 0.
        for offset in range(0, len(order), args.batch_size):
            values, phones, mask, targets = local.batch(data, order[offset:offset + args.batch_size], "cpu")
            optimizer.zero_grad(set_to_none=True)
            losses = -(targets * model(values, mask, phones, mask)[:, 0].log_softmax(-1)).sum(-1)
            require(bool(torch.isfinite(losses).all()), "Nonfinite refit loss")
            losses.mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(losses.detach().sum())
        history.append({"epoch": epoch, "trainPerRaterLogLoss": loss_sum / len(order)})
        if on_epoch:
            on_epoch(history)
    return model, history


def run_refit(args):
    sources = source_hashes()
    selected, trials, artifacts, original, data = checked_candidates(args.kind, args.candidates)
    torch.set_num_threads(original.threads)
    data = outer_data(args.kind, original, data)
    config = {"phase": "outer-refit", "kind": args.kind, "selected": selected, "trials": trials,
              "innerArtifactsSha256": artifacts, "sourceSha256": sources,
              "family": original.family, "regime": original.regime, "fold": original.fold,
              "seed": original.seed, "fitRows": data["fit"], "priorState": data["priors"],
              "fixedEpochs": selected["epochs"], "learningRate": selected["lr"],
              "selectionRule": "same-family/regime/fold/seed inner macro-phone NLL; ties lower LR then earlier epoch",
              "epochRule": "refit from initialization for selected inner best epoch count",
              "innerConfigPath": str(Path(selected["directory"]) / "config.json"),
              "inputBinding": data["binding"] if args.kind == "local" else data["bindings"],
              "outerOutcomesUsed": False, "authorTestInferencePerformed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False}
    guard(sources, artifacts)
    input_guard(args.kind, data)
    fresh(args.output)
    atomic_json(args.output / "config.json", config)
    started = time.perf_counter()

    def progress(history):
        guard(sources, artifacts)
        atomic_json(args.output / "history.json", history)
        atomic_json(args.output / "status.json", {"complete": False, "epoch": len(history),
                    "fixedEpochs": selected["epochs"], "holdoutPredictionsComputed": False})

    model, history = fit_epochs(original, data, selected["epochs"], progress)
    save_checkpoint(args.output / "checkpoint.pt", {"model": model.state_dict(), "mean": data["mean"],
                    "std": data["std"], "epoch": selected["epochs"], "configSha256": digest(args.output / "config.json")})
    frozen = {"complete": True, "configSha256": digest(args.output / "config.json"),
              "checkpointSha256": digest(args.output / "checkpoint.pt"),
              "historySha256": digest(args.output / "history.json"),
              "epochsRun": len(history), "elapsedSeconds": time.perf_counter() - started,
              "outerOutcomesUsed": False, "holdoutPredictionsComputed": False}
    guard(sources, artifacts)
    input_guard(args.kind, data)
    atomic_json(args.output / "frozen.json", frozen)
    atomic_json(args.output / "status.json", frozen)
    return frozen


def run_evaluate(args):
    frozen_artifacts = {str((args.input / name).resolve()): digest(args.input / name)
                        for name in ("config.json", "frozen.json", "checkpoint.pt", "history.json")}
    config, frozen = read_json(args.input / "config.json"), read_json(args.input / "frozen.json")
    require(config["phase"] == "outer-refit" and frozen["complete"] is True
            and config["outerOutcomesUsed"] is False and frozen["outerOutcomesUsed"] is False
            and frozen["holdoutPredictionsComputed"] is False
            and frozen["configSha256"] == digest(args.input / "config.json")
            and frozen["checkpointSha256"] == digest(args.input / "checkpoint.pt")
            and frozen["historySha256"] == digest(args.input / "history.json"), "Frozen refit differs")
    all_artifacts = {**config["innerArtifactsSha256"], **frozen_artifacts}
    guard(config["sourceSha256"], all_artifacts)
    original = original_args(read_json(Path(config["innerConfigPath"])))
    torch.set_num_threads(original.threads)
    data = outer_data(config["kind"], original, TRAINERS[config["kind"]].setup(original))
    require(config["fitRows"] == data["fit"] and config["priorState"] == data["priors"]
            and config["inputBinding"] == (data["binding"] if config["kind"] == "local" else data["bindings"])
            and config["fixedEpochs"] == frozen["epochsRun"] == config["selected"]["epochs"],
            "Frozen refit row/statistic identity differs")
    saved = torch.load(args.input / "checkpoint.pt", map_location="cpu", weights_only=True)
    require(saved["configSha256"] == frozen["configSha256"] and saved["epoch"] == config["fixedEpochs"]
            and torch.equal(saved["mean"], data["mean"]) and torch.equal(saved["std"], data["std"]),
            "Frozen checkpoint normalization or epoch differs")
    model = local.make_model(original, data["values"].shape[1])
    model.load_state_dict(saved["model"], strict=True)
    fresh(args.output)  # Refuse an existing destination before any holdout prediction.
    metrics, predictions = local.evaluate(model, data, data["holdout"], "cpu", original.batch_size)
    rows = [data["cohort"]["rows"][i] for i in data["holdout"]]
    prior = np.asarray([data["priors"][row["targetPhone"]]["probabilities"] for row in rows])
    atomic_json(args.output / "predictions.json", predictions)
    atomic_json(args.output / "prior.json", {"rowIndices": data["holdout"], "probabilities": prior.tolist(),
                                            "evaluation": score_predictions(prior, rows)})
    report = {"complete": True, "phase": "outer-evaluation", "kind": config["kind"], "fold": config["fold"],
              "family": config["family"], "regime": config["regime"], "evaluation": metrics,
              "predictionsSha256": digest(args.output / "predictions.json"),
              "priorSha256": digest(args.output / "prior.json"), "sourceSha256": config["sourceSha256"],
              "frozenArtifactsSha256": frozen_artifacts,
              "interpretation": "Development cross-fit speaker holdout; shared research decisions used overlapping inner folds",
              "authorTestInferencePerformed": False, "clinicalUseEligible": False, "learnerFeedbackEligible": False}
    guard(config["sourceSha256"], all_artifacts)
    input_guard(config["kind"], data)
    require(digest(args.input / "checkpoint.pt") == frozen["checkpointSha256"], "Checkpoint changed during evaluation")
    atomic_json(args.output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="phase", required=True)
    fit = commands.add_parser("refit")
    fit.add_argument("--kind", choices=TRAINERS, required=True)
    fit.add_argument("--candidates", type=Path, nargs=2, required=True)
    fit.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--input", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_refit(args) if args.phase == "refit" else run_evaluate(args)
    print(f"{args.phase}: complete={result['complete']}; {args.output}")
