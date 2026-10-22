"""Ten frozen child-targeted temperature fits and separate outer development audit."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import torch

import multiphone_research_audio as files
import multiphone_phonetic_head as head
import multiphone_head_outer as outer_head
import multiphone_outer_report as loader
import multiphone_selection_audit as metrics
import multiphone_rating_reliability as reliability
from rating_temperature import core

HERE = files.HERE
BASE = HERE / 'outputs/multiphone-20260926'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-temperature-protocol.md'
REGIMES = ('all-age', 'child-only')
AGES = ('allAges', 'ages6to12', 'ages13plus')
COHORT_SHA = '33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805'
SPLITS_SHA = 'b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf'
COMPARISON_SHA = 'c12a0562ffec6f9783c231950a7099dee3a0b0e196cf0a2bc0c7ae810077c542'
FALSE_FLAGS = dict(authorTestRead=False, encoderInferencePerformed=False, headTrainingPerformed=False,
                   clinicalUseEligible=False, learnerFeedbackEligible=False, promotionEligible=False)
require = files.require


def read(pin):
    return files.read_bound_json(pin['path'], pin['sha256'])[0]


def model_name(regime):
    require(regime in REGIMES, 'Unexpected age regime')
    return 'phonetic-target-scalars-' + regime


def runtime():
    return dict(python=sys.version, executable=files.binding(sys.executable), numpy=np.__version__,
                torch=torch.__version__, platform=platform.platform(), headReplayDevice='cpu', headReplayThreads=2)


def checked_membership(config, cohort, splits):
    fold, regime = config['fold'], config['regime']
    require(type(fold) is int and 0 <= fold < 5 and regime in REGIMES, 'Invalid fold or regime')
    partition, rows = splits['folds'][fold], cohort['rows']
    fit = [i for i in partition['innerFitRows'] if regime == 'all-age' or 6 <= rows[i]['age'] <= 12]
    validation = partition['innerValidationRows']
    selected = [i for i in validation if 6 <= rows[i]['age'] <= 12]
    require(config['fitRows'] == fit and config['validationRows'] == validation
            and config['selectionRows'] == (validation if regime == 'all-age' else selected), 'Inner membership differs')
    metrics.check_partitions(rows, fit, validation, partition['outerHoldoutRows'])
    require(selected and len({rows[i]['targetPhone'] for i in selected}) == 23, 'Child calibration phone coverage differs')
    return fit, validation, selected


def inputs():
    pins = dict(cohort=files.binding(BASE / 'cohort.json', COHORT_SHA),
                splits=files.binding(BASE / 'splits.json', SPLITS_SHA), protocol=files.binding(PROTOCOL),
                comparison=files.binding(BASE / 'outer-comparison-v1/report.json', COMPARISON_SHA))
    cohort, splits = read(pins['cohort']), read(pins['splits'])
    require(cohort['authorPartition'] == splits['authorPartition'] == 'train', 'Author-training data required')
    jobs = []
    for regime in REGIMES:
        for fold in range(5):
            refit = BASE / 'head-outer' / f'{model_name(regime)}-f{fold}-refit' / 'config.json'
            refit_pin = files.binding(refit)
            outer = read(refit_pin)
            require(outer['phase'] == 'outer-refit' and outer['outerOutcomesUsed'] is False
                    and outer['fold'] == fold and outer['regime'] == regime and outer['family'] == 'target-scalars', 'Refit identity differs')
            inner = Path(outer['selected']['directory'])
            candidates = []
            for rate, suffix in ((.0003, '0003'), (.001, '001')):
                directory = BASE / f'phonetic-head-target-scalars-{regime}-f{fold}-s7-lr{suffix}'
                cfg = json.loads((directory / 'config.json').read_text())
                report = json.loads((directory / 'report.json').read_text())
                history = json.loads((directory / 'history.json').read_text())
                require(cfg['family'] == 'target-scalars' and cfg['fold'] == fold and cfg['regime'] == regime
                        and cfg['lr'] == rate and cfg['seed'] == 7 and cfg['phase'] == 'inner'
                        and cfg['outerOutcomesUsed'] is False and cfg['authorTestInferencePerformed'] is False,
                        'Inner candidate scope differs')
                checked_membership(cfg, cohort, splits)
                epoch = outer_head.verified_epoch(cfg, report, history)
                candidates.append(dict(directory=str(directory), lr=rate, epochs=epoch, loss=report['bestSelectionMacroLogLoss']))
                require(report['complete'] is True and report['configSha256'] == files.digest(directory / 'config.json'), 'Incomplete inner run')
                for key, name in (('checkpoint', 'best.pt'), ('predictions', 'predictions.json'), ('history', 'history.json'), ('prior', 'prior.json')):
                    require(report[key + 'Sha256'] == files.digest(directory / name), 'Inner report artifact differs')
                for name in outer_head.ARTIFACTS:
                    path = directory / name
                    require(outer['innerArtifactsSha256'].get(str(path)) == files.digest(path), 'Refit/inner artifact linkage differs')
            require(outer['selected'] == min(candidates, key=lambda t: (t['loss'], t['lr'], t['epochs']))
                    and sorted(outer['trials'], key=lambda t: t['lr']) == candidates, 'Original candidate selection differs')
            cfg_pin = files.binding(inner / 'config.json')
            cfg = read(cfg_pin)
            fit, validation, calibration = checked_membership(cfg, cohort, splits)
            require(cfg['inputFiles'] == outer['inputBinding'], 'Inner/refit feature lineage differs')
            for path, sha in outer['innerArtifactsSha256'].items():
                pins['artifact/' + path] = files.binding(path, sha)
            for key, pin in cfg['inputFiles'].items():
                pins['input/' + pin['path']] = pin
            pins['binding/' + cfg['binding']] = files.binding(cfg['binding'], cfg['bindingSha256'])
            for name, sha in cfg['sourceSha256'].items():
                pins['trainer/' + name] = files.binding(HERE / name, sha)
            pins['refit/' + str(refit)] = refit_pin
            pred_pin = files.binding(inner / 'predictions.json')
            pred = read(pred_pin)
            require(pred['rowIndices'] == validation, 'Inner prediction row identity differs')
            core.normalized(pred['probabilities'])
            job = dict(regime=regime, fold=fold, name=model_name(regime), innerDirectory=str(inner),
                       config=cfg_pin, predictions=pred_pin, checkpoint=files.binding(inner / 'best.pt'),
                       refitConfig=refit_pin, fitRows=fit, validationRows=validation, calibrationRows=calibration)
            jobs.append(job)
    for path in sorted(HERE.glob('*.py')) + sorted(DIRECTORY.glob('*.py')):
        pins['source/' + str(path)] = files.binding(path)
    files.guard(pins)
    return pins, jobs


def plan_value(pins, jobs):
    return dict(inputs=pins, jobs=jobs, runtime=runtime(), betaBounds=[.05, 20], iterations=80,
                fitPopulation='ages6to12 inner validation', calibrationFittingPerformed=False,
                outerPredictionsRead=False, **FALSE_FLAGS)


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
    pins, jobs = inputs()
    output.mkdir(parents=True, mode=0o700)
    files.write_json(output / 'plan.json', plan_value(pins, jobs))
    return files.binding(output / 'plan.json')


def load_plan(path, sha):
    pin = files.binding(path, sha)
    plan = read(pin)
    pins, jobs = inputs()
    require(plan == plan_value(pins, jobs), 'Frozen declaration differs')
    return plan, pin


def replay(job):
    """Equivalent to the original replay, but never rewrites its pinned receipt."""
    cfg = read(job['config'])
    args = argparse.Namespace(**cfg)
    args.binding, args.output = Path(args.binding), Path(args.output)
    head.source_guard(cfg)
    data = head.setup(args)
    require(data['bindings'] == cfg['inputFiles'] and data['fit'] == cfg['fitRows']
            and data['validation'] == cfg['validationRows'] and data['selection'] == cfg['selectionRows']
            and data['priors'] == cfg['priorState'], 'Replay fitting/input identity differs')
    report = json.loads((Path(job['innerDirectory']) / 'report.json').read_text())
    saved = torch.load(job['checkpoint']['path'], map_location='cpu', weights_only=True)
    require(saved['configSha256'] == job['config']['sha256'] and saved['epoch'] == saved['bestEpoch'] == report['bestEpoch']
            and saved['bestLoss'] == report['bestSelectionMacroLogLoss']
            and torch.equal(saved['mean'], data['mean']) and torch.equal(saved['std'], data['std']), 'Replay selected state differs')
    network = head.make_model(args, data['values'].shape[1])
    network.load_state_dict(saved['model'], strict=True)
    with torch.inference_mode():
        scores, probabilities = head.evaluate(network, data, data['validation'], 'cpu', args.batch_size)
    require(probabilities == read(job['predictions']) and scores == report['evaluation'], 'Actual inner checkpoint replay differs')
    head.source_guard(cfg)
    files.guard(cfg['inputFiles'])
    return dict(exact=True, headInferencePerformed=True, encoderInferencePerformed=False,
                checkpoint=job['checkpoint'], predictions=job['predictions'], rows=len(job['validationRows']))


def fitted_value(job, rows):
    pred = read(job['predictions'])
    positions = {index: pos for pos, index in enumerate(pred['rowIndices'])}
    p = np.asarray([pred['probabilities'][positions[i]] for i in job['calibrationRows']], dtype=np.float64)
    selected = [rows[i] for i in job['calibrationRows']]
    counts = np.asarray([r['raterCounts'] for r in selected])
    fitted = core.fit(p, counts)
    q, corrected = core.normalized(p), core.scaled(p, fitted['beta'])
    require(np.array_equal(q.argmax(1), corrected.argmax(1)), 'Positive temperature changed argmax')
    return dict(regime=job['regime'], fold=job['fold'], rows=job['calibrationRows'], parameters=fitted,
                rawProbabilities=p.tolist(), normalizedProbabilities=q.tolist(), correctedProbabilities=corrected.tolist(),
                maxNormalizationChange=float(np.max(np.abs(q - p))), support=metrics.support(selected),
                outerPredictionsRead=False, calibrationFittingPerformed=True, **FALSE_FLAGS)


def fit(path, sha):
    torch.set_num_threads(2)
    plan, pin = load_plan(path, sha)
    root = Path(path).resolve().parent
    files.write_json(root / 'fit-started.json', dict(plan=pin))
    results = []
    try:
        rows = read(plan['inputs']['cohort'])['rows']
        for job in plan['jobs']:
            receipt = replay(job)
            value = fitted_value(job, rows)
            value['actualReplay'] = receipt
            target = root / f"fit-{job['regime']}-f{job['fold']}.json"
            files.write_json(target, value)
            results.append(files.binding(target))
            print(json.dumps(dict(fitted=job['name'], fold=job['fold'])), flush=True)
        files.guard(plan['inputs'])
        files.write_json(root / 'freeze.json', dict(complete=True, plan=pin, fits=results,
                         calibrationFittingPerformed=True, headReplayCount=10, outerPredictionsRead=False, **FALSE_FLAGS))
        return files.binding(root / 'freeze.json')
    except Exception as error:
        files.write_json(root / 'fit-failure.json', dict(error=f'{type(error).__name__}: {error}', fits=results))
        raise


def check_freeze(plan, plan_pin, path, sha):
    pin = files.binding(path, sha)
    freeze = read(pin)
    require(freeze['complete'] is True and freeze['plan'] == plan_pin and len(freeze['fits']) == 10
            and freeze['outerPredictionsRead'] is False and freeze['headReplayCount'] == 10, 'Incomplete or foreign freeze')
    rows = read(plan['inputs']['cohort'])['rows']
    fits = []
    for job, ref in zip(plan['jobs'], freeze['fits'], strict=True):
        saved = read(ref)
        require({k: v for k, v in saved.items() if k != 'actualReplay'} == fitted_value(job, rows), 'Frozen fit reconstruction differs')
        receipt = saved['actualReplay']
        require(receipt == dict(exact=True, headInferencePerformed=True, encoderInferencePerformed=False,
                checkpoint=job['checkpoint'], predictions=job['predictions'], rows=len(job['validationRows'])), 'Frozen replay receipt differs')
        fits.append(saved)
    return fits, pin


def reliability_views(p, rows):
    result = {}
    for age in AGES:
        mask = np.asarray([age == 'allAges' or (6 <= r['age'] <= 12 if age == 'ages6to12' else r['age'] >= 13) for r in rows])
        rr = [r for r, keep in zip(rows, mask, strict=True) if keep]
        pp = p[mask]
        phones = {}
        for phone in ('aggregate', *metrics.PHONES):
            select = np.asarray([phone == 'aggregate' or r['targetPhone'] == phone for r in rr], dtype=bool)
            phones[phone] = {event: reliability.reliability(pp[select], [r for r, keep in zip(rr, select, strict=True) if keep], classes)
                             for event, classes in reliability.EVENTS.items()}
        result[age] = phones
    return result


def exact_discrimination_nll(value, logs, counts):
    value['perRaterLogLoss'] = float(-(counts * logs).sum() / counts.sum())
    for label in range(3):
        total = counts[:, label].sum()
        value['classes'][str(label)]['conditionalNLL'] = (
            float(-(counts[:, label] * logs[:, label]).sum() / total) if total else None)


def summarize(p, rows, seen, logs):
    """Reuse ranking/support metrics, replace every clipped NLL/entropy copy."""
    require(logs.shape == p.shape and np.isfinite(logs).all()
            and np.allclose(np.exp(logs), p, rtol=3e-13, atol=0), 'Stable log probabilities differ')
    measures = metrics.summarize(p, rows, seen)
    seen = np.asarray(seen, dtype=bool)
    for word, word_mask in (('allWords', np.ones(len(rows), dtype=bool)), ('seenWords', seen), ('unseenWords', ~seen)):
        for age in AGES:
            mask = word_mask & np.asarray([age == 'allAges' or (6 <= r['age'] <= 12 if age == 'ages6to12' else r['age'] >= 13) for r in rows])
            selected = [r for r, keep in zip(rows, mask, strict=True) if keep]
            value = measures[word]['metrics'][age]
            if not selected:
                require(value is None, 'Empty metric slice is not null')
                continue
            counts = np.asarray([r['raterCounts'] for r in selected], dtype=np.float64)
            lp = logs[mask]
            value['perRaterLogLoss'] = float(-(counts * lp).sum() / counts.sum())
            exact_discrimination_nll(value['discrimination'], lp, counts)
            per_phone_nll = []
            for phone in metrics.PHONES:
                pmask = np.asarray([r['targetPhone'] == phone for r in selected])
                if not pmask.any():
                    continue
                nll = float(-(counts[pmask] * lp[pmask]).sum() / counts[pmask].sum())
                value['perTarget'][phone]['perRaterLogLoss'] = nll
                exact_discrimination_nll(value['targetDiscrimination']['perPhone'][phone], lp[pmask], counts[pmask])
                per_phone_nll.append(nll)
            value['macroTargetLogLoss'] = float(np.mean(per_phone_nll))
            measures[word]['confidence'][age]['meanEntropy'] = float(-(p[mask] * lp).sum(1).mean())
    return dict(measures=measures, reliability=reliability_views(p, rows), nllUsesUnclippedStableLogs=True)


def normalization_delta(raw_metrics, normalized_summary):
    result = {}
    for age in AGES:
        raw = raw_metrics[age]
        normalized = normalized_summary['measures']['allWords']['metrics'][age]
        result[age] = None if raw is None else {
            k: normalized[k] - raw[k] for k in ('perRaterLogLoss', 'macroTargetLogLoss', 'perRaterBrier')}
    return result


def primary(summary):
    m = summary['measures']['allWords']['metrics']['ages6to12']
    return dict(NLL=m['perRaterLogLoss'], macroNLL=m['macroTargetLogLoss'], Brier=m['perRaterBrier'],
                rating0AP=m['discrimination']['rating0']['averagePrecision'],
                below2AP=m['discrimination']['ratingBelow2']['averagePrecision'])


def screen(baseline, corrected, folds):
    require(len(folds) == 5, 'Exactly five outer folds required')
    b, c = primary(baseline), primary(corrected)
    delta = {k: c[k] - b[k] for k in b}
    fdelta = [primary(f['corrected'])['NLL'] - primary(f['normalized'])['NLL'] for f in folds]
    require(all(np.isfinite(v) for v in [*delta.values(), *fdelta]), 'Undefined primary metric')
    checks = dict(pooledNLLImproves=delta['NLL'] < -1e-12,
                  everyFoldNLLNoWorse=all(v <= 1e-12 for v in fdelta),
                  pooledMacroNLLNoWorse=delta['macroNLL'] <= 1e-12,
                  pooledBrierNoWorse=delta['Brier'] <= 1e-12,
                  pooledRating0APNoWorse=delta['rating0AP'] >= -1e-12,
                  pooledBelow2APNoWorse=delta['below2AP'] >= -1e-12)
    return dict(consistentDevelopmentGain=all(checks.values()), checks=checks, childDelta=delta,
                childFoldNLLDeltas=fdelta, promotionEligible=False)


def outer_calculation(plan, plan_pin, freeze_path, freeze_sha):
    # Verify/freeze all ten fits before any outer prediction loader is called.
    fits, freeze_pin = check_freeze(plan, plan_pin, freeze_path, freeze_sha)
    published = read(plan['inputs']['comparison'])
    bundle = loader.load_predictions(Path(published['releasePath']), published['releaseSha256'],
                                     Path(published['evaluationLedgerPath']), published['evaluationLedgerSha256'])
    rows, indices = bundle['rows'], bundle['rowIndices']
    require(len(indices) == 14837 and indices == published['alignedRowIndices'], 'Historical outer row alignment differs')
    source_pins = {k: files.binding(k, v) for k, v in bundle['artifactSha256'].items()}
    for job in plan['jobs']:
        require(source_pins[job['refitConfig']['path']] == job['refitConfig'], 'Calibrator linked to a different released refit')
    models = {}
    for regime in REGIMES:
        name = model_name(regime)
        raw = bundle['models'][name]
        normalized = core.normalized(raw)
        corrected = np.full_like(normalized, np.nan)
        normalized_logs = core.log_scaled(raw, 1)
        corrected_logs = np.full_like(normalized, np.nan)
        seen = bundle['seenTargetWords'][name]
        folds = []
        for fold in range(5):
            mask = np.asarray(bundle['rowFolds']) == fold
            fit_value = next(v for v in fits if v['regime'] == regime and v['fold'] == fold)
            corrected[mask] = core.scaled(raw[mask], fit_value['parameters']['beta'])
            corrected_logs[mask] = core.log_scaled(raw[mask], fit_value['parameters']['beta'])
            rr = [r for r, keep in zip(rows, mask, strict=True) if keep]
            folds.append(dict(fold=fold, rowIndices=[i for i, keep in zip(indices, mask, strict=True) if keep],
                              normalized=summarize(normalized[mask], rr, seen[mask], normalized_logs[mask]),
                              corrected=summarize(corrected[mask], rr, seen[mask], corrected_logs[mask]),
                              rawHistoricalMetrics=metrics.score_predictions(raw[mask], rr)))
            folds[-1]['normalizedMinusRawHistorical'] = normalization_delta(folds[-1]['rawHistoricalMetrics'], folds[-1]['normalized'])
        require(np.isfinite(corrected).all() and np.array_equal(raw.argmax(1), corrected.argmax(1)), 'Outer output missing or argmax changed')
        normalized_summary = summarize(normalized, rows, seen, normalized_logs)
        corrected_summary = summarize(corrected, rows, seen, corrected_logs)
        models[regime] = dict(rowIndices=indices, rowFolds=bundle['rowFolds'], seenInFitVocabulary=seen.tolist(),
            rawProbabilities=raw.tolist(), normalizedProbabilities=normalized.tolist(), correctedProbabilities=corrected.tolist(),
            normalizedLogProbabilities=normalized_logs.tolist(), correctedLogProbabilities=corrected_logs.tolist(),
            maxNormalizationChange=float(np.max(np.abs(raw - normalized))),
            rawValuesBelowLegacyNLLFloor=int((raw < 1e-12).sum()), correctedValuesBelowLegacyNLLFloor=int((corrected < 1e-12).sum()),
            rawHistoricalNLLFloor=1e-12,
            rawHistoricalMetrics=metrics.score_predictions(raw, rows), normalized=normalized_summary,
            corrected=corrected_summary, folds=folds, decision=screen(normalized_summary, corrected_summary, folds))
        models[regime]['normalizedMinusRawHistorical'] = normalization_delta(models[regime]['rawHistoricalMetrics'], normalized_summary)
    loader.guard_bundle(bundle)
    files.guard(plan['inputs'])
    return dict(complete=True, plan=plan_pin, freeze=freeze_pin, outerInputBindings=source_pins, models=models,
                independentFinalValidation=False, calibrationFittingPerformed=True, outerPredictionsRead=True,
                evaluationUsesFrozenCorrections=True, **FALSE_FLAGS)


def audit(path, sha, freeze_path, freeze_sha, output):
    plan, pin = load_plan(path, sha)
    require(not output.exists() and output.resolve().is_relative_to(HERE / 'outputs'), 'Fresh ignored output required')
    output.mkdir(mode=0o700, parents=True)
    files.write_json(output / 'started.json', dict(plan=pin, freeze=files.binding(freeze_path, freeze_sha)))
    try:
        value = outer_calculation(plan, pin, freeze_path, freeze_sha)
        files.write_json(output / 'report.json', value)
        return files.binding(output / 'report.json')
    except Exception as error:
        files.write_json(output / 'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


def verify(path, sha, freeze_path, freeze_sha, output):
    plan, pin = load_plan(path, sha)
    expected = outer_calculation(plan, pin, freeze_path, freeze_sha)
    report_pin = files.binding(output / 'report.json')
    require(read(report_pin) == expected, 'Saved outer report reconstruction differs')
    return dict(verified=True, report=report_pin, scalarFitsReconstructed=10, headInferencePerformed=False,
                encoderInferencePerformed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'fit', 'audit', 'verify'))
    for key in ('plan', 'freeze', 'output'):
        parser.add_argument('--' + key, type=Path)
    for key in ('plan-sha256', 'freeze-sha256'):
        parser.add_argument('--' + key)
    args = parser.parse_args()
    if args.command == 'declare':
        value = declare(args.output)
    elif args.command == 'fit':
        value = fit(args.plan, args.plan_sha256)
    else:
        value = globals()[args.command](args.plan, args.plan_sha256, args.freeze, args.freeze_sha256, args.output)
    print(json.dumps(value), flush=True)
