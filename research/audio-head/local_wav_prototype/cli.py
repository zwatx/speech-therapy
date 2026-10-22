"""Single local WAV research preview. No server, training, downloads or retries."""
import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from bindings import configuration, guard, model_bindings, source_bindings
from common import (HEAD, HERE, ROOT, PHONES, MAX_WAV, Refused, canonical, cleanup, digest,
                    interruption_flag, parse, read, require, save, sha, supervise,
                    allowed_input, failure_details, validate_age, validate_prompt, validate_wav)

OUTPUTS = HEAD / "outputs/local-wav-prototype"
PHRASE_OUTPUTS = HEAD / "outputs/local-phrase-prototype"
LIMITS = {"wordSeconds": 60, "sharedSeconds": 120, "overallSeconds": 190, "childExitGraceSeconds": 5}
CLAIM_LIMITS = {name: False for name in ("requestedWordVerified", "producedPhoneLabelsAvailable",
               "pronunciationCorrectnessValidated", "learnerFeedbackEligible", "clinicalUseEligible",
               "productionUseEligible", "independentAccuracyEstablished")}


def prompt_choice(config, ident):
    rows = parse(read(ROOT / config["catalog"], 100000))
    require(digest(ROOT / config["catalog"]) == config["sources"][config["catalog"]], "catalog_changed")
    require(type(rows) is list and len(rows) == 15 and len({r["id"] for r in rows}) == 15, "catalog_shape")
    matching = [row["prompt"] for row in rows if row["id"] == ident]
    require(len(matching) == 1, "unknown_prompt_choice")
    return matching[0]


def make_evidence(result, metrics, audio_sha, lifecycle, policy, manifest_sha):
    require(type(result) is dict and set(result) == {"speechEvidence", "recognition", "status", "reason",
            "audioSha256", "workerElapsedSeconds"} and result["audioSha256"] == audio_sha, "word_result_binding")
    require(lifecycle["cleanupConfirmed"] and lifecycle["workerExitCode"] == 0
            and not lifecycle["timedOut"] and not lifecycle["cancelled"], "word_worker_failed")
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    if sys.platform == "darwin":
        peak /= 1024  # macOS reports bytes; the policy field is KiB.
    evidence = {"schemaVersion": 1, "status": result["status"], "reason": result["reason"],
                "capture": {"audioSha256": audio_sha, "valid": True, "metrics": metrics},
                "speechEvidence": result["speechEvidence"], "recognition": result["recognition"],
                "binding": {"audioSha256": audio_sha, "modelManifestSha256": manifest_sha,
                            "policySha256": policy.POLICY_SHA},
                "runtime": {"elapsedSeconds": lifecycle["elapsedSeconds"], "peakRssKiB": peak,
                            "workerExitCode": lifecycle["workerExitCode"], "timedOut": False, "acousticCalls": 1},
                "claimLimits": dict(policy.CLAIMS)}
    evidence["evidenceSha256"] = policy.digest(evidence)
    return evidence


