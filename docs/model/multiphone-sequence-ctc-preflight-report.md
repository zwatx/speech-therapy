# Sequence likelihood calculation passes numerical preflight

The new sequence-level calculation agrees with independent CTC calculations on
all fixed examples. This verifies a new way to extract model evidence; it does
not yet demonstrate improved pronunciation-rating prediction.

The [protocol](multiphone-sequence-ctc-preflight-protocol.md) fixed three
recordings from fold-0 child fitting data by duration, without using ratings.
All 18 eligible target positions were included. Each position considered every
one of the decoder's 388 nonspecial tokens and deletion of that position.
The complete expected sequence was also checked once per recording.

All **7,002 replacement/deletion hypotheses and three canonical likelihoods**
agreed with PyTorch's full-sequence CTC loss within **1.4211 × 10⁻¹³** absolute
log-likelihood difference, well inside the predeclared 10⁻⁸ tolerance. A second
optimized pass reproduced the same serialized numerical bytes. No case was
dropped, and no special-token mass was redistributed among allowed alternatives.

| Recording | Frames | Target positions | First optimized pass | Repeat | Reference pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| 000050175 | 79 | 4 | 6.62 ms | 6.37 ms | 25.77 ms |
| 000540123 | 159 | 6 | 18.39 ms | 18.31 ms | 140.18 ms |
| 000560117 | 535 | 8 | 79.10 ms | 79.39 ms | 724.83 ms |

These are observed CPU durations for one first pass and one repeat on this Mac,
not a general runtime guarantee. They support testing the feature on the
retained corpus without allocating Colab. No recognizer inference, new audio,
fitting, rating correlation, validation/outer calculation or author-test access
occurred in this preflight.

Eleven focused tests passed. Separate mathematical and implementation reviews
also checked exhaustive raw CTC paths, including 8,160 comparisons of the actual
implementation across repeated labels, impossible lengths, different blank
IDs and candidate orderings. The source WAVs, posterior bytes, row/slot
identities, provisional mappings, original source files and runtime were bound
before execution and rechecked afterward. All 18 positions belong to the
declared fitting children.

## Why this is a useful next feature

The previous features use one forced target interval. The new calculation
instead sums valid alignments of entire token sequences, so it can compare an
expected token with a missing token without forcing that token to occupy a
frame. Shared prefix and suffix calculations make the finite alternative set
practical. The [research notes](multiphone-sequence-ctc-notes.md) explain its
published basis and how it differs from the earlier local-posterior study.

These remain decoder hypotheses. A preferred alternative is not a human
annotation of what was spoken, a diagnosis, or proof that the canonical sound
was incorrect. The multilingual decoder inventory and provisional mapping
also contain variants and merged tokens. The restricted-set log share is not
a calibrated probability of correctness; insertions are not modeled.

## Next experiment

Proceed to a separately declared model comparison using sequence evidence
alongside the existing acoustic features. Preserve the same speaker splits,
original warm heads, fit-only normalization, matched training budget and
retained ordinary-NLL controls. Declare the feature columns and selection rule
before fitting; freeze all selections before evaluating held-out speakers.
Retain child rare-rating metrics, probability-fit tradeoffs, unfamiliar-word
slices and per-sound positive-speaker support. The feature must earn its place
through that comparison; numerical parity alone is insufficient.

Learner judgments remain disabled and the existing four research bundles remain
unchanged. This preflight used no Colab units. Broader application tests did not
run because only new research scripts, tests and documentation changed.

Local evidence:

- [Declared inputs](../../research/audio-head/outputs/multiphone-20260927/sequence-ctc-preflight-v1/plan.json), SHA-256 `fb8b77c8e4798a48db660e7030f6df297a7c948dffddab78b9204558f9ae2f37`.
- [Raw comparison report](../../research/audio-head/outputs/multiphone-20260927/sequence-ctc-preflight-v1/report.json), SHA-256 `422bfac1040d3cec900787774908f81a08d5dcd7b3912540114b009f993751c9`.
