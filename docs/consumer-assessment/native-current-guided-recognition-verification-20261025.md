# Current guided recognition integration — October 25, 2026

The current optimized iOS app module completed review → selected practice → fresh
recheck using the actual bundled local word recognizer. One test passed, with no
failures, skips, expected failures or automatic restarts. This closes a functional
integration gap after the encoder-state validation change; it adds no new learner
feature and does not establish pronunciation accuracy or diagnosis.

## Observed behavior

- Twelve distinct file-backed takes passed the existing capture-quality gate.
- Ten actual recognition requests returned ten exact cleanup-confirmed receipts:
  two Bread matches and eight deliberate mismatches against Pig, Moon, Tiger and
  Dog. Each review round reused the same licensed public Bread recording.
- The initial review stayed frozen. Review, practice and recheck used fresh visit,
  take, operation and round identities; duplicate checks did not issue requests.
- Two selected practice words saved exactly two private participation rows. Practice
  did not invoke optional word checks; fresh recheck issued the other five requests.
- Advancing removed each exact take. Close confirmed the strict fully-ended state,
  no remaining file/hardware owners, exactly one successful actual runtime release,
  and deletion of the test's UUID directory and private history. No playback occurred.

The method took 15.057 seconds; its internal whole-case receipt recorded 15,054 ms.
These are single-run observations, not an end-to-end speed comparison.

## Configuration and boundaries

Only the task-local `CurrentGuidedPublicWordTests` method was compiled and selected.
It copies the canonical public-word sequence while replacing the old protected-device
gate with the owned simulator gate and adding explicit runtime-release forwarding,
retry-capability forwarding and strict cleanup assertions. Production source,
recognition policy, thresholds, models and resource bytes were unchanged.

A fresh generated project, DerivedData and module cache were used. Actual compiler
invocations confirmed app `-O`, testability enabled and no DEBUG definition; tests
used `-Onone`. Canonical resource paths and all built resource bytes were admitted
before recognition. This was a normal app-hosted Release test, not the ordinary
shipping binary or a UI test. Home startup can read existing saved-word/history
metadata; the exercised session used private ownership and history.

The owned iPhone SE (3rd generation), iOS 26.2 simulator was
`CA4010CD-BF51-49C7-B289-2924926469EA`. The other simulator was state/list only.
Permission and capture hardware were doubled; the real capture/file lifecycle used
an inert driver that copied the fixture. There was no microphone, camera, audible
output, personal recording, reserved-study input, download, fitting or upload step.

The fixture is Dvortygirl's Wikimedia Commons `File:En-us-bread.ogg`, CC BY-SA 3.0,
converted to mono 16-kHz PCM16 without trimming, normalization or speed changes.
Existing attribution remains in `apps/ios-learner/PublicFixture`. The WAV is 17,912
bytes, SHA256 `0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f`.
Speaker age is unknown. Twelve copies do not constitute twelve independent speech
productions, and deliberate word mismatches are not individual-sound error labels.

## Restoration and evidence

After root observed the test controller's terminal exit, the separate restoration
controller reinstalled `practice-current-20261025-simulator-7`. All 26 installed
bundle files matched its preserved app exactly. No Data reset or app launch was
performed by that controller. Both simulators finished Shutdown.

Evidence is in `work/current-guided-recognition-20261025`:

- `current-checks-v1/VERIFIED.json`, the exact xcresult, exported summary/tree and
  aggregate test log bind the successful run and compiled inputs.
- `restore-candidate-7-v1/ROOT.json` records full installed-bundle equality and states.
- `ADMISSION.json` preserves 737 prior artifacts, four document bindings, 44 prior
  build namespaces, two Mac namespaces, 271 before-files and 123 compiled bindings.
- Root observed SDK session 66795 exit 0, restoration session 3599 exit 0, export
  exit 0, and verifier session 14590 exit 0. No run was retried.

The exported runtime-warning list is empty. The raw test log retains three Xcode
SDK-version parse messages and two Apple launch-measurement send failures. The build
log also retains one missing SwiftShims PCM-path warning and two skipped AppIntents
metadata-extraction warnings. Their causes were not diagnosed in this check; this is
not a warning-free build claim. Bounded process-group monitoring is not proof of all
implicit SDK services or simulator-app RSS.

This does not qualify live recording/playback/mirror usability, physical audibility,
VoiceOver, all recognition outcomes, child performance, phoneme-specific feedback,
clinical findings or release rights. Those remain separate work. The broad app goal
is active; candidate 7 remains the current demo.
