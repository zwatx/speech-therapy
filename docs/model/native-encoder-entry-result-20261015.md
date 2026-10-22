# Native encoder-entry result — October 15, 2026

The new isolated encoder probe **fails at the positional-embedding output,
before attention**. Both fixed inputs fail all three exposed native/reference
comparisons. Backend/converter and trace comparisons remain exact. This narrows
the earliest exposed mismatch to the positional module; it does not yet identify
convolution, trimming, activation or compiler fusion as the cause.

The [frontend prefix passed](native-frontend-prefix-result-20261015.md), while
the [complete hidden model remains unqualified](native-hidden-export-result-20261015.md).
No failed candidate has been integrated into learner sound feedback.

## Fixed inputs and unchanged graph

The [prospective plan](../../work/native-encoder-entry-20261015/PLAN.json)
selects the same LCG-noise and zero controls in that order, using their exact
saved **backend** projected tensors from the passing frontend reference. Each
input is finite FP32 `[1,199,1024]`, 815,104 bytes. Native projected outputs were
not substituted. The retained sampleCount=64000 identifies each original
synthetic waveform; this diagnostic receives activations, not waveform samples.

The [Python probe](../../work/native-encoder-entry-20261015/encoder_probe.py)
uses the unchanged learned positional module, residual addition/dropout, and
actual first stable-layer-norm encoder block. It preserves the original all-valid
padding-zeroing and eager additive-mask path. The outer encoder norm is excluded
because this model applies it after all 24 blocks. A converter wrapper registers
only the positional module, dropout, first block and original config.

Backend Torch 2.8.0 and converter Torch 2.7.0 use the same checkpoint,
Transformers 4.57.6, NumPy 2.2.6, CPU/eager FP32 and two threads. Coremltools 9
exports a new FP32/iOS17 ML Program with `skip_model_load=True`. The new
[Swift worker](../../work/native-encoder-entry-20261015/NativeEncoderEntryWorker.swift)
executes it on this Mac with CPU_ONLY and owned input/retained output buffers.
Python never loads or predicts a Core ML model. This is not simulator evidence.

## Actual numerical result

Each of the six pairs in the
[comparison](../../work/native-encoder-entry-20261015/compare/comparison.json)
must meet the unchanged maximum/mean limits `1e-3/1e-4`.

| Input | Output | Maximum error | Mean error | Result |
| --- | --- | ---: | ---: | --- |
| LCG noise | Position embeddings | 3.035736084 | 0.02771252086 | Fail |
| LCG noise | Encoder entry | 3.035736084 | 0.02771252057 | Fail |
| LCG noise | First block | 5.749988556 | 0.05190570000 | Fail |
| Zeros | Position embeddings | 2.241080284 | 0.02425025479 | Fail |
| Zeros | Encoder entry | 2.241081238 | 0.02425025362 | Fail |
| Zeros | First block | 4.579914093 | 0.04938629830 | Fail |

All six converter/backend and all six trace/converter comparisons have exactly
zero measured error, meeting their respective `1e-4/1e-5` and `1e-5/1e-6` limits.
Two explicit reference forwards, two converter forwards and two trace checks
ran; trace construction also evaluates the wrapper outside those counters.

A separate [closed-output location analysis](../../work/native-encoder-entry-20261015/positional-error-location.json)
found that exactly 63 positional-output frames exceed the maximum-error limit
for each input: zero-based frames 1 through 63. Frame 0 and frames 64 through
198 meet that maximum limit. This pattern informs the next diagnostic; it does
not prove a padding bug or change the all-output acceptance rule. Encoder-entry
errors approximately propagate the positional errors, with small rounding
differences; they are not all numerically identical.

## Execution and verification

The [root terminal record](../../work/native-encoder-entry-20261015/ROOT-TERMINAL.json)
reports complete=true, comparisonPassed=false and fullModelQualified=false.
Actual root session 26694 exited **2** after 33.859610208 seconds, preserving a
completed negative result. Swift compilation, references, conversion, Core ML
compilation and native execution exited 0; comparison exited 2. All six recorded
owned process groups closed without remaining members, signals or cleanup errors.

The [transport check](../../work/native-encoder-entry-20261015/native-transport-check.json)
verifies two returned calls, six output files, four exact invocation/return
markers, an eleven-file output namespace and normal worker exit separately
from numerical acceptance. Compiler evidence binds the fresh package, compiled
copy, source, tools and immediately captured binary. The
[root audit](../../work/native-encoder-entry-20261015/ROOT-ACTUAL-PIN-AUDIT.json)
rehashed 742 unique bound source/runtime/checkpoint/reference/export/native
files successfully after execution. The package totals 83,957,241 bytes.

The largest sampled owned-group RSS was 1,762,224 KiB in conversion; native
execution sampled 120,976 KiB. Sampling excludes resources outside owned groups
and is not an exact high-water mark or phone-memory estimate. Monitoring
includes bounded query and cleanup overhead.

Seven [focused validation tests](../../research/audio-head/test_native_encoder_entry.py)
and three Python compilation checks passed. Independent Astra
[source review](../../work/native-encoder-entry-20261015/SOURCE-REVIEW.md) and
[closed-result review](../../work/native-encoder-entry-20261015/RESULT-REVIEW.md)
found no blocking issue for this diagnostic and reporting its failure.

## Next correction boundary

The [next diagnostic](../../work/native-encoder-entry-20261015/NEXT-DIAGNOSTIC.md)
splits the unchanged positional module into convolution, its real padding trim,
and its real activation. Their output lengths are 200, 199 and 199 frames. It
uses the same saved backend projected inputs and compares the isolated backend
activation output with the saved positional reference before native conversion.
This is a proposed diagnostic, not an observed correction.

Reduced graphs can compile differently, and later layers can amplify errors.
The original full-model failure remains preserved; any correction must pass its
original complete suite and limits. No weights, activation definitions,
thresholds, cases or denominators changed, and no automatic retry occurred.
No recordings, reserved study data, simulator/media actions, signing/account
changes or uploads were involved. Learner, clinical and production eligibility
remain false; native q8 CTC, occurrence features, retained heads and app
integration remain separate work.
