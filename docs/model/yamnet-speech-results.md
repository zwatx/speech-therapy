# YAMNet speech-evidence results

Completed September 27, 2026. **The fixed YAMNet rule fails adoption as a
universal additional filter:** it retains every full child utterance and removes
the current filter's known dog admission, but loses two short-word crops.
No filter or learner behavior was changed.

The [declared comparison](yamnet-speech-protocol.md) used the unmodified official
YAMNet model, Speech class 0, maximum window score >=0.5. Scores are uncalibrated
event scores. No threshold, class combination or veto was tuned after outcomes.

## Full child utterances and short words

| Input panel | Existing filter B | YAMNet Y | B AND Y |
| --- | ---: | ---: | ---: |
| Child utterances | 1,037 / 1,037 | 1,037 / 1,037 | 1,037 / 1,037 |
| Previously studied word crops | 17 / 17 | 15 / 17 | 15 / 17 |

All 5,654 original consonant positions from 52 children ages 6–12 remain in the
retained full-utterance set, across all 23 phones. This includes every one of the
331 positions with a rating-0 vote and 805 with a below-2 vote; total votes remain
532/705/27,033 for ratings 0/1/2. The study preserves phone and age support tables.
Retention is not a pronunciation-accuracy result or proof of speech at every
target position. Ages 8 and 10 each have only two children in the cohort.

Two estimated crops that the existing filter accepted are rejected:

| Crop | Age | Word | Duration | Maximum Speech score |
| --- | ---: | --- | ---: | ---: |
| `001040136-word-3` | 6 | BE | 0.285 s | 0.076242 |
| `030830135-word-0` | 10 | AND | 0.445 s | 0.345026 |

Both are shorter than the model's 0.975-second input requirement for its first
complete analysis window. Padding does not supply missing speech context. These
are estimated segments of known utterances, not newly collected isolated words;
whole-utterance pronunciation labels were not transferred to them. Their loss
is nevertheless a concrete regression for the current short-word capability.

## Environmental and synthetic challenges

| Panel | Existing B admissions | Y admissions | B AND Y admissions |
| --- | ---: | ---: | ---: |
| 12 initial known ESC-10 clips | 0 / 12 | 0 / 12 | 0 / 12 |
| 24 known extension clips | 1 / 24 | 1 / 24 | 0 / 24 |
| 24 new source-disjoint clips | Unmeasured | 0 / 24 | Unmeasured |
| Three known synthetic cases | 0 / 3 | 0 / 3 | 0 / 3 |

The two known dog admissions are different recordings. B admits
`4-182395-A-0.wav`, whose Y score is 0.099656; Y admits
`4-183992-A-0.wav`, whose score is 0.570285 and which B rejects. Their conjunction
admits neither. This is useful complementarity on known development cases,
not evidence that either detector perfectly distinguishes speech from dogs.

The new panel has four clips each from dog, rain, sea waves, crackling fire,
helicopter and chainsaw categories. Original source IDs exclude all prior 36
clips, and original/conversion hashes and individual attributions were retained.
ESC category labels do **not** establish that recordings contain no incidental
speech. Accordingly these are admissions by category, not independently
annotated false-acceptance rates. Pretraining overlap is unknown. The prior
filter was not inferred on the new panel, and its unmeasured values remain null.

## Execution, verification and decision

All 1,117 declared recordings completed in 28.21 seconds of CPU processing,
including per-record output saves and the final repeat; model import/construction
is excluded from that time. No training, Colab allocation or author-test access
occurred. Every 521-class score array was saved with its waveform binding and
window geometry. Repeating the first recording after all intervening inputs
produced identical scores. A separate pass reconstructed decisions and tables.

Twenty focused tests passed. Independent pre-run review checked all 1,117
waveforms, 1,093 historical filter joins, the 17 exact crop slices, fresh-source
selection and licensing, and the actual wrapper's synthetic boundary/repeat
behavior. Independent post-run verification is recorded separately.

The fixed retention screen fails because it includes short words as well as
utterances. The universal conjunction is not adopted. A future duration-aware
candidate would be a new development proposal motivated by these observations;
it must preserve this failed result and receive its own declared evaluation.
Further independent child speech and speech-presence annotations remain needed
for broader claims. Learner, clinical and promotion eligibility remain false.

Evidence: [plan](../../research/audio-head/outputs/multiphone-20260927/yamnet-speech-v1/plan.json),
[inference freeze](../../research/audio-head/outputs/multiphone-20260927/yamnet-speech-v1/inference-freeze.json),
[complete results](../../research/audio-head/outputs/multiphone-20260927/yamnet-speech-v1/results.json),
and [source review](../../work/yamnet-review-20260927/source-review.json).
