"""Prepare pending content metadata from a supplied public catalog snapshot.

This adapter receives bytes and never opens catalog-declared source paths. Its
source hashes pin the catalog-derived pack bytes, not a raw dictionary file.
Historical catalogSourceHashes remain upstream declarations, not current mobile
source verification or qualified content approval.
"""

import hashlib
import json
import re

from .domain import ValidationError, bind_manifest, semantic_digest


_PROMPT_FIELDS = frozenset('''
    id intendedUse learnerFindingEligible modelInventorySupported modelTargetID
    multipleOccurrencesAtSelectedPosition position pronunciationVariants
    repeatedTargetInAnyVariant reviewStatus selectedIndexesDifferAcrossVariants
    selectedPositionIndexesByVariant soundID sourceWord targetIndexesByVariant
    targetPhone variantCount word
'''.split())


def _shape(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValidationError('invalid_content_shape')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError('invalid_content_json')
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ValidationError('invalid_content_json')


def _parse(pack_bytes):
    if type(pack_bytes) is not bytes:
        raise ValidationError('invalid_content_bytes')
    try:
        pack = json.loads(pack_bytes.decode('utf-8'), object_pairs_hook=_unique_object,
                          parse_constant=_reject_nonfinite)
        semantic_digest(pack)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('invalid_content_json') from error
    return pack


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValidationError('invalid_content_metadata')


def _indexes(value, expected):
    if (type(value) is not list or any(type(index) is not int for index in value)
            or value != expected):
        raise ValidationError('invalid_content_indexes')


def _validate_prompt(prompt):
    _shape(prompt, _PROMPT_FIELDS)
    if (prompt['reviewStatus'] != 'pending' or prompt['learnerFindingEligible'] is not False
            or prompt['intendedUse'] != 'internal engineering exercise only'):
        raise ValidationError('content_not_pending')
    for field in ('id', 'word', 'sourceWord', 'soundID', 'targetPhone'):
        _text(prompt[field])
    if prompt['position'] not in ('beginning', 'middle', 'end'):
        raise ValidationError('invalid_content_metadata')
    variants = prompt['pronunciationVariants']
    count = prompt['variantCount']
    if type(variants) is not list or not variants or type(count) is not int or count != len(variants):
        raise ValidationError('invalid_content_variants')
    for field in ('targetIndexesByVariant', 'selectedPositionIndexesByVariant'):
        if type(prompt[field]) is not list or len(prompt[field]) != count:
            raise ValidationError('invalid_content_variants')
    targets_by_variant = []
    selected_by_variant = []
    for index, phones in enumerate(variants):
        if type(phones) is not list or not phones or any(type(phone) is not str for phone in phones):
            raise ValidationError('invalid_content_variants')
        targets = [i for i, phone in enumerate(phones) if phone.rstrip('012') == prompt['targetPhone']]
        if not targets:
            raise ValidationError('invalid_content_indexes')
        selected = [i for i in targets if {
            'beginning': i == 0, 'middle': 0 < i < len(phones) - 1,
            'end': i == len(phones) - 1,
        }[prompt['position']]]
        if not selected:
            raise ValidationError('invalid_content_indexes')
        _indexes(prompt['targetIndexesByVariant'][index], targets)
        _indexes(prompt['selectedPositionIndexesByVariant'][index], selected)
        targets_by_variant.append(targets)
        selected_by_variant.append(selected)
    expected_flags = {
        'repeatedTargetInAnyVariant': any(len(targets) > 1 for targets in targets_by_variant),
        'multipleOccurrencesAtSelectedPosition': any(len(selected) > 1 for selected in selected_by_variant),
        'selectedIndexesDifferAcrossVariants': len({tuple(selected) for selected in selected_by_variant}) > 1,
    }
    for field, expected in expected_flags.items():
        if type(prompt[field]) is not bool or prompt[field] != expected:
            raise ValidationError('invalid_content_metadata')
    supported = prompt['modelInventorySupported']
    model_id = prompt['modelTargetID']
    if (type(supported) is not bool or (supported and (type(model_id) is not int or model_id < 0))
            or (not supported and model_id is not None)):
        raise ValidationError('invalid_content_metadata')


def _validate_pack(pack):
    _shape(pack, ('schemaVersion', 'status', 'catalogSourceHashes', 'prompts'))
    if type(pack['schemaVersion']) is not int or pack['schemaVersion'] != 1:
        raise ValidationError('invalid_content_schema')
    if pack['status'] != 'PROPOSED / ALL REVIEW PENDING':
        raise ValidationError('content_not_pending')
    if type(pack['prompts']) is not list or not pack['prompts']:
        raise ValidationError('invalid_content_shape')
    declarations = pack['catalogSourceHashes']
    if type(declarations) is not list or not declarations:
        raise ValidationError('invalid_content_shape')
    paths = set()
    for declaration in declarations:
        _shape(declaration, ('path', 'sha256'))
        _text(declaration['path'])
        if (type(declaration['sha256']) is not str
                or not re.fullmatch(r'[0-9a-f]{64}', declaration['sha256'])
                or declaration['path'] in paths):
            raise ValidationError('invalid_content_metadata')
        paths.add(declaration['path'])
    for prompt in pack['prompts']:
        _validate_prompt(prompt)


def prepare_content_manifest(pack_bytes: bytes) -> dict:
    """Return a validated preparation manifest with zero enrolled attempts.

    Lexical groups normalize sourceWord by stripping surrounding whitespace and
    Unicode case-folding. Word display, pronunciation variants and every target
    occurrence remain as supplied. All content and task definitions stay pending.
    """
    pack = _parse(pack_bytes)
    _validate_pack(pack)
    sha = hashlib.sha256(pack_bytes).hexdigest()
    version = 'catalog-pack-' + sha
    prompts = []
    for source in pack['prompts']:
        prompts.append({
            'id': source['id'], 'version': version, 'word': source['word'],
            'lexicalGroup': source['sourceWord'].strip().casefold(), 'language': 'en',
            'targetPhone': source['targetPhone'],
            'variants': [{'id': 'variant-' + str(index + 1), 'phones': phones,
                          'occurrenceIndexes': source['targetIndexesByVariant'][index]}
                         for index, phones in enumerate(source['pronunciationVariants'])],
            'source': {'kind': 'dictionary_snapshot', 'sha256': sha},
            'engineeringStatus': 'pending',
        })
    return bind_manifest({
        'schemaVersion': 1, 'projectId': 'content-preparation-' + sha[:16],
        'title': 'Public prompt content preparation', 'mode': 'preparation',
        'task': {'id': 'catalog-content-review', 'version': version,
                 'referenceVariety': 'pending', 'definitionSource': 'pending',
                 'controlledReviewRecord': {
                     'sourcePackSha256': sha, 'sourcePackStatus': pack['status'],
                     'snapshotMeaning': 'catalog-derived public pack bytes; not a raw dictionary digest',
                     'catalogSourceHashes': pack['catalogSourceHashes'],
                     'catalogSourceHashesMeaning': 'retained upstream declarations; source paths were not opened',
                     'lexicalGroupNormalization': 'sourceWord.strip().casefold()',
                     'currentSourceVerificationEstablished': False,
                     'qualifiedReviewEstablished': False,
                     'learnerFeedbackEligible': False, 'clinicalUseEligible': False,
                     'productionUseEligible': False,
                 }},
        'policy': {'id': 'engineering-ages-6-12', 'version': 'v1',
                   'allowedAges': [6, 12], 'intendedLanguage': 'en'},
        'prompts': prompts, 'participants': [], 'attempts': [],
    })
