"""Declared paired whole-child uncertainty for all expanded-fitting contrasts."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import numpy as np
from lexical_uncertainty import core
from lexical_expanded_uncertainty import analysis

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'research/audio-head/outputs/multiphone-20260927'
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = ROOT / 'docs/model/multiphone-lexical-expanded-uncertainty-protocol.md'
PARENT_SHA = '8acf9c21ac69ef8c1aec9518ab4a8a75b27049322d6d8fe7733a5373fb97154c'
REPORT_SHA = 'bfc6329c98a212c1b93fa765cc4c3b4419adb30b981f04999d5d138f1f6eea6f'
CORE_SHA = '4457a068ded18bda1c1d276dc89812ca351fad858ad36a43a0d52caa77b19ad3'
AUDIT_SHAS = {'inner-result.json': '5b812068b119ac300bc774f7b17e3b52bb26729c8ce7c55f206573f5845fe5da',
    'outer-refit-result.json': 'a02e13ae99e6254d2d4c8725c531b8264f29d6c21c5f0be012a8c624f36ed9f9',
    'outer-result.json': 'c0c3a0077d378f526ad2ef9383d4c3cef05b90b83c2617830b56fc17d60e0ac0',
    'report-result.json': '6b52c64767b0f72942c0b31d1b6881e8bcf4669759989523ff4a29a8b851c329'}
REGIMES = ('all-age', 'child-only')
CONTRASTS = ('scalars', 'pca16-scalars', 'equal-mixture', 'mixtureVsCorrectedMixture')
ENDPOINTS = ('NLL', 'Brier', 'macroNLL', 'rating0AP', 'below2AP')
RECIPE = dict(replicates=2000, seed=20260927, generator='PCG64', samplingUnit='whole child',
    strata='original five speaker folds', quantiles=[.025, .975], quantileMethod='linear',
    contrasts=list(CONTRASTS), regimes=list(REGIMES), sharedWeights=True,
    macro='fixed 23 phones; null if any absent', perPhoneIntervals='NLL',
    influence='all five folds and all pooled leave-one-child-out NLL contrasts')
FLAGS = dict(trainingPerformed=False, modelInferencePerformed=False, authorTestRead=False,
    audioDecoded=False, encoderInferencePerformed=False, independentFinalValidation=False,
    clinicalUseEligible=False, promotionEligible=False, learnerFeedbackEligible=False,
    learnerJudgmentsEnabled=False, hyperparameterSearchPerformed=False)


def require(ok, message):
    if not ok: raise ValueError(message)


def binding(path, expected=None):
    path = Path(path).resolve()
    with path.open('rb') as stream: sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(expected is None or sha == expected, 'Changed input: '+str(path))
    return dict(path=str(path), sha256=sha)


def read(pin):
    binding(pin['path'], pin['sha256'])
    return json.loads(Path(pin['path']).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def guard(pins):
    for pin in pins.values(): binding(pin['path'], pin['sha256'])


def inputs():
    pp = binding(BASE/'lexical-expanded-heads-v1/plan.json', PARENT_SHA)
    pins = dict(read(pp)['inputs'], expandedHeadsPlan=pp,
        expandedHeadsReport=binding(BASE/'lexical-expanded-heads-audit-v1/report.json', REPORT_SHA),
        pairedCore=binding(ROOT/'research/audio-head/lexical_uncertainty/core.py', CORE_SHA),
        expandedUncertaintyProtocol=binding(PROTOCOL))
    folder = ROOT/'work/lexical-expanded-heads-audit-20260927'
    for name, sha in AUDIT_SHAS.items():
        pin = binding(folder/name, sha); audit = read(pin)
        require(audit['status'] == 'passed', 'Incomplete parent audit')
        pins['expandedHeadAudit/'+name] = pin
        if 'sourceBindings' in audit:
            for source, digest in audit['sourceBindings'].items():
                pins['expandedHeadAuditSource/'+source] = binding(source, digest)
        elif 'auditorSource' in audit:
            for field in ('auditorSource', 'helperSource'):
                source = audit[field]; pins['expandedHeadAuditSource/'+source['path']] = source
        else:
            pins['expandedHeadAuditSource/states.py'] = binding(folder/'states.py', audit['auditorSourceSha256'])
    for path in sorted(DIRECTORY.glob('*.py')): pins['expandedUncertaintySource/'+path.name] = binding(path)
    guard(pins)
    return pins


def plan_value(pins):
    return dict(inputs=pins, recipe=RECIPE, **FLAGS, resamplingPerformed=False,
        runtime=dict(python=sys.version, numpy=np.__version__, platform=platform.platform(), executable=binding(sys.executable)))


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(BASE), 'Fresh ignored output required')
    plan = plan_value(inputs())
    # Validate matched metadata and complete prediction arrays, without computing
    # endpoints or sampling. Declaration never calls analysis/core preparation.
    checked_inputs(plan)
    output.mkdir(parents=True, mode=0o700)
    write(output/'plan.json', plan)
    return binding(output/'plan.json')


def load_plan(path, sha):
    pin = binding(path, sha); plan = read(pin)
    require(plan == plan_value(inputs()), 'Declaration no longer matches')
    return plan, pin


def checked_view(value, eligible, folds, groups):
    require(value['rowIndices'] == eligible and value['rowFolds'] == folds
            and value['rowWordGroups'] == groups, 'Reference row/fold/word identity differs')
    p, logs = (np.asarray(value[k], dtype=np.float64) for k in ('probabilities', 'logProbabilities'))
    require(p.shape == logs.shape == (len(eligible), 3) and np.isfinite(p).all()
        and np.isfinite(logs).all() and (p >= 0).all() and (p <= 1).all() and (logs <= 0).all()
        and np.allclose(p.sum(1), 1, atol=1e-12, rtol=0)
        and np.allclose(np.exp(logs), p, atol=0, rtol=1e-12), 'Invalid stable predictions')
    require([(v['speakerFold'], v['wordGroup']) for v in value['cells']]
            == [(s, w) for s in range(5) for w in range(5)], 'Incomplete cell matrix')
    for cell in value['cells']:
        require(cell['rowIndices'] == [i for i, f, g in zip(eligible, folds, groups, strict=True)
            if (f, g) == (cell['speakerFold'], cell['wordGroup'])], 'Cell row membership differs')
    require([v['speakerFold'] for v in value['speakerFolds']] == list(range(5)), 'Incomplete fold matrix')
    for fold in value['speakerFolds']:
        require(fold['rowIndices'] == [i for i, f in zip(eligible, folds, strict=True) if f == fold['speakerFold']],
                'Fold row membership differs')
    return dict(probabilities=p, logProbabilities=logs)


def checked_inputs(plan):
    pins = plan['inputs']; parent = read(pins['expandedHeadsPlan']); expanded = read(pins['expandedHeadsReport'])
    require(expanded['complete'] is True and expanded['plan'] == pins['expandedHeadsPlan'], 'Expanded report lineage')
    require(all(expanded[k] is False for k in FLAGS if k in expanded), 'Expanded report scope')
    cohorts = read(pins['originalCohort'])['rows']; rows = read(pins['cohort'])['rows']
    eligible = [i for i, r in enumerate(cohorts) if r['trainingEligible']]
    legacy = {r['legacyRowIndex']: i for i, r in enumerate(rows) if r['legacyRowIndex'] is not None}
    require(len(legacy) == 14837 and sorted(legacy) == eligible, 'Original population coverage')
    require(sum(r['legacyRowIndex'] is not None for r in rows) == len(legacy), 'Duplicate original mapping')
    for old, new in legacy.items():
        require(rows[new]['legacyRowId'] == cohorts[old]['id'] and all(rows[new][k] == cohorts[old][k]
            for k in ('clipId','speakerId','age','targetPhone','targetWord','wordIndex','phoneIndex','raterCounts')), 'Original label/identity join')
    cell_by_row = {}
    for job in parent['jobs']:
        if job['family'] != 'scalars' or job['regime'] != 'all-age': continue
        for i in job['outerRows']:
            old = rows[i]['legacyRowIndex']
            if old is not None:
                require(old not in cell_by_row, 'Duplicate original outer membership')
                cell_by_row[old] = (job['speakerFold'], job['wordGroup'])
    require(sorted(cell_by_row) == eligible, 'Missing original outer membership')
    folds = [cell_by_row[i][0] for i in eligible]; groups = [cell_by_row[i][1] for i in eligible]
    keep = [k for k, i in enumerate(eligible) if 6 <= cohorts[i]['age'] <= 12]
    child_rows = [cohorts[eligible[k]] for k in keep]
    require(len(child_rows) == 5654 and len({r['speakerId'] for r in child_rows}) == 52
        and set(r['targetPhone'] for r in child_rows) == set(analysis.PHONES), 'Child population differs')
    child_folds = [folds[k] for k in keep]
    require(set(child_folds) == set(range(5)), 'Missing child speaker fold')
    speaker_folds = {}
    for row, fold in zip(child_rows, child_folds, strict=True):
        require(speaker_folds.setdefault(row['speakerId'], fold) == fold, 'Child crosses speaker folds')
    references = {}
    for name in ('scalar', 'compact', 'mixture', 'corrected'):
        reference = read(pins[name+'ReferenceReport'])
        require(reference['complete'] is True and reference['plan'] == pins[name+'ReferencePlan'], 'Historical lineage')
        references[name] = reference
    comparisons = {}
    for regime in REGIMES:
        for contrast in CONTRASTS:
            family = 'equal-mixture' if contrast == 'mixtureVsCorrectedMixture' else contrast
            candidate = expanded['models'][regime][family]['original']
            reference = {'scalars': references['scalar']['models'][regime]['scalars'],
                'pca16-scalars': references['compact']['models'][regime],
                'equal-mixture': references['mixture']['models'][regime],
                'mixtureVsCorrectedMixture': references['corrected']['models'][regime]}[contrast]
            pair = [checked_view(v, eligible, folds, groups) for v in (candidate, reference)]
            expected = expanded['comparisons'][regime]['secondary' if contrast == 'mixtureVsCorrectedMixture' else 'primary'][contrast]
            comparisons[regime+'/'+contrast] = dict(candidate={k: v[keep] for k, v in pair[0].items()},
                reference={k: v[keep] for k, v in pair[1].items()}, sourceComparison=expected)
    return dict(rows=child_rows, rowIndices=[eligible[k] for k in keep],
        folds=[folds[k] for k in keep], groups=[groups[k] for k in keep], comparisons=comparisons)


def calculate(plan, pin):
    data = checked_inputs(plan)
    sampling = core.speaker_weights([r['speakerId'] for r in data['rows']], data['folds'], RECIPE['replicates'], RECIPE['seed'])
    results = {}
    for name, pair in data['comparisons'].items():
        result = analysis.analyze(data['rows'], data['folds'], data['groups'], pair['candidate'], pair['reference'], sampling)
        for key in ENDPOINTS:
            delta = result['observed']['candidate'][key] - result['observed']['reference'][key]
            require(np.isclose(delta, pair['sourceComparison']['childDelta'][key], rtol=2e-11, atol=2e-12), 'Observed comparison differs')
        for fold, expected in enumerate(pair['sourceComparison']['speakerFoldChildDeltas']):
            require(np.isclose(result['influence']['speakerFolds'][str(fold)]['NLLDelta'], expected['NLL'],
                rtol=2e-11, atol=2e-12), 'Observed fold NLL differs')
        require(np.isclose(sum(v['additiveNLLContribution'] for v in result['influence']['speakerFolds'].values()),
            pair['sourceComparison']['childDelta']['NLL'], rtol=2e-11, atol=2e-12), 'Fold contributions do not sum to pooled NLL')
        result['originalConsistencyDecision'] = pair['sourceComparison']
        results[name] = result
        print(json.dumps(dict(completed=name)), flush=True)
    guard(plan['inputs'])
    return dict(complete=True, plan=pin, recipe=RECIPE, **FLAGS, resamplingPerformed=True,
        sampling=dict(speakerIds=sampling['speakerIds'], speakerFolds=sampling['speakerFolds'], weights=sampling['weights'].tolist(),
            rowIndices=data['rowIndices'], rowFolds=data['folds'], rowWordGroups=data['groups']), comparisons=results)


def run(path, sha, verify=False):
    plan, pin = load_plan(path, sha); folder = Path(path).resolve().parent
    if not verify: write(folder/'started.json', dict(plan=pin))
    try:
        result = calculate(plan, pin)
        if verify:
            require(read(binding(folder/'report.json')) == result, 'Offline reconstruction differs')
            return dict(verified=True, report=binding(folder/'report.json'))
        write(folder/'report.json', result)
        return binding(folder/'report.json')
    except Exception as error:
        if not verify: write(folder/'failure.json', dict(error=f'{type(error).__name__}: {error}'))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'run', 'verify'))
    parser.add_argument('--output', type=Path); parser.add_argument('--plan', type=Path); parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    require(args.output is not None if args.command == 'declare' else args.plan is not None and args.plan_sha256 is not None, 'Missing arguments')
    print(json.dumps(declare(args.output) if args.command == 'declare' else run(args.plan, args.plan_sha256, args.command == 'verify')), flush=True)