def run(wav_path, prompt, age, output, *, mode="word"):
    """Called only by the explicit CLI or by generated tests with inert doubles."""
    started = time.monotonic()
    require(mode in ("word", "phrase-v1"), "unsupported_preview_mode")
    validate_age(age)
    if mode == "phrase-v1":
        from phrase_admission import validate_phrase_prompt
        validate_phrase_prompt(prompt)
        require(age is not None, "known_child_age_6_to_12_required")
    else:
        validate_prompt(prompt)
    output_parent = PHRASE_OUTPUTS if mode == "phrase-v1" else OUTPUTS
    wav_path, output = Path(wav_path).absolute(), Path(output).absolute()
    allowed_input(wav_path)
    require(output.parent == output_parent and output == output.resolve()
            and not output.exists() and not output.is_symlink(), "fresh_private_output_required")
    raw = read(wav_path, MAX_WAV)
    metrics = validate_wav(raw)
    config = configuration()
    sources = source_bindings(config)
    input_sha = sha(raw)
    require(not wav_path.is_relative_to(output), "input_output_overlap")
    output_parent.mkdir(mode=0o700, exist_ok=True)
    require(not output_parent.is_symlink() and output_parent == output_parent.resolve(), "unsafe_output_parent")
    output.mkdir(mode=0o700)
    scratch = output / "temporary"
    audio = scratch / "source.wav"
    receipt = {"schemaVersion": 1, "status": "failed", "reason": None, "audioSHA256": input_sha,
               "ageYears": age, "sharedPredictionPerformed": False, "targets": [], "workers": [],
               "cleanupConfirmed": False, "originalAudioUnchanged": False, "sourcesUnchanged": False,
               "recognition": None, "wordAdmission": None, "researchOnly": True, **CLAIM_LIMITS}
    receipt.update(phase="private_setup", failurePhase=None,
                   modelManifestSHA256=config["wordModelManifest"]["sha256"],
                   wordPolicySHA256=config["wordPolicySha256"],
                   rssMeaning="Observed cumulative child-process peak for this CLI process, not a per-worker RSS measurement")
    if mode == "phrase-v1":
        receipt.update(mode=mode, phraseAdmission=None, requestedPhraseVerified=False,
                       workerLaunchStates={"word": "not_attempted", "shared": "not_attempted"})
    owned_settled = True
    old_umask = os.umask(0o077)
    handlers = ExitStack()
    stopped = handlers.enter_context(interruption_flag())
    # Fixed local interpreter; the expected prompt never enters this child's argv,
    # environment or stdin. Only WAV bytes enter admission.worker.
    env = {**os.environ, "PYTHONPATH": str(ROOT / "research/assessment-admission"),
           "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "HF_HUB_DISABLE_TELEMETRY": "1", "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
           "TMPDIR": str(scratch / "model-tmp")}
    try:
        scratch.mkdir(mode=0o700)
        (scratch / "asr").mkdir(mode=0o700)
        (scratch / "model-tmp").mkdir(mode=0o700)
        with audio.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
        request = {"schemaVersion": 1, "originalAudioSHA256": input_sha,
             "prompt": prompt, "ageYears": age, "context": "known-child-age" if age is not None else "recognition-only-age-unknown-or-adult",
             "sources": sources, "limits": LIMITS, "inputMetrics": metrics, "researchOnly": True, **CLAIM_LIMITS}
        if mode == "phrase-v1":
            request["mode"] = mode
        save(output / "request.json", request)
        guard(sources)
        sys.path.insert(0, str(ROOT / "research/assessment-admission"))
        from admission import policy
        require(policy.POLICY_SHA == config["wordPolicySha256"], "word_policy_changed")
        # The existing fixed waveform gates run before expensive inference.
        if metrics["railSamples"] > policy.POLICY["maximumRailSamples"]:
            receipt.update(status="abstain", reason="clipping")
        elif metrics["rms"] < policy.POLICY["minimumRms"]:
            receipt.update(status="abstain", reason="silence")
        else:
            receipt["phase"] = "word_model_readiness"
            word_models = model_bindings(config, shared=False)
            require(not stopped["requested"], "interrupted")
            with audio.open("rb") as stdin:
                remaining = LIMITS["overallSeconds"] - (time.monotonic() - started)
                require(remaining > 0, "overall_budget_exceeded")
                receipt["phase"] = "word_inference"
                owned_settled = False
                if mode == "phrase-v1":
                    receipt["workerLaunchStates"]["word"] = "attempted_unknown"
                lifecycle = supervise([str(ROOT / config["python"]), "-m", "admission.worker", str(scratch / "asr")],
                                      cwd=ROOT, env=env, stdin=stdin,
                                      timeout=min(LIMITS["wordSeconds"], remaining), stopped=stopped)
            receipt["workers"].append(lifecycle)
            if mode == "phrase-v1":
                receipt["workerLaunchStates"]["word"] = "launch_failed" if lifecycle.get("launchFailed") else "launched"
            owned_settled = lifecycle["cleanupConfirmed"]
            require(owned_settled, "word_cleanup_unconfirmed")
            require(lifecycle["workerExitCode"] == 0 and not lifecycle["timedOut"]
                    and not lifecycle["cancelled"], "word_worker_failed")
            result = parse(read(scratch / "asr/result.json", 100000, private=True))
            evidence = make_evidence(result, metrics, input_sha, lifecycle, policy, config["wordModelManifest"]["sha256"])
            receipt["phase"] = "word_admission"
            if mode == "phrase-v1":
                from phrase_admission import decide
                decision = decide(evidence, prompt, policy)
                receipt["phraseAdmission"] = decision
                receipt["wordAdmission"] = decision["baseWordDecision"]
            else:
                decision = policy.decide(evidence, prompt["transcript"])
                receipt["wordAdmission"] = decision
            guard(word_models)
            # Do not export the raw ASR transcript. Preserve actual numeric
            # evidence and the fixed policy decision; this is not correctness.
            recognition = evidence["recognition"]
            receipt["recognition"] = None if recognition is None else {
                key: value for key, value in recognition.items()
                if key != "transcript" and (mode == "word" or key != "selectedTokenPosteriors")}
            receipt["recognitionEvidenceSHA256"] = evidence["evidenceSha256"]
            receipt["speechEvidence"] = evidence["speechEvidence"]
            receipt.update(status="abstain", reason=decision["reason"])
            if decision["admitted"] and age is None:
                receipt.update(status="recognition_only", reason="known_child_age_required_for_shared_scores")
            elif decision["admitted"]:
                guard(sources)
                require(not stopped["requested"], "interrupted")
                remaining = LIMITS["overallSeconds"] - (time.monotonic() - started)
                require(remaining > 0, "overall_budget_exceeded")
                shared_job = {
                    "schemaVersion": 1, "audio": str(audio), "audioSha256": input_sha,
                    "ageYears": age, "prompt": prompt, "supportedPhones": PHONES, "sources": sources,
                    "wordAdmissionEvidenceSHA256": evidence["evidenceSha256"]}
                if mode == "phrase-v1":
                    shared_job.update(kind=mode, phraseAdmission=decision)
                job = save(scratch / "shared-job.json", shared_job)
                owned_settled = False
                receipt["phase"] = "shared_inference"
                if mode == "phrase-v1":
                    receipt["workerLaunchStates"]["shared"] = "attempted_unknown"
                lifecycle = supervise([str(ROOT / config["python"]), str(HERE / "worker.py"), job["path"], job["sha256"]],
                                      cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                      timeout=min(LIMITS["sharedSeconds"], remaining), stopped=stopped)
                receipt["workers"].append(lifecycle)
                if mode == "phrase-v1":
                    receipt["workerLaunchStates"]["shared"] = "launch_failed" if lifecycle.get("launchFailed") else "launched"
                owned_settled = lifecycle["cleanupConfirmed"]
                require(owned_settled, "shared_cleanup_unconfirmed")
                require(lifecycle["workerExitCode"] == 0 and not lifecycle["timedOut"]
                        and not lifecycle["cancelled"], "shared_worker_failed")
                shared = parse(read(output / "shared-result.json", 2_000_000, private=True))
                require(shared["audioSha256"] == input_sha and shared["jobSha256"] == job["sha256"]
                        and [t["id"] for t in shared["targets"]] == [t["id"] for t in prompt["targets"]], "shared_result_binding")
                if mode == "phrase-v1":
                    keys = ("id", "wordIndex", "phoneIndex", "targetPhone")
                    require(shared["mode"] == mode
                            and shared["phraseAdmissionEvidenceSHA256"] == evidence["evidenceSha256"]
                            and [[target[key] for key in keys] for target in shared["targets"]]
                            == [[target[key] for key in keys] for target in prompt["targets"]],
                            "phrase_shared_result_binding")
                receipt.update(status=shared["status"], reason=None if shared["sharedPredictionPerformed"] else "phone_evidence_missing",
                               targets=shared["targets"], sharedPredictionPerformed=shared["sharedPredictionPerformed"])
                receipt["sharedResultSHA256"] = digest(output / "shared-result.json")
    except BaseException as error:
        receipt.update(status="failed", failurePhase=receipt["phase"],
                       reason=str(error) if isinstance(error, Refused) else "execution_failed")
        try:
            receipt["failureDiagnostic"] = save(output / "failure.json", failure_details(error, receipt["phase"]))
        except OSError:
            receipt["failureDiagnosticUnavailable"] = True
    finally:
        try:
            require(owned_settled, "owned_process_cleanup_unknown")
            receipt["deletedTemporaries"] = cleanup(scratch)
            receipt["cleanupConfirmed"] = True
        except BaseException as error:
            receipt.update(status="cleanup_unknown", reason="owned_temporary_cleanup_unconfirmed")
            receipt["failurePhase"] = receipt["failurePhase"] or "cleanup"
            receipt["cleanupFailure"] = failure_details(error, "cleanup")
        try:
            guard(sources)
            receipt["sourcesUnchanged"] = True
            require(sha(read(wav_path, MAX_WAV)) == input_sha, "original_audio_changed")
            receipt["originalAudioUnchanged"] = True
        except BaseException as error:
            receipt["finalGuardFailure"] = "final_source_or_input_guard_failed"
            receipt["finalGuardDiagnostic"] = failure_details(error, "final_guard")
            if receipt["cleanupConfirmed"]:
                receipt.update(status="failed", reason="final_source_or_input_guard_failed")
            receipt["failurePhase"] = receipt["failurePhase"] or "final_guard"
        receipt["elapsedSeconds"] = time.monotonic() - started
        try:
            save(output / "receipt.json", receipt)
        finally:
            os.umask(old_umask)
            handlers.close()
    return receipt


