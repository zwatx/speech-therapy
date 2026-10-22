"""One fixed scalar/corrected-projection probability mixture; no fitting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from lexical_mixture import study as mixture
from lexical_projection import study as projection

ROOT = projection.ROOT
BASE = projection.BASE
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = ROOT / 'docs/model/multiphone-lexical-projection-mixture-protocol.md'
SOURCE = BASE / 'lexical-projection-v1'
SOURCE_HASHES = {
    'plan': '7d9941d73c94c63873fdac8ec606b2ca871cd47c3b5fcb14a7a1a2a2becf3d7e',
    'outer-freeze': '69e34e265416eb4db20eed617395772eb2f54f47c202a2aa4403bd50edb79f92',
    'report': '309861819be78be994ca00f2bc0a68ab656414c67aaf49efdfed9e8495939c41',
}
RECIPE = dict(scalarWeight=.5, projectionWeight=.5,
              arithmetic='float64 logaddexp(logScalar, logProjection) - log(2)',
              fitting=False, weightSearch=False, primaryReference='existing scalar/PCA mixture',
              secondaryReferences=['scalar', 'corrected projection'],
              normalization='inherit normalized stable source logs; no floor or correction')
FLAGS = dict(mixture.FLAGS, modelInferencePerformed=False)
require = projection.require
binding = projection.binding
read = projection.read
write = projection.write


def check_pair(scalar, corrected):
    require(scalar['family'] == 'scalars'
            and corrected['sourceJobId'] == scalar['id'].replace('scalars', 'pca16-scalars')
            and all(scalar[k] == corrected[k] for k in
                    ('regime', 'speakerFold', 'wordGroup', 'fitRows', 'selectionRows', 'refitRows', 'outerRows')),
            'Component membership differs')


def inputs():
    plan, plan_pin, _ = projection.load_plan(SOURCE / 'plan.json', SOURCE_HASHES['plan'])
    outer_pin = binding(SOURCE / 'outer-freeze.json', SOURCE_HASHES['outer-freeze'])
    outer = read(outer_pin)
    require(outer['complete'] is True and outer['plan'] == plan_pin
            and outer['outerInferencePerformed'] is True and outer['trainingPerformed'] is False
            and [p['jobId'] for p in outer['predictions']] == [j['id'] for j in plan['jobs']],
            'Incomplete projection outer freeze')
    refits, refit_pin = projection.check_freeze(plan, plan_pin, outer['refitFreeze']['path'],
                                              outer['refitFreeze']['sha256'], 'outer-refit')
    pins = dict(plan['inputs'], correctedPlan=plan_pin, correctedOuter=outer_pin, correctedRefit=refit_pin,
                correctedInner=refits['innerFreeze'],
                correctedReport=binding(SOURCE / 'report.json', SOURCE_HASHES['report']),
                projectionMixtureProtocol=binding(PROTOCOL))
    scalar_plan = read(pins['baselinePlan'])
    _, scalar_outer, scalar_refits = mixture.checked_outer(mixture.baseline, scalar_plan, pins['baselinePlan'],
                                                          pins['baselineOuter']['path'], pins['baselineOuter']['sha256'])
    scalar_jobs = {j['id']: j for j in scalar_plan['jobs']}
    scalar_predictions = {p['jobId']: p['artifact'] for p in scalar_outer['predictions']}
    corrected_predictions = {p['jobId']: p['artifact'] for p in outer['predictions']}
    corrected_refits = {r['jobId']: r for r in refits['runs']}
    jobs = []
    for source in plan['jobs']:
        scalar_id = source['sourceJobId'].replace('pca16-scalars', 'scalars')
        check_pair(scalar_jobs[scalar_id], source)
        job = {k: source[k] for k in ('regime', 'speakerFold', 'wordGroup', 'outerRows')}
        job.update(id=source['id'].replace('projection', 'projection-mixture'), scalarJobId=scalar_id,
                   projectionJobId=source['id'], scalarPrediction=scalar_predictions[scalar_id],
                   projectionPrediction=corrected_predictions[source['id']],
                   scalarCheckpoint=scalar_refits[scalar_id]['artifacts']['best.pt'],
                   projectionCheckpoint=corrected_refits[source['id']]['artifacts']['best.pt'],
                   projectionSourceOuter=source['sourceOuter'])
        for family in ('scalar', 'projection'):
            pin = job[family + 'Prediction']
            pins['projectionMixturePrediction/' + job['id'] + '/' + family] = binding(pin['path'], pin['sha256'])
        jobs.append(job)
    for path in sorted(DIRECTORY.glob('*.py')):
        pins['projectionMixtureSource/' + path.name] = binding(path)
    require(len(jobs) == len({j['id'] for j in jobs}) == 50, 'Expected 50 fixed pairs')
    mixture.files.guard(pins)
    return pins, jobs


def plan_value(pins, jobs):
    return dict(inputs=pins, jobs=jobs, recipe=RECIPE,
                runtime=dict(python=sys.version, numpy=np.__version__, executable=binding(sys.executable)),
                mixtureCalculated=False, outerPredictionsRead=False, **FLAGS)


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(BASE), 'Fresh ignored output required')
    pins, jobs = inputs()
    output.mkdir(parents=True, mode=0o700)
    write(output / 'plan.json', plan_value(pins, jobs))
    return binding(output / 'plan.json')


def load_plan(path, sha):
    pin = binding(path, sha)
    plan = read(pin)
    pins, jobs = inputs()
    require(plan == plan_value(pins, jobs), 'Projection mixture declaration differs')
    return plan, pin


def checked_predictions(job):
    a, b = read(job['scalarPrediction']), read(job['projectionPrediction'])
    require(a['jobId'] == job['scalarJobId'] and a['refitCheckpoint'] == job['scalarCheckpoint']
            and b['jobId'] == job['projectionJobId'] and b['checkpoint'] == job['projectionCheckpoint']
            and b['sourceOuter'] == job['projectionSourceOuter'] and b['zeroDeltaSourceReplayExact'] is True
            and a['prediction']['rowIndices'] == b['prediction']['rowIndices'] == job['outerRows'],
            'Component prediction lineage differs')
    require(a['prior'] == b['prior'], 'Component fitting priors differ')
    return a['prediction'], b['prediction']


def calculate(plan, pin):
    rows = read(plan['inputs']['cohort'])['rows']
    eligible = [i for i, row in enumerate(rows) if row['trainingEligible']]
    references = {name: read(plan['inputs'][key]) for name, key in
                  [('scalar', 'baselineReport'), ('existingMixture', 'mixtureReport'), ('projection', 'correctedReport')]}
    for name, key in [('scalar', 'baselinePlan'), ('existingMixture', 'mixturePlan'), ('projection', 'correctedPlan')]:
        require(references[name]['complete'] is True and references[name]['plan'] == plan['inputs'][key],
                'Reference report lineage differs')
    require(references['projection']['outerFreeze'] == plan['inputs']['correctedOuter'], 'Projection report freeze differs')
    models, comparisons = {}, {}
    for regime in mixture.REGIMES:
        cells, merged = [], {}
        for job in [j for j in plan['jobs'] if j['regime'] == regime]:
            a, b = checked_predictions(job)
            rr = [rows[i] for i in job['outerRows']]
            pred = mixture.mixture(a, b, rr)
            cells.append(dict(speakerFold=job['speakerFold'], wordGroup=job['wordGroup'],
                              sourcePredictions=dict(scalar=job['scalarPrediction'], projection=job['projectionPrediction']),
                              rowIndices=job['outerRows'], prediction=pred, summary=mixture.compact.summarize(pred, rr)))
            for i, p, lp in zip(pred['rowIndices'], pred['probabilities'], pred['logProbabilities'], strict=True):
                require(i not in merged, 'Duplicate mixture position')
                merged[i] = p, lp, job['speakerFold'], job['wordGroup']
        require(sorted(merged) == eligible and len(cells) == 25, 'Incomplete mixture outer coverage')
        p = [merged[i][0] for i in eligible]
        lp = [merged[i][1] for i in eligible]
        row_folds = [merged[i][2] for i in eligible]
        full = dict(rowIndices=eligible, probabilities=p, logProbabilities=lp)
        folds = []
        for fold in range(5):
            keep = [k for k, f in enumerate(row_folds) if f == fold]
            ids = [eligible[k] for k in keep]
            pred = dict(probabilities=[p[k] for k in keep], logProbabilities=[lp[k] for k in keep])
            folds.append(dict(speakerFold=fold, rowIndices=ids, summary=mixture.compact.summarize(pred, [rows[i] for i in ids])))
        candidate = dict(**full, rowFolds=row_folds, rowWordGroups=[merged[i][3] for i in eligible],
                         cells=cells, speakerFolds=folds, pooled=mixture.compact.summarize(full, [rows[i] for i in eligible]))
        refs = dict(scalar=references['scalar']['models'][regime]['scalars'],
                    existingMixture=references['existingMixture']['models'][regime],
                    projection=references['projection']['models'][regime],
                    prior=references['scalar']['models'][regime]['prior'])
        for reference in refs.values():
            mixture.compact.check_reference_identity(candidate, reference)
        models[regime] = candidate
        comparisons[regime] = {name: mixture.compact.consistency(candidate, refs[name])
                               for name in ('existingMixture', 'scalar', 'projection')}
        comparisons[regime]['minusPrior'] = mixture.compact.primary_delta(candidate['pooled'], refs['prior']['pooled'])
    mixture.files.guard(plan['inputs'])
    return dict(complete=True, plan=pin, models=models, comparisons=comparisons, recipe=RECIPE,
                referenceReports={name: plan['inputs'][key] for name, key in
                                  [('scalar', 'baselineReport'), ('existingMixture', 'mixtureReport'), ('projection', 'correctedReport')]},
                mixtureCalculated=True, outerPredictionsRead=True, **FLAGS)


def run(path, sha, verify=False):
    plan, pin = load_plan(path, sha)
    root = Path(path).resolve().parent
    if not verify:
        write(root / 'started.json', dict(plan=pin, **FLAGS))
    try:
        value = calculate(plan, pin)
        if verify:
            report_pin = binding(root / 'report.json')
            require(read(report_pin) == value, 'Saved projection mixture report differs')
            return dict(verified=True, report=report_pin, **FLAGS)
        write(root / 'report.json', value)
        return binding(root / 'report.json')
    except Exception as error:
        if not verify:
            write(root / 'failure.json', dict(error=f'{type(error).__name__}: {error}', **FLAGS))
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
