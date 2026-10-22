"""Declare, acquire once, run once, and verify the fixed Part A offline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import torch
import multiphone_environment_challenge as environment
import multiphone_nonspeech as fixed
import multiphone_short_vad_filter as filtering
from . import selection as s

raw, gate, vad = filtering.raw, filtering.gate, filtering.study
PROTOCOL = raw.HERE/'../../docs/model/nonspeech-robustness-protocol-draft-20260929.md'
PRIOR_PLAN_SHA = '1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9'
URL = f'https://raw.githubusercontent.com/karolpiczak/ESC-50/{s.COMMIT}/'
POLICIES = {'combined250': 250, 'combined100': 100}
CURL = '/usr/bin/curl'
CURL_OPTIONS = ['--disable', '--fail', '--silent', '--show-error', '--max-time', '60',
                '--retry', '0', '--proto', '=https', '--location', '--proto-redir', '=https']
FLAGS = dict(researchOnly=True, trainingPerformed=False, thresholdAdjustmentPerformed=False,
             clinicalUseEligible=False, learnerFeedbackEligible=False, partBComplete=False,
             handoffRequirementMet=False)
LIMITATIONS = [
    'Admissions by category label in this fixed designed mix; not a general false-acceptance rate.',
    'No listening screen or outcome-based relabeling; admitted clips may contain incidental speech.',
    'No child speech retention, age 6–12, speech disorder, or clinical validation.',
    'Upstream Silero/CTC pretraining overlap with these Freesound recordings is unknown.',
    'Co-primary 250/100 policies; no policy preference, threshold change, or product integration.',
    'Failures remain in the denominator and are never counted as rejection; no implicit retry.',
]


def now():
    return datetime.now(timezone.utc).isoformat()


def freeze(path, value):
    vad.durable_json(path, value)
    Path(path).chmod(0o400)
    return raw.binding(path)


def output_path(output):
    output = Path(output).absolute()
    raw.require(output.resolve().is_relative_to((raw.HERE/'outputs').resolve()), 'Ignored research output required')
    # Keep new evidence outside the historical root so later scans remain historical.
    raw.require(not output.resolve().is_relative_to(s.ROOT.resolve()), 'Keep fresh output outside historical scan root')
    return output


def source_pins():
    paths = {p.name: p for p in Path(__file__).parent.iterdir() if p.suffix in ('.py', '.md')}
    paths.update(protocol=PROTOCOL, conversionHelper=environment.__file__, promptSource=fixed.__file__,
                 requirements=raw.HERE/'requirements.lock.txt')
    return {'worker/'+name: raw.binding(path) for name, path in paths.items()}


def command_output(command):
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout


def ctc_pins(contract, node):
    """Locate the actual cache using the same installed runtime as the pinned worker."""
    module = (raw.HERE/'../../packages/audio-model-adapter/node_modules/@huggingface/transformers/dist/transformers.node.mjs').resolve()
    script = 'const {env}=await import('+json.dumps(module.as_uri())+'); console.log(JSON.stringify(env.cacheDir));'
    cache = Path(json.loads(command_output([node, '--input-type=module', '-e', script])))
    checkpoint = contract['ctcCheckpoint']
    directory = cache/checkpoint['id']/checkpoint['revision']
    files = {'config.json': 'configFile', 'preprocessor_config.json': 'preprocessorFile',
             'vocab.json': 'vocabularyFile', checkpoint['modelFile']: 'modelFile'}
    pins = {}
    for name, key in files.items():
        path = directory/name
        raw.require(path.stat().st_size == checkpoint[key+'Bytes'], 'CTC checkpoint size differs')
        pins['ctc/'+name] = raw.binding(path, checkpoint[key+'Sha256'])
    return pins


def fetch_bytes(url, limit):
    raw.require(url.startswith('https://'), 'HTTPS source required')
    payload = subprocess.run([CURL, *CURL_OPTIONS, '--max-filesize', str(limit), url],
                             check=True, capture_output=True).stdout
    raw.require(len(payload) <= limit, 'Unexpected download size')
    return payload


def get_json(url):
    return fetch_bytes(url, 8_000_000)


def audio_tree(rows, payload, commit_payload):
    commit = json.loads(commit_payload)
    tree = json.loads(payload)
    raw.require(commit.get('sha') == s.COMMIT and tree.get('sha') == commit['tree']['sha']
                and tree.get('truncated') is False, 'ESC commit tree incomplete/different')
    by_path = {item['path']: item for item in tree['tree']}
    pins = {}
    for row in rows:
        entry = by_path.get('audio/'+row['filename'])
        raw.require(entry and entry['type'] == 'blob' and entry['size'] == 441044
                    and len(entry['sha']) == 40, 'Missing/invalid ESC audio blob')
        pins[row['filename']] = dict(gitBlobSha1=entry['sha'], bytes=entry['size'], url=URL+entry['path'])
    return pins


def declare(output):
    output = output_path(output)
    raw.require(not output.exists(), 'Fresh declaration required')
    # This is a global stop, before even a metadata network request.
    pins = filtering.approved_context()
    pins.update(source_pins())
    prior, pins['priorMetadataPlan'] = raw.read_bound_json(s.ROOT/'environment-v1/plan.json', PRIOR_PLAN_SHA)
    raw.require(prior['commit'] == s.COMMIT, 'Approved metadata source commit differs')
    sources = {k: prior['sources'][k] for k in ('meta/esc50.csv', 'LICENSE', 'README.md')}
    for key, pin in sources.items():
        raw.require(pin['url'] == URL+key, 'Metadata source URL differs')
        pins['esc/'+key] = {k: pin[k] for k in ('path', 'sha256')}
        raw.require(pins['esc/'+key] == prior['inputBindings'][key], 'Approved metadata binding differs')
    raw.guard(pins)
    rows = s.metadata(sources['meta/esc50.csv']['path'])
    history, history_pins = s.scan_historical(s.ROOT, rows)
    pins.update(history_pins)
    selected = s.select_rows(rows, history['excludedSources'])
    license_text = Path(sources['LICENSE']['path']).read_text()
    ffmpeg, node = shutil.which('ffmpeg'), shutil.which('node')
    raw.require(ffmpeg and node, 'ffmpeg and node required')
    pins.update(ffmpeg=raw.binding(ffmpeg), node=raw.binding(node), curl=raw.binding(CURL))
    ledger, pins['headLedger'] = raw.read_bound_json(fixed.FINAL_LEDGER, fixed.FINAL_LEDGER_SHA)
    job = next(j for j in ledger['jobs'] if j['variant'] == 'unweighted-all-age')
    raw.require(job['state'] == 'complete' and job['replay']['verifiedExact'] is True, 'Head replay incomplete')
    head = dict(bundle=job['output'], manifestSha256=job['manifestSha256'], variant=job['variant'])
    manifest, pins['headManifest'] = raw.read_bound_json(Path(head['bundle'])/'manifest.json', head['manifestSha256'])
    for name, sha in manifest['filesSha256'].items():
        raw.require(name in raw.inference.FILES, 'Unexpected head file')
        pins['head/'+name] = raw.binding(Path(head['bundle'])/name, sha)
    contract, _, _, _, runtime_pins = raw.load_contract(raw.CONTRACT, fixed.CONTRACT_SHA, fixed.SNAPSHOT)
    pins.update({'raw/'+k: v for k, v in runtime_pins.items()})
    pins.update(ctc_pins(contract, node))
    commit_url = f'https://api.github.com/repos/karolpiczak/ESC-50/git/commits/{s.COMMIT}'
    commit_payload = get_json(commit_url)
    commit = json.loads(commit_payload)
    raw.require(commit.get('sha') == s.COMMIT, 'ESC commit identity differs')
    tree_url = f'https://api.github.com/repos/karolpiczak/ESC-50/git/trees/{commit["tree"]["sha"]}?recursive=1'
    payload = get_json(tree_url)
    blobs = audio_tree(selected, payload, commit_payload)
    output.mkdir(parents=True, mode=0o700)
    for name, body in (('esc-tree.json', payload), ('esc-commit.json', commit_payload)):
        with (output/name).open('xb') as stream:
            stream.write(body)
        (output/name).chmod(0o400)
    pins['escTree'] = raw.binding(output/'esc-tree.json')
    pins['escCommit'] = raw.binding(output/'esc-commit.json')
    prompt = freeze(output/'prompt.json', fixed.PROMPT)
    pins['prompt'] = prompt
    clips = [dict(metadata=row, **blobs[row['filename']],
                  attribution=s.attribution(row, license_text)) for row in selected]
    selection = dict(commit=s.COMMIT, rows=selected, clips=clips, categories=list(s.CATEGORIES),
                     subgroups=s.GROUPS, salt=s.SALT, selectionRule=s.RULE,
                     selectionRevisionReason=s.REVISION, history=history, sources=sources,
                     treeUrl=tree_url, tree=pins['escTree'], commitUrl=commit_url,
                     commitRecord=pins['escCommit'], inferencePerformed=False)
    pins['selection'] = freeze(output/'selection.json', selection)
    plan = dict(schemaVersion=1, declaredAt=now(), selection=pins['selection'], inputBindings=pins,
                head=head, prompt=prompt, contractSha256=fixed.CONTRACT_SHA, snapshot=str(fixed.SNAPSHOT),
                runtime=vad.runtime(), ffmpegVersion=command_output([ffmpeg, '-version']),
                nodeVersion=command_output([node, '--version']).strip(), sileroCommit=vad.COMMIT,
                downloaderCommand=[CURL, *CURL_OPTIONS, '--max-filesize', '<limit>', '<url>'],
                parameters=vad.PARAMS, policies=POLICIES, repeats=1, inferencePerformed=False,
                conversionCommand=[ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', '<original>',
                                   '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '<converted>'],
                approvedArtifactHashes=dict(COMPARISON_SHA=filtering.COMPARISON_SHA,
                    FOLLOWUP_SHA=filtering.FOLLOWUP_SHA, BASELINE_SOURCE_SHA=filtering.BASELINE_SOURCE_SHA), **FLAGS)
    raw.guard(pins)
    return freeze(output/'declaration.json', plan)


def checked_declaration(output, expected_sha, preflight=True):
    output = output_path(output)
    plan, pin = raw.read_bound_json(output/'declaration.json', expected_sha)
    raw.require(plan['runtime'] == vad.runtime() and plan['parameters'] == vad.PARAMS
                and plan['policies'] == POLICIES and plan['repeats'] == 1
                and plan['sileroCommit'] == vad.COMMIT and plan['inferencePerformed'] is False,
                'Declared environment or policy differs; stop, do not retry')
    raw.require(all(plan['inputBindings'].get(k) == v for k, v in source_pins().items()), 'Worker source changed')
    raw.guard(plan['inputBindings'])
    if preflight:
        approved = filtering.approved_context()
        raw.require(all(plan['inputBindings'].get(k) == v for k, v in approved.items()), 'Approved context changed')
    selection, selection_pin = raw.read_bound_json(plan['selection']['path'], plan['selection']['sha256'])
    raw.require(selection_pin == plan['inputBindings']['selection'] and selection['commit'] == s.COMMIT
                and selection['selectionRule'] == s.RULE and selection['salt'] == s.SALT, 'Selection differs')
    rows = s.metadata(selection['sources']['meta/esc50.csv']['path'])
    raw.require(selection['rows'] == s.select_rows(rows, selection['history']['excludedSources']), 'Selection recomputation differs')
    blobs = audio_tree(selection['rows'], Path(selection['tree']['path']).read_bytes(),
                       Path(selection['commitRecord']['path']).read_bytes())
    license_text = Path(selection['sources']['LICENSE']['path']).read_text()
    raw.require(selection['clips'] == [dict(metadata=row, **blobs[row['filename']],
                    attribution=s.attribution(row, license_text)) for row in selection['rows']], 'Selected provenance differs')
    return output, plan, pin, selection


def download_clip(clip, path):
    payload = fetch_bytes(clip['url'], clip['bytes'])
    raw.require(len(payload) == clip['bytes'] and hashlib.sha1(
        b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest() == clip['gitBlobSha1'],
        'ESC download byte size or pinned Git blob mismatch; stop')
    with Path(path).open('xb') as stream:
        stream.write(payload)
    Path(path).chmod(0o400)
    return raw.binding(path)


def active_pins(plan):
    # Huge historical scan evidence is guarded at stage boundaries, not 60 times.
    return {k: v for k, v in plan['inputBindings'].items() if not k.startswith('scan/')}


def stop_on_hash_failure(error):
    # Historical helpers signal integrity failures with ValueError rather than a shared type.
    message = str(error).lower()
    if any(term in message for term in ('sha256', 'sha-256', 'hash mismatch', 'pinned artifact differs',
            'caller-pinned json differs', 'posterior bytes differ', 'derived artifacts changed',
            'input, model or source changed', 'source or input changed', 'integrity check')):
        raise error


def acquire(output, expected_sha):
    output, plan, declaration_pin, selection = checked_declaration(output, expected_sha)
    directory = output/'acquisition'
    raw.require(not directory.exists(), 'No acquisition retry or implicit resume')
    directory.mkdir(mode=0o700)
    (directory/'original').mkdir(mode=0o700)
    (directory/'pcm16').mkdir(mode=0o700)
    pins, records = active_pins(plan), []
    for index, clip in enumerate(selection['clips']):
        raw.guard(pins)
        name = clip['metadata']['filename']
        original, converted = directory/'original'/name, directory/'pcm16'/name
        # Network failures and identity mismatches abort globally, outside the per-clip catch.
        record = dict(clip=clip, original=download_clip(clip, original), acquiredAt=now())
        try:
            record['conversionCommand'] = environment.convert(original, converted, pins['ffmpeg']['path'])
            record.update(converted=raw.binding(converted), state='ready')
            converted.chmod(0o400)
        except Exception as error:
            stop_on_hash_failure(error)
            raw.guard(pins)
            record.update(state='failed', stage='conversion', error=f'{type(error).__name__}: {error}')
        records.append(freeze(directory/f'{index:02d}.json', record))
    raw.guard(plan['inputBindings'])
    return freeze(directory/'manifest.json', dict(declaration=declaration_pin, records=records, **FLAGS))


def read_acquisition(output, declaration_pin, selection, expected_sha, plan):
    acquisition, pin = raw.read_bound_json(output/'acquisition/manifest.json', expected_sha)
    raw.require(acquisition['declaration'] == declaration_pin and len(acquisition['records']) == 60,
                'Acquisition declaration/coverage differs')
    records = []
    for index, (record_pin, clip) in enumerate(zip(acquisition['records'], selection['clips'], strict=True)):
        raw.require(Path(record_pin['path']) == output/'acquisition'/f'{index:02d}.json', 'Acquisition record path differs')
        record, _ = raw.read_bound_json(record_pin['path'], record_pin['sha256'])
        raw.require(record['clip'] == clip and record['state'] in ('ready', 'failed'), 'Acquisition clip differs')
        original_path = output/'acquisition/original'/clip['metadata']['filename']
        converted_path = output/'acquisition/pcm16'/clip['metadata']['filename']
        raw.require(Path(record['original']['path']) == original_path, 'Original path differs')
        raw.guard({'original': record['original']})
        payload = Path(record['original']['path']).read_bytes()
        raw.require(len(payload) == clip['bytes'] and hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
                    == clip['gitBlobSha1'], 'Original Git identity changed')
        if record['state'] == 'ready':
            command = [plan['inputBindings']['ffmpeg']['path'], '-nostdin', '-v', 'error', '-n', '-i', str(original_path),
                       '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(converted_path)]
            raw.require(Path(record['converted']['path']) == converted_path and record['conversionCommand'] == command,
                        'Converted path or conversion command differs')
            raw.guard({'converted': record['converted']})
            environment.check_wave(record['converted']['path'], 16000)
        records.append(record)
    return records, pin


def partials(directory):
    return sorted(str(p.relative_to(directory)) for p in directory.rglob('*') if '.partial' in p.name)


def run(output, expected_sha, acquisition_sha):
    output, plan, declaration_pin, selection = checked_declaration(output, expected_sha)
    records, acquisition_pin = read_acquisition(output, declaration_pin, selection, acquisition_sha, plan)
    results = output/'results'
    raw.require(not results.exists(), 'No run retry or implicit resume')
    results.mkdir(mode=0o700)
    torch.set_num_threads(2)
    pins, outcomes = active_pins(plan), []
    for index, record in enumerate(records):
        raw.guard(pins)
        clip = record['clip']
        outcome = dict(clip=clip, attempt=1, state='failed', stage=record.get('stage', 'raw-adapter'))
        if record['state'] == 'failed':
            outcome['error'] = record['error']
        else:
            destination = results/f'{index:02d}'
            args = SimpleNamespace(contract=raw.CONTRACT, contract_sha256=plan['contractSha256'],
                wav=Path(record['converted']['path']), wav_sha256=record['converted']['sha256'],
                prompt=Path(plan['prompt']['path']), prompt_sha256=plan['prompt']['sha256'],
                bundle=Path(plan['head']['bundle']), manifest_sha256=plan['head']['manifestSha256'],
                phonetic_snapshot=Path(plan['snapshot']), output=destination/'raw', node=pins['node']['path'])
            try:
                raw.run(args)
                outcome['rawReport'] = raw.binding(args.output/'report.json')
                outcome['stage'] = 'combined-filter'
                filtering.filter_report(outcome['rawReport']['path'], outcome['rawReport']['sha256'], destination/'filtered')
                outcome.update(state='complete', combined250=raw.binding(destination/'filtered/default250/finalreport.json'),
                               combined100=raw.binding(destination/'filtered/finalreport.json'))
            except Exception as error:
                stop_on_hash_failure(error)
                # Corrupt pinned input/model/source is global stop, never denominator rejection.
                raw.guard(pins)
                raw.guard({'audio': record['converted']})
                outcome['error'] = f'{type(error).__name__}: {error}'
        outcome['partialOutputs'] = partials(results)
        outcomes.append(freeze(results/f'{index:02d}-outcome.json', outcome))
        print(json.dumps(dict(completed=index+1, total=60, state=outcome['state'])), flush=True)
    raw.guard(plan['inputBindings'])
    freeze(results/'manifest.json', dict(declaration=declaration_pin, acquisition=acquisition_pin,
                                        outcomes=outcomes, partialOutputs=partials(results), **FLAGS))
    report = reconstruct(output, plan, declaration_pin, selection, records, acquisition_pin)
    return freeze(results/'report.json', report)


def complete_decisions(outcome, record, plan):
    """Reconstruct admissions from bound reports; no audio/model inference or segmentation."""
    original, original_pin = raw.read_bound_json(outcome['rawReport']['path'], outcome['rawReport']['sha256'])
    raw.require(original['complete'] is True and original['researchOnly'] is True
                and original['inputBindings']['audio'] == record['converted']
                and original['inputBindings']['prompt'] == plan['prompt']
                and original['headManifestSha256'] == plan['head']['manifestSha256']
                and original['contractSha256'] == plan['contractSha256'], 'Raw input/head chain differs')
    contract_pin = plan['inputBindings']['raw/contract']
    contract, _ = raw.read_bound_json(contract_pin['path'], contract_pin['sha256'])
    raw.require(contract_pin['sha256'] == plan['contractSha256'], 'Declared contract binding differs')
    manifest_pin = plan['inputBindings']['headManifest']
    manifest, _ = raw.read_bound_json(manifest_pin['path'], manifest_pin['sha256'])
    raw.require(manifest_pin['sha256'] == plan['head']['manifestSha256'], 'Declared head binding differs')
    # Derive required coverage from the bound contract and manifest, not from whatever
    # keys happen to be present in the output. A truncated binding map must fail.
    required_raw = {'contract'} | {'source/'+name for name in contract['dependencySha256']} | {
        'source/'+name for name in raw.RUNTIME_SOURCES} | {
        'phonetic/'+name for name in contract['phoneticCheckpoint']['artifactSha256']}
    expected_bindings = {'audio': record['converted'], 'prompt': plan['prompt'], 'headManifest': manifest_pin}
    for name in required_raw:
        declared = plan['inputBindings'].get('raw/'+name)
        raw.require(declared is not None, 'Required declared raw binding missing: '+name)
        expected_bindings[name] = declared
    for name in manifest['filesSha256']:
        declared = plan['inputBindings'].get('head/'+name)
        raw.require(declared is not None, 'Required declared head binding missing: '+name)
        expected_bindings['head/'+name] = declared
    raw.require(original['inputBindings'] == expected_bindings, 'Raw report binding coverage or declared pins differ')
    ctc = original['ctcRuntime']
    raw.require(ctc.get('complete') is True and ctc.get('checkpoint') == contract['ctcCheckpoint']
                and ctc.get('fetchAttempts') == 0 and type(ctc.get('fetchAttempts')) is int
                and ctc.get('sessionOptions') == contract['ctcSessionOptions']
                and ctc.get('node') == plan['nodeVersion'], 'Raw CTC checkpoint/network/runtime differs')
    raw.guard(original['inputBindings'])
    for name, sha in original['filesSha256'].items():
        path = Path(original_pin['path']).parent/name
        raw.require(path.resolve().is_relative_to(Path(original_pin['path']).parent.resolve()), 'Raw artifact escapes')
        raw.binding(path, sha)
    decisions, phone, probabilities = {}, None, None
    for policy, duration in POLICIES.items():
        report, _ = raw.read_bound_json(outcome[policy]['path'], outcome[policy]['sha256'])
        raw.require(report['complete'] is True and report['researchOnly'] is True and report['sourceReport'] == original_pin
                    and report['inputBindings']['audio'] == record['converted']
                    and report['runtime'] == plan['runtime']
                    and report['vad']['parameters'] == {**plan['parameters'], 'min_speech_duration_ms': duration},
                    'Combined report input/runtime/parameters differ')
        raw.guard(report['inputBindings'])
        for name in ('vendor/utils_vad.py', 'vendor/silero_vad.jit', 'studySource', 'gateSource', 'rawSource'):
            raw.require(report['inputBindings'][name] == plan['inputBindings'][name], 'Filter approved source differs')
        if policy == 'combined250':
            evidence_pin = report['inputBindings']['phoneEvidenceReport']
            evidence, _ = raw.read_bound_json(evidence_pin['path'], evidence_pin['sha256'])
            raw.guard(evidence['inputBindings'])
            raw.require(evidence['sourceReport'] == original_pin and evidence['inputBindings']['audio'] == record['converted']
                        and evidence['decision'] == report['phoneEvidenceDecision'], 'Phone-evidence report chain differs')
        else:
            raw.require(report['inputBindings']['default250Report'] == outcome['combined250'], 'Default250 report chain differs')
        vad.validate_probabilities(report['vad']['probabilities'], report['vad']['sampleCount'])
        vad.validate_timestamps(report['vad']['timestamps'], report['vad']['sampleCount'])
        current_phone = report['phoneEvidenceDecision']
        raw.require(type(current_phone['ratingAvailable']) is bool and
                    type(current_phone['recognizedPhoneTokens']) is int and current_phone['recognizedPhoneTokens'] >= 0
                    and type(report['vad']['vad']) is bool and report['vad']['vad'] == bool(report['vad']['timestamps'])
                    and report['vad']['sampleCount'] == original['ctcRuntime']['sampleCount'] == 80000
                    and type(report['decision']['ratingAvailable']) is bool
                    and report['decision']['ratingAvailable'] == (current_phone['ratingAvailable'] and report['vad']['vad']),
                    'Combined decision arithmetic or waveform coverage differs')
        if phone is not None:
            raw.require(phone == current_phone and probabilities == report['vad']['probabilities'], 'Policies did not share one VAD pass')
        phone, probabilities = current_phone, report['vad']['probabilities']
        decisions[policy] = report['decision']['ratingAvailable']
        decisions['vad'+str(duration)] = report['vad']['vad']
    decisions['phoneEvidence'] = phone['ratingAvailable']
    decisions['recognizedPhoneTokens'] = phone['recognizedPhoneTokens']
    return decisions


def summarize(outcomes):
    def counts(group):
        failed = sum(o['state'] == 'failed' for o in group)
        return dict(total=len(group), failed=failed, policies={policy: dict(
            admitted=sum(o['state'] == 'complete' and o['decisions'][policy] for o in group),
            rejected=sum(o['state'] == 'complete' and not o['decisions'][policy] for o in group),
            failed=failed, denominator=len(group)) for policy in POLICIES})
    return dict(overall=counts(outcomes), categories={c: counts([o for o in outcomes if o['clip']['metadata']['category'] == c])
                    for c in s.CATEGORIES}, subgroups={g: counts([o for o in outcomes if o['clip']['metadata']['category'] in cats])
                    for g, cats in s.GROUPS.items()})


def reconstruct(output, plan, declaration_pin, selection, records, acquisition_pin):
    manifest, manifest_pin = raw.read_bound_json(output/'results/manifest.json')
    raw.require(manifest['declaration'] == declaration_pin and manifest['acquisition'] == acquisition_pin
                and len(manifest['outcomes']) == 60, 'Run provenance/coverage differs')
    outcomes = []
    for index, (pin, record) in enumerate(zip(manifest['outcomes'], records, strict=True)):
        raw.require(Path(pin['path']) == output/'results'/f'{index:02d}-outcome.json', 'Outcome path/order differs')
        outcome, _ = raw.read_bound_json(pin['path'], pin['sha256'])
        raw.require(outcome['clip'] == selection['clips'][index] and outcome['attempt'] == 1
                    and outcome['state'] in ('complete', 'failed'), 'Outcome clip/attempt differs')
        if outcome['state'] == 'complete':
            raw.require(record['state'] == 'ready', 'Failed conversion cannot have completed inference')
            outcome['decisions'] = complete_decisions(outcome, record, plan)
        else:
            raw.require(outcome.get('error') and 'decisions' not in outcome, 'Failure must not count as rejection')
        outcomes.append(outcome)
    raw.require(manifest['partialOutputs'] == partials(output/'results'), 'Stale partial inventory differs')
    return dict(schemaVersion=1, complete=True, declaration=declaration_pin, acquisition=acquisition_pin,
                resultsManifest=manifest_pin, outcomes=outcomes, summary=summarize(outcomes),
                coPrimaryOutcomes=list(POLICIES), partialOutputs=manifest['partialOutputs'],
                limitations=LIMITATIONS, offlineCountsRecomputed=True, **FLAGS)


def verify(output, expected_sha, acquisition_sha, report_sha):
    # Reads and hashes only. Never re-executes models, conversion, acquisition or filters.
    output, plan, declaration_pin, selection = checked_declaration(output, expected_sha, preflight=False)
    records, acquisition_pin = read_acquisition(output, declaration_pin, selection, acquisition_sha, plan)
    expected = reconstruct(output, plan, declaration_pin, selection, records, acquisition_pin)
    stored, pin = raw.read_bound_json(output/'results/report.json', report_sha)
    raw.require(stored == expected, 'Saved counts/report differ from offline reconstruction')
    return dict(report=pin, verified=True, summary=expected['summary'], partialOutputs=expected['partialOutputs'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('declare', 'acquire', 'run', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--declaration-sha256')
    parser.add_argument('--report-sha256')
    parser.add_argument('--acquisition-sha256')
    args = parser.parse_args()
    if args.command == 'declare':
        result = declare(args.output)
    else:
        raw.require(args.declaration_sha256 is not None, 'Declaration SHA256 required')
        if args.command == 'verify':
            raw.require(args.report_sha256 is not None, 'Report SHA256 required')
            raw.require(args.acquisition_sha256 is not None, 'Acquisition SHA256 required')
            result = verify(args.output, args.declaration_sha256, args.acquisition_sha256, args.report_sha256)
        elif args.command == 'run':
            raw.require(args.acquisition_sha256 is not None, 'Acquisition SHA256 required')
            result = run(args.output, args.declaration_sha256, args.acquisition_sha256)
        else:
            result = acquire(args.output, args.declaration_sha256)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
