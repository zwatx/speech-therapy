"""Bound, phased rating-zero proper-loss experiment. Declaration never fits a head."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from middle_layer import extract, heads
from middle_layer_replication import study as previous
from lexical_expanded_heads import study as expanded
from lexical_seed_replication import study as historical, validation
from temporal_pooling import study as temporal
from rare0_proper_loss import core

files, read, require = historical.files, historical.read, historical.require
BASE, ROOT = extract.BASE, extract.ROOT
FLAGS = dict(heads.FLAGS)
STUDY = 'rare0-proper-loss-v1'
PROTOCOL = ROOT/'docs/model/rare0-proper-loss-protocol.md'
SEEDS = core.SEEDS
ROLES = ('fitRows', 'selectionRows', 'addedValidationRows', 'refitRows')
PINS = {k: v for k, v in temporal.PINS.items() if k not in ('featureReport', 'extractionReview')}
PILOT_JOB = 'seed17-unweighted-child-only-pca16-scalars-s0-w0'


def source_paths():
    return set(Path(__file__).parent.glob('*.py')) | {
        Path(temporal.__file__), Path(previous.__file__), Path(historical.__file__),
        Path(validation.__file__), Path(core.seeded.__file__), Path(core.compact.__file__),
        Path(extract.__file__), Path(heads.__file__),
        extract.HERE/'multiphone_models.py', extract.HERE/'multiphone_local_head.py'}


def make_jobs(old, rows, inventory=None):
    """Use the exact historical row order, then retain only original child outer rows."""
    originals = {j['id']: j for j in old['jobs']}
    if inventory is not None:
        base = {j['id']: j for j in old['baseJobs']}
        checked = set()
    jobs = []
    for seed in SEEDS:
        for sf in range(5):
            for wg in range(5):
                prefix = f'seed{seed}-unweighted-child-only-'
                refs = {'scalar': prefix+f'scalars-s{sf}-w{wg}',
                        'final': prefix+f'pca16-scalars-s{sf}-w{wg}'}
                require(all(k in originals for k in refs.values()), 'Historical control cell missing')
                final, scalar = (originals[refs[k]] for k in ('final', 'scalar'))
                if inventory is not None:
                    source = base[final['baseJobId']]
                    if source['id'] not in checked:
                        expanded.check_job(source, rows, inventory['canonicalTokens'], inventory['wordGroups'])
                        checked.add(source['id'])
                    require(all(final[k] == source[k] for k in ROLES+('outerRows',)),
                            'Historical seed partition differs from validated expanded job')
                require(all(final[k] == scalar[k] for k in ROLES+('outerRows',)),
                        'Ordered control membership differs')
                require(final['seed'] == seed and final['speakerFold'] == sf and final['wordGroup'] == wg
                        and final['objective'] == 'unweighted' and final['regime'] == 'child-only'
                        and final['family'] == core.FAMILY and scalar['family'] == 'scalars',
                        'Historical control identity differs')
                outer = [i for i in final['outerRows'] if 6 <= rows[i]['age'] <= 12
                         and rows[i]['legacyRowIndex'] is not None]
                require(all(6 <= rows[i]['age'] <= 12 for k in ROLES for i in final[k]),
                        'Child-only fitting rows changed')
                jobs.append(dict(final, id='rare0-'+final['id'], outerRows=outer,
                                 representation='final-pca16-scalars', references=refs))
        ids = [i for j in jobs if j['seed'] == seed for i in j['outerRows']]
        expected = {i for i, row in enumerate(rows) if 6 <= row['age'] <= 12
                    and row['legacyRowIndex'] is not None}
        require(len(ids) == len(set(ids)) == 5654 and set(ids) == expected,
                'Original child outer coverage differs')
    require(len(jobs) == 75, 'Expected 75 candidate jobs')
    return jobs


def _bindings():
    pins = {k: files.binding(path, sha) for k, (path, sha) in PINS.items()}
    old = read(pins['historicalPlan'])
    pins.update(cohort=old['inputs']['cohort'], historicalFeatureReport=old['inputs']['featureReport'],
                protocol=files.binding(PROTOCOL))
    feature = read(pins['historicalFeatureReport'])
    pins.update(historicalTarget=feature['matrices']['target'],
                historicalScalars=feature['inputs']['scalars'])
    for name, binding in read(pins['candidatePlan'])['sources'].items():
        pins['candidateSource/'+name] = binding
    for name, binding in read(pins['priorProbePlan'])['sources'].items():
        pins['priorProbeSource/'+name] = binding
    cohort = read(pins['cohort'])
    jobs = make_jobs(old, cohort['rows'], read(old['inputs']['inventoryReport']))
    selected = {ref for job in jobs for ref in job['references'].values()}
    require(len(selected) == 150, 'Exactly 150 same-seed controls required')
    for phase in ('Inner', 'Refit', 'Outer'):
        frozen = read(pins['historical'+phase])
        require(frozen['complete'] is True and frozen['plan'] == pins['historicalPlan'],
                'Incomplete historical control phase')
        records = {r['jobId']: r for r in frozen['predictions' if phase == 'Outer' else 'runs']}
        require(selected <= records.keys(), 'Historical control artifacts missing')
        for job_id in sorted(selected):
            artifacts = {'prediction': records[job_id]['artifact']} if phase == 'Outer' else records[job_id]['artifacts']
            for name, binding in artifacts.items():
                pins[f'control/{phase}/{job_id}/{name}'] = binding
    files.guard(pins)
    return pins, jobs


def declaration(phase='pilot', pilot_freeze=None, pilot_sha=None, pilot_review=None):
    require(phase in ('pilot', 'full'), 'Unknown declaration phase')
    pins, jobs = _bindings()
    if phase == 'full':
        require(pilot_freeze is not None and pilot_sha and pilot_review is not None,
                'Reviewed completed pilot required for full plan')
        pilot = files.binding(pilot_freeze, pilot_sha)
        pilot_value = read(pilot)
        require(pilot_value['complete'] is True and pilot_value['phase'] == 'pilot'
                and pilot_value['study'] == STUDY and pilot_value['jobId'] == 'rare0-'+PILOT_JOB
                and pilot_value['weightsDiscarded'] is True
                and pilot_value['trainingPerformed'] is True
                and pilot_value['outerInferencePerformed'] is False
                and 'best.pt' not in pilot_value['artifacts']
                and 'selection.json' not in pilot_value['artifacts'],
                'Pilot freeze differs')
        files.guard(pilot_value['artifacts'])
        files.guard({'pilotFitReplay': pilot_value['fitReplay']})
        pilot_plan = read(pilot_value['plan'])
        require(pilot_plan == declaration('pilot'), 'Pilot declaration/source changed')
        pins['pilotFreeze'] = pilot
        pins['pilotReview'] = review_binding(pilot_review, pilot_value['plan']['sha256'])
        require(read(pins['pilotReview']).get('pilotFreeze') == pilot,
                'Pilot review did not bind completed pilot')
    sources = {str(p.resolve()): files.binding(p) for p in sorted(source_paths())}
    return dict(study=STUDY, phase=phase, inputs=pins, sources=sources,
                jobs=[j for j in jobs if j['id'] == 'rare0-'+PILOT_JOB] if phase == 'pilot' else jobs,
                seeds=list(SEEDS), objective=core.OBJECTIVE, binaryCoefficient=core.COEFFICIENT,
                historicalObjective='unweighted', recipes={str(s): core.seeded.recipe(s) for s in SEEDS},
                transform=core.compact.TRANSFORM_RECIPE, runtime=extract.environment(),
                pilotEpochs=10 if phase == 'pilot' else None,
                innerFits=0 if phase == 'pilot' else 75, refits=0 if phase == 'pilot' else 75,
                outerPasses=0 if phase == 'pilot' else 75, controlReplays=0 if phase == 'pilot' else 150,
                mixtureWeights=[.5, .5],
                phaseOrder='pilot fitting-only, discard weights' if phase == 'pilot' else
                'reviewed pilot; all 150 control replays; all 75 inner; all 75 refit; all 75 outer',
                trainingPerformed=False, outerInferencePerformed=False, **FLAGS)


def declare(output, phase='pilot', pilot_freeze=None, pilot_sha=None, pilot_review=None):
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(BASE), 'Fresh research output required')
    value = declaration(phase, pilot_freeze, pilot_sha, pilot_review)
    output.mkdir(mode=0o700)
    files.write_json(output/'plan.json', value)
    return files.binding(output/'plan.json')


def load_plan(path, sha):
    pin = files.binding(path, sha)
    plan = read(pin)
    inputs = plan['inputs']
    pilot = inputs.get('pilotFreeze')
    require(plan == declaration(plan['phase'], None if pilot is None else pilot['path'],
                                None if pilot is None else pilot['sha256'],
                                None if pilot is None else inputs['pilotReview']['path']),
            'Rare0 declaration changed')
    files.guard(plan['sources'])
    feature = read(inputs['historicalFeatureReport'])
    bundle = dict(cohort=read(inputs['cohort']),
                  positions={i: i for i in range(len(read(inputs['cohort'])['rows']))},
                  target=np.load(inputs['historicalTarget']['path'], allow_pickle=False),
                  scalars=np.load(inputs['historicalScalars']['path'], allow_pickle=False))
    return plan, pin, bundle


def review_binding(path, sha):
    binding = files.binding(path)
    extract.checked_review(Path(binding['path']), sha)
    return binding


def config_value(job, pin, phase, selection=None):
    return dict(historical.config_value(job, pin, phase, selection), study=STUDY,
                representation='final-pca16-scalars', featureReport=read(pin)['inputs']['historicalFeatureReport'],
                objective=core.OBJECTIVE, binaryCoefficient=core.COEFFICIENT,
                historicalObjective='unweighted')


def fresh_phase(root, label):
    require(not any((root/name).exists() for name in (label, label+'-started.json',
            label+'-freeze.json', label+'-failure.json')), 'Preserve partial phase; no implicit restart')
    (root/label).mkdir()


def _manifest(output):
    artifacts = historical.parent.scalar.manifest(output)
    return artifacts, historical.parent.scalar.check_manifest(artifacts)


def same_model(left, right):
    a = torch.load(left['path'], map_location='cpu', weights_only=True)['model']
    b = torch.load(right['path'], map_location='cpu', weights_only=True)['model']
    require(list(a) == list(b) and all(torch.equal(a[k], b[k]) for k in a),
            'Initial model tensors differ from same-seed compact control')


def _control_run(plan, job, phase):
    old = read(plan['inputs']['historical'+('Inner' if phase == 'inner' else 'Refit')])
    return next(r for r in old['runs'] if r['jobId'] == job['references']['final'])


def validate_run(job, record, pin, phase, cohort):
    require(record['jobId'] == job['id'] and phase in ('inner', 'outer-refit'), 'Wrong candidate run')
    artifacts, report = record['artifacts'], historical.parent.scalar.check_manifest(record['artifacts'])
    checked = core.validate_run(Path(artifacts['config.json']['path']).parent, cohort,
        seed=job['seed'], phase=phase,
        fit_rows=job['fitRows' if phase == 'inner' else 'refitRows'],
        selection_rows=job['selectionRows'] if phase == 'inner' else [])
    require(checked == report, 'Independent candidate run validation differs')
    cfg = read(artifacts['config.json'])
    fit = job['fitRows' if phase == 'inner' else 'refitRows']
    require(cfg['study'] == STUDY and cfg['plan'] == pin and cfg['phase'] == phase
            and cfg['job'] == {k: job[k] for k in validation.JOB_FIELDS}
            and cfg['objective'] == core.OBJECTIVE and cfg['binaryCoefficient'] == 1.
            and cfg['fitRows'] == fit and cfg['selectionRows'] == (job['selectionRows'] if phase == 'inner' else [])
            and cfg['featureWidth'] == 29 and cfg['transformRecipe'] == core.compact.TRANSFORM_RECIPE
            and cfg['addedValidationRowsNotUsedForSelection'] == job['addedValidationRows'],
            'Candidate configuration/partition/objective differs')
    require(report['complete'] is True and report['objective'] == core.OBJECTIVE
            and report['bestEpoch'] == record['selectedEpoch'] and report['phase'] == phase,
            'Candidate report differs')
    transform = torch.load(artifacts['transform.pt']['path'], map_location='cpu', weights_only=True)
    require(transform['fitRows'] == fit and transform['rank'] == 16,
            'PCA fit membership or rank differs')
    history = read(artifacts['history.json'])
    require(all(np.isfinite(h['trainLoss']) and np.isfinite(h['trainCategoricalNLL'])
                and np.isfinite(h['trainRating0BinaryNLL']) and
                abs(h['trainLoss'] - h['trainCategoricalNLL'] - h['trainRating0BinaryNLL']) < 1e-5
                for h in history), 'Unauditable loss terms')
    require(report['bestEpoch'] >= 1 and (phase != 'inner' or
            read(artifacts['selected-replay.json']) == history[report['bestEpoch']-1]['selection']),
            'Ordinary selection/replay differs')
    control = _control_run(read(pin), job, phase)
    same_model(artifacts['initial.pt'], control['artifacts']['initial.pt'])
    historical_history = read(control['artifacts']['history.json'])
    common = min(len(history), len(historical_history))
    require(common > 0 and all(history[i]['orderSha256'] == historical_history[i]['orderSha256']
            for i in range(common)), 'Supervised batch-order prefix differs from same-seed control')
    return report


def checked_controls(plan, bundle):
    return previous.checked_controls(plan, bundle)


def checked_control_freeze(plan, pin):
    binding = files.binding(Path(pin['path']).parent/'controls-freeze.json')
    value = read(binding)
    require(value['complete'] is True and value['study'] == STUDY and value['plan'] == pin
            and value['controlCount'] == 150 and value['probeReuse'] == temporal.prior_probes(plan)
            and value['trainingPerformed'] is False and value['outerInferencePerformed'] is True
            and all(value[k] is v for k, v in FLAGS.items()), 'Control preflight differs')
    require(review_binding(value['review']['path'], pin['sha256']) == value['review'],
            'Control review differs')
    require(set(read(value['records'])) == {ref for j in plan['jobs'] for ref in j['references'].values()},
            'Missing control replay')
    return binding


def controls(path, sha, review):
    plan, pin, bundle = load_plan(path, sha)
    require(plan['phase'] == 'full', 'Controls require full declaration')
    reviewed = review_binding(review, sha)
    reuse = temporal.prior_probes(plan)
    root = Path(pin['path']).parent
    fresh_phase(root, 'controls')
    files.write_json(root/'controls-started.json', dict(plan=pin, review=reviewed, probeReuse=reuse))
    try:
        records = checked_controls(plan, bundle)
        files.write_json(root/'controls'/'records.json', records)
        files.guard(plan['inputs']); files.guard(plan['sources'])
        files.write_json(root/'controls-freeze.json', dict(complete=True, study=STUDY, plan=pin,
            review=reviewed, controlCount=150, probeReuse=reuse,
            records=files.binding(root/'controls'/'records.json'),
            trainingPerformed=False, outerInferencePerformed=True, **FLAGS))
        return checked_control_freeze(plan, pin)
    except Exception as error:
        files.write_json(root/'controls-failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


def pilot(path, sha, review):
    plan, pin, bundle = load_plan(path, sha)
    require(plan['phase'] == 'pilot' and len(plan['jobs']) == 1, 'Pilot plan required')
    reviewed = review_binding(review, sha)
    root = Path(pin['path']).parent
    fresh_phase(root, 'pilot')
    files.write_json(root/'pilot-started.json', dict(plan=pin, review=reviewed))
    job = plan['jobs'][0]
    try:
        data = core.prepare(bundle, job['fitRows'])
        output = root/'pilot'/job['id']
        core.train(data, [], output, config_value(job, pin, 'pilot'), seed=17, epochs=10, pilot=True)
        artifacts = historical.parent.scalar.manifest(output)
        report = read(artifacts['report.json'])
        require(core.validate_run(output, bundle['cohort'], seed=17, phase='pilot',
                    fit_rows=job['fitRows'], selection_rows=[]) == report,
                'Independent pilot state validation differs')
        require(report['phase'] == 'pilot' and report['epochsRun'] == 10
                and report['bestEpoch'] == 0 and report['selectionRows'] == []
                and 'best.pt' not in artifacts and 'selection.json' not in artifacts,
                'Pilot acquired selection or outer state')
        same_model(artifacts['initial.pt'], _control_run(plan, job, 'inner')['artifacts']['initial.pt'])
        replay = core.replay(output, data, job['fitRows'], seed=17, checkpoint='last.pt')
        files.write_json(output/'fit-replay.json', replay)
        files.guard(plan['inputs']); files.guard(plan['sources'])
        files.write_json(root/'pilot-freeze.json', dict(complete=True, phase='pilot', study=STUDY,
            plan=pin, review=reviewed, jobId=job['id'], artifacts=artifacts,
            fitReplay=files.binding(output/'fit-replay.json'), weightsDiscarded=True,
            trainingPerformed=True, outerInferencePerformed=False, **FLAGS))
        return files.binding(root/'pilot-freeze.json')
    except Exception as error:
        files.write_json(root/'pilot-failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


def check_freeze(plan, pin, path, sha, phase, cohort):
    label = 'inner' if phase == 'inner' else 'refit'
    require(phase in ('inner', 'outer-refit') and Path(path).resolve() == Path(pin['path']).parent/(label+'-freeze.json'),
            'Canonical candidate freeze required')
    binding = files.binding(path, sha); value = read(binding)
    require(value['complete'] is True and value['study'] == STUDY and value['phase'] == phase
            and value['plan'] == pin and value['controls'] == checked_control_freeze(plan, pin)
            and value['trainingPerformed'] is True and value['outerInferencePerformed'] is False
            and len(value['runs']) == 75 and [r['jobId'] for r in value['runs']] == [j['id'] for j in plan['jobs']],
            'Incomplete candidate phase')
    require(review_binding(value['review']['path'], pin['sha256']) == value['review'], 'Run review differs')
    for job, record in zip(plan['jobs'], value['runs'], strict=True):
        validate_run(job, record, pin, phase, cohort)
    if phase == 'outer-refit':
        inner, inner_pin = check_freeze(plan, pin, value['innerFreeze']['path'],
                                        value['innerFreeze']['sha256'], 'inner', cohort)
        for record, selected in zip(value['runs'], inner['runs'], strict=True):
            require(record['selectedEpoch'] == selected['selectedEpoch'] and
                    read(record['artifacts']['config.json'])['innerSelection'] == dict(
                    innerFreeze=inner_pin, checkpoint=selected['artifacts']['best.pt'],
                    epoch=selected['selectedEpoch']), 'Refit epoch lineage differs')
    return value, binding


def fit(path, sha, phase, review, freeze_path=None, freeze_sha=None):
    require(phase in ('inner', 'outer-refit'), 'Unknown fitting phase')
    plan, pin, bundle = load_plan(path, sha)
    require(plan['phase'] == 'full', 'Full declaration required')
    reviewed = review_binding(review, sha)
    controls_pin = checked_control_freeze(plan, pin)
    previous_freeze, previous_pin = (None, None) if phase == 'inner' else check_freeze(
        plan, pin, freeze_path, freeze_sha, 'inner', bundle['cohort'])
    root = Path(pin['path']).parent; label = 'inner' if phase == 'inner' else 'refit'
    fresh_phase(root, label)
    files.write_json(root/(label+'-started.json'), dict(plan=pin, review=reviewed,
        controls=controls_pin, innerFreeze=previous_pin))
    runs = []; started = time.monotonic()
    try:
        for number, job in enumerate(plan['jobs']):
            data = core.prepare(bundle, job['fitRows' if phase == 'inner' else 'refitRows'])
            selected = None if previous_freeze is None else previous_freeze['runs'][number]
            selection = None if selected is None else dict(innerFreeze=previous_pin,
                checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch'])
            output = root/label/job['id']
            core.train(data, job['selectionRows'] if phase == 'inner' else [], output,
                config_value(job, pin, phase, selection), seed=job['seed'],
                epochs=None if selected is None else selected['selectedEpoch'])
            if phase == 'inner':
                files.write_json(output/'selected-replay.json',
                    core.replay(output, data, job['selectionRows'], seed=job['seed']))
            artifacts, report = _manifest(output)
            record = dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=report['bestEpoch'])
            validate_run(job, record, pin, phase, bundle['cohort']); runs.append(record)
            print(json.dumps(dict(phase=phase, completed=len(runs), total=75, job=job['id'])), flush=True)
        files.guard(plan['inputs']); files.guard(plan['sources'])
        frozen = dict(complete=True, study=STUDY, phase=phase, plan=pin, review=reviewed,
            controls=controls_pin, runs=runs, elapsedSeconds=time.monotonic()-started,
            trainingPerformed=True, outerInferencePerformed=False, **FLAGS)
        if previous_pin is not None: frozen['innerFreeze'] = previous_pin
        files.write_json(root/(label+'-freeze.json'), frozen)
        return files.binding(root/(label+'-freeze.json'))
    except Exception as error:
        files.write_json(root/(label+'-failure.json'), dict(error=f'{type(error).__name__}: {error}',
            completedJobs=[r['jobId'] for r in runs]))
        raise


def outer(path, sha, freeze_path, freeze_sha):
    plan, pin, bundle = load_plan(path, sha)
    require(plan['phase'] == 'full', 'Full declaration required')
    refits, refit_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'outer-refit', bundle['cohort'])
    root = Path(pin['path']).parent; fresh_phase(root, 'outer')
    files.write_json(root/'outer-started.json', dict(plan=pin, refitFreeze=refit_pin))
    predictions = []; started = time.monotonic()
    try:
        for job, fitted in zip(plan['jobs'], refits['runs'], strict=True):
            data = core.prepare(bundle, job['refitRows'])
            pred = core.replay(Path(fitted['artifacts']['best.pt']['path']).parent,
                               data, job['outerRows'], seed=job['seed'])
            prior = np.asarray([data['priors'][bundle['cohort']['rows'][i]['targetPhone']]['probabilities']
                                for i in job['outerRows']])
            output = root/'outer'/(job['id']+'.json')
            files.write_json(output, dict(study=STUDY,
                job={k: job[k] for k in validation.JOB_FIELDS},
                refitCheckpoint=fitted['artifacts']['best.pt'], prediction=pred,
                prior=dict(rowIndices=job['outerRows'], probabilities=prior.tolist(),
                           logProbabilities=np.log(prior).tolist()), headInferencePerformed=True, **FLAGS))
            predictions.append(dict(jobId=job['id'], artifact=files.binding(output)))
        files.guard(plan['inputs']); files.guard(plan['sources'])
        files.write_json(root/'outer-freeze.json', dict(complete=True, study=STUDY, plan=pin,
            refitFreeze=refit_pin, predictions=predictions,
            elapsedSeconds=time.monotonic()-started,
            trainingPerformed=False, outerInferencePerformed=True, **FLAGS))
        return files.binding(root/'outer-freeze.json')
    except Exception as error:
        files.write_json(root/'outer-failure.json', dict(error=f'{type(error).__name__}: {error}',
            completedJobs=[p['jobId'] for p in predictions]))
        raise


def checked_outer(plan, pin, bundle, freeze_path, freeze_sha):
    require(Path(freeze_path).resolve() == Path(pin['path']).parent/'outer-freeze.json',
            'Canonical outer freeze required')
    outer_pin = files.binding(freeze_path, freeze_sha); frozen = read(outer_pin)
    require(frozen['complete'] is True and frozen['study'] == STUDY and frozen['plan'] == pin
            and frozen['trainingPerformed'] is False and frozen['outerInferencePerformed'] is True
            and all(frozen[k] is v for k, v in FLAGS.items())
            and len(frozen['predictions']) == 75 and
            [p['jobId'] for p in frozen['predictions']] == [j['id'] for j in plan['jobs']],
            'Incomplete 75 outer predictions')
    refits, _ = check_freeze(plan, pin, frozen['refitFreeze']['path'],
                             frozen['refitFreeze']['sha256'], 'outer-refit', bundle['cohort'])
    inner = read(refits['innerFreeze']); records = {}
    for job, pred, fitted, selected in zip(plan['jobs'], frozen['predictions'], refits['runs'], inner['runs'], strict=True):
        require(Path(pred['artifact']['path']) == Path(pin['path']).parent/'outer'/(job['id']+'.json'),
                'Outer artifact path differs')
        data = core.prepare(bundle, job['refitRows'])
        value = read(pred['artifact'])
        require(value['study'] == STUDY and value['job'] == {k: job[k] for k in validation.JOB_FIELDS}
                and value['refitCheckpoint'] == fitted['artifacts']['best.pt']
                and value['headInferencePerformed'] is True
                and all(value[k] is v for k, v in FLAGS.items()), 'Outer lineage differs')
        replay = core.replay(Path(fitted['artifacts']['best.pt']['path']).parent,
                             data, job['outerRows'], seed=job['seed'])
        require(value['prediction'] == replay, 'Outer replay differs')
        prior = np.asarray([data['priors'][bundle['cohort']['rows'][i]['targetPhone']]['probabilities']
                            for i in job['outerRows']])
        require(value['prior'] == dict(rowIndices=job['outerRows'], probabilities=prior.tolist(),
                                      logProbabilities=np.log(prior).tolist()), 'Outer prior differs')
        fit_data = core.prepare(bundle, job['fitRows'])
        require(core.replay(Path(selected['artifacts']['best.pt']['path']).parent,
                            fit_data, job['selectionRows'], seed=job['seed']) ==
                read(selected['artifacts']['selected-replay.json']), 'Selected replay differs')
        records[job['id']] = dict(prediction=value['prediction'], prior=value['prior'])
    return records, outer_pin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare-pilot', 'pilot', 'declare-full', 'controls', 'inner', 'refit', 'outer'))
    for name in ('plan', 'freeze', 'output', 'review', 'pilot-freeze', 'pilot-review'):
        parser.add_argument('--'+name, type=Path)
    for name in ('plan-sha256', 'freeze-sha256', 'pilot-sha256'):
        parser.add_argument('--'+name)
    args = parser.parse_args()
    if args.command == 'declare-pilot': result = declare(args.output)
    elif args.command == 'declare-full': result = declare(args.output, 'full', args.pilot_freeze,
                                                          args.pilot_sha256, args.pilot_review)
    elif args.command == 'pilot': result = pilot(args.plan, args.plan_sha256, args.review)
    elif args.command == 'controls': result = controls(args.plan, args.plan_sha256, args.review)
    elif args.command == 'outer': result = outer(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256)
    else: result = fit(args.plan, args.plan_sha256,
                       'inner' if args.command == 'inner' else 'outer-refit', args.review,
                       args.freeze, args.freeze_sha256)
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
