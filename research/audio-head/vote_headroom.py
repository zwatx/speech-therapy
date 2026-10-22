"""Finite five-vote loss decomposition; no training, model inference or selection."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT/'research/audio-head/outputs/multiphone-20260927/posterior-pooling-model-comparison-v1'
WORK = ROOT/'work/core-model-next-method-20260927'
PROTOCOL = ROOT/'docs/model/vote-headroom-v1.md'
SEEDS = (17, 29, 43)
TOL = 1e-12
PINS = {
    'studyPlan': (STUDY/'plan.json', 'bccaf64d0ca431913f073c5c6e6042dd7054dd427235e1bf109528a83ea017df'),
    'results': (STUDY/'results.json', '3bcdbdfc4f717f24aaca78994bb56d568f6275dff5690dcf4e325078bc3c3ee3'),
    'outer': (STUDY/'outer-freeze.json', 'd565d91f95504507ae703fd161673f1da43a01e20765ce2d6234b6f562546411'),
    'controls': (STUDY/'controls-freeze.json', 'a50b00b76739294340cb64adfe72d24900d8efe9f01e40d35c805fc85782cf4e'),
    'resultReview': (WORK/'opus-training-results-review.json', 'b23f7e5cecd029749797dd9a1aa04ca44f1d2fbcfb474f4b2c90cffd34ab2770'),
    'sourceReview': (WORK/'astra-training-source-review.json', '7ac5badcea024f32ac9bc017998460dbb724e68db4bf80c74d3a47def7589b90'),
}
FLAGS = dict(trainingPerformed=False, headInferencePerformed=False, encoderInferencePerformed=False,
             authorTestRead=False, winnerSelected=False, clinicalUseEligible=False,
             learnerFeedbackEligible=False, promotionEligible=False, independentFinalValidation=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path, sha=None):
    path = Path(path).resolve()
    value = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    require(sha is None or value['sha256'] == sha, 'Bound artifact changed: '+str(path))
    return value


def read(pin):
    binding(pin['path'], pin['sha256'])
    return json.loads(Path(pin['path']).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def guards(plan):
    for pin in [*plan['inputs'].values(), *plan['sources'].values()]:
        binding(pin['path'], pin['sha256'])


def declaration():
    inputs = {k: binding(*v) for k, v in PINS.items()}
    old, result, outer, controls = [read(inputs[k]) for k in ('studyPlan', 'results', 'outer', 'controls')]
    require(result['complete'] and outer['complete'] and controls['complete']
            and outer['jobCount'] == len(outer['predictions']) == 150
            and controls['decision']['scalarReuse'], 'Completed all-cell scalar reuse study required')
    inputs['cohort'] = binding(old['inputs']['cohort']['path'], old['inputs']['cohort']['sha256'])
    inputs['scalars'] = binding(controls['records']['path'], controls['records']['sha256'])
    for entry in outer['predictions']:
        inputs['prediction/'+entry['jobId']] = binding(entry['artifact']['path'], entry['artifact']['sha256'])
    for name in ('training-results-root-observation.json', 'training-closeout-root-observation.json'):
        inputs[name] = binding(WORK/name)
    require(len(result['rowIndices']) == len(set(result['rowIndices'])) == 5654, 'Original child coverage differs')
    value = dict(study='vote-headroom-v1', inputs=inputs,
                 sources={p.name: binding(p) for p in (PROTOCOL, Path(__file__), Path(__file__).with_name('test_vote_headroom.py'))},
                 rowIndices=result['rowIndices'], cells=old['cells'], seeds=list(SEEDS),
                 auditTolerance=TOL, empiricalNllReductionReference=.05, population='original child outer positions',
                 runtime=dict(python=platform.python_version(), numpy=np.__version__),
                 empiricalFloorOnly=True, **FLAGS)
    guards(value)
    return value


def terms(counts, logs):
    counts, logs = np.asarray(counts), np.asarray(logs, dtype=np.float64)
    require(counts.ndim == 2 and counts.shape == logs.shape and counts.shape[1] == 3 and len(counts)
            and np.isfinite(counts).all() and (counts >= 0).all() and (counts == np.floor(counts)).all()
            and (counts.sum(1) == 5).all() and np.isfinite(logs).all(), 'Invalid five-vote counts or logs')
    p = np.exp(logs)
    require(np.allclose(p.sum(1), 1., atol=TOL, rtol=0), 'Unnormalized stable logs')
    r = counts/5
    log_r = np.zeros_like(r)
    np.log(r, out=log_r, where=r > 0)
    entropy = -(r*log_r).sum(1)
    nll = -(r*logs).sum(1)
    kl = (r*(log_r-logs)).sum(1)
    floor = 1-(r*r).sum(1)
    brier = 1+(p*p-2*p*r).sum(1)
    squared = ((p-r)**2).sum(1)
    require(np.allclose(nll, entropy+kl, atol=TOL, rtol=0)
            and np.allclose(brier, floor+squared, atol=TOL, rtol=0)
            and (kl >= -TOL).all() and (squared >= -TOL).all(), 'Loss decomposition failed')
    return dict(empiricalEntropy=entropy, nll=nll, nllExcess=kl,
                empiricalBrierFloor=floor, brier=brier, brierExcess=squared)


def view(rows, logs):
    counts = np.asarray([r['raterCounts'] for r in rows])
    values = terms(counts, logs)
    summary = {k: float(v.mean()) for k, v in values.items()}
    summary['empiricalNllExcessFraction'] = summary['nllExcess']/summary['nll'] if summary['nll'] > 0 else None
    summary['fivePercentNllReductionNotRuledOutByEmpiricalFloor'] = (
        summary['empiricalNllExcessFraction'] >= .05 if summary['empiricalNllExcessFraction'] is not None else None)
    return dict(**summary, support=dict(positions=len(rows), recordings=len({r['clipId'] for r in rows}),
                children=len({r['speakerId'] for r in rows}), votes=counts.sum(0).tolist(),
                unanimousPositions=int((counts.max(1) == 5).sum()), mixedVotePositions=int((counts.max(1) < 5).sum())))


def calculate(plan):
    guards(plan)
    rows = read(plan['inputs']['cohort'])['rows']
    prior = read(plan['inputs']['results'])
    scalar = read(plan['inputs']['scalars'])
    expected = plan['rowIndices']
    require(expected == sorted(i for i, r in enumerate(rows) if 6 <= r['age'] <= 12 and r['legacyRowIndex'] is not None),
            'Original child population changed')
    chosen_rows = [rows[i] for i in expected]
    require(len({r['speakerId'] for r in chosen_rows}) == 52 and len({r['targetPhone'] for r in chosen_rows}) == 23
            and {r['age'] for r in chosen_rows} == set(range(6, 13)), 'Child/phone/age support changed')
    output = {}
    for seed in SEEDS:
        collected = {arm: {} for arm in ('candidate', 'freshHard', 'scalar')}
        folds = {}
        cells = [c for c in plan['cells'] if c['seed'] == seed]
        require(len(cells) == 25 and len({(c['speakerFold'], c['wordGroup']) for c in cells}) == 25, 'Incomplete cells')
        for cell in cells:
            for arm in collected:
                record = scalar[cell['id']] if arm == 'scalar' else read(plan['inputs']['prediction/'+cell['jobs'][arm]])
                value = record['prediction']
                require(value['rowIndices'] == cell['outerRows'], 'Outer order differs')
                for index, logs in zip(value['rowIndices'], value['logProbabilities'], strict=True):
                    require(index not in collected[arm], 'Duplicated outer position')
                    collected[arm][index] = logs
                    require(folds.setdefault(index, cell['speakerFold']) == cell['speakerFold'], 'Fold differs')
        require(all(sorted(v) == expected for v in collected.values()), 'Missing original rows')
        logs = {k: np.asarray([v[i] for i in expected]) for k, v in collected.items()}
        logs.update({k+'Mixture': np.logaddexp(logs[k], logs['scalar'])-np.log(2.) for k in ('candidate', 'freshHard')})
        axes = dict(fold=[folds[i] for i in expected], age=[r['age'] for r in chosen_rows],
                    phone=[r['targetPhone'] for r in chosen_rows], child=[r['speakerId'] for r in chosen_rows])
        groups = {'pooled': dict(all=np.ones(len(expected), dtype=bool))}
        groups.update({axis: {str(k): np.asarray(values) == k for k in sorted(set(values))} for axis, values in axes.items()})
        output[str(seed)] = {}
        for axis, masks in groups.items():
            output[str(seed)][axis] = {}
            for key, mask in masks.items():
                selected = [r for r, keep in zip(chosen_rows, mask, strict=True) if keep]
                arm_values = {arm: view(selected, v[mask]) for arm, v in logs.items()}
                require(all(v['support'] == arm_values['scalar']['support'] for v in arm_values.values()), 'Support differs')
                for arm, value in arm_values.items():
                    old = prior['seeds'][str(seed)]['pooled' if axis == 'pooled' else 'groups']
                    old = old if axis == 'pooled' else old[axis][key]
                    for metric in ('nll', 'brier'):
                        require(abs(value[metric]-old['metrics'][arm][metric]) <= TOL, 'Frozen metric differs')
                output[str(seed)][axis][key] = arm_values
        output[str(seed)]['equalPhoneMeans'] = {arm: {k: float(np.mean([v[arm][k] for v in output[str(seed)]['phone'].values()]))
                                                        for k in ('empiricalEntropy', 'nll', 'nllExcess', 'empiricalBrierFloor', 'brier', 'brierExcess')}
                                                    for arm in logs}
    guards(plan)
    return dict(complete=True, study=plan['study'], seeds=output, empiricalFloorOnly=True,
                populationIrreducibilityEstablished=False, acousticAchievabilityEstablished=False, **FLAGS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'calculate'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--sha256')
    parser.add_argument('--review', type=Path)
    args = parser.parse_args()
    if args.command == 'declare':
        value = declaration()
        args.out.mkdir(parents=True, exist_ok=False)
        write(args.out/'plan.json', value)
        print(json.dumps(binding(args.out/'plan.json')))
        return
    require(args.sha256 and args.review, 'Actual plan hash and independent review required')
    plan_pin = binding(args.out/'plan.json', args.sha256)
    plan = read(plan_pin)
    require(plan == declaration(), 'Actual declaration no longer reconstructs')
    review_pin = binding(args.review)
    review = read(review_pin)
    require(review.get('independent') is True and review.get('verdict') == 'clear'
            and not review.get('blockingFindings') and review.get('plan') == plan_pin
            and review.get('sourceReviewed') is True and review.get('actualDeclarationReviewed') is True
            and review.get('calculationAuthorized') is True, 'Independent actual-declaration review required')
    output, failure = args.out/'results.json', args.out/'failure.json'
    require(not output.exists() and not failure.exists(), 'Preserve prior outputs; no restart')
    try:
        result = calculate(plan)
        binding(plan_pin['path'], plan_pin['sha256'])
        binding(review_pin['path'], review_pin['sha256'])
        guards(plan)
        write(output, dict(result, plan=plan_pin, review=review_pin))
        print(json.dumps(binding(output)))
    except BaseException as error:
        write(failure, dict(complete=False, errorType=type(error).__name__, error=str(error),
                            traceback=traceback.format_exc(), restartAllowed=False, **FLAGS))
        raise


if __name__ == '__main__':
    main()
