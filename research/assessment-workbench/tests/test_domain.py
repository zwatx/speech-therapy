import copy
import unittest

from workbench.domain import ValidationError, bind_manifest, semantic_digest, split_diagnostics, validate_manifest, admission


def manifest_fixture():
    return {
        'schemaVersion': 1, 'projectId': 'invented-project', 'title': 'Invented checks',
        'mode': 'synthetic',
        'task': {'id': 'word-task', 'version': '1', 'referenceVariety': 'en-US',
                 'controlledReviewRecord': None, 'definitionSource': 'synthetic'},
        'policy': {'id': 'engineering', 'version': '1', 'allowedAges': [6, 12],
                   'intendedLanguage': 'en'},
        'prompts': [{'id': 'sun', 'version': '1', 'word': 'sun', 'lexicalGroup': 'sun',
                     'language': 'en', 'targetPhone': 'S',
                     'variants': [{'id': 'default', 'phones': ['S', 'AH1', 'N'],
                                   'occurrenceIndexes': [0]}],
                     'source': {'kind': 'synthetic', 'sha256': 'a' * 64},
                     'engineeringStatus': 'accepted'}],
        'participants': [{'id': 'child-a', 'householdId': 'home-a', 'ageYears': 8,
                          'languageVariety': 'en-US', 'identityLinkage': 'declared'}],
        'attempts': [{'id': 'attempt-a', 'participantId': 'child-a', 'promptId': 'sun',
                      'variantId': 'default', 'occurrenceIndex': 0, 'sessionId': 'session-a',
                      'conditionId': 'room-a', 'plannedRepeatOf': None, 'retryOf': None,
                      'split': 'development', 'terminal': 'processed_unverified',
                      'recording': {'assetId': 'invented-a', 'sha256': 'b' * 64,
                                    'durationMs': 800, 'origin': 'synthetic'},
                      'permissions': {'version': '1', 'recordSha256': 'c' * 64,
                                      'review': 'allowed', 'research': 'allowed', 'withdrawn': False},
                      'context': {'taskSha256': '', 'policySha256': '',
                                  'promptSha256': '', 'permissionSha256': ''}}],
    }


