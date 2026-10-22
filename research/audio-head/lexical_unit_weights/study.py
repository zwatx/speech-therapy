"""Fixed recording/sound-unit loss experiment on all expanded lexical jobs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from lexical_expanded_heads import study as prior, evaluation
from lexical_phone_response import analysis as response
from lexical_unit_weights import core, weights

files,read,require = prior.files,prior.read,prior.require
HERE,BASE = prior.HERE,prior.BASE
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE/'../../docs/model/multiphone-lexical-unit-weights-protocol.md'
FAMILIES,REGIMES,FLAGS = prior.FAMILIES,prior.REGIMES,prior.FLAGS
scalar,compact,inventory,implementation = prior.scalar,prior.compact,prior.inventory,prior.implementation
RESPONSE_PLAN = 'a710cd6d849037e55c6b3df659718a7e1820979ef529d871918c51ff5b279cb5'
RESPONSE_REPORT = '7fadd79901f745739ae7862e64fff66af5dcd34ae9ea34183416259597122831'
RESPONSE_AUDIT = '33b85d587b636e4212f13a773072cbd02b6b82f02aa481f1ab84cace133126dc'


def inputs():
    parent = files.binding(BASE/'lexical-phone-response-v1/plan.json',RESPONSE_PLAN)
    pins = dict(read(parent)['inputs'],unitResponsePlan=parent,
                unitResponseReport=files.binding(BASE/'lexical-phone-response-v1/report.json',RESPONSE_REPORT),
                unitProtocol=files.binding(PROTOCOL))
    receipt = files.binding(HERE/'../../work/lexical-phone-response-audit-20260927/result.json',RESPONSE_AUDIT)
    audited = read(receipt)
    require(audited['status'] == 'passed' and audited['plan'] == parent and audited['report'] == pins['unitResponseReport'], 'Response audit lineage')
    pins['unitResponseAudit'] = receipt
    for path,sha in audited['sourceBindings'].items():pins['unitAuditSource/'+path] = files.binding(path,sha)
    for path in sorted(DIRECTORY.glob('*.py')):pins['unitSource/'+path.name] = files.binding(path)
    review_pin = files.binding(HERE/'../../work/lexical-unit-weights-audit-20260927/core-review.json','fda859b7f70048834668df0b1c3c4e478729c24b328b85ca1ee1f26fc7180f5a')
    review = read(review_pin)
    require(review['status'] == 'clear', 'Core review incomplete')
    for path,sha in review['sourceBindings'].items():files.binding(path,sha)
    pins['unitCoreReview'] = review_pin
    files.guard(pins)
    cohort, original = read(pins['cohort']),read(pins['originalCohort'])
    support = read(pins['inventoryReport']);heads = read(pins['expandedHeadsPlan'])
    require(support['complete'] is True and support['plan'] == pins['inventoryPlan'], 'Support lineage')
    jobs = prior.make_jobs(support,read(pins['scalarReferencePlan']),read(pins['compactReferencePlan']),cohort['rows'])
    require(jobs == heads['jobs'], 'Weighted jobs differ from expanded controls')
    require(heads['recipe'] == core.RECIPE and heads['transform'] == compact.core.TRANSFORM_RECIPE, 'Unchanged training/transform required')
    for job in jobs:
        for field in ('fitRows','refitRows'):weights.fit_weights(cohort,job[field])
    feature = read(pins['featureReport'])
    target = inventory.features.checked_array(feature['matrices']['target'],(28227,1024))
    scalars = inventory.features.checked_array(feature['inputs']['scalars'],(28227,13))
    bundle = dict(cohort=cohort,originalCohort=original,target=target,scalars=scalars,positions={i:i for i in range(len(cohort['rows']))})
    return pins,jobs,bundle


def plan_value(pins,jobs):
    return dict(inputs=pins,jobs=jobs,recipe=core.RECIPE,transform=compact.core.TRANSFORM_RECIPE,
                weightRecipe=weights.RECIPE,runtime=inventory.features.runtime(),innerFits=100,refits=100,outerPasses=100,
                selection='Unchanged original retained selection rows and unweighted NLL',
                refit='Fresh transform, initialization and fit-local weights at selected epoch count',
                mixtureWeights=[.5,.5],primaryPopulation='Original outer rows only, remapped to original indices',
                primaryReferences='Corresponding unweighted expanded scalar, PCA and mixture',
                secondaryReference='Original corrected-projection mixture',
                addedOuter='Separate descriptive population; no matched historical claim',
                trainingPerformed=False,outerInferencePerformed=False,**FLAGS)


def declare(output):
    output = Path(output).resolve()
    require(not output.exists() and output.is_relative_to(BASE),'Fresh ignored output required')
    pins,jobs,_ = inputs();output.mkdir(mode=0o700)
    files.write_json(output/'plan.json',plan_value(pins,jobs))
    return files.binding(output/'plan.json')


def load_plan(path,sha):
    pin=files.binding(path,sha);plan=read(pin);pins,jobs,bundle=inputs()
    require(plan == plan_value(pins,jobs),'Unit-weight declaration changed')
    return plan,pin,bundle


def loss_responses(result,references,original_rows):
    output={}
    for regime in REGIMES:
        for contrast in (*FAMILIES,'equal-mixture','mixtureVsCorrectedMixture'):
            family='equal-mixture' if contrast == 'mixtureVsCorrectedMixture' else contrast
            candidate=result['models'][regime][family]['original']
            reference=references[regime]['corrected-mixture' if contrast == 'mixtureVsCorrectedMixture' else family]
            for key in ('rowIndices','rowFolds','rowWordGroups'):require(candidate[key] == reference[key],'Loss response pairing differs')
            keep=[k for k,i in enumerate(candidate['rowIndices']) if 6 <= original_rows[i]['age'] <= 12]
            rows=[original_rows[candidate['rowIndices'][k]] for k in keep]
            folds=[candidate['rowFolds'][k] for k in keep];groups=[candidate['rowWordGroups'][k] for k in keep]
            value=response.analyze(rows,folds,groups,np.asarray(candidate['logProbabilities'])[keep],np.asarray(reference['logProbabilities'])[keep])
            expected=result['comparisons'][regime]['secondary' if contrast=='mixtureVsCorrectedMixture' else 'primary'][contrast]
            require(np.isclose(value['pooled']['meanNLLDelta'],expected['childDelta']['NLL'],atol=2e-12,rtol=2e-11),'Child NLL response differs')
            value['originalConsistencyDecision']=expected
            output[regime+'/'+contrast]=value
    return output


def config_value(job, pin, phase, selection=None):
    value = scalar.config_value(job, pin, phase, selection)
    value['experiment'] = 'lexical-unit-weights-v1'
    value['addedValidationRowsNotUsedForSelection'] = job['addedValidationRows']
    return value


def validate_run(job, run, pin, phase, cohort):
    rows = cohort['rows']
    module = implementation(job['family'])
    report = module.validate_history(job, run, pin, phase, rows)
    artifacts = run['artifacts']
    cfg = read(artifacts['config.json'])
    require(cfg['experiment'] == 'lexical-unit-weights-v1'
            and cfg['addedValidationRowsNotUsedForSelection'] == job['addedValidationRows'], 'Expanded run policy differs')
    expected_weights = weights.fit_weights(cohort, job['fitRows'] if phase == 'inner' else job['refitRows'])
    require(cfg['weightRecipe'] == weights.RECIPE and cfg['weights'] == artifacts['weights.json']
            and read(artifacts['weights.json']) == expected_weights, 'Run fitting-weight lineage differs')
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
                and state['priorState'] == cfg['priorState']
                and state['weightsSha256'] == artifacts['weights.json']['sha256'], 'Checkpoint epoch/configuration differs')
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


def check_freeze(plan, pin, path, sha, phase, cohort):
    frozen_pin = files.binding(path, sha)
    value = read(frozen_pin)
    require(value['complete'] is True and value['plan'] == pin and value['phase'] == phase
            and value['outerInferencePerformed'] is False and value['trainingPerformed'] is True
            and all(value[k] is v for k, v in FLAGS.items())
            and [r['jobId'] for r in value['runs']] == [j['id'] for j in plan['jobs']], 'Incomplete or wrong phase freeze')
    for job, run in zip(plan['jobs'], value['runs'], strict=True):
        validate_run(job, run, pin, phase, cohort)
    if phase == 'outer-refit':
        previous, _ = check_freeze(plan, pin, value['innerFreeze']['path'], value['innerFreeze']['sha256'], 'inner', cohort)
        for run, old in zip(value['runs'], previous['runs'], strict=True):
            require(run['selectedEpoch'] == old['selectedEpoch'], 'Refit duration differs')
            require(read(run['artifacts']['config.json'])['innerSelection'] == dict(innerFreeze=value['innerFreeze'],
                    checkpoint=old['artifacts']['best.pt'], epoch=old['selectedEpoch']), 'Refit selection lineage differs')
    return value, frozen_pin


def fit(path, sha, phase, freeze_path=None, freeze_sha=None):
    require(phase in ('inner', 'outer-refit'), 'Unknown fitting phase')
    plan, pin, bundle = load_plan(path, sha)
    previous, previous_pin = (None, None) if phase == 'inner' else check_freeze(plan, pin, freeze_path, freeze_sha, 'inner', bundle['cohort'])
    root = Path(path).resolve().parent
    label = 'inner' if phase == 'inner' else 'refit'
    files.write_json(root/(label+'-started.json'), dict(plan=pin, innerFreeze=previous_pin))
    runs = []
    try:
        for number, job in enumerate(plan['jobs']):
            data = core.prepare(bundle, job['family'], job['fitRows'] if phase == 'inner' else job['refitRows'])
            output = root/label/job['id']
            selected = None if previous is None else previous['runs'][number]
            selection = None if selected is None else dict(innerFreeze=previous_pin,
                        checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch'])
            core.train(data, job['selectionRows'] if phase == 'inner' else [], output,
                              config_value(job, pin, phase, selection),
                              epochs=None if selected is None else selected['selectedEpoch'])
            if phase == 'inner':
                files.write_json(output/'selected-replay.json', core.replay(output, data, job['selectionRows']))
            artifacts = scalar.manifest(output)
            result = scalar.check_manifest(artifacts)
            run = dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=result['bestEpoch'])
            validate_run(job, run, pin, phase, bundle['cohort'])
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
    frozen, refit_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'outer-refit', bundle['cohort'])
    root = Path(path).resolve().parent
    files.write_json(root/'outer-started.json', dict(plan=pin, refitFreeze=refit_pin))
    predictions = []
    try:
        for job, run in zip(plan['jobs'], frozen['runs'], strict=True):
            data = core.prepare(bundle, job['family'], job['refitRows'])
            prediction = core.replay(Path(run['artifacts']['best.pt']['path']).parent, data, job['outerRows'])
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
    refits, _ = check_freeze(plan, pin, frozen['refitFreeze']['path'], frozen['refitFreeze']['sha256'], 'outer-refit', bundle['cohort'])
    records = {}
    for job, pred, run in zip(plan['jobs'], frozen['predictions'], refits['runs'], strict=True):
        value = read(pred['artifact'])
        require(value['jobId'] == job['id'] and value['refitCheckpoint'] == run['artifacts']['best.pt'], 'Prediction checkpoint lineage differs')
        cfg = read(run['artifacts']['config.json'])
        prior = np.asarray([cfg['priorState'][bundle['cohort']['rows'][i]['targetPhone']]['probabilities'] for i in job['outerRows']])
        require(value['prior'] == dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()), 'Prediction prior differs')
        records[job['id']] = value
    controls = read(plan['inputs']['expandedHeadsReport'])
    require(controls['complete'] is True and controls['plan'] == plan['inputs']['expandedHeadsPlan'], 'Expanded controls lineage')
    corrected = read(plan['inputs']['correctedReferenceReport'])
    require(corrected['complete'] is True and corrected['plan'] == plan['inputs']['correctedReferencePlan'], 'Secondary control lineage')
    references = {regime: {**{family:controls['models'][regime][family]['original'] for family in (*FAMILIES,'equal-mixture')},
                          'corrected-mixture':corrected['models'][regime]} for regime in REGIMES}
    result = evaluation.evaluate(bundle['cohort']['rows'], bundle['originalCohort']['rows'], plan['jobs'], records, references)
    result['childLossResponses'] = loss_responses(result, references, bundle['originalCohort']['rows'])
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
