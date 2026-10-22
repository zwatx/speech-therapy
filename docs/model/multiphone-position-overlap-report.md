# Target-local speech-detector overlap diagnostic

Across 28,227 canonical consonant positions, 623 have no occupied-frame center
inside the fixed 100 ms detector's padded speech segments. Of these, 524 have
all five corpus ratings equal to 2. Among children ages 6–12, the corresponding
counts are 313 and 277. This does not support automatically withholding those
positions: detector overlap and estimated alignment are not verified phone
presence or correctness labels. No withholding rule or model score changed.

The [declared protocol](multiphone-position-overlap-protocol.md) covers all
2,500 author-training recordings, 125 speakers and all 23 supported consonants.
It reuses 2,496 bound VAD records and runs four missing fixed Silero passes.
Both duration settings use the same probabilities and unchanged 30 ms padding.
No speech encoder, CTC recognizer or pronunciation head was run or trained.

## Measured overlap

Frame centers are mapped exactly as `320*i + 199.5` samples at 16 kHz. The
occupied convolutional frontend footprint and the footprint of its pooling
window (two extra frames on each side, clipped to the frame grid) are also
compared with the union of padded VAD intervals. These footprints do not
represent the contextual Transformer's complete support or verified phone
boundaries. The disjoint-footprint counts are nested subsets of the zero-center
count; do not add these columns together.

| Duration / population | Positions | No frame center inside | Occupied footprint disjoint | Pooling footprint disjoint |
| --- | ---: | ---: | ---: | ---: |
| 100 ms, all ages | 28,227 | 623 | 464 | 169 |
| 100 ms, ages 6–12 | 9,891 | 313 | 232 | 107 |
| 250 ms, all ages | 28,227 | 643 | 485 | 192 |
| 250 ms, ages 6–12 | 9,891 | 322 | 242 | 119 |

Under 100 ms, the 623 zero-center positions span 535 recordings and 112
speakers. They contain 205 rating-0, 36 rating-1 and 2,874 rating-2 votes;
78 positions have at least one rating-0 vote and 99 have any vote below 2.
The 313 child positions span 267 recordings and 49 children, with votes
28/28/1,509; 19 have any rating-0 vote and 36 have any vote below 2.
Even the wider pooling footprint is fully disjoint for 169 positions, including
138 all-top positions; for children those counts are 107 and 91.

Original positions account for 350 zero-center cases out of 14,837; added
positions account for 273 out of 13,390. Their child counts are 186/5,654 and
127/4,237. Positions and votes add across those populations, while distinct
speaker/recording counts require set unions. The saved report retains all
original and added support under both policies and all three age views.

## Every consonant, fixed 100 ms setting

These are descriptive support counts, not error rates. “All-top” means all
five votes are 2; “any 0” and “any below 2” do not require a majority.
The table shows zero-center positions, including empty cells.

| Phone | All positions | Zero-center | Of these all-top | Of these any 0 | Of these any below 2 | Child positions | Child zero-center | Child zero-center all-top |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 901 | 16 | 12 | 3 | 4 | 291 | 12 | 9 |
| CH | 165 | 4 | 1 | 3 | 3 | 42 | 0 | 0 |
| D | 1806 | 20 | 13 | 5 | 7 | 606 | 13 | 10 |
| DH | 1532 | 40 | 16 | 15 | 24 | 468 | 14 | 6 |
| F | 859 | 40 | 37 | 3 | 3 | 288 | 25 | 23 |
| G | 575 | 4 | 4 | 0 | 0 | 217 | 4 | 4 |
| HH | 1093 | 156 | 145 | 10 | 11 | 358 | 51 | 47 |
| JH | 189 | 10 | 9 | 1 | 1 | 86 | 9 | 9 |
| K | 1380 | 56 | 53 | 2 | 3 | 579 | 31 | 30 |
| L | 1784 | 14 | 11 | 3 | 3 | 682 | 12 | 9 |
| M | 1515 | 1 | 0 | 1 | 1 | 563 | 0 | 0 |
| N | 3002 | 21 | 19 | 1 | 2 | 1120 | 15 | 13 |
| NG | 534 | 0 | 0 | 0 | 0 | 144 | 0 | 0 |
| P | 699 | 43 | 38 | 5 | 5 | 187 | 13 | 13 |
| R | 1245 | 1 | 1 | 0 | 0 | 469 | 1 | 1 |
| S | 2073 | 38 | 35 | 3 | 3 | 750 | 25 | 25 |
| SH | 353 | 29 | 22 | 7 | 7 | 142 | 10 | 9 |
| T | 4019 | 97 | 89 | 8 | 8 | 1324 | 57 | 56 |
| TH | 301 | 6 | 1 | 2 | 5 | 85 | 4 | 0 |
| V | 807 | 4 | 1 | 0 | 3 | 285 | 3 | 1 |
| W | 1586 | 18 | 13 | 5 | 5 | 550 | 10 | 9 |
| Y | 577 | 3 | 3 | 0 | 0 | 231 | 2 | 2 |
| Z | 1232 | 2 | 1 | 1 | 1 | 424 | 2 | 1 |

HH contributes 156 zero-center positions, of which 145 are all-top; T contributes
97, of which 89 are all-top. This concentration motivates inspecting detector
and alignment behavior, but it does not identify which component is wrong.
Moving from the 250 ms reference to 100 ms reduces the aggregate zero-center
count from 643 to 623 and the child count from 322 to 313. Neither setting was
selected using these outcomes. High aggregate overlap cannot establish speech
at each target, and absent overlap cannot establish silence or mispronunciation.

## Verification and decision

Seven focused tests passed. The actual calculation and offline reconstruction
both completed with exit zero. Independent review checked all 7,667 input pins
covering 7,616 unique bindings, plus four new VAD records, the exact
2,495 + 1 + 4 record lineage, and four direct state-reset VAD replays matching
all 426 probabilities. All 5,000 segmentations were replayed with the pinned
vendor helper. An independent sample-mask calculation reproduced all 56,454
position-policy measurements; independent aggregation reproduced 432 summary
cells containing 2,160 support views, including votes and distinct clip/speaker
sets. Narrative review passed. The
[independent audit](../../work/position-overlap-audit-20260927/verification.json)
has SHA-256 `46dab803b987c4c0aa131bc19971ff63a3099fd3cafacf9743f6da6eef9a71cf`.

Retain the existing exploratory whole-recording filter and keep learner
judgments disabled. Do not discard training positions or introduce a target-local
abstention threshold from this diagnostic. The completed
[context follow-up](multiphone-position-context-report.md) separates detected-
segment edges, internal gaps and existing alignment warnings. It preserves all
ratings and all 23 phones and remains descriptive; phone timing is unverified.

No new corpus, author-test audio, threshold fitting, model training or Colab
allocation was used. This author-training cohort is development evidence, not
independent clinical validation. App builds and UI tests were not run because
app behavior did not change.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/position-overlap-v1/plan.json): `675815f90b4cc4e99a30582ce88fdf19dbb658601acc545eed0ef3a2ba831407`.
- [Complete results](../../research/audio-head/outputs/multiphone-20260927/position-overlap-v1/report.json): `f4130122ec6267ffa71e313109a47fa1ee1a8090da01d5f2d9f54697b91d71b8`.

Reconstruct all saved measurements without acoustic inference, from
`research/audio-head`:

```sh
.venv/bin/python -m position_overlap.study verify \
  --plan outputs/multiphone-20260927/position-overlap-v1/plan.json \
  --plan-sha256 675815f90b4cc4e99a30582ce88fdf19dbb658601acc545eed0ef3a2ba831407
```
