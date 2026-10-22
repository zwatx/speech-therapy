# Native guided practice verification — October 12, 2026

The current guided flow passed all 23 selected unit tests and all 14 UI journeys on the dedicated compact iOS 26.5 simulator. Debug and unsigned Release builds succeeded. UI checks covered compact and largest text, first checks, explicit practice choices, fresh practice recordings, optional manual word checks, paired rechecks, cancellation, and closing while processing owns a recording. These use generated engineering fixtures; they do not measure speech accuracy.

The previous UI run passed 13 of 14 journeys and failed an exact selection assertion: three selected words where two were expected. The working explanation was that a short central scroll gesture could activate a choice. The sole repair moves automated scrolling into observed blank outer space, away from controls, with bounded corrections based on actual movement. No production state or UI behavior changed. The exact selection, containment, 44-point touch, cancellation and recording-ownership assertions remain. The earlier failed results are preserved.

The repaired UI test is 24,944 bytes, SHA-256 `1bdb8bee3f063caf13a4d74dae07ee33b9db53bd583744edb78572a4c1632e81`. It is the only changed row in the 338-input verification inventory; all other 337 rows remained unchanged.

Root actual session 16376 returned exit 0, terminal `0a0813`. Immediate independent collection returned exit 0, terminal `808fe3`. A further root check through that terminal verified every saved evidence pin, current source and resource guards, absence of all twelve known stage groups and the controller, and exact simulator Shutdown. It completed after 858.769 seconds within the original 3,000-second interval (`d534e1`). The actual collection is retained in `work/r-inference-checkpoint-20261012/restart-native-ai-v1/coreml-whisper-v1/native-guided-practice-gutter-verification-v1/ROOT-ACTUAL-COLLECTION-v1.json`.

Apple English speech assets and capability readiness are installed and verified separately. The attempted Apple recognition route returned denied speech authorization without starting a recognition task. The app's existing bundled Core ML Whisper recognizer remains the working route. Signing and account settings were unchanged, and recordings were not uploaded.

This establishes the selected guided-flow behavior and build checks. Physical microphone, playback and camera operation, Release UI execution, independent sound-error accuracy, child assessment, treatment effectiveness and diagnosis remain unverified by these checks.

## Practice Next quality eligibility October 15

Guided practice previously enabled **Next word** whenever a latest take existed,
even when its recording quality prevented completion. Tapping it could therefore
do nothing. The coordinator now requires the latest take's existing acceptable
assessment and finite duration/power, matching the media owner's completion
requirements. An earlier acceptable take does not qualify a rejected latest take.
Record another try, Skip and Close remain available; word-recognition outcomes
still do not determine participation or progression.

Two generated coordinator regressions cover no take, a short take, a fresh
acceptable replacement, an acceptable earlier take followed by a short/NaN/infinite
latest duration, and a third acceptable take restoring progress. They verify the
same visit and frozen initial results, no premature deletion/save/recognition,
one exact persisted participation record, duplicate-save prevention and cleanup.
Fifteen existing tests cover valid completion, save recovery, optional word-check
outcomes, held operations, cancellation, exact receipts and Close.

The first equality-form fix's Debug run passed exactly 17 tests with zero
failures, skips or expected failures in 59.446 seconds. All 211 pinned inputs stayed unchanged and the
dedicated simulator returned to Shutdown. The original Release build reported
`SwiftCompile normal x86_64` exit-zero/no-output failure and then stalled without
compiler descendants. Root terminated only its verified isolated process group;
the enclosing command exited one, Xcode was terminated with SIGTERM, and elapsed
time was 384.784 seconds. Inputs remained unchanged and the simulator shut down.
The official summary could not be read (xcresulttool exited 64), so no test count
or assertion-failure outcome is assigned to that build. Its cause is unknown and
all original artifacts are preserved in
`work/guided-practice-next-quality-20261015/`.

A same-source arm64-only successor reported the same error in the XCTest target,
then reached its unchanged 600-second enclosing deadline. Xcode was terminated
with SIGTERM; the enclosing command exited one after 612.725 seconds including
cleanup. Inputs remained unchanged, the simulator returned to Shutdown, and no
members of its exact build process group remained. Its official summary was also
unavailable, so test counts remain unknown. This rules out an Intel-only failure;
it does not establish the compiler's cause. Artifacts remain in
`work/guided-practice-next-quality-20261015-v2/`.

A third configuration retained that source and seventeen tests, kept the arm64
Release app optimized with `-O`, and set only the XCTest target to `-Onone`.
Its wrapper exited one when the final simulator-state query timed out before
writing the child outcome. Xcode's exit code, timeout status and official test
counts were not recorded and remain unknown. Follow-up found unchanged inputs,
no test success/failure banner or compile error, and no remaining compiler workers
owned by that attempt. A fresh bounded query confirmed the dedicated simulator
Shutdown and available. This is an inconclusive verification attempt, preserved
in `work/guided-practice-next-quality-20261015-v3/`.

The final source uses a case-pattern guard on the same exact latest take instead
of synthesized enum equality. Independent source review confirmed equivalent
assessment and finite-value requirements, including cleanup publication windows.
No phase-summary shortcut, getter, threshold or test assertion changed. A brief
compiler sample caught the SIL ownership optimizer, but severe observed host
load and the limited sample prevent attributing the earlier failures or delay
to a particular expression. No compiler-cause or timing-distribution claim follows.

Root then verified the final source in two ordered stages:

| Current-source stage | Passed | Failed/skipped/expected failures | Enclosing elapsed |
| --- | --- | --- | --- |
| Debug app and XCTest harness, both `-Onone` | 17 | 0/0/0 | 33.239 seconds |
| Release app `-O`, XCTest harness `-Onone` | 17 | 0/0/0 | 52.749 seconds |

Both enclosing commands and Xcode children exited zero. The official method
inventories match exactly; all 211 inputs remained current and identical across
stages. Actual SwiftDriver command lines confirm those optimization flags, DEBUG
present only in the Debug stage, and the arm64 simulator target. Both built app
and test Mach-O binaries contain only arm64. The dedicated simulator returned to
Shutdown, cleanup queries completed without errors, and separate exact-build-path
process scans found no remaining owned compiler workers or required signals.
The revised runner saves known child outcomes before cleanup queries so a later
query failure cannot discard those facts. Verification is recorded in
`work/guided-practice-next-quality-20261015-v4/verification.json`, its source pins,
official results, compiler-flag receipts and independent source/plan review.

This verifies the optimized, unsigned, testable Release app with an unoptimized
XCTest harness on arm64. It does not establish the original fully optimized
XCTest or universal build configurations, byte-identical shipping archives or
manual Release UI/media behavior. Earlier failed and inconclusive attempts remain
preserved; the current pass does not diagnose their cause.

Independent Astra source and execution-plan review found no blockers. Full-file
strict formatting lint still reports 18 existing production and 27 existing test
diagnostics; before/current diagnostics match exactly after mapping unchanged
lines, with zero findings on changed lines. Unrelated formatting was preserved.
These generated checks do not reproduce the earlier real-ASR run on the changed
source or establish manual UI, live microphone/playback, accuracy or diagnosis.

A later [ordinary Release UI checkpoint](native-release-navigation-verification-20261015.md)
passed two navigation journeys on the subsequently repaired word-picker view,
including skip-only review/practice/recheck and sampled Cancel dismissal at large
text size. It uses the normal Release root, with both app and UI-test module
optimized and testability disabled. It does not rerun this report's earlier
recognition or media evidence on that changed source.
