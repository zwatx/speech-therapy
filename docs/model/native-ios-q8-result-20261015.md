# iOS simulator q8 result — October 15, 2026

The first static iOS simulator run completed all27 native calls with normal cleanup, but **only5 cases passed numerical parity;22 failed**. All27 respective frame-argmax and greedy-token comparisons matched. That discrete agreement does not qualify the score arrays for alignment/features or pronunciation feedback. This candidate remains withheld from the app's feedback route. The later preserved-output diagnostic below now narrows the failing control's measured discrepancy to the 24 encoder blocks plus final outer normalization; it does not repair the scores.

The exact317,712,852-byte quantized model, SHA256 `3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120`, ran through the official ONNX Runtime1.24.3 static arm64 simulator framework/API24. Native inputs were byte-identical copies of the actual JavaScript processor feeds from the [closed Mac verification](native-q8-runtime-verification-20261015.md). There was no new reference forward, recording, dataset access, weight conversion or threshold change. The C bridge retains CPU default execution, intra2/inter1/sequential, model/input/output ownership and joined deadline watchdog; only static loading and provenance replace the Mac dylib interface.

The [reviewed source](../../work/native-ios-q8-runtime-20261015/SOURCE-REVIEW.md) binds576 source/tool/SDK/reference files. The [run plan](../../work/native-ios-q8-runtime-20261015/RUN-PLAN.json) preserves the original27 cases and fixed per-array maximum1e-4/mean1e-5 gates, exact normalized inputs and exact respective discrete outputs. Its copied original numeric PLAN is historical; RUN-PLAN explicitly requires zero new JavaScript reference forwards.

Actual root91914 exited2 after21.530347833 seconds. All eight stages closed normally: device-state observation, C/Swift compilation, platform/dependency inspection, native inference, comparison and final device-state observation. Comparison exited2 for failed numerical gates; the other stages exited0. The worker returned27 Run calls,54 arrays,54 invocation/return markers and the exact109-file output namespace. Its request-bound OWNER.json remained outside that output namespace. The parent observed the exact executable/PID/PGID/parent PID, verified normal native and CLI exit, and found no remaining native PID/group members or cleanup signals/errors. The dedicated simulator was Shutdown before and after standalone execution.

Worst logit maximum error was0.1756577491760254; worst serialized log-posterior maximum error was0.25507354736328125. Both arrays fail in the same22 cases. Six complete native/reference array pairs are byte-identical. All results, including failures, remain in the [comparison](../../work/native-ios-q8-runtime-20261015/compare/comparison.json). The [closed audit](../../work/native-ios-q8-runtime-20261015/ROOT-AUDIT.json) rehashed576 source bindings and791 file bindings, independently recomputed all54 numerical metrics from saved FP32 bytes, and verified the failed outcome. Independent [result review](../../work/native-ios-q8-runtime-20261015/RESULT-REVIEW.md) accepts this as a completed negative experiment.

Native-suite time was7.501749875 seconds; maximum sampled owned RSS was1,036,336KiB. Memory covers the deduplicated CLI process group plus the identified native PID, excluding other host/simulator resources; it is not an exact peak or phone measurement. Matching generated greedy tokens does not establish real-word recognition accuracy, corrective usefulness or clinical validity.

The published build recipe alone does not establish actual kernel selection: embedded KleidiAI symbols exist in both binaries, and build strings share a commit prefix. The failed27-case run will not be rerun unchanged or reclassified by widening limits.

