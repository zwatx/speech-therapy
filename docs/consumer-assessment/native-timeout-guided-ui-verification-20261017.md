# Guided timeout feedback: screen verification

The current timeout message is “Word check took too long. Your recording is still
here.” It uses the existing exact-take formatter for both the visible result and
the accessibility announcement. Recording policy, the first-review freeze,
recognition deadlines and cleanup ownership are unchanged.

The earlier message promised recording while the first guided submission kept
“Record another try” disabled. Two generated screen journeys exposed that
contradiction. Their passing results and original six screenshots remain intact;
the corrected wording has separate results and six new screenshots.

## Current-copy checks

Exactly two selected UI methods passed once each on the dedicated arm64 iPhone SE
(3rd generation), iOS 26.5 simulator: normal text and accessibility5. There were
zero failures, skips, expected failures or reported runtime warnings. Root viewed
all six new screenshots.

Each journey makes two generated takes and one fake word-check request, replays
and explicitly stops the retained take through the controlled player, then
practices ball with a fresh recording. No automatic second check is submitted.
The first timeout remains frozen through practice, an explicitly skipped recheck
and the paired summary. Exactly one practice participation row is saved; both
generated takes have been removed by Done/Close, without a pending borrow.

The updated timeout and frozen-review text are readable at both sizes. At
accessibility5 the tall summary continues below the viewport; the actual journey
scrolls to and activates Done. This is targeted screen verification, not general
accessibility certification.

The full test target compiled. The existing presentation unit assertion was
updated, but the earlier 21 unit methods were not rerun or added to this two-method
result. The new test command took 160.517 seconds; infrastructure and scripted
scrolling make this unsuitable as an app-latency measurement.

## Release restoration

A fresh ordinary Release app was built and installed, and the dedicated simulator
returned to Shutdown. Actual app and contracts compiler records on arm64 and
x86_64 use `-O`, include the current canonical Swift sources, and exclude DEBUG,
testability, the lifecycle verification condition and coverage profiling flags.
All 19 ordinary Whisper resource names and bytes match the source resources.
This restoration installs without launching the ordinary app.

The task-local scheme disables coverage. The canonical project, signing and
account settings are unchanged. Earlier restoration evidence is preserved: the
first command rejected a testing-only coverage option before compilation, and
its corrected build still contained Swift profiling. Those outcomes are separate
from the successful current-copy restoration with profiling flags absent.

## Evidence and limits

Current sources, before copies, process receipts, official results and images are
under `work/mobile-timeout-copy-20261017/`. The
[official admission](../../work/mobile-timeout-copy-20261017/execution-v1/OFFICIAL-ADMISSION.json)
records exact methods, device, image hashes and compiler evidence. The earlier
[generated checkpoint review](../../work/mobile-guided-lifecycle-20261017/execution-v1/RESULT-REVIEW.md)
retains the original wording issue and restoration limitations.
The independent [current-copy result review](../../work/mobile-timeout-copy-20261017/execution-v1/RESULT-REVIEW.md)
is clear for the two journeys and ordinary Release restoration within this scope.

These journeys use explicitly labeled generated capture, recognition and playback
fixtures. They establish no real microphone/camera acquisition, audio output,
model inference, elapsed 15-second timeout, real-worker cancellation or clinical
accuracy. The separate earlier bundled-recognizer/public-file integration remains
its own evidence. Apple English assets and en-US capability are established, but
Apple Speech authorization remains denied before recognition; no reset or repeated
Apple attempt was made. No recordings were uploaded.

The subsequent [real-worker Close checkpoint](native-word-guided-close-verification-20261017.md)
passed one guided coordinator integration case while a real encoder result was
deliberately held. Its scope is separate from these generated screen journeys.
The whole-app goal remains active.
