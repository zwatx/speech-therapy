# Original versus complete occurrence training

## Question and fixed comparison

Does retaining every supported consonant occurrence improve prediction of the
five-rater score distribution on held-out speakers? Compare original eligible
rows against all 28,227 position rows, using exactly the same 1,037 columns,
phone-conditioned head and five outer speaker folds. Run both all-age and
child-only (ages 6–12) fitting: two row populations × two age regimes × five
folds = twenty fresh fits. No weighting, warm-start, encoder update, LR sweep,
new epoch selection or changed architecture is part of this comparison.

Use the settings already selected on the original inner folds and retained in
the corresponding `head-outer/phonetic-target-scalars-*-refit/config.json`.
All-age learning rates are 0.0003 and epochs are [5, 3, 4, 4, 3]. Child-only
learning rates are [0.0003, 0.001, 0.0003, 0.001, 0.001] and epochs are
[5, 3, 7, 3, 2]. Both arms retain each fold's setting. Seed 7, CPU two threads,
batch size 64, hidden width 128, dropout 0.1, AdamW weight decay 0.01 and
maximum gradient norm 5 remain fixed. Each row is weighted equally and its
five-vote distribution defines ordinary soft-label negative log likelihood.
More rows therefore imply more optimizer updates per epoch; this tests the
complete training-data expansion, not a fixed-update data-value estimate.

Normalization uses only the arm's actual fit rows: float64 population moments
cast to float32; standard deviations below 1e-6 become one. Old-row arms must
preserve original row order before shuffling and exactly reproduce historical
normalization, every epoch's training loss and final model tensors. Failure
stops the comparison. Expanded fits use occurrence order. The only label
inputs are author-train corpus ratings. Split speaker membership is unchanged.

## Freeze before evaluation

Declare all twenty runs, input/source/protocol hashes and exact fit/holdout
memberships before fitting. Fit every run to its fixed count, save checkpoint,
history and fit-only per-phone prior, then freeze all twenty artifacts before
producing any new held-out prediction. New directories only; no implicit
restart, omission or overwrite after failure. Model and checkpoint replay must
match exactly. Preserve both successful and failed evidence.

## Reporting and decision

For every model, predict all outer-held positions exactly once. Report three
explicit populations: original positions (14,837; 5,654 child), all positions
(28,227; 9,891 child) and newly added positions (13,390; 4,237 child). Within
each, retain all ages, ages 6–12 and ages 13-plus results; all 23 phone support cells;
five-rater NLL/Brier; rating-0 and below-2 AUROC/AP; and confidence summaries.
Absent positives/negatives yield undefined metrics, not zero or omitted phones.

Report seen/unseen target-word slices using the original-row fit vocabulary
for both arms, so each comparison has the same denominator. Also retain each
arm's actual fitting vocabulary and membership flags. A target word absent
from fit target rows may occur elsewhere in its recordings: this is not a
word-disjoint study. Preserve every fold and pooled prediction, plus each
arm's own smoothed fit-only prior. Do not select an age regime from these
outer results.

The fixed research-lead rule is evaluated separately for each age regime.
For both the original-position and all-position child populations, expanded
training must improve pooled below-2 macro-phone AP by more than 1e-7, lose
no more than 1e-7 in any fold's below-2 macro-phone AP, and worsen neither pooled
rating-0 macro-phone AP, macro-phone NLL nor per-rater Brier by more than 1e-7. All required metrics
must be defined. The exact fields in each `allWords.metrics.ages6to12` table
are `targetDiscrimination.macroTarget.ratingBelow2.averagePrecision`,
`targetDiscrimination.macroTarget.rating0.averagePrecision`,
`macroTargetLogLoss`, and `perRaterBrier`. AP is the existing within-phone
five-vote-weighted calculation, averaged over supported phones; retain the
phone support/undefined cells alongside every macro value. A missing required
aggregate makes the rule fail, rather than dropping a fold or a criterion. Report the added-only population descriptively. Passing this
rule suggests further research; it never enables learner feedback or implies
clinical validation. No new significance or independence claim is made.

These are reused development speakers and prompts, now with more scored
occurrences, not an independent cohort. No ages 2–5 or independently labeled
speech-sound-disorder population has been added. Author-test objects remain
closed; learner/clinical/production eligibility remains false. A subsequent
research adapter for repeated occurrences requires its own interface contract
and verification and is not granted by this feature/training experiment.
