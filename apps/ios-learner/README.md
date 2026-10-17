# iOS learner

SwiftUI speech-practice app for children ages 6–12. The app currently displays
Cadence; the Xcode project, scheme, and bundle identifiers retain that name.
See the [root README](../../README.md) for product scope and the
[consumer plan](../../.plans/2026-10-02_consumer_speech_app_direction.html)
for the intended assessment and practice experience.

## Run locally

From the repository root, with Node.js, pnpm, Xcode, Swift, and XcodeGen installed:

```sh
pnpm install
pnpm ios:generate
open apps/ios-learner/CadenceLearner.xcodeproj
```

Select the `CadenceLearner` scheme and an installed iPhone simulator. The project
uses Swift 6 and targets iOS 17.0 or later. Simulator builds need no signing team.
A supported physical TrueDepth device is required for the live face preview.

Compiled Whisper model directories are excluded from Git. Native word recognition
requires the exact files and hashes in the
[bundled-resource manifest](WhisperResources/RESOURCE-MANIFEST-v1.json).
The presentation prototype runs without a model server, download, account, or
network connection.

## Current presentation prototype

Ordinary Debug and Release launch opens a home with **Today**, **Sounds**, and
**Progress** tabs. Sound checks and practice open as sessions over that home;
results return to Today. Sounds browses the bundled library, and Progress shows
activity from the current in-memory round.

The presentation scenario checks **boat**, **rabbit**, and **sun**, selects
**rain** and **ring** for practice, then asks for a fresh **rabbit** recheck.
Recording, replay, spoken examples, and cleanup use the native media session.
**Pronunciation outcomes are authored in `CACScript`, rather than inferred from
audio or a model.** The scenario demonstrates the experience; it does not measure
sound accuracy, improvement, or a diagnosis. Results are not saved to practice
history or clinical records.

Starting a sound check opens the first word and requests the camera preview.
The microphone starts only after Record. On supported devices, ARKit/TrueDepth
shows a face wireframe and relative jaw/lip movement. Hide stops the camera and
continues audio-only practice. Camera images, meshes, and movement readings are
transient on-device data; the app does not save or upload them. Facial movement
does not change the authored result or estimate tongue position.

The prototype allows nonzero quiet recordings without a low-volume warning.
All-zero audio and other capture failures remain ineligible. Retaking clears the
old result, and moving to another word waits for media cleanup. Returning from
the background never restarts capture automatically.

The [presentation routine](../../docs/consumer-assessment/cac-presentation-routine-20261025.md)
records the scenario and its verification limits. Its earlier welcome/recap
navigation descriptions predate the current tabbed home.

## Retained practice routes

These routes are reached through explicit Debug launch arguments, rather than
ordinary launch. Add arguments under the scheme's **Run → Arguments** settings.
Release builds always open the presentation prototype.

| Argument | Destination | Availability |
| --- | --- | --- |
| `-CadenceLegacyHome` | Practice library, search, history, and local five-word review | Debug |
| `-CadenceClinicalMode` | Caregiver enrollment and clinician-assigned practice | Debug |
| `-CadenceFeedbackMode` | Service-based free recording feedback | Debug simulator |
| `-CadenceGuidedWordMode` | Service-based guided word review | Debug simulator |
| `-CadenceSoundMode` | Standalone adult research sound preview | Debug simulator |
| `-CadenceAssessmentMode` | Earlier speech-check research lab | Debug simulator |
| `-CadenceAssessmentMode -CadenceAdmissionMode` | Speech-check lab with independent speech/word admission | Debug simulator |

### Library and direct practice

The bundled library has **24 consonant groups, 892 distinct words, and 2,398
sound-position entries**. Search and beginning/middle/end lists open short
sessions of up to three words, with an option to continue. Dictionary variants
establish intended sound placement, not what the learner produced. CMUdict
attribution is available in About → Dictionary license; see
[practice-library provenance](../../docs/content/practice-library-provenance.md).

Direct practice records mono 16 kHz PCM16 WAV clips capped at four seconds. It
keeps up to two takes for explicit earlier/latest listening. A third take removes
the oldest before allocating another file. Skip word is available before keeping
a recording; skipped words do not count as practiced. An all-skipped session adds
no participation entry.

About this sound contains optional B/P/M/T/D and R/BR guidance for supported
canonical targets. It describes general practice, without detecting an error.
The adapted B/P/M/T/D guide text is CC BY-SA 4.0; that license covers the guide
text, not the app. Sources and limits are recorded in the
[default-guide report](../../docs/consumer-assessment/native-default-sound-guide-verification-20261024.md)
and [professional handoff](../../docs/consumer-assessment/roadmap-completion/professional-handoff.md).

The optional plain Show mirror preview is separate from the prototype's AR face
guide. It performs no frame analysis, recording, upload, or speech assessment.
Normal simulators report camera unavailability.

### On-device review, practice and recheck

From legacy Home, **Review, practice, recheck** starts with five distinct library
entries. The default set is ball, pig, moon, tiger, and dog. Setup can save one
ordered set of words locally; it saves no recordings or results.

