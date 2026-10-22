# Release bundled word recognition verification

The default bundled recognizer matched the existing licensed public **bread**
recording in a Release-configuration simulator test build. The exact provider
receipt, worker/timer return, temporary-copy deletion and empty file ownership
were confirmed. This adds one Release whole-word runtime case to the prior Debug
evidence. It does not establish the full Release recording/practice journey.

## Implementation and original failure

The existing public-word test now shares its unchanged execution and assertions
between separately gated Debug and Release methods. The Release method requires
non-Debug simulator compilation, an explicit test-only environment opt-in, the
dedicated simulator ID and the exact app/test bundle metadata. Production source,
model resources, whole-take input, independent recognition, expected-word
comparison and the existing 15-second cooperative policy are unchanged.

The first attempt failed during unit-test compilation: existing visual tests used
configuration helpers that are intentionally excluded from Release. Xcode exited
65 before testing; the official summary contains zero tests and there was no
word-case receipt. The enclosing command exited one after 38.973 seconds, with
unchanged inputs and the dedicated simulator Shutdown. This failure remains in
`work/release-bundled-word-20261015/`; it was not relabelled as a runtime result.

Seven visual lifecycle tests now construct an equivalent explicit test-local
configuration, keeping their assertions active in both builds. Only the Debug
argument-parser test is conditional; Release instead checks that the runtime
default keeps visual feasibility disabled. No production research capability was
enabled to make the tests compile.

## Actual verification

Root ran the reviewed successor stages in order, verifying the Debug results and
cleanup before starting Release:

| Stage | Selected tests | Passed | Failed/skipped/expected failures | Enclosing elapsed |
| --- | --- | --- | --- | --- |
| Debug generated visual lifecycle/configuration | 9 | 9 | 0/0/0 | 31.385 seconds |
| Release generated visual lifecycle/default plus one real word case | 10 | 10 | 0/0/0 | 71.417 seconds |

Both official result trees match their exact selected method inventories. Root
observed both enclosing commands and Xcode children exit zero. All 191 pinned
source, project, runner, fixture and manifest inputs remained unchanged, and the
dedicated simulator returned to Shutdown after each stage. Separate Astra source
and execution-plan review found no blockers. Strict formatting passed for the
two visual test files; the public-word file retained its existing formatting.

The single Release word receipt reports `matched`, the actual default factory,
source/copy hash confirmation, the exact operation receipt, provider return,
worker/timer completion, confirmed cleanup, deletion and empty ownership. Its
whole-case time was 2,424 milliseconds. The test used the full existing 17,912-byte
WAV with its pinned SHA-256; no trimming, alternate input or prompt hint was added.

The console-log API was unavailable during collection. A broad action-log scan
then rejected six identical hierarchical copies of the printed receipt. Root
collected the one marker from the exact test-case leaf's `emittedOutput`; the
official details contain one test run. These were reads of the same saved result,
with no repeated test or model inference. Evidence, including the original
collection limitations, is in
`work/release-bundled-word-20261015-v2/verification.json`, the official result
bundles, `collect_verified.py`, source pins and independent review.

## Scope

This was an unsigned simulator Release test build with `ENABLE_TESTABILITY=YES`,
which exposes internals to XCTest. The generated Release configuration retains
`-O` optimization. Release starts the ordinary Home root; the Debug inert root is
not used for the Release stage. This is not proof of byte-identical shipping
archive behavior, manual UI navigation or physical-device performance.

The input is the previously used public Dvortygirl recording, attributed under
CC BY-SA 3.0 in the app's test fixture directory. Speaker age is unknown. One
reused word does not measure child recognition accuracy, general word coverage,
individual-sound correctness, improvement or diagnosis. Its timing is one
observation with uncontrolled caches, not a latency distribution.

No microphone, camera, playback, audio routing, Apple authorization request/reset,
same-Mac assessment request or external upload occurred. Generated visual checks
use existing mock capture/monitor dependencies. No signing/account settings,
scientific thresholds, reserved study or model weights were changed. Release
capture/playback, mirror and complete guided-media runtime remain unverified;
independent pronunciation references and fixed evaluation remain necessary for
sound corrections.

## Release guided coordinator continuation

A separate Release test now exercises the production guided coordinator with the
actual default bundled recognizer: five initial checks, manually chosen bread
and pig practice, two persisted participation records, and five fresh rechecks.
The initial results stay frozen; every recheck has fresh visit, take and request
identities. Recording, practice and repeating Check on the same take add no
unrequested recognition. No production Swift source changed for this continuation.

| Ordered Release stage | Passed | Failed/skipped/expected failures | Enclosing elapsed |
| --- | --- | --- | --- |
| Existing generated coordinator lifecycle/recovery checks | 8 | 0/0/0 | 75.710 seconds |
| Actual bundled-recognizer guided journey | 1 | 0/0/0 | 170.808 seconds |

The native journey itself took 70,380 milliseconds and made exactly ten actual
recognition requests with ten returned receipts. The unchanged public bread WAV
was copied into twelve fresh temporary takes. All twelve passed the default
AVAudioFile summary and capture-quality gates. Bread matched in each round; pig,
moon, tiger and dog were deliberate mismatches against that same bread source,
yielding two matches and eight nonmatches. This is one reused recording with four
mismatch controls per round, not five genuine word productions or new accuracy
evidence. Practice selection remained manual and dispatched no recognition.

