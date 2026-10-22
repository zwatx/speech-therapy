# Complete repeated-position scalar feature export

The expanded research dataset now has estimated local geometry and thirteen
recognizer-confidence features for **all 28,227 consonant positions** across
2,500 recordings. Every one of the **14,837 original positions matches its
previous features exactly**. This completes the scalar-feature stage for
repeated sounds; it does not yet establish a model-quality improvement.

The [declared protocol](multiphone-position-geometry-protocol.md) and reviewed
implementation kept the recognizer, canonical mapping, full-sequence alignment,
frame grid and pooling context unchanged. The run reused 2,495 saved CTC arrays
and performed exactly five new offline CPU recognizer passes for the newly
included recordings. Each new job retained its waveform, checkpoint, source,
runtime and output hashes, with zero attempted network fetches.

There are **5,792 repeated recording/phone groups**, containing the **13,390
new positions**. Every requested occurrence retains its word/phone indices,
flattened canonical index, separate state interval, two-frame context window,
raw scalar values and diagnostic flags. Repeated canonical states are ordered
and disjoint; adjacent identical tokens require an intervening blank state.
Context windows can overlap. These checks establish algorithmic state identity,
not verified acoustic boundaries or correct pronunciation.

Original-position parity covers all thirteen scalars, token IDs, intervals,
frame-center times, windows, mapping caveats and diagnostic flags. Utterance
diagnostics also match. No row was removed because of rating, confidence or
alignment quality. The complete matrix has shape 28,227 × 13, with explicit
occurrence order and support for all 23 targets. The child 6–12 slice contains
9,891 positions.

Eleven focused geometry/export tests and eleven dataset-builder tests pass.
Independent source review cleared both stages before execution. Offline
saved-array reconstruction and the independent exported-artifact audit passed.
The independent audit reconstructed all 2,500 Viterbi paths and matched every
interval, window and all 366,951 scalar values, including adjacent repeated
tokens. Verification used retained arrays without another recognizer pass.
The audit record is `work/position-geometry-audit-20260927/verification.json`
(SHA-256 `4e8038ffbbc1a35acc273b0b960a30eba3bcc9c0e4fe42504b90e4da95e22ff3`).

## Saved evidence

- [Plan](../../research/audio-head/outputs/multiphone-20260927/position-scalars-v1/plan.json): `d404c3762dc2bb70105dde70b8cc030b6ebda8e4ee74c06d908a251d27643cca`.
- [Complete export](../../research/audio-head/outputs/multiphone-20260927/position-scalars-v1/report.json): `5b2828cec062b50c575334c8f4182e1d7a712c869bf6ae90867417a9eb5698b9`.
- Float32 scalar matrix SHA-256: `d2795a98ab60a1887911f172ce0248544af036deab3eae8af28756e64b29ba9e`.
- [Upstream dataset and audio verification](multiphone-position-data-report.md).

Next, extract the current full-precision phonetic encoder's position-specific
vectors, verify the old pooled vectors exactly, and compare original-row versus
all-position fitting under fixed speaker folds. The old phonetic export saved
pooled vectors rather than complete hidden frames, so new pooling needs new
encoder passes for recordings with added positions. Historical extraction took
about 9.5 minutes for 2,495 recordings on the Mac; local compute is sufficient
for this bounded stage.

No new model was fitted or promoted. No author-test inference, hidden-vector
extraction, Colab allocation or learner feedback occurred. Broader app tests
were not run because this change is isolated research feature preparation.
