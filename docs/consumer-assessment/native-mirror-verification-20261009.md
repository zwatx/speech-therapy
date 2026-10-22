# Native optional mirror verification — October 9

## October 12 update

The later production revision exposes the optional mirror in Debug and Release.
Its separate verification passed both Debug and unsigned Release builds, all 44
selected unit checks and all 14 selected Debug mirror interaction checks. Both
built app descriptions include the preview-only camera purpose. Source, resource,
product and owned-process cleanup checks passed; the dedicated simulator finished
available and shut down. No new speech inference was selected.

Physical camera operation and Release-runtime interaction remain unverified.
See the [October 12 independent actual-result review](../../work/r-inference-checkpoint-20261012/restart-native-ai-v1/ASTRA-NATIVE-RELEASE-MIRROR-ACTUAL-v2.md).
The remaining October 9 report below describes its earlier Debug-only revision,
including that revision's Release camera-description behavior.

The native Debug direct-practice screen adds **Show mirror** below its audio controls. This is an optional plain front-camera preview. It does not analyze faces, record camera frames, upload images or judge speech. Normal simulators report that the camera is unavailable; generated verification screens clearly label their sample image.

## Behavior

Camera permission and scene activity are separate gates. Waiting for a camera permission decision temporarily pauses Record. Cancel returns to audio practice. An unavailable or denied camera leaves recording available. A first microphone permission request stops an active mirror; after permission is already granted, an explicitly shown mirror can accompany recording or review while the app remains active.

Hide, Close, inactivity, background, disappearance and completion revoke the visible preview immediately. The app retains its exact camera owner until cleanup is acknowledged; an explicit Retry can recover a failed stop. Old permission callbacks or cleanup events cannot reopen a camera or stop a successor. Returning to the screen does not automatically restart the mirror.

Audio and camera recovery are independent. Close pauses practice and waits for both camera release and current audio/file cleanup proof. An ordinary camera failure permits audio practice, while a failure after Close or completion uses neutral recovery text rather than promising continued practice. Camera recovery remains above the completed-practice heading and stays reachable. Completion counters/history cannot be committed by reentrant Close or old callbacks.

## Actual final verification

At the same SOURCE-v7/INPUTS-v7, **127 unit methods**, **8 mirror UI methods**, **6 Close/completion UI methods** and **7 existing research UI methods** passed. Each group matched its exact declared method names, with zero failed, skipped or expected-failure checks. The21 UI methods ran in three separate groups. Previous-version passes were not pooled into these results.

Generic Release compilation passed without execution. Its generated Info.plist keeps the microphone purpose and omits the Debug-only camera purpose. All267 inputs and157 Swift inventory remained exact; the dedicated simulator was freshly verified Shutdown before/after each of the five capsules. All140 direct generated PNG hashes were checked. Strict formatting checks passed for all15 added/changed Swift files.

The127 units cover camera ownership, immutable stop acknowledgements, successor/reentrant safety, separate permission/activity gates, preview revocation, parent-state publication, audio/camera release in both orders, current retained-file evidence, strict generated launch admission and unchanged playback recovery. Fourteen mirror UI methods exercise sample recording/replay/completion, permission cancellation, unavailable/denied camera, failed/held Close and completed-practice recovery at normal and largest accessibility text. Seven existing UI methods preserve selected-word focus, missing examples, guided/manual/recheck boundaries, both word/sound orders and local replay during service cleanup pause.

Fixed generated camera/audio drivers and generated PCM files use no hardware sensors, actual audio output, network or speech model. The dedicated simulator is132DD629-A694-4D98-A0BB-B828676DD698, Cadence Sound Compact Verification, available iOS26.5, serial Shutdown before/after. Runner gates the exact source inventory, all267 inputs and same-version unit proof. Original60/90 per-test limits,600-second child budget and assertions remain; no retry flags. Only safe test summary/tree and direct task-owned generated PNGs are read, without raw result attachments/activities/OS logs/private history.

Opus5.5 inspected10 fresh, unaltered partial v7 screenshots and three source files and found no blocking issue. Its sole reported model was `claude-opus-5-5`; the earlier paused-copy finding is clear in source and supplied pixels. Normal completion shows recovery above the title; largest text wraps the neutral copy and sample disclaimer. Most large-text images are scrolled crops: they do not show the entire Close panel, every denied/unavailable button, focus announcements or measured touch targets. Ordinary stop-failure reassurance is source-only in this review. The functional checks separately exercise recovery controls. These are partial views, not a comprehensive accessibility or physical-device review.

## Preserved findings

Diagnostic compiler v1/v2 isolation/escaping-closure failures were repaired and retained. Sourcev1/v2 are preserved unexecuted. V3 passed127 units but one largest-text three-state UI method timed out at60 seconds. V4 split each permission state/size into its own test, retaining assertions/caps;127 units/8 UI passed, then all4 Close tests failed because the fixture's closed marker existed behind its presented screen. V4 positive marker existence cannot prove dismissal. V5 shows the marker only after dismissal and asserts initial absence; fresh127 units/8 UI/4 Close tests passed.

Actual Opus5.5 review of8 partial v5 PNGs and source found the misleading failed-camera copy after Close/completion. V6 fixes that copy and initial recovery focus and adds2 completion UI tests, but remains unexecuted. Astra found a new-test immediate post-Retry absence assertion raced asynchronous UI state. V7 adds a bounded5-second disappearance expectation while retaining the original assertion and subsequent actual Close proof. Disappearance alone is not camera-release proof because the control also disappears while stopping.

## Source and boundaries

- SOURCE-v7:168 rows/157 Swift, digest `b61963b6d760c5ab0293a82fd3006b4f527a44d31be4958a393e8df759cd86ba`.
- INPUTS-v7:267 rows, digest `7a0c71f09c7990935ba5b8403b697c5cc7383048c714735a212064b10f71a795`.
- Original50 direct-practice session-test bytes remain an exact prefix, followed by18 new integration tests.
- All96 reserved browser rows remain exact. Delivered8813 and earlier owner-used services, source/runtime/history/tabs were not contacted or changed.
- Six Debug components, two unit files and one UI file are added. Session/player/root/app/test-host composition and generated project membership change. Release camera eligibility remains unchanged.
- Task receipts: `work/consumer-feedback-20261009/native-mirror-integration/`; frozen source/input archives, admission/source reviews, exact selections, safe results, device receipts, direct PNG hashes and all earlier failures.

This is Debug engineering behavior. Physical front-camera preview/crop, mirroring, camera/audio coexistence, permission timing, privacy indicators, power/performance and VoiceOver remain unverified. It does not establish pronunciation correctness, useful correction, child calibration, visual utility, improvement or diagnosis. Lawful independent references, intended-user evidence, final qualified review and release resources remain open. The whole app goal remains active.
