# Integrated native hidden-state parity — October 15, 2026

The three-program native path **passes all 54 final comparisons across the original 27 generated cases**, at the unchanged maximum/mean limits `1e-3/1e-4`. Every full 199-frame output passes against its original padded reference; every valid prefix passes against its original unpadded reference. This establishes bounded hidden-state parity on Mac CPU_ONLY. It does not establish iOS performance, speech correctness, clinical accuracy or a complete learner-feedback model.

The [full-model failure](native-hidden-export-result-20261015.md) and subsequent [positional failures](native-positional-padding-result-20261015.md) remain preserved. The passing [external-padding boundary](native-materialized-padding-result-20261015.md) supplied the concrete correction tested here. No numerical tolerance, learned weight, activation, source reference, case or scientific threshold changed.

## Complete native path

The [original fixed plan](../../work/native-hidden-integrated-20261015/PLAN.json) partitions the unchanged model into:

1. The exact previously passing frontend package and compiled model, retaining all three outputs. Its native projected output supplies the next steps.
2. Swift-owned memory: derive valid frames using the original seven convolution kernels/strides; zero invalid projected rows to positive zero; retain that masked tensor for the residual; transpose all 199 rows into the center of a buffer with 64 positive-zero columns on either side. The exact passing positional package consumes this external buffer, with no padding operation in its graph. All three outputs remain present; activated output feeds the encoder body.
3. A separate encoder-body program: original residual addition and eval dropout, all 24 original stable-layer-norm blocks using the original dynamic eager key mask, then the final outer layer norm. There is no repeated positional convolution and no premature outer norm. Later invalid-query rows remain intact.

Every downstream native input comes from actual preceding native output and the declared Swift transformation. Saved teacher intermediates never enter this native chain. The [worker](../../work/native-hidden-integrated-admission-20261015/NativeIntegratedWorker.swift) checks all seven returned outputs per case, retains inputs/providers/results/arrays/copies through model teardown, and saves four arrays per case plus actual padding/mask hashes. Expected order, geometry, exact masking and recovered padding bytes are checked independently by the [comparison source](../../work/native-hidden-integrated-20261015/integrated_probe.py).

## Preserved inspection failure and new admission

The first integrated attempt, actual root session 20941, exited **1** after 31.600048500 seconds before any encoder-body compilation or native call. All 162 explicit converter/trace forwards and all 27 case gates had passed. The [failed structure record](../../work/native-hidden-integrated-20261015/export/structure.json) disagreed only on the frame-mask dtype display string: the inspector expected `int32`, while `var.dtype.__name__` returned `int`.

Coremltools 9 creates multiple integer classes with the Python name `int`; that name cannot distinguish widths. The actual package retained an INT32 input. The [closed failure audit](../../work/native-hidden-integrated-20261015/ROOT-CONVERTER-FAILURE-AUDIT.json) bound 1,067 unique files, the saved package and the original unsuccessful receipts. Nothing in that failed task was overwritten or relabeled as successful.

A separate [admission plan](../../work/native-hidden-integrated-admission-20261015/PLAN.json) and [inspector](../../work/native-hidden-integrated-admission-20261015/admit_saved.py) validate the exact saved package anew. Protobuf feature type INT32 and MIL tensor type INT32 are checked independently, with exact FP32 input/output shapes, all defined SSA references, all three input paths reaching hidden, and zero convolution/pad/nested-block operations. The serialized graph contains 1,414 operations. The new check also requires the old failed observation to differ only in that dtype description. It does not accept a generic `int` alias.

The [new admission receipt](../../work/native-hidden-integrated-admission-20261015/export/admission.json) records **zero new forwards and no conversion**. It byte-copies the saved encoder-body package, trace and 162 boundary files, then rechecks the historical numerical evidence using the unchanged original verifier. Its separately bound manifest identifies the original producer, failure and carried historical counters. Only the identical Swift source was recompiled to obtain a fresh persisted binary binding, followed by the first encoder-body compilation and native chain.

## Numerical result

