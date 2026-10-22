"""Fixed combined phone-evidence/Silero filter for offline research reports only."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import torch
import multiphone_vad_study as study

raw = study.raw
gate = study.evaluation.gate
APPROVED_REPORT = study.ROOT/'vad-v1/report.json'
APPROVED_SHA = 'e343ea03db257fbffd28fa10da8811d7e53e4ef5328842379d32fb4699b9b8c5'


def approved_inputs():
    approved, report_pin = raw.read_bound_json(APPROVED_REPORT, APPROVED_SHA)
    raw.require(approved['complete'] and approved['researchOnly'] and approved['stateResetReplayExact'],
                'Approved study is incomplete')
    source = approved['inputBindings']
    names = ('sourceManifest', 'vendor/silero_vad.jit', 'vendor/utils_vad.py', 'studySource',
             'evaluationSource', 'gateSource', 'pcmSource', 'rawSource', 'localSource')
    pins = {name: source[name] for name in names}
    pins.update(approvedStudy=report_pin, filterSource=raw.binding(__file__),
                filterTests=raw.binding(raw.HERE/'test_multiphone_vad_filter.py'))
    expected_paths = dict(studySource=study.__file__, evaluationSource=study.evaluation.__file__,
                          gateSource=gate.__file__, rawSource=raw.__file__, localSource=raw.local.__file__,
                          pcmSource=raw.HERE/'speechocean_r_probe.py')
    for name, path in expected_paths.items():
        raw.require(pins[name] == raw.binding(path, pins[name]['sha256']), 'Approved source differs')
    raw.guard(pins)
    manifest, _ = raw.read_bound_json(pins['sourceManifest']['path'], pins['sourceManifest']['sha256'])
    raw.require(manifest['commit'] == study.COMMIT, 'Approved source commit differs')
    for name in ('silero_vad.jit', 'utils_vad.py'):
        entry = manifest['files'][name]
        raw.require({k: entry[k] for k in ('path', 'sha256')} == pins['vendor/'+name],
                    'Approved vendor artifact differs')
    plan, pins['approvedPlan'] = raw.read_bound_json(approved['plan']['path'], approved['plan']['sha256'])
    raw.require(plan['parameters'] == study.PARAMS and plan['runtime'] == study.runtime(),
                'Approved parameters or runtime differ')
    return pins


def filter_report(report_path, expected_sha, output):
    output = Path(output).absolute()
    raw.require(not output.exists() and output.resolve().is_relative_to((raw.HERE/'outputs').resolve()),
                'Choose a fresh ignored research output directory')
    original, original_pin = raw.read_bound_json(report_path, expected_sha)
    pins = approved_inputs()
    pins['rawReport'] = original_pin
    output.mkdir(parents=True, mode=0o700)
    evidence_result = gate.filter_report(report_path, expected_sha, output/'phone-evidence.json')
    evidence, pins['phoneEvidenceReport'] = raw.read_bound_json(evidence_result['report'], evidence_result['sha256'])
    audio = original['inputBindings']['audio']
    raw.require(evidence['sourceReport'] == original_pin and evidence['inputBindings']['audio'] == audio,
                'Phone evidence and VAD audio chain differ')
    pins['audio'] = audio
    samples = raw.read_rating_pcm(Path(audio['path']), audio['sha256'])
    raw.require(len(samples) == original['ctcRuntime']['sampleCount'], 'Waveform sample count differs')
    raw.guard(pins)
    torch.set_num_threads(2)
    helper = study.load_helper(pins['vendor/utils_vad.py'])
    model = torch.jit.load(pins['vendor/silero_vad.jit']['path'], map_location='cpu').eval()
    with torch.inference_mode():
        vad = study.infer(helper, model, samples)
    available = evidence['decision']['ratingAvailable'] and vad['vad']
    reasons = list(evidence['decision']['reasons'])
    if not vad['vad']: reasons.append('no-silero-speech-segment')
    decision = dict(policyId='research-phone-evidence-and-silero-v1', ratingAvailable=available,
                    status='research-evidence-present' if available else 'abstain', reasons=reasons,
                    speechPresenceValidated=False, promptMatchValidated=False,
                    pronunciationCorrectnessValidated=False)
    result = dict(schemaVersion=1, complete=True, researchOnly=True, sourceReport=original_pin,
                  inputBindings=pins, decision=decision, phoneEvidenceDecision=evidence['decision'],
                  vad=dict(**vad, parameters=study.PARAMS, sampleCount=len(samples)),
                  targets=gate.gated_targets(original['targets'], decision),
                  runtime=study.runtime(), trainingPerformed=False, thresholdAdjustmentPerformed=False,
                  clinicalUseEligible=False, learnerFeedbackEligible=False,
                  limitations=['Whole-recording research evidence does not validate speech at each target.',
                    'No prompt-match, pronunciation correctness, child/SSD or clinical validation.',
                    'The study environmental challenge was previously observed and is not independent validation.',
                    'Raw diagnostic artifacts may contain unfiltered subjective corpus rating vectors.'])
    raw.guard(pins)
    study.durable_json(output/'finalreport.json', result)
    return dict(report=str(output/'finalreport.json'), sha256=raw.digest(output/'finalreport.json'), decision=decision)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(filter_report(args.report, args.sha256, args.output), indent=2))
