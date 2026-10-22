# Native positional split result — October 15, 2026

The mismatch already appears in the **native positional convolution output,
before trimming or activation**. Both generated controls fail all three exposed
output comparisons. This identifies the earliest tested failing boundary; it
does not establish which converter/compiler/runtime behavior causes the error.

This follows the [passing frontend](native-frontend-prefix-result-20261015.md)
and [failing encoder-entry probe](native-encoder-entry-result-20261015.md).
The complete hidden model remains unqualified for app integration.

## Unchanged module and references

The [fixed plan](../../work/native-positional-split-20261015/PLAN.json) uses
the exact saved backend projected tensors for LCG-noise and zero controls,
each FP32 `[1,199,1024]`. The [Python probe](../../work/native-positional-split-20261015/positional_probe.py)
calls the original positional module's parametrized convolution, real padding
trim and real GELU activation. It exposes frame-major outputs of 200, 199 and
199 frames, all width 1024. Kernel 128, internal padding 64, groups 16, stride
one, dilation one and weight-normalization dimension two remain unchanged.

No attention block is evaluated. The prior all-valid padding-zeroing is a no-op
on these saved inputs and is explicitly omitted. Both backend activation outputs
match the saved encoder positional references with exactly zero error. Thus the
isolated backend boundary reproduces the preceding diagnostic.

Backend Torch 2.8.0 and converter Torch 2.7.0 use the same checkpoint,
Transformers 4.57.6, NumPy 2.2.6 and CPU/eager FP32 with two threads.
Coremltools 9 exports a fresh FP32/iOS17 ML Program with `skip_model_load=True`.
The [Swift worker](../../work/native-positional-split-20261015/NativePositionalSplitWorker.swift)
owns its input, retains all three returned arrays before copying, and executes
on this Mac with CPU_ONLY. Python does not load or predict a Core ML model.
These are native Mac checks, not iOS simulator or phone evidence.

## Actual result

Every pair in the [comparison](../../work/native-positional-split-20261015/compare/comparison.json)
must meet the unchanged maximum/mean absolute-error limits `1e-3/1e-4`.

| Input | Output | Maximum error | Mean error | Result |
| --- | --- | ---: | ---: | --- |
| LCG noise | Convolution | 6.816350937 | 0.05745005615 | Fail |
| LCG noise | Trimmed | 6.816350937 | 0.05773868228 | Fail |
| LCG noise | Activated | 3.035736084 | 0.02771252086 | Fail |
| Zeros | Convolution | 2.699400187 | 0.04478360111 | Fail |
| Zeros | Trimmed | 2.699400187 | 0.04500858375 | Fail |
| Zeros | Activated | 2.241080284 | 0.02425025479 | Fail |

All six converter/backend comparisons and all six trace/converter comparisons
have exactly zero measured error. Their limits remain `1e-4/1e-5` and
`1e-5/1e-6`. Two explicit reference, two converter and two trace-check forwards
ran; trace construction also evaluates the wrapper outside those counters.

The [closed-output location analysis](../../work/native-positional-split-20261015/error-location.json)
finds exactly 63 frames above the maximum-error limit for every exposed output
and both controls: zero-based frames 1–63. Other frames meet that maximum
criterion. Native activated output bytes also exactly match the earlier native
encoder positional output bytes for both controls. This reproduces the failure
across the two reduced graphs; it is not proof of a particular padding kernel bug.

## Closure and verification

Actual root session 74127 exited **2** after 54.528399166 seconds. Its
[terminal record](../../work/native-positional-split-20261015/ROOT-TERMINAL.json)
reports complete=true, comparisonPassed=false and fullModelQualified=false.
Swift compilation, references, conversion, Core ML compilation and native
execution exited 0; comparison exited 2. All six owned process groups closed
without remaining members, signals or cleanup errors.

The [transport check](../../work/native-positional-split-20261015/native-transport-check.json)
verifies two returned native calls, six files, four exact invocation/return
markers and the eleven-file output namespace, plus normal exit and teardown.
Compiler evidence binds the source, tools, package, compiled copy and immediately
captured worker binary. Root's [pin audit](../../work/native-positional-split-20261015/ROOT-ACTUAL-PIN-AUDIT.json)
rehashed 759 unique bound source/runtime/checkpoint/reference/export/native
files successfully. The package totals 33,562,624 bytes.

Largest sampled owned-group RSS was 1,756,032 KiB in conversion; native execution
sampled 61,776 KiB. These are neither exact high-water marks nor host-wide or
phone-memory measurements. Monitoring includes bounded query/cleanup overhead.

Seven [focused validation tests](../../research/audio-head/test_native_positional_split.py)
and three Python compilation checks passed. Independent Astra
[source review](../../work/native-positional-split-20261015/SOURCE-REVIEW.md) and
[result review](../../work/native-positional-split-20261015/RESULT-REVIEW.md)
found no blocking issue for this bounded diagnostic and reporting its failure.
No weights, activation definitions, thresholds, cases or denominators changed;
no automatic retry occurred. No recordings, reserved study data, simulator/media
actions, signing/account changes or uploads were involved.

## Concrete correction candidate

The [next candidate](../../work/native-positional-split-20261015/NEXT-CORRECTION.md)
adds explicit symmetric zeros before a zero-internal-padding convolution using
the same parametrized weights and bias, followed by the original trim and GELU.
It must compare directly with these original references in both Torch runtimes
and native execution. An exported structural gate must show connected explicit
zero padding to width 327 and a valid grouped convolution producing 200 frames.
This is a proposed equivalent lowering, not an observed fix or kernel diagnosis.

Any successful reduced candidate still needs the original complete-model suite
and limits. Native q8 CTC, occurrence features, retained heads and app integration
remain separate work; learner, clinical and production eligibility stay false.
