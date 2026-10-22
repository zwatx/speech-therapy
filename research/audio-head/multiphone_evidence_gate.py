"""Withhold research ratings when the recording has no recognized phone evidence.

This is a necessary-input check, not speech detection or prompt verification.
The historical raw adapter and bundles remain unchanged and reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import multiphone_research_audio as raw

POLICY = {
    'id': 'research-phone-evidence-v1',
    'constantWaveform': 'withhold when every PCM sample equals the first sample',
    'noDecodedPhone': 'withhold when collapsed greedy CTC has no token ID above 3',
    'thresholdFitted': False,
    'meaning': 'Necessary input evidence only; acceptance does not establish speech, prompt match or correct pronunciation',
}


def assess(samples, log_prob):
    """No fitted amplitude cutoff; weak recognized speech remains eligible."""
    x = np.asarray(samples)
    raw.require(x.ndim == 1 and 1600 <= len(x) <= 480000 and
                np.isfinite(x).all() and (np.abs(x) <= 1).all(), 'Invalid PCM samples')
    # Validate even rejected inputs: corrupt posterior bytes are runtime errors,
    # never an apparent successful abstention.
    mapping = json.loads(raw.local.RECIPE.read_text())
    frames = raw.local.convolution_frames(len(x), mapping)
    raw.local.validate_log_prob(log_prob, frames)
    phones = [token for token in raw.local.greedy_tokens(log_prob) if token > 3]
    reasons = []
    if np.all(x == x[0]):
        reasons.append('constant-waveform')
    if not phones:
        reasons.append('no-recognized-phone-evidence')
    return {'policyId': POLICY['id'], 'status': 'abstain' if reasons else 'research-evidence-present',
            'ratingAvailable': not reasons, 'reasons': reasons,
            'recognizedPhoneTokens': len(phones), 'speechPresenceValidated': False,
            'promptMatchValidated': False, 'pronunciationCorrectnessValidated': False}


def gated_targets(targets, decision):
    result = []
    for target in targets:
        item = {key: target[key] for key in ('id', 'targetPhone', 'wordIndex', 'phoneIndex')}
        item['subjectiveCorpusRatingProbabilities'] = (
            target['subjectiveCorpusRatingProbabilities'] if decision['ratingAvailable'] else None)
        result.append(item)
    return result


def filter_report(report_path, expected_sha, output):
    """Verify and filter a completed raw-adapter report; never rewrite it."""
    report, report_pin = raw.read_bound_json(report_path, expected_sha)
    raw.require(report.get('complete') is True and report.get('researchOnly') is True and
                report.get('clinicalUseEligible') is False and report.get('learnerFeedbackEligible') is False,
                'Expected completed research-only raw report')
    pins = {**report['inputBindings'], 'rawReport': report_pin,
            'gateSource': raw.binding(__file__), 'localFeaturesSource': raw.binding(raw.local.__file__)}
    for name, path in [('mappingRecipe', raw.local.RECIPE), ('rawSource', raw.__file__),
                       ('pcmSource', raw.HERE/'speechocean_r_probe.py')]:
        matching = [pin['sha256'] for pin in report['inputBindings'].values()
                    if Path(pin['path']).resolve() == Path(path).resolve()]
        raw.require(len(set(matching)) <= 1, 'Conflicting runtime input pins')
        pins[name] = raw.binding(path, matching[0] if matching else None)
    directory = Path(report_path).absolute().parent
    raw.require({'ctc.f32', 'ctc.json', 'ctc-job.json'} <= set(report['filesSha256']),
                'Raw report lacks required CTC artifact bindings')
    for name, sha in report['filesSha256'].items():
        file_path = (directory/name).resolve()
        raw.require(file_path.is_relative_to(directory.resolve()), 'Artifact path escapes raw output')
        pins['artifact/'+name] = raw.binding(file_path, sha)
    audio = pins['audio']
    samples = raw.read_rating_pcm(Path(audio['path']), audio['sha256']).numpy()
    ctc, _ = raw.read_bound_json(directory/'ctc.json', report['filesSha256']['ctc.json'])
    job, _ = raw.read_bound_json(directory/'ctc-job.json', report['filesSha256']['ctc-job.json'])
    frames = raw.local.convolution_frames(len(samples), json.loads(raw.local.RECIPE.read_text()))
    raw.require(ctc == report.get('ctcRuntime') and ctc.get('complete') is True
                and ctc['jobSha256'] == report['filesSha256']['ctc-job.json']
                and ctc['posteriorsPath'] == 'ctc.f32'
                and ctc['posteriorsSha256'] == report['filesSha256']['ctc.f32']
                and ctc['audioSha256'] == audio['sha256'] == job['audioSha256']
                and ctc['sampleCount'] == len(samples) == job['sampleCount']
                and ctc['frames'] == frames == job['expectedFrames']
                and job.get('researchOnly') is True
                and job['bindings'] == report['inputBindings']
                and job['bindings']['audio'] == audio
                and Path(job['audioPath']).absolute() == Path(audio['path']).absolute()
                and ctc['checkpoint'] == job['ctcCheckpoint']
                and ctc['sessionOptions'] == job['sessionOptions'], 'CTC runtime, job or waveform binding differs')
    # Hash the exact bytes used below, then recheck all bindings before writing.
    posterior_bytes = (directory/'ctc.f32').read_bytes()
    raw.require(hashlib.sha256(posterior_bytes).hexdigest() == ctc['posteriorsSha256'],
                'CTC posterior bytes differ')
    logp = np.frombuffer(posterior_bytes, dtype='<f4').reshape(-1, 392)
    decision = assess(samples, logp)
    result = {'schemaVersion': 1, 'complete': True, 'researchOnly': True,
              'policy': POLICY, 'decision': decision,
              'sourceReport': report_pin, 'inputBindings': pins,
              'targets': gated_targets(report['targets'], decision),
              'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
              'limitations': [POLICY['meaning'],
                  'Recognizers can emit phones on nonspeech and miss genuine speech.',
                  'This fixed exploratory policy has no independent child/SSD validation.',
                  'Raw diagnostic artifacts may contain unfiltered corpus ratings.']}
    raw.guard(pins)
    output = Path(output).absolute()
    raw.require(output.resolve().is_relative_to((raw.HERE/'outputs').resolve()),
                'Keep gated reports in ignored research outputs')
    output.parent.mkdir(parents=True, exist_ok=True)
    raw.write_json(output, result)
    return {'report': str(output), 'sha256': raw.digest(output), 'decision': decision}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(filter_report(args.report, args.sha256, args.output), indent=2))
