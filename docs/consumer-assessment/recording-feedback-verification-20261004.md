# Recording feedback app — October 4, 2026

The local app now supports recording, explicit whole-word checking, fresh tries, two-take replay/comparison and a separate optional local mouth outline. Start with `python3 scripts/consumer-app.py` and open `http://127.0.0.1:8782/`. The broader product goal remains active. The native simulator extension is reviewed, and the browser guided13-word first-round/practice/fresh-recheck extension is documented in [guided verification](guided-word-check-verification-20261004.md). Original recording verification below remains bound to its preserved sources.

## Observed checks

| Evidence | Observed scope |
| --- | --- |
| Backend | 35 focused checks, 19 independent rejection checks; narrow invalid-prompt correction adds two actual HTTP regressions, independently passed. |
| Actual speech processing | Eight declared HTTP requests all terminal/passed: licensed banana match; identical banana with door prompt mismatch; treasure/ZH whole-word match with target unsupported; generated nonspeech; silence; signed rails; short audio; concatenated two words. No injected model outcomes or research head. |
| Saved result audit | Independent reconstruction verifies every request/audio/prompt/response/source binding, seven valid measurement rows and unavailable short capture; eight distinct diagnostics confirm normal completion/cleanup. |
| Frontend | 52 independent actual-source controlled checks, including the eight saved real responses, every core pin/claim mutation, contradictory RMS, stale requests/permissions, byte wiping, third-take replacement, cleanup latch and visual races. These are controlled seams, not hardware/browser evidence. |
| Browser practice | Actual app, worklet and resampling with generated 48 kHz tone: four-second mono16 kHz PCM16/64,000 frames/128,044-byte WAV. Explicit matched/mismatched/uncertain **unit** results, A/B playback state, third replacement, late microphone/camera cancellation, stale response after word change and explicit cleanup observed. Zero speech-model calls in this helper. |
| Actual local face SDK | Official pinned MediaPipe assets/model actually loaded in browser on permitted prerecorded portrait/generated canvas: 40 outline segments for one face; no outline for checkerboard or two portraits; stop/restart and word-change stop observed. One denied SDK telemetry attempt observed on close. No hardware or child-face accuracy claim. |
| Visual source | 17 authored lifecycle and 14 independent frame/network checks passed. Source/privacy review cleared before actual SDK execution. Published SDK includes telemetry; guards and restrictive CSP deny external connections. |
| Layout/accessibility | Actual default desktop1280×900 and phone375×667 screenshots: no horizontal overflow; Record bottom493.7px on phone. Opus5.5 pixel review cleared layout, found hidden fallback naming bug; markup corrected and actual DOM now has an unnamed figure with correctly named loaded image. |

Recognition describes what the model reported. No target-phone correctness, diagnosis, child accuracy, improvement, physical capture/storage, or release eligibility is established. All eleven feedback claim flags remain false. The face outline is a visible-position aid, not a movement correction or articulation assessment. Licensed test speakers' ages are unknown; request age9 is a harness parameter, not their factual age.

## Preserved failures and limits

The first verifier failed before any HTTP or model call because its function name shadowed an import; original script/failure retained, then corrected. The first interface rejected valid replies because it expected only three core pins; actual API repeats six. Failure DOM and exact Opus source retained before correction. Independent review exposed silence/match contradictions; genuine failing results and prior source retained before fixes. A contradictory prompt originally closed its HTTP connection; exact pre-fix source and actual red regression remain, followed by bounded400 correction.

Two generated-helper page reloads failed to load app.js; direct guarded route was200 and a new status-only diagnostic helper load succeeded. Cause remains unknown. The actual consumer app subsequently loaded on8784 and the replaced8782 server. Do not represent those successful loads as proof of the helper failure's cause.

Creating another in-app browser tab left the practice document's visibility state **visible**. Therefore actual hidden-page cleanup was not exercised. The independent controlled-source tests cover that handler, and explicit browser stops/late cancellation were observed. The helper independently cleans up on pagehide, so page close alone cannot prove app-owned cleanup. No hardware sensors, real patient, guardian authority, qualified review or intended-child validation was fabricated.

## Bindings and preservation

Evidence root: `work/consumer-feedback-20261004/`. Actual model run binds backend wrapper `58e4a632…3434`; exact source copies remain in `actual-feedback-source/`. The later two-line transport fix binds wrapper `d05830fe…2b18` and did not rerun acoustics or alter frozen models/policy. The 52-check UI receipt binds app.js `f1d5dbb0…ef670`; markup-only accessibility addendum binds HTML `68223cc5…16eda8`. Browser cases bind exact earlier source copies in `browser-source/`; later RMS validation/copy/markup changes are independently reviewed and default layouts reloaded.

Review receipts: `backend-review/REVIEW_RECEIPT.json`, `actual-feedback-review/REVIEW_RECEIPT.json`, `backend-refusal-fix/independent-review.json`, `visual-review/REVIEW_RECEIPT.json`, `ui-review/REVIEW_RECEIPT.json`, `ui-review/accessibility-addendum.json`. Original consumer delivery copies, Opus implementation and pre-review UI copies preserve earlier source bindings. No original benchmark, reserved-study input, failed mobile private stage or historical snapshot was changed.
