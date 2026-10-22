"""Generated audio/contracts only; no real phrase CLI, models, corpus or sensors.

The generated helper is an explicit CLI/inner-worker receipt double. Its actual
Popen lifecycle tests outer ownership; invented inner facts test validation, not
model execution. HTTP tests bind their own ephemeral loopback socket only.
"""
import base64
import copy
import http.client
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid
import wave

from phrase_app import service as s
from phrase_app.server import Server


PROMPT = {"schemaVersion": 2, "language": "en", "transcript": "my ball",
          "words": [{"text": "my", "phones": ["M", "AY1"]}, {"text": "ball", "phones": ["B", "AO1", "L"]}],
          "targets": [{"id": "ball-final", "wordIndex": 1, "phoneIndex": 2, "targetPhone": "L"}]}
CONFIG = {"python": "unused", "wordPolicySha256": "a" * 64,
          "wordModelManifest": {"sha256": "b" * 64}, "sharedManifest": {"sha256": "c" * 64}}


def wav(*, rate=16000, channels=1, frames=3200, sample=800):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(sample.to_bytes(2, "little", signed=True) * frames * channels)
    return stream.getvalue()


def request(**changes):
    value = {"requestId": str(uuid.uuid4()), "promptId": "one", "ageYears": 7,
             "consent": True, "audioBase64": base64.b64encode(wav()).decode()}
    value.update(changes)
    return value


class GeneratedGuard:
    """Explicit source double for generated outer-process/HTTP tests."""
    def __init__(self, app, root):
        self.app, self.root = app, root
        self.config, self.sources, self.seal = CONFIG, {}, "d" * 64
        self.changed = False

    def check(self):
        if self.changed:
            raise s.SafeError("source_changed", 503)


HELPER = r'''
import hashlib, json, os, pathlib, signal, subprocess, sys, time
def canonical(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def save(path, value):
    with path.open("xb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(canonical(value) + b"\n")
data = json.loads(pathlib.Path(sys.argv[1]).read_bytes())
output = pathlib.Path(data["output"])
directory = pathlib.Path(data["directory"])
mode = data["scenario"]
cancelled = False
def stop(*_):
    global cancelled
    if mode != "ignore_term": cancelled = True
signal.signal(signal.SIGTERM, stop)
save(directory / "ready.json", {})
if mode == "missing_receipt": sys.exit(1)
if mode == "group_alive":
    subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(0.8)"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.exit(1)
deadline = time.monotonic() + data.get("wait", 0)
while time.monotonic() < deadline and not cancelled: time.sleep(0.01)
output.parent.mkdir(mode=0o700, exist_ok=True)
output.mkdir(mode=0o700)
save(output / "request.json", data["request"])
receipt = data["receipt"]
if cancelled:
    receipt.update(status="failed", reason="interrupted", targets=[], sharedPredictionPerformed=False)
    receipt["workerLaunchStates"] = {"word":"not_attempted", "shared":"not_attempted"}
    receipt["workers"] = []
if mode == "wrong_receipt": receipt["audioSHA256"] = "e" * 64
if mode == "unconfirmed": receipt.update(cleanupConfirmed=False, status="cleanup_unknown")
if mode == "unknown_worker": receipt["workerLaunchStates"]["word"] = "attempted_unknown"
if "shared" in data and not cancelled:
    shared = data["shared"]
    save(output / "shared-result.json", shared)
    receipt["sharedResultSHA256"] = sha((output / "shared-result.json").read_bytes())
    with (output / "features.npy").open("xb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(b"invented features, never a model array")
save(output / "receipt.json", receipt)
sys.exit(0 if receipt["status"] != "failed" else 1)
'''


