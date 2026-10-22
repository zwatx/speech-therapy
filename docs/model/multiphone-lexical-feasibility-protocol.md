# Word- and speaker-disjoint development feasibility

Audit whether the original author-training cohort can support supervised
head evaluation on unfamiliar speakers and held-out orthographic word types.
This is a metadata-only support inventory, not a training or model evaluation.
The prior unfamiliar-word slices only checked vocabulary among fitted target
rows; the same words could occur elsewhere in a fitting utterance. Contextual
features require excluding complete utterances to address that exposure.

## Fixed grouping before support calculation

Use the existing content-pinned original cohort and five speaker splits.
Tokenize each complete canonical transcript with Python `str.upper().split()`;
keep punctuation, apostrophes and inflections literal. Verify every cohort row's
wordIndex points to exactly its uppercase targetWord in that transcript. Reject
inconsistent metadata instead of guessing a normalization. Group every unique
transcript token, including words with no supported consonant position, by:

`int.from_bytes(sha256(('cadence-lexical-holdout-v1\0' + token).encode('utf-8')).digest(), 'big') % 5`

The separator is one NUL byte. There is one fixed seed and five groups; no seed
sweep, stopword removal, rarity cutoff or support-driven regrouping is allowed.
Before any grouping results or support counts are computed, freeze the source,
tests, protocol, runtime and input hashes in a fresh declaration.

Use the full Cartesian product of five speaker folds and five word groups,
for both all-age and child-only fitting. This is 25 cells per regime, 50 metadata
cells total, with no head fits. The initial design considered a diagonal subset;
full crossing was chosen before computing any group support because it retains
every original eligible outer position exactly once per regime. It would require
25 heads per regime in a later experiment, rather than treating repeated fitting
populations as independent replications.

## Exact membership and exclusion

For speaker fold s and held-out word group w:

- Begin from the unchanged original inner fitting, inner validation and outer
  holdout speaker/row partitions. All-age fitting uses all eligible fit rows;
  child-only fitting uses ages6–12. Inner validation retains all ages; selection
  rows are all ages for all-age fitting and children only for child-only fitting.
- Exclude an entire fitting, validation or selection utterance if ANY token in
  its complete transcript belongs to group w. Include tokens outside eligible
  target rows, repeated occurrences and vowel-only words in this check.
- Apply the same exclusion to original outerFitRows for a possible future refit.
  Never reintroduce removed validation words through an outer refit.
- The outer evaluation cell contains only original outerHoldoutRows whose
  targetWord belongs to group w. Other words in an outer utterance may remain
  familiar; this tests novelty of the evaluated target type, not an entirely
  novel sentence. Save both retained and omitted row IDs.
- Assert fit/validation/outer speaker separation, exact retained/excluded
  accounting, and absence of every held-out group word from every retained
  fit/validation/selection/refit transcript. Empty sets are valid diagnostic
  findings, not a reason to change the grouping.

Retain the complete token-to-group mapping, per-group blocked clip IDs and
trigger tokens, and all cell row memberships. Pooled outer row coverage must
be exactly the original14,837 rows once per regime. Fit/selection/refit unions
across cells must deduplicate rows, clips and speakers; do not sum them as
participants. Every support view retains all23 consonants and explicit empty
cells. Report all-age/6–12/13-plus position, clip, speaker and word counts,
five-vote totals, event-positive/negative votes and contributing speakers for
rating0 and below2. Report retained and excluded populations separately.

## Feasibility interpretation

Report missing phones in every retained fitting/selection/refit/outer cell and
which phone/event cells lack positive or negative votes. These are structural
support facts, not a statistical power guarantee. Do not promote a split merely
because a minimal support check passes. Do not change seed, group count or rules
in response to sparse outcomes. Keep every shortcoming visible in the report.

A later experiment would require newly initialized heads, per-cell fit-only
normalization and priors, and selection using only the purged inner validation
speakers. Existing supervised heads or warm checkpoints may have seen held-out
words and must not be reused as a word-disjoint initialization. The frozen
encoder's pretraining word exposure is unknown; this is novelty relative to
subsequent supervised head fitting/selection, not a claim of never-seen words
throughout the model's history. Exact orthographic separation does not exclude
phonetic neighbors, inflections, homophones or sentence templates.

These author-training folds and outcomes have been used in development before.
The audit neither creates independent clinical validation nor accesses author-
test data. No audio or prediction payload is opened, no model inference/training
occurs, and no learner feedback/bundle changes are authorized by the counts.
Reconstruct the complete inventory offline, independently audit membership and
support, and only then choose a concrete next research step.
