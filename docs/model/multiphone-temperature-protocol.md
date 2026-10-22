# Fixed child-targeted temperature calibration study

Test one positive shared temperature per fold for each of the existing
phonetic target-plus-scalars all-age and child-only pipelines. Use the original
14,837 eligible positions and their five corpus ratings, including all 23
consonants. The motivation is the completed development reliability diagnostic:
mean lower-rating probability differs from observed vote frequency in opposite
directions for the two pipelines. No corrected result has been computed yet.
This is a bounded ten-fit comparison, not a temperature grid or per-phone search.

Temperature scaling is a one-parameter probability correction described by
[Guo et al. (2017)](https://proceedings.mlr.press/v70/guo17a.html). Here the
objective is explicitly adapted to five-rater soft corpus labels; it does not
estimate a child's probability of clinically correct pronunciation.

## Fit membership and correction

For each pipeline's five folds, use exactly its already selected original
inner checkpoint. Replay its saved validation predictions exactly from the
bound features/checkpoint without new encoder inference or head fitting.
Select only children ages 6–12 in that fold's inner validation set to fit the
correction for either age regime. Keep all 23 phones, including mixed votes.
Verify that calibration speakers are disjoint from the corresponding inner
head-fitting and outer-held-out speakers. This is 545/967/784/753/1,196 child
positions from 5/9/7/7/11 children per fold; overlapping folds contain 2,954
unique positions from 27 children, not their summed number of participants.

The same inner validation set previously selected the checkpoint. Reusing it
for correction is development fitting, not independent calibration validation.
The existing outer refit changes the head after inner selection; transferring
the correction to that refit must be evaluated rather than assumed valid.
All outer folds have been inspected in previous development studies, so they
are not an untouched final test. Author-test data remain closed.

Validate saved Nx3 probabilities as finite, strictly positive and summing to
one within 1e-6. Normalize each row once in float64 to remove float32 sum drift,
and retain the maximum change. The uncorrected comparator is this explicitly
normalized baseline; also reproduce the raw historical baseline metrics and
record its difference from the normalized comparator. Do not clip or impute
zero probabilities. Historical metric helpers used a 1e-12 NLL floor. Retain
those raw historical values for reproduction only; compute all new normalized
and corrected NLL, conditional class NLL and entropy from stable finite log
probabilities, including every age/word/phone view. Save both log and ordinary
probabilities and count values below the legacy floor. Identity inverse temperature must reproduce the normalized
baseline exactly.

Let q be the normalized baseline and beta = 1/T. Return
`softmax(beta * log(q))`, using stable float64 arithmetic. Fit beta within fixed
[0.05, 20] by minimizing equal-position five-rater NLL. Every row's target is
its original three integer vote counts divided by five. The loss is convex in
beta. Use its monotone derivative and 80 deterministic bisection iterations,
or the appropriate bound if its derivative proves the constrained minimum is
there. In the exactly flat uniform case use identity beta=1. Retain endpoint
status, objective at identity and optimum, derivatives, curvature and temperature.
The fixed numeric bounds are not chosen from results. No offsets, phone-specific
coefficients, class weights, new head parameters or alternative correction are
added. In-sample fit improvement is not evidence of generalization.

## Freeze before outer evaluation

Bind the selected inner config/checkpoint/prediction/history lineage, both
original LR candidate artifacts and selection rule, feature inputs, cohort,
splits, source/tests/protocol/runtime and existing outer-comparison report
before fitting. Hashing that historical report does not fit to its outcomes.
Use exclusive fresh output/start/failure artifacts. Freeze all ten scalar
corrections, actual replay receipts, child fit-row IDs and fitted outputs before
opening outer prediction payloads for this study. A separate audit command must
require the freeze's content hash; no implicit refit after outer evaluation.

Then use the existing reviewed outer-prediction loader and released refit chain.
Apply each frozen correction only to its matching pipeline/fold and compare to
the same normalized baseline. Retain every outer row exactly once per pipeline;
verify original speaker isolation, canonical row identity and unchanged argmax
labels for positive temperature. Save raw, normalized and corrected vectors;
never infer predictions from reported metrics. Every lower-rating ranking
measure must be recalculated: multiclass temperature need not preserve event
ranking, especially when pooling folds with different temperatures.

## Outcomes, support and decision

Report both models without selecting a winner. Preserve all-age/6–12/13-plus
NLL, Brier, macro-phone NLL, rating-0/below-2 AUROC and AP, probability means,
original five-vote support and all 23 per-phone cells. Report each fold and the
pooled out-of-speaker predictions. Include seen/unseen target-word slices using
the matching original outer fitting vocabulary; these are descriptive slices,
not word-disjoint experiments. Include fixed ten-bin event reliability for
rating 0 and below 2, with aggregate/per-phone and age support; retain empty
bins/cells explicitly. Clip and speaker counts use distinct sets, never sums
across repeated positions or overlapping inner folds.

The primary probability-quality endpoint is child per-rater NLL. For each
pipeline, report a predeclared consistency screen: pooled child NLL improves
by more than 1e-12; each of five child fold NLL values is no worse within 1e-12;
pooled child macro-phone NLL and Brier are no worse within 1e-12; and both pooled
child rating-0 and below-2 AP are no worse within 1e-12. These screen AP values
use pooled vote-weighted discrimination, not the equal-phone macro AP; both
aggregations remain reported. Report every constituent,
every fold/per-phone result and all tradeoffs even if the screen fails. This
screen is descriptive and not a significance or clinical calibration claim.
It cannot enable learner feedback or automatically replace the four bundles.

Tests cover identity, analytic known-optimum soft labels, derivatives/curvature,
constrained endpoints, flat/extreme probabilities, invalid inputs, argmax
preservation and fold/row/speaker guards. Reconstruct all fits and outputs
without refitting heads; independently review source, parameters, metrics,
rare support, word slices and the report. No new audio, author-test access,
encoder training, production judgments or Colab allocation is required.
