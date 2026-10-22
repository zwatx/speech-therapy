# Native hidden-feature padding check — October 15, 2026

All **18 generated cases passed** a prospective comparison of the actual
backend's variable-length hidden features with a fixed-four-second padded
candidate. This resolves one input-representation question before a new native
encoder export. It does not verify Core ML output, the complete native model,
speech accuracy or pronunciation feedback.

The [source audit](../../work/native-model-next-step-20261015/AUDIT.md) found that
the old converter exposed 392-way CTC logits, while the actual backend also needs
a separate 1,024-wide hidden-state stream. The converter's reference used padded
inputs; the backend's unchanged `PhoneticEncoder` uses the actual input length.
The previous [Swift transport observation](native-input-interface-diagnostic-20261013.md)
does not answer that numerical compatibility question and retains its original
verification timeout and incomplete converter provenance.

## What ran

The new [focused checker](../../research/audio-head/check_native_hidden_padding.py)
uses the existing backend encoder directly, without modifying it. Both branches
use the same locally cached FP32 checkpoint and processor. The reference calls
`PhoneticEncoder(samples)`; the candidate pads to 64,000 samples with an attention
mask and retains only the valid hidden frames. There is no Core ML conversion,
CTC decoding, alignment, head prediction, audio-file input or cohort input.

The prospective [plan](../../work/native-hidden-padding-20261015/execution/plan.json)
was written before framework imports and model forwards. Its 28 bindings cover
the checker, recipe, old numerical-policy source, static local import closure,
interpreter, checkpoint artifacts, package metadata and relevant Transformers
sources. Actual imported versions were Torch 2.8.0, Transformers 4.57.6 and NumPy
2.2.6, using CPU Float32/eager attention and two intra-op threads. Actual inter-op
threads were 16; that setting was observed, not changed. This is the backend
environment, distinct from the old converter's Torch 2.7.0 environment.

Six existing deterministic PCM16 patterns—zeros, constant, impulse, alternating,
periodic ramp and seeded LCG noise—were fixed at 1,600, 16,000 and 64,000 samples.
One model load served **36 sequential backbone forwards**, one per branch per
case. The six full-length pairs were controls. Normalized valid prefixes matched
exactly; masks, zero tails, shapes, Float32 types and finite values were required.
Only the corresponding 4, 49 or 199 valid frames × 1,024 hidden coordinates were
compared. No vocabulary argmax or CTC-collapse rule was applied to hidden features.

Each case had to meet maximum absolute error ≤ **1e-4** and mean absolute error
≤ **1e-5**. These are the existing converter wrapper's engineering error budget,
prospectively applied to this new hidden-boundary check. They are not speech or
clinical thresholds. A failing case could not be replaced, averaged away or
rescued by changing limits. Whole-clip pooled differences were recorded only as
observations; pooling could not override a failed hidden frame.

## Observed result and closure

The [root verification](../../work/native-hidden-padding-20261015/verification.json)
binds all 18 per-case receipts and the exact plan, result, launch, ownership and
terminal records. The [worker result](../../work/native-hidden-padding-20261015/execution/result.json)
reports complete=true, comparisonPassed=true, 36 completed forwards and unchanged
pins. Root independently rehashed all 28 plan bindings and matched each saved
case receipt to the final result. All 18 cases and all six full-length controls
passed; all preprocessing comparisons were exact.

| Measurement | Observed |
| --- | ---: |
| Largest per-case maximum absolute hidden error | 6.258487701416016e-6 |
| Largest per-case mean absolute hidden error | 3.260278731431754e-7 |
| Checker interval after preflight | 9.835770083 s |
| Enclosing launcher wall time | 11.422538250 s |
| Largest sampled aggregate worker-group RSS | 1,782,112 KiB |
| Successful resource samples | 41 |

The [terminal record](../../work/native-hidden-padding-20261015/terminal.json)
records worker 81593 exiting 0, no termination signals or cleanup errors and an
empty final owned-process-group query. The root command session 89811 completed
with exit 0. No job remains active. The 240-second monitoring deadline allows
bounded query/cleanup overhead; the 8 GiB RSS envelope is sampled, not a hard
instantaneous memory cap. The recorded memory is not phone memory or an exact
high-water mark. The checker interval starts after its metadata/checkpoint
preflight; the enclosing launcher measures the wider process interval. No
automatic retry or prior converter rerun occurred.

Five [focused unit tests](../../research/audio-head/test_native_hidden_padding.py)
passed: shape/dtype and nonfinite rejection, rejection of frame errors hidden by
pooling, independent mean-error enforcement, and exact-array/frame-geometry
controls. Python compilation checks passed for the checker, tests and launcher.
These tests do not substitute for the actual 36 forwards above.

Independent Astra [source and launcher review](../../work/native-hidden-padding-20261015/SOURCE-REVIEW.md)
cleared the frozen implementation after two ownership/cleanup findings were
repaired before execution. The direct backend import was inspected and found to
perform no corpus reads at import time. Source clearance is distinct from the
actual numerical result.

## Next implementation boundary

This passing screen supports preparing a **new hidden-output export**, with
checkpoint and conversion-source bindings saved before prediction, and comparing
its native outputs to the unchanged backend. The result covers these three
generated lengths; convolution-transition lengths and the rest of the permitted
range still need coverage before a full-range native parity claim.

The quantized q8 ONNX CTC stream remains a separate requirement. Replacing it
with FP32 CTC logits would change alignment and the 13 scalar features. The full
1,037-feature occurrence pipeline, retained transforms/heads and app lifecycle
integration remain additional native boundaries. The old logits-only artifact
has not been qualified by this new test.

Even complete engineering parity would reproduce the existing research rating
pipeline. Independent produced-phone references, appropriate validation and
effective correction evidence remain necessary for sound-correctness findings.
Learner-feedback, clinical and production eligibility remain false. No private
recordings, reserved studies, simulator/device operations, account/signing
changes or recording uploads were involved in this checkpoint.
