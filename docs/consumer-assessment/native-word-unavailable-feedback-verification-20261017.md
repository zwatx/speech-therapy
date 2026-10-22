# Unavailable word-check feedback

The mobile app now says “Word check unavailable. Your recording is still here.”
The About text explains that word checks are optional and directs people to the
available controls. This avoids suggesting that another recording is available
within a guided review whose first submission has already been frozen.

The change contains three literal substitutions in two canonical files: the
presentation strings and an existing availability assertion. Recording rules,
same-take identity checks, guided review freezing, cancellation, cleanup, models
and recognition thresholds are unchanged.

## Verification

Five existing `LocalWordRecognitionPresentationTests` passed once each in an
optimized Release app with an inert entry point on the dedicated iPhone SE
(3rd generation), iOS 26.5 simulator. The official result reports five passes,
zero failures, skips, expected failures or runtime warnings, and one device and
configuration. These are presentation-value checks; they do not demonstrate a
new UI journey, audio capture, model inference or clinical validity.

The separate ordinary Release build compiled the current production sources
without testability, DEBUG, lifecycle verification conditions or coverage.
Its 19 bundled Whisper resource files matched the source resources. It contained
no test plugins or public/hidden verification fixtures. It was installed after
the tests without launching, and the dedicated simulator was confirmed Shutdown.

The first generation attempt failed when the disk filled up, before compilation
or test execution. Its missing aggregate receipt remains missing. Fifteen
regenerable SDK module caches from completed verification builds were removed;
the checked source, product and evidence files were preserved. Both subsequent
builds passed. An initial metadata admission then rejected Xcode's generated test
debug-symbol folder; the reviewed correction accepts only that exact optional
package, its three-file layout, metadata identity and generation-log evidence.
No recompilation or test replay was needed for that correction.

The saved test log retains Xcode `invalidDigitCount` and launch-measurement
diagnostics; these are not reported as runtime warnings in the official result.

## Evidence and limits

Task folder: `work/mobile-unavailable-copy-20261017`. The execution-v1 failure,
execution-v2 source freeze/build/test/collection, ordinary restoration,
root-observed parent exits, saved-result admission and independent reviews are
kept separately. Later source changes require new verification; the saved frozen
maps describe the source versions checked at this checkpoint.

No recordings were uploaded. No microphone, camera, physical phone, signing or
account settings were used or changed. Apple recognition authorization and the
consumed research study were not retried. The browser app on port 8823 was left
running. Actual Home/foreground behavior during real model work remains a
separate follow-up, as do produced-sound correctness and diagnosis.
