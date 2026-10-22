# Native hidden export result — October 15, 2026

The new hidden-feature model **runs through native Core ML, but fails numerical
parity**. All 27 native calls returned with finite, correctly shaped outputs;
every case exceeded the unchanged error limits. This candidate must not replace
the backend encoder or be integrated as a qualified sound-analysis model.

This is a complete negative engineering result. It preserves the separate
passing [HF padding screen](native-hidden-padding-verification-20261015.md).
It does not repair or qualify the older logits-only converter artifact, and it
adds no speech-accuracy, pronunciation or clinical evidence.

## Implemented boundary and checks

The [new Python tool](../../research/audio-head/native_hidden_export.py) separates
reference generation, conversion and comparison. The
[fixed prospective plan](../../work/native-hidden-export-20261015/PLAN.json)
uses six deterministic PCM patterns at 1,600, 16,000 and 64,000 samples, plus LCG
noise immediately before, at and after three convolution-frame transitions:
1,679/1,680/1,681, 16,079/16,080/16,081 and 63,759/63,760/63,761. All 27 cases
are required. The nine extra cases extend boundary coverage; they do not prove
every permitted length.

The actual backend environment uses Torch 2.8.0; the existing Core ML converter
environment uses Torch 2.7.0. Both use Transformers 4.57.6 and NumPy 2.2.6. The
tool therefore directly checks their outputs rather than assuming equivalence:

1. The unchanged backend `PhoneticEncoder` produces unpadded references. Its
   same processor/backbone produces padded references and exact normalized inputs.
2. The Torch 2.7 wrapper exposes only `.wav2vec2(...).last_hidden_state`. It
   checks full padded outputs and valid prefixes directly against both backend
   references. Independently checked tracing retains tensor-valued sample counts.
3. Coremltools 9 exports a new FP32 ML Program with `skip_model_load=True`.
   Loading, checkpoint, source/runtime, trace and conversion provenance are saved
   before native prediction. Python never loads or predicts a Core ML model.
4. A new [Swift worker](../../work/native-hidden-export-20261015/NativeHiddenWorker.swift)
   loads the freshly compiled package on this Mac using CPU_ONLY. Owned input
   arrays, providers, returned arrays and copied bytes remain retained through
   synchronous execution and teardown. Output is Float32 `[1,199,1024]`;
   logical indexing respects strides. This is Mac native execution, not an iOS
   simulator or physical-device run.
5. Native full outputs are compared directly with the backend padded references;
   valid prefixes are compared directly with the backend unpadded references.
   No CTC decoding, hidden-coordinate argmax, pooling rescue or head prediction
   enters acceptance.

All learned weights, numerical budgets and cases stayed unchanged after results.
No refit, substituted case, threshold widening or automatic retry occurred.

## Actual numerical result

The [comparison result](../../work/native-hidden-export-20261015/compare/comparison.json)
contains every native case and both required comparisons. Bounds apply to each
comparison, rather than averaging success across cases.

| Boundary | Passed / required comparisons | Largest maximum absolute error | Largest mean absolute error | Fixed max / mean limits |
| --- | ---: | ---: | ---: | --- |
| Backend unpadded vs padded valid prefix | 27 / 27 | 9.059906006e-6 | 3.422874670e-7 | 1e-4 / 1e-5 |
| Converter Torch 2.7 vs both backend references | 54 / 54 | 9.059906006e-6 | 3.422874670e-7 | 1e-4 / 1e-5 |
| Trace vs converter wrapper | 27 / 27 | 0 | 0 | 1e-5 / 1e-6 |
| Native full output vs padded backend | **0 / 27** | 3.884114087 | 0.01924375851 | 1e-3 / 1e-4 |
| Native valid prefix vs unpadded backend | **0 / 27** | 0.1624163389 | 0.005800196308 | 1e-3 / 1e-4 |

