"""One shared-model extraction, after the parent observes actual word admission."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

from common import HEAD, ROOT, canonical, failure_details, parse, read, require, save, sha, validate_age, validate_prompt
from bindings import configuration, guard, model_bindings, source_bindings


def validate_job_prompt(job, config):
    """Check the explicit mode and phrase receipt before model imports."""
    kind = job.get("kind", "word")
    require(kind in ("word", "phrase-v1"), "unsupported_preview_mode")
    if kind == "phrase-v1":
        from phrase_admission import PHRASE_POLICY_SHA, validate_phrase_prompt
        validate_phrase_prompt(job["prompt"])
        decision = job["phraseAdmission"]
        require(decision["admitted"] is True and decision["reason"] is None
                and decision["phrasePolicySHA256"] == PHRASE_POLICY_SHA
                and decision["baseWordPolicySHA256"] == config["wordPolicySha256"]
                and decision["evidenceSHA256"] == job["wordAdmissionEvidenceSHA256"]
                and decision["baseWordDecision"]["admitted"] is False
                and decision["baseWordDecision"]["reason"] == "single_word_required"
                and decision["baseWordDecision"]["policySha256"] == config["wordPolicySha256"]
                and decision["baseWordDecision"]["evidenceSha256"] == decision["evidenceSHA256"]
                and decision["baseWordDecision"]["expectedWordSha256"] == sha(canonical(job["prompt"]["transcript"]))
                and decision["decisionSHA256"] == sha(canonical({key: value for key, value in decision.items()
                                                                 if key != "decisionSHA256"})),
                "phrase_admission_binding_changed")
    else:
        validate_prompt(job["prompt"])
    return kind


def run(job_path, job_sha, state):
    state["phase"] = "job_binding"
    raw_job = read(job_path, 512000, private=True)
    require(sha(raw_job) == job_sha, "job_changed")
    job = parse(raw_job)
    config = configuration()
    pins = source_bindings(config)
    require(pins == job["sources"], "source_binding_changed")
    pins.update(model_bindings(config, shared=True))
    validate_age(job["ageYears"])
    require(job["ageYears"] is not None, "known_child_age_required")
    kind = validate_job_prompt(job, config)
    audio = Path(job["audio"])
    require(audio == job_path.parent / "source.wav" and sha(read(audio, 132096, private=True)) == job["audioSha256"], "audio_binding_changed")
    pins[str(audio)] = job["audioSha256"]
    pins[str(job_path)] = job_sha
    guard(pins)  # Check all project sources before importing model/extractor code.
    state["phase"] = "model_imports"
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    def deny_network(event, args):
        if event in ("socket.connect", "socket.getaddrinfo"):
            raise RuntimeError("network_forbidden")
    sys.addaudithook(deny_network)
    sys.path.insert(0, str(HEAD))
    import numpy as np
    import torch
    from position_inference import audio as occurrence
    from ages_6_12_bundle import inference as shared
    import multiphone_evidence_gate as gate

    started = time.monotonic()
    state["phase"] = "canonical_prompt"
    torch.set_num_threads(2)
    contract, mapping, recipe, vocabulary, extraction_pins = occurrence.load_contract(
        ROOT / config["occurrenceContract"]["path"], config["occurrenceContract"]["sha256"],
        ROOT / config["phoneticSnapshot"])
    samples = occurrence.read_rating_pcm(audio, job["audioSha256"])
    frames = occurrence.local.convolution_frames(len(samples), mapping)
    canonical = occurrence.validate_prompt(job["prompt"], mapping, vocabulary, shared.PHONES, frames)
    require(tuple(shared.PHONES) == tuple(job["supportedPhones"]), "phone_inventory_changed")
    extraction_pins["audio"] = {"path": str(audio), "sha256": job["audioSha256"]}
    # This CTC job contains no expected text, phones, targets or prompt path.
    ctc_job = {"schemaVersion": 1, "researchOnly": True, "audioPath": str(audio),
               "audioSha256": job["audioSha256"], "sampleCount": len(samples), "expectedFrames": frames,
               "bindings": extraction_pins, "ctcCheckpoint": contract["ctcCheckpoint"],
               "sessionOptions": contract["ctcSessionOptions"]}
    ctc_pin = save(job_path.parent / "ctc-job.json", ctc_job)
    state["phase"] = "prompt_blind_ctc"
    subprocess.run([config["node"], str(HEAD / "multiphone_research_ctc.ts"), ctc_pin["path"], ctc_pin["sha256"]],
                   check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ctc = parse(read(job_path.parent / "ctc.json", 100000, private=True))
    require(ctc["complete"] is True and ctc["fetchAttempts"] == 0 and ctc["audioSha256"] == job["audioSha256"]
            and ctc["jobSha256"] == ctc_pin["sha256"] and ctc["frames"] == frames
            and ctc["sampleCount"] == len(samples) and ctc["posteriorsPath"] == "ctc.f32"
            and ctc["checkpoint"] == contract["ctcCheckpoint"] and ctc["sessionOptions"] == contract["ctcSessionOptions"], "ctc_binding_changed")
    payload = read(job_path.parent / "ctc.f32", 3_000_000, private=True)
    state["phase"] = "phone_evidence"
    require(hashlib.sha256(payload).hexdigest() == ctc["posteriorsSha256"], "ctc_bytes_changed")
    logp = np.frombuffer(payload, dtype="<f4").reshape(-1, 392)
    evidence = gate.assess(samples.numpy(), logp)
    # Observation is computed without the expected prompt. Alignment below is
    # explicitly canonical/forced; do not relabel it produced-phone recognition.
    observed = occurrence.local.greedy_tokens(logp)
    output = {"schemaVersion": 1, "audioSha256": job["audioSha256"], "jobSha256": job_sha,
              "status": "abstain", "phoneEvidence": evidence,
              "promptBlindCTCTokenIds": observed, "expectedMappedTokenIds": canonical["mappedTokenIds"],
              "ctcExactlyMatchesExpected": observed == canonical["mappedTokenIds"],
              "ctcMatchControlsAdmission": False, "targets": [dict(t, subjectiveCorpusRatingProbabilities=None)
                                                              for t in job["prompt"]["targets"]],
              "sharedPredictionPerformed": False, "featureSHA256": None,
              "modelManifestSHA256": config["sharedManifest"]["sha256"], "ctcRuntime": ctc,
              "producedPhoneLabelsAvailable": False, "learnerFeedbackEligible": False,
              "clinicalUseEligible": False, "productionUseEligible": False}
    if kind == "phrase-v1":
        output.update(mode=kind, phraseAdmissionEvidenceSHA256=job["wordAdmissionEvidenceSHA256"],
                      promptBlindCTCTokenCount=len(observed), expectedMappedTokenCount=len(canonical["mappedTokenIds"]))
        del output["promptBlindCTCTokenIds"], output["expectedMappedTokenIds"]
    if evidence["ratingAvailable"]:
        state["phase"] = "phonetic_features"
        encoder = occurrence.phonetic.PhoneticEncoder(ROOT / config["phoneticSnapshot"], recipe)
        hidden = encoder(samples)
        values, rows, diagnostics = occurrence.make_features(canonical, logp, hidden, mapping)
        predictor = shared.load_bundle((ROOT / config["sharedManifest"]["path"]).parent,
                                       config["sharedManifest"]["sha256"])
        state["phase"] = "shared_prediction"
        ids = np.asarray([row["modelTargetId"] for row in rows], dtype=np.int64)
        probabilities = predictor.predict(values, ids, age_years=job["ageYears"])["probabilities"]
        features = job_path.parent.parent / "features.npy"
        with features.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            np.save(stream, values, allow_pickle=False)
        from common import digest
        output.update(status="research_scores", sharedPredictionPerformed=True, featureSHA256=digest(features),
                      targets=[{key: row[key] for key in ("id", "targetPhone", "wordIndex", "phoneIndex", "modelTargetId", "diagnosticFlags")}
                               | {"subjectiveCorpusRatingProbabilities": probability.tolist()}
                               for row, probability in zip(rows, probabilities, strict=True)],
                      canonicalPathDiagnostics=diagnostics)
    state["phase"] = "final_bindings"
    guard(pins)
    occurrence.guard(extraction_pins)
    output["elapsedSeconds"] = time.monotonic() - started
    output["runtime"] = {"torch": str(torch.__version__), "numpy": np.__version__, "threads": 2, "device": "cpu"}
    save(job_path.parent.parent / "shared-result.json", output)


def main():
    # The parent supplies this owned job path. Diagnostics survive scratch cleanup.
    job_path = Path(sys.argv[1])
    state = {"phase": "worker_setup"}
    try:
        run(job_path, sys.argv[2], state)
        return 0
    except BaseException as error:
        try:
            save(job_path.parent.parent / "worker-error.json", failure_details(error, state["phase"]))
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    # Parent owns exclusive output, timeout, signals and removal of audio/CTC.
    raise SystemExit(main())