Record and check submits a fresh eligible take after Stop or the recording limit.
Record only permits listening and replacement before the first check. The first
submitted review observation stays frozen. Select one to three words for manual
practice, then recheck the original five with fresh takes. Practice completion
requires an eligible latest recording, regardless of the optional word-match
result. Review and recheck save no participation history.

The summary distinguishes skipped, unselected, and unfinished visits. Review
these five again starts fresh observations with the same words. Practice from a
summary opens a new session after cleanup; earlier observations do not carry over.
See [guided review behavior](../../docs/consumer-assessment/native-guided-feedback-review-20261024.md)
and [review-to-practice handoff](../../docs/consumer-assessment/native-guided-practice-handoff-verification-20261024.md).

### Word recognition and media ownership

Native word checks use the bundled English Whisper model through Core ML.
Resource hashes are checked when a check starts. The recognizer reads the whole
stopped recording without an expected-word hint, then compares its independent
transcription with the requested word. Checking downloads nothing and uploads
no audio. A whole-word match does not assess individual sounds; a mismatch does
not identify a pronunciation error.

Each retained take keeps its own temporary word-check observation. A short Word
guess, when available, belongs only to the current take and visit and may be wrong.
No transcript or guessed text enters participation history. First-review and
recheck submissions remain frozen; ordinary practice can explicitly retry a clean
unavailable check without recording again.

Recording, playback, recognition, and camera use have explicit owners. Cancel,
Close, background, and interruption revoke pending work. Recognition has a
15-second cooperative deadline; cancellation waits for the worker and timer to
return before releasing the recording. Unknown cleanup retains the owner/file
and blocks conflicting actions. Recovery never silently restarts media or checks.
See [retained word checks](../../docs/consumer-assessment/native-retained-word-check-verification-20261024.md)
and [timeout retry](../../docs/consumer-assessment/native-timeout-retry-verification-20261024.md).

Practice history stores up to 100 session/date/sound-group/word-count entries,
without audio, word text, age, identity, or pronunciation scores. Writes are
atomic and request complete file protection in a backup-excluded directory.
Unreadable data stays intact until explicit clearing; failed saves offer an
explicit retry. Participation counts do not measure speech improvement.

## Research services and clinician mode

Research labs require explicit processing opt-in and the separately configured
same-Mac service. `127.0.0.1` is the simulator's Mac loopback route; it does not
connect a physical iPhone to that Mac. Use each service's guide for exact source,
model, runtime, and cleanup requirements. Do not reuse an active private runtime
for verification.

- [Browser word-guess service](../../research/assessment-consumer-browser-guess-app/README.md):
  the current combined-feedback factory uses the reviewed profile on port 8803.
  Launch it with `--port 8803` rather than its default 8797, along with all
  required source/runtime arguments. Historical guided/standalone clients use the
  [unified service](../../research/assessment-consumer-unified-app/README.md) on 8793;
  those contracts and ports are not interchangeable.
- [Research assessment bridge](../../research/audio-head/consumer_assessment/README.md):
  port 8765, including opt-in local guided research processing after a native
  word match and declared age 6–12. Research distributions stay in session memory
  and are not learner findings. See the
  [guided model integration](../../docs/consumer-assessment/native-guided-model-integration-20261014.md).
- [Independent admission service](../../research/assessment-mobile-admission/README.md):
  port 8778 for the optional admission lab.

The clinical route is a separate legacy foundation. It verifies enrollment,
current consent, and the exact assignment before uploading a capture. Credentials
use the iOS Keychain; temporary audio is removed after upload outcomes. The server
returns a silent-practice receipt, without corrective feedback. Provider setup
and clinical gates remain incomplete; this mode is not approved for patient data.
See the [clinician guide](../clinician-web/README.md) and
[phase gates](../../docs/implementation/phase-gates.md).

## Checks and evidence

Run from the repository root:

| Command | Scope |
| --- | --- |
| `pnpm build:ios` | Generate the project and build for iOS Simulator |
| `pnpm test:ios` | Generate the project and run native unit/UI tests on iPhone 17 Pro |
| `pnpm test:swift-contracts` | Shared Swift contract tests |
| `pnpm lint:swift` | Swift formatting checks |

For another installed simulator, use its ID explicitly:

```sh
xcodebuild \
  -project apps/ios-learner/CadenceLearner.xcodeproj \
  -scheme CadenceLearner \
  -destination 'platform=iOS Simulator,id=<SIMULATOR_UDID>' \
  test
```

Generated test hosts use isolated stores, controlled recordings, and visibly
labeled camera fixtures. They establish software behavior, not physical capture,
audibility, face tracking, or clinical accuracy. Service loopback tests require
explicit opt-in and their documented setup. Read the dated reports for the exact
source, executed checks, failures, and remaining limits:

- [Release word recognition](../../docs/consumer-assessment/native-release-word-verification-20261015.md)
- [Native playback runtime](../../docs/consumer-assessment/native-playback-runtime-verification-20261016.md)
- [History access](../../docs/consumer-assessment/native-history-access-verification-20261016.md)
- [Native mirror](../../docs/consumer-assessment/native-mirror-verification-20261009.md)
- [Assessment preparation and catalog audit](../../docs/consumer-assessment/README.md)
- [Model roadmap](../../docs/model/model-development-roadmap.md)
