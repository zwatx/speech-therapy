# Native q8 pre-normalization observation

The new pre-normalization probe did not preserve the existing Mac final hidden
anchor. Both saved-result readers found **22 of 24** original-output byte checks
passing, with the Mac `encoderFinalAnchor` changing for both generated cases.
Instrumentation validity and diagnostic interpretation are therefore **false**.
This probe does not locate the original Mac/simulator discrepancy or establish
its cause. The original 27-case result remains **5 passing, 22 failing**, and q8
remains withheld from learner feedback.

## What actually ran

The new model appends the raw block-23 residual before final normalization. Its
original five model outputs and non-output protobuf content were preserved by
the earlier independent metadata proof. Six existing worker artifacts remain
the prefix, followed by the new residual artifact. This structural proof alone
does not establish unchanged runtime results.

Fresh Mac and simulator diagnostic workers built successfully in ten commands,
under one surviving owner, in 25.641276 seconds. Their actual reported inputs,
retained objects/PCHs and explicit linker inputs were checked against the
prospective inventory and current bytes. The independent build review was clear
for this narrow diagnostic. Exhaustive implicit Apple SDK stub selection and
full compiler/linker closure remain explicitly unproven.

Exactly one invocation per runtime processed the same two original generated
controls, `periodicRamp-L1600` and `impulse-L1600`: four fresh native calls total.
Mac closed normally in 1.711705 seconds; the simulator observer closed normally
in 3.752109 seconds with bound EXIT, fresh absence and no signals, cleanup errors
or remaining owned processes. The dedicated SE3/iOS26.5 simulator was available
and Shutdown before and after the invocation. All 28 arrays, 377,856 bytes and
38 output names were retained and independently checked. These timings and
sampled owned-process memory measurements are not app or physical-phone
performance measurements.

## Preserved controller failure and saved-only reconciliation

The original controller exited unsuccessfully after 25.168722 seconds. Its
post-observer check passed an immutable `MappingProxyType` to a guard requiring
an exact `dict`, producing `ValueError: Missing bindings`. Both native workers
had already returned normally. The failed controller still reports only its
two admitted Mac calls; its incomplete ROOT and absent aggregate publications
remain unchanged.

A separate generated-file check reproduced the exact mapping failure without a
model call. Converting a synthetic map to `dict` passed the type check and still
rejected changed file bytes. This establishes a narrow future call-site fix;
the frozen failed controller was not edited or rerun.

Two separately reviewed saved-only readers reconstructed the actual four calls
from their requests, markers, receipts and normal lifecycle evidence. They
validated the original source/build/observer bindings and exact native file
namespaces, then independently computed the 24 same-runtime preservation checks
and full numerical comparisons. The primary used the unchanged numerical
helpers; the independent implementation used its own Float32 decoding,
`math.fsum`, lowest-ID argmax and blank-collapse checks.

The reconciler closed normally with diagnostic exit 2 in 20.327480 seconds. The
independent auditor agreed and closed normally with exit 2 in 14.621446 seconds.
Each had its own 90-second stage and 120-second parent bound. Neither dispatched
a native worker, created a model session or repeated an inference. Their new
records explicitly retain the original controller failure and zero new calls.

| Original output, both controls | Mac byte checks | Simulator byte checks |
| --- | ---: | ---: |
| logits | 2/2 | 2/2 |
| encoderEntryAnchor | 2/2 | 2/2 |
| block7Residual | 2/2 | 2/2 |
| block15Residual | 2/2 | 2/2 |
| encoderFinalAnchor | **0/2** | 2/2 |
| logProb | 2/2 | 2/2 |

The original 16 preservation checks remain bound through the prior V6 evidence;
the new 24 direct checks nevertheless fail. The new residual observations cannot
be used to attribute the original discrepancy. Original numerical thresholds
remain max `1e-4`, mean `1e-5`, with exact discrete decisions; no threshold,
reference, fitting, holdout or eligibility changed.

## Evidence and next step

Task: `work/native-q8-pre-normalization-20261016/`.

- Narrow build admission: `build-v3/DIAGNOSTIC-BUILD-ADMISSION.json`, SHA256
  `3190adc7afcfca2a964784574f8636f4c93b13fe89b2faa986ff2f85317f4c77`.
- Preserved failed controller: `measurement-v1/ROOT-TERMINAL.json`, SHA256
  `0230051e988e072cb9cf98db056054bf683e93cd907d899a8c65aae581518157`.
- Saved reconciliation ROOT:
  `measurement-v1/saved-reconciliation-v1/ROOT-TERMINAL.json`, SHA256
  `27b83321de90697c67f64a2dcc6341544db06a5e315a3373e6d2d4ff612f0bb0`.
