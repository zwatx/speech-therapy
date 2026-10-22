# Native direct practice: two tries and history-save retry — verification guide

Date: 2026-10-11 · Status: **checkpoint closed within its generated simulator scope; final Fable engineering/evidence review CLEAR**

## Scope

This guide covers the iOS learner app's ordinary direct-practice session:

- Recording up to two completed takes of the current word.
- Listening back to either take, only by explicit choice.
- Retrying a failed save of participation metadata for the same completed session.

This flow makes no phonetic or diagnostic judgment and claims no improvement. Recording tips describe capture quality of the latest take only. The learner may listen to both takes and compare them for themselves, but the app makes no automatic comparison and never judges one take better or worse. No prospective listening cue and no automatic speech recognition are integrated.

## Behavior (native SOURCE-v2)

Sources: [`DirectPracticeSession.swift`](../../apps/ios-learner/Sources/DirectPractice/DirectPracticeSession.swift) and [`DirectPracticePlayerView.swift`](../../apps/ios-learner/Sources/DirectPractice/DirectPracticePlayerView.swift).

- **At most two kept takes.** Takes are stored oldest first. "Record another try" keeps the current take. When two exist, it first removes the earlier one, with exact evidence, and only then asks for microphone permission or opens a recording file.
- **Explicit listening.** With two takes, the screen shows separate "Play earlier try" and "Play latest try" rows. Tapping the playing row stops it. Tapping the other row stops the exact active operation and starts the requested take only after a positive release acknowledgement. A missing or negative acknowledgement never starts other audio. While a stop is settling, both rows are disabled.
- **No automatic playback.** Recording another try never stops playback on the learner's behalf; it waits until playback is idle. "Back to your recording" after a denied or failed replacement never starts playback or capture.
- **Destructive actions are labelled.** "Delete both tries and start over" removes every kept take and returns to Ready. Next word, Finish and Close also remove both takes.
- **Participation save retry.** On completion, one frozen, immutable record is created: session ID, completion date, sound ID and word count. If the save fails, "Try saving again" rewrites that same record. A retry never captures audio, changes counters or starts media cleanup. Close, restart or Practice more revoke the frozen record. A write already in progress may commit its own entry, but no later session is labelled "Saved".
- **Cleanup gates.** Close stays blocked until playback, microphone and camera (Debug mirror only) release are confirmed. A second explicit Close may leave a file-only failure pending only when every retained file has a process-held producer retry.

## Inputs and environment

- **Native source:** SOURCE-v2, 170 rows, 159 Swift, digest `145176da16a981b4ff08246f2a191b3607af345362bfa47c6bfca61a818cbb8e`. Identical in INPUTS-v2 and INPUTS-v3; there is no SOURCE-v3. Native source was unchanged through the checkpoint.
- **INPUTS-v2:** 269 rows, digest `4ef23d8147873e6773ca300a0343f49bc5e2ab84847bb996607f1effb4ef964a`. All 269 rows remain exact.
- **INPUTS-v3:** 269 rows, digest `78b65a14f45a488d39ac84e89756e70928dfc9dc1cab42c95b1f2cbc1feb68af`. It replaces the three v2 harness rows (`SELECTION-v2.json`, `export_safe_results-v2.py`, `run_checks-v2.py`) with three new rows for the current v3 files: [`SELECTION-v3.json`](../../work/consumer-feedback-20261009/direct-two-try/SELECTION-v3.json), [`export_safe_results-v3.py`](../../work/consumer-feedback-20261009/direct-two-try/export_safe_results-v3.py) and [`run_checks-v3.py`](../../work/consumer-feedback-20261009/direct-two-try/run_checks-v3.py).
  - `SELECTION-v3.json` content is byte-identical to `SELECTION-v2.json`; only the filename changed.
  - No native-source or 96-reserved-row guard change.
  - Root ran `py_compile` on both v3 scripts, unchanged from Opus's version: exit 0.
