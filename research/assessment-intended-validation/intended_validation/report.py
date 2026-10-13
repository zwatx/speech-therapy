"""Strict all-attempt, household-unit reporting of supplied private observations."""
from collections import Counter
from math import sqrt
from .protocol import (CLAIMS, ProtocolError, exact, identifier, sha, choice, integer,
                       roster, validate_protocol, prompt_definitions, review_context_digest)
from workbench.domain import semantic_digest

FIELDS = {
    'quality': ('usable', 'unusable', 'uncertain', 'unavailable'),
    'speech': ('present', 'absent', 'uncertain', 'unavailable'),
    'word': ('requested', 'other', 'extra', 'uncertain', 'unavailable'),
    'variant': ('accepted', 'other', 'uncertain', 'not_applicable', 'unavailable'),
    'occurrence': ('resolved', 'uncertain', 'not_observable', 'not_applicable', 'unavailable'),
    'target': ('expected', 'altered', 'omitted', 'indeterminate', 'unscorable', 'not_applicable'),
}
TERMINALS = ('processed', 'unavailable', 'cancelled', 'failed', 'skipped', 'withdrawn')


def wilson(successes, units, z=1.959963984540054):
    integer(units, 1, 20000); integer(successes, 0, units)
    p = successes / units
    scale = 1 + z*z / units
    center = (p + z*z / (2*units)) / scale
    radius = z * sqrt(p*(1-p)/units + z*z/(4*units*units)) / scale
    return {'lower': max(0.0, center-radius), 'upper': min(1.0, center+radius),
            'confidence': 0.95, 'unit': 'participant_household',
            'meaning': 'conditional_on_declared_independent_binomial_sampling'}


def _observations(row):
    exact(row, ' '.join(FIELDS))
    for field, options in FIELDS.items():
        choice(row[field], options)
    if row['speech'] == 'absent' and row['word'] == 'requested':
        raise ProtocolError('contradictory_review')
    return row

def _available_observations(observations, recording_sha):
    _observations(observations)
    if recording_sha is None and (any(observations[field] != 'unavailable'
            for field in ('quality', 'speech', 'word', 'variant', 'occurrence'))
            or observations['target'] not in ('unscorable', 'not_applicable')):
        raise ProtocolError('absent_recording_has_substantive_review')
    return observations


def _bound_hash(row, key):
    sha(row[key])
    if semantic_digest({k: v for k, v in row.items() if k != key}) != row[key]:
        raise ProtocolError('review_hash_mismatch')


def _fraction(a, b):
    return {'numerator': a, 'denominator': b, 'fraction': a / b if b else None}


