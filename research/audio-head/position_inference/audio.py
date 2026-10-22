"""Occurrence-aware PCM16 research adapter; legacy inference remains immutable.

The execution sequence deliberately mirrors the frozen legacy runner because
its declared source hash cannot change. Feature extraction and model prediction
reuse its reviewed helpers; only prompt identity and position checks change.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import numpy as np
import torch
import multiphone_research_audio as raw
from multiphone_research_audio import (
    local, phonetic, inference, read_rating_pcm, require, digest, binding,
    read_bound_json, guard, write_json, recording_measurements,
)

HERE = raw.HERE
DIRECTORY = Path(__file__).resolve().parent
CONTRACT = DIRECTORY/'contract-v2.json'
PARENT_SHA = 'c077e68e37fa68da36a44194094e5c07c40e1866148834c68b6fbd24a5da9782'
RUNTIME_SOURCES = ('position_inference/__init__.py', 'position_inference/audio.py',
                   'multiphone_research_audio.py', 'multiphone_research_ctc.ts')


def load_contract(path, expected_sha, snapshot):
    extension, pin = read_bound_json(path, expected_sha)
    require(set(extension) == {'schemaVersion', 'researchOnly', 'parentContractSha256',
            'promptSchemaVersion', 'maximumTargets', 'occurrenceIdentity', 'sourceSha256'}
            and type(extension['schemaVersion']) is int and extension['schemaVersion'] == 2
            and extension['researchOnly'] is True and extension['parentContractSha256'] == PARENT_SHA
            and type(extension['promptSchemaVersion']) is int and extension['promptSchemaVersion'] == 2
            and type(extension['maximumTargets']) is int and extension['maximumTargets'] == 512
            and extension['occurrenceIdentity'] == 'zero-based wordIndex/phoneIndex'
            and isinstance(extension['sourceSha256'], dict)
            and set(extension['sourceSha256']) == set(RUNTIME_SOURCES), 'Unsupported occurrence contract')
    contract, mapping, recipe, vocabulary, bindings = raw.load_contract(raw.CONTRACT, PARENT_SHA, snapshot)
    bindings['parentContract'] = bindings.pop('contract')
    bindings['contract'] = pin
    for name, sha in extension['sourceSha256'].items(): bindings['source/'+name] = binding(HERE/name, sha)
    guard(bindings)
    contract = {**contract, 'schemaVersion': 2, 'promptConstraints': [
        'Explicit canonical word/phone positions; unique caller IDs and unique positions; repeated phones allowed.',
        'Caller target order is preserved; at most512 targets and512 canonical phones; schema2 only.',
        'Target identity does not establish verified articulation timing or produced-phone identity.'],
        'limitations': contract['limitations']+[
            'Existing bundled heads were fitted on the original unique-phone rows. Repeated-position support is an extraction capability, not a new validated accuracy claim.']}
    return contract, mapping, recipe, vocabulary, bindings


def validate_prompt(prompt, mapping, vocabulary, supported_phones, frames):
    """Zero-based word/phone positions; each requested occurrence has a unique position."""
    require(isinstance(prompt, dict) and set(prompt) == {'schemaVersion', 'language', 'transcript', 'words', 'targets'}
            and type(prompt['schemaVersion']) is int and prompt['schemaVersion'] == 2
            and prompt['language'] == 'en', 'Unsupported canonical prompt schema/language')
    words, targets = prompt['words'], prompt['targets']
    require(isinstance(words, list) and 1 <= len(words) <= 200 and isinstance(targets, list)
            and 1 <= len(targets) <= 512, 'Expected nonempty bounded words/targets')
    phones, offsets = [], []
    for word in words:
        require(isinstance(word, dict) and set(word) == {'text', 'phones'} and isinstance(word['text'], str)
                and 1 <= len(word['text']) <= 64 and word['text'].isprintable()
                and not any(c.isspace() for c in word['text']) and isinstance(word['phones'], list)
                and word['phones'], 'Each word needs explicit text and canonical phones')
        offsets.append(len(phones))
        for phone in word['phones']:
            require(isinstance(phone, str) and re.fullmatch(r'[A-Z]+[012]?', phone), 'Invalid canonical ARPAbet spelling')
            base = re.sub(r'[012]$', '', phone)
            require(base in mapping['vowels'] or phone in mapping['consonants'],
                    'Unsupported canonical phone or stress mark on a consonant')
            phones.append(phone)
    require(isinstance(prompt['transcript'], str) and len(prompt['transcript']) <= 4096
            and prompt['transcript'] == ' '.join(w['text'] for w in words), 'Transcript must exactly join the supplied words')
    require(len(phones) <= 512, 'Canonical sequence exceeds the research resource bound')
    mapped, tokens, ambiguities = local.canonical_mapping(phones, vocabulary, mapping)
    minimum_frames = len(tokens)+sum(a == b for a, b in zip(tokens, tokens[1:]))
    require(minimum_frames <= frames, 'Canonical sequence cannot fit the available CTC frames')
    rows, seen_ids, seen_positions = [], set(), set()
    for target in targets:
        require(isinstance(target, dict) and set(target) == {'id', 'wordIndex', 'phoneIndex', 'targetPhone'}
                and isinstance(target['id'], str) and 1 <= len(target['id']) <= 128 and target['id'].isprintable()
                and target['id'] not in seen_ids and type(target['wordIndex']) is int
                and 0 <= target['wordIndex'] < len(words), 'Invalid target ID or zero-based word position')
        word = words[target['wordIndex']]
        require(type(target['phoneIndex']) is int and 0 <= target['phoneIndex'] < len(word['phones']),
                'Invalid zero-based phone position within the supplied word')
        phone = target['targetPhone']
        require(isinstance(phone, str) and phone in supported_phones and (target['wordIndex'], target['phoneIndex']) not in seen_positions
                and word['phones'][target['phoneIndex']] == phone,
                'Target must identify a distinct supported consonant position')
        rows.append({**target, 'targetWord': word['text'], 'modelTargetId': inference.TARGETS.index(phone),
                     'canonicalIndex': offsets[target['wordIndex']]+target['phoneIndex']})
        seen_ids.add(target['id']); seen_positions.add((target['wordIndex'], target['phoneIndex']))
    return {'schemaVersion': 2, 'transcript': prompt['transcript'], 'canonicalPhones': phones, 'mappedTokens': mapped,
            'mappedTokenIds': tokens, 'mappingAmbiguities': ambiguities, 'targets': rows}


def make_features(prompt, log_prob, hidden, mapping):
    values, rows, diagnostics = raw.make_features(prompt, log_prob, hidden, mapping)
    # Check canonical occupancy in chronological order without reordering outputs.
    groups = defaultdict(list)
    for row in rows: groups[row['tokenId']].append(row)
    for group in groups.values():
        ordered = sorted(group, key=lambda r: r['canonicalIndex'])
        for first, second in zip(ordered, ordered[1:]):
            require(first['intervalFrames'][1] <= second['intervalFrames'][0],
                    'Repeated canonical occupancies overlap or reverse')
            if second['canonicalIndex'] == first['canonicalIndex']+1:
                require(first['intervalFrames'][1] < second['intervalFrames'][0],
                        'Adjacent equal CTC tokens require an intervening blank')
    return values, rows, diagnostics


def run(args):
    started = time.perf_counter()
    contract, mapping, phonetic_recipe, vocabulary, bindings = load_contract(args.contract, args.contract_sha256, args.phonetic_snapshot)
    bindings['audio'] = binding(args.wav, args.wav_sha256)
    prompt, bindings['prompt'] = read_bound_json(args.prompt, args.prompt_sha256)
    samples = read_rating_pcm(args.wav, args.wav_sha256)
    frames = local.convolution_frames(len(samples), mapping)
    manifest, bindings['headManifest'] = read_bound_json(args.bundle/'manifest.json', args.manifest_sha256)
    for name, sha in manifest['filesSha256'].items():
        require(name in inference.FILES, 'Unexpected head bundle filename')
        bindings['head/'+name] = binding(args.bundle/name, sha)
    torch.set_num_threads(2)
    t0 = time.perf_counter(); head = inference.load_head(args.bundle, args.manifest_sha256)
    timings = {'headLoadSeconds': time.perf_counter()-t0}
    require(head.feature_source_binding_sha256 == contract['featureSourceBindingSha256']
            and list(head.feature_columns) == contract['featureColumns'], 'Head and raw extractor feature binding differ')
    canonical = validate_prompt(prompt, mapping, vocabulary, head.supported_phones, frames)
    require(not args.output.exists() and args.output.resolve().is_relative_to((HERE/'outputs').resolve()),
            'Choose a fresh ignored research output; no implicit resume')
    stage = args.output.with_name(args.output.name+'.partial')
    require(not stage.exists(), 'Partial research output exists; inspect it before choosing another output')
    stage.mkdir(parents=True, mode=0o700)
    try:
        guard(bindings)
        job = {'schemaVersion': 1, 'researchOnly': True, 'audioPath': str(args.wav.absolute()),
               'audioSha256': args.wav_sha256, 'sampleCount': len(samples), 'expectedFrames': frames,
               'bindings': bindings, 'ctcCheckpoint': contract['ctcCheckpoint'],
               'sessionOptions': contract['ctcSessionOptions']}
        write_json(stage/'ctc-job.json', job)
        job_sha = digest(stage/'ctc-job.json')
        timings['inputAndProvenanceSeconds'] = time.perf_counter()-started
        t0 = time.perf_counter()
        subprocess.run([args.node, str(HERE/'multiphone_research_ctc.ts'), str((stage/'ctc-job.json').absolute()), job_sha],
                       check=True, env={**os.environ, 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'})
        timings['ctcWorkerWallSeconds'] = time.perf_counter()-t0
        ctc, ctc_pin = read_bound_json(stage/'ctc.json')
        require(ctc['complete'] is True and ctc['jobSha256'] == job_sha and ctc['audioSha256'] == args.wav_sha256
                and ctc['frames'] == frames and ctc['checkpoint'] == contract['ctcCheckpoint']
                and ctc['sessionOptions'] == contract['ctcSessionOptions'] and ctc['fetchAttempts'] == 0
                and ctc['posteriorsPath'] == 'ctc.f32', 'CTC output source/runtime binding differs')
        payload = (stage/'ctc.f32').read_bytes()
        require(hashlib.sha256(payload).hexdigest() == ctc['posteriorsSha256'], 'CTC posterior bytes differ')
        logp = np.frombuffer(payload, dtype='<f4').reshape((-1, 392))
        local.validate_log_prob(logp, frames)
        os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
        t0 = time.perf_counter(); encoder = phonetic.PhoneticEncoder(args.phonetic_snapshot, phonetic_recipe)
        timings['phoneticLoadSeconds'] = time.perf_counter()-t0
        t0 = time.perf_counter(); hidden = encoder(samples)
        timings['phoneticForwardSeconds'] = time.perf_counter()-t0
        t0 = time.perf_counter(); values, rows, diagnostic = make_features(canonical, logp, hidden, mapping)
        timings['alignmentAndPoolingSeconds'] = time.perf_counter()-t0
        t0 = time.perf_counter(); probabilities = head.predict(values, np.asarray([r['modelTargetId'] for r in rows], dtype=np.int64))
        timings['headPredictSeconds'] = time.perf_counter()-t0
        with (stage/'features.npy').open('xb') as stream:
            (stage/'features.npy').chmod(0o600); np.save(stream, values, allow_pickle=False)
        rows = [{**row, 'subjectiveCorpusRatingProbabilities': p.tolist()} for row, p in zip(rows, probabilities, strict=True)]
        artifacts = {'ctc-job.json': job_sha, 'ctc.json': ctc_pin['sha256'], 'ctc.f32': ctc['posteriorsSha256'],
                     'features.npy': digest(stage/'features.npy')}
        guard(bindings)
        require(all(digest(stage/name) == sha for name, sha in artifacts.items()), 'Derived artifacts changed before publication')
        timings['totalSeconds'] = time.perf_counter()-started
        report = {'schemaVersion': 2, 'complete': True, 'researchOnly': True, 'inputProvenance': 'caller-supplied; author partition unspecified',
            'headVariant': head.variant, 'headManifestSha256': args.manifest_sha256,
            'contractSha256': args.contract_sha256, 'parentContractSha256': PARENT_SHA, 'featureSourceBindingSha256': head.feature_source_binding_sha256,
            'inputBindings': bindings, 'filesSha256': artifacts, 'featureMatrix': {'path': 'features.npy',
                'dtype': 'float32', 'shape': list(values.shape), 'columns': contract['featureColumns']},
            'canonicalPrompt': canonical, 'targets': rows, 'occurrenceIdentity': 'zero-based wordIndex/phoneIndex', 'canonicalPathDiagnostics': diagnostic,
            'recordingMeasurements': recording_measurements(samples), 'ctcRuntime': ctc, 'timings': timings,
            'runtime': {'device': 'cpu', 'threads': 2, 'torch': str(torch.__version__), 'numpy': np.__version__},
            'probabilityMeaning': 'Distribution over corpus five-rater subjective score classes0/1/2; weighted heads reverse objective weights. Not empirical calibration or pronunciation correctness.',
            'intervalMeaning': 'Forced canonical CTC state occupancy and fixed contextual pooling window; not verified phone boundaries',
            'trainingPerformed': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
            'producedPhoneLabelsAvailable': False, 'frameTimesValidated': False, 'limitations': contract['limitations']}
        write_json(stage/'report.json', report)
        stage.rename(args.output)
        return {'output': str(args.output.absolute()), 'reportSha256': digest(args.output/'report.json'), 'targets': len(rows), 'timings': timings}
    except Exception as error:
        write_json(stage/'failure.json', {'complete': False, 'error': f'{type(error).__name__}: {error}'})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('wav', 'prompt', 'bundle', 'output', 'phonetic-snapshot'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('wav-sha256', 'prompt-sha256', 'manifest-sha256', 'contract-sha256'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--contract', type=Path, default=CONTRACT)
    parser.add_argument('--node', default='node')
    print(json.dumps(run(parser.parse_args()), indent=2))
