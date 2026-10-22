"""Fixed same-seed posterior-pooling comparisons with explicit material, compact, age and phone gates.

Run from research/audio-head after a complete outer freeze:
  python -m posterior_pooling.evaluation evaluate --plan PLAN --sha256 SHA --outer OUTER --outer-sha256 SHA
  python -m posterior_pooling.evaluation verify --plan PLAN --sha256 SHA --outer OUTER --outer-sha256 SHA
The frozen middle_layer.evaluation metrics/difference/screen are reused
unchanged. Each seed passes only on screen.materialGainPass (relative to the
same-seed fresh-hard mixture) plus a compact NLL gain; the directional screen
alone never passes. Means across seeds are descriptive only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import traceback

import numpy as np
import torch

from middle_layer.evaluation import metrics, difference, screen
from multiphone_data import TARGETS
from posterior_pooling import study as s

SEEDS, require = s.SEEDS, s.require
KEYS = ('candidate', 'freshHard', 'scalar')
PAIRS = dict(primary=('candidateMixture', 'freshHardMixture'), compact=('candidate', 'freshHard'))
AXES = ('fold', 'age', 'phone', 'child')
TOLERANCE = 1e-7


class InvalidEvaluation(ValueError):
    """An undefined or nonfinite primary endpoint makes the comparison invalid, neither pass nor fail."""


def support(value):
    """Positions, children, recordings, votes and each event's positive/negative rater and child support."""
    if value is None:
        return None
    return dict({k: value[k] for k in ('positions', 'children', 'recordings', 'votes')},
                events={name: {k: value['events'][name][k] for k in
                               ('positiveRaterWeight', 'negativeRaterWeight', 'positiveChildren', 'negativeChildren')}
                        for name in ('rating0', 'below2')})


def checked_primary(deltas, folds, reference):
    primary, compact = deltas['primary'], deltas['compact']
    values = [reference, None if compact is None else compact['nll'], *(None if f is None else f['nll'] for f in folds)]
    values += [None] if primary is None else [primary[k] for k in ('nll', 'macroNll', 'brier', 'rating0Ap', 'below2Ap')]
    if any(v is None or not np.isfinite(v) for v in values) or not reference > 0:
        raise InvalidEvaluation('Undefined or nonfinite primary endpoint invalidates the evaluation')


def evaluate_seed(rows, indices, folds, logs):
    require(set(logs) == set(KEYS), 'Expected candidate, fresh hard and one shared scalar prediction')
    require(len(indices) == len(set(indices)) == len(rows) == len(folds), 'Duplicate or incomplete rows')
    require(set(folds) == set(range(5)), 'Missing speaker fold')
    require(all(6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None for r in rows), 'Expected original child positions')
    predictions = {k: np.asarray(v, dtype=np.float64) for k, v in logs.items()}
    for arm in s.ARMS:
        # Both mixtures use the identical selected scalar component.
        predictions[arm+'Mixture'] = np.logaddexp(predictions[arm], predictions['scalar']) - np.log(2.)

    def view(mask):
        chosen = [r for r, keep in zip(rows, mask, strict=True) if keep]
        values = {k: metrics(v[mask], chosen) for k, v in predictions.items()}
        shown = [support(v) for v in values.values()]
        require(all(v == shown[0] for v in shown), 'Arms differ in subgroup support')
        return dict(metrics=values, support=shown[0],
                    deltas={k: difference(values[a], values[b]) for k, (a, b) in PAIRS.items()})

    pooled = view(np.ones(len(rows), dtype=bool))
    axes = dict(fold=(folds, range(5)), age=([r['age'] for r in rows], range(6, 13)),
                phone=([r['targetPhone'] for r in rows], TARGETS[:23]),
                child=([r['speakerId'] for r in rows], sorted({r['speakerId'] for r in rows})))
    groups = {axis: {str(k): view(np.asarray(values) == k) for k in keys} for axis, (values, keys) in axes.items()}
    fold_deltas = [groups['fold'][str(i)]['deltas']['primary'] for i in range(5)]
    reference = pooled['metrics']['freshHardMixture']['nll']
    checked_primary(pooled['deltas'], fold_deltas, reference)
    primary = screen(pooled['deltas']['primary'], fold_deltas, reference)
    compact = bool(pooled['deltas']['compact']['nll'] < -TOLERANCE)
    six = groups['age']['6']
    return dict(pooled=pooled, groups=groups, screen=primary, compactCoCondition=compact,
                seedPass=bool(primary['materialGainPass'] and compact),
                relativeNllDenominator='same-seed fresh-hard mixture NLL',
                ageSix=None if six['support'] is None else dict(
                    rating0Ap={k: v['events']['rating0']['averagePrecision'] for k, v in six['metrics'].items()},
                    macroNll={k: v['macroNll'] for k, v in six['metrics'].items()}, deltas=six['deltas']))


