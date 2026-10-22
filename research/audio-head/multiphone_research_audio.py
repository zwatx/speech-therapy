"""Explicit raw PCM16 + canonical-prompt adapter for local research rating heads.

No pronunciation dictionary, model fitting, data discovery, upload, or correctness
decision occurs. The caller supplies the exact canonical word/phone structure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

import numpy as np
import torch

import multiphone_local_features as local
import multiphone_phonetic_features as phonetic
import multiphone_research_inference as inference
from speechocean_r_probe import read_rating_pcm

HERE = Path(__file__).resolve().parent
CONTRACT = HERE/'experiments/multiphone-research-audio-v1.json'
RUNTIME_SOURCES = ('multiphone_research_audio.py', 'multiphone_research_ctc.ts')
require = inference.require


def digest(path):
    hash_value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''): hash_value.update(part)
    return hash_value.hexdigest()


def binding(path, expected=None):
    # Retain the lexical path so a changed snapshot symlink is checked again.
    path = Path(path).absolute()
    actual = digest(path)
    require(expected is None or actual == expected, 'Pinned artifact differs: '+str(path))
    return {'path': str(path), 'sha256': expected or actual}


def read_bound_json(path, expected=None):
    payload = Path(path).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    require(expected is None or actual == expected, 'Caller-pinned JSON differs')
    return json.loads(payload), {'path': str(Path(path).absolute()), 'sha256': expected or actual}


def guard(bindings):
    actual = {}
    for value in bindings.values():
        if value['path'] not in actual: actual[value['path']] = digest(value['path'])
        require(actual[value['path']] == value['sha256'], 'Input, model or source changed during inference')


def write_json(path, value):
    with Path(path).open('x') as stream:
        Path(path).chmod(0o600)
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')


def validate_prompt(prompt, mapping, vocabulary, supported_phones, frames):
    """Zero-based word/phone positions; every requested consonant occurs once."""
    require(isinstance(prompt, dict) and set(prompt) == {'schemaVersion', 'language', 'transcript', 'words', 'targets'}
            and type(prompt['schemaVersion']) is int and prompt['schemaVersion'] == 1
            and prompt['language'] == 'en', 'Unsupported canonical prompt schema/language')
    words, targets = prompt['words'], prompt['targets']
    require(isinstance(words, list) and 1 <= len(words) <= 200 and isinstance(targets, list)
            and 1 <= len(targets) <= 23, 'Expected nonempty bounded words/targets')
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
    rows, seen_ids, seen_phones = [], set(), set()
    for target in targets:
        require(isinstance(target, dict) and set(target) == {'id', 'wordIndex', 'phoneIndex', 'targetPhone'}
                and isinstance(target['id'], str) and 1 <= len(target['id']) <= 128 and target['id'].isprintable()
                and target['id'] not in seen_ids and type(target['wordIndex']) is int
                and 0 <= target['wordIndex'] < len(words), 'Invalid target ID or zero-based word position')
        word = words[target['wordIndex']]
        require(type(target['phoneIndex']) is int and 0 <= target['phoneIndex'] < len(word['phones']),
                'Invalid zero-based phone position within the supplied word')
        phone = target['targetPhone']
        require(isinstance(phone, str) and phone in supported_phones and phone not in seen_phones
                and word['phones'][target['phoneIndex']] == phone and phones.count(phone) == 1,
                'Target must be a supported consonant with exactly one canonical occurrence in the clip')
        rows.append({**target, 'targetWord': word['text'], 'modelTargetId': inference.TARGETS.index(phone),
                     'canonicalIndex': offsets[target['wordIndex']]+target['phoneIndex']})
        seen_ids.add(target['id']); seen_phones.add(phone)
    return {'transcript': prompt['transcript'], 'canonicalPhones': phones, 'mappedTokens': mapped,
            'mappedTokenIds': tokens, 'mappingAmbiguities': ambiguities, 'targets': rows}


def make_features(prompt, log_prob, hidden, mapping):
    require(hidden.dtype == np.float32 and hidden.shape == (len(log_prob), 1024)
            and np.isfinite(hidden).all(), 'Phonetic hidden frames differ from the CTC grid')
    estimates, diagnostic = local.local_features(log_prob, prompt['mappedTokenIds'],
        [row['canonicalIndex'] for row in prompt['targets']], mapping)
    rows = []
    for source, estimate in zip(prompt['targets'], estimates, strict=True):
        require(source['canonicalIndex'] == estimate['canonicalIndex'], 'Canonical target order changed')
        start, end = estimate['intervalFrames']
        rows.append({**source, **estimate,
                     'estimatedPoolingWindowFrames': [max(0, start-2), min(len(log_prob), end+2)]})
    pooled, _ = phonetic.pooled_vectors(hidden, rows, len(log_prob))
    scalars = np.asarray([row['scalarFeatures'] for row in rows], dtype=np.float32)
    require(scalars.shape == (len(rows), 13) and np.isfinite(scalars).all(), 'Invalid fixed scalar feature order')
    return np.concatenate((pooled, scalars), axis=1), rows, diagnostic


def recording_measurements(samples):
    x = samples.numpy().astype(np.float64)
    rms = float(np.sqrt(np.mean(x*x)))
    return {'sampleCount': len(x), 'seconds': len(x)/16000, 'rms': rms,
            'rmsDbFS': 20*np.log10(rms) if rms else None, 'peak': float(np.max(np.abs(x))),
            'railSamples': int(np.count_nonzero((x <= -1) | (x >= 32767/32768))),
            'meaning': 'Recording measurements only; not pronunciation quality or accuracy'}


def load_contract(path, expected_sha, snapshot):
    contract, contract_pin = read_bound_json(path, expected_sha)
    require(contract['featureSourceBindingSha256'] == '360c829d179f9c66b66c900fdcf3db2cb0897fdc5724feb642100802d3da4985'
            and contract['featureColumns'] == [f'targetPhonetic:{i}' for i in range(1024)]+list(inference.SCALARS)
            and contract['ctcSessionOptions'] == {'intraOpNumThreads': 2, 'interOpNumThreads': 1, 'executionMode': 'sequential'}
            and contract['device'] == 'cpu' and contract['threads'] == 2
            and contract['researchOnly'] is True, 'Unsupported raw research feature contract')
    bindings = {'contract': contract_pin}
    for name, value in contract['dependencySha256'].items(): bindings['source/'+name] = binding(HERE/name, value)
    for name in RUNTIME_SOURCES: bindings['source/'+name] = binding(HERE/name)
    for filename, sha in contract['phoneticCheckpoint']['artifactSha256'].items():
        bindings['phonetic/'+filename] = binding(snapshot/filename, sha)
    mapping, _ = read_bound_json(local.RECIPE, contract['dependencySha256'][str(local.RECIPE.relative_to(HERE))])
    phonetic_recipe, _ = read_bound_json(phonetic.RECIPE, contract['dependencySha256'][str(phonetic.RECIPE.relative_to(HERE))])
    require({k: phonetic_recipe[k] for k in contract['phoneticCheckpoint']} == contract['phoneticCheckpoint']
            and mapping['poolingContextFrames'] == 2 and local.SCALAR_NAMES == list(inference.SCALARS),
            'Encoder identity, trained scalar names or pooling context differs')
    vocabulary, _ = read_bound_json(snapshot/'vocab.json', contract['phoneticCheckpoint']['artifactSha256']['vocab.json'])
    require(len(vocabulary) == 392 and vocabulary['<pad>'] == 0, 'Expected pinned full phoneme vocabulary')
    guard(bindings)
    return contract, mapping, phonetic_recipe, vocabulary, bindings


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
        report = {'schemaVersion': 1, 'complete': True, 'researchOnly': True, 'inputProvenance': 'caller-supplied; author partition unspecified',
            'headVariant': head.variant, 'headManifestSha256': args.manifest_sha256,
            'contractSha256': args.contract_sha256, 'featureSourceBindingSha256': head.feature_source_binding_sha256,
            'inputBindings': bindings, 'filesSha256': artifacts, 'featureMatrix': {'path': 'features.npy',
                'dtype': 'float32', 'shape': list(values.shape), 'columns': contract['featureColumns']},
            'canonicalPrompt': canonical, 'targets': rows, 'canonicalPathDiagnostics': diagnostic,
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
