# Public CTC head: bounded native engineering screen — October 24, 2026

The new pure Swift public-head calculation passes all 32 same-input comparisons
against Torch. The composed screen passes 23 of 24 comparisons and **fails its
fixed overall gate**. This route remains unqualified and has no learner caller.
No diagnosis or sound-correctness conclusion follows from these generated inputs.

## Implemented component

[`NativeCTCProjection.swift`](../../apps/ios-learner/Sources/Assessment/NativeCTCProjection.swift)
accepts finite FP32 weights `[392,1024]`, bias `[392]` and 1–199 hidden rows.
It accumulates exact FP32 operand products in Double, casts each completed logit
to Float, and computes shifted full-vocabulary log-softmax. It preserves every
supplied row, including padded rows and blank ID 0. Cancellation propagates
without returning a partial output. It supplies arithmetic only: resource loading,
decoding, valid-frame selection and eligibility belong to future callers.

Four actual generated XCTest methods passed in a standalone Mac harness. They
cover orientation/bias, distinct rows, full-vocabulary normalization with huge
common offsets, malformed/nonfinite inputs, overflow and cancellation. The first
harness failed to compile because its XCTest setup was wrong; that failure is
retained. Only the harness was corrected. The same production arithmetic source
was subsequently compiled and executed on Mac and an owned iOS simulator.

## Fixed source and execution

The public source is `facebook/wav2vec2-lv-60-espeak-cv-ft`, revision
`ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`. Restricted weights-only deserialization
extracted only `lm_head.weight` and `lm_head.bias`; no model constructor or encoder
forward ran. Weight SHA256 is
`e1356ef11c3d14cd5ee065691e18810cca1b5af3aa48310222a78612f848e3f3`;
bias SHA256 is
`af81a53447bacec190cd5c83ccb9d4be64c1657b5999f2fe30f13d476182bdde`.

The screen reused eight original saved hidden matrices for generated
`periodicRamp-L1600` and `impulse-L1600`: unpadded and padded reference outputs,
plus padded Mac and iOS outputs. Each has four valid frames; padded inputs retain
all 199 rows. Eight Torch head evaluations supplied references. Four Mac and four
iOS native evaluations used the reference-padded and respective native-padded
inputs. No acoustic model was rerun and no private retained head was read.

Both native workers returned all calls and closed cleanly. The owned simulator
was actually Shutdown after cleanup. The protected simulator was observed through
device lists only. No microphone, camera, physical phone, signing/account change,
recording upload or external message was involved.

## Measured outcome

Targets were fixed before outputs: implementation maximum `1e-4`, mean `1e-5`;
composed maximum `1e-3`, mean `1e-4`. These are engineering stop targets, not
validated mathematical, acoustic or clinical tolerances. Each case/output/scope
is evaluated independently.

| Comparison | Passed | Outcome |
| --- | ---: | --- |
| Native versus Torch on identical reference/native input bytes | 32/32 | Pass |
| Native on native hidden versus Torch on original reference hidden | 23/24 | Fail |
| Entire fixed screen | 55/56 | Fail |

The sole failure is iOS, `periodicRamp-L1600`, composed full-199-row log
probabilities: maximum `0.0012874603271484375`, mean
`0.0000362970569276843`, RMS `0.00012325466194988222`. Its worst coordinate is
`[0,7,1]`, beyond the four valid rows. All prospectively separate valid-prefix and
original-unpadded comparisons pass. That distinction does **not** remove the
full-row failure, change the gate, establish a cause or qualify a masked route.

The comparator admitted exactly 42 FP32 arrays / 15,292,576 bytes, completed all
56 comparisons and 16 separately counted unsigned Double sensitivity products,
and rechecked its 20 declared source/runtime bindings. Its completed failure
returned exit 2; the owning process closed normally without signals or remnants.
No retry, refit, threshold change or rescue run occurred. Root postchecks verified
all 164 comparison bindings, plus the earlier 59 native bindings, 16 native output
artifacts and 16 private input/source copies.

Arithmetic envelopes remain explicitly `conditionalUnproven`. No observed input
or output subnormals and no exceeded conditional logit envelopes establish neither
intermediate arithmetic policies nor a total log-probability error theorem.
Sampled memory observations and declared source pins do not establish full
implicit runtime/OS closure or physical-device performance.

## Consequence and evidence

Keep this implementation available as an isolated, tested arithmetic component.
Do not connect it to learner scoring, replace the retained research recipe, claim
full-model parity or reopen the generic q8 checkpoint ladder. The original q8
5-pass/22-fail result remains WITHHELD. A future route needs an independently
specified integration/resource/lifecycle contract and relevant broader evidence;
this two-case screen is not that qualification.

Actual [comparison result](../../work/native-public-head-screen-20261024/comparison-v1/RESULT.json),
[root postcheck](../../work/native-public-head-screen-20261024/COMPARISON-POSTCHECK.json),
[native result review](../../work/native-public-head-screen-20261024/NATIVE-RESULT-REVIEW.md)
and [actual comparison review](../../work/native-public-head-screen-20261024/COMPARISON-RESULT-REVIEW.md)
retain the finite scope and failures. The task directory also preserves source
plans, call markers, runtime closure records and the failed first test harness.
