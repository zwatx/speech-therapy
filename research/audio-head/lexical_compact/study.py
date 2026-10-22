"""Fixed fit-only PCA16 phonetic head on canonical lexical partitions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys

import numpy as np
import torch

import multiphone_research_audio as files
from rating_temperature import study as scoring
from lexical_heads import study as baseline
from lexical_compact import core

HERE = files.HERE
BASE = HERE / 'outputs/multiphone-20260927'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-lexical-compact-protocol.md'
BASE_PLAN = BASE / 'lexical-heads-v1/plan.json'
BASE_PLAN_SHA = 'bd55f8ab41f52137c6be6f5f9bfefbad64c3855d4ed84077a26245a600edfa18'
BASE_REPORT = BASE / 'lexical-head-audit-v1/report.json'
BASE_REPORT_SHA = '6f4680ddf6b3f89b4e9796d7bd21d2b0f44c2232cd1cf361efbf38c3c45291fb'
FAMILY = 'pca16-scalars'
REGIMES = ('all-age', 'child-only')
FLAGS = baseline.FLAGS
require = files.require
read = baseline.read


def inputs():
    original_pin = files.binding(BASE_PLAN, BASE_PLAN_SHA)
    original = read(original_pin)
    pins, original_jobs, bundle = baseline.inputs()
    require(original == baseline.plan_value(pins, original_jobs), 'Baseline declaration changed')
    pins = dict(pins, baselinePlan=original_pin, baselineReport=files.binding(BASE_REPORT, BASE_REPORT_SHA),
                compactProtocol=files.binding(PROTOCOL))
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['compactSource/' + str(path)] = files.binding(path)
    jobs = []
    for old in original_jobs:
        if old['family'] != 'target-scalars':
            continue
        job = dict(old, family=FAMILY, id=old['id'].replace('target-scalars', FAMILY))
        # baseline.inputs checked every complete utterance, row, speaker and age.
        jobs.append(job)
    require(len(jobs) == 50, 'Expected 50 fixed candidate cells')
    files.guard(pins)
    return pins, jobs, bundle


def plan_value(pins, jobs):
    return dict(inputs=pins, jobs=jobs, recipe=core.RECIPE,
                runtime=dict(python=sys.version, numpy=np.__version__, torch=torch.__version__, platform=platform.platform(), executable=files.binding(sys.executable)),
                transform=core.TRANSFORM_RECIPE, innerFitCount=50, refitCount=50, outerInferenceCount=50, trainingPerformed=False,
                outerInferencePerformed=False, **FLAGS)


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
    pins, jobs, _ = inputs()
    output.mkdir(parents=True, mode=0o700)
    files.write_json(output / 'plan.json', plan_value(pins, jobs))
    return files.binding(output / 'plan.json')


def load_plan(path, sha):
    pin = files.binding(path, sha)
    plan = read(pin)
    pins, jobs, bundle = inputs()
    require(plan == plan_value(pins, jobs), 'Head declaration changed')
    return plan, pin, bundle


def config_value(job, plan_pin, phase, selection=None):
    value = dict(experiment='canonical-lexical-compact-v1', phase=phase, plan=plan_pin,
                 job={k: job[k] for k in ('id', 'family', 'regime', 'speakerFold', 'wordGroup')},
                 outerInferencePerformed=False, **FLAGS)
    if selection is not None:
        value['innerSelection'] = selection
    return value


def manifest(directory):
    # Bind all files created by the trainer, including saved initialization and histories.
    paths = sorted(p for p in directory.iterdir() if p.is_file())
    require(paths and (directory / 'report.json').is_file(), 'Incomplete trainer artifacts')
    return {p.name: files.binding(p) for p in paths}


def check_manifest(value):
    files.guard(value)
    require('report.json' in value and 'config.json' in value and 'history.json' in value
            and all(name in value for name in ('best.pt', 'last.pt', 'initial.pt')), 'Incomplete run manifest')
    return read(value['report.json'])


def inner(path, sha):
    plan, pin, bundle = load_plan(path, sha)
    root = Path(path).resolve().parent
    files.write_json(root / 'inner-started.json', dict(plan=pin))
    runs = []
    try:
        for job in plan['jobs']:
            data = core.prepare(bundle, job['family'], job['fitRows'])
            output = root / 'inner' / job['id']
            core.train(data, job['selectionRows'], output, config_value(job, pin, 'inner'))
            artifacts = manifest(output)
            report = check_manifest(artifacts)
            require(report['complete'] is True and 1 <= report['bestEpoch'] <= 100, 'Invalid completed inner selection')
            replay = core.replay(output, data, job['selectionRows'])
            files.write_json(output / 'selected-replay.json', replay)
            artifacts = manifest(output)
            runs.append(dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=report['bestEpoch']))
            print(json.dumps(dict(innerComplete=job['id'], selectedEpoch=report['bestEpoch'], epochsRun=report['epochsRun'])), flush=True)
        files.guard(plan['inputs'])
        files.write_json(root / 'inner-freeze.json', dict(complete=True, plan=pin, runs=runs,
            trainingPerformed=True, outerInferencePerformed=False, **FLAGS))
        return files.binding(root / 'inner-freeze.json')
    except Exception as error:
        files.write_json(root / 'inner-failure.json', dict(error=f'{type(error).__name__}: {error}', completedJobs=[r['jobId'] for r in runs]))
        raise


def validate_history(job, run, plan_pin, phase, rows):
    # Same fixed recipe/history semantics as the pinned baseline; add transform lineage.
    require(core.RECIPE == baseline.core.RECIPE, 'Head training recipe changed')
    report = baseline.validate_history(job, run, plan_pin, phase, rows)
    artifacts = run['artifacts']
    cfg = read(artifacts['config.json'])
    require(cfg['transform'] == artifacts['transform.pt'] and cfg['transformRecipe'] == core.TRANSFORM_RECIPE
            and cfg['featureWidth'] == 29 and cfg['family'] == FAMILY, 'Transform configuration binding differs')
    transform = torch.load(artifacts['transform.pt']['path'], map_location='cpu', weights_only=True)
    expected_fit = job['fitRows'] if phase == 'inner' else job['refitRows']
    require(transform['fitRows'] == expected_fit and transform['rank'] == 16
            and tuple(transform['center'].shape) == (1024,) and tuple(transform['basis'].shape) == (1024, 16)
            and tuple(transform['eigenvalues'].shape) == (1024,), 'Transform fitting identity or shape differs')
    for name, epoch in [('initial.pt', 0), ('best.pt', report['bestEpoch']), ('last.pt', report['epochsRun'])]:
        state = torch.load(artifacts[name]['path'], map_location='cpu', weights_only=True)
        require(state['transformSha256'] == artifacts['transform.pt']['sha256']
                and state['configSha256'] == artifacts['config.json']['sha256'] and state['epoch'] == epoch,
                'Checkpoint transform/configuration/epoch lineage differs')
    return report


def check_freeze(plan, plan_pin, path, sha, phase):
    pin = files.binding(path, sha)
    frozen = read(pin)
    require(frozen['complete'] is True and frozen['plan'] == plan_pin
            and frozen['outerInferencePerformed'] is False and frozen['trainingPerformed'] is True
            and all(frozen[k] is v for k, v in FLAGS.items())
            and [r['jobId'] for r in frozen['runs']] == [j['id'] for j in plan['jobs']], 'Wrong or incomplete fit freeze')
    rows = read(plan['inputs']['cohort'])['rows']
    for job, run in zip(plan['jobs'], frozen['runs'], strict=True):
        validate_history(job, run, plan_pin, phase, rows)
    return frozen, pin


def refit(path, sha, freeze_path, freeze_sha):
    plan, pin, bundle = load_plan(path, sha)
    frozen, inner_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'inner')
    root = Path(path).resolve().parent
    files.write_json(root / 'refit-started.json', dict(plan=pin, innerFreeze=inner_pin))
    runs = []
    try:
        for job, selected in zip(plan['jobs'], frozen['runs'], strict=True):
            data = core.prepare(bundle, job['family'], job['refitRows'])
            output = root / 'refit' / job['id']
            source = dict(innerFreeze=inner_pin, checkpoint=selected['artifacts']['best.pt'], epoch=selected['selectedEpoch'])
            core.train(data, [], output, config_value(job, pin, 'outer-refit', source), epochs=selected['selectedEpoch'])
            artifacts = manifest(output)
            report = check_manifest(artifacts)
            require(report['epochsRun'] == report['bestEpoch'] == selected['selectedEpoch'], 'Refit epoch budget differs')
            runs.append(dict(jobId=job['id'], artifacts=artifacts, selectedEpoch=selected['selectedEpoch']))
            print(json.dumps(dict(refitComplete=job['id'], epochsRun=report['epochsRun'])), flush=True)
        files.guard(plan['inputs'])
        files.write_json(root / 'refit-freeze.json', dict(complete=True, plan=pin, innerFreeze=inner_pin, runs=runs,
            trainingPerformed=True, outerInferencePerformed=False, **FLAGS))
        return files.binding(root / 'refit-freeze.json')
    except Exception as error:
        files.write_json(root / 'refit-failure.json', dict(error=f'{type(error).__name__}: {error}', completedJobs=[r['jobId'] for r in runs]))
        raise


def checked_refits(plan, pin, freeze_path, freeze_sha):
    frozen, refit_pin = check_freeze(plan, pin, freeze_path, freeze_sha, 'outer-refit')
    inner_freeze, _ = check_freeze(plan, pin, frozen['innerFreeze']['path'], frozen['innerFreeze']['sha256'], 'inner')
    for refit_run, inner_run in zip(frozen['runs'], inner_freeze['runs'], strict=True):
        require(refit_run['selectedEpoch'] == inner_run['selectedEpoch'], 'Refit/inner selected epoch differs')
        cfg = read(refit_run['artifacts']['config.json'])
        require(cfg['innerSelection'] == dict(innerFreeze=frozen['innerFreeze'], checkpoint=inner_run['artifacts']['best.pt'], epoch=inner_run['selectedEpoch']),
                'Refit selected checkpoint lineage differs')
    return frozen, refit_pin


def outer(path, sha, freeze_path, freeze_sha):
    plan, pin, bundle = load_plan(path, sha)
    frozen, refit_pin = checked_refits(plan, pin, freeze_path, freeze_sha)
    root = Path(path).resolve().parent
    files.write_json(root / 'outer-started.json', dict(plan=pin, refitFreeze=refit_pin))
    predictions = []
    try:
        for job, run in zip(plan['jobs'], frozen['runs'], strict=True):
            data = core.prepare(bundle, job['family'], job['refitRows'])
            directory = Path(run['artifacts']['best.pt']['path']).parent
            prediction = core.replay(directory, data, job['outerRows'])
            rows = [bundle['cohort']['rows'][i] for i in job['outerRows']]
            prior = np.asarray([data['priors'][r['targetPhone']]['probabilities'] for r in rows])
            value = dict(jobId=job['id'], refitCheckpoint=run['artifacts']['best.pt'], prediction=prediction,
                         prior=dict(rowIndices=job['outerRows'], probabilities=prior.tolist(), logProbabilities=np.log(prior).tolist()),
                         headInferencePerformed=True, **FLAGS)
            output = root / 'outer' / (job['id'] + '.json')
            output.parent.mkdir(exist_ok=True)
            files.write_json(output, value)
            predictions.append(dict(jobId=job['id'], artifact=files.binding(output)))
            print(json.dumps(dict(outerComplete=job['id'], rows=len(rows))), flush=True)
        files.guard(plan['inputs'])
        files.write_json(root / 'outer-freeze.json', dict(complete=True, plan=pin, refitFreeze=refit_pin,
            predictions=predictions, outerInferencePerformed=True, trainingPerformed=False, **FLAGS))
        return files.binding(root / 'outer-freeze.json')
    except Exception as error:
        files.write_json(root / 'outer-failure.json', dict(error=f'{type(error).__name__}: {error}', completedJobs=[p['jobId'] for p in predictions]))
        raise


def summarize(prediction, rows):
    p, logs = (np.asarray(prediction[k], dtype=np.float64) for k in ('probabilities', 'logProbabilities'))
    return scoring.summarize(p, rows, np.zeros(len(rows), dtype=bool), logs)


def primary_delta(candidate, control):
    a, b = scoring.primary(candidate), scoring.primary(control)
    return {k: a[k] - b[k] for k in a}


def consistency(candidate, control):
    delta = primary_delta(candidate['pooled'], control['pooled'])
    fold_delta = [primary_delta(a['summary'], b['summary']) for a, b in zip(candidate['speakerFolds'], control['speakerFolds'], strict=True)]
    require(len(fold_delta) == 5 and all(np.isfinite(v) for d in [delta, *fold_delta] for v in d.values()), 'Undefined primary endpoint')
    checks = dict(pooledChildNLLImproves=delta['NLL'] < -1e-7,
                  everySpeakerFoldChildNLLNoWorse=all(d['NLL'] <= 1e-7 for d in fold_delta),
                  pooledChildMacroNLLNoWorse=delta['macroNLL'] <= 1e-7,
                  pooledChildBrierNoWorse=delta['Brier'] <= 1e-7,
                  pooledChildRating0APNoWorse=delta['rating0AP'] >= -1e-7,
                  pooledChildBelow2APNoWorse=delta['below2AP'] >= -1e-7)
    return dict(consistentDevelopmentGain=all(checks.values()), checks=checks, childDelta=delta,
                speakerFoldChildDeltas=fold_delta, promotionEligible=False)


def check_reference_identity(candidate, reference):
    require(all(reference[key] == candidate[key] for key in ('rowIndices', 'rowFolds', 'rowWordGroups')),
            'Reference outer identities differ')
    require([(c['speakerFold'], c['wordGroup'], c['rowIndices']) for c in reference['cells']]
            == [(c['speakerFold'], c['wordGroup'], c['rowIndices']) for c in candidate['cells']],
            'Reference cells differ')
    require([(f['speakerFold'], f['rowIndices']) for f in reference['speakerFolds']]
            == [(f['speakerFold'], f['rowIndices']) for f in candidate['speakerFolds']],
            'Reference speaker fold identity differs')


def calculate(plan, pin, freeze_path, freeze_sha):
    outer_pin = files.binding(freeze_path, freeze_sha)
    frozen = read(outer_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['outerInferencePerformed'] is True
            and [p['jobId'] for p in frozen['predictions']] == [j['id'] for j in plan['jobs']], 'Outer prediction freeze differs')
    refits, _ = checked_refits(plan, pin, frozen['refitFreeze']['path'], frozen['refitFreeze']['sha256'])
    rows = read(plan['inputs']['cohort'])['rows']
    eligible = [i for i, r in enumerate(rows) if r['trainingEligible']]
    # Reference outcomes are opened only after the candidate refits and predictions are frozen.
    control = read(plan['inputs']['baselineReport'])
    require(control['complete'] is True and control['plan'] == plan['inputs']['baselinePlan'], 'Incomplete reference results')
    records = {}
    for job, pred, refit_run in zip(plan['jobs'], frozen['predictions'], refits['runs'], strict=True):
        value = read(pred['artifact'])
        require(value['jobId'] == job['id'] and value['refitCheckpoint'] == refit_run['artifacts']['best.pt'], 'Outer model lineage differs')
        for key in ('prediction', 'prior'):
            require(value[key]['rowIndices'] == job['outerRows'], 'Outer row identity differs')
        cfg = read(refit_run['artifacts']['config.json'])
        prior = np.asarray([cfg['priorState'][rows[i]['targetPhone']]['probabilities'] for i in job['outerRows']])
        require(value['prior']['probabilities'] == prior.tolist() and value['prior']['logProbabilities'] == np.log(prior).tolist(),
                'Outer prior differs from exact refit counts')
        records[job['id']] = value
    models, comparisons = {}, {}
    for regime in REGIMES:
        cells, merged = [], {}
        for job in [j for j in plan['jobs'] if j['regime'] == regime]:
            pred = records[job['id']]['prediction']
            cells.append(dict(speakerFold=job['speakerFold'], wordGroup=job['wordGroup'], rowIndices=job['outerRows'],
                              summary=summarize(pred, [rows[i] for i in job['outerRows']])))
            for i, p, lp in zip(pred['rowIndices'], pred['probabilities'], pred['logProbabilities'], strict=True):
                require(i not in merged, 'Duplicate outer prediction')
                merged[i] = (p, lp, job['speakerFold'], job['wordGroup'])
        require(sorted(merged) == eligible and len(cells) == 25, 'Incomplete lexical outer coverage')
        p = [merged[i][0] for i in eligible]; logs = [merged[i][1] for i in eligible]
        row_folds = [merged[i][2] for i in eligible]; row_groups = [merged[i][3] for i in eligible]
        full = dict(rowIndices=eligible, probabilities=p, logProbabilities=logs)
        folds = []
        for fold in range(5):
            keep = [pos for pos, f in enumerate(row_folds) if f == fold]
            ids = [eligible[i] for i in keep]
            pred = dict(probabilities=[p[i] for i in keep], logProbabilities=[logs[i] for i in keep])
            folds.append(dict(speakerFold=fold, rowIndices=ids, summary=summarize(pred, [rows[i] for i in ids])))
        candidate = dict(**full, rowFolds=row_folds, rowWordGroups=row_groups, cells=cells, speakerFolds=folds,
                         pooled=summarize(full, [rows[i] for i in eligible]))
        models[regime] = candidate
        for reference in control['models'][regime].values():
            check_reference_identity(candidate, reference)
        comparisons[regime] = dict(candidateVsScalar=consistency(candidate, control['models'][regime]['scalars']),
            candidateVsCombined=consistency(candidate, control['models'][regime]['target-scalars']),
            candidateMinusPrior=primary_delta(candidate['pooled'], control['models'][regime]['prior']['pooled']))
    files.guard(plan['inputs'])
    return dict(complete=True, plan=pin, outerFreeze=outer_pin, referenceReport=plan['inputs']['baselineReport'],
                models=models, comparisons=comparisons, trainingPerformed=False, headInferencePerformed=False,
                outerPredictionsRead=True, **FLAGS)


def audit(path, sha, freeze_path, freeze_sha, output, verify=False):
    plan, pin, _ = load_plan(path, sha)
    if not verify:
        require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
        output.mkdir(parents=True, mode=0o700)
        files.write_json(output / 'started.json', dict(plan=pin, outerFreeze=files.binding(freeze_path, freeze_sha)))
    try:
        value = calculate(plan, pin, freeze_path, freeze_sha)
        if verify:
            report_pin = files.binding(output / 'report.json')
            require(read(report_pin) == value, 'Saved lexical head report differs')
            return dict(verified=True, report=report_pin, **FLAGS)
        files.write_json(output / 'report.json', value)
        return files.binding(output / 'report.json')
    except Exception as error:
        if not verify:
            files.write_json(output / 'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'inner', 'refit', 'outer', 'audit', 'verify'))
    for key in ('plan', 'freeze', 'output'):
        parser.add_argument('--' + key, type=Path)
    for key in ('plan-sha256', 'freeze-sha256'):
        parser.add_argument('--' + key)
    args = parser.parse_args()
    if args.command == 'declare':
        value = declare(args.output)
    elif args.command == 'inner':
        value = inner(args.plan, args.plan_sha256)
    elif args.command in ('refit', 'outer'):
        value = globals()[args.command](args.plan, args.plan_sha256, args.freeze, args.freeze_sha256)
    else:
        value = audit(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256, args.output, args.command == 'verify')
    print(json.dumps(value), flush=True)
