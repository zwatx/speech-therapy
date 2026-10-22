import copy
import unittest
from intended_validation import ProtocolError, blank_bundle, build_report, make_protocol, wilson
from workbench.domain import semantic_digest

S = 'a' * 64

def sample():
    alloc = [{'id': 'p1', 'positiveAttemptId': 'positive', 'challengeAttemptId': 'challenge',
              'positivePromptId': 'r-beginning-rabbit', 'challengePromptId': 'r-beginning-rabbit', 'challengeType': 'wrong_word'}]
    people = [{'id':'p1', 'householdId':'h1', 'linkageStatus':'declared', 'ageYears':9, 'variety':'declared-example', 'permissionRecordSha256':S, 'partition':'evaluation'}]
    protocol = make_protocol(S, S, semantic_digest(alloc), semantic_digest(people))
    bundle = blank_bundle(protocol)
    bundle.update(mode='invented_exercise', independenceDeclared=True, allocation=alloc)
    bundle['participants'] = [{'id':'p1', 'householdId':'h1', 'linkageStatus':'declared', 'ageYears':9,
                              'variety':'declared-example', 'permissionRecordSha256':S, 'partition':'evaluation'}]
    bundle['reviewerRecords'] = [{'id':role,'role':role,'identityEvidenceSha256':S,'qualificationEvidenceSha256':S,
                                  'conflictEvidenceSha256':S,'blindingEvidenceSha256':S} for role in ('reviewer-a','reviewer-b','adjudicator')]
    for order, role in enumerate(('positive', 'challenge'), 1):
        attempt = {'id':role,'participantId':'p1','order':order,'sessionId':'s1','conditionId':'room1',
                   'promptId':'r-beginning-rabbit','word':'rabbit','variantId':'variant-1','occurrenceIndex':0,
                   'primaryRole':role,'terminal':'processed' if role == 'positive' else 'unavailable','reason':'engineering',
                   'recordingSha256':str(order)*64,'modelManifestSha256':S,'admissionPolicySha256':S,
                   'admission':'admitted' if role == 'positive' else 'rejected','evidenceSha256':S,
                   'retryOf':None,'repeatOf':None,'replayOf':None,'acquiredAt':order}
        bundle['attempts'].append(attempt)
        obs = {'quality':'usable','speech':'present','word':'requested' if role == 'positive' else 'other',
               'variant':'accepted','occurrence':'resolved','target':'expected'}
        for reviewer in ('reviewer-a','reviewer-b'):
            row = {'id':role+'-'+reviewer,'reviewerId':reviewer,'blindItemId':'opaque-'+role+'-'+reviewer,
                   'attemptId':role,'recordingSha256':attempt['recordingSha256'],'protocolSha256':bundle['protocolSha256'],
                   'observations':copy.deepcopy(obs)}
            row['originalSha256'] = semantic_digest(row)
            bundle['originalReviews'].append(row)
    return protocol, bundle

def rehash(row):
    row['originalSha256'] = semantic_digest({k:v for k,v in row.items() if k != 'originalSha256'})

