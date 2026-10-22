from copy import deepcopy
import hashlib
import io
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
import wave

from review_service.auth import AuthStore, SessionManager
from recording_access import Vault
from journey.engine import Journey
from journey.models import JourneyError
from workbench.domain import semantic_digest


def pcm():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\x00\x00' * 3200)
    return stream.getvalue()


def declaration(raw, retain=1900000000):
    granted = {'status': 'granted', 'expiresAt': 1800000030, 'evidenceSha256': 'a' * 64,
               'declaration': 'Invented nonspeech fixture, no actual participant or authority claim'}
    result = {'schemaVersion': 1, 'expectedSha256': hashlib.sha256(raw).hexdigest(),
            'source': {'kind': 'invented_fixture', 'description': 'Generated nonspeech unit fixture',
                       'originalSha256': hashlib.sha256(raw).hexdigest(), 'provenanceEvidenceSha256': 'b' * 64},
            'subject': {'id': 'invented-source', 'kind': 'invented', 'ageYears': None,
                        'identityDeclaration': None, 'identityEvidenceSha256': None,
                        'consentAuthorityDeclaration': None, 'consentAuthorityEvidenceSha256': None},
            'permissions': {purpose: {'rights': deepcopy(granted), 'consent': deepcopy(granted)}
                            for purpose in ('storage', 'review', 'research', 'inference', 'redistribution')},
            'retainUntil': retain}
    result['permissions']['research']['rights']['expiresAt'] = 1800000020
    return result


