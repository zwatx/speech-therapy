"""Pure fixed-phone paired uncertainty using supplied whole-speaker draws."""
import numpy as np

from lexical_uncertainty import core

PHONES = tuple('B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG'.split())
ENDPOINTS = ('NLL', 'Brier', 'macroNLL', 'rating0AP', 'below2AP')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def interval(values, observed):
    """Descriptive paired differences; fractions are not hypothesis-test p-values."""
    valid = np.asarray([v for v in values if v is not None], dtype=np.float64)
    require(valid.ndim == 1 and np.isfinite(valid).all()
            and (observed is None or np.isscalar(observed) and np.isfinite(observed)),
            'Interval values must be finite scalars or explicit nulls')
    return dict(observed=observed,
                interval95=np.quantile(valid, [.025, .975], method='linear').tolist() if len(valid) else None,
                validReplicates=len(valid), undefinedReplicates=len(values) - len(valid),
                fractionBelowZero=float(np.mean(valid < 0)) if len(valid) else None,
                fractionAboveZero=float(np.mean(valid > 0)) if len(valid) else None)


def _sampling(rows, folds, groups, sampling):
    require(len(rows) > 0, 'Nonempty rows required')
    folds = core._integers(folds, 'folds', (len(rows),))
    groups = core._integers(groups, 'groups', (len(rows),))
    require((folds < 5).all() and (groups < 5).all(), 'Fold/group must be in 0..4')
    speakers = [row['speakerId'] for row in rows]
    require(all(isinstance(s, str) and s for s in speakers)
            or all(isinstance(s, (int, np.integer)) and not isinstance(s, (bool, np.bool_)) for s in speakers),
            'Speaker IDs must be homogeneous nonempty strings or integers')
    ids = sorted(set(speakers))
    require(list(sampling['speakerIds']) == ids, 'Sampling speaker IDs must be sorted, unique and match rows')
    speaker_folds = core._integers(sampling['speakerFolds'], 'sampling speaker folds', (len(ids),))
    index = {speaker: i for i, speaker in enumerate(ids)}
    row_speakers = np.asarray([index[s] for s in speakers], dtype=np.int64)
    require((speaker_folds < 5).all()
            and np.array_equal(speaker_folds[row_speakers], folds), 'Speaker fold assignments differ')
    weights = core._integers(sampling['weights'], 'sampling weights')
    require(weights.ndim == 2 and weights.shape[1] == len(ids) and weights.shape[0] > 0,
            'Expected positive replicate count and one weight per speaker')
    for fold in range(5):
        selected = speaker_folds == fold
        count = int(selected.sum())
        require((weights[:, selected] <= count).all()
                and (weights[:, selected].sum(1) == count).all(), 'Sampling must preserve each speaker-fold stratum size')
    return folds, ids, row_speakers, weights


def _difference(candidate, reference):
    return {key: candidate[key] - reference[key]
            if candidate[key] is not None and reference[key] is not None else None for key in ENDPOINTS}


def _influence(rows, folds, speakers, row_speakers, counts, loss_delta):
    by_fold = {}
    for fold in range(5):
        mask = folds == fold
        count = int(mask.sum())
        total = float(loss_delta[mask].sum())
        by_fold[str(fold)] = dict(positions=count, children=len(set(row_speakers[mask].tolist())),
            raterVotes=counts[mask].sum(0).tolist(), NLLDelta=total / count if count else None,
            additiveNLLContribution=total / len(rows))
    leave_one_out = {}
    for index, speaker in enumerate(speakers):
        removed = row_speakers == index
        keep = ~removed
        leave_one_out[speaker] = dict(removedPositions=int(removed.sum()), remainingPositions=int(keep.sum()),
                                     NLLDelta=float(loss_delta[keep].mean()) if keep.any() else None)
    return dict(speakerFolds=by_fold, leaveOneChildOut=leave_one_out)


def analyze(rows, folds, groups, candidate, reference, sampling):
    """Return candidate-minus-reference paired draws and complete influence views.

    Sampling is supplied, never generated here. Every row from one speaker gets
    the same integer multiplicity. The caller checks actual cohort identity and
    shares the identical sampling object across all declared comparisons.
    Missing phones keep macro NLL undefined against the fixed 23-phone inventory.
    """
    folds, speakers, row_speakers, weights = _sampling(rows, folds, groups, sampling)
    require(all(isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_))
                for row in rows for v in row['raterCounts']), 'Five-vote labels must be integers, not booleans')
    counts = core._integers([row['raterCounts'] for row in rows], 'five-vote counts', (len(rows), 3))
    phones = np.asarray([row['targetPhone'] for row in rows])
    prepared = [core.prepare(model['probabilities'], model['logProbabilities'], counts, phones, PHONES)
                for model in (candidate, reference)]
    one = np.ones(len(rows), dtype=np.int64)
    actual_candidate, actual_reference = (core.evaluate(value, one) for value in prepared)
    observed = _difference(actual_candidate, actual_reference)
    loss_delta = prepared[0]['nll'] - prepared[1]['nll']
    masks = {phone: phones == phone for phone in PHONES}
    replicates = {key: [] for key in ENDPOINTS}
    per_phone = {phone: [] for phone in PHONES}
    for speaker_weights in weights:
        row_weights = speaker_weights[row_speakers]
        values = _difference(*(core.evaluate(value, row_weights) for value in prepared))
        for key in ENDPOINTS:
            replicates[key].append(values[key])
        for phone, mask in masks.items():
            mass = int(row_weights[mask].sum())
            per_phone[phone].append(float(np.dot(row_weights[mask], loss_delta[mask]) / mass) if mass else None)
    return dict(
        observed=dict(candidate=actual_candidate, reference=actual_reference),
        pairedIntervals={key: interval(replicates[key], observed[key]) for key in ENDPOINTS},
        replicates=replicates,
        perPhone={phone: dict(interval(per_phone[phone], float(loss_delta[mask].mean()) if mask.any() else None),
            positions=int(mask.sum()), children=len(set(row_speakers[mask].tolist())),
            raterVotes=counts[mask].sum(0).tolist(), replicates=per_phone[phone]) for phone, mask in masks.items()},
        influence=_influence(rows, folds, speakers, row_speakers, counts, loss_delta))
