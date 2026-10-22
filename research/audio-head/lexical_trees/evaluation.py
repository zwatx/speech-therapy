"""Score both fixed depths only after all refits and outer outputs are frozen."""
import argparse
import json
import numpy as np
from lexical_trees import core, study


def average_precision(scores, positive, negative):
    """Pooled rater-vote AP with exact-score ties grouped; both classes required."""
    if not positive.sum() or not negative.sum():
        return None
    order = np.argsort(-scores, kind='stable')
    s, p, n = scores[order], positive[order], negative[order]
    ends = np.r_[np.flatnonzero(s[1:] != s[:-1]), len(s)-1]
    tp, total = p.cumsum()[ends], (p+n).cumsum()[ends]
    additions = np.diff(np.r_[0, tp])
    return float(np.sum(additions * tp / total) / positive.sum())


def metrics(logp, rows):
    if not rows:
        return None
    counts = np.asarray([r['raterCounts'] for r in rows], dtype=np.int64)
    nll = core.nll(logp, counts)
    p = np.exp(logp)
    phones = np.asarray([r['targetPhone'] for r in rows])
    loss = -(counts * logp).sum(1) / 5
    events = {}
    for label, end in [('rating0', 1), ('below2', 2)]:
        positive, negative = counts[:, :end].sum(1), counts[:, end:].sum(1)
        events[label] = dict(
            averagePrecision=average_precision(p[:, :end].sum(1), positive, negative),
            positiveVotes=int(positive.sum()), negativeVotes=int(negative.sum()),
            positiveChildren=len({r['speakerId'] for r, v in zip(rows, positive) if v}),
            negativeChildren=len({r['speakerId'] for r, v in zip(rows, negative) if v}))
    return dict(nll=nll, macroNll=float(np.mean([loss[phones == ph].mean() for ph in np.unique(phones)])),
                brier=float(np.mean((p*p - 2*p*counts/5).sum(1)+1)),
                positions=len(rows), children=len({r['speakerId'] for r in rows}),
                recordings=len({r['clipId'] for r in rows}),
                words=len({r['targetWord'].upper() for r in rows}),
                votes=counts.sum(0).tolist(), events=events)


def comparison(candidate, reference):
    if candidate is None or reference is None:
        return None
    deltas = {k: candidate[k]-reference[k] for k in ('nll', 'macroNll', 'brier')}
    for event in ('rating0', 'below2'):
        a, b = (v['events'][event]['averagePrecision'] for v in (candidate, reference))
        deltas[event+'Ap'] = a-b if a is not None and b is not None else None
    return deltas


def screen(delta, fold_deltas, reference_nll):
    directional = (all(delta[k] < -1e-7 for k in ('nll', 'macroNll', 'brier'))
                   and all(delta[k] is not None and delta[k] > 1e-7 for k in ('rating0Ap', 'below2Ap'))
                   and all(d['nll'] <= 1e-7 for d in fold_deltas))
    return dict(directionalPass=directional,
                materialGainPass=bool(directional and -delta['nll']/reference_nll >= .05
                                      and delta['rating0Ap'] >= .01),
                relativeNllReduction=-delta['nll']/reference_nll)


def evaluate(args):
    plan, rows, _, counts = study.load_plan(args.plan, args.sha256)
    out = args.plan.resolve().parent
    frozen = study.read(dict(path=str(out/'outer-freeze.json'), sha256=args.outer_sha256))
    study.require(frozen['complete'] and frozen['phase']=='outer' and frozen['planSha256']==args.sha256,
                  'Invalid outer freeze')
    refit = frozen['refitFreeze']
    study.checked_freeze(refit['path'], refit['sha256'], args.sha256, 'refit', plan['jobs'])
    study.require([r['jobId'] for r in frozen['runs']]==[j['id'] for j in plan['jobs']], 'Incomplete outer freeze')
    results = []
    for depth in (4, 6):
        ids, folds, cells, candidate, scalars, compact = [], [], [], [], [], []
        for job, run in zip(plan['jobs'], frozen['runs'], strict=True):
            if job['depth'] != depth:
                continue
            binding = run['artifact']
            study.require(study.sha(binding['path'])==binding['sha256'], 'Changed outer predictions')
            with np.load(binding['path'], allow_pickle=False) as saved:
                ii = saved['rowIndices'].tolist()
                study.require(ii==job['outerRows'] and np.array_equal(saved['raterCounts'], counts[ii]), 'Outer row/label mismatch')
                lp = saved['logProbabilities']
                study.require(np.array_equal(saved['probabilities'], np.exp(lp)), 'Probability mismatch')
                candidate.extend(lp)
            for family, dest in [('scalars', scalars), ('pca16-scalars', compact)]:
                ref = study.read(job['references'][family])['prediction']
                ri = ref['rowIndices']
                study.require(len(ri)==len(set(ri)), 'Duplicate reference positions')
                lookup = dict(zip(ri, ref['logProbabilities'], strict=True))
                dest.extend(lookup[i] for i in ii)
            ids.extend(ii); folds.extend([job['speakerFold']]*len(ii)); cells.extend([f"s{job['speakerFold']}-w{job['wordGroup']}"]*len(ii))
        study.require(len(ids)==len(set(ids))==5654, 'Outer coverage mismatch')
        rr = [rows[i] for i in ids]
        lp = dict(candidate=np.asarray(candidate, dtype=np.float64), scalars=np.asarray(scalars, dtype=np.float64))
        lp['mixture'] = np.logaddexp(lp['scalars'], np.asarray(compact, dtype=np.float64))-np.log(2.)
        def slice_result(mask):
            selected = [r for r, yes in zip(rr, mask) if yes]
            values = {name: metrics(value[mask], selected) for name, value in lp.items()}
            return dict(metrics=values, vsMixture=comparison(values['candidate'], values['mixture']),
                        vsScalars=comparison(values['candidate'], values['scalars']))
        pooled = slice_result(np.ones(len(ids), dtype=bool))
        axes = dict(phone=([r['targetPhone'] for r in rr], core.PHONES),
                    age=([r['age'] for r in rr], list(range(6, 13))),
                    fold=(folds, list(range(5))), cell=(cells, sorted(set(cells))),
                    child=([r['speakerId'] for r in rr], sorted({r['speakerId'] for r in rr})))
        groups = {axis: {str(k): slice_result(np.asarray(values)==k) for k in keys}
                  for axis, (values, keys) in axes.items()}
        outcome = screen(pooled['vsMixture'], [g['vsMixture'] for g in groups['fold'].values()],
                         pooled['metrics']['mixture']['nll'])
        results.append(dict(depth=depth, pooled=pooled, groups=groups, screen=outcome))
    study.write(out/'results.json', dict(complete=True, planSha256=args.sha256,
                outerFreeze=dict(path=str(out/'outer-freeze.json'), sha256=args.outer_sha256),
                candidates=results, **study.FLAGS))
    print(json.dumps([dict(depth=r['depth'], delta=r['pooled']['vsMixture'], screen=r['screen']) for r in results]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=study.Path, required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--outer-sha256', required=True)
    evaluate(p.parse_args())
