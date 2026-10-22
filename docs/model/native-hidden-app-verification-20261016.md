# Hidden-feature calculation inside the iOS app

October 16, 2026. The actual iOS app implementation now passes all 54 saved-reference comparisons across 27 generated controls. A separate owned, stopped synthetic WAV passes through the app operation and adds two passing comparisons. This closes a component-integration gap after the [standalone simulator check](native-ios-hidden-verification-20261015.md). It does not enable new consumer feedback: the separate [q8 score mismatch](native-q8-encoder-thirds-verification-20261016.md), complete feature/head composition and app lifecycle/performance qualification remain open.

## Implementation boundary

`NativeHiddenResources`, `NativeHiddenCoreMLWorker` and `NativeHiddenOperation` are internal production sources. They validate the fixed resource namespace and hashes, retain the exact stopped-recording borrow across background work, run the three CPU-only Core ML programs, and return owned finite hidden arrays. Cancellation revokes publication and waits for actual worker and timer completion before releasing the borrow. Unconfirmed cleanup retains ownership and blocks reuse. Thirteen unit checks cover the resource, operation, cancellation and cleanup contracts using controlled workers; they do not establish cancellation during a real Core ML prediction.

The model calculation preserves normalized 64,000-sample input, projected-row masking, materialized 64-column borders, the original frame mask, invalid-query behavior and 1,024-wide hidden output. It does not substitute hidden values for the separate 392-token q8 CTC scores. The ordinary app has no callsite or resource bundle enabling this new component. Its bundled local whole-word recognition and manual practice route remain available.

## Actual app numerical check

The private task is `work/native-hidden-app-integration-20261016/`. A separate inert Release test host uses the actual app implementation and exact accepted simulator model resources: 15 compiled files totaling 1,262,091,085 bytes, plus the fixed resource manifest. No model conversion, training, calibration or reference generation was performed for these tests.

Both selected native methods passed once on the dedicated arm64 iPhone SE (3rd generation), iOS Simulator 26.5. The first sends all 27 saved normalized inputs through the actual bundled kernel. The second creates a 3,244-byte PCM16 WAV containing 1,600 zero samples, borrows that owned stopped file and uses the real operation. The compiled source implies 84 predictions across these methods; this is not an instrumented runtime prediction count.

An independent root reader checked the 28 exported FP32 outputs against the unchanged full-output and valid-prefix references, recomputing all 56 comparisons. Acceptance remains maximum absolute error at most 1e-3 and mean absolute error at most 1e-4. The largest maximum error is 0.00043487548828125; the largest case mean is 0.0000025604318017349317. Both remain within those limits. Agreement with Swift aggregation was checked separately; it did not change acceptance thresholds.

The reader also reconciled the exact two official methods, model copies, source/build/result maps, attachment namespace, synthetic WAV construction, request/take identities and reported cleanup. The stopped-WAV hidden bytes equal the direct zero-input control. Reported file deletion and cleanup come from the compiled test observations; the saved-attachment reader does not independently observe filesystem absence. The numerical run closed normally, and the simulator was Shutdown afterward. Elapsed times are observations of this synthetic suite, not qualified phone latency or app memory.

## Evidence and limits

The unit result preserves an original build-audit failure, a failed saved-result schema correction and a later result-collection cache addition. Separately reviewed saved-evidence admissions establish the actual successful compiler/test observations without rewriting those failures. The unit receipt keeps `originalBuildWorkflowComplete` false.

The numerical task's official receipt admits the two method passes and deliberately leaves attachment interpretation to a separate receipt. `NUMERICAL-ATTACHMENT-ADMISSION.json` records 27 controls, one stopped WAV, 56 comparisons and current bindings. Independent `RESULT-REVIEW.md` is clear for that limited slice. Original receipts are unchanged.

After the generated hosts finished, a fresh ordinary Release app build passed with all current production sources and unchanged local word-recognition resources. It includes neither the synthetic host nor the hidden model package. One existing compact guided-repeat UI method passed once: it selects a word, navigates manual practice and recheck, starts a fresh review of the same five words, and checks unchanged history entry identifiers. It never starts recording, replay or mirror. Root inspected the saved compact summary image; the whole-word limitation and repeat controls are readable. The official receipt's original unreviewed-image flag remains unchanged, with the actual inspection recorded separately. The app was terminated and the dedicated simulator returned to Shutdown. These checks do not establish complete history-container equality or active-media behavior.

This is generated-input numerical parity, not real-speech recognition accuracy, target-sound correctness, effective correction or diagnosis. It does not qualify real in-flight cancellation, Close/background behavior during model work, complete native assessment, app/service peak memory, physical-phone performance or the practical 1.26 GB model footprint. Learner, clinical and complete-pipeline eligibility remain false. No signing/account settings, recording upload, consumed study or sealed reserve changed.
