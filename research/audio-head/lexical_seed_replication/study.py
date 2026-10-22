"""Three fixed paired seed replications with complete 600-job phase barriers."""
import argparse
import json
from pathlib import Path

import numpy as np

from lexical_unit_weights import study as parent
from lexical_seed_replication import analysis, core, validation

files, read, require = parent.files, parent.read, parent.require
HERE, BASE, FLAGS = parent.HERE, parent.BASE, parent.FLAGS
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = (HERE / '../../docs/model/multiphone-lexical-seed-replication-protocol.md').resolve()
AUDIT = (HERE / '../../work/lexical-seed-replication-audit-20260927').resolve()
SEEDS, OBJECTIVES = analysis.SEEDS, analysis.OBJECTIVES
PARENT_PLAN = '8bf68c8a8738abe238ee9992949db4a3fbf8a2733fe082f25732e2dcf626ca8a'
PARENT_REPORT = 'd5ba68decc6b9e5bf514b9eece85316f71b03f073b13e7ee5cb1cb3b74669aed'
PARENT_BINDING = 'b0a649c307f3a63f5d9744f80d56dbca83e6c594657e83464de8d151e956d694'


def make_jobs(base_jobs):
    expected = {f'{r}-{f}-s{s}-w{w}' for r in parent.REGIMES for f in parent.FAMILIES
                for s in range(5) for w in range(5)}
    require(len(base_jobs) == 100 and {j['id'] for j in base_jobs} == expected, 'Complete original job matrix required')
    return [{**job, 'baseJobId': job['id'], 'id': f'seed{seed}-{objective}-{job["id"]}',
             'seed': seed, 'objective': objective}
            for seed in SEEDS for objective in OBJECTIVES for job in base_jobs]


def inputs():
    old_plan, old_pin, bundle = parent.load_plan(BASE / 'lexical-unit-weights-v1/plan.json', PARENT_PLAN)
    pins = dict(old_plan['inputs'], seedParentPlan=old_pin,
                seedParentReport=files.binding(BASE / 'lexical-unit-weights-audit-v1/report.json', PARENT_REPORT),
                seedProtocol=files.binding(PROTOCOL))
    receipt = files.binding(HERE / '../../work/lexical-unit-weights-audit-20260927/report-binding-result.json', PARENT_BINDING)
    joint = read(receipt)
    require(joint['status'] == 'passed' and joint['plan'] == old_pin
            and joint['report'] == pins['seedParentReport'], 'Completed parent joint audit differs')
    pins['seedParentJointAudit'] = receipt
    for path, sha in joint['hashedFiles'].items():
        pins['seedParentEvidence/' + path] = files.binding(path, sha)
    review_pin = files.binding(AUDIT / 'core-review.json')
    review = read(review_pin)
    required_sources = {str((DIRECTORY / name).resolve()) for name in ('core.py', 'test_core.py')}
    actual_sources = {str(Path(path).resolve()): sha for path, sha in review['sourceBindings'].items()}
    require(review['status'] == 'clear' and required_sources <= set(actual_sources), 'Seed trainer review incomplete')
    for path, sha in actual_sources.items():
        pins['seedCoreReviewedSource/' + path] = files.binding(path, sha)
    pins['seedCoreReview'] = review_pin
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['seedSource/' + path.name] = files.binding(path)
    files.guard(pins)
    require(core.OBJECTIVES == OBJECTIVES, 'Objective contract differs')
    # Geometry is seed-independent. Recheck both objectives for all 200 base partitions.
    for job in old_plan['jobs']:
        for field in ('fitRows', 'refitRows'):
            for objective in OBJECTIVES:
                core.fitting_weights(bundle['cohort'], job[field], objective)
    return pins, old_plan['jobs'], make_jobs(old_plan['jobs']), bundle


