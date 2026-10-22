"""Inner-only rare-rating emphasis on the fixed phonetic target/scalar head.

This changes only the supervised objective. Population, features, architecture,
seeds, optimizer, stopping and matched unweighted selection remain declared.
Log-weight correction reverses the weighted objective's population optimum;
it does not establish empirical calibration or pronunciation correctness.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import random
import time

import numpy as np
import torch

import multiphone_phonetic_head as baseline
from multiphone_cache import atomic_json, digest
from multiphone_child_train import corrected_probabilities, fit_class_weights, score_predictions, weighted_loss
from multiphone_train import save_checkpoint

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "experiments/multiphone-phonetic-balanced-v1.json"
read_json, require = baseline.read_json, baseline.require


def source_hashes():
    return {**baseline.source_hashes(), "multiphone_phonetic_balanced.py": digest(Path(__file__))}


def setup(args):
    recipe = read_json(RECIPE)
    require(digest(baseline.RECIPE) == recipe["baselineRecipeSha256"]
            and digest(args.binding) == recipe["featureBindingSha256"]
            and args.family == recipe["family"] and args.regime in recipe["regimes"]
            and args.fold in recipe["folds"] and args.lr in recipe["learningRates"],
            "Arguments differ from the fixed weighted-objective comparison")
    data = baseline.setup(args)
    # The existing mode name selects the formula, not this run's population;
    # `data['fit']` already applies the separately declared age regime.
    state = fit_class_weights([data["cohort"]["rows"][i] for i in data["fit"]], "balanced-all-age")
    data["classWeightState"] = state
    data["classWeights"] = torch.tensor(state["weights"], dtype=torch.float32)
    return data


@torch.no_grad()
def evaluate(model, data, indices, batch_size):
    model.eval()
    probabilities = []
    for offset in range(0, len(indices), batch_size):
        values, phones, mask, _ = baseline.batch(data, indices[offset:offset + batch_size], "cpu")
        logits = model(values, mask, phones, mask)[:, 0]
        probabilities.extend(corrected_probabilities(logits, data["classWeights"]).numpy())
    probabilities = np.asarray(probabilities, dtype=np.float64)
    rows = [data["cohort"]["rows"][i] for i in indices]
    return score_predictions(probabilities, rows), {"rowIndices": indices, "probabilities": probabilities.tolist(),
        "probabilityScale": "softmax(logits - log(fit class weights)); objective correction, not empirical calibration"}


def guard(config, config_sha=None):
    require(digest(RECIPE) == config["recipeSha256"] and source_hashes() == config["sourceSha256"]
            and digest(baseline.RECIPE) == config["baselineRecipeSha256"]
            and digest(Path(config["binding"])) == config["bindingSha256"], "Weighted-head source/recipe/binding changed")
    baseline.extraction.guard(config["inputFiles"])
    if config_sha is not None:
        require(digest(Path(config["output"]) / "config.json") == config_sha, "Immutable run configuration changed")


def train(args):
    require(not args.output.exists() and args.output.resolve().is_relative_to((HERE / "outputs").resolve()),
            "Choose a fresh weighted-head run directory")
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    generator = np.random.default_rng(args.seed)
    started = time.perf_counter()
    data = setup(args)
    model = baseline.make_model(args, data["values"].shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    config = {name: str(value.resolve()) if isinstance(value, Path) else value
              for name, value in vars(args).items() if name != "command"}
    config.update(recipeSha256=digest(RECIPE), baselineRecipeSha256=digest(baseline.RECIPE),
                  sourceSha256=source_hashes(), bindingSha256=digest(args.binding), inputFiles=data["bindings"],
                  fitRows=data["fit"], validationRows=data["validation"], selectionRows=data["selection"],
                  priorState=data["priors"], classWeightState=data["classWeightState"],
                  selection="same population-specific unweighted macro-phone NLL as original frozen comparison",
                  objective="global fit-class weighted soft five-rater NLL without row renormalization",
                  phase="inner", authorPartition="train", outerOutcomesUsed=False,
                  authorTestInferencePerformed=False, clinicalUseEligible=False, learnerFeedbackEligible=False,
                  empiricalCalibrationEstablished=False, torch=str(torch.__version__), numpy=np.__version__)
    guard(config)
    args.output.mkdir(parents=True, mode=0o700)
    atomic_json(args.output / "config.json", config)
    config_sha = digest(args.output / "config.json")
    rows = [data["cohort"]["rows"][i] for i in data["validation"]]
    prior = np.asarray([data["priors"][row["targetPhone"]]["probabilities"] for row in rows])
    prior_metrics = score_predictions(prior, rows)
    atomic_json(args.output / "prior.json", {"state": data["priors"], "rowIndices": data["validation"],
                                           "probabilities": prior.tolist(), "evaluation": prior_metrics})
    best_loss, best_epoch, history = float("inf"), 0, []
    for epoch in range(1, args.epochs + 1):
        model.train()
        order, loss_sum = generator.permutation(data["fit"]).tolist(), 0.
        for offset in range(0, len(order), args.batch_size):
            values, phones, mask, targets = baseline.batch(data, order[offset:offset + args.batch_size], "cpu")
            optimizer.zero_grad(set_to_none=True)
            losses = weighted_loss(model(values, mask, phones, mask)[:, 0], targets, data["classWeights"])
            require(bool(torch.isfinite(losses).all()), "Nonfinite weighted objective")
            losses.mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(losses.detach().sum())
        metrics, _ = evaluate(model, data, data["validation"], args.batch_size)
        value = baseline.selection_loss(metrics, args.regime)
        require(np.isfinite(value), "Nonfinite corrected selection loss")
        history.append({"epoch": epoch, "trainWeightedObjective": loss_sum / len(order),
                        "selectionMacroTargetLogLoss": value, "evaluation": metrics})
        improved = value < best_loss - 1e-7
        if improved:
            best_loss, best_epoch = value, epoch
        checkpoint = {"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                      "mean": data["mean"], "std": data["std"], "classWeights": data["classWeights"],
                      "classWeightState": data["classWeightState"], "epoch": epoch, "bestEpoch": best_epoch,
                      "bestLoss": best_loss, "configSha256": config_sha}
        guard(config, config_sha)
        save_checkpoint(args.output / "last.pt", checkpoint)
        if improved:
            save_checkpoint(args.output / "best.pt", checkpoint)
        atomic_json(args.output / "history.json", history)
        atomic_json(args.output / "status.json", {"complete": False, "epoch": epoch, "bestEpoch": best_epoch})
        if epoch - best_epoch >= args.patience:
            break
    saved = torch.load(args.output / "best.pt", map_location="cpu", weights_only=True)
    model.load_state_dict(saved["model"], strict=True)
    metrics, predictions = evaluate(model, data, data["validation"], args.batch_size)
    require(baseline.selection_loss(metrics, args.regime) == best_loss, "Selected corrected checkpoint score differs")
    atomic_json(args.output / "predictions.json", predictions)
    guard(config, config_sha)
    report = {"complete": True, "phase": "inner", "configSha256": config_sha,
              **{key + "Sha256": digest(args.output / name) for key, name in
                 (("checkpoint", "best.pt"), ("predictions", "predictions.json"), ("history", "history.json"), ("prior", "prior.json"))},
              "bestEpoch": best_epoch, "epochsRun": len(history), "bestSelectionMacroLogLoss": best_loss,
              "evaluation": metrics, "sameFitPriorEvaluation": prior_metrics, "elapsedSeconds": time.perf_counter() - started,
              "outerOutcomesUsed": False, "authorTestInferencePerformed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False, "empiricalCalibrationEstablished": False}
    atomic_json(args.output / "report.json", report)
    atomic_json(args.output / "status.json", {"complete": True, "bestEpoch": best_epoch, "epochsRun": len(history)})
    return report


def replay(output):
    config, report = read_json(output / "config.json"), read_json(output / "report.json")
    guard(config, report["configSha256"])
    require(report["complete"] is True and all(report[key + "Sha256"] == digest(output / name) for key, name in
            (("checkpoint", "best.pt"), ("predictions", "predictions.json"), ("history", "history.json"), ("prior", "prior.json"))),
            "Completed weighted-head artifacts changed")
    args = argparse.Namespace(**config)
    args.binding, args.output = Path(args.binding), Path(args.output)
    torch.set_num_threads(args.threads)
    data = setup(args)
    require(config["fitRows"] == data["fit"] and config["validationRows"] == data["validation"]
            and config["selectionRows"] == data["selection"] and config["classWeightState"] == data["classWeightState"]
            and config["priorState"] == data["priors"] and config["inputFiles"] == data["bindings"],
            "Replayed fit rows, class weights, prior or input binding differs")
    saved = torch.load(output / "best.pt", map_location="cpu", weights_only=True)
    require(saved["configSha256"] == report["configSha256"] and saved["epoch"] == saved["bestEpoch"] == report["bestEpoch"]
            and saved["bestLoss"] == report["bestSelectionMacroLogLoss"]
            and saved["classWeightState"] == data["classWeightState"]
            and all(torch.equal(saved[key], data[key]) for key in ("mean", "std", "classWeights")),
            "Weighted checkpoint selection or fit statistics differ")
    model = baseline.make_model(args, data["values"].shape[1])
    model.load_state_dict(saved["model"], strict=True)
    metrics, predictions = evaluate(model, data, data["validation"], args.batch_size)
    require(predictions == read_json(output / "predictions.json") and metrics == report["evaluation"],
            "Weighted-head CPU replay is not exact")
    guard(config, report["configSha256"])
    result = {"exact": True, "rows": len(data["validation"]), "checkpointSha256": report["checkpointSha256"], "evaluation": metrics}
    atomic_json(output / "replay.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fit = commands.add_parser("train")
    fit.add_argument("--binding", type=Path, required=True)
    fit.add_argument("--output", type=Path, required=True)
    fit.add_argument("--regime", choices=("all-age", "child-only"), required=True)
    fit.add_argument("--fold", type=int, choices=range(5), required=True)
    fit.add_argument("--lr", type=float, choices=(.001, .0003), required=True)
    fit.set_defaults(family="target-scalars", seed=7, hidden=128, dropout=.1, weight_decay=.01,
                     batch_size=64, epochs=100, patience=15, threads=2, device="cpu")
    check = commands.add_parser("replay")
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = train(args) if args.command == "train" else replay(args.output)
    print(f"complete={result.get('complete', result.get('exact'))}")
