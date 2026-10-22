from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workbench.domain import ValidationError
from workbench.store import Store, verify_export
from workbench.demo import example_answer
from review_service.engine import Service, create_fixture_service, UNAVAILABLE_ANSWER


class AccessEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'service'
        self.service = create_fixture_service(self.root)
        self.actors = {role: {'accountId': 'fixture-' + role, 'generation': 1}
                       for role in ('coordinator', 'reviewer-a', 'reviewer-b', 'adjudicator')}

    def tearDown(self):
        self.temp.cleanup()

    def test_blinded_state_and_private_media_gate(self):
        actor = self.actors['reviewer-a']
        state = self.service.state(actor, 'demo-review')
        self.assertEqual(state['access']['role'], 'reviewer-a')
        self.assertNotIn('person-a', str(state))
        self.assertEqual(len(self.service.media(actor, 'demo-review', state['items'][0]['mediaId'])), 38444)
        self.assertFalse(state['items'][3]['recordingAvailable'])
        with self.assertRaises(ValidationError):
            self.service.media(actor, 'demo-review', '0' * 24)
        with self.assertRaises(ValidationError):
            self.service.export(actor, 'demo-review')

    def test_withdrawal_blocks_substantive_new_answers_but_keeps_unavailable_marker(self):
        coord = self.actors['coordinator']
        reviewer = self.actors['reviewer-a']
        item = self.service.state(reviewer, 'demo-review')['items'][0]
        self.service.mutate(coord, 'demo-review', 'withdraw', {'participantId': 'person-a', 'reason': 'Invented restriction.'})
        with self.assertRaises(ValidationError):
            self.service.mutate(reviewer, 'demo-review', 'reviews', {'itemId': item['itemId'], 'answer': example_answer('attempt-01', 'reviewer-a')})
        self.service.mutate(reviewer, 'demo-review', 'reviews', {'itemId': item['itemId'], 'answer': UNAVAILABLE_ANSWER})
        state = self.service.state(reviewer, 'demo-review')
        self.assertFalse(state['items'][0]['recordingAvailable'])
        self.assertEqual(state['items'][0]['review']['target'], 'unscorable')

    def test_role_spoof_and_cross_project_fail_without_mutation(self):
        reviewer = self.actors['reviewer-a']
        item = self.service.state(reviewer, 'demo-review')['items'][0]
        with self.assertRaises(ValidationError):
            self.service.mutate(reviewer, 'demo-review', 'reviews', {'reviewerId': 'reviewer-b', 'itemId': item['itemId'], 'answer': UNAVAILABLE_ANSWER})
        with self.assertRaises(ValidationError):
            self.service.mutate(reviewer, 'demo-review', 'withdraw', {'participantId': 'person-a', 'reason': 'No.'})
        with self.assertRaises(ValidationError):
            self.service.state(reviewer, 'content-preparation-a957a9e3291f0d90')
        self.assertEqual(self.service.export(self.actors['coordinator'], 'demo-review')['events'][-1]['seq'], 0)

    def test_operator_store_edit_is_quarantined_instead_of_unattributed(self):
        Store.open(self.root / 'projects' / 'demo-review').withdraw('person-a', 'Outside service boundary.')
        with self.assertRaisesRegex(ValidationError, 'project_quarantined'):
            Service.open(self.root)

    def test_actor_bound_content_and_export_replay(self):
        coord = self.actors['coordinator']
        self.service.mutate(coord, 'demo-review', 'content-reviews', {'promptId': 'rabbit', 'record': {
            'decision': 'accepted', 'notes': 'Invented engineering decision.', 'reference': None}})
        bundle = self.service.export(coord, 'demo-review')
        self.assertTrue(verify_export(bundle)['verified'])
        self.assertEqual(bundle['aggregate']['contentReviews'][0]['record']['reviewerId'], 'fixture-coordinator')
        self.assertEqual(Service.open(self.root).export(coord, 'demo-review'), bundle)

    def test_committed_review_with_missing_receipt_recovers_once(self):
        reviewer = self.actors['reviewer-a']
        item = self.service.state(reviewer, 'demo-review')['items'][0]
        with patch.object(self.service.audit, 'result', side_effect=OSError('injected receipt interruption')):
            with self.assertRaisesRegex(ValidationError, 'operation_outcome_unavailable'):
                self.service.mutate(reviewer, 'demo-review', 'reviews', {
                    'itemId':item['itemId'], 'answer':example_answer('attempt-01','reviewer-a')})
        reopened = Service.open(self.root)
        self.assertEqual(reopened.stores['demo-review'].revision, 1)
        receipts = [r['payload'] for r in reopened.audit.records() if r['kind'] == 'result']
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]['status'], 'applied')
        self.assertTrue(receipts[0]['recovered'])
        self.assertIsNotNone(reopened.state(reviewer, 'demo-review')['items'][0]['review'])
        with self.assertRaises(ValidationError):
            reopened.mutate(reviewer, 'demo-review', 'reviews', {
                'itemId':item['itemId'], 'answer':example_answer('attempt-01','reviewer-a')})
        self.assertEqual(reopened.stores['demo-review'].revision, 1)

    def test_review_interrupted_before_store_append_recovers_as_not_applied(self):
        reviewer = self.actors['reviewer-a']
        item = self.service.state(reviewer, 'demo-review')['items'][0]
        with patch.object(self.service.stores['demo-review'], 'submit_review', side_effect=OSError('injected source interruption')):
            with self.assertRaisesRegex(ValidationError, 'operation_outcome_unavailable'):
                self.service.mutate(reviewer, 'demo-review', 'reviews', {
                    'itemId':item['itemId'], 'answer':example_answer('attempt-01','reviewer-a')})
        reopened = Service.open(self.root)
        self.assertEqual(reopened.stores['demo-review'].revision, 0)
        receipts = [r['payload'] for r in reopened.audit.records() if r['kind'] == 'result']
        self.assertEqual(receipts[0]['status'], 'not_applied')
        self.assertTrue(receipts[0]['recovered'])
        self.assertIsNone(reopened.state(reviewer, 'demo-review')['items'][0]['review'])
