# Declared adult word practice — 2026-10-07

The new local word practice app is available at **http://127.0.0.1:8791/**. Both free practice and guided word checking offer **Adult (18+)** alongside **Child, age6–12**. Adult practice no longer requires a child age. Record, example playback, replay, the bread listening cue, mirror, explicit checking, guided first round, practice and fresh recheck retain their existing behavior. The person and checking choices begin unset/off; microphone and camera start only through their explicit controls.

“Who is practicing?” is a self-declared context, not age verification, consent or evidence of accuracy. The app says whole-word recognition is experimental and accuracy has not been established for adults or children. Ages13–17 are not supported by this version. Recognition outcomes remain whole-word observations with explicit uncertainty/failure states; target assessment, pronunciation correctness, diagnosis and clinical eligibility remain unestablished.

## Contract and isolation

Only `/api/feedback` uses the new closed schema2 request:

```json
{"schemaVersion":2,"attemptId":"<fresh-v4-uuid>","practiceContext":{"kind":"adult"},"prompt":"<existing exact canonical prompt object>","audioBase64":"<bounded generated or owned WAV>"}
```

The other supported context is exactly `{"kind":"child","ageYears":6}` through12. Adult contains no numeric age or child fallback. Missing, malformed, unknown or extra context fields fail before processing. Legacy `/api/assessment`, shared mobile admission, the child research head, recognition models and recognition thresholds remain unchanged. The feedback worker calls age-free prompt-blind recognition followed by the existing decision policy; no child research head is invoked by this feedback path.

The policy is `consumer-recording-feedback-v2`, with request/context semantics in its canonical digest. Public declaration/response closed field shapes remain schema1, and all eleven claim flags remain false. Actual request bytes bind the context through requestSha256; the private worker envelope now independently repeats that hash, and the parent rejects cross-context substitution. Guided fingerprints bind the full frozen context; every capture/take stores its own copy. Changes cancel and clear both tries, checks and guided state. Recheck retains the original context; late permissions and replies cannot return discarded results. CSRF-only refresh retains valid metadata while source drift clears it.

The successor is isolated in `research/assessment-consumer-word-context-app`, with the same package name in a clean process. Both the explicit launcher and ordinary module entrypoint use8791 and a distinct runtime. Child PYTHONPATH starts with the successor; exact module import identity is checked. Existing word8782, sound8788 and sound-practice8789 sources/ports and current native clients remain compatible with their historical versions. The copied closed visual inventory is byte-identical; no model or asset was acquired or run.

Current binding:

- feedback source: `a769aabd08412c35dd6f3fbcf306d74c27dea9febb39417c926786f891cf88a4`
- wrapper source: `efa00f73fffd4a58a73a5ece64602214951be679d8cc04644f9e8ed66dec1df8`
- feedback policy: `c21530e7c85575a1ac425036cc182707f63b76da4a07b74b1c32e6dea4fc1407`
- reviewed40-row source digest: `003a4f0f39c1d4227c17f2fdb87474522ed65ab3b19bc11544356b990558199b`

## Actual verification

**77 focused checks passed:**50 Python backend tests under pinned Python3.13 with warnings as errors,14 current-source generated UI/context checks, and13 bread/playback checks. JavaScript syntax and launcher check-only validation succeeded. The backend tests cover closed decoding, unchanged legacy child refusal, HTTP boundaries, exact worker/module identity, private request hash mismatch, evidence/claim rejection and cleanup behavior.

Two additional actual HTTP posts used2400 zero PCM16 samples through the live successor and its real isolated feedback workers: adult context and child9 context. Both returned the expected silence observation with exact source/audio/request bindings and all claims false. Pre-acoustic validation prevents acoustic model inference for this generated silence; this conclusion follows from the verified source and validated response, not an independently monitored global model counter. Temporary attempt directories and cleanup intents were removed, and the declaration reported processing available afterward. No owner runtime inspection occurred after delivery.

An isolated, visibly labelled browser helper denied real microphone/camera access and injected generated tones plus invented feedback. Actual browser controls produced three recordings; all three tracks stopped and all three audio contexts closed, with zero fixture errors and zero speech-model calls. It received two exact adult requests without top-level ageYears and one child9 request. A delayed adult request was stopped; context switched to child9, both clips disappeared, and the released late result stayed discarded. Guided adult setup, incomplete13-word summary (one skipped/twelve not reached), fresh recheck and end/clear were exercised without automatic recording or posts.

At375px width, the selector measured16px text and44px height, its checkbox label44.5px, and the product had no measured horizontal overflow. The initial966px document width came only from the test-only JSON output; wrapping that fixture display yielded375px document width. Initial screenshots and their exact Opus5.5 review remain intact. A test-only assumption that a hidden selector updated before its view rendered was corrected; the initial13-pass/one-failure evidence is retained. One CUA checkbox locator mismatch was resolved by reading the fresh DOM and using the actual mode button.

GPT-6 Astra found no source blockers. Exact Opus5.5 implemented the controls/copy and reviewed three actual screenshots with no blocking usability finding. Its review identifies scaling, unshown child/recheck/keyboard states and absent real Safari/sensor/acoustic evidence. This is scoped integration verification, not a release, clinical or whole-product approval. Root's subsequent375px DOM measurement verifies fixture wrapping separately from that pixel review.

The generated helper stopped, its tab closed and temporary viewport reset. A fresh real app tab remains open with checking/camera/recording off. Public static HTML/JS responses for all four live apps matched their source byte-for-byte. No old owner tabs, recordings, reserved data, physical devices, models or frozen historical writers were used.

[Full follow-up verification](../../work/consumer-feedback-20261007/adult-word-context/FOLLOWUP_VERIFICATION.json), [frozen source](../../work/consumer-feedback-20261007/adult-word-context/FROZEN_INPUTS.json), [independent review](../../work/consumer-feedback-20261007/adult-word-context/review/ASTRA_FINAL_REVIEW.md), and [actual silence checks](../../work/consumer-feedback-20261007/adult-word-context/ACTUAL_SUCCESSOR_SILENCE.json) preserve exact identities and observed limits. Launch with `research/audio-head/.venv/bin/python scripts/consumer-word-context-app.py --port 8791 --runtime <fresh-owned-runtime>`; `--check` verifies source/catalog setup without starting a runtime, listener or acoustic model.

The overall goal remains active. The next useful product step is to bring truthful adult word checking and the separate sound practice into one coherent flow while retaining exact request/source ownership and the current limits. Native schema2 integration and independent real-speaker sound accuracy remain unfinished; no human reference labels, diagnoses, consent or outcomes were fabricated.
