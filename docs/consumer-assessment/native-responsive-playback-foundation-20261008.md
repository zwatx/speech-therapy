# Native responsive playback foundation — 8 October 2026

Status: **FOUNDATION_VERIFIED; consumer migration remains open.** The broad app goal remains active. This milestone verifies the queue/ownership boundary and one recorder-startup fix. The current default player, three production playback sessions, guided transitions and screen controls still use the existing synchronous playback API. This does not yet establish a responsive app or working audible output.

## Implemented behavior

`PracticePlaybackRuntime` owns immutable operation IDs and URLs on MainActor. All injected driver construction, activation, preparation, play, stop, resource release and deactivation execute on a dedicated serial Dispatch queue. The factory is Sendable; mutable driver references do not cross that queue boundary. An independently locked cancellation bit can be revoked immediately while a driver call is blocked. Cancellation before play commitment prevents future play; cancellation after commitment requires cleanup and does not promise that no sound occurred.

The runtime reports preparing, playing only after actual start acknowledgement, stopping, cleanup blocked and idle. Duplicate stops share the original immutable acknowledgement, including a negative receipt. Only explicit retry starts another cleanup attempt. A successful receipt requires stop, playback resource release and deactivation. An exact hardware lease is retained through blocked or failed cleanup and rejected by other player/capture reservations. The ownership gate retains a reachable explicit recovery action even if the original facade disappears. The concrete recorder does not yet reserve this hardware gate.

The new AVFoundation driver stores configuration at construction, defers real session/player work to queue-invoked methods, checks actual prepare/play return values and propagates deactivation failure. Its nonisolated delegate proxy uses immutable player identity and operation values; callbacks never consult the driver's mutable player across threads. This driver compiled but was not executed in this milestone and is not the current default player.

`ProcessAudioFileOwnership` retains exact file claims and playback borrows. Pending borrows, wrong owners and overlapping retaining owners prevent removal. Claims are released only after actual deletion; failed deletion leaves ownership intact. Startup scanning is once per standardized directory per process, protects retained/borrowed URLs, rejects reentrant scanning and preserves an initial failure. **The real `SystemAudioCapturer` initializer now uses this once-only scan**, fixing route recreation deleting a take created after the initial scan. Capture creation/discard and production playback borrowing still require integration. This process-local registry is not crash recovery.

## Observed verification

Frozen inputs contain 142 exact rows: all native source/tests/UI tests/resources, contracts source/manifest, native project/spec/shared scheme and the controlled runner. Row digest: `a42f8095987cd9654f3fff918423fa8fad1a846b11654e95c884d13f84e51595`. All current files and `foundation-source-v2` copies match. The 127-row initial baseline has 123 unchanged rows and four changed existing rows; six new Swift files were added. Nine extra pinned rows were absent from the initial manifest and are additional coverage, not evidence of nine new product files.

Actual `FOUNDATION-v1` exited 0 with **27 distinct tests passed, zero failed and zero skipped** on owned iPhone SE 3 / iOS 26.5 simulator `132DD629-A694-4D98-A0BB-B828676DD698`: 16 runtime, seven registry, two recovery and two temporary-store cases. The result bundle summary and individual case export agree. Inputs remained exact before and after execution. Parallel testing was explicitly disabled and no retry flags were used; all inherited audio/capture/transport opt-ins were stripped. Tests used controlled drivers and uniquely created generated file fixtures, never the new AV driver or recorder permission/start methods.

The controlled runtime cases cover blocked construction/activation/preparation with MainActor heartbeat, immediate cancellation, committed play with delayed cleanup, independently held stop/resource release/deactivation, capture/second-player reservation refusal, false/throwing starts, every cleanup-stage failure, multiple explicit failed retries, exact duplicate acknowledgements, same-facade successor/stale callbacks, natural completion and cancellation suppression, cancellation-handler-only behavior, facade loss, and generated file retention through pending/failed cleanup and route scavenging. These are controlled software checks, not real capture/output measurements.

The final frozen Release app build exited 0 without execution. Earlier generic Debug builds also exited 0 but predate later recovery/initializer/test edits; final Debug compilation is established by the actual foundation test invocation. Scoped formatting checks passed after preserving the original registry formatting warnings. The test compile emitted two weak-reference variable mutability suggestions; the result summary contains no runtime warnings.

Independent GPT-6 Astra source review v1 identified a non-Sendable factory, an unexpected-error false-pass test helper and a fixed deletion target outside an owned fixture directory. These were corrected before execution. Review v2 and the final runner/input review found no remaining foundation blocker. Final independent source/result/documentation review is complete in `FOUNDATION_EVIDENCE_REVIEW-v1.md`; its two wording corrections were applied before finalizing this note. A tool-free exact Opus 5.5 UI specification is retained with verified model identity; no UI changes or pixel review occurred here.

The owned simulator was already shut down after Xcode's test run. A subsequent shutdown request was refused with code 405; follow-up metadata confirms Shutdown and no retry occurred. No manual media cleanup was performed. Test assertions verify the exact generated file retention/deletion cases; no broader crash-cleanup claim is made.

## Required continuation

1. Connect an acknowledgement-aware player facade to all three playback owners and the process file registry; preserve accessible cleanup retry after screen loss.
2. Integrate concrete capture hardware leases and truthful deactivation failure handling, including legacy capture owners.
3. Convert guided/free completion, replay switching, retakes, checks, save, lifecycle and navigation to wait for exact cleanup receipts and revalidate route/visit/take tokens before changing state or deleting files.
4. Apply reviewed preparing/stopping/retry/Close UI states, update injected players/fixtures, then run meaningful controlled session/navigation checks and independent review.
5. Establish reliable real acquisition/output in a permitted functioning environment without repeating the historical failed renderer variants. Independent produced-sound labels, calibration, intended-child and clinical evidence remain external open requirements.

The historical actual native playback failure remains unchanged: couldNotPlay after two 15-second CoreAudio timeouts and zero frames. No microphone, camera, actual audio renderer, physical device, owner endpoint/runtime/history, reserved study, speech-assessment/recognition model execution or automatic pronunciation/diagnostic claim was exercised by this milestone.

## Evidence

Task directory: `work/consumer-feedback-20261008/native-responsive-playback/`. Key records: `ARCHITECTURE-v1.md`, `SOURCE_BEFORE.json`, `FOUNDATION_INPUTS.json`, `foundation-source-v2`, `FOUNDATION_REVIEW-v1.md`, `FOUNDATION_REVIEW-v2.md`, `FOUNDATION_RUNNER_REVIEW-v1.md`, `FOUNDATION-v1-COMMAND.json`, `FOUNDATION-v1-EXIT.json`, `FOUNDATION-v1-SUMMARY.json`, `FOUNDATION-v1-TESTS.json`, `FOUNDATION-v1-CASES.json`, `FOUNDATION_POSTCHECK-v1.json`, `BUILD_RECEIPTS-v1.json`, `OPUS_UI_SPEC-v1.md`, `OPUS_UI_RECEIPT-v1.json`, and owned simulator metadata/attempt receipt. Original warnings, pre-regeneration freeze, reviewed source versions and prior milestone artifacts remain preserved.
