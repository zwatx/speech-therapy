# Frozen lexical mixtures under one fixed 20 dB noise condition

The corrected-projection mixture improves pooled child measures but fails the
primary consistency screen against the original scalar/PCA mixture. This study
asks a different question: how much do the two fixed distributions move when
recording conditions change? Smaller movement is not pronunciation accuracy,
clinical safety, or proof that a changed prediction is wrong. Noise can mask
useful evidence. There is no promotion screen for this sensitivity diagnostic.

## Fixed scope and provenance

Use the existing full-author-training `consistency-features-extension-v1`
20 dB white-noise cache. Its producer fixed seed 20260926, CPU/two threads and
whole-waveform SNR; retain its exact waveform, quantization, normalization,
CTC alignment and phonetic pooling recipe. Do not regenerate audio, vary noise
level or refit the encoder. Run the complete frozen cache validator: original
and extension plans, all upstream/source/checkpoint/audio/posterior/unit hashes,
canonical row identities, every unit-to-array join and complete coverage.
Additionally match its clean feature binding, local/phonetic recipe hashes and
13 scalar column names to the current lexical source models. Noise may change
estimated alignment windows; do not require them to equal the clean windows.

Keep all 14,837 original eligible positions from 125 speakers in both training
regimes, including 5,654 positions from 52 children aged 6–12 and all 23 phones.
Each position uses its own original held-out speaker-fold/word-group head.
All 50 canonical cells retain original whole-utterance lexical exclusions,
fit/selection/refit/outer memberships and checkpoints. The noisy feature cache
previously supported other development studies; it is not a new independent
sample or unseen recording condition. No transformed waveform receives the
original human ratings or any fabricated target. No noisy NLL, Brier, AP,
accuracy, calibration or supervised loss will be calculated.

## Label-free computation and phase order

Declare and pin new source/tests, this protocol, all source plans/freezes and
predictions, current reference reports, complete cache inputs and exact pairs
before any new head inference. Preserve earlier pinned sources unchanged.

Use only saved head weights, normalization means/scales, original PCA center
and basis, and saved supervised projection correction. Do not fit or recompute
normalization/center from noisy inputs. The prediction API accepts target and
scalar arrays, offsets and canonical phone IDs; it has no rating-label input.
Use CPU, two threads, batch 64, float32 head evaluation, float64 stable
log-softmax and the original casts: base PCA coordinates from float64 matrix
multiplication cast to float32, then add float32(centered raw @ correction)
within each original-sized batch. Preserve raw float32 softmax probabilities
as well as float64 stable probabilities/logs. No probability floor.

First run all 50 clean cells. Require exact equality of raw probabilities,
stable probabilities and logs for the scalar, PCA and corrected-PCA components,
and exact stable probabilities/logs for both fixed .5/.5 mixtures. Bind the
source rows and checkpoints. Freeze all 50 clean results before any noise
forward pass. A failed parity check stops the study and is retained. Then
run all 50 noisy cells with the same parameters, normalization, row ordering,
phone IDs and batching, and freeze the complete noisy population before
summarization. An incomplete or mismatched freeze cannot proceed. Source/file
guards run before phases and after computation; no optimizer or encoder runs.

## Descriptive outcomes

For each mixture, compare its noisy distribution with its own clean distribution.
Retain every per-position total variation (half the sum of absolute probability
changes), signed expected-rating shift on [0,1,2], absolute expected-rating
shift, rating-0 probability shift, below-2 probability shift and argmax change.
Ties use the first class. A class change is a model movement, not an observed
pronunciation error.

Summarize mean/max TV, mean/max absolute expected-rating shift, mean signed
expected-rating/rating-0/below-2 shifts, and argmax-change counts. Report positions,
recordings, speakers and observed phones. Retain all three age populations,
all 23 phone slices (including zero-support/null measures), all 25 cells, five
speaker folds, five word groups and all 52 children. Pooled means weight target
positions equally; overlapping model-fit populations do not add participants.

Compare paired movements as corrected-mixture minus existing-mixture. Retain
per-position TV differences; their mean; difference of slice maximum TV values;
mean absolute-expected-shift difference; argmax-count difference; and counts
with lower/same/higher TV using fixed 1e-12 descriptive tolerance. Difference
of maxima is not maximum paired difference. No significance or improvement
gate, case exclusion, uncertainty threshold, weight search or phone selection
follows these observations. The two source training regimes both remain.

## Verification and interpretation

Before declaration, test label-free inference, frozen moments/head behavior,
zero/nonzero projection cast order, analytic movement/tie examples, extreme
stable probabilities, malformed inputs, slice support and phase-order guards.
Independently review source/protocol. After running, independently reconstruct
all clean/noisy component outputs and both mixtures using a separate tensor
path, and verify all movements, paired summaries, memberships and null support.
Reconstruct the complete report offline and independently review its narrative.
Retain failed attempts rather than rewriting evidence. No labels may enter
independent noisy prediction arithmetic either.

This tests one synthetic noise condition, not room acoustics, microphone
hardware, clipping, volume changes or natural short-word performance. The
existing five-child gain/10 dB diagnostic does not contain saved 1024-dimensional
vectors needed to apply these heads directly. No new result for those conditions
is implied. Canonical alignment is unverified; produced-phone identity and
child-SSD/age-2–5 coverage remain absent. Keep author-test closed and learner
judgments disabled. No Colab allocation, app changes or app builds/UI tests.
