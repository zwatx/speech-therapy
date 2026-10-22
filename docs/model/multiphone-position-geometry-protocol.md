# Repeated-position CTC geometry and scalar features

September 27, 2026. After the complete position-aware cohort passes its source,
audio and split review, build a separate feature artifact for every one of its
28,227 supported consonant positions. This stage does not fit a model, extract
new full-precision phonetic hidden vectors or choose a checkpoint.

Keep the existing canonical mapping, quantized CTC checkpoint, 16 kHz frame
grid, Viterbi algorithm, thirteen scalar columns and two-frame pooling context.
Reuse the verified CTC arrays for the original 2,495 recordings. Run the same
existing CPU2 offline CTC worker for only the five newly included recordings.
Bind each new job, source, checkpoint, audio, runtime and result; preserve
failure evidence and never infer missing outputs.

For each recording, align its full canonical token sequence once and request
all supported canonical indices. Repeated tokens must remain separate CTC
states, including adjacent equal tokens separated by a required blank state.
Retain the existing diagnostic flags and provisional mapping caveats. Every
position gets an independent occurrence ID, estimated state interval, fixed
context window and scalar vector. No label or alignment-confidence filtering.
Forced canonical occupancy is not a verified phone boundary or a production
label, and contextual pooling windows may overlap.

Reconcile every original eligible position with its old exported target using
legacy row identity. All thirteen scalar values, token ID, state interval,
frame-center times and diagnostic flags must match exactly, as must the
utterance diagnostics. New occurrence IDs must not alter old acoustic results.
Report all positions and recordings, per-phone/child support, repeated-token
groups, disjoint state intervals, and explicit old-position parity counts.
No inference about correctness follows from distinct alignment states.

Declare cohort/split/source/test/protocol/runtime and historical-input hashes
before calculation in a fresh output directory. Save each consumed or generated
CTC binding, per-clip geometry, a complete ordered float32 scalar matrix, and
the exact row order. Abort on missing, duplicate, nonfinite or mismatched data;
preserve partial/failure artifacts. Verification reconstructs geometry and
scalars from saved arrays, checks new-worker provenance and exact old parity,
and compares the complete report/matrix without repeating model inference.

Tests must cover repeated phones with different positions, adjacent repeats,
invalid/duplicate indices, state/window geometry, exact old-position parity,
and rejection of corrupt source or derived artifacts. Independent review of
code and actual output precedes downstream model use. No author-test payloads,
training, new calibration, clinical eligibility or learner feedback are enabled.
