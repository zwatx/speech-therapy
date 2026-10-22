# Fixed uncertainty for expanded lexical fitting

This descriptive follow-up covers every comparison declared in the completed
[expanded fitting study](multiphone-lexical-expanded-heads-report.md). It does
not train or select a model, change weights, alter consistency decisions or
establish independent final validation. Keep all original and failed comparisons.
Declare source, tests, this protocol, inputs and completed numerical audit receipts
before actual resampling; keep them immutable afterward. Use fresh exclusive outputs.

## Fixed populations and comparisons

Use exactly the original 5,654 eligible positions from all 52 children aged 6–12,
with all 23 supported consonants. Retain historical original indices, including
ineligible gaps. Require exact expanded-to-original labels/identity, original
speaker folds and word groups. Match full original-population prediction arrays
and all 25 cells/five folds before restricting to children. Added and full expanded
populations are not substituted for the common historical comparison.

There are eight fixed contrasts: expanded scalar minus original scalar, expanded
PCA16/scalar minus original PCA16/scalar, expanded equal scalar/PCA mixture minus
original equal mixture, and expanded equal mixture minus original corrected-
projection mixture, each in both all-age and child-only fitting regimes. The first
three retain their primary status; the corrected-mixture contrast remains secondary.
Carry their exact original consistency records into the result. Do not select only
the favorable child mixture or change a failed check based on an interval.

## Paired whole-child resampling

Reuse the immutable `lexical_uncertainty.core` sampling and weighted metric
implementation. Use 2,000 NumPy PCG64 draws with seed 20260927, sorted speaker
identifiers and sorted original speaker-fold strata. Each replicate samples the
original number of children with replacement within each of the five folds. Every
position, recording and five-vote vector from a child receives that child's same
integer multiplicity. Do not resample positions, recordings, words or votes as
independent participants. Save one complete 2,000×52 multiplicity matrix and reuse
it across all models, regimes and contrasts.

Keep model predictions fixed. Intervals condition on the fitted models, original
folds and corpus and all adaptive development choices. They do not capture training
variability, overlapping training sets, new populations or repeated model search.
They are descriptive, not confirmatory significance tests, clinical confidence
bounds or evidence of independent final validation.

For each contrast and replicate report candidate-minus-reference differences in
five pooled endpoints: stable-log five-vote per-rater NLL; per-rater Brier;
unweighted mean NLL across the fixed 23 phones; rating-0 AP; and below-2 AP.
NLL/Brier weight positions equally, so children with more positions have greater
weight conditional on their sampling multiplicity. AP groups exact score ties
before accumulating positive-vote-weighted precision increments. AP is null with
zero positive votes and remains defined with positive votes but no negatives.
Fixed-23-phone macro NLL is null if any phone is absent; never change its denominator.

Report observed differences, 2.5/97.5 percentile endpoints using linear interpolation,
valid/undefined replicate counts and fractions of valid differences below/above
zero. These sign fractions are neither posterior probabilities nor p-values.
Retain nulls; do not redraw until a desired number of valid replicates or search
seeds, interval levels or estimands. Also report all 23 phone-specific NLL differences,
intervals, complete replicate arrays, absent-phone replicate counts and original
position/child/rater-vote support. These intervals have no simultaneous-coverage or
multiplicity-correction claim. Rare-event AP point estimates are not clinical accuracy.

## Fixed influence summaries

For every contrast and each of all five speaker folds, retain positions, children,
three-class vote counts, mean NLL difference and additive contribution to pooled
NLL difference (fold loss-difference sum divided by the complete child position
count). Fold contributions must sum back to the pooled difference. Do not focus
only on the previously troublesome fold 4 or whichever fold now looks favorable.

For every one of the 52 children, report pooled leave-one-child-out NLL difference
and removed/remaining position counts. Retain every child; these are influence
diagnostics, not a proposed exclusion policy. No model, threshold, mixture-weight,
phone, speaker, word-group or early-stopping change follows automatically.

## Verification and scope

Test row/fold/word pairing, old-index gaps and corrupted labels, duplicate/missing
membership, report lineage, complete stable probability arrays, immutable input
binding, no-resampling declaration, null support, tied scores, extreme stable logs,
integer whole-child pairing and stratum totals, quantiles, all-fold contributions
and leave-one-child-out identities. Check weighted endpoints against explicit
synthetic row duplication. Validate the observed contrasts against the completed
parent report before accepting any new intervals. Independently review source,
reconstruct results offline and independently check the actual multiplicities,
metrics, intervals, missing support and influence summaries.

No author-test audio, new data collection, audio/encoder/model inference, training,
Colab allocation, app or learner policy change is part of this analysis. Expert
produced-phone labels, ages 2–5 and an established speech-sound disorder cohort
remain absent. Learner judgments stay disabled. The full improvement goal remains
active regardless of this bounded analysis's outcome.
