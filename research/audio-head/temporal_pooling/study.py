"""Seventy-five fixed temporal-bin fits with complete, reviewed phase barriers.

The experiment field is the frozen trainer's compatibility tag; study and
representation identify this experiment and are checked independently.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from middle_layer import extract as old_extract, heads
from temporal_pooling import extract, core
from middle_layer_replication import study as previous
from middle_layer_replication import evaluation as previous_evaluation
from lexical_seed_replication import study as historical, validation

files, read, require = historical.files, historical.read, historical.require
BASE, ROOT = old_extract.BASE, old_extract.ROOT
FLAGS = dict(heads.FLAGS)
SEEDS = (17, 29, 43)
STUDY = 'temporal-pooling-heads-v1'
REPRESENTATION = 'final-pre-interval-post'
PROTOCOL = ROOT / 'docs/model/temporal-pooling-protocol.md'
OLD = BASE / 'lexical-seed-replication-v1'
PINS = {key: value for key, value in previous.PINS.items() if key not in ('featureReport', 'candidateReview')}
PINS.update(
    priorProbePlan=(BASE/'middle-layer-replication-v1/plan.json', 'fd24799ff5e1226f7c14514b4c09e52e7781937710e2c3efe69b94e32ad1cef0'),
    priorProbeFreeze=(BASE/'middle-layer-replication-v1/controls-freeze.json', 'b5a9453cd2afdae905250c735ef79af3d6d22381d94e3abff0a327f7c446df0a'),
    priorProbeReview=(ROOT/'work/middle-layer-replication-review-20260927/results-review.json', '835ea9a253fce0c4fc1cb9b2b4cfada51fb520fc1121fcd0384ae163f6e2333d'))
ROLES = ('fitRows', 'selectionRows', 'addedValidationRows', 'refitRows')


def make_jobs(old, candidate, rows):
    originals = {j['id']: j for j in old['jobs']}
    base = [j for j in candidate['jobs'] if j['representation'] == 'middle']
    require(len(base) == 25 and len({(j['speakerFold'], j['wordGroup']) for j in base}) == 25,
            'Complete candidate cells required')
    jobs = []
    for seed in SEEDS:
        for source in base:
            sf, wg = source['speakerFold'], source['wordGroup']
            prefix = f'seed{seed}-unweighted-child-only-'
            refs = {name: prefix+family+f'-s{sf}-w{wg}' for name, family in
                    (('scalar', 'scalars'), ('final', 'pca16-scalars'))}
            old_job = originals[refs['final']]
            for name, ref in refs.items():
                control = originals[ref]
                require(control['seed'] == seed and control['objective'] == 'unweighted'
                        and control['regime'] == 'child-only' and control['family'] ==
                        ('scalars' if name == 'scalar' else 'pca16-scalars'), 'Control identity differs')
                require(all(control[k] == source[k] for k in ROLES), 'Ordered fitting/selection membership differs')
                expected = [i for i in control['outerRows'] if 6 <= rows[i]['age'] <= 12
                            and rows[i]['legacyRowIndex'] is not None]
                require(expected == source['outerRows'], 'Original child outer membership/order differs')
            jobs.append(dict(old_job, id='temporal-'+old_job['id'], outerRows=source['outerRows'],
                             representation=REPRESENTATION, references=refs))
        ids = [i for j in jobs if j['seed'] == seed for i in j['outerRows']]
        expected = {i for i, r in enumerate(rows) if 6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None}
        require(len(ids) == len(set(ids)) == 5654 and set(ids) == expected, 'Incomplete original child coverage')
    return jobs


def declaration(feature_report, feature_sha, extraction_review, extraction_review_sha):
    pins = {key: files.binding(path, sha) for key, (path, sha) in PINS.items()}
    pins['featureReport'] = files.binding(feature_report, feature_sha)
    pins['extractionReview'] = files.binding(extraction_review, extraction_review_sha)
    extract.verify(Path(pins['featureReport']['path']), pins['featureReport']['sha256'])
    receipt = read(pins['extractionReview'])
    require(receipt.get('independent') is True and receipt.get('verdict') == 'clear'
            and receipt.get('blockingFindings') == [] and receipt.get('report') == pins['featureReport'],
            'Matching independent extraction result review required')
    old, candidate = read(pins['historicalPlan']), read(pins['candidatePlan'])
    pins.update(cohort=old['inputs']['cohort'], historicalFeatureReport=old['inputs']['featureReport'],
                protocol=files.binding(PROTOCOL))
    for name, binding in candidate['sources'].items():
        pins['candidateSource/'+name] = binding
    for name, binding in read(pins['priorProbePlan'])['sources'].items():
        pins['priorProbeSource/'+name] = binding
    cohort = read(pins['cohort'])
    jobs = make_jobs(old, candidate, cohort['rows'])
    # Bind every selected control artifact, including config, weights, transform,
    # checkpoints and histories, without importing the huge flattened old inputs.
    selected = {ref for job in jobs for ref in job['references'].values()}
    for phase in ('Inner', 'Refit', 'Outer'):
        frozen = read(pins['historical'+phase])
        require(frozen['complete'] is True and frozen['plan'] == pins['historicalPlan'], 'Incomplete historical phase')
        key = 'predictions' if phase == 'Outer' else 'runs'
        records = {r['jobId']: r for r in frozen[key]}
        require(selected <= records.keys(), 'Missing historical controls')
        for job_id in sorted(selected):
            artifacts = {'prediction': records[job_id]['artifact']} if phase == 'Outer' else records[job_id]['artifacts']
            for name, binding in artifacts.items():
                pins[f'control/{phase}/{job_id}/{name}'] = binding
    feature = read(pins['historicalFeatureReport'])
    pins.update(historicalTarget=feature['matrices']['target'], historicalScalars=feature['inputs']['scalars'])
    files.guard(pins)
    temporal = read(pins['featureReport'])
    ids = np.load(temporal['rowIndices']['path'], allow_pickle=False)
    require(np.array_equal(np.load(temporal['matrices']['final']['path'], allow_pickle=False),
                           np.load(pins['historicalTarget']['path'], allow_pickle=False)[ids]), 'Historical target exact parity failed')
    require(np.array_equal(np.load(temporal['scalars']['path'], allow_pickle=False),
                           np.load(pins['historicalScalars']['path'], allow_pickle=False)[ids]), 'Historical scalar exact parity failed')
    source_paths = set(Path(__file__).parent.glob('*.py')) | {
        Path(core.__file__), Path(validation.__file__), Path(historical.__file__), Path(extract.__file__),
        Path(heads.__file__), Path(core.compact.__file__), Path(core.scalar.__file__),
        Path(core.unitcore.__file__), Path(core.weights.__file__), Path(previous.__file__), Path(previous_evaluation.__file__),
        Path(old_extract.__file__), Path(core.prior.__file__), old_extract.HERE/'multiphone_models.py',
        old_extract.HERE/'multiphone_local_head.py'}
    return dict(study=STUDY, representation=REPRESENTATION, inputs=pins,
                sources={str(p.resolve()): files.binding(p) for p in sorted(source_paths)}, jobs=jobs,
                seeds=list(SEEDS), objectives=['unweighted'], recipes={str(s): core.recipe(s) for s in SEEDS},
                transform=core.compact.TRANSFORM_RECIPE, runtime=old_extract.environment(),
                innerFits=75, refits=75, outerPasses=75, mixtureWeights=[.5, .5],
                phaseOrder='All 75 inner fits, then all 75 fresh refits, then all 75 outer passes',
                trainingPerformed=False, outerInferencePerformed=False, **FLAGS)


def load_plan(path, sha):
    pin = files.binding(path, sha); plan = read(pin)
    require(plan == declaration(plan['inputs']['featureReport']['path'], plan['inputs']['featureReport']['sha256'],
                               plan['inputs']['extractionReview']['path'], plan['inputs']['extractionReview']['sha256']),
            'Temporal declaration changed')
    feature = read(plan['inputs']['featureReport'])
    indices = np.load(feature['rowIndices']['path'], allow_pickle=False).tolist()
    bundle = dict(cohort=read(plan['inputs']['cohort']), positions={i: p for p, i in enumerate(indices)},
                  target=np.load(feature['matrices']['temporal']['path'], allow_pickle=False),
                  scalars=np.load(feature['scalars']['path'], allow_pickle=False))
    return plan, pin, bundle


def config_value(job, pin, phase, feature, selection=None):
    return dict(historical.config_value(job, pin, phase, selection), study=STUDY,
                representation=REPRESENTATION, featureReport=feature)


def validate_run(job, record, pin, phase, cohort, feature):
    result = core.validate_run(job, record, pin, phase, cohort)
    cfg = read(record['artifacts']['config.json'])
    require(cfg.get('study') == STUDY and cfg.get('representation') == REPRESENTATION
            and cfg.get('featureReport') == feature, 'Temporal representation lineage differs')
    expected = Path(pin['path']).parent / ('inner' if phase == 'inner' else 'refit') / job['id']
    require(all(Path(p['path']).parent == expected for p in record['artifacts'].values()), 'Run artifact path differs')
    old_phase = 'historicalInner' if phase == 'inner' else 'historicalRefit'
    old_runs = read(files.binding(*PINS[old_phase]))['runs']
    control = next(r for r in old_runs if r['jobId'] == job['references']['final'])
    same_model(record['artifacts']['initial.pt'], control['artifacts']['initial.pt'])
    return result


def review_binding(path, sha):
    binding = files.binding(path)
    old_extract.checked_review(Path(binding['path']), sha)
    return binding


def check_freeze(plan, pin, path, sha, phase, cohort):
    label = 'inner' if phase == 'inner' else 'refit'
    require(phase in ('inner', 'outer-refit') and Path(path).resolve() == Path(pin['path']).parent/(label+'-freeze.json'),
            'Canonical phase freeze required')
    binding = files.binding(path, sha); frozen = read(binding)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['phase'] == phase
            and frozen['study'] == STUDY and frozen['trainingPerformed'] is True
            and frozen['outerInferencePerformed'] is False and all(frozen[k] is v for k, v in FLAGS.items())
            and len(frozen['runs']) == 75
            and [r['jobId'] for r in frozen['runs']] == [j['id'] for j in plan['jobs']], 'Incomplete 75-job phase freeze')
    require(review_binding(frozen['review']['path'], pin['sha256']) == frozen['review'], 'Review changed')
    require(frozen['controls'] == checked_control_freeze(plan, pin), 'Control parity lineage differs')
    for job, record in zip(plan['jobs'], frozen['runs'], strict=True):
        validate_run(job, record, pin, phase, cohort, plan['inputs']['featureReport'])
    if phase == 'outer-refit':
        inner, inner_pin = check_freeze(plan, pin, frozen['innerFreeze']['path'], frozen['innerFreeze']['sha256'], 'inner', cohort)
        for record, selected in zip(frozen['runs'], inner['runs'], strict=True):
            require(record['selectedEpoch'] == selected['selectedEpoch'] and
                    read(record['artifacts']['config.json'])['innerSelection'] == dict(innerFreeze=inner_pin,
                    checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch']), 'Refit selection lineage differs')
    return frozen, binding


def fresh_phase(root, label):
    require(not any((root/name).exists() for name in (label, label+'-started.json', label+'-freeze.json', label+'-failure.json')),
            'Preserve partial phase; no implicit restart')
    (root/label).mkdir()


def fit(path, sha, phase, review, freeze_path=None, freeze_sha=None):
    require(phase in ('inner', 'outer-refit'), 'Unknown phase')
    plan, pin, bundle = load_plan(path, sha)
    reviewed = review_binding(review, sha)
    control_pin = checked_control_freeze(plan, pin)
    previous, previous_pin = (None, None) if phase == 'inner' else check_freeze(
        plan, pin, freeze_path, freeze_sha, 'inner', bundle['cohort'])
    root = Path(pin['path']).parent; label = 'inner' if phase == 'inner' else 'refit'
    fresh_phase(root, label)
    files.write_json(root/(label+'-started.json'), dict(plan=pin, review=reviewed, controls=control_pin, innerFreeze=previous_pin))
    runs = []; started = time.monotonic()
    try:
        for number, job in enumerate(plan['jobs']):
            data = core.prepare(bundle, job['family'], job['fitRows' if phase == 'inner' else 'refitRows'], 'unweighted')
            selected = None if previous is None else previous['runs'][number]
            selection = None if selected is None else dict(innerFreeze=previous_pin,
                checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch'])
            output = root/label/job['id']
            core.train(data, job['selectionRows'] if phase == 'inner' else [], output,
                       config_value(job, pin, phase, plan['inputs']['featureReport'], selection), seed=job['seed'],
                       epochs=None if selected is None else selected['selectedEpoch'])
            if phase == 'inner':
                files.write_json(output/'selected-replay.json', core.replay(output, data, job['selectionRows'], seed=job['seed']))
            artifacts = historical.parent.scalar.manifest(output)
            report = historical.parent.scalar.check_manifest(artifacts)
            record = dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=report['bestEpoch'])
            validate_run(job, record, pin, phase, bundle['cohort'], plan['inputs']['featureReport']); runs.append(record)
            print(json.dumps(dict(phase=phase, completed=len(runs), total=75, job=job['id'])), flush=True)
        files.guard(plan['inputs']); files.guard(plan['sources'])
        frozen = dict(complete=True, study=STUDY, phase=phase, plan=pin, review=reviewed, controls=control_pin, runs=runs, elapsedSeconds=time.monotonic()-started,
                      trainingPerformed=True, outerInferencePerformed=False, **FLAGS)
        if previous_pin is not None: frozen['innerFreeze'] = previous_pin
        files.write_json(root/(label+'-freeze.json'), frozen)
        return files.binding(root/(label+'-freeze.json'))
    except Exception as error:
        files.write_json(root/(label+'-failure.json'), dict(error=f'{type(error).__name__}: {error}', completedJobs=[r['jobId'] for r in runs]))
        raise


def outer(path, sha, freeze_path, freeze_sha):
    plan, pin, bundle = load_plan(path, sha)
    refits, refit_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'outer-refit', bundle['cohort'])
    root = Path(pin['path']).parent; fresh_phase(root, 'outer')
    files.write_json(root/'outer-started.json', dict(plan=pin, refitFreeze=refit_pin))
    predictions = []; started = time.monotonic()
    try:
        for job, fitted in zip(plan['jobs'], refits['runs'], strict=True):
            data = core.prepare(bundle, job['family'], job['refitRows'], 'unweighted')
            value = core.replay(Path(fitted['artifacts']['best.pt']['path']).parent, data, job['outerRows'], seed=job['seed'])
            prior = np.asarray([data['priors'][bundle['cohort']['rows'][i]['targetPhone']]['probabilities'] for i in job['outerRows']])
            output = root/'outer'/(job['id']+'.json')
            files.write_json(output, dict(study=STUDY, representation=REPRESENTATION, job={k: job[k] for k in validation.JOB_FIELDS},
                refitCheckpoint=fitted['artifacts']['best.pt'], prediction=value,
                prior=dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()),
                headInferencePerformed=True, **FLAGS))
            predictions.append(dict(jobId=job['id'], artifact=files.binding(output)))
        files.guard(plan['inputs']); files.guard(plan['sources'])
        files.write_json(root/'outer-freeze.json', dict(complete=True, study=STUDY, plan=pin, refitFreeze=refit_pin,
            predictions=predictions, elapsedSeconds=time.monotonic()-started, trainingPerformed=False, outerInferencePerformed=True, **FLAGS))
        return files.binding(root/'outer-freeze.json')
    except Exception as error:
        files.write_json(root/'outer-failure.json', dict(error=f'{type(error).__name__}: {error}', completedJobs=[p['jobId'] for p in predictions]))
        raise


def replay_record(job, record, fitted, bundle):
    require(record['job'] == {k: job[k] for k in validation.JOB_FIELDS}
            and record['refitCheckpoint'] == fitted['artifacts']['best.pt'] and record['headInferencePerformed'] is True
            and all(record[k] is v for k, v in FLAGS.items()), 'Outer seed/objective/checkpoint differs')
    data = core.prepare(bundle, job['family'], job['refitRows'], job['objective'])
    replay = core.replay(Path(fitted['artifacts']['best.pt']['path']).parent, data, job['outerRows'], seed=job['seed'])
    require(replay == record['prediction'], 'Outer exact replay differs')
    prior = np.asarray([data['priors'][bundle['cohort']['rows'][i]['targetPhone']]['probabilities'] for i in job['outerRows']])
    require(record['prior'] == dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()),
            'Outer prior differs')
    return dict(prediction=record['prediction'], prior=record['prior'])


def replay_selection(job, fitted, bundle):
    data = core.prepare(bundle, job['family'], job['fitRows'], job['objective'])
    replay = core.replay(Path(fitted['artifacts']['best.pt']['path']).parent, data, job['selectionRows'], seed=job['seed'])
    require(replay == read(fitted['artifacts']['selected-replay.json']), 'Selected checkpoint replay differs')


def checked_outer(plan, pin, bundle, freeze_path, freeze_sha):
    require(Path(freeze_path).resolve() == Path(pin['path']).parent/'outer-freeze.json', 'Canonical outer freeze required')
    outer_pin = files.binding(freeze_path, freeze_sha); frozen = read(outer_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['study'] == STUDY
            and frozen['trainingPerformed'] is False and frozen['outerInferencePerformed'] is True
            and all(frozen[k] is v for k, v in FLAGS.items()) and len(frozen['predictions']) == 75
            and [r['jobId'] for r in frozen['predictions']] == [j['id'] for j in plan['jobs']], 'Incomplete 75-job outer freeze')
    refits, _ = check_freeze(plan, pin, frozen['refitFreeze']['path'], frozen['refitFreeze']['sha256'], 'outer-refit', bundle['cohort'])
    inner = read(refits['innerFreeze']); records = {}
    for job, pred, fitted, selected in zip(plan['jobs'], frozen['predictions'], refits['runs'], inner['runs'], strict=True):
        require(Path(pred['artifact']['path']) == Path(pin['path']).parent/'outer'/(job['id']+'.json'), 'Outer artifact path differs')
        value = read(pred['artifact'])
        require(value['study'] == STUDY and value['representation'] == REPRESENTATION, 'Outer representation differs')
        replay_selection(job, selected, bundle)
        records[job['id']] = replay_record(job, value, fitted, bundle)
    return records, outer_pin


checked_controls = previous.checked_controls


def same_model(left, right):
    a = torch.load(left['path'], map_location='cpu', weights_only=True)['model']
    b = torch.load(right['path'], map_location='cpu', weights_only=True)['model']
    require(list(a) == list(b) and all(torch.equal(a[k], b[k]) for k in a), 'Probe model tensors differ')


def prior_probes(plan):
    """Reuse only reviewed probes with identical bound trainer, runtime and control data."""
    pins = plan['inputs']
    prior_plan = read(pins['priorProbePlan'])
    files.guard(prior_plan['sources'])
    require(prior_plan['runtime'] == plan['runtime'], 'Prior probe runtime differs')
    for key in ('historicalPlan', 'historicalInner', 'historicalRefit', 'historicalOuter',
                'cohort', 'historicalFeatureReport', 'historicalTarget', 'historicalScalars'):
        require(prior_plan['inputs'][key] == pins[key], 'Prior probe input differs: '+key)
    receipt = read(pins['priorProbeReview'])
    require(receipt.get('independent') is True and receipt.get('verdict') == 'clear'
            and receipt.get('blockingFindings') == []
            and receipt['bindings']['plan.json'] == pins['priorProbePlan']
            and receipt['bindings']['controls-freeze.json'] == pins['priorProbeFreeze'], 'Prior probe review differs')
    require(previous.checked_control_freeze(prior_plan, pins['priorProbePlan']) == pins['priorProbeFreeze'],
            'Prior probe validation differs')
    return dict(plan=pins['priorProbePlan'], freeze=pins['priorProbeFreeze'], review=pins['priorProbeReview'])


def checked_control_freeze(plan, pin):
    binding = files.binding(Path(pin['path']).parent/'controls-freeze.json')
    value = read(binding)
    require(value['complete'] is True and value['study'] == STUDY and value['plan'] == pin
            and value['controlCount'] == 150 and value['probeReuse'] == prior_probes(plan)
            and value['trainingPerformed'] is False and value['outerInferencePerformed'] is True
            and all(value[k] is v for k, v in FLAGS.items()), 'Incomplete temporal control freeze')
    require(review_binding(value['review']['path'], pin['sha256']) == value['review'], 'Control review changed')
    require(set(read(value['records'])) == {r for j in plan['jobs'] for r in j['references'].values()}, 'Control records incomplete')
    return binding


def controls(path, sha, review):
    """Validate reviewed prior trainer probes and freshly replay all 150 controls."""
    plan, pin, bundle = load_plan(path, sha)
    reviewed = review_binding(review, sha)
    reused = prior_probes(plan)
    root = Path(pin['path']).parent; fresh_phase(root, 'controls')
    files.write_json(root/'controls-started.json', dict(plan=pin, review=reviewed, probeReuse=reused))
    started = time.monotonic()
    try:
        records = checked_controls(plan, bundle)
        files.write_json(root/'controls'/'records.json', records)
        files.guard(plan['inputs']); files.guard(plan['sources'])
        files.write_json(root/'controls-freeze.json', dict(complete=True, study=STUDY, plan=pin, review=reviewed,
            controlCount=150, probeReuse=reused, elapsedSeconds=time.monotonic()-started, records=files.binding(root/'controls'/'records.json'),
            trainingPerformed=False, outerInferencePerformed=True, **FLAGS))
        return checked_control_freeze(plan, pin)
    except Exception as error:
        files.write_json(root/'controls-failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


def declare(output, feature_report, feature_sha, extraction_review, extraction_review_sha):
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(BASE), 'Fresh research output required')
    value = declaration(feature_report, feature_sha, extraction_review, extraction_review_sha); output.mkdir(mode=0o700); files.write_json(output/'plan.json', value)
    return files.binding(output/'plan.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'controls', 'inner', 'refit', 'outer'))
    for name in ('plan', 'freeze', 'output', 'review', 'feature-report', 'extraction-review'): parser.add_argument('--'+name, type=Path)
    for name in ('plan-sha256', 'freeze-sha256', 'feature-sha256', 'extraction-review-sha256'): parser.add_argument('--'+name)
    args = parser.parse_args()
    if args.command == 'declare': value = declare(args.output, args.feature_report, args.feature_sha256, args.extraction_review, args.extraction_review_sha256)
    elif args.command == 'controls': value = controls(args.plan, args.plan_sha256, args.review)
    elif args.command == 'outer': value = outer(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256)
    else: value = fit(args.plan, args.plan_sha256, 'inner' if args.command == 'inner' else 'outer-refit',
                      args.review, args.freeze, args.freeze_sha256)
    print(json.dumps(value), flush=True)


if __name__ == '__main__': main()
