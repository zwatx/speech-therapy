"""Exploratory conditional phone-evidence follow-up; fixed cached VAD outcomes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import multiphone_environment_challenge as environment

raw, gate = environment.raw, environment.gate
ROOT = environment.OUTPUT.parent
OUTPUT = ROOT/'short-vad-followup-v1'
REPORT_SHA = '936814170ea54b37addb84211b99d80153e53096b6c8892bc1b0b936710e9bae'
PRIOR_SHA = '1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9'
POLICIES = ('default250', 'short100')


def selected_ids(records):
    for r in records.values():
        raw.require(set(r['vad']) == set(POLICIES) and all(type(v) is bool for v in r['vad'].values()),
                    'Invalid cached VAD decisions')
        raw.require(not r['vad']['default250'] or r['vad']['short100'], 'Policy retention not nested')
    return sorted(k for k,r in records.items() if r['vad']['short100'])


def combine(records, measured):
    raw.require(set(measured) == set(selected_ids(records)), 'Missing or unexpected phone-evidence results')
    raw.require(all(isinstance(d, dict) for d in measured.values()), 'Missing measured decision')
    result = {}
    for name,r in records.items():
        decision = measured.get(name)
        if decision is not None:
            raw.require(type(decision['ratingAvailable']) is bool and
                        type(decision['recognizedPhoneTokens']) is int and decision['recognizedPhoneTokens'] >= 0,
                        'Invalid measured phone evidence')
        result[name] = dict(clip=r['clip'], vad=r['vad'], phoneEvidence=decision,
            phoneEvidenceMeasured=decision is not None,
            recognizedPhoneTokens=None if decision is None else decision['recognizedPhoneTokens'],
            combined={p: bool(r['vad'][p] and decision['ratingAvailable']) for p in POLICIES})
    return result


def inputs():
    comparison, report_pin = raw.read_bound_json(ROOT/'short-vad-v1/report.json', REPORT_SHA)
    comparison_plan, plan_pin = raw.read_bound_json(comparison['plan']['path'], comparison['plan']['sha256'])
    prior, prior_pin = raw.read_bound_json(environment.OUTPUT/'plan.json', PRIOR_SHA)
    records = {k:r for k,r in comparison['records'].items() if r['clip']['population'] == 'fresh'}
    raw.require(len(records) == 24 and sorted((r['clip'] for r in records.values()), key=lambda c:c['id']) ==
                sorted(comparison_plan['freshClips'], key=lambda c:c['id']), 'Fresh coverage differs')
    raw.require(len(selected_ids(records)) == 2, 'Expected exactly two conditional inferences')
    pins = {'comparisonReport': report_pin, 'comparisonPlan': plan_pin, 'priorPlan': prior_pin,
            'source': raw.binding(__file__), 'tests': raw.binding(raw.HERE/'test_multiphone_short_vad_followup.py'),
            'protocol': raw.binding(raw.HERE/'../../docs/model/multiphone-short-vad-followup-protocol.md'),
            **{'comparison/'+k:v for k,v in comparison_plan['inputBindings'].items()},
            **{'prior/'+k:v for k,v in prior['inputBindings'].items()},
            **{'vadArtifact/'+k:v for k,v in comparison['freshArtifacts'].items()}}
    for name,r in records.items(): pins[name] = r['clip']['audio']
    raw.require(prior['inputBindings']['gateSource'] == raw.binding(gate.__file__) and
                prior['head']['variant'] == 'unweighted-all-age', 'Fixed runtime differs')
    raw.guard(pins)
    return records, prior, pins


def declare():
    raw.require(not OUTPUT.exists(), 'Fresh output required')
    records, prior, pins = inputs()
    OUTPUT.mkdir(mode=0o700)
    raw.write_json(OUTPUT/'plan.json', dict(declaredAt=datetime.now(timezone.utc).isoformat(),
        inputBindings=pins, records=records, selectedIds=selected_ids(records), head=prior['head'],
        conditionalOnObservedVAD=True, inferencePerformed=False, trainingPerformed=False))
    return raw.binding(OUTPUT/'plan.json')


def load_plan(sha):
    plan, pin = raw.read_bound_json(OUTPUT/'plan.json', sha)
    records, prior, pins = inputs()
    raw.require(plan['inputBindings'] == pins and plan['records'] == records and
                plan['selectedIds'] == selected_ids(records) and plan['head'] == prior['head'] and
                plan['conditionalOnObservedVAD'] is True, 'Declaration differs')
    return plan, pin, records, prior, pins


def raw_bindings(prior, audio):
    pins = prior['inputBindings']
    return {**{k[len('runtime/'):]:v for k,v in pins.items() if k.startswith('runtime/')},
            **{k:v for k,v in pins.items() if k.startswith('head/') or k in ('headManifest','prompt')},
            'audio': audio}


def verify_report_metadata(report, canonical, contract):
    runtime = dict(device=contract['device'], threads=contract['threads'],
                   torch=str(raw.torch.__version__), numpy=np.__version__)
    raw.require(runtime['device'] == 'cpu' and runtime['threads'] == 2 and
                report['runtime'] == runtime, 'Raw execution runtime differs')
    raw.require(report['canonicalPrompt'] == canonical, 'Canonical prompt differs')


def verify_clip(directory, audio, prior):
    report, report_pin = raw.read_bound_json(directory/'report.json')
    filtered, filtered_pin = raw.read_bound_json(directory/'gated.json')
    expected = raw_bindings(prior, audio)
    raw.require(report['inputBindings'] == expected and report['complete'] is True and
                report['researchOnly'] is True and report['clinicalUseEligible'] is False and
                report['learnerFeedbackEligible'] is False and
                report['headManifestSha256'] == prior['head']['manifestSha256'] and
                report['headVariant'] == prior['head']['variant'] and
                report['contractSha256'] == prior['contractSha256'], 'Raw input/head chain differs')
    raw.require(set(report['filesSha256']) == {'ctc.f32','ctc.json','ctc-job.json','features.npy'},
                'Raw artifact coverage differs')
    artifacts = {name:raw.binding(directory/name, sha) for name,sha in report['filesSha256'].items()}
    ctc, _ = raw.read_bound_json(directory/'ctc.json', artifacts['ctc.json']['sha256'])
    job, _ = raw.read_bound_json(directory/'ctc-job.json', artifacts['ctc-job.json']['sha256'])
    contract, _ = raw.read_bound_json(expected['contract']['path'], expected['contract']['sha256'])
    samples = raw.read_rating_pcm(Path(audio['path']), audio['sha256']).numpy()
    mapping_pin = expected['source/'+str(raw.local.RECIPE.relative_to(raw.HERE))]
    mapping, _ = raw.read_bound_json(mapping_pin['path'], mapping_pin['sha256'])
    vocabulary, _ = raw.read_bound_json(expected['phonetic/vocab.json']['path'], expected['phonetic/vocab.json']['sha256'])
    prompt, _ = raw.read_bound_json(expected['prompt']['path'], expected['prompt']['sha256'])
    manifest, _ = raw.read_bound_json(expected['headManifest']['path'], expected['headManifest']['sha256'])
    supported = [raw.inference.TARGETS[t['id']] for t in manifest['targets'] if t['supported']]
    frames = raw.local.convolution_frames(len(samples), mapping)
    canonical = raw.validate_prompt(prompt, mapping, vocabulary, supported, frames)
    verify_report_metadata(report, canonical, contract)
    raw.require(ctc == report['ctcRuntime'] and ctc['complete'] is True and ctc['fetchAttempts'] == 0 and
        ctc['jobSha256'] == artifacts['ctc-job.json']['sha256'] and ctc['posteriorsPath'] == 'ctc.f32' and
        ctc['posteriorsSha256'] == artifacts['ctc.f32']['sha256'] and
        ctc['audioSha256'] == job['audioSha256'] == audio['sha256'] and
        ctc['sampleCount'] == job['sampleCount'] == len(samples) == 80000 and
        ctc['frames'] == job['expectedFrames'] == frames and job['researchOnly'] is True and
        job['bindings'] == expected and Path(job['audioPath']).absolute() == Path(audio['path']).absolute() and
        ctc['checkpoint'] == job['ctcCheckpoint'] == contract['ctcCheckpoint'] and
        ctc['sessionOptions'] == job['sessionOptions'] == contract['ctcSessionOptions'], 'CTC job chain differs')
    payload = (directory/'ctc.f32').read_bytes()
    raw.require(hashlib.sha256(payload).hexdigest() == artifacts['ctc.f32']['sha256'], 'Posterior changed')
    decision = gate.assess(samples, np.frombuffer(payload, dtype='<f4').reshape(-1,392))
    raw.require(filtered['complete'] is True and filtered['researchOnly'] is True and
                filtered['clinicalUseEligible'] is False and filtered['learnerFeedbackEligible'] is False and
                filtered['sourceReport'] == report_pin and filtered['policy'] == gate.POLICY and
                filtered['decision'] == decision and
                filtered['targets'] == gate.gated_targets(report['targets'], decision), 'Saved phone gate differs')
    for name,value in {**expected, 'rawReport':report_pin, 'gateSource':raw.binding(gate.__file__),
                       **{'artifact/'+k:v for k,v in artifacts.items()}}.items():
        raw.require(filtered['inputBindings'].get(name) == value, 'Gate artifact/input chain differs')
    raw.guard({**expected, **artifacts, **filtered['inputBindings']})
    return decision, dict(rawReport=report_pin, gatedReport=filtered_pin, artifacts=artifacts)


def verify(sha, write=False):
    plan, pin, records, prior, pins = load_plan(sha)
    raw.require({p.name for p in (OUTPUT/'results').iterdir()} ==
                {Path(name).stem for name in plan['selectedIds']}, 'Conditional output coverage differs')
    measured, artifacts = {}, {}
    for name in plan['selectedIds']:
        measured[name], artifacts[name] = verify_clip(OUTPUT/'results'/Path(name).stem, records[name]['clip']['audio'], prior)
    outcomes = combine(records, measured)
    totals = {p:dict(total=24, vadRetained=sum(r['vad'][p] for r in outcomes.values()),
                    combinedRetained=sum(r['combined'][p] for r in outcomes.values())) for p in POLICIES}
    report = dict(complete=True, researchOnly=True, plan=pin, inputBindings=pins, outcomes=outcomes,
        artifacts=artifacts, totals=totals, measuredPhoneEvidence=2, unmeasuredPhoneEvidence=22,
        conditionalOnObservedVAD=True, trainingPerformed=False, newVADInferencePerformed=False,
        clinicalUseEligible=False, learnerFeedbackEligible=False,
        limitations=['Exploratory conditional follow-up selected after observed VAD outcomes.',
            'Phone evidence is unmeasured for 22 VAD-rejected clips; conjunction is logically false.',
            'Acceptance does not establish speech, prompt match or pronunciation correctness.',
            'Environmental labels are not speech ground truth; pretrained overlap is unknown.'])
    raw.guard({**pins,'plan':pin})
    if write: raw.write_json(OUTPUT/'report.json', report)
    else: raw.require(raw.read_bound_json(OUTPUT/'report.json')[0] == report, 'Saved follow-up differs')
    return dict(report=raw.binding(OUTPUT/'report.json'), totals=totals)


def run(sha):
    plan, pin, records, prior, pins = load_plan(sha)
    raw.require(not (OUTPUT/'results').exists(), 'No implicit restart')
    (OUTPUT/'results').mkdir(mode=0o700)
    for name in plan['selectedIds']:
        raw.guard({**pins,'plan':pin})
        audio = records[name]['clip']['audio']; directory = OUTPUT/'results'/Path(name).stem
        raw.run(SimpleNamespace(contract=Path(prior['inputBindings']['runtime/contract']['path']),
            contract_sha256=prior['contractSha256'], wav=Path(audio['path']), wav_sha256=audio['sha256'],
            prompt=Path(prior['prompt']['path']), prompt_sha256=prior['prompt']['sha256'],
            bundle=Path(prior['head']['bundle']), manifest_sha256=prior['head']['manifestSha256'],
            phonetic_snapshot=Path(prior['snapshot']), output=directory, node=prior['node']))
        gate.filter_report(directory/'report.json', raw.digest(directory/'report.json'), directory/'gated.json')
    return verify(sha, write=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare','run','verify'])
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command != 'declare': raw.require(args.plan_sha256 is not None, 'Plan SHA required')
    print(json.dumps(declare() if args.command == 'declare' else
                     (run if args.command == 'run' else verify)(args.plan_sha256), indent=2))
