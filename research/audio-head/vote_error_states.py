"""Three exhaustive observed-vote/model-mode states; arithmetic only."""
import argparse
from pathlib import Path
import json
import traceback

import numpy as np
import vote_headroom as h

BASE = h.ROOT/'research/audio-head/outputs/multiphone-20260928/vote-headroom-v1'
PROTOCOL = h.ROOT/'docs/model/vote-error-states-v1.md'
STATES = ('unanimousAgree', 'unanimousDisagree', 'mixed')
METRICS = ('nll', 'empiricalEntropy', 'nllExcess', 'brier', 'empiricalBrierFloor', 'brierExcess')


def declaration():
    parent_pin = h.binding(BASE/'plan.json', '36a613e6946f10452e3e42ac7072b9c9e71bc71129561f3c294cd71df3be438f')
    parent = h.read(parent_pin)
    h.require(parent == h.declaration(), 'Frozen parent declaration changed')
    result_pin = h.binding(BASE/'results.json', '4da4edb8a68ab1054fc5edfe3934d5f999cd45bb20efb710b3c3728d4d8d980e')
    result = h.read(result_pin)
    h.require(result['complete'] and result['plan'] == parent_pin, 'Completed parent required')
    inputs = dict(parent['inputs'], parentPlan=parent_pin, parentResult=result_pin)
    inputs['parentSourceReview'] = h.binding(h.WORK/'opus-vote-headroom-review.json', '9639aca87c4277d42895683ffaf5968da9962314e7d7e4712cc3e6e48b6c1be1')
    inputs['parentResultsReview'] = h.binding(h.WORK/'opus-vote-headroom-results-review.json', 'dda808eb11896f3dfbf52983f40c49b24d3f7aa83148e53c81e30d097b8da944')
    for name in ('vote-headroom-results-root-observation.json', 'vote-headroom-closeout-root-observation.json'):
        inputs[name] = h.binding(h.WORK/name)
    sources = dict(parent['sources'])
    sources.update({p.name: h.binding(p) for p in (PROTOCOL, Path(__file__), Path(__file__).with_name('test_vote_error_states.py'))})
    plan = dict(study='vote-error-states-v1', inputs=inputs, sources=sources,
                rowIndices=parent['rowIndices'], cells=parent['cells'], seeds=parent['seeds'], runtime=parent['runtime'],
                states=list(STATES), tieRule='lowest class index in stable-log argmax', auditTolerance=h.TOL, **h.FLAGS)
    h.guards(plan)
    return plan


def states(counts, logs):
    values = h.terms(counts, logs)
    counts, logs = np.asarray(counts), np.asarray(logs, dtype=np.float64)
    mode, observed = logs.argmax(1), counts.argmax(1)
    unanimous = counts.max(1) == 5
    labels = np.where(unanimous, np.where(mode == observed, 0, 1), 2)
    return labels, mode, observed, values


def partition(rows, logs):
    counts = np.asarray([r['raterCounts'] for r in rows])
    logs = np.asarray(logs, dtype=np.float64)
    labels, mode, observed, values = states(counts, logs)
    probability = np.exp(logs)
    totals = {k: float(values[k].sum()) for k in METRICS}
    output = {}
    for index, name in enumerate(STATES):
        mask = labels == index
        chosen = [r for r, keep in zip(rows, mask, strict=True) if keep]
        n = len(chosen)
        sums = {k: float(values[k][mask].sum()) for k in METRICS}
        output[name] = dict(support=dict(positions=n, recordings=len({r['clipId'] for r in chosen}),
                          children=len({r['speakerId'] for r in chosen}), votes=counts[mask].sum(0).tolist()),
                            totals=sums, means={k: v/n if n else None for k, v in sums.items()},
                            nllShare=sums['nll']/totals['nll'] if n and totals['nll'] > 0 else None,
                            excessShare=sums['nllExcess']/totals['nllExcess'] if n and totals['nllExcess'] > 0 else None,
                            meanMaximumProbability=float(probability[mask].max(1).mean()) if n else None,
                            meanUnanimousClassProbability=float(probability[np.flatnonzero(mask), observed[mask]].mean())
                            if n and index != 2 else None)
    confusion = [[int(((counts.max(1) == 5) & (observed == a) & (mode == b)).sum()) for b in range(3)] for a in range(3)]
    h.require(sum(v['support']['positions'] for v in output.values()) == len(rows)
              and sum(map(sum, confusion)) == len(rows)-output['mixed']['support']['positions'], 'Incomplete state partition')
    for key in METRICS:
        h.require(abs(sum(v['totals'][key] for v in output.values())-totals[key])/len(rows) <= h.TOL, 'State totals differ')
    return dict(states=output, unanimousClassByMode=confusion)


