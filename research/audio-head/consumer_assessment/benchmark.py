"""Aggregate-only runtime and sampled process-tree RSS for the unchanged bridge.

Run with --wav, --prompt (schema 2), --age-years and optional fresh --output.
No raw requests, audio, features or prediction distributions are exported.
"""
from __future__ import annotations

import os
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
from importlib import metadata
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
import uuid

from consumer_assessment import bridge

MODEL = {'id': 'ages-6-12-research-mixture', 'manifestSha256': bridge.MANIFEST_SHA}
REASONS = {'request_too_large', 'invalid_request', 'age_out_of_range', 'unsupported_target',
           'invalid_audio', 'audio_too_long', 'silence', 'clipping', 'timeout',
           'model_unavailable', 'inference_failed'}


def process_snapshot():
    """macOS ps emits only numeric PID, parent PID and RSS; no command strings."""
    if sys.platform != 'darwin': raise NotImplementedError('macOS sampling required')
    process = subprocess.Popen(['/bin/ps', '-axo', 'pid=,ppid=,rss='],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    try:
        output, _ = process.communicate(timeout=2)
        if process.returncode != 0: raise ChildProcessError('ps failed')
        return output, process.pid
    finally:
        if process.poll() is None:
            process.kill(); process.wait()


class ProcessTreeSampler:
    """Accumulate safe numeric ps snapshots without retaining process identities."""

    def __init__(self, parent_pid, *, interval_seconds=0.05, snapshot_reader=process_snapshot):
        if type(parent_pid) is not int or parent_pid <= 0: raise ValueError('invalid parent PID')
        if type(interval_seconds) not in (int, float) or not math.isfinite(interval_seconds) or not 0.01 <= interval_seconds <= 1:
            raise ValueError('sample interval must be 0.01–1 seconds')
        self.parent_pid = parent_pid
        self.interval_seconds = interval_seconds
        self.snapshot_reader = snapshot_reader
        self.succeeded = 0
        self.errors = {}
        self.parent_peak = None
        self.descendant_peak = None
        self.process_count = 0
        self.stop_event = threading.Event()
        self.thread = None
        self.previous_sample = None
        self.maximum_gap = None

    def sample(self):
        now = time.perf_counter()
        if self.previous_sample is not None:
            self.maximum_gap = max(self.maximum_gap or 0, now - self.previous_sample)
        self.previous_sample = now
        try:
            snapshot, pid = self.snapshot_reader()
            self.sample_snapshot(snapshot, sampler_pid=pid)
        except Exception as exc:
            reason = ('unsupported_platform' if isinstance(exc, NotImplementedError) else
                      'ps_timeout' if isinstance(exc, subprocess.TimeoutExpired) else
                      'invalid_snapshot' if isinstance(exc, (ValueError, TypeError)) else 'ps_unavailable')
            self.errors[reason] = self.errors.get(reason, 0) + 1

    def __enter__(self):
        self.sample()
        def loop():
            while not self.stop_event.wait(self.interval_seconds): self.sample()
        self.thread = threading.Thread(target=loop, name='assessment-rss-sampler', daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_event.set()
        self.thread.join()
        self.sample()

    def sample_snapshot(self, text, *, sampler_pid):
        rows = {}
        for line in text.splitlines():
            parts = line.split()
            if len(parts) != 3 or any(not part.isdecimal() for part in parts):
                raise ValueError('invalid process snapshot')
            pid, ppid, rss = map(int, parts)
            if pid in rows or pid == 0: raise ValueError('invalid process snapshot')
            rows[pid] = (ppid, rss)
        if self.parent_pid not in rows: raise ValueError('parent absent')
        population = {self.parent_pid}
        while True:
            added = {pid for pid, (ppid, _) in rows.items()
                     if ppid in population and pid not in population and pid != sampler_pid}
            if not added: break
            population.update(added)
        descendants = population - {self.parent_pid}
        rss = sum(rows[pid][1] for pid in descendants)
        self.parent_peak = max(self.parent_peak or 0, rows[self.parent_pid][1])
        if descendants: self.descendant_peak = max(self.descendant_peak or 0, rss)
        self.process_count = max(self.process_count, len(descendants))
        self.succeeded += 1

    def report(self):
        return {'metric': 'sampled aggregate resident set size', 'unit': 'KiB',
                'sampleIntervalMilliseconds': self.interval_seconds * 1000,
                'samplesSucceeded': self.succeeded,
                'samplesFailed': sum(self.errors.values()), 'sampleErrorCounts': dict(self.errors),
                'partialSampling': bool(self.errors),
                'maximumObservedSampleStartGapMilliseconds': None if self.maximum_gap is None else self.maximum_gap * 1000,
                'memoryUnavailable': self.succeeded == 0,
                'unavailableReason': 'no_successful_samples' if self.succeeded == 0 else None,
                'descendants': {'population': 'all benchmark-process descendants excluding sampler ps',
                                'sampledPeakRssKiB': self.descendant_peak,
                                'memoryUnavailable': self.descendant_peak is None,
                                'unavailableReason': 'no_descendant_observed' if self.succeeded and self.descendant_peak is None else
                                                     'no_successful_samples' if not self.succeeded else None,
                                'maximumObservedProcessCount': self.process_count},
                'benchmarkParent': {'population': 'benchmark Python process only; separate from descendants',
                                    'sampledPeakRssKiB': self.parent_peak},
                'limitations': ['Shared resident pages may be counted more than once across processes.',
                                'Finite sampling can miss transient peaks; ps rows may reflect slightly different instants.',
                                'This is not an exact process high-water mark or an iPhone memory measurement.']}


def environment_report():
    """Versions and CPU details only; never hostname, user, paths, serial or IP."""
    def command(arguments):
        try:
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=2, check=True)
            return result.stdout.strip()
        except Exception: return None
    versions = {}
    for name in ('numpy', 'torch', 'transformers', 'tokenizers', 'safetensors', 'huggingface_hub'):
        try: versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError: versions[name] = None
    transformer_manifest = (bridge.ROOT / 'packages/audio-model-adapter/node_modules/@huggingface/transformers/package.json').resolve()
    # Read installed package metadata, not manifests' requested version ranges.
    # Fixed Node code resolves the ONNX dependency from the actual transformer package.
    javascript = {'@huggingface/transformers': None, 'onnxruntime-node': None}
    try:
        result = subprocess.run(['node', '-e',
            "const fs=require('node:fs'),{createRequire}=require('node:module');"
            "const p=process.argv[1],r=createRequire(p);"
            "const out={'@huggingface/transformers':JSON.parse(fs.readFileSync(p,'utf8')).version,'onnxruntime-node':null};"
            "try{const path=require('node:path');let d=path.dirname(r.resolve('onnxruntime-node'));"
            "for(let i=0;i<8;i++){const m=path.join(d,'package.json');if(fs.existsSync(m)){const v=JSON.parse(fs.readFileSync(m,'utf8'));"
            "if(v.name==='onnxruntime-node'){out['onnxruntime-node']=v.version;break}}d=path.dirname(d)}}catch{};"
            "process.stdout.write(JSON.stringify(out));", str(transformer_manifest)],
            capture_output=True, text=True, timeout=2, check=True)
        actual = bridge.strict_json(result.stdout.encode())
        if set(actual) == set(javascript) and all(v is None or isinstance(v, str) for v in actual.values()):
            javascript = actual
    except Exception: pass
    return {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine(),
            'macOSVersion': platform.mac_ver()[0] or None, 'python': platform.python_version(),
            'pythonImplementation': platform.python_implementation(),
            'cpu': {'model': command(['/usr/sbin/sysctl', '-n', 'machdep.cpu.brand_string']) if sys.platform == 'darwin' else None,
                    'logicalCpuCount': os.cpu_count()},
            'dependencies': {**versions, 'node': command(['node', '--version']), 'javascript': javascript}}


def bounded_read(path, limit):
    with Path(path).open('rb') as source: data = source.read(limit + 1)
    if len(data) > limit: raise ValueError('input exceeds bridge limit')
    return data


def aggregate_response(response, binding, requested_targets):
    """Validate bindings/eligibility, then expose only approved aggregate fields."""
    if not isinstance(response, dict) or any(response.get(k) is not v for k, v in bridge.FLAGS.items()):
        raise ValueError('invalid bridge response')
    if response.get('binding') != binding or response.get('promptMatch') != 'unverified':
        raise ValueError('invalid bridge binding')
    outcome = response.get('outcome'); reason = response.get('reason'); targets = response.get('targets')
    timings = response.get('timingMilliseconds')
    if not isinstance(timings, dict) or set(timings) != {'total', 'inference'} or any(
            type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in timings.values()):
        raise ValueError('invalid timing')
    if not isinstance(targets, list): raise ValueError('invalid target count')
    if outcome == 'processed':
        if reason is not None or response.get('model') != MODEL or len(targets) != requested_targets:
            raise ValueError('invalid processed response')
    elif outcome == 'unavailable':
        if reason not in REASONS or targets or response.get('model') is not None:
            raise ValueError('invalid unavailable response')
    else: raise ValueError('invalid outcome')
    return {'outcome': outcome, 'reason': reason, 'returnedTargetCount': len(targets),
            'responseTimingMilliseconds': dict(timings), 'responseModel': response.get('model')}


def run_benchmark(wav, prompt, age_years, *, repeats=3, interval_seconds=0.05, output=None):
    """Assess exact supplied inputs 1–5 times, returning an aggregate-only audit.

    Existing output files (including input aliases/symlinks) fail before inference.
    Each assessment still owns a fresh bridge worker and temporary-file cleanup.
    """
    if type(repeats) is not int or not 1 <= repeats <= 5: raise ValueError('repeats must be 1–5')
    # Validate sampler configuration before reading inputs or reserving output.
    ProcessTreeSampler(os.getpid(), interval_seconds=interval_seconds)
    audio = bounded_read(wav, bridge.MAX_AUDIO_BYTES)
    prompt_value = bridge.strict_json(bounded_read(prompt, 40_000))
    requests = []
    for _ in range(repeats):
        request = {'schemaVersion': 1, 'attemptId': str(uuid.uuid4()), 'ageYears': age_years,
                   'prompt': prompt_value, 'audioBase64': base64.b64encode(audio).decode('ascii')}
        data = bridge.canonical_bytes(request)
        bridge.prepare(data)  # fail closed for malformed age/prompt/WAV before any inference
        requests.append(data)
    reserved = None
    try:
        if output is not None:
            # O_EXCL also rejects dangling symlinks and hard links to an input.
            fd = os.open(Path(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            reserved = os.fdopen(fd, 'wb')
        report = {'schemaVersion': 1, **bridge.FLAGS,
                  'timestampUTC': datetime.now(timezone.utc).isoformat(),
                  'model': dict(MODEL), 'promptMatch': 'unverified', 'ageScopeYears': [6, 12],
                  'environment': environment_report(),
                  'sourceSha256': {'benchmark': bridge.sha(Path(__file__).read_bytes()),
                                   'bridge': bridge.sha(Path(bridge.__file__).read_bytes()),
                                   'worker': bridge.sha(Path(bridge.__file__).with_name('worker.py').read_bytes())},
                  'execution': {'bridge': 'consumer_assessment.bridge.assess',
                                'repeatCount': repeats, 'workerLifecycle': 'fresh process if model work starts; capture rejections start no worker',
                                'firstCallState': 'first call in this benchmark run',
                                'repeatedCallState': 'repeated calls with fresh process-cold model workers',
                                'osDiskCache': 'uncontrolled', 'residentModelWarmup': False,
                                'machineColdClaim': False,
                                'samplingWindow': 'immediately before through immediately after each assessment',
                                'threadConfiguration': 'unchanged bridge/worker settings'},
                  'attempts': []}
        for index, data in enumerate(requests):
            binding = bridge.response_base(data)['binding']
            sampler = ProcessTreeSampler(os.getpid(), interval_seconds=interval_seconds)
            with sampler:
                started = time.perf_counter()
                try:
                    response = bridge.assess(data)  # No deliberate bridge artifact export.
                    elapsed = (time.perf_counter() - started) * 1000
                    aggregate = aggregate_response(response, binding, len(prompt_value['targets']))
                except bridge.CleanupUnconfirmed:
                    raise
                except Exception:
                    elapsed = (time.perf_counter() - started) * 1000
                    aggregate = {'outcome': 'unavailable', 'reason': 'benchmark_runtime_failure',
                                 'returnedTargetCount': 0, 'responseTimingMilliseconds': None, 'responseModel': None}
            report['attempts'].append({'attemptNumber': index + 1,
                                       'callLabel': 'first_call' if index == 0 else 'repeated_call',
                                       'workerState': 'process_cold_if_started', 'binding': binding,
                                       'requestedTargetCount': len(prompt_value['targets']),
                                       'endToEndMilliseconds': elapsed, **aggregate, 'memory': sampler.report()})
        attempts = report['attempts']
        times = [a['endToEndMilliseconds'] for a in attempts]
        report['summary'] = {'attemptCount': len(attempts),
                             'processedCount': sum(a['outcome'] == 'processed' for a in attempts),
                             'unavailableCount': sum(a['outcome'] == 'unavailable' for a in attempts),
                             'reasonCounts': dict(Counter(a['reason'] for a in attempts if a['reason'] is not None)),
                             'runtimeDenominator': 'all attempted assessments, including unavailable and runtime failures',
                             'endToEndMilliseconds': {'minimum': min(times), 'maximum': max(times),
                                                       'mean': statistics.mean(times), 'median': statistics.median(times)}}
        if reserved is not None:
            reserved.write(bridge.canonical_bytes(report) + b'\n'); reserved.close(); reserved = None
        return report
    except BaseException:
        if reserved is not None:
            reserved.close(); Path(output).unlink()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wav', type=Path, required=True)
    parser.add_argument('--prompt', type=Path, required=True)
    parser.add_argument('--age-years', type=int, required=True)
    parser.add_argument('--repeats', type=int, default=3, choices=range(1, 6))
    parser.add_argument('--sample-interval-seconds', type=float, default=0.05)
    parser.add_argument('--output', type=Path, help='Fresh aggregate JSON file; never overwritten')
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(args.wav, args.prompt, args.age_years, repeats=args.repeats,
                               interval_seconds=args.sample_interval_seconds, output=args.output)
    except Exception:
        print('Benchmark input or output unavailable; no report written.', file=sys.stderr)
        return 2
    print(json.dumps(report, allow_nan=False, indent=2))
    return 0 if report['summary']['processedCount'] == args.repeats else 2


if __name__ == '__main__': sys.exit(main())
