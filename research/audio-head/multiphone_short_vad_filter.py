"""Fixed exploratory 100-ms phone-evidence/Silero filter; research only."""
import argparse
import json
from pathlib import Path
import multiphone_vad_filter as baseline
import multiphone_short_vad as short

raw, gate, study = baseline.raw, baseline.gate, baseline.study
COMPARISON = study.ROOT/'short-vad-v1/report.json'
COMPARISON_SHA = '936814170ea54b37addb84211b99d80153e53096b6c8892bc1b0b936710e9bae'
FOLLOWUP = study.ROOT/'short-vad-followup-v1/report.json'
FOLLOWUP_SHA = '94ecd1e3a19ba744ca3a8b8f74dde74d88fcb41853f09da0c2c71fa98aceeae4'
# The approved, independently reviewed baseline filter is reused without edits.
BASELINE_SOURCE_SHA = '9a9b21ad72cc171ebf77963be4658f76b2fa473edb5f1ccf336ec3a8041e951c'


def approved_context():
    comparison, comparison_pin = raw.read_bound_json(COMPARISON, COMPARISON_SHA)
    plan, plan_pin = raw.read_bound_json(comparison['plan']['path'], comparison['plan']['sha256'])
    followup, followup_pin = raw.read_bound_json(FOLLOWUP, FOLLOWUP_SHA)
    pins = baseline.approved_inputs()
    raw.require(comparison['complete'] is True and followup['complete'] is True and
                comparison['researchOnly'] is True and followup['researchOnly'] is True and
                followup['inputBindings']['comparisonReport'] == comparison_pin, 'Approved reports differ')
    raw.require(plan['inputBindings']['comparisonSource'] == raw.binding(short.__file__) and
                plan['baseParameters'] == study.PARAMS and plan['policies'] == dict(default250=250,short100=100)
                and plan['runtime'] == study.runtime() and
                plan['inputBindings']['vendor/utils_vad.py'] == pins['vendor/utils_vad.py'],
                'Approved comparison source, helper or parameters differ')
    pins.update({'comparison/'+k:v for k,v in plan['inputBindings'].items()})
    pins.update(approvedComparison=comparison_pin, approvedComparisonPlan=plan_pin,
                approvedFollowup=followup_pin, baselineFilterSource=raw.binding(baseline.__file__,BASELINE_SOURCE_SHA),
                shortFilterSource=raw.binding(__file__),
                shortFilterTests=raw.binding(raw.HERE/'test_multiphone_short_vad_filter.py'))
    raw.guard(pins)
    return pins


def filter_report(report_path, expected_sha, output):
    output = Path(output).absolute()
    raw.require(not output.exists() and output.resolve().is_relative_to((raw.HERE/'outputs').resolve()),
                'Choose a fresh ignored research output directory')
    original, original_pin = raw.read_bound_json(report_path, expected_sha)
    pins = approved_context()
    output.mkdir(parents=True, mode=0o700)
    old_result = baseline.filter_report(report_path, expected_sha, output/'default250')
    old, old_pin = raw.read_bound_json(old_result['report'], old_result['sha256'])
    original, reloaded_pin = raw.read_bound_json(report_path, expected_sha)
    audio = original['inputBindings']['audio']
    raw.require(reloaded_pin == original_pin == old['sourceReport'] and
                old['inputBindings']['audio'] == audio and old['vad']['parameters'] == study.PARAMS and
                old['vad']['sampleCount'] == original['ctcRuntime']['sampleCount'] and
                old['runtime'] == study.runtime() and old['complete'] is True and old['researchOnly'] is True,
                'Baseline report, audio, runtime or parameters differ')
    for name in ('vendor/utils_vad.py','vendor/silero_vad.jit','studySource','gateSource','rawSource'):
        raw.require(old['inputBindings'][name] == pins[name], 'Baseline approved input differs')
    pins.update({'baseline/'+k:v for k,v in old['inputBindings'].items()})
    pins.update(rawReport=original_pin, audio=audio, default250Report=old_pin)
    helper = study.load_helper(pins['vendor/utils_vad.py'])
    probabilities, length = old['vad']['probabilities'], old['vad']['sampleCount']
    default = short.segment(helper, probabilities, length, 250)
    raw.require(default == old['vad']['timestamps'] and bool(default) == old['vad']['vad'],
                'Baseline probability segmentation differs')
    intervals = short.segment(helper, probabilities, length, 100)
    phone = old['phoneEvidenceDecision']
    available = phone['ratingAvailable'] and bool(intervals)
    reasons = list(phone['reasons'])
    if not intervals: reasons.append('no-silero-speech-segment')
    decision = dict(policyId='research-phone-evidence-and-silero-short100-v1', ratingAvailable=available,
        status='research-evidence-present' if available else 'abstain', reasons=reasons,
        speechPresenceValidated=False,promptMatchValidated=False,pronunciationCorrectnessValidated=False)
    result = dict(schemaVersion=1,complete=True,researchOnly=True,sourceReport=original_pin,
        inputBindings=pins,decision=decision,phoneEvidenceDecision=phone,
        vad=dict(probabilities=probabilities,timestamps=intervals,vad=bool(intervals),sampleCount=length,
                 parameters={**study.PARAMS,'min_speech_duration_ms':100}),
        targets=gate.gated_targets(original['targets'],decision),runtime=study.runtime(),
        trainingPerformed=False,thresholdAdjustmentPerformed=False,clinicalUseEligible=False,
        learnerFeedbackEligible=False,limitations=[
            '100 ms was selected using prior crop observations; this remains exploratory research.',
            'Conditional fresh follow-up found one combined acceptance among 24 environmental clips.',
            'Environmental labels are not speech ground truth; no prompt or pronunciation correctness validation.',
            'Raw and intermediate files may contain unfiltered rating vectors; consume this final report.'])
    raw.guard(pins)
    study.durable_json(output/'finalreport.json',result)
    return dict(report=str(output/'finalreport.json'),sha256=raw.digest(output/'finalreport.json'),decision=decision)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(filter_report(args.report,args.sha256,args.output),indent=2))
