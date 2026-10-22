"""Prepare an isolated calibration from explicitly supplied listener-vote rows.

No corpus discovery, model access, inference, CLI or automatic export occurs here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import platform
from pathlib import Path

import numpy as np
import scipy
from scipy.linalg import cho_factor, cho_solve
from scipy.special import expit


_RECIPE = {
    "inputProbability": "retained_p0_plus_p1",
    "positiveVotes": "derhotic_n_minus_k", "negativeVotes": "rhotic_k",
    "targetProbability": "positiveVotes/(positiveVotes+negativeVotes)",
    "outputProbabilityOrder": ["derhotic", "rhotic"],
    "weightRule": "n_i/sum_child_n/child_count",
    "moments": "unweighted_row_float64_population", "standardDeviationFloor": 1e-6,
    "inputClip": 1e-6, "priorClip": 1e-6, "slopeRidge": 0.001, "interceptPenalty": 0.0,
    "optimizer": "damped_newton_analytic_hessian_scipy_cholesky",
    "gradientInfinityNormGate": 1e-8, "maximumNewtonSteps": 100,
    "maximumBacktrackingSteps": 50, "armijoCoefficient": 1e-4,
    "backtrackingFactor": 0.5, "roundoffEpsilonMultiplier": 16,
    "roundoffRequiresStrictGradientDecrease": True,
    "negativeSlopeBoundary": "zero_slope_clipped_weighted_prior_logit",
    "zeroSlopeProjectedGradient": "min(slope_gradient,0)",
}
_DIGEST_FORMAT = "sha256_utf8_json_sort_keys_compact_ensure_ascii_false"
_CONTROL_FIELDS = {
    "schemaVersion", "status", "researchOnly", "clinicalUseEligible", "learnerFeedbackEligible",
    "productionUseEligible", "fullChildDenominator", "selectedTokenDenominator", "canonicalInput",
    "inputDigest", "membershipDigest", "digestFormat", "source", "dependencies", "recipe",
    "initialization", "coefficients", "transform", "weights", "unconstrained", "boundaryApplied",
    "projected", "fittedPredictions",
}


def _digest(value):
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class CalibrationFitError(ValueError):
    """Terminal numerical failure, with diagnostics available to the caller."""

    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identifier(value):
    return type(value) is str and bool(value.strip())


def _finite_json(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_finite_json(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _finite_json(item) for key, item in value.items())
    return False


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _probability(value):
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


def _key(row):
    return row["childId"], row["tokenId"]


def _canonical_input(payload):
    _require(type(payload) is dict and set(payload) == {"children", "selectedTokens", "rows"},
             "input requires exactly children, selectedTokens and rows")
    children = payload["children"]
    _require(type(children) is list and bool(children), "children requires a nonempty explicit roster")
    child_ids = set()
    for child in children:
        _require(type(child) is dict and set(child) == {"childId"}
                 and _identifier(child["childId"]), "children require only a nonblank string childId")
        _require(child["childId"] not in child_ids, "duplicate childId")
        child_ids.add(child["childId"])

    def roster(rows, label, fields):
        _require(type(rows) is list, f"{label} requires a list")
        keys = set()
        for row in rows:
            _require(type(row) is dict and set(row) == fields, f"invalid {label} fields")
            _require(_identifier(row["childId"]) and _identifier(row["tokenId"]),
                     f"invalid {label} identity")
            _require(row["childId"] in child_ids, f"unknown child in {label}")
            _require(_key(row) not in keys, f"duplicate {label} identity")
            keys.add(_key(row))
        return keys

    selected = roster(payload["selectedTokens"], "selectedTokens", {"childId", "tokenId"})
    row_keys = roster(payload["rows"], "rows", {"childId", "tokenId", "retainedProbability",
                                              "positiveVotes", "negativeVotes"})
    _require(selected == row_keys, "rows must match selectedTokens exactly")
    _require({key[0] for key in selected} == child_ids, "every selected child requires tokens")
    for row in payload["rows"]:
        probability = row["retainedProbability"]
        _require(_probability(probability), "retainedProbability must be finite in [0,1]")
        counts = row["positiveVotes"], row["negativeVotes"]
        _require(all(type(count) is int and count >= 0 for count in counts) and sum(counts) > 0,
                 "votes require nonnegative integer counts and positive n")
    _require(sum(row["positiveVotes"] for row in payload["rows"]) > 0
             and sum(row["negativeVotes"] for row in payload["rows"]) > 0,
             "fitting requires both vote classes")
    canonical = copy.deepcopy(payload)
    canonical["children"].sort(key=lambda row: row["childId"])
    canonical["selectedTokens"].sort(key=_key)
    canonical["rows"].sort(key=_key)
    for row in canonical["rows"]:
        value = float(row["retainedProbability"])
        row["retainedProbability"] = value if value else 0.0
    return canonical


def _objective(parameters, design, targets, weights):
    logits = design @ parameters
    probabilities = expit(logits)
    objective = float(np.dot(weights, np.logaddexp(0, logits) - targets * logits)
                      + 0.001 / 2 * parameters[1] ** 2)
    gradient = design.T @ (weights * (probabilities - targets))
    gradient[1] += 0.001 * parameters[1]
    hessian = design.T @ ((weights * probabilities * (1 - probabilities))[:, None] * design)
    hessian[1, 1] += 0.001
    if not all(np.all(np.isfinite(value)) for value in (objective, gradient, hessian)):
        raise CalibrationFitError("nonfinite objective, gradient or Hessian", {"reason": "nonfinite_numeric"})
    return objective, gradient, hessian


def _diagnostics(objective, gradient, trace):
    return {"objective": objective, "gradient": gradient.tolist(),
            "gradientInfinityNorm": float(np.max(np.abs(gradient))),
            "newtonSteps": len(trace), "steps": trace}


def _newton(design, targets, weights, intercept):
    parameters = np.array([intercept, 0.0], dtype=np.float64)
    trace = []
    for iteration in range(101):
        objective, gradient, hessian = _objective(parameters, design, targets, weights)
        diagnostics = _diagnostics(objective, gradient, trace)
        if diagnostics["gradientInfinityNorm"] <= 1e-8:
            return parameters, diagnostics
        if iteration == 100:
            raise CalibrationFitError("Newton iteration budget exhausted", diagnostics)
        try:
            direction = cho_solve(cho_factor(hessian, lower=True, check_finite=True), -gradient,
                                  check_finite=True)
        except (ValueError, np.linalg.LinAlgError) as error:
            raise CalibrationFitError("failed Hessian Cholesky solve", diagnostics) from error
        if not np.all(np.isfinite(direction)):
            raise CalibrationFitError("nonfinite Newton direction", diagnostics)
        directional = float(np.dot(gradient, direction))
        if not math.isfinite(directional) or directional >= 0:
            raise CalibrationFitError("Newton direction does not descend", diagnostics)
        for backtracks in range(50):
            step = 0.5 ** backtracks
            trial = parameters + step * direction
            trial_objective, trial_gradient, _ = _objective(trial, design, targets, weights)
            trial_norm = float(np.max(np.abs(trial_gradient)))
            armijo = trial_objective <= objective + 1e-4 * step * directional
            roundoff = (trial_objective <= objective + 16 * np.finfo(np.float64).eps * max(1, abs(objective))
                        and trial_norm < diagnostics["gradientInfinityNorm"])
            if armijo or roundoff:
                trace.append({"newtonStep": iteration + 1, "backtracks": backtracks,
                              "stepSize": step, "acceptance": "armijo" if armijo else "roundoff",
                              "objective": trial_objective, "gradientInfinityNorm": trial_norm})
                parameters = trial
                break
        else:
            raise CalibrationFitError("Armijo/roundoff line search exhausted", diagnostics)
    raise AssertionError("unreachable Newton exit")


def fit_calibration(payload):
    """Fit only caller-supplied complete child/token rows; malformed input fails."""
    canonical = _canonical_input(payload)
    rows = canonical["rows"]
    probabilities = np.asarray([row["retainedProbability"] for row in rows], dtype=np.float64)
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    logits = np.log(clipped) - np.log1p(-clipped)
    mean, std = float(logits.mean()), float(logits.std(ddof=0))
    scale = 1.0 if std < 1e-6 else std
    totals = {child["childId"]: 0 for child in canonical["children"]}
    for row in rows:
        totals[row["childId"]] += row["positiveVotes"] + row["negativeVotes"]
    weights = np.asarray([(row["positiveVotes"] + row["negativeVotes"]) /
                          totals[row["childId"]] / len(totals) for row in rows], dtype=np.float64)
    targets = np.asarray([row["positiveVotes"] / (row["positiveVotes"] + row["negativeVotes"])
                          for row in rows], dtype=np.float64)
    weighted_mean = float(np.dot(weights, targets))
    prior = float(np.clip(weighted_mean, 1e-6, 1 - 1e-6))
    intercept = math.log(prior) - math.log1p(-prior)
    design = np.column_stack((np.ones(len(rows), dtype=np.float64), (logits - mean) / scale))
    parameters, diagnostics = _newton(design, targets, weights, intercept)
    unconstrained = {"coefficients": {"intercept": float(parameters[0]), "slope": float(parameters[1])},
                     "diagnostics": diagnostics}
    boundary = bool(parameters[1] < 0)
    if boundary:
        parameters = np.array([intercept, 0.0], dtype=np.float64)
    objective, gradient, _ = _objective(parameters, design, targets, weights)
    projected_gradient = gradient.copy()
    if parameters[1] == 0:
        projected_gradient[1] = min(float(gradient[1]), 0.0)
    projected = {"objective": objective, "gradient": gradient.tolist(),
                 "projectedGradient": projected_gradient.tolist(),
                 "projectedGradientInfinityNorm": float(np.max(np.abs(projected_gradient)))}
    if projected["projectedGradientInfinityNorm"] > 1e-8:
        raise CalibrationFitError("projected stationarity gate failed", {
            "unconstrained": unconstrained, "boundaryApplied": boundary, "projected": projected})
    coefficients = {"intercept": float(parameters[0]), "slope": float(parameters[1])}
    control = {"schemaVersion": 1,
            "status": "supplied_input_fit_preparation_not_study_declaration",
            "researchOnly": True, "clinicalUseEligible": False,
            "learnerFeedbackEligible": False, "productionUseEligible": False,
            "fullChildDenominator": len(totals), "selectedTokenDenominator": len(rows),
            "canonicalInput": canonical, "inputDigest": _digest(canonical),
            "membershipDigest": _digest({key: canonical[key] for key in ("children", "selectedTokens")}),
            "digestFormat": _DIGEST_FORMAT,
            "source": {"module": "r_confirmatory.calibrate",
                       "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "dependencies": {"python": platform.python_version(), "numpy": np.__version__,
                             "scipy": scipy.__version__, "dtype": "float64"},
            "recipe": copy.deepcopy(_RECIPE),
            "initialization": {"weightedTargetMean": weighted_mean, "clippedWeightedTargetMean": prior,
                               "intercept": intercept, "slope": 0.0},
            "coefficients": coefficients,
            "unconstrained": unconstrained, "boundaryApplied": boundary, "projected": projected,
            "transform": {"logitMean": mean, "logitPopulationStd": std,
                          "logitScale": scale, "inputClip": 1e-6},
            "weights": [{"childId": row["childId"], "tokenId": row["tokenId"],
                         "weight": float(weight)} for row, weight in zip(rows, weights)],
            "fittedPredictions": []}
    control["fittedPredictions"] = [
        {"childId": row["childId"], "tokenId": row["tokenId"], "probability": probability}
        for row, probability in zip(rows, predict_calibration(control, probabilities.tolist()))]
    return control


def predict_calibration(saved_control, probabilities):
    """Apply fixed saved parameters; an independent audit must bind the full receipt."""
    _require(type(saved_control) is dict and set(saved_control) == _CONTROL_FIELDS
             and _finite_json(saved_control), "saved control requires the exact finite JSON receipt")
    _require(type(saved_control["schemaVersion"]) is int and saved_control["schemaVersion"] == 1
             and saved_control["status"] == "supplied_input_fit_preparation_not_study_declaration",
             "invalid saved control schema/status")
    _require(saved_control["researchOnly"] is True
             and all(saved_control[key] is False for key in
                     ("clinicalUseEligible", "learnerFeedbackEligible", "productionUseEligible")),
             "saved control must remain research only")
    _require(saved_control["recipe"] == _RECIPE, "saved control recipe mismatch")
    transform, coefficients = saved_control["transform"], saved_control["coefficients"]
    _require(type(coefficients) is dict and set(coefficients) == {"intercept", "slope"}
             and all(_finite_number(value) for value in coefficients.values())
             and coefficients["slope"] >= 0, "invalid saved coefficients")
    _require(type(transform) is dict and set(transform) == {
        "logitMean", "logitPopulationStd", "logitScale", "inputClip"}
        and all(_finite_number(value) for value in transform.values())
        and transform["inputClip"] == 1e-6 and transform["logitPopulationStd"] >= 0
        and transform["logitScale"] == (1.0 if transform["logitPopulationStd"] < 1e-6
                                        else transform["logitPopulationStd"]),
        "invalid saved transform")
    _require(type(probabilities) is list, "probabilities requires a list")
    _require(all(_probability(value) for value in probabilities), "probabilities must be finite in [0,1]")
    clipped = np.clip(np.asarray(probabilities, dtype=np.float64), 1e-6, 1 - 1e-6)
    with np.errstate(over="raise", divide="raise", invalid="raise"):
        try:
            standardized = (np.log(clipped) - np.log1p(-clipped) - transform["logitMean"]) / transform["logitScale"]
            logits = coefficients["intercept"] + coefficients["slope"] * standardized
        except FloatingPointError as error:
            raise ValueError("saved control produced nonfinite logits") from error
    _require(np.all(np.isfinite(logits)), "saved control produced nonfinite logits")
    return expit(logits).tolist()