def plan_value(pins, base_jobs, jobs):
    return dict(inputs=pins, baseJobs=base_jobs, jobs=jobs, seeds=list(SEEDS), objectives=list(OBJECTIVES),
                recipes={str(seed): core.recipe(seed) for seed in SEEDS},
                weightRecipes={'unweighted': core.UNWEIGHTED_RECIPE, 'unit-weighted': parent.weights.RECIPE},
                transform=parent.compact.core.TRANSFORM_RECIPE, runtime=parent.inventory.features.runtime(),
                innerFits=600, refits=600, outerPasses=600, mixtureWeights=[.5, .5],
                primary='Weighted minus unweighted within the same new seed, original child population only',
                secondary='Each objective equal mixture versus original corrected-projection mixture trained at seed 7',
                selection='Unchanged original selection rows and unweighted NLL; each run selects its own epoch',
                acrossSeeds='All three seeds separately plus descriptive mean/minimum/maximum; no seed selection or uncertainty interval',
                phaseOrder='All 600 inner fits before any refit; all 600 refits before any outer inference',
                seed7IncludedInNewResults=False, trainingPerformed=False, outerInferencePerformed=False, **FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(BASE), 'Fresh ignored output required')
    pins, base_jobs, jobs, _ = inputs()
    output.mkdir(mode=0o700)
    files.write_json(output / 'plan.json', plan_value(pins, base_jobs, jobs))
    return files.binding(output / 'plan.json')


def load_plan(path, sha):
    pin = files.binding(path, sha)
    plan = read(pin)
    pins, base_jobs, jobs, bundle = inputs()
    require(plan == plan_value(pins, base_jobs, jobs), 'Seed replication declaration changed')
    return plan, pin, bundle


def config_value(job, pin, phase, selection=None):
    value = dict(experiment='lexical-seed-replication-v1', plan=pin, phase=phase,
                 job={key: job[key] for key in validation.JOB_FIELDS},
                 addedValidationRowsNotUsedForSelection=job['addedValidationRows'],
                 outerInferencePerformed=False, **FLAGS)
    if selection is not None:
        value['innerSelection'] = selection
    return value


