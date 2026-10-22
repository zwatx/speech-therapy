"""Metadata-only selection and historical-use audit."""
import csv
import hashlib
import re
from pathlib import Path

import multiphone_research_audio as raw

COMMIT = '33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6'
SALT = 'nonspeech-v1'
GROUPS = {
    'vocalization': ('coughing', 'sneezing', 'breathing', 'snoring', 'laughing', 'crying_baby'),
    'human_activity': ('clapping', 'footsteps', 'brushing_teeth', 'drinking_sipping'),
    'animal': ('dog', 'cat'),
    'household': ('door_wood_knock', 'keyboard_typing', 'vacuum_cleaner'),
}
CATEGORIES = tuple(c for group in GROUPS.values() for c in group)
ROOT = raw.HERE/'outputs/multiphone-20260927'
PRIOR = {
    'environment-v1/selection.json': '8c35fe5fe55fe4ca702688d2ddd16f3e589b40a2f3742ead5f28550359528a03',
    'environment-extension-v1/selection.json': '4d3e491f53ed3c1d3b59af73ae67dbe3d9d03e0a9305446a1c6a62f6c9597a53',
    'yamnet-speech-v1/acquisition/selection.json': 'dfeab9e8756f16d2069e7bc7f5036c89d3d58bf220372f227396d35b29d32853',
}
ESC_NAME = re.compile(r'(?<![\w-])([1-5]-\d+-[A-Z]+-\d+\.wav)(?![\w.])')
TEXT_SUFFIXES = {'.json', '.jsonl', '.txt', '.md', '.csv', '.log', '.ts', '.py', '.yaml', '.yml'}
RULE = ('Fixed category order; eligible folds 2/3/5 minus historical src_file; rank sources '
        'by SHA256 UTF8 nonspeech-v1|src_file then src_file; take four skipping sources '
        'chosen by earlier categories; lexicographically smallest take per source')
REVISION = ('Metadata-only revision: fold5-only leaves three dog sources. Pool folds 2/3/5, '
            'exclude all 60 historical clips by src_file; include crying_baby before audio.')


def metadata(path):
    rows = list(csv.DictReader(Path(path).read_text().splitlines()))
    raw.require(rows and len({r['filename'] for r in rows}) == len(rows), 'Duplicate/empty metadata')
    for row in rows:
        raw.require(ESC_NAME.fullmatch(row['filename']) and row['src_file'] and row['take']
                    and row['fold'] in ('1', '2', '3', '4', '5')
                    and row['esc10'].lower() in ('true', 'false'), 'Invalid ESC metadata')
    return rows


def select_rows(rows, excluded):
    raw.require(len({r['filename'] for r in rows}) == len(rows), 'Duplicate metadata filenames')
    chosen, seen = [], set(excluded)
    for category in CATEGORIES:
        by_source = {}
        for row in rows:
            if row['fold'] in ('2', '3', '5') and row['category'] == category and row['src_file'] not in seen:
                by_source.setdefault(row['src_file'], []).append(row)
        ranked = sorted(by_source, key=lambda source: (
            hashlib.sha256((SALT+'|'+source).encode('utf-8')).hexdigest(), source))
        raw.require(len(ranked) >= 4, 'Insufficient unused sources for '+category)
        for source in ranked[:4]:
            takes = by_source[source]
            raw.require(len({r['take'] for r in takes}) == len(takes), 'Ambiguous source take')
            chosen.append(min(takes, key=lambda row: row['take']))
            seen.add(source)
    raw.require(len(chosen) == len({r['src_file'] for r in chosen}) == 60, 'Expected 60 unique sources')
    return chosen


def scan_historical(root, rows, prior=PRIOR):
    """Scan every folder, file names and textual records, excluding master metadata."""
    root = Path(root)
    by_name = {r['filename']: r for r in rows}
    expected, pins = set(), {}
    for relative, sha in prior.items():
        record, pins['prior/'+relative] = raw.read_bound_json(root/relative, sha)
        raw.require(record['commit'] == COMMIT, 'Historical ESC commit differs')
        names = [r['filename'] for r in record['rows']]
        raw.require(len(names) == len(set(names)), 'Duplicate historical selection')
        for row in record['rows']:
            raw.require(by_name.get(row['filename']) == row, 'Historical metadata differs')
        expected.update(names)
    raw.require(len(expected) == 60, 'Historical selection union must contain exactly 60 files')
    found, evidence = set(), {}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.name == 'esc50.csv':
            continue
        names = set(ESC_NAME.findall(path.name))
        if path.suffix.lower() in TEXT_SUFFIXES:
            # Some historical JSON arrays are several GB. Keep only a bounded overlap.
            with path.open('rb') as stream:
                overlap = b''
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    payload = overlap+chunk
                    # Numeric historical arrays cannot match without this literal suffix.
                    # Check bytes first while retaining overlap for boundary-spanning names.
                    if b'.wav' in payload:
                        text = payload.decode('utf-8', errors='replace')
                        # Defer a chunk-end match until its trailing boundary is known.
                        names.update(match[1] for match in ESC_NAME.finditer(text) if match.end() < len(text))
                    overlap = payload[-256:]
                names.update(ESC_NAME.findall(overlap.decode('utf-8', errors='replace')))
            if names:
                pins['scan/'+str(path.relative_to(root))] = raw.binding(path)
        if names:
            evidence[str(path.relative_to(root))] = sorted(names)
            found.update(names)
    raw.require(found == expected, 'Recursive historical scan differs from the 60-file selection union')
    raw.require(found <= set(by_name), 'Historical ESC filename missing from metadata')
    return dict(filenames=sorted(found), excludedSources=sorted({by_name[n]['src_file'] for n in found}),
                evidence=evidence), pins


def attribution(row, license_text):
    key = '-'.join(row['filename'][:-4].split('-')[:-1])+'.ogg'
    lines = [line for line in license_text.splitlines() if '['+key+']' in line]
    raw.require(len(lines) == 1, 'Exact Freesound attribution missing: '+row['filename'])
    line = lines[0]
    match = re.search(r'\((https?://[^)]+)\) by (.+) \[([^]]+)\]', line)
    raw.require(match is not None, 'Unparseable Freesound attribution')
    return dict(text=line, sourceUrl=match[1], creator=match[2], originalLicense=match[3],
                datasetLicense='CC BY 3.0' if row['esc10'].lower() == 'true' else 'CC BY-NC 3.0',
                use='strictly noncommercial research; no redistribution')
