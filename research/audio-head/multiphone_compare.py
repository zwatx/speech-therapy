"""Compare verified frozen INNER runs without encoder or checkpoint inference.

Only the predeclared all-age macro-phone NLL selects learning rates. Child
slices, ranking diagnostics and seed spreads describe selected inner runs;
overlapping validation partitions are never pooled as independent evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import itertools
import math
from pathlib import Path

import numpy as np

import multiphone_verify as verify
from multiphone_controls import (canonical_sha, check_binding, choose_trial as choose_control,
                                 predict_control, validate_study)
from multiphone_train import distribution_metrics

HERE = Path(__file__).resolve().parent
VERIFIER_SHA256 = "5ba5fa3e92bb3d4e6367c3817df958a35becf8d04147fd8be82c63d34fd10d39"
GROUP_FIELDS = ("encoder", "head", "fold", "seed")
ARTIFACT_NAMES = {"config.json", "best.pt", "report.json", "predictions.json", "history.jsonl"}
SLICES = ("allAges", "ages6to12")
CONTROL_FAMILIES = ("prior", "word-age-backoff", "linear-word-age-capture")
SOURCE_FILES = ("multiphone_compare.py", "multiphone_verify.py", "multiphone_controls.py",
                "multiphone_train.py", "speechocean_r_rater_cv.py")
require, digest, read_json = verify.require, verify.digest, verify.read_json


def source_hashes():
    return {name: digest(HERE / name) for name in SOURCE_FILES}


def verification_index(paths: list[Path], recipe: dict, base: Path):
    """Consume verifier evidence and bind it to current inputs; never bless a raw run."""
    require(paths and len(set(path.resolve() for path in paths)) == len(paths), "Expected unique verifier reports")
    sources = {**verify.SOURCE_SHA256, **verify.CACHE_SOURCE_SHA256}
    require(digest(HERE / "multiphone_verify.py") == VERIFIER_SHA256
            and all(digest(HERE / name) == value for name, value in sources.items()), "Pinned verification sources differ")
    require(digest(base / "cohort.json") == recipe["cohortSha256"]
            and digest(base / "splits.json") == recipe["splitsSha256"], "Study data/split changed")
    indexed, conflicts, evidence, cache_pins = {}, {}, [], {}
    for path in paths:
        snapshot = read_json(path)
        require(snapshot["verifierSha256"] == VERIFIER_SHA256
                and snapshot["recipeSha256"] == verify.RECIPE_SHA256
                and snapshot["sourceSha256"] == sources
                and snapshot["selectionUnchanged"] is True
                and snapshot["authorTestInferencePerformed"] is False
                and snapshot["outerOutcomesUsed"] is False
                and snapshot["clinicalUseEligible"] is False
                and snapshot["learnerFeedbackEligible"] is False, "Verification scope or provenance differs")
        encoders = snapshot["requestedEncoders"]
        require(encoders and len(set(encoders)) == len(encoders) and set(encoders) <= set(recipe["encoders"]),
                "Verification encoder scope differs")
        expected = {row["name"]: row for row in verify.matrix_runs(recipe, encoders)}
        requested = snapshot["requestedRunNames"]
        if requested is not None:
            require(requested and len(set(requested)) == len(requested) and set(requested) <= set(expected),
                    "Verification requested-run scope differs")
            expected = {name: expected[name] for name in requested}
        names = [run["name"] for run in snapshot["runs"]]
        require(len(set(names)) == len(names) and set(names) <= set(expected)
                and snapshot["expectedRuns"] == len(expected) and snapshot["verifiedRuns"] == len(names)
                and sorted(snapshot["missingRuns"]) == sorted(set(expected) - set(names))
                and snapshot["completeForRequestedScope"] == (len(names) == len(expected)),
                "Verification coverage/counts differ")
        for encoder, pin in snapshot["cacheIndexSha256"].items():
            require(encoder in recipe["encoders"]
                    and digest(base / verify.CACHES[encoder] / "index.json") == pin,
                    "Verified cache index changed")
            require(encoder not in cache_pins or cache_pins[encoder] == pin, "Conflicting cache pins")
            cache_pins[encoder] = pin
        for row in snapshot["runs"]:
            require(all(row[key] == value for key, value in expected[row["name"]].items())
                    and type(row["bestEpoch"]) is int and 1 <= row["bestEpoch"] <= recipe["maximumEpochs"]
                    and math.isfinite(row["selectionMacroTargetLogLoss"]) and row["selectionMacroTargetLogLoss"] >= 0
                    and set(row["artifactsSha256"]) == ARTIFACT_NAMES
                    and row["encoder"] in snapshot["cacheIndexSha256"], "Verified run identity/evidence differs")
            selected_evidence = {key: row[key] for key in
                                 (*expected[row["name"]], "bestEpoch", "selectionMacroTargetLogLoss", "artifactsSha256")}
            if row["name"] in indexed and indexed[row["name"]] != selected_evidence:
                conflicts[row["name"]] = "Independent verifier reports disagree about this run"
            indexed[row["name"]] = selected_evidence
        evidence.append({"path": str(path.resolve()), "sha256": digest(path), "verifiedRuns": len(names)})
    return indexed, conflicts, {"reports": evidence, "cacheIndexSha256": cache_pins}


def inventory_runs(recipe: dict, base: Path, verified: dict, conflicts=None) -> list[dict]:
    result = []
    for expected in verify.matrix_runs(recipe):
        row = dict(expected)
        pin = verified.get(row["name"])
        if row["name"] in (conflicts or {}):
            row.update(status="invalid", reason=conflicts[row["name"]])
        elif pin is None:
            row.update(status="incomplete", reason="Completed report awaits independent verification"
                       if (base / row["name"] / "report.json").is_file() else "Completed report not published")
        else:
            try:
                require(all(digest(base / row["name"] / filename) == sha
                            for filename, sha in pin["artifactsSha256"].items()), "Artifact changed after verification")
                row.update(status="complete", bestEpoch=pin["bestEpoch"],
                           selectionMacroTargetLogLoss=pin["selectionMacroTargetLogLoss"],
                           artifactsSha256=pin["artifactsSha256"])
            except (OSError, ValueError) as error:
                row.update(status="invalid", reason=str(error))
        result.append(row)
    return result


def select_learning_rates(inventory: list[dict], recipe: dict) -> list[dict]:
    expected = {row["name"]: row for row in verify.matrix_runs(recipe)}
    require(len(inventory) == len(expected) and {row["name"] for row in inventory} == set(expected),
            "Comparison inventory does not exactly cover the declared matrix")
    for row in inventory:
        require(all(row[key] == value for key, value in expected[row["name"]].items())
                and row["status"] in ("complete", "incomplete", "invalid"), "Inventory identity/status differs")
    selections = []
    for group in itertools.product(recipe["encoders"], recipe["heads"], recipe["folds"], recipe["initializationSeeds"]):
        identity = dict(zip(GROUP_FIELDS, group, strict=True))
        candidates = [row for row in inventory if all(row[key] == value for key, value in identity.items())]
        require(len(candidates) == len(recipe["learningRates"])
                and {row["lr"] for row in candidates} == set(recipe["learningRates"]), "Learning-rate coverage differs")
        if not all(row["status"] == "complete" for row in candidates):
            selections.append({**identity, "status": "unavailable", "candidateNames": [row["name"] for row in candidates]})
            continue
        require(all(math.isfinite(row["selectionMacroTargetLogLoss"]) for row in candidates), "Nonfinite selection score")
        winner = min(candidates, key=lambda row: (row["selectionMacroTargetLogLoss"], row["lr"], row["bestEpoch"]))
        selections.append({**identity, "status": "selected", "name": winner["name"], "lr": winner["lr"],
                           "bestEpoch": winner["bestEpoch"], "selectionMacroTargetLogLoss": winner["selectionMacroTargetLogLoss"],
                           "candidates": [{key: row[key] for key in
                                           ("name", "lr", "bestEpoch", "selectionMacroTargetLogLoss")} for row in candidates]})
    return selections


def slice_mask(rows: list[dict], name: str) -> np.ndarray:
    require(name in SLICES and all(type(row["age"]) in (int, float) and math.isfinite(row["age"])
                                  for row in rows), "Unknown age slice or invalid age metadata")
    return np.asarray([name == "allAges" or 6 <= row["age"] <= 12 for row in rows], dtype=bool)


def proper_metrics(probabilities, counts, phones):
    metrics = distribution_metrics(probabilities, counts)
    per_phone = {phone: distribution_metrics(probabilities[phones == phone], counts[phones == phone])
                 for phone in sorted(set(phones))}
    return {**metrics, "perPhone": per_phone,
            "macroTargetLogLoss": float(np.mean([row["perRaterLogLoss"] for row in per_phone.values()])),
            "macroTargetBrier": float(np.mean([row["perRaterBrier"] for row in per_phone.values()]))}


def slice_diagnostics(probabilities, rows: list[dict], target_phones: list[str], name: str):
    p, counts = verify.validate_predictions(probabilities, [row["raterCounts"] for row in rows])
    mask = slice_mask(rows, name)
    chosen = [row for row, include in zip(rows, mask, strict=True) if include]
    support = {"positions": len(chosen), "clips": len({row["clipId"] for row in chosen}),
               "speakers": len({row["speakerId"] for row in chosen}),
               "raterWeights": counts[mask].sum(0).astype(int).tolist(),
               "presentPhones": sorted({row["targetPhone"] for row in chosen}),
               "absentPhones": sorted(set(target_phones) - {row["targetPhone"] for row in chosen})}
    if not chosen:
        return {"support": support, "proper": None, "pooled": None, "perPhone": {}, "macroTarget": None}
    phones = np.asarray([row["targetPhone"] for row in chosen])
    require(set(phones) <= set(target_phones), "Unexpected phone in diagnostic slice")
    discrimination = verify.target_discrimination(p[mask], counts[mask], phones)
    for phone, value in discrimination["perPhone"].items():
        selected = [row for row in chosen if row["targetPhone"] == phone]
        value["support"] = {"positions": len(selected), "clips": len({row["clipId"] for row in selected}),
                            "speakers": len({row["speakerId"] for row in selected})}
    return {"support": support, "proper": proper_metrics(p[mask], counts[mask], phones),
            "pooled": verify.discrimination(p[mask], counts[mask]), **discrimination}


def comparison_delta(model: dict, prior: dict) -> dict:
    require(model["support"] == prior["support"], "Comparator slice/support differs")
    if model["proper"] is None:
        return {"proper": None, "pooled": None, "macroTarget": None, "perPhone": {}}

    def difference(a, b):
        return None if a is None or b is None else a - b

    def binary_difference(a, b):
        require(all(a[key] == b[key] for key in ("positiveRaterWeight", "negativeRaterWeight", "prevalence")),
                "Comparator event support differs")
        return {key: difference(a[key], b[key]) for key in ("auroc", "averagePrecision")}

    macro = {}
    for event in ("rating0", "ratingBelow2"):
        a, b = model["macroTarget"][event], prior["macroTarget"][event]
        require(all(a[key] == b[key] for key in ("definedTargets", "undefinedTargets", "excludedPhones")),
                "Comparator macro-phone support differs")
        macro[event] = {key: difference(a[key], b[key]) for key in ("auroc", "averagePrecision")}
    return {"proper": {key: model["proper"][key] - prior["proper"][key] for key in
                       ("perRaterLogLoss", "perRaterBrier", "macroTargetLogLoss", "macroTargetBrier")},
            "pooled": {event: binary_difference(model["pooled"][event], prior["pooled"][event])
                       for event in ("rating0", "ratingBelow2")}, "macroTarget": macro,
            "perPhone": {phone: {event: binary_difference(model["perPhone"][phone][event],
                                                           prior["perPhone"][phone][event])
                                  for event in ("rating0", "ratingBelow2")} for phone in model["perPhone"]}}


def controls_for_fold(directory: Path, fold_number: int, cohort: dict, splits: dict, recipe: dict, base: Path):
    location = directory / f"fold-{fold_number}-inner"
    config_path, selection_path = location / "config.json", location / "selection.json"
    config, selection = read_json(config_path), read_json(selection_path)
    binding = {"cohortPath": str((base / "cohort.json").resolve()), "cohortSha256": recipe["cohortSha256"],
               "splitsPath": str((base / "splits.json").resolve()), "splitsSha256": recipe["splitsSha256"],
               "cohortCanonicalSha256": canonical_sha(cohort)}
    check_binding(config, binding, fold_number)
    fold = splits["folds"][fold_number]
    require(config["phase"] == "inner" and config["fitRows"] == fold["innerFitRows"]
            and config["validationRows"] == fold["innerValidationRows"]
            and selection["configSha256"] == digest(config_path) and selection["outerOutcomesUsed"] is False
            and set(config["families"]) == set(CONTROL_FAMILIES), "Controls use different partitions/scope")
    rows = [cohort["rows"][i] for i in sorted(fold["innerValidationRows"])]
    phones = [cohort["targetPhones"][i] for i in cohort["eligibleTargetIds"]]
    reference, prior_evidence = verify.supplied_prior(directory, fold_number, cohort, splits, recipe)
    results, pins = {}, {str(config_path): digest(config_path), str(selection_path): digest(selection_path)}
    for family in CONTROL_FAMILIES:
        selected = selection["selected"][family]
        winner = choose_control(selection["trials"][family])
        require(all(selected[key] == winner[key] for key in ("setting", "statePath", "stateSha256")),
                "Control selection differs from inner macro-NLL rule")
        path = (location / selected["statePath"]).resolve()
        require(path.is_relative_to(location.resolve()) and digest(path) == selected["stateSha256"], "Control checkpoint digest/path differs")
        state = read_json(path)
        require(state["family"] == family, "Control family differs")
        probabilities = predict_control(state, rows, cohort["clips"])
        if family == "prior":
            require(np.array_equal(probabilities, reference), "Prior differs from exact inner-fit counts")
        profiles = {name: slice_diagnostics(probabilities, rows, phones, name) for name in SLICES}
        require(abs(profiles["allAges"]["proper"]["macroTargetLogLoss"] - selected["innerMacroTargetLogLoss"]) <= 1e-10,
                "Replayed control differs from saved inner loss")
        results[family] = {"setting": selected["setting"], "statePath": str(path),
                           "stateSha256": digest(path), "slices": profiles}
        pins[str(path)] = digest(path)
    return {"fold": fold_number, "rows": sorted(fold["innerValidationRows"]), "families": results,
            "priorEvidence": prior_evidence, "artifactsSha256": pins}


def seed_spread(selections: list[dict], recipe: dict) -> list[dict]:
    result = []

    def summarize(values):
        usable = [value for value in values if value is not None]
        return {"definedSeeds": len(usable), "missingSeeds": len(values) - len(usable),
                "mean": float(np.mean(usable)) if usable else None,
                "minimum": min(usable) if usable else None, "maximum": max(usable) if usable else None,
                "populationSD": float(np.std(usable)) if usable else None}

    for encoder, head, fold in itertools.product(recipe["encoders"], recipe["heads"], recipe["folds"]):
        chosen = [row for row in selections if (row["encoder"], row["head"], row["fold"]) == (encoder, head, fold)]
        require(len(chosen) == len(recipe["initializationSeeds"])
                and {row["seed"] for row in chosen} == set(recipe["initializationSeeds"]), "Seed coverage differs")
        metrics = {}
        for age in SLICES:
            profiles = [row["slices"][age] for row in chosen]
            require(all(row["support"] == profiles[0]["support"] for row in profiles), "Seed slice support differs")
            current = {key: summarize([row["proper"][key] if row["proper"] else None for row in profiles])
                       for key in ("perRaterLogLoss", "perRaterBrier", "macroTargetLogLoss", "macroTargetBrier")}
            for event in ("rating0", "ratingBelow2"):
                for key in ("auroc", "averagePrecision"):
                    current[f"macroTarget.{event}.{key}"] = summarize([
                        row["macroTarget"][event][key] if row["macroTarget"] else None for row in profiles])
            current["macroNLLModelMinusPrior"] = summarize([
                row["modelMinusControls"]["prior"][age]["proper"]["macroTargetLogLoss"]
                if row["modelMinusControls"]["prior"][age]["proper"] else None for row in chosen])
            metrics[age] = {"support": profiles[0]["support"], "metrics": current}
        result.append({"encoder": encoder, "head": head, "fold": fold,
                       "selectedRuns": [{key: row[key] for key in ("seed", "name", "lr", "bestEpoch")} for row in chosen],
                       "slices": metrics, "interpretation": "Initialization spread on the same inner speakers; not independent replicates or a confidence interval"})
    return result


def partition_overlap(cohort: dict, splits: dict):
    result = {}
    for age in SLICES:
        memberships = []
        for fold in splits["folds"]:
            selected = fold["innerValidationRows"]
            rows = [cohort["rows"][i] for i in selected]
            members = [(i, row) for i, row, include in zip(selected, rows, slice_mask(rows, age), strict=True) if include]
            memberships.append({"fold": fold["fold"], "rows": {i for i, _ in members},
                                "speakers": {row["speakerId"] for _, row in members},
                                "clips": {row["clipId"] for _, row in members}})
        result[age] = {"distinctSpeakers": len(set().union(*(row["speakers"] for row in memberships))),
                       "speakerMembershipsAcrossFolds": sum(len(row["speakers"]) for row in memberships),
                       "pairs": [{"folds": [a["fold"], b["fold"]], **{
                           key: len(a[key] & b[key]) for key in ("rows", "clips", "speakers")}}
                                 for a, b in itertools.combinations(memberships, 2)]}
    return result


def compare_matrix(base: Path, verification_paths: list[Path], controls: Path, *, status_only=False):
    recipe = verify.load_recipe()
    initial_sources = source_hashes()
    indexed, conflicts, evidence = verification_index(verification_paths, recipe, base)
    inventory = inventory_runs(recipe, base, indexed, conflicts)
    selections = select_learning_rates(inventory, recipe)
    statuses = {status: sum(row["status"] == status for row in inventory) for status in ("complete", "incomplete", "invalid")}
    result = {"schemaVersion": 1, "createdAtUTC": datetime.now(timezone.utc).isoformat(),
              "scope": "Conditional diagnostics of saved author-train INNER predictions",
              "recipeSha256": verify.RECIPE_SHA256, "recipeSelectionRule": recipe["selection"],
              "sourceSha256": initial_sources, "verification": evidence,
              "expectedRuns": len(inventory), "runStatusCounts": statuses, "runs": inventory,
              "wholeMatrixVerified": statuses["complete"] == len(inventory),
              "diagnosticsComputed": False, "selections": selections,
              "selectionUsesChildMetrics": False, "selectionUsesOuterMetrics": False,
              "crossFoldPredictionsPooled": False, "encoderInferencePerformed": False,
              "checkpointInferencePerformed": False, "savedControlRulesReplayed": False,
              "authorTestInferencePerformed": False, "outerOutcomesUsed": False,
              "clinicalUseEligible": False, "learnerFeedbackEligible": False,
              "limitations": ["Inner outcomes already selected epochs and learning rates; diagnostics include selection optimism.",
                              "Child slices are descriptive, often very small, and never select settings.",
                              "Individual expert-rating discrimination is not clinical pronunciation-error detection.",
                              "Phone macro rankings exclude targets lacking positive or negative rater support; absent phones are separately listed.",
                              "Validation partitions overlap; no pooled cross-fold score, independence assumption, or confidence interval is produced.",
                              "Artifact integrity and saved-score checks do not replay acoustic model checkpoints or rehash frame arrays."]}
    if not status_only and result["wholeMatrixVerified"]:
        cohort, splits = read_json(base / "cohort.json"), read_json(base / "splits.json")
        validate_study(cohort, splits)
        target_phones = [cohort["targetPhones"][i] for i in cohort["eligibleTargetIds"]]
        control_profiles = {fold: controls_for_fold(controls, fold, cohort, splits, recipe, base) for fold in recipe["folds"]}
        for selected in selections:
            directory = base / selected["name"]
            p, _, rows = verify.checked_predictions(read_json(directory / "predictions.json"),
                                                    splits["folds"][selected["fold"]]["innerValidationRows"],
                                                    cohort["rows"], read_json(directory / "report.json")["evaluation"])
            selected["slices"] = {name: slice_diagnostics(p, rows, target_phones, name) for name in SLICES}
            comparators = control_profiles[selected["fold"]]["families"]
            selected["modelMinusControls"] = {family: {name: comparison_delta(selected["slices"][name], profiles["slices"][name])
                                                       for name in SLICES} for family, profiles in comparators.items()}
        result.update(diagnosticsComputed=True, savedControlRulesReplayed=True,
                      controls=list(control_profiles.values()), seedSpreadByFold=seed_spread(selections, recipe),
                      partitionOverlap=partition_overlap(cohort, splits))
        require(all(digest(Path(path)) == pin for control in control_profiles.values()
                    for path, pin in control["artifactsSha256"].items()), "Control artifacts changed during comparison")
    require(source_hashes() == initial_sources and digest(verify.RECIPE) == verify.RECIPE_SHA256,
            "Comparison sources/recipe changed")
    require(inventory_runs(recipe, base, indexed, conflicts) == inventory, "Run artifacts changed during comparison")
    require(digest(base / "cohort.json") == recipe["cohortSha256"] and digest(base / "splits.json") == recipe["splitsSha256"]
            and all(digest(Path(row["path"])) == row["sha256"] for row in evidence["reports"])
            and all(digest(base / verify.CACHES[kind] / "index.json") == pin for kind, pin in evidence["cacheIndexSha256"].items()),
            "Study or verification evidence changed during comparison")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification", action="append", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=verify.BASE)
    parser.add_argument("--controls", type=Path, default=verify.BASE / "controls")
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import json
    result = compare_matrix(args.base.resolve(), args.verification, args.controls.resolve(), status_only=args.status_only)
    with args.output.open("x") as stream:
        args.output.chmod(0o600)
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("expectedRuns", "runStatusCounts", "diagnosticsComputed")}))
