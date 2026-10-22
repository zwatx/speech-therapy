"""One declared equal-probability mixture of frozen lexical heads; no fitting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys

import numpy as np

import multiphone_research_audio as files
from lexical_compact import study as compact
from lexical_heads import study as baseline

HERE = files.HERE
BASE = HERE / 'outputs/multiphone-20260927'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = HERE / '../../docs/model/multiphone-lexical-mixture-protocol.md'
COMPACT_PLAN = BASE / 'lexical-compact-v1/plan.json'
COMPACT_PLAN_SHA = '93796077be5af479c07d4e84e15d87c5c96c8d05664a89bd16ab0b7c70550f16'
COMPACT_OUTER = BASE / 'lexical-compact-v1/outer-freeze.json'
COMPACT_OUTER_SHA = 'abd4b4d7f4e7ead2bca964122a217259ad84591c9be250bce9d49a57ef19a37d'
BASE_OUTER = BASE / 'lexical-heads-v1/outer-freeze.json'
BASE_OUTER_SHA = '53b1ac63258dc7c09804cd64572ac2ac2628646e528cf79ed0bb3076d0a6bbb0'
COMPACT_REPORT = BASE / 'lexical-compact-audit-v1/report.json'
COMPACT_REPORT_SHA = '143450faa46e98a9e091972b906de69a00488cdb8f885adb3ddf8d88d04cd4cd'
RECIPE = dict(scalarWeight=.5, compactWeight=.5, arithmetic='float64 logaddexp(logScalar, logCompact) - log(2)',
              fitting=False, weightSearch=False, normalization='inherit normalized stable source logs; no floor or correction')
FLAGS = dict(baseline.FLAGS, trainingPerformed=False, headInferencePerformed=False, mixtureFittingPerformed=False)
REGIMES = ('all-age', 'child-only')
require = files.require
read = baseline.read


def checked_outer(module, plan, plan_pin, path, sha):
    pin = files.binding(path, sha)
    value = read(pin)
    require(value['complete'] is True and value['plan'] == plan_pin and value['outerInferencePerformed'] is True
            and value['trainingPerformed'] is False
            and [p['jobId'] for p in value['predictions']] == [j['id'] for j in plan['jobs']], 'Incomplete source outer freeze')
    refits, _ = module.checked_refits(plan, plan_pin, value['refitFreeze']['path'], value['refitFreeze']['sha256'])
    return pin, value, {r['jobId']: r for r in refits['runs']}


def check_pair(a, b):
    require(a['family'] == 'scalars' and b['family'] == 'pca16-scalars'
            and all(a[k] == b[k] for k in ('regime', 'speakerFold', 'wordGroup', 'fitRows', 'selectionRows', 'refitRows', 'outerRows')),
            'Component membership differs')


def inputs():
    compact_pin = files.binding(COMPACT_PLAN, COMPACT_PLAN_SHA)
    compact_plan = read(compact_pin)
    pins, compact_jobs, _ = compact.inputs()
    require(compact_plan == compact.plan_value(pins, compact_jobs), 'Compact declaration changed')
    base_pin = pins['baselinePlan']
    base_plan = read(base_pin)
    cp, co, cr = checked_outer(compact, compact_plan, compact_pin, COMPACT_OUTER, COMPACT_OUTER_SHA)
    bp, bo, br = checked_outer(baseline, base_plan, base_pin, BASE_OUTER, BASE_OUTER_SHA)
    pins = dict(pins, compactPlan=compact_pin, compactOuter=cp, baselineOuter=bp,
                compactReport=files.binding(COMPACT_REPORT, COMPACT_REPORT_SHA), mixtureProtocol=files.binding(PROTOCOL))
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['mixtureSource/' + str(path)] = files.binding(path)
    base_jobs = {j['id']: j for j in base_plan['jobs']}
    cpreds = {p['jobId']: p['artifact'] for p in co['predictions']}
    bpreds = {p['jobId']: p['artifact'] for p in bo['predictions']}
    jobs = []
    for job in compact_jobs:
        scalar_id = job['id'].replace('pca16-scalars', 'scalars')
        check_pair(base_jobs[scalar_id], job)
        identity = {k: job[k] for k in ('regime', 'speakerFold', 'wordGroup', 'outerRows')}
        value = dict(**identity, id=job['id'].replace('pca16-scalars', 'equal-mixture'),
                     scalarJobId=scalar_id, compactJobId=job['id'],
                     scalarPrediction=bpreds[scalar_id], compactPrediction=cpreds[job['id']],
                     scalarCheckpoint=br[scalar_id]['artifacts']['best.pt'], compactCheckpoint=cr[job['id']]['artifacts']['best.pt'])
        for family in ('scalar', 'compact'):
            source = value[family + 'Prediction']
            pins['source/' + value['id'] + '/' + family] = files.binding(source['path'], source['sha256'])
        jobs.append(value)
    require(len(jobs) == 50, 'Expected 50 fixed mixture cells')
    files.guard(pins)
    return pins, jobs


def plan_value(pins, jobs):
    return dict(inputs=pins, jobs=jobs, recipe=RECIPE,
                runtime=dict(python=sys.version, numpy=np.__version__, platform=platform.platform(), executable=files.binding(sys.executable)),
                mixtureCalculated=False, outerPredictionsRead=False, **FLAGS)


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
    require(plan == plan_value(pins, jobs), 'Mixture declaration changed')
    return plan, pin


def mixture(a, b, rows):
    require(a['rowIndices'] == b['rowIndices'] and len(rows) == len(a['rowIndices'])
            and len(rows) > 0 and len(set(a['rowIndices'])) == len(rows), 'Mixture row identity differs')
    logs = []
    for value in (a, b):
        p = np.asarray(value['probabilities'], dtype=np.float64)
        lp = np.asarray(value['logProbabilities'], dtype=np.float64)
        require(p.shape == lp.shape == (len(rows), 3) and np.isfinite(lp).all() and np.isfinite(p).all()
                and np.allclose(np.exp(lp), p, rtol=3e-13, atol=0)
                and np.allclose(p.sum(1), 1, atol=1e-12, rtol=0), 'Invalid source probability/log pair')
        logs.append(lp)
    lp = np.logaddexp(logs[0], logs[1]) - np.log(2.)
    p = np.exp(lp)
    counts = np.asarray([r['raterCounts'] for r in rows], dtype=np.float64)
    require(counts.shape == p.shape and np.isfinite(counts).all() and (counts >= 0).all()
            and (counts == np.floor(counts)).all() and (counts.sum(1) == 5).all(), 'Invalid five-vote counts')
    return dict(rowIndices=list(a['rowIndices']), probabilities=p.tolist(), logProbabilities=lp.tolist(),
                NLL=float(-(counts * lp).sum() / (5 * len(rows))))


def calculate(plan, pin):
    rows = read(plan['inputs']['cohort'])['rows']
    eligible = [i for i, row in enumerate(rows) if row['trainingEligible']]
    base = read(plan['inputs']['baselineReport'])
    pca = read(plan['inputs']['compactReport'])
    require(base['complete'] is True and base['plan'] == plan['inputs']['baselinePlan']
            and pca['complete'] is True and pca['plan'] == plan['inputs']['compactPlan'], 'Reference report lineage differs')
    models, comparisons = {}, {}
    for regime in REGIMES:
        cells, merged = [], {}
        for job in [j for j in plan['jobs'] if j['regime'] == regime]:
            a, b = read(job['scalarPrediction']), read(job['compactPrediction'])
            for family, value in (('scalar', a), ('compact', b)):
                require(value['jobId'] == job[family + 'JobId'] and value['refitCheckpoint'] == job[family + 'Checkpoint']
                        and value['prediction']['rowIndices'] == job['outerRows'], 'Component prediction lineage differs')
            require(a['prior'] == b['prior'], 'Component fitting priors differ')
            rr = [rows[i] for i in job['outerRows']]
            pred = mixture(a['prediction'], b['prediction'], rr)
            cells.append(dict(speakerFold=job['speakerFold'], wordGroup=job['wordGroup'],
                              sourcePredictions=dict(scalar=job['scalarPrediction'], compact=job['compactPrediction']),
                              rowIndices=job['outerRows'], prediction=pred, summary=compact.summarize(pred, rr)))
            for i, p, lp in zip(pred['rowIndices'], pred['probabilities'], pred['logProbabilities'], strict=True):
                require(i not in merged, 'Duplicate mixture position')
                merged[i] = p, lp, job['speakerFold'], job['wordGroup']
        require(sorted(merged) == eligible and len(cells) == 25, 'Incomplete mixture outer coverage')
        p = [merged[i][0] for i in eligible]; lp = [merged[i][1] for i in eligible]
        row_folds = [merged[i][2] for i in eligible]; row_groups = [merged[i][3] for i in eligible]
        full = dict(rowIndices=eligible, probabilities=p, logProbabilities=lp)
        folds = []
        for fold in range(5):
            keep = [k for k, f in enumerate(row_folds) if f == fold]
            ids = [eligible[k] for k in keep]
            pred = dict(probabilities=[p[k] for k in keep], logProbabilities=[lp[k] for k in keep])
            folds.append(dict(speakerFold=fold, rowIndices=ids, summary=compact.summarize(pred, [rows[i] for i in ids])))
        candidate = dict(**full, rowFolds=row_folds, rowWordGroups=row_groups, cells=cells, speakerFolds=folds,
                         pooled=compact.summarize(full, [rows[i] for i in eligible]))
        references = dict(scalar=base['models'][regime]['scalars'], compact=pca['models'][regime], prior=base['models'][regime]['prior'])
        for reference in references.values():
            compact.check_reference_identity(candidate, reference)
        models[regime] = candidate
        comparisons[regime] = dict(mixtureVsScalar=compact.consistency(candidate, references['scalar']),
            mixtureVsCompact=compact.consistency(candidate, references['compact']),
            mixtureMinusPrior=compact.primary_delta(candidate['pooled'], references['prior']['pooled']))
    files.guard(plan['inputs'])
    return dict(complete=True, plan=pin, models=models, comparisons=comparisons, recipe=RECIPE,
                referenceReports=dict(baseline=plan['inputs']['baselineReport'], compact=plan['inputs']['compactReport']),
                mixtureCalculated=True, outerPredictionsRead=True, **FLAGS)


def run(path, sha, verify=False):
    plan, pin = load_plan(path, sha)
    root = Path(path).resolve().parent
    if not verify:
        files.write_json(root / 'started.json', dict(plan=pin, **FLAGS))
    try:
        value = calculate(plan, pin)
        if verify:
            report_pin = files.binding(root / 'report.json')
            require(read(report_pin) == value, 'Saved mixture report differs')
            return dict(verified=True, report=report_pin, **FLAGS)
        files.write_json(root / 'report.json', value)
        return files.binding(root / 'report.json')
    except Exception as error:
        if not verify:
            files.write_json(root / 'failure.json', dict(error=f'{type(error).__name__}: {error}', **FLAGS))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'verify'))
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = declare(args.output) if args.command == 'declare' else run(args.plan, args.plan_sha256, args.command == 'verify')
    print(json.dumps(result), flush=True)
