"""Pure NumPy paired-speaker bootstrap and fixed-phone weighted endpoints."""
import numpy as np


def _integers(value, name, shape=None):
    a = np.asarray(value)
    if (a.dtype.kind not in 'iu' or a.dtype.kind == 'b' or
            (shape is not None and a.shape != shape) or np.any(a < 0)):
        raise ValueError(f'{name} must be nonnegative integers of the required shape')
    if np.any(a > np.iinfo(np.int64).max):
        raise ValueError(f'{name} exceeds int64')
    return a.astype(np.int64, copy=False)


def speaker_weights(speaker_ids, speaker_folds, replicates=2000, seed=20260927):
    """Return sorted speakerIds, aligned speakerFolds and int64 replicate×speaker weights.

    Inputs may repeat speakers across positions. Each speaker must have one fold.
    Each replicate draws n speakers with replacement within each n-speaker fold.
    Fold order and sorted speaker order fix the PCG64 random-number consumption.
    """
    ids = np.asarray(speaker_ids)
    if ids.ndim != 1 or not len(ids) or ids.dtype.kind not in 'USiu':
        raise ValueError('speaker_ids must be nonempty string or integer identifiers')
    folds = _integers(speaker_folds, 'speaker_folds', ids.shape)
    if isinstance(replicates, (bool, np.bool_)) or not isinstance(replicates, (int, np.integer)) or replicates < 1:
        raise ValueError('replicates must be a positive integer')
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    unique, inverse = np.unique(ids, return_inverse=True)
    sf = np.empty(len(unique), dtype=np.int64)
    for i in range(len(unique)):
        values = np.unique(folds[inverse == i])
        if len(values) != 1:
            raise ValueError('each speaker must belong to exactly one fold')
        sf[i] = values[0]
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    weights = np.zeros((int(replicates), len(unique)), dtype=np.int64)
    for fold in np.unique(sf):
        selected = np.flatnonzero(sf == fold)
        weights[:, selected] = rng.multinomial(len(selected), np.full(len(selected), 1 / len(selected)), size=int(replicates))
    return {'speakerIds': unique.tolist(), 'speakerFolds': sf.tolist(), 'weights': weights}


def _ties(scores, positives):
    order = np.argsort(-scores, kind='stable')
    starts = np.r_[0, np.flatnonzero(np.diff(scores[order]) != 0) + 1]
    return order, starts, positives[order]


def prepare(p, lp, counts, phone_ids, all_phones):
    """Validate fixed rows and cache losses and exact-score tie groups for evaluate."""
    p, lp = np.asarray(p, dtype=np.float64), np.asarray(lp, dtype=np.float64)
    if p.ndim != 2 or p.shape[1:] != (3,) or not len(p) or lp.shape != p.shape:
        raise ValueError('probabilities and logs must be nonempty N×3 arrays')
    if (not np.isfinite(p).all() or not np.isfinite(lp).all() or
            np.any(p < 0) or np.any(p > 1) or np.any(lp > 0) or
            not np.allclose(p.sum(1), 1, atol=1e-12, rtol=0) or
            not np.allclose(np.exp(lp), p, atol=0, rtol=1e-12)):
        raise ValueError('invalid normalized probabilities or stable log correspondence')
    counts = _integers(counts, 'counts', p.shape)
    if np.any(counts > 5) or np.any(counts.sum(1) != 5):
        raise ValueError('each position requires five votes')
    phones = np.asarray(phone_ids)
    inventory = np.asarray(all_phones)
    if (phones.shape != (len(p),) or inventory.ndim != 1 or not len(inventory) or
            len(np.unique(inventory)) != len(inventory) or not np.isin(phones, inventory).all()):
        raise ValueError('phone inventory must be unique and cover all row phones')
    phone_index = np.array([np.flatnonzero(inventory == phone)[0] for phone in phones])
    return {'rows': len(p), 'allPhones': inventory.tolist(), 'phoneIndex': phone_index,
            'nll': -np.sum(counts / 5 * lp, axis=1),
            'brier': 1 + np.sum(p * p - 2 * p * counts / 5, axis=1),
            'rating0': _ties(p[:, 0], counts[:, 0]),
            'below2': _ties(p[:, :2].sum(1), counts[:, :2].sum(1))}


def _ap(cache, weights):
    order, starts, positives = cache
    ordered = weights[order]
    positive = np.add.reduceat(ordered * positives, starts)
    total = 5 * np.add.reduceat(ordered, starts)
    pos, mass = np.cumsum(positive), np.cumsum(total)
    count = float(pos[-1])
    precision = np.divide(pos, mass, out=np.zeros_like(pos), where=mass > 0)
    return (float(np.sum(positive * precision) / count) if count else None,
            count, float(mass[-1] - count))


def evaluate(prepared, weights):
    """Compute endpoints for nonnegative integer row multiplicities; no zero-mass sample.

    Macro NLL is None if any declared phone is absent. AP is None without positive
    votes, but remains defined (one) when positive votes exist without negatives.
    Support describes the weighted sample, not an independent participant count.
    """
    weights = _integers(weights, 'weights', (prepared['rows'],)).astype(np.float64)
    mass = float(weights.sum())
    if mass <= 0 or not np.isfinite(mass):
        raise ValueError('weights must have positive finite mass')
    phone_mass = np.bincount(prepared['phoneIndex'], weights=weights, minlength=len(prepared['allPhones']))
    phone_loss = np.bincount(prepared['phoneIndex'], weights=weights * prepared['nll'], minlength=len(phone_mass))
    absent = [p for p, m in zip(prepared['allPhones'], phone_mass) if m == 0]
    ap0, pos0, neg0 = _ap(prepared['rating0'], weights)
    ap2, pos2, neg2 = _ap(prepared['below2'], weights)
    return {'NLL': float(np.sum(weights * prepared['nll']) / mass),
            'Brier': float(np.sum(weights * prepared['brier']) / mass),
            'macroNLL': None if absent else float(np.mean(phone_loss / phone_mass)),
            'rating0AP': ap0, 'below2AP': ap2,
            'support': {'rowMass': mass, 'voteMass': 5 * mass,
                        'phoneRowMass': dict(zip(prepared['allPhones'], phone_mass.tolist())),
                        'absentPhones': absent,
                        'rating0': {'positiveVotes': pos0, 'negativeVotes': neg0},
                        'below2': {'positiveVotes': pos2, 'negativeVotes': neg2},
                        'undefined': [key for key, value in [('macroNLL', None if absent else 0), ('rating0AP', ap0), ('below2AP', ap2)] if value is None]}}


def metrics(p, lp, counts, phone_ids, weights, all_phones):
    """Convenience prepare/evaluate for one weighted sample; see their contracts."""
    return evaluate(prepare(p, lp, counts, phone_ids, all_phones), weights)
