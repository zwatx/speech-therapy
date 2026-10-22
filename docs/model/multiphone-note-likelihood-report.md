# Direct pronunciation-note diagnostic

September 27, 2026. The fixed recognizer favors the annotated substitute over
the expected sound in **163 of 182** selected comparisons. It places the
annotated token alone at the top of all 388 replacement candidates in only
**72 of 182**. This is evidence of useful acoustic discrimination in a narrow
subset, not reliable produced-phone recognition or an improvement to the
trained rating model. No weights changed.

The [protocol](multiphone-note-likelihood-protocol.md), source and eight focused
tests were frozen before joining annotations to saved model likelihoods.
The diagnostic reuses the complete-sequence CTC export; no audio, new model
inference, training or Colab allocation was needed.

## Actual annotation support

The independent [train-only inventory](../../work/phone-note-inventory-20260927/METHODOLOGY.md)
checked the original author metadata, all five rater sequences and means,
canonical positions and the existing cohort. It found 1,991 notes across
47,076 canonical positions. Note presence exactly coincides with average
rating below 0.5; absent notes do not mean correct production. This matches
the [authors' description](https://github.com/jimbozhang/speechocean762#the-mispronunciations-block).

Of 992 notes for the supported 23 consonants, 315 have exact unstarred
single-phone descriptions. The existing single-occurrence export covers 182
of these, across 144 recordings and 35 speakers. Only 12 comparisons, from
10 recordings and seven children, concern ages 6–12. They cover twelve
canonical consonants, one observation each: B, P, K, S, Z, SH, CH, JH, L, Y,
TH and DH. The other eleven have zero child support here. This is not a
training-grade child error corpus.

All 1,809 excluded notes remain in the report: 999 unsupported canonical
targets, 342 literal deletion markers, 227 unknown identities, 94 approximate
labels, 14 multi-phone descriptions and 133 exact notes outside the old
single-occurrence export. The categories follow the declared selection order;
they do not claim that only 133 notes occur at repeated targets. The separate
inventory accounts for 497 supported-target notes at repeated occurrences.

## Observed comparisons

| Group | Events / speakers | Noted token favored | Canonical favored | Noted token unique maximum |
| --- | --- | ---: | ---: | ---: |
| All ages | 182 / 35 | 163 | 19 | 72 |
| Ages 6–12 | 12 / 7 | 9 | 3 | 4 |
| Older than 12 | 170 / 28 | 154 | 16 | 68 |
| All ages, only one note in utterance | 15 / 12 | 14 | 1 | 7 |
| All ages, multiple notes in utterance | 167 / 29 | 149 | 18 | 65 |

There were no pairwise ties at the fixed 1e-8 tolerance. Median
noted-minus-canonical log likelihood is 5.1041 overall and 3.1129 for children.
The complete output retains every event, raw label, exact rank/tie count and
all 23 phones in each of nine age/context tables, including zero-support cells.

Each comparison changes only the noted slot; all other positions retain the
canonical sequence. Most utterances have additional notes, so the remaining
transcript is not a verified production. Existing provisional decoder mappings
also simplify vowels, rhotics, flaps and laterals. Source review identified and
fixed an omitted postvocalic-R limitation before declaration; both hypotheses
now retain the actual preceding phone and the full canonical mapping caveats.

These selectively severe, previously available training examples cannot measure
false positives, detection accuracy, clinical performance or generalization.
No missing-note controls, corrected-phone transcript, calibrated probability,
new winner or learner judgment is inferred.

## Verification and next action

Eight focused tests pass. An independent method/source review cleared the
selection, positional joins, mapping-context fix and statistical scope. The
actual saved report rebuilt exactly from its pinned inputs without inference.
Independent [saved-output audit](../../work/note-likelihood-audit-20260927/verification.json)
also passed: 159 bindings, all 1,991 notes, 144 consumed clips, 70,616 replacement
values, every comparison and all 216 total/per-phone summary cells matched.

The metadata audit exposed a concrete next data expansion: retaining every
supported canonical position would yield **28,227 rows rather than 14,837**,
including **9,891 child rows rather than 5,654**. Child rating-0 votes rise from
532 to 918; these are votes from the same children, not new independent cases.
The [expansion assessment](multiphone-all-position-feasibility.md) describes
the required position-aware cohort and feature changes. This is a stronger
next experiment than repeating the closed warm-tuning studies.

## Evidence

- [Declared plan](../../research/audio-head/outputs/multiphone-20260927/note-likelihood-v1/plan.json): `32246fad19a4af2d623a5fb121cfe69e5815c0ca090866a6d1b5f3f9ca5ee5a2`.
- [Saved diagnostic](../../research/audio-head/outputs/multiphone-20260927/note-likelihood-v1/report.json): `ea716ac5b04ff72576db140bc01dcec1cdef0b6e212ba179a0030c7265ffe340`.
- [Independent metadata inventory](../../work/phone-note-inventory-20260927/inventory.json): `46390471461249a1bb33cb4fd3581f241377217312be98b73a3793cb75a6036c`.

Broader application checks did not run: this adds isolated research analysis
and documentation. Author-test labels remain unopened and learner feedback
remains disabled.