def fixture(job, scenario, *, wait=0):
    """Invented inner receipt; only the helper outer process is real."""
    expected_request = {"schemaVersion": 1, "mode": "phrase-v1", "originalAudioSHA256": job.audio_sha,
        "prompt": job.prompt, "ageYears": job.age, "context": "known-child-age", "sources": job.sources,
        "inputMetrics": job.metrics, "researchOnly": True, "learnerFeedbackEligible": False, "clinicalUseEligible": False}
    receipt = {"schemaVersion": 1, "mode": "phrase-v1", "status": "abstain", "reason": "silence",
        "audioSHA256": job.audio_sha, "ageYears": job.age, "sourcesUnchanged": True,
        "originalAudioUnchanged": True, "researchOnly": True, "learnerFeedbackEligible": False,
        "clinicalUseEligible": False, "requestedPhraseVerified": False, "cleanupConfirmed": True,
        "wordPolicySHA256": CONFIG["wordPolicySha256"], "modelManifestSHA256": CONFIG["wordModelManifest"]["sha256"],
        "workerLaunchStates": {"word": "not_attempted", "shared": "not_attempted"}, "workers": [],
        "phraseAdmission": None, "wordAdmission": None, "sharedPredictionPerformed": False, "targets": [], "elapsedSeconds": 0.125}
    value = {"directory": str(job.directory), "output": str(job.output), "scenario": scenario,
             "wait": wait, "request": expected_request, "receipt": receipt}
    worker = {"pid": 121, "childExitCollected": True, "workerExitCode": 0, "timedOut": False,
              "cancelled": False, "cleanupConfirmed": True}
    if scenario in ("mismatch", "uncertain", "phone_missing", "bad_target", "unknown_worker", "bad_job", "raw_leak"):
        base = {"admitted": False, "reason": "single_word_required", "expectedWordSha256": s.sha(s.canonical(job.prompt["transcript"])),
                "policySha256": CONFIG["wordPolicySha256"], "evidenceSha256": "f" * 64}
        admitted = scenario != "mismatch"
        decision = {"admitted": admitted, "reason": None if admitted else "requested_phrase_not_matched",
            "baseWordPolicySHA256": CONFIG["wordPolicySha256"], "method": "independent-asr-exact-phrase",
            "baseWordDecision": base, "evidenceSHA256": "f" * 64, "requestedPhraseVerified": False,
            "recognitionRejectionIsArticulationError": False}
        decision["decisionSHA256"] = s.sha(s.canonical(decision))
        receipt.update(phraseAdmission=decision, wordAdmission=base, recognitionEvidenceSHA256="f" * 64,
            workerLaunchStates={"word": "launched", "shared": "not_attempted"}, workers=[dict(worker)],
            reason="requested_phrase_not_matched" if not admitted else None,
            recognition={"transcript": "DO NOT EXPOSE PRIVATE RECOGNIZED SPEECH", "selectedTokenPosteriors": [0.456]})
        if admitted:
            performed = scenario != "phone_missing"
            targets = [dict(t, subjectiveCorpusRatingProbabilities=[.1, .2, .7] if performed else None,
                            diagnosticFlags=["unverified-forced-canonical-location", "fewer-than-two-target-state-frames"])
                       for t in job.prompt["targets"]]
            if scenario == "bad_target": targets[0]["wordIndex"] = 0
            shared_job = {"schemaVersion": 1, "audio": str(job.output / "temporary/source.wav"),
                "audioSha256": job.audio_sha, "ageYears": job.age, "prompt": job.prompt, "sources": job.sources,
                "supportedPhones": list(s.PHONES), "wordAdmissionEvidenceSHA256": "f" * 64,
                "kind": "phrase-v1", "phraseAdmission": decision}
            shared = {"audioSha256": job.audio_sha, "jobSha256": s.sha(s.canonical(shared_job) + b"\n"),
                "mode": "phrase-v1", "phraseAdmissionEvidenceSHA256": "f" * 64,
                "status": "research_scores" if performed else "abstain", "sharedPredictionPerformed": performed,
                "targets": targets, "featureSHA256": s.sha(b"invented features, never a model array"),
                "modelManifestSHA256": CONFIG["sharedManifest"]["sha256"], "promptBlindCTCTokenIds": [88, 55]}
            if scenario == "bad_job": shared["jobSha256"] = "0" * 64
            value["shared"] = shared
            receipt.update(status=shared["status"], sharedPredictionPerformed=performed, targets=targets,
                workerLaunchStates={"word": "launched", "shared": "launched"}, workers=[dict(worker), dict(worker)],
                reason=None if performed else "phone_evidence_missing")
    return value


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="generated-phrase-app-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.app = self.root / "app"
        self.app.mkdir()
        rows = [{"id": name, "prompt": copy.deepcopy(PROMPT), "focus": "Generated focus", "cue": "Generated cue"}
                for name in ("one", "two", "three", "four")]
        s.save(self.app / "catalog.json", {"schemaVersion": 1, "prompts": rows})
        (self.app / "ui").mkdir()
        for name in ("index.html", "app.css", "app.js"):
            (self.app / "ui" / name).write_text("generated asset")
        self.helper = self.root / "generated-helper.py"
        self.helper.write_text(HELPER)
        self.guard = GeneratedGuard(self.app, self.root)
        self.scenario, self.wait = "silence", 0
        self.service = s.Service(self.root / "runtime", guard=self.guard, output_parent=self.root / "outputs", command_builder=self.command)
        self.addCleanup(self.service.stop)

    def command(self, job):
        s.save(job.directory / "generated-helper-input.json", fixture(job, self.scenario, wait=self.wait))
        return [sys.executable, "-B", str(self.helper), str(job.directory / "generated-helper-input.json")]

    def settled(self, job_id, timeout=3):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            result = self.service.get(job_id)
            if result["status"] in s.TERMINAL:
                return result
            time.sleep(.01)
        self.fail("generated helper did not settle")

    def ready(self, job_id):
        until = time.monotonic() + 3
        job = self.service.jobs[job_id]
        while time.monotonic() < until:
            if (job.directory / "ready.json").exists():
                return job
            time.sleep(.01)
        self.fail("generated helper did not become ready")

    def test_age_consent_and_format_refuse_before_launch(self):
        cases = [{"ageYears": age} for age in (None, True, False, 5, 13, 7.0, "7")]
        cases += [{"consent": False}, {"consent": 1}, {"audioBase64": "a%=="}, {"audioBase64": ""},
                  {"audioBase64": base64.b64encode(wav(rate=8000)).decode()},
                  {"audioBase64": base64.b64encode(wav(channels=2)).decode()},
                  {"audioBase64": base64.b64encode(wav(frames=1599)).decode()},
                  {"audioBase64": base64.b64encode(wav(frames=64001)).decode()}]
        with mock.patch.object(s.subprocess, "Popen") as launch:
            for changes in cases:
                with self.subTest(changes=list(changes)), self.assertRaises(s.SafeError):
                    self.service.submit(request(**changes))
            extra = request()
            extra["transcript"] = "never accepted"
            with self.assertRaises(s.SafeError): self.service.submit(extra)
            launch.assert_not_called()
        self.assertEqual(list(self.service.runtime.iterdir()), [])

    def test_strict_parser_rejects_duplicates_and_nonfinite(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[] trailing'):
            with self.subTest(raw=raw), self.assertRaises(s.SafeError): s.parse(raw)

    def test_busy_duplicate_and_lost202_address(self):
        self.wait = .3
        original = request()
        accepted = self.service.submit(original)
        self.assertEqual(accepted["jobId"], original["requestId"])
        for retry, tag in ((original, "capture_reused"), (request(), "busy")):
            with self.assertRaises(s.SafeError) as raised: self.service.submit(retry)
            self.assertEqual(raised.exception.tag, tag)
        result = self.settled(accepted["jobId"])
        self.assertEqual(result["result"]["kind"], "silence")
        with self.assertRaises(s.SafeError) as raised: self.service.submit(original)
        self.assertEqual(raised.exception.tag, "capture_reused")

    def test_projections_hide_private_outputs(self):
        for scenario, kind in (("silence", "silence"), ("mismatch", "phrase_mismatch"),
                               ("uncertain", "uncertain"), ("phone_missing", "phone_evidence_missing")):
            with self.subTest(scenario=scenario):
                self.scenario = scenario
                accepted = self.service.submit(request())
                result = self.settled(accepted["jobId"])
                self.assertEqual(result["status"], "complete")
                self.assertTrue(result["cleanupConfirmed"])
                value = result["result"]
                self.assertEqual(value["kind"], kind)
                self.assertFalse(value["soundAnalysisAvailable"])
                self.assertFalse(value["learnerFeedbackEligible"])
                self.assertFalse(value["clinicalUseEligible"])
                self.assertEqual(value["scoredOccurrences"], 1 if scenario == "uncertain" else 0)
                self.assertEqual(value["alignmentUnverified"], scenario == "uncertain")
                text = json.dumps(result)
                for forbidden in ("DO NOT EXPOSE", "0.456", "subjectiveCorpus", "TokenIds", "features.npy", "my ball", "ball-final", str(self.root)):
                    self.assertNotIn(forbidden, text)
                job = self.service.jobs[accepted["jobId"]]
                self.assertFalse(job.directory.exists())
                self.assertFalse(job.output.exists())
                audit = (self.service.runtime / (job.id + ".json")).read_text()
                self.assertNotIn("ageYears", audit)
                self.assertNotIn("my ball", audit)

    def test_bad_shared_job_and_target_suppress_result_with_confirmed_cleanup(self):
        for scenario in ("bad_job", "bad_target"):
            self.scenario = scenario
            result = self.settled(self.service.submit(request())["jobId"])
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["cleanupConfirmed"])
            self.assertEqual(result["result"]["kind"], "failed")

    def test_actual_missing_executable_cleans_unborrowed_input(self):
        self.service.command_builder = lambda job: [str(self.root / "missing-executable")]
        accepted = self.service.submit(request())
        result = self.settled(accepted["jobId"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cleanupConfirmed"])
        self.assertFalse(self.service.blocked)
        self.assertFalse(self.service.jobs[accepted["jobId"]].directory.exists())

    def test_unknown_receipts_retain_borrow_and_latch(self):
        # Each scenario gets a fresh Service since the unknown latch never resets.
        for index, scenario in enumerate(("missing_receipt", "wrong_receipt", "unconfirmed", "unknown_worker")):
            with self.subTest(scenario=scenario):
                service = s.Service(self.root / ("runtime-unknown-" + str(index)), guard=self.guard,
                    output_parent=self.root / "outputs", command_builder=self.command)
                self.addCleanup(service.stop)
                self.scenario = scenario
                accepted = service.submit(request())
                job = service.jobs[accepted["jobId"]]
                job.thread.join(timeout=3)
                result = service.get(job.id)
                self.assertEqual(result["status"], "cleanup_unknown")
                self.assertFalse(result["cleanupConfirmed"])
                self.assertTrue((job.directory / "source.wav").exists())
                self.assertTrue((job.directory / "prompt.json").exists())
                if scenario != "missing_receipt": self.assertTrue(job.output.exists())
                with self.assertRaises(s.SafeError) as raised: service.submit(request())
                self.assertEqual(raised.exception.tag, "blocked")

    def test_actual_group_survives_collected_leader_retains(self):
        self.scenario = "group_alive"
        result = self.settled(self.service.submit(request())["jobId"])
        self.assertEqual(result["status"], "cleanup_unknown")
        job = self.service.jobs[result["jobId"]]
        self.assertTrue(job.outer_collected)
        self.assertFalse(job.outer_absent)
        self.assertTrue(job.directory.exists())
        time.sleep(.9)  # Generated child exits itself; never kill a collected group.
        self.assertTrue(self.service.blocked)

    def test_cancel_real_waitable_parent_and_late_cancel(self):
        self.wait = 2
        accepted = self.service.submit(request())
        job = self.ready(accepted["jobId"])
        actual_kill, signals = os.kill, []
        def checked_kill(pid, sig):
            self.assertFalse(job.outer_collected)
            self.assertIsNone(job.process.returncode)
            self.assertEqual(pid, job.process.pid)
            self.assertEqual(sig, signal.SIGTERM)
            self.assertTrue(self.service.lock._is_owned())
            signals.append(pid)
            return actual_kill(pid, sig)
        with mock.patch.object(s.os, "kill", side_effect=checked_kill):
            self.assertEqual(self.service.cancel(job.id)["status"], "cancelling")
            result = self.settled(job.id)
            self.assertEqual(result["status"], "cancelled")
            self.assertTrue(result["cleanupConfirmed"])
            self.assertIsNone(result["result"])
            self.assertEqual(self.service.cancel(job.id)["status"], "cancelled")
        self.assertEqual(len(signals), 1)
        self.assertTrue(job.outer_collected and job.outer_absent)
        self.assertFalse(job.directory.exists())

    def test_parent_delay_keeps_owner_and_unknown_never_auto_resets(self):
        self.scenario, self.wait = "ignore_term", .4
        self.service.cancel_grace = .04
        accepted = self.service.submit(request())
        job = self.ready(accepted["jobId"])
        self.service.cancel(job.id)
        result = self.settled(job.id)
        self.assertEqual(result["status"], "cleanup_unknown")
        self.assertTrue(job.thread.is_alive())
        self.assertTrue(job.directory.exists())
        job.thread.join(timeout=2)
        self.assertTrue(job.outer_collected)
        self.assertEqual(self.service.get(job.id)["status"], "cleanup_unknown")
        self.assertTrue(job.directory.exists())
        self.assertTrue(job.output.exists())

    def test_source_changed_before_launch_and_public_result(self):
        self.guard.changed = True
        with mock.patch.object(s.subprocess, "Popen") as launch:
            with self.assertRaises(s.SafeError): self.service.submit(request())
            launch.assert_not_called()
        with self.assertRaises(s.SafeError): self.service.catalog()
        self.guard.changed = False
        accepted = self.service.submit(request())
        self.settled(accepted["jobId"])
        self.guard.changed = True
        with self.assertRaises(s.SafeError) as raised: self.service.get(accepted["jobId"])
        self.assertEqual(raised.exception.status, 503)

    def test_fresh_runtime_and_safe_cleanup(self):
        with self.assertRaises(s.SafeError):
            s.Service(self.service.runtime, guard=self.guard, output_parent=self.root / "outputs")
        linked = self.root / "linked"
        linked.symlink_to(self.service.runtime, target_is_directory=True)
        with self.assertRaises(s.SafeError):
            s.Service(linked, guard=self.guard, output_parent=self.root / "outputs")
        scratch = self.root / "unsafe-tree"
        scratch.mkdir()
        (scratch / "borrowed-link").symlink_to(self.helper)
        with self.assertRaises(s.SafeError): s.cleanup_owned(scratch)
        self.assertTrue(self.helper.exists())

    def http(self, server, method, path, *, body=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            client.request(method, path, body=body, headers=headers or {})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_actual_http_host_origin_csrf_size_and_valid_check(self):
        server = Server(("127.0.0.1", 0), self.service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        status, catalog = self.http(server, "GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(len(catalog["prompts"]), 4)
        base_headers = {"Content-Type": "application/json", "Origin": server.origin, "X-CSRF-Token": catalog["csrfToken"]}
        body = s.canonical(request())
        for changes, tag in (({"Host": "localhost:" + str(server.server_port)}, "invalid_host"),
                             ({"Origin": "https://foreign.example"}, "invalid_origin"),
                             ({"X-CSRF-Token": "wrong"}, "invalid_csrf")):
            headers = {**base_headers, **changes}
            status, value = self.http(server, "POST", "/api/check", body=body, headers=headers)
            self.assertEqual((status, value["error"]), (403, tag))
        status, value = self.http(server, "POST", "/api/check", body=b" " * (s.MAX_JSON + 1), headers=base_headers)
        self.assertEqual((status, value["error"]), (413, "request_too_large"))
        status, accepted = self.http(server, "POST", "/api/check", body=body, headers=base_headers)
        self.assertEqual(status, 202)
        result = self.settled(accepted["jobId"])
        status, public = self.http(server, "GET", "/api/jobs/" + accepted["jobId"])
        self.assertEqual(status, 200)
        self.assertEqual(public, result)
        status, value = self.http(server, "GET", "/api/catalog", headers={"Origin": "https://foreign.example"})
        self.assertEqual((status, value["error"]), (403, "invalid_origin"))
        self.guard.changed = True
        status, value = self.http(server, "GET", "/api/catalog")
        self.assertEqual((status, value["error"]), (503, "source_changed"))


class SourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="generated-source-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.app = self.root / "app"
        self.app.mkdir()
        for name in ("phrase_app/__init__.py", "phrase_app/service.py", "phrase_app/server.py", "catalog.json", "pyproject.toml", "README.md", "ui/app.js"):
            path = self.app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"generated source fixture only")
        proto = self.root / "research/audio-head/local_wav_prototype"
        proto.mkdir(parents=True)
        raw = proto.parent / "raw.json"
        occurrence = proto.parent / "occurrence.json"
        s.save(raw, {"dependencySha256": {}})
        s.save(occurrence, {})
        config = {**CONFIG, "sources": {}, "rawContract": {"path": str(raw.relative_to(self.root)), "sha256": s.digest(raw)},
                  "occurrenceContract": {"path": str(occurrence.relative_to(self.root)), "sha256": s.digest(occurrence)}}
        names = ("__init__.py", "common.py", "bindings.py", "cli.py", "worker.py", "pins.json", "phrase_admission.py", "phrase_cli.py", "README.md", "test_prototype.py", "test_phrase_admission.py", "test_phrase_runtime.py")
        for name in names:
            if name == "pins.json": s.save(proto / name, config)
            else: (proto / name).write_bytes(b"generated prototype fixture only")
        manifest = {"schemaVersion": 4, "files": [{"path": str((proto / name).relative_to(self.root)), "sha256": s.digest(proto / name)} for name in names]}
        s.save(proto / "SOURCE-v4.json", manifest)
        self.proto_manifest_sha = s.digest(proto / "SOURCE-v4.json")
        app_manifest = {"schemaVersion": 1, "prototypeSourceManifestSha256": self.proto_manifest_sha,
                        "files": [{"path": str(path.relative_to(self.app)), "sha256": s.digest(path)} for path in sorted(self.app.rglob("*")) if path.is_file()]}
        s.save(self.app / "source-pins.json", app_manifest)
        self.guard = s.SourceGuard(self.app, self.root, prototype_manifest_sha=self.proto_manifest_sha)

    def test_all_app_and_prototype_changes_and_unlisted_assets_fail_closed(self):
        for path in (self.app / "ui/app.js", self.root / "research/audio-head/local_wav_prototype/test_phrase_runtime.py"):
            original = path.read_bytes()
            path.write_bytes(b"changed generated bytes")
            with self.assertRaises(s.SafeError) as raised: self.guard.check()
            self.assertEqual(raised.exception.status, 503)
            path.write_bytes(original)
            self.guard.check()
        extra = self.app / "ui/extra.js"
        extra.write_bytes(b"unlisted")
        with self.assertRaises(s.SafeError): self.guard.check()
        extra.unlink()
        cache = self.app / "phrase_app/__pycache__"
        cache.mkdir()
        with self.assertRaises(s.SafeError): self.guard.check()
        cache.rmdir()
        self.guard.check()

    def test_manifest_mutation_and_source_symlink_fail_closed(self):
        manifest = self.app / "source-pins.json"
        original = manifest.read_bytes()
        manifest.write_bytes(original + b" ")
        with self.assertRaises(s.SafeError): self.guard.check()
        manifest.write_bytes(original)
        source = self.app / "ui/app.js"
        raw = source.read_bytes()
        source.unlink()
        source.symlink_to(self.app / "README.md")
        with self.assertRaises(s.SafeError): self.guard.check()
        source.unlink()
        source.write_bytes(raw)
        self.guard.check()


if __name__ == "__main__":
    unittest.main()
