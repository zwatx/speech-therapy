# Installed search-fix demo — October 25, 2026

The current simulator demo is **practice-search-fix-20261025-simulator-8**. Search now announces matching sound groups as well as word entries. For example, `ʒ` has a ZH sound-group result and no spelling matches; it previously announced “No words match.” Empty wording now requires both collections to be empty. Filtering, navigation and the existing cancellable400ms debounce are unchanged.

## Verification and identity

The small source change received independent Sol investigation and Astra review. A fresh arm64 ordinary Release build passed with optimization `-O`, no DEBUG definition and testability disabled. The first temporary build project had an incorrect resource reference and failed; the corrected fresh project/build/cache passed in37.138seconds. Both results remain in `work/search-result-announcement-20261025`. One AppIntents metadata-extraction warning is retained. No runtime speech-delivery claim follows from compilation.

The already-built app was installed on the owned **Cadence Home short-screen Oct23**, iPhone SE3/iOS26.2, UUID `CA4010CD-BF51-49C7-B289-2924926469EA`. All25 installed bundle files equal the source build exactly, including all19 unchanged Whisper resource files. Root observed the installer outer34808 complete with exit0 (terminaldfa3d1). There was no data reset, app-sandbox data read by the controller, capture, playback, recognition, signing/account setting change or protected-device operation. The installer returned both relevant devices to Shutdown.

Root then used Apple's Device Hub to start only the owned simulator, open Cadence, choose **Review, practice, recheck**, and choose **Start first review**. Actual accessibility output and the inspected screenshot showed **First review · 1 of5**, **ball**, **Record and check**, **Record only**, **Next word** disabled, and **Skip this word**. No recording or playback was started. The app was left at this screen for human rehearsal. Device Hub's Sound control was observed at zero and was not changed by the agent.

Exact candidate metadata and installer receipts are in [the task folder](../../work/current-search-demo-20261025/CANDIDATE.json). The launcher/first-screen observation is narrow UI evidence. The [candidate7 artifact](native-current-release-candidate-verification-20261025.md) remains unchanged and available as the fallback; its prior normal/largest-text journeys were not rerun on candidate8 and are not claimed for it. Earlier sealed document bindings are historical; their former bytes were preserved in this task's `before-documents` directory before these current-status updates.

## Next human rehearsal

Use Device Hub's **Cadence Home short-screen Oct23** window. The app is ready at Ball; recording starts only when the user chooses a recording action. Raise the Sound control yourself if needed for audible replay. No raw recording upload is needed; record observations about the build, word/stage, action, visible result and unexpected sound or delay.

1. In the first review, choose **Record and check**, say the displayed word, and manually stop one take. On another word, allow the four-second cap to finish. Check whether capture starts clearly, Stop stays reachable, and the retained recording belongs to the intended word.
2. Replay a retained take, then explicitly stop playback. Check audible content and whether the controls recover without unexpected recording or advancement.
3. Finish the initial review, choose a word for practice, record it and optionally check it. Note whether feedback and the offered next actions are understandable, including any actual wait.
4. Open the practice reminder and deliberately retake. Compare earlier/latest playback, and check the new take if desired. Check readability and take/result identity. Use timeout recovery only if a timeout naturally occurs.
5. Continue into fresh recheck, finish and Close. Check that initial observations remain unchanged, recheck uses fresh recordings, participation is understandable, and no recording/playback continues after departure.

The human rehearsal has been requested but has **not** been observed or reported complete. It does not require a clinician to review every increment. A concrete failure should drive the next software fix. Mirror preview and actual VoiceOver use remain separate observations; a simulator cannot establish actual camera presentation on a camera-capable device.

## Remaining limits

Three separate public VoiceOver API attempts failed before completing the activation route. They establish neither working nor broken word-transition focus. See [the retained investigation](../../work/native-voiceover-20261025/RESULTS.md). No speculative focus change or fourth unsupported gesture variation was added.

Controlled Session/generated UI tests, current bundled-recognizer integration using a licensed public recording, this Release compile and no-media entry do not establish integrated live-media usability, intended-child/dialect accuracy, individual-sound correctness, improvement or diagnosis. Intended-use/reference observations, qualified reviewer acceptance and the outstanding rights facts still require real evidence. Existing closed model studies remain closed. No new outreach or mailbox poll occurred in this delivery.

The full consumer-app goal remains active. No broad release, clinical or all-accessibility completion claim is made.
