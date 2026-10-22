"""Proposed Part-1 selection from supplied metadata only; no corpus discovery."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

SALT = 'percept-r-external-v1'
CAP = 40
VOWELS = frozenset('AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW'.split())
CONSONANTS = frozenset('B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG ZH'.split())
TOKEN_FIELDS = {'childId', 'tokenId', 'folder', 'session', 'recordId', 'ageYears',
                'phones', 'startSeconds', 'endSeconds'}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare_selection(payload):
    """Return deterministic proposed selection and every input-row disposition.

    Caller supplies the complete reserved child roster and complete structural
    metadata. This function cannot establish either input's corpus completeness.
    It never reads files except its own source for the receipt, and never joins
    ratings, decodes audio, invokes models, or authorizes a scientific run.
    """
    _require(isinstance(payload, dict) and set(payload) == {'children', 'tokens'}, 'Invalid selection shape')
    _require(isinstance(payload['children'], list) and bool(payload['children']), 'Missing child roster')
    children = []
    for child in payload['children']:
        _require(isinstance(child, dict) and set(child) == {'childId'}, 'Invalid child record')
        identity = child['childId']
        _require(isinstance(identity, str) and re.fullmatch(r'[1-9][0-9]*', identity) is not None,
                 'Child ID must be a canonical positive numeric string')
        children.append(identity)
    _require(len(set(children)) == len(children), 'Duplicate child ID')
    children.sort()
    _require(isinstance(payload['tokens'], list), 'Invalid token list')
    rows = []
    seen = set()
    for supplied in payload['tokens']:
        _require(isinstance(supplied, dict) and set(supplied) == TOKEN_FIELDS, 'Invalid metadata fields')
        _require(supplied['childId'] in children, 'Token outside child roster')
        for field in ('folder', 'session', 'recordId'):
            _require(isinstance(supplied[field], str) and
                     re.fullmatch(r'[A-Za-z0-9_.-]+', supplied[field]) is not None,
                     'Invalid structural identity')
        _require(supplied['folder'].rsplit('_', 1)[-1] == supplied['childId'], 'Folder child differs')
        identity = '/'.join(supplied[field] for field in ('folder', 'session', 'recordId'))
        _require(supplied['tokenId'] == identity and identity not in seen, 'Invalid or duplicate token identity')
        seen.add(identity)
        _require(type(supplied['ageYears']) is int and 6 <= supplied['ageYears'] <= 12, 'Age outside scope')
        for field in ('startSeconds', 'endSeconds'):
            _require(_finite(supplied[field]), 'Invalid segment')
        _require(0 <= supplied['startSeconds'] < supplied['endSeconds'], 'Invalid segment range')
        phones = supplied['phones']
        _require(isinstance(phones, list) and bool(phones) and all(isinstance(p, str) and p for p in phones),
                 'Missing phones')
        eligible = phones.count('R') == 1 and not any(p.startswith('ER') for p in phones)
        unmappable = [p for p in phones if re.fullmatch(r'[A-Z]+[012]?', p) is None or
                      not (re.sub(r'[012]$', '', p) in VOWELS or p in CONSONANTS)]
        # Historical recipe rounds duration to six decimals before the reader test.
        seconds = round(supplied['endSeconds'] - supplied['startSeconds'], 6)
        _require(math.isfinite(seconds), 'Invalid segment duration')
        rank = hashlib.sha256(f"{SALT}|{supplied['folder']}|{supplied['session']}|{supplied['recordId']}".encode()).hexdigest()
        rows.append({**supplied, 'phones': list(phones), 'durationSeconds': seconds,
                     'eligible': eligible, 'selectionRankSha256': rank,
                     'unmappablePhones': unmappable, 'belowReaderMinimum': seconds < .1,
                     'disposition': 'eligible_not_selected' if eligible else 'ineligible_single_consonantal_r'})
    rows.sort(key=lambda row: (row['childId'], row['tokenId']))
    child_reports = []
    for child in children:
        all_rows = [row for row in rows if row['childId'] == child]
        eligible = [row for row in all_rows if row['eligible']]
        selected = sorted(eligible, key=lambda row: (row['selectionRankSha256'], row['tokenId']))[:CAP]
        for row in selected:
            row['disposition'] = 'selected'
        child_reports.append({'childId': child, 'suppliedTokens': len(all_rows), 'eligibleTokens': len(eligible),
                              'selectedTokenIds': [row['tokenId'] for row in selected],
                              'reason': None if selected else 'no_eligible_tokens'})
    selected = [row for row in rows if row['disposition'] == 'selected']
    canonical_input = {'children': [{'childId': child} for child in children],
                       'tokens': [{field: row[field] for field in TOKEN_FIELDS} for row in rows]}
    membership = [{'childId': child['childId'], 'tokenIds': child['selectedTokenIds']} for child in child_reports]
    return {'schemaVersion': 1, 'status': 'prepared_selection_not_study_declaration',
            'researchOnly': True, 'learnerFeedbackEligible': False, 'clinicalUseEligible': False,
            'productionUseEligible': False, 'inputSha256': _digest(canonical_input),
            'selectedMembershipSha256': _digest(membership),
            'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'recipe': {'salt': SALT, 'perChildCap': CAP, 'order': 'lexical child ID; hash rank then token ID',
                       'eligibility': 'exactly one R and no phone beginning ER',
                       'unmappableExclusion': 'after capped selection, counted with no substitution',
                       'belowReaderMinimum': 'selected duration rounded to six decimals < 0.1, downstream failure',
                       'mapping': {'vowels': sorted(VOWELS), 'consonants': sorted(CONSONANTS)}},
            'counts': {'fullChildDenominator': len(children), 'suppliedTokens': len(rows),
                       'eligibleTokens': sum(row['eligible'] for row in rows), 'selectedTokens': len(selected),
                       'unselectedEligibleTokens': sum(row['disposition'] == 'eligible_not_selected' for row in rows),
                       'preAudioUnmappableTokens': sum(bool(row['unmappablePhones']) for row in selected),
                       'belowReaderMinimumTokens': sum(row['belowReaderMinimum'] for row in selected)},
            'children': child_reports, 'tokens': rows,
            'limitations': ['Caller must separately verify complete structural metadata and reserved roster.',
                            'No real reserved metadata was used in synthetic verification.',
                            'Prepared mapping/eligibility applicability requires the new declaration.',
                            'Numeric IDs do not establish biological or household independence.']}
