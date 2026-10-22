"""Pure, synthetic-first manifest validation and engineering evidence gates."""

import copy
import hashlib
import json
import math
import re


class ValidationError(ValueError):
    """A fixed, safe error code suitable for a local API response."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _json_value(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValidationError('invalid_json')


def semantic_digest(value):
    """Digest exact finite JSON semantics; this does not establish authenticity."""
    try:
        _json_value(value)
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('invalid_json') from error
    return hashlib.sha256(encoded).hexdigest()


_SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_VOWELS = frozenset('AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW'.split())
_CONSONANTS = frozenset('B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH'.split())
_TARGETS = _VOWELS | _CONSONANTS
_TERMINALS = ('processed_unverified', 'rejected', 'cancelled', 'failed', 'skipped')
_SPLITS = ('development', 'calibration', 'evaluation', 'unassigned')


def _shape(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValidationError('invalid_shape')


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValidationError('invalid_value')


def _id(value):
    if type(value) is not str or not _SAFE_ID.fullmatch(value):
        raise ValidationError('invalid_id')


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise ValidationError('invalid_sha256')


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ValidationError('invalid_value')


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError('invalid_value')


def _roster(value):
    if type(value) is not list:
        raise ValidationError('invalid_shape')
    seen = set()
    for record in value:
        if type(record) is not dict or 'id' not in record:
            raise ValidationError('invalid_shape')
        _id(record['id'])
        if record['id'] in seen:
            raise ValidationError('duplicate_id')
        seen.add(record['id'])


def _manifest_shape(manifest, binding=False):
    semantic_digest(manifest)
    _shape(manifest, 'schemaVersion projectId title mode task policy prompts participants attempts')
    if type(manifest['schemaVersion']) is not int or manifest['schemaVersion'] != 1:
        raise ValidationError('invalid_schema_version')
    _id(manifest['projectId'])
    _text(manifest['title'])
    _enum(manifest['mode'], ('synthetic', 'preparation'))
    task = manifest['task']
    _shape(task, 'id version referenceVariety controlledReviewRecord definitionSource')
    _id(task['id'])
    _text(task['version'])
    _text(task['referenceVariety'])
    if task['controlledReviewRecord'] is not None and type(task['controlledReviewRecord']) is not dict:
        raise ValidationError('invalid_shape')
    _enum(task['definitionSource'], ('synthetic', 'pending'))
    policy = manifest['policy']
    _shape(policy, 'id version allowedAges intendedLanguage')
    _id(policy['id'])
    _text(policy['version'])
    if (type(policy['allowedAges']) is not list or len(policy['allowedAges']) != 2
            or any(type(age) is not int for age in policy['allowedAges'])
            or policy['allowedAges'] != [6, 12] or policy['intendedLanguage'] != 'en'):
        raise ValidationError('invalid_policy')
    for key in ('prompts', 'participants', 'attempts'):
        _roster(manifest[key])
    prompts = {item['id']: item for item in manifest['prompts']}
    participants = {item['id']: item for item in manifest['participants']}
    for prompt in manifest['prompts']:
        _shape(prompt, 'id version word lexicalGroup language targetPhone variants source engineeringStatus')
        for field in ('version', 'word', 'lexicalGroup', 'language'):
            _text(prompt[field])
        _enum(prompt['targetPhone'], _TARGETS)
        _enum(prompt['engineeringStatus'], ('pending', 'accepted', 'revise'))
        _shape(prompt['source'], 'kind sha256')
        _enum(prompt['source']['kind'], ('dictionary_snapshot', 'synthetic'))
        _sha(prompt['source']['sha256'])
        _roster(prompt['variants'])
        if not prompt['variants']:
            raise ValidationError('invalid_variant')
        for variant in prompt['variants']:
            _shape(variant, 'id phones occurrenceIndexes')
            phones = variant['phones']
            if type(phones) is not list or not phones:
                raise ValidationError('invalid_phone')
            for phone in phones:
                if (type(phone) is not str or (phone not in _TARGETS and
                        not (phone[:-1] in _VOWELS and phone[-1:] in ('0', '1', '2')))):
                    raise ValidationError('invalid_phone')
            occurrences = variant['occurrenceIndexes']
            expected = [i for i, phone in enumerate(phones)
                        if phone.rstrip('012') == prompt['targetPhone']]
            if (type(occurrences) is not list or not expected
                    or any(type(index) is not int for index in occurrences) or occurrences != expected):
                raise ValidationError('invalid_occurrences')
    for participant in manifest['participants']:
        _shape(participant, 'id householdId ageYears languageVariety identityLinkage')
        if participant['householdId'] is not None:
            _id(participant['householdId'])
        if participant['ageYears'] is not None:
            _integer(participant['ageYears'], 0, 120)
        _text(participant['languageVariety'])
        _enum(participant['identityLinkage'], ('declared', 'unknown'))
    prior = {}
    for attempt in manifest['attempts']:
        fields = 'id participantId promptId variantId occurrenceIndex sessionId conditionId plannedRepeatOf retryOf split terminal recording permissions'
        _shape(attempt, fields if binding and 'context' not in attempt else fields + ' context')
        for key in ('participantId', 'promptId', 'variantId', 'sessionId', 'conditionId'):
            _id(attempt[key])
        if attempt['participantId'] not in participants or attempt['promptId'] not in prompts:
            raise ValidationError('unknown_reference')
        prompt = prompts[attempt['promptId']]
        variants = {item['id']: item for item in prompt['variants']}
        if attempt['variantId'] not in variants:
            raise ValidationError('unknown_reference')
        occurrence = attempt['occurrenceIndex']
        if occurrence is not None and (type(occurrence) is not int
                or occurrence not in variants[attempt['variantId']]['occurrenceIndexes']):
            raise ValidationError('invalid_occurrence')
        _enum(attempt['split'], _SPLITS)
        _enum(attempt['terminal'], _TERMINALS)
        if attempt['recording'] is not None:
            recording = attempt['recording']
            _shape(recording, 'assetId sha256 durationMs origin')
            _text(recording['assetId'])
            _sha(recording['sha256'])
            duration = recording['durationMs']
            if (type(duration) not in (int, float) or duration < 0
                    or (type(duration) is float and not math.isfinite(duration))):
                raise ValidationError('invalid_duration')
            _enum(recording['origin'], ('synthetic', 'permissioned', 'unknown'))
        permissions = attempt['permissions']
        _shape(permissions, 'version recordSha256 review research withdrawn')
        _text(permissions['version'])
        _sha(permissions['recordSha256'])
        for key in ('review', 'research'):
            _enum(permissions[key], ('allowed', 'denied', 'unknown'))
        if type(permissions['withdrawn']) is not bool:
            raise ValidationError('invalid_value')
        if not binding or attempt.get('context'):
            _shape(attempt['context'], 'taskSha256 policySha256 promptSha256 permissionSha256')
        elif 'context' in attempt and type(attempt['context']) is not dict:
            raise ValidationError('invalid_shape')
        if not binding:
            for pin in attempt['context'].values():
                _sha(pin)
        if attempt['plannedRepeatOf'] is not None and attempt['retryOf'] is not None:
            raise ValidationError('ambiguous_attempt_link')
        for link in ('plannedRepeatOf', 'retryOf'):
            predecessor = attempt[link]
            if predecessor is None:
                continue
            _id(predecessor)
            if predecessor not in prior:
                raise ValidationError('invalid_attempt_link')
            earlier = prior[predecessor]
            fields = ('participantId', 'promptId', 'variantId', 'occurrenceIndex')
            if link == 'retryOf':
                fields += ('conditionId', 'sessionId')
            if any(attempt[field] != earlier[field] for field in fields):
                raise ValidationError('attempt_link_mismatch')
        prior[attempt['id']] = attempt


def _contexts(manifest):
    prompts = {prompt['id']: prompt for prompt in manifest['prompts']}
    return {attempt['id']: {
        'taskSha256': semantic_digest(manifest['task']),
        'policySha256': semantic_digest(manifest['policy']),
        'promptSha256': semantic_digest(prompts[attempt['promptId']]),
        'permissionSha256': semantic_digest(attempt['permissions']),
    } for attempt in manifest['attempts']}


def bind_manifest(manifest):
    """Prepare context pins for an initial import without mutating the caller."""
    _manifest_shape(manifest, binding=True)
    bound = copy.deepcopy(manifest)
    contexts = _contexts(bound)
    for attempt in bound['attempts']:
        attempt['context'] = contexts[attempt['id']]
    return validate_manifest(bound)


def validate_manifest(manifest):
    _manifest_shape(manifest)
    contexts = _contexts(manifest)
    for attempt in manifest['attempts']:
        if attempt['context'] != contexts[attempt['id']]:
            raise ValidationError('context_mismatch')
    return copy.deepcopy(manifest)


def split_diagnostics(manifest):
    """Describe declared leakage and joint isolation limits; never invent a split."""
    manifest = validate_manifest(manifest)
    attempts = manifest['attempts']
    participants = {record['id']: record for record in manifest['participants']}
    prompts = {record['id']: record for record in manifest['prompts']}
    dimensions = {'participants': {}, 'households': {}, 'lexicalGroups': {}}
    membership = []
    for attempt in attempts:
        participant = participants[attempt['participantId']]
        keys = {'participants': participant['id'], 'households': participant['householdId'],
                'lexicalGroups': prompts[attempt['promptId']]['lexicalGroup']}
        links = []
        for dimension, key in keys.items():
            if key is None:
                continue
            dimensions[dimension].setdefault(key, []).append(attempt)
            links.append((dimension, key))
        membership.append(links)
    result = {}
    for dimension, groups in dimensions.items():
        rows = [{'id': key, 'attemptIds': [item['id'] for item in group],
                 'splits': sorted({item['split'] for item in group if item['split'] != 'unassigned'})}
                for key, group in sorted(groups.items())]
        result[dimension] = {'groups': rows,
                             'leakageGroups': [row for row in rows if len(row['splits']) > 1]}
    unknown_identity = sorted(item['id'] for item in participants.values()
                              if item['identityLinkage'] == 'unknown')
    unknown_households = sorted(item['id'] for item in participants.values()
                                if item['householdId'] is None)
    result['unknownIsolation'] = {
        'participantIds': unknown_identity, 'householdParticipantIds': unknown_households,
        'declaredLinkageComplete': not (unknown_identity or unknown_households),
        'isolationEstablished': False,
        'meaning': 'declared_metadata_only',
    }
    parents = list(range(len(attempts)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    first = {}
    for index, links in enumerate(membership):
        for link in links:
            if link in first:
                parents[find(index)] = find(first[link])
            else:
                first[link] = index
    components = {}
    for index, attempt in enumerate(attempts):
        components.setdefault(find(index), []).append(attempt)
    rows = []
    for number, group in enumerate(components.values(), 1):
        participant_ids = sorted({item['participantId'] for item in group})
        rows.append({
            'id': 'component-' + str(number), 'attemptIds': [item['id'] for item in group],
            'participantIds': participant_ids,
            'householdIds': sorted({participants[key]['householdId'] for key in participant_ids
                                    if participants[key]['householdId'] is not None}),
            'lexicalGroups': sorted({prompts[item['promptId']]['lexicalGroup'] for item in group}),
            'splits': sorted({item['split'] for item in group if item['split'] != 'unassigned'}),
        })
    enough = len(rows) >= 3
    result['joint'] = {
        'components': rows, 'componentCount': len(rows),
        'leakingComponents': sum(len(row['splits']) > 1 for row in rows),
        'threeWayIsolation': 'not_established' if enough else 'infeasible',
        'reason': 'allocation_not_validated' if enough else 'fewer_than_three_joint_components',
        'unknownLinkageMayMergeComponents': bool(unknown_identity or unknown_households),
    }
    return result


def admission(aggregate, attemptId):
    """Evaluate engineering gates using original evidence and current restrictions.

    Aggregate review/lock records are supplied by the validated append-only store.
    An adjudication can resolve the target alone. Corpus probabilities never
    substitute for speech, prompt, occurrence, quality, or permission evidence.
    """
    manifest = validate_manifest(aggregate['manifest'])
    attempts = {item['id']: item for item in manifest['attempts']}
    if attemptId not in attempts:
        raise ValidationError('unknown_attempt')
    return _admission(aggregate, manifest, attempts[attemptId])


def _admission(aggregate, manifest, attempt):
    participant = next(item for item in manifest['participants'] if item['id'] == attempt['participantId'])
    prompt = next(item for item in manifest['prompts'] if item['id'] == attempt['promptId'])
    reasons = []
    restrictions = []
    if participant['identityLinkage'] != 'declared':
        reasons.append('identity_linkage_unknown')
    if participant['householdId'] is None:
        reasons.append('household_unknown')
    age = participant['ageYears']
    if age is None:
        reasons.append('age_unknown')
    elif not 6 <= age <= 12:
        reasons.append('age_out_of_scope')
    if participant['languageVariety'] in ('unknown', 'pending', 'und'):
        reasons.append('language_unknown')
    elif participant['languageVariety'] != manifest['task']['referenceVariety']:
        reasons.append('language_variety_mismatch')
    if prompt['language'] != manifest['policy']['intendedLanguage']:
        reasons.append('prompt_language_mismatch')
    if manifest['task']['definitionSource'] != 'synthetic':
        reasons.append('task_definition_pending')
    if prompt['targetPhone'] in ('ER', 'ZH'):
        reasons.append('unsupported_target')
    if attempt['occurrenceIndex'] is None:
        reasons.append('occurrence_not_selected')
    content = next((entry['record'] for entry in reversed(aggregate.get('contentReviews', []))
                    if entry['promptId'] == prompt['id']), None)
    decision = content['decision'] if content else prompt['engineeringStatus']
    if decision != 'accepted':
        reasons.append('content_' + decision)
        if content:
            restrictions.append('content_' + decision)
    if content:
        reference = content.get('reference')
        if reference is not None and reference.get('rights') != 'allowed':
            reasons.append('content_rights_not_allowed')
            restrictions.append('content_rights_not_allowed')
        elif reference is None and (manifest['mode'] != 'synthetic' or prompt['source']['kind'] != 'synthetic'):
            reasons.append('content_reference_missing')
            restrictions.append('content_reference_missing')
    elif manifest['mode'] != 'synthetic' or prompt['source']['kind'] != 'synthetic':
        reasons.append('content_reference_missing')
    permissions = attempt['permissions']
    for key in ('review', 'research'):
        if permissions[key] != 'allowed':
            code = key + '_permission_' + permissions[key]
            reasons.append(code)
            restrictions.append(code)
    if permissions['withdrawn']:
        reasons.append('permission_withdrawn')
        restrictions.append('permission_withdrawn')
    if any(item['participantId'] == participant['id'] for item in aggregate.get('withdrawals', [])):
        reasons.append('current_withdrawal')
        restrictions.append('current_withdrawal')
    if attempt['recording'] is None:
        reasons.append('recording_absent')
    elif attempt['recording']['origin'] == 'unknown':
        reasons.append('recording_origin_unknown')
    if attempt['terminal'] != 'processed_unverified':
        reasons.append('terminal_' + attempt['terminal'])
    lock = aggregate.get('predictionLock')
    if lock is None:
        reasons.append('prediction_not_locked')
    else:
        row = next((row for row in lock['payload']['rows'] if row['attemptId'] == attempt['id']), None)
        if row is None or row['status'] != 'processed':
            reasons.append('model_unavailable')
    originals = []
    for role in ('reviewer-a', 'reviewer-b'):
        record = aggregate.get('reviews', {}).get(role, {}).get(attempt['id'])
        if not record:
            reasons.append(role.replace('-', '_') + '_missing')
        else:
            originals.append(record['answer'])
        if aggregate.get('seals', {}).get(role) is not True:
            reasons.append(role.replace('-', '_') + '_unsealed')
    if len(originals) == 2:
        for field, expected, code in (
            ('speech', 'present', 'speech_not_confirmed'),
            ('promptMatch', 'matched', 'prompt_not_matched'),
            ('occurrence', 'resolved', 'occurrence_not_resolved'),
            ('quality', 'usable', 'quality_not_usable'),
        ):
            if any(answer[field] != expected for answer in originals):
                reasons.append(code)
        target_a, target_b = (answer['target'] for answer in originals)
        adjudication = aggregate.get('adjudications', {}).get(attempt['id'])
        target = adjudication['answer']['target'] if adjudication else target_a
        if not adjudication and target_a != target_b:
            reasons.append('target_disagreement')
        if target not in ('expected', 'altered', 'omitted') or (
                not adjudication and target_b not in ('expected', 'altered', 'omitted')):
            reasons.append('target_unscorable')
    return {
        'status': 'abstain' if reasons else 'engineering_ready',
        'reasons': reasons, 'historicalContext': copy.deepcopy(attempt['context']),
        'currentRestrictions': restrictions,
        'learnerFeedbackEligible': False, 'clinicalUseEligible': False,
        'productionUseEligible': False,
    }
