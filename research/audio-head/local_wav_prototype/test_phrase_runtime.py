"""Generated-only phrase routing tests; no model, service or media execution.

The invented ASR and shared-worker responses exercise protocol boundaries, not
recognition accuracy or rating quality. The admission policy itself is real.
"""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c
import cli
import phrase_cli
import worker
from phrase_admission import decide as phrase_decide

sys.path.insert(0, str(c.ROOT / "research/assessment-admission"))
from admission import policy
from admission.models import MODEL_MANIFEST_SHA


def generated_pcm():
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, 2, 16000, 4096, "NONE", "not compressed"))
        stream.writeframes((200).to_bytes(2, "little", signed=True) * 4096)
    return output.getvalue()


def phrase_prompt():
    return {"schemaVersion": 2, "language": "en", "transcript": "bob bib",
            "words": [{"text": "bob", "phones": ["B", "AA1", "B"]},
                      {"text": "bib", "phones": ["B", "IH1", "B"]}],
            "targets": [{"id": "second-final", "wordIndex": 1, "phoneIndex": 2, "targetPhone": "B"},
                        {"id": "first-initial", "wordIndex": 0, "phoneIndex": 0, "targetPhone": "B"},
                        {"id": "second-initial", "wordIndex": 1, "phoneIndex": 0, "targetPhone": "B"}]}


def invented_asr_response(audio_sha, *, transcript="Bob bib.", token_log_probability=-0.2):
    """A well-formed, invented protocol response, independent of prompt input."""
    return {"speechEvidence": {"method": "silero-vad", "passed": True,
                              "positiveSamples": 4096, "maximumConsecutivePositiveSamples": 4096,
                              "windowCount": 8, "probabilities": [0.9] * 8,
                              "speechPresenceVerified": False},
            "recognition": {"method": "whisper-base.en", "transcript": transcript,
                            "meanTokenLogProbability": token_log_probability,
                            "noSpeechProbability": 0.1, "complete": True, "endTokenId": 50256,
                            "generatedTokenCount": 3,
                            "selectedTokenPosteriors": [
                                {"tokenId": 701, "selectedLogProbability": token_log_probability},
                                {"tokenId": 702, "selectedLogProbability": token_log_probability}],
                            "requestedWordVerified": False},
            "status": "recognized", "reason": None,
            "audioSha256": audio_sha, "workerElapsedSeconds": 0.01}


def settled_lifecycle():
    return {"cleanupConfirmed": True, "workerExitCode": 0, "timedOut": False,
            "cancelled": False, "elapsedSeconds": 0.01, "childExitCollected": True}


class PhraseRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="phrase-generated-only-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.output_parent = self.base / "phrase-outputs"
        self.output_parent.mkdir(mode=0o700)
        self.output = self.output_parent / "attempt"
        self.wav = self.base / "generated.wav"
        self.original = generated_pcm()
        self.wav.write_bytes(self.original)
        self.audio_sha = c.sha(self.original)
        self.config = {"python": "generated-inert-python",
                       "wordPolicySha256": policy.POLICY_SHA,
                       "wordModelManifest": {"sha256": MODEL_MANIFEST_SHA}}
        self.response = invented_asr_response(self.audio_sha)
        self.calls = []
        self.jobs = []
        self.shared_mutation = None
        saved_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved_path))
        for patch in (mock.patch.object(cli, "PHRASE_OUTPUTS", self.output_parent),
                      mock.patch.object(cli, "configuration", return_value=self.config),
                      mock.patch.object(phrase_cli, "configuration", return_value=self.config),
                      mock.patch.object(cli, "source_bindings", return_value={}),
                      mock.patch.object(cli, "guard"),
                      mock.patch.object(cli, "model_bindings", return_value={})):
            patch.start()
            self.addCleanup(patch.stop)

    def fake_supervise(self, argv, **kwargs):
        """Explicit inert doubles; never start either worker or model code."""
        self.calls.append(list(argv))
        if "admission.worker" in argv:
            self.assertEqual(kwargs["stdin"].read(), self.original)
            # The worker receives only WAV bytes, not the expected phrase,
            # canonical phones, target IDs or an expected-prompt file path.
            exported = json.dumps({"argv": argv, "env": kwargs["env"]})
            for private in ("bob bib", "second-final", "first-initial", "AA1", "IH1"):
                self.assertNotIn(private, exported)
            self.assertEqual(argv[1:3], ["-m", "admission.worker"])
            c.save(Path(argv[-1]) / "result.json", copy.deepcopy(self.response))
        else:
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(Path(argv[1]), c.HERE / "worker.py")
            job_path = Path(argv[-2])
            self.assertEqual(c.digest(job_path), argv[-1])
            job = c.parse(c.read(job_path, 512000, private=True))
            self.jobs.append(job)
            self.assertEqual(job["kind"], "phrase-v1")
            self.assertEqual(job["ageYears"], 6)
            self.assertEqual(job["prompt"], phrase_prompt())
            self.assertEqual(tuple(job["supportedPhones"]), c.PHONES)
            self.assertEqual(job["audioSha256"], self.audio_sha)
            self.assertEqual(c.read(Path(job["audio"]), c.MAX_WAV, private=True), self.original)
            decision = job["phraseAdmission"]
            self.assertTrue(decision["admitted"])
            self.assertIsNone(decision["reason"])
            self.assertFalse(decision["baseWordDecision"]["admitted"])
            self.assertEqual(decision["baseWordDecision"]["reason"], "single_word_required")
            self.assertEqual(decision["baseWordPolicySHA256"], policy.POLICY_SHA)
            self.assertEqual(decision["evidenceSHA256"], job["wordAdmissionEvidenceSHA256"])
            shared = {
                "audioSha256": self.audio_sha, "jobSha256": argv[-1],
                "mode": "phrase-v1", "phraseAdmissionEvidenceSHA256": job["wordAdmissionEvidenceSHA256"],
                "status": "research_scores", "sharedPredictionPerformed": True,
                "targets": [dict(target, subjectiveCorpusRatingProbabilities=[0.1, 0.2, 0.7])
                            for target in job["prompt"]["targets"]]}
            if self.shared_mutation is not None:
                self.shared_mutation(shared)
            c.save(self.output / "shared-result.json", shared)
        return settled_lifecycle()

    def attempt(self, *, supervisor=None):
        with mock.patch.object(cli, "supervise", side_effect=supervisor or self.fake_supervise):
            result = cli.run(self.wav, phrase_prompt(), 6, self.output, mode="phrase-v1")
        self.assertEqual(self.wav.read_bytes(), self.original)
        return result

    def assert_private_receipt(self, result):
        exported = json.dumps(result)
        for private in (self.response["recognition"]["transcript"], "selectedTokenPosteriors", "tokenId",
                        "promptBlindCTCTokenIds", "expectedMappedTokenIds"):
            self.assertNotIn(private, exported)
        for claim in ("requestedPhraseVerified", "requestedWordVerified", "producedPhoneLabelsAvailable",
                      "pronunciationCorrectnessValidated", "learnerFeedbackEligible",
                      "clinicalUseEligible", "productionUseEligible", "independentAccuracyEstablished"):
            self.assertIs(result[claim], False)
        self.assertEqual(c.parse(c.read(self.output / "receipt.json", 2_000_000, private=True)), result)

    def test_exact_phrase_routes_asr_once_then_existing_shared_worker_in_target_order(self):
        result = self.attempt()
        self.assertEqual(result["status"], "research_scores")
        self.assertEqual(len(self.calls), 2)
        self.assertIn("admission.worker", self.calls[0])
        self.assertEqual(Path(self.calls[1][1]), c.HERE / "worker.py")
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual([target["id"] for target in result["targets"]],
                         ["second-final", "first-initial", "second-initial"])
        self.assertEqual([(target["wordIndex"], target["phoneIndex"]) for target in result["targets"]],
                         [(1, 2), (0, 0), (1, 0)])
        self.assertEqual(result["wordAdmission"], result["phraseAdmission"]["baseWordDecision"])
        self.assertTrue(result["cleanupConfirmed"])
        self.assertFalse((self.output / "temporary").exists())
        self.assert_private_receipt(result)

    def test_phrase_mismatch_withholds_shared(self):
        self.response = invented_asr_response(self.audio_sha, transcript="private invented mismatch")
        result = self.attempt()
        self.assertEqual(result["status"], "abstain")
        self.assertFalse(result["phraseAdmission"]["admitted"])
        self.assertIsNotNone(result["reason"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.jobs, [])
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assert_private_receipt(result)

    def assert_shared_binding_failure(self):
        result = self.attempt()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "phrase_shared_result_binding")
        self.assertEqual(result["targets"], [])
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assertTrue(result["cleanupConfirmed"])
        self.assertFalse((self.output / "temporary").exists())
        self.assert_private_receipt(result)

    def test_same_id_wrong_occurrence_withholds_accepted_scores(self):
        # A genuine target ID alone must not let a rating move to another word.
        self.shared_mutation = lambda shared: shared["targets"][0].update(wordIndex=0)
        self.assert_shared_binding_failure()

    def test_wrong_phrase_evidence_binding_withholds_accepted_scores(self):
        self.shared_mutation = lambda shared: shared.update(phraseAdmissionEvidenceSHA256="f" * 64)
        self.assert_shared_binding_failure()

    def test_wrong_shared_mode_withholds_accepted_scores(self):
        self.shared_mutation = lambda shared: shared.update(mode="word")
        self.assert_shared_binding_failure()

    def test_low_token_confidence_withholds_shared(self):
        self.response = invented_asr_response(self.audio_sha, token_log_probability=-1.0)
        result = self.attempt()
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["reason"], "recognition_uncertain")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.jobs, [])
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assert_private_receipt(result)

    def test_unknown_bool_and_out_of_range_ages_refuse_before_output(self):
        for age in (None, True, False, 5, 13):
            with self.subTest(age=age), mock.patch.object(cli, "supervise") as launch:
                with self.assertRaisesRegex(c.Refused, "known_child_age_6_to_12_required"):
                    cli.run(self.wav, phrase_prompt(), age, self.output, mode="phrase-v1")
                launch.assert_not_called()
                self.assertFalse(self.output.exists())
                self.assertEqual(self.wav.read_bytes(), self.original)

    def test_unconfirmed_asr_cleanup_retains_borrow_and_blocks_successor(self):
        unknown = {"cleanupConfirmed": False, "workerExitCode": None,
                   "pid": 424242, "launchFailed": False, "childExitCollected": False,
                   "timedOut": False, "cancelled": False,
                   "reason": "child_exit_unconfirmed", "elapsedSeconds": 0.01}
        with mock.patch.object(cli, "supervise", return_value=unknown) as launch:
            result = cli.run(self.wav, phrase_prompt(), 6, self.output, mode="phrase-v1")
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(result["status"], "cleanup_unknown")
        self.assertFalse(result["cleanupConfirmed"])
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assertEqual(result["workerLaunchStates"]["shared"], "not_attempted")
        self.assertEqual(c.read(self.output / "temporary/source.wav", c.MAX_WAV, private=True), self.original)
        self.assertEqual(self.wav.read_bytes(), self.original)

    def test_supervisor_exception_keeps_attempt_unknown_and_retains_borrow(self):
        with mock.patch.object(cli, "supervise", side_effect=OSError("private generated launch uncertainty")) as launch:
            result = cli.run(self.wav, phrase_prompt(), 6, self.output, mode="phrase-v1")
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(result["status"], "cleanup_unknown")
        self.assertEqual(result["workerLaunchStates"], {"word": "attempted_unknown", "shared": "not_attempted"})
        self.assertFalse(result["cleanupConfirmed"])
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assertEqual(c.read(self.output / "temporary/source.wav", c.MAX_WAV, private=True), self.original)
        self.assertEqual(self.wav.read_bytes(), self.original)
        self.assertNotIn("private generated launch uncertainty", json.dumps(result))

    def test_shared_supervisor_exception_retains_borrow_and_marks_shared_unknown(self):
        def uncertain_shared(argv, **kwargs):
            if "admission.worker" in argv:
                return self.fake_supervise(argv, **kwargs)
            self.calls.append(list(argv))
            raise OSError("private generated shared launch uncertainty")
        result = self.attempt(supervisor=uncertain_shared)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result["status"], "cleanup_unknown")
        self.assertEqual(result["workerLaunchStates"], {"word": "launched", "shared": "attempted_unknown"})
        self.assertFalse(result["cleanupConfirmed"])
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assertEqual(c.read(self.output / "temporary/source.wav", c.MAX_WAV, private=True), self.original)
        self.assertTrue((self.output / "temporary/shared-job.json").exists())
        self.assertNotIn("private generated shared launch uncertainty", json.dumps(result))

    def test_cancellation_after_asr_never_launches_shared(self):
        def cancel_after_response(argv, **kwargs):
            lifecycle = self.fake_supervise(argv, **kwargs)
            kwargs["stopped"]["requested"] = True
            return lifecycle
        result = self.attempt(supervisor=cancel_after_response)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "interrupted")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result["workerLaunchStates"]["shared"], "not_attempted")
        self.assertFalse(result["sharedPredictionPerformed"])
        self.assertTrue(result["cleanupConfirmed"])
        self.assertFalse((self.output / "temporary").exists())

    def main_arguments(self):
        prompt_path = self.base / "prompt.json"
        c.save(prompt_path, phrase_prompt())
        return ["phrase_cli.py", "--wav", str(self.wav), "--prompt-json", str(prompt_path),
                "--age-years", "6", "--output", str(self.output)]

    def test_phrase_terminal_exports_no_private_text_or_token_ids(self):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", self.main_arguments()), \
                mock.patch.object(cli, "supervise", side_effect=self.fake_supervise), redirect_stdout(stdout):
            exit_code = phrase_cli.main()
        terminal = c.parse(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(terminal["status"], "research_scores")
        self.assertEqual(terminal["scoredOccurrences"], 3)
        for private in ("Bob bib.", "bob bib", "selectedTokenPosteriors", "tokenId"):
            self.assertNotIn(private, stdout.getvalue())

    def test_phrase_receipt_write_failure_is_failed_exit_one_after_output_creation(self):
        original_save = cli.save
        def fail_receipt(path, value):
            if path.name == "receipt.json":
                raise OSError("private generated receipt-write failure")
            return original_save(path, value)
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", self.main_arguments()), \
                mock.patch.object(cli, "save", side_effect=fail_receipt), \
                mock.patch.object(cli, "supervise", side_effect=self.fake_supervise), redirect_stdout(stdout):
            exit_code = phrase_cli.main()
        terminal = c.parse(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(terminal["reason"], "receipt_or_execution_failed")
        self.assertTrue(self.output.exists())
        self.assertFalse((self.output / "temporary").exists())
        self.assertNotIn("private generated receipt-write failure", stdout.getvalue())


class PhraseJobPromptTests(unittest.TestCase):
    """Exercise only the real pre-model helper with sealed invented evidence."""
    def setUp(self):
        raw = generated_pcm()
        self.prompt = phrase_prompt()
        evidence = cli.make_evidence(invented_asr_response(c.sha(raw)), c.validate_wav(raw),
                                     c.sha(raw), settled_lifecycle(), policy, MODEL_MANIFEST_SHA)
        self.decision = phrase_decide(evidence, self.prompt, policy)
        self.job = {"kind": "phrase-v1", "prompt": self.prompt,
                    "phraseAdmission": self.decision,
                    "wordAdmissionEvidenceSHA256": evidence["evidenceSha256"]}
        self.config = {"wordPolicySha256": policy.POLICY_SHA}

    def reseal_decision(self):
        self.decision["decisionSHA256"] = c.sha(c.canonical({
            key: value for key, value in self.decision.items() if key != "decisionSHA256"}))

    def assert_binding_refused(self):
        with self.assertRaisesRegex(c.Refused, "phrase_admission_binding_changed"):
            worker.validate_job_prompt(self.job, self.config)

    def test_real_policy_phrase_decision_validates_before_models(self):
        self.assertTrue(self.decision["admitted"])
        self.assertFalse(self.decision["baseWordDecision"]["admitted"])
        self.assertEqual(self.decision["baseWordDecision"]["reason"], "single_word_required")
        self.assertEqual(worker.validate_job_prompt(self.job, self.config), "phrase-v1")
        self.assertFalse(any(name in sys.modules for name in ("torch", "numpy", "transformers")))

    def test_changed_decision_sha_is_refused(self):
        self.decision["decisionSHA256"] = "f" * 64
        self.assert_binding_refused()

    def test_wrong_expected_phrase_hash_is_refused_even_when_resealed(self):
        self.decision["baseWordDecision"]["expectedWordSha256"] = policy.digest("invented other phrase")
        self.reseal_decision()
        self.assert_binding_refused()

    def test_changed_evidence_sha_is_refused_even_when_resealed(self):
        self.decision["evidenceSHA256"] = "f" * 64
        self.decision["baseWordDecision"]["evidenceSha256"] = "f" * 64
        self.reseal_decision()
        self.assert_binding_refused()

    def test_admitted_base_word_decision_is_refused_even_when_resealed(self):
        self.decision["baseWordDecision"].update(admitted=True, reason=None)
        self.reseal_decision()
        self.assert_binding_refused()

    def test_unknown_job_kind_is_refused(self):
        self.job["kind"] = "phrase-v2"
        with self.assertRaisesRegex(c.Refused, "unsupported_preview_mode"):
            worker.validate_job_prompt(self.job, self.config)


if __name__ == "__main__":
    unittest.main(verbosity=2)
