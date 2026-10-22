"""Compile the fixed public catalog into an entirely pending review addendum.

Catalog-declared source paths are retained metadata in the frozen adapter. They
are never opened here. This compiler establishes no rights, reference bytes,
professional approval, learner findings or clinical/production readiness.
"""
import hashlib
import json
import math
from pathlib import Path

from workbench.content import prepare_content_manifest
from workbench.domain import ValidationError, semantic_digest

PUBLIC_PACK_SHA256 = 'a957a9e3291f0d90b275d40cd914890836ee7e6fc4fd361f7589cd1444587ef3'
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_NUMBER_CHARACTERS = 128
REQUIREMENTS = (
    'reference_variety', 'acceptable_variants', 'occurrence_rule', 'age_readiness',
    'adult_support', 'reference_provenance', 'reference_rights', 'reference_scope',
    'illustration_meaning_rights', 'cue_instruction_safety', 'controlled_professional_record',
)
_CLAIM_FIELDS = (
    'qualifiedApprovalEstablished', 'referenceAudioVerified', 'rightsVerified',
    'learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible',
)


class PacketError(ValueError):
    """A fixed safe code; never carries paths, source values or supplied JSON."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PacketError('invalid_json')
        result[key] = value
    return result


def _constant(value):
    raise PacketError('invalid_json')


def _integer(value):
    if len(value) > MAX_NUMBER_CHARACTERS:
        raise PacketError('invalid_json')
    return int(value)


def _float(value):
    if len(value) > MAX_NUMBER_CHARACTERS:
        raise PacketError('invalid_json')
    number = float(value)
    if not math.isfinite(number):
        raise PacketError('invalid_json')
    return number


def strict_json(raw: bytes | str):
    """Parse at most 8 MiB of strict UTF-8 JSON with bounded numeric tokens.

    Duplicate keys, nonfinite/oversized numbers, invalid Unicode and excessive
    nesting fail with one safe code. Scalar JSON is accepted at this parse seam;
    compiler/evidence validation supplies the exact domain schemas.
    """
    try:
        if type(raw) is bytes:
            if len(raw) > MAX_JSON_BYTES:
                raise PacketError('invalid_json')
            text = raw.decode('utf-8')
        elif type(raw) is str:
            if len(raw) > MAX_JSON_BYTES or len(raw.encode('utf-8')) > MAX_JSON_BYTES:
                raise PacketError('invalid_json')
            text = raw
        else:
            raise PacketError('invalid_json')
        parsed = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant,
                            parse_int=_integer, parse_float=_float)
        # Exact finite JSON semantics also reject escaped unpaired surrogates.
        semantic_digest(parsed)
        return parsed
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise PacketError('invalid_json') from None


def _pin(pack_bytes):
    if (type(pack_bytes) is not bytes or len(pack_bytes) > MAX_JSON_BYTES
            or hashlib.sha256(pack_bytes).hexdigest() != PUBLIC_PACK_SHA256):
        raise PacketError('source_pack_drift')


def load_pack_bytes() -> bytes:
    """Read only the fixed public pack, enforce its exact byte pin, return bytes."""
    path = Path(__file__).resolve().parents[3] / 'docs/consumer-assessment/proposed-engineering-pack.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
    except OSError:
        raise PacketError('source_pack_unavailable') from None
    _pin(raw)
    return raw


def _prepared(pack_bytes):
    _pin(pack_bytes)
    pack = strict_json(pack_bytes)
    try:
        manifest = prepare_content_manifest(pack_bytes)
    except ValidationError:
        raise PacketError('invalid_packet') from None
    return pack, manifest


def load_pack() -> dict:
    """Return a fresh, validated metadata object from the fixed pinned pack."""
    pack, _ = _prepared(load_pack_bytes())
    return pack


def source_manifest() -> dict:
    """Return the frozen preparation manifest for only the fixed pinned source."""
    _, manifest = _prepared(load_pack_bytes())
    return manifest


def _selected_cluster(source):
    # Only the two named catalog contexts are described; no clinical inference.
    for phones, indexes in zip(source['pronunciationVariants'], source['selectedPositionIndexesByVariant']):
        if source['id'] == 'r-middle-bread' and any(
                index > 0 and phones[index - 1:index + 1] == ['B', 'R'] for index in indexes):
            return True
        if source['id'] == 's-beginning-sky' and any(
                phones[index:index + 2] == ['S', 'K'] for index in indexes):
            return True
    return False


def _prompt(source):
    issues = []
    if source['variantCount'] > 1:
        issues.append('variant_choice')
    if source['repeatedTargetInAnyVariant']:
        issues.append('repeated_target')
    if any(len(indexes) > 1 for indexes in source['selectedPositionIndexesByVariant']):
        issues.append('selected_occurrence_ambiguous')
    if source['word'] != source['sourceWord']:
        issues.append('source_spelling_alias')
    if not source['modelInventorySupported']:
        issues.append('unsupported_target')
    if _selected_cluster(source):
        issues.append('cluster_context')
    issues.extend(('reference_variety_pending', 'professional_review_pending'))
    return {
        'id': source['id'], 'word': source['word'], 'sourceWord': source['sourceWord'],
        'lexicalGroup': source['sourceWord'].strip().casefold(), 'targetPhone': source['targetPhone'],
        'position': source['position'], 'modelInventorySupported': source['modelInventorySupported'],
        'modelTargetId': source['modelTargetID'], 'status': 'pending', 'issues': issues,
        'variants': [
            {'id': 'variant-' + str(index + 1), 'phones': list(phones),
             'allTargetIndexes': list(source['targetIndexesByVariant'][index]),
             'selectedPositionIndexes': list(source['selectedPositionIndexesByVariant'][index])}
            for index, phones in enumerate(source['pronunciationVariants'])
        ], 'requirements': list(REQUIREMENTS),
    }


def compile_packet(pack_bytes: bytes) -> dict:
    """Return deterministic preparation metadata; byte drift precedes parsing."""
    pack, manifest = _prepared(pack_bytes)
    prompts = [_prompt(source) for source in pack['prompts']]
    variants = [variant for prompt in prompts for variant in prompt['variants']]
    counts = {'prompts': len(prompts), 'distinctSourceWords': len({p['lexicalGroup'] for p in prompts}),
              'variants': len(variants), 'allTargetOccurrences': sum(len(v['allTargetIndexes']) for v in variants),
              'selectedPositionOccurrences': sum(len(v['selectedPositionIndexes']) for v in variants)}
    return {
        'schemaVersion': 1, 'kind': 'content-review-preparation', 'sourcePackSha256': PUBLIC_PACK_SHA256,
        'sourceManifestSha256': semantic_digest(manifest), 'projectId': manifest['projectId'],
        'status': 'all_professional_review_pending',
        'scope': {'minAge': 6, 'maxAge': 12, 'intendedLanguage': 'en', 'referenceVariety': 'pending',
                  'use': 'engineering_preparation_only'},
        'counts': counts,
        'controlledWorkflow': {
            'handoff': 'docs/model/slp-handoff.md',
            'worksheet': 'docs/consumer-assessment/proposed-engineering-pack.md',
            'annotationPreparation': 'docs/consumer-assessment/annotation-data-preparation.md',
            'meaning': 'Links to existing controlled records; no new approval authority',
        },
        'prompts': prompts, 'claimLimits': {field: False for field in _CLAIM_FIELDS},
    }


def validate_packet(packet) -> None:
    """Accept only the exact current compiler result, including JSON field types."""
    expected = compile_packet(load_pack_bytes())
    try:
        matches = semantic_digest(packet) == semantic_digest(expected)
    except (ValidationError, ValueError, TypeError, RecursionError, OverflowError):
        raise PacketError('invalid_packet') from None
    if not matches:
        raise PacketError('invalid_packet')