class UnitAdapter:
    unit_test_only = True
    def __init__(self, blocked=False):
        self.entered, self.release = threading.Event(), threading.Event()
        self.calls = 0
        if not blocked: self.release.set()
    def declaration(self):
        return {'schemaVersion': 1, 'version': 'unit-only-v1', 'unitTestOnly': True, 'policySha256': 'b'*64, 'modelManifestSha256': 'c'*64}
    def assess(self, raw, prompt, age_years=9):
        self.calls += 1
        self.entered.set()
        if not self.release.wait(5): raise RuntimeError('unit worker timeout')
        return {'schemaVersion': 1, 'status': 'processed', 'reason': None,
                'capture': {'valid': True}, 'speechEvidence': {'status': 'detected'},
                'wordMatch': {'admitted': True, 'reason': None},
                'research': {'outcome': 'processed', 'reason': None, 'PRIVATE_SCORE': 0.9, 'promptMatch':'unverified', **{k:False for k in ('learnerFeedbackEligible','clinicalUseEligible','productionUseEligible')}, 'binding':{'audioSha256':hashlib.sha256(raw).hexdigest(),'promptSha256':semantic_digest(prompt),'requestSha256':'d'*64}},
                'binding': {'audioSha256':hashlib.sha256(raw).hexdigest(),'promptSha256':semantic_digest(prompt),'ageYears':9,'policySha256':'b'*64,'modelManifestSha256':'c'*64,'evidenceSha256':'e'*64,'bridgeRequestSha256':'d'*64}, 'runtime': None, 'claimLimits': {'learnerFeedbackEligible': False, 'clinicalUseEligible': False, 'productionUseEligible': False}}


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.auth = AuthStore.create(self.root)
        self.password = secrets.token_urlsafe(24)
        self.auth.add_account('operator', self.password)
        self.auth.assign('operator', 'journey-test', 'coordinator')
        self.monotonic, self.utc = [0], [1800000000]
        self.sessions = SessionManager(self.auth, clock=lambda: self.monotonic[0])
        self.vault = Vault.create(self.root, self.sessions, 'journey-test', utc_clock=lambda: self.utc[0])
        self.raw = pcm()
        source_declaration = declaration(self.raw)
        if getattr(self,'extended_permissions',False):
            for scope in source_declaration['permissions'].values():
                for grant in scope.values():grant['expiresAt']=1900000000
        imported = self.vault.import_recording(self.raw, source_declaration)
        self.inventory = [{'id': 'a' * 24, 'recordingId': imported['recordingId'], 'sha256': imported['sha256'],
                           'label': 'Generated silence', 'kind': 'invented_fixture', 'sourceWord': None, 'ageKnown': False}]
        self.prompts = [{'id': 'rabbit-r', 'word': 'rabbit', 'sourceWord': 'rabbit', 'targetPhone': 'R',
                         'variantId': 'variant-1', 'phones': ['R', 'AE', 'B', 'AH', 'T'], 'occurrenceIndex': 0, 'supported': True}]
        if getattr(self, 'unsupported_prompt', False):
            self.prompts[0].update(targetPhone='ZH',phones=['ZH'],occurrenceIndex=0,supported=False)
        token, _ = self.sessions.bootstrap()
        self.token, public = self.sessions.login(token, 'operator', self.password)
        self.csrf = public['csrfToken']
        self.adapter = UnitAdapter()
        self.engine = Journey.create(self.root, self.sessions, self.vault, self.prompts, self.inventory, self.adapter, utc_clock=lambda: self.utc[0])
        self.addCleanup(lambda: self.engine.wait_idle(5))
        self.addCleanup(self.adapter.release.set)

    def start(self, key='start-a', repeat=None):
        return self.engine.start(self.token, self.csrf, {'idempotencyKey': key, 'promptId': 'rabbit-r', 'itemId': 'a' * 24, 'repeatOf': repeat})

    def test_authenticated_assessment_practice_and_identical_repeat_are_linked_without_scores(self):
        started = self.start()
        self.assertEqual(started['status'], 'pending')
        self.assertTrue(self.engine.wait_idle(5))
        first = self.engine.attempt(self.token, started['attemptId'])
        self.assertEqual(first['status'], 'available')
        self.assertNotIn('PRIVATE_SCORE', str(first))
        self.assertFalse(first['result']['claimLimits']['learnerFeedbackEligible'])
        self.engine.practice(self.token, self.csrf, {'idempotencyKey': 'practice-a', 'promptId': 'rabbit-r', 'attemptId': first['id']})
        repeated = self.start('repeat-a', first['id'])
        self.assertTrue(self.engine.wait_idle(5))
        second = self.engine.attempt(self.token, repeated['attemptId'])
        self.assertEqual(second['repeatOf'], first['id'])
        self.assertEqual(second['replay']['kind'], 'same_bytes_replay')
        self.assertFalse(second['replay']['independentReassessment'])
        state = self.engine.state(self.token)
        self.assertEqual(state['participation'], {'planned': 2, 'started': 2, 'terminal': 2, 'manualPractice': 1, 'replays': 1})
        self.assertEqual(self.adapter.calls, 2)
        self.assertEqual(len(state['history']), 2)

    def test_cancel_is_durable_idempotent_and_ignores_late_worker(self):
        self.adapter.release.clear()
        begun = self.start()
        self.assertTrue(self.adapter.entered.wait(2))
        body = {'idempotencyKey': 'cancel-a', 'attemptId': begun['attemptId']}
        cancelled = self.engine.cancel(self.token, self.csrf, body)
        self.assertEqual(cancelled['status'], 'cancelled')
        count = len(self.engine.store.load()[0])
        self.assertEqual(self.engine.cancel(self.token, self.csrf, body), cancelled)
        self.assertEqual(len(self.engine.store.load()[0]), count)
        self.adapter.release.set(); self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(self.engine.attempt(self.token, begun['attemptId'])['status'], 'cancelled')
        self.assertEqual(list((self.root / 'journey-results').iterdir()), [])

    def test_missing_csrf_cannot_start_or_persist_practice(self):
        with self.assertRaises(Exception):
            self.engine.start(self.token, None, {'idempotencyKey': 'missing', 'promptId': 'rabbit-r', 'itemId': 'a' * 24, 'repeatOf': None})
        self.assertEqual(self.engine.store.load()[1]['attempts'], {})
        with self.assertRaises(Exception):
            self.engine.practice(self.token, None, {'idempotencyKey': 'missing-practice', 'promptId': 'rabbit-r', 'attemptId': None})
        self.assertEqual(self.engine.store.load()[1]['practice'], [])

    def test_clear_retains_denominator_and_reopen_does_not_restore_results(self):
        begun = self.start(); self.assertTrue(self.engine.wait_idle(5))
        self.engine.clear_history(self.token, self.csrf, {'idempotencyKey': 'clear-a'})
        reopened = Journey.open(self.root, self.sessions, self.vault, self.adapter, utc_clock=lambda: self.utc[0])
        state = reopened.state(self.token)
        self.assertEqual(state['history'][0]['status'], 'forgotten')
        self.assertIsNone(state['history'][0]['result'])
        self.assertEqual(state['participation']['planned'], 1)
        self.assertEqual(list((self.root / 'journey-results').iterdir()), [])

    def test_duplicate_start_does_not_repeat_acoustics(self):
        begun = self.start(); self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(self.start()['attemptId'], begun['attemptId'])
        self.assertEqual(self.adapter.calls, 1)
        with self.assertRaises(JourneyError): self.start(repeat=begun['attemptId'])

    def test_revocation_during_compute_suppresses_private_output(self):
        self.adapter.release.clear(); begun = self.start(); self.assertTrue(self.adapter.entered.wait(2))
        self.auth.revoke_account('operator')
        self.adapter.release.set(); self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(self.engine.store.load()[1]['attempts'][begun['attemptId']]['status'], 'suppressed')
        self.assertEqual(list((self.root / 'journey-results').iterdir()), [])

    def test_expired_retention_scrubs_on_read(self):
        begun = self.start(); self.assertTrue(self.engine.wait_idle(5))
        self.utc[0] += 86400
        row = self.engine.attempt(self.token, begun['attemptId'])
        self.assertEqual(row['status'], 'suppressed'); self.assertEqual(row['reason'], 'retention_expired')
        self.assertIsNone(row['result']); self.assertEqual(list((self.root / 'journey-results').iterdir()), [])

    def test_pending_intent_reopen_is_interrupted_late_result_ignored(self):
        self.adapter.release.clear(); begun = self.start(); self.assertTrue(self.adapter.entered.wait(2))
        reopened = Journey.open(self.root, self.sessions, self.vault, self.adapter, utc_clock=lambda: self.utc[0])
        self.assertEqual(reopened.attempt(self.token, begun['attemptId'])['status'], 'interrupted')
        self.adapter.release.set(); self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(reopened.attempt(self.token, begun['attemptId'])['status'], 'interrupted')
        self.assertEqual(list((self.root / 'journey-results').iterdir()), [])

    def test_withdrawal_while_pending_is_suppressed_before_worker_finishes(self):
        self.adapter.release.clear(); begun=self.start(); self.assertTrue(self.adapter.entered.wait(2))
        self.vault.withdraw_subject(self.token,self.csrf,'invented-source','owner_withdrawal')
        row=self.engine.attempt(self.token,begun['attemptId'])
        self.assertEqual(row['status'],'suppressed');self.assertIsNone(row['result'])
        self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_session_expiration_during_worker_suppresses_and_cannot_poll(self):
        self.adapter.release.clear();begun=self.start();self.assertTrue(self.adapter.entered.wait(2))
        self.monotonic[0]=901;self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))
        with self.assertRaises(Exception):self.engine.attempt(self.token,begun['attemptId'])
        self.assertEqual(self.engine.store.load()[1]['attempts'][begun['attemptId']]['status'],'suppressed')
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_other_account_cannot_read_history_or_start_without_coordinator(self):
        begun=self.start();self.assertTrue(self.engine.wait_idle(5))
        password=secrets.token_urlsafe(24);self.auth.add_account('other',password);self.auth.assign('other','journey-test','reviewer-a')
        boot,_=self.sessions.bootstrap();token,public=self.sessions.login(boot,'other',password)
        self.assertEqual(self.engine.state(token)['history'],[])
        with self.assertRaises(JourneyError):self.engine.attempt(token,begun['attemptId'])
        with self.assertRaises(Exception):self.engine.start(token,public['csrfToken'],{'idempotencyKey':'other-start','promptId':'rabbit-r','itemId':'a'*24,'repeatOf':None})
        self.assertEqual(self.engine.state(token)['history'],[])

    def test_result_binding_tamper_is_not_accepted_as_processed(self):
        original=self.adapter.assess
        def wrong(*args,**kwargs):
            result=original(*args,**kwargs);result['binding']['audioSha256']='f'*64;return result
        self.adapter.assess=wrong;begun=self.start();self.assertTrue(self.engine.wait_idle(5))
        row=self.engine.attempt(self.token,begun['attemptId'])
        self.assertEqual(row['status'],'unavailable');self.assertIsNone(row['result'])
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_denied_source_is_planned_unavailable_and_manual_practice_remains_possible(self):
        self.vault.restrict(self.token,self.csrf,self.inventory[0]['recordingId'],'inference','purpose_denied')
        begun=self.start();self.assertEqual(begun['status'],'unavailable');self.assertEqual(self.adapter.calls,0)
        self.engine.practice(self.token,self.csrf,{'idempotencyKey':'denied-practice','promptId':'rabbit-r','attemptId':begun['attemptId']})
        state=self.engine.state(self.token)
        self.assertEqual(state['participation']['planned'],1);self.assertEqual(state['participation']['started'],0)
        self.assertEqual(state['participation']['manualPractice'],1)

    def test_ordinary_capacity_reserves_cancel_and_forgetting(self):
        from unittest.mock import patch
        self.adapter.release.clear()
        with patch('journey.store.ORDINARY_EVENTS',4):
            begun=self.start();self.assertTrue(self.adapter.entered.wait(2))
            self.engine.practice(self.token,self.csrf,{'idempotencyKey':'capacity-practice','promptId':'rabbit-r','attemptId':begun['attemptId']})
            before=(self.root/'journey.jsonl').read_bytes()
            with self.assertRaises(JourneyError):self.engine.practice(self.token,self.csrf,{'idempotencyKey':'capacity-extra','promptId':'rabbit-r','attemptId':None})
            self.assertEqual((self.root/'journey.jsonl').read_bytes(),before)
            self.engine.cancel(self.token,self.csrf,{'idempotencyKey':'capacity-cancel','attemptId':begun['attemptId']})
            self.engine.clear_history(self.token,self.csrf,{'idempotencyKey':'capacity-clear'})
            self.assertEqual(self.engine.attempt(self.token,begun['attemptId'])['status'],'forgotten')
            self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))

    def test_invalid_append_and_partial_journal_do_not_manufacture_results(self):
        before=(self.root/'journey.jsonl').read_bytes()
        with self.assertRaises(Exception):self.engine.store.append('practice',{'at':self.utc[0],'actor':[],'promptId':'rabbit-r','attemptId':None,'idempotencyKey':'bad','actionSha256':'f'*64})
        self.assertEqual((self.root/'journey.jsonl').read_bytes(),before)
        with (self.root/'journey.jsonl').open('ab') as output:output.write(b'{partial')
        with self.assertRaises(JourneyError):Journey.open(self.root,self.sessions,self.vault,self.adapter,utc_clock=lambda:self.utc[0])

    def test_foreign_project_assignment_is_not_current_project_access(self):
        password=secrets.token_urlsafe(24);self.auth.add_account('foreign',password);self.auth.assign('foreign','other-project','coordinator')
        boot,_=self.sessions.bootstrap();token,public=self.sessions.login(boot,'foreign',password)
        with self.assertRaises(Exception):self.engine.state(token)
        with self.assertRaises(Exception):self.engine.start(token,public['csrfToken'],{'idempotencyKey':'foreign','promptId':'rabbit-r','itemId':'a'*24,'repeatOf':None})
        self.assertEqual(self.engine.store.load()[1]['attempts'],{})

    def test_unavailable_envelope_stages_are_scoped_and_expire(self):
        original=self.adapter.assess
        def unavailable(*args,**kwargs):
            result=original(*args,**kwargs);result.update(status='unavailable',reason='requested_word_not_matched',research=None);result['wordMatch']['admitted']=False;return result
        self.adapter.assess=unavailable;begun=self.start();self.assertTrue(self.engine.wait_idle(5))
        row=self.engine.attempt(self.token,begun['attemptId'])
        self.assertEqual(row['status'],'unavailable');self.assertEqual(row['result']['capture']['status'],'valid')
        self.assertEqual(row['result']['wordMatch']['reason'],None);self.assertIsNone(row['result']['research'])
        self.utc[0]+=86400
        self.assertIsNone(self.engine.attempt(self.token,begun['attemptId'])['result'])
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_stage_projection_separates_model_gate_from_verified_speech(self):
        from journey.models import public_result, prompt_request
        value=self.adapter.assess(self.raw,prompt_request(self.prompts[0]))
        value['speechEvidence']={'passed':True,'speechPresenceVerified':False,'probabilities':[0.9]}
        projected=public_result(value)
        self.assertEqual(projected['speechEvidence']['status'],'passed')
        self.assertNotIn('probabilities',str(projected))
        value['speechEvidence']['passed']=False
        self.assertEqual(public_result(value)['speechEvidence']['status'],'not_passed')

    def test_password_generation_change_scrubs_previous_output_after_new_login(self):
        begun=self.start();self.assertTrue(self.engine.wait_idle(5))
        replacement=secrets.token_urlsafe(24);self.auth.reset_password('operator',replacement)
        with self.assertRaises(Exception):self.engine.attempt(self.token,begun['attemptId'])
        boot,_=self.sessions.bootstrap();token,_=self.sessions.login(boot,'operator',replacement)
        row=self.engine.attempt(token,begun['attemptId'])
        self.assertEqual(row['status'],'suppressed');self.assertEqual(row['reason'],'authorization_changed');self.assertIsNone(row['result'])
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_permission_expiry_denies_and_scrubs_result_before_result_retention(self):
        begun=self.start();self.assertTrue(self.engine.wait_idle(5));self.utc[0]+=30
        row=self.engine.attempt(self.token,begun['attemptId'])
        self.assertEqual(row['status'],'suppressed');self.assertEqual(row['reason'],'recording_unavailable');self.assertIsNone(row['result'])
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_cancel_intent_survives_terminal_write_failure_and_blocks_late_result(self):
        from unittest.mock import patch
        self.adapter.release.clear();begun=self.start();self.assertTrue(self.adapter.entered.wait(2))
        append=self.engine.store.append
        def fault(kind,payload):
            if kind=='terminal':raise OSError('unit interrupted terminal append')
            return append(kind,payload)
        with patch.object(self.engine.store,'append',side_effect=fault):
            with self.assertRaises(OSError):self.engine.cancel(self.token,self.csrf,{'idempotencyKey':'fault-cancel','attemptId':begun['attemptId']})
        self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))
        row=self.engine.attempt(self.token,begun['attemptId']);self.assertEqual(row['status'],'cancelled');self.assertIsNone(row['result'])
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_clear_intent_recovers_exact_targets_and_empty_clear_binds_idempotency(self):
        from unittest.mock import patch
        body={'idempotencyKey':'empty-clear'}
        self.engine.clear_history(self.token,self.csrf,body)
        begun=self.start();self.assertTrue(self.engine.wait_idle(5))
        self.engine.clear_history(self.token,self.csrf,body)
        self.assertEqual(self.engine.attempt(self.token,begun['attemptId'])['status'],'available')
        append=self.engine.store.append
        def fault(kind,payload):
            if kind=='discard':raise OSError('unit interrupted clear append')
            return append(kind,payload)
        with patch.object(self.engine.store,'append',side_effect=fault):
            with self.assertRaises(OSError):self.engine.clear_history(self.token,self.csrf,{'idempotencyKey':'fault-clear'})
        row=self.engine.attempt(self.token,begun['attemptId']);self.assertEqual(row['status'],'forgotten');self.assertIsNone(row['result'])
        later=self.start('later-after-clear');self.assertTrue(self.engine.wait_idle(5))
        self.engine.clear_history(self.token,self.csrf,{'idempotencyKey':'fault-clear'})
        self.assertEqual(self.engine.attempt(self.token,later['attemptId'])['status'],'available')

    def test_worker_completion_checks_retention_before_private_write(self):
        self.adapter.release.clear();begun=self.start();self.assertTrue(self.adapter.entered.wait(2))
        self.utc[0]+=86400;self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))
        _,state=self.engine.store.load();row=state['attempts'][begun['attemptId']]
        self.assertEqual(row['status'],'suppressed');self.assertEqual(row['reason'],'retention_expired')
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_research_denied_before_start_never_reads_or_calls_model(self):
        self.vault.restrict(self.token,self.csrf,self.inventory[0]['recordingId'],'research','purpose_denied')
        before=len(self.vault.journal.load()[0]);begun=self.start()
        self.assertEqual(begun['status'],'unavailable');self.assertEqual(self.adapter.calls,0)
        self.assertEqual(len(self.vault.journal.load()[0]),before)
        self.assertEqual(self.engine.state(self.token)['participation']['started'],0)

    def test_research_revoked_midworker_and_after_output_suppresses_both(self):
        self.adapter.release.clear();begun=self.start();self.assertTrue(self.adapter.entered.wait(2))
        self.vault.restrict(self.token,self.csrf,self.inventory[0]['recordingId'],'research','purpose_denied')
        self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(self.engine.attempt(self.token,begun['attemptId'])['status'],'suppressed')
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_research_restriction_after_output_scrubs_before_retained_read(self):
        begun=self.start();self.assertTrue(self.engine.wait_idle(5))
        self.vault.restrict(self.token,self.csrf,self.inventory[0]['recordingId'],'research','purpose_denied')
        row=self.engine.attempt(self.token,begun['attemptId']);self.assertEqual(row['status'],'suppressed');self.assertIsNone(row['result'])
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_research_permission_expiry_alone_scrubs_result(self):
        begun=self.start();self.assertTrue(self.engine.wait_idle(5));self.utc[0]+=20
        row=self.engine.attempt(self.token,begun['attemptId'])
        self.assertEqual(row['status'],'suppressed');self.assertEqual(row['reason'],'recording_unavailable');self.assertIsNone(row['result'])
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])


