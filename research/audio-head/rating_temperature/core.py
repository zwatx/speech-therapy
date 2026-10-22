"""One bounded inverse-temperature fit against five-rater soft targets."""
from numbers import Real

import numpy as np

LOWER_BETA = 0.05
UPPER_BETA = 20.0
BISECTION_ITERATIONS = 80


def normalized(probabilities):
    """Validate strictly positive N×3 distributions and normalize roundoff."""
    raw = np.asarray(probabilities)
    if raw.dtype.kind not in 'fiu' or raw.ndim != 2 or raw.shape[1] != 3 or not len(raw):
        raise ValueError('probabilities must be a nonempty numeric N×3 array')
    p = np.asarray(raw, dtype=np.float64)
    sums = p.sum(axis=1, keepdims=True)
    if not np.all(np.isfinite(p)) or np.any(p <= 0) or np.any(p > 1):
        raise ValueError('probabilities must be finite and in (0, 1]')
    if np.any(np.abs(sums - 1.0) > 1e-6):
        raise ValueError('probability rows must sum to 1 within 1e-6')
    return p / sums


def _beta(beta):
    if isinstance(beta, (bool, np.bool_)) or not isinstance(beta, Real):
        raise ValueError('beta must be a real number')
    beta = float(beta)
    if not np.isfinite(beta) or not LOWER_BETA <= beta <= UPPER_BETA:
        raise ValueError('beta must be finite and in [0.05, 20]')
    return beta


def _targets(counts, shape):
    raw = np.asarray(counts)
    if raw.dtype.kind not in 'fiu' or raw.shape != shape:
        raise ValueError('counts must be a numeric N×3 array matching probabilities')
    c = np.asarray(raw, dtype=np.float64)
    if (not np.all(np.isfinite(c)) or np.any(c < 0) or np.any(c > 5)
            or np.any(c != np.floor(c)) or np.any(c.sum(axis=1) != 5)):
        raise ValueError('counts must be nonnegative integers summing to five per row')
    return c / 5.0


def _logsoftmax(logp, beta):
    z = beta * logp
    z = z - z.max(axis=1, keepdims=True)
    return z - np.log(np.exp(z).sum(axis=1, keepdims=True))


def log_scaled(probabilities, beta):
    """Return finite log probabilities without clipping or exponential underflow."""
    p = normalized(probabilities)
    beta = _beta(beta)
    if beta == 1.0:
        return np.log(p)
    return _logsoftmax(np.log(p), beta)


def scaled(probabilities, beta):
    """Apply a bounded inverse temperature; identity is bitwise normalized p."""
    p = normalized(probabilities)
    beta = _beta(beta)
    if beta == 1.0:
        return p
    return np.exp(_logsoftmax(np.log(p), beta))


def _derivatives(logp, targets, beta):
    logq = _logsoftmax(logp, beta)
    q = np.exp(logq)
    expected = np.sum(q * logp, axis=1)
    loss = -np.mean(np.sum(targets * logq, axis=1))
    gradient = np.mean(expected - np.sum(targets * logp, axis=1))
    curvature = np.mean(np.sum(q * (logp - expected[:, None]) ** 2, axis=1))
    return float(loss), float(gradient), float(curvature)


def loss_derivatives(probabilities, counts, beta):
    """Return equal-position soft NLL, beta gradient, and beta curvature."""
    p = normalized(probabilities)
    return _derivatives(np.log(p), _targets(counts, p.shape), _beta(beta))


def fit(probabilities, counts):
    """Fit exactly one beta by deterministic bounded convex minimization.

    Returns a JSON-compatible diagnostic dictionary. ``boundary`` is ``lower``,
    ``upper``, or None; ``status`` is ``flat``, ``boundary``, or ``interior``.
    """
    p = normalized(probabilities)
    targets = _targets(counts, p.shape)
    logp = np.log(p)
    identity_loss = _derivatives(logp, targets, 1.0)[0]
    lower_gradient = _derivatives(logp, targets, LOWER_BETA)[1]
    upper_gradient = _derivatives(logp, targets, UPPER_BETA)[1]
    boundary = None
    iterations = 0
    if np.all(logp == logp[:, :1]):
        beta, status = 1.0, 'flat'
    elif lower_gradient >= 0:
        beta, status, boundary = LOWER_BETA, 'boundary', 'lower'
    elif upper_gradient <= 0:
        beta, status, boundary = UPPER_BETA, 'boundary', 'upper'
    else:
        lower, upper = LOWER_BETA, UPPER_BETA
        for _ in range(BISECTION_ITERATIONS):
            middle = (lower + upper) / 2.0
            if _derivatives(logp, targets, middle)[1] < 0:
                lower = middle
            else:
                upper = middle
        beta, status = (lower + upper) / 2.0, 'interior'
        iterations = BISECTION_ITERATIONS
    objective, gradient, curvature = _derivatives(logp, targets, beta)
    if objective > identity_loss + 1e-12:
        raise ValueError('fit must not worsen training NLL')
    return {
        'beta': beta, 'temperature': 1.0 / beta,
        'boundary': boundary, 'status': status, 'iterations': iterations,
        'objective_identity': identity_loss, 'objective_optimum': objective,
        'gradient_lower': lower_gradient, 'gradient_upper': upper_gradient,
        'gradient': gradient, 'curvature': curvature,
    }
