# Explicit-padding candidate result — October 15, 2026

The explicit-padding candidate **does not fix native numerical parity**. All
six native outputs are byte-identical to the preceding failed positional split.
The exported and compiled graph metadata both retain explicit padding and a
valid convolution. This result does not prove that the compiler folded padding
back into the convolution, or identify a native kernel cause.

The [original positional failure](native-positional-split-result-20261015.md)
and [complete hidden-model failure](native-hidden-export-result-20261015.md)
remain preserved. No candidate was integrated into learner sound feedback.

## Equivalent lowering and direct target

The [fixed plan](../../work/native-positional-explicit-pad-20261015/PLAN.json)
uses the same two saved backend projected inputs. The
[Python candidate](../../work/native-positional-explicit-pad-20261015/padding_probe.py)
adds 64 explicit zeros at each side of the channel-first input, then calls
`F.conv1d` with the original parametrized weight, bias, stride, dilation and
groups, using internal padding zero. The original trim and GELU remain intact.
No learned weight, weight-normalization parametrization or activation changes.

Torch 2.8 runs the **original** module and screens all outputs against the
saved original positional references. The candidate runs in converter Torch
2.7 and its trace; native results and converter outputs compare **directly**
with those old Torch 2.8 references. This does not claim a Torch 2.8 candidate
forward. There are two original reference, two candidate converter and two
trace-check forwards; trace construction has additional execution outside
those counters. Both environments retain Transformers 4.57.6 and NumPy 2.2.6,
CPU/eager FP32 and two threads.

Coremltools 9 uses its unchanged default pass pipeline, FP32/iOS17 and
`skip_model_load=True`. The bound [structural receipt](../../work/native-positional-explicit-pad-20261015/export/structure.json)
derives from the actual converted MIL: connected constant-zero padding produces
`[1,1024,327]`, feeding one valid, zero-internal-padding grouped convolution
with kernel 128 and output `[1,1024,200]`. The real trim and EXACT GELU produce
199 frames. The graph passed this gate before compilation/native admission.

The [compiled metadata inspection](../../work/native-positional-explicit-pad-20261015/compiled-padding-inspection.json)
also finds one pad and one convolution, with valid padding, internal pad `[0,0]`
and groups 16. This is graph metadata, not proof of native implementation or
runtime fusion behavior.

## Actual result

Every original-backend correspondence, candidate-converter/original-reference
comparison and trace/converter comparison has exactly zero measured error.
The [native comparison](../../work/native-positional-explicit-pad-20261015/compare/comparison.json)
fails every output at the unchanged max/mean limits `1e-3/1e-4`:

| Input | Output | Maximum error | Mean error |
| --- | --- | ---: | ---: |
| LCG noise | Convolution | 6.816350937 | 0.05745005615 |
| LCG noise | Trimmed | 6.816350937 | 0.05773868228 |
| LCG noise | Activated | 3.035736084 | 0.02771252086 |
| Zeros | Convolution | 2.699400187 | 0.04478360111 |
| Zeros | Trimmed | 2.699400187 | 0.04500858375 |
| Zeros | Activated | 2.241080284 | 0.02425025479 |

Root [rehashed both sets of output bytes](../../work/native-positional-explicit-pad-20261015/native-reproduction.json)
and verified that all six candidate native outputs exactly equal the previous
failed split outputs. Identical outputs do not establish which native operation
or optimization caused them.

Actual root session 17985 exited **2** after 140.776296583 seconds. Its
[terminal record](../../work/native-positional-explicit-pad-20261015/ROOT-TERMINAL.json)
reports complete=true, comparisonPassed=false and fullModelQualified=false.
All six owned process groups closed normally, without remaining members,
signals or cleanup errors; comparison exited 2 and other stages exited 0.
The [transport record](../../work/native-positional-explicit-pad-20261015/native-transport-check.json)
verifies two returned calls, six outputs, four invocation/return markers,
the eleven-file namespace, teardown and normal native exit. The worker source
retains the input, providers and all returned arrays through copying/teardown.
This is native Mac CPU_ONLY execution, not simulator or phone evidence.

The [root audit](../../work/native-positional-explicit-pad-20261015/ROOT-ACTUAL-PIN-AUDIT.json)
rehashed 774 unique bound files, including the direct old target arrays. All
44 source/tool/upstream bindings remain current. The new package totals
33,563,086 bytes. Largest sampled owned-group RSS was 1,757,792 KiB during
conversion and 62,576 KiB natively; these exclude resources outside owned
groups and do not measure phone memory or exact high-water marks.

Seven [focused validation tests](../../research/audio-head/test_native_positional_padding.py)
and three Python compilation checks passed. Independent Astra
[source review](../../work/native-positional-explicit-pad-20261015/SOURCE-REVIEW.md) and
[result review](../../work/native-positional-explicit-pad-20261015/RESULT-REVIEW.md)
found no blocking issue for reporting this completed failure. The prospective
comparison monitoring cap was 60 seconds because this check adds provenance
hashing; actual comparison took 43.768932208 seconds. Numerical limits stayed
unchanged. No retry, case substitution, refit or activation rewrite occurred.

## Next discriminator

The [next plan](../../work/native-positional-explicit-pad-20261015/NEXT-DIAGNOSTIC.md)
supplies exact pre-padded channels as the external native input, leaving **no
pad operation in the model graph**. It can reuse existing original references;
zero borders, the transpose and recovered original-input hash must be verified.
This separates externally materialized padding from the current combined path.
It is a proposed diagnostic, not an observed fix. The full-model suite remains
required before integration.

No recordings, reserved study data, simulator/media activity, signing/account
changes or uploads were used. Learner, clinical and production eligibility stay
false; q8 CTC, occurrence features, retained heads and app integration remain open.
