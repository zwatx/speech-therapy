import http.client
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest

from workbench.store import verify_export
from review_service.engine import create_fixture_service, UNAVAILABLE_ANSWER
from review_service.server import make_server
from review_service.auth import SessionManager
from review_service.engine import CONTENT_PROJECT
from workbench.demo import example_answer, make_predictions
from workbench.review import item_id


class AuthenticatedHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'service'
        self.service = create_fixture_service(self.root)
        self.credentials = json.loads((self.root / 'fixture-credentials.json').read_text())
        self.server = make_server(self.service, 0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            encoded = json.dumps(body) if body is not None and not isinstance(body, (str,bytes)) else body
            connection.request(method, path, body=encoded, headers=headers or {})
            result = connection.getresponse()
            return result.status, dict(result.getheaders()), result.read()
        finally:
            connection.close()

    def sign_in(self, role):
        status, headers, body = self.request('GET', '/api/session')
        self.assertEqual(status, 200)
        session = json.loads(body)
        cookie = headers['Set-Cookie'].split(';')[0]
        headers = {'Cookie': cookie, 'Content-Type': 'application/json',
                   'Origin': f'http://127.0.0.1:{self.port}', 'X-Review-CSRF': session['csrfToken']}
        account = 'fixture-' + role
        status, response, body = self.request('POST', '/api/login', {
            'accountId': account, 'password': self.credentials[account]}, headers)
        self.assertEqual(status, 200)
        session = json.loads(body)
        headers['Cookie'] = response['Set-Cookie'].split(';')[0]
        headers['X-Review-CSRF'] = session['csrfToken']
        return headers

    def test_anonymous_and_wrong_roles_cannot_fetch_protected_data(self):
        for path in ['/api/projects', '/api/projects/demo-review/state', '/api/projects/demo-review/export']:
            status, _, body = self.request('GET', path)
            self.assertEqual(status, 401)
            self.assertNotIn('person-a', body.decode())
        headers = self.sign_in('reviewer-a')
        status, _, body = self.request('GET', '/api/projects', headers=headers)
        self.assertEqual([p['id'] for p in json.loads(body)['projects']], ['demo-review'])
        status, _, body = self.request('GET', '/api/projects/demo-review/state', headers=headers)
        self.assertEqual(status, 200)
        self.assertNotIn('person-a', body.decode())
        self.assertEqual(json.loads(body)['access']['role'], 'reviewer-a')
        status, _, _ = self.request('GET', '/api/projects/demo-review/export', headers=headers)
        self.assertEqual(status, 403)
        denied = self.service.audit.records()[-1]['payload']
        self.assertEqual(denied, {'accountId': 'fixture-reviewer-a', 'projectId': None,
            'role': None, 'action': 'access_denied', 'objectId': None, 'outcome': 'denied'})
        status, _, body = self.request('GET', '/api/projects/demo-review/state?role=coordinator', headers=headers)
        self.assertEqual(status, 400)
        self.assertNotIn('person-a', body.decode())

    def test_media_is_role_scoped_and_never_returned_on_denial(self):
        a = self.sign_in('reviewer-a')
        _, _, body = self.request('GET', '/api/projects/demo-review/state', headers=a)
        items = json.loads(body)['items']
        status, headers, body = self.request('GET', '/api/projects/demo-review/media/' + items[0]['mediaId'], headers=a)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'audio/wav')
        self.assertEqual(len(body), 38444)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        b = self.sign_in('reviewer-b')
        status, _, denied = self.request('GET', '/api/projects/demo-review/media/' + items[0]['mediaId'], headers=b)
        self.assertEqual(status, 403)
        self.assertFalse(denied.startswith(b'RIFF'))
        self.assertNotIn('fixture-v1.wav', denied.decode())

    def test_origin_csrf_cookie_and_body_spoofing_are_rejected(self):
        headers = self.sign_in('reviewer-a')
        for bad in [{**headers, 'Origin': 'https://foreign.invalid'},
                    {**headers, 'X-Review-CSRF': 'wrong'},
                    {**headers, 'Cookie': headers['Cookie'] + '; ' + headers['Cookie']},
                    {**headers, 'Cookie': headers['Cookie'] + '; ' + headers['Cookie'].replace('=', ' =', 1)},
                    {**headers, 'Cookie': headers['Cookie'].replace('=', '="', 1) + '"'},
                    {**headers, 'Cookie': 'review_service_session='},
                    {**headers, 'Cookie': 'review_service_session=malformed'}]:
            status, _, _ = self.request('POST', '/api/projects/demo-review/seal', {}, bad)
            self.assertIn(status, (400, 403))
        _, _, body = self.request('GET', '/api/projects/demo-review/state', headers=headers)
        item = json.loads(body)['items'][0]
        status, _, _ = self.request('POST', '/api/projects/demo-review/reviews', {
            'reviewerId': 'reviewer-b', 'itemId': item['itemId'], 'answer': UNAVAILABLE_ANSWER}, headers)
        self.assertEqual(status, 400)
        self.assertEqual(self.service.stores['demo-review'].revision, 0)

    def test_logout_and_cli_revocation_invalidate_cookies(self):
        headers = self.sign_in('reviewer-a')
        status, returned, _ = self.request('POST', '/api/logout', {}, headers)
        self.assertEqual(status, 200)
        self.assertIn('Max-Age=0', returned['Set-Cookie'])
        status, _, _ = self.request('GET', '/api/projects', headers=headers)
        self.assertEqual(status, 401)
        headers = self.sign_in('reviewer-b')
        self.service.auth.revoke_account('fixture-reviewer-b')
        status, _, _ = self.request('GET', '/api/projects/demo-review/state', headers=headers)
        self.assertEqual(status, 401)

    def test_coordinator_export_is_private_replayable_attachment(self):
        headers = self.sign_in('coordinator')
        status, response, body = self.request('GET', '/api/projects/demo-review/export', headers=headers)
        self.assertEqual(status, 200)
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(verify_export(json.loads(body))['verified'])
        for password in self.credentials.values():
            if password in body.decode():
                self.fail('Credential leaked into assessment export')
        self.assertNotIn('passwordRecord', body.decode())

    def test_complete_authenticated_workflow_and_current_withdrawal(self):
        coordinator = self.sign_in('coordinator')
        status, _, body = self.request('GET', '/api/projects/demo-review/state', headers=coordinator)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['attempts']), 11)
        available = json.loads(body)['attempts'][0]['mediaId']
        self.assertEqual(self.request('GET', '/api/projects/demo-review/media/' + available, headers=coordinator)[0], 200)
        status, _, body = self.request('GET', f'/api/projects/{CONTENT_PROJECT}/state', headers=coordinator)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)['attempts']), 0)
        for prompt in ['rabbit', 'rural', 'sun', 'bird']:
            self.assertEqual(self.request('POST', '/api/projects/demo-review/content-reviews', {
                'promptId': prompt, 'record': {'decision': 'accepted', 'notes': 'Invented engineering exercise.', 'reference': None}}, coordinator)[0], 200)
        adjudicator = self.sign_in('adjudicator')
        status, _, body = self.request('GET', '/api/projects/demo-review/state', headers=adjudicator)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['items'], [])
        self.assertEqual(self.request('GET', '/api/projects/demo-review/media/' + available, headers=adjudicator)[0], 403)
        manifest = self.service.stores['demo-review'].manifest
        reviewers = {}
        for role in ['reviewer-a', 'reviewer-b']:
            headers = self.sign_in(role)
            reviewers[role] = headers
            for attempt in manifest['attempts']:
                answer = UNAVAILABLE_ANSWER if attempt['id'] in ['attempt-03','attempt-04','attempt-07'] else example_answer(attempt['id'], role)
                status, _, body = self.request('POST', '/api/projects/demo-review/reviews', {
                    'itemId': item_id(manifest, role, attempt['id']), 'answer': answer}, headers)
                self.assertEqual(status, 200, body)
            self.assertEqual(self.request('POST', '/api/projects/demo-review/seal', {}, headers)[0], 200)
        status, _, body = self.request('GET', '/api/projects/demo-review/state', headers=adjudicator)
        self.assertEqual(status, 200)
        items = json.loads(body)['items']
        self.assertEqual(len(items), 11)
        self.assertEqual(self.request('GET', '/api/projects/demo-review/media/' + items[0]['mediaId'], headers=adjudicator)[0], 200)
        unavailable = next(i for i in items if i['attemptId'] == 'attempt-04')
        self.assertEqual(self.request('POST', '/api/projects/demo-review/adjudications', {
            'attemptId': 'attempt-04', 'answer': {'target': 'expected', 'notes': 'Not authorized to observe.',
            'reviewedOriginals': [unavailable['reviewA']['sha256'], unavailable['reviewB']['sha256']]}}, adjudicator)[0], 403)
        disagreement = next(i for i in items if i['attemptId'] == 'attempt-10')
        status, _, body = self.request('POST', '/api/projects/demo-review/adjudications', {
            'attemptId': 'attempt-10', 'answer': {'target': 'altered', 'notes': 'Invented explicit resolution.',
            'reviewedOriginals': [disagreement['reviewA']['sha256'], disagreement['reviewB']['sha256']]}}, adjudicator)
        self.assertEqual(status, 200, body)
        prepared = make_predictions(manifest)
        self.assertEqual(self.request('POST', '/api/projects/demo-review/prediction-preview', {'rawJson': json.dumps(prepared)}, coordinator)[0], 200)
        status, _, body = self.request('POST', '/api/projects/demo-review/prediction-lock', {k: prepared[k] for k in ['payload','expectedSha256']}, coordinator)
        self.assertEqual(status, 200, body)
        bundle = json.loads(self.request('GET', '/api/projects/demo-review/export', headers=coordinator)[2])
        self.assertTrue(verify_export(bundle)['verified'])
        self.assertEqual(len(bundle['aggregate']['reviews']['reviewer-a']), 11)
        self.assertEqual(len(bundle['aggregate']['reviews']['reviewer-b']), 11)
        self.assertTrue(all(bundle['aggregate']['seals'].values()))
        self.assertEqual(self.request('POST', '/api/projects/demo-review/withdraw', {'participantId': 'person-a', 'reason': 'Invented withdrawal.'}, coordinator)[0], 200)
        self.assertEqual(self.request('GET', '/api/projects/demo-review/media/' + available, headers=coordinator)[0], 403)
        revision = self.service.stores['demo-review'].revision
        intents = sum(r['kind'] == 'intent' for r in self.service.audit.records())
        # The adjudicator opened this item before withdrawal; a stale draft is still denied.
        opened = items[0]
        self.assertEqual(self.request('POST', '/api/projects/demo-review/adjudications', {
            'attemptId': opened['attemptId'], 'answer': {'target':'expected', 'notes':'Stale invented draft.',
            'reviewedOriginals':[opened['reviewA']['sha256'],opened['reviewB']['sha256']]}}, adjudicator)[0], 403)
        self.assertEqual(self.service.stores['demo-review'].revision, revision)
        self.assertEqual(sum(r['kind'] == 'intent' for r in self.service.audit.records()), intents)
        with self.service.auth.lock():
            self.assertTrue(self.service._reconcile()['verified'])

    def test_passive_session_reads_do_not_extend_idle_expiry(self):
        current = [100.0]
        self.server.sessions = SessionManager(self.service.auth, clock=lambda: current[0])
        headers = self.sign_in('reviewer-a')
        current[0] += 899
        self.assertEqual(self.request('GET', '/api/session', headers=headers)[0], 200)
        # A denied operation must not renew the idle window either.
        self.assertEqual(self.request('GET', '/api/projects/demo-review/export', headers=headers)[0], 403)
        current[0] += 2
        self.assertEqual(self.request('GET', '/api/projects', headers=headers)[0], 401)

    def test_invalid_json_framing_and_host_never_mutate(self):
        headers = self.sign_in('reviewer-a')
        for raw in ['{"itemId":"a","itemId":"b","answer":{}}', '{"x":NaN}', '{"x":Infinity}', '{}'.encode('utf-16')]:
            self.assertEqual(self.request('POST', '/api/projects/demo-review/reviews', raw, headers)[0], 400)
        self.assertEqual(self.request('GET', '/api/projects', headers={**headers, 'Host': 'foreign.invalid'})[0], 400)
        self.assertEqual(self.request('POST', '/api/projects/demo-review/seal', {}, {**headers, 'Transfer-Encoding':'chunked'})[0], 400)
        self.assertEqual(self.service.stores['demo-review'].revision, 0)
