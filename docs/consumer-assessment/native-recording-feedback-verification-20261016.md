# Per-take recording signal feedback

Saved practice takes now carry recording advice when the actual PCM16 evidence supports it. An all-zero take shows **No sound was saved in this try**, with a suggestion to make another try with the microphone uncovered. A take containing an exact positive or negative digital endpoint shows **Recording reached its volume limit**. Advice stays with that take's UUID as it becomes the earlier try; replacement and cleanup remove the corresponding note. Unknown formats and ordinary non-event samples produce no badge or implied endorsement.

These are recording observations, not pronunciation judgments. Endpoint samples do not by themselves establish audible distortion. The volume-limit suggestion uses the actual existing assessment: an acceptable take suggests recording a little farther away using the usual voice; a rejected take gets a neutral request for another recording. The existing latest quiet tip is suppressed only for the actual latest all-zero take with the same existing quiet-coaching value. Duration and unequal custom tips remain.

## Implementation boundary

The existing bounded AVAudioFile summary scan still computes duration and whole-clip RMS using its unchanged arithmetic, partial-read loop, finite-sample rejection and floor. That same loop optionally accumulates exact sample, zero and endpoint counts and widened peak magnitude. New evidence requires the actual saved mono 16 kHz signed/packed little-endian PCM16 format, the expected Float32 processing format, and an exact Int16 lattice roundtrip for every sample. An unproved mapping discards the entire new measurement; it does not replace the existing finite RMS path with a guess. Measurements require 1–64,000 samples.

`CaptureSummary` has an optional immutable measurement, defaulting to nil for existing callers. Quality thresholds, eligibility, history, recognizer and media ownership policies are unchanged. The Debug PCM reader shares only integer accumulation; its parser, Int64 RMS arithmetic, floor and result fields remain. Two existing internal injection initializers are available in Release so the actual player can be verified without a shipping fixture flag. Their bodies, visibility and default factories are unchanged. The change comprises seven production files and five test/support files.

## Actual verification

| Check | Observed result | Evidence boundary |
| --- | --- | --- |
| Fifteen new measurement/advice/lifecycle cases plus seventeen existing regressions | 32 passed, once per method; zero failures/skips | Debug app and test module; actual generated WAV scanning is included |
| Compact Release component journey | Passed once; 26.777 seconds | Real player/session with explicit generated dependencies |
| Accessibility XXXL Release component journey | Passed once; 105.983 seconds | Same production source; complete advice captured through measured scrolling |
| Ordinary Release compact repeat smoke | Passed once; 58.880 seconds | Shipping root, skip-only navigation; not a live recording-feedback test |

Actual WAV tests positively admitted zero, endpoint, near-endpoint, constant-level and final-frame PCM16 vectors. Float32 input retained its whole-tail RMS and received no invented integer evidence; nonfinite input and existing rate/channel/frame bounds were rejected. These are generated engineering fixtures, not participant recordings or a microphone test. Session checks cover exact earlier/latest bindings, third-try eviction, denied/failed replacement, reentrant Close, background/Next cleanup and unchanged guided participation.

Each current UI journey explicitly creates four generated takes: zero, endpoints, unknown evidence and non-event evidence. It checks exact IDs and labels, replacement, quiet-tip behavior, absence of unsupported badges, one requested silent-driver replay and zero automatic checks/history/camera actions. Positive Finish assertions require end acknowledgement, empty ownership and removal of the owned directory. The UI uses marker files and injected summaries; it does not substitute them for the actual WAV measurement tests.

Both component methods passed on the dedicated arm64 iPhone SE3/iOS26.5 simulator. Their command took 137.614 seconds and enclosing phase 150.736 seconds. The separate unit command/root took 7.365/21.022 seconds; ordinary Release took 66.235/79.849 seconds. All completed with Shutdown and no required signals, cleanup errors or remaining owned groups. Actual compiler arguments confirm Debug/-Onone/testability for units, and Release/-O/noDEBUG/no testability for both component and ordinary app/UI modules. The installed simulator SDK 27.0 compiled an iOS 17 deployment target; iOS 17 runtime was not tested. Existing signing/account settings were retained.