The [complete Mac feature/head path](native-feature-head-verification-20261015.md) and Release app build remain verified. iOS acoustic score parity, complete app packaging/lifecycle and live Release media still need work. The separate [iOS hidden-feature chain](native-ios-hidden-verification-20261015.md) now passes all54 original comparisons. The separate [iOS retained-head comparison](native-ios-head-readiness-20261015.md#full-ios-feature-and-retained-head-comparison) now passes on saved Mac acoustic inputs. Apple Speech authorization remains denied; bundled CoreML word recognition remains the verified default. No signing/account settings changed, recordings were not uploaded, and the consumed study/sealed reserve were untouched.

## Paired prepacking control

A separately [reviewed fixed diagnostic](../../work/native-q8-prepacking-diagnostic-20261015/SOURCE-REVIEW.md) changed only the supported session setting `session.disable_prepacking=1`, plus read-only build-info collection. It used periodicRamp-L1600 and impulse-L1600, both1600 samples/four frames, on each runtime: four new native calls, zero reference forwards. It did not rerun the27-case experiment or change any numerical limits.

Actual root57892 exited0 after28.786757 seconds. All stages closed normally, including the identified iOS native PID; the dedicated simulator was Shutdown before and after standalone execution. Both new Mac arrays and both new iOS arrays for each input were byte-identical to their respective saved baselines—all eight arrays unchanged. The periodic-ramp control still matches across runtimes. The impulse discrepancy remains exactly: logit max0.07778644561767578/mean0.0286659094129632; log-posterior max0.11594772338867188/mean0.036985949579892416. Actual API build strings report Release commits3a728b7506 and3a728b7; that common prefix does not identify the selected kernels.

The [comparison](../../work/native-q8-prepacking-diagnostic-20261015/compare/comparison.json) retains all20 branches, including each new runtime against both saved baselines and against the other new runtime. The [closed audit](../../work/native-q8-prepacking-diagnostic-20261015/ROOT-AUDIT.json) rehashed816 source bindings/991 file bindings and independently recomputed every numerical metric. [Result review](../../work/native-q8-prepacking-diagnostic-20261015/RESULT-REVIEW.md) confirms this completed diagnostic found no correction. Prepacking had no observable effect on this pair; no unique cause or global exclusion of a kernel family follows.

The subsequent checks below inspect the actual original-default optimized graphs without inference, then measure shared internal boundaries. Adding intermediate outputs must also preserve each runtime's original logits before its result can explain the original discrepancy. No further flag sweep or learner-facing score is enabled.

## Original-default optimized graphs

The [reviewed metadata-only continuation](../../work/native-q8-graph-boundary-20261015/SOURCE-REVIEW.md) created one original-default session on each runtime and made **zero Run calls**. Both runtimes serialized exactly the same optimized model: 317,405,134 bytes, SHA256 `d3ae4ada0a7dfad2018036572a7ad6c02fda119405f71d2872b962732c171784`. Each optimized graph contains 875 nodes and 737 initializers; the original model contains 2,129 nodes and 754 initializers. This establishes identical saved graph bytes, including their embedded weights and attributes. It does not establish identical internal kernel selection, numerical execution or repaired score parity.

Actual root10766 exited0 after33.100076125 seconds. All15 stages closed normally: original protobuf inventory; Mac C/Swift compilation, platform/dependency inspection, session serialization and inventory; the corresponding iOS stages plus device-state observations. The parent observed iOS native PID94239 and CLI/PGID94227, then verified their absence with no cleanup signals or errors. The dedicated simulator was Shutdown before and after standalone execution. Each native output namespace contains only its optimized model and receipt; both sessions released their owners before the final file checks.

The [closed audit](../../work/native-q8-graph-boundary-20261015/ROOT-AUDIT.json) rehashed962 frozen source/tool/runtime bindings and1,059 file bindings. The three private protobuf inventories record operator topology, declared shapes, initializer fingerprints and attribute fingerprints. The reader uses the existing protobuf runtime and the pinned generated ONNX schema without installing or importing the ONNX package, running shape inference, reading external tensor files or emitting tensor values. Any external-data tensor reference is rejected. Session construction may optimize or fold constants; zero explicit Run calls does not mean zero internal initialization work.

Session/serialization stages took2.516677208 seconds on Mac and2.489824459 seconds on iOS. Maximum sampled owned RSS was1,716,384KiB and1,646,640KiB respectively; the latter deduplicates the CLI group and identified native PID. These are suite observations, excluding other host/service resources, not exact peaks, prediction latency or phone measurements.

The unchanged numerical failure remains open. The subsequent boundary checks below verify that exposing shared internals preserves each runtime's original logits. The separate iOS head comparison now passes on saved Mac acoustic inputs; that component result cannot repair or qualify the complete iOS acoustic path. No model weights, scientific limits, app dependencies, signing/accounts, recordings or reserved study data changed.

## First quantization and convolution boundaries

The [reviewed first-boundary probe](../../work/native-q8-first-boundary-20261015/SOURCE-REVIEW.md) completed four native calls on the fixed periodic-ramp/impulse pair. It added five output declarations to the exact original model: input quantized bytes, scale, zero point, first integer convolution and pre-bias dequantized output. An independent protobuf audit proves that all non-output content is byte-identical after removing the output declarations, and separately verifies the unchanged original logits declaration. No weights, optimizer settings or prepacking settings changed.

**All eight instrumentation guards passed:** each new final-logit and serialized log-posterior array is byte-identical to its saved same-runtime baseline. Both runtimes also match exactly at all five internal boundaries for both inputs. The impulse's unchanged final discrepancy therefore occurs after this measured prefix. This does not identify the first differing operator elsewhere, exclude a kernel family globally or repair numerical parity. The periodic-ramp case remains byte-identical throughout the measured and final outputs.

Actual root66854 exited0 after40.175602667 seconds. All15 stages closed normally: preparation, independent output-only proof, both builds/platform/dependency checks, four native calls, device-state observations and comparison. The workers saved28 typed arrays, eight invocation/return markers and two receipts:19 output files per runtime. iOS native PID14053 and CLI/PGID14043 were observed and then absent, with no signals or cleanup errors. The dedicated simulator was Shutdown before and after standalone execution. No new reference forward occurred.

The [comparison](../../work/native-q8-first-boundary-20261015/compare/comparison.json) retains all results. The [closed audit](../../work/native-q8-first-boundary-20261015/ROOT-AUDIT.json) rehashed986 source bindings and1,122 file bindings, independently recomputing the eight baseline guards and typed boundary differences. [Result review](../../work/native-q8-first-boundary-20261015/RESULT-REVIEW.md) is clear. Internal floating differences are observational; no new acceptance tolerance was invented. The continuation below measures bias, normalization and activation while retaining the same final-array guards and adding checks against the saved pre-bias anchors. The candidate remains withheld from learner feedback.


## First-layer bias, normalization and activation endpoints

The [reviewed continuation](../../work/native-q8-normalization-boundary-20261015/SOURCE-REVIEW.md) completed four native calls on the same two generated inputs, using original optimization and prepacking settings. It starts from the exact original model, retains the prior pre-bias anchor and adds the post-bias, post-normalization and activation outputs. Each internal output is FP32[1,512,319]. The three new declarations are copied byte-for-byte from original valueInfo messages; an [independent protobuf audit](../../work/native-q8-normalization-boundary-20261015/PROBE-AUDIT.json) verifies those copies, the unchanged original logits declaration and identical non-output content. No model operations, weights or scientific limits changed.

**All twelve preservation checks passed:** all eight final-logit/log-posterior arrays remain byte-identical to their saved same-runtime baselines, and all four repeated pre-bias arrays remain byte-identical to their respective first-boundary outputs. Both runtimes also match exactly at all four measured internal endpoints for both inputs. The impulse final-score discrepancy remains unchanged after the measured first-layer activation endpoint: logits max0.07778644561767578/mean0.0286659094129632; log-posterior max0.11594772338867188/mean0.036985949579892416. The periodic-ramp case remains exact at the measured endpoints and final outputs. This moves the search later; it neither identifies a unique operator cause nor excludes transient differences between endpoints or changed internal fusion/dispatch.

Actual root86782 exited0 after57.850753 seconds. All15 stages closed normally. Each runtime saved12 arrays, four invocation/return markers and its receipt:17 output files per runtime,34 total. Native iOS PID25239 and CLI/PGID25227 were observed alive and then absent, with no signals or cleanup errors; the dedicated simulator remained Shutdown before and after standalone execution. No new reference forward, flag sweep, tolerance change or unchanged27-case rerun occurred.

The Mac native stage took1.987121375 seconds with maximum sampled owned RSS1,212,000KiB; the iOS stage took1.975875583 seconds with deduplicated sampled owned RSS1,012,544KiB. These are whole-stage observations, excluding other host/service resources, not exact peaks, prediction latency or phone measurements. The [closed audit](../../work/native-q8-normalization-boundary-20261015/ROOT-AUDIT.json) verifies1,141 source bindings and1,274 file bindings, independently recomputing all twelve guards and boundary differences. The [comparison](../../work/native-q8-normalization-boundary-20261015/compare/comparison.json) preserves both cases and every observation. The iOS acoustic candidate remains withheld; the subsequent coarse check below narrows the measured interval, while numerical repair and complete native model/app integration remain open. Production, clinical and learner qualification remain false.

## Coarse frontend and encoder boundaries

The [reviewed coarse diagnostic](../../work/native-q8-coarse-boundary-20261015/SOURCE-REVIEW.md) completed four native calls on the same periodic-ramp and impulse controls. It copies four complete original output declarations: the repeated first-layer activation, final frontend activation, encoder entry after projection/position addition, and encoder output after its outer final normalization. An [independent protobuf audit](../../work/native-q8-coarse-boundary-20261015/PROBE-AUDIT.json) verifies all four original declarations, the previous activation declaration, unchanged original logits, and byte-identical complete non-output content. Runtime options, weights and numerical limits remain unchanged.

**All twelve preservation checks pass:** eight original final-logit/log-posterior arrays and four repeated activation arrays are byte-identical to their saved same-runtime outputs. Both runtimes match exactly at the measured final feature-extraction and encoder-entry endpoints for both controls. The impulse differs at the final normalized encoder output; the periodic ramp remains exact at every measured endpoint and both final arrays.

| Control | First activation | Final frontend | Encoder entry | Final normalized encoder |
| --- | --- | --- | --- | --- |
| Periodic ramp | Byte-identical | Byte-identical | Byte-identical | Byte-identical |
| Impulse | Byte-identical | Byte-identical | Byte-identical | All 4,096 values differ |

For the impulse encoder output, maximum absolute error is 0.07064515352249146 and mean absolute error is 0.0032121792572752383. These internal errors are observations, with no new acceptance tolerance. Original final errors remain exactly unchanged: logits maximum 0.07778644561767578/mean 0.0286659094129632; log-posterior maximum 0.11594772338867188/mean 0.036985949579892416. Final argmax and collapsed greedy sequences still match, while the original numeric budgets still fail.

This localizes a measured interval from encoder entry through all 24 blocks and final outer normalization. It does not identify the first differing operator, a unique kernel cause, unchanged fusion/dispatch or an absence of transient differences elsewhere. No repair, full-model qualification or learner-facing sound assessment follows.

Actual root 90135 exited 0 after 71.303557625 seconds. All 15 stages closed normally. Each runtime returned two calls and saved 12 arrays, four markers and a receipt: 17 output names per runtime, 34 total, with 2,827,264 array bytes. Native iOS PID 57994 and CLI/PGID 57984 were observed alive and then absent, with no signals or cleanup errors. This q8 observer uses request-bound OWNER identity and has no acknowledgment handshake. The dedicated simulator stayed Shutdown before and after standalone execution; no reference forward, recording, training, flag sweep, threshold change or unchanged 27-case rerun occurred.

The Mac native stage took 2.048406083 seconds with maximum sampled owned RSS 1,194,528 KiB; iOS took 2.269474083 seconds with deduplicated sampled owned RSS 1,023,648 KiB. These are whole-stage observations including loading, two calls, copying and teardown, excluding other host/service resources. They are not exact peaks, utterance latency or physical-phone measurements.

The [closed audit](../../work/native-q8-coarse-boundary-20261015/ROOT-AUDIT.json) verifies 1,295 source bindings and 1,464 file bindings. It independently recomputes all twelve byte guards, every internal and final numeric metric, lowest-ID argmax/greedy checks and both complete case results, and verifies process closure and output namespaces. The [comparison](../../work/native-q8-coarse-boundary-20261015/compare/comparison.json) preserves every observation. The next investigation can split this encoder interval using a separately prepared plan; no finer probe ran as part of this diagnostic. The original negative result, app-integration work and false production/clinical/learner eligibility remain preserved.

## Encoder-half split: rejected instrumentation

The [reviewed encoder split](../../work/native-q8-encoder-boundary-20261015/SOURCE-REVIEW.md) completed all four native calls, but **failed two of its sixteen preservation checks**. The final logits and log-posteriors passed all eight original byte guards. Encoder entry passed for both cases on both runtimes, and iOS encoder final passed for both cases. Mac encoder final changed for both cases relative to the valid coarse diagnostic.

| Failed preservation check | Maximum absolute error | Mean absolute error |
| --- | ---: | ---: |
| Mac periodic-ramp encoder final | 0.0000002384185791015625 | 0.000000002862938330849829 |
| Mac impulse encoder final | 0.0000002384185791015625 | 0.000000002951296096398437 |

Exact byte preservation was required prospectively. The small errors do not excuse the failed guards: `instrumentationValid` and `attributionPermitted` remain false, with `firstMeasuredDivergence` null globally and for both cases. The exported block11/block23 values cannot narrow the original discrepancy to either half or outer normalization. The earlier valid coarse result still supports only the full encoder interval.

The model added four complete original declarations: encoder entry, block11 residual, block23 residual and final normalized encoder. Its [independent protobuf proof](../../work/native-q8-encoder-boundary-20261015/PROBE-AUDIT.json) passes all four CopyFrom checks, both historical endpoint-declaration checks, unchanged original logits and complete non-output byte identity. Structural identity does not establish numerically noninvasive observation after optimization.

Actual root 93225 exited 2 after 103.33377475 seconds. All 15 stages closed normally: comparison exited 2 for invalid instrumentation; the other fourteen exited 0. Both workers returned two calls and released their owners normally. There are 24 saved arrays totalling 312,320 bytes, eight markers and two receipts: 17 output names per runtime. Native iOS PID 67809 and CLI/PGID 67795 were observed and then absent, without signals or cleanup errors; the dedicated simulator remained Shutdown before and after standalone execution. No new reference, recording, training, option change or numerical-limit change occurred.

The Mac native stage took 2.020830375 seconds with maximum sampled owned RSS 1,249,392 KiB; iOS took 2.5898885 seconds with deduplicated sampled owned RSS 1,023,344 KiB. These whole-stage observations include loading, calls, copying and teardown, exclude other host/service resources, and are not exact peaks, utterance latency or phone performance.

The [closed audit](../../work/native-q8-encoder-boundary-20261015/ROOT-AUDIT.json) checks 1,483 source bindings and 1,619 file bindings, independently recomputes all sixteen guards and complete numeric/discrete case results, and confirms global attribution suppression. [Independent result review](../../work/native-q8-encoder-boundary-20261015/RESULT-REVIEW.md) accepts this as a completed invalid diagnostic. The [comparison](../../work/native-q8-encoder-boundary-20261015/compare/comparison.json) retains all observations. The original score failure and this rejected experiment remain preserved; no repair or model/app qualification follows.

## Later split observation remains unverified

The subsequent encoder-thirds probe did not reach numerical comparison. Its Mac
stages closed normally, but the iOS process observer rejected native identity
after initial live admission. Worker output files and a zero CLI exit cannot establish the
missing temporal admission. The [failure audit](../../work/native-q8-encoder-thirds-20261015/FAILURE-AUDIT.json)
preserves the original failure, sources and outputs; its
[independent review](../../work/native-q8-encoder-thirds-20261015/FAILURE-AUDIT-REVIEW.md)
does not qualify the iOS run or permit narrower numerical attribution.

Separate no-model observer controls also remain failed. The latest selected-row
control passed 24 metadata tests but rejected a non-Z process row whose command
display had changed from the admitted full path to a parenthesized short name.
Natural cleanup subsequently observed a zombie and actual absence with CLI0,
an empty owned process group and no signals or cleanup errors. That closure does not repair
the failed monitor or identify the earlier iOS failure's cause. The
[control failure review](../../work/native-q8-observer-selection-20261015/CONTROL-FAILURE-REVIEW.md)
recommends independently bound process-exit evidence rather than broader command
exceptions. No new model comparison ran after this control. The original q8
candidate remains withheld, and the valid coarse encoder interval remains the
last admitted localization.
