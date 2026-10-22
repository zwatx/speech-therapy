"""Synthetic engineering tests; no corpus or model files are opened."""
import unittest
import time
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import os
import signal
import subprocess
import sys
from unittest.mock import patch
import wave
from consumer_assessment import benchmark
from consumer_assessment import bridge


def synthetic_inputs(directory):
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as writer:
        writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(16000)
        writer.writeframes(b'\xe8\x03' * 1600)
    wav = directory / 'synthetic.wav'; wav.write_bytes(audio.getvalue())
    prompt = directory / 'prompt.json'
    prompt.write_text(json.dumps({'schemaVersion': 2, 'language': 'en', 'transcript': 'BOB',
                                 'words': [{'text': 'BOB', 'phones': ['B', 'AA1', 'B']}],
                                 'targets': [{'id': 'private-target', 'wordIndex': 0,
                                              'phoneIndex': 2, 'targetPhone': 'B'}]}))
    return wav, prompt


class MemoryTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin', 'macOS ps population check')
    def test_live_sampler_observes_python_worker_and_node_grandchild(self):
        worker = subprocess.Popen([sys.executable, '-c',
            "import subprocess;subprocess.run(['node','-e','setTimeout(()=>{},500)'],check=True)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        try:
            sampler = benchmark.ProcessTreeSampler(os.getpid(), interval_seconds=0.01)
            with sampler: worker.wait(timeout=3)
            memory = sampler.report()
            self.assertFalse(memory['memoryUnavailable'])
            self.assertGreaterEqual(memory['descendants']['maximumObservedProcessCount'], 2)
            self.assertGreater(memory['descendants']['sampledPeakRssKiB'], 0)
            self.assertGreater(memory['benchmarkParent']['sampledPeakRssKiB'], 0)
        finally:
            if worker.poll() is None:
                os.killpg(worker.pid, signal.SIGKILL); worker.wait()

    def test_tree_includes_worker_and_grandchild_excludes_sampler_and_other_tree(self):
        # RSS in KiB: parent 10, worker 100, Node grandchild 200, other 900.
        snapshot = '10 1 10\n20 10 100\n30 20 200\n40 1 900\n50 10 800\n'
        sampler = benchmark.ProcessTreeSampler(10, interval_seconds=0.05)
        sampler.sample_snapshot(snapshot, sampler_pid=50)
        memory = sampler.report()
        self.assertEqual(memory['descendants']['sampledPeakRssKiB'], 300)
        self.assertEqual(memory['benchmarkParent']['sampledPeakRssKiB'], 10)
        self.assertEqual(memory['descendants']['maximumObservedProcessCount'], 2)
        self.assertEqual(memory['samplesSucceeded'], 1)
        self.assertEqual(memory['sampleIntervalMilliseconds'], 50)

    def test_sampling_retains_errors_without_fabricating_memory(self):
        def unavailable(): raise OSError('private machine detail must not escape')
        sampler = benchmark.ProcessTreeSampler(10, interval_seconds=0.01, snapshot_reader=unavailable)
        with sampler:
            time.sleep(0.025)
        memory = sampler.report()
        self.assertTrue(memory['memoryUnavailable'])
        self.assertIsNone(memory['descendants']['sampledPeakRssKiB'])
        self.assertIsNone(memory['benchmarkParent']['sampledPeakRssKiB'])
        self.assertGreaterEqual(memory['samplesFailed'], 2)
        self.assertNotIn('private', str(memory))

    def test_invalid_snapshot_does_not_increment_success_or_replace_peak(self):
        snapshots = iter([('10 1 10\n20 10 100\n', 50), ('unsafe command line', 50)])
        def read():
            try: return next(snapshots)
            except StopIteration: raise OSError()
        sampler = benchmark.ProcessTreeSampler(10, interval_seconds=0.01, snapshot_reader=read)
        with sampler: time.sleep(0.015)
        memory = sampler.report()
        self.assertEqual(memory['samplesSucceeded'], 1)
        self.assertGreaterEqual(memory['samplesFailed'], 1)
        self.assertEqual(memory['descendants']['sampledPeakRssKiB'], 100)
        self.assertTrue(memory['partialSampling'])


class ReportTests(unittest.TestCase):
    def test_environment_reports_installed_javascript_versions_without_machine_identity(self):
        report = benchmark.environment_report()
        self.assertIn('javascript', report['dependencies'])
        self.assertEqual(set(report['dependencies']['javascript']), {'@huggingface/transformers', 'onnxruntime-node'})
        for private in ('hostname', 'serial', 'ipAddress', 'username', 'executable'):
            self.assertNotIn(private, report)

    def test_three_attempts_bind_exact_inputs_and_keep_failures_in_denominator(self):
        requests = []
        def assessment(data):
            requests.append(data)
            if len(requests) == 2: raise RuntimeError('private context')
            response = bridge.response_base(data)
            response.update(outcome='processed', model={'id': 'ages-6-12-research-mixture',
                            'manifestSha256': bridge.MANIFEST_SHA},
                            targets=[{'id': 'private-target', 'subjectiveCorpusRatingProbabilities': [0.1, 0.2, 0.7]}])
            response['timingMilliseconds'] = {'total': 12, 'inference': 10}
            return response
        with tempfile.TemporaryDirectory() as temp:
            wav, prompt = synthetic_inputs(Path(temp))
            with patch.object(bridge, 'assess', side_effect=assessment):
                report = benchmark.run_benchmark(wav, prompt, 6)
            self.assertEqual(report['summary']['attemptCount'], 3)
            self.assertEqual(report['summary']['processedCount'], 2)
            self.assertEqual(report['summary']['unavailableCount'], 1)
            self.assertEqual(report['summary']['reasonCounts'], {'benchmark_runtime_failure': 1})
            self.assertEqual([a['callLabel'] for a in report['attempts']], ['first_call', 'repeated_call', 'repeated_call'])
            self.assertEqual(len({a['binding']['attemptId'] for a in report['attempts']}), 3)
            for attempt, data in zip(report['attempts'], requests):
                self.assertEqual(attempt['binding']['requestSha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(attempt['binding']['audioSha256'], hashlib.sha256(wav.read_bytes()).hexdigest())
                self.assertEqual(base64.b64decode(json.loads(data)['audioBase64']), wav.read_bytes())
                self.assertGreaterEqual(attempt['endToEndMilliseconds'], 0)
                self.assertEqual(attempt['requestedTargetCount'], 1)
            text = json.dumps(report)
            for private in ('audioBase64', 'subjectiveCorpusRatingProbabilities', 'private-target', 'private context', 'transcript', 'captureMetrics'):
                self.assertNotIn(private, text)
            for flag in ('learnerFeedbackEligible', 'clinicalUseEligible', 'productionUseEligible'):
                self.assertIs(report[flag], False)
            self.assertEqual(report['model']['manifestSha256'], bridge.MANIFEST_SHA)

    def test_existing_output_and_input_alias_fail_before_assessment(self):
        with tempfile.TemporaryDirectory() as temp:
            wav, prompt = synthetic_inputs(Path(temp))
            output = Path(temp) / 'report.json'; output.write_bytes(b'existing audit')
            alias = Path(temp) / 'alias.json'; alias.symlink_to(wav)
            original = wav.read_bytes()
            with patch.object(bridge, 'assess', side_effect=AssertionError('must not infer')) as assess:
                for destination in (output, wav, prompt, alias):
                    with self.assertRaises(FileExistsError):
                        benchmark.run_benchmark(wav, prompt, 6, output=destination)
                self.assertEqual(assess.call_count, 0)
            self.assertEqual(output.read_bytes(), b'existing audit')
            self.assertEqual(wav.read_bytes(), original)

    def test_invalid_inputs_fail_closed_before_report_or_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            wav, prompt = synthetic_inputs(Path(temp))
            output = Path(temp) / 'report.json'
            with patch.object(bridge, 'assess', side_effect=AssertionError('must not infer')) as assess:
                for age in (5, 13, True):
                    with self.assertRaises(bridge.Unavailable): benchmark.run_benchmark(wav, prompt, age, output=output)
                for repeats in (0, 6, True):
                    with self.assertRaises(ValueError): benchmark.run_benchmark(wav, prompt, 6, repeats=repeats, output=output)
                for interval in (0, float('nan'), 10):
                    with self.assertRaises(ValueError): benchmark.run_benchmark(wav, prompt, 6, interval_seconds=interval, output=output)
                prompt.write_bytes(b'{"schemaVersion":2,"schemaVersion":2}')
                with self.assertRaises(ValueError): benchmark.run_benchmark(wav, prompt, 6, output=output)
                wav, prompt = synthetic_inputs(Path(temp)); wav.write_bytes(b'not audio')
                with self.assertRaises(bridge.Unavailable): benchmark.run_benchmark(wav, prompt, 6, output=output)
                self.assertEqual(assess.call_count, 0)
            self.assertFalse(output.exists())

    def test_silence_cli_saves_only_aggregate_report_and_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            wav, prompt = synthetic_inputs(Path(temp))
            wav.write_bytes(wav.read_bytes()[:44] + b'\0' * 3200)
            output = Path(temp) / 'report.json'
            stdout = io.StringIO(); stderr = io.StringIO()
            from contextlib import redirect_stdout, redirect_stderr
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = benchmark.main(['--wav', str(wav), '--prompt', str(prompt), '--age-years', '6',
                                       '--repeats', '1', '--output', str(output)])
            self.assertEqual(code, 2)
            self.assertEqual(stderr.getvalue(), '')
            report = json.loads(output.read_bytes())
            self.assertEqual(json.loads(stdout.getvalue()), report)
            self.assertEqual(report['summary']['reasonCounts'], {'silence': 1})
            self.assertEqual(report['attempts'][0]['returnedTargetCount'], 0)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ['prompt.json', 'report.json', 'synthetic.wav'])
            self.assertIsNone(report['attempts'][0]['memory']['descendants']['sampledPeakRssKiB'])
            self.assertNotIn(str(temp), output.read_text())

    def test_invalid_bridge_binding_or_eligibility_becomes_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            wav, prompt = synthetic_inputs(Path(temp))
            for field in ('binding', 'learnerFeedbackEligible'):
                def invalid(data):
                    response = bridge.response_base(data); response['reason'] = 'silence'
                    response[field] = {} if field == 'binding' else True
                    return response
                with patch.object(bridge, 'assess', side_effect=invalid):
                    report = benchmark.run_benchmark(wav, prompt, 6, repeats=1)
                self.assertEqual(report['summary']['processedCount'], 0)
                self.assertEqual(report['summary']['unavailableCount'], 1)
                self.assertIs(report['learnerFeedbackEligible'], False)


if __name__ == '__main__': unittest.main()
