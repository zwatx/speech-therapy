import base64
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from mobile_admission import contract
from mobile_admission.service import Executor


def body(audio=None):
    if audio is None:
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 16000)
        audio = output.getvalue()
    prompt = {'schemaVersion': 2, 'language': 'en', 'transcript': 'baby',
              'words': [{'text': 'baby', 'phones': ['B', 'EY1', 'B', 'IY0']}],
              'targets': [{'id': 'baby-0', 'wordIndex': 0, 'phoneIndex': 0, 'targetPhone': 'B'}]}
    return contract.canonical({'schemaVersion': 1, 'attemptId': '00000000-0000-4000-8000-000000000123',
                              'ageYears': 9, 'prompt': prompt, 'audioBase64': base64.b64encode(audio).decode()})


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.executor = Executor(Path(self.directory.name) / 'runtime')
    def tearDown(self): self.executor.close(); self.directory.cleanup()

    def test_pins_bind_exact_current_sources(self): self.assertEqual(contract.verify_sources(), contract.bindings())

    def test_request_audio_and_prompt_binding_and_no_evidence_projection(self):
        raw = body(); request, audio = contract.prepare(raw)
        result = contract.response(raw, request, audio, reason='silence')
        self.assertEqual(result['binding']['requestSha256'], contract.sha(raw))
        self.assertEqual(result['binding']['audioSha256'], contract.sha(audio))
        self.assertEqual(result['binding']['promptSha256'], contract.sha(contract.canonical(request['prompt'])))
        self.assertEqual(result['claimLimits'], contract.CLAIMS)
        self.assertNotIn('transcript', result)
        self.assertNotIn('research', result)

    def test_strict_request_shape_and_byte_bounds(self):
        for edit in (lambda r: r.update(schemaVersion=True), lambda r: r.update(ageYears=5),
                     lambda r: r.update(path='/tmp/untrusted.wav'), lambda r: r.update(audioBase64='!!!')):
            request = json.loads(body()); edit(request)
            with self.assertRaises(Exception): contract.prepare(contract.canonical(request))
        with self.assertRaises(ValueError): contract.strict_json(b'{"schemaVersion":1,"schemaVersion":2}')
        with self.assertRaises(UnicodeDecodeError): contract.strict_json(body().decode('utf-8').encode('utf-16'))
        with self.assertRaises(ValueError): contract.prepare(b'x' * 200001)
        with self.assertRaises(ValueError): contract.prepare(body(b'x' * 132097))

    def test_busy_is_bound_and_does_not_start_worker(self):
        self.executor.slot.acquire()
        try:
            with patch('mobile_admission.service.supervise') as supervisor:
                result = self.executor.execute(body()); supervisor.assert_not_called()
                self.assertEqual(result['reason'], 'busy')
                self.assertIsNotNone(result['binding']['audioSha256'])
        finally: self.executor.slot.release()

    def test_refuses_changed_sources_before_worker(self):
        with patch('mobile_admission.service.verify_sources', side_effect=ValueError()):
            with patch('mobile_admission.service.supervise') as supervisor:
                result = self.executor.execute(body()); supervisor.assert_not_called()
                self.assertEqual(result['reason'], 'source_binding_failed')

    def test_cleanup_failure_durably_blocks_restart_and_preserves_stage(self):
        with patch('mobile_admission.service.supervise', return_value={'cleanupConfirmed': False}):
            result = self.executor.execute(body())
        self.assertEqual(result['reason'], 'cleanup_unconfirmed')
        self.assertTrue((self.executor.runtime / 'cleanup-blocked').exists())
        self.assertEqual(len(list(self.executor.runtime.glob('attempt-*'))), 1)
        self.executor.close()
        self.executor = Executor(self.executor.runtime)
        with patch('mobile_admission.service.supervise') as supervisor:
            self.assertEqual(self.executor.execute(body())['reason'], 'cleanup_unconfirmed')
            supervisor.assert_not_called()

    def test_worker_timeout_confirmed_cleanup_removes_stage(self):
        with patch('mobile_admission.service.supervise', return_value={'cleanupConfirmed': True, 'timedOut': True}):
            self.assertEqual(self.executor.execute(body())['reason'], 'timeout')
        self.assertFalse(list(self.executor.runtime.glob('attempt-*')))
        self.assertFalse((self.executor.runtime / 'cleanup-blocked').exists())

    def test_stage_delete_failure_cannot_return_success(self):
        raw = body(); request, audio = contract.prepare(raw)
        result = contract.response(raw, request, audio, reason='silence')
        def supervise(command, *args, **kwargs):
            path = Path(command[-1]) / 'result.json'
            path.write_bytes(contract.canonical(result)); path.chmod(0o600)
            return {'cleanupConfirmed': True, 'timedOut': False, 'workerExitCode': 0}
        with patch('mobile_admission.service.supervise', side_effect=supervise), patch('mobile_admission.service.shutil.rmtree', side_effect=OSError()):
            self.assertEqual(self.executor.execute(raw)['reason'], 'cleanup_unconfirmed')
        self.assertTrue((self.executor.runtime / 'cleanup-blocked').exists())

    def test_owner_lock_refuses_second_service(self):
        with self.assertRaises(BlockingIOError): Executor(self.executor.runtime)

    def test_interrupted_stage_blocks_before_another_start(self):
        self.executor.close()
        (self.executor.runtime / 'attempt-interrupted').mkdir()
        self.executor = Executor(self.executor.runtime)
        self.assertEqual(self.executor.execute(body())['reason'], 'cleanup_unconfirmed')


