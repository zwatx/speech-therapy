"""Predeclared offline Silero retention study; no fitting or product decisions."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import sys
import torch
import multiphone_evidence_gate_evaluate as evaluation

raw = evaluation.raw
ROOT = raw.HERE / 'outputs/multiphone-20260927'
COMMIT = '5cd7945676eb32225748052e2e6a0580e4686a08'
GATE_SHA = '82c16b2a01b552b5f1382a44a6b939a011d1d44d131b076a149741ad7bba18d9'
ENV_SHA = '1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9'
ENV_REPORT_SHA = 'a2bec929eacd4978b36c5c15b2eddc73f9c83a24d6127fb7d4f78e3857e0b9a9'
PARAMS = dict(threshold=0.5, sampling_rate=16000, min_speech_duration_ms=250,
              max_speech_duration_s='infinity', min_silence_duration_ms=100, speech_pad_ms=30,
              return_seconds=False, time_resolution=1, visualize_probs=False, neg_threshold=0.35,
              min_silence_at_max_speech=98, use_max_poss_sil_at_max_speech=True)
require = raw.require


def parameters():
    return {**PARAMS, 'max_speech_duration_s': float('inf')}


def runtime():
    return dict(python=sys.version, executable=raw.binding(sys.executable), torch=torch.__version__,
                platform=platform.platform(), device='cpu', threads=2)


def source_pins():
    return {name: raw.binding(path) for name, path in {
        'studySource': __file__, 'testSource': raw.HERE/'test_multiphone_vad_study.py',
        'evaluationSource': evaluation.__file__, 'gateSource': evaluation.gate.__file__,
        'rawSource': raw.__file__, 'localSource': raw.local.__file__,
        'pcmSource': raw.HERE/'speechocean_r_probe.py',
        'protocol': raw.HERE/'../../docs/model/multiphone-vad-protocol.md',
        'requirements': raw.HERE/'requirements.lock.txt'}.items()}


def corpus(pins):
    features, pins['features'] = raw.read_bound_json(evaluation.FEATURES, evaluation.FEATURES_SHA)
    manifest, pins['manifest'] = raw.read_bound_json(features['manifestPath'], features['manifestSha256'])
    cohort, pins['cohort'] = raw.read_bound_json(manifest['cohortPath'], manifest['cohortSha256'])
    require(features['complete'] and features['fullCohortCoverage'] and
            manifest['authorPartition'] == cohort['authorPartition'] == 'train', 'Author-train only')
    raw.local.validate_manifest_rows(manifest, cohort)
    rows = [r for r in cohort['rows'] if r['trainingEligible']]
    require(len(manifest['clips']) == 2495 and len(rows) == 14837 and
            len({r['targetPhone'] for r in rows}) == 23, 'Incomplete full corpus')
    return manifest, rows


def inputs(source_manifest):
    pins = source_pins()
    vendor, pins['sourceManifest'] = raw.read_bound_json(source_manifest)
    require(vendor['commit'] == COMMIT and set(vendor['files']) ==
            {'utils_vad.py', 'silero_vad.jit', 'LICENSE', 'README.md'}, 'Unexpected Silero source')
    for name, pin in vendor['files'].items():
        pins['vendor/'+name] = raw.binding(pin['path'], pin['sha256'])
    manifest, rows = corpus(pins)
    previous, pins['gateReport'] = raw.read_bound_json(ROOT/'evidence-gate-v3/report.json', GATE_SHA)
    require(previous['complete'] and set(previous['decisions']) == {c['id'] for c in manifest['clips']},
            'Previous gate coverage differs')
    clips = []
    for c in manifest['clips']:
        require(previous['clipBindings'][c['id']]['audio'] == raw.binding(c['audioPath'], c['audioSha256']),
                'Previous corpus decision waveform differs')
        clips.append(dict(id='corpus/'+c['id'], corpusId=c['id'], population='corpus',
                          audio=raw.binding(c['audioPath'], c['audioSha256']), sampleCount=c['sampleCount'],
                          gate=previous['decisions'][c['id']]['ratingAvailable']))
    env, pins['environmentPlan'] = raw.read_bound_json(ROOT/'environment-v1/plan.json', ENV_SHA)
    outcomes, pins['environmentReport'] = raw.read_bound_json(ROOT/'environment-v1/results/report.json', ENV_REPORT_SHA)
    by_name = {o['filename']: o for o in outcomes['outcomes']}
    require(len(env['clips']) == len(by_name) == 12 and all(o['pipelineComplete'] for o in by_name.values()),
            'Environmental coverage differs')
    for c in env['clips']:
        name = c['metadata']['filename']
        old_raw, pins['environmentRaw/'+name] = raw.read_bound_json(by_name[name]['rawReport']['path'], by_name[name]['rawReport']['sha256'])
        require(old_raw['inputBindings']['audio'] == c['converted'], 'Previous environmental waveform differs')
        clips.append(dict(id='environment/'+name, population='environment', category=c['metadata']['category'],
                          audio=raw.binding(c['converted']['path'], c['converted']['sha256']), sampleCount=80000,
                          gate=by_name[name]['decision']['ratingAvailable']))
    for label in ('zero', 'gaussian', 'sine440'):
        filtered, pins['synthetic/'+label] = raw.read_bound_json(previous['rawReportChecks'][label]['report'],
                                                               previous['rawReportChecks'][label]['sha256'])
        original, pins['syntheticRaw/'+label] = raw.read_bound_json(filtered['sourceReport']['path'], filtered['sourceReport']['sha256'])
        audio = original['inputBindings']['audio']
        clips.append(dict(id='synthetic/'+label, population='synthetic', category=label,
                          audio=raw.binding(audio['path'], audio['sha256']),
                          sampleCount=original['ctcRuntime']['sampleCount'], gate=filtered['decision']['ratingAvailable']))
    require(len({c['id'] for c in clips}) == 2510, 'Duplicate/missing clips')
    raw.guard(pins)
    return pins, clips, rows


def durable_json(path, value):
    raw.write_json(path, value)
    with Path(path).open('rb') as stream: os.fsync(stream.fileno())


def declare(source_manifest, output):
    output = Path(output).absolute()
    require(not output.exists() and output.resolve().is_relative_to((raw.HERE/'outputs').resolve()),
            'Fresh ignored output directory required')
    pins, clips, _ = inputs(source_manifest)
    plan = dict(schemaVersion=1, declaredAt=datetime.now(timezone.utc).isoformat(), inputBindings=pins,
                clips=clips, parameters=PARAMS, runtime=runtime(), commit=COMMIT,
                inferencePerformed=False, trainingPerformed=False, authorTestRead=False)
    output.mkdir(parents=True, mode=0o700)
    durable_json(output/'plan.json', plan)
    return raw.binding(output/'plan.json')


def load_helper(pin):
    raw.guard({'helper': pin})
    spec = importlib.util.spec_from_file_location('pinned_silero_utils', pin['path'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_probabilities(probs, sample_count):
    require(isinstance(probs, list) and len(probs) == (sample_count+511)//512 and
            all(type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1 for p in probs),
            'Invalid probability values or frame coverage')


def validate_timestamps(timestamps, sample_count):
    require(isinstance(timestamps, list), 'Invalid timestamp list')
    previous_end = 0
    for interval in timestamps:
        require(isinstance(interval, dict) and set(interval) == {'start', 'end'} and
                type(interval['start']) is int and type(interval['end']) is int and
                previous_end <= interval['start'] < interval['end'] <= sample_count,
                'Invalid, overlapping, or out-of-bounds timestamps')
        previous_end = interval['end']


class CaptureModel:
    def __init__(self, model):
        self.model, self.probabilities, self.resets = model, [], 0

    def reset_states(self):
        self.probabilities = []
        self.resets += 1
        return self.model.reset_states()

    def __call__(self, chunk, rate):
        value = self.model(chunk, rate)
        require(value.numel() == 1, 'Non-scalar model output')
        p = value.item()
        require(math.isfinite(p) and 0 <= p <= 1, 'Invalid model probability')
        self.probabilities.append(p)
        return value


def infer(helper, model, samples):
    captured = CaptureModel(model)
    timestamps = helper.get_speech_timestamps(samples, captured, **parameters())
    validate_timestamps(timestamps, len(samples))
    require(captured.resets == 1, 'Expected state reset for every clip')
    validate_probabilities(captured.probabilities, len(samples))
    require(timestamps == helper.get_speech_timestamps_from_probs(captured.probabilities,
            audio_length_samples=len(samples), **parameters()), 'Probability replay differs')
    return dict(probabilities=captured.probabilities, timestamps=timestamps, vad=bool(timestamps))


def checked_plan(output, expected_sha):
    plan, pin = raw.read_bound_json(Path(output)/'plan.json', expected_sha)
    require(plan['parameters'] == PARAMS and plan['commit'] == COMMIT and
            plan['runtime'] == runtime() and plan['inferencePerformed'] is False, 'Declaration differs')
    require(all(plan['inputBindings'].get(k) == v for k,v in source_pins().items()), 'Stale study source')
    raw.guard(plan['inputBindings'])
    return plan, pin


def derive_records(helper, clips, records):
    require(set(records) == {c['id'] for c in clips} and len(records) == len(clips), 'Recorded coverage differs')
    checked = {}
    for clip in clips:
        record = records[clip['id']]
        require(record['clip'] == clip, 'Recorded clip binding differs')
        validate_probabilities(record['probabilities'], clip['sampleCount'])
        timestamps = helper.get_speech_timestamps_from_probs(record['probabilities'],
                         audio_length_samples=clip['sampleCount'], **parameters())
        validate_timestamps(record['timestamps'], clip['sampleCount'])
        validate_timestamps(timestamps, clip['sampleCount'])
        require(record['timestamps'] == timestamps and type(record['vad']) is bool and
                record['vad'] == bool(timestamps), 'Recorded decision or timestamps differ')
        checked[clip['id']] = record
    return checked


def tables(rows, clips, records):
    retention = {}
    for method in ('gate', 'vad', 'combined'):
        decisions = {c['corpusId']: {'ratingAvailable': c['gate'] if method == 'gate' else
                     records[c['id']]['vad'] if method == 'vad' else c['gate'] and records[c['id']]['vad']}
                     for c in clips if c['population'] == 'corpus'}
        retention[method] = {}
        for population, selected in [('allAge', rows), ('child6to12', [r for r in rows if 6 <= r['age'] <= 12])]:
            selected_by_clip = {}
            for row in selected:
                selected_by_clip.setdefault(row['clipId'], []).append(row)
            withheld = sorted(c for c in selected_by_clip if not decisions[c]['ratingAvailable'])
            support = {c: dict(**evaluation.counts(selected_by_clip[c]),
                               speakerIds=sorted({r['speakerId'] for r in selected_by_clip[c]}),
                               ages=sorted({r['age'] for r in selected_by_clip[c]}),
                               phones={p: evaluation.counts([r for r in selected_by_clip[c] if r['targetPhone'] == p])
                                       for p in sorted({r['targetPhone'] for r in selected_by_clip[c]})})
                       for c in withheld}
            retention[method][population] = dict(overall=evaluation.summarize(selected, decisions),
                phones={p: evaluation.summarize([r for r in selected if r['targetPhone'] == p], decisions)
                        for p in sorted({r['targetPhone'] for r in rows})}, withheldClipIds=withheld, withheldClipSupport=support)
    challenge = {}
    for population in ('environment', 'synthetic'):
        challenge[population] = {}
        for category in sorted({c['category'] for c in clips if c['population'] == population}):
            group = [c for c in clips if c['population'] == population and c['category'] == category]
            challenge[population][category] = dict(total=len(group), gateRetained=sum(c['gate'] for c in group),
                vadRetained=sum(records[c['id']]['vad'] for c in group),
                combinedRetained=sum(c['gate'] and records[c['id']]['vad'] for c in group),
                clips=[dict(id=c['id'], gate=c['gate'], vad=records[c['id']]['vad'],
                            combined=c['gate'] and records[c['id']]['vad']) for c in group])
    return dict(retention=retention, challenges=challenge)


def report(output, expected_sha, write=False):
    output = Path(output)
    plan, pin = checked_plan(output, expected_sha)
    # Reconstruct the exact predeclared cohort and comparison inputs independently.
    pins, clips, rows = inputs(plan['inputBindings']['sourceManifest']['path'])
    require(pins == plan['inputBindings'] and clips == plan['clips'], 'Input declaration differs')
    helper = load_helper(pins['vendor/utils_vad.py'])
    expected_files = {f'{i:04d}.json' for i in range(len(clips))}
    require({p.name for p in (output/'records').iterdir()} == expected_files, 'Record files coverage differs')
    records, artifact_pins = {}, {}
    for i, clip in enumerate(clips):
        record, artifact_pin = raw.read_bound_json(output/'records'/f'{i:04d}.json')
        require(record['clip']['id'] == clip['id'], 'Record order or ID differs')
        records[clip['id']], artifact_pins[clip['id']] = record, artifact_pin
    derive_records(helper, clips, records)
    replay, replay_pin = raw.read_bound_json(output/'state-reset-replay.json')
    require(replay == records[clips[0]['id']], 'State-reset replay differs')
    artifact_pins['stateResetReplay'] = replay_pin
    result = dict(complete=True, researchOnly=True, plan=pin, inputBindings=pins, recordBindings=artifact_pins,
                  records=records, stateResetReplayExact=True, **tables(rows, clips, records), trainingPerformed=False, authorTestRead=False,
                  clinicalUseEligible=False, learnerFeedbackEligible=False, independentValidation=False,
                  limitations=['Corpus retention is not clinical false-rejection accuracy.',
                    'Public pretrained model training provenance may overlap evaluation material.',
                    'Environmental challenge is previously observed; category labels are not speech ground truth.',
                    'Synthetic negatives are known checks, not an independent test.',
                    'No fitting, threshold selection, prompt-match validation, or product integration.'])
    raw.guard({**pins, **artifact_pins, 'plan': pin})
    if write:
        durable_json(output/'report.json', result)
    else:
        stored, _ = raw.read_bound_json(output/'report.json')
        require(stored == result, 'Saved report differs from independent reconstruction')
    return {'report': raw.binding(output/'report.json'), 'verifiedFromProbabilities': True,
            'retention': {k: v['allAge']['overall'] for k,v in result['retention'].items()}}


def run(output, expected_sha):
    output = Path(output)
    plan, pin = checked_plan(output, expected_sha)
    require(not (output/'records').exists() and not (output/'report.json').exists(), 'No implicit reruns or resume')
    # Verify plan contents before any model execution.
    pins, clips, _ = inputs(plan['inputBindings']['sourceManifest']['path'])
    require(pins == plan['inputBindings'] and clips == plan['clips'], 'Declared inputs differ')
    (output/'records').mkdir(mode=0o700)
    torch.set_num_threads(2)
    helper = load_helper(pins['vendor/utils_vad.py'])
    raw.guard(pins)
    model = torch.jit.load(pins['vendor/silero_vad.jit']['path'], map_location='cpu').eval()
    with torch.inference_mode():
        for i, clip in enumerate(clips):
            samples = raw.read_rating_pcm(Path(clip['audio']['path']), clip['audio']['sha256'])
            require(len(samples) == clip['sampleCount'], 'Waveform sample count differs')
            record = dict(clip=clip, **infer(helper, model, samples))
            durable_json(output/'records'/f'{i:04d}.json', record)
            if (i+1) % 100 == 0: print(json.dumps({'completed': i+1, 'total': len(clips)}), flush=True)
    first = clips[0]
    samples = raw.read_rating_pcm(Path(first['audio']['path']), first['audio']['sha256'])
    with torch.inference_mode():
        replay = dict(clip=first, **infer(helper, model, samples))
    original, _ = raw.read_bound_json(output/'records/0000.json')
    durable_json(output/'state-reset-replay.json', replay)
    require(replay == original, 'State-reset replay differs')
    raw.guard({**pins, 'plan': pin})
    return report(output, expected_sha, write=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare', 'run', 'report'])
    parser.add_argument('--source-manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        require(args.source_manifest is not None, 'Source manifest required')
        answer = declare(args.source_manifest, args.output)
    else:
        require(args.plan_sha256 is not None, 'Plan SHA required')
        answer = (run if args.command == 'run' else report)(args.output, args.plan_sha256)
    print(json.dumps(answer, indent=2))
