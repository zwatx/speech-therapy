"""Declare and acquire a fixed source-disjoint ESC-10 extension; no inference."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

import multiphone_environment_challenge as original

raw = original.raw
require = raw.require
COMMIT = original.COMMIT
CATEGORIES = original.CATEGORIES
PRIOR = original.OUTPUT/'plan.json'
PRIOR_SHA = '1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9'
OUTPUT = raw.HERE/'outputs/multiphone-20260927/environment-extension-v1'
PROTOCOL = raw.HERE/'../../docs/model/multiphone-environment-extension-protocol.md'
RULE = ('Fixed category order; first four lexicographic filenames per category with esc10=true, '
        'fold=4, globally distinct src_file, excluding all prior twelve src_file values')


def select_rows(rows, excluded):
    require(len({r['filename'] for r in rows}) == len(rows), 'Duplicate metadata filenames')
    selected, seen = [], set(excluded)
    for category in CATEGORIES:
        candidates = sorted((r for r in rows if r['esc10'].lower() == 'true'
                             and r['fold'] == '4' and r['category'] == category), key=lambda r: r['filename'])
        chosen = []
        for row in candidates:
            name = row['filename']
            require(Path(name).name == name and name.endswith('.wav') and '\\' not in name,
                    'Unsafe audio filename')
            require(bool(row['src_file']), 'Missing source identifier')
            if row['src_file'] not in seen:
                chosen.append(row); seen.add(row['src_file'])
            if len(chosen) == 4: break
        require(len(chosen) == 4, 'Insufficient distinct ESC10 fold4 sources for '+category)
        selected.extend(chosen)
    require(len(selected) == 24 and len({r['src_file'] for r in selected}) == 24,
            'Expected exactly 24 unique sources')
    return selected


def attribution(row, license_text):
    key = '-'.join(row['filename'][:-4].split('-')[:-1])+'.ogg'
    lines = [line for line in license_text.splitlines() if '['+key+']' in line]
    require(len(lines) == 1, 'Exact source attribution missing for '+row['filename'])
    return lines[0]


def declare():
    require(not OUTPUT.exists(), 'Fresh extension output required')
    prior, prior_pin = raw.read_bound_json(PRIOR, PRIOR_SHA)
    require(prior['commit'] == COMMIT and len(prior['clips']) == 12, 'Unexpected prior challenge')
    ffmpeg = shutil.which('ffmpeg')
    require(ffmpeg is not None, 'ffmpeg required')
    pins = {'priorPlan': prior_pin, 'source': raw.binding(__file__),
            'tests': raw.binding(raw.HERE/'test_multiphone_environment_extension.py'),
            'protocol': raw.binding(PROTOCOL), 'conversionHelper': raw.binding(original.__file__),
            'bindingHelper': raw.binding(raw.__file__), 'ffmpeg': raw.binding(ffmpeg)}
    for key in ('meta/esc50.csv', 'LICENSE', 'README.md'):
        pins[key] = prior['inputBindings'][key]
    raw.guard(pins)
    excluded = sorted({c['metadata']['src_file'] for c in prior['clips']})
    require(len(excluded) == 12, 'Prior sources are not twelve distinct sources')
    rows = list(csv.DictReader(Path(pins['meta/esc50.csv']['path']).read_text().splitlines()))
    selected = select_rows(rows, excluded)
    license_text = Path(pins['LICENSE']['path']).read_text()
    attributions = {r['filename']: attribution(r, license_text) for r in selected}
    declaration = {'schemaVersion': 1, 'declaredAt': datetime.now(timezone.utc).isoformat(),
        'commit': COMMIT, 'selectionRule': RULE, 'categories': list(CATEGORIES), 'rows': selected,
        'selectionRevisionReason': 'Metadata-only feasibility check: fold2 helicopter has two distinct sources; fold3 has three. Fold4 is the first single fresh fold with at least four sources in every fixed category. Revised before any audio download or inference.',
        'excludedPriorSources': excluded, 'attributions': attributions, 'inputBindings': pins,
        'sources': {k: prior['sources'][k] for k in ('meta/esc50.csv', 'LICENSE', 'README.md')},
        'ffmpegVersion': subprocess.run([ffmpeg, '-version'], capture_output=True, text=True, check=True).stdout,
        'inferencePerformed': False, 'trainingPerformed': False}
    raw.guard(pins)
    OUTPUT.mkdir(parents=True, mode=0o700)
    raw.write_json(OUTPUT/'selection.json', declaration)
    (OUTPUT/'selection.json').chmod(0o400)
    return raw.binding(OUTPUT/'selection.json')


def acquire(expected_sha):
    selection, selection_pin = raw.read_bound_json(OUTPUT/'selection.json', expected_sha)
    pins = {**selection['inputBindings'], 'selection': selection_pin}
    raw.guard(pins)
    require(pins['source'] == raw.binding(__file__) and selection['commit'] == COMMIT
            and selection['selectionRule'] == RULE, 'Unexpected extension declaration')
    rows = list(csv.DictReader(Path(pins['meta/esc50.csv']['path']).read_text().splitlines()))
    require(selection['rows'] == select_rows(rows, selection['excludedPriorSources']), 'Selection differs')
    require(not (OUTPUT/'original').exists() and not (OUTPUT/'pcm16').exists()
            and not (OUTPUT/'plan.json').exists(), 'No implicit resume or overwrite')
    (OUTPUT/'original').mkdir(mode=0o700); (OUTPUT/'pcm16').mkdir(mode=0o700)
    clips = []
    for row in selection['rows']:
        raw.guard(pins)
        filename = row['filename']
        source = OUTPUT/'original'/filename
        source_pin = original.download('audio/'+filename, source)
        target = OUTPUT/'pcm16'/filename
        command = original.convert(source, target, pins['ffmpeg']['path'])
        clips.append({'metadata': row, 'original': source_pin, 'converted': raw.binding(target),
                      'conversionCommand': command, 'attribution': selection['attributions'][filename]})
        pins['original/'+filename] = raw.binding(source)
        pins['converted/'+filename] = raw.binding(target)
    require(len(clips) == 24, 'Expected 24 valid clips')
    raw.guard(pins)
    plan = {'schemaVersion': 1, 'declaredAt': selection['declaredAt'], 'commit': COMMIT,
            'acquiredAt': datetime.now(timezone.utc).isoformat(), 'selectionRule': RULE,
            'clips': clips, 'inputBindings': pins, 'sources': selection['sources'],
            'ffmpegVersion': selection['ffmpegVersion'], 'inferencePerformed': False,
            'trainingPerformed': False, 'clinicalUseEligible': False,
            'limitation': 'Fresh to this experiment and src_file-disjoint from the prior twelve; '
                          'not guaranteed disjoint from pretrained model training data. '
                          'Environmental labels are not speech ground truth.'}
    raw.write_json(OUTPUT/'plan.json', plan)
    (OUTPUT/'plan.json').chmod(0o400)
    return raw.binding(OUTPUT/'plan.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare', 'acquire'])
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.command == 'acquire': require(args.sha256 is not None, 'Selection SHA required')
    print(json.dumps(declare() if args.command == 'declare' else acquire(args.sha256), indent=2))
