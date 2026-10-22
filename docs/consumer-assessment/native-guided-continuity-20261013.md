# Native guided-practice continuity

The mobile flow now carries each word's frozen first-review observation into practice and recheck. The observation follows the exact entry ID and current media visit, including when two entries display the same word. It describes a word check and explicitly says that word checks cannot identify which sound was made. Recording ownership, audio deletion and history behavior are unchanged.

Actual saved simulator results contain exactly 24 selected unit tests and 14 selected UI tests, all passed with zero failures, skips or expected failures. Debug and unsigned Release build commands also exited zero. The checks cover the first review, explicit word selection, fresh practice visits, recheck continuity, recovery and accessibility behavior. They do not verify a physical microphone, speaker or camera, or the Release interface on a device.

## Preserved verification failure

The original enclosing verification ended with exit one: session 75022, terminal `dce1d1`. All 12 child stages exited zero, but the frozen saved-results reader accepted only 23 unit names or 14 UI names. The added unit test produced a 24-name selection; its reader rejection became `postCollectionGuardOrDecode / ValueError`. The original negative report and its `sourceUnchanged: false` field remain intact.

A separate, independently reviewed reader changes only that count literal to support 23, 24 or 14, while its caller requires the exact current 24/14 selection. It reads the existing metadata without repeating builds or tests. Structural validity and complete selection are checked separately from passed, failed and skipped counts.

Actual collection: session 47271, exit zero, terminal `952467`. It independently checked current 338 inputs, resources, copies and completed build markers, all 12 known stage groups and the controller absent, and the exact dedicated simulator in Shutdown. Collection completed within 1,782.834 seconds of the original 3,000-second limit. The report is 21,476 bytes, SHA-256 `098d2d44226895142de1151113b0f93f58e366d3f1e676f838deaab7b5e2b2a1`; a subsequent pinned read (`45031e`) confirmed the exact counts and closure flags. Current integrity does not erase the original historical failure flag.

## Recognition readiness

[Apple English assets and capability checks](apple-ondevice-recognition-verification-20261012.md) completed, but the legacy recognition attempt observed denied speech authorization and created no recognition task. No permission reset or unchanged retry was performed. The bundled recognizer remains the working word-check route. This continuity change does not establish individual-sound accuracy, facial assessment or clinical diagnosis.

No signing or account settings were changed, and no recording was uploaded.
