# Cancelling a guided word check

One Cancel-check UI journey passed on the dedicated arm64 iPhone SE
(3rd generation), iOS 26.5 simulator, UUID 132DD629-A694-4D98-A0BB-B828676DD698.
The sole method ran once in configuration 1, taking 32.42276906967163 seconds,
with no failures, skips or expected failures. See the
[official summary](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/execution-v2/collection/summary.log),
[run detail](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/execution-v2/collection/details.log)
and [actual UI activity log](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/execution-v2/test/test.log).

The production Cancel check button was pressed while a real encoder result was
held after prediction returned. The same owned WAV, take and operation stayed
protected until joined cleanup. The cancelled receipt preceded the still-open,
retained-take checkpoint with its first review frozen. Replay was enabled but
not played; replacement recording and rechecking were ineligible. Actual Next
then caused one producer discard and opened a distinct ready “pig” visit, with
no second take/check. Only then did empty-visit Close dismiss the flow.

The [sole JSON attachment](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/execution-v2/collection/attachments/B815EA47-6A7A-427B-A4DE-FEF0E376C7CF.json)
and its [association manifest](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/execution-v2/collection/attachments/manifest.json)
record 22 ordered events, one cancellation, one observed worker entry/encoder
return, and no safety release or history row. Two model constructions and zero
decoder predictions are SOURCE-DERIVED counts, not independent runtime counters.
Recognizer deadline and gate both remained 15 seconds.

Root observed build 30459/admission 95771/test 34715/collector 62715/restore 40481
exit 0. The [closure observation](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/ROOT-CLOSURE-OBSERVATION.json)
(SHA256 e68a97433732a46a8a29dbe37b531ac05bddcca12e6ff3779a2bf9cde2196c79)
records unchanged canonical inputs, empty scoped groups and final file absence
(absence alone does not establish cause). The
[ordinary restore](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/shipping-restore-v2/install/ROOT-TERMINAL.json)
installed the same-current prebuild without launch, signing or account changes.
The simulator ended Shutdown.

The [original execution-v1 failure](/Users/zacharywilson/Documents/speech-therapy/work/mobile-word-cancel-ui-20261017/failed-build-recovery-v1/OBSERVATION.json)
remains failed: parent 41616 exited 1 with ENOSPC before any test. Its terminal,
child exit, RSS and wall time are unknown. Only closed SDK caches were removed,
with protected evidence unchanged; sparse logical sizes are not reclaimed-space
measurements.

The attributed public “bread” speaker's age is unknown; this is not clinical
gold. Capture hardware/permission were substituted, without participant microphone,
camera, playback or upload. This establishes no inside-CoreML interruption,
loading/prediction responsiveness, latency, phone performance, phoneme accuracy
or clinical diagnosis. Canonical app code was unchanged.