- Independent saved audit:
  `measurement-v1/saved-reconciliation-v1/ROOT-AUDIT.json`, SHA256
  `6540a10c208f16ee260548bedc24d32c8644a9e1b39a8f1ea6a57923c05b2867`.

Inspect output indexing, buffer ownership and output visibility before choosing
another measurement. Optimizer behavior is a hypothesis until supported by
additional evidence. Source inspection found no concrete indexing, copying or
tensor-lifetime defect: the final anchor remains raw output 4, and all OrtValues
survive complete copy-out. No model was rerun during reconciliation.
The working whole-word guided-practice route remains unchanged; this checkpoint
adds no sound-correction, diagnosis, full-pipeline or clinical claim.

## October 23: generated comparison-reader controls

The unchanged optimized-graph metadata reader now passes ten generated-protobuf
helper tests, including changed normalization metadata, output exposure,
producer identity and rejection cases. Root observed normal owned-process
closure; the independent engineering review is clear with limits. The exact
scope and retained receipts are in
[the reader-control handoff](../../work/native-q8-reader-controls-20261023/HANDOFF.md).
These tests use no retained model, saved numerical array, recording, inference
or simulator. They do not test full export admission or repair this probe's
two failed preservation checks. A fresh optimized-graph comparison remains
unexecuted; q8 remains withheld at 5 passing/22 failing of 27.

A separate [generated output-exposure control](../../work/native-q8-fusion-control-20261023/HANDOFF.md)
then reproduced the proposed fusion mechanism in the cached runtime. Two tiny
graphs differ only by exposing the residual as an extra output: the internal
case becomes one SkipLayerNormalization node, while the exposed case retains
Add plus LayerNormalization. Both optimization-only sessions closed normally,
with zero inference calls. This supports a specific instrumentation hypothesis;
it does not establish that the retained graphs take those paths, explain their
numerical differences or repair the failed preservation checks.

The subsequent [retained public graph comparison](../../work/native-q8-optimized-comparison-20261023/HANDOFF.md)
now observes that structural difference in the actual two diagnostic graphs.
Among 939 shared producer tensors, only the final-normalization producer
metadata changes: fused SkipLayerNormalization becomes separate Add and
LayerNormalization when the block-23 sum is exposed. Initializer metadata,
input signatures and the five old output signatures are preserved. Both
optimization-only exports closed normally, with zero explicit inference calls.
This confirms that the probe changes the optimized path it intended to measure;
it does not prove numerical causation or repair. A replacement exposing the
fused operation's existing inputs needs its own structural and numerical
preservation checks before attribution. Original failures remain unchanged.

The [replacement input-exposure probe](../../work/native-q8-fusion-preserving-probe-20261023/HANDOFF.md)
now passes that optimized structural check: all 939 producer tensors and their
metadata remain equal, as do initializer metadata, inputs and the old output
prefix; final SkipLayerNormalization is retained. The public graph copy changes
only two exact output declarations. One fresh optimization-only export closed
normally, reusing the saved baseline and making no explicit inference call.
Numerical preservation still requires the original generated-control output
guards; this structural pass does not qualify the model or erase any failure.