class ManifestTests(unittest.TestCase):
    def test_bound_manifest_is_an_independent_snapshot_and_altered_prompt_is_rejected(self):
        original = manifest_fixture()
        bound = bind_manifest(original)
        self.assertEqual(validate_manifest(bound), bound)
        self.assertEqual(original['attempts'][0]['context']['taskSha256'], '')
        changed = copy.deepcopy(bound)
        changed['prompts'][0]['word'] = 'moon'
        with self.assertRaises(ValidationError) as failure:
            validate_manifest(changed)
        self.assertEqual(failure.exception.code, 'context_mismatch')

    def test_import_rejects_malformed_metadata_without_dropping_attempts(self):
        changes = [
            lambda m: m.update({'extra': 'secret'}),
            lambda m: m['participants'][0].update({'ageYears': True}),
            lambda m: m['attempts'][0]['recording'].update({'durationMs': float('nan')}),
            lambda m: m['attempts'][0].update({'participantId': 'unknown'}),
            lambda m: m['attempts'].append(copy.deepcopy(m['attempts'][0])),
            lambda m: m['prompts'][0]['variants'][0].update({'phones': ['S', 'AH1', 'S']}),
            lambda m: m['attempts'][0].update({'retryOf': 'attempt-a'}),
        ]
        for change in changes:
            with self.subTest(change=change):
                manifest = manifest_fixture()
                change(manifest)
                with self.assertRaises(ValidationError):
                    bind_manifest(manifest)

    def test_out_of_scope_age_and_unresolved_occurrence_remain_in_manifest(self):
        manifest = manifest_fixture()
        manifest['participants'][0]['ageYears'] = 4
        manifest['attempts'][0]['occurrenceIndex'] = None
        self.assertEqual(len(bind_manifest(manifest)['attempts']), 1)

    def test_repeated_phone_variants_must_preserve_all_target_occurrences(self):
        manifest = manifest_fixture()
        manifest['prompts'][0]['variants'][0].update(
            {'phones': ['S', 'AH1', 'S'], 'occurrenceIndexes': [0, 2]})
        self.assertEqual(bind_manifest(manifest)['prompts'][0]['variants'][0]['occurrenceIndexes'], [0, 2])
        manifest['prompts'][0]['variants'][0]['occurrenceIndexes'] = [0]
        with self.assertRaises(ValidationError):
            bind_manifest(manifest)

    def test_semantic_digest_is_order_independent_but_rejects_non_json(self):
        self.assertEqual(semantic_digest({'a': 1, 'b': 2}), semantic_digest({'b': 2, 'a': 1}))
        for value in (float('inf'), {'a': object()}, {1: 'bad'}, ('tuple',)):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                semantic_digest(value)

    def test_binding_accepts_initial_context_omission_and_empty_context_but_validation_requires_pins(self):
        for omit in (False, True):
            manifest = manifest_fixture()
            if omit:
                del manifest['attempts'][0]['context']
            else:
                manifest['attempts'][0]['context'] = {}
            with self.subTest(omit=omit):
                self.assertEqual(len(bind_manifest(manifest)['attempts'][0]['context']), 4)
                with self.assertRaises(ValidationError):
                    validate_manifest(manifest)

    def test_changing_task_policy_prompt_or_permission_snapshot_invalidates_an_attempt(self):
        for field in ('task', 'policy', 'prompt', 'permission'):
            manifest = bind_manifest(manifest_fixture())
            if field == 'task':
                manifest['task']['version'] = '2'
            elif field == 'policy':
                manifest['policy']['version'] = '2'
            elif field == 'prompt':
                manifest['prompts'][0]['engineeringStatus'] = 'revise'
            else:
                manifest['attempts'][0]['permissions']['research'] = 'denied'
            with self.subTest(field=field), self.assertRaises(ValidationError) as error:
                validate_manifest(manifest)
            self.assertEqual(error.exception.code, 'context_mismatch')

    def test_retry_requires_same_session_while_declared_repeat_mismatch_is_retained(self):
        manifest = manifest_fixture()
        followup = copy.deepcopy(manifest['attempts'][0])
        followup.update({'id': 'followup', 'retryOf': 'attempt-a', 'sessionId': 'later-session'})
        manifest['attempts'].append(followup)
        with self.assertRaises(ValidationError):
            bind_manifest(manifest)
        followup.update({'retryOf': None, 'plannedRepeatOf': 'attempt-a', 'conditionId': 'different'})
        self.assertEqual(len(bind_manifest(manifest)['attempts']), 2)

    def test_finite_large_integer_duration_is_valid_json_without_float_conversion_overflow(self):
        manifest = manifest_fixture()
        manifest['attempts'][0]['recording']['durationMs'] = 10 ** 400
        self.assertEqual(bind_manifest(manifest)['attempts'][0]['recording']['durationMs'], 10 ** 400)


class SplitTests(unittest.TestCase):
    def test_joint_constraints_expose_leakage_and_infeasible_three_way_isolation(self):
        manifest = manifest_fixture()
        manifest['participants'].append({'id': 'child-b', 'householdId': None, 'ageYears': 8,
                                         'languageVariety': 'en-US', 'identityLinkage': 'unknown'})
        second = copy.deepcopy(manifest['attempts'][0])
        second.update({'id': 'attempt-b', 'participantId': 'child-b', 'split': 'evaluation'})
        manifest['attempts'].append(second)
        result = split_diagnostics(bind_manifest(manifest))
        self.assertEqual(result['participants']['leakageGroups'], [])
        self.assertEqual(result['lexicalGroups']['leakageGroups'][0]['id'], 'sun')
        self.assertEqual(result['joint']['componentCount'], 1)
        self.assertEqual(result['joint']['threeWayIsolation'], 'infeasible')
        self.assertEqual(result['unknownIsolation']['participantIds'], ['child-b'])
        self.assertFalse(result['unknownIsolation']['isolationEstablished'])

    def test_complete_declared_linkage_does_not_claim_isolation_when_assigned_splits_leak(self):
        manifest = manifest_fixture()
        second = copy.deepcopy(manifest['attempts'][0])
        second.update({'id': 'attempt-b', 'split': 'evaluation'})
        manifest['attempts'].append(second)
        result = split_diagnostics(bind_manifest(manifest))
        self.assertTrue(result['unknownIsolation']['declaredLinkageComplete'])
        self.assertFalse(result['unknownIsolation']['isolationEstablished'])



