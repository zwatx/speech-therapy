# Expanded occurrence support under strict lexical exclusions

The complete inventory preserves every original speaker and word exclusion while
adding 13,390 consonant occurrences, including 4,237 child occurrences. All 50
crossed cells retain exactly the original examples in their original partitions.
This establishes usable additional training support, not better predictions.
Rare child ratings remain sparse; learner pronunciation judgments stay disabled.

## Corpus support

“Added” means occurrences absent from the original export, mostly from existing
recordings. Speaker, recording and word counts overlap between strata and must
not be added as independent participants. All 125 speakers, including 52 children
aged 6–12, were already present. Five additional recordings include three child
recordings. Ratings are five subjective corpus votes per occurrence, not verified
produced-phone or clinical labels.

| Population | Stratum | Positions | Recordings | Speakers | Rating-0 votes | Below-2 votes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| All ages | original | 14,837 | 2,495 | 125 | 3,911 | 5,449 |
| All ages | added | 13,390 | 2,262 | 125 | 3,892 | 4,875 |
| All ages | all | 28,227 | 2,500 | 125 | 7,803 | 10,324 |
| Ages 6–12 | original | 5,654 | 1,037 | 52 | 532 | 1,237 |
| Ages 6–12 | added | 4,237 | 900 | 52 | 386 | 767 |
| Ages 6–12 | all | 9,891 | 1,040 | 52 | 918 | 2,004 |
| Ages 13+ | original | 9,183 | 1,458 | 73 | 3,379 | 4,212 |
| Ages 13+ | added | 9,153 | 1,362 | 73 | 3,506 | 4,108 |
| Ages 13+ | all | 18,336 | 1,460 | 73 | 6,885 | 8,320 |

## What survives the exclusions

Each regime has 25 cells: five unchanged speaker folds crossed with five unchanged
word groups. A fitting or selection recording is removed when any of its complete
canonical words belongs to the cell's held-out word group. Outer membership uses
the target word's group. Child-only full inner-validation and outer membership
remain all ages; child-only fit, selection and refit use ages 6–12.

The ranges below describe positions per cell; the minima and maxima in different
columns need not come from the same cell. All 23 sounds remain represented in
every inner-fit and refit cell for both regimes. Child selection still has seven
cells missing at least one sound. Expansion does not remove that limitation.

| Regime | Partition | Original range | Expanded range | Original cells missing a sound | Expanded cells missing a sound |
| --- | --- | ---: | ---: | ---: | ---: |
| all-age | Inner fit | 1,647–3,396 | 2,901–5,845 | 0 | 0 |
| all-age | Selection | 384–870 | 662–1,543 | 0 | 0 |
| all-age | Refit | 2,098–4,143 | 3,749–7,266 | 0 | 0 |
| child-only | Inner fit | 848–1,655 | 1,393–2,768 | 0 | 0 |
| child-only | Selection | 143–475 | 245–799 | 7 | 7 |
| child-only | Refit | 1,096–1,921 | 1,788–3,178 | 0 | 0 |

Event support is stricter than sound presence. A cell below is counted when at
least one sound lacks either positive or negative votes for the specified event;
this includes sounds absent entirely. All 25 child-only selection cells still
lack a class for at least one sound for both events. These are descriptive counts,
not a threshold for declaring sufficient clinical evidence.

| Regime | Partition | Original rating-0 class gaps | Expanded rating-0 class gaps | Original below-2 class gaps | Expanded below-2 class gaps |
| --- | --- | ---: | ---: | ---: | ---: |
| all-age | Inner fit | 9 | 7 | 6 | 5 |
| all-age | Selection | 25 | 23 | 24 | 20 |
| all-age | Refit | 5 | 5 | 5 | 5 |
| child-only | Inner fit | 25 | 24 | 25 | 23 |
| child-only | Selection | 25 | 25 | 25 | 25 |
| child-only | Refit | 25 | 23 | 25 | 22 |

## Child support for every sound

Counts here cover the complete child corpus before each cell's fitting exclusions.
For example, /CH/ gains no occurrences. /G/ gains rating-0 votes, but remains rare.
The full artifact retains per-cell support, positive/negative speaker counts and
explicit missing classes; these pooled totals must not replace those details.

