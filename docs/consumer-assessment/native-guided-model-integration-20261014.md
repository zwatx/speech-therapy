# Guided same-Mac model integration

October 14, 2026. The Debug iOS simulator guided flow now connects its existing
recording owner to the complete local acoustic model pipeline. This implements
an engineering route. Controlled virtual input has completed the full journey
for T and N. Pronunciation correctness, corrective feedback and improvement
judgments remain disabled. The required validated Sunday demo is
still unsupported by independent evidence.

## Run the prototype

Use the existing local Python environment and pinned cached models, from the
repository root:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m consumer_assessment.service --port 8765
```

Build the learner's Debug simulator app using its existing XcodeGen project.
On the same Mac, open Home → **Review, practice, recheck**. Enable **Run the local
research sound model** and choose the child's genuinely known completed age,
6–12. No age is assumed. Setup remains editable until Start; starting freezes
the five canonical entries and research context. Enabling the option does not
record, check or play anything.

Record, Stop and Check remain explicit. The bundled native recognizer checks
the whole word first. A matched word with confirmed cleanup permits the exact
same stopped take to reach `127.0.0.1:8765`; uncertain, mismatched, unavailable,
unsupported or cancelled checks withhold the research request. The model's own
forced phonetic alignment remains unverified even after a whole-word match.

Choose one to three review words to practice; none is selected from model output.
Complete practice explicitly, then start recheck for fresh takes of the same
five entries. Check during practice is optional. Each research note belongs to
its exact entry, take and operation; the first observation stays frozen when a
later take is checked. Notes say whether processing ran, without displaying
rating probabilities, sound correctness, a score, correction or improvement.
Only completed practice writes existing participation metadata. Age, audio,
transcripts and model results are absent from that history.

This route is compiled only for Debug simulators. The local service cannot be
reached by a physical phone through the simulator's loopback address. Release
retains ordinary on-device word checks and practice.

## Complete pipeline and ownership

`GuidedResearchModelRecognizer` composes the bundled word recognizer with the
existing `ResearchAssessmentClient`. The Mac worker already supplies q8 CTC,
separate 1,024-wide encoder features for target occurrences, 13 CTC scalars,
and the retained ages-6–12 research head. The 1,037-wide input is complete;
this integration does not substitute native CTC logits for encoder features.
There is no new model training, calibration, backend, network destination or
dependency. The [bridge contract](../../research/audio-head/consumer_assessment/README.md)
retains fixed source/model hashes, audio/request/prompt bindings, 23 supported
consonants, and disabled learner/clinical/production eligibility flags.

The composite holds a separate file borrow across both processing stages.
Cancellation revokes results but waits for actual bounded work to return before
releasing the native recording. Navigation, background and Close use the existing
single-owner cleanup path. A wrong word receipt or unconfirmed local cleanup
cannot acknowledge file release. Transport/protocol failures and server outcomes
that cannot establish cleanup pause subsequent research requests across sessions
for the app process lifetime. Toggling the option or reopening the flow does not
clear that pause. Word checks and manual practice remain available when their
own cleanup is confirmed.

## Observed verification

The private task directory is `work/guided-model-integration-20261014/`.
Private speech crops are test-only resources in a task-local Xcode project;
they are absent from the product resource configuration. No participant audio,
transcripts, rating probabilities or source records are reproduced here.

- Debug builds v2 through v7 and the unsigned Release build passed. The first
  test build exposed a missing test-helper actor annotation, which was fixed.
  The first Release invocation rejected a testing-only coverage flag; the
  corrected build passed. Original logs remain preserved.
- All 47 focused generated tests passed, with zero failures or skips: adapter
  14, guided research flow 3, ledger 14, generated host 6 and strict client 10.
  These exercise bindings, supported/unsupported context, cancellation, cleanup
  holds and shared pause, late observations, five-sound review, explicit practice
  and fresh recheck. Word/model doubles in these tests do not prove inference.
- A direct Mac request on a permitted known-age training crop processed one
  target in 7.926 seconds. This proves the full Mac feature/head path on that
  input; it bypassed native word admission.
- Earlier bundled-recognizer tests did **not** complete the full route. The original
  B/R crop cases failed; a diagnostic collection stalled and was terminated,
  with its incomplete result bundle retained. A corrected-duration B case
  returned word-not-matched. Two additional predeclared training crops returned
  word-uncertain for /s/ and word-not-matched for /f/. All correctly withheld the
  sound-model request. No word gate or model threshold was relaxed.
- Real-model boundary tests are reported separately below. They use the same
  fixed /s/ and /f/ crops, genuine declared ages and actual Swift HTTP client,
  model, temporary files and guided lifecycle, while **word recognition and
  capture hardware are doubled**. New take IDs replay the same source waveform;
  they do not represent new independent productions.

Both separately selected boundary tests passed: **2 passed, 0 failed, 0 skipped**
in 49.55 seconds, with six real model calls (review, practice and recheck for
each sound). Service processing times were 7.989, 6.316, 6.240, 6.592, 6.537 and
6.405 seconds. Passing assertions confirmed distinct take/operation identities,
frozen first observations, one practice-history row per case, temporary-file
deletion and unchanged source audio. These facts are supported by the official
`BoundaryRealModelTests.xcresult` summary and the inspected passing assertions;
the modern result reader provided no console log, so printed aggregate records
were not independently extracted. Service scratch was empty after completion,
and the task-owned service stopped cleanly. Do not interpret this boundary success
as a successful native word-admission→model journey.

The additional crops were chosen from already permitted author-training data by
fixed metadata/source-hash rules before inference, without consulting subjective
ratings or held-out outcomes. They are engineering inputs, not independent child
pronunciation validation. All failed attempts remain in the task directory.
The PERCEPT-R failed once-only study and its reserve were not reused.

### October 15 complete-word follow-up

The earlier sparse feature cache contained only selected consonant intervals.
A separate fixed fixture preparation used the existing full author-training CTC
cache to span every canonical phone in each word, including vowels, with the
existing convolution support and fixed 100 ms margins. Exact primary app
pronunciations, genuine ages 6–12 and source/cache hashes were required. Four
candidates were fixed by metadata and SHA-256 order before alignment or recognition:
/b/, /p/, /m/ and /t/. No /d/ candidate met that metadata filter. No failed
candidate was replaced and no admission threshold changed. Selected source
metadata objects include unused rating fields; those ratings were not consulted.
Canonical occupancy still does not establish true word boundaries.

The native run completed with **2 passed, 2 failed, 0 skipped** in 78.57 seconds
(command exit 65). /p/ and /t/ passed the real bundled native recognizer, actual
Swift client and complete Mac model in initial review, selected practice and
fresh recheck: six real model calls. /b/ and /m/ returned word-uncertain and
correctly withheld model requests. Earlier B/R/S/F negatives remain preserved.
Service times were 9.227, 7.389, 6.668, 6.833, 6.773 and 6.538 seconds.

The passing assertions establish fresh take/operation IDs, frozen first results,
participation-only history and owned-file deletion. The repeated takes contain
the same source waveform. **Capture permission/hardware and playback remain
doubled; word recognition and sound-model processing are real in these cases.**
This verifies native admission and model integration on two engineering inputs,
not live microphone capture, recognition accuracy or sound correctness.

Evidence: `work/guided-model-integration-20261015/CompleteWordNativeTests.xcresult`,
`native-tests-summary.json`, `native-test-tree.json`, `service-aggregates.jsonl`
and `source-pins-v2.json`. A separate source-only Astra review found no blockers
in fixture preparation or the four-case tests. The follow-up Debug build passed;
production source is unchanged from the previously reviewed integration.

A separately selected real-request cancellation test passed (**1 passed, 0 failed,
0 skipped**, 14.49 seconds). It used native word admission and the actual local
model. The file could not be removed while the model request was pending; after
the response, the borrow released while the stopped take remained available.
Media, ledger and model observations stayed cancelled. Close then deleted the
recording, with no history entry. The preserved JSON attachment independently
records those completion predicates. Its service call processed in 8.862 seconds.
Evidence is `RealCancellationTests.xcresult` and `cancellation-attachments/` in
the October 15 task directory. Independent source review corrected the test to
distinguish retained recording ownership from an active processing borrow.

The owner subsequently authorized a bounded simulator microphone test using
replay of the existing permitted fixtures. This authorizes no physical-phone,
new-participant or external-upload work.

Both controlled microphone cases failed (**0 passed, 2 failed, 0 skipped**;
command exit 65). They used the actual production capturer and permission path,
with fixture replay through an in-app player. Each recorded one take: 1.237 and
1.301 seconds, both at the recorder's −160 dBFS floor. Saved diagnostics report
permission granted, built-in microphone input, speaker output and confirmed
recording deletion/cleanup. Native word recognition returned uncertain; neither
case made a model request. These negative results do not establish microphone
speech capture or microphone-to-model success.

A subsequent read-only host check found default Mac output muted at 0%, with
input unmuted. Audible fixture replay was therefore unavailable; this does not
establish that output mute was the only capture problem. The owner chose to keep
output muted. No host volume or route was changed and no further replay ran.
A proposed external-player diagnostic was archived without building or running;
the live test source was restored exactly to the microphone-run version.

Evidence: `ControlledMicrophoneTests.xcresult`, `microphone-tests-summary.json`,
`microphone-attachments-all/` and `source-pins-v4.json` in the October 15 task
directory. The Debug microphone-test build passed. Xcode's diagnostic collection
outlasted the tests; its parent ultimately exited 65. An identified task-owned
orphan diagnostic collector was terminated after the final result and attachments
were preserved. No test, model, playback or capture process remains active.

### Controlled virtual input, October 15

The owner requested virtual-input testing without unmuting the Mac and installed
BlackHole 2ch 0.7.1. Its official package checksum, developer signature and Apple
notarization were checked before installation. The unchanged production recorder
receives the virtual device's input; recordings are not substituted with source
files. Fixtures remain private test resources, with original known ages.

The first virtual run changed only the Mac defaults. It failed both P/T cases
with recordings at the −160 dBFS floor and no model calls. The defaults were
restored. One physical output mute changed from unmuted to muted during that run;
no physical mute/volume setter was called, and it was left muted. This failure is
preserved under `virtual-input/`.

Device Hub has separate remembered input/output choices. Explicitly selecting
BlackHole for both on the dedicated simulator, enabling its digital sound level
and clearing **only BlackHole's** virtual mute produced nonzero recorder input.
Physical Mac output stayed muted during the subsequent checks. No Mac default-device
selection setters were called after v1 restoration. See [Apple's routing documentation](https://developer.apple.com/documentation/xcode/configuring-a-simulator-for-your-environment).

With that route, P failed native word admission and T matched but its model request
hit the old 45-second worker deadline. A separate fixed T diagnostic observed a
CTC result file at 38.797 seconds, then timed out before the complete pipeline
returned. File existence is not proof of validated intermediate output. The
worker group and scratch were cleaned; the app correctly paused model requests.
Results are preserved under `virtual-input-v2/` and `virtual-input-v3/`.

The processing budget is now 90 seconds. Native session/request/resource limits
are 100/100/105 seconds; the POST sets its own limit explicitly. Worker-group
termination, cleanup and conservative pause behavior are unchanged. All 16 bridge
unit tests and all 47 focused native checks passed, including the outgoing-request
budget assertion. Updated Debug builds passed. No model, feature, pronunciation
admission or judgment threshold changed. Cold-start latency under the new budget
has not been independently characterized.

The next fixed P/T run finished **1 passed (T), 1 failed (P), 0 skipped** in
65.906 seconds. T completed review → selected practice → fresh recheck using
three actual production-recorder takes, native word recognition, the strict Swift
client and the complete model. Its real model calls took 14.237, 12.226 and 9.266
seconds. Saved aggregates confirm fresh take IDs, source replay unchanged,
recording cleanup and disabled judgments; passing assertions also check frozen
first observations and participation-only history. Recorded power was approximately
−38 dBFS. P recorded measurable audio but returned word-not-matched and withheld
the model request. This is a successful controlled virtual-input **T** journey,
not multiple-sound capture success or independent new child productions.

Evidence: `virtual-input-v4/VirtualMicrophoneTests.xcresult`,
`tests-summary.json`, `attachments/`, `service-aggregates.jsonl`,
`FocusedTests.xcresult` and `source-pins.json` in the October 15 task directory.
The same original fixed B/P/M/T fixture set was then completed with B/M capture
cases: **0 passed, 2 failed, 0 skipped**. B was word-uncertain and M word-not-matched;
both captured nonzero audio, withheld model calls and confirmed cleanup. Those
negatives are retained under `virtual-input-v5/`.

An additional N/K/L engineering batch was selected after those earlier failures,
using the same permitted author-training cache, genuine age metadata, canonical-word
criteria, fixed crop margins and first-hash selection before each candidate's
inference. Candidate counts were N7/K4/L1; all three fixed crops prepared without
failure. No candidate was replaced according to its result. This is not a
prospectively fixed overall accuracy study or independent validation.

That run finished **1 passed (N), 2 failed (K/L), 0 skipped** in 43.364 seconds.
N completed the same actual recorder → native word → model → selected practice →
fresh recheck path, with three real model calls taking 6.659, 7.488 and 6.606
seconds. Its three recordings were approximately −32 dBFS. Attached aggregates
confirm the actual system recorder, fresh take IDs, source replay unchanged,
cleanup and disabled judgments. K/L captured nonzero audio but returned
word-not-matched and correctly withheld model requests. Evidence is
`virtual-input-v6/VirtualAdditionalSoundsTests.xcresult`, `tests-summary.json`,
`attachments/`, `service-aggregates.jsonl` and `source-pins.json`.

**T and N therefore establish two controlled virtual-input engineering journeys,
with six fresh recorder takes and six real model calls.** These repeat existing
source waveforms; they do not establish independent child productions,
physical-microphone quality, recognition accuracy or pronunciation correctness.
P/B/M/K/L failures remain part of the reviewable evidence.

A normal-app UI smoke check also opened Home → Review, practice, recheck, confirmed
that research processing defaults off, enabling it reveals known-age choices
6–12, and Start is disabled while age remains undeclared. It then closed back to
Home without recording or making a model request. The UI smoke did not repeat the
full journey through screen interactions; full recorder/model lifecycle evidence
comes from the explicit integration tests above.

Afterward, the app stopped and Device Hub confirmed restoration of the simulator's
original Input=System, Output=System and Sound=0. The dedicated simulator shut down;
all task services stopped and scratch directories were empty. Prior physical
output devices became unavailable during the work, and the Mac's current default became
BlackHole. That current selection was preserved and left **muted**; no physical
output was unmuted. Present original devices retained their levels; disappeared
devices were not recreated or forcibly selected. See `virtual-input-v6/cleanup-summary.json`
and `cleanup-audit-notes.md` for the exact restoration scope.

## Cause-specific guidance, October 15

The Debug simulator guided flow now preserves the service's exact cleanup-safe
rejection reason instead of reducing all nine reasons to a generic unavailable
message. Silence, a recording at its digital limit, unreadable audio and excess
duration receive distinct recording guidance. Unsupported targets, an unavailable
or busy model, rejected requests and rejected age declarations receive separate
service/context guidance. Age rejection never suggests changing a genuinely
declared age. Busy guidance refers to a later recording; a matched word still
cannot be checked again on the same take.

These are recording/service observations. In the unchanged bridge, `silence`
means exactly zero RMS and `clipping` means one or more PCM rail samples. Neither
establishes speech presence, loudness, sound correctness or a diagnosis. The
existing nine-code cleanup-safe boundary is unchanged; timeout, inference failure,
unknown codes, malformed processed timing and thrown errors still pause model
requests when cleanup cannot be confirmed. Cancellation still waits for actual
processing return before releasing the recording borrow.

The note remains bound to the exact entry, recording and submitted operation.
First-review notes stay frozen through selected practice and a fresh recheck;
later observations cannot replace the first note or attach to a sibling entry.
Recording and manual practice start no automatic model requests, and only
participation enters history.

Actual focused verification passed **32 tests, zero failures, skips or expected
failures**: 18 adapter, 10 existing client and four guided-flow tests. The official
result tree matches every selected method. The tests use generated recordings,
injected model/recognition responses and controlled transport; they establish
mapping, request binding, cancellation and lifecycle behavior, not new acoustic
or model accuracy. Strict formatting passed and separate Astra source review
found no blockers. The native runner exited zero, source pins remained unchanged,
and the dedicated simulator returned to Shutdown after 41.037 seconds. No model
inference, physical capture, audio-route mutation or external upload ran for this
change. Evidence is in `work/guided-model-feedback-reasons-20261015/`, including
`native-checks.xcresult`, `verification.json` and `independent-review.md`.

## Service readiness and recovery, October 15

After the existing word, consent, age, exact-entry and recording-cleanup gates,
the Debug simulator guided flow now checks the local service before submitting
audio. It sends only `GET http://127.0.0.1:8765/health`, with no recording, prompt,
age or context headers. A separate session uses four-second request and
five-second resource limits, disables cookies/cache and rejects redirects.
The response must be JSON, HTTP 200, at most 1,024 bytes and the exact six-field
research-only declaration. Missing, extra, duplicate and incorrectly typed fields
are rejected. The declaration says model availability is checked per attempt;
this is service liveness, not a successful model check.

