"""Evaluate supplied terminal predictions against binary listener vote counts.

This module performs no model loading, fitting, inference or corpus access.
"""
from __future__ import annotations
import math
import json
import copy
import statistics
import numpy as np
import argparse
import sys
from pathlib import Path

ARM_NAMES = ("candidate", "retained", "calibration")


def _validate(payload):
    """Require complete, unambiguous terminal rows; never discard malformed data."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def identifier(value):
        return type(value) is str and bool(value.strip())

    def finite_json(value):
        if value is None or type(value) in (str, bool, int):
            return True
        if type(value) is float:
            return math.isfinite(value)
        if type(value) is list:
            return all(finite_json(item) for item in value)
        if type(value) is dict:
            return all(type(key) is str and finite_json(item) for key, item in value.items())
        return False

    require(type(payload) is dict, "input must be an object")
    require(finite_json(payload), "input must contain finite JSON values with string object keys")
    require(set(payload) == {"children", "selectedTokens", "arms", "ratings"},
            "input requires children, selectedTokens, arms and ratings")
    require(type(payload["children"]) is list, "children must be a full explicit list")
    child_ids = set()
    for child in payload["children"]:
        require(type(child) is dict and identifier(child.get("childId")), "invalid childId")
        require(child["childId"] not in child_ids, "duplicate childId")
        require(set(child) <= {"childId", "descriptors"}, "unknown child fields")
        require("descriptors" not in child or type(child["descriptors"]) is dict,
                "descriptors must be an object")
        child_ids.add(child["childId"])

    def roster(rows, label):
        require(type(rows) is list, f"{label} must be a list")
        keys = set()
        for row in rows:
            require(type(row) is dict and identifier(row.get("childId"))
                    and identifier(row.get("tokenId")), f"invalid {label} identity")
            require(row["childId"] in child_ids, f"unknown child in {label}")
            key = _key(row)
            require(key not in keys, f"duplicate {label} row")
            keys.add(key)
        return keys

    selected = roster(payload["selectedTokens"], "selectedTokens")
    require(all(set(row) == {"childId", "tokenId"} for row in payload["selectedTokens"]),
            "selected tokens require only childId and tokenId")
    require(type(payload["arms"]) is dict and set(payload["arms"]) == set(ARM_NAMES),
            "arms must be exactly candidate, retained and calibration")
    for name in ARM_NAMES:
        require(roster(payload["arms"][name], name) == selected, f"incomplete {name} roster")
        for row in payload["arms"][name]:
            status = row.get("status")
            if status == "processed":
                probability = row.get("probability")
                require(type(probability) in (int, float) and math.isfinite(probability)
                        and 0 <= probability <= 1, "invalid probability")
                require(set(row) == {"childId", "tokenId", "status", "probability"},
                        "processed row requires probability only")
            else:
                require(status in ("unavailable", "failed"), "invalid terminal status")
                require(type(row.get("reason")) is str and bool(row["reason"].strip()),
                        "unavailable/failed requires a reason")
                require(set(row) == {"childId", "tokenId", "status", "reason"},
                        "unavailable/failed row requires reason only")
    require(roster(payload["ratings"], "ratings") == selected, "incomplete rating roster")
    for row in payload["ratings"]:
        if row.get("status") == "available":
            counts = (row.get("positiveVotes"), row.get("negativeVotes"))
            require(all(type(count) is int and count >= 0 for count in counts)
                    and sum(counts) > 0, "votes require nonnegative integer counts and positive n")
            require(set(row) == {"childId", "tokenId", "status", "positiveVotes", "negativeVotes"},
                    "available rating requires separate vote counts")
        else:
            require(row.get("status") == "unavailable", "invalid rating status")
            require(type(row.get("reason")) is str and bool(row["reason"].strip()),
                    "unavailable rating requires a reason")
            require(set(row) == {"childId", "tokenId", "status", "reason"},
                    "unavailable rating requires reason only")


def _key(row):
    return row["childId"], row["tokenId"]


def _auroc(rows):
    positive = sum(pos for _, pos, _ in rows)
    negative = sum(neg for _, _, neg in rows)
    if not positive or not negative:
        return None
    credit = sum(pos * neg * (1 if p > q else 0.5 if p == q else 0)
                 for p, pos, _ in rows for q, _, neg in rows)
    return credit / (positive * negative)


def _metrics(rows):
    votes = sum(pos + neg for _, pos, neg in rows)
    clipped = [(min(1 - 1e-6, max(1e-6, p)), pos, neg) for p, pos, neg in rows]
    return {"auroc": _auroc(rows),
            "logLoss": -sum(pos * math.log(p) + neg * math.log1p(-p)
                            for p, pos, neg in clipped) / votes if votes else None,
            "brier": sum(pos * (1 - p)**2 + neg * p**2
                         for p, pos, neg in clipped) / votes if votes else None}


def _child_metrics(keys, predictions, ratings):
    rows, exclusions = [], []
    statuses = {status: 0 for status in ("processed", "unavailable", "failed")}
    rated = 0
    for key in keys:
        prediction, rating = predictions[key], ratings[key]
        statuses[prediction["status"]] += 1
        rated += rating["status"] == "available"
        reasons = []
        if prediction["status"] != "processed":
            reasons.append(f"prediction:{prediction['status']}:{prediction['reason']}")
        if rating["status"] != "available":
            reasons.append(f"rating:unavailable:{rating['reason']}")
        if reasons:
            exclusions.append({"tokenId": key[1], "reasons": reasons})
        else:
            rows.append((prediction["probability"], rating["positiveVotes"], rating["negativeVotes"]))
    metrics = _metrics(rows)
    positive = sum(pos for _, pos, _ in rows)
    negative = sum(neg for _, _, neg in rows)
    reason = "no_selected_tokens" if not keys else "no_processed_rated_tokens" if not rows else None
    auroc_reason = reason or ("no_positive_votes" if not positive else "no_negative_votes" if not negative else None)
    return {**metrics, "coverage": {"selected": len(keys), **statuses, "ratingAvailable": rated,
                                   "processedAndRated": len(rows), "positiveVotes": positive, "negativeVotes": negative},
            "exclusions": exclusions,
            "metricReasons": {"auroc": auroc_reason, "logLoss": reason, "brier": reason}}


def _pair(keys, candidate, comparator, ratings):
    shared = [key for key in keys if candidate[key]["status"] == comparator[key]["status"] == "processed"
              and ratings[key]["status"] == "available"]
    left = _child_metrics(shared, candidate, ratings)
    right = _child_metrics(shared, comparator, ratings)
    # A pair with no intersection still distinguishes empty selection from coverage loss.
    if not shared and keys:
        for side in (left, right):
            side["metricReasons"] = {metric: "no_shared_processed_rated_tokens" for metric in ("auroc", "logLoss", "brier")}
    def gain(metric, direction):
        return direction * (left[metric] - right[metric]) if left[metric] is not None and right[metric] is not None else None
    return {"tokenIds": [key[1] for key in shared], "selectedTokens": len(keys),
            "sharedProcessedRatedTokens": len(shared),
            "excludedTokens": [{"tokenId": key[1], "reasons":
                                ([f"candidate:{candidate[key]['status']}:{candidate[key]['reason']}"] if candidate[key]["status"] != "processed" else []) +
                                ([f"comparator:{comparator[key]['status']}:{comparator[key]['reason']}"] if comparator[key]["status"] != "processed" else []) +
                                ([f"rating:unavailable:{ratings[key]['reason']}"] if ratings[key]["status"] != "available" else [])}
                               for key in keys if key not in shared],
            "candidate": left, "comparator": right,
            "aurocGain": gain("auroc", 1), "logLossGain": gain("logLoss", -1), "brierGain": gain("brier", -1)}


def _summary(children, arm, metric):
    defined = [child for child in children if child["arms"][arm][metric] is not None]
    values = [child["arms"][arm][metric] for child in defined]
    return {"fullChildDenominator": len(children), "definedChildIds": [child["childId"] for child in defined],
            "excludedChildren": [{"childId": child["childId"], "reason": child["arms"][arm]["metricReasons"][metric]}
                                 for child in children if child["arms"][arm][metric] is None],
            "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None}


def _paired_summary(children, pair_name, metric):
    defined, excluded, gains = [], [], []
    for child in children:
        pair = child["paired"][pair_name]
        value = pair[metric + "Gain"]
        if value is None:
            excluded.append({"childId": child["childId"], "reasons": {
                side: pair[side]["metricReasons"][metric] for side in ("candidate", "comparator")}})
        else:
            defined.append(child["childId"])
            gains.append(value)
    bootstrap = {"population": "defined_paired_children_only", "seed": 20261002,
                 "generator": "numpy.default_rng/PCG64", "requestedReplicates": 2000,
                 "quantileMethod": "linear", "confidenceLevel": 0.95,
                 "generatedReplicates": 0, "undefinedReplicates": 0,
                 "skippedReplicates": 2000, "interval95": None,
                 "degenerate": len(gains) == 1}
    if gains:
        # Each endpoint restarts the fixed RNG; only saved paired child gains are sampled.
        rng = np.random.default_rng(20261002)
        sampled = rng.choice(np.asarray(gains), size=(2000, len(gains)), replace=True).mean(axis=1)
        bootstrap.update(generatedReplicates=2000, skippedReplicates=0,
                         interval95=np.quantile(sampled, [0.025, 0.975], method="linear").tolist())
    return {"fullChildDenominator": len(children), "definedChildIds": defined,
            "excludedChildren": excluded, "gains": [{"childId": child_id, "gain": gain} for child_id, gain in zip(defined, gains)],
            "gainDirection": "candidate_minus_comparator" if metric == "auroc" else "comparator_minus_candidate",
            "meanGain": statistics.mean(gains) if gains else None,
            "medianGain": statistics.median(gains) if gains else None,
            "improvedChildren": sum(gain > 0 for gain in gains), "worsenedChildren": sum(gain < 0 for gain in gains),
            "tiedChildren": sum(gain == 0 for gain in gains),
            "fractionImproved": sum(gain > 0 for gain in gains) / len(gains) if gains else None,
            "fractionWorsened": sum(gain < 0 for gain in gains) / len(gains) if gains else None,
            "bootstrap": bootstrap}


def evaluate(payload):
    """Return deterministic descriptive metrics for an explicit selected roster."""
    _validate(payload)
    # Canonical order fixes the resampling population order and exported receipt.
    payload = copy.deepcopy(payload)
    payload["children"].sort(key=lambda row: row["childId"])
    for rows in (payload["selectedTokens"], payload["ratings"], *payload["arms"].values()):
        rows.sort(key=_key)
    ratings = {_key(row): row for row in payload["ratings"]}
    predictions = {name: {_key(row): row for row in payload["arms"][name]} for name in ARM_NAMES}
    children = []
    for child in payload["children"]:
        keys = [_key(row) for row in payload["selectedTokens"] if row["childId"] == child["childId"]]
        arms = {}
        for name in ARM_NAMES:
            arms[name] = _child_metrics(keys, predictions[name], ratings)
        pairs = {"candidateVsRetained": _pair(keys, predictions["candidate"], predictions["retained"], ratings),
                 "candidateVsCalibration": _pair(keys, predictions["candidate"], predictions["calibration"], ratings)}
        children.append({"childId": child["childId"], "descriptors": copy.deepcopy(child.get("descriptors", {})),
                         "arms": arms, "paired": pairs})
    return {"schemaVersion": 1, "researchOnly": True, "clinicalUseEligible": False, "learnerFeedbackEligible": False, "productionUseEligible": False,
            "fullChildDenominator": len(children), "selectedTokenDenominator": len(payload["selectedTokens"]), "children": children,
            "armSummary": {name: {metric: _summary(children, name, metric) for metric in ("auroc", "logLoss", "brier")} for name in ARM_NAMES},
            "pairedSummary": {"candidateVsRetained": {"auroc": _paired_summary(children, "candidateVsRetained", "auroc")},
                              "candidateVsCalibration": {metric: _paired_summary(children, "candidateVsCalibration", metric) for metric in ("logLoss", "brier")}},
            "terminalOutcomes": copy.deepcopy({key: payload[key] for key in ("selectedTokens", "arms", "ratings")})}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main(argv=None):
    """Evaluate the supplied JSON file; errors leave an existing export untouched."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="explicit terminal-roster JSON")
    parser.add_argument("--output", type=Path, required=True, help="deterministic evaluation JSON")
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve() or (args.output.exists() and args.input.samefile(args.output)):
            raise ValueError("output must not replace input")
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("output already exists")
        payload = json.loads(args.input.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        result = evaluate(payload)
        serialized = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8") as destination:
            destination.write(serialized)
    except (ValueError, OSError) as error:
        print(f"evaluation error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
