# iOS integrated hidden-feature verification — October 15, 2026

The complete three-program hidden-feature chain passes all54 original full-output and valid-prefix comparisons across27 generated cases in an arm64 iOS simulator executable. All81 native predictions returned with verified model teardown and normal process closure. This verifies the hidden component on the dedicated iOS26.5 simulator; the separate [iOS q8 score mismatch](native-ios-q8-result-20261015.md) and complete app model integration remain unresolved.

The test uses the unchanged frontend, positional model with externally materialized padding and encoder-body packages from the [passing Mac composition](native-integrated-hidden-result-20261015.md). Their sizes are18,972,623,33,562,366 and1,209,494,844 bytes:1,262,029,833 bytes total. All three were freshly compiled for iOS with deployment minimum17.0. No Mac compiled model was substituted. The new Swift worker changes transport and process observation only; it preserves the exact feature, masking, physical padding, encoder, stride-copy, lifetime and output logic.

## Preserved pre-inference failure and corrected copy boundary

Original root15072 exited1 after68.398962959 seconds. Its eight stages closed normally, including the Swift build and all three iOS model compilations. The root copy wrapper then passed an absolute saved normalized-input pin to the unchanged copy primitive, which requires relative paths. It rejected the first source before creating an input file. No native worker was launched, no prediction was made and no numerical comparison ran. This remains a failed verification; it does not establish a model-loading failure.

The [failure audit](../../work/native-ios-hidden-integrated-20261015/FAILURE-AUDIT.json) verifies2,403 source bindings and2,478 file bindings, including the exact compiled trees and executable, and confirms the executable was absent at audit. [Independent failure review](../../work/native-ios-hidden-integrated-20261015/FAILURE-REVIEW.md) confirms the cause and conditional artifact reuse. Original sources, receipts, outputs and failure status remain unchanged.

A [separately reviewed continuation](../../work/native-ios-hidden-admission-20261015/SOURCE-REVIEW.md) normalizes only the path of a trusted frozen source pin before calling the same copy primitive. Expected size and SHA stay unchanged, and canonical regular single-link source identity is checked before and after copying. Six focused filesystem tests passed, covering absolute and relative inputs, wrong hashes/sizes, absent frozen mappings, symlinks/aliases, hard links, nonregular sources and preservation of existing destinations. The continuation reuses the exact saved iOS executable and all three compiled trees. It makes no additional Swift or Core ML compilation, conversion, Python model forward or reference generation.

## Native schedule and numerical result

Actual root42731 exited0 after125.009392875 seconds. All five stages closed normally: copy checks, device-state observation, native inference, comparison and final device-state observation. Each of the27 saved normalized inputs passes through the actual frontend, physical-padding positional model and full24-layer encoder body, with no saved teacher intermediate injected between models. Invalid projected rows become positive zero before the unchanged64-column borders; the original frame mask and later invalid-query behavior remain preserved.

All81 committed/returned marker pairs,108 saved arrays and the receipt form the exact271-file output namespace. Each array is FP32[1,199,1024],815,104 bytes. All27 full199-frame outputs and all27 valid prefixes independently pass the original maximum1e-3/mean1e-4 limits. Boundary diagnostics remain separate from acceptance.

| Acceptance branch | Largest absolute error | Largest case mean absolute error |
| --- | ---: | ---: |
| Full padded output | 0.00043487548828125 | 0.0000025604318017349317 |
| Valid unpadded prefix | 0.000040471553802490234 | 0.000001853867605840339 |

The original [comparator](../../work/native-hidden-integrated-20261015/integrated_probe.py) and its numerical functions are unchanged; its [comparison result](../../work/native-ios-hidden-admission-20261015/compare/comparison.json) records the checks above. It accepts accurate new worker-source pins directly, so no source-identity adapter or threshold override was introduced. The new parent separately enforces the reviewed worker hash, saved binary identity, all three actual iOS compile histories and exact copied model trees.

The [closed independent audit](../../work/native-ios-hidden-admission-20261015/ROOT-AUDIT.json) verifies2,491 source bindings and2,884 file bindings. It recomputes all54 acceptance metrics from saved FP32 bytes using independent Double arithmetic, rebuilds the physical padding and frame masks, and checks every input, array, marker, model tree and process receipt. Its1e-15 check concerns agreement of independently summed means only; acceptance still uses exactly1e-3/1e-4.

## Lifecycle, resources and remaining integration

The parent observed native PID40315 and CLI/PGID40303, acknowledged the exact request-bound identity before model loading, and verified both were absent afterward. There were no cleanup signals or errors. The dedicated simulator remained Shutdown before and after standalone execution. The native stage took55.869442959 seconds, including loading, all81 predictions, validation, copying and teardown. Maximum sampled owned-process RSS was2,453,744KiB. These are suite measurements, excluding unrelated Core ML/host services; they are not exact peak memory, per-utterance latency or physical-phone performance. Deployment minimum17.0 is not execution on an iOS17 runtime.

The [separate iOS feature/head check](native-ios-head-readiness-20261015.md#full-ios-feature-and-retained-head-comparison) also passes on saved Mac acoustic inputs. These component results do not compose into a complete native app assessment by themselves: q8 numerical parity, packaging, integration and end-to-end lifecycle/performance still need work. The1.26GB package footprint remains a practical issue for mobile delivery. No real-speech correctness, effective correction or clinical validity is established; production, clinical and learner eligibility stay false. No signing/account settings, recording uploads, consumed study or sealed reserve changed.
