"""Expanded fitting occurrences with fixed original lexical selection examples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from lexical_expansion import study as inventory
from lexical_heads import study as scalar
from lexical_compact import study as compact
from lexical_expanded_heads import evaluation

files, read, require = inventory.files, inventory.read, inventory.require
HERE, BASE = inventory.HERE, inventory.BASE
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE/'../../docs/model/multiphone-lexical-expanded-heads-protocol.md'
FAMILIES = ('scalars', 'pca16-scalars')
REGIMES = inventory.prior.REGIMES
FLAGS = dict(scalar.FLAGS, audioDecoded=False, learnerJudgmentsEnabled=False)
INVENTORY_PLAN = 'b44bdef2eadb9637f97f66532f659f4b963e0ed1af1b210b6c008baea7ab5fb9'
INVENTORY_REPORT = 'e04e2bb64b21e4328da5b9898627a7dc648e6367473aef918a0aea73da608177'
REFERENCES = {
    'scalar': ('lexical-heads-v1', 'bd55f8ab41f52137c6be6f5f9bfefbad64c3855d4ed84077a26245a600edfa18',
               'lexical-head-audit-v1', '6f4680ddf6b3f89b4e9796d7bd21d2b0f44c2232cd1cf361efbf38c3c45291fb'),
    'compact': ('lexical-compact-v1', '93796077be5af479c07d4e84e15d87c5c96c8d05664a89bd16ab0b7c70550f16',
                'lexical-compact-audit-v1', '143450faa46e98a9e091972b906de69a00488cdb8f885adb3ddf8d88d04cd4cd'),
    'mixture': ('lexical-mixture-v1', '83c31246a295db47d4cc3402e971f8e5d1199fa2bf478378a55ee104f8370bf7',
                'lexical-mixture-v1', '8df2508a7af9f728396fea41f2e34317d086cbeca773b662cc1918b37d3ced47'),
    'corrected': ('lexical-projection-mixture-v1', '0ea7bac5ed8dfa29da35622c21c7b1c94041520dde65e1ecfadcd75d56896a31',
                  'lexical-projection-mixture-v1', 'ade1a17833eb84ef7c05c342c01a4acf4c6523d5f26b0e8636f0abaac6442d3c'),
}


def implementation(family):
    require(family in FAMILIES, 'Unknown expanded feature family')
    return scalar if family == 'scalars' else compact


def check_job(job, rows, tokens, groups):
    require(job['family'] in FAMILIES and job['regime'] in REGIMES
            and job['speakerFold'] in range(5) and job['wordGroup'] in range(5), 'Invalid expanded job identity')
    require(job['id'] == f"{job['regime']}-{job['family']}-s{job['speakerFold']}-w{job['wordGroup']}", 'Job ID differs')
    scalar.membership.check_partitions(rows, job['fitRows'], job['selectionRows'], job['outerRows'])
    for key in ('fitRows', 'selectionRows', 'addedValidationRows', 'refitRows', 'outerRows'):
        ids = job[key]
        require(len(ids) == len(set(ids)) and all(type(i) is int and 0 <= i < len(rows) for i in ids), 'Invalid partition rows')
    fit, selection, added = (set(job[k]) for k in ('fitRows', 'selectionRows', 'addedValidationRows'))
    require(not fit & selection and not fit & added and not selection & added
            and sorted(fit | selection | added) == sorted(job['refitRows']), 'Expanded refit union differs')
    require(all(rows[i]['legacyRowIndex'] is not None for i in selection)
            and all(rows[i]['legacyRowIndex'] is None for i in added), 'Original selection or added-validation identity differs')
    require(not {rows[i]['speakerId'] for i in added} & {rows[i]['speakerId'] for i in fit | set(job['outerRows'])},
            'Added validation speaker leaks into fit or outer')
    for key in ('fitRows', 'selectionRows', 'addedValidationRows', 'refitRows'):
        require(all(all(groups[w] != job['wordGroup'] for w in tokens[rows[i]['clipId']]) for i in job[key]),
                'Held-out word remains in fitting or validation utterance')
        if job['regime'] == 'child-only':
            require(all(6 <= rows[i]['age'] <= 12 for i in job[key]), 'Child-only age restriction differs')
    require(all(groups[rows[i]['targetWord'].upper()] == job['wordGroup'] for i in job['outerRows']), 'Outer word group differs')
    for key in ('fitRows', 'refitRows'):
        require({rows[i]['targetPhone'] for i in job[key]} == set(scalar.membership.PHONES), 'Missing fitting phone')


def make_jobs(report, original_plan, compact_plan, rows):
    mapping = {int(k): v for k, v in report['originalRowToExpanded'].items()}
    controls = {family: {j['id']: j for j in plan['jobs']} for family, plan in
                (('scalars', original_plan), ('pca16-scalars', compact_plan))}
    jobs = []
    for regime in REGIMES:
        cells = report['models'][regime]['cells']
        require([(c['speakerFold'], c['wordGroup']) for c in cells] == [(s, w) for s in range(5) for w in range(5)], 'Incomplete inventory cells')
        for family in FAMILIES:
            for cell in cells:
                name = f"{regime}-{family}-s{cell['speakerFold']}-w{cell['wordGroup']}"
                source = controls[family][name]
                part = cell['partitions']
                selection = [mapping[i] for i in source['selectionRows']]
                require(sorted(selection) == sorted(part['selection']['retainedByOrigin']['original']['rowIndices']), 'Original selection population differs')
                for src_key, part_key in (('fitRows', 'innerFit'), ('refitRows', 'outerFit'), ('outerRows', 'outer')):
                    require(sorted(mapping[i] for i in source[src_key]) == sorted(part[part_key]['retainedByOrigin']['original']['rowIndices']), 'Original fitting or outer population differs')
                job = dict(id=name, family=family, regime=regime, speakerFold=cell['speakerFold'], wordGroup=cell['wordGroup'],
                           fitRows=part['innerFit']['retainedRows'], selectionRows=selection,
                           addedValidationRows=part['selection']['retainedByOrigin']['added']['rowIndices'],
                           refitRows=part['outerFit']['retainedRows'], outerRows=part['outer']['retainedRows'],
                           originalJobId=source['id'])
                check_job(job, rows, report['canonicalTokens'], report['wordGroups'])
                jobs.append(job)
    require(len(jobs) == len({j['id'] for j in jobs}) == 100, 'Expected exactly 100 training jobs')
    return jobs


def inputs():
    inventory_pin = files.binding(BASE/'lexical-expansion-v1/plan.json', INVENTORY_PLAN)
    old = read(inventory_pin)
    require(old == inventory.plan_value(), 'Expanded inventory declaration changed')
    pins = dict(old['inputs'], inventoryPlan=inventory_pin,
                inventoryReport=files.binding(BASE/'lexical-expansion-v1/report.json', INVENTORY_REPORT),
                expandedHeadProtocol=files.binding(PROTOCOL))
    report = read(pins['inventoryReport'])
    require(report['complete'] is True and report['plan'] == inventory_pin and report['originalPartitionsExact'] is True,
            'Complete exact expanded inventory required')
    feature = read(pins['featureReport'])
    pins.update(cohort=feature['inputs']['cohort'], originalCohort=read(pins['oldPlan'])['inputs']['cohort'])
    cohort, original = read(pins['cohort']), read(pins['originalCohort'])
    mapping = inventory.legacy_map(original['rows'], cohort['rows'])
    require(report['originalRowToExpanded'] == {str(k): v for k, v in mapping.items()}, 'Legacy mapping changed')
    inventory.feature_parity(feature, cohort['rows'], mapping)
    plans = {}
    for name, (folder, plan_sha, report_folder, report_sha) in REFERENCES.items():
        pins[name+'ReferencePlan'] = files.binding(BASE/folder/'plan.json', plan_sha)
        pins[name+'ReferenceReport'] = files.binding(BASE/report_folder/'report.json', report_sha)
        plans[name] = read(pins[name+'ReferencePlan'])
        # Bind reference provenance without opening its outer outcomes before fitting.
        inventory.collect_pins(plans[name], 'reference/'+name, pins)
    require(plans['scalar']['recipe'] == plans['compact']['recipe'] == scalar.core.RECIPE == compact.core.RECIPE,
            'Fixed training recipe changed')
    require(plans['compact']['transform'] == compact.core.TRANSFORM_RECIPE, 'Fixed PCA recipe changed')
    jobs = make_jobs(report, plans['scalar'], plans['compact'], cohort['rows'])
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['expandedHeadSource/'+path.name] = files.binding(path)
    files.guard(pins)
    target = inventory.features.checked_array(feature['matrices']['target'], (28227, 1024))
    scalars = inventory.features.checked_array(feature['inputs']['scalars'], (28227, 13))
    bundle = dict(cohort=cohort, originalCohort=original, target=target, scalars=scalars,
                  positions={i: i for i in range(len(cohort['rows']))})
    return pins, jobs, bundle


def plan_value(pins, jobs):
    return dict(inputs=pins, jobs=jobs, recipe=scalar.core.RECIPE, transform=compact.core.TRANSFORM_RECIPE,
                runtime=inventory.features.runtime(), innerFits=100, refits=100, outerPasses=100,
                selection='Only original retained selection rows, in original order',
                refit='All expanded purged outer-fit occurrences, including added inner-validation occurrences',
                mixtureWeights=[.5, .5], primaryPopulation='Original outer rows only, remapped to original indices',
                addedOuter='Separate descriptive population; no old-population comparison',
                trainingPerformed=False, outerInferencePerformed=False, **FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(BASE), 'Fresh ignored output required')
    pins, jobs, _ = inputs()
    output.mkdir(mode=0o700)
    files.write_json(output/'plan.json', plan_value(pins, jobs))
    return files.binding(output/'plan.json')


def load_plan(path, sha):
    pin = files.binding(path, sha)
    plan = read(pin)
    pins, jobs, bundle = inputs()
    require(plan == plan_value(pins, jobs), 'Expanded head declaration changed')
    return plan, pin, bundle


def config_value(job, pin, phase, selection=None):
    value = scalar.config_value(job, pin, phase, selection)
    value['experiment'] = 'expanded-lexical-heads-v1'
    value['addedValidationRowsNotUsedForSelection'] = job['addedValidationRows']
    return value


def validate_run(job, run, pin, phase, rows):
    module = implementation(job['family'])
    report = module.validate_history(job, run, pin, phase, rows)
    artifacts = run['artifacts']
    cfg = read(artifacts['config.json'])
    require(cfg['experiment'] == 'expanded-lexical-heads-v1'
            and cfg['addedValidationRowsNotUsedForSelection'] == job['addedValidationRows'], 'Expanded run policy differs')
    history = read(artifacts['history.json'])
    updates = (len(cfg['fitRows'])+63)//64
    for filename, epoch in (('initial.pt', 0), ('best.pt', report['bestEpoch']), ('last.pt', report['epochsRun'])):
        state = torch.load(artifacts[filename]['path'], map_location='cpu', weights_only=True)
        selected_epoch, selected_loss = 0, None
        for i, entry in enumerate(history[:epoch], 1):
            if phase == 'outer-refit':
                selected_epoch = i
            elif selected_loss is None or entry['selection']['NLL'] < selected_loss-1e-7:
                selected_epoch, selected_loss = i, entry['selection']['NLL']
        require(state['epoch'] == epoch and state['bestEpoch'] == selected_epoch and state['bestLoss'] == selected_loss
                and state['configSha256'] == artifacts['config.json']['sha256']
                and state['priorState'] == cfg['priorState'], 'Checkpoint epoch/configuration differs')
        require(all(torch.isfinite(value).all() for value in state['model'].values())
                and torch.isfinite(state['mean']).all() and torch.isfinite(state['std']).all()
                and (state['std'] > 0).all(), 'Nonfinite checkpoint or normalization')
        states = state['optimizer']['state']
        require((epoch == 0 and not states) or (epoch > 0 and len(states) == len(state['model'])
                and all(int(v['step']) == epoch*updates and torch.isfinite(v['exp_avg']).all()
                        and torch.isfinite(v['exp_avg_sq']).all() for v in states.values())), 'Optimizer state/update count differs')
        expected_rng = np.random.default_rng(7)
        for _ in range(epoch):
            expected_rng.permutation(cfg['fitRows'])
        require(state['rng']['numpyPermutation'] == expected_rng.bit_generator.state, 'Permutation RNG state differs')
    return report


def check_freeze(plan, pin, path, sha, phase, rows):
    frozen_pin = files.binding(path, sha)
    value = read(frozen_pin)
    require(value['complete'] is True and value['plan'] == pin and value['phase'] == phase
            and value['outerInferencePerformed'] is False and value['trainingPerformed'] is True
            and all(value[k] is v for k, v in FLAGS.items())
            and [r['jobId'] for r in value['runs']] == [j['id'] for j in plan['jobs']], 'Incomplete or wrong phase freeze')
    for job, run in zip(plan['jobs'], value['runs'], strict=True):
        validate_run(job, run, pin, phase, rows)
    if phase == 'outer-refit':
        previous, _ = check_freeze(plan, pin, value['innerFreeze']['path'], value['innerFreeze']['sha256'], 'inner', rows)
        for run, old in zip(value['runs'], previous['runs'], strict=True):
            require(run['selectedEpoch'] == old['selectedEpoch'], 'Refit duration differs')
            require(read(run['artifacts']['config.json'])['innerSelection'] == dict(innerFreeze=value['innerFreeze'],
                    checkpoint=old['artifacts']['best.pt'], epoch=old['selectedEpoch']), 'Refit selection lineage differs')
    return value, frozen_pin


def fit(path, sha, phase, freeze_path=None, freeze_sha=None):
    require(phase in ('inner', 'outer-refit'), 'Unknown fitting phase')
    plan, pin, bundle = load_plan(path, sha)
    previous, previous_pin = (None, None) if phase == 'inner' else check_freeze(plan, pin, freeze_path, freeze_sha, 'inner', bundle['cohort']['rows'])
    root = Path(path).resolve().parent
    label = 'inner' if phase == 'inner' else 'refit'
    files.write_json(root/(label+'-started.json'), dict(plan=pin, innerFreeze=previous_pin))
    runs = []
    try:
        for number, job in enumerate(plan['jobs']):
            module = implementation(job['family'])
            data = module.core.prepare(bundle, job['family'], job['fitRows'] if phase == 'inner' else job['refitRows'])
            output = root/label/job['id']
            selected = None if previous is None else previous['runs'][number]
            selection = None if selected is None else dict(innerFreeze=previous_pin,
                        checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch'])
            module.core.train(data, job['selectionRows'] if phase == 'inner' else [], output,
                              config_value(job, pin, phase, selection),
                              epochs=None if selected is None else selected['selectedEpoch'])
            if phase == 'inner':
                files.write_json(output/'selected-replay.json', module.core.replay(output, data, job['selectionRows']))
            artifacts = scalar.manifest(output)
            result = scalar.check_manifest(artifacts)
            run = dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=result['bestEpoch'])
            validate_run(job, run, pin, phase, bundle['cohort']['rows'])
            runs.append(run)
            print(json.dumps(dict(phase=phase, completed=len(runs), job=job['id'], selectedEpoch=result['bestEpoch'], epochsRun=result['epochsRun'])), flush=True)
        files.guard(plan['inputs'])
        value = dict(complete=True, phase=phase, plan=pin, runs=runs, trainingPerformed=True, outerInferencePerformed=False, **FLAGS)
        if previous_pin is not None:
            value['innerFreeze'] = previous_pin
        files.write_json(root/(label+'-freeze.json'), value)
        return files.binding(root/(label+'-freeze.json'))
    except Exception as error:
        files.write_json(root/(label+'-failure.json'), dict(error=f'{type(error).__name__}: {error}', completedJobs=[r['jobId'] for r in runs]))
        raise


def outer(path, sha, freeze_path, freeze_sha):
    plan, pin, bundle = load_plan(path, sha)
    frozen, refit_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'outer-refit', bundle['cohort']['rows'])
    root = Path(path).resolve().parent
    files.write_json(root/'outer-started.json', dict(plan=pin, refitFreeze=refit_pin))
    predictions = []
    try:
        for job, run in zip(plan['jobs'], frozen['runs'], strict=True):
            module = implementation(job['family'])
            data = module.core.prepare(bundle, job['family'], job['refitRows'])
            prediction = module.core.replay(Path(run['artifacts']['best.pt']['path']).parent, data, job['outerRows'])
            rows = [bundle['cohort']['rows'][i] for i in job['outerRows']]
            prior = np.asarray([data['priors'][r['targetPhone']]['probabilities'] for r in rows])
            output = root/'outer'/(job['id']+'.json')
            output.parent.mkdir(exist_ok=True)
            files.write_json(output, dict(jobId=job['id'], refitCheckpoint=run['artifacts']['best.pt'], prediction=prediction,
                prior=dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()),
                headInferencePerformed=True, **FLAGS))
            predictions.append(dict(jobId=job['id'], artifact=files.binding(output)))
            print(json.dumps(dict(outerComplete=job['id'], rows=len(rows))), flush=True)
        files.guard(plan['inputs'])
        files.write_json(root/'outer-freeze.json', dict(complete=True, plan=pin, refitFreeze=refit_pin,
            predictions=predictions, outerInferencePerformed=True, trainingPerformed=False, **FLAGS))
        return files.binding(root/'outer-freeze.json')
    except Exception as error:
        files.write_json(root/'outer-failure.json', dict(error=f'{type(error).__name__}: {error}', completedJobs=[p['jobId'] for p in predictions]))
        raise


def calculate(plan, pin, bundle, freeze_path, freeze_sha):
    outer_pin = files.binding(freeze_path, freeze_sha)
    frozen = read(outer_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['outerInferencePerformed'] is True
            and frozen['trainingPerformed'] is False and all(frozen[k] is v for k, v in FLAGS.items())
            and [p['jobId'] for p in frozen['predictions']] == [j['id'] for j in plan['jobs']], 'Incomplete outer prediction freeze')
    refits, _ = check_freeze(plan, pin, frozen['refitFreeze']['path'], frozen['refitFreeze']['sha256'], 'outer-refit', bundle['cohort']['rows'])
    records = {}
    for job, pred, run in zip(plan['jobs'], frozen['predictions'], refits['runs'], strict=True):
        value = read(pred['artifact'])
        require(value['jobId'] == job['id'] and value['refitCheckpoint'] == run['artifacts']['best.pt'], 'Prediction checkpoint lineage differs')
        cfg = read(run['artifacts']['config.json'])
        prior = np.asarray([cfg['priorState'][bundle['cohort']['rows'][i]['targetPhone']]['probabilities'] for i in job['outerRows']])
        require(value['prior'] == dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()), 'Prediction prior differs')
        records[job['id']] = value
    references = {}
    loaded = {}
    for name in REFERENCES:
        loaded[name] = read(plan['inputs'][name+'ReferenceReport'])
        require(loaded[name]['complete'] is True and loaded[name]['plan'] == plan['inputs'][name+'ReferencePlan'], 'Incomplete reference results')
    for regime in REGIMES:
        references[regime] = {'scalars': loaded['scalar']['models'][regime]['scalars'],
            'pca16-scalars': loaded['compact']['models'][regime], 'equal-mixture': loaded['mixture']['models'][regime],
            'corrected-mixture': loaded['corrected']['models'][regime]}
    result = evaluation.evaluate(bundle['cohort']['rows'], bundle['originalCohort']['rows'], plan['jobs'], records, references)
    files.guard(plan['inputs'])
    return dict(complete=True, plan=pin, outerFreeze=outer_pin, **result,
                trainingPerformed=False, headInferencePerformed=False, outerPredictionsRead=True, **FLAGS)


def audit(path, sha, freeze_path, freeze_sha, output, verify=False):
    plan, pin, bundle = load_plan(path, sha)
    if not verify:
        require(not output.exists() and output.resolve().is_relative_to(BASE), 'Fresh ignored output required')
        output.mkdir(mode=0o700)
        files.write_json(output/'started.json', dict(plan=pin, outerFreeze=files.binding(freeze_path, freeze_sha)))
    try:
        result = calculate(plan, pin, bundle, freeze_path, freeze_sha)
        if verify:
            report = files.binding(output/'report.json')
            require(read(report) == result, 'Expanded head report reconstruction differs')
            return dict(verified=True, report=report)
        files.write_json(output/'report.json', result)
        return files.binding(output/'report.json')
    except Exception as error:
        if not verify:
            files.write_json(output/'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'inner', 'refit', 'outer', 'audit', 'verify'))
    for name in ('plan', 'freeze', 'output'):
        parser.add_argument('--'+name, type=Path)
    for name in ('plan-sha256', 'freeze-sha256'):
        parser.add_argument('--'+name)
    args = parser.parse_args()
    if args.command == 'declare':
        result = declare(args.output)
    elif args.command in ('inner', 'refit'):
        result = fit(args.plan, args.plan_sha256, 'inner' if args.command == 'inner' else 'outer-refit', args.freeze, args.freeze_sha256)
    elif args.command == 'outer':
        result = outer(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256)
    else:
        result = audit(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256, args.output, args.command == 'verify')
    print(json.dumps(result), flush=True)
