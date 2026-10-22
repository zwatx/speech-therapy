"""Pinned ESC-10 environmental challenge; no fitting or gate adjustment."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import urllib.request
import wave

import multiphone_nonspeech as fixed
import multiphone_evidence_gate as gate
import multiphone_research_audio as raw

COMMIT = '33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6'
URL = f'https://raw.githubusercontent.com/karolpiczak/ESC-50/{COMMIT}/'
CATEGORIES = ('dog', 'rain', 'sea_waves', 'crackling_fire', 'helicopter', 'chainsaw')
OUTPUT = raw.HERE/'outputs/multiphone-20260927/environment-v1'
PROTOCOL = raw.HERE/'../../docs/model/multiphone-environment-protocol.md'
require = raw.require


def select_rows(rows):
    selected = []
    require(len({r['filename'] for r in rows}) == len(rows), 'Duplicate metadata filenames')
    for category in CATEGORIES:
        candidates = sorted((r for r in rows if r['esc10'].lower() == 'true'
                             and r['fold'] == '1' and r['category'] == category), key=lambda r: r['filename'])
        chosen, seen = [], set()
        for row in candidates:
            require(Path(row['filename']).name == row['filename'] and row['filename'].endswith('.wav'),
                    'Unsafe audio filename')
            if row['src_file'] not in seen:
                chosen.append(row); seen.add(row['src_file'])
            if len(chosen) == 2: break
        require(len(chosen) == 2, 'Insufficient distinct ESC10 fold1 sources for '+category)
        selected.extend(chosen)
    return selected


def download(relative, path):
    # Only public files at the declared commit; no script execution or redirects to models.
    with urllib.request.urlopen(URL+relative, timeout=60) as response:
        payload = response.read(4_000_000)
    require(len(payload) < 4_000_000, 'Unexpected download size')
    with path.open('xb') as stream: stream.write(payload)
    path.chmod(0o600)
    return {'url': URL+relative, **raw.binding(path)}


def check_wave(path, rate):
    with wave.open(str(path), 'rb') as stream:
        require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes(),
                 stream.getcomptype()) == (1, 2, rate, 5*rate, 'NONE'), 'Expected complete 5-second mono PCM16 WAV')
        require(len(stream.readframes(5*rate)) == 10*rate, 'Truncated WAV')


def convert(source, output, ffmpeg):
    check_wave(source, 44100)
    require(not output.exists(), 'Conversion output exists')
    command = [ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', str(source),
               '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(output)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    output.chmod(0o600)
    check_wave(output, 16000)
    return command


def declare():
    require(not OUTPUT.exists(), 'Fresh challenge output required')
    ffmpeg, node = shutil.which('ffmpeg'), shutil.which('node')
    require(ffmpeg is not None and node is not None, 'ffmpeg and node required')
    OUTPUT.mkdir(parents=True, mode=0o700)
    pins = {'source': raw.binding(__file__), 'gateSource': raw.binding(gate.__file__),
            'protocol': raw.binding(PROTOCOL), 'ffmpeg': raw.binding(ffmpeg), 'node': raw.binding(node)}
    source_pins = {}
    for relative in ('meta/esc50.csv', 'LICENSE', 'README.md'):
        source_pins[relative] = download(relative, OUTPUT/Path(relative).name)
        pins[relative] = {k: source_pins[relative][k] for k in ('path', 'sha256')}
    rows = list(csv.DictReader((OUTPUT/'esc50.csv').read_text().splitlines()))
    selected = select_rows(rows)
    # Lock selection before downloading audio or performing conversion/inference.
    raw.write_json(OUTPUT/'selection.json', {'commit': COMMIT, 'selectionRule':
        'First two lexicographic filenames per fixed category, esc10=true, fold=1, distinct src_file',
        'categories': list(CATEGORIES), 'rows': selected, 'inferencePerformed': False})
    pins['selection'] = raw.binding(OUTPUT/'selection.json')
    license_text = (OUTPUT/'LICENSE').read_text()
    clips = []
    (OUTPUT/'original').mkdir(mode=0o700); (OUTPUT/'pcm16').mkdir(mode=0o700)
    for row in selected:
        filename = row['filename']
        original = OUTPUT/'original'/filename
        source_pin = download('audio/'+filename, original)
        target = OUTPUT/'pcm16'/filename
        command = convert(original, target, ffmpeg)
        # Legacy LICENSE keys omit the final category ID and use .ogg.
        attribution_key = '-'.join(filename[:-4].split('-')[:-1])+'.ogg'
        attribution = [line for line in license_text.splitlines() if '['+attribution_key+']' in line]
        require(len(attribution) == 1, 'Exact source attribution missing for '+filename)
        clips.append({'metadata': row, 'original': source_pin, 'converted': raw.binding(target),
                      'conversionCommand': command, 'attribution': attribution[0]})
        pins['original/'+filename] = raw.binding(original)
        pins['converted/'+filename] = raw.binding(target)
    ledger, pins['ledger'] = raw.read_bound_json(fixed.FINAL_LEDGER, fixed.FINAL_LEDGER_SHA)
    job = next(j for j in ledger['jobs'] if j['variant'] == 'unweighted-all-age')
    require(job['state'] == 'complete' and job['replay']['verifiedExact'] is True, 'Head not replayed')
    head = {'bundle': job['output'], 'manifestSha256': job['manifestSha256'], 'variant': job['variant']}
    manifest, pins['headManifest'] = raw.read_bound_json(Path(head['bundle'])/'manifest.json', head['manifestSha256'])
    for name, sha in manifest['filesSha256'].items():
        require(name in raw.inference.FILES, 'Unexpected head bundle file')
        pins['head/'+name] = raw.binding(Path(head['bundle'])/name, sha)
    _, _, _, _, runtime_pins = raw.load_contract(raw.CONTRACT, fixed.CONTRACT_SHA, fixed.SNAPSHOT)
    pins.update({'runtime/'+k: v for k,v in runtime_pins.items()})
    raw.write_json(OUTPUT/'prompt.json', fixed.PROMPT)
    pins['prompt'] = raw.binding(OUTPUT/'prompt.json')
    raw.guard(pins)
    plan = {'schemaVersion': 1, 'declaredAt': datetime.now(timezone.utc).isoformat(), 'commit': COMMIT,
            'clips': clips, 'inputBindings': pins, 'sources': source_pins, 'head': head,
            'ffmpegVersion': subprocess.run([ffmpeg,'-version'],capture_output=True,text=True,check=True).stdout,
            'node': node, 'snapshot': str(fixed.SNAPSHOT), 'contractSha256': fixed.CONTRACT_SHA,
            'prompt': pins['prompt'], 'inferencePerformed': False, 'trainingPerformed': False,
            'device': 'cpu', 'threads': 2, 'repeats': 1}
    raw.write_json(OUTPUT/'plan.json', plan)
    return raw.binding(OUTPUT/'plan.json')


def run(expected_sha):
    plan, pin = raw.read_bound_json(OUTPUT/'plan.json', expected_sha)
    pins = {**plan['inputBindings'], 'plan': pin}
    require(plan['commit'] == COMMIT and plan['inferencePerformed'] is False, 'Unexpected declaration')
    require(pins['source'] == raw.binding(__file__) and pins['gateSource'] == raw.binding(gate.__file__),
            'Challenge or gate source changed')
    require([c['metadata'] for c in plan['clips']] == select_rows(list(csv.DictReader((OUTPUT/'esc50.csv').read_text().splitlines()))),
            'Declared selection differs')
    raw.guard(pins)
    results = OUTPUT/'results'; require(not results.exists(), 'No implicit repeats or resume')
    results.mkdir(mode=0o700)
    outcomes = []
    for clip in plan['clips']:
        raw.guard(pins)
        row = clip['metadata']; destination = results/Path(row['filename']).stem
        args = SimpleNamespace(contract=raw.CONTRACT, contract_sha256=plan['contractSha256'],
            wav=Path(clip['converted']['path']), wav_sha256=clip['converted']['sha256'],
            prompt=Path(plan['prompt']['path']), prompt_sha256=plan['prompt']['sha256'],
            bundle=Path(plan['head']['bundle']), manifest_sha256=plan['head']['manifestSha256'],
            phonetic_snapshot=Path(plan['snapshot']), output=destination, node=plan['node'])
        outcome = {'filename': row['filename'], 'category': row['category'], 'stage': 'raw-adapter'}
        try:
            raw.run(args)
            outcome['rawReport'] = raw.binding(destination/'report.json')
            outcome['stage'] = 'evidence-gate'
            result = gate.filter_report(destination/'report.json', outcome['rawReport']['sha256'], destination/'gated.json')
            outcome.update(pipelineComplete=True, decision=result['decision'], gatedReport=raw.binding(result['report']))
        except Exception as error:
            raw.guard(pins)
            outcome.update(pipelineComplete=False, error=f'{type(error).__name__}: {error}',
                           meaning='Pipeline failure, not abstention')
        outcomes.append(outcome)
        print(json.dumps(outcome), flush=True)
    raw.guard(pins)
    summary = {}
    for category in CATEGORIES:
        group = [o for o in outcomes if o['category'] == category]
        summary[category] = {'total': len(group), 'accepted': sum(o['pipelineComplete'] and o['decision']['ratingAvailable'] for o in group),
            'abstained': sum(o['pipelineComplete'] and not o['decision']['ratingAvailable'] for o in group),
            'pipelineFailures': sum(not o['pipelineComplete'] for o in group)}
    report = {'complete': True, 'plan': pin, 'outcomes': outcomes, 'summary': summary,
              'finishedAt': datetime.now(timezone.utc).isoformat(), 'trainingPerformed': False,
              'thresholdAdjustmentPerformed': False, 'clinicalUseEligible': False, 'learnerFeedbackEligible': False,
              'limitation': 'Environmental categories do not establish absence of incidental speech; this is not VAD ground truth.'}
    raw.write_json(results/'report.json', report)
    return raw.binding(results/'report.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare','run']); parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.command == 'run': require(args.sha256 is not None, 'Plan SHA required')
    print(json.dumps(declare() if args.command == 'declare' else run(args.sha256), indent=2))
