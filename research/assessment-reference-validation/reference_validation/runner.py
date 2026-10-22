"""Declare every case before fresh fixed-bridge inference and retain every outcome."""
import base64
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import statistics
import time
import uuid
import wave

from consumer_assessment import bridge
from consumer_assessment.bridge import assess, canonical_bytes
from reference_assets import AssetError, validate_registry
from content_review.packet import compile_packet, load_pack_bytes, strict_json
from content_review.private_io import create_root, read_private, write_private
from workbench.domain import semantic_digest


class RunError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _wav(samples):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as out:
        out.setparams((1, 2, 16000, len(samples), 'NONE', 'not compressed'))
        out.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
    return stream.getvalue()


def generated_case(kind):
    if kind == 'silence':
        return _wav([0] * 16000)
    if kind == 'tone':
        return _wav([round(1000 * math.sin(2 * math.pi * 220 * i / 16000)) for i in range(19200)])
    if kind == 'clipping':
        return _wav([32767] + [0] * 15999)
    if kind == 'malformed':
        return b'not-a-WAV'
    raise RunError('invalid_case')


def prompt_for(prompt, variant):
    return {'schemaVersion': 2, 'language': 'en', 'transcript': prompt['word'],
            'words': [{'text': prompt['word'], 'phones': variant['phones']}],
            'targets': [{'id': prompt['id'] + '-index-' + str(i), 'wordIndex': 0,
                         'phoneIndex': i, 'targetPhone': prompt['targetPhone']}
                        for i in variant['selectedPositionIndexes']]}


def _assets(registry):
    try:
        validate_registry(registry, require_complete=True)
    except (AssetError, OSError, ValueError, TypeError, KeyError):
        raise RunError('invalid_registry') from None
    assets = {}
    for record in registry['assets']:
        if (type(record) is not dict or type(record.get('sourceWord')) is not str
                or record['sourceWord'] in assets or record.get('clinicalReferenceApproved') is not False
                or record.get('speakerAgeKnown') is not False
                or type(record.get('wavPath')) is not str
                or type(record.get('wavSha256')) is not str or len(record['wavSha256']) != 64):
            raise RunError('invalid_registry')
        assets[record['sourceWord']] = record
    packet = compile_packet(load_pack_bytes())
    if set(assets) != {p['sourceWord'] for p in packet['prompts']}:
        raise RunError('incomplete_registry')
    return assets


def prepare_plan(registry):
    """No inference, fitting or source acquisition occurs here."""
    assets = _assets(registry)
    packet = compile_packet(load_pack_bytes())
    cases = []
    for prompt in packet['prompts']:
        for variant in prompt['variants']:
            cases.append({'id': prompt['id'] + '-' + variant['id'], 'kind': 'public_reference',
                          'sourceWord': prompt['sourceWord'], 'audioSha256': assets[prompt['sourceWord']]['wavSha256'],
                          'prompt': prompt_for(prompt, variant),
                          'referenceMeaning': 'Source-declared word; actual produced phones and speaker age unverified'})
    prompts = {p['id']: p for p in packet['prompts']}
    for identifier, source, destination in [('rabbit-requested-as-thumb', 'rabbit', 'th-beginning-thumb'),
                                          ('banana-requested-as-door', 'banana', 'r-end-door')]:
        prompt = prompts[destination]
        cases.append({'id': identifier, 'kind': 'deliberate_source_word_mismatch', 'sourceWord': source,
                      'audioSha256': assets[source]['wavSha256'], 'prompt': prompt_for(prompt, prompt['variants'][0]),
                      'referenceMeaning': 'Requested word deliberately differs from the source-declared word; no human hearing claimed'})
    rabbit = prompts['r-beginning-rabbit']
    for kind in ('silence', 'tone', 'clipping', 'malformed'):
        cases.append({'id': 'generated-' + kind, 'kind': kind, 'sourceWord': None,
                      'audioSha256': sha(generated_case(kind)), 'prompt': prompt_for(rabbit, rabbit['variants'][0]),
                      'referenceMeaning': 'Generated engineering input, no recorded participant'})
    return {'schemaVersion': 1, 'kind': 'public-reference-engineering-validation',
            'sourcePackSha256': packet['sourcePackSha256'], 'registrySha256': semantic_digest(registry),
            'runnerSha256': sha(Path(__file__).read_bytes()),
            'bridgeSha256': sha(Path(bridge.__file__).read_bytes()),
            'harnessAgeYears': 9, 'harnessAgeMeaning': 'Engineering request parameter, not the actual speaker age',
            'actualSpeakerAge': 'unknown', 'fittingOrTuningAllowed': False,
            'predeclaredChecks': {'silence': 'unavailable:silence', 'clipping': 'unavailable:clipping',
                                 'malformed': 'unavailable:invalid_audio', 'unsupportedZH': 'unavailable:unsupported_target',
                                 'wrongSourceWord': 'Observe returned outcome; prompt match must remain unverified',
                                 'tone': 'Observe returned outcome; nonspeech admission is not established'},
            'cases': cases, 'expectedAttempts': len(cases),
            'claimLimits': {'intendedChildAccuracyEstablished': False, 'clinicalReferenceApproved': False,
                            'promptMatchingValidated': False, 'learnerFeedbackEligible': False,
                            'clinicalUseEligible': False, 'productionUseEligible': False}}


