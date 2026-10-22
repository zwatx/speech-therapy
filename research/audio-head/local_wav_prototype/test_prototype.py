"""Generated PCM, process and routing tests. Never import or run model code."""
import ast
import copy
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
from types import SimpleNamespace
import unittest
from unittest import mock
import wave

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c
import cli
import worker


def pcm(*, count=1600, channels=1, rate=16000, width=2, value=0):
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setparams((channels, width, rate, count, "NONE", "not compressed"))
        stream.writeframes(int(value).to_bytes(width, "little", signed=True) * count * channels)
    return out.getvalue()


def prompt():
    return {"schemaVersion": 2, "language": "en", "transcript": "bob",
            "words": [{"text": "bob", "phones": ["B", "AA1", "B"]}],
            "targets": [{"id": "last-b", "wordIndex": 0, "phoneIndex": 2, "targetPhone": "B"},
                        {"id": "first-b", "wordIndex": 0, "phoneIndex": 0, "targetPhone": "B"}]}


class InputTests(unittest.TestCase):
    def test_repeated_occurrences_preserve_identity_and_order(self):
        value = prompt()
        self.assertIs(c.validate_prompt(value), value)
        self.assertEqual([t["id"] for t in value["targets"]], ["last-b", "first-b"])
        self.assertEqual(len(c.PHONES), 23)
        self.assertNotIn("ZH", c.PHONES)
        self.assertFalse(set(c.PHONES) & c.VOWELS)

    def test_malformed_unsupported_and_multitoken_inputs_refused(self):
        for change in (
            lambda p: p["targets"][0].update(targetPhone="ZH"),
            lambda p: p["targets"][0].update(targetPhone="AA1"),
            lambda p: p["targets"][0].update(id="first-b"),
            lambda p: p["targets"][0].update(phoneIndex=0),
            lambda p: p["targets"][0].update(phoneIndex=True),
            lambda p: p["words"].append({"text": "bob", "phones": ["B"]}),
            lambda p: p.update(transcript="different"),
        ):
            value = prompt()
            change(value)
            with self.assertRaises(c.Refused):
                c.validate_prompt(value)
        for age in (True, 5, 13, 6.5, "6"):
            with self.assertRaises(c.Refused):
                c.validate_age(age)
        for age in (None, 6, 12):
            c.validate_age(age)

    def test_pcm_format_and_duration_without_conversion(self):
        self.assertEqual(c.validate_wav(pcm())["sampleCount"], 1600)
        for raw in (b"not a wav", pcm(channels=2), pcm(rate=8000), pcm(width=1),
                    pcm(count=1599), pcm(count=64001), pcm()[:-2]):
            with self.assertRaises(c.Refused):
                c.validate_wav(raw)

    def test_json_duplicate_and_nonfinite_refused(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e900}', b'broken'):
            with self.assertRaises(c.Refused):
                c.parse(raw)

    def test_reserved_input_paths_refused_without_opening_them(self):
        for root in c.FORBIDDEN_INPUT_ROOTS:
            with self.assertRaisesRegex(c.Refused, "reserved_input_refused"):
                c.allowed_input(root / "generated-never-opened.wav")

    def test_actual_extractor_helper_chain_is_present_without_importing_models(self):
        def tree(relative):
            return ast.parse((c.HEAD / relative).read_text())
        occurrence = tree("position_inference/audio.py")
        self.assertTrue(any(isinstance(node, ast.ImportFrom) and node.module == "multiphone_research_audio"
                            and any(alias.name == "local" for alias in node.names) for node in occurrence.body))
        raw = tree("multiphone_research_audio.py")
        self.assertTrue(any(isinstance(node, ast.Import) and any(alias.name == "multiphone_local_features"
                            and alias.asname == "local" for alias in node.names) for node in raw.body))
        local = tree("multiphone_local_features.py")
        helper = next(node for node in local.body if isinstance(node, ast.FunctionDef) and node.name == "greedy_tokens")
        self.assertEqual([arg.arg for arg in helper.args.args], ["log_prob"])
        self.assertFalse(any(name in sys.modules for name in ("torch", "numpy", "transformers")))


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="wav-prototype-generated-")
        self.base = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)