The [replacement probe's numerical preservation check](../../work/native-q8-preserving-measurement-20261023/HANDOFF.md)
also passes for the two fixed original generated controls. Two Mac and two iOS
calls returned; all 24 original logits, log-probability and four-anchor byte
hashes match their saved same-runtime baselines exactly. Mac guards passed
before iOS dispatch. The fresh iOS 26.5 simulator and native processes closed
normally, with final Shutdown verified; the protected older device stayed
Shutdown. No reference forward, recording, reserved data, refit, threshold
change or numerical operand interpretation occurred in this execution.
The two additional operands can now support a separate analysis without the
known instrumentation disturbance. This establishes preservation for these
specific cases, not cross-runtime equality, numerical causation, a model repair
or clinical validity. Original q8 failures and learner exclusion remain.

A subsequent [analysis of twelve preserved generated tensors](../../work/native-q8-operand-analysis-20261023/HANDOFF.md)
places a substantial impulse-case discrepancy before final normalization: the
two inputs differ between Mac and iOS by maxima 4.1026859283 and 4.7265396118,
while the final anchor differs by 0.0706451535. The periodic control is bitwise
equal in all three tensors. This analysis made no new model call and used no
recording or reserved data. It narrows the next investigation earlier in the
late encoder; it does not isolate the cause, establish repair or qualify q8.

The next [block-19 midpoint probe](../../work/native-q8-late-encoder-midpoint-20261023/HANDOFF.md)
has passed all seven optimized structural checks, retaining 939 unchanged
producer tensors and the final fused normalization. Only one exact existing
output declaration was appended. Preparation and one optimization-only export
closed normally, with zero explicit inference calls. Its numerical measurement
remains separate and must preserve all 24 original same-runtime byte guards.

Its [four-call numerical measurement](../../work/native-q8-midpoint-measurement-20261023/HANDOFF.md)
now passes all 24 original same-runtime byte guards for the two fixed generated
controls on Mac and iOS. Both native processes closed normally, and final
Shutdown was verified for the owned simulator; the protected device stayed
Shutdown. Four additional block-19 tensors are admitted for a separate analysis.
This checkpoint did not decode their values or make a reference forward. It
establishes preservation for these cases, not cross-runtime equality, repair,
learner eligibility or clinical validity. Prior q8 failures remain unchanged.

A separate [saved block-19 analysis](../../work/native-q8-midpoint-analysis-20261023/HANDOFF.md)
now finds the impulse discrepancy already substantial at this checkpoint:
maximum absolute difference 1.2184143066 and RMS 0.3039612148, with all 4096
element bit patterns differing. The periodic control remains bitwise equal.
Combined with the small previously preserved block-15 difference, this
prioritizes blocks 16–19 for the next investigation. It does not identify the
first faulty operator or establish a repair. The analysis reads four admitted
synthetic tensors and makes zero model or reference calls; q8 remains withheld.

The next [block-17 probe](../../work/native-q8-block17-probe-20261023/HANDOFF.md)
now passes all seven optimized structural checks, preserving the 939 producer
tensors and final fused normalization. Preparation added only one exact existing
output declaration; the single optimization-only candidate session made no
explicit inference call. This prepares the midpoint of the 16–19 investigation
interval. Numerical measurement and all 24 original same-runtime byte guards
remain separate requirements; no repair or model qualification follows yet.

The subsequent [block-17 numerical preservation check](../../work/native-q8-block17-measurement-20261023/HANDOFF.md)
now passes all 24 original same-runtime byte guards for the two fixed generated
controls on Mac and iOS. Four calls returned with clean native closure and final
owned-simulator Shutdown; the protected device remained Shutdown. Four additional
block-17 tensors are admitted for a separate analysis. This measurement made no
new reference forward or numerical interpretation and does not qualify q8 or
erase its original failures.

A separate [saved block-17 analysis](../../work/native-q8-block17-analysis-20261023/HANDOFF.md)
finds a substantial impulse discrepancy already at block 17: maximum absolute
difference 0.4266924858, RMS 0.1046575402, with all 4096 element bit patterns
differing. The periodic control remains bitwise equal. Together with the small
preserved block-15 discrepancy, this prioritizes blocks 16–17 next; it does not
identify a first faulty operator, mechanism or repair. Four admitted saved
synthetic arrays were analyzed with zero new model/reference calls. q8 remains
withheld and the next block-16 checkpoint requires its own preservation checks.

The [block-16 probe](../../work/native-q8-block16-probe-20261023/HANDOFF.md)
now passes all seven optimized structural checks: the same 939 producer tensors
and metadata, preserved signatures and final fused normalization. Only one
existing output declaration was appended; preparation and one optimization-only
candidate session closed normally with zero explicit inference calls. Numerical
preservation remains a separate requirement before interpreting this checkpoint.


### October 24 — preserved block-16 execution

The [block-16 measurement](../../work/native-q8-block16-measurement-20261023/HANDOFF.md)
returned exactly four synthetic calls and passed all24 original same-runtime byte
guards. The owned simulator returned to verified Shutdown; the protected device
remained Shutdown. Four saved block-16 arrays are admitted for a separate bounded
analysis. No numerical interpretation or q8 qualification follows from preservation.
Generic localization will close after this boundary check unless a concrete
bounded repair mechanism emerges; app result integration is the next priority.


The separate [saved block-16 analysis](../../work/native-q8-block16-analysis-20261024/HANDOFF.md)
completed with zero new model calls. The periodic control is bitwise equal.
Impulse maximum absolute discrepancy is0.0768928528/RMS0.0112120201, concentrated
in frame1; other frames have maxima≤1.52587890625e-5. A larger discrepancy is
present by block16, without identifying a faulty operator or repair. Generic
checkpoint localization is closed; q8 remains5P22F/27 and withheld. Next priorities
are preserving typed take-bound research results in the app and separately
qualifying any public full-precision projection route.
