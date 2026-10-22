# Target-position overlap with padded VAD segments

Measure overlap for all 28,227 supported positions in the fixed 2,500-recording
author-training cohort. This is a diagnostic, not a new filtering policy.
Keep all 23 consonants, original and added positions, and all speaker/vote
support. Do not select or tune a threshold, change model scores, or enable
learner judgments based on this analysis.

Reuse the original 2,495 audio-bound VAD probability records and the verified
position-filter record for 000530027. Run only the four missing fixed Silero
passes: 001040026, 005600146, 010420047 and 096110011. Reset state per recording
using the existing reviewed implementation. No speech encoder, head training
or new CTC inference is required. Reconstruct the saved 250 ms segmentation
exactly, then compute the existing 100 ms segmentation from the same probabilities.
The 100 ms rule is primary; 250 ms is the fixed reference, not another search.
All VAD parameters remain unchanged, including 30 ms speech padding.

## Exact time mapping

Derive the fixed convolution stride and receptive field from the pinned kernel
and stride recipe: 320 and 400 samples. At 16 kHz, frame i has center
`320*i + 199.5` samples. For half-open VAD intervals `[start,end)`, compare
`2*start <= 640*i + 399 < 2*end` to avoid rounding the half-sample center.

For each saved canonical occupied-frame interval `[s,e)`, retain:

- Number and fraction of its frame centers inside any padded VAD segment.
- The frontend receptive-field union `[320*s, 320*(e-1)+400)` and its overlap
  with the union of padded VAD segments, in samples and as a fraction of that
  footprint's length.
- The corresponding union and overlap for the fixed pooling window, extending
  two frames on each side and clipped to the actual frame grid.

Segments must be ordered, disjoint and inside the WAV; touching interval
boundaries contribute no sample overlap. Validate saved frame-center estimates,
frame counts and pooling geometry. These are convolutional frontend footprints,
not the contextual Transformer's complete support and not verified articulation
boundaries. Overlap with padded detector output does not prove a target phone
was produced, and no overlap does not prove the target was silent or incorrect.

## Complete support report

Retain every occurrence ID, word/phone index, clip/speaker/age, original-row
link, original five-vote counts, both frame intervals and all overlap measures.
For each policy, report original/all/added populations; all ages, ages 6–12 and
ages 13-plus; all 23 phones and an aggregate. Report mean overlap fractions,
with null for empty cells. Define these five support views:

- Every position.
- At least one occupied-frame center inside a padded VAD segment.
- Zero occupied-frame centers inside any padded VAD segment.
- The entire occupied frontend footprint is disjoint from VAD segments.
- The entire pooling frontend footprint is disjoint from VAD segments.

Each view reports positions, distinct clips/speakers, the three rater-vote
counts, positions with any rating-0 vote, positions with any vote below 2, and
positions with all five votes equal to 2. These are corpus ratings, not clinical
correctness labels. All-top means exactly `[0,0,5]`; a rare rating does not need
a majority. The last two disjoint-footprint views are nested subsets of the
zero-center view; they are not additional disjoint categories to sum.

Reconcile original plus added position/vote counts with all positions in every
cell. Compute clip/speaker counts as set unions; they can appear in both
populations and therefore must not be added. Do not use corpus labels to select
a segmentation setting or an abstention threshold.

## Verification and scope

Freeze protocol, code/tests, cohort, all 2,500 audio bindings, saved geometry,
2,496 reused VAD records and model/runtime sources before calculation. Require
unique clip/position IDs and exactly four new passes. Preserve failures and use
fresh output directories without implicit retry or resume. Tests cover exact
half-sample boundaries, touching/disjoint intervals, empty VAD output, multiple
frames, invalid geometry, contextual-window overlap and vote/set accounting.
An offline verifier reconstructs every measurement and table; independent review
checks mapping, coverage, support and conclusions.

No author-test audio, new corpus acquisition, model fitting, threshold fitting,
production withholding change, clinical validation or Colab allocation occurs.
Potential exclusion of unvoiced consonants and high-rated positions is evidence
to inspect, not permission to label those positions incorrect or discard them.
