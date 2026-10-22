# Guided Close with the real bundled word worker

One optimized simulator integration test passed once using the actual bundled
Whisper encoder and an owned copy of the licensed public “bread” recording. It
exercised the guided coordinator's Close method twice while the worker deliberately
held its returned encoder result and runtime. This was a coordinator integration
test; it did not press a screen button or record a microphone.

## Observed behavior

The test observed exactly one worker entry and one encoder return. While the
returned result was held, a MainActor task ran, the first Close requested
cancellation, and a second Close joined the pending operation. A sibling request
was refused without another worker entry, and the guided coordinator suppressed
another check. Neither Close completed or discarded the recording while it was
borrowed. The owned file's identity, private permissions and bytes stayed intact.

After the test released its gate, the real worker returned cancelled with cleanup
confirmed and no retained handle. The original recognition receipt then returned,
the recording's producer discarded exactly one file, and both Close requests
completed successfully. The original operation/take identity was preserved in
the cancelled first submission. No participation history row was created, no
borrow or pending cleanup owner remained, and the now-empty fixture directory was
removed. The test did not manually release file ownership or delete the take.

The exported metadata contains six successful check groups and 19 ordered events.
Root independently reconciled the receipt, exact identities, counts, file state
and required partial order with the saved official result. The single method
took 1.953 seconds; the full test command took 9.272 seconds. These durations
include the deliberately gated test and are not ordinary recognition latency.

## Implementation and restoration

The worker has one verification-only callback immediately after the existing
encoder prediction returns and before the existing stop check. A scoped lifetime
hold keeps the actual runtime and returned provider alive across that callback.
The callback, its storage and its overload are absent when the explicit
`WORD_RECOGNITION_LIFECYCLE_VERIFICATION` condition is absent. Reversing only the
wrapper and conditional hook reproduces all previous worker source bytes.
Recognition math, stop-check order, the 15-second deadline and cleanup policy are
unchanged. The existing recognizer still awaits the worker and its cancelled
deadline task before releasing the recording borrow; this test does not
independently hold the timer task.

Both the instrumented test build and the ordinary app build passed. The latter
was built before the model test, installed afterward without launching, and the
dedicated iPhone SE (3rd generation), iOS 26.5 simulator returned to Shutdown.
Actual ordinary app/contract compiler records for arm64 and x86_64 use optimized
Release settings with no verification, testability or coverage profiling flags.
All 19 ordinary Whisper resource files match; test recordings, test bundles and
hidden-feature resources are absent from the ordinary app.

The canonical project, signing and account settings were unchanged. Capture
permission and the recording driver were doubled to create the public-file copy;
no microphone, camera or playback was requested, and no recording was uploaded.
The public source and attribution remained unchanged. Its speaker age is unknown
and it is not a clinical reference label.

## Evidence and remaining boundaries

The [official admission](../../work/mobile-word-lifecycle-20261017/execution-v1/OFFICIAL-ADMISSION.json)
binds the saved single-method result, attachment, stage receipts and source map.
Sources, before copies, build admissions and restoration evidence are under
`work/mobile-word-lifecycle-20261017/`. The earlier metadata reader's overly
strict architecture assertion is preserved; checking the saved records resolved
it without rebuilding or repeating a model call.

Official results report one pass, zero failures, skips or expected failures, and
no runtime warnings. Raw SDK output separately contains launch-measurement and
operating-system-build diagnostics; these are retained and support no launch
performance claim. All owned execution groups closed normally. Their sampled
memory figures exclude unowned app/services and are not device memory peaks.

Two model constructions and zero decoder predictions follow from the reached
source path and its subsequent cancellation check; they are source-derived,
not separate runtime counters. The test gate acts after encoder return. It
establishes neither interruption inside CoreML nor UI responsiveness during model
loading or prediction. The subsequent
[actual Close-button check](native-word-guided-close-ui-verification-20261017.md)
passed once using the same retained-result boundary and production guided view.
Backgrounding, standalone Cancel, ordinary per-take latency and physical-device
performance remain open.
This result adds no individual-sound accuracy or diagnostic qualification. The
whole-app goal remains active.
