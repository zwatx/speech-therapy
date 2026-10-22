"""Fixed metadata-selected raw-WAV parity cases, with offline artifact replay."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import numpy as np
import torch
from position_inference import audio as a

BASE = a.HERE/'outputs/multiphone-20260927'
PROTOCOL = a.HERE/'../../docs/model/multiphone-position-audio-protocol.md'
VARIANTS = ('unweighted-all-age', 'unweighted-child-only', 'weighted-all-age', 'weighted-child-only')
FEATURE_SHA = '80a0dd901f026deebd74ea9fb66d234f14e80ca44d03ab8c0816e0d8494341be'
SCALAR_SHA = '5b2828cec062b50c575334c8f4182e1d7a712c869bf6ae90867417a9eb5698b9'
SNAPSHOT = a.HERE/'outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4'


def read(pin):
    return a.read_bound_json(pin['path'], pin['sha256'])[0]


def choose(cohort):
    grouped = defaultdict(list)
    for index, row in enumerate(cohort['rows']): grouped[row['clipId']].append((index, row))
    clips = sorted(cohort['clips'], key=lambda c: c['id'])
    def predicates(clip):
        rows = [r for _, r in grouped[clip['id']]]
        same = any(x['targetPhone'] == y['targetPhone'] and x['wordIndex'] == y['wordIndex']
                   for i,x in enumerate(rows) for y in rows[i+1:])
        across = any(x['targetPhone'] == y['targetPhone'] and x['wordIndex'] != y['wordIndex']
                     for i,x in enumerate(rows) for y in rows[i+1:])
        adjacent = any(x['targetPhone'] == y['targetPhone'] and x['canonicalIndex']+1 == y['canonicalIndex']
                       for x,y in zip(rows, rows[1:]))
        return dict(sameWordRepeat=same, acrossWordRepeat=across, adjacentEqualConsonants=adjacent,
                    allAdded=all(r['legacyRowIndex'] is None for r in rows),
                    allOriginal=all(r['legacyRowIndex'] is not None for r in rows))
    selected, reasons = [], defaultdict(list)
    for criterion in ('sameWordRepeat', 'acrossWordRepeat', 'adjacentEqualConsonants', 'allAdded', 'allOriginal'):
        clip = next(c for c in clips if 6 <= c['age'] <= 12 and predicates(c)[criterion])
        if clip not in selected: selected.append(clip)
        reasons[clip['id']].append(criterion)
    remaining = set(a.inference.TARGETS[:23])
    for c in selected: remaining -= {r['targetPhone'] for _,r in grouped[c['id']]}
    while remaining:
        candidates = [c for c in clips if 6 <= c['age'] <= 12 and c not in selected]
        clip = min(candidates, key=lambda c: (-len(remaining & {r['targetPhone'] for _,r in grouped[c['id']]}), c['id']))
        gain = remaining & {r['targetPhone'] for _,r in grouped[clip['id']]}
        a.require(gain, 'Child clips cannot cover all supported phones')
        selected.append(clip); reasons[clip['id']].append('phoneCoverage:'+','.join(sorted(gain))); remaining -= gain
    cases=[]
    for number,c in enumerate(selected):
        rows=grouped[c['id']]
        if number % 2: rows=list(reversed(rows))
        prompt=dict(schemaVersion=2,language='en',transcript=' '.join(w['text'] for w in c['words']),
                    words=[dict(text=w['text'],phones=w['phones']) for w in c['words']],
                    targets=[{k:r[k] for k in ('id','wordIndex','phoneIndex','targetPhone')} for _,r in rows])
        cases.append(dict(clipId=c['id'],rowIndices=[i for i,_ in rows],prompt=prompt,variant=VARIANTS[number%4],
                          audio=a.binding(c['audioPath'],c['audioSha256']),reasons=reasons[c['id']],properties=predicates(c)))
    a.require({c['variant'] for c in cases} == set(VARIANTS), 'Cases must cover all four bundle variants')
    return cases


def declare(output):
    a.require(output.resolve().is_relative_to(a.HERE/'outputs') and not output.exists(), 'Fresh ignored output required')
    pins={'features':a.binding(BASE/'position-phonetic-v1/report.json',FEATURE_SHA),
          'scalars':a.binding(BASE/'position-scalars-v1/report.json',SCALAR_SHA),
          'contract':a.binding(a.CONTRACT),'protocol':a.binding(PROTOCOL),
          'python':a.binding(sys.executable),'node':a.binding(shutil.which('node'))}
    features,scalars=read(pins['features']),read(pins['scalars'])
    pins['cohort']=features['inputs']['cohort'];pins['matrix']=features['matrices']['combined']
    cohort=read(pins['cohort']);cases=choose(cohort)
    for path in sorted(a.DIRECTORY.glob('*.py')):pins['source/'+path.name]=a.binding(path)
    _,_,_,_,dependencies=a.load_contract(a.CONTRACT,pins['contract']['sha256'],SNAPSHOT)
    pins.update({'runtime/'+k:v for k,v in dependencies.items()})
    bundles={}
    for variant in VARIANTS:
        directory=a.HERE/'outputs/multiphone-20260926/phonetic-final'/variant
        pin=a.binding(directory/'manifest.json');manifest=read(pin)
        bundles[variant]=dict(directory=str(directory),manifest=pin)
        pins['bundle/'+variant+'/manifest']=pin
        for name,sha in manifest['filesSha256'].items():pins['bundle/'+variant+'/'+name]=a.binding(directory/name,sha)
    for case in cases:
        cid=case['clipId'];pins['audio/'+cid]=case['audio']
        pins['geometry/'+cid]=scalars['clipArtifacts'][cid];pins['posterior/'+cid]=scalars['posteriorBindings'][cid]
    a.guard(pins);output.mkdir(mode=0o700,parents=True)
    plan=dict(inputs=pins,cases=cases,bundles=bundles,snapshot=str(SNAPSHOT),researchOnly=True,trainingPerformed=False,
              sourceSelection='metadata only; fixed child repeat categories then greedy phone coverage',learnerFeedbackEligible=False)
    a.write_json(output/'plan.json',plan)
    return a.binding(output/'plan.json')


def load(path,sha):
    pin=a.binding(path,sha);plan=read(pin);a.guard(plan['inputs'])
    a.require(plan['cases']==choose(read(plan['inputs']['cohort'])), 'Case selection differs')
    a.require(plan['researchOnly'] is True and plan['learnerFeedbackEligible'] is False, 'Research posture differs')
    return plan,pin


def check_case(plan,case,directory):
    pins=plan['inputs'];cohort=read(pins['cohort']);source_rows=[cohort['rows'][i] for i in case['rowIndices']]
    report=read(a.binding(directory/'report.json'));a.guard(report['inputBindings'])
    for name,sha in report['filesSha256'].items():a.binding(directory/name,sha)
    a.require(report['schemaVersion']==2 and report['complete'] is True and report['clinicalUseEligible'] is False
              and report['learnerFeedbackEligible'] is False and report['trainingPerformed'] is False
              and report['headVariant']==case['variant'] and report['ctcRuntime']['fetchAttempts']==0,'Invalid completed research report')
    a.require(report['inputBindings']['audio']==case['audio'] and
              read(report['inputBindings']['prompt'])==case['prompt'] and
              report['headManifestSha256']==plan['bundles'][case['variant']]['manifest']['sha256'] and
              report['contractSha256']==pins['contract']['sha256'],'Case provenance differs')
    a.require(a.digest(directory/'ctc.f32')==pins['posterior/'+case['clipId']]['sha256'],'Actual CTC posterior differs')
    actual=np.load(directory/'features.npy',allow_pickle=False)
    expected=np.load(pins['matrix']['path'],mmap_mode='r',allow_pickle=False)[case['rowIndices']]
    a.require(actual.dtype==np.float32 and actual.shape==(len(source_rows),1037) and np.array_equal(actual,expected),'Actual raw features differ')
    geometry=read(pins['geometry/'+case['clipId']]);expected_rows={r['id']:r for r in geometry['rows']}
    a.require(len(report['targets'])==len(source_rows),'Target count differs')
    for source,target in zip(source_rows,report['targets'],strict=True):
        a.require(all(target[k]==source[k] for k in ('id','wordIndex','phoneIndex','targetPhone','targetWord','canonicalIndex')),'Target position/order differs')
        a.require(target['modelTargetId']==a.inference.TARGETS.index(source['targetPhone']),'Target model ID differs')
        for k in ('tokenId','intervalFrames','estimatedPoolingWindowFrames','estimatedFrameCenterSeconds','scalarFeatures','diagnosticFlags'):
            a.require(target[k]==expected_rows[source['id']][k],'Target geometry/scalars differ: '+k)
    a.require(report['canonicalPathDiagnostics']==geometry['diagnostics'],'Path diagnostics differ')
    a.require(report['canonicalPrompt']['mappedTokenIds']==geometry['mappedTokenIds']
              and report['canonicalPrompt']['mappedTokens']==geometry['mappedTokens']
              and report['canonicalPrompt']['mappingAmbiguities']==geometry['mappingAmbiguities']
              and report['canonicalPrompt']['canonicalPhones']==[p for w in case['prompt']['words'] for p in w['phones']],
              'Canonical prompt mapping differs')
    head=a.inference.load_head(Path(plan['bundles'][case['variant']]['directory']),plan['bundles'][case['variant']]['manifest']['sha256'])
    ids=np.array([a.inference.TARGETS.index(r['targetPhone']) for r in source_rows],dtype=np.int64)
    probability=head.predict(expected,ids)
    a.require(np.array_equal(probability,np.array([r['subjectiveCorpusRatingProbabilities'] for r in report['targets']])),'Bundle prediction replay differs')
    return dict(clipId=case['clipId'],positions=len(source_rows),phones=sorted(set(r['targetPhone'] for r in source_rows)),
                originalPositions=sum(r['legacyRowIndex'] is not None for r in source_rows),
                addedPositions=sum(r['legacyRowIndex'] is None for r in source_rows),variant=case['variant'],
                properties=case['properties'],ctcExact=True,featuresExact=True,geometryExact=True,predictionsExact=True,
                report=a.binding(directory/'report.json'))


def run(path,sha):
    torch.set_num_threads(2);plan,pin=load(path,sha);root=Path(path).resolve().parent
    a.write_json(root/'started.json',dict(plan=pin));records=[]
    try:
        for case in plan['cases']:
            prompt=root/(case['clipId']+'-prompt.json');a.write_json(prompt,case['prompt'])
            bundle=plan['bundles'][case['variant']];output=root/'cases'/case['clipId']
            result=a.run(SimpleNamespace(contract=a.CONTRACT,contract_sha256=plan['inputs']['contract']['sha256'],
                wav=Path(case['audio']['path']),wav_sha256=case['audio']['sha256'],prompt=prompt,prompt_sha256=a.digest(prompt),
                bundle=Path(bundle['directory']),manifest_sha256=bundle['manifest']['sha256'],phonetic_snapshot=Path(plan['snapshot']),
                output=output,node=plan['inputs']['node']['path']))
            records.append(check_case(plan,case,output));print(json.dumps(result),flush=True)
        a.guard(plan['inputs']);report=dict(complete=True,plan=pin,cases=records,trainingPerformed=False,learnerFeedbackEligible=False,
            clinicalUseEligible=False,independentAccuracyEvidence=False,authorTestRead=False)
        a.write_json(root/'report.json',report);return a.binding(root/'report.json')
    except Exception as error:
        a.write_json(root/'failure.json',dict(error=f'{type(error).__name__}: {error}',completed=records));raise


def verify(path,sha):
    torch.set_num_threads(2);plan,pin=load(path,sha);root=Path(path).resolve().parent;report=read(a.binding(root/'report.json'))
    a.require(report['complete'] is True and report['plan']==pin
              and all(report[k] is False for k in ('trainingPerformed','learnerFeedbackEligible','clinicalUseEligible',
                                                  'independentAccuracyEvidence','authorTestRead')),
              'Completed matching research report required')
    a.require([check_case(plan,c,root/'cases'/c['clipId']) for c in plan['cases']]==report['cases'],'Saved case verification differs')
    a.guard(plan['inputs']);return dict(verified=True,cases=len(report['cases']),positions=sum(c['positions'] for c in report['cases']),
                                      report=a.binding(root/'report.json'),encoderInferencePerformed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('declare','run','verify'))
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256')
    args=parser.parse_args()
    result=declare(args.output) if args.command=='declare' else globals()[args.command](args.plan,args.plan_sha256)
    print(json.dumps(result),flush=True)