class UnsupportedTests(unittest.TestCase):
    unsupported_prompt=True
    def setUp(self):JourneyTests.setUp(self)
    def test_source_bound_unsupported_target_is_honest_without_acoustic_call(self):
        begun=self.engine.start(self.token,self.csrf,{'idempotencyKey':'unsupported','promptId':'rabbit-r','itemId':'a'*24,'repeatOf':None})
        self.assertEqual(begun['status'],'unavailable');self.assertEqual(self.adapter.calls,0)
        row=self.engine.attempt(self.token,begun['attemptId']);self.assertEqual(row['reason'],'unsupported_target')
        self.assertIsNone(row['result']);self.assertEqual(self.engine.state(self.token)['participation']['started'],0)
        self.engine.practice(self.token,self.csrf,{'idempotencyKey':'unsupported-practice','promptId':'rabbit-r','attemptId':begun['attemptId']})


class PublicationDeadlineTests(unittest.TestCase):
    extended_permissions=True
    def setUp(self):JourneyTests.setUp(self)
    def test_clock_crossing_during_last_pipeline_check_never_writes_private_output(self):
        from unittest.mock import patch
        self.adapter.release.clear()
        begun=self.engine.start(self.token,self.csrf,{'idempotencyKey':'deadline-edge','promptId':'rabbit-r','itemId':'a'*24,'repeatOf':None})
        self.assertTrue(self.adapter.entered.wait(2));self.utc[0]+=86400-1
        original=self.engine._pipeline_current;calls=[0]
        def advances():
            answer=original();calls[0]+=1
            if calls[0]==2:self.utc[0]+=2
            return answer
        with patch.object(self.engine,'_pipeline_current',side_effect=advances):
            self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])
        row=self.engine.store.load()[1]['attempts'][begun['attemptId']]
        self.assertEqual(row['status'],'suppressed');self.assertEqual(row['reason'],'retention_expired')

    def test_session_expiring_during_last_pipeline_check_is_terminal_suppressed(self):
        from unittest.mock import patch
        self.adapter.release.clear()
        begun=self.engine.start(self.token,self.csrf,{'idempotencyKey':'session-edge','promptId':'rabbit-r','itemId':'a'*24,'repeatOf':None})
        self.assertTrue(self.adapter.entered.wait(2));original=self.engine._pipeline_current;calls=[0]
        def advances():
            answer=original();calls[0]+=1
            if calls[0]==2:self.monotonic[0]=901
            return answer
        with patch.object(self.engine,'_pipeline_current',side_effect=advances):
            self.adapter.release.set();self.assertTrue(self.engine.wait_idle(5))
        row=self.engine.store.load()[1]['attempts'][begun['attemptId']]
        self.assertEqual(row['status'],'suppressed');self.assertEqual(row['reason'],'authorization_changed')
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])

    def test_unpublished_result_from_failed_terminal_is_removed_by_one_expiry_cleanup(self):
        from unittest.mock import patch
        append=self.engine.store.append
        def fault(kind,payload):
            if kind=='terminal':raise OSError('unit failed terminal write')
            return append(kind,payload)
        with patch.object(self.engine.store,'append',side_effect=fault):
            begun=self.engine.start(self.token,self.csrf,{'idempotencyKey':'unpublished-edge','promptId':'rabbit-r','itemId':'a'*24,'repeatOf':None})
            self.assertTrue(self.engine.wait_idle(5))
        self.assertEqual(len(list((self.root/'journey-results').iterdir())),1)
        self.utc[0]+=86400;self.engine.cleanup()
        self.assertEqual(list((self.root/'journey-results').iterdir()),[])
        self.assertEqual(self.engine.store.load()[1]['attempts'][begun['attemptId']]['status'],'suppressed')

    def test_extra_word_safe_reason_is_preserved_without_transcript(self):
        from journey.models import public_result,prompt_request
        value=self.adapter.assess(self.raw,prompt_request(self.prompts[0]));value.update(status='unavailable',reason='single_word_required',research=None)
        value['wordMatch'].update(admitted=False,reason='single_word_required',transcript='PRIVATE extra words')
        projected=public_result(value)
        self.assertEqual(projected['reason'],'single_word_required');self.assertEqual(projected['wordMatch']['reason'],'single_word_required')
        self.assertNotIn('PRIVATE',str(projected))