if __name__ == '__main__': unittest.main()

class IntentTests(unittest.TestCase):
    def test_prelaunch_intent_failure_starts_no_worker_and_blocks_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = Executor(Path(directory) / 'runtime')
            try:
                with patch('mobile_admission.service.block', side_effect=OSError()), patch('mobile_admission.service.supervise') as supervisor:
                    result = executor.execute(body())
                    self.assertEqual(result['reason'], 'cleanup_unconfirmed')
                    supervisor.assert_not_called()
                self.assertTrue(executor.is_blocked())
            finally: executor.close()

    def test_late_marker_failure_preserves_prelaunch_intent(self):
        from mobile_admission.service import block as original_block
        with tempfile.TemporaryDirectory() as directory:
            executor = Executor(Path(directory) / 'runtime')
            def injected_block(path, name='cleanup-blocked'):
                if name == 'cleanup-blocked': raise OSError('injected_marker_write_failure')
                original_block(path, name)
            try:
                with patch('mobile_admission.service.block', side_effect=injected_block), patch('mobile_admission.service.supervise', return_value={'cleanupConfirmed': False}):
                    self.assertEqual(executor.execute(body())['reason'], 'cleanup_unconfirmed')
                self.assertTrue((executor.runtime / 'cleanup-required').exists())
                self.assertTrue(executor.is_blocked())
                executor.close()
                executor = Executor(executor.runtime)
                with patch('mobile_admission.service.supervise') as supervisor:
                    self.assertEqual(executor.execute(body())['reason'], 'cleanup_unconfirmed')
                    supervisor.assert_not_called()
            finally: executor.close()

class ProjectionTests(unittest.TestCase):
    def prepared(self):
        raw = body(); request, audio = contract.prepare(raw)
        from consumer_assessment.bridge import MANIFEST_SHA
        binding = contract.response(raw, request, audio)['binding']
        research = {'schemaVersion': 1, 'reason': None, 'researchOnly': True, 'outcome': 'processed', 'promptMatch': 'unverified',
                    'learnerFeedbackEligible': False, 'clinicalUseEligible': False,
                    'productionUseEligible': False,
                    'binding': {'audioSha256': binding['audioSha256'], 'promptSha256': binding['promptSha256'], 'requestSha256': contract.sha(raw), 'attemptId': request['attemptId']},
                    'model': {'id': 'ages-6-12-research-mixture', 'manifestSha256': MANIFEST_SHA},
                    'targets': [{'subjectiveCorpusRatingProbabilities': [0.1, 0.2, 0.7]}]}
        result = {'status': 'processed', 'reason': None, 'claimLimits': dict(contract.CLAIMS),
                  'binding': {'audioSha256': binding['audioSha256'], 'promptSha256': binding['promptSha256'],
                              'policySha256': binding['policySha256'], 'modelManifestSha256': binding['modelManifestSha256'],
                              'ageYears': 9, 'bridgeRequestSha256': contract.sha(raw), 'evidenceSha256': 'e' * 64},
                  'capture': {'valid': True, 'audioSha256': contract.sha(audio)},
                  'speechEvidence': {'passed': True, 'probabilities': [0.9]},
                  'wordMatch': {'admitted': True, 'evidenceSha256': 'e' * 64,
                                'policySha256': binding['policySha256'],
                                'expectedWordSha256': contract.sha(contract.canonical('baby'))}, 'research': research,
                  'recognition': {'transcript': 'private unit-only string'}}
        return raw, request, audio, result

    def test_unit_only_projection_removes_all_private_evidence(self):
        raw, request, audio, result = self.prepared()
        public = contract.project(result, raw, request, audio)
        self.assertEqual(public['status'], 'processed')
        self.assertTrue(public['speechAdmissionPassed'])
        self.assertTrue(public['wordAdmissionPassed'])
        self.assertTrue(public['researchProcessed'])
        self.assertNotIn('private unit-only string', contract.canonical(public).decode())
        self.assertNotIn('probabilities', contract.canonical(public).decode())
        self.assertEqual(public['claimLimits'], contract.CLAIMS)

    def test_unit_projection_refuses_changed_gate_research_model_or_binding(self):
        mutations = [lambda r: r['speechEvidence'].update(passed=False),
                     lambda r: r['wordMatch'].update(admitted=False),
                     lambda r: r['research'].update(learnerFeedbackEligible=True),
                     lambda r: r['research'].update(promptMatch='verified'),
                     lambda r: r['research']['model'].update(manifestSha256='changed'),
                     lambda r: r['research']['binding'].update(audioSha256='changed'),
                     lambda r: r['binding'].update(policySha256='changed')]
        for mutation in mutations:
            raw, request, audio, result = self.prepared(); mutation(result)
            public = contract.project(result, raw, request, audio)
            self.assertEqual(public['status'], 'unavailable')
            self.assertEqual(public['reason'], 'research_binding_failed')
            self.assertFalse(public['researchProcessed'])

class FramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        from mobile_admission.service import LocalServer
        cls.directory = tempfile.TemporaryDirectory()
        class FakeExecutor:
            runtime = Path(cls.directory.name)
            blocked = False
            calls = 0
            def execute(self, raw):
                self.calls += 1
                request, audio = contract.prepare(raw)
                return contract.response(raw, request, audio, reason='silence')
        cls.executor = FakeExecutor()
        cls.server = LocalServer(cls.executor)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.directory.cleanup()
    def send(self, *, headers=None, path='/v1/admission', duplicate_host=False):
        import http.client
        raw = body()
        connection = http.client.HTTPConnection('127.0.0.1', 8778, timeout=5)
        try:
            connection.putrequest('POST', path, skip_host=True)
            values = {'Host': '127.0.0.1:8778', 'Content-Type': 'application/json', 'Content-Length': str(len(raw))}
            values.update(headers or {})
            for key, value in values.items(): connection.putheader(key, value)
            if duplicate_host: connection.putheader('Host', '127.0.0.1:8778')
            connection.endheaders(raw)
            response = connection.getresponse()
            return response.status, response.getheader('Cache-Control'), json.loads(response.read())
        finally: connection.close()
    def test_actual_http_framing_dispatch_uses_unit_only_projection(self):
        before = self.executor.calls
        status, cache, response = self.send()
        self.assertEqual(status, 200); self.assertEqual(cache, 'no-store')
        self.assertEqual(response['reason'], 'silence')
        self.assertEqual(response['binding']['requestSha256'], contract.sha(body()))
        self.assertEqual(self.executor.calls, before + 1)
    def test_host_origin_duplicates_transfer_type_path_and_length_refuse_before_dispatch(self):
        before = self.executor.calls
        for headers in ({'Host': 'localhost:8778'}, {'Host': 'example.invalid:8778'},
                        {'Origin': 'http://127.0.0.1:8778'}, {'Transfer-Encoding': 'chunked'},
                        {'Content-Type': 'text/plain'}, {'Content-Length': '200001'},
                        {'Content-Length': '0'}, {'Content-Length': '-1'}):
            self.assertEqual(self.send(headers=headers)[0], 400)
        self.assertEqual(self.send(duplicate_host=True)[0], 400)
        self.assertEqual(self.send(path='/v1/assessment')[0], 400)
        self.assertEqual(self.executor.calls, before)


class CompletedProofTests(unittest.TestCase):
    prepared = ProjectionTests.prepared
    def test_processed_refuses_missing_null_malformed_or_inconsistent_evidence_and_bridge_proof(self):
        for field in ('evidenceSha256', 'bridgeRequestSha256'):
            for value in (None, '', 'x' * 64, '0' * 63):
                raw, request, audio, result = self.prepared()
                result['binding'][field] = value
                if field == 'bridgeRequestSha256': result['research']['binding']['requestSha256'] = value
                self.assertEqual(contract.project(result, raw, request, audio)['status'], 'unavailable')
            raw, request, audio, result = self.prepared(); del result['binding'][field]
            self.assertEqual(contract.project(result, raw, request, audio)['status'], 'unavailable')
        for mutation in (lambda r: r['capture'].update(valid=False),
                         lambda r: r['wordMatch'].update(evidenceSha256='0' * 64),
                         lambda r: r['wordMatch'].update(expectedWordSha256='0' * 64),
                         lambda r: r['research']['binding'].update(attemptId='bad')):
            raw, request, audio, result = self.prepared(); mutation(result)
            self.assertEqual(contract.project(result, raw, request, audio)['status'], 'unavailable')