- **Reserved rows:** the 96 reserved rows are exact in both 269-row manifests, and the 170 native source rows are exact. Root verified this after all groups, including REGRESSION (64 PNGs).
- **Simulator:** dedicated iOS 26.5, `132DD629-A694-4D98-A0BB-B828676DD698`. The owned device was exactly Shutdown before and after every group.
- **Runner:** owned and bound to the source, 600 s overall limit, 60/90 s per-test caps, no retries, no raw attachments. Generated tests use no physical sensors, audio output, network or models. No physical device was used.

## Harness v3 repair

In harness v2, reaping ran only while the child was still alive. If a runner failure (such as a screenshot helper fault) occurred and the child then exited on its own, its status was lost (`exitCode` null). Successful v2 runs did record the child's exit code; only that failure path lost it. Harness v3, repaired by Opus and Fable, absorbs only optional screenshot faults (`TimeoutExpired`, `CalledProcessError` from the screenshot call), keeps every other guard fatal, and always waits for the child after the reap.

Four synthetic Python child fault cases were run. They used synthetic devices, synthetic screenshot faults and actual source-guard fixtures. They did not invoke the native app or any device, so they prove harness behavior only, not native or clinical behavior. In every case the child was reaped.

1. **v2, screenshot fault injected after the child exits:** runner status 1, child exit null. This reproduces the v2 lost-status gap.
2. **v3, screenshot fault injected after the child exits:** runner status 0, child exit 0.
3. **v3, screenshot fault injected while the child is still running:** runner status 0, child exit 0. The v3 runner still collected the exit.
4. **v3, device-list fault (fatal guard) while the child is still running:** runner status 1, child exit 1 as recorded. No OS signal return value is inferred from it.

"After the child exits" / "while still running" describe only when the fault was injected, not whether the runner waits for the child. All four matched their expected behavior. This harness change is why UNIT, UI2, REGRESSION and RELEASE were run fresh under v3.

## Verification by run group

Each group is a separate run. Their counts are not a whole-suite result and must not be added together.

| Group | Harness / inputs | Result | PNGs |
|---|---|---|---|
| UNIT | v3 / INPUTS-v3 | **PASS** 232 | 0 |
| UI (12 generated direct tests, normal and largest accessibility size) | v2 / INPUTS-v2, reused | **PASS** 12 | 119 |
| UI2 (14 existing mirror UI regressions) | v3 / INPUTS-v3 | **PASS** 14 | 78 |
| REGRESSION (7 research UI regressions) | v3 / INPUTS-v3 | **PASS** 7 | 64 |
| RELEASE (build and purpose strings) | v3 / INPUTS-v3 | Exit 0; no test count applies | 0 |

- **Every group:** exit code 0; all inputs unchanged; owned device Shutdown before and after.
- **UNIT, UI, UI2, REGRESSION safe proofs:** exact names match and all passed; 0 failed, skipped or expected failures.
- **v3 groups:** `childExitCollected` true, `captureFailures` empty, telemetry complete.
- **UI (v2):** exit code 0 was recorded. v2 has no separate `childExitCollected` flag and no optional capture telemetry field, so none is reported.
- **RELEASE:** the compiled Release Info.plist has a microphone purpose string and no camera purpose string. No physical-device validation was done.
- **Strict Swift lint, 8 affected files:** exit 0.
- **Original 68 Session and 11 Admission full-file prefixes:** preserved. Failed original sources and fixtures are preserved.
- **Final engineering/evidence review:** **CLEAR**, actual Fable 5.1, read-only; [review and bounded verdict](../../work/consumer-feedback-20261009/direct-two-try/fable-final-evidence-review-v1/REVIEW.md).

**Why reusing the 12-test UI result is bounded.** It ran at the same native source (SOURCE-v2) as the v3 groups, and the UI argv and environment are the same apart from output labels. It is cited only under the INPUTS-v2 digest, never under v3 and never pooled. It is not a v3 rerun; Fable recommended a v3 rerun to avoid a cross-digest note; root accepted bounded reuse, so this paragraph records that mapping.

**Historical v2 unit results** are duplicates of the same tests. They are not added to the 232.

