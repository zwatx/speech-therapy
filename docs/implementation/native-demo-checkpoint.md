# Cadence native demo delivery record

September 26, 2026. This record replaces the earlier in-progress checkpoint.
The accepted first delivery is native iOS in the Mac's iPhone simulator. Website
delivery remains a later option; no public deployment is part of this delivery.

## September 26 redesign addendum

The native interface now follows the requested black/white direction, drawing
from The Lab's restrained rows and CS Club's serif display typography. Flat
sound rows and thin rules replace cards; the purple palette, all-caps labels,
eyebrows, status icons, progress capsules, and completion chips are removed.
Light and dark appearances use the same hierarchy. The optional Camera lab and
app icon are monochrome as well. Session, microphone, replay, cleanup, library,
and pronunciation behavior did not change.

The six direct-practice UI tests pass on iPhone SE / iOS 26.2 in
`/tmp/cadence-monochrome-ui-3.xcresult`, including full accessibility audits,
real recording/replay/retry/completion, microphone denial, background cleanup,
largest Dynamic Type, and sound selection. The home/prompt test also passes
with full accessibility audits in dark appearance:
`/tmp/cadence-monochrome-dark.xcresult`. An unsigned physical-iOS Debug build
passes (`/tmp/cadence-monochrome-device.log`), and strict formatting passes on
the four changed Swift view/style files. Physical camera behavior was not
tested. The unit suite and Release build below are earlier delivery evidence,
not new runs for this visual-only pass.

Actual screenshots in `/tmp/cadence-monochrome-preview/` include `home.png`,
`prompt.png`, `complete.png`, `dark-home.png`, and `installed-home.png`. Both
appearances were visually inspected; the orchestrator independently reviewed
the normal-size home, prompt, completion, and source with no blocking finding.
The revised Debug app is installed and launched at standard text size on the
iPhone 17 Pro / iOS 26.5 simulator. The remaining sections retain the earlier
delivery's behavior and verification record; they do not mark the separately
requested continuing model-training work complete.

## Delivered behavior

Cadence opens directly to a sound library. Start practice or choose a sound,
read the illustrated word, record, replay, retry, and continue through three
words to completion. It needs no account, enrollment, clinician, assignment,
network service, or model inference. Younger children can practice with a
grown-up; the About sheet explains this without adding onboarding.

The library has 24 English consonant groups and 72 prompts. It is explicitly
unreviewed demo vocabulary, not an age-specific treatment sequence. The
[SLP worksheet](../model/practice-content-review.md) contains every implemented
prompt with a pending review status. No reviewed reference-audio pack is
available. Recording tips concern duration and volume; completion acknowledges
participation. There is no pronunciation score or correctness claim.

Audio uses real AVAudioRecorder/AVAudioPlayer, mono 16 kHz WAV, capped at four
seconds. Temporary recordings are removed on retry, advance, exit, interruption,
and backgrounding. Startup removes stale clips; cleanup failures prevent further
recording. Generation checks reject stale permission, recorder, and replay
callbacks. The capture reader consumes partial WAV reads before calculating
whole-clip duration and power. The audio session permits output while recording
so it does not deliberately suppress spoken accessibility feedback.

An optional Debug Camera lab uses ARKit face tracking on supported phones. It
shows four mouth/jaw expression measurements after camera opt-in and saves no
images, measurements, or audio. It is absent in the simulator. It cannot access
Face ID enrollment data and supplies no pronunciation judgment. See the
[camera feasibility note](../model/truedepth-feasibility.md).

## Requirement-by-requirement verification

