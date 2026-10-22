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