The largest full-output difference occurs for periodicRamp-L1600; the largest
valid-prefix maximum occurs for lcgNoise-L64000. All six full-length controls
also fail. Consequently, a masked-tail or padding-only explanation is
insufficient. The exact cause remains unestablished.

Reference generation completed 54 explicit coverage forwards. The converter
completed 27 wrapper and 27 trace verification forwards; tracing itself performs
additional execution not included in that 54-forward coverage counter. These
are engineering comparisons of generated inputs, not independent speech examples.

## Execution, provenance and cleanup

The [root terminal record](../../work/native-hidden-export-20261015/ROOT-TERMINAL.json)
reports complete=true and comparisonPassed=false. Root command session 87820
actually exited **2**, matching a completed numerical failure. The six stages
closed as follows:

| Stage | Actual exit | Enclosing wall seconds |
| --- | ---: | ---: |
| Swift compilation | 0 | 4.718467417 |
| Backend references | 0 | 13.064659541 |
| Converter/trace/export | 0 | 26.261823833 |
| Native package compilation | 0 | 0.317999625 |
| Native worker | 0 | 10.807288708 |
| Numerical comparison | **2** | 5.263684291 |

The whole enclosing run took 62.877818416 seconds. Native worker 91001 returned
27 calls. The [transport check](../../work/native-hidden-export-20261015/native-transport-check.json)
binds all 27 output files, 54 exact invocation/return markers, the request, final
receipt, compiled tree and worker binary. The exact native output namespace has
82 files. Normal exit, final status=complete and acknowledged teardown were
required separately from numerical acceptance.

Each recorded owned process group was empty after its stage, with no termination
signals or cleanup errors. This is owned-group closure, not an exhaustive
host-wide compiler/service audit. The largest sampled group RSS was 2,503,024 KiB
in the native stage; it excludes resources outside those groups and is neither
an exact high-water mark nor phone memory. Prospective monitoring deadlines
include bounded query delay and cleanup overhead; the 8 GiB limit is sampled.

Root's [actual pin audit](../../work/native-hidden-export-20261015/ROOT-ACTUAL-PIN-AUDIT.json)
rehashed 842 unique source/runtime/checkpoint/reference/export/native artifact
files successfully after execution. The new package has three files totaling
1,262,233,459 bytes; the copied compiled model has five totaling 1,262,553,107.
The prior failed artifacts remain separate. All actual job handles are terminal.

Nine [focused validation tests](../../research/audio-head/test_native_hidden_export.py)
passed; their [saved output](../../work/native-hidden-export-20261015/unit-tests.log)
is separate from model evidence. Python compilation checks passed for the CLI,
tests and launcher. Astra's [pre-execution source review](../../work/native-hidden-export-20261015/SOURCE-REVIEW.md)
cleared the exact exporter, worker, launcher and collector. Source clearance did
not predict or override the failed numerical result.

## Next diagnostic and remaining product work

The mismatch appears after the independently passing Torch trace boundary,
within conversion or compiled native execution/copy-out; no individual operator
or runtime behavior has been identified as its cause. Static inspection of the
compiled MIL text found 32 GELU operations with EXACT modes, 57 layer-normalization
operations and no `fp16` type mentions. That does not prove runtime arithmetic or
rule out a compiler/runtime issue; it supplies no basis for blaming a particular
activation or silently rewriting learned-model behavior.

The next bounded diagnostic should expose unchanged learned frontend boundaries
on fixed full-length generated controls, separating convolution/normalization/
activation/projection from the later positional and attention stack. Its outputs
must be compared with the same backend, with the original failure retained.
A prefix diagnostic cannot qualify the failed complete model.

Native q8 CTC alignment/scalars, the full 1,037-feature occurrence pipeline,
retained heads and app integration remain separate unfinished boundaries. Even
complete engineering parity would reproduce research rating behavior; independent
produced-phone evidence is still needed for corrective pronunciation findings.
Learner, clinical and production eligibility remain false. No private recordings,
reserved-study data, simulator/device actions, microphone/playback/camera activity,
signing/account changes or recording uploads were involved.