If readiness fails, the matched word result stays intact and the app explains
that the service could not be reached or confirmed. Manual practice remains
available; a later fresh recording can be checked after the service starts.
The first review stays frozen through practice and fresh recheck. There is no
automatic request or same-take retry. This pre-submission failure does not pause
future model requests. An existing cleanup pause is never cleared, and unconfirmed
cleanup after assessment submission still pauses future model requests. The nine
trusted cleanup-safe rejection causes remain unpaused. Cancellation retains the
independent recording borrow until the bounded
health request actually returns and prevents assessment submission. Shared pause
is checked again after readiness and before model dispatch.

Actual focused verification passed **48 tests, zero failures, skips or expected
failures**: 27 adapter, 16 client and five guided-flow tests, retaining all 32
previous methods. The official result tree matches the selected source inventory.
The runner and Xcode exited zero, source pins remained unchanged, and the
dedicated simulator returned to Shutdown after 37.364 seconds. Strict formatting
passed; separate Astra source review found no blockers. Controlled transport
tests simulate timeout/errors; they do not measure a real five-second timeout
or reproduce a redirect handshake. The existing redirect delegate was reviewed.
A separate actual backend health-contract check passed with zero assessment
calls and confirmed server-thread/socket cleanup. No model inference, new capture,
audio routing change or recording upload ran for this change. Evidence is in
`work/guided-model-readiness-20261015/verification.json`, the official result
bundle and `independent-review.md`.

