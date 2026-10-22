import http.client
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest

from workbench.demo import make_manifest
from workbench.store import Store, verify_export
from workbench.server import make_server

class BrowserBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store.create(Path(self.temp.name) / 'project', make_manifest())
        self.server = make_server(self.store, 0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_reviewer_api_returns_only_its_blinded_projection(self):
        status, headers, body = self.request('GET', '/api/state?role=reviewer-a')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(set(data), {'project', 'reviewerId', 'sealed', 'items'})
        for forbidden in ('person-a', 'home-a', 'subjective_corpus_classes', 'development', 'invented-permission'):
            self.assertNotIn(forbidden, body.decode())
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_same_origin_review_save_survives_server_refresh(self):
        item = self.store.snapshot('reviewer-a')['items'][0]
        body = json.dumps({'reviewerId': 'reviewer-a', 'itemId': item['itemId'], 'answer': {
            'speech': 'present', 'promptMatch': 'matched', 'occurrence': 'resolved', 'target': 'expected',
            'quality': 'usable', 'notes': 'Invented API exercise.'}})
        status, _, result = self.request('POST', '/api/reviews', body, {
            'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{self.port}'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(result)['revision'], 1)
        status, _, result = self.request('GET', '/api/state?role=reviewer-a')
        self.assertEqual(json.loads(result)['items'][0]['review']['target'], 'expected')

    def test_export_is_a_downloadable_replayable_private_snapshot(self):
        status, headers, body = self.request('GET', '/api/export')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Disposition'], 'attachment; filename="assessment-workbench-export.json"')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertTrue(verify_export(json.loads(body))['verified'])

    def test_cross_origin_and_rebinding_hosts_cannot_save(self):
        for headers in [
            {'Origin': 'https://foreign.invalid'},
            {'Origin': f'http://127.0.0.1:{self.port}', 'Host': f'foreign.invalid:{self.port}'},
            {},
        ]:
            headers['Content-Type'] = 'application/json'
            status, _, body = self.request('POST', '/api/seal', '{"reviewerId":"reviewer-a"}', headers)
            self.assertEqual(status, 400)
            self.assertFalse(json.loads(body)['ok'])
        self.assertEqual(self.store.revision, 0)

    def test_duplicate_nonfinite_oversized_and_traversal_requests_fail(self):
        headers = {'Content-Type': 'application/json', 'Origin': f'http://127.0.0.1:{self.port}'}
        for body in ['{"reviewerId":"reviewer-a","reviewerId":"reviewer-b"}', '{"reviewerId":NaN}']:
            status, _, result = self.request('POST', '/api/seal', body, headers)
            self.assertEqual(status, 400)
            self.assertFalse(json.loads(result)['ok'])
        status, _, result = self.request('POST', '/api/seal', '{}', {**headers, 'Content-Length': str(1024 * 1024 + 1)})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(result)['error'], 'request_size')
        status, _, _ = self.request('GET', '/../../work/WORKLOG.md')
        self.assertEqual(status, 404)
        self.assertEqual(self.store.revision, 0)

    def test_preparation_projects_are_not_exposed_in_browser(self):
        from workbench.domain import bind_manifest, ValidationError
        manifest = make_manifest()
        manifest['mode'] = 'preparation'
        manifest['task']['definitionSource'] = 'pending'
        private = Store.create(Path(self.temp.name) / 'preparation', bind_manifest(manifest))
        with self.assertRaises(ValidationError):
            make_server(private, 0)

if __name__ == '__main__':
    unittest.main()
