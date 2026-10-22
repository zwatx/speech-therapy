# Native default playback runtime

The production default `SystemAcknowledgedPracticeAudioPlayer` now has an actual
Release simulator natural-completion check. Its default AVFoundation driver
starts playback, reports the exact successful completion, releases its audio and
file ownership, and permits deletion of the owned temporary copy. The dedicated
arm64 iOS26.5 simulator returns to Shutdown after the test.

## Natural completion

One exact selected XCTest passed with zero failures, skips or expected failures,
one official run and one receipt in its exact method leaf. It uses the unchanged
licensed public bread WAV, copied into a private temporary file. The source and
copy hashes agree. No playback driver or hardware facade is substituted.

The observed state sequence is idle → preparing → playing → stopping → idle.
The callback reports the exact operation and successful completion once. Querying
Stop afterward returns the original positive cleanup acknowledgement. The hardware
lease is clear, the file is removable through its real ownership registry, the
owned copy is deleted, and the isolated directory and registries are empty.

The build phase completed six stages normally in 50.419 seconds; the test phase
completed nine stages normally in 23.106 seconds, including host reads, simulator
boot and shutdown. Its test command took 8.081 seconds. These timings include test
infrastructure and do not estimate playback startup latency. All 144 frozen input
bindings and 38 generated/product bindings remained unchanged, with no signals
or cleanup errors. [Verification and exact bindings](../../work/release-native-playback-20261015/verification.json)
and the [independent result review](../../work/release-native-playback-20261015/RESULT-REVIEW.md)
preserve the complete result.

## Explicit Stop

A separate selected XCTest also passes with zero failures, skips or expected
failures, one official run and one exact leaf receipt. Swift generates eight
seconds of mono 16kHz PCM16 silence: a fixed 44-byte RIFF header and 256,000 zero
payload bytes, 256,044 bytes total. Its header, payload, on-disk copy and
pre-deletion hash match the independently generated input contract. No speech
recording or public fixture is used for this case.

Successful start, the exact playing operation and no prior finish callback are
required before two immediate Stop requests. Both return the same acknowledgement
object for that operation. The original acknowledgement reports positive release;
the player returns to idle, the hardware lease clears and the owned file becomes
removable. No finish callback arrives during the one-second post-release window.
The file and isolated directory are then deleted with empty ownership registries.
An already finished input, a timeout or a separate cleanup retry cannot pass this
test; no manual hardware or borrow release is used.

The build completed six stages normally in 52.241 seconds; the test phase
completed nine stages normally in 24.119 seconds, with an 8.876-second test
command. All 141 input bindings and 36 generated/product bindings remained
unchanged. Host samples agree before/after, the simulator is Shutdown, and there
are no signals or cleanup errors. The [explicit-Stop verification](../../work/release-native-playback-stop-20261016/verification.json)
preserves the official result, exact aggregate and bindings. The finite callback
window supplies no assertion about all future time.

## Host state and scope

The actual driver activates the simulator's playback/spokenAudio session with
duckOthers, then deactivates it during cleanup. Read-only host snapshots before
and after agree on output/input/alert volume, output mute and three default
device IDs. Output mute was off and was preserved. This checks those sampled
values; it does not establish the complete route graph, rule out every transient
audio-session effect or establish audibility.

The app is optimized Release `-O`, with an unoptimized XCTest harness and
testability enabled. Existing simulator signing defaults are retained. No signing
or account settings were changed. The public bread attribution is preserved in
the test-only resource folder; speaker age and produced-phone correctness are
unknown. This test requests no microphone, camera, ASR or remote service and
uploads no recording.

These two playback-component checks are separate from the guided journey below.

## Combined guided word checks and replay

A subsequent current-source Release test passes the full file-backed guided
coordinator with its actual default bundled CoreML word recognizer and actual
default AVFoundation player. Five fixed licensed recordings supply twelve fresh
owned takes: five initial checks, two optional practice checks and five fresh
rechecks. Three current bread takes are replayed before recognition: initial
review, first practice and recheck. Playback uses no driver factory substitution.
Capture hardware and permissions remain explicit test doubles.

All three replays require a successful real start, successful natural callback,
exact operation, preparing/playing/stopping/idle states, original positive cleanup
acknowledgement, released hardware and file borrow, and an unchanged current take.
No recognition request occurs during those playback lifecycles. Check is observed
disabled while playing in all three visits. Next is observed disabled in review
and recheck, and enabled in practice, consistent with the existing participation
rule. This test waits for playback cleanup before advancing; it does not exercise
Next during playback.

All twelve takes pass the production AVAudioFile summary and capture-quality gate.
The recognizer returns nine matches and three nonmatches, all for sky, with no
required match distribution or changed policy. Initial observations stay frozen;
optional practice observations attach only to their current takes. Participation
does not require a lexical match. Exactly two practice records reopen unchanged,
recheck identities are fresh, and all twelve owned files are deleted after
acknowledged cleanup. Final ownership registries and the directory are empty.

The official result has one selected passing method, one run, no failures, skips
or expected failures and one receipt in its exact method leaf. The combined case
took 24,987 milliseconds. Build completed six stages normally in 52.849 seconds;
the test phase completed nine stages normally in 48.200 seconds, with a
32.692-second test command. These single observations include test infrastructure
and uncontrolled caches; they are not latency or accuracy estimates. All 149
input bindings and 42 generated/product bindings remained current. The 98
production Swift files and three icon files match the prior guided sources.
The app is Release `-O`, the harness `-Onone`, and testability is enabled.

The simulator returned to Shutdown. Read-only host samples agree before/after,
including mute off, with no settings setter, signing/account override or recording
upload. The [combined verification](../../work/release-guided-native-media-20261016/verification.json)
preserves the exact aggregate, official result and 308 file bindings; the
[independent result review](../../work/release-guided-native-media-20261016/RESULT-REVIEW.md)
checks the saved evidence and its scope. Earlier failed test contracts and all
recognizer nonmatches remain preserved.

This establishes combined file-backed app integration. Live microphone acquisition,
mirror runtime, manual UI media interactions and physical-device behavior remain
unverified in this combined check. Apple Speech authorization remains denied;
the bundled recognizer supplies these word observations. The public recordings
do not establish child accuracy, individual-sound correctness, corrective feedback
or clinical validity. Full acoustic-model app integration remains separate work.
