"""Declare, fit and export the fixed full-child mixture; never report fit efficacy."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import platform
import tempfile
import shutil
import numpy as np
import torch
from lexical_heads import core as scalar
from lexical_compact import core as compact
import multiphone_models

ROOT = Path(__file__).resolve().parents[3]
HEAD = ROOT / 'research/audio-head'
BASE = HEAD / 'outputs/multiphone-20260927'
OLD = BASE / 'lexical-expanded-heads-v1'
PROTOCOL = ROOT / 'docs/model/ages-6-12-bundle-protocol.md'
PHONES = 'B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG'.split()
PLAN_SHA = '8acf9c21ac69ef8c1aec9518ab4a8a75b27049322d6d8fe7733a5373fb97154c'
INNER_SHA = '3afea90b57ebe5ab60f9cb5da3a4451e3f8e9a4c979edf9c87ad0d26dc873bf1'
FLAGS = dict(learnerFeedbackEligible=False, clinicalUseEligible=False, promotionEligible=False)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def pin(path):
    return dict(path=str(Path(path).resolve()), sha256=sha(path))


def read(pin_value):
    require(sha(pin_value['path']) == pin_value['sha256'], 'Input hash changed: '+pin_value['path'])
    return json.loads(Path(pin_value['path']).read_text())


def write(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def support(rows):
    return dict(positions=len(rows), children=len({r['speakerId'] for r in rows}),
                clips=len({r['clipId'] for r in rows}),
                votes=[sum(r['raterCounts'][k] for r in rows) for k in range(3)])


def declaration():
    prior = read(dict(path=str(OLD/'plan.json'), sha256=PLAN_SHA))
    inner = read(dict(path=str(OLD/'inner-freeze.json'), sha256=INNER_SHA))
    require(inner['complete'] and inner['phase'] == 'inner' and inner['plan']['sha256'] == PLAN_SHA,
            'Expected completed fixed inner study')
    cohort = read(prior['inputs']['cohort'])
    features = read(prior['inputs']['featureReport'])
    require(features['complete'] and features['inputs']['cohort'] == prior['inputs']['cohort'],
            'Feature cohort mismatch')
    rows = cohort['rows']
    fit = [i for i,r in enumerate(rows) if type(r['age']) is int and 6 <= r['age'] <= 12]
    chosen = [rows[i] for i in fit]
    require(len(fit) == 9891 and len({r['speakerId'] for r in chosen}) == 52, 'Child population changed')
    require({r['targetPhone'] for r in chosen} == set(PHONES), 'Missing fitting phone')
    require(all(r['trainingEligible'] is True for r in chosen), 'Ineligible fitting row')
    histories, epochs = {}, {}
    for family in ('scalars', 'pca16-scalars'):
        runs = [r for r in inner['runs'] if r['jobId'].startswith('child-only-'+family+'-')]
        require({r['jobId'] for r in runs} == {f'child-only-{family}-s{s}-w{w}' for s in range(5) for w in range(5)},
                'Incomplete historical selection cells')
        entries = []
        for run in runs:
            report = read(run['artifacts']['report.json'])
            require(report['complete'] and report['phase'] == 'inner'
                    and type(run['selectedEpoch']) is int and 1 <= run['selectedEpoch'] <= 100
                    and report['bestEpoch'] == run['selectedEpoch'], 'Invalid inner selected epoch')
            entries.append(dict(jobId=run['jobId'], epoch=run['selectedEpoch'], report=run['artifacts']['report.json']))
        histories[family] = entries
        epochs[family] = sorted(x['epoch'] for x in entries)[12]
    sources = {str(p): sha(p) for p in Path(__file__).parent.glob('*.py')}
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            p = Path(filename).resolve()
            if p.is_relative_to(HEAD) and p.suffix == '.py' and '.venv' not in p.parts:
                sources[str(p)] = sha(p)
    source_inputs = dict(cohort=prior['inputs']['cohort'], featureReport=prior['inputs']['featureReport'],
                         target=features['matrices']['target'], scalars=features['inputs']['scalars'],
                         originalPlan=dict(path=str(OLD/'plan.json'),sha256=PLAN_SHA),
                         innerFreeze=dict(path=str(OLD/'inner-freeze.json'),sha256=INNER_SHA), protocol=pin(PROTOCOL))
    return dict(schemaVersion=1, fitRows=fit, inputs=source_inputs, sourceBindings=sources,
                recipe=scalar.RECIPE, transformRecipe=compact.TRANSFORM_RECIPE, seed=7,
                epochRule='Median of 25 historical child-only inner-selected epochs per family',
                epochs=epochs, historicalSelections=histories, mixtureWeights=[.5,.5],
                runtime=dict(python=platform.python_version(),numpy=np.__version__,torch=torch.__version__,device="cpu"),
                ageRangeYears=[6,12], ageUpperExclusive=13, targetPhones=PHONES,
                support=support(chosen),
                supportByAge={str(age):support([r for r in chosen if r['age']==age]) for age in range(6,13)},
                supportByPhone={p:support([r for r in chosen if r['targetPhone']==p]) for p in PHONES},
                supportByAgeAndPhone={str(a):{p:support([r for r in chosen if r['age']==a and r['targetPhone']==p])
                                             for p in PHONES} for a in range(6,13)},
                efficacyEvaluated=False, authorTestRead=False, **FLAGS)


def check_plan(path, digest):
    plan = read(dict(path=str(path),sha256=digest))
    require(plan == declaration(), 'Declaration or implementation changed')
    for value in plan['inputs'].values():
        require(sha(value['path']) == value['sha256'], 'Changed input')
    return plan


def fit(path, digest, review_path):
    from ages_6_12_bundle.inference import load_bundle
    plan = check_plan(path, digest)
    review = json.loads(Path(review_path).read_text())
    require(review['status']=='clear' and not review['blockingFindings'] and review['planSha256']==digest,
            'Matching source review required')
    for source, expected in review['sourceBindings'].items():
        require(sha(source)==expected, 'Reviewed source changed')
    out = Path(path).resolve().parent
    require(not (out/'fit').exists() and not (out/'bundle').exists(), 'Fresh fitting output required')
    cohort = read(plan['inputs']['cohort'])
    target = np.load(plan['inputs']['target']['path'],allow_pickle=False)
    scalars = np.load(plan['inputs']['scalars']['path'],allow_pickle=False)
    require(target.shape==(len(cohort['rows']),1024) and scalars.shape==(len(cohort['rows']),13), 'Feature shape differs')
    data_bundle = dict(cohort=cohort,target=target,scalars=scalars,positions={i:i for i in range(len(target))})
    chosen = plan['fitRows']; checkpoints = {}; predictions = {}; projection = None
    for family, core, name in [('scalars',scalar,'scalar'),('pca16-scalars',compact,'compact')]:
        print(json.dumps(dict(stage='fitting',family=family,epochs=plan['epochs'][family],rows=len(chosen))),flush=True)
        data = core.prepare(data_bundle,family,chosen)
        report = core.train(data,[],out/'fit'/name,dict(exportPlanSha256=digest),epochs=plan['epochs'][family])
        state = torch.load(out/'fit'/name/'best.pt',map_location='cpu',weights_only=True)
        require(state['epoch']==plan['epochs'][family] and report['totalUpdates']==state['epoch']*((len(chosen)+63)//64),
                'Incomplete fitting updates')
        checkpoints[name] = dict(model=state['model'],mean=state['mean'],std=state['std'],epochs=state['epoch'])
        prediction = core.replay(out/'fit'/name,data,chosen)
        # Scores returned by legacy replay are deliberately not published as efficacy.
        predictions[name] = np.asarray(prediction['logProbabilities'],dtype=np.float64)
        if name=='compact':
            projection = {k:data['transform'][k] for k in ('center','basis')}
    bundle = out/'bundle'; bundle.mkdir()
    for name,state in checkpoints.items():
        with (bundle/f'{name}.pt').open('xb') as f: torch.save(state,f)
    with (bundle/'projection.pt').open('xb') as f: torch.save(projection,f)
    provenance = dict(plan=plan,planSha256=digest,fitReports={name:pin(out/'fit'/name/'report.json') for name in checkpoints},
                      featureContract='1024 pinned raw target-window features then 13 ordered CTC scalars',
                      scalarColumns=plan['inputs']['scalars']['columns'],
                      independentPerformanceScore=None, **FLAGS)
    write(bundle/'provenance.json',provenance)
    manifest = dict(schemaVersion=1,kind='cadence-expanded-child-mixture',ageRangeYears=[6,12],
                    featureWidth=1037,targetPhones=PHONES,mixtureWeights=[.5,.5],
                    modelSourceSha256=sha(multiphone_models.__file__),
                    files={n:sha(bundle/n) for n in ('scalar.pt','compact.pt','projection.pt','provenance.json')},**FLAGS)
    write(bundle/'manifest.json',manifest)
    expected = np.logaddexp(predictions['scalar'],predictions['compact'])-np.log(2.)
    raw = np.concatenate((target[chosen],scalars[chosen]),axis=1)
    ids = np.asarray([cohort['rows'][i]['targetId'] for i in chosen],dtype=np.int64)
    age = np.asarray([cohort['rows'][i]['age'] for i in chosen])
    loaded = load_bundle(bundle,sha(bundle/'manifest.json'))
    # Age parameter is a caller scope guard, not a model feature. All source rows
    # are already verified inside scope; score in one batch to preserve row order.
    actual = loaded.predict(raw,ids,age_years=6)
    dp=float(np.abs(actual['probabilities']-np.exp(expected)).max())
    dl=float(np.abs(actual['logProbabilities']-expected).max())
    require(dp<=1e-7 and dl<=1e-6,'Export differs from established core')
    np.savez(out/'parity.npz',rowIndices=np.asarray(chosen),ages=age,targetIds=ids,
             expectedLogProbabilities=expected,actualLogProbabilities=actual['logProbabilities'])
    with tempfile.TemporaryDirectory() as temporary:
        moved=Path(temporary)/'relocated';shutil.copytree(bundle,moved)
        again=load_bundle(moved,sha(bundle/'manifest.json')).predict(raw[:65],ids[:65],age_years=12.5)
        same=loaded.predict(raw[:65],ids[:65],age_years=12.5)
        require(np.array_equal(again['logProbabilities'],same['logProbabilities']),'Relocation changed predictions')
    result=dict(complete=True,planSha256=digest,bundleManifest=pin(bundle/'manifest.json'),rowsCompared=len(chosen),
                maxAbsProbabilityDifference=dp,maxAbsLogProbabilityDifference=dl,relocationExact=True,
                fittingSupport=plan['support'],epochs=plan['epochs'],parityArtifact=pin(out/'parity.npz'),
                efficacyEvaluated=False,independentPerformanceScore=None,**FLAGS)
    write(out/'export-report.json',result)
    print(json.dumps(result),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('declare');d.add_argument('--output',type=Path,required=True)
    f=sub.add_parser('fit');f.add_argument('--plan',type=Path,required=True);f.add_argument('--sha256',required=True);f.add_argument('--review',type=Path,required=True)
    args=p.parse_args()
    if args.command=='declare':
        require(not args.output.exists() and args.output.resolve().is_relative_to(BASE),'Fresh research output required')
        plan=declaration();args.output.mkdir(parents=True);write(args.output/'plan.json',plan)
        print(json.dumps(pin(args.output/'plan.json')))
    else: fit(args.plan,args.sha256,args.review)


if __name__=='__main__':main()
