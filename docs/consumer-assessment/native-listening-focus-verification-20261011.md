# Native direct practice: intended-sound listening cue — verification guide

Date: 2026-10-11 · Status: **checkpoint closed within generated simulator scope; independent Astra engineering/evidence review CLEAR**

## Scope and behavior

The ordinary native direct-practice review screen now gives neutral guidance for listening to the learner's own usable kept recording. One take reads, for example, `Play your try. Listen for /b/ at the start of “ball”.` With two kept takes it starts `Play the earlier try, then the latest.` before naming the same selected target and printed word.

The cue binds only the intended sound symbol, selected word position and current printed word. Positions are “at the start,” “in the middle,” and “at the end.” Repeated targets and consonant clusters do not cause it to choose or describe a particular occurrence. The one/two-take wording follows the currently kept takes.

The cue is static text in the review state, identified as `cadence.listening-focus`. It requires a latest kept take and usable replay: cleanup must not be blocked or retrying, and playback must not be stopping. It disappears during recording, when advancing to a word without a kept take, and after completion. Displaying it does not record, start playback, add its own announcement, or choose between takes. Replay remains an explicit learner action.

This is intended-sound self-listening guidance. It does not state what the learner produced, report a phonetic error, score pronunciation, diagnose, rank takes, or claim improvement. Recording-quality advice remains separate and concerns the latest successful capture.

Sources: [pure cue helper](../../apps/ios-learner/Sources/DirectPractice/DirectPracticeListeningFocus.swift), [review view](../../apps/ios-learner/Sources/DirectPractice/DirectPracticePlayerView.swift), [pure helper tests](../../apps/ios-learner/Tests/DirectPracticeListeningFocusTests.swift), and [generated UI journeys](../../apps/ios-learner/UITests/DirectTryUITests.swift).

## Frozen inputs and bounded verification

- Native [SOURCE-v2.json](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/SOURCE-v2.json): 172 rows, 161 Swift files in the guarded inventory, rowDigest `074dd968be28baedaf384f50344b28b03292331a9183328871cf602e72fad41e`.
- [INPUTS-v3.json](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/INPUTS-v3.json): 271 rows, rowDigest `eacc6a284a411f73b147b5593bba250a7da3d91d2ffd99803dd0b99c761659ca`. It binds the 172 native source rows, 96 reserved rows and three harness rows to this source snapshot.
- Dedicated owned simulator: `132DD629-A694-4D98-A0BB-B828676DD698`, Cadence Sound Compact Verification, runtime `com.apple.CoreSimulator.SimRuntime.iOS-26-5`. All six completed groups below have exact Shutdown receipts before and after.
- The [source-bound runner](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/run_checks-v3.py) runs groups serially with a 600-second overall limit, 60/90-second test allowances, no retries, and at most 120 direct frames. Safe result exports exclude raw attachments and OS logs. Generated hosts use inert sensors and generated files rather than physical capture, audible output, network or models.

Each row below is a separate controlled run. Counts are not a whole-suite result and must not be pooled. All results below bind the same current input digest.

| Group | Inputs | Observed result | Retained PNGs |
| --- | --- | --- | ---: |
| UNIT-v3 | INPUTS-v3 / SOURCE-v2 | **PASS: 236**; exact selected names; 0 failed, skipped or expected failures | 0 |
| UI-v3: 12 baseline direct-practice cases | INPUTS-v3 / SOURCE-v2 | **PASS: 12**; exact selected names; 0 failed, skipped or expected failures | 120 |
| FOCUS-v3: four listening-cue cases | INPUTS-v3 / SOURCE-v2 | **PASS: 4**; exact selected names; 0 failed, skipped or expected failures | 40 |
| UI2-v3: 14 mirror UI regressions | INPUTS-v3 / SOURCE-v2 | **PASS: 14**; exact selected names; 0 failed, skipped or expected failures | 79 |
| REGRESSION-v3: seven research UI regressions | INPUTS-v3 / SOURCE-v2 | **PASS: 7**; exact selected names; 0 failed, skipped or expected failures | 63 |
| RELEASE-v3 | INPUTS-v3 / SOURCE-v2 | **Build exit 0**; microphone purpose present, camera purpose absent; no test count applies | 0 |

For every completed group, the exact child exit was collected as 0, runner-failure fields are null and teardown-failure arrays empty, all 271 input rows were unchanged, and the owned device was Shutdown at closure. Capture failures are empty and telemetry complete. Root verified all 302 passing-group PNG hashes (120 baseline UI, 40 FOCUS, 79 mirror and 63 research); this establishes retained-file integrity, not an all-pixel review.

Evidence: [UNIT safe proof](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UNIT-v3-SAFE-PROOF.json), [UNIT exit](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UNIT-v3-EXIT.json), [UI safe proof](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UI-v3-SAFE-PROOF.json), [UI exit](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UI-v3-EXIT.json), [FOCUS safe proof](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/FOCUS-v3-SAFE-PROOF.json), and [FOCUS exit](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/FOCUS-v3-EXIT.json).

