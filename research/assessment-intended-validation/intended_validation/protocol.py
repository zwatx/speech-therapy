"""Fixed prospective engineering protocol; no enrollment or clinical claims."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from workbench.domain import semantic_digest

CLAIMS = dict.fromkeys(('learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible',
                       'qualifiedReviewEstablished', 'authenticProvenanceEstablished',
                       'meaningfulImprovementEstablished'), False)
CONTENT_SHA = 'c7a5769596b3f9b107a7dda96e6954e0e1d18338703d40be33b6f2f3ce82b498'
WORDS = ('rabbit', 'bread', 'door', 'baby', 'banana', 'backpack', 'sky', 'vase', 'yoyo',
         'thumb', 'feather', 'ring', 'treasure')

class ProtocolError(ValueError):
    """Safe fixed reporting code."""

def exact(row, fields):
    if type(row) is not dict or set(row) != set(fields.split()):
        raise ProtocolError('invalid_shape')

def identifier(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) is None:
        raise ProtocolError('invalid_id')

def sha(value, nullable=False):
    if nullable and value is None:
        return
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ProtocolError('invalid_sha')

def choice(value, options):
    if type(value) is not str or value not in options:
        raise ProtocolError('invalid_value')

def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ProtocolError('invalid_integer')

def roster(rows, maximum=20000):
    if type(rows) is not list or len(rows) > maximum:
        raise ProtocolError('invalid_roster')
    output = {}
    for row in rows:
        if type(row) is not dict or 'id' not in row:
            raise ProtocolError('invalid_shape')
        identifier(row['id'])
        if row['id'] in output:
            raise ProtocolError('duplicate_id')
        output[row['id']] = row
    return output

def make_protocol(model_manifest_sha, admission_policy_sha, allocation_sha, participant_roster_sha):
    sha(model_manifest_sha); sha(admission_policy_sha); sha(allocation_sha); sha(participant_roster_sha)
    return {
        'schemaVersion': 1, 'id': 'intended-recording-admission-v1',
        'status': 'prospective_not_collected', 'ageRange': [6, 12], 'language': 'en',
        'contentSha256': CONTENT_SHA, 'modelManifestSha256': model_manifest_sha,
        'admissionPolicySha256': admission_policy_sha, 'lexicalGroups': list(WORDS),
        'allocationSha256': allocation_sha,
        'participantRosterSha256': participant_roster_sha,
        'sampling': {'unit': 'one_participant_per_independent_household', 'plannedUnits': 210,
                     'basis': 'prospective_engineering_precision_not_clinical_standard',
                     'splitMode': 'participant_household', 'unfamiliarWordClaim': False,
                     'pretrainedDataOverlapKnown': False},
        'primaryAllocation': {'positive': 'first_preassigned_requested_word_attempt',
                              'challenge': 'first_preassigned_wrong_extra_or_nonspeech_attempt',
                              'retriesMayReplacePrimary': False},
        'thresholds': {'wilsonZ': 1.959963984540054, 'confidence': 0.95,
                       'positiveLowerAtLeast': 0.90, 'challengeFailureUpperAtMost': 0.05},
        'missingness': 'unresolved_or_missing_is_not_primary_success',
        'repeatSchedule': {'newRecordingIntervalSeconds': [86400, 604800],
                           'conditionsMustMatch': True, 'sameBytesMeaning': 'computational_replay',
                           'postPracticeMeaning': 'longitudinal_observation_not_improvement'},
        'phoneDecisionEvaluation': 'excluded_no_justified_corpus_to_correctness_mapping',
        'review': {'originalRoles': ['reviewer-a', 'reviewer-b'], 'adjudicatorRole': 'adjudicator',
                   'qualificationVerification': 'factual_owner_records_required',
                   'blinding': ['predictions', 'challenge_assignment', 'source_filename',
                                'participant_identity', 'other_review']},
        'claimLimits': deepcopy(CLAIMS),
    }

def make_protocol_v2(model_manifest_sha, admission_policy_sha, allocation_sha, participant_roster_sha):
    protocol = make_protocol(model_manifest_sha, admission_policy_sha, allocation_sha, participant_roster_sha)
    protocol.update(schemaVersion=2, id='intended-recording-admission-v2')
    protocol['reviewContextBinding'] = {
        'fields': ['protocolSha256', 'attemptId', 'recordingSha256', 'promptId',
                   'word', 'variantId', 'occurrenceIndex'],
        'digest': 'semantic_digest', 'originalField': 'reviewContextSha256',
        'requiredForEveryOriginal': True, 'legacyReviewsMayBeAutoBound': False,
        'adjudicationBinding': 'immutable_original_hashes',
    }
    return protocol

def validate_protocol(protocol):
    if type(protocol) is not dict:
        raise ProtocolError('invalid_protocol')
    version = protocol.get('schemaVersion')
    if type(version) is not int or version not in (1, 2):
        raise ProtocolError('invalid_protocol')
    builder = make_protocol if version == 1 else make_protocol_v2
    try:
        expected = builder(protocol['modelManifestSha256'], protocol['admissionPolicySha256'], protocol['allocationSha256'], protocol['participantRosterSha256'])
    except KeyError:
        raise ProtocolError('invalid_protocol') from None
    if protocol != expected or semantic_digest(protocol) != semantic_digest(expected):
        raise ProtocolError('protocol_changed')
    return deepcopy(protocol)

def blank_bundle(protocol):
    validate_protocol(protocol)
    return {'schemaVersion': 1, 'mode': 'preparation', 'protocolSha256': semantic_digest(protocol),
            'independenceDeclared': False, 'allocation': [], 'participants': [], 'attempts': [],
            'reviewerRecords': [], 'originalReviews': [], 'adjudications': []}

def prompt_definitions():
    path = Path(__file__).resolve().parents[3] / 'work/assessment-real-data-20261004/engineering-pack.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTENT_SHA:
        raise ProtocolError('content_binding_mismatch')
    return {row['decision']['promptId']: row['decision'] for row in json.loads(raw)['prompts']}