def check_freeze(plan, pin, path, sha, phase, cohort):
    require(phase in ('inner', 'outer-refit'), 'Unknown freeze phase')
    label = 'inner' if phase == 'inner' else 'refit'
    require(Path(path).resolve() == Path(pin['path']).parent / (label + '-freeze.json'), 'Freeze is outside its declared phase path')
    frozen_pin = files.binding(path, sha)
    frozen = read(frozen_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['phase'] == phase
            and frozen['trainingPerformed'] is True and frozen['outerInferencePerformed'] is False
            and all(frozen[k] is v for k, v in FLAGS.items()) and len(frozen['runs']) == 600
            and [r['jobId'] for r in frozen['runs']] == [j['id'] for j in plan['jobs']], 'Incomplete 600-job phase freeze')
    for job, record in zip(plan['jobs'], frozen['runs'], strict=True):
        validation.run(job, record, pin, phase, cohort)
    if phase == 'outer-refit':
        old, _ = check_freeze(plan, pin, frozen['innerFreeze']['path'], frozen['innerFreeze']['sha256'], 'inner', cohort)
        for record, selected in zip(frozen['runs'], old['runs'], strict=True):
            require(record['selectedEpoch'] == selected['selectedEpoch'], 'Refit selected epoch differs')
            require(read(record['artifacts']['config.json'])['innerSelection'] == dict(innerFreeze=frozen['innerFreeze'],
                    checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch']), 'Refit selection provenance differs')
    return frozen, frozen_pin


def fit(path, sha, phase, freeze_path=None, freeze_sha=None):
    require(phase in ('inner', 'outer-refit'), 'Unknown fitting phase')
    plan, pin, bundle = load_plan(path, sha)
    previous, previous_pin = (None, None) if phase == 'inner' else check_freeze(
        plan, pin, freeze_path, freeze_sha, 'inner', bundle['cohort'])
    root = Path(pin['path']).parent
    label = 'inner' if phase == 'inner' else 'refit'
    files.write_json(root / (label + '-started.json'), dict(plan=pin, innerFreeze=previous_pin))
    runs = []
    try:
        for number, job in enumerate(plan['jobs']):
            data = core.prepare(bundle, job['family'], job['fitRows' if phase == 'inner' else 'refitRows'], job['objective'])
            selected = None if previous is None else previous['runs'][number]
            selection = None if selected is None else dict(innerFreeze=previous_pin,
                checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch'])
            output = root / label / job['id']
            core.train(data, job['selectionRows'] if phase == 'inner' else [], output,
                       config_value(job, pin, phase, selection), seed=job['seed'],
                       epochs=None if selected is None else selected['selectedEpoch'])
            if phase == 'inner':
                files.write_json(output / 'selected-replay.json', core.replay(output, data, job['selectionRows'], seed=job['seed']))
            artifacts = parent.scalar.manifest(output)
            report = parent.scalar.check_manifest(artifacts)
            record = dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=report['bestEpoch'])
            validation.run(job, record, pin, phase, bundle['cohort'])
            runs.append(record)
            print(json.dumps(dict(phase=phase, completed=len(runs), job=job['id'],
                                  selectedEpoch=record['selectedEpoch'], epochsRun=report['epochsRun'])), flush=True)
        files.guard(plan['inputs'])
        frozen = dict(complete=True, phase=phase, plan=pin, runs=runs, trainingPerformed=True, outerInferencePerformed=False, **FLAGS)
        if previous_pin is not None:
            frozen['innerFreeze'] = previous_pin
        files.write_json(root / (label + '-freeze.json'), frozen)
        return files.binding(root / (label + '-freeze.json'))
    except Exception as error:
        files.write_json(root / (label + '-failure.json'), dict(error=f'{type(error).__name__}: {error}', completedJobs=[r['jobId'] for r in runs]))
        raise


def outer(path, sha, freeze_path, freeze_sha):
    plan, pin, bundle = load_plan(path, sha)
    frozen, refit_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'outer-refit', bundle['cohort'])
    root = Path(pin['path']).parent
    files.write_json(root / 'outer-started.json', dict(plan=pin, refitFreeze=refit_pin))
    predictions = []
    try:
        for job, record in zip(plan['jobs'], frozen['runs'], strict=True):
            data = core.prepare(bundle, job['family'], job['refitRows'], job['objective'])
            value = core.replay(Path(record['artifacts']['best.pt']['path']).parent, data, job['outerRows'], seed=job['seed'])
            rows = [bundle['cohort']['rows'][i] for i in job['outerRows']]
            prior = np.asarray([data['priors'][r['targetPhone']]['probabilities'] for r in rows])
            output = root / 'outer' / (job['id'] + '.json')
            output.parent.mkdir(exist_ok=True)
            files.write_json(output, dict(job={k: job[k] for k in validation.JOB_FIELDS},
                refitCheckpoint=record['artifacts']['best.pt'], prediction=value,
                prior=dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()),
                headInferencePerformed=True, **FLAGS))
            predictions.append(dict(jobId=job['id'], artifact=files.binding(output)))
            print(json.dumps(dict(outerComplete=job['id'], rows=len(rows))), flush=True)
        files.guard(plan['inputs'])
        files.write_json(root / 'outer-freeze.json', dict(complete=True, plan=pin, refitFreeze=refit_pin, predictions=predictions,
                                                       trainingPerformed=False, outerInferencePerformed=True, **FLAGS))
        return files.binding(root / 'outer-freeze.json')
    except Exception as error:
        files.write_json(root / 'outer-failure.json', dict(error=f'{type(error).__name__}: {error}', completedJobs=[p['jobId'] for p in predictions]))
        raise


def checked_outer(plan, pin, bundle, freeze_path, freeze_sha):
    require(Path(freeze_path).resolve() == Path(pin['path']).parent / 'outer-freeze.json', 'Canonical outer freeze path required')
    outer_pin = files.binding(freeze_path, freeze_sha)
    frozen = read(outer_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['outerInferencePerformed'] is True
            and frozen['trainingPerformed'] is False and all(frozen[k] is v for k, v in FLAGS.items())
            and len(frozen['predictions']) == 600
            and [p['jobId'] for p in frozen['predictions']] == [j['id'] for j in plan['jobs']], 'Incomplete 600-job outer freeze')
    refits, _ = check_freeze(plan, pin, frozen['refitFreeze']['path'], frozen['refitFreeze']['sha256'], 'outer-refit', bundle['cohort'])
    records = {}
    for job, pred, fitted in zip(plan['jobs'], frozen['predictions'], refits['runs'], strict=True):
        value = read(pred['artifact'])
        require(value['job'] == {k: job[k] for k in validation.JOB_FIELDS}
                and value['refitCheckpoint'] == fitted['artifacts']['best.pt']
                and value['headInferencePerformed'] is True and all(value[k] is v for k, v in FLAGS.items()), 'Outer seed/objective lineage differs')
        cfg = read(fitted['artifacts']['config.json'])
        prior = np.asarray([cfg['priorState'][bundle['cohort']['rows'][i]['targetPhone']]['probabilities'] for i in job['outerRows']])
        require(value['prior'] == dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()),
                'Saved prior prediction differs')
        # Only the evaluator's dictionary key is translated back to the unchanged base job ID.
        # The complete seed/objective identity above has already been checked against the frozen plan.
        records[job['id']] = dict(prediction=value['prediction'], prior=value['prior'])
    return records, outer_pin