def spread(values):
    """Descriptive only; never a gate or a rescue."""
    if any(v is None for v in values):
        return None
    require(np.isfinite(values).all(), 'Nonfinite delta')
    return dict(mean=float(np.mean(values)), minimum=float(min(values)), maximum=float(max(values)))


def summarize(seeds):
    require(set(seeds) == {str(seed) for seed in SEEDS}, 'Exactly seeds 17, 29, 43 required')
    ordered = [seeds[str(seed)] for seed in SEEDS]
    passes = [bool(v['screen']['materialGainPass'] and v['compactCoCondition']) for v in ordered]
    require(passes == [v['seedPass'] for v in ordered], 'Seed pass must equal material gain and the compact co-condition')
    changes = {pair: {k: spread([v['pooled']['deltas'][pair][k] for v in ordered]) for k in ordered[0]['pooled']['deltas'][pair]}
               for pair in PAIRS}
    groups = {}
    for axis in AXES:
        keys = list(ordered[0]['groups'][axis])
        require(all(list(v['groups'][axis]) == keys for v in ordered), 'Subgroup inventory differs across seeds')
        groups[axis] = {}
        for key in keys:
            views = [v['groups'][axis][key] for v in ordered]
            require(all(w['support'] is not None and w['support'] == views[0]['support'] for w in views),
                    'Subgroup support missing or differs across seeds')
            deltas = [w['deltas']['primary'] for w in views]
            nll = [d['nll'] for d in deltas]
            groups[axis][key] = dict(support=views[0]['support'], nllChange=spread(nll),
                                     perSeedNllChange=dict(zip(map(str, SEEDS), nll, strict=True)),
                                     seedsWithWorseNll=sum(d > TOLERANCE for d in nll),
                                     perSeedRating0ApChange=dict(zip(map(str, SEEDS), (d['rating0Ap'] for d in deltas), strict=True)),
                                     perSeedBelow2ApChange=dict(zip(map(str, SEEDS), (d['below2Ap'] for d in deltas), strict=True)))
    require(list(groups['fold']) == [str(i) for i in range(5)] and list(groups['age']) == [str(a) for a in range(6, 13)]
            and list(groups['phone']) == list(TARGETS[:23]), 'All five folds, seven ages and 23 consonants required')
    every = {axis: [k for k, v in groups[axis].items() if v['seedsWithWorseNll'] == len(SEEDS)] for axis in AXES}
    some = {axis: {k: v['seedsWithWorseNll'] for k, v in groups[axis].items() if 0 < v['seedsWithWorseNll'] < len(SEEDS)}
            for axis in AXES}
    per_seed = {str(seed): dict(seedPass=passed, materialGainPass=v['screen']['materialGainPass'],
                                directionalPass=v['screen']['directionalPass'], compactCoCondition=v['compactCoCondition'],
                                relativeNllReduction=v['screen']['relativeNllReduction'], checks=v['screen']['checks'],
                                regressionCounts={axis: sum(g['perSeedNllChange'][str(seed)] > TOLERANCE for g in groups[axis].values())
                                                  for axis in AXES})
                for seed, v, passed in zip(SEEDS, ordered, passes, strict=True)}
    development = bool(all(passes) and not every['age'] and not every['phone'])
    return dict(perSeed=per_seed, changes=changes, changesDescriptiveOnly=True, groups=groups,
                ageGuard=dict(passed=not every['age'], agesWorseAtEverySeed=every['age']),
                phoneGuard=dict(passed=not every['phone'], phonesWorseAtEverySeed=every['phone']),
                regressionsAtEverySeed=every, lessConsistentRegressions=some,
                childRegressionsDescriptiveOnly=True,
                allSeedsMaterialGain=all(v['screen']['materialGainPass'] for v in ordered),
                allSeedsCompactGain=all(v['compactCoCondition'] for v in ordered),
                allSeedsPass=all(passes), developmentPass=development,
                promotionEligible=False, clinicalUseEligible=False, learnerFeedbackEligible=False,
                independentFinalValidation=False)


