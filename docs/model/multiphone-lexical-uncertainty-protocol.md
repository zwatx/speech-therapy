# Fixed child-speaker uncertainty and contribution analysis

This descriptive follow-up examines the already observed equal-weight mixture
versus scalar comparison. It does not fit or select a model, change mixture
weights, relax the primary consistency screen, or establish independent final
validation. Source predictions, cohorts, declarations and prior audit receipts
remain hash-bound. Declare this protocol, source/tests and inputs before any
actual resampling or contribution calculation. Keep them immutable thereafter.

## Sampling and estimands

Use every original eligible child position (ages 6–12), all 52 children and all
23 phones in both training regimes. Require exact source row, speaker-fold and
word-group identity. Resample whole children within their original five speaker
folds, preserving each fold's child count. A child's complete positions, clips
and five-vote count vectors receive the same integer multiplicity. Do not
resample positions, recordings, words or individual votes independently.

Use NumPy PCG64 seed 20260927, 2,000 replicates, sorted speaker identifiers and
sorted fold strata. Save the complete multiplicity matrix and reuse it for both
models and both regimes. Keep the model predictions fixed; do not refit any
head or encoder. These intervals condition on the existing fitted models,
folds, corpus and adaptive development choices. Overlapping training sets,
training variability, new populations and repeated model search are not
accounted for. This is not a confirmatory significance test.

For each replicate calculate mixture-minus-scalar differences in the original
five pooled child endpoints: per-rater NLL from stable logs; per-rater Brier;
unweighted mean of the 23 phone NLLs; aggregate rating-0 AP; aggregate below-2 AP.
NLL/Brier weight positions equally (each position has five votes); larger child
recordings consequently contribute more positions. AP groups exactly tied
scores before summing positive-vote-weighted precision increments. AP is
undefined if positive vote mass is zero; it is defined even with no negatives.
The fixed-23-phone macro NLL is undefined when any phone is absent. Do not
silently change its phone denominator. Missing metrics are null, not zero.

Report the observed difference, 2.5/97.5 percentile endpoints using NumPy's
linear quantile interpolation, valid/undefined replicate counts, and fraction
of valid differences below/above zero. Conditional intervals explicitly retain
the number of undefined replicates; no resampling until a desired count of
valid replicates, no alternate seeds or percentile searches. The sign fractions
are descriptive bootstrap frequencies, not posterior probabilities or p-values.
Also report all 23 phone-specific NLL differences and paired intervals, with
absent-phone replicate counts and original positive/negative vote support.
No simultaneous coverage or multiplicity correction is claimed.

## Contribution diagnosis

For every speaker fold, and for fold 4 split by every child, every supported
phone, all five word groups and all three rating classes, report position/vote
support and the additive NLL contribution: group sum of per-position
mixture-minus-scalar loss divided by the complete fold's position count. Sum
each partition back to that fold's observed NLL delta. Retain absent phone/word
cells explicitly with zero contribution and null within-cell mean. Class
contributions decompose loss using original vote counts; their position support
is positions with any vote in that class and can overlap across classes.

Report pooled leave-one-child-out NLL differences for all 52 children and
fold-4 leave-one-child-out differences for each child in that fold. These are
descriptive influence diagnostics, not permission to exclude any child or tune
weights. Keep every original result and primary/secondary screen unchanged.

## Verification and limits

Test expanded-row equivalence, ties, missing classes/phones, stable extreme
logs, invalid input, paired weights and stratum integrity. Independently check
numerical calculations and actual resampling/results; reconstruct the complete
report offline. Preserve all failed calculations and require fresh output for
declaration. No author-test audio, new data, training, inference, Colab compute,
learner feedback or research-bundle promotion is part of this analysis.
