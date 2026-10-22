# One fixed scalar/compact probability mixture

The [compact study](multiphone-lexical-compact-report.md) improved all-age child
rare-rating ranking while slightly worsening pooled child NLL against scalars.
This follow-up tests one equal-weight probability average. It is an adaptive
development comparison motivated by exposed results, not untouched validation.

## Fixed inputs and arithmetic

Use the complete frozen scalar and PCA16/scalar outer predictions from the
previous canonical word/speaker studies. Match all 25 speaker×word cells in
each of the all-age and child-only training regimes. Require identical original
inner-fit, selection, refit and outer row memberships, speaker folds, word
groups, and five-rater labels. Check complete source declarations, refit and
outer freezes, checkpoint lineage and content hashes. Existing whole-utterance
word exclusions and speaker separation are inherited unchanged.

Calculate exactly one mixture in each regime: half scalar probabilities plus
half compact probabilities. The same .5/.5 weights apply to every class, phone,
speaker, word and row. No model, PCA, calibration, threshold or weight is fitted.
There is no grid search, per-phone family selection or outcome-based gate.
Do not average logits or log probabilities directly. For each class compute
`logaddexp(logScalar, logCompact) - log(2)` in float64, and exponentiate that
stable log to obtain the ordinary probability used for ranking and Brier.
Inherit the normalized stable source logs; use no probability floor, additional
normalization or correction. Preserve finite stable logs even when an ordinary
probability underflows to zero. Mixture NLL uses the original five-vote counts
and stable logs. Source raw float32 probabilities remain in their pinned
artifacts; no new network or raw float32 output is fabricated.

Freeze this protocol, source, exact pairs and reference reports in a separate
declaration before calculating any mixture. Retain the complete source pins in
the declaration, cell predictions and report. Use a fresh output directory,
preserve failures and reproduce the full saved report offline. No head or
encoder inference, transform calculation or training is needed for this study.

## Outcomes and fixed assessment

Retain all 25 cells per regime and pool every original eligible outer position
exactly once: 14,837 positions from 125 speakers, including 5,654 positions from
52 children aged 6–12. Preserve all 23 consonants, absent-phone metrics and
undefined rare-rating quantities. Report original speaker/word/recording/vote
support; five votes and repeated overlapping fit populations are not additional
independent participants. Summarize all-age, child and age-13-plus populations,
25 cells, five speaker folds pooling word groups, and pooled outcomes.

The primary comparison is mixture versus scalar. Use the same fixed consistency
screen: pooled child NLL improves by more than 1e-7; all five speaker-fold child
NLL values are no worse within 1e-7; pooled child macro-phone NLL and Brier are
no worse within 1e-7; pooled child rating-0 AP and below-2 AP are no worse within
1e-7. Report every check and difference, even if the screen fails. Apply the
same checks against compact as a secondary descriptive comparison, and report
mixture-minus-matched-prior pooled child differences. A secondary gain cannot
replace the primary comparison, and neither screen authorizes promotion.

Keep complete per-phone NLL/Brier/AP/AUROC, conditional NLL, reliability,
confidence and support. Do not choose favorable folds, phones, regimes or
weights after observing mixture outcomes. No parameter search follows a failure
of this one fixed average.

## Verification and interpretation

Test equal-probability arithmetic against ordinary means and a high-precision
Decimal reference, extreme log probabilities, component swapping, identical
components, row/partition mismatches, malformed probabilities/counts and
declaration-before-calculation guards. Independently review source, reconstruct
all 50 mixture vectors from pinned source logs, verify source/checkpoint and
partition lineage, reproduce all metrics/support and assess narrative claims.
Tests and auditors must not use the mixture helper as their numerical oracle.

This method requires both existing heads at inference time; a retrospective
saved-prediction calculation does not implement a deployable ensemble adapter
or establish end-to-end latency. Previous reports already verified the source
head outputs. This study adds mixture arithmetic and evaluation, not fresh
head replays. Any apparent gain remains development evidence on repeatedly
studied speakers. Pretrained lexical exposure is unknown; no child-SSD cohort,
ages 2–5 or verified produced-phone ground truth is introduced. Existing research
bundles and learner judgments remain unchanged. No author-test, new audio,
Colab allocation or app change occurs; app builds/UI tests are unnecessary for
this research-only calculation.
