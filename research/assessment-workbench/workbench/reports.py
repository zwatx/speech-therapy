"""All-attempt engineering reports, with explicit conditional denominators."""

from collections import Counter

from .domain import _admission, validate_manifest


TERMINALS = ('processed_unverified', 'rejected', 'cancelled', 'failed', 'skipped')
CATEGORIES = ('expected', 'altered', 'omitted', 'indeterminate', 'unscorable')
SCORABLE = CATEGORIES[:3]
ROLES = ('reviewer-a', 'reviewer-b')


def _fraction(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator}


def _breakdown(attempts, key, admissions, predictions, reviews):
    groups = {}
    for attempt in attempts:
        value = key(attempt)
        rows = groups.setdefault(value, [])
        rows.append(attempt)
    result = []
    for value, group in sorted(groups.items(), key=lambda item: str(item[0])):
        ids = [item['id'] for item in group]
        terminals = Counter(item['terminal'] for item in group)
        result.append({
            'value': value, 'attempts': len(group),
            'participants': len({item['participantId'] for item in group}),
            'terminalCounts': {terminal: terminals[terminal] for terminal in TERMINALS},
            'recordingsPresent': sum(item['recording'] is not None for item in group),
            'predictionsProcessed': sum(predictions.get(identifier, {}).get('status') == 'processed'
                                        for identifier in ids),
            'engineeringReady': sum(admissions[identifier]['status'] == 'engineering_ready' for identifier in ids),
            'reviewACount': sum(identifier in reviews.get('reviewer-a', {}) for identifier in ids),
            'reviewBCount': sum(identifier in reviews.get('reviewer-b', {}) for identifier in ids),
        })
    return result


def _sealed(aggregate):
    return all(aggregate.get('seals', {}).get(role) is True for role in ROLES)


def _agreement(aggregate, attempts):
    reviews = aggregate.get('reviews', {})
    pairs = [(reviews['reviewer-a'][item['id']]['answer']['target'],
              reviews['reviewer-b'][item['id']]['answer']['target']) for item in attempts
             if all(item['id'] in reviews.get(role, {}) for role in ROLES)]
    result = {
        'available': _sealed(aggregate), 'categories': list(CATEGORIES),
        'confusion': None, 'pairedCount': len(pairs), 'exactAgreement': None,
        'kappa': None, 'excludedUncertainOrUnscorable': None,
        'scorablePairs': _fraction(None, len(pairs)),
        'exactScorableAgreement': None,
        'basis': 'original_reviewer_a_and_reviewer_b_targets',
    }
    if not result['available']:
        return result
    confusion = {a: {b: 0 for b in CATEGORIES} for a in CATEGORIES}
    for a, b in pairs:
        confusion[a][b] += 1
    result['confusion'] = confusion
    result['exactAgreement'] = sum(a == b for a, b in pairs) / len(pairs) if pairs else None
    scorable = [(a, b) for a, b in pairs if a in SCORABLE and b in SCORABLE]
    result['excludedUncertainOrUnscorable'] = len(pairs) - len(scorable)
    result['scorablePairs'] = _fraction(len(scorable), len(pairs))
    count = len(scorable)
    if count:
        observed = sum(a == b for a, b in scorable) / count
        marginal_a = Counter(a for a, _ in scorable)
        marginal_b = Counter(b for _, b in scorable)
        expected = sum(marginal_a[target] * marginal_b[target] for target in SCORABLE) / count ** 2
        result['exactScorableAgreement'] = observed
        if expected < 1:
            result['kappa'] = (observed - expected) / (1 - expected)
    return result


def _reference_comparison(aggregate, attempts, predictions, admissions):
    reasons = []
    if not _sealed(aggregate):
        reasons.append('review_batches_unsealed')
    if aggregate.get('predictionLock') is None:
        reasons.append('prediction_not_locked')
    result = {
        'available': not reasons, 'reasons': reasons, 'rows': [],
        'meaning': 'subjective_corpus_predictions_with_engineering_reference_evidence',
        'modelAccuracyEstablished': False, 'clinicalValidityEstablished': False,
        'authenticationEstablished': False,
    }
    if reasons:
        return result
    reviews = aggregate.get('reviews', {})
    adjudications = aggregate.get('adjudications', {})
    for attempt in attempts:
        identifier = attempt['id']
        prediction = predictions.get(identifier, {})
        original_a = reviews.get('reviewer-a', {}).get(identifier)
        original_b = reviews.get('reviewer-b', {}).get(identifier)
        adjudication = adjudications.get(identifier)
        ready = admissions[identifier]['status'] == 'engineering_ready'
        resolved = adjudication['answer']['target'] if adjudication else (
            original_a['answer']['target'] if ready else None)
        result['rows'].append({
            'attemptId': identifier, 'predictionStatus': prediction.get('status', 'unavailable'),
            'probabilities': list(prediction['probabilities']) if 'probabilities' in prediction else None,
            'reviewATarget': original_a['answer']['target'] if original_a else None,
            'reviewBTarget': original_b['answer']['target'] if original_b else None,
            'adjudicatedTarget': adjudication['answer']['target'] if adjudication else None,
            'engineeringReferenceTarget': resolved if ready else None,
            'admission': admissions[identifier],
        })
    return result