**PNGs.** The three passing PNG groups retained 261 PNGs (119 + 78 + 64). Root checked all 261 hashes. Hash checks prove the files are intact, not that every pixel was reviewed.

## Historical failure: UI2 under harness v2 (preserved)

Under harness v2, all 14 safe UI2 tests passed (0 failed) and 78 PNGs were retained. The controlled run still **failed**: exit code null (not collected), `TimeoutExpired` in a helper. **Which helper timed out, and why, is unknown.** The fresh v3 result does not turn this into a pass. The rerun is justified by the changed harness, not by the earlier failure.

## Pixel review (partial)

Opus 5.5 (`claude-opus-5-5`) reviewed ten unaltered PNG crops from the UI (v2) set of 119: frames 013, 014, 016, 029, 048, 066, 067, 075, 112 and 114. It also read three sources: the player view, the generated host and the UI tests. Its verdict was **CLEAR**, with no blocking visual issue. No UI2 (78) or REGRESSION (64) PNG was reviewed.

- Normal and largest text show distinct earlier and latest replay labels, each with its own duration.
- Failed-save/retry and saved-note states are visible.
- The largest-text failed-replacement crop shows the earlier-take reassurance and Back.
- Restore text is black when enabled and grey when disabled at both sizes. That control belongs only to the generated fixture.

Nonblocking P2 notes; no product change was made for them:

- 0.35 s is displayed as "0.3 s" because of rounding.
- The label shifts sideways when the play icon becomes the wider stop icon.
- Some states are not in any reviewed crop: the failed-replacement title and delete button, Record another, and Next/Finish.

These are partial scroll crops from ten of the 261 PNGs. They do not establish an all-pixel review, fit, measured touch dimensions, VoiceOver, audibility, hardware, child, clinical or improvement behavior.

## Preserved findings

- **Canonical v1 run:** 232 units passed. UI: 7 passed, 3 failed. All 96 PNGs are retained.
  - Two fixture "Restore" button targets measured 13.5 pt, below the 44 pt minimum.
  - The combined accessibility-size journey timed out at 60 s. This is a failure, not a pass.
- **Old compact combined journey** (switch, stop, Delete, Close) passed in v1. That result is historical and is not pooled into later runs.
- **Scoped repair by Opus and Fable, in 2 Debug fixture/UI files only:**
  - A 44 pt frame and content shape inside the plain-style button label.
  - A conditional "closed files" producer line, shown only after dismissal.
  - The combined journey split into comparison→Close and delete-ready→Close, at normal and accessibility sizes, giving 12 tests.
  - The product retry binding and the core are byte-identical.
- **Reviews:** Fable 5.1's UI repair review (v1) was CLEAR, conditional on fresh checks. Fable's v3 runner review was CLEAR for bounded integration, with nonblocking notes (reap exception without receipt, `runnerSignalsSent` recorded before delivery, screenshot timeout not a hard wall-clock bound, periodic guards stop at 120 frames). Neither review approves execution results.

## Coverage limitation (P2, accepted)

The split keeps every individual old assertion, but **it does not keep every old combined event sequence.**

- Destructive retry after a two-take playback switch is no longer run as one journey.
- Retry after playback is covered only with one take, in the failed-start journey.
- Unchanged core unit tests cover two-take destructive retry and exact switch/stop ownership separately.
- The Close line must show 0 kept files and 2 playback starts. If it does not, that is a product finding. Do not widen waits or drop counts.

## Boundaries

- This guide made no source changes and no owner-browser requests.
- It makes no correctness, improvement, physical-device or clinical claim. It does not approve release.
- Final Fable engineering/evidence review is **CLEAR** for this checkpoint and roadmap-only publication; it does not establish the wider product evidence.
- The wider goal is still active. These items remain open:
  - lawfully usable, independent labels of the speech sounds actually produced
  - child calibration
  - qualified review
  - content, reference-audio and participant permissions and rights. Correct release purpose strings do not resolve these, and development authorization cannot supply legal consent or licenses.
  - release eligibility
- Clinical professional review is deferred by the user.
