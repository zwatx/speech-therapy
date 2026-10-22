# Native cleanup, navigation and feedback integration — 2026-10-09

Status: SOURCE-v10 passed 384 controlled owner tests, five generated UI checks across two runs, and Release compilation. Final bounded visual review found no blocking sizing/overlap issue. The broad app goal remains active.

## Resulting behavior

Recording, playback, examples and guided practice join the actual owner's cleanup before departure or another action. Failed cleanup retains exact file/operation recovery callbacks; Retry remains explicit. A genuine successful retry settles the current state without rewriting the original failed acknowledgement. Close revokes eligibility synchronously and retains its task across view loss. Completed assessment cannot reopen from a stale failed removal result.

Two actual Feedback defects were repaired: reentrant exact file recovery no longer leaves a stale cleanup flag, and a clean invalid-recording failure permits a fresh recording under every existing guard. Failed unlinking remains visible as paused with Retry. Guided plan departure follows actual settlement.

Home exposes process-owned pending cleanup after leaving a screen, with passive snapshots and explicit Retry. Initial generated Sound and About reopening share the exact admitted resources. File-only second Close requires real retained callbacks and clear hardware/permission; leaving does not claim deletion.

Actual UI failures exposed an oversized Sound header and an outer safe-area notice covering Home's About control. The full Close note now scrolls below the fixed Close/header and is announced when it changes. The recovery notice reserves real space above navigation. Full warning text scrolls when it cannot fit within 40% of the host viewport, with Retry pinned; a small SwiftUI Layout adopts natural height for short messages. The existing guarded Debug/simulator Sound link sits below About's heading, with its destination, guard, identifier, resources and disabled state preserved. All explanatory text and other lab links remain.

## Final verification

- SOURCE-v10: 157 app/project/package source rows and 146 Swift-file inventory.
- OWNER_CHECKS-v10: exit 0, exact 384 distinct passing methods in 21 suites; no failures, skips or expected failures, all 159 inputs unchanged.
- GENERATED_UI_CHECKS-v10: exit 0, 2 PASS / 0 FAIL / 0 SKIP, all 162 inputs unchanged; exact normal/AccessibilityXXXL persistent file failure → first/second Close → Home explicit Retry failure → About actual guarded reopen → Close/Done → same pending Home.
- GENERATED_UI_CHECKS-v11: exit 0, 3 PASS / 0 FAIL / 0 SKIP, all 161 inputs unchanged; the same three previous generated Sound BW result/limitation/banner, Unified service-pause/replay-available (no Replay tap), and guided denied/skip/early-finish/all13 planned rows.
- RELEASE_COMPILE-v4: exit 0, all 157 source inputs unchanged; generic simulator build only, no app or tests executed. Package inspection verifies microphone purpose and absent Release camera purpose.
- Visual review: verified sole Opus5.5 source/image proposals v1–v4 and final v5 review found no blocking sizing/overlap issue in five exact Source-v10 viewports. Normal frame040 resolves the prior blank expansion; XXXL frames026/030 retain pinned Retry below scrolling text. Sheet frame021 does not show its entire long warning or Retry; automated full journeys supply reachability evidence, not a full manual visual audit.

Owner and UI runs all had no expected failures. The baseline UI durations were 35.44 seconds (guided), 18.00 seconds (Sound) and 43.98 seconds (Unified). The dedicated simulator was confirmed Shutdown before and after each serial run; after both UI runs it was already Shutdown when root checked, so no further shutdown mutation was needed.

These are separate runs, not one 389-test suite. Every version keeps its own input digest, command, exit receipt and safe test summary/tree. Source must remain unchanged during each run. Only the exact dedicated simulator is used, with shutdown before/after serial tests. Screens are direct task-owned simulator PNGs; no raw result attachments or OS logs are read.

## Preserved failures

Debug compilation first failed on task-result tuple labels, then on an explicit Bool return. The first executed 384-method owner run had 374 passes and 10 failures. Production fixes addressed two Feedback defects; insertion-only test setup/terminal joins and the exact example-player facade registration addressed genuine fixture sequencing races without weakening assertions or waits. Earlier Capture's ended → cleanupBlocked regression and Direct's future-driver injection failure remain recorded with their repairs.

UI-v3 and v4 each had two genuine failed hittability checks. UI-v3 Xcode finalization stalled and required SIGINT to its exact owned child after 649 seconds; finalized results still record both failures. UI-v4 completed with diagnostics disabled. Actual cause of the earlier infrastructure stall is unproven. Safe geometry/pixels confirmed Close at y=-26 with a 469-point note, and About at y=28 behind the notice ending at y=148.

UI-v5 and v6 each passed Normal and failed XXXL at the unchanged one-minute allowance while traversing the long About page. The existing preview link moved toward the top; UI-v8 subsequently passed both complete journeys, at 58.74 and 36.06 seconds. No allowance, assertion, font size, cleanup result or retry policy was weakened. Test navigation uses bounded real gestures on identified notice/About scroll surfaces. Final visual review then found normal-size empty space from a greedy height frame; the Source-v10 height-cap layout addresses that measured issue.

## Limits and remaining work

Permission, capture, player, service and recording fixtures are generated/injected. Runtime state, file deletion, serialization and cleanup receipt paths are actual. No physical microphone/camera/output, acoustic-model/endpoint request, private history, owner runtime, study media, participant data or refit was used. The persistent failure intentionally remains pending; process termination is not deletion or crash/relaunch recovery proof.

No new full UI accessibility audit, numeric contrast, dark/landscape/device variants, physical VoiceOver or actual audibility is established. The XXXL full journey's 58.72-second Source-v10 pass has little headroom under 60 seconds (Normal 36.11 seconds); a passing run does not establish repeated timing reliability. Earlier Source-v9 timings remain recorded separately.

Engineering verification does not establish independently produced phonemes, target-sound correctness, age calibration, diagnosis, correction efficacy or meaningful child improvement. Real acquisition/output in an allowed functioning environment, lawful independent reference labels, intended-user validation and final qualified review remain separate dependencies. The failed real-player evidence remains open. Experimental feedback/preview remain Debug/simulator only; Release compile is not Release execution or device eligibility.

Evidence roots: work/consumer-feedback-20261009/native-owner-integration, generated-ui-selected-verification, native-owner-final-review and native-recovery-layout. Earlier immutable guides and capsules retain their original scopes.

## Exact evidence bindings

SOURCE-v10: `806576e4d65c2cb4ae8970bab8c95218649085c4ac93ac2abd5f8e54a8d8380d`. Owner INPUTS-v10: `9922e1c383a1e1d6f5e99542461285b9dcc3b12ee1b06bdf6fbc21c95f3f38da`. UI INPUTS-v10: `a074d1f0f3f33dccdbe363877a72e856d953cf1503913692dc5db17bd4d4bb9b`. UI INPUTS-v11: `5e38d68b4da9d248769fd2706ae29d936035b313a28057006aff5cd68c3ebee5`. All refer to the same final 157 source rows and 146 Swift-file inventory.

Root safe exports: OWNER_CHECKS-v10-SUMMARY/TESTS/RESULT, GENERATED_UI_CHECKS-v10/v11-SUMMARY/TESTS and separate RESULT-v10.json / RESULT-v11.json, Release-v4 compile/package receipts and selected screenshot capture-v6 (43 PNGs, no capture failure). Exact method sets were checked against the selections. No raw attachments were used. LAYOUT_PREEXEC-v4 and Opus VISUAL_REVIEW-v5 retain their original scope and limitations. Earlier evidence versions are preserved.