| Requirement | Observed evidence |
| --- | --- |
| Immediate entry, prompt, sound selection | Six direct-practice UI tests pass on both iPhone SE / iOS 26.2 and iPhone 17 Pro / iOS 26.5, including choosing SH and seeing `ship`. |
| Real recording, replay, retry, progress, completion, restart | Actual system permission and AVAudioRecorder/AVAudioPlayer path passes on both devices. Tests wait for replay completion, assert no playback error, retry and complete all three words. No injected waveform is used in these UI tests. |
| Microphone denial | Tests reset real simulator microphone authorization, deny the system prompt, reach Settings/retry recovery, and close practice. |
| Interruption and cleanup | Session tests cover interruption and stale callbacks, permission/background races, replay errors, actual temporary-file removal, and terminal cleanup failure. A UI test backgrounds a real recording and verifies it is unavailable after return. Both app containers contain zero practice recordings after final tests. |
| Accessible layouts | Full platform accessibility audits pass on home, prompt, and completion. Largest Dynamic Type reaches Start and Record; denial recovery is scroll-reachable on the small phone. Actual screenshots were independently visually inspected. This is not a manual VoiceOver or child usability study. |
| Native foundations and camera lifecycle | All 80 native unit tests pass in the final integrated run, including the new session, library, and camera tests and the WAV partial-read regression. |
| Build configurations | Debug simulator tests, unsigned physical-iOS Debug build, and Release simulator build pass after the last source change. Strict Swift formatting passes on changed Swift files. |
| Research reproducibility | 320 actual local inferences per run; fresh-process replay matches all probability vectors, transformed-waveform hashes, and summaries exactly; zero failures. Seven new numerical/boundary tests and four reused waveform-transform tests passed. |
| SLP handoff | Exact 72-row worksheet and links to the existing 40-clip annotation protocol, signoff worksheet, and intake guide independently checked against current sources. |
| Authorization boundaries | Default app entry constructs no enrollment model. Direct-practice code uses no network client, credentials, or scoring model. The existing linked-device flow remains behind Debug launch arguments. Server/web authorization code was not changed. |

Local evidence (temporary result bundles on the development Mac):

- `/tmp/cadence-native-delivery.xcresult`: **86/86 pass**, 80 unit + 6 direct UI,
  iPhone 17 Pro / iOS 26.5, after the final audio-category correction.
- `/tmp/cadence-native-compact-final.xcresult`: **6/6 direct UI pass**, iPhone SE /
  iOS 26.2. `/tmp/cadence-native-compact-audio.xcresult`: the actual recording,
  replay, retry, completion, restart test passes again after that correction.
- `/tmp/cadence-final-cleanup-evidence.json`: both app-container identities and
  zero remaining `cadence-attempt-*` files.
- `/tmp/cadence-final-physical-debug-build.log` and
  `/tmp/cadence-final-simulator-release-build.log`: successful final builds.
- `/tmp/cadence-compact-final-attachments`: actual compact-device screenshots.

The six original linked-device UI tests still fail. A separate project copied
all 24 original Swift source/test files byte-for-byte from the pre-change
snapshot and reproduced all six failures on the same iPhone 17 Pro / iOS 26.5.
Five audits report pre-existing contrast, Dynamic Type, and hit-area issues;
the unlink test expects a missing `Keep device linked` button. Evidence:
`/tmp/CadenceBaselineComparison-i4jbt7m5/LegacyAccessibility.xcresult`.
Their assertions were not relaxed to make the demo pass. No web/JavaScript or
contract source changed, so those suites were not rerun for this native delivery.

## Model and content handoff

The [capture-sensitivity report](../model/r-capture-sensitivity-report.md)
documents the pinned sample, reproducible command, hashes, probability movement,
subgroups, and runtime. Both existing whole-clip rating heads changed their
highest-probability class on 3/40 clips under each tested noise condition. This
is a sensitivity diagnostic, not an accuracy estimate or a model improvement.
These training-side clips cover ages 6–37, include 17 clips aged 6–12, and include
none aged 2–5. No new qualified labels or held-out child/SSD evaluation exist.

The [SLP handoff](../model/slp-handoff.md) separates content review from qualified
sound annotation. No reviewers were contacted, no child recordings collected,
and no packs sent. All work used existing local resources, with no paid compute.
The Dell was reachable but no work or data needed to move there.

## Review and limits

Independent agents reviewed the session/recording engine, UI integration,
camera lifecycle, model outputs, and SLP worksheet. They caught the invalid
record-only ducking option, partial WAV reads, and spoken-accessibility audio
category issue; those changes were applied and verified. No remaining blocking
finding was reported. A separate unchanged-baseline run established the legacy
UI failures.

Physical phone camera behavior, microphone/speaker routing, headset behavior,
and manual VoiceOver listening remain device follow-up checks. Simulator tests
prove the real recording/replay pipeline executes, not that a human listener
judged captured speech or that pronunciation assessment is validated. The full
ages 2–12 audience still needs SLP content review and usability evaluation.

The simulator backend and actual screenshots work. Automated control of Xcode
27's Device Hub window times out, so its window visibility is not claimed.
Open **Xcode → Open Developer Tool → Device Hub** and select the running iPhone
17 Pro to use the installed demo. Standard run instructions are in the
[native README](../../apps/ios-learner/README.md).

No repository history existed at the start; all project content remains
untracked. Existing work was preserved. No files were staged, committed, or
published. Scoped changes to original native files were reviewed against
`/tmp/cadence-ios-baseline`.
