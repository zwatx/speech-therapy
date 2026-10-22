"""Paired original-child comparisons; no fitting, selection, or artifact I/O."""
import numpy as np
from multiphone_verify import weighted_binary_metrics, validate_predictions
from multiphone_data import TARGETS
from lexical_compact.core import require


def metrics(logs, rows):
    if not rows:
        return None
    logs = np.asarray(logs, dtype=np.float64)
    require(logs.shape == (len(rows), 3) and np.isfinite(logs).all(), 'Invalid stable logs')
    counts = np.asarray([r['raterCounts'] for r in rows], dtype=np.int64)
    p, _ = validate_predictions(np.exp(logs), counts)
    require(np.allclose(p.sum(1), 1, rtol=0, atol=1e-12), 'Unnormalized stable logs')
    loss = -(counts * logs).sum(1) / 5
    phones = np.asarray([r['targetPhone'] for r in rows])
    events = {}
    for name, end in [('rating0', 1), ('below2', 2)]:
        pos, neg = counts[:, :end].sum(1), counts[:, end:].sum(1)
        rank = weighted_binary_metrics(p[:, :end].sum(1), pos, neg)
        # Preserve undefined discrimination when either class lacks support.
        if not pos.sum() or not neg.sum():
            rank['averagePrecision'] = rank['auroc'] = None
        events[name] = dict(**rank,
            positiveChildren=len({r['speakerId'] for r, n in zip(rows, pos) if n}),
            negativeChildren=len({r['speakerId'] for r, n in zip(rows, neg) if n}))
    return dict(nll=float(loss.mean()),
        macroNll=float(np.mean([loss[phones == phone].mean() for phone in np.unique(phones)])),
        brier=float(np.mean((p*p - 2*p*counts/5).sum(1)+1)), events=events,
        positions=len(rows), children=len({r['speakerId'] for r in rows}),
        recordings=len({r['clipId'] for r in rows}), votes=counts.sum(0).tolist())


def difference(candidate, reference):
    if candidate is None or reference is None:
        return None
    result = {k: candidate[k]-reference[k] for k in ('nll', 'macroNll', 'brier')}
    for event in ('rating0', 'below2'):
        a, b = [v['events'][event]['averagePrecision'] for v in (candidate, reference)]
        result[event+'Ap'] = None if a is None or b is None else a-b
    return result


def screen(delta, folds, reference_nll):
    require(len(folds) == 5 and reference_nll > 0, 'Expected five folds and positive reference loss')
    values = [*delta.values(), *(f['nll'] for f in folds)]
    require(all(v is not None and np.isfinite(v) for v in values), 'Undefined primary endpoint')
    checks = dict(pooledNllImproves=delta['nll'] < -1e-7,
        everyFoldNllNonworse=all(f['nll'] <= 1e-7 for f in folds),
        macroNllNonworse=delta['macroNll'] <= 1e-7,
        brierNonworse=delta['brier'] <= 1e-7,
        rating0ApNonworse=delta['rating0Ap'] >= -1e-7,
        below2ApNonworse=delta['below2Ap'] >= -1e-7)
    passed = all(checks.values())
    relative = -delta['nll']/reference_nll
    return dict(checks=checks, directionalPass=passed, relativeNllReduction=relative,
        materialGainPass=bool(passed and relative >= .05 and delta['rating0Ap'] >= .01))


def evaluate(rows, row_indices, folds, logs):
    """Inputs share ordered global indices; caller verifies frozen prediction lineage."""
    names = {'l12', 'l24', 'scalar', 'retainedCompact'}
    require(set(logs) == names and len(row_indices) == len(set(row_indices)) == len(rows) == len(folds),
            'Incomplete or duplicate matched predictions')
    require(all(6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None for r in rows),
            'Expected original child positions only')
    require(set(folds) == set(range(5)), 'Missing speaker fold')
    predictions = {k: np.asarray(v, dtype=np.float64) for k, v in logs.items()}
    for k in ('l12', 'l24', 'retainedCompact'):
        predictions[k+'Mixture'] = np.logaddexp(predictions[k], predictions['scalar'])-np.log(2.)
    pairs = dict(primary=('l12Mixture', 'l24Mixture'),
                 replacement=('l12Mixture', 'retainedCompactMixture'),
                 compact=('l12', 'l24'),
                 freshControl=('l24Mixture', 'retainedCompactMixture'))

    def view(mask):
        selected = [r for r, keep in zip(rows, mask, strict=True) if keep]
        values = {k: metrics(v[mask], selected) for k, v in predictions.items()}
        return dict(metrics=values,
                    deltas={k: difference(values[a], values[b]) for k, (a, b) in pairs.items()})

    pooled = view(np.ones(len(rows), dtype=bool))
    axes = dict(fold=(folds, range(5)), age=([r['age'] for r in rows], range(6, 13)),
                phone=([r['targetPhone'] for r in rows], TARGETS[:23]),
                child=([r['speakerId'] for r in rows], sorted({r['speakerId'] for r in rows})))
    groups = {axis: {str(k): view(np.asarray(values) == k) for k in keys}
              for axis, (values, keys) in axes.items()}
    screens = {name: screen(pooled['deltas'][name],
                [groups['fold'][str(i)]['deltas'][name] for i in range(5)],
                pooled['metrics'][pairs[name][1]]['nll']) for name in ('primary', 'replacement')}
    co_condition = pooled['deltas']['compact']['nll'] < -1e-7
    return dict(pooled=pooled, groups=groups, screens=screens,
        compactCoCondition=co_condition,
        candidateForConfirmation=bool(co_condition and all(s['directionalPass'] for s in screens.values())),
        promotionEligible=False, clinicalUseEligible=False, learnerFeedbackEligible=False,
        independentFinalValidation=False)
