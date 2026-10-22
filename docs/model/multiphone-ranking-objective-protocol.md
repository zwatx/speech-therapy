# Fixed child rating-ranking objective comparison

Status: independently reviewed and fixed on September 26, 2026, before new
ranking implementation or fitting. Bind this file and the executable recipe
before the fitting-only equivalence check and any new supervised fit.
This is an exploratory follow-up after the prior
development comparisons, not an untouched confirmatory evaluation.

## Question and scope

The completed child fits improve probability fit without consistently improving
within-phone rare-rating ranking. The question is whether one explicit ranking
auxiliary objective changes that tradeoff using the same features, architecture,
warm checkpoints and speaker partitions. This is not a new pronunciation label
task, a clinical error detector, or evidence that pairwise objectives are
inherently better. Proper non-pairwise losses can also support good ranking;
the result depends on fitting, finite data and model constraints
([Agarwal, 2014](https://www.jmlr.org/papers/v15/agarwal14b.html)). The pairwise
logistic mechanism follows ranking-loss work, with the corpus-vote weighting
specified explicitly below
([Burges et al., 2005](https://www.microsoft.com/en-us/research/publication/learning-to-rank-using-gradient-descent/)).

Add exactly **five new fits**, one per existing inner fold, using only the
child fitting population (ages 6–12). Compare them with the five already
declared child-only coefficient-zero continuation controls from the original
noise study and its four-fold replication. Those controls never forward noisy
inputs during fitting. No duplicate control fitting, new encoder, new learning
rate, new population, coefficient search or outer evaluation is introduced.
The final report waits for all five controls and new arms to finish and replay.

## Fixed model and supervised component

Use the existing 1,037 clean features, original three-class head and same-fold
unweighted child warm checkpoint at original learning rate .0003. Use its
saved fit-only normalization. Preserve the original child fit/validation rows,
source identities, selected warm epoch and exact warm predictions.

Continuation uses seed 7, evaluation mode with gradients (dropout disabled),
AdamW learning rate .00003, weight decay .01, 64-row clean NLL batches, gradient
clipping at 5, and the existing seed-7 NumPy row permutation. The clean term
is ordinary five-rater distribution NLL. No new label is assigned to any clip.

Both controls and new arms permit epoch zero, run at most six epochs and stop
after two epochs without a clean child macro-phone NLL improvement greater
than 1e-7. Earlier exact ties stay selected. Ranking metrics never select an
epoch, target, coefficient or checkpoint.

## Auxiliary pair distribution and loss

The two corpus-rating events are rating 0 and rating below 2. For an event,
let q_i be its observed fraction of five votes at clean target position i.
For logits z, the stable scores are:

- Rating 0: z0 − logsumexp(z1, z2).
- Rating below 2: logsumexp(z0, z1) − z2.

For each phone/event cell, the intended loss is the weighted mean of
softplus(s_j − s_i) over ordered pairs i != j from its fitting rows, with
weight q_i(1 − q_j). Both directions are represented when the ratings are
mixed. Identical target rows are excluded; no rater-disagreement threshold
creates a hard correct/incorrect label. These weights describe draws from
marginal vote distributions, not matched judgments by an individual rater.

Draw **64 independent ordered pairs per optimizer update** using a separate
NumPy RNG seeded 20260926. For each pair choose an event uniformly, then a
phone uniformly among that event's positive-mass fitting cells. Sample i
proportional to q_i[sum_j(1 − q_j) − (1 − q_i)], then j != i proportional to
(1 − q_j). This is exact sampling from the specified cell distribution. The
plain mean sampled softplus is the auxiliary loss; do not multiply by the vote
fractions again. Do not use accidental pairs inside the NLL minibatch.

The total update objective is **mean clean NLL + .1 × mean pairwise loss**.
The auxiliary coefficient and pair count are fixed. The last, possibly smaller
NLL minibatch still uses 64 auxiliary pairs. Save NLL batch identities or a
deterministic digest, sampled-pair identities/digests and the separate RNG
recipe so the paired control's supervised order can be verified.

Same-speaker pairs remain eligible when their row IDs differ. Excluding them
would change the objective and would not make the remaining pairs independent.
Save each phone/event's positive/negative vote mass and distinct supporting
speakers, total pair mass, and expected same-speaker pair fraction. Zero-mass
cells are excluded from that event's pair sampler but remain in NLL and the
reported target inventory. Do not add a new support cutoff. One-child support
remains one child regardless of the number of sampled pairs.

The [fit-only support assessment](../../research/audio-head/outputs/multiphone-20260926/pairwise-sampling-support-assessment-v1.json),
SHA-256 `cefb950e7cfddc80ca3de7bbbc1775240f3fbd31c199085668545cfbc60c7d92`,
was independently reconstructed before this declaration. Of 230 phone/event/
fold cells, only /G/ rating 0 in folds 0 and 3 has zero pair mass. Sixteen
cells have just one child at the positive endpoint. Same-speaker pairs account
for 2.36–3.07% of the specified sampler's expected mass by fold; the most
represented child participates in 15.16–17.50% of draws. Pin this assessment
and recompute the corresponding fitting-only support in the trainer.

## Preflight and verification

Before new fitting, verify that the new auxiliary-disabled update is exactly
equivalent to the frozen original coefficient-zero update. Use a meaningful
synthetic mixed-vote case and a fitting-only actual warm-head case; compare
losses, model and optimizer state, normalization, target IDs and supervised
row order. No validation outcome chooses settings. A failed equivalence check
blocks reuse of the controls until the implementation difference is resolved.

Tests must cover the analytical joint-pair probabilities, mixed-rater reverse
pairs, same-row exclusion, zero-support cells, stable extreme-logit scores,
no squared weighting, fit-only inputs, separate RNGs and unchanged NLL batch
ordering. Freeze source/recipe/input pins, use fresh output directories, save
checkpoints and histories, and require a separate exact selected-checkpoint
replay before reporting an arm complete.

## Reporting and limits

Retain all five original warm checkpoints, five NLL controls and five new arms.
Report clean NLL, per-rater Brier, both within-phone AUROC/average-precision
events, per-phone support, mean class probabilities, entropy and argmax counts.
Keep per-epoch ranking measurements as diagnostic histories; do not choose a
ranking-best epoch afterward. Compare selected arms against both their own
warm checkpoint and matched continuation control, preserving undefined cells.

Report every fold and descriptive equal-fold means with signed differences;
the inner validation speakers overlap, so do not imply five independent
replications or inflate child counts by summing fold memberships. Keep unique
child/clip/position counts alongside membership totals. Any effect belongs
to this objective **and its sampling distribution**, not an isolated causal
claim about ranking losses in general.

This objective has no global log-weight correction. Probability fit or Brier
does not by itself establish calibration; retain confidence changes and any
proper-score harm. No noisy labels, accuracy percentages, decision thresholds,
learner feedback, new full-data winner export, child/SSD suitability claim or
author-test inference follows. The four existing research bundles remain
unchanged, and independent qualified child data remain necessary.
