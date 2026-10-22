# Recovering labeled repeated-phone positions

Follow-up: the [complete cohort](multiphone-position-data-report.md) and
[scalar/geometry export](multiphone-position-geometry-report.md),
[full phonetic vectors](multiphone-position-phonetic-report.md), and
[twenty-fit comparison](multiphone-position-training-report.md) are complete.
The comparison is mixed and neither fitting regime passes its fixed gate. The
original feasibility assessment below describes the evidence before that work.

The September 27 train-only metadata audit identified **13,390 additional
labeled consonant positions** already available in the permitted SpeechOcean
recordings. The old recipe excludes a phone whenever it occurs more than once
in a recording. That avoids ambiguity for a whole-recording feature plus
phone-type model, but discards useful supervision for a model with a separately
estimated window at each canonical position.

This is a data feasibility result, not a newly built training set or measured
model improvement. The old cohort, features, models and contracts remain intact.

| Evidence | Existing eligible rows | All 23-target positions | Additional |
| --- | ---: | ---: | ---: |
| Positions | 14,837 | 28,227 | 13,390 |
| Child positions, ages 6–12 | 5,654 | 9,891 | 4,237 |
| Rating-0 votes, all ages | 3,911 | 7,803 | 3,892 |
| Rating-0 votes, children | 532 | 918 | 386 |
| Below-2 votes, all ages | 5,449 | 10,324 | 4,875 |
| Below-2 votes, children | 1,237 | 2,004 | 767 |
| Exact single-phone notes, all ages | 182 | 315 | 133 |
| Exact single-phone notes, children | 12 | 20 | 8 |

Counts are positions, five-rater votes or selectively supplied notes as labeled,
not independent participants. There are no new speakers or younger/SSD cohorts.
Annotations remain subjective ratings and sparse production notes without
verified phone times. All 23 per-phone denominators are retained in the
[complete supplemental inventory](../../work/phone-note-inventory-20260927/position-expansion.json).

The existing CTC-manifest recordings cover 13,347 additional positions,
including 4,217 child positions. Five previously excluded recordings contain
the remaining 43 positions, including 20 child positions. Their audio and
new extraction must be verified before inclusion. The current phonetic encoder
extraction saved pooled vectors only, so its cached unique-target vectors do
not provide repeated-target vectors for free. A separate older WavLM cache has
full frames, but those belong to a different encoder and feature contract.

## Required implementation

Simply removing the old filter would be wrong. In 1,522 repeated clip/phone
groups, occurrences have different ratings. A repeated /S/ at the beginning
and end of a sentence must retain two distinct identities and windows.

1. Build a fresh author-training cohort keyed by utterance, word index and
   within-word phone index, with a checked flattened canonical index. Reconcile
   every original eligible row exactly and retain all additional labels.
   Verify all five newly included WAVs against the pinned source archive.
2. Preserve the existing speaker assignments. Keep every occurrence from a
   speaker in the same fitting/validation/holdout partition. Repeated positions
   do not create independent data, and prompt overlap remains a limitation.
3. Build new feature manifests keyed by position. Reuse verified CTC arrays
   where possible, compute the five missing recordings, and estimate local
   windows for every requested occurrence. Re-extract the needed local encoder
   vectors; verify old-position parity and adversarial repeated-phone cases.
4. Compare fixed original-row and all-position fitting on the same speaker
   folds, architecture and features. Lock learning/stopping rules before new
   outcomes; report both the original evaluation positions and the expanded
   set, per-phone/age support and unfamiliar-word slices. Do not select on old
   outer results or call reused development data a final test.
5. Introduce a separate position-aware research inference contract after those
   checks. The existing raw adapter explicitly rejects repeated target phones;
   it must remain reproducible, and its guard cannot be silently relaxed.

No claim is made yet about whether the larger fitting set improves rare-error
detection or generalization. No new fit, encoder pass or app behavior change
has occurred. Learner pronunciation judgments remain disabled.

## Verified scope

The independent inventory checked source metadata pins, five-rater alignment
and means, unique word/phone and flattened position identities, original
14,837-row reconciliation and every existing CTC-manifest canonical sequence.
A second run reproduced the supplemental output byte for byte. It opened no
audio, model outcomes or author-test score objects.

Supplement SHA-256: `6465270e723c3fc6f845f05a8bb8ad3eaa34eb8197508ecca484cebb7235eaca`.
The [implementation-level findings](../../work/phone-note-inventory-20260927/POSITION-EXPANSION.md)
record the relevant existing constraints and source bindings.