def seed_result(plan, pin, bundle, records, outer_pin, corrected, seed):
    views = {}
    for objective in OBJECTIVES:
        selected = {j['baseJobId']: records[j['id']] for j in plan['jobs'] if j['seed'] == seed and j['objective'] == objective}
        views[objective] = analysis.models(bundle['cohort']['rows'], bundle['originalCohort']['rows'], plan['baseJobs'], selected)
    comparisons = analysis.paired(views, corrected['models'], bundle['originalCohort']['rows'])
    return dict(complete=True, plan=pin, outerFreeze=outer_pin, seed=seed, models=views, **comparisons,
                secondaryReference=dict(artifact=plan['inputs']['correctedReferenceReport'], trainingSeed=7),
                primaryReference='Same-seed unweighted expanded model', trainingPerformed=False, headInferencePerformed=False,
                outerPredictionsRead=True, **FLAGS)


def audit(path, sha, freeze_path, freeze_sha, output, verify=False):
    plan, pin, bundle = load_plan(path, sha)
    records, outer_pin = checked_outer(plan, pin, bundle, freeze_path, freeze_sha)
    output = Path(output).resolve()
    if not verify:
        require(not output.exists() and output.is_relative_to(BASE), 'Fresh ignored audit output required')
        output.mkdir(mode=0o700)
        files.write_json(output / 'started.json', dict(plan=pin, outerFreeze=outer_pin))
    else:
        require(read(files.binding(output / 'started.json')) == dict(plan=pin, outerFreeze=outer_pin), 'Audit start lineage differs')
    seeds, briefs = [], []
    try:
        corrected = read(plan['inputs']['correctedReferenceReport'])
        require(corrected['complete'] is True and corrected['plan'] == plan['inputs']['correctedReferencePlan'], 'Secondary reference lineage differs')
        for seed in SEEDS:
            result = seed_result(plan, pin, bundle, records, outer_pin, corrected, seed)
            location = output / f'seed-{seed}.json'
            if verify:
                require(read(files.binding(location)) == result, 'Seed report reconstruction differs')
            else:
                files.write_json(location, result)
            seeds.append(dict(seed=seed, artifact=files.binding(location)))
            briefs.append(dict(seed=seed, childLossResponses=result['childLossResponses']))
            del result
            print(json.dumps(dict(seedComplete=seed, verified=verify)), flush=True)
        summary = analysis.across_seeds(briefs)
        files.guard(plan['inputs'])
        result = dict(complete=True, plan=pin, outerFreeze=outer_pin, seedReports=seeds, acrossSeeds=summary,
                      trainingPerformed=False, headInferencePerformed=False, outerPredictionsRead=True, **FLAGS)
        if verify:
            require(read(files.binding(output / 'report.json')) == result, 'Aggregate report reconstruction differs')
            return dict(verified=True, report=files.binding(output / 'report.json'))
        files.write_json(output / 'report.json', result)
        return files.binding(output / 'report.json')
    except Exception as error:
        if not verify:
            files.write_json(output / 'failure.json', dict(error=f'{type(error).__name__}: {error}', completedSeeds=seeds))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'inner', 'refit', 'outer', 'audit', 'verify'))
    for name in ('plan', 'freeze', 'output'):
        parser.add_argument('--' + name, type=Path)
    for name in ('plan-sha256', 'freeze-sha256'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    if args.command == 'declare':
        value = declare(args.output)
    elif args.command in ('inner', 'refit'):
        value = fit(args.plan, args.plan_sha256, 'inner' if args.command == 'inner' else 'outer-refit', args.freeze, args.freeze_sha256)
    elif args.command == 'outer':
        value = outer(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256)
    else:
        value = audit(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256, args.output, args.command == 'verify')
    print(json.dumps(value), flush=True)