def ready_aggregate():
    manifest = bind_manifest(manifest_fixture())
    answer = {'speech': 'present', 'promptMatch': 'matched', 'occurrence': 'resolved',
              'target': 'expected', 'quality': 'usable', 'notes': ''}
    return {'manifest': manifest,
            'reviews': {role: {'attempt-a': {'answer': copy.deepcopy(answer),
                                           'sha256': semantic_digest(answer)}}
                        for role in ('reviewer-a', 'reviewer-b')},
            'seals': {'reviewer-a': True, 'reviewer-b': True},
            'adjudications': {}, 'contentReviews': [], 'withdrawals': [],
            'predictionLock': {'payload': {
                'schemaVersion': 1,
                'model': {'id': 'invented-model', 'version': '1',
                          'manifestSha256': semantic_digest(manifest),
                          'preprocessingSha256': 'd' * 64, 'meaning': 'subjective_corpus_classes'},
                'rows': [{'attemptId': 'attempt-a', 'contextSha256': semantic_digest(manifest['attempts'][0]['context']),
                          'status': 'processed', 'probabilities': [0.2, 0.3, 0.5]}]},
                'sha256': 'e' * 64}}


class AdmissionTests(unittest.TestCase):
    def test_independent_sealed_evidence_allows_engineering_only_and_withdrawal_blocks_current_use(self):
        aggregate = ready_aggregate()
        result = admission(aggregate, 'attempt-a')
        self.assertEqual(result['status'], 'engineering_ready')
        for flag in ('learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible'):
            self.assertFalse(result[flag])
        aggregate['withdrawals'].append({'participantId': 'child-a', 'reason': 'invented withdrawal'})
        withdrawn = admission(aggregate, 'attempt-a')
        self.assertEqual(withdrawn['status'], 'abstain')
        self.assertIn('current_withdrawal', withdrawn['currentRestrictions'])
        self.assertEqual(withdrawn['historicalContext'], result['historicalContext'])

    def test_adjudication_resolves_only_target_and_cannot_bypass_uncertain_speech(self):
        aggregate = ready_aggregate()
        aggregate['reviews']['reviewer-b']['attempt-a']['answer']['target'] = 'altered'
        self.assertIn('target_disagreement', admission(aggregate, 'attempt-a')['reasons'])
        aggregate['adjudications']['attempt-a'] = {'answer': {'target': 'expected'}}
        self.assertEqual(admission(aggregate, 'attempt-a')['status'], 'engineering_ready')
        aggregate['reviews']['reviewer-b']['attempt-a']['answer']['speech'] = 'uncertain'
        self.assertIn('speech_not_confirmed', admission(aggregate, 'attempt-a')['reasons'])

    def test_unavailable_processing_and_denied_reference_rights_abstain(self):
        aggregate = ready_aggregate()
        aggregate['predictionLock']['payload']['rows'][0]['status'] = 'unavailable'
        aggregate['contentReviews'].append({'promptId': 'sun', 'record': {
            'decision': 'accepted', 'reference': {'rights': 'denied'}}})
        result = admission(aggregate, 'attempt-a')
        self.assertIn('model_unavailable', result['reasons'])
        self.assertIn('content_rights_not_allowed', result['reasons'])

    def test_unknown_identity_and_household_cannot_count_as_independent_engineering_evidence(self):
        aggregate = ready_aggregate()
        manifest = manifest_fixture()
        manifest['participants'][0].update({'identityLinkage': 'unknown', 'householdId': None})
        aggregate['manifest'] = bind_manifest(manifest)
        result = admission(aggregate, 'attempt-a')
        self.assertEqual(result['status'], 'abstain')
        self.assertIn('identity_linkage_unknown', result['reasons'])
        self.assertIn('household_unknown', result['reasons'])
        self.assertEqual(len(aggregate['manifest']['attempts']), 1)

    def test_later_content_restrictions_are_separate_from_immutable_historical_context(self):
        aggregate = ready_aggregate()
        before = admission(aggregate, 'attempt-a')
        aggregate['contentReviews'].append({'promptId': 'sun', 'record': {
            'decision': 'revise', 'reference': {'rights': 'denied'}}})
        after = admission(aggregate, 'attempt-a')
        self.assertEqual(after['status'], 'abstain')
        self.assertEqual(after['historicalContext'], before['historicalContext'])
        self.assertIn('content_revise', after['currentRestrictions'])
        self.assertIn('content_rights_not_allowed', after['currentRestrictions'])
        self.assertEqual(aggregate['manifest']['prompts'][0]['engineeringStatus'], 'accepted')


if __name__ == '__main__':
    unittest.main()
