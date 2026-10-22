"""Declared, label-free 20 dB sensitivity of two frozen lexical mixtures."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import torch
import multiphone_consistency_extension as cache
from multiphone_selection_audit import PHONES
from lexical_noise import core
from lexical_projection_mixture import study as parent

ROOT = parent.ROOT
BASE = parent.BASE
DIRECTORY = Path(__file__).resolve().parent
PROTOCOL = ROOT / 'docs/model/multiphone-lexical-noise-protocol.md'
PARENT = BASE / 'lexical-projection-mixture-v1'
PARENT_SHA = '0ea7bac5ed8dfa29da35622c21c7b1c94041520dde65e1ecfadcd75d56896a31'
PARENT_REPORT_SHA = 'ade1a17833eb84ef7c05c342c01a4acf4c6523d5f26b0e8636f0abaac6442d3c'
NOISE = ROOT / 'research/audio-head/outputs/multiphone-20260926/consistency-features-extension-v1/features/features.json'
NOISE_SHA = '70143aa6e39bed17d498046fe676a8888d4339e9fb4bc70bab8a0cd477c9b426'
FAMILIES = ('existingMixture', 'correctedMixture')
RECIPE = dict(condition='noise20db', snrDb=20, batchSize=64, threads=2, device='cpu',
              mixtureWeights=[.5, .5], sourceTrainingRegimes=['all-age', 'child-only'],
              pairedTVTieTolerance=1e-12, expectedRatingValues=[0, 1, 2], argmaxTies='first class',
              fit=False, transformedLabels=False, accuracyMeasured=False, promotionGate=False)
FLAGS = dict(authorTestRead=False, encoderInferencePerformed=False, trainingPerformed=False,
             labelsTransferred=False, noisySupervisedMetricsCalculated=False, clinicalUseEligible=False,
             learnerFeedbackEligible=False, promotionEligible=False, independentFinalValidation=False)
require = core.require
binding = parent.binding
read = parent.read
write = parent.write


def compatible(noise, pins, clean):
    require(noise['inputFiles']['cleanFeatureBinding'] == pins['featureBinding']
            and noise['cleanFeatureBindingSha256'] == noise['featureSourceBindingSha256'] == pins['featureBinding']['sha256'],
            'Clean feature binding differs')
    for key, old in [('original/localRecipe', 'feature/original/recipe'), ('original/phoneticRecipe', 'feature/recipe')]:
        require(noise['inputFiles'][key] == pins[old], 'Feature extraction recipe differs')
    require(noise['scalarFeatureNames'] == cache.original.local.SCALAR_NAMES
            and noise['rowIndices'] == sorted(clean['positions']) and len(noise['rows']) == len(noise['rowIndices']),
            'Feature row/order contract differs')
    original = read(pins['feature/headInput/report'])
    originals = {r['rowIndex']: r for r in original['rows']}
    for r in noise['rows']:
        require(all(r[k] == originals[r['rowIndex']][k] for k in cache.original.IDENTITY), 'Canonical feature identity differs')


def inputs():
    prior, pp = parent.load_plan(PARENT / 'plan.json', PARENT_SHA)
    nr, nt, ns, npins = cache.validate_features(NOISE, NOISE_SHA)
    _, _, clean = parent.mixture.baseline.inputs()
    compatible(nr, prior['inputs'], clean)
    pins = dict(prior['inputs'], parentPlan=pp, parentReport=binding(PARENT / 'report.json', PARENT_REPORT_SHA),
                noiseReport=binding(NOISE, NOISE_SHA), noiseProtocol=binding(PROTOCOL))
    pins.update({'noise/' + k: v for k, v in npins.items()})
    for p in sorted(DIRECTORY.glob('*.py')):
        pins['noiseSource/' + p.name] = binding(p)
    cp = read(pins['correctedPlan'])
    source_jobs = {j['id']: j for j in cp['jobs']}
    corrections = {r['jobId']: r for r in read(pins['correctedRefit'])['runs']}
    baseline_outer = read(pins['baselineOuter'])
    scalars = {r['jobId']: r for r in read(baseline_outer['refitFreeze'])['runs']}
    jobs = []
    for old in prior['jobs']:
        source = source_jobs[old['projectionJobId']]
        assets = dict(scalarCheckpoint=old['scalarCheckpoint'], scalarConfig=scalars[old['scalarJobId']]['artifacts']['config.json'],
                      pcaCheckpoint=source['sourceRefit']['checkpoint'], pcaConfig=source['sourceRefit']['config'],
                      transform=source['sourceRefit']['transform'], correctionCheckpoint=old['projectionCheckpoint'],
                      correctionConfig=corrections[old['projectionJobId']]['artifacts']['config.json'])
        job = dict(old, assets=assets, pcaPrediction=source['sourceOuter'])
        for key, pin in assets.items():
            pins['head/' + old['id'] + '/' + key] = binding(pin['path'], pin['sha256'])
        jobs.append(job)
    parent.mixture.files.guard(pins)
    data = dict(clean=clean, noisyTarget=nt, noisyScalars=ns, positions={i: k for k, i in enumerate(nr['rowIndices'])})
    require(data['positions'] == clean['positions'], 'Noisy array offsets differ')
    return pins, jobs, data


def plan_value(pins, jobs):
    return dict(inputs=pins, jobs=jobs, recipe=RECIPE, **FLAGS, headInferencePerformed=False,
                runtime=dict(python=sys.version, numpy=np.__version__, torch=torch.__version__, executable=binding(sys.executable)))


def declare(output):
    require(not output.exists() and output.resolve().is_relative_to(BASE), 'Fresh ignored output required')
    pins, jobs, _ = inputs()
    output.mkdir(parents=True, mode=0o700)
    write(output / 'plan.json', plan_value(pins, jobs))
    return binding(output / 'plan.json')


def load_plan(path, sha):
    pp = binding(path, sha)
    plan = read(pp)
    pins, jobs, data = inputs()
    require(plan == plan_value(pins, jobs), 'Noise declaration changed')
    return plan, pp, data


def loaded_heads(job):
    a = job['assets']
    for pin in a.values():
        binding(pin['path'], pin['sha256'])
    tensors = {k: torch.load(a[k]['path'], map_location='cpu', weights_only=True)
               for k in ('scalarCheckpoint', 'pcaCheckpoint', 'transform', 'correctionCheckpoint')}
    for checkpoint, cfg in [('scalarCheckpoint', 'scalarConfig'), ('pcaCheckpoint', 'pcaConfig'), ('correctionCheckpoint', 'correctionConfig')]:
        require(tensors[checkpoint]['configSha256'] == a[cfg]['sha256'], 'Checkpoint configuration differs')
    pc, cc = read(a['pcaConfig']), read(a['correctionConfig'])
    require(tensors['pcaCheckpoint']['transformSha256'] == a['transform']['sha256'] and pc['transform'] == a['transform']
            and tensors['transform']['fitRows'] == pc['fitRows'] == cc['fitRows'], 'PCA fitting lineage differs')
    source = dict(checkpoint=a['pcaCheckpoint'], config=a['pcaConfig'], transform=a['transform'])
    require(cc['sourceBindings'] == tensors['correctionCheckpoint']['sourceBindings'] == source
            and all(torch.equal(tensors['correctionCheckpoint'][k], tensors['pcaCheckpoint'][k]) for k in ('mean', 'std')),
            'Correction source differs')
    return tensors


def predictions(job, data, noisy=False):
    states = loaded_heads(job)
    target = data['noisyTarget'] if noisy else data['clean']['target']
    scalars = data['noisyScalars'] if noisy else data['clean']['scalars']
    ids = job['outerRows']
    offsets = [data['positions'][i] for i in ids]
    phones = [data['clean']['cohort']['rows'][i]['targetId'] for i in ids]
    scalar = core.predict(states['scalarCheckpoint'], target, scalars, offsets, phones)
    pca = core.predict(states['pcaCheckpoint'], target, scalars, offsets, phones, states['transform'])
    corrected = core.predict(states['pcaCheckpoint'], target, scalars, offsets, phones,
                             states['transform'], states['correctionCheckpoint']['delta'])
    return dict(scalar=scalar, pca=pca, corrected=corrected,
                existingMixture=core.average(scalar, pca), correctedMixture=core.average(scalar, corrected))


def check_clean(job, values, references):
    for family, key in [('scalar', 'scalarPrediction'), ('pca', 'pcaPrediction'), ('corrected', 'projectionPrediction')]:
        source = read(job[key])['prediction']
        require(source['rowIndices'] == job['outerRows']
                and values[family] == {k: source[k] for k in ('probabilities', 'logProbabilities', 'rawProbabilities')},
                'Clean component replay differs')
    for family, report in references.items():
        cell = next(c for c in report['models'][job['regime']]['cells']
                    if c['speakerFold'] == job['speakerFold'] and c['wordGroup'] == job['wordGroup'])
        require(cell['rowIndices'] == job['outerRows'] and values[family] ==
                {k: cell['prediction'][k] for k in ('probabilities', 'logProbabilities')}, 'Clean mixture replay differs')


def checked_freeze(plan, pp, path, sha, phase):
    fp = binding(path, sha)
    frozen = read(fp)
    require(frozen['complete'] is True and frozen['plan'] == pp and frozen['phase'] == phase
            and [r['jobId'] for r in frozen['runs']] == [j['id'] for j in plan['jobs']]
            and all(frozen[k] == v for k, v in FLAGS.items()), 'Incomplete phase freeze')
    references = {k: read(plan['inputs'][v]) for k, v in [('existingMixture', 'mixtureReport'), ('correctedMixture', 'parentReport')]} if phase == 'anchors' else None
    for job, run in zip(plan['jobs'], frozen['runs'], strict=True):
        value = read(run['artifact'])
        require(value['plan'] == pp and value['jobId'] == job['id'] and value['rowIndices'] == job['outerRows']
                and value['phase'] == phase and value['assets'] == job['assets']
                and value['headInferencePerformed'] is True and all(value[k] == v for k, v in FLAGS.items()),
                'Prediction phase lineage differs')
        pred = value['predictions']
        require(set(pred) == {'scalar', 'pca', 'corrected', *FAMILIES}, 'Incomplete component inventory')
        for family, output in pred.items():
            p, _ = core.probabilities(output)
            require(len(p) == len(job['outerRows']), 'Wrong prediction population')
            if family not in FAMILIES:
                raw = np.asarray(output['rawProbabilities'])
                require(raw.shape == p.shape and np.isfinite(raw).all() and (raw >= 0).all()
                        and np.allclose(raw, p, atol=2e-7, rtol=2e-6), 'Invalid raw probabilities')
        require(core.average(pred['scalar'], pred['pca']) == pred['existingMixture']
                and core.average(pred['scalar'], pred['corrected']) == pred['correctedMixture'], 'Stored mixture differs')
        if phase == 'anchors':
            require(value['exactSourceParity'] is True and value['anchorFreeze'] is None, 'Missing clean parity')
            check_clean(job, pred, references)
    return frozen, fp


def execute(path, sha, phase, anchor_path=None, anchor_sha=None):
    plan, pp, data = load_plan(path, sha)
    root = Path(path).resolve().parent
    anchor_pin = None
    if phase == 'noise':
        _, anchor_pin = checked_freeze(plan, pp, anchor_path, anchor_sha, 'anchors')
    else:
        require(phase == 'anchors', 'Unknown inference phase')
    write(root / (phase + '-started.json'), dict(plan=pp, anchorFreeze=anchor_pin, **FLAGS))
    references = {k: read(plan['inputs'][v]) for k, v in [('existingMixture', 'mixtureReport'), ('correctedMixture', 'parentReport')]}
    runs = []
    try:
        for job in plan['jobs']:
            values = predictions(job, data, noisy=phase == 'noise')
            if phase == 'anchors':
                check_clean(job, values, references)
            value = dict(plan=pp, jobId=job['id'], phase=phase, rowIndices=job['outerRows'], predictions=values,
                         assets=job['assets'], anchorFreeze=anchor_pin, exactSourceParity=phase == 'anchors',
                         headInferencePerformed=True, **FLAGS)
            dest = root / phase / (job['id'] + '.json')
            dest.parent.mkdir(exist_ok=True)
            write(dest, value)
            runs.append(dict(jobId=job['id'], artifact=binding(dest)))
            print(json.dumps(dict(phase=phase, completed=job['id'])), flush=True)
        parent.mixture.files.guard(plan['inputs'])
        dest = root / (phase + '-freeze.json')
        write(dest, dict(plan=pp, phase=phase, complete=True, runs=runs, anchorFreeze=anchor_pin, **FLAGS))
        return binding(dest)
    except Exception as error:
        write(root / (phase + '-failure.json'), dict(error=str(error), completedJobs=[r['jobId'] for r in runs], **FLAGS))
        raise


def subset(moves, ix):
    return {k: [v[i] for i in ix] for k, v in moves.items()}


def summary(moves, rows, ix):
    selected = {k: subset(v, ix) for k, v in moves.items()}
    return dict(models={k: core.summarize(v, [rows[i] for i in ix]) for k, v in selected.items()},
                paired=core.compare(selected['correctedMixture'], selected['existingMixture']))


def population(moves, rows):
    groups = dict(allAges=list(range(len(rows))), ages6to12=[i for i, r in enumerate(rows) if 6 <= r['age'] <= 12],
                  ages13plus=[i for i, r in enumerate(rows) if r['age'] >= 13])
    return {age: dict(overall=summary(moves, rows, ix),
                     perPhone={phone: summary(moves, rows, [i for i in ix if rows[i]['targetPhone'] == phone]) for phone in PHONES})
            for age, ix in groups.items()}


def calculate(plan, pp, noise_path, noise_sha):
    noisy, npin = checked_freeze(plan, pp, noise_path, noise_sha, 'noise')
    clean, cpin = checked_freeze(plan, pp, noisy['anchorFreeze']['path'], noisy['anchorFreeze']['sha256'], 'anchors')
    rows = read(plan['inputs']['cohort'])['rows']
    jobs = {j['id']: j for j in plan['jobs']}
    merged = {regime: {} for regime in ('all-age', 'child-only')}
    cells = {regime: [] for regime in merged}
    for c, n in zip(clean['runs'], noisy['runs'], strict=True):
        job = jobs[c['jobId']]
        cv, nv = read(c['artifact']), read(n['artifact'])
        require(nv['anchorFreeze'] == cpin and c['jobId'] == n['jobId'], 'Clean/noisy pairing differs')
        moves = {f: core.movement(cv['predictions'][f], nv['predictions'][f]) for f in FAMILIES}
        rr = [rows[i] for i in job['outerRows']]
        cells[job['regime']].append(dict(jobId=job['id'], speakerFold=job['speakerFold'], wordGroup=job['wordGroup'],
                                        rowIndices=job['outerRows'], anchor=c['artifact'], noise=n['artifact'], summary=population(moves, rr)))
        for k, i in enumerate(job['outerRows']):
            require(i not in merged[job['regime']], 'Duplicate outer row')
            merged[job['regime']][i] = ({f: {key: val[k] for key, val in v.items()} for f, v in moves.items()},
                                        job['speakerFold'], job['wordGroup'])
    models = {}
    eligible = [i for i, r in enumerate(rows) if r['trainingEligible']]
    rr = [rows[i] for i in eligible]
    for regime, mapping in merged.items():
        require(sorted(mapping) == eligible and len(cells[regime]) == 25, 'Incomplete population')
        moves = {f: {k: [mapping[i][0][f][k] for i in eligible] for k in mapping[eligible[0]][0][f]} for f in FAMILIES}
        folds = [mapping[i][1] for i in eligible]
        groups = [mapping[i][2] for i in eligible]
        def part(ix):
            return dict(rowIndices=[eligible[i] for i in ix], summary=population({f: subset(v, ix) for f, v in moves.items()}, [rr[i] for i in ix]))
        children = sorted({r['speakerId'] for r in rr if 6 <= r['age'] <= 12})
        models[regime] = dict(rowIndices=eligible, rowFolds=folds, rowWordGroups=groups, movements=moves,
            pooled=population(moves, rr), cells=cells[regime],
            speakerFolds={str(f): part([i for i, v in enumerate(folds) if v == f]) for f in range(5)},
            wordGroups={str(g): part([i for i, v in enumerate(groups) if v == g]) for g in range(5)},
            children={child: part([i for i, r in enumerate(rr) if r['speakerId'] == child]) for child in children})
    parent.mixture.files.guard(plan['inputs'])
    return dict(complete=True, plan=pp, anchorFreeze=cpin, noiseFreeze=npin, models=models, recipe=RECIPE, **FLAGS)


def audit(path, sha, noise_path, noise_sha, verify=False):
    plan, pp, _ = load_plan(path, sha)
    root = Path(path).resolve().parent
    if not verify:
        write(root / 'audit-started.json', dict(plan=pp, **FLAGS))
    value = calculate(plan, pp, noise_path, noise_sha)
    if verify:
        require(read(binding(root / 'report.json')) == value, 'Offline sensitivity report differs')
        return dict(verified=True, report=binding(root / 'report.json'))
    write(root / 'report.json', value)
    return binding(root / 'report.json')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('declare', 'anchors', 'noise', 'audit', 'verify'))
    p.add_argument('--plan', type=Path)
    p.add_argument('--plan-sha256')
    p.add_argument('--output', type=Path)
    p.add_argument('--freeze', type=Path)
    p.add_argument('--freeze-sha256')
    a = p.parse_args()
    if a.command == 'declare':
        result = declare(a.output)
    elif a.command in ('anchors', 'noise'):
        result = execute(a.plan, a.plan_sha256, a.command, a.freeze, a.freeze_sha256)
    else:
        result = audit(a.plan, a.plan_sha256, a.freeze, a.freeze_sha256, a.command == 'verify')
    print(json.dumps(result), flush=True)