def evaluate(rows, cells, predictions, scalars, *, positions=s.OUTER_POSITIONS):
    """Every cell's acoustic arms and the shared scalar component on identical ordered original-child rows."""
    expected = {i for i, r in enumerate(rows) if 6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None}
    require(len(expected) == positions, 'Expected every original child position')
    require(len(cells) == 25*len(SEEDS) and set(scalars) == {c['id'] for c in cells}, 'Incomplete cells or scalar component')
    seeds = {}
    for seed in SEEDS:
        chosen = [c for c in cells if c['seed'] == seed]
        require(sorted((c['speakerFold'], c['wordGroup']) for c in chosen) == [(f, w) for f in range(5) for w in range(5)],
                'Incomplete seed cells')
        values, folds = {k: {} for k in KEYS}, {}
        for cell in chosen:
            for name in KEYS:
                prediction = (scalars[cell['id']] if name == 'scalar' else predictions[cell['jobs'][name]])['prediction']
                require(prediction['rowIndices'] == cell['outerRows'], 'Prediction outer membership or order differs')
                for i, lp in zip(prediction['rowIndices'], prediction['logProbabilities'], strict=True):
                    require(i not in values[name], 'Duplicated matched row')
                    values[name][i] = lp
                    require(folds.setdefault(i, cell['speakerFold']) == cell['speakerFold'], 'Speaker fold differs')
        require(all(set(v) == expected for v in values.values()), 'Incomplete matched child coverage')
        ids = sorted(expected)
        seeds[str(seed)] = evaluate_seed([rows[i] for i in ids], ids, [folds[i] for i in ids],
                                         {k: [v[i] for i in ids] for k, v in values.items()})
    return dict(seeds=seeds, acrossSeeds=summarize(seeds), rowIndices=sorted(expected))


def diagnostics(plan, pin, controls):
    """PCA variance, selected epochs, counts and timings; descriptive, never tuning criteria."""
    root = Path(pin['path']).parent
    phases = {label: s.read(s.files.binding(root/(label+'-freeze.json'))) for label in ('controls', 'inner', 'refit', 'outer')}
    variance = {}
    for label in ('inner', 'refit'):
        for record in phases[label]['runs']:
            if 'transform.pt' in record['artifacts']:
                transform = torch.load(record['artifacts']['transform.pt']['path'], map_location='cpu', weights_only=True)
                variance.setdefault(label, {})[record['jobId']] = transform['varianceFraction']
    return dict(descriptiveOnly=True, pcaVarianceFraction=variance,
                selectedEpochs={label: {r['jobId']: r['selectedEpoch'] for r in phases[label]['runs']} for label in ('inner', 'refit')},
                phaseElapsedSeconds={label: value['elapsedSeconds'] for label, value in phases.items()},
                counts=dict(historicalScalarControlsChecked=len(controls['cells']), scalarReuse=controls['decision']['scalarReuse'],
                            innerFits=len(phases['inner']['runs']), refits=len(phases['refit']['runs']),
                            outerPasses=len(phases['outer']['predictions'])),
                extraction=plan['extraction'])


def calculate(path, sha, outer_path, outer_sha):
    plan, pin, _, bundles = s.load_plan(path, sha)
    require(plan['gates'] == s.GATES, 'Declared gates differ from the evaluator')
    controls, control_pin = s.checked_control_freeze(plan, pin)
    predictions, outer_pin = s.checked_outer(plan, pin, bundles, outer_path, outer_sha)
    records = {}
    if controls['decision']['scalarReuse']:
        outcomes, records = s.scalar_controls(plan, bundles, [])
        require({k: controls[k] for k in outcomes} == outcomes and records == s.read(controls['records']),
                'Scalar control replay differs from its freeze')
    scalars = s.scalar_component(plan, controls, records, predictions)
    value = evaluate(bundles['cohort']['rows'], plan['cells'], predictions, scalars)
    require(all(len(v['groups']['child']) == plan['support']['children'] for v in value['seeds'].values()),
            'All children must be shown with identical support')
    diagnostic = diagnostics(plan, pin, controls)
    s.final_guards(plan)
    s.guard_freeze(control_pin)
    s.guard_freeze(outer_pin)
    return dict(complete=True, study=s.STUDY, plan=pin, controls=control_pin, outerFreeze=outer_pin,
                scalarComponent=controls['decision']['mode'], gates=s.GATES, **value, diagnostics=diagnostic,
                limitations=s.LIMITATIONS, researchDataOnly=True, trainingPerformed=False, headInferencePerformed=True,
                **s.FLAGS)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('evaluate', 'verify'))
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--outer', type=Path, required=True)
    parser.add_argument('--outer-sha256', required=True)
    args = parser.parse_args()
    root = args.plan.resolve().parent
    output, failure = root/'results.json', root/'results-failure.json'
    if args.command == 'evaluate':
        require(not output.exists() and not failure.exists(), 'Preserve existing results; no implicit restart')
    started = time.monotonic()
    try:
        result = calculate(args.plan, args.sha256, args.outer, args.outer_sha256)
    except BaseException as error:
        if args.command == 'evaluate':
            s.files.write_json(failure, dict(complete=False, study=s.STUDY, errorType=type(error).__name__, errorMessage=str(error),
                                             errorTraceback=''.join(traceback.format_exception(error)),
                                             invalid=isinstance(error, InvalidEvaluation), elapsedSeconds=time.monotonic()-started,
                                             restartAllowed=False, **s.FLAGS))
        raise
    if args.command == 'evaluate':
        s.files.write_json(output, result)
    else:
        require(s.read(s.files.binding(output)) == result, 'Results do not reconstruct exactly')
    print(json.dumps(s.files.binding(output)))


if __name__ == '__main__':
    main()
