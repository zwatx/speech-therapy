# Direct-practice live demo plan

Status: **superseded delivery order, September 26, 2026**. The user selected
native iOS first, initially in the Mac's iPhone simulator, with physical-phone
testing afterward. Local-only model research proceeds in parallel; the user can
involve an SLP. The native implementation now provides 24 sound groups / 72
unreviewed demo words, local record/replay/retry/completion, and an opt-in Debug
camera experiment on supported phones. See the [native app instructions](../../apps/ios-learner/README.md),
[current model research](../model/current-multiphone-decision.md), and
[SLP handoff](../model/slp-handoff.md). Website delivery remains a later option.

The following is the original September 25 planning audit, retained as context.
Its web-first ordering is no longer the active implementation decision.

The requested demo is a no-account
experience: open a website or app and begin practicing. Web is the first delivery
surface because it gives a visitor a shareable link with no installation step.
An iOS download can follow after the practice flow works end to end. This demo
scope is distinct from the clinician-guided, consent-bound pilot described in
the phase gates.

## What the first demo should prove

A new visitor can open the site on a phone, choose a short practice, hear or
read a clear prompt, allow the microphone only when ready, record and replay a
word, get honest recording-quality guidance when necessary, advance through a
small session, and reach a satisfying finish. The flow should take under a
minute to understand and roughly three minutes to experience. It needs a
graceful path when microphone access is denied or unavailable.

One concrete presentation path is: open the URL on a clean phone browser ->
start a beginning-sound practice -> hear a human example -> record a word ->
replay it -> receive a quality-only retry if the capture is too short or quiet
-> complete the remaining cards -> see a clear session completion state.
The presenter should be able to run the same path twice without resetting a
database or relying on a prepared account.

## What exists today

- The native iOS learner already has a polished prompt, recording, local
  quality, retry, progress, and receipt flow. Its normal entry point requires
  clinician-issued enrollment and a current server assignment. Its Debug
  preview bypasses those dependencies for accessibility testing, but is not a
  distributable no-account experience.
- The clinician website has a navigable fictional preview and established
  styling, but no public browser-based practice flow. Its public root is a
  protected clinician page, and its preview assignment action only produces
  an unsaved summary.
- The shared foundation exercise has one bounded silent `/b/` prompt (`ball`).
  There is no reviewed public practice pack, recorded reference audio, or
  no-account session state.
- Frozen-encoder custom heads and a benchmark scorer are research artifacts.
  They have no validated produced-phone labels, child/SSD evaluation, or
  calibrated pronunciation decision. The current app intentionally gives no
  correctness or corrective feedback.
- JavaScript tests pass locally on this planning checkpoint. The clinician
  preview loaded and its assignment preview interaction worked. iOS simulator
  verification is currently blocked because Xcode's license has not been
  accepted on this machine.

## Build order

1. **Lock the demo promise and content.** Choose the first audience, one
   sound/skill, three to five prompts, the exact words shown on every screen,
   and what a completed session means. Get a speech-language pathologist to
   review any instruction presented as therapeutic technique. Keep demo copy
   explicit that recording quality is not pronunciation correctness.
2. **Build a separate public practice surface.** Add a small web app/route
   whose practice state is local to the browser. Do not route no-account
   visitors through clinician APIs or weaken the existing authorization
   boundary. Start practice from the landing screen in one tap; request the
   microphone only on the record action. Keep recordings in memory and clear
   them on reset, navigation, and session end. No identity, upload, analytics
   tied to voice, or server persistence is needed for the first demo.
3. **Make the core loop genuinely usable.** Add an owned or properly licensed
   reference recording, large prompt and cue, visible recording state,
   waveform or level affordance, stop/replay/redo controls, conservative
   duration/level checks, progress, and a completion screen. Define every
   transition and failure state, including permission denial, unsupported
   browser, interrupted capture, silence, and refresh.
4. **Polish for an audience.** Make the first screen explain the benefit in
   seconds, use a consistent warm visual language, responsive layouts,
   readable typography, clear audio controls, and lightweight motion that
   respects reduced-motion settings. No fake scores, streaks, or fabricated
   improvement claims. A visitor should always know what to do next.
5. **Verify the exact live path.** Test fresh-load and repeat-run behavior on
   current iPhone Safari and desktop Chrome, with microphone allowed and
   denied. Exercise keyboard and screen-reader navigation, slow/offline
   behavior, the full short session, and media cleanup. Rehearse on the same
   device and network used for the presentation and keep a short prerecorded
   walkthrough as a fallback for venue failures.
6. **Publish a controlled demo.** Use a dedicated demo hostname/environment
   with no clinical records or production credentials. Review public claims,
   privacy notice, and any child-directed implications before opening it to
   general traffic. Monitor uptime and errors without collecting recordings.
   Only after the web flow is solid, adapt the native app to an explicit
   no-account practice mode and distribute a test build.

## Model decision for the demo

The first direct-practice path can be excellent without judging pronunciation:
the real interaction is recording, replay, and capture coaching. If automatic
pronunciation judgment is required as the central demo claim, it becomes a
separate gated workstream: obtain approved target-specific labels, evaluate on
speaker-independent child/SSD data, calibrate uncertainty and abstention,
review copy and error cases with SLPs, and only then expose a bounded result.
The current `/R/` whole-clip rating head and automatic adult phone heads do not
meet that bar. A clearly labeled research presentation using public audio may
show technical progress, but must not be represented as the visitor's speech
assessment.

## Demo-ready acceptance check

- A visitor reaches the first prompt without an account, clinician, token, or
  setup instructions.
- A real microphone recording can be played back and retried; the UI never
  calls recording quality a pronunciation score.
- The complete session works on phone and desktop, including denied-mic and
  interruption paths, with no voice data sent to a server.
- The public page has no route into protected clinician data, and demo hosting
  uses no patient data.
- The presenter can complete the prepared live script twice on a clean device;
  a fallback walkthrough and a concise explanation of the model's current
  research status are ready.

## Decisions still open

- Whether the first demo must judge pronunciation, or whether guided practice
  and recording-quality feedback are sufficient.
- Primary age range and whether the initial practice should feel child-led or
  caregiver-guided.
- Whether the first deliverable is a shareable website alone or also an iOS
  test build. Web-first is the current planning default.