def build_report(protocol, bundle):
    validate_protocol(protocol)
    exact(bundle, 'schemaVersion mode protocolSha256 independenceDeclared allocation participants attempts reviewerRecords originalReviews adjudications')
    version = protocol['schemaVersion']
    integer(bundle['schemaVersion'], version, version)
    choice(bundle['mode'], ('preparation', 'invented_exercise', 'supplied_observations'))
    if type(bundle['independenceDeclared']) is not bool:
        raise ProtocolError('invalid_value')
    if bundle['protocolSha256'] != semantic_digest(protocol):
        raise ProtocolError('protocol_binding_mismatch')
    people = roster(bundle['participants'], 1000)
    if semantic_digest(bundle['participants']) != protocol['participantRosterSha256']:
        raise ProtocolError('participant_roster_binding_mismatch')
    attempts = roster(bundle['attempts'])
    reviewers = roster(bundle['reviewerRecords'], 3)
    originals = roster(bundle['originalReviews'], 40000)
    adjudications = roster(bundle['adjudications'])
    allocation = roster(bundle['allocation'], 1000)
    if semantic_digest(bundle['allocation']) != protocol['allocationSha256']:
        raise ProtocolError('allocation_binding_mismatch')
    if set(allocation) != set(people):
        raise ProtocolError('allocation_roster_mismatch')
    for row in allocation.values():
        exact(row, 'id positiveAttemptId challengeAttemptId positivePromptId challengePromptId challengeType')
        for key in ('positiveAttemptId', 'challengeAttemptId', 'positivePromptId', 'challengePromptId'):
            identifier(row[key])
        if row['positiveAttemptId'] == row['challengeAttemptId']:
            raise ProtocolError('invalid_primary_allocation')
        choice(row['challengeType'], ('wrong_word', 'extra_word', 'nonspeech'))
    if bundle['mode'] == 'preparation' and any((people, attempts, reviewers, originals, adjudications)):
        raise ProtocolError('preparation_must_be_empty')
    linkage_reasons, household_partitions, households = set(), {}, {}
    evidence_reasons = set()
    for person in people.values():
        exact(person, 'id householdId linkageStatus ageYears variety permissionRecordSha256 partition')
        choice(person['linkageStatus'], ('declared', 'unknown'))
        integer(person['ageYears'], 6, 12)
        identifier(person['variety']); sha(person['permissionRecordSha256'], nullable=True)
        if person['permissionRecordSha256'] is None:
            evidence_reasons.add('permission_evidence_pending')
        choice(person['partition'], ('development', 'evaluation'))
        household = person['householdId']
        if household is None or person['linkageStatus'] == 'unknown':
            linkage_reasons.add('unknown_household_or_identity_linkage')
        if household is not None:
            identifier(household)
            if household in household_partitions and household_partitions[household] != person['partition']:
                linkage_reasons.add('household_partition_conflict')
            household_partitions[household] = person['partition']
            households.setdefault(household, []).append(person['id'])
    if any(len(ids) > 1 for ids in households.values()):
        linkage_reasons.add('multiple_participants_per_household')
    roles = {}
    for person in reviewers.values():
        exact(person, 'id role identityEvidenceSha256 qualificationEvidenceSha256 conflictEvidenceSha256 blindingEvidenceSha256')
        choice(person['role'], ('reviewer-a', 'reviewer-b', 'adjudicator'))
        if person['role'] in roles:
            raise ProtocolError('duplicate_reviewer_role')
        roles[person['role']] = person['id']
        for key in ('identityEvidenceSha256', 'qualificationEvidenceSha256', 'conflictEvidenceSha256', 'blindingEvidenceSha256'):
            sha(person[key], nullable=True)
            if person[key] is None:
                evidence_reasons.add('reviewer_evidence_pending')
    if attempts and set(roles) != {'reviewer-a', 'reviewer-b', 'adjudicator'}:
        raise ProtocolError('reviewer_records_required')
    by_person = {pid: {} for pid in people}
    by_order = {}
    prompt_map = prompt_definitions()
    # Validate referenced row shapes and ordering before cross-row comparisons.
    for raw in attempts.values():
        exact(raw, 'id participantId order sessionId conditionId promptId word variantId occurrenceIndex primaryRole terminal reason recordingSha256 modelManifestSha256 admissionPolicySha256 admission evidenceSha256 retryOf repeatOf replayOf acquiredAt')
        integer(raw['order'], 1, 20000)
    for attempt in attempts.values():
        exact(attempt, 'id participantId order sessionId conditionId promptId word variantId occurrenceIndex primaryRole terminal reason recordingSha256 modelManifestSha256 admissionPolicySha256 admission evidenceSha256 retryOf repeatOf replayOf acquiredAt')
        pid = attempt['participantId']
        if type(pid) is not str or pid not in people:
            raise ProtocolError('unknown_participant')
        for key in ('sessionId', 'conditionId', 'variantId', 'reason'):
            identifier(attempt[key])
        choice(attempt['word'], protocol['lexicalGroups'])
        definition = prompt_map.get(attempt['promptId']) if type(attempt['promptId']) is str else None
        if (not definition or definition['sourceWord'] != attempt['word']
                or attempt['variantId'] not in definition['acceptedVariantIds']
                or type(attempt['occurrenceIndex']) is not int
                or attempt['occurrenceIndex'] not in definition['allTargetIndexesByVariant'][attempt['variantId']]):
            raise ProtocolError('invalid_prompt_occurrence')
        integer(attempt['order'], 1, 20000); integer(attempt['acquiredAt'], 0, 253402300799)
        integer(attempt['occurrenceIndex'], 0, 128)
        choice(attempt['primaryRole'], ('positive', 'challenge', 'none'))
        choice(attempt['terminal'], TERMINALS)
        choice(attempt['admission'], ('admitted', 'rejected', 'unavailable'))
        sha(attempt['recordingSha256'], nullable=True); sha(attempt['evidenceSha256'], nullable=True)
        for key in ('modelManifestSha256', 'admissionPolicySha256'):
            if attempt[key] != protocol[key]:
                raise ProtocolError('processing_binding_mismatch')
        if (attempt['admission'] == 'admitted' and (attempt['terminal'] != 'processed'
                or attempt['recordingSha256'] is None or attempt['evidenceSha256'] is None)):
            raise ProtocolError('invalid_admitted_attempt')
        orderkey = (pid, attempt['order'])
        if orderkey in by_order:
            raise ProtocolError('duplicate_initiation_order')
        by_order[orderkey] = attempt['id']
        ancestors = [key for key in ('retryOf', 'repeatOf', 'replayOf') if attempt[key] is not None]
        if len(ancestors) > 1 or ancestors and attempt['primaryRole'] != 'none':
            raise ProtocolError('invalid_ancestry')
        for key in ancestors:
            parent = attempts.get(attempt[key]) if type(attempt[key]) is str else None
            if (not parent or parent['participantId'] != pid or parent['order'] >= attempt['order']
                    or parent['word'] != attempt['word'] or parent['variantId'] != attempt['variantId']
                    or parent['occurrenceIndex'] != attempt['occurrenceIndex']):
                raise ProtocolError('invalid_ancestry')
            if key == 'replayOf' and (not attempt['recordingSha256'] or parent['recordingSha256'] != attempt['recordingSha256']):
                raise ProtocolError('invalid_replay')
            if key == 'repeatOf' and attempt['recordingSha256'] and parent['recordingSha256'] == attempt['recordingSha256']:
                raise ProtocolError('same_bytes_are_replay')
        role = attempt['primaryRole']
        if role != 'none':
            planned = allocation[pid]
            if attempt['id'] != planned[role + 'AttemptId'] or attempt['promptId'] != planned[role + 'PromptId']:
                raise ProtocolError('primary_allocation_mismatch')
            if role in by_person[pid]:
                raise ProtocolError('duplicate_primary_attempt')
            by_person[pid][role] = attempt['id']
    if any(set(primaries) != {'positive', 'challenge'} for primaries in by_person.values()):
        raise ProtocolError('missing_primary_roster')
    reviews, blind_ids = {}, set()
    for original in originals.values():
        original_fields = 'id reviewerId blindItemId attemptId recordingSha256 protocolSha256 observations originalSha256'
        if version == 2:
            original_fields += ' reviewContextSha256'
        exact(original, original_fields)
        _bound_hash(original, 'originalSha256'); identifier(original['blindItemId'])
        if original['blindItemId'] in blind_ids:
            raise ProtocolError('duplicate_blind_item')
        blind_ids.add(original['blindItemId'])
        rid, aid = original['reviewerId'], original['attemptId']
        reviewer = reviewers.get(rid) if type(rid) is str else None
        attempt = attempts.get(aid) if type(aid) is str else None
        if not reviewer or reviewer['role'] not in ('reviewer-a', 'reviewer-b') or not attempt:
            raise ProtocolError('unknown_review_reference')
        if (original['recordingSha256'] != attempt['recordingSha256']
                or original['protocolSha256'] != bundle['protocolSha256']):
            raise ProtocolError('review_binding_mismatch')
        if version == 2:
            sha(original['reviewContextSha256'])
            if original['reviewContextSha256'] != review_context_digest(protocol, attempt):
                raise ProtocolError('review_context_binding_mismatch')
        _available_observations(original['observations'], attempt['recordingSha256'])
        if (aid, reviewer['role']) in reviews:
            raise ProtocolError('duplicate_original_review')
        reviews[aid, reviewer['role']] = original
    if len(reviews) != len(attempts)*2:
        raise ProtocolError('missing_original_review_rows')
    resolutions = {}
    for decision in adjudications.values():
        exact(decision, 'id attemptId adjudicatorId originalASha256 originalBSha256 observations reason decisionSha256')
        _bound_hash(decision, 'decisionSha256'); identifier(decision['reason'])
        aid = decision['attemptId']
        if type(aid) is not str or aid not in attempts or aid in resolutions or decision['adjudicatorId'] != roles['adjudicator']:
            raise ProtocolError('invalid_adjudication')
        for role, field in (('reviewer-a', 'originalASha256'), ('reviewer-b', 'originalBSha256')):
            if decision[field] != reviews[aid, role]['originalSha256']:
                raise ProtocolError('adjudication_binding_mismatch')
        observations = _available_observations(decision['observations'], attempts[aid]['recordingSha256'])
        resolutions[aid] = observations
    unresolved, resolved, agreements = [], {}, Counter()
    for aid in attempts:
        a, b = (reviews[aid, role]['observations'] for role in ('reviewer-a', 'reviewer-b'))
        for field in FIELDS:
            agreements[field] += a[field] == b[field]
        if aid in resolutions:
            resolved[aid] = resolutions[aid]
        elif a == b:
            resolved[aid] = a
        else:
            unresolved.append(aid)
    rows = []
    for pid, primary in by_person.items():
        pos, challenge = (attempts[primary[role]] for role in ('positive', 'challenge'))
        pr, cr = resolved.get(pos['id']), resolved.get(challenge['id'])
        positive_ref = bool(pr and pr['quality'] == 'usable' and pr['speech'] == 'present' and pr['word'] == 'requested')
        prohibited_ref = bool(cr and (cr['speech'] == 'absent' or cr['speech'] == 'present' and cr['word'] in ('other', 'extra')))
        challenge_type = allocation[pid]['challengeType']
        type_compliant = bool(cr and (cr['speech'] == 'absent' if challenge_type == 'nonspeech'
                else cr['speech'] == 'present' and cr['word'] == ('other' if challenge_type == 'wrong_word' else 'extra')))
        safe = bool(type_compliant and challenge['admission'] == 'rejected'
                    and challenge['terminal'] in ('processed', 'unavailable')
                    and challenge['recordingSha256'] and challenge['evidenceSha256'])
        rows.append({'participantId': pid, 'partition': people[pid]['partition'],
                     'positiveAttemptId': pos['id'], 'challengeAttemptId': challenge['id'],
                     'positiveConfirmed': positive_ref and pos['admission'] == 'admitted',
                     'safeChallengeConfirmed': safe,
                     'observedUnsafeAdmission': prohibited_ref and challenge['admission'] == 'admitted',
                     'challengeReferenceUnresolved': not prohibited_ref,
                     'challengeTypeCompliant': type_compliant,
                     'challengeAllocationMismatch': prohibited_ref and not type_compliant,
                     'captureUsable': bool(pr and pr['quality'] == 'usable')})
    eval_rows = [row for row in rows if row['partition'] == 'evaluation']
    n = len(eval_rows)
    positive = sum(row['positiveConfirmed'] for row in eval_rows)
    failures = sum(not row['safeChallengeConfirmed'] for row in eval_rows)
    interval_reasons = sorted(linkage_reasons | evidence_reasons)
    hash_partitions = {}
    for attempt in attempts.values():
        if attempt['recordingSha256']:
            hash_partitions.setdefault(attempt['recordingSha256'], set()).add(people[attempt['participantId']]['partition'])
    if any(len(partitions) > 1 for partitions in hash_partitions.values()):
        interval_reasons.append('cross_partition_recording_overlap')
    primary_hashes = [attempts[row[key]]['recordingSha256'] for row in eval_rows
                      for key in ('positiveAttemptId', 'challengeAttemptId')
                      if attempts[row[key]]['recordingSha256']]
    if len(primary_hashes) != len(set(primary_hashes)):
        interval_reasons.append('primary_recording_hash_reused')
    if not bundle['independenceDeclared']:
        interval_reasons.append('independent_sampling_not_declared')
    if bundle['mode'] != 'supplied_observations':
        interval_reasons.append('no_intended_recording_observations')
    if not n:
        interval_reasons.append('no_evaluation_units')
    if bundle['mode'] == 'supplied_observations' and n != protocol['sampling']['plannedUnits']:
        interval_reasons.append('evaluation_roster_size_mismatch')
    intervals = None if interval_reasons else {'positiveAdmission': wilson(positive, n), 'conservativeChallengeFailure': wilson(failures, n)}
    criteria = bool(intervals and n == protocol['sampling']['plannedUnits'] and not unresolved
                    and intervals['positiveAdmission']['lower'] >= protocol['thresholds']['positiveLowerAtLeast']
                    and intervals['conservativeChallengeFailure']['upper'] <= protocol['thresholds']['challengeFailureUpperAtMost'])
    strata = {}
    for field in ('ageYears', 'variety', 'word', 'conditionId'):
        counts = Counter(str(people[a['participantId']][field] if field in ('ageYears', 'variety') else a[field]) for a in attempts.values())
        strata[field] = dict(sorted(counts.items()))
    repeat_rows = []
    for attempt in attempts.values():
        key = 'repeatOf' if attempt['repeatOf'] else 'replayOf' if attempt['replayOf'] else None
        if key:
            parent = attempts[attempt[key]]
            interval = attempt['acquiredAt'] - parent['acquiredAt']
            repeat_rows.append({'from': parent['id'], 'to': attempt['id'], 'kind': 'new_recording_repeat' if key == 'repeatOf' else 'computational_replay',
                                'bothPresent': bool(attempt['recordingSha256'] and parent['recordingSha256']),
                                'conditionMatch': attempt['conditionId'] == parent['conditionId'],
                                'withinDeclaredInterval': key == 'repeatOf' and protocol['repeatSchedule']['newRecordingIntervalSeconds'][0] <= interval <= protocol['repeatSchedule']['newRecordingIntervalSeconds'][1],
                                'meaningfulImprovementEstablished': False})
    return {'schemaVersion': 1, 'protocolSha256': bundle['protocolSha256'], 'bundleSha256': semantic_digest(bundle),
            'mode': bundle['mode'], 'allAttemptDenominators': {'participants': len(people), 'attempts': len(attempts),
                 'recordings': sum(a['recordingSha256'] is not None for a in attempts.values()),
                 'uniqueRecordingHashes': len({a['recordingSha256'] for a in attempts.values() if a['recordingSha256']}),
                 'terminalCounts': {t: sum(a['terminal'] == t for a in attempts.values()) for t in TERMINALS},
                 'admissionCounts': dict(Counter(a['admission'] for a in attempts.values())),
                 'originalReviews': len(originals), 'adjudications': len(adjudications)},
            'primaryParticipantRows': rows, 'evaluationPrimary': {'units': n, 'positiveConfirmed': _fraction(positive, n),
                 'conservativeChallengeFailures': _fraction(failures, n),
                 'observedUnsafeAdmissions': _fraction(sum(r['observedUnsafeAdmission'] for r in eval_rows), n),
                 'challengeReferenceUnresolved': _fraction(sum(r['challengeReferenceUnresolved'] for r in eval_rows), n),
                 'challengeAllocationMismatch': _fraction(sum(r['challengeAllocationMismatch'] for r in eval_rows), n)},
            'participantIntervals': intervals, 'intervalSuppressionReasons': interval_reasons,
            'split': {'mode': 'participant_household', 'violations': sorted(linkage_reasons), 'unfamiliarWordClaim': False},
            'originalAgreement': {field: _fraction(agreements[field], len(attempts)) for field in FIELDS},
            'unresolvedOriginalDisagreements': unresolved, 'descriptiveAttemptStrata': strata,
            'repeatPairs': repeat_rows, 'phoneDecisionEvaluation': 'not_evaluable',
            'engineeringCriteriaMet': criteria, 'claimLimits': dict(CLAIMS),
            'evidenceAuthenticityVerified': False, 'permissionVerified': False,
            'interpretation': 'structural_and_declared_observation_summary_not_clinical_validation'}
