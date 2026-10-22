"""Fixed same-seed comparisons; no seed choice or pooled-average rescue."""
import argparse
import json
from pathlib import Path

import numpy as np

from middle_layer.evaluation import metrics, difference, screen
from lexical_compact.core import require
from multiphone_data import TARGETS

SEEDS = (17, 29, 43)


def evaluate_seed(rows, indices, folds, logs):
    require(set(logs) == {'middle', 'final', 'scalar'}, 'Expected three matched predictions')
    require(len(indices) == len(set(indices)) == len(rows) == len(folds), 'Duplicate or incomplete rows')
    require(set(folds) == set(range(5)), 'Missing speaker fold')
    require(all(6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None for r in rows),
            'Expected original child positions')
    predictions = {k: np.asarray(v, dtype=np.float64) for k, v in logs.items()}
    for k in ('middle', 'final'):
        predictions[k+'Mixture'] = np.logaddexp(predictions[k], predictions['scalar']) - np.log(2.)
    pairs = dict(primary=('middleMixture', 'finalMixture'), compact=('middle', 'final'))

    def view(mask):
        chosen = [r for r, keep in zip(rows, mask, strict=True) if keep]
        values = {k: metrics(v[mask], chosen) for k, v in predictions.items()}
        return dict(metrics=values, deltas={k: difference(values[a], values[b]) for k, (a, b) in pairs.items()})

    pooled = view(np.ones(len(rows), dtype=bool))
    axes = dict(fold=(folds, range(5)), age=([r['age'] for r in rows], range(6, 13)),
                phone=([r['targetPhone'] for r in rows], TARGETS[:23]),
                child=([r['speakerId'] for r in rows], sorted({r['speakerId'] for r in rows})))
    groups = {axis: {str(k): view(np.asarray(values) == k) for k in keys}
              for axis, (values, keys) in axes.items()}
    primary = screen(pooled['deltas']['primary'],
                     [groups['fold'][str(i)]['deltas']['primary'] for i in range(5)],
                     pooled['metrics']['finalMixture']['nll'])
    compact = bool(pooled['deltas']['compact']['nll'] < -1e-7)
    return dict(pooled=pooled, groups=groups, screen=primary, compactCoCondition=compact,
                seedPass=bool(primary['directionalPass'] and compact))


def summarize(seeds):
    require(set(seeds) == {str(s) for s in SEEDS}, 'Exactly seeds 17, 29, 43 required')
    ordered = [seeds[str(s)] for s in SEEDS]

    def spread(values):
        if any(v is None for v in values):
            return None
        require(np.isfinite(values).all(), 'Nonfinite delta')
        return dict(mean=float(np.mean(values)), minimum=float(min(values)), maximum=float(max(values)))

    changes = {pair: {k: spread([s['pooled']['deltas'][pair][k] for s in ordered])
                     for k in ordered[0]['pooled']['deltas'][pair]} for pair in ('primary', 'compact')}
    groups = {}
    for axis in ('age', 'phone', 'child'):
        first = ordered[0]['groups'][axis]
        require(all(set(s['groups'][axis]) == set(first) for s in ordered), 'Subgroup inventory differs')
        groups[axis] = {}
        for key in first:
            views = [s['groups'][axis][key] for s in ordered]
            values = [v['metrics']['middleMixture'] for v in views]
            require(all(v is not None for v in values), 'Missing subgroup support')
            support = [{k: v[k] for k in ('positions', 'children', 'recordings', 'votes')} for v in values]
            require(all(s == support[0] for s in support), 'Subgroup support differs across seeds')
            nll = [v['deltas']['primary']['nll'] for v in views]
            groups[axis][key] = dict(support=support[0], nllChange=spread(nll),
                                    seedsWithWorseNll=sum(d > 1e-7 for d in nll),
                                    perSeedNllChange=dict(zip(map(str, SEEDS), nll, strict=True)))
    require(set(groups['age']) == {str(a) for a in range(6, 13)}, 'All seven ages required')
    failed_ages = [age for age, v in groups['age'].items() if v['seedsWithWorseNll'] == 3]
    age_guard = not failed_ages
    all_seeds = all(s['seedPass'] for s in ordered)
    return dict(changes=changes, groups=groups,
                regressionCounts={str(seed): {axis: sum(v['perSeedNllChange'][str(seed)] > 1e-7
                    for v in groups[axis].values()) for axis in groups} for seed in SEEDS},
                ageGuard=dict(passed=age_guard, agesWorseAtEverySeed=failed_ages),
                allSeedsPass=all_seeds, replicationPass=bool(all_seeds and age_guard),
                allSeedsMaterialGain=all(s['screen']['materialGainPass'] for s in ordered))


