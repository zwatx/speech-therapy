# Owned stopped-recording handoff — October 24, 2026

Guided research processing previously rebuilt a `CapturedRecording` from the word
request URL and decoded WAV duration. Its average power was NaN and its producer
owner was missing. The actual stopped take already retained those measurements and
ownership. The exercised guided path now passes that original recording instead.

## Contract and implementation

`LocalWordCapturedContextRecognizing` is an optional internal capability. The
ordinary `LocalWordRecognizing` request/receipt contract remains unchanged.
`DirectPracticeSession` snapshots the actual stopped recording, request, take ID,
canonical entry ID and guided visit before submission/checking publications. It
rechecks the exact operation, cancellation, take, entry, visit and departure
state before dispatching the captured context. The ordinary provider's existing
already-cancelled request behavior remains unchanged.

The research wrapper prepares the exact canonical entry and guided visit. It
admits the context only when request/take/URL/entry/visit agree, measurements are
finite and the registered producer has exclusive retained ownership with no
current borrower. The `canRemove` ownership check and independent wrapper borrow
occur in one MainActor turn without a suspension or publication between them.
After the borrow, removal is correctly disallowed. Existing WAV validation also
checks that decoded duration equals the original capture duration. The original
recording, including PCM16 signal measurements and cleanup-owner identity, reaches
the processor unchanged; no replacement power or owner is synthesized.

This is an in-process capture provenance contract, not an unforgeable token. A
struct alone cannot prove that arbitrary caller-supplied measurements are real.
The production guarantee comes from the session's direct retained-take snapshot,
exact identity checks and live ownership registry.

URL-only calls and malformed supplied contexts can still perform the existing
independent word check. They cannot start research readiness or processing without
valid owned context. Existing disabled/age/entry/word-outcome reason priorities
remain intact; metadata failure does not reclassify an independent word match as
a sound judgment. Contributors must use the real stopped recording rather than
reconstructing capture evidence from a URL. The generic assessment client's
parser-input API and request JSON schema are unchanged.

Wrong-request and unconfirmed-cleanup word receipts previously allowed the
wrapper's `defer` to release its independent file borrow. That borrow now remains
protected even after the underlying recognizer releases its separate borrow.
Cancellation is not a cleanup acknowledgment. No recovery receipt is invented;
the existing session cleanup-blocked contract remains conservative.

## Actual verification

One current-source **Debug simulator** run passed **58 tests: 56 units and two UI
journeys**, with zero failures, skips or expected failures. The official summary
records no runtime warnings; separate Xcode SDK-version/debugger diagnostics remain
in the raw log. Tests use explicitly generated capture/recognizer/processor
fixtures. They make no actual model inference, sensor capture, network call or
recording upload.

| Test group | Passed | Scope |
| --- | ---: | --- |
| Guided research recognizer | 35 | Original word/readiness/model-result/cancellation contracts plus exact capture propagation, missing/malformed context, stale visit, competing borrower/producer, and independent cleanup protection |
| Guided research flow | 14 | Actual coordinator → retained capture → wrapper → processor seam, frozen first review/history, fresh recheck, and synchronous Close/background before processing |
| Selected direct-session checks | 7 | Captured capability dispatch, cancellation during publication, ordinary cancellation compatibility, retained-take results and guided continuity |
| Guided UI | 2 | Normal text 81.380 s; accessibility5 text 275.730 s |

The UI journeys start from a labelled generated five-check seed. They inspect
bound first-review results, choose and complete practice, make a fresh first-word
recheck, explicitly finish with other words unreached, inspect summary/history,
then repeat without inheriting old results. They are bounded stage journeys, not
a full initial review performed through user controls from launch. The unit flow
separately exercises all five initial and five fresh recheck operations.

Existing unit model-call expectations were preserved by migrating fixtures to
explicit generated producer ownership and prepared visits. New negative checks
prove that malformed contexts retain one word call but start zero readiness or
research calls. Processing checks assert exact original capture metadata and that
the producer cannot remove the borrowed recording. Both wrong word receipts and
unconfirmed cleanup leave the independent wrapper protection in place after the
fake word consumer finishes. Competing-owner tests do not bypass ownership to
force a cleanup acknowledgment.

Forty PNG files were exported. Hash grouping identifies 16 byte-distinct images;
the independent reviewer visually inspected those representatives, covering all
identical-file groups, and the coordinating agent viewed four representatives.
The UI is a regression check of existing internal research details, not a new
learner feedback panel. Largest text remains scrollable; full content need not fit
in one viewport. No VoiceOver speech/order claim follows from these captures.

The root personally observed SDK outer session 95870 exit 0, with the test stage
closing normally after 401.709 s, then export session 73283 exit 0. All owned stages
ended without signals, remaining process-group members or cleanup errors. Actual
before/after device queries show the dedicated SE3/iOS 26.2 and protected
simulators Shutdown. The protected device was never operated.

## Preservation and remaining work

The preceding verified app/build was preserved in an inert 2,297-file snapshot
before compiling at the original active build location. No copied build database
was executed. The final postcheck verified all 2,587 frozen input bindings and
the complete archived namespace, including the previous successful app inventory.
It also verified the older 1,255-file failed build, 2,323-file archive, 1,514 moved
intermediates and all 426 + 654 + 327 preceding milestone artifacts unchanged.
The prior task's active build path now holds this successor; its old bytes are
retained in this task's verified snapshot. Approximately 1.09 GB remained free at
the final check; space fluctuates and is not a guaranteed future build budget.

Evidence lives in `work/owned-capture-handoff-20261024/`: scoped dirty-tree baseline
and delta, exact source bindings, official test exports, image hash groups,
independent review and `POSTCHECK.json`. The actual current app product remains
under the preceding task's `checks-v2-DerivedData`; this run's result is this
task's **checks-v1**. No Git publication or deployment occurred.

The opt-in live integration test now checks original stopped-recording propagation,
but was only compiled, not executed. No hidden-model adapter, model resource,
threshold, learner finding, pronunciation score or clinical diagnosis was added.
`NativeHiddenOperation` still has no production caller, and full native acoustic
composition remains unqualified. Closed q8/public-head screens and the consumed
private study were not reopened. Real-media/VoiceOver verification, qualified
sound-level evidence, reviewer acceptance and release eligibility remain open;
the broad app goal stays active.