The production SystemAudioCapturer used a file-writing hardware driver and a
permission facade. Playback was an idle test double. No microphone, camera,
playback, audio-route change, Apple authorization request or assessment-service
request occurred. Actual per-file deletion receipts, empty file ownership,
released hardware ownership, closed coordinator and removal of the isolated
history directory were confirmed. The dedicated simulator returned to Shutdown
after both stages. Exact official test inventories had zero skips or failures;
the native method has one official run and one exact leaf receipt.

All 192 pinned inputs remained current across both stages. All 95 production
Swift files (94 app, one contract) match the preceding Release milestone. Strict
formatting passed for the new test. Independent Astra source/runner review found
no blockers before execution. An initial result collector incorrectly expected
96 app source files; it stopped at that count assertion. Correcting the inventory
to the actual 95 production Swift files used the same saved result and repeated
no test or model call. Evidence and this limitation are recorded in
`work/release-guided-public-word-20261015/verification.json`, its collector,
official results, frozen source pins and independent reviews.

This extends the tested Release coordinator/native-word path. It retains the
unsigned, testable Release instrumentation described above and does not verify
manual UI navigation, live capture/playback, mirror behavior or physical-device
performance. Independent pronunciation references and fixed evaluation are still
required before correctness judgments, corrective findings or diagnosis.

A later [practice Next quality fix](native-guided-practice-verification-20261012.md#practice-next-quality-eligibility-october-15)
was verified separately on its final source with seventeen Debug and seventeen
optimized-Release-app checks, using an unoptimized XCTest harness. The actual-ASR
journey above belongs to its earlier frozen source milestone and was not rerun
for that eligibility-only change.

A later [ordinary Release UI checkpoint](native-release-navigation-verification-20261015.md)
passed two navigation journeys on the subsequently repaired word-picker view,
including skip-only review/practice/recheck and sampled Cancel dismissal at large
text size. It uses the normal Release root, with both app and UI-test module
optimized and testability disabled. It does not rerun this report's earlier
recognition or media evidence on that changed source.

## Five distinct public words and optional practice checks

A fresh Release integration test passes the current guided coordinator using five
different licensed recordings: **baby, backpack, bread, door and sky**. It performs
five initial checks, two explicitly requested practice checks on bread and sky,
then five checks on fresh recheck takes. All twelve takes pass the production
AVAudioFile summary and default capture-quality checks. The actual default bundled
CoreML recognizer returns twelve receipts: nine matches and three nonmatches.
All three sky checks return nonmatch; those observations are retained unchanged.
There was no required match count, fixture substitution or recognition-policy change.

Optional practice results remain attached to the current take. They do not alter
the frozen initial review, select practice words, write participation records or
gate Next on a word match. Duplicate Check calls after a terminal lexical result
create no additional request. Explicit advancement saves exactly two practice
records, which are reopened from disk. The recheck uses fresh visit, operation
and take identities. All twelve temporary files are deleted only after confirmed
ownership cleanup; the final coordinator and ownership registries are clear.

The official result contains exactly one selected passing method, one run, no
failures/skips/expected failures and one receipt in the exact method leaf. The
journey took 23,411 milliseconds; the enclosing test phase took 45.856 seconds,
including boot and shutdown. These are single engineering observations with
uncontrolled caches, not latency or accuracy estimates. All 144 source/tool/input
bindings and 42 generated/product bindings remained current. The 98 production
Swift files and three icon asset files match the preceding failed test's source.
The app uses Release `-O`, the XCTest harness `-Onone`, and testability is enabled.
Existing simulator signing defaults were used with no signing/account overrides.
The dedicated iOS26.5 simulator returned to Shutdown.

The preceding distinct-word test remains **failed**. It stopped after six actual
checks because its assertion incorrectly assumed manually requested practice
checks were disabled. Current production and its existing generated tests
deliberately support those optional checks; no production behavior was changed
to satisfy the successor. Earlier settings-query failures also remain preserved.
An initial saved-result collector counted three icon files as Swift; correcting
that inventory read the same saved official result and repeated no test or word
check. The [verification and bindings](../../work/release-guided-distinct-words-20261015-v4/verification.json)
and [source review](../../work/release-guided-distinct-words-20261015-v4/SOURCE-REVIEW.md)
record the exact current scope and prior failure lineage. The separate
[result review](../../work/release-guided-distinct-words-20261015-v4/RESULT-REVIEW.md)
confirms the official method inventory and twelve-check aggregate.

Capture hardware and permission remain doubled, and playback is an idle double.
This verifies the current coordinator, quality, native word provider, history and
file-lifecycle integration. It does not establish live recording, playback,
mirror behavior, manual UI navigation, physical-device performance or
individual-sound correctness. The five public recordings supply no child
accuracy estimate or clinical validation. [Apple Speech authorization remains
denied](apple-ondevice-recognition-verification-20261012.md); this passing test uses
the separately bundled native recognizer. No recordings were uploaded.

Separate [actual default-player checks](native-playback-runtime-verification-20261016.md)
now pass natural completion and explicit Stop with positive ownership cleanup and
deletion. Those component checks use the real AVFoundation driver. They do not
replace this guided test's idle playback double. A later
[combined guided-media check](native-playback-runtime-verification-20261016.md#combined-guided-word-checks-and-replay)
now passes twelve native checks and three actual replays on fresh file-backed
takes. Live microphone capture, mirror runtime and sound-specific validation
remain open.