## Coverage and scoped helper repair

Four pure-helper test methods cover the actual 2,398 library entries, representative positions, current one/two-take wording, repeated target phones and beginning clusters. Their checks bind each entry's selected symbol, position and word; they do not validate sounds actually produced by a speaker.

Four generated FOCUS journeys cover compact and largest accessibility text at one and two takes, exact ball-to-boat word rebinding, disappearance during recording/word transition/completion, a complete cue viewport below the generated banner, and zero playback starts from showing the cue. The 12 baseline cases remain a disjoint group; all 16 direct UI names are selected across UI and FOCUS without changing their assertions or event sequences.

The original 366-line DirectTry UI prefix was exact at SOURCE-v1. **That whole-prefix claim no longer applies at SOURCE-v2.** The intentional later change is confined to `scrollTo`: viewport, generated banner bottom and window bounds are cached within one invocation; target frame and `isHittable` remain fresh for each drag. The 24-drag cap, travel rules, assertions, test names and event sequences are unchanged. It is not a cross-action geometry cache.

[INTEGRATION-v2.json](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/INTEGRATION-v2.json) records that only `DirectTryUITests.swift` changed among native source rows from SOURCE-v1, with no app-source, core, library, store or profile change from that snapshot. The three harness rows were versioned separately. The original cue integration passed strict Swift lint on its four affected files; the later changed UI helper also passed strict lint with exit 0. These are recorded root checks, not checks performed while drafting this guide.

## Historical failures retained

Fresh v3 success does not turn either earlier controlled run into a pass.

- **UI-v1, combined 16-case selection:** failed at the aggregate 600-second budget, observed at `600.1697827920143` seconds. The runner sent SIGINT and collected child exit 75. Thirteen cases passed; the largest-text Delete/Close case was canceled and represented as Failed in the safe tree; two planned cases did not run. Exact-name coverage is false. All four new cue cases individually passed, but the controlled combined run failed. Its 120 PNGs, failure receipt, exact input checks and Shutdown closure are retained.
- **UI-v2, 12 baseline cases:** failed at the aggregate budget, observed at `600.0864152910071` seconds. The runner sent SIGINT and collected child exit 73. Ten cases passed and two were recorded Failed: largest-text Next/Finish reached the 60-second allowance, and the last largest-text comparison/Close case was canceled. All 12 names are present, but `allPassed` is false. Its 120 PNGs, failure receipt, exact input checks and Shutdown closure are retained.

Those runs bind different inputs: UI-v1 digest `6a02bb1b5c8c77b707e25249a79c8d997840f62cf7e6b35d7dc680e3377acc77`; UI-v2 digest `feb5b49fca3244cdb6119cb956afbea463375301d4dcb1940ecca4094179c568`. Neither is reused as current SOURCE-v2/INPUTS-v3 success. Group separation and the scoped helper repair led to fresh v3 runs while retaining the existing caps and assertions.

Preserved evidence: [UI-v1 safe proof](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UI-v1-SAFE-PROOF.json), [UI-v1 exit](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UI-v1-EXIT.json), [UI-v2 safe proof](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UI-v2-SAFE-PROOF.json), and [UI-v2 exit](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/UI-v2-EXIT.json).

## Pixel review: six partial crops

Actual native GPT-6 Astra reviewed only six exact unaltered FOCUS-v3 crops, with a **CLEAR** verdict within that scope. Opus/Fable subscription quota was unavailable; Astra was the disclosed fallback. [ASTRA_PIXEL_REVIEW-v1.md](../../work/consumer-feedback-20261009/native-direct-listening-cue-20261011/ASTRA_PIXEL_REVIEW-v1.md) records these limits:

- Crops 008 and 015 show complete compact cue paragraphs, including one-take boat and two-take ball bindings.
- Crop 033 shows a complete largest-text single-take ball paragraph, without visible horizontal clipping or overlap.
- Crop 021 cuts off the cue; crop 026 shows a partial recording-tip/Finish region; crop 029 is the home screen.

There is no complete reviewed largest-text two-take paragraph or largest-text boat cue. The six crops do not establish every hidden state or all-pixel coverage. The fresh generated UI assertions and the partial visual review are separate evidence. This review establishes no physical touch measurement, contrast audit, VoiceOver behavior, audibility, hardware, child accuracy, or clinical benefit.

## Separate ASR feasibility and remaining limits

Separate asset/setup and file-lifecycle receipts are not evidence for this listening-cue checkpoint. The exact on-device module has separately completed one install request and reported installed; no speech-file inference or ordinary provider integration has run. Asset readiness does not establish cancellation/drain ownership, useful recognition, or production safety.

This guide records generated engineering evidence only. Physical-device validation, lawful independent labels for produced speech sounds, child calibration, qualified review, meaningful-change evidence and release eligibility remain outside these checks. Clinical professional review remains deferred by the user. Independent native GPT-6 Astra engineering/evidence review is CLEAR for this checkpoint and its roadmap-only publication. The broader goal remains active.