The authorized coordination task confirmed the prior Apple results: English
assets are installed and en-US on-device support is available, but Apple speech
authorization was denied and no recognition task started. No permission reset,
signing/account change or unchanged Apple retry was performed. Bundled Whisper
remains the working word route; see the [Apple verification](apple-ondevice-recognition-verification-20261012.md).

## Fresh-worker runtime check, October 15

A fixed four-call measurement exercised the unchanged complete Mac model bridge
on the existing permitted T and N training-derived engineering recordings, two
calls per input in that order. Each call started a fresh isolated worker with the
existing 90-second limit; inputs, genuine declared ages, canonical prompts and
source hashes were fixed before inference. No failed input was replaced.

| Input | First call | Repeated call |
| --- | --- | --- |
| T | 8.300 seconds | 6.434 seconds |
| N | 6.396 seconds | 6.526 seconds |

All four processed successfully, with no sampling errors. Maximum sampled
aggregate descendant RSS was approximately 1.57 GiB. The worker limit did not
expire; all four workers exited zero, their known process groups were absent,
the task's scratch directory was empty, and source/input hashes remained
unchanged. Root observed the enclosing command exit zero and independently read
the two reports and closure. The whole measurement took 27.972 seconds. Source
review found no blockers before execution. Evidence is in
`work/model-fresh-worker-runtime-20261015/verified-aggregate.json` and its retained
private reports, plan and source review.