class TemporaryTests(Sandbox):
    def test_missing_executable_never_launches_and_allows_cleanup(self):
        result = c.supervise([str(self.base / "missing-executable")], cwd=self.base,
                             env=os.environ.copy(), stdin=subprocess.DEVNULL,
                             timeout=1, stopped={"requested": False})
        self.assertTrue(result["cleanupConfirmed"])
        self.assertTrue(result["launchFailed"])
        self.assertFalse(result["childExitCollected"])
        self.assertIsNone(result["pid"])
        self.assertEqual(result["launchError"]["exceptionType"], "FileNotFoundError")

    def test_diagnostics_exclude_recognition_messages_source_lines_and_locals(self):
        private_text = "generated private recognition text"
        try:
            raise KeyError(private_text)
        except KeyError as error:
            details = c.failure_details(error, "generated_phase")
        self.assertEqual(details["exceptionType"], "KeyError")
        self.assertEqual(details["phase"], "generated_phase")
        self.assertTrue(details["frames"])
        self.assertNotIn(private_text, json.dumps(details))
        self.assertNotIn("raise KeyError", json.dumps(details))

    def test_actual_shared_worker_job_failure_preserves_private_diagnostic(self):
        scratch = self.base / "temporary"
        scratch.mkdir(mode=0o700)
        job = c.save(scratch / "shared-job.json", {"generated": True})
        result = self.helper_with_argv([sys.executable, "-B", str(c.HERE / "worker.py"),
                                       job["path"], "0" * 64])
        self.assertEqual(result["workerExitCode"], 1)
        self.assertTrue(result["cleanupConfirmed"])
        error_file = self.base / "worker-error.json"
        details = c.parse(c.read(error_file, 100000, private=True))
        self.assertEqual(details["phase"], "job_binding")
        self.assertEqual(details["exceptionType"], "Refused")
        self.assertEqual(details["reason"], "job_changed")
        c.cleanup(scratch)
        self.assertTrue(error_file.exists())

    def helper_with_argv(self, argv):
        return c.supervise(argv, cwd=self.base, env=os.environ.copy(),
                           stdin=subprocess.DEVNULL, timeout=2, stopped={"requested": False})

    def test_cleanup_only_owned_tree_preserves_original_and_numeric_results(self):
        original = self.base / "original.wav"
        original.write_bytes(pcm())
        original_sha = c.digest(original)
        scratch = self.base / "temporary"
        scratch.mkdir(mode=0o700)
        (scratch / "source.wav").write_bytes(pcm())
        (scratch / "ctc.f32").write_bytes(b"generated numeric intermediate")
        (self.base / "features.npy").write_bytes(b"generated retained feature fixture")
        c.save(self.base / "provenance.json", {"generated": True})
        inventory = c.cleanup(scratch)
        self.assertEqual({r["path"] for r in inventory}, {"source.wav", "ctc.f32"})
        self.assertTrue(all(r["removed"] for r in inventory))
        self.assertFalse(scratch.exists())
        self.assertEqual(c.digest(original), original_sha)
        self.assertTrue((self.base / "features.npy").exists())
        self.assertTrue((self.base / "provenance.json").exists())

    def test_cleanup_refuses_links_before_any_deletion(self):
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                scratch = self.base / kind
                scratch.mkdir(mode=0o700)
                outside = self.base / (kind + ".txt")
                outside.write_bytes(b"outside fixture")
                (scratch / "source.wav").write_bytes(pcm())
                if kind == "symlink":
                    (scratch / "linked").symlink_to(outside)
                else:
                    os.link(outside, scratch / "linked")
                with self.assertRaises(c.Refused):
                    c.cleanup(scratch)
                self.assertTrue(outside.exists())
                self.assertTrue((scratch / "source.wav").exists())

    def helper(self, code, timeout=1, stopped=None):
        return c.supervise([sys.executable, "-c", code], cwd=self.base, env=os.environ.copy(),
                           stdin=subprocess.DEVNULL, timeout=timeout, stopped=stopped or {"requested": False})

    def test_actual_helper_success_and_timeout_collected(self):
        success = self.helper("pass")
        self.assertEqual(success["workerExitCode"], 0)
        self.assertTrue(success["cleanupConfirmed"])
        self.assertTrue(success["childExitCollected"])
        timeout = self.helper("import time; time.sleep(20)", timeout=0.05)
        self.assertTrue(timeout["timedOut"])
        self.assertTrue(timeout["cleanupConfirmed"])
        self.assertEqual(timeout["workerExitCode"], -signal.SIGKILL)

    def test_actual_interrupt_collected_before_return(self):
        with c.interruption_flag() as stopped:
            timer = threading.Timer(0.05, lambda: os.kill(os.getpid(), signal.SIGINT))
            timer.start()
            try:
                result = self.helper("import time; time.sleep(20)", stopped=stopped)
            finally:
                timer.join()
        self.assertTrue(result["cancelled"])
        self.assertTrue(result["cleanupConfirmed"])
        self.assertEqual(result["workerExitCode"], -signal.SIGKILL)

    def test_eperm_after_collected_exit_is_never_absence(self):
        original = os.killpg
        def deny_probe(pid, signum):
            if signum == 0:
                raise PermissionError("generated permission failure")
            return original(pid, signum)
        with mock.patch.object(c.os, "killpg", side_effect=deny_probe):
            result = self.helper("pass")
        self.assertFalse(result["cleanupConfirmed"])
        self.assertEqual(result["reason"], "group_absence_unconfirmed")
        self.assertTrue(result["childExitCollected"])

    def test_collected_leader_with_live_descendant_is_unknown_without_signalling_group(self):
        marker = self.base / "generated-descendant.json"
        code = """
import json, os, time
reader, writer = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(reader)
    os.write(writer, b'R')
    os.close(writer)
    time.sleep(20)
    os._exit(0)
os.close(writer)
assert os.read(reader, 1) == b'R'
os.close(reader)
with open(MARKER, 'x') as output:
    json.dump({'pid': pid, 'group': os.getpid()}, output)
os._exit(23)
""".replace("MARKER", repr(str(marker)))
        original_killpg = os.killpg
        signals = []
        def observe(group, signum):
            signals.append(signum)
            return original_killpg(group, signum)
        try:
            with mock.patch.object(c.os, "killpg", side_effect=observe):
                result = self.helper(code)
            self.assertEqual(result["workerExitCode"], 23)
            self.assertFalse(result["cleanupConfirmed"])
            self.assertTrue(result["childExitCollected"])
            self.assertNotIn(signal.SIGKILL, signals)
        finally:
            # Only this test knows the independently recorded descendant PID.
            if marker.exists():
                descendant = json.loads(marker.read_text())
                try:
                    self.assertEqual(os.getpgid(descendant["pid"]), descendant["group"])
                    os.kill(descendant["pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 3
                while True:
                    try:
                        os.getpgid(descendant["pid"])
                    except ProcessLookupError:
                        break
                    self.assertLess(time.monotonic(), deadline, "generated descendant remains")
                    time.sleep(0.01)


class RoutingTests(Sandbox):
    def test_actual_launch_failure_removes_temporary_audio(self):
        self.config["python"] = str(self.base / "missing-executable")
        result = cli.run(self.wav, prompt(), 6, self.output)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cleanupConfirmed"])
        self.assertTrue(result["workers"][0]["launchFailed"])
        self.assertFalse((self.output / "temporary").exists())
        self.assertEqual(self.wav.read_bytes(), self.original)
        self.assertEqual(c.parse(c.read(self.output / "failure.json", 100000))["phase"], "word_inference")

    def test_budget_failure_before_launch_cleans_audio(self):
        with mock.patch.dict(cli.LIMITS, {"overallSeconds": 0}):
            result = cli.run(self.wav, prompt(), 6, self.output)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "overall_budget_exceeded")
        self.assertTrue(result["cleanupConfirmed"])
        self.assertEqual(result["workers"], [])
        self.assertFalse((self.output / "temporary").exists())

    def test_shared_launch_failure_cleans_audio_after_admitted_word(self):
        original_supervise = cli.supervise
        def launch(argv, **kwargs):
            if "admission.worker" in argv:
                return self.fake_supervise(argv, **kwargs)
            return original_supervise([str(self.base / "missing-shared-worker")], **kwargs)
        with mock.patch.object(cli, "supervise", side_effect=launch):
            result = cli.run(self.wav, prompt(), 6, self.output)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cleanupConfirmed"])
        self.assertEqual(len(result["workers"]), 2)
        self.assertTrue(result["workers"][1]["launchFailed"])
        self.assertFalse((self.output / "temporary").exists())

    def test_receipt_write_failure_is_not_reported_as_preflight_refusal(self):
        original_save = cli.save
        def fail_receipt(path, value):
            if path.name == "receipt.json":
                raise OSError("generated private receipt-write failure")
            return original_save(path, value)
        arguments = ["cli.py", "run", "--wav", str(self.wav), "--prompt-json", str(self.base / "prompt.json"),
                     "--age-years", "6", "--output", str(self.output)]
        c.save(self.base / "prompt.json", prompt())
        stdout = io.StringIO()
        from contextlib import redirect_stdout
        with mock.patch.object(sys, "argv", arguments), mock.patch.object(cli, "save", side_effect=fail_receipt), \
                mock.patch.object(cli, "supervise", side_effect=self.fake_supervise), redirect_stdout(stdout):
            exit_code = cli.main()
        terminal = c.parse(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(terminal["reason"], "receipt_or_execution_failed")
        self.assertNotIn("generated private receipt-write failure", stdout.getvalue())
        self.assertFalse((self.output / "temporary").exists())

    def setUp(self):
        super().setUp()
        self.output_parent = self.base / "outputs"
        self.output_parent.mkdir(mode=0o700)
        self.wav = self.base / "generated.wav"
        self.wav.write_bytes(pcm(value=200))
        self.output = self.output_parent / "one-attempt"
        self.original = self.wav.read_bytes()
        self.config = {"python": "generated-python", "wordPolicySha256": "generated-policy",
                       "wordModelManifest": {"sha256": "0" * 64}}
        self.decision = {"admitted": True, "reason": None, "requestedWordVerified": False}
        self.policy = SimpleNamespace(POLICY_SHA="generated-policy", CLAIMS={},
                                      POLICY={"maximumRailSamples": 0, "minimumRms": 0.001},
                                      digest=lambda x: c.sha(c.canonical(x)),
                                      decide=lambda evidence, expected: dict(self.decision))
        patches = (mock.patch.object(cli, "OUTPUTS", self.output_parent),
                   mock.patch.object(cli, "configuration", return_value=self.config),
                   mock.patch.object(cli, "source_bindings", return_value={}),
                   mock.patch.object(cli, "guard"), mock.patch.object(cli, "model_bindings", return_value={}),
                   mock.patch.dict(sys.modules, {"admission": SimpleNamespace(policy=self.policy)}))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        saved_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved_path))
        self.calls = []

    def fake_supervise(self, argv, **kwargs):
        self.calls.append(argv)
        if "admission.worker" in argv:
            self.assertEqual(kwargs["stdin"].read(), self.original)
            self.assertNotIn("bob", json.dumps(argv))
            c.save(Path(argv[-1]) / "result.json", {
                "speechEvidence": {"generated": True}, "recognition": {"transcript": "generated private text"},
                "status": "recognized", "reason": None, "audioSha256": c.sha(self.original), "workerElapsedSeconds": 0.01})
        else:
            job = c.parse(c.read(Path(argv[-2]), 512000))
            self.assertEqual(job["ageYears"], 6)
            self.assertEqual([t["id"] for t in job["prompt"]["targets"]], ["last-b", "first-b"])
            c.save(self.output / "shared-result.json", {
                "audioSha256": c.sha(self.original), "jobSha256": argv[-1], "status": "research_scores",
                "targets": [dict(t, subjectiveCorpusRatingProbabilities=[0.1, 0.2, 0.7]) for t in job["prompt"]["targets"]],
                "sharedPredictionPerformed": True})
        return {"cleanupConfirmed": True, "workerExitCode": 0, "timedOut": False,
                "cancelled": False, "elapsedSeconds": 0.01, "childExitCollected": True}

    def attempt(self, age):
        with mock.patch.object(cli, "supervise", side_effect=self.fake_supervise):
            result = cli.run(self.wav, prompt(), age, self.output)
        self.assertEqual(self.wav.read_bytes(), self.original)
        self.assertFalse((self.output / "temporary").exists())
        self.assertTrue(result["cleanupConfirmed"])
        self.assertNotIn("generated private text", json.dumps(result))
        return result

    def test_unknown_age_is_recognition_only_without_shared_worker(self):
        result = self.attempt(None)
        self.assertEqual(result["status"], "recognition_only")
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(result["sharedPredictionPerformed"])

    def test_mismatch_withholds_shared_even_for_known_child(self):
        self.decision = {"admitted": False, "reason": "requested_word_not_matched"}
        result = self.attempt(6)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(result["sharedPredictionPerformed"])

    def test_known_age_routes_exact_occurrences_only_after_admission(self):
        result = self.attempt(6)
        self.assertEqual(result["status"], "research_scores")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([t["id"] for t in result["targets"]], ["last-b", "first-b"])
        self.assertFalse(result["pronunciationCorrectnessValidated"])

    def test_setup_write_failure_cleans_copied_audio_and_preserves_failure(self):
        original_save = cli.save
        def fail_request(path, value):
            if path.name == "request.json":
                raise OSError("generated write failure")
            return original_save(path, value)
        with mock.patch.object(cli, "save", side_effect=fail_request):
            result = self.attempt(6)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.calls, [])
        self.assertTrue((self.output / "receipt.json").exists())

    def test_unconfirmed_child_keeps_borrow_and_blocks_successor(self):
        with mock.patch.object(cli, "supervise", return_value={"cleanupConfirmed": False}) as launch:
            result = cli.run(self.wav, prompt(), 6, self.output)
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(result["status"], "cleanup_unknown")
        self.assertFalse(result["cleanupConfirmed"])
        self.assertTrue((self.output / "temporary/source.wav").exists())
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assertEqual(self.wav.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
