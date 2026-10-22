"""Tied PR, probability calibration and speaker-cluster uncertainty for Stage D."""
import numpy as np
from scipy.special import expit

from .gop import pr_curve, coverage_curve, operating_counts

TARGETS = 'R L S Z SH CH TH DH K G F V'.split()


def ranking(y, scores, weights=None):
    """Vectorized tied curve summaries; speaker bootstrap uses integer weights."""
    y, scores = np.asarray(y, dtype=bool), np.asarray(scores, dtype=float)
    if not len(y) or not y.any():
        return dict(AP=None, precision_at_recall={str(r):None for r in (.3,.5,.7)},
                    recall_at_precision={str(p):None for p in (.9,.8)})
    w = np.ones(len(y)) if weights is None else np.asarray(weights, dtype=float)
    keep = w > 0
    y, scores, w = y[keep], scores[keep], w[keep]
    order = np.argsort(-scores, kind='stable')
    y, scores, w = y[order], scores[order], w[order]
    total = float(np.dot(w, y))
    if not total:
        return dict(AP=None, precision_at_recall={str(r):None for r in (.3,.5,.7)},
                    recall_at_precision={str(p):None for p in (.9,.8)})
    endpoints = np.r_[np.flatnonzero(scores[:-1] != scores[1:]), len(scores)-1]
    tp, count = np.cumsum(w*y)[endpoints], np.cumsum(w)[endpoints]
    precision, recall = tp/count, tp/total
    return dict(AP=float(np.dot(np.diff(np.r_[0., recall]), precision)),
                precision_at_recall={str(r):float(precision[recall >= r].max())
                                     if np.any(recall >= r) else 0. for r in (.3,.5,.7)},
                recall_at_precision={str(p):float(recall[precision >= p].max())
                                     if np.any(precision >= p) else 0. for p in (.9,.8)})


def ece(y, probabilities, bins=15):
    y, probabilities = np.asarray(y), np.asarray(probabilities)
    indices = np.minimum((probabilities*bins).astype(int), bins-1)
    detail = []
    for b in range(bins):
        use = indices == b
        if use.any():
            detail.append(dict(bin=b, n=int(use.sum()), mean_probability=float(probabilities[use].mean()),
                               error_rate=float(y[use].mean())))
    return dict(value=sum(r['n']*abs(r['mean_probability']-r['error_rate']) for r in detail)/len(y),
                bins=bins, occupied_bins=detail)


def speaker_bootstrap(records, scores, repeats=2000, seed=73):
    speakers = np.asarray([r['speaker'] for r in records])
    names, ids = np.unique(speakers, return_inverse=True)
    y = np.asarray([r['error'] for r in records])
    rng = np.random.default_rng(seed)
    values = []
    # Sort once: replicate weights do not change score ordering or tied groups.
    order = np.argsort(-np.asarray(scores), kind='stable')
    yy, ss, ii = y[order], np.asarray(scores)[order], ids[order]
    endpoints = np.r_[np.flatnonzero(ss[:-1] != ss[1:]), len(ss)-1]
    for _ in range(repeats):
        counts = np.bincount(rng.integers(0, len(names), len(names)), minlength=len(names))
        weights = counts[ii]
        total = np.dot(weights, yy)
        if not total:
            continue
        tp, n = np.cumsum(weights*yy)[endpoints], np.cumsum(weights)[endpoints]
        use = n > 0
        precision, recall = tp[use]/n[use], tp[use]/total
        ap = float(np.dot(np.diff(np.r_[0.,recall]), precision))
        rp = float(recall[precision >= .9].max()) if np.any(precision >= .9) else 0.
        values.append((ap, rp))
    intervals = np.percentile(values, [2.5,97.5], axis=0) if values else [[None,None],[None,None]]
    return dict(seed=seed, requested=repeats, valid=len(values), excluded_no_error=repeats-len(values),
                speakers=len(names), method='speaker-cluster percentile, fixed fitted model',
                AP=[intervals[0][0], intervals[1][0]],
                recall_at_precision_0_9=[intervals[0][1], intervals[1][1]])


def summarize(records, logits, threshold, bootstrap=False):
    y = np.asarray([r['error'] for r in records], dtype=bool)
    logits = np.asarray(logits)
    result = dict(phones=len(y), errors=int(y.sum()), speakers=len({r['speaker'] for r in records}),
                  **ranking(y, logits), at_frozen_threshold=operating_counts(y, logits >= threshold),
                  ECE=ece(y, expit(logits)), pr_curve=pr_curve(y,logits),
                  coverage_curve=coverage_curve(y, logits, threshold))
    result['per_phone'] = {}
    for phone in TARGETS:
        use = np.asarray([r['phone'] == phone for r in records])
        result['per_phone'][phone] = dict(phones=int(use.sum()), errors=int(y[use].sum()),
                **ranking(y[use], logits[use]), at_frozen_threshold=operating_counts(y[use], logits[use]>=threshold))
    if bootstrap:
        result['bootstrap_95'] = speaker_bootstrap(records, logits)
    return result