These are fresh-process bridge measurements, including worker completion and
cleanup. They exclude native word recognition, recording, HTTP transport and UI.
N follows the two T calls. OS disk cache and other host activity were uncontrolled;
no machine-cold, exact peak-memory, phone-performance or latency-distribution
claim follows. Replayed training recordings are not new productions or independent
pronunciation evidence. The earlier 45-second failures remain preserved; this run
did not reproduce their startup stall or establish its cause. No further timing,
model or admission change is supported by these four observations.

## Remaining limits and Sunday

Actual recorder → model → practice → recheck is established for the controlled
virtual-input T and N cases above. Multiple-sound virtual input is demonstrated;
physical-microphone behavior and the complete Release media flow remain unverified.
A separate [testable Release word check](native-release-word-verification-20261015.md)
establishes one licensed public whole-word case and its cleanup. Its
[guided continuation](native-release-word-verification-20261015.md#release-guided-coordinator-continuation)
also passed eight generated coordinator checks and one actual ten-check
review/practice/recheck journey, with two participation saves and twelve
quality-admitted file-backed takes. Capture hardware, permission and playback
were doubled; live Release media and manual UI remain unverified. Earlier
silent-input and native admission failures are preserved. File-backed native/model
success remains established separately for P/T. Existing recording implementation and
generated lifecycle tests do not close those gaps. Model observations are fitted
corpus-rating outputs; word recognition and successful computation cannot turn
them into validated sound judgments.

A Sunday engineering review is realistic using the integrated build, the two
controlled virtual-input cases and the preserved failure evidence above. The requested Sunday acceptance additionally requires independent qualified
sound-level references and a fixed evaluation supporting the judgments shown.
None has been supplied or established. The [Sunday target](sunday-prototype-20261018.md)
therefore remains incomplete, with unsupported judgments disabled.

Independent Astra reviews covered the integration, timing fix, test-only fixture
preparation and added real-capture cases. Runtime evidence was supplied by the
primary agent; source review does not independently reproduce that evidence.
Final current-source/document review is recorded in the October 15 task directory.
The native UI setup smoke described above supersedes the earlier inability to
find the simulator surface: this Xcode version uses Device Hub.
