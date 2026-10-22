"""Pure float64 fitting and fixed confirmation statistics for quality research.

Callers own source/partition/phase barriers and one-thread BLAS configuration.
Selection accepts fit and selection data only; refitting is an explicit call.
"""
import hashlib

import numpy as np

GRID = (0.01, 0.1, 1.0, 10.0)
POLICY = {
    'version': 'nisqa-quality-ridge-v1', 'dtype': 'float64', 'blasThreads': 1,
    'objective': 'sum((Y-intercept-X@B)**2)/(5*n) + lambda*sum(B**2)',
    'solvePenalty': '5*n*lambda', 'interceptPenalized': False,
    'lambdaGrid': list(GRID), 'selection': 'equal-weight five-dimension MAE; larger lambda on exact ties',
    'standardization': 'fit-only population mean/std; exactly zero std uses scale one and output zero',
    'nonfitFeatureBounds': 'clamp standardized values to saved fit-column min/max at SSL-before-PCA and final candidate/acoustic scaling; never clamp predictions',
    'pca': {'components': 16, 'method': 'compact SVD of fit-only standardized SSL1536',
            'rankThreshold': 'max(shape)*float64_eps*largest_singular_value',
            'sign': 'first maximum-absolute loading nonnegative', 'whitening': False},
    'features': {'candidate': 22, 'acoustic': 6}, 'targets': 'finite n x 5 in [1,5]',
    'finalPCScoreScaling': 'unit population variance; effective whitening intended after unwhitened PCA projection',
    'predictions': 'finite unbounded; no clipping, mapping or calibration',
    'macroRMSE': 'arithmetic mean of five dimension RMSEs',
    'bootstrap': {'generator': 'PCG64', 'seed': 27092026, 'draws': 10000,
                  'components': 40, 'oneRecordingPerComponent': True,
                  'indicesHash': 'SHA256 little-endian int64 C-order common indices',
                  'quantiles': [0.025, 0.975], 'quantileMethod': 'linear'},
    'conditionMean': 'fit five target means separately for phone and Skype; refit only on authorized160',
    'screen': {'maeImprovementThreeControls': 0.05, 'upperAllIntervalsStrictlyBelow': 0,
               'maxDimensionWorseningVsPooledMean': 0.10, 'maxCaptureWorseningVsConditionMean': 0},
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _matrix(value, *, columns=None, rows=None):
    original = np.asarray(value)
    _require(original.ndim == 2 and original.shape[0] > 0 and original.shape[1] > 0
             and original.dtype.kind in 'fiu', 'Expected positive real numeric matrix')
    result = np.asarray(original, dtype=np.float64)
    _require(np.isfinite(result).all() and (columns is None or result.shape[1] == columns)
             and (rows is None or result.shape[0] == rows), 'Matrix shape or finiteness differs')
    return result


def _targets(value, *, rows=None):
    result = _matrix(value, columns=5, rows=rows)
    _require(np.all((result >= 1) & (result <= 5)), 'Targets must lie in [1,5]')
    return result


def fit_standardization(features):
    x = _matrix(features)
    # Exact repeated values have mathematical std zero even if reduction
    # roundoff would make a repeated decimal's computed std slightly positive.
    constant = np.all(x == x[0], axis=0)
    mean, std = x.mean(axis=0), x.std(axis=0, ddof=0)
    mean[constant], std[constant] = x[0, constant], 0.
    constant = std == 0
    scale = np.where(constant, 1., std)
    _require(np.isfinite(mean).all() and np.isfinite(scale).all(), 'Standardization overflow')
    standardized = (x - mean) / scale
    standardized[:, constant] = 0.
    _require(np.isfinite(standardized).all(), 'Standardization overflow')
    return {'mean': mean, 'scale': scale, 'constant': constant, 'fitRows': len(x), 'ddof': 0,
            'fitMin': standardized.min(axis=0), 'fitMax': standardized.max(axis=0)}


def standardize(features, state, *, return_diagnostics=False):
    x = _matrix(features, columns=len(state['mean']))
    result = (x - state['mean']) / state['scale']
    result[:, state['constant']] = 0.
    _require(np.isfinite(result).all(), 'Standardized features are nonfinite')
    changed = (result < state['fitMin']) | (result > state['fitMax'])
    result = np.clip(result, state['fitMin'], state['fitMax'])
    _require(np.isfinite(result).all(), 'Bounded standardized features are nonfinite')
    diagnostics = {'totalClampCount': int(changed.sum()),
                   'perRowClampCounts': changed.sum(axis=1).tolist(),
                   'perColumnClampCounts': changed.sum(axis=0).tolist(),
                   'constantColumns': np.flatnonzero(state['constant']).tolist(),
                   'constantInputDifferenceCount': int(np.count_nonzero((x != state['mean'])[:, state['constant']]))}
    return (result, diagnostics) if return_diagnostics else result


def fit_pca(ssl):
    x = _matrix(ssl, columns=1536)
    scaler = fit_standardization(x)
    standardized = standardize(x, scaler)
    _, singular, components = np.linalg.svd(standardized, full_matrices=False)
    threshold = max(standardized.shape) * np.finfo(np.float64).eps * singular[0]
    rank = int(np.count_nonzero(singular > threshold))
    _require(rank >= 16, 'Fit SSL numerical rank is below sixteen')
    components = components[:16].copy()
    anchors = np.argmax(np.abs(components), axis=1)
    components *= np.where(components[np.arange(16), anchors] < 0, -1., 1.)[:, None]
    return {'scaler': scaler, 'singularValues': singular, 'components': components,
            'numericalRank': rank, 'rankThreshold': float(threshold), 'signAnchors': anchors,
            'fitShape': list(x.shape)}


def pca_transform(ssl, state, *, return_diagnostics=False):
    standardized, diagnostics = standardize(_matrix(ssl, columns=1536), state['scaler'], return_diagnostics=True)
    result = standardized @ state['components'].T
    _require(result.shape[1] == 16 and np.isfinite(result).all(), 'Invalid PCA projection')
    return (result, diagnostics) if return_diagnostics else result


def fit_transform(ssl, scalars, *, kind='candidate'):
    raw = _matrix(scalars, columns=6)
    _require(kind in ('candidate', 'acoustic'), 'Unknown feature recipe')
    pca = None
    if kind == 'candidate':
        source = _matrix(ssl, columns=1536, rows=len(raw))
        pca = fit_pca(source)
        joined = np.column_stack((pca_transform(source, pca), raw))
    else:
        joined = raw
    state = {'kind': kind, 'sslPca': pca, 'joinedScaler': fit_standardization(joined)}
    return standardize(joined, state['joinedScaler']), state


def transform_features(ssl, scalars, state, *, return_diagnostics=False):
    raw = _matrix(scalars, columns=6)
    _require(state['kind'] in ('candidate', 'acoustic'), 'Unknown feature recipe')
    ssl_diagnostics = None
    joined = raw
    if state['kind'] == 'candidate':
        projected, ssl_diagnostics = pca_transform(_matrix(ssl, columns=1536, rows=len(raw)), state['sslPca'], return_diagnostics=True)
        joined = np.column_stack((projected, raw))
    result, final_diagnostics = standardize(joined, state['joinedScaler'], return_diagnostics=True)
    diagnostics = {'sslBeforePca': ssl_diagnostics, 'finalStandardization': final_diagnostics}
    return (result, diagnostics) if return_diagnostics else result


def fit_ridge(features, targets, ridge_lambda):
    x = _matrix(features)
    y = _targets(targets, rows=len(x))
    _require(type(ridge_lambda) in (int, float) and ridge_lambda in GRID, 'Lambda outside declared grid')
    x_mean, y_mean = x.mean(axis=0), y.mean(axis=0)
    centered_x, centered_y = x - x_mean, y - y_mean
    penalty = 5 * len(x) * float(ridge_lambda)
    gram = centered_x.T @ centered_x + penalty * np.eye(x.shape[1])
    rhs = centered_x.T @ centered_y
    _require(np.isfinite(gram).all() and np.isfinite(rhs).all(), 'Ridge system overflow')
    coefficients = np.linalg.solve(gram, rhs)
    intercept = y_mean - x_mean @ coefficients
    _require(np.isfinite(coefficients).all() and np.isfinite(intercept).all(), 'Nonfinite ridge solution')
    residual = y - intercept - x @ coefficients
    objective = float(np.sum(residual ** 2) / (5 * len(x)) + ridge_lambda * np.sum(coefficients ** 2))
    condition = float(np.linalg.cond(gram))
    _require(np.isfinite(objective) and np.isfinite(condition), 'Nonfinite ridge diagnostics')
    return {'coefficients': coefficients, 'intercept': intercept, 'xMean': x_mean, 'yMean': y_mean,
            'lambda': float(ridge_lambda), 'penalty': penalty, 'fitRows': len(x),
            'centeredRank': int(np.linalg.matrix_rank(centered_x)), 'systemCondition': condition,
            'objective': objective, 'solver': 'numpy.linalg.solve'}


def predict(features, state):
    x = _matrix(features, columns=state['coefficients'].shape[0])
    predictions = x @ state['coefficients'] + state['intercept']
    _require(predictions.shape == (len(x), 5) and np.isfinite(predictions).all(), 'Nonfinite ridge predictions')
    return predictions


def fitted_mean(fit_targets, rows):
    y = _targets(fit_targets)
    _require(type(rows) is int and rows > 0, 'Positive prediction row count required')
    return np.tile(y.mean(axis=0), (rows, 1))


def _conditions(values, rows):
    _require(isinstance(values, (list, tuple)) and len(values) == rows
             and all(v in ('phone', 'Skype') for v in values), 'phone/Skype capture conditions required')
    return np.array(values)


def condition_mean(targets, capture_conditions):
    y = _targets(targets)
    conditions = _conditions(capture_conditions, len(y))
    _require(all(np.any(conditions == name) for name in ('phone', 'Skype')), 'Both fitting captures required')
    return {'means': {name: y[conditions == name].mean(axis=0) for name in ('phone', 'Skype')},
            'fitCounts': {name: int(np.count_nonzero(conditions == name)) for name in ('phone', 'Skype')}}


def predict_condition_mean(state, capture_conditions):
    _require(isinstance(capture_conditions, (list, tuple)) and len(capture_conditions) > 0, 'Positive capture prediction rows required')
    conditions = _conditions(capture_conditions, len(capture_conditions))
    predictions = np.vstack([state['means'][name] for name in conditions])
    _require(predictions.shape == (len(conditions), 5) and np.isfinite(predictions).all(), 'Invalid condition means')
    return predictions


def metrics(targets, predictions):
    y = _targets(targets)
    p = _matrix(predictions, columns=5, rows=len(y))
    errors = p - y
    absolute = np.abs(errors)
    mae, rmse = absolute.mean(axis=0), np.sqrt(np.mean(errors ** 2, axis=0))
    correlations = []
    for column in range(5):
        a, b = y[:, column] - y[:, column].mean(), p[:, column] - p[:, column].mean()
        denominator = np.linalg.norm(a) * np.linalg.norm(b)
        constant = np.all(y[:, column] == y[0, column]) or np.all(p[:, column] == p[0, column])
        correlations.append(None if constant or denominator == 0 else float(np.dot(a, b) / denominator))
    _require(np.isfinite(mae).all() and np.isfinite(rmse).all()
             and all(v is None or np.isfinite(v) for v in correlations), 'Nonfinite error metrics')
    return {'dimensionMAE': mae.tolist(), 'dimensionRMSE': rmse.tolist(),
            'macroMAE': float(mae.mean()), 'macroRMSE': float(rmse.mean()),
            'pearson': correlations, 'absoluteErrors': absolute.tolist(), 'rows': len(y)}


def select_model(fit_ssl, fit_scalars, fit_targets, selection_ssl, selection_scalars,
                 selection_targets, *, fit_capture_conditions, selection_capture_conditions, kind='candidate'):
    """Fit four grid points using fit data only; select using selection MAE."""
    fit_x, transform = fit_transform(fit_ssl, fit_scalars, kind=kind)
    selection_x, clamp_diagnostics = transform_features(selection_ssl, selection_scalars, transform, return_diagnostics=True)
    fit_y = _targets(fit_targets, rows=len(fit_x))
    selection_y = _targets(selection_targets, rows=len(selection_x))
    _conditions(selection_capture_conditions, len(selection_y))
    grid = []
    for value in GRID:
        state = fit_ridge(fit_x, fit_y, value)
        predictions = predict(selection_x, state)
        grid.append({'lambda': value, 'model': state, 'predictions': predictions,
                     'metrics': metrics(selection_y, predictions)})
    chosen = min(range(4), key=lambda i: (grid[i]['metrics']['macroMAE'], -grid[i]['lambda']))
    condition = condition_mean(fit_y, fit_capture_conditions)
    return {'kind': kind, 'transform': transform, 'grid': grid,
            'selectedIndex': chosen, 'selectedLambda': grid[chosen]['lambda'],
            'selectionClampDiagnostics': clamp_diagnostics,
            'meanControlPredictions': fitted_mean(fit_y, len(selection_y)),
            'conditionMeanControl': condition,
            'conditionMeanControlPredictions': predict_condition_mean(condition, selection_capture_conditions)}


def refit_model(ssl, scalars, targets, ridge_lambda, *, kind='candidate'):
    """Explicit new fit; caller must enforce the frozen-lambda phase barrier."""
    x, transform = fit_transform(ssl, scalars, kind=kind)
    return {'kind': kind, 'transform': transform, 'model': fit_ridge(x, targets, ridge_lambda)}


def confirmation_report(targets, candidate, acoustic, mean, condition_mean_predictions, component_ids, capture_conditions):
    """Fixed paired 40-component bootstrap and prespecified continuation screen."""
    y = _targets(targets, rows=40)
    _require(isinstance(component_ids, (list, tuple)) and len(component_ids) == 40
             and all(isinstance(v, str) and v for v in component_ids) and len(set(component_ids)) == 40,
             'Forty distinct component IDs required')
    _require(isinstance(capture_conditions, (list, tuple)) and len(capture_conditions) == 40
             and capture_conditions.count('phone') == capture_conditions.count('Skype') == 20,
             'Balanced phone/Skype confirmation captures required')
    predictions = {name: _matrix(value, columns=5, rows=40) for name, value in
                   (('candidate', candidate), ('acoustic', acoustic), ('mean', mean), ('conditionMean', condition_mean_predictions))}
    report = {name: metrics(y, p) for name, p in predictions.items()}
    row_errors = {name: np.abs(p - y).mean(axis=1) for name, p in predictions.items()}
    indices = np.random.Generator(np.random.PCG64(27092026)).integers(0, 40, size=(10000, 40), dtype=np.int64)
    comparisons = {}
    for name in ('acoustic', 'mean', 'conditionMean'):
        delta = row_errors['candidate'] - row_errors[name]
        draws = delta[indices].mean(axis=1)
        interval = np.quantile(draws, [.025, .975], method='linear')
        comparisons[name] = {'macroMAEDifference': float(delta.mean()), 'pairedRowDifferences': delta.tolist(),
                             'interval95': interval.tolist()}
    captures = {}
    for name in ('phone', 'Skype'):
        mask = np.array([v == name for v in capture_conditions])
        captures[name] = {key: metrics(y[mask], p[mask]) for key, p in predictions.items()}
        captures[name]['candidateMinusConditionMeanMacroMAE'] = float((row_errors['candidate'] - row_errors['conditionMean'])[mask].mean())
    guards = {
        'improvesThreeControlsAtLeast005': all(v['macroMAEDifference'] <= -.05 for v in comparisons.values()),
        'allUpperIntervalsBelowZero': all(v['interval95'][1] < 0 for v in comparisons.values()),
        'noDimensionMoreThan010WorseThanMean': bool(np.all(np.array(report['candidate']['dimensionMAE'])
                                                        - np.array(report['mean']['dimensionMAE']) <= .10)),
        'bothCapturesNonpositiveVsConditionMean': all(v['candidateMinusConditionMeanMacroMAE'] <= 0 for v in captures.values()),
    }
    return {'models': report, 'comparisons': comparisons, 'captures': captures,
            'bootstrap': {'seed': 27092026, 'draws': 10000, 'indexShape': [10000, 40],
                          'indexDtype': '<i8', 'indicesSha256': hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest(),
                          'componentOrder': list(component_ids), 'quantileMethod': 'linear'},
            'guards': guards, 'passesContinuationScreen': all(guards.values()),
            'limitations': 'Finite sample; approximate publisher-code components, not verified independent people.'}
