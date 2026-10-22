"""Invented workflow metadata. No recordings, participants or actual ratings."""
from copy import deepcopy
from hashlib import sha256


def make_manifest():
    from .domain import bind_manifest
    def pin(text):
        return sha256(text.encode()).hexdigest()
    prompts = []
    for identifier, word, target, phones in [
        ('rabbit', 'rabbit', 'R', ['R', 'AE', 'B', 'AH', 'T']),
        ('rural', 'rural', 'R', ['R', 'UH', 'R', 'AH', 'L']),
        ('sun', 'sun', 'S', ['S', 'AH', 'N']),
        ('bird', 'bird', 'ER', ['B', 'ER', 'D']),
    ]:
        prompts.append({'id': identifier, 'version': 'v1', 'word': word, 'lexicalGroup': word,
                        'language': 'en', 'targetPhone': target,
                        'variants': [{'id': 'v1', 'phones': phones,
                                      'occurrenceIndexes': [i for i, p in enumerate(phones) if p == target]}],
                        'source': {'kind': 'synthetic', 'sha256': pin('invented-source-' + word)},
                        'engineeringStatus': 'pending'})
    participants = [
        {'id': 'person-a', 'householdId': 'home-a', 'ageYears': 8, 'languageVariety': 'synthetic-en', 'identityLinkage': 'declared'},
        {'id': 'person-b', 'householdId': 'home-b', 'ageYears': 10, 'languageVariety': 'synthetic-en', 'identityLinkage': 'declared'},
        {'id': 'person-c', 'householdId': 'home-c', 'ageYears': 4, 'languageVariety': 'synthetic-en', 'identityLinkage': 'declared'},
        {'id': 'person-d', 'householdId': None, 'ageYears': 9, 'languageVariety': 'synthetic-en', 'identityLinkage': 'unknown'},
    ]
    attempts = []
    def add(identifier, participant='person-a', prompt='rabbit', **changes):
        permission = {'version': 'v1', 'recordSha256': pin('invented-permission-' + identifier),
                      'review': 'allowed', 'research': 'allowed', 'withdrawn': False}
        row = {'id': identifier, 'participantId': participant, 'promptId': prompt, 'variantId': 'v1',
               'occurrenceIndex': 0 if prompt != 'bird' else 1, 'sessionId': 'session-a', 'conditionId': 'quiet',
               'plannedRepeatOf': None, 'retryOf': None, 'split': 'development', 'terminal': 'processed_unverified',
               'recording': {'assetId': 'invented-' + identifier, 'sha256': pin('invented-recording-' + identifier),
                             'durationMs': 1200, 'origin': 'synthetic'}, 'permissions': permission, 'context': {key: '0' * 64 for key in ('taskSha256', 'policySha256', 'promptSha256', 'permissionSha256')}}
        row.update(changes)
        attempts.append(row)
    add('attempt-01')
    add('attempt-02', plannedRepeatOf='attempt-01', sessionId='session-b')
    add('attempt-03', retryOf='attempt-02', sessionId='session-b', terminal='failed', recording=None)
    add('attempt-04', participant='person-b')
    attempts[-1]['permissions'].update(review='denied', research='denied')
    add('attempt-05', participant='person-b', prompt='sun')
    add('attempt-06', prompt='rural', occurrenceIndex=None)
    add('attempt-07', participant='person-b', terminal='skipped', recording=None)
    add('attempt-08', participant='person-c', prompt='sun')
    add('attempt-09', participant='person-d', prompt='sun', split='evaluation')
    add('attempt-10', participant='person-b', prompt='sun')
    add('attempt-11', participant='person-b', prompt='bird')
    return bind_manifest({'schemaVersion': 1, 'projectId': 'invented-workbench', 'title': 'Assessment validation workbench',
        'mode': 'synthetic', 'task': {'id': 'target-occurrence-review', 'version': 'v1', 'referenceVariety': 'synthetic-en',
                                  'controlledReviewRecord': None, 'definitionSource': 'synthetic'},
        'policy': {'id': 'engineering-only', 'version': 'v1', 'allowedAges': [6, 12], 'intendedLanguage': 'en'},
        'prompts': prompts, 'participants': participants, 'attempts': attempts})


def make_predictions(manifest):
    from .domain import semantic_digest
    rows = []
    for attempt in manifest['attempts']:
        row = {'attemptId': attempt['id'], 'contextSha256': semantic_digest(attempt['context'])}
        if not attempt['recording'] or attempt['permissions']['research'] != 'allowed':
            row.update(status='unavailable', reason='permission_denied' if attempt['permissions']['research'] != 'allowed' else 'recording_unavailable')
        else:
            row.update(status='processed', probabilities=[0.2, 0.7, 0.1] if attempt['id'] == 'attempt-02' else [0.8, 0.15, 0.05])
        rows.append(row)
    payload = {'schemaVersion': 1, 'model': {'id': 'invented-model', 'version': 'v1',
               'manifestSha256': semantic_digest(manifest), 'preprocessingSha256': sha256(b'invented-no-preprocessing').hexdigest(),
               'meaning': 'subjective_corpus_classes'}, 'rows': rows}
    return {'synthetic': True, 'payload': payload, 'expectedSha256': semantic_digest(payload)}


def example_answer(attempt_id, reviewer_id):
    """Explicit invented exercise labels; never infer these from actual data."""
    answer = {'speech': 'present', 'promptMatch': 'matched', 'occurrence': 'resolved', 'target': 'expected',
              'quality': 'usable', 'notes': 'Invented workflow exercise; no audio judgment.'}
    if attempt_id in ('attempt-03', 'attempt-04', 'attempt-07'):
        answer.update(speech='unavailable', promptMatch='unavailable', occurrence='unavailable', target='unscorable', quality='unusable')
    elif attempt_id == 'attempt-02':
        answer['target'] = 'altered'
    elif attempt_id == 'attempt-05':
        answer['promptMatch'] = 'mismatched' if reviewer_id == 'reviewer-a' else 'uncertain'
    elif attempt_id == 'attempt-06':
        answer.update(occurrence='ambiguous', target='indeterminate')
    elif attempt_id == 'attempt-10' and reviewer_id == 'reviewer-b':
        answer['target'] = 'altered'
    return deepcopy(answer)
