# Explicit spoken-word practice — current checkpoint

The native direct and guided practice screens now offer an explicit **Hear word**
action beside the printed target. The caption identifies it as a synthetic voice;
word readings and accents can vary. Playback never starts on screen appearance,
word changes or recovery. This feature supplies a spoken prompt, not a reference
judgment about the learner's pronunciation.

The spoken-word runtime shares audio ownership with recording and recording
replay. Its serial worker owns the speech framework objects. Only an actual
matching start event enables the speaking state; matching finish/cancellation,
disposal and audio-session deactivation must complete before releasing ownership.
Stop, Close, backgrounding and explicit recovery retain that ordering. Recording,
replay and word checks stay unavailable while speech owns audio. A blocked cleanup
keeps the recording protected and joins the existing Close after explicit Retry.
The five/three-second timers bound queued delegate waits, not synchronous SDK
calls or destruction. They are not hard interruption guarantees.

The nine integrated files passed independent source and formatting-delta review.
A fresh Debug controlled suite passed **244 exact methods** before the current
`c564…` voice-selection-only correction, with zero failures,
skips or expected failures. This includes 21 new speech-runtime/session cases and
existing capture, playback, recognition-owner, file-ownership and recovery cases.
The host had no speech/model resources or actual sensor/framework media calls.
This fake-driver result does not verify actual SDK voice selection and is separate
from the actual voice and interface results.

The first optimized-app installed-voice case **failed**. Two synthetic word
operations produced two start and two natural-finish events, one stop invocation,
zero cancellation events, two disposal/deactivation returns and an empty hardware
lease. Its explicit cancellation assertions failed. The engine logged voice
catalog decoding/fallback errors and audio diagnostics. Cleanup worked in this
observation; audible synthesis and explicit cancellation are not established.
The original failed case will not be relabeled or replayed to obtain a pass.

One catalog-only observation then found 68 installed voices and five eligible
ordinary English (US) voices. Production selection now asks Apple for the English
(US) language voice and verifies eligibility, installed membership and exact
identifier resolution. It does not cycle through candidates or download voices.
A separately reviewed repetition of the fixed two-operation test selected
Samantha for both operations and **also failed** the same cancellation assertions:
two starts, two natural finishes, no cancellation, and successful disposal and
deactivation. This does not establish the cause of the earlier failure or audible
output. No further unchanged speech pair is scheduled.

Three generated UI runs remain failed. Private fixture corrections addressed
recording setup, diagnostic-footer overlap and missing-element diagnostics. The
third run reached normal Hear/Stop and recovered controls at both text sizes,
then failed its first accessibility audit: compact timed out after five minutes;
largest text reported unsupported Dynamic Type on the private “Generated test”
footer, confirmed by its element screenshot. These observations do not establish
a production-control accessibility failure or a completed guided Close.

A separate interaction-only scope omits accessibility audits and uses generated
speech fixtures. In **interactions-v1**, compact text passed in 73.666 seconds,
including all three fixtures and held-Stop pending Close/Retry. Largest text failed
in 127.090 seconds while revealing the disabled Check control in held-Stop; its
bottom remained clipped. This is not an all-six-fixture pass.

**Interactions-v2 failed both methods**: compact at Record Another and largest
text at Check. Tiny edge adjustments left the controls incompletely revealed.
**Interactions-v3 also failed both methods**, at compact Close and largest Hear.
Spotlight was observed; the app backgrounded and the take cleared. That is not
evidence of a successful Close, and a unique gesture cause remains unknown.
All original failures remain failed.

**Interactions-v4 passed both methods once.** Its reviewed three-line test change moves
the scroll gesture endpoints toward the center while retaining the middle-fit
travel calculation and existing assertions. The normal-text method passed in
61.900 seconds and largest text in 130.044 seconds, with zero failures, skips,
expected failures or official runtime warnings. All six generated scenarios
completed, including protected pending Close, explicit Retry joining that Close,
exact operation counts and empty audio ownership before the next scenario.
Build, test and result collection closed normally. Root inspected eight saved
screenshots; independent actual-result review cleared this bounded checkpoint.
Raw SDK diagnostics remain preserved. The large private diagnostic footer and
final fixture evidence remain oversized; no accessibility audits were performed.
This scope cannot establish audible speech, full accessibility, physical
microphone capture or clinical/produced-phone correctness.

Apple's installed English **recognition** assets are ready; this and on-device
recognition capability do not establish text-to-speech readiness. The prior legacy Apple Speech
authorization denial remains unresolved; bundled local Whisper remains the working
word-recognition route. The current ordinary Release built successfully for both
simulator architectures and was installed over the existing app. All 26 installed
files match the verified build, including the 19 bundled recognition resources.
The app was not launched by this installation check, and app-data preservation
was intended but not measured. The simulator returned to Shutdown.
No signing/account settings changed and no recordings were
uploaded. Physical capture, audible-output quality, produced-sound correction and
clinical diagnosis remain separate unqualified claims.

