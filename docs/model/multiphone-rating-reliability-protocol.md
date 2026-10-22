# Fixed child corpus-rating reliability diagnostic

Declared September 26, 2026, after the completed development comparison and
before computing this diagnostic. Better NLL or Brier does not by itself show
where predicted rating probabilities agree with observed rating frequencies.
This descriptive check addresses that reporting gap. It adds no training,
inference, temperature scaling, threshold, model selection or clinical claim.

## Fixed population and predictions

Use the existing, pinned development comparison only: all 5,654 eligible
positions from 52 children aged 6–12, each with five original corpus votes.
Use exactly four saved out-of-speaker prediction sets:

- Phonetic target plus scalars, all-age fitting.
- Phonetic target plus scalars, child-only fitting.
- Full13 scalar reference, all-age fitting.
- The matched child-fit phone prior from each outer fitting partition.

These are the previously declared fold refits, not the four full-data research
exports. Every prediction excludes its speaker from fitting. Earlier model
choices used overlapping development outcomes, so this is an exploratory
development diagnostic, not untouched calibration validation. No author-test
audio or predictions are opened.

## Two fixed rating events and summaries

For rating 0, compare predicted p0 with the observed fraction of five votes
assigned 0. For rating below 2, compare p0+p1 with the fraction assigned 0 or 1.
Do not threshold votes, use an argmax-correctness target, or count five votes as
five independent children. Positions receive equal weight; all have five votes.

For each model/event, use exactly ten fixed equal-width probability bins:
[0,.1), [.1,.2), ..., [.8,.9), [.9,1]. A value on an internal boundary belongs
to the bin on its right; 1 belongs to the final bin. Retain all empty bins with
zero support and undefined means. Do not change bins after seeing results.

Within each bin report position, clip, phone and distinct-child counts; positive and
negative vote counts; number of children with any positive vote; mean predicted
event probability; observed vote fraction; and their signed difference
(prediction minus observation). Preserve mixed-vote positions. Report overall
mean predicted probability, observed event prevalence and signed difference,
plus the position-weighted mean absolute binned difference. This last quantity
is a finite-bin descriptive residual, not a population calibration certificate.

Retain the same complete bin table for every eligible phone and separately for
every outer fold, alongside the pooled table. Also report the equal-phone mean
of the 23 per-phone absolute binned residuals, clearly distinguished from the
pooled position-weighted summary. Pooling can conceal opposite errors across
phones or folds; per-phone tables and their denominators remain primary context.

No confidence interval, significance test, independent-bin/phone assumption,
best-model ranking, calibration correction or operating threshold is produced.
Children and raters recur across positions; sparse high-probability bins and
finite binning limit interpretation. Empty bins do not mean perfect agreement.
Different models assign different positions to bins, so comparisons within a
bin are not paired comparisons of identical recordings.
The fixed bins follow the reliability-diagram idea described by
[Guo et al. (2017)](https://proceedings.mlr.press/v70/guo17a.html), adapted here
explicitly to corpus-vote events rather than predicted-label correctness.

## Integrity and output

Reuse the existing reviewed development-prediction loader and its complete
release, cohort, split, checkpoint and saved-prediction guards. Bind this
protocol, source, report, loader and all used inputs before computation and
recheck them before publishing. Verify row identities, integer vote counts,
probability bounds/sums, and that every position belongs to exactly one bin.
Tests cover exact boundaries, zero/one, mixed votes, empty bins, repeated-child
denominators, signed differences, weighting, and invalid probabilities/votes.

Keep every model/event/phone/fold result in one fresh local JSON and a concise
Markdown comparison. A lower residual here does not establish useful sound
error ranking, calibration on new children, device robustness, SSD suitability,
or pronunciation correctness. Neither ages 2–5 nor qualified produced-phone
labels are supplied by this diagnostic. Existing research bundles and native
learner behavior remain unchanged.
