"""Fixed same-seed evaluation of the rating-0 proper-loss candidate."""
import argparse
import json
from pathlib import Path

import numpy as np

from middle_layer_replication import evaluation as frozen
from rare0_proper_loss import study as s

SEEDS = (17, 29, 43)
TOL = 1e-7
LABELS = {'middle': 'rare0', 'middleMixture': 'rare0Mixture',
          'replicationPass': 'historicalScreenPass'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rename(value, mapping):
    if isinstance(value, dict):
        return {mapping.get(key, key): rename(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [rename(item, mapping) for item in value]
    return value


def extra_screen(seed):
    phones = seed['groups']['phone']
    require(len(phones) == 23, 'Expected all 23 phone views')
    candidate, reference = [], []
    for phone in phones.values():
        c = phone['metrics']['rare0Mixture']['events']['rating0']['averagePrecision']
        r = phone['metrics']['finalMixture']['events']['rating0']['averagePrecision']
        require(c is not None and r is not None and np.isfinite(c) and np.isfinite(r),
                'Undefined required phone rating-0 AP')
        candidate.append(c); reference.append(r)
    age6 = seed['groups']['age']['6']['deltas']['primary']
    require(age6['rating0Ap'] is not None and age6['macroNll'] is not None
            and np.isfinite(age6['rating0Ap']) and np.isfinite(age6['macroNll']),
            'Undefined required age-6 endpoint')
    delta = float(np.mean(candidate) - np.mean(reference))
    checks = dict(equalPhoneRating0ApNonworse=delta >= -TOL,
                  age6Rating0ApNonworse=age6['rating0Ap'] >= -TOL,
                  age6MacroNllNonworse=age6['macroNll'] <= TOL)
    return dict(checks=checks, passed=all(checks.values()),
                equalPhoneRating0Ap=dict(candidate=float(np.mean(candidate)),
                                         reference=float(np.mean(reference)), delta=delta,
                                         supportedPhones=23),
                age6=dict(rating0ApDelta=age6['rating0Ap'], macroNllDelta=age6['macroNll']))


def class_contribution(counts, candidate, reference):
    """Decompose ordinary NLL without hardening mixed five-vote labels."""
    counts = np.asarray(counts, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    require(counts.ndim == 2 and counts.shape[1] == 3 and len(counts) > 0
            and counts.shape == candidate.shape == reference.shape
            and np.all(counts >= 0) and np.all(counts.sum(1) == 5)
            and np.isfinite(candidate).all() and np.isfinite(reference).all()
            and np.allclose(np.exp(candidate).sum(1), 1, atol=1e-12, rtol=0)
            and np.allclose(np.exp(reference).sum(1), 1, atol=1e-12, rtol=0),
            'Invalid vote/log-probability arrays')
    votes = counts.sum(0)
    weighted = (counts * (reference - candidate)).sum(0)
    n = len(counts)
    c_nll = float(-(counts * candidate).sum() / (5*n))
    r_nll = float(-(counts * reference).sum() / (5*n))
    additive = weighted / (5*n)
    require(abs(float(additive.sum()) - (c_nll-r_nll)) <= 1e-12,
            'Class contributions do not sum to NLL change')
    return dict(candidateNll=c_nll, referenceNll=r_nll, nllDelta=c_nll-r_nll,
                additiveNllDelta=additive.tolist(),
                classConditionalMeanDelta=[float(w/v) if v else None for w, v in zip(weighted, votes)],
                votes=votes.astype(int).tolist(), votePrior=(votes/(5*n)).tolist())


def class_views(rows, jobs, candidates, controls, result):
    """Reassemble every original child row for pooled, age and phone diagnostics."""
    ids = result['rowIndices']
    require(len(ids) == len(set(ids)) == 5654, 'Incomplete original-child rows')
    selected_rows = [rows[i] for i in ids]
    counts = np.asarray([row['raterCounts'] for row in selected_rows])
    out = {}
    for seed in SEEDS:
        values = {name: {} for name in ('rare0', 'final', 'scalar')}
        for job in [job for job in jobs if job['seed'] == seed]:
            for name in values:
                record = candidates[job['id']] if name == 'rare0' else controls[job['references'][name]]
                pred = record['prediction']
                lookup = dict(zip(pred['rowIndices'], pred['logProbabilities'], strict=True))
                require(len(lookup) == len(pred['rowIndices']), 'Duplicate source prediction rows')
                for index in job['outerRows']:
                    require(index in lookup and index not in values[name], 'Missing or duplicate matched row')
                    values[name][index] = lookup[index]
        require(all(set(value) == set(ids) for value in values.values()), 'Incomplete matched coverage')
        logs = {name: np.asarray([value[i] for i in ids]) for name, value in values.items()}
        for name in ('rare0', 'final'):
            logs[name+'Mixture'] = np.logaddexp(logs[name], logs['scalar']) - np.log(2.)
        diagnostic = {}
        axes = [('pooled', 'all', np.ones(len(ids), dtype=bool), result['seeds'][str(seed)]['pooled'])]
        for axis, keys, labels in (('age', range(6, 13), [r['age'] for r in selected_rows]),
                                   ('phone', frozen.TARGETS[:23], [r['targetPhone'] for r in selected_rows])):
            axes.extend((axis, str(key), np.asarray(labels) == key,
                         result['seeds'][str(seed)]['groups'][axis][str(key)]) for key in keys)
        for axis, key, mask, saved in axes:
            pairs = {'primary': ('rare0Mixture', 'finalMixture'),
                     'compact': ('rare0', 'final')}
            values = {}
            for pair, (candidate, reference) in pairs.items():
                value = class_contribution(counts[mask], logs[candidate][mask], logs[reference][mask])
                require(abs(value['candidateNll']-saved['metrics'][candidate]['nll']) <= 1e-12
                        and abs(value['referenceNll']-saved['metrics'][reference]['nll']) <= 1e-12
                        and abs(value['nllDelta']-saved['deltas'][pair]['nll']) <= 1e-12,
                        'Class decomposition differs from frozen evaluator')
                values[pair] = value
            diagnostic.setdefault(axis, {})[key] = values
        out[str(seed)] = diagnostic
    return out


def evaluate(rows, jobs, candidates, controls):
    value = rename(frozen.evaluate(rows, jobs, candidates, controls), LABELS)
    for seed in SEEDS:
        item = value['seeds'][str(seed)]
        item['properLossSafeguards'] = extra_screen(item)
        item['strictSeedPass'] = bool(item['seedPass'] and item['properLossSafeguards']['passed'])
    across = value['acrossSeeds']
    across['strictDevelopmentScreenPass'] = bool(across['ageGuard']['passed']
            and all(value['seeds'][str(seed)]['strictSeedPass'] for seed in SEEDS))
    value['classConditional'] = class_views(rows, jobs, candidates, controls, value)
    return value


def calculate(path, sha, outer_path, outer_sha):
    plan, pin, bundle = s.load_plan(path, sha)
    control_pin = s.checked_control_freeze(plan, pin)
    candidates, outer_pin = s.checked_outer(plan, pin, bundle, outer_path, outer_sha)
    controls = s.checked_controls(plan, bundle)
    require(controls == s.read(s.read(control_pin)['records']), 'Control replay differs from preflight')
    value = evaluate(bundle['cohort']['rows'], plan['jobs'], candidates, controls)
    s.files.guard(plan['inputs']); s.files.guard(plan['sources'])
    return dict(complete=True, study=s.STUDY, plan=pin, controls=control_pin,
                outerFreeze=outer_pin, **value, **s.FLAGS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('evaluate', 'verify'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--outer-sha256', required=True)
    args = parser.parse_args()
    root = args.plan.resolve().parent
    result = calculate(args.plan, args.plan_sha256, root/'outer-freeze.json', args.outer_sha256)
    if args.command == 'evaluate':
        require(not (root/'results.json').exists(), 'Preserve existing results')
        s.files.write_json(root/'results.json', result)
    else:
        require(s.read(s.files.binding(root/'results.json')) == result,
                'Results do not reconstruct exactly')
    print(json.dumps(s.files.binding(root/'results.json')))


if __name__ == '__main__':
    main()
