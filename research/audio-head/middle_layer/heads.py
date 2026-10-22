"""Fresh matched compact heads on frozen middle/final representations."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
import torch

from middle_layer import extract, evaluation
from lexical_compact import core, study as compact
from lexical_heads import study as scalar
from lexical_expanded_heads import study as expanded

files, read, require = compact.files, compact.read, core.require
BASE = extract.BASE
OLD = BASE/'lexical-expanded-heads-v1'
OLD_PLAN = extract.PINS['expanded'][1]
OLD_OUTER = '6bf403e910d7330db3892c7366c6a4bcd7a694927d9c4c1cd467dad2ab2515df'
FLAGS = dict(authorTestRead=False, learnerFeedbackEligible=False,
             clinicalUseEligible=False, promotionEligible=False, independentFinalValidation=False)


def jobs_from_parent(parent, outer, cohort):
    rows = cohort['rows']
    references = {r['jobId']: r['artifact'] for r in outer['predictions']}
    original = {j['id']: j for j in parent['jobs']}
    tokens = {c['id']: [w['text'].upper() for w in c['words']] for c in cohort['clips']}
    groups = {w: expanded.inventory.prior.word_group(w) for words in tokens.values() for w in words}
    jobs = []
    for representation in ('middle', 'final'):
        for sf in range(5):
            for wg in range(5):
                name = f'child-only-pca16-scalars-s{sf}-w{wg}'
                old = original[name]
                expanded.check_job(old, rows, tokens, groups)
                control = original[f'child-only-scalars-s{sf}-w{wg}']
                require(all(set(old[k]) == set(control[k]) for k in
                            ('fitRows', 'selectionRows', 'refitRows', 'outerRows')), 'Unmatched scalar reference')
                job = dict(old, id=representation+'-'+name, representation=representation,
                    outerRows=[i for i in old['outerRows'] if 6 <= rows[i]['age'] <= 12
                               and rows[i]['legacyRowIndex'] is not None],
                    references={k: references[v] for k, v in
                                [('scalar', control['id']), ('retainedCompact', old['id'])]})
                jobs.append(job)
    expected = {i for i, r in enumerate(rows) if 6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None}
    for representation in ('middle', 'final'):
        ids = [i for j in jobs if j['representation'] == representation for i in j['outerRows']]
        require(len(ids) == len(set(ids)) == 5654 and set(ids) == expected, 'Original-child outer coverage differs')
    return jobs


def declaration(feature_report, feature_sha):
    extract.verify(feature_report, feature_sha)
    parent_pin = files.binding(OLD/'plan.json', OLD_PLAN)
    outer_pin = files.binding(OLD/'outer-freeze.json', OLD_OUTER)
    parent, outer = read(parent_pin), read(outer_pin)
    require(outer['complete'] and outer['plan'] == parent_pin, 'Incomplete parent outer freeze')
    cohort = read(parent['inputs']['cohort'])
    sources = {str(p): files.binding(p) for p in [
        Path(__file__), Path(evaluation.__file__), Path(__file__).with_name('test_heads.py'),
        Path(__file__).with_name('test_evaluation.py'), Path(core.__file__), Path(compact.__file__),
        Path(scalar.__file__), Path(scalar.core.__file__), Path(expanded.__file__),
        Path(expanded.evaluation.__file__), Path(expanded.evaluation.mixture.__file__),
        Path(expanded.inventory.__file__), Path(expanded.inventory.prior.__file__),
        Path(scalar.membership.__file__), Path(scalar.scoring.__file__),
        extract.HERE/'multiphone_models.py', extract.HERE/'multiphone_local_head.py',
        extract.HERE/'multiphone_child_train.py', extract.HERE/'multiphone_verify.py',
        extract.HERE/'multiphone_data.py', extract.HERE/'multiphone_research_audio.py']}
    return dict(inputs=dict(parentPlan=parent_pin, parentOuter=outer_pin,
        cohort=parent['inputs']['cohort'], featureReport=files.binding(feature_report, feature_sha),
        protocol=files.binding(extract.ROOT/'docs/model/middle-layer-protocol.md')),
        sources=sources, jobs=jobs_from_parent(parent, outer, cohort),
        recipe=core.RECIPE, transform=core.TRANSFORM_RECIPE,
        runtime=extract.environment(), mixtureWeights=[.5, .5], **FLAGS)


def load(path, sha):
    pin = files.binding(path, sha)
    plan = read(pin)
    feature = plan['inputs']['featureReport']
    require(plan == declaration(Path(feature['path']), feature['sha256']), 'Head declaration changed')
    report = read(feature)
    cohort = read(plan['inputs']['cohort'])
    indices = np.load(report['rowIndices']['path'], allow_pickle=False).tolist()
    shared = dict(cohort=cohort, positions={i: k for k, i in enumerate(indices)},
                  scalars=np.load(report['scalars']['path'], allow_pickle=False))
    bundles = {key: dict(shared, target=np.load(value['path'], allow_pickle=False))
               for key, value in report['matrices'].items()}
    return plan, pin, bundles


def config(job, pin, phase, selection):
    value = compact.config_value(job, pin, phase, selection)
    return dict(value, experiment='normalized-middle-layer-heads-v1',
                representation=job['representation'], addedValidationRows=job['addedValidationRows'])


def validate_run(job, run, pin, phase, rows):
    result = compact.validate_history(job, run, pin, phase, rows)
    cfg = read(run['artifacts']['config.json'])
    require(cfg['experiment'] == 'normalized-middle-layer-heads-v1'
            and cfg['representation'] == job['representation']
            and cfg['addedValidationRows'] == job['addedValidationRows'], 'Representation or validation policy differs')
    return result


def frozen(path, sha, plan, pin, phase, rows):
    binding = files.binding(path, sha)
    value = read(binding)
    require(value['complete'] and value['plan'] == pin and value['phase'] == phase
            and all(value.get(k) is v for k, v in FLAGS.items()) and value['outerPredictionsRead'] is False
            and [r['jobId'] for r in value['runs']] == [j['id'] for j in plan['jobs']], 'Incomplete phase freeze')
    for job, run in zip(plan['jobs'], value['runs'], strict=True):
        validate_run(job, run, pin, phase, rows)
    if phase == 'outer-refit':
        old, old_pin = frozen(Path(value['innerFreeze']['path']), value['innerFreeze']['sha256'], plan, pin, 'inner', rows)
        for run, previous in zip(value['runs'], old['runs'], strict=True):
            expected = dict(innerFreeze=old_pin, checkpoint=previous['artifacts']['best.pt'], epoch=previous['selectedEpoch'])
            require(run['selectedEpoch'] == previous['selectedEpoch']
                    and read(run['artifacts']['config.json'])['innerSelection'] == expected, 'Refit selection lineage differs')
    return value, binding


def fit(args, phase):
    plan, pin, bundles = load(args.plan, args.sha256)
    extract.checked_review(args.review, args.sha256)
    rows = bundles['middle']['cohort']['rows']
    previous, previous_pin = (None, None) if phase == 'inner' else frozen(
        args.plan.parent/'inner-freeze.json', args.inner_sha256, plan, pin, 'inner', rows)
    label = 'inner' if phase == 'inner' else 'refit'
    require(not (args.plan.parent/label).exists(), 'Preserve partial phase; no implicit restart')
    (args.plan.parent/label).mkdir()
    runs = []; started = time.monotonic()
    for number, job in enumerate(plan['jobs']):
        bundle = bundles[job['representation']]
        fit_ids = job['fitRows'] if phase == 'inner' else job['refitRows']
        data = core.prepare(bundle, 'pca16-scalars', fit_ids)
        selected = None if previous is None else previous['runs'][number]
        selection = None if selected is None else dict(innerFreeze=previous_pin,
            checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch'])
        destination = args.plan.parent/label/job['id']
        core.train(data, job['selectionRows'] if phase == 'inner' else [], destination,
                   config(job, pin, phase, selection), epochs=None if selected is None else selected['selectedEpoch'])
        if phase == 'inner':
            files.write_json(destination/'selected-replay.json', core.replay(destination, data, job['selectionRows']))
        x = bundle['target'][[bundle['positions'][i] for i in fit_ids]].astype(np.float64)
        variances = x.var(0)
        files.write_json(destination/'feature-diagnostics.json', dict(fitRows=fit_ids,
            pca16VarianceFraction=data['transform']['varianceFraction'],
            largestChannelVarianceShare=float(variances.max()/variances.sum())))
        artifacts = scalar.manifest(destination)
        report = scalar.check_manifest(artifacts)
        run = dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=report['bestEpoch'])
        validate_run(job, run, pin, phase, rows); runs.append(run)
        print(json.dumps(dict(phase=phase, completed=len(runs), total=50, job=job['id'], selectedEpoch=run['selectedEpoch'])), flush=True)
    files.guard(plan['inputs']); files.guard(plan['sources'])
    value = dict(complete=True, phase=phase, plan=pin, runs=runs,
                 wallSeconds=time.monotonic()-started, outerPredictionsRead=False, **FLAGS)
    if previous_pin: value['innerFreeze'] = previous_pin
    output = args.plan.parent/(label+'-freeze.json')
    files.write_json(output, value)
    return files.binding(output)


def predict(args):
    plan, pin, bundles = load(args.plan, args.sha256)
    rows = bundles['middle']['cohort']['rows']
    refits, refit_pin = frozen(args.plan.parent/'refit-freeze.json', args.refit_sha256, plan, pin, 'outer-refit', rows)
    destination = args.plan.parent/'outer'; require(not destination.exists(), 'Outer output exists'); destination.mkdir()
    predictions = []
    for job, run in zip(plan['jobs'], refits['runs'], strict=True):
        data = core.prepare(bundles[job['representation']], 'pca16-scalars', job['refitRows'])
        prediction = core.replay(Path(run['artifacts']['best.pt']['path']).parent, data, job['outerRows'])
        path = destination/(job['id']+'.json')
        files.write_json(path, dict(jobId=job['id'], checkpoint=run['artifacts']['best.pt'], prediction=prediction))
        predictions.append(dict(jobId=job['id'], artifact=files.binding(path)))
    output = args.plan.parent/'outer-freeze.json'
    files.guard(plan['inputs']); files.guard(plan['sources'])
    files.write_json(output, dict(complete=True, plan=pin, refitFreeze=refit_pin, predictions=predictions, **FLAGS))
    return files.binding(output)


def calculate(args):
    plan, pin, bundles = load(args.plan, args.sha256)
    rows = bundles['middle']['cohort']['rows']
    outer_pin = files.binding(args.plan.parent/'outer-freeze.json', args.outer_sha256)
    outer = read(outer_pin)
    require(outer['complete'] and outer['plan'] == pin
            and [r['jobId'] for r in outer['predictions']] == [j['id'] for j in plan['jobs']], 'Outer freeze differs')
    refits, _ = frozen(Path(outer['refitFreeze']['path']), outer['refitFreeze']['sha256'], plan, pin, 'outer-refit', rows)
    values = {name: {} for name in ('l12', 'l24', 'scalar', 'retainedCompact')}
    folds = {}; scalar_replays = {}; diagnostics = {}
    parent = read(plan['inputs']['parentPlan'])
    feature = read(parent['inputs']['featureReport'])
    scalar_pin = feature['inputs']['scalars']; files.guard({'scalars': scalar_pin})
    full_bundle = dict(cohort=bundles['middle']['cohort'],
        scalars=np.load(scalar_pin['path'], allow_pickle=False), positions={i: i for i in range(len(rows))})
    for job, saved, refit in zip(plan['jobs'], outer['predictions'], refits['runs'], strict=True):
        record = read(saved['artifact'])
        require(record['jobId'] == job['id'] and record['checkpoint'] == refit['artifacts']['best.pt'], 'Outer checkpoint lineage differs')
        pred = record['prediction']; ids = job['outerRows']
        diagnostics[job['id']] = dict(refit=read(refit['artifacts']['feature-diagnostics.json']),
                                     refitArtifact=refit['artifacts']['feature-diagnostics.json'])
        expanded.evaluation.checked_prediction(pred, ids, [rows[i] for i in ids])
        name = 'l12' if job['representation'] == 'middle' else 'l24'
        for i, lp in zip(ids, pred['logProbabilities'], strict=True):
            require(i not in values[name], 'Duplicate candidate output')
            values[name][i] = lp
            require(i not in folds or folds[i] == job['speakerFold'], 'Representation fold mismatch')
            folds[i] = job['speakerFold']
        for reference_name, reference_pin in job['references'].items():
            reference = read(reference_pin); prediction = reference['prediction']
            ri = prediction['rowIndices']
            require(len(ri) == len(set(ri)), 'Duplicate reference rows')
            expanded.evaluation.checked_prediction(prediction, ri, [rows[i] for i in ri])
            lookup = dict(zip(ri, prediction['logProbabilities'], strict=True))
            for i in ids:
                require(i in lookup and (i not in values[reference_name]
                        or values[reference_name][i] == lookup[i]), 'Reference identity mismatch')
                values[reference_name][i] = lookup[i]
            if reference_name == 'scalar' and reference_pin['sha256'] not in scalar_replays:
                # Replay the original complete cell with its original batch grouping.
                files.guard({'checkpoint': reference['refitCheckpoint']})
                directory = Path(reference['refitCheckpoint']['path']).parent
                cfg = json.loads((directory/'config.json').read_text())
                require(cfg['fitRows'] == job['refitRows'], 'Reference fitting membership differs')
                data = scalar.core.prepare(full_bundle, 'scalars', job['refitRows'])
                replay = scalar.core.replay(directory, data, ri)
                require(replay == prediction, 'Scalar reference replay differs')
                scalar_replays[reference_pin['sha256']] = dict(reference=reference_pin, exact=True, rows=len(ri))
    indices = sorted(values['l12'])
    require(len(indices) == 5654 and all(set(v) == set(indices) for v in values.values())
            and len(scalar_replays) == 25, 'Incomplete matched outer identities or scalar replay')
    result = evaluation.evaluate([rows[i] for i in indices], indices, [folds[i] for i in indices],
                                 {k: [v[i] for i in indices] for k, v in values.items()})
    inner = read(refits['innerFreeze'])
    for job, run in zip(plan['jobs'], inner['runs'], strict=True):
        diagnostics[job['id']].update(inner=read(run['artifacts']['feature-diagnostics.json']),
                                     innerArtifact=run['artifacts']['feature-diagnostics.json'])
    files.guard(plan['inputs']); files.guard(plan['sources'])
    return dict(complete=True, plan=pin, outerFreeze=outer_pin, scalarReferenceReplays=list(scalar_replays.values()),
                fitFeatureDiagnostics=diagnostics,
                rowIndices=indices, rowFolds=[folds[i] for i in indices], **result, **{'authorTestRead': False})


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    d = sub.add_parser('declare'); d.add_argument('--feature-report', type=Path, required=True)
    d.add_argument('--feature-sha256', required=True); d.add_argument('--out', type=Path, required=True)
    for name in ('inner', 'refit', 'outer', 'evaluate', 'verify'):
        t = sub.add_parser(name); t.add_argument('--plan', type=Path, required=True); t.add_argument('--sha256', required=True)
        if name in ('inner', 'refit'): t.add_argument('--review', type=Path, required=True)
        if name == 'refit': t.add_argument('--inner-sha256', required=True)
        if name == 'outer': t.add_argument('--refit-sha256', required=True)
        if name in ('evaluate', 'verify'): t.add_argument('--outer-sha256', required=True)
    args = p.parse_args()
    if args.command == 'declare':
        require(not args.out.exists() and args.out.resolve().is_relative_to(BASE), 'Fresh research output required')
        value = declaration(args.feature_report.resolve(), args.feature_sha256)
        args.out.mkdir(); files.write_json(args.out/'plan.json', value); result = files.binding(args.out/'plan.json')
    elif args.command == 'outer': result = predict(args)
    elif args.command in ('evaluate', 'verify'):
        value = calculate(args); output = args.plan.parent/'results.json'
        if args.command == 'evaluate': files.write_json(output, value)
        else: require(read(files.binding(output)) == value, 'Saved results do not reconstruct')
        result = files.binding(output)
    else: result = fit(args, 'inner' if args.command == 'inner' else 'outer-refit')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
