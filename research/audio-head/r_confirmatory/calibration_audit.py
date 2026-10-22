"""Independent scalar replay of a supplied calibration; no optimizer/model imports."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


TOLERANCE = 1e-10
STATIONARITY_GATE = 1e-8

EXPECTED_RECIPE = {
    'inputProbability': 'retained_p0_plus_p1', 'positiveVotes': 'derhotic_n_minus_k', 'negativeVotes': 'rhotic_k',
    'targetProbability': 'positiveVotes/(positiveVotes+negativeVotes)', 'outputProbabilityOrder': ['derhotic', 'rhotic'],
    'weightRule': 'n_i/sum_child_n/child_count', 'moments': 'unweighted_row_float64_population',
    'standardDeviationFloor': 1e-6, 'inputClip': 1e-6, 'priorClip': 1e-6, 'slopeRidge': .001, 'interceptPenalty': 0.0,
    'optimizer': 'damped_newton_analytic_hessian_scipy_cholesky', 'gradientInfinityNormGate': 1e-8,
    'maximumNewtonSteps': 100, 'maximumBacktrackingSteps': 50, 'armijoCoefficient': 1e-4,
    'backtrackingFactor': .5, 'roundoffEpsilonMultiplier': 16, 'roundoffRequiresStrictGradientDecrease': True,
    'negativeSlopeBoundary': 'zero_slope_clipped_weighted_prior_logit', 'zeroSlopeProjectedGradient': 'min(slope_gradient,0)',
}
CONTROL_FIELDS = {'schemaVersion', 'status', 'researchOnly', 'clinicalUseEligible', 'learnerFeedbackEligible',
                  'productionUseEligible', 'fullChildDenominator', 'selectedTokenDenominator', 'canonicalInput',
                  'inputDigest', 'membershipDigest', 'digestFormat', 'source', 'dependencies', 'recipe',
                  'initialization', 'coefficients', 'transform', 'weights', 'unconstrained', 'boundaryApplied',
                  'projected', 'fittedPredictions'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _close(actual, expected, label):
    _require(_finite(actual)
             and math.isclose(actual, expected, abs_tol=TOLERANCE, rel_tol=TOLERANCE),
             'Calibration replay differs: ' + label)


def _sigmoid(value):
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def audit_calibration(payload, control):
    """Independently check moments, child weights, solution and probability replay.

    Uses scalar math/fsum, not the NumPy/SciPy fitter. This verifies supplied
    artifacts only; it cannot verify corpus membership, ratings or fit execution.
    """
    _require(type(payload) is dict and set(payload) == {'children', 'selectedTokens', 'rows'},
             'Invalid audit input')
    _require(type(payload['children']) is list and bool(payload['children']), 'Missing children')
    children = []
    for child in payload['children']:
        _require(type(child) is dict and set(child) == {'childId'}
                 and type(child['childId']) is str and bool(child['childId'].strip()), 'Invalid child')
        children.append(child['childId'])
    _require(len(children) == len(set(children)), 'Duplicate child')
    children.sort()
    keys = []
    _require(type(payload['selectedTokens']) is list, 'Invalid selection')
    for selected in payload['selectedTokens']:
        _require(type(selected) is dict and set(selected) == {'childId', 'tokenId'}, 'Invalid selected row')
        _require(all(type(selected[k]) is str and selected[k].strip() for k in ('childId', 'tokenId')),
                 'Invalid selected identity')
        keys.append((selected['childId'], selected['tokenId']))
    _require(len(keys) == len(set(keys)) and {key[0] for key in keys} == set(children), 'Incomplete selection')
    keys.sort()
    _require(type(payload['rows']) is list, 'Invalid fitting rows')
    rows = []
    for row in payload['rows']:
        _require(type(row) is dict and set(row) == {'childId', 'tokenId', 'retainedProbability',
                                                  'positiveVotes', 'negativeVotes'}, 'Invalid fitting row')
        _require(all(type(row[k]) is str and row[k].strip() for k in ('childId', 'tokenId')), 'Invalid row identity')
        _require(_finite(row['retainedProbability']) and 0 <= row['retainedProbability'] <= 1,
                 'Invalid retained probability')
        _require(all(type(row[k]) is int and row[k] >= 0 for k in ('positiveVotes', 'negativeVotes'))
                 and row['positiveVotes'] + row['negativeVotes'] > 0, 'Invalid votes')
        rows.append({**row, 'retainedProbability': float(row['retainedProbability']) or 0.0})
    rows.sort(key=lambda row: (row['childId'], row['tokenId']))
    _require([(row['childId'], row['tokenId']) for row in rows] == keys, 'Fitting roster differs')
    _require(sum(row['positiveVotes'] for row in rows) > 0 and sum(row['negativeVotes'] for row in rows) > 0,
             'Both fitting vote classes required')
    canonical = {'children': [{'childId': child} for child in children],
                 'selectedTokens': [{'childId': child, 'tokenId': token} for child, token in keys], 'rows': rows}
    totals = {child: sum(row['positiveVotes'] + row['negativeVotes'] for row in rows if row['childId'] == child)
              for child in children}
    weights = [(row['positiveVotes'] + row['negativeVotes']) / totals[row['childId']] / len(children) for row in rows]
    targets = [row['positiveVotes'] / (row['positiveVotes'] + row['negativeVotes']) for row in rows]
    logits = []
    for row in rows:
        p = min(max(row['retainedProbability'], 1e-6), 1 - 1e-6)
        logits.append(math.log(p) - math.log1p(-p))
    mean = math.fsum(logits) / len(logits)
    std = math.sqrt(math.fsum((value - mean) ** 2 for value in logits) / len(logits))
    scale = 1.0 if std < 1e-6 else std
    _require(type(control) is dict and set(control) == CONTROL_FIELDS, 'Invalid saved control')
    _require(type(control['schemaVersion']) is int and control['schemaVersion'] == 1
             and control['status'] == 'supplied_input_fit_preparation_not_study_declaration', 'Invalid control version/status')
    _require(control['researchOnly'] is True and all(control[key] is False for key in
             ('clinicalUseEligible', 'learnerFeedbackEligible', 'productionUseEligible')), 'Invalid eligibility flags')
    _require(_digest(control['recipe']) == _digest(EXPECTED_RECIPE), 'Changed calibration recipe')
    _require(type(control['fullChildDenominator']) is int and control['fullChildDenominator'] == len(children)
             and type(control['selectedTokenDenominator']) is int and control['selectedTokenDenominator'] == len(rows),
             'Changed fitting denominator')
    _require(_digest(control['canonicalInput']) == _digest(canonical) and control['inputDigest'] == _digest(canonical)
             and control['membershipDigest'] == _digest({key: canonical[key] for key in ('children', 'selectedTokens')})
             and control['digestFormat'] == 'sha256_utf8_json_sort_keys_compact_ensure_ascii_false', 'Changed input binding')
    source = control['source']
    _require(type(source) is dict and set(source) == {'module', 'sha256'}
             and source['module'] == 'r_confirmatory.calibrate'
             and source['sha256'] == hashlib.sha256(Path(__file__).with_name('calibrate.py').read_bytes()).hexdigest(),
             'Changed calibration source binding')
    dependencies = control['dependencies']
    _require(type(dependencies) is dict and set(dependencies) == {'python', 'numpy', 'scipy', 'dtype'}
             and dependencies['dtype'] == 'float64'
             and all(type(dependencies[key]) is str and dependencies[key].strip() for key in ('python', 'numpy', 'scipy')),
             'Invalid dependency receipt')
    transform = control.get('transform')
    _require(type(transform) is dict and set(transform) == {'logitMean', 'logitPopulationStd', 'logitScale', 'inputClip'},
             'Invalid saved transform')
    for field, expected in [('logitMean', mean), ('logitPopulationStd', std), ('logitScale', scale), ('inputClip', 1e-6)]:
        _close(transform[field], expected, field)
    saved_weights = control.get('weights')
    _require(type(saved_weights) is list and len(saved_weights) == len(rows), 'Missing saved weights')
    for saved, row, expected in zip(saved_weights, rows, weights):
        _require(type(saved) is dict and set(saved) == {'childId', 'tokenId', 'weight'}
                 and (saved['childId'], saved['tokenId']) == (row['childId'], row['tokenId']), 'Weight identity differs')
        _close(saved['weight'], expected, 'child-balanced weight')
    standardized = [(value - mean) / scale for value in logits]

    def replay(coefficients):
        _require(type(coefficients) is dict and set(coefficients) == {'intercept', 'slope'}
                 and all(_finite(value) for value in coefficients.values()),
                 'Invalid coefficients')
        intercept, slope = coefficients['intercept'], coefficients['slope']
        z = [intercept + slope * value for value in standardized]
        _require(all(math.isfinite(value) for value in z), 'Nonfinite replay logits')
        predictions = [_sigmoid(value) for value in z]
        # Stable scalar softplus avoids overflow independently of NumPy logaddexp.
        try:
            objective = math.fsum(weight * (max(value, 0) + math.log1p(math.exp(-abs(value))) - target * value)
                                  for weight, target, value in zip(weights, targets, z)) + .001 / 2 * slope ** 2
            residuals = [weight * (prediction - target) for weight, prediction, target in zip(weights, predictions, targets)]
            gradient = [math.fsum(residuals), math.fsum(r * x for r, x in zip(residuals, standardized)) + .001 * slope]
        except (OverflowError, ValueError) as error:
            raise ValueError('Unrepresentable numerical replay') from error
        _require(all(math.isfinite(value) for value in [objective, *gradient, *predictions]), 'Nonfinite replay')
        return objective, gradient, predictions

    _require(type(control.get('unconstrained')) is dict and set(control['unconstrained']) == {'coefficients', 'diagnostics'}, 'Missing unconstrained solution')
    unconstrained = control['unconstrained']
    raw_objective, raw_gradient, _ = replay(unconstrained.get('coefficients'))
    raw_norm = max(abs(value) for value in raw_gradient)
    _require(raw_norm <= STATIONARITY_GATE + TOLERANCE, 'Unconstrained solution is not stationary')
    diagnostic = unconstrained.get('diagnostics')
    _require(type(diagnostic) is dict and set(diagnostic) == {'objective', 'gradient', 'gradientInfinityNorm',
                                                             'newtonSteps', 'steps'}, 'Missing unconstrained diagnostics')
    _require(type(diagnostic['newtonSteps']) is int and 0 <= diagnostic['newtonSteps'] <= 100
             and type(diagnostic['steps']) is list and len(diagnostic['steps']) == diagnostic['newtonSteps'],
             'Invalid Newton trace size')
    for index, step in enumerate(diagnostic['steps'], 1):
        _require(type(step) is dict and set(step) == {'newtonStep', 'backtracks', 'stepSize', 'acceptance',
                                                    'objective', 'gradientInfinityNorm'}, 'Invalid Newton step')
        _require(type(step['newtonStep']) is int and step['newtonStep'] == index
                 and type(step['backtracks']) is int and 0 <= step['backtracks'] < 50
                 and step['stepSize'] == .5 ** step['backtracks']
                 and step['acceptance'] in ('armijo', 'roundoff'), 'Invalid Newton trace settings')
        _require(all(_finite(step[key]) and step[key] >= 0
                     for key in ('objective', 'gradientInfinityNorm')), 'Invalid Newton trace numbers')
    _close(diagnostic.get('objective'), raw_objective, 'unconstrained objective')
    _close(diagnostic.get('gradientInfinityNorm'), raw_norm, 'unconstrained stationarity')
    _require(type(diagnostic.get('gradient')) is list and len(diagnostic['gradient']) == 2, 'Missing gradient')
    for actual, expected in zip(diagnostic['gradient'], raw_gradient): _close(actual, expected, 'unconstrained gradient')
    boundary = unconstrained['coefficients']['slope'] < 0
    _require(type(control.get('boundaryApplied')) is bool and control['boundaryApplied'] == boundary, 'Boundary decision differs')
    weighted_mean = math.fsum(w * target for w, target in zip(weights, targets))
    prior = min(max(weighted_mean, 1e-6), 1 - 1e-6)
    initialization = control['initialization']
    _require(type(initialization) is dict and set(initialization) == {'weightedTargetMean', 'clippedWeightedTargetMean',
                                                                    'intercept', 'slope'}, 'Invalid initialization')
    for key, expected in [('weightedTargetMean', weighted_mean), ('clippedWeightedTargetMean', prior),
                          ('intercept', math.log(prior) - math.log1p(-prior)), ('slope', 0.0)]:
        _close(initialization[key], expected, 'initialization:' + key)
    expected_coefficients = {'intercept': math.log(prior) - math.log1p(-prior), 'slope': 0.0} if boundary else unconstrained['coefficients']
    coefficients = control.get('coefficients')
    objective, gradient, predictions = replay(coefficients)
    for key, expected in expected_coefficients.items(): _close(coefficients[key], expected, key)
    _require(coefficients['slope'] >= 0, 'Negative monotonic slope')
    projected = [gradient[0], min(gradient[1], 0.0) if coefficients['slope'] == 0 else gradient[1]]
    norm = max(abs(value) for value in projected)
    _require(norm <= STATIONARITY_GATE + TOLERANCE, 'Projected solution is not stationary')
    saved_projected = control.get('projected')
    _require(type(saved_projected) is dict, 'Missing projected diagnostics')
    _close(saved_projected.get('objective'), objective, 'projected objective')
    _close(saved_projected.get('projectedGradientInfinityNorm'), norm, 'projected stationarity')
    for name, expected in [('gradient', gradient), ('projectedGradient', projected)]:
        _require(type(saved_projected.get(name)) is list and len(saved_projected[name]) == 2, 'Missing projected gradient')
        for actual, value in zip(saved_projected[name], expected): _close(actual, value, name)
    saved_predictions = control['fittedPredictions']
    _require(type(saved_predictions) is list and len(saved_predictions) == len(rows), 'Missing predictions')
    for saved, row, expected in zip(saved_predictions, rows, predictions):
        _require(type(saved) is dict and set(saved) == {'childId', 'tokenId', 'probability'}
                 and (saved['childId'], saved['tokenId']) == (row['childId'], row['tokenId']), 'Prediction identity differs')
        _close(saved['probability'], expected, 'prediction')
    return {'schemaVersion': 1, 'outcome': 'verified' , 'researchOnly': True,
            'learnerFeedbackEligible': False, 'clinicalUseEligible': False, 'productionUseEligible': False,
            'inputSha256': _digest(canonical), 'controlSha256': _digest(control), 'objective': objective, 'projectedGradientInfinityNorm': norm,
            'predictions': predictions, 'fullChildDenominator': len(children), 'selectedTokenDenominator': len(rows),
            'auditorSourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'numericTolerance': {'absolute': TOLERANCE, 'relative': TOLERANCE},
            'limitations': ['Supplied-artifact scalar replay, not verification of corpus membership or original ratings.',
                            'Does not rerun fitting or verify each historical optimizer step.',
                            'Not a study declaration, qualified statistical review or learner calibration.']}