The UI successor changes only helpers. The unit result is reused through 114 byte-equal actual compiled inputs and 48 unchanged products; it is not a new unit run. Current component and ordinary Release builds bind 49 and 68 products. After component testing, the exact already-tested ordinary app was reinstalled without launching it, and the simulator returned to Shutdown. Restoration took 14.974 seconds and made no signing, account, sensor, model or upload action.

## Preserved failure and visual evidence

The original component run passed largest text but failed compact at 59.427 seconds while its full-swipe helper alternated above and below **Record another try**. It exhausted its 20-gesture limit rather than timing out. The compact case never reached its first replacement or Finish, so its cleanup remains unconfirmed. The initial largest-text pass also captured only partial volume-limit text. Those results and their 403-binding failure audit remain unchanged.

The corrected helper uses finite measured target-directed slow gutter drags, retains the 20-drag and 180-second case limits, and requires complete vertical coverage of the exact advice row. Tall notes use overlapping parts with the same take ID and stable height. Both original journey bodies, fixture/banner, production code and outer 420/600-second stage/phase bounds remain unchanged.

Root inspected all 12 current UI PNGs and all 10 geometry attachments, covering eight advice presentations. Compact notes are completely visible. Large zero notes are readable in one frame; the larger volume-limit notes are readable across overlapping frames, including the final **using your usual voice** phrase. This is scoped copy/layout evidence, not a full VoiceOver, keyboard or accessibility audit. Passing cleanup evidence consists of the actual source-bound Finish assertions and captured status, without a separately exported machine stdout receipt.

Inputs and official results are retained in `work/native-recording-feedback-20261016/execution-v1/` and the helper successor `execution-v2/`, with the complete shipping patch and before copies in the parent task. The [history-access checkpoint](native-history-access-verification-20261016.md) and its still-open largest-text Clear-confirmation defect are separate. A repair candidate is prepared; this feedback result does not close that defect.

No live microphone, camera preview, audible playback, new model inference, physical-device, target-sound correctness, clinical diagnosis or effectiveness is established here. The broader app goal remains active. Apple Speech authorization remains denied; earlier bundled-word recognition evidence remains separate from this recording-signal change.

## October 24 accessibility announcement continuation

The existing phase announcement now adds the review payload's own recording
observation when the view observes recording → review. It reuses the current
all-zero/volume-limit text rather than introducing an evidence rule. Unknown or
ordinary evidence announces readiness only. Returning to a kept take does not
repeat its advice. Checking, cancelling and cleanup-blocked word checks suppress
the review announcement and retain their existing dedicated announcements.

Nine actual pure XCTest methods pass: five existing advice regressions and four
new announcement cases covering zero, both rail-assessment details, missing or
ordinary evidence, independent consecutive inputs and return-to-review copy.
These ran in a standalone Mac harness with the test body unchanged; only the
app-module import was removed with a byte-restoration check. They are not iOS
session-lifecycle or VoiceOver integration tests. The full ordinary Release app
build also passed for arm64 and x86_64 simulator targets, including the changed
SwiftUI caller. The build retains one AppIntents metadata-extraction warning.

Root observed the finite verification finish normally, with no signals, cleanup
errors or remaining owned groups. Postchecks verified 290 source/generated
bindings. [Evidence and review](../../work/recording-advice-announcement-20261024/HANDOFF.md)
preserve the narrow patch, actual logs and independent review. No device was
launched or app installed for this continuation, and no model or recording ran.

SwiftUI can coalesce phase changes, and a fast word check may already be finished
when the phase callback runs. This change does not guarantee every completion is
spoken, exactly-once delivery or announcement ordering. Actual VoiceOver timing
and audibility remain unverified. Existing recording eligibility, visual advice,
media ownership, scores and pronunciation claims are unchanged.