def evaluate(rows, jobs, candidates, controls):
    require(len(jobs) == 75 and len({j['id'] for j in jobs}) == 75
            and set(candidates) == {j['id'] for j in jobs}, 'Incomplete 75-job candidates')
    expected = {i for i, r in enumerate(rows) if 6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None}
    require(len(expected) == 5654, 'Expected all 5654 original child positions')
    require(set(controls) == {ref for j in jobs for ref in j['references'].values()}
            and len(controls) == 150, 'Incomplete controls')
    seeds = {}
    for seed in SEEDS:
        selected = [j for j in jobs if j['seed'] == seed]
        require(len(selected) == 25 and {(j['speakerFold'], j['wordGroup']) for j in selected}
                == {(s, w) for s in range(5) for w in range(5)}, 'Incomplete seed cells')
        values = {k: {} for k in ('middle', 'final', 'scalar')}; folds = {}
        for job in selected:
            require(job['objective'] == 'unweighted' and job['regime'] == 'child-only'
                    and job['family'] == 'pca16-scalars', 'Wrong scientific arm')
            for name in values:
                if name == 'middle':
                    record = candidates[job['id']]
                else:
                    family = 'scalars' if name == 'scalar' else 'pca16-scalars'
                    reference = f'seed{seed}-unweighted-child-only-{family}-s{job["speakerFold"]}-w{job["wordGroup"]}'
                    require(job['references'][name] == reference, 'Unmatched control seed/cell')
                    record = controls[reference]
                pred = record['prediction']; ids = pred['rowIndices']
                require(len(ids) == len(set(ids)), 'Duplicate prediction identities')
                require(name != 'middle' or ids == job['outerRows'], 'Candidate outer membership differs')
                lookup = dict(zip(ids, pred['logProbabilities'], strict=True))
                for i in job['outerRows']:
                    require(i in lookup and i not in values[name], 'Missing or duplicated matched row')
                    values[name][i] = lookup[i]
                    require(i not in folds or folds[i] == job['speakerFold'], 'Fold differs')
                    folds[i] = job['speakerFold']
        require(all(set(v) == expected for v in values.values()), 'Incomplete matched child coverage')
        ids = sorted(expected)
        seeds[str(seed)] = evaluate_seed([rows[i] for i in ids], ids, [folds[i] for i in ids],
                                        {k: [v[i] for i in ids] for k, v in values.items()})
    return dict(seeds=seeds, acrossSeeds=summarize(seeds), rowIndices=sorted(expected))


