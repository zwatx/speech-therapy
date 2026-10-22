"""Fixed 250/100 ms segmentation comparison with fresh environmental inference."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import torch
import multiphone_vad_study as study
import multiphone_vad_crop_check as crop
import multiphone_environment_extension as environment

raw = study.raw
BASE_SHA = 'e343ea03db257fbffd28fa10da8811d7e53e4ef5328842379d32fb4699b9b8c5'
CROP_SHA = '9b7af6bffa4c61753bdc19a2c907ef957f616a21d25402557f6beaa05a56e162'
POLICIES = {'default250': 250, 'short100': 100}
CATEGORIES = ('dog', 'rain', 'sea_waves', 'crackling_fire', 'helicopter', 'chainsaw')
OUTPUT = study.ROOT/'short-vad-v1'


def segment(helper, probabilities, length, minimum):
    study.validate_probabilities(probabilities, length)
    args = study.parameters()
    args['min_speech_duration_ms'] = minimum
    intervals = helper.get_speech_timestamps_from_probs(probabilities, audio_length_samples=length, **args)
    study.validate_timestamps(intervals, length)
    return intervals


def compare(helper, record, historical=True):
    clip = record['clip']
    intervals = {name: segment(helper, record['probabilities'], clip['sampleCount'], minimum)
                 for name, minimum in POLICIES.items()}
    if historical:
        raw.require(intervals['default250'] == record['timestamps'] and
                    bool(intervals['default250']) == record['vad'], 'Historical baseline differs')
    raw.require(not intervals['default250'] or intervals['short100'], 'Shorter rule lost baseline retention')
    result = {'clip': clip, 'intervals': intervals,
              'vad': {name: bool(value) for name, value in intervals.items()}}
    if 'gate' in clip:
        result['combined'] = {name: clip['gate'] and value for name, value in result['vad'].items()}
    return result


def inputs(extension_path, extension_sha):
    base, bpin = raw.read_bound_json(study.ROOT/'vad-v1/report.json', BASE_SHA)
    cropped, cpin = raw.read_bound_json(study.ROOT/'vad-crops-v1/report.json', CROP_SHA)
    # The historical verifiers perform no acoustic inference.
    study.report(study.ROOT/'vad-v1', base['plan']['sha256'])
    crop.verify(cropped['plan']['sha256'])
    extension, epin = raw.read_bound_json(extension_path, extension_sha)
    pins = {**base['inputBindings'], 'baseline': bpin, 'crops': cpin, 'extension': epin,
            'comparisonSource': raw.binding(__file__),
            'comparisonTests': raw.binding(raw.HERE/'test_multiphone_short_vad.py'),
            'comparisonProtocol': raw.binding(raw.HERE/'../../docs/model/multiphone-short-vad-protocol.md')}
    pins.update({'extension/'+k: v for k,v in extension['inputBindings'].items()})
    cohort, pins['cohort'] = raw.read_bound_json(pins['cohort']['path'], pins['cohort']['sha256'])
    rows = [r for r in cohort['rows'] if r['trainingEligible']]
    old_environment, _ = raw.read_bound_json(study.ROOT/'environment-v1/plan.json', study.ENV_SHA)
    excluded = {c['metadata']['src_file'] for c in old_environment['clips']}
    raw.require(extension['commit'] == environment.COMMIT and
                extension['inputBindings']['source'] == raw.binding(environment.__file__),
                'Extension source or commit differs')
    metadata_pin = extension['inputBindings']['meta/esc50.csv']
    raw.guard({'metadata': metadata_pin})
    metadata = list(csv.DictReader(Path(metadata_pin['path']).read_text().splitlines()))
    raw.require([c['metadata'] for c in extension['clips']] == environment.select_rows(metadata, excluded),
                'Extension metadata selection differs')
    fresh = []
    for item in extension['clips']:
        m, audio = item['metadata'], item['converted']
        raw.require(m['fold'] == '4' and m['esc10'].lower() == 'true' and
                    m['category'] in CATEGORIES and m['src_file'] not in excluded, 'Fresh selection differs')
        pins['fresh/'+m['filename']] = raw.binding(audio['path'], audio['sha256'])
        fresh.append(dict(id='fresh/'+m['filename'], audio=audio, sampleCount=80000,
                          category=m['category'], sourceId=m['src_file'], population='fresh'))
    raw.require(len(fresh) == len({c['id'] for c in fresh}) == len({c['sourceId'] for c in fresh}) == 24
                and all(sum(c['category'] == name for c in fresh) == 4 for name in CATEGORIES),
                'Fresh source or category coverage differs')
    cached = dict(base['records'])
    for name, record in cropped['records'].items():
        cached['crop/'+name] = {**record, 'clip': {**record['clip'], 'id': 'crop/'+name, 'population': 'crop'}}
    raw.require(len(cached) == 2527, 'Cached coverage differs')
    raw.guard(pins)
    return pins, cached, fresh, rows


def declare(extension_path, extension_sha):
    raw.require(not OUTPUT.exists(), 'Fresh output required')
    pins, cached, fresh, _ = inputs(extension_path, extension_sha)
    OUTPUT.mkdir(mode=0o700)
    raw.write_json(OUTPUT/'plan.json', dict(declaredAt=datetime.now(timezone.utc).isoformat(),
        inputBindings=pins, cachedIds=sorted(cached), freshClips=fresh, policies=POLICIES,
        baseParameters=study.PARAMS, runtime=study.runtime(), inferencePerformed=False))
    return raw.binding(OUTPUT/'plan.json')


def load_plan(expected_sha):
    plan, pin = raw.read_bound_json(OUTPUT/'plan.json', expected_sha)
    pins, cached, fresh, rows = inputs(plan['inputBindings']['extension']['path'],
                                     plan['inputBindings']['extension']['sha256'])
    raw.require(plan['inputBindings'] == pins and plan['cachedIds'] == sorted(cached) and
                plan['freshClips'] == fresh and plan['policies'] == POLICIES and
                plan['baseParameters'] == study.PARAMS and plan['runtime'] == study.runtime(), 'Plan differs')
    return plan, pin, pins, cached, fresh, rows


def summarize(records, rows):
    corpus_clips = [r['clip'] for r in records.values() if r['clip']['population'] == 'corpus']
    retention = {}
    challenge = {}
    crops = {}
    for policy in POLICIES:
        # Reuse tested full per-phone/age/error-support accounting.
        predicted = {name: {'vad': r['vad'][policy]} for name,r in records.items()}
        retention[policy] = study.tables(rows, corpus_clips, predicted)['retention']
        challenge[policy] = {}
        for population in ('environment', 'synthetic', 'fresh'):
            selected = [r for r in records.values() if r['clip']['population'] == population]
            challenge[policy][population] = {category: {
                'total': sum(r['clip']['category'] == category for r in selected),
                'retained': sum(r['clip']['category'] == category and r['vad'][policy] for r in selected),
                **({'combinedRetained': sum(r['clip']['category'] == category and r['combined'][policy]
                                           for r in selected)} if population != 'fresh' else {})}
                for category in sorted({r['clip']['category'] for r in selected})}
        words = [r for r in records.values() if r['clip']['population'] == 'crop']
        crops[policy] = {}
        for method in ('vad', 'combined'):
            retained = [r for r in words if r[method][policy]]
            crops[policy][method] = dict(retainedWords=len(retained), totalWords=len(words),
                retainedPositions=sum(len(r['clip']['targets']) for r in retained),
                totalPositions=sum(len(r['clip']['targets']) for r in words),
                retainedSpeakers=len({r['clip']['speakerId'] for r in retained}),
                totalSpeakers=len({r['clip']['speakerId'] for r in words}))
    return dict(retention=retention, challenges=challenge, crops=crops)


def verify(expected_sha, write=False):
    plan, pin, pins, cached, fresh, rows = load_plan(expected_sha)
    helper = study.load_helper(pins['vendor/utils_vad.py'])
    raw.require({p.name for p in (OUTPUT/'fresh').iterdir()} == {f'{i:02d}.json' for i in range(24)},
                'Fresh record coverage differs')
    artifacts, fresh_records = {}, {}
    for i,c in enumerate(fresh):
        record, artifacts[c['id']] = raw.read_bound_json(OUTPUT/'fresh'/f'{i:02d}.json')
        fresh_records[c['id']] = record
    study.derive_records(helper, fresh, fresh_records)
    results = {name: compare(helper, record) for name,record in {**cached, **fresh_records}.items()}
    raw.require(len(results) == 2551, 'Final coverage differs')
    report = dict(complete=True, researchOnly=True, plan=pin, freshArtifacts=artifacts,
        records=results, **summarize(results, rows), trainingPerformed=False, authorTestRead=False,
        labelsTransferred=False, clinicalUseEligible=False, learnerFeedbackEligible=False,
        limitations=['100 ms was chosen after observing prior crop failures; those are development data.',
            'Fresh ESC10 sources exclude prior12 but pretraining overlap is unknown.',
            'Environmental labels do not establish absence of incidental speech.',
            'No fresh CTC inference: fresh combined-gate outcomes are unmeasured.',
            'No natural isolated-word or child/SSD validation.'])
    raw.guard({**pins, **artifacts, 'plan': pin})
    if write: raw.write_json(OUTPUT/'report.json', report)
    else: raw.require(raw.read_bound_json(OUTPUT/'report.json')[0] == report, 'Saved comparison differs')
    return dict(report=raw.binding(OUTPUT/'report.json'), crops=report['crops'], challenges=report['challenges'])


def run(expected_sha):
    plan, pin, pins, cached, fresh, _ = load_plan(expected_sha)
    raw.require(not (OUTPUT/'fresh').exists(), 'No implicit rerun')
    (OUTPUT/'fresh').mkdir(mode=0o700)
    torch.set_num_threads(2)
    helper = study.load_helper(pins['vendor/utils_vad.py'])
    # Check cached baseline equality before any new acoustic inference.
    for record in cached.values(): compare(helper, record)
    model = torch.jit.load(pins['vendor/silero_vad.jit']['path'], map_location='cpu').eval()
    with torch.inference_mode():
        for i,c in enumerate(fresh):
            samples = raw.read_rating_pcm(Path(c['audio']['path']), c['audio']['sha256'])
            raw.require(len(samples) == c['sampleCount'], 'Fresh duration differs')
            study.durable_json(OUTPUT/'fresh'/f'{i:02d}.json', dict(clip=c, **study.infer(helper, model, samples)))
    raw.guard({**pins, 'plan': pin})
    return verify(expected_sha, write=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare', 'run', 'verify'])
    parser.add_argument('--extension-plan', type=Path)
    parser.add_argument('--extension-sha256')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        raw.require(args.extension_plan is not None and args.extension_sha256, 'Extension plan and SHA required')
        result = declare(args.extension_plan, args.extension_sha256)
    else:
        raw.require(args.plan_sha256 is not None, 'Plan SHA required')
        result = (run if args.command == 'run' else verify)(args.plan_sha256)
    print(json.dumps(result, indent=2))
