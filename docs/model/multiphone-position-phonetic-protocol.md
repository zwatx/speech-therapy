# Complete position phonetic-vector protocol

This feature-only step covers the reviewed 28,227 author-train consonant
positions in 2,500 clips. It preserves all 23 targets, ratings, and original
speaker splits. No ratings or annotation notes select acoustic features.
Author-test data remains closed. It does not fit or promote a model.

Use the original pinned full-precision facebook/wav2vec2-lv-60-espeak-cv-ft
checkpoint, local-only loading, CPU float32 eager attention and two Torch
threads. Preserve the original normalized mono 16 kHz preprocessing, frame
geometry, and float64 mean accumulation cast to float32. Pool at the exact
estimated windows already saved in position-scalars-v1. These are unvalidated
canonical forced-alignment windows, not measured phone boundaries.

Re-extract all positions in the 2,262 clips containing newly added occurrences,
including five newly included recordings. Reuse the original vectors in the
remaining 238 recordings. Require exact identity/window and target-vector
parity for all 14,837 legacy rows and exact original whole-clip vectors for
all 2,495 old recordings. A discrepancy fails the run; no tolerance adjustment,
row omission or alternative encoder is permitted. No complete hidden-frame
cache is required. Save target/global vectors per clip, an ordered 28,227 by
1,024 target matrix, and a 28,227 by 1,037 matrix concatenating the unchanged
thirteen scalar columns after the target vectors.

Declare source, tests, protocol, data, geometry, old vectors, checkpoint and
runtime hashes before inference. Use a fresh ignored output directory and
exclusive start marker. No implicit retry, overwrite or resume. Preserve
failure evidence. Initialize the encoder once, and make one additional pass
at the end for the first recomputed clip in sorted ID order. Save that pass
separately and require exact target/global equality with its first pass.

Offline verification rechecks every input, unit identity, window, legacy
vector, repeat output, matrix value, row order and support table without
encoder inference. An independent reviewer must inspect the source before
execution and actual saved artifacts afterward. Learner feedback and clinical
eligibility remain false. Broader training comparison needs a separate fixed
protocol and cannot infer improved accuracy from increased feature coverage.
