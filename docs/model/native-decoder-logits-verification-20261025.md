# Decoder-logit copy optimization — October 25, 2026

The ordinary word recognizer now copies contiguous decoder logits through scoped Float storage instead of51,864 boxed tensor reads on each decoding decision. Generated-tensor measurements show a median **64.380917ms →0.287937ms** for that copy operation. This is not a measured full word-check latency improvement or an accuracy change.

## Behavior preserved

[`WhisperDecoderLogits.swift`](../../apps/ios-learner/Sources/Assessment/WhisperDecoderLogits.swift) admits exactly float32[1,51864], count51864. It checks exact strides[51864,1] and sufficient storage inside the scoped borrow. Other layouts retain the original logical indexing path. The owned output array contains all scores, with the original51 cancellation boundaries at indices0,1024,…51200. No pointer escapes.

The first actual benchmark failed before timing: the SDK's indexed NSNumber conversion canonicalized a NaN payload, while a direct Float read preserved it. The failed input/source and result are retained. The corrected fast path uses the original indexed conversion **only for NaNs**, preserving SDK behavior without hard-coding a replacement. Finite values and infinities remain on the fast path. NaNs are not repaired to finite values or rejected early; the existing later selection still rejects every nonfinite score, including suppressed tokens.

The worker change replaces only metadata validation/copy with the helper and removes its unused private validator. Model resources, selection, token suppression, EOS, token limit, text comparison, status policy, cancellation ownership and runtime release are unchanged.

## Actual verification

- Model-free optimized Mac harness compiles the exact production helper. Only its error-enum case is projected for standalone compilation. Its baseline is the original indexed copy, preserved from the hash-verified before-worker.
- All11 correctness records pass: three tensor layouts with sampled signed-zero/subnormal/finite/infinity/NaN bit patterns, every51 cancellation boundaries plus precancellation per layout, and five invalid-metadata cases. Every returned bit is compared with the actual original indexed result. This is sampled bit-class coverage, not enumeration of every possible Float bit pattern.
- After parity, two warmups per implementation and ten alternating paired trials pass. Allocation, metadata, scoped acquisition/copy and51 locked cancellation reads are timed; input creation and output checking are outside the interval. All24 output checksum observations agree. Raw times and the failed first benchmark remain retained.
- All **six canonical iOS unit tests pass**,0failures/skips/expected failures and exactly one start/pass each. They cover indexed semantics, signed NaN-payload regression, metadata, cancellation, precancellation and the unchanged later nonfinite rejection. Actual tests total1.227seconds; enclosing build/test stage168.818seconds.
- These app-hosted units use Release optimization with testability enabled, no DEBUG; test code is unoptimized. They ran only on the positively owned spare SE3/iOS27 simulator A2EBC95C-D10F-462A-AF40-00C62AD15456. The exported result identifies that exact device. It ended Shutdown. The prepared primary simulator was only listed and remained Booted; its app was not replaced or manipulated.
- A separate ordinary arm64 Release build passes with optimization−O, no DEBUG and testability disabled. It was compiled, not installed or launched. Six units and the Mac benchmark load no model and start no recording/playback/camera.

Root personally observed each outer process terminal before dependent execution/export. Final source pins pass. The two raw unit-build AppIntents metadata warnings are retained; exported runtime warnings are empty, which does not imply warning-free raw logs. The first benchmark's failure and subsequent minimal correction are distinct from the closed scientific studies; no model study was rerun.

## Evidence and limits

Actual task receipts, generated harness, before-worker, first failed inputs/result, corrected benchmark, compiler source bindings and unit result bundle are retained in `work/decoder-logit-performance-20261025/`. `MAC-POSTCHECK.json` and `UNIT-POSTCHECK.json` record actual outcomes. No end-to-end model request was added, no weights changed and no private/reserved data was used.

The installed search-fix candidate8 remains untouched for the user's optional rehearsal. This source optimization is not installed in that demo. Whole-check latency, recognition accuracy, individual-sound correctness and clinical usefulness remain separate measurements. The separate [phone-decoder development result](ctc-prefix-development-20261025.md) concerns a different research model and cannot be attributed to this optimization.
