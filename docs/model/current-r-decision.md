# Current /R/ model decision

Historical research checkpoint: September 23, 2026. See the
[current multi-sound decision](current-multiphone-decision.md) for the active
23-consonant training campaign. Native practice now supports recording and
replay; no trained head supplies learner pronunciation feedback.

## What is already trained

The local pipeline has frozen wav2vec2 and WavLM representations with owned
heads trained on public speech. The CMU Arctic phone-CTC runs are engineering
checks against automatic adult labels. The more relevant SpeechOcean762 run
fits a three-class distribution of five expert **whole-clip /R/ ratings** on
766 author-training clips from 124 speakers. Its five outer folds hold speakers
out; a separate final research fit uses all 766 training clips. Neither task
uses verified target /ɹ/ times or a complete produced-phone transcription. See the
[training record](local-training.md) and [source/rights inventory](model-development-roadmap.md).
An [offline replay command](local-training.md#offline-replay-of-the-final-r-rater-heads)
now verifies both saved heads on exact pinned public author-training WAVs. Its
in-sample probabilities are an artifact check, not a new evaluation.

| Train-side speaker-held-out predictor | Per-rater log loss ↓ |
| --- | ---: |
| Fold training prior | 0.37168 |
| Canonical word + corpus age, categorical control | 0.34836 |
| Canonical word + corpus age + full-clip duration/RMS, linear control | 0.33195 |
| Frozen WavLM + owned rating head | 0.32175 |
| Frozen wav2vec2 + owned rating head | 0.31804 |

The duration/RMS control improves over a paired word-and-age linear fit by
0.03793 log-loss units on the same rows. In a descriptive 2,000-draw
whole-speaker resampling of **fixed** out-of-fold predictions, its difference
from wav2vec2 is +0.01391 with a 95% percentile interval of
[−0.01060, +0.03782]; its difference from WavLM is +0.01020
[−0.01850, +0.03888]. Positive differences favor the acoustic head, but both
intervals cross zero. This resampling omits refitting, selection, and new-corpus
uncertainty, and all folds were already inspected during development. It is
not an equivalence test or a clinical confidence interval. The source ratings
are heavily top-scored, and [mixed-rater clips remain difficult](local-training.md#rater-disagreement-diagnostics-on-saved-predictions).
In the public corpus's 349 child-band training clips, 301 receive five top
ratings; WavLM's fixed out-of-fold log loss there is slightly worse than the
fold training prior. That slice cannot stand in for children with speech sound
disorders. A separate [capture-control age-slice diagnostic](local-training.md#capture-control-by-corpus-age-band)
compares the same fixed predictions within the corpus child and adult bands.
Its four 2,000-draw within-band speaker intervals for capture-control minus
acoustic log loss all cross zero. The pooled acoustic advantage therefore does
not establish an age-specific winner or a target-sound cue.

A [speaker-and-target-word purge stress test](local-training.md#speaker-and-target-word-purge-stress-test)
keeps the same author-training speaker holdouts while removing overlapping
target words from each fit. Both frozen acoustic heads beat a fit-only class
prior there, but the fits shrink to 264–318 clips and contain only 7–20
class-1 judgments each. Its result does not isolate target-word reliance or
establish an encoder winner.

The authors' [SpeechOcean annotation guide](https://github.com/jimbozhang/speechocean762#the-mispronunciations-block)
also provides a limited `pronounced-phone` note when a phone's averaged score
is below 0.5. In the pinned author-training, exactly-one-`R` cohort, only 49
of 766 clips have such a note at `/R/`; 5 are from child-band clips. The five
child notes are `R*` (3) and `<unk>` (2), with no concrete alternate phone.
Across this cohort note presence is exactly equivalent to the already modeled
`/R/` rating being below 0.5. It therefore supplies neither an independent
binary training label nor a complete produced-phone sequence or target time.

## Decision and next gate

Keep both acoustic heads as private research artifacts and keep model feedback
disabled. Another encoder on the current automatic adult labels would test
runtime/architecture sensitivity, but would not answer whether /ɹ/ was
produced or where it occurred. The next priority is the prepared **40-clip,
40-speaker, author-training-only annotation feasibility pilot**. Two local
blinded public-audio packs and a [draft reviewer protocol](r-reviewer-protocol-draft.md)
are ready, along with provisional
[intake, merge, and agreement commands](../../research/audio-head/ANNOTATION_INTAKE_DRAFT.md).
The draft now also includes a single-reviewer export check and a disabled,
loopback-only reviewer page for future approved use. The merge checks each
reviewer's blinded pack order before combining records. The page requires
study-owner launch and a separate browser-only reviewer account so the
private source-rating manifest remains inaccessible to reviewers.
No qualified reviewer labels have been collected or distributed. The merge
validates both reviewers' 40-record submissions and preserves the original
judgments; it does not
adjudicate or approve them for training.
Private, verified full-clip frame caches for those same 40 clips are now
prepared for both frozen encoders. They remain unlabeled contextual features;
they cannot establish target /ɹ/ location or train a target-localized head.

Before reviewers begin, a qualified speech-language pathologist and study
owner must complete a controlled copy of the
[draft signoff worksheet](r-annotation-signoff-draft.md) and approve the
`expected`/`altered`/`omitted`/`indeterminate` task,
target-word and /ɹ/ timing rules, the meaning of an altered-segment interval,
playback rules, handling of disputed audio, acceptable timing tolerance and
paired-interval coverage, agreement criteria, and permitted later label use.
Keep both
independent records and any adjudication separate. The pilot tests whether
reviewers can produce usable reference labels; its deliberately balanced 40
clips cannot estimate population performance.

If the task proves feasible, lock a separate untouched cohort, then compare
verified target-localized features with whole-clip features under speaker- or
household-grouped selection and prompt/capture baselines. Evaluate child speech
and speech-sound-disorder use on representative, permissioned data before any
calibration, release decision, or learner feedback. If reliable target times
cannot be obtained, stop the localized-head path and seek a suitable licensed
reference corpus. A separate [candidate-corpus assessment](produced-phone-corpus-candidates.md)
identifies L2-ARCTIC's manual phone-error TextGrids as a conditional
noncommercial method benchmark. Access and use review, then an audit of its
actual /R/ counts and error balance, must precede any fit. Its adult L2 speech
cannot substitute for child SSD evidence. The fuller
[roadmap](model-development-roadmap.md) records those later gates; none is
satisfied by the current rating experiment.
