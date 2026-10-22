"""Declared fresh-head training and separate lexical outer evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys

import numpy as np
import torch

import multiphone_research_audio as files
import multiphone_phonetic_head as features
import multiphone_selection_audit as membership
from lexical_canonical import study as lexical
from rating_temperature import study as scoring
from lexical_heads import core

HERE = files.HERE
BASE = HERE / 'outputs/multiphone-20260927'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-lexical-head-protocol.md'
LEXICAL_PLAN = BASE / 'lexical-canonical-v1/plan.json'
LEXICAL_PLAN_SHA = 'c4484f79500bcba049a5b192aa8ec3935e01b44e48dbe99526c9b9c7ab097e8e'
LEXICAL_REPORT = BASE / 'lexical-canonical-v1/report.json'
LEXICAL_REPORT_SHA = '1cb2953ef78cfba10f004598c84f4f1f8a43c66881dee36d5daf506880a731c4'
FEATURE_BINDING = HERE / 'outputs/multiphone-20260926/phonetic-head-binding-v1.json'
FEATURE_BINDING_SHA = '360c829d179f9c66b66c900fdcf3db2cb0897fdc5724feb642100802d3da4985'
FAMILIES = ('scalars', 'target-scalars')
REGIMES = ('all-age', 'child-only')
FLAGS = dict(authorTestRead=False, encoderInferencePerformed=False, calibrationFittingPerformed=False,
             independentFinalValidation=False, clinicalUseEligible=False, learnerFeedbackEligible=False, promotionEligible=False)
require = files.require


def read(pin):
    return files.read_bound_json(pin['path'], pin['sha256'])[0]


def check_job(job, rows, tokens, groups):
    require(job['family'] in FAMILIES and job['regime'] in REGIMES
            and type(job['speakerFold']) is int and 0 <= job['speakerFold'] < 5
            and type(job['wordGroup']) is int and 0 <= job['wordGroup'] < 5, 'Invalid lexical job identity')
    membership.check_partitions(rows, job['fitRows'], job['selectionRows'], job['outerRows'])
    require(sorted(job['fitRows'] + job['selectionRows']) == sorted(job['refitRows'])
            and len(job['refitRows']) == len(set(job['refitRows'])), 'Refit membership differs from fit/selection union')
    for key in ('fitRows', 'selectionRows', 'refitRows'):
        require(all(all(groups[w] != job['wordGroup'] for w in tokens[rows[i]['clipId']]) for i in job[key]),
                'Held-out word occurs in supervised fit/selection utterance')
        if job['regime'] == 'child-only':
            require(all(6 <= rows[i]['age'] <= 12 for i in job[key]), 'Child-only age restriction differs')
    require(all(groups[rows[i]['targetWord'].upper()] == job['wordGroup'] for i in job['outerRows']),
            'Outer target does not belong to held-out word group')
    for key in ('fitRows', 'refitRows'):
        require({rows[i]['targetPhone'] for i in job[key]} == set(membership.PHONES), 'Fitting phone inventory differs')


def inputs():
    old_pin = files.binding(LEXICAL_PLAN, LEXICAL_PLAN_SHA)
    old = read(old_pin)
    require(old == lexical.plan_value(), 'Canonical lexical declaration changed')
    report_pin = files.binding(LEXICAL_REPORT, LEXICAL_REPORT_SHA)
    inventory = read(report_pin)
    require(inventory['complete'] is True and inventory['plan'] == old_pin, 'Incomplete lexical inventory')
    feature_pin = files.binding(FEATURE_BINDING, FEATURE_BINDING_SHA)
    loaded = features.load_bound(FEATURE_BINDING, json.loads(features.RECIPE.read_text()))
    pins = dict(old['inputs'], lexicalPlan=old_pin, lexicalReport=report_pin, featureBinding=feature_pin,
                headProtocol=files.binding(PROTOCOL))
    for key, pin in loaded['bindings'].items():
        pins['feature/' + key] = pin
    for folder in (DIRECTORY, Path(scoring.__file__).parent):
        for path in sorted(folder.glob('*.py')):
            pins['headSource/' + str(path)] = files.binding(path)
    rows = loaded['cohort']['rows']
    require(files.binding(HERE / 'outputs/multiphone-20260926/cohort.json') == pins['cohort'], 'Feature/lexical cohort differs')
    jobs = []
    for regime in REGIMES:
        cells = inventory['models'][regime]['cells']
        require([(c['speakerFold'], c['wordGroup']) for c in cells] == [(s, w) for s in range(5) for w in range(5)], 'Lexical cell inventory differs')
        for family in FAMILIES:
            for cell in cells:
                part = cell['partitions']
                job = dict(id=f"{regime}-{family}-s{cell['speakerFold']}-w{cell['wordGroup']}",
                           family=family, regime=regime, speakerFold=cell['speakerFold'], wordGroup=cell['wordGroup'],
                           fitRows=part['innerFit']['retainedRows'], selectionRows=part['selection']['retainedRows'],
                           refitRows=part['outerFit']['retainedRows'], outerRows=part['outer']['retainedRows'])
                check_job(job, rows, inventory['canonicalProjection']['canonicalTokens'], inventory['wordGroups'])
                jobs.append(job)
    files.guard(pins)
    bundle = dict(cohort=loaded['cohort'], scalars=loaded['scalars'], target=loaded['arrays']['target'], positions=loaded['positions'])
    return pins, jobs, bundle


def plan_value(pins, jobs):
    return dict(inputs=pins, jobs=jobs, recipe=core.RECIPE,
                runtime=dict(python=sys.version, numpy=np.__version__, torch=torch.__version__, platform=platform.platform(), executable=files.binding(sys.executable)),
                innerFitCount=100, refitCount=100, outerInferenceCount=100, trainingPerformed=False,
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
    value = dict(experiment='canonical-lexical-heads-v1', phase=phase, plan=plan_pin,
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
    artifacts = run['artifacts']
    report = check_manifest(artifacts)
    cfg = read(artifacts['config.json'])
    expected_fit = job['fitRows'] if phase == 'inner' else job['refitRows']
    expected_selection = job['selectionRows'] if phase == 'inner' else []
    require(cfg['phase'] == phase and cfg['plan'] == plan_pin
            and cfg['job'] == config_value(job, plan_pin, phase)['job']
            and cfg['recipe'] == core.RECIPE and cfg['family'] == job['family']
            and cfg['fitRows'] == expected_fit and cfg['selectionRows'] == expected_selection
            and cfg['priorState'] == core.fit_priors([rows[i] for i in expected_fit]),
            'Run configuration or partition identity differs')
    require(report['complete'] is True and report['configSha256'] == artifacts['config.json']['sha256']
            and report['fitRows'] == expected_fit and report['selectionRows'] == expected_selection
            and all(artifacts.get(name) == bound for name, bound in report['artifacts'].items()), 'Run report binding differs')
    history = read(artifacts['history.json'])
    require(1 <= len(history) <= 100 and report['epochsRun'] == len(history), 'Incomplete epoch history')
    rng = np.random.default_rng(7)
    best_epoch, best_loss = 0, None
    import hashlib
    updates = (len(expected_fit) + 63) // 64
    for epoch, entry in enumerate(history, 1):
        order = rng.permutation(expected_fit).tolist()
        digest = hashlib.sha256(json.dumps(order, separators=(',', ':')).encode()).hexdigest()
        require(entry['epoch'] == epoch and entry['orderSha256'] == digest and entry['updates'] == updates
                and entry['totalUpdates'] == epoch * updates and np.isfinite(entry['trainLoss']), 'Training update/order history differs')
        if phase == 'inner':
            prediction = entry['selection']
            require(prediction['rowIndices'] == expected_selection, 'Selection history row identity differs')
            lp = np.asarray(prediction['logProbabilities'], dtype=np.float64)
            pp = np.asarray(prediction['probabilities'], dtype=np.float64)
            counts = np.asarray([rows[i]['raterCounts'] for i in expected_selection])
            require(lp.shape == pp.shape == counts.shape and np.isfinite(lp).all()
                    and np.allclose(np.exp(lp), pp, atol=0, rtol=3e-13)
                    and np.allclose(pp.sum(1), 1, atol=1e-12, rtol=0), 'Selection probability/log history differs')
            loss = float(-(counts * lp).sum() / (5 * len(expected_selection)))
            require(prediction['NLL'] == loss, 'Selection NLL differs from stable log probabilities')
            if best_loss is None or loss < best_loss - 1e-7:
                best_epoch, best_loss = epoch, loss
            require(epoch == len(history) or epoch - best_epoch < 15, 'Training continued beyond declared patience')
    require(report['totalUpdates'] == len(history) * updates, 'Total update count differs')
    if phase == 'inner':
        require(len(history) == 100 or len(history) - best_epoch == 15, 'Inner run stopped before declared criterion')
        require(report['bestEpoch'] == run['selectedEpoch'] == best_epoch and report['bestLoss'] == best_loss,
                'Frozen inner checkpoint selection differs')
        require(read(artifacts['selection.json']) == read(artifacts['selected-replay.json']) == history[best_epoch-1]['selection'],
                'Selected prediction/replay differs from history')
    else:
        require(cfg['fixedEpochs'] == len(history) == report['bestEpoch'] == run['selectedEpoch']
                and cfg['innerSelection']['epoch'] == len(history) and report['bestLoss'] is None
                and all('selection' not in h for h in history), 'Refit duration or no-selection policy differs')
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


def calculate(plan, pin, freeze_path, freeze_sha):
    outer_pin = files.binding(freeze_path, freeze_sha)
    frozen = read(outer_pin)
    require(frozen['complete'] is True and frozen['plan'] == pin and frozen['outerInferencePerformed'] is True
            and [p['jobId'] for p in frozen['predictions']] == [j['id'] for j in plan['jobs']], 'Outer prediction freeze differs')
    refits, _ = checked_refits(plan, pin, frozen['refitFreeze']['path'], frozen['refitFreeze']['sha256'])
    rows = read(plan['inputs']['cohort'])['rows']
    eligible = [i for i, r in enumerate(rows) if r['trainingEligible']]
    record_map = {}
    for job, prediction, refit_run in zip(plan['jobs'], frozen['predictions'], refits['runs'], strict=True):
        value = read(prediction['artifact'])
        require(value['jobId'] == job['id'] and value['refitCheckpoint'] == refit_run['artifacts']['best.pt'], 'Outer model lineage differs')
        for key in ('prediction', 'prior'):
            require(value[key]['rowIndices'] == job['outerRows'] and len(value[key]['probabilities']) == len(job['outerRows']), 'Outer row identity differs')
        cfg = read(refit_run['artifacts']['config.json'])
        expected_prior = np.asarray([cfg['priorState'][rows[i]['targetPhone']]['probabilities'] for i in job['outerRows']])
        require(value['prior']['probabilities'] == expected_prior.tolist()
                and value['prior']['logProbabilities'] == np.log(expected_prior).tolist(), 'Outer prior differs from exact refit counts')
        record_map[job['id']] = value
    models, comparisons = {}, {}
    for regime in REGIMES:
        regime_models = {}
        for family in (*FAMILIES, 'prior'):
            source_family = 'scalars' if family == 'prior' else family
            key = 'prior' if family == 'prior' else 'prediction'
            jobs = [j for j in plan['jobs'] if j['regime'] == regime and j['family'] == source_family]
            cells, merged = [], {}
            for job in jobs:
                pred = record_map[job['id']][key]
                if family == 'prior':
                    sibling = job['id'].replace('-scalars-', '-target-scalars-')
                    require(record_map[sibling]['prior'] == pred, 'Family-specific fitting priors differ')
                rr = [rows[i] for i in job['outerRows']]
                cells.append(dict(speakerFold=job['speakerFold'], wordGroup=job['wordGroup'], rowIndices=job['outerRows'], summary=summarize(pred, rr)))
                for index, p, lp in zip(pred['rowIndices'], pred['probabilities'], pred['logProbabilities'], strict=True):
                    require(index not in merged, 'Duplicate outer prediction')
                    merged[index] = (p, lp, job['speakerFold'], job['wordGroup'])
            require(sorted(merged) == eligible and len(cells) == 25, 'Incomplete lexical outer coverage')
            p = [merged[i][0] for i in eligible]; logs = [merged[i][1] for i in eligible]
            row_folds = [merged[i][2] for i in eligible]
            row_groups = [merged[i][3] for i in eligible]
            full = dict(rowIndices=eligible, probabilities=p, logProbabilities=logs)
            folds = []
            for fold in range(5):
                keep = [pos for pos, f in enumerate(row_folds) if f == fold]
                pred = dict(probabilities=[p[i] for i in keep], logProbabilities=[logs[i] for i in keep])
                ids = [eligible[i] for i in keep]
                folds.append(dict(speakerFold=fold, rowIndices=ids, summary=summarize(pred, [rows[i] for i in ids])))
            regime_models[family] = dict(**full, rowFolds=row_folds, rowWordGroups=row_groups, cells=cells, speakerFolds=folds,
                                        pooled=summarize(full, [rows[i] for i in eligible]))
        models[regime] = regime_models
        comparisons[regime] = dict(combinedVsScalar=consistency(regime_models['target-scalars'], regime_models['scalars']),
            neuralMinusPrior={family: primary_delta(regime_models[family]['pooled'], regime_models['prior']['pooled']) for family in FAMILIES})
    files.guard(plan['inputs'])
    return dict(complete=True, plan=pin, outerFreeze=outer_pin, models=models, comparisons=comparisons,
                trainingPerformed=False, headInferencePerformed=False, outerPredictionsRead=True, **FLAGS)


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
