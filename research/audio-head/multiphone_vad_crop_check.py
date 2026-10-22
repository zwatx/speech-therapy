"""Fixed short-crop sensitivity extension; no labels, fitting or new CTC inference."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import torch
import multiphone_vad_study as study

raw = study.raw
OUTPUT = study.ROOT/'vad-crops-v1'
CROP_REPORT = raw.HERE/'outputs/multiphone-20260926/word-context-sensitivity-v1/diagnostic/report.json'
CROP_SHA = '6b3df8d70231cd2ee23f3c79dfb645524d5ad94ff4167f8e8a446de4a21b219e'
BASE_SHA = 'e343ea03db257fbffd28fa10da8811d7e53e4ef5328842379d32fb4699b9b8c5'


def inputs():
    base, bpin = raw.read_bound_json(study.ROOT/'vad-v1/report.json', BASE_SHA)
    crops, cpin = raw.read_bound_json(CROP_REPORT, CROP_SHA)
    pins = {**base['inputBindings'], 'baselineReport': bpin, 'cropReport': cpin,
            'cropSource': raw.binding(__file__),
            'cropProtocol': raw.binding(raw.HERE/'../../docs/model/multiphone-vad-crop-protocol.md')}
    baseline_plan, pins['baselinePlan'] = raw.read_bound_json(base['plan']['path'], base['plan']['sha256'])
    raw.require(baseline_plan['parameters'] == study.PARAMS and baseline_plan['runtime'] == study.runtime(),
                'Baseline parameters or runtime differ')
    raw.require(pins['studySource'] == raw.binding(study.__file__), 'Study source differs')
    raw.require(crops['complete'] and len(crops['words']) == 17 and
                crops['successfulTargets'] == 23 and crops['failedWords'] == 0, 'Crop coverage differs')
    clips = []
    for word in crops['words']:
        ident, source_id = word['wordId'], word['clipId']
        audio = raw.binding(word['waveform']['audioPath'], word['waveform']['audioSha256'])
        original = base['records']['corpus/'+source_id]
        source = original['clip']['audio']
        raw.require(source['sha256'] == word['waveform']['sourceAudioSha256'] and
                    original['vad'] is True, 'Original waveform or decision differs')
        samples = raw.read_rating_pcm(Path(audio['path']), audio['sha256'])
        full = raw.read_rating_pcm(Path(source['path']), source['sha256'])
        left, right = word['cropSampleRange']
        raw.require(torch.equal(samples, full[left:right]) and len(samples) ==
                    word['waveform']['sampleCount'], 'Crop is not exact original slice')
        ctc = crops['derivedFiles']['cropCTC/'+ident+'/posterior']
        raw.require(ctc['sha256'] == word['ctcRuntime']['posteriorsSha256'] and
                    word['ctcRuntime']['audioSha256'] == audio['sha256'], 'Crop CTC differs')
        pins['crop/'+ident], pins['ctc/'+ident], pins['original/'+source_id] = audio, ctc, source
        raw.guard({'ctc': ctc})
        gate = study.evaluation.gate.assess(samples.numpy(), np.fromfile(ctc['path'], dtype='<f4').reshape(-1, 392))
        original_meta = crops['originals'][source_id]
        clips.append(dict(id=ident, audio=audio, sampleCount=len(samples), sourceClipId=source_id,
                          age=original_meta['age'], speakerId=original_meta['speakerId'], word=word['text'],
                          targets=[{'rowId': t['rowId'], 'phone': t['targetPhone']} for t in word['targets']],
                          fullRecordingVad=original['vad'], gate=gate['ratingAvailable']))
    raw.require(len({c['id'] for c in clips}) == 17 and
                len({t['rowId'] for c in clips for t in c['targets']}) == 23 and
                len({c['speakerId'] for c in clips}) == 5, 'Crop identity coverage differs')
    raw.guard(pins)
    return pins, clips


def declare():
    raw.require(not OUTPUT.exists(), 'Fresh output required')
    pins, clips = inputs()
    OUTPUT.mkdir(mode=0o700)
    raw.write_json(OUTPUT/'plan.json', dict(declaredAt=datetime.now(timezone.utc).isoformat(),
                   inputBindings=pins, clips=clips, parameters=study.PARAMS, runtime=study.runtime()))
    return raw.binding(OUTPUT/'plan.json')


def verify(expected_sha, write=False):
    plan, pin = raw.read_bound_json(OUTPUT/'plan.json', expected_sha)
    pins, clips = inputs()
    raw.require(plan['inputBindings'] == pins and plan['clips'] == clips and
                plan['parameters'] == study.PARAMS and plan['runtime'] == study.runtime(), 'Plan differs')
    helper = study.load_helper(pins['vendor/utils_vad.py'])
    raw.require({p.name for p in (OUTPUT/'records').iterdir()} ==
                {str(i)+'.json' for i in range(17)}, 'Record coverage differs')
    records, artifacts = {}, {}
    for i, clip in enumerate(clips):
        record, artifacts[clip['id']] = raw.read_bound_json(OUTPUT/'records'/f'{i}.json')
        records[clip['id']] = record
    study.derive_records(helper, clips, records)
    summary = {}
    for method in ('gate', 'vad', 'combined'):
        keep = [c for c in clips if c['gate']] if method == 'gate' else [
            c for c in clips if records[c['id']]['vad'] and (method == 'vad' or c['gate'])]
        summary[method] = dict(retainedWords=len(keep), totalWords=17,
            retainedPositions=sum(len(c['targets']) for c in keep), totalPositions=23,
            retainedSpeakers=len({c['speakerId'] for c in keep}), totalSpeakers=5)
    result = dict(complete=True, researchOnly=True, plan=pin, recordBindings=artifacts,
                  records=records, summary=summary, labelsTransferred=False, trainingPerformed=False,
                  authorTestRead=False, thresholdAdjustmentPerformed=False,
                  clinicalUseEligible=False, learnerFeedbackEligible=False)
    raw.guard({**pins, **artifacts})
    if write: raw.write_json(OUTPUT/'report.json', result)
    else: raw.require(raw.read_bound_json(OUTPUT/'report.json')[0] == result, 'Saved report differs')
    return {'report': raw.binding(OUTPUT/'report.json'), 'summary': summary}


def run(expected_sha):
    plan, pin = raw.read_bound_json(OUTPUT/'plan.json', expected_sha)
    pins, clips = inputs()
    raw.require(plan['inputBindings'] == pins and plan['clips'] == clips and
                plan['parameters'] == study.PARAMS and plan['runtime'] == study.runtime(), 'Plan differs')
    raw.require(not (OUTPUT/'records').exists(), 'No implicit rerun')
    (OUTPUT/'records').mkdir(mode=0o700)
    torch.set_num_threads(2)
    helper = study.load_helper(pins['vendor/utils_vad.py'])
    model = torch.jit.load(pins['vendor/silero_vad.jit']['path'], map_location='cpu').eval()
    with torch.inference_mode():
        for i, clip in enumerate(clips):
            samples = raw.read_rating_pcm(Path(clip['audio']['path']), clip['audio']['sha256'])
            study.durable_json(OUTPUT/'records'/f'{i}.json', dict(clip=clip, **study.infer(helper, model, samples)))
    raw.guard({**pins, 'plan': pin})
    return verify(expected_sha, write=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare', 'run', 'verify'])
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.command != 'declare': raw.require(args.plan_sha256 is not None, 'Plan SHA required')
    print(json.dumps(declare() if args.command == 'declare' else
                     (run if args.command == 'run' else verify)(args.plan_sha256), indent=2))
