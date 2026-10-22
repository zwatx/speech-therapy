# Native CTC feature verification — October 15, 2026

The production Swift feature kernel passes **all 29 generated cases** against the existing Python math: ten complete numerical cases and nineteen expected errors. All 315 compared Double values pass the fixed limits. Every saved FP32 feature, pooled and global array is byte-identical, and all scalar casts have zero ULP difference. The actual app Release simulator build also passes. This verifies the deterministic feature code; actual native q8 model inference and the complete feature/head integration remain open.

## Implemented boundary

[CanonicalCTCFeatures.swift](../../apps/ios-learner/Sources/Assessment/CanonicalCTCFeatures.swift) implements the exact provisional canonical mapping, Double max-sum CTC alignment, first-ID greedy decoding, thirteen research scalars, clipped ±2-frame hidden pooling and ordered 1,037-value feature rows. Inputs retain all 392 log-posterior columns and the independent 1,024 hidden coordinates. The module performs no model inference, file access, learner eligibility decision or UI action. No existing app caller has been switched to it yet.

The mapping preserves literal UTF-8 vocabulary identity using `Data` keys. The exact vocabulary contains both decomposed `u + U+0303` at ID191 and composed `U+0169` at ID374. Swift string equality merges those keys, so a string-key dictionary cannot represent this model inventory. The diagnostic loader retains `NSDictionary` entries until each key has been encoded independently; it verifies all392 entries and both distinct IDs.

The kernel preserves requested target order and inventory metadata, including ID23. The retained research heads separately support23 fitted phones; accepting an inventory ID does not admit it to a head. Forced canonical occupancy remains an estimated location, with low-support/one-frame diagnostics retained. It does not establish which phone a speaker produced.

## Actual verification

The [fixed plan](../../work/native-q8-kernel-v3-20261015/PLAN.json) keeps Double limits `1e-10 + 1e-12 × abs(reference)`, each FP32 component within2 ULP, exact generated dyadic pooling bytes, and exact discrete paths, ordering, intervals, flags and error classes. No case, reference or numerical limit changed after a failure.

The ten complete cases cover predecessor/final-state ties, repeated-token blank separation, edge occupancy and reversed requested order, special-token mass, lowest-ID argmax ties, low support, stress/rhotic mapping, all199 frames and inventory ID23. Nineteen expected errors cover malformed dimensions/dtypes, NaN/Inf, invalid log probabilities, impossible alignment, mapping/target errors and injected callback cancellation/deadline. Callback injections are deterministic throws, not evidence of an actual expired inference deadline. Dtype controls exercise the diagnostic boundary; the production API accepts `[Float]` arrays.

Actual root12859 exited0 after8.742186291 seconds. Optimized Mac compilation, iOS17 simulator SDK typecheck, Python preparation, native worker and comparison each exited0 with empty owned process groups and no cleanup signals/errors. The worker returned29 cases and the exact31-file output namespace: thirty arrays plus receipt. No model forward or audio input occurred. The [root audit](../../work/native-q8-kernel-v3-20261015/ROOT-AUDIT.json) rehashed208 unique artifact pins and all40 frozen source/tool/prior-evidence bindings. [Comparison](../../work/native-q8-kernel-v3-20261015/compare/comparison.json) and independent source/result review remain available with the private evidence.

The full app was regenerated using its normal XcodeGen specification and built in Release for the generic iOS simulator destination, with signing disabled for that invocation. The [build result](../../work/native-q8-kernel-v3-20261015/app-build/RESULT.json) records99 source bindings, successful project generation and a32.890265-second build. This included the new kernel in the actual app target. It launched no simulator and changed no signing/account settings. Compilation is not live-media verification.

Eight existing Python controls also passed. Eleven malformed-request regression checks passed on the preserved v2 transport worker: reordered/duplicate/non-integer/boolean/null/type-invalid requests, incorrect SHA/size and deadline mismatches. They processed no mathematical cases and do not establish production model accuracy.

## Preserved failures

The first worker stopped before any case because Foundation key collation differed from Python lexical JSON ordering. A new harness retained strict byte admission with an ASCII-key UTF-8 encoder and earlier private failure publication. The next run returned29 errors because Swift dictionary bridging collapsed the392-entry vocabulary to391. A separate metadata probe measured NSDictionary392, Swift-string dictionary391 and byte-key set392. The third run tested the byte-preserving fix above and passed. Original sources, receipts and unsuccessful results remain intact under the original and v2 task directories.

A first transport regression checker also expected the wrong rejection stage for a string-valued integer and lacked provenance copies. Its corrected successor copied the bound provenance and verified the actual schema-stage rejection; the first failed checker is preserved. The first post-run audit used the wrong base for transport artifact paths; its corrected audit rehashed the actual outputs without repeating any kernel run.

## Next integration

The exact q8 model opens in native ONNX Runtime1.24.3 and exposes only `input_values` FLOAT with dynamic length; the separate [SDK readiness record](../../work/native-q8-kernel-20261015/SDK-READINESS.md) establishes metadata, with zero inference calls. Next, compare actual native q8 logits and serialized full-vocabulary log posteriors against the actual JavaScript backend on the original27 generated PCM cases. Then join actual native q8 with the [native hidden path verified on27 generated cases](native-integrated-hidden-result-20261015.md), verify retained transforms/heads and test the simulator app lifecycle, packaging and performance.

Apple Speech permission remains denied; the bundled Core ML word recognizer remains the verified default route. No participant/reserved inputs, recording uploads, signing/account changes or new clinical judgments were used here. Produced-phone references and professional review remain separate product requirements.
