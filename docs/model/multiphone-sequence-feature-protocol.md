# Fixed sequence-evidence feature experiment

Declared September 27, 2026 before corpus sequence-feature calculation or new
fitting. Do not modify after the first declaration. This is development
research on previously used author-training data, not final validation.

## Question and fixed features

Does complete-sequence substitution/deletion evidence improve child rating
prediction beyond the existing 1,037 acoustic and local-scalar features?
The numerical preflight passed; it did not evaluate rating prediction.

Export all 2,495 retained author-training recordings and exactly the 14,837
eligible target positions, covering all 23 supported consonants. Use only the
existing full 392-token cached log posteriors and canonical mappings. For each
eligible slot use the same 388 nonspecial replacement tokens (IDs 4–391) and
one deletion. The four columns, in this exact order, are:

1. Canonical log likelihood minus log-sum likelihood of all replacements and
   deletion (`canonicalVsAlternativesLogRatio`).
2. Canonical minus deletion log likelihood (`canonicalVsDeletionLogRatio`).
3. Canonical minus highest other-token replacement log likelihood
   (`canonicalVsBestOtherTokenLogRatio`).
4. Complete canonical log likelihood divided by the number of decoder frames
   (`canonicalLogLikelihoodPerFrame`).

These are decoder evidence features, not produced-phone labels or calibrated
correctness probabilities. No insertion model, token-subset renormalization,
clipping, imputation, rating-based feature choice or row omission is allowed.
Undefined or nonfinite features fail the export and retain diagnostics.
Calculate in float64, retain raw per-slot likelihoods and summaries, then save
the four-column float32 matrix in eligible cohort row order. Bind source,
protocol, runtime, cache/audio bytes, canonical mappings and row identities
before calculation. Verify the three original preflight clips against their
saved numerical output and recompute those three at completion. Ratings are
not copied into feature artifacts. No new encoder inference or author-test
access. Extraction may process outer rows because its transformation is fixed,
per-recording and label-free; no aggregate feature analysis chooses the recipe.

## Fixed model comparison

Use the original five child-only warm heads, feature binding and speaker splits
from `experiments/multiphone-ranking-v1.json`. Existing 1,037-column fit moments
and model weights remain unchanged at initialization. Normalize the four new
features separately using only each fold's child fitting rows: float32 mean
and population standard deviation, with standard deviation floored at 1e-6.
No outer or selection data enter normalization or vocabulary construction.

Add a bias-free four-to-128 linear projection, initialized to exact zeros, to
the output of the original acoustic linear projection before its GELU. Keep
the original acoustic matrix operation separate to avoid changing its width
or rounding at initialization. All original parameters and the new projection
are trainable. This adds 512 weights: the comparison tests the full feature
augmentation, including its extra capacity, rather than isolating information
from capacity. No alternative architecture or feature sweep. Verify initial
predictions exactly match each warm head, and separately verify a disabled
branch follows the retained ordinary-NLL update on synthetic tests and one
fixed fold-0 fitting epoch. That verification is not a candidate selection.

Five new trajectories, folds 0–4, exactly six continuation epochs each. Fresh
AdamW, learning rate 0.00003, weight decay 0.01, batch size 64, gradient norm
limit 5, dropout off, seed/order 7, CPU two threads. The supervised objective
is the original unweighted five-rater distribution NLL. No pairwise auxiliary.
Reuse the completed selection-policy study's ordinary-NLL trajectories as
matched controls; bind all five manifests, seven checkpoints each, predictions
and histories before training. Do not rerun identical controls or substitute
historical early-stopped models. Stop on failed lineage or equivalence checks.

Save epoch 0–6 states, optimizer and RNG states, inner probabilities, full
metrics and update/order digests. Select each new trajectory by child macro
phone NLL, strict improvement >1e-7 with chronological earlier ties, epoch 0
eligible. Compare with the ordinary-NLL controls selected by the same rule.
No AP-based alternative selection in this experiment. Freeze all five new
selections and five control selections, with exact selected-prediction replay,
before any new outer rating prediction. Training source and evaluation source
must be bound in a separate declaration after feature export; feature export
alone is not authorization within this protocol to skip those checks.

## Evaluation and decision

Use each selected model only on its same-fold outer speakers. Fit, inner
selection and outer speakers must be pairwise disjoint. Pool cross-fitted
predictions so every eligible row appears once. No outer-fit refitting.
Primary contrast: new minus control pooled child macro-phone below-2 AP.
Retain pooled and per-fold rating-0 AP/AUROC, below-2 AUROC, macro NLL,
per-rater NLL/Brier, entropy and argmax counts. Include all-age, child and adult
slices, all 23 phone metrics with undefined cells explicit, and positive-vote
and positive-speaker support. Report seen/unseen words according to exact
uppercase text in that fold's child fitting vocabulary and show support first.
Those slices are not a word-disjoint experiment.

A consistent development ranking gain requires pooled child below-2 AP gain
>1e-7, no fold below-2 AP contrast below -1e-7, no pooled child rating-0 AP
decline beyond 1e-7, and no pooled child macro NLL or Brier increase beyond
1e-7. Otherwise classify results as mixed/no consistent gain and retain every
tradeoff. This rule assesses this fixed recipe, not all possible sequence
features. A favorable result still cannot promote learner judgments without
independent validation. Previously used outer data can influence research
direction, fold fits overlap, and no significance or independent-replicate
claim follows from five folds. No clinical-correctness claim.

Budget: one full cached feature export, three-clip repeat, one fold-0 disabled
equivalence epoch and five six-epoch candidate fits. Mac CPU only, no Colab
allocation. Retain failures; no implicit restart or hidden extra fit. Existing
research bundles and learner eligibility remain unchanged.
