# Native frontend prefix result — October 15, 2026

The unchanged learned frontend **passes all six numerical comparisons** in a
new two-input native Core ML diagnostic. Convolution features, normalized
features and projected features each match the backend within the original
limits. The [complete hidden model still fails](native-hidden-export-result-20261015.md)
and is not qualified for app integration.

This narrows the investigation; it does not establish speech accuracy or
pronunciation correctness. Truncating a graph and exposing intermediate outputs
can change compiler optimizations, and later layers can amplify small errors.

## What ran

The [prospective plan](../../work/native-frontend-prefix-20261015/PLAN.json)
requires the exact saved normalized `lcgNoise-L64000` and `zeros-L64000` inputs
from the failed complete-model run. Each has 64,000 valid samples. The unchanged
checkpoint modules return:

- `feature_extractor(...).transpose(1,2)`: features `[1,199,512]`.
- `feature_projection(...)`: normalized features `[1,199,512]` and projected
  features `[1,199,1024]`.

The [Python probe](../../work/native-frontend-prefix-20261015/prefix_probe.py)
produces references using backend Torch 2.8.0, checks converter Torch 2.7.0
directly against those references, and separately checks its trace. Both use
Transformers 4.57.6, NumPy 2.2.6, CPU/eager FP32 and two threads. Coremltools 9
exports a fresh FP32/iOS17 ML Program with `skip_model_load=True`.

A new [Swift worker](../../work/native-frontend-prefix-20261015/NativeFrontendWorker.swift)
executes the compiled package on this Mac with CPU_ONLY. It owns the input and
retains all returned arrays before copying logical, stride-respecting values.
Python never loads or predicts a Core ML model. This is native Mac evidence,
not an iOS simulator or phone result.

## Numerical result

The [comparison](../../work/native-frontend-prefix-20261015/compare/comparison.json)
retains all six output/reference pairs. Each must independently meet maximum
absolute error `1e-3` and mean absolute error `1e-4`.

| Input | Output | Maximum error | Mean error | Result |
| --- | --- | ---: | ---: | --- |
| LCG noise | Features | 2.115964890e-6 | 7.738259234e-8 | Pass |
| LCG noise | Normalized features | 5.435943604e-5 | 1.642187914e-6 | Pass |
| LCG noise | Projected features | 7.438659668e-5 | 3.246747362e-6 | Pass |
| Zeros | Features | 2.031170879e-6 | 1.735655086e-7 | Pass |
| Zeros | Normalized features | 4.959106445e-5 | 4.026971872e-6 | Pass |
| Zeros | Projected features | 1.182556152e-4 | 6.858599955e-6 | Pass |

All six converter/backend comparisons and all six trace/converter comparisons
have exactly zero measured error. Their separate fixed max/mean budgets remain
`1e-4/1e-5` and `1e-5/1e-6`. There were two explicit reference forwards, two
converter forwards and two trace verification forwards; trace construction also
evaluates the wrapper outside these coverage counters. These are two generated
engineering inputs, not independent speech examples.

## Execution and verification

The [root terminal record](../../work/native-frontend-prefix-20261015/ROOT-TERMINAL.json)
reports complete=true, comparisonPassed=true and fullModelQualified=false.
Actual root session 43675 exited 0; its enclosing run took 24.075230875 seconds.
Swift compilation, references, conversion, Core ML compilation, native execution
and comparison all exited 0. Their recorded owned process groups closed without
remaining members, termination signals or cleanup errors.

The [transport check](../../work/native-frontend-prefix-20261015/native-transport-check.json)
verifies two returned calls, six output files, four exact invocation/return
markers and the eleven-file output namespace. Compiler evidence binds the
fresh package, compiled copy, actual worker binary, source and tools. The
[root audit](../../work/native-frontend-prefix-20261015/ROOT-ACTUAL-PIN-AUDIT.json)
rehashed 735 unique bound source/runtime/checkpoint/reference/export/native
files successfully after execution.

Largest sampled owned-group RSS was 1,804,480 KiB in conversion; native execution
sampled 147,424 KiB. These are sampled group measurements, not exact high-water
marks, host-wide accounting or phone memory. Monitoring has bounded query and
cleanup overhead.

Six [focused validation tests](../../research/audio-head/test_native_frontend_prefix.py)
and Python compilation checks passed. Independent Astra
[source review](../../work/native-frontend-prefix-20261015/SOURCE-REVIEW.md) and
[closed-result review](../../work/native-frontend-prefix-20261015/RESULT-REVIEW.md)
found no blocking issue within this scope. No automatic retry, weights change,
activation substitution or threshold adjustment occurred.

## Next boundary

The [next diagnostic](../../work/native-frontend-prefix-20261015/NEXT-DIAGNOSTIC.md)
feeds the exact saved backend projected tensors into the unchanged positional
module, encoder entry and first stable-layer-norm transformer block. That
removes frontend differences from the new diagnostic's input. It must preserve
the eager all-valid mask path and omit the outer encoder norm, which belongs
after all 24 blocks. This recommendation is not an observed result.

The failed complete graph stays preserved. A concrete correction must eventually
pass its original full suite and limits. Native q8 CTC, occurrence features,
retained heads and app integration remain separate work. No recordings,
reserved study data, simulator/media operations, signing/account changes or
uploads were used here; learner, clinical and production eligibility stay false.