class ReportingTests(unittest.TestCase):
    def test_empty_preparation_is_complete_preparation_not_validation(self):
        protocol = make_protocol(S,S,semantic_digest([]),semantic_digest([]))
        report = build_report(protocol,blank_bundle(protocol))
        self.assertEqual(report['allAttemptDenominators']['attempts'],0)
        self.assertFalse(report['engineeringCriteriaMet'])
        self.assertIsNone(report['participantIntervals'])
        self.assertTrue(all(v is False for v in report['claimLimits'].values()))
    def test_fixed_precision_planning_values(self):
        self.assertAlmostEqual(wilson(0,210)['upper'],0.01796405,places=7)
        self.assertLess(wilson(4,210)['upper'],0.05)
        self.assertGreater(wilson(5,210)['upper'],0.05)
        self.assertGreater(wilson(198,210)['lower'],0.90)
        self.assertGreater(wilson(0,30)['upper'],0.11)
    def test_invented_rows_count_without_intended_intervals(self):
        p,b=sample(); r=build_report(p,b)
        self.assertEqual(r['evaluationPrimary']['positiveConfirmed']['numerator'],1)
        self.assertEqual(r['evaluationPrimary']['conservativeChallengeFailures']['numerator'],0)
        self.assertIsNone(r['participantIntervals'])
    def test_unsafe_and_unknown_are_separate_failures(self):
        p,b=sample(); a=b['attempts'][1]; a.update(terminal='processed',admission='admitted')
        r=build_report(p,b)
        self.assertEqual(r['evaluationPrimary']['observedUnsafeAdmissions']['numerator'],1)
        for row in b['originalReviews'][2:]: row['observations']['word']='uncertain'; rehash(row)
        r=build_report(p,b)
        self.assertEqual(r['evaluationPrimary']['observedUnsafeAdmissions']['numerator'],0)
        self.assertEqual(r['evaluationPrimary']['conservativeChallengeFailures']['numerator'],1)
    def test_failed_rejection_is_not_confirmed_safe(self):
        p,b=sample(); b['attempts'][1]['terminal']='failed'
        self.assertEqual(build_report(p,b)['evaluationPrimary']['conservativeChallengeFailures']['numerator'],1)
    def test_unresolved_disagreement_is_retained(self):
        p,b=sample(); b['originalReviews'][0]['observations']['word']='uncertain'; rehash(b['originalReviews'][0])
        r=build_report(p,b)
        self.assertEqual(r['unresolvedOriginalDisagreements'],['positive'])
        self.assertEqual(r['evaluationPrimary']['positiveConfirmed']['numerator'],0)
    def test_full_field_adjudication_binds_originals(self):
        p,b=sample(); b['originalReviews'][0]['observations']['word']='uncertain'; rehash(b['originalReviews'][0])
        a={'id':'decision','attemptId':'positive','adjudicatorId':'adjudicator',
           'originalASha256':b['originalReviews'][0]['originalSha256'],'originalBSha256':b['originalReviews'][1]['originalSha256'],
           'observations':copy.deepcopy(b['originalReviews'][1]['observations']),'reason':'qualified-later'}
        a['decisionSha256']=semantic_digest(a); b['adjudications']=[a]
        self.assertEqual(build_report(p,b)['unresolvedOriginalDisagreements'],[])
        b['adjudications'][0]['originalASha256']=S
        with self.assertRaises(ProtocolError): build_report(p,b)
    def test_unknown_linkage_suppresses_intervals(self):
        p,b=sample(); b['mode']='supplied_observations'; b['participants'][0]['householdId']=None
        p['participantRosterSha256']=semantic_digest(b['participants']);b['protocolSha256']=semantic_digest(p)
        for row in b['originalReviews']: row['protocolSha256']=b['protocolSha256'];rehash(row)
        r=build_report(p,b); self.assertIsNone(r['participantIntervals'])
        self.assertIn('unknown_household_or_identity_linkage',r['split']['violations'])
    def test_protocol_threshold_changes_refused(self):
        p,b=sample(); p['thresholds']['positiveLowerAtLeast']=0.1
        with self.assertRaises(ProtocolError):build_report(p,b)
    def test_allocation_cannot_be_reselected(self):
        p,b=sample(); b['allocation'][0]['positiveAttemptId']='challenge'
        with self.assertRaises(ProtocolError):build_report(p,b)
    def test_missing_duplicate_review_and_stale_audio_refused(self):
        for change in ('missing','duplicate','stale'):
            p,b=sample()
            if change=='missing':b['originalReviews'].pop()
            if change=='duplicate':b['originalReviews'].append(copy.deepcopy(b['originalReviews'][0]))
            if change=='stale':b['originalReviews'][0]['recordingSha256']=S; rehash(b['originalReviews'][0])
            with self.subTest(change=change),self.assertRaises(ProtocolError):build_report(p,b)
    def test_occurrence_out_of_pack_and_bool_age_refused(self):
        for change in ('occurrence','age'):
            p,b=sample()
            if change=='occurrence':b['attempts'][0]['occurrenceIndex']=2
            if change=='age':b['participants'][0]['ageYears']=True
            with self.subTest(change=change),self.assertRaises(ProtocolError):build_report(p,b)
    def test_retry_cannot_replace_primary(self):
        p,b=sample(); b['attempts'][1]['retryOf']='positive'
        with self.assertRaises(ProtocolError):build_report(p,b)
    def test_identical_bytes_cannot_be_new_recording_repeat(self):
        p,b=sample(); child=copy.deepcopy(b['attempts'][0]); child.update(id='repeat',primaryRole='none',order=3,repeatOf='positive')
        b['attempts'].append(child)
        with self.assertRaises(ProtocolError):build_report(p,b)
    def test_changing_partition_or_linkage_cannot_shrink_frozen_roster(self):
        for key, value in (('partition', 'development'), ('householdId', None)):
            p,b=sample(); b['participants'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ProtocolError): build_report(p,b)
    def test_adjudication_cannot_restore_unavailable_audio(self):
        p,b=sample(); a=b['attempts'][1]; a['recordingSha256']=None
        for row in b['originalReviews'][2:]:
            row['recordingSha256']=None
            row['observations']={field:'unavailable' for field in ('quality','speech','word','variant','occurrence')}
            row['observations']['target']='unscorable'; rehash(row)
        decision={'id':'decision','attemptId':'challenge','adjudicatorId':'adjudicator',
            'originalASha256':b['originalReviews'][2]['originalSha256'],'originalBSha256':b['originalReviews'][3]['originalSha256'],
            'observations':copy.deepcopy(b['originalReviews'][0]['observations']),'reason':'invalid-substantive-restore'}
        decision['decisionSha256']=semantic_digest(decision);b['adjudications']=[decision]
        with self.assertRaises(ProtocolError):build_report(p,b)
    def test_short_supplied_roster_cannot_claim_precision(self):
        p,b=sample();b['mode']='supplied_observations';r=build_report(p,b)
        self.assertIsNone(r['participantIntervals']);self.assertIn('evaluation_roster_size_mismatch',r['intervalSuppressionReasons'])
    def test_preassigned_challenge_cannot_be_replaced_by_easier_input(self):
        p,b=sample()
        for row in b['originalReviews'][2:]:
            row['observations'].update(speech='absent',word='unavailable',target='not_applicable');rehash(row)
        r=build_report(p,b)
        self.assertEqual(r['evaluationPrimary']['conservativeChallengeFailures']['numerator'],1)
        self.assertEqual(r['evaluationPrimary']['challengeAllocationMismatch']['numerator'],1)
    def test_absent_audio_cannot_have_expected_target(self):
        p,b=sample();b['attempts'][1]['recordingSha256']=None
        for row in b['originalReviews'][2:]:
            row['recordingSha256']=None
            row['observations']={field:'unavailable' for field in ('quality','speech','word','variant','occurrence')}
            row['observations']['target']='expected';rehash(row)
        with self.assertRaises(ProtocolError):build_report(p,b)
    def test_pending_permission_and_reviewer_records_are_reported(self):
        p,b=sample();b['participants'][0]['permissionRecordSha256']=None
        p['participantRosterSha256']=semantic_digest(b['participants']);b['protocolSha256']=semantic_digest(p)
        for row in b['originalReviews']:row['protocolSha256']=b['protocolSha256'];rehash(row)
        b['reviewerRecords'][0]['qualificationEvidenceSha256']=None
        r=build_report(p,b)
        self.assertIn('permission_evidence_pending',r['intervalSuppressionReasons'])
        self.assertIn('reviewer_evidence_pending',r['intervalSuppressionReasons'])
    def test_cross_partition_audio_reuse_suppresses_intervals(self):
        p,b=sample();person=copy.deepcopy(b['participants'][0]);person.update(id='p2',householdId='h2',partition='development')
        b['participants'].append(person)
        alloc=copy.deepcopy(b['allocation'][0]);alloc.update(id='p2',positiveAttemptId='positive2',challengeAttemptId='challenge2')
        b['allocation'].append(alloc)
        for parent in list(b['attempts']):
            a=copy.deepcopy(parent);a.update(id=parent['id']+'2',participantId='p2');b['attempts'].append(a)
        for parent in list(b['originalReviews']):
            row=copy.deepcopy(parent);row.update(id=parent['id']+'2',attemptId=parent['attemptId']+'2',blindItemId=parent['blindItemId']+'2');b['originalReviews'].append(row)
        p['participantRosterSha256']=semantic_digest(b['participants']);p['allocationSha256']=semantic_digest(b['allocation']);b['protocolSha256']=semantic_digest(p)
        for row in b['originalReviews']:row['protocolSha256']=b['protocolSha256'];rehash(row)
        self.assertIn('cross_partition_recording_overlap',build_report(p,b)['intervalSuppressionReasons'])
    def test_unsorted_child_before_malformed_parent_is_safe_error(self):
        p,b=sample();parent=b['attempts'][0];child=copy.deepcopy(parent)
        child.update(id='retry',order=3,primaryRole='none',retryOf='positive')
        parent['order']={'bad':'type'};b['attempts'].insert(0,child)
        with self.assertRaises(ProtocolError):build_report(p,b)
    def test_absent_audio_substantive_review_refused(self):
        p,b=sample(); b['attempts'][1]['recordingSha256']=None
        for row in b['originalReviews'][2:]: row['recordingSha256']=None; rehash(row)
        with self.assertRaises(ProtocolError):build_report(p,b)

if __name__=='__main__':unittest.main()
