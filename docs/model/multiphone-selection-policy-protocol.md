# Fixed-horizon checkpoint selection study

Declared 2026-09-27 before new fitting or outer predictions. This is exploratory
development evidence, not independent final validation. Do not modify this
protocol after a run is declared; record deviations separately.

## Question and rationale

Does selecting a child-trained checkpoint for within-phone ranking of ratings
below 2 improve that same metric on same-fold held-out speakers, compared with
selecting for child macro-phone negative log likelihood (NLL)?

The previous ranking histories discarded a better below-2 AP epoch in four of
five folds, but a better rating-0 AP epoch in only two. Those are maxima on the
selection data, not generalization evidence. Matched controls did not save full
ranking histories, and some intermediate checkpoints are absent. We will not
relabel a historical discarded checkpoint as a winner.

## Fixed matrix and training

Use the existing author-training cohort, frozen 1,037-dimensional target/scalar
features, five speaker splits and child-only warm heads pinned by
`research/audio-head/experiments/multiphone-ranking-v1.json`. Historical sources
and outputs remain unchanged. No author-test access or new audio inference.

Ten trajectories: folds 0–4 crossed with clean five-rater NLL and the existing
NLL + 0.1 pairwise auxiliary. Reuse the original ranking trainer's loader,
sampler, model, prediction and update functions. Fit exactly six further epochs
for each trajectory; no early stopping. Each starts from its original warm
model and fresh AdamW, learning rate 0.00003, weight decay 0.01, batch size 64,
gradient limit 5, CPU two threads, dropout off, initialization/order seed 7 and
separate pair seed 20260926. All sampling details stay as previously declared.
No new hyperparameter sweep. Budget: ten fits, sixty epochs on this Mac; no
Colab allocation. Stop and retain diagnostics if a run fails verification.

Save epoch 0 and every completed epoch's model, normalization, predictions,
full age/per-phone metrics and update/order digests. Pin recipe, protocol,
source and input bytes before fitting. Both objectives must reproduce their
historical realized trajectory prefix (validation probabilities where saved,
NLL and update digests where available); historical warm predictions must
replay exactly. Each selected checkpoint must replay its predictions exactly.

## Selection frozen before outer evaluation

Each trajectory supplies two selections among epochs 0–6:

- NLL: child `macroTargetLogLoss`, minimized with strict improvement > 1e-7.
- AP: child `targetDiscrimination.macroTarget.ratingBelow2.averagePrecision`,
  maximized with strict improvement > 1e-7.

Scan in chronological order, retain the earlier epoch on a tie or improvement
within tolerance. Epoch 0 is eligible. These are within-phone, five-rater vote
weighted AP values, equally averaged over phones having both positive and
negative votes. Undefined phones remain explicit; support is fixed across
epochs. Warm heads were themselves previously selected by inner child NLL;
the study compares continuation selection conditional on those warm heads.

All ten histories, twenty selections, selected checkpoint/prediction hashes
and prefix/replay verification must be frozen in one selection manifest before
any new outer prediction. Audit code may read split membership and support
metadata earlier, but never use outer outcomes for fitting or selection.

## Held-out-speaker development audit

Evaluate only the two selected checkpoints per trajectory on its declared
`outerHoldoutRows`. Same-fold fitting, selection and outer speakers must be
pairwise disjoint; normalization and vocabulary derive from fitting rows only.
No refitting on the larger outer-fit partition. Combine each of four pipelines
(two objectives × two rules) into one cross-fitted prediction set covering each
eligible cohort row exactly once (14,837 rows across all 23 supported phones;
six unsupported ZH rows are excluded). All twenty selections are frozen before
this stage.

Primary contrast: AP minus NLL selection in each objective, measured by child
macro-phone below-2 AP on the pooled cross-fitted predictions. Report both
contrasts; do not choose the more favorable objective after audit. Per-fold
values and their equal-fold means are descriptive consistency checks, not an
alternative primary aggregate.
Secondary descriptive metrics: rating-0 AP/AUROC, below-2 AUROC, macro NLL,
per-rater NLL/Brier, entropy and argmax counts. Include all-age and adult slices,
all 23 phones with missing/undefined metrics explicit, positive votes and
positive-speaker counts. Report target words seen/unseen in that fold's child
fit vocabulary (uppercase exact text); these slices are not word-disjoint
evaluation. Show coverage and counts before interpreting subgroup metrics.

These outer development speakers have appeared in earlier experiments and may
have influenced the wider research direction. They are held out from their own
fold's fitting/selection, but are not a newly untouched final cohort. Fold
training sets overlap; five fold metrics are not five independent replicates.
No significance claim, independence-based confidence interval, deployment
promotion, clinical correctness claim or learner feedback follows this study.
Retain failures and proper-score tradeoffs regardless of ranking direction.

## Decision

Use the result to assess whether continuation checkpoint selection merits
further research. A gain on selection rows alone is insufficient. Mixed or
worse child outer results close this selection-policy lead for now. Here a
consistent ranking gain requires both primary contrasts to exceed 1e-7 and no
same-objective fold contrast below -1e-7; opposing fold signs or opposing
objective directions are mixed. This does not waive NLL/Brier tradeoffs. Even a
consistent gain is only development evidence and requires fresh independent
data before promotion. Existing learner judgments remain disabled.