def preview(receipt):
    status, reason = receipt["status"], receipt["reason"]
    if status == "research_scores":
        return "The recognizer matched the practice word. Research rating estimates were saved privately; they do not judge pronunciation."
    if status == "recognition_only":
        return "The recognizer matched the practice word. No child sound scores were computed because no known age (6–12) was given."
    if status == "cleanup_unknown":
        return "Temporary-file cleanup is unconfirmed. Keep the private output for inspection; do not assume processing stopped."
    if status == "failed":
        return "Processing failed. No usable research result was accepted."
    if reason == "requested_word_not_matched":
        return "The recognizer did not match the expected word. This is not a pronunciation-error finding."
    if reason in ("silence", "speech_not_detected"):
        return "The recording did not pass the speech-evidence rule. No sound scores were computed."
    if reason == "clipping":
        return "The recording clipped. No sound scores were computed."
    if reason == "phone_evidence_missing":
        return "Phone evidence was insufficient for scoring. No sound scores were computed."
    if reason == "single_word_required":
        return "The recognizer could not match a single practice word. No sound scores were computed."
    return "There was insufficient evidence for this attempt. No sound scores were computed."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List existing prompt choices; no model load")
    attempt = commands.add_parser("run", help="Process one explicitly supplied WAV")
    attempt.add_argument("--wav", type=Path, required=True,
                         help="Mono 16 kHz PCM16 WAV, 0.1–4 s, at most 132,096 bytes; use paths without symlinked components")
    prompt = attempt.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt-choice", help="ID in the existing 15-entry candidate catalog")
    prompt.add_argument("--prompt-json", type=Path, help="Existing schema-2 single-word canonical prompt")
    age = attempt.add_mutually_exclusive_group(required=True)
    age.add_argument("--age-years", type=int, help="Actual known completed child age, 6–12")
    age.add_argument("--recognition-only", action="store_true", help="Unknown/adult age; never invoke the child research head")
    attempt.add_argument("--output", type=Path, required=True,
                         help="New directory directly under research/audio-head/outputs/local-wav-prototype/")
    args = parser.parse_args()
    output_created = False
    try:
        config = configuration()
        if args.command == "list":
            path = ROOT / config["catalog"]
            require(digest(path) == config["sources"][config["catalog"]], "catalog_changed")
            rows = parse(read(path, 100000))
            for row in rows:
                phones = [target["targetPhone"] for target in row["prompt"]["targets"]]
                print(canonical({"id": row["id"], "expectedWord": row["prompt"]["transcript"],
                                 "targets": phones, "supported": all(phone in PHONES for phone in phones)}).decode())
            return 0
        if args.prompt_json:
            allowed_input(args.prompt_json)
        expected = prompt_choice(config, args.prompt_choice) if args.prompt_choice else parse(read(args.prompt_json.absolute(), 512000))
        # A receipt-save error after setup must not be labelled a preflight refusal.
        output_existed = args.output.exists()
        try:
            receipt = run(args.wav, expected, args.age_years, args.output)
        finally:
            output_created = not output_existed and args.output.exists()
        print(canonical({"status": receipt["status"], "reason": receipt["reason"],
                         "message": preview(receipt),
                         "failurePhase": receipt["failurePhase"],
                         "scoredOccurrences": sum(t.get("subjectiveCorpusRatingProbabilities") is not None for t in receipt["targets"]),
                         "receipt": str(args.output.absolute() / "receipt.json"),
                         "cleanupConfirmed": receipt["cleanupConfirmed"],
                         "researchOnly": True, "learnerFeedbackEligible": False}).decode())
        return 0 if receipt["status"] in ("abstain", "recognition_only", "research_scores") else 1
    except Refused as error:
        print(canonical({"status": "failed" if output_created else "refused_before_execution",
                         "reason": str(error), "researchOnly": True}).decode())
        return 1 if output_created else 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(canonical({"status": "failed" if output_created else "refused_before_execution",
                         "reason": "receipt_or_execution_failed" if output_created else "input_unreadable_or_invalid",
                         "exceptionType": type(error).__name__,
                         "researchOnly": True}).decode())
        return 1 if output_created else 2


if __name__ == "__main__":
    raise SystemExit(main())