| Sound | Original positions | Added positions | Expanded positions | Original rating-0 votes | Expanded rating-0 votes | Original below-2 votes | Expanded below-2 votes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 55 | 291 | 13 | 13 | 16 | 16 |
| CH | 42 | 0 | 42 | 8 | 8 | 10 | 10 |
| D | 322 | 284 | 606 | 37 | 61 | 64 | 116 |
| DH | 333 | 135 | 468 | 29 | 39 | 126 | 157 |
| F | 191 | 97 | 288 | 5 | 7 | 7 | 12 |
| G | 195 | 22 | 217 | 1 | 6 | 3 | 8 |
| HH | 237 | 121 | 358 | 7 | 10 | 9 | 13 |
| JH | 76 | 10 | 86 | 13 | 14 | 14 | 15 |
| K | 330 | 249 | 579 | 9 | 31 | 16 | 40 |
| L | 357 | 325 | 682 | 60 | 103 | 76 | 137 |
| M | 341 | 222 | 563 | 32 | 54 | 67 | 109 |
| N | 402 | 718 | 1,120 | 52 | 136 | 61 | 181 |
| NG | 119 | 25 | 144 | 10 | 11 | 18 | 22 |
| P | 153 | 34 | 187 | 15 | 20 | 25 | 31 |
| R | 304 | 165 | 469 | 60 | 95 | 82 | 136 |
| S | 378 | 372 | 750 | 35 | 59 | 45 | 86 |
| SH | 134 | 8 | 142 | 18 | 21 | 25 | 30 |
| T | 378 | 946 | 1,324 | 27 | 92 | 46 | 155 |
| TH | 75 | 10 | 85 | 19 | 26 | 94 | 116 |
| V | 200 | 85 | 285 | 17 | 28 | 93 | 159 |
| W | 323 | 227 | 550 | 18 | 25 | 22 | 31 |
| Y | 190 | 41 | 231 | 9 | 10 | 15 | 18 |
| Z | 338 | 86 | 424 | 38 | 49 | 303 | 406 |

## Additional recordings and vocabulary

Every extra recording keeps its existing speaker's original roles in all five
folds. The complete artifact lists those roles and all occurrence indices.
`COVER` is the only additional canonical word type; its fixed hash assigns group
1. Repeated tokens remain in the canonical utterance; grouping uses their same
spelling consistently. Words without a supported target also participate in
whole-utterance exclusions.

| Clip | Existing speaker | Age | Positions | Canonical words | Word groups |
| --- | --- | ---: | ---: | --- | --- |
| 000530027 | 0053 | 6 | 6 | THREE THREE NINE | 3, 3, 2 |
| 001040026 | 0104 | 6 | 10 | FIVE SIX FIVE SIX | 1, 3, 1, 3 |
| 005600146 | 0560 | 23 | 5 | COVER OF A COVER A | 1, 0, 1, 1, 1 |
| 010420047 | 1042 | 7 | 4 | TWO TWO NINE | 2, 2, 2 |
| 096110011 | 9611 | 30 | 18 | HE LEFT THEM THERE FOR A LONG TIME HANGING THERE | 4, 0, 2, 1, 2, 1, 4, 3, 0, 1 |

## Verification and next experiment

The [declared protocol](multiphone-lexical-expansion-protocol.md) and the new
`lexical_expansion` source/tests are frozen. Eight focused tests pass; separate
Astra source review found no blocking issue. Actual inventory calculation and complete offline reconstruction finished with
exit zero. Independent artifact audit also finished with exit zero: 15,121,637
checks across 37,891 input references and 17,825 unique hashed paths, including
750 original membership-list comparisons, 1,420 distinct support views across
three age groups, and all 2,500 saved feature units. The audit reconstructs word
hashes, speaker memberships and support directly without importing the study's
calculation. No failure or blocking finding remains.

The [independent artifact receipt](../../work/lexical-expansion-review-20260927/result.json)
binds its executed audit sources and frozen study artifacts. Eight focused tests
cover invalid legacy joins, full-utterance exclusion, exact scalar/vector joins,
stratum accounting, fresh declaration and changed-plan rejection.

The actual calculation reconstructs the original canonical report and expanded
speaker splits, checks original base/retained/excluded membership in every cell
and partition, and validates the full saved feature export. Every original target
vector and scalar matches exactly; expanded concatenation and saved unit assembly
match exactly. Source and artifact hashes are checked before and after calculation.
Audio bytes are read only for hashing, without decoding; no audio encoder, head
prediction, fitting, transform fitting, author-test decoding or Colab allocation
occurs. App build and UI tests were not run because this is research-only work.

- [Frozen declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-expansion-v1/plan.json):
  `b44bdef2eadb9637f97f66532f659f4b963e0ed1af1b210b6c008baea7ab5fb9`.
- [Complete inventory](../../research/audio-head/outputs/multiphone-20260927/lexical-expansion-v1/report.json):
  `e04e2bb64b21e4328da5b9898627a7dc648e6367473aef918a0aea73da608177`.

The next hypothesis is a separately declared comparison of the existing scalar
and compact phonetic training recipes with expanded fitting data. Use common
original outer examples for the primary comparison, retain added outer examples
as a separate assessment, and preserve both fitting age regimes and every sound.
Selection-data treatment, training budget and comparison rules must be fixed
before fitting. Earlier expanded full-feature studies used a different design;
this inventory does not overturn their mixed results or establish a new model.
The full model-improvement goal remains active.