def discovery_check():
    """Reconstruct seed-7 views from frozen predictions, without fitting or inference."""
    from middle_layer_replication import study as s
    root = s.BASE/'middle-layer-heads-v1'
    pins = {key: s.files.binding(root/name, sha) for key, name, sha in (
        ('plan', 'plan.json', '08b9b403a317f684cd270d438f0f6070724fe741a16371c0b8a4b0f335cb1b71'),
        ('outer', 'outer-freeze.json', '324d79d85c63e623332f6402d9d96af7f1b341cc65476f9c6383ecc1a71c1c9e'),
        ('results', 'results.json', '9f28614a6cd8d55faa54cd295a1c31aec4ea2fb56ad00d6b04df40a635e9de7c'))}
    plan, outer, saved = [s.read(pins[k]) for k in ('plan', 'outer', 'results')]
    require(outer['plan'] == pins['plan'] and saved['outerFreeze'] == pins['outer'], 'Discovery lineage differs')
    rows = s.read(plan['inputs']['cohort'])['rows']
    values = {k: {} for k in ('middle', 'final', 'scalar')}; folds = {}
    require(len(plan['jobs']) == len(outer['predictions']) == 50, 'Incomplete discovery')
    for job, record in zip(plan['jobs'], outer['predictions'], strict=True):
        require(record['jobId'] == job['id'], 'Discovery job differs')
        pred = s.read(record['artifact'])['prediction']
        require(pred['rowIndices'] == job['outerRows'], 'Discovery rows differ')
        name = job['representation']
        for i, lp in zip(pred['rowIndices'], pred['logProbabilities'], strict=True):
            require(i not in values[name], 'Duplicate discovery candidate')
            values[name][i] = lp; folds[i] = job['speakerFold']
        scalar = s.read(job['references']['scalar'])['prediction']
        lookup = dict(zip(scalar['rowIndices'], scalar['logProbabilities'], strict=True))
        for i in job['outerRows']:
            require(i not in values['scalar'] or values['scalar'][i] == lookup[i], 'Discovery scalar differs')
            values['scalar'][i] = lookup[i]
    ids = saved['rowIndices']
    require(len(ids) == 5654 and all(set(v) == set(ids) for v in values.values()), 'Discovery coverage differs')
    result = evaluate_seed([rows[i] for i in ids], ids, [folds[i] for i in ids],
                           {k: [v[i] for i in ids] for k, v in values.items()})
    rename = dict(middle='l12', final='l24', scalar='scalar', middleMixture='l12Mixture', finalMixture='l24Mixture')
    def compare(a, b):
        require(all(a['metrics'][k] == b['metrics'][old] for k, old in rename.items())
                and all(a['deltas'][k] == b['deltas'][k] for k in ('primary', 'compact')),
                'Discovery evaluator differs')
    compare(result['pooled'], saved['pooled']); count = 1
    for axis, views in result['groups'].items():
        require(set(views) == set(saved['groups'][axis]), 'Discovery subgroup inventory differs')
        for key, value in views.items():
            compare(value, saved['groups'][axis][key]); count += 1
    require(result['screen'] == saved['screens']['primary']
            and result['compactCoCondition'] == saved['compactCoCondition'], 'Discovery decision differs')
    return dict(bindings=pins, exact=True, viewsCompared=count, seed=7)


def calculate(path, sha, outer_path, outer_sha):
    from middle_layer_replication import study as s
    plan, pin, bundle = s.load_plan(path, sha)
    control_pin = s.checked_control_freeze(plan, pin)
    candidates, outer_pin = s.checked_outer(plan, pin, bundle, outer_path, outer_sha)
    controls = s.checked_controls(plan, bundle)
    require(controls == s.read(s.read(control_pin)['records']), 'Control replay differs from preflight')
    value = evaluate(bundle['cohort']['rows'], plan['jobs'], candidates, controls)
    s.files.guard(plan['inputs']); s.files.guard(plan['sources'])
    return dict(complete=True, study=s.STUDY, plan=pin, controls=control_pin, outerFreeze=outer_pin,
                discoveryContext=discovery_check(), **value, **s.FLAGS)


def main():
    from middle_layer_replication import study as s
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('evaluate', 'verify'))
    parser.add_argument('--plan', type=Path, required=True); parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--outer-sha256', required=True)
    args = parser.parse_args(); root = args.plan.resolve().parent
    result = calculate(args.plan, args.plan_sha256, root/'outer-freeze.json', args.outer_sha256)
    if args.command == 'evaluate':
        require(not (root/'results.json').exists(), 'Preserve existing results')
        s.files.write_json(root/'results.json', result)
    else:
        require(s.read(s.files.binding(root/'results.json')) == result, 'Results do not reconstruct exactly')
    print(json.dumps(s.files.binding(root/'results.json')))


if __name__ == '__main__': main()