def _repeatability(aggregate, attempts, predictions, admissions):
    by_id = {item['id']: item for item in attempts}
    reviews = aggregate.get('reviews', {})
    pairs = []
    for attempt in attempts:
        earlier_id = attempt['plannedRepeatOf']
        if earlier_id is None:
            continue
        earlier = by_id[earlier_id]
        identifier = attempt['id']
        same_condition = earlier['conditionId'] == attempt['conditionId']
        reasons = []
        if earlier['retryOf'] is not None or attempt['retryOf'] is not None:
            reasons.append('retry_endpoint')
        if not same_condition:
            reasons.append('condition_mismatch')
        for endpoint, label in ((earlier_id, 'from'), (identifier, 'to')):
            if admissions[endpoint]['status'] != 'engineering_ready':
                reasons.append(label + '_attempt_abstains')
        if not _sealed(aggregate):
            reasons.append('review_batches_unsealed')
        transitions = {}
        if _sealed(aggregate):
            for role in ROLES:
                initial = reviews.get(role, {}).get(earlier_id)
                repeated = reviews.get(role, {}).get(identifier)
                transitions[role] = {
                    'from': initial['answer']['target'] if initial else None,
                    'to': repeated['answer']['target'] if repeated else None,
                }
        probabilities = None
        initial_prediction = predictions.get(earlier_id, {})
        repeated_prediction = predictions.get(identifier, {})
        if not reasons and all(row.get('status') == 'processed'
                               for row in (initial_prediction, repeated_prediction)):
            probabilities = [repeated - initial for initial, repeated in
                             zip(initial_prediction['probabilities'], repeated_prediction['probabilities'])]
        pairs.append({
            'fromAttemptId': earlier_id, 'toAttemptId': identifier,
            'conditionMatch': same_condition, 'comparable': not reasons, 'reasons': reasons,
            'originalTargetTransitions': transitions,
            'probabilityDifferences': probabilities,
            'fromAdmissionReasons': list(admissions[earlier_id]['reasons']),
            'toAdmissionReasons': list(admissions[identifier]['reasons']),
        })
    return {
        'declaredPairs': len(pairs), 'comparablePairs': sum(pair['comparable'] for pair in pairs),
        'pairs': pairs, 'retryAttemptsExcluded': sum(item['retryOf'] is not None for item in attempts),
        'meaningfulImprovementEstablished': False,
        'probabilityDifferenceMeaning': 'repeat_minus_original_subjective_corpus_class_probability',
        'comparisonBasis': 'declared_same_condition_pairs_with_engineering_evidence',
    }


def build_report(aggregate):
    """Recompute from the whole immutable roster; no favorable-attempt filtering."""
    manifest = validate_manifest(aggregate['manifest'])
    attempts = manifest['attempts']
    participants = {item['id']: item for item in manifest['participants']}
    prompts = {item['id']: item for item in manifest['prompts']}
    reviews = aggregate.get('reviews', {})
    lock = aggregate.get('predictionLock')
    predictions = {} if lock is None else {row['attemptId']: row for row in lock['payload']['rows']}
    admissions = {item['id']: _admission(aggregate, manifest, item) for item in attempts}
    terminal_counts = Counter(item['terminal'] for item in attempts)
    counts = {
        'attempts': len(attempts), 'participants': len(participants),
        'householdsKnown': len({item['householdId'] for item in participants.values()
                                if item['householdId'] is not None}),
        'terminalCounts': {terminal: terminal_counts[terminal] for terminal in TERMINALS},
        'recordingsPresent': sum(item['recording'] is not None for item in attempts),
        'predictionsProcessed': sum(predictions.get(item['id'], {}).get('status') == 'processed' for item in attempts),
        'engineeringReady': sum(item['status'] == 'engineering_ready' for item in admissions.values()),
        'reviewACount': sum(item['id'] in reviews.get('reviewer-a', {}) for item in attempts),
        'reviewBCount': sum(item['id'] in reviews.get('reviewer-b', {}) for item in attempts),
        'pairedOriginalReviews': sum(all(item['id'] in reviews.get(role, {}) for role in ROLES) for item in attempts),
        'adjudicated': sum(item['id'] in aggregate.get('adjudications', {}) for item in attempts),
    }
    reason_counts = Counter(reason for result in admissions.values() for reason in result['reasons'])
    coverage = {key: _fraction(counts[key], len(attempts)) for key in (
        'recordingsPresent', 'predictionsProcessed', 'engineeringReady', 'reviewACount',
        'reviewBCount', 'pairedOriginalReviews', 'adjudicated')}
    coverage['participantsAttempted'] = _fraction(len({item['participantId'] for item in attempts}), len(participants))
    coverage['participantAgesKnown'] = _fraction(sum(item['ageYears'] is not None for item in participants.values()), len(participants))
    coverage['participantHouseholdsKnown'] = _fraction(sum(item['householdId'] is not None for item in participants.values()), len(participants))
    return {
        'denominators': counts, 'coverage': coverage,
        'admissionByAttemptId': admissions,
        'reasonCounts': dict(sorted(reason_counts.items())),
        'agreement': _agreement(aggregate, attempts),
        'referenceComparison': _reference_comparison(aggregate, attempts, predictions, admissions),
        'repeatability': _repeatability(aggregate, attempts, predictions, admissions),
        'byAge': _breakdown(attempts, lambda item: participants[item['participantId']]['ageYears'], admissions, predictions, reviews),
        'byTarget': _breakdown(attempts, lambda item: prompts[item['promptId']]['targetPhone'], admissions, predictions, reviews),
        'bySplit': _breakdown(attempts, lambda item: item['split'], admissions, predictions, reviews),
        'flags': {'synthetic': manifest['mode'] == 'synthetic',
                  'learnerFeedbackEligible': False, 'clinicalUseEligible': False,
                  'productionUseEligible': False, 'qualifiedReviewEstablished': False,
                  'independentAuthenticationEstablished': False,
                  'meaningfulImprovementEstablished': False,
                  'predictionMeaning': 'subjective_corpus_classes'},
    }
