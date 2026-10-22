"""Frozen temperature control on original inner heads and outer speakers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from rating_temperature import study as prior
from rating_temperature import core

files, head, metrics = prior.files, prior.head, prior.metrics
require, read = files.require, prior.read
HERE = files.HERE
ROOT = HERE / 'outputs/multiphone-20260927'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-temperature-transfer-protocol.md'
OLD_PLAN = ROOT / 'temperature-v1/plan.json'
OLD_PLAN_SHA = 'b2fc54f03e246b1678f3636e7f52e89caec0b7d353b229e23109f2ce0802be59'
OLD_FREEZE = ROOT / 'temperature-v1/freeze.json'
OLD_FREEZE_SHA = '73ecdda7f807896df94a1d69871dff5fa46ea329899c3be9f6ce3c00d1e43dac'
OLD_REPORT = ROOT / 'temperature-audit-v1/report.json'
OLD_REPORT_SHA = '9ab82dd8af7bfeedad2ee44204cce249ad07e699c3aef54fffbd630ee516ee33'
FLAGS = dict(calibrationFittingPerformed=False, **prior.FALSE_FLAGS)


def frozen_inputs():
    # Read the already audited, content-pinned optima; never call core.fit.
    old, old_pin = prior.load_plan(OLD_PLAN, OLD_PLAN_SHA)
    freeze_pin = files.binding(OLD_FREEZE, OLD_FREEZE_SHA)
    freeze = read(freeze_pin)
    require(freeze['complete'] is True and freeze['plan'] == old_pin
            and len(freeze['fits']) == len(old['jobs']) == 10, 'Foreign calibration freeze')
    pins = dict(old['inputs'], calibrationPlan=old_pin, calibrationFreeze=freeze_pin,
                refitReport=files.binding(OLD_REPORT, OLD_REPORT_SHA), transferProtocol=files.binding(PROTOCOL))
    rows, splits = read(pins['cohort'])['rows'], read(pins['splits'])
    jobs = []
    for job, fit_pin in zip(old['jobs'], freeze['fits'], strict=True):
        fit = read(fit_pin)
        require(fit['regime'] == job['regime'] and fit['fold'] == job['fold']
                and fit['rows'] == job['calibrationRows']
                and fit['actualReplay']['checkpoint'] == job['checkpoint'], 'Correction/model identity differs')
        beta = fit['parameters']['beta']
        require(np.isfinite(beta) and .05 <= beta <= 20, 'Invalid frozen inverse temperature')
        outer = splits['folds'][job['fold']]['outerHoldoutRows']
        metrics.check_partitions(rows, job['fitRows'], job['validationRows'], outer)
        pins[f"frozenFit/{job['regime']}/{job['fold']}"] = fit_pin
        jobs.append(dict(job, correction=fit_pin, beta=beta, outerRows=outer))
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['transferSource/' + str(path)] = files.binding(path)
    files.guard(pins)
    return pins, jobs


def plan_value():
    pins, jobs = frozen_inputs()
    return dict(inputs=pins, jobs=jobs, runtime=prior.runtime(), headInferencePerformed=False,
                independentFinalValidation=False, evaluationUsesFrozenCorrections=True, **FLAGS)


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
    value = plan_value()
    output.mkdir(parents=True, mode=0o700)
    files.write_json(output / 'plan.json', value)
    return files.binding(output / 'plan.json')


def load_plan(path, sha):
    pin = files.binding(path, sha)
    plan = read(pin)
    require(plan == plan_value(), 'Transfer declaration differs')
    return plan, pin


def validate_prediction(job, value, rows):
    require(value['regime'] == job['regime'] and value['fold'] == job['fold']
            and value['checkpoint'] == job['checkpoint'] and value['correction'] == job['correction']
            and value['rowIndices'] == job['outerRows'], 'Prediction/model/outer row identity differs')
    require(value['headInferencePerformed'] is True and all(value[k] is v for k, v in FLAGS.items()),
            'Prediction execution or eligibility flags differ')
    metrics.check_partitions(rows, job['fitRows'], job['validationRows'], value['rowIndices'])
    raw = np.asarray(value['probabilities'], dtype=np.float64)
    require(raw.shape == (len(job['outerRows']), 3), 'Outer prediction shape differs')
    core.normalized(raw)
    selected = [rows[i] for i in job['outerRows']]
    seen = metrics.lexical_mask(selected, [rows[i] for i in job['fitRows']])
    require(value['seenInFitVocabulary'] == seen.tolist(), 'Inner fitting vocabulary differs')
    require(value['innerReplay'] == dict(exact=True, rows=job['validationRows'],
                checkpoint=job['checkpoint'], predictions=job['predictions']), 'Missing exact inner replay')
    return raw, seen


def infer(job):
    cfg = read(job['config'])
    args = argparse.Namespace(**cfg)
    args.binding, args.output = Path(args.binding), Path(args.output)
    head.source_guard(cfg)
    data = head.setup(args)
    require(data['bindings'] == cfg['inputFiles'] and data['fit'] == cfg['fitRows']
            and data['validation'] == cfg['validationRows'] and data['selection'] == cfg['selectionRows']
            and data['priors'] == cfg['priorState'], 'Inner model setup differs')
    saved = torch.load(job['checkpoint']['path'], map_location='cpu', weights_only=True)
    old_report = json.loads((Path(job['innerDirectory']) / 'report.json').read_text())
    require(saved['configSha256'] == job['config']['sha256']
            and saved['epoch'] == saved['bestEpoch'] == old_report['bestEpoch']
            and saved['bestLoss'] == old_report['bestSelectionMacroLogLoss']
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']),
            'Selected checkpoint or fit-only normalization differs')
    network = head.make_model(args, data['values'].shape[1])
    network.load_state_dict(saved['model'], strict=True)
    rows = data['cohort']['rows']
    metrics.check_partitions(rows, data['fit'], data['validation'], job['outerRows'])
    with torch.inference_mode():
        scores, replay = head.evaluate(network, data, data['validation'], 'cpu', args.batch_size)
        require(replay == read(job['predictions']) and scores == old_report['evaluation'], 'Actual inner replay differs')
        _, prediction = head.evaluate(network, data, job['outerRows'], 'cpu', args.batch_size)
    value = dict(regime=job['regime'], fold=job['fold'], checkpoint=job['checkpoint'], correction=job['correction'],
                 rowIndices=prediction['rowIndices'], probabilities=prediction['probabilities'],
                 seenInFitVocabulary=metrics.lexical_mask([rows[i] for i in job['outerRows']],
                                                         [rows[i] for i in data['fit']]).tolist(),
                 innerReplay=dict(exact=True, rows=job['validationRows'], checkpoint=job['checkpoint'], predictions=job['predictions']),
                 headInferencePerformed=True, **FLAGS)
    validate_prediction(job, value, rows)
    head.source_guard(cfg)
    files.guard(cfg['inputFiles'])
    return value


def run(path, sha):
    torch.set_num_threads(2)
    plan, pin = load_plan(path, sha)
    output = Path(path).resolve().parent
    files.write_json(output / 'started.json', dict(plan=pin))
    predictions = []
    try:
        for job in plan['jobs']:
            value = infer(job)
            dest = output / f"outer-{job['regime']}-f{job['fold']}.json"
            files.write_json(dest, value)
            predictions.append(files.binding(dest))
            print(json.dumps(dict(inferred=job['regime'], fold=job['fold'], rows=len(value['rowIndices']))), flush=True)
        files.guard(plan['inputs'])
        files.write_json(output / 'freeze.json', dict(complete=True, plan=pin, predictions=predictions,
            innerReplayCount=10, outerInferenceCount=10, headInferencePerformed=True, **FLAGS))
        return files.binding(output / 'freeze.json')
    except Exception as error:
        files.write_json(output / 'failure.json', dict(error=f'{type(error).__name__}: {error}', predictions=predictions))
        raise


def summary(raw, rows, seen, beta):
    q, p = core.normalized(raw), core.scaled(raw, beta)
    require(np.array_equal(q.argmax(1), p.argmax(1)), 'Positive temperature changed argmax')
    return dict(normalized=prior.summarize(q, rows, seen, core.log_scaled(raw, 1)),
                corrected=prior.summarize(p, rows, seen, core.log_scaled(raw, beta)))


def primary_contrast(baseline, corrected):
    a, b = prior.primary(baseline), prior.primary(corrected)
    return {key: b[key] - a[key] for key in a}


def arm_comparison(same, refit):
    require(same['rowIndices'] == refit['rowIndices'] and same['rowFolds'] == refit['rowFolds'],
            'Same-head/refit outer alignment differs')
    sd, rd = same['decision']['childDelta'], refit['decision']['childDelta']
    return dict(sameHeadChildDelta=sd, refitChildDelta=rd,
                sameHeadMinusRefitDelta={k: sd[k] - rd[k] for k in sd},
                sameHeadBaselineMinusRefitBaseline=primary_contrast(refit['normalized'], same['normalized']),
                sameHeadCorrectedMinusRefitCorrected=primary_contrast(refit['corrected'], same['corrected']),
                folds=[dict(fold=f['fold'], sameHeadChildDelta=primary_contrast(f['normalized'], f['corrected']),
                            refitChildDelta=primary_contrast(r['normalized'], r['corrected']))
                       for f, r in zip(same['folds'], refit['folds'], strict=True)],
                causalAttributionEstablished=False, independentFinalValidation=False)


def calculate(plan, pin, freeze_path, freeze_sha):
    freeze_pin = files.binding(freeze_path, freeze_sha)
    frozen = read(freeze_pin)
    require(frozen == dict(complete=True, plan=pin, predictions=frozen['predictions'], innerReplayCount=10,
            outerInferenceCount=10, headInferencePerformed=True, **FLAGS)
            and len(frozen['predictions']) == len(plan['jobs']) == 10, 'Transfer inference freeze differs')
    cohort = read(plan['inputs']['cohort'])
    rows = cohort['rows']
    expected = [i for i, row in enumerate(rows) if row['trainingEligible']]
    require(len(expected) == 14837, 'Original eligible population differs')
    reference = read(plan['inputs']['refitReport'])
    models = {}
    for regime in prior.REGIMES:
        tables, by_index = [], {}
        for job, prediction_pin in zip(plan['jobs'], frozen['predictions'], strict=True):
            if job['regime'] != regime:
                continue
            value = read(prediction_pin)
            raw, seen = validate_prediction(job, value, rows)
            rr = [rows[i] for i in job['outerRows']]
            tables.append(dict(fold=job['fold'], rowIndices=job['outerRows'], **summary(raw, rr, seen, job['beta'])))
            for i, p, visible in zip(job['outerRows'], raw, seen, strict=True):
                require(i not in by_index, 'Duplicate outer row')
                by_index[i] = (p, bool(visible), job['fold'], job['beta'])
        require([t['fold'] for t in tables] == list(range(5)) and sorted(by_index) == expected, 'Incomplete outer folds/rows')
        raw = np.asarray([by_index[i][0] for i in expected])
        seen = np.asarray([by_index[i][1] for i in expected])
        row_folds = [by_index[i][2] for i in expected]
        corrected = np.empty_like(raw)
        logs = np.empty_like(raw)
        for fold in range(5):
            mask = np.asarray(row_folds) == fold
            beta = next(j['beta'] for j in plan['jobs'] if j['regime'] == regime and j['fold'] == fold)
            corrected[mask] = core.scaled(raw[mask], beta)
            logs[mask] = core.log_scaled(raw[mask], beta)
        q = core.normalized(raw)
        require(np.array_equal(q.argmax(1), corrected.argmax(1)), 'Pooled argmax differs')
        rr = [rows[i] for i in expected]
        normalized_summary = prior.summarize(q, rr, seen, core.log_scaled(raw, 1))
        corrected_summary = prior.summarize(corrected, rr, seen, logs)
        model = dict(rowIndices=expected, rowFolds=row_folds, seenInFitVocabulary=seen.tolist(),
                     rawProbabilities=raw.tolist(), normalizedProbabilities=q.tolist(), correctedProbabilities=corrected.tolist(),
                     normalizedLogProbabilities=core.log_scaled(raw, 1).tolist(), correctedLogProbabilities=logs.tolist(),
                     normalized=normalized_summary, corrected=corrected_summary, folds=tables,
                     maxNormalizationChange=float(np.max(np.abs(raw-q))),
                     rawValuesBelowLegacyNLLFloor=int((raw < 1e-12).sum()),
                     correctedValuesBelowLegacyNLLFloor=int((corrected < 1e-12).sum()),
                     decision=prior.screen(normalized_summary, corrected_summary, tables))
        model['refitComparison'] = arm_comparison(model, reference['models'][regime])
        models[regime] = model
    files.guard(plan['inputs'])
    files.guard({str(i): p for i, p in enumerate(frozen['predictions'])})
    return dict(complete=True, plan=pin, inferenceFreeze=freeze_pin, refitReport=plan['inputs']['refitReport'], models=models,
                independentFinalValidation=False, evaluationUsesFrozenCorrections=True,
                calibrationParametersInherited=True, headInferencePerformed=False, **FLAGS)


def audit(path, sha, freeze_path, freeze_sha, output, verify=False):
    plan, pin = load_plan(path, sha)
    if not verify:
        require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
        output.mkdir(parents=True, mode=0o700)
        files.write_json(output / 'started.json', dict(plan=pin, freeze=files.binding(freeze_path, freeze_sha)))
    try:
        value = calculate(plan, pin, freeze_path, freeze_sha)
        if verify:
            report_pin = files.binding(output / 'report.json')
            require(read(report_pin) == value, 'Transfer report reconstruction differs')
            return dict(verified=True, report=report_pin, headInferencePerformed=False, **FLAGS)
        files.write_json(output / 'report.json', value)
        return files.binding(output / 'report.json')
    except Exception as error:
        if not verify:
            files.write_json(output / 'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'audit', 'verify'))
    for key in ('plan', 'freeze', 'output'):
        parser.add_argument('--' + key, type=Path)
    for key in ('plan-sha256', 'freeze-sha256'):
        parser.add_argument('--' + key)
    args = parser.parse_args()
    if args.command == 'declare':
        result = declare(args.output)
    elif args.command == 'run':
        result = run(args.plan, args.plan_sha256)
    else:
        result = audit(args.plan, args.plan_sha256, args.freeze, args.freeze_sha256, args.output, args.command == 'verify')
    print(json.dumps(result), flush=True)