def calculate(plan):
    h.guards(plan)
    cohort = h.read(plan['inputs']['cohort'])['rows']
    parent = h.read(plan['inputs']['parentResult'])
    scalars = h.read(plan['inputs']['scalars'])
    expected = plan['rowIndices']
    h.require(expected == sorted(i for i, r in enumerate(cohort) if 6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None),
              'Original child coverage changed')
    rows = [cohort[i] for i in expected]
    output = {}
    for seed in h.SEEDS:
        collected, folds = {k: {} for k in ('candidate', 'freshHard', 'scalar')}, {}
        for cell in [c for c in plan['cells'] if c['seed'] == seed]:
            for arm in collected:
                value = (scalars[cell['id']] if arm == 'scalar' else h.read(plan['inputs']['prediction/'+cell['jobs'][arm]]))['prediction']
                h.require(value['rowIndices'] == cell['outerRows'], 'Outer order differs')
                for i, lp in zip(value['rowIndices'], value['logProbabilities'], strict=True):
                    h.require(i not in collected[arm], 'Duplicate original position')
                    collected[arm][i] = lp
                    h.require(folds.setdefault(i, cell['speakerFold']) == cell['speakerFold'], 'Fold differs')
        h.require(all(sorted(v) == expected for v in collected.values()), 'Incomplete original coverage')
        logs = {k: np.asarray([v[i] for i in expected]) for k, v in collected.items()}
        logs.update({k+'Mixture': np.logaddexp(logs[k], logs['scalar'])-np.log(2.) for k in ('candidate', 'freshHard')})
        axes = dict(fold=[folds[i] for i in expected], age=[r['age'] for r in rows],
                    phone=[r['targetPhone'] for r in rows], child=[r['speakerId'] for r in rows])
        masks = dict(pooled=dict(all=np.ones(len(rows), dtype=bool)))
        masks.update({axis: {str(k): np.asarray(values) == k for k in sorted(set(values))} for axis, values in axes.items()})
        h.require({k: len(v) for k, v in masks.items()} == dict(pooled=1, fold=5, age=7, phone=23, child=52), 'Subgroup coverage differs')
        output[str(seed)] = {}
        for axis, groups in masks.items():
            output[str(seed)][axis] = {}
            for key, mask in groups.items():
                selected = [r for r, keep in zip(rows, mask, strict=True) if keep]
                output[str(seed)][axis][key] = {arm: partition(selected, lp[mask]) for arm, lp in logs.items()}
                for arm, value in output[str(seed)][axis][key].items():
                    old = parent['seeds'][str(seed)][axis][key][arm]
                    h.require(sum(v['support']['positions'] for v in value['states'].values()) == old['support']['positions']
                              and np.array_equal(np.sum([v['support']['votes'] for v in value['states'].values()], axis=0), old['support']['votes']),
                              'Parent support differs')
                    for metric in METRICS:
                        average = sum(v['totals'][metric] for v in value['states'].values())/len(selected)
                        h.require(abs(average-old[metric]) <= h.TOL, 'Parent loss decomposition differs')
    h.guards(plan)
    return dict(complete=True, study=plan['study'], seeds=output,
                populationIrreducibilityEstablished=False, acousticAchievabilityEstablished=False, **h.FLAGS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'calculate'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sha256')
    parser.add_argument('--review', type=Path)
    args = parser.parse_args()
    if args.command == 'declare':
        value = declaration()
        args.out.mkdir(parents=True, exist_ok=False)
        h.write(args.out/'plan.json', value)
        print(json.dumps(h.binding(args.out/'plan.json')))
        return
    h.require(args.sha256 and args.review, 'Plan hash and actual independent review required')
    plan_pin = h.binding(args.out/'plan.json', args.sha256)
    plan = h.read(plan_pin)
    h.require(plan == declaration(), 'Actual declaration changed')
    review_pin = h.binding(args.review)
    review = h.read(review_pin)
    h.require(review.get('independent') is True and review.get('verdict') == 'clear'
              and not review.get('blockingFindings') and review.get('plan') == plan_pin
              and review.get('sourceReviewed') is True and review.get('actualDeclarationReviewed') is True
              and review.get('calculationAuthorized') is True, 'Reviewed actual declaration required')
    output, failure = args.out/'results.json', args.out/'failure.json'
    h.require(not output.exists() and not failure.exists(), 'Preserve prior outputs; no restart')
    try:
        value = calculate(plan)
        h.guards(plan)
        h.binding(plan_pin['path'], plan_pin['sha256'])
        h.binding(review_pin['path'], review_pin['sha256'])
        h.write(output, dict(value, plan=plan_pin, review=review_pin))
        print(json.dumps(h.binding(output)))
    except BaseException as error:
        h.write(failure, dict(complete=False, errorType=type(error).__name__, error=str(error),
                             traceback=traceback.format_exc(), restartAllowed=False, **h.FLAGS))
        raise


if __name__ == '__main__':
    main()