The historical converter evidence consists of 27 local untraced/traced frontend comparisons, 27 local untraced/traced positional comparisons, and 27 untraced/traced encoder-body comparisons: 162 explicit forwards. Both complete converter paths use the exact reused frontend and positional traces; one ends in untraced encoder body, the other in its trace. Both paths pass all 54 original-reference comparisons. Their full outputs match the original padded targets exactly; worst valid-prefix maximum is `9.059906006e-6`, worst mean `3.422874670e-7`. All 189 local trace-output comparisons have zero error. Trace capture has additional evaluation outside the explicit counters; no teacher-model forward was repeated.

Final native [comparisons](../../work/native-hidden-integrated-admission-20261015/compare/comparison.json), each independently subject to maximum `1e-3` and mean `1e-4`:

| Branch | Passing cases | Largest maximum error | Largest mean error |
| --- | ---: | ---: | ---: |
| Full versus original padded | 27/27 | 0.0002937912941 | 0.000001934448700 |
| Valid prefix versus original unpadded | 27/27 | 0.00003916025162 | 0.000001887460973 |

The largest full error occurs on periodic ramp/1,600 samples; the largest valid-prefix error occurs on LCG noise/63,760 samples. The suite retains all six full-length controls and all nine frame-transition lengths. No tolerance summation, case substitution or averaged-case acceptance was used.

All 27 intermediate projected, masked-projected and positional diagnostics also pass. Their largest maximum errors are respectively `0.0001754760742`, `0.0001754760742` and `0.0006332397461`. These diagnostics are separately recorded and do not replace final acceptance.

## Execution and verification

Actual continuation root session 12900 exited **0** after 51.196393291 seconds. The [terminal record](../../work/native-hidden-integrated-admission-20261015/ROOT-TERMINAL.json) reports complete=true, comparisonPassed=true and generatedHiddenParityPassed=true; fullModelQualified remains false. All five stages exited zero and their owned process groups closed normally, without remaining members, signals or cleanup errors. This does not audit host-wide compiler/XPC resources.

The [transport check](../../work/native-hidden-integrated-admission-20261015/native-transport-check.json) verifies 81 returned calls, 108 output arrays, 162 invocation/return markers and the exact 271-file namespace, teardown and independently observed normal native exit. Native stage duration was 24.113828708 seconds for the complete fixed suite, not a user latency benchmark. Its maximum sampled owned-group RSS was 2,395,248 KiB, not exact peak or phone memory.

The three packages total **1,262,029,833 bytes**: frontend 18,972,623; positional 33,562,366; encoder body 1,209,494,844. Packaging and memory on iOS remain material work. The [post-run audit](../../work/native-hidden-integrated-admission-20261015/ROOT-ACTUAL-PIN-AUDIT.json) verified 1,573 unique bound files and all 95 frozen source/tool/prior-evidence bindings.

Seven original [partition tests](../../research/audio-head/test_native_hidden_integrated.py), five new [actual type/protobuf regression tests](../../research/audio-head/test_native_integrated_admission.py), Python compilation checks and a real-package metadata precheck passed. Independent Astra [original source review](../../work/native-hidden-integrated-20261015/SOURCE-REVIEW.md), [admission source review](../../work/native-hidden-integrated-admission-20261015/SOURCE-REVIEW.md) and [result review](../../work/native-hidden-integrated-admission-20261015/RESULT-REVIEW.md) cover their stated scopes. No unchanged Torch/conversion run was repeated to clear the metadata defect.

## Next product work

Implement the [exact q8 CTC/alignment/scalar path](../../work/native-hidden-integrated-20261015/NEXT-Q8-IMPLEMENTATION.md), preserving its distinct quantized model and preprocessing. Then join actual native q8 outputs with actual native hidden outputs, verify the complete 1,037-feature kernel, retained transforms/heads, and simulator integration/performance. Complete live Release recording/playback/mirror/manual-practice/recheck verification separately. Apple Speech permission remains denied; these tests do not repair that permission state or replace the bundled word recognizer.

Independent produced-phone references and clinical/effectiveness evidence remain external requirements before corrective findings or diagnosis claims. No recordings, participant/reserved data, simulator/media actions, signing/account changes or uploads were used here. Learner, clinical and production eligibility remain false.
