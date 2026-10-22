# Native q8 inference verification — October 15, 2026

The exact quantized CTC model now runs through native ONNX Runtime on Mac and **passes all27 original generated cases** against the actual JavaScript backend. All54 full-matrix comparisons are byte-identical: logits and serialized log posteriors have zero maximum and mean error. Their respective frame argmax and collapsed greedy token sequences match exactly. This closes native q8 output parity for this fixed suite; iOS packaging and complete feature/head integration remain separate work.

## Exact model and runtime

The native worker loads the unchanged317,712,852-byte quantized ONNX model, SHA256 `3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120`, through the existing Mac arm64 ONNX Runtime1.24.3 library and API24. No model conversion, replacement checkpoint, requantization or app dependency was introduced. The [SDK readiness record](../../work/native-q8-kernel-20261015/SDK-READINESS.md) contains the official header/license sources and earlier metadata-only results.

Both runtimes use CPU, two intra-op threads, one inter-op thread and sequential execution. The graph accepts only `input_values` FLOAT[1,N], at actual clip length; its output is FLOAT[1,T,392]. The JavaScript processor's attention mask is not a graph input. All392 logits are retained. Native Swift computes full-vocabulary log-softmax in Double, then serializes each value to FP32 before any downstream feature math.

For this runtime comparison, native inputs were byte-identical copies of the actual JavaScript processor's normalized feeds. It does not by itself verify native preprocessing or WAV decoding. No hidden-state output, canonical forced path, scalar feature, retained head or learner judgment is produced by this worker.

## Fixed comparison and actual run

The [prospective plan](../../work/native-q8-runtime-20261015/PLAN.json) uses the original27 PCM16 cases: six deterministic patterns at1600/16000/64000 samples and nine LCG cases around frame transitions. Pure tests passed, and all27 generated PCM byte hashes matched the original Python generator before inference. No microphone, participant corpus or reserved study input was used.

Acceptance was fixed before model execution: maximum absolute error1e-4 and mean absolute error1e-5 independently for logits and serialized log posteriors in every case, exact normalized input bytes, expected shape/finite values and exact respective argmax/greedy sequences. Logit and rounded-log-posterior discrete outputs are checked against their corresponding JavaScript boundaries; no extra equality between those two representations is assumed. No limits or cases changed after results were read.

Actual root20505 exited0 after22.067108250 seconds. C compilation, optimized Swift compilation, JavaScript reference, native inference and comparison all exited0 with normal empty owned process groups and no cleanup signals/errors. The JavaScript reference returned all27 forwards and disposal; the native worker returned27 actual Run calls,54 arrays,54 invocation/return markers and the exact109-file output namespace. The [comparison](../../work/native-q8-runtime-20261015/compare/comparison.json) records every case.

Native buffers, tensor values, run options and the copied model remain owned through their relevant scope. Each native call uses a joined deadline watchdog; unknown join or close state prevents completion. Native and reference sessions return before success admission. This passing run did not expire an inference deadline or fault-inject the ORT cancellation path.

The reference suite took5.589594750 seconds, with maximum sampled owned-group RSS1,067,264KiB; the native suite took6.944116500 seconds and sampled1,306,416KiB. These are complete generated-suite timings and sampled memory, not per-utterance latency, exact peak, iOS or physical-phone performance.

The [root audit](../../work/native-q8-runtime-20261015/ROOT-AUDIT.json) rehashed all348 source/tool/cache/prior-evidence bindings and332 unique artifact pins. It independently confirmed all54 native/reference array pairs have identical byte hashes. Independent [source review](../../work/native-q8-runtime-20261015/SOURCE-REVIEW.md) and [result review](../../work/native-q8-runtime-20261015/RESULT-REVIEW.md) cover the declared scopes. Before execution, review caught an omitted Swift compiler binding; the original freeze/controller were preserved, and the amended controller requires resolved compiler/SDK bindings. No inference failure or retry occurred in this task.

## Swift preprocessing continuation

The [native preprocessing helper](../../apps/ios-learner/Sources/Assessment/NativeCTCPreprocessing.swift) separately reproduces the actual sequential Double mean/population variance and one FP32 cast per normalized sample, with no padding, resampling or cropping. It accepts1600–64000 finite decoded samples and propagates cancellation/deadline callbacks. Caller-side PCM decoding, recording identity and sample-rate admission remain separate.

Actual root16787 exited0 after8.386760917 seconds: optimized harness compilation, optimized check compilation, iOS17 simulator SDK typecheck,58 focused validation/callback checks and all27 saved-feed comparisons passed. Every normalized output is byte-identical to the actual JavaScript processor's saved input, with the exact28-file namespace. Allfive owned groups closed normally. No model forward was repeated. The [closed audit](../../work/native-feature-head-20261015/ROOT-AUDIT.json) rehashed414 bindings and confirmed the promoted app helper is byte-identical to the tested source. Those58 checks include invalid lengths/NaN/Inf, constant input at both boundaries, and two distinct thrown errors at all25 callback positions.

The actual app target was regenerated and built in Release for the generic iOS simulator destination after promotion. Its [build result](../../work/native-feature-head-20261015/app-build/RESULT.json) records100 source bindings, both helpers included, normal project-generation/build exits and a31.168330417-second build. No simulator was launched and signing/account settings were unchanged.

This verifies the helper and feed bytes independently. The native inference worker above consumed copied JavaScript feeds; a single app call through Swift preprocessing into the native model is still integration work.

## Remaining integration

Join the actual native q8 stream with the [native hidden outputs verified on27 generated cases](native-integrated-hidden-result-20261015.md), through the [verified Swift feature kernel](native-ctc-feature-verification-20261015.md). The actual consumer bundle uses a13-scalar head and aPCA16-plus-scalar29 head, with equal unweighted rating-probability mixture; the source audit resolved an older PCA64 planning reference. That contract, its transforms/age/phone guards and native head outputs still require integration checks.

The current Mac library is not an iOS runtime dependency. Simulator/iOS library admission, combined packaging/memory/lifecycle, and live Release recording/playback/mirror/practice/recheck verification remain open. Apple Speech authorization remains denied; bundled CoreML word recognition remains the verified default. No signing/account changes or recording uploads occurred. These generated engineering results do not establish produced-phone correctness, effective corrective feedback or diagnosis.