class UnsupportedTests(unittest.TestCase):
    def test_structurally_valid_unsupported_ZH_is_bound_refusal_without_worker(self):
        request = json.loads(body())
        request['prompt'] = {'schemaVersion': 2, 'language': 'en', 'transcript': 'treasure',
                             'words': [{'text': 'treasure', 'phones': ['T', 'R', 'EH1', 'ZH', 'ER0']}],
                             'targets': [{'id': 'treasure-3', 'wordIndex': 0, 'phoneIndex': 3, 'targetPhone': 'ZH'}]}
        raw = contract.canonical(request)
        with tempfile.TemporaryDirectory() as directory:
            executor = Executor(Path(directory) / 'runtime')
            try:
                with patch('mobile_admission.service.supervise') as supervisor:
                    result = executor.execute(raw); supervisor.assert_not_called()
                self.assertEqual(result['reason'], 'unsupported_target')
                self.assertEqual(result['binding']['requestSha256'], contract.sha(raw))
                self.assertEqual(result['binding']['promptSha256'], contract.sha(contract.canonical(request['prompt'])))
                self.assertIsNotNone(result['binding']['audioSha256'])
                request['prompt']['targets'][0]['phoneIndex'] = 999
                self.assertEqual(executor.execute(contract.canonical(request))['reason'], 'invalid_request')
            finally: executor.close()

class DiagnosticTests(unittest.TestCase):
    def test_monitor_failure_cannot_publish_processed_after_recovered_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = Executor(Path(directory) / 'runtime')
            try:
                with patch('mobile_admission.service.supervise', return_value={
                        'cleanupConfirmed': True, 'cleanupFailurePhase': 'monitor_scan', 'timedOut': False, 'workerExitCode': 0}):
                    self.assertEqual(executor.execute(body())['reason'], 'assessment_failed')
                self.assertFalse(list(executor.runtime.glob('attempt-*')))
                self.assertFalse((executor.runtime / 'cleanup-required').exists())
            finally: executor.close()

    def test_diagnostic_persistence_failure_discards_result_after_confirmed_safety_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            executor = Executor(Path(directory) / 'runtime')
            try:
                with patch('mobile_admission.service.supervise', return_value={
                        'cleanupConfirmed': True, 'timedOut': False, 'workerExitCode': 0}), patch('mobile_admission.service.save_runtime', side_effect=OSError()):
                    self.assertEqual(executor.execute(body())['reason'], 'assessment_failed')
                self.assertFalse(executor.is_blocked())
                self.assertFalse(list(executor.runtime.glob('attempt-*')))
                self.assertFalse((executor.runtime / 'cleanup-required').exists())
            finally: executor.close()

    def test_private_diagnostic_filters_arguments_environment_and_evidence(self):
        from mobile_admission.service import save_runtime
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_runtime(root, {'cleanupConfirmed': True, 'workerExitCode': 0,
                                'tracked': [{'pid': 1, 'ppid': 0, 'state': 'Z', 'started': 'unit-only-stamp', 'argv': 'private'}],
                                'argv': 'private', 'environment': 'private', 'transcript': 'private'})
            data = (root / 'last-runtime.json').read_text()
            self.assertNotIn('private', data)
            self.assertEqual((root / 'last-runtime.json').stat().st_mode & 0o777, 0o600)

class ObservedIdentityTests(unittest.TestCase):
    def test_diagnostic_last_observed_is_filtered_to_owned_initial_identities(self):
        from mobile_admission.service import save_runtime
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_runtime(root, {'tracked': [{'pid': 10, 'ppid': 1, 'state': 'R', 'started': 'owned'}],
                                'lastObserved': {10: {'pid': 10, 'ppid': 1, 'state': 'Z', 'started': 'owned'},
                                                 20: {'pid': 20, 'ppid': 1, 'state': 'R', 'started': 'unrelated'}}})
            data = json.loads((root / 'last-runtime.json').read_text())
            self.assertEqual(data['runtime']['lastObserved'], [{'pid': 10, 'ppid': 1, 'state': 'Z', 'started': 'owned'}])
            self.assertNotIn('unrelated', (root / 'last-runtime.json').read_text())