A separate, single-operation speech-engine diagnostic **passed**: Apple's installed
Samantha voice produced 7,678 finite samples, including 7,384 nonzero samples,
within the fixed observation window. All admitted callbacks published before the
checkpoint. The official result retains one priority-inversion runtime warning;
it is not a warning-free performance result. The diagnostic used buffer output,
not the production playback path, and kept its framework objects alive until
process shutdown. It establishes neither complete synthesis nor audible playback.
Both saved host checks show the Mac muted; no host settings were changed.
The earlier cancellation failures remain failed. Independent review recommends
one distinct production-path timing trace before considering a product change.

That single timing observation also completed. The instrumented speech call
returned in 0.148375 milliseconds; Stop returned true in 0.027 milliseconds and
preceded the observed natural-finish callback by 18.786292 milliseconds. Apple
reported finished rather than cancelled, then the runtime disposed, deactivated
and released its exact audio lease. This observation supports neither a blocking
speech call nor a finish-callback-before-Stop explanation. It does not expose SDK
internal completion timing or an application-controlled defect. The run retains
one priority-inversion warning and includes instrumentation overhead. Independent
review cleared the bounded trace; no further speech diagnostic matrix is scheduled.
The older cancellation qualification remains failed.

The timing run's host audio samples were unmuted at volume 50; the earlier PCM
samples were muted at volume 38. These are separate dated observations, and no
agent setting change is claimed. After verification returned the simulator to
Shutdown, a separate human handoff opened the ordinary app in Xcode's **Device
Hub**, selected **Start practice**, and visibly reached **ball → Hear word**.
Hear, Record and Show mirror were left for the user; no automatic playback or
sensor activation was requested. The simulator is now open for that handoff.

Evidence and review lineage are retained under
`work/spoken-word-20261017/`: INTEGRATION, INTEGRATED-SOURCE-REVIEW,
units-v1/ACTUAL-RESULT-ADMISSION and ACTUAL-RESULT-REVIEW,
actual-v2 and actual-v3/ACTUAL-FAILURE-ADMISSION, catalog-v1's catalog admission,
voice-selection-v2's source review, ui-v1 through ui-v3's original results, and
interactions-v1 through interactions-v4's separate reviews and saved metadata.
`ordinary-v1/BUILD-ADMISSION.json` and `INSTALLED-OBSERVATION.json` retain the actual
compiler/product checks and dated installed-file comparison. The whole-app goal
remains unfinished. The later user report and view-only UI checkpoint below
update the handoff without promoting earlier failed results.
`pcm-v3/ACTUAL-RESULT-ADMISSION.json`, `ACTUAL-RESULT-REVIEW.md` and `NEXT-STEP.md`
retain the bounded speech-sample result, its warning and the next diagnostic scope.
`timing-v1/ACTUAL-RESULT-ADMISSION.json` and `ACTUAL-RESULT-REVIEW.md` retain the
single timing observation. `ordinary-v1/POST-TIMING-INSTALLED-OBSERVATION.json`
records a fresh match of all 26 ordinary installed files before the human handoff.


## User-observed prompt and stable practice layout

The user confirmed “Yea i heard it” for one ordinary-app Hear word prompt, then
reported disliking its surrounding UI and movement. Their 2.833-second video has
no audio stream. This report establishes one human-observed audible prompt, not
general voice quality, cancellation, physical capture or pronunciation accuracy.

The view-only refinement replaces the wide Hear control with a compact outlined
speaker button. Hear, Stop and Stopping titles share their measured space. At the
ready screen, the recording instruction and normal spoken-word statuses share a
measured region, preventing their conditional insertion/removal from moving the
primary controls. Long recovery messages can still expand, Retry remains available,
and the full stopping explanation remains available to accessibility. Audio,
session, recording, mirror and recognition behavior are unchanged.

Two targeted generated UI checks passed once on the dedicated iPhone SE simulator:
normal text in 16.398 seconds and largest accessibility text in 30.914 seconds.
At normal text size, the word, Hear/Stop and Record frames had **zero measured
movement** across ready, preparing, speaking, stopping and idle. The largest-text
check establishes selected-control readability and interaction with scrolling;
it does not establish simultaneous visibility or an invariant viewport. Root
inspected six saved screenshots. No accessibility audit, actual speech or sensor
capture ran in these checks. Independent source and actual-result reviews cleared
this bounded regression check; earlier failed checkpoints remain failed.

A fresh ordinary Release built successfully and was installed. All 26 installed
files matched the verified product in the dated comparison. Verification returned
the simulator to Shutdown. A later separate human handoff booted it in Device Hub,
opened ordinary Cadence, selected Start practice and visually confirmed the updated
ball screen with the compact Hear button and Record control. Mirror remains below
with native scrolling. The app is left open for the user. The agent did not press
Hear, Record or Show mirror during this handoff, change sound or account settings,
or upload recordings. No new listening result is claimed for the view-only update.

Current evidence: `work/spoken-word-20261017/ui-stability-v1/PLAYER.patch`,
`DESIGN-HANDOFF.md`, `SOURCE-REVIEW.md`, `check-v1/BUILD-ADMISSION.json`,
`check-v1/ACTUAL-RESULT-ADMISSION.json`, `check-v1/ACTUAL-RESULT-REVIEW.md`,
`ordinary-v1/BUILD-ADMISSION.json`, `ordinary-v1/INSTALLED-OBSERVATION.json` and
`HUMAN-HANDOFF.json`. This completes the requested layout refinement, not the
whole app roadmap or clinical qualification.
