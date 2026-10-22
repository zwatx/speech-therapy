# Frozen temperature transfer control

The completed [temperature study](multiphone-temperature-report.md) failed its
consistency screen for both pipelines. It fitted correction on an original
inner head and applied it to a subsequently refitted outer head. This follow-up
reuses exactly those ten frozen inverse temperatures and predicts the same
outer speakers with the original selected inner heads. No new correction,
checkpoint, epoch, rate, threshold or model parameter will be fitted or selected.

## Fixed scope

Use the original 14,837 eligible author-training positions and five outer folds,
with all-age and child-only target-plus-scalars heads. Bind the prior calibration
plan, freeze, every fit and the completed refit evaluation by their known hashes.
Reuse the audited calibration values directly; do not call an optimizer even to
reconstruct them. Pin all new source, tests, this protocol and runtime before
new outer inference. Historical source and artifacts remain immutable.

For each of the ten selected checkpoints, load the original configuration,
fit-only feature moments and cached features. Verify exact replay of its original
inner validation probabilities and metrics before running it on that fold's
outer holdout rows. Assert disjoint fitting, inner validation and outer speakers.
Only ten additional outer head passes are needed; no acoustic encoder inference,
new audio, head training or Colab allocation is needed. Retain exact row identity,
all predictions, replay receipts and checkpoint/correction bindings. Freeze the
ten new prediction files before normalized/corrected and between-arm summary
calculation. The reused head evaluator also computes raw metrics during each
outer pass; those helper metrics are discarded and do not select anything.
Failures remain recorded.

## Comparisons and interpretation

Apply each original frozen positive beta to its matching new outer predictions
with the unchanged float64 normalization and stable log-softmax implementation.
Save raw, normalized and corrected vectors and log probabilities. Identity and
argmax invariants remain checked. Use exact NLL, including all nested NLL and
entropy copies, without a probability floor. Retain fixed ten-bin reliability,
all 23 phone cells and all-age, child 6–12 and age-13-plus support. Seen/unseen
word summaries use each ORIGINAL INNER head's actual fitting vocabulary, not
its corresponding refit vocabulary. These slices are descriptive and are not
word-disjoint test sets.

For each regime, report baseline/corrected metrics for each fold and pooled
outer rows. Reuse the prior consistency screen without modification: pooled
child NLL improves by more than 1e-12, every child fold NLL is no worse within
1e-12, pooled child macro-phone NLL and Brier are no worse, and pooled vote-
weighted rating-0 and below-2 AP are no worse. Preserve all component results.

Alongside this same-head result, show the existing refit arm's all-word child
baseline/corrected outcomes and correction deltas, aligned on identical rows
and fold identities. Report same-head delta minus refit delta, baseline and
corrected differences between arms. Do not compare differently defined
seen/unseen slices as matched populations. Any benefit from retaining the
original inner head combines a different fit population and model state; this
control does not establish a unique causal explanation for refit differences.
A failure on the same head would show refitting is not necessary for that
observed failure, not that transfer has no effect.

The same inner validation data selected the checkpoint and fitted temperature;
outer folds have repeatedly been used for development. This is not untouched
final evaluation or clinical calibration. No learner feedback or automatic
bundle replacement follows even if a screen passes. Do not select a temperature
or a model from these results or expand the correction search.

## Verification

Test wrong row/model identity, speaker overlap, vocabulary membership, missing
folds and frozen-input ordering. Reconstruct the complete saved result offline
without head inference or optimization. Independently review source and actual
head outputs, frozen correction identity, primary and slice metrics, rare-vote
support, arm comparisons and narrative. Keep author-test data closed and all
production/clinical/learner eligibility false.