def request_for(case, audio):
    if sha(audio) != case['audioSha256']:
        raise RunError('audio_changed')
    return canonical_bytes({'schemaVersion': 1,
                            'attemptId': str(uuid.uuid5(uuid.NAMESPACE_URL, 'public-reference-v1/' + case['id'])),
                            'ageYears': 9, 'prompt': case['prompt'],
                            'audioBase64': base64.b64encode(audio).decode('ascii')})


def summarize(plan, rows):
    if len(rows) != plan['expectedAttempts'] or [r['caseId'] for r in rows] != [c['id'] for c in plan['cases']]:
        raise RunError('incomplete_run')
    outcomes = Counter(row['response']['outcome'] for row in rows)
    wrong = [r for r in rows if r['kind'] == 'deliberate_source_word_mismatch']
    tone = next(r for r in rows if r['kind'] == 'tone')
    return {'schemaVersion': 1, 'kind': plan['kind'], 'planSha256': semantic_digest(plan),
            'allAttemptDenominator': len(rows), 'outcomes': dict(sorted(outcomes.items())),
            'unavailableReasons': dict(sorted(Counter(r['response']['reason'] for r in rows
                                                       if r['response']['outcome'] == 'unavailable').items())),
            'publicReferenceAttempts': sum(r['kind'] == 'public_reference' for r in rows),
            'wrongPromptProbesProcessed': sum(r['response']['outcome'] == 'processed' for r in wrong),
            'wrongPromptProbeDenominator': len(wrong),
            'generatedToneProcessed': tone['response']['outcome'] == 'processed',
            'latencySeconds': [r['elapsedSeconds'] for r in rows],
            'latencySummarySeconds': {'allAttemptMedian': statistics.median(r['elapsedSeconds'] for r in rows),
                                     'allAttemptMaximum': max(r['elapsedSeconds'] for r in rows)},
            'allAttemptResults': rows, 'claimLimits': dict(plan['claimLimits']),
            'meaning': 'Fixed-bridge behavior on public word references and generated negatives; no new accuracy, child, produced-phone or clinical estimate'}


def run_plan(plan, registry, expected_sha, new_root):
    if type(expected_sha) is not str or semantic_digest(plan) != expected_sha or semantic_digest(plan) != semantic_digest(prepare_plan(registry)):
        raise RunError('plan_changed')
    assets = _assets(registry)
    # Bind every original requested converted file before the first model call.
    audio = {}
    for word, asset in assets.items():
        raw = read_private(asset['wavPath'])
        if len(raw) > 132096 or sha(raw) != asset['wavSha256']:
            raise RunError('audio_changed')
        audio[word] = raw
    root = create_root(new_root)
    write_private(str(root / 'plan.json'), canonical_bytes(plan) + b'\n')
    rows = []
    for number, case in enumerate(plan['cases'], 1):
        raw = audio[case['sourceWord']] if case['sourceWord'] is not None else generated_case(case['kind'])
        request = request_for(case, raw)
        write_private(str(root / ('attempt-%02d-started.json' % number)), canonical_bytes({
            'caseId': case['id'], 'attemptNumber': number, 'requestSha256': sha(request),
            'audioSha256': case['audioSha256'], 'planSha256': expected_sha}) + b'\n')
        started = time.monotonic()
        response = assess(request)
        if (response['binding']['requestSha256'] != sha(request)
                or response['binding']['audioSha256'] != sha(raw)
                or any(response[k] is not False for k in ('learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible'))
                or response['promptMatch'] != 'unverified'):
            raise RunError('response_binding_changed')
        row = {'caseId': case['id'], 'kind': case['kind'], 'sourceWord': case['sourceWord'],
               'sourceMeaning': case['referenceMeaning'], 'elapsedSeconds': time.monotonic() - started,
               'response': response}
        rows.append(row)
        write_private(str(root / ('attempt-%02d-terminal.json' % number)), canonical_bytes(row) + b'\n')
        print(json.dumps({'attempt': number, 'total': len(plan['cases']), 'outcome': response['outcome'],
                          'reason': response['reason']}), flush=True)
    if semantic_digest(prepare_plan(registry)) != expected_sha:
        raise RunError('source_changed_during_run')
    result = summarize(plan, rows)
    write_private(str(root / 'report.json'), canonical_bytes(result) + b'\n')
    return result
