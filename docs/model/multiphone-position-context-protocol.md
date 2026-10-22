# Context of target positions outside padded VAD output

Follow up the completed target-overlap diagnostic using its exact 28,227 rows,
2,500 author-training recordings, both fixed duration policies and all 23
consonants. This is a descriptive diagnosis of detector/alignment mismatch,
not a filtering, training or correctness rule. No waveform or model inference
is needed; retain original five-vote support and all original/added positions.
The overlap results are already observed, so this is a declared follow-up on
development data, not a fresh independent validation.

## Exhaustive geometric categories

Use the same doubled center coordinates `640*i + 399` and half-open padded
VAD intervals. Classify every position independently under 100 ms and 250 ms:

1. `centerInside`: at least one occupied-frame center inside a VAD segment.
2. `noSegments`: the detector produced no segments in the recording.
3. `beforeFirst`: every occupied-frame center is before the first segment.
4. `afterLast`: every occupied-frame center is at or after the last segment end.
5. `internalGap`: all occupied-frame centers lie in one gap between consecutive
   segments, at or after the left segment end and before the right segment start.
6. `segmentBetweenCenters`: no center is inside, but the center span crosses a
   segment. Retain this exhaustive fallback even if impossible with the current
   minimum-duration parameters; do not silently assign it to a single gap.

Precedence is the order above. Categories are mutually exclusive and exhaustive.
“Before/after” refers to detected segments, not verified utterance boundaries;
“gap” does not prove silence. For every row save the containing gap's sample
interval when defined: recording start to first segment, between consecutive
segments, last segment to recording end, or whole recording if no segments.
A center-inside or segment-between-centers row has no single containing gap.
Save the exact minimum distance from any occupied-frame center to any segment
as doubled samples; zero for center-inside and null for no segments. A segment's
exclusive end uses its distance infimum, not rounded integer membership. Derive
milliseconds as doubled samples / 32. No distance cutoff is selected.

## Alignment and prompt context

Retain the original diagnostic flags and all thirteen scalar features. Report
separately the existing fewer-than-two-frames flag and existing target-not-argmax-
on-most-occupied-frames flag (fraction strictly below .5), plus their conjunction.
Verify each against the frozen interval/feature recipe. These are alignment
warnings, not verified alignment errors. Every position remains explicitly
unverified. Preserve utterance-wide canonical-mapping caveats at clip level;
do not present a caveat elsewhere in an utterance as a target-specific defect.

Record whether the canonical phone is first/last in its word and first/last in
the complete prompt. Keep these as overlapping Boolean counts: a single-phone
word can be both first and last. These indices are prompt positions, not actual
spoken boundaries. Do not equate a first-word consonant with an utterance's
first canonical phone. Retain existing occupied/pooling footprint-disjoint
indicators so wider-context cases remain visible.

## Complete support and verification

For each duration policy, original/all/added population, all ages/6–12/13-plus,
and aggregate/all 23 phones, report all rows, zero-center rows, and each of the
six mutually exclusive categories. Each view retains distinct clip/speaker
sets, five-vote totals, any-0/any-below-2/all-top position counts, the context
Boolean counts and footprint-disjoint counts. Report count, minimum, median,
90th percentile and maximum of finite nearest-distance milliseconds; no-segment
nulls are excluded and counted separately. Report the same descriptive summaries
for occupied-frame counts, target posterior mean and blank posterior mean.
Quantiles use NumPy's fixed linear method. Empty numeric views have count zero
and null summaries. All row-level values remain saved.

Category position and vote totals must reconcile with the full view, and the
five zero-center categories must reconcile with the zero-center view. Preserve
set-union semantics for distinct clips/speakers, including original/added
accounting. Report every cell, including zeros; do not choose phone subsets by
outcome or drop low-confidence positions.

Bind the prior overlap declaration/report, all inherited source/data inputs,
the four fresh VAD records, geometry/cohort, this protocol, new source/tests and
runtime before calculation. Verify complete unique row identity and inherited
support before classification, then reconstruct all output without model
inference. Save exclusive start/failure artifacts; do not overwrite runs.
Tests cover exact half-sample boundaries, before/after/internal/no-segment and
between-center cases, multi-frame distance, invalid segments/geometry, prompt
boundaries, diagnostic-flag consistency, rare votes and non-additive speaker
counts. Independent review checks exhaustive categories, exact distances,
all cells and conclusions. No source or protocol pinned by an earlier study
is edited. No model fitting, threshold search, author-test access, new data,
Colab allocation, production withholding change or learner judgment is enabled.
