# External padding result — October 15, 2026

Materializing padding outside the Core ML graph **passes all six output comparisons on the two fixed generated controls**. This provides a working positional boundary for the next integrated test. The largest convolution error is close to the unchanged maximum limit; the complete hidden model remains unqualified.

The [previous explicit-padding failure](native-positional-padding-result-20261015.md), [original positional failure](native-positional-split-result-20261015.md) and [full hidden-model failure](native-hidden-export-result-20261015.md) remain preserved. No candidate has been integrated into learner sound feedback.

## Representation and reference

The [fixed plan](../../work/native-positional-materialized-20261015/PLAN.json) and [Python implementation](../../work/native-positional-materialized-20261015/materialized_probe.py) reuse the exact saved original projected inputs and original Torch 2.8 positional targets. NumPy preparation performs **zero inference forwards**, preparing two cases: LCG noise and zeros, each 64,000 samples.

Preparation transposes projected FP32 `[1,199,1024]` into the center of a positive-zero `[1,1024,327]` buffer, with 64 columns on each side. It verifies finite values, zero border bits and exact recovered center bytes, including signed zeros, against the original projected-input hash. The [Swift worker](../../work/native-positional-materialized-20261015/NativeMaterializedWorker.swift) independently checks those same properties before prediction and owns contiguous input memory.

The model consumes this buffer directly: original parametrized convolution weight and bias, kernel 128, groups 16, stride/dilation 1 and internal padding zero, followed by the original one-frame trim and GELU. There is no pad operation in the model graph. The [exported structural gate](../../work/native-positional-materialized-20261015/export/structure.json) verifies that actual connectivity, shapes and FP32 outputs. The [compiled graph inspection](../../work/native-positional-materialized-20261015/compiled-structure.json) also finds zero pads and one valid convolution with internal pad `[0,0]`. Graph metadata does not establish a unique kernel cause or runtime fusion behavior.

Converter Torch 2.7 runs the candidate twice and checks its trace twice. All six converter comparisons directly against the original Torch 2.8 targets, and all six trace comparisons against the converter, have exactly zero measured error. Trace construction has additional evaluation outside those four explicit checks. No new teacher-model forward was needed. Transformers 4.57.6, NumPy 2.2.6, CPU/eager FP32 and two threads remain fixed. Coremltools 9 uses unchanged default passes, FP32/iOS17 and `skip_model_load=True`; Python never loads or predicts with Core ML.

## Native result

All pairs pass the unchanged individual maximum/mean limits `1e-3/1e-4`, directly against the original targets in the [comparison](../../work/native-positional-materialized-20261015/compare/comparison.json):

| Control | Output | Maximum error | Mean error |
| --- | --- | ---: | ---: |
| LCG noise | Convolution | 0.0009765625 | 0.00003340150672 |
| LCG noise | Trimmed | 0.0009765625 | 0.00003350172853 |
| LCG noise | Activated | 0.0005874633789 | 0.00001556526773 |
| Zeros | Convolution | 0.0008392333984 | 0.00003043813785 |
| Zeros | Trimmed | 0.0008392333984 | 0.00003053050826 |
| Zeros | Activated | 0.0005035400391 | 0.00001338362864 |

The worst convolution maximum has only `0.0000234375` headroom, 2.34375% of the limit. Neither these passing controls nor their smaller activation errors guarantee bounded error through the remaining 24 blocks. Tolerances cannot be added or relaxed for the integrated test.

Actual root session 85683 exited **0** after 19.716234917 seconds. Its [terminal record](../../work/native-positional-materialized-20261015/ROOT-TERMINAL.json) reports complete=true, comparisonPassed=true and fullModelQualified=false. All six stage exits were zero, with empty owned process groups, no signals and no cleanup errors. This closure does not audit host-wide compiler/XPC resources.

The [transport check](../../work/native-positional-materialized-20261015/native-transport-check.json) verifies two returned native calls, six output artifacts, four invocation/return markers, the eleven-file output namespace, teardown and independently observed normal exit. Inputs, providers and all returned arrays remain alive through copying and teardown. This is Mac CPU_ONLY evidence, not simulator or phone execution.

The [post-run audit](../../work/native-positional-materialized-20261015/ROOT-ACTUAL-PIN-AUDIT.json) verified 772 unique bound files, including direct original targets, and all 49 frozen source/tool/upstream bindings. The package totals 33,562,366 bytes. Maximum sampled owned-group RSS was 1,754,352 KiB during conversion and 64,336 KiB natively; these are not exact high-water marks or phone memory measurements.

Seven [focused unit tests](../../research/audio-head/test_native_materialized_padding.py) and three Python compilation checks passed. Independent Astra [source review](../../work/native-positional-materialized-20261015/SOURCE-REVIEW.md) and [result review](../../work/native-positional-materialized-20261015/RESULT-REVIEW.md) found no blocker within this bounded reporting scope.

## Next complete-model test

The [next implementation](../../work/native-positional-materialized-20261015/NEXT-IMPLEMENTATION.md) composes the passing frontend, externally padded positional program and a new encoder-body program containing the original residual addition, dropout, all 24 stable-layer-norm blocks and final outer norm. Swift must zero invalid projected rows before materializing padding, retain that same masked tensor for the residual, and preserve later invalid-query rows.

The original 27 cases require 81 actual native calls and 54 final comparisons: every full output against its original padded reference, and every valid prefix against its original unpadded reference, all at unchanged limits. Passing the two-control boundary does not substitute for this test. Native q8 CTC, complete occurrence features, retained heads, mobile packaging and app integration remain open; these engineering checks add no pronunciation or clinical accuracy evidence.

No recordings, reserved study data, simulator/media actions, signing/account changes or uploads were used. Learner, clinical and production eligibility remain false.
