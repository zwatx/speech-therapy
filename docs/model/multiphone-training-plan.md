# Shared consonant-rating model: training plan

Started September 26, 2026. This work expands real model training from the
existing /R/ experiment to a shared model of the available consonant-rating
labels. The immediate task is to predict the distribution of five subjective
SpeechOcean ratings at a canonical phone position. The model will consume
whole-clip acoustic features and the requested phone type. It will not supply
verified phone boundaries or a learner pronunciation judgment.

The user authorized at least six hours of useful local model development,
training, and evaluation. The orchestrator's run begins at 08:13:14 UTC and
continues through at least 14:13:14 UTC. The matrix below provides substantive
training work and checkpoints; elapsed time must not be filled by idle waits
or repeated completed diagnostics.

## Data and label evidence

The [data recipe](../../research/audio-head/experiments/multiphone-data-v1.json)
and [builder](../../research/audio-head/multiphone_data.py) use the pinned public
SpeechOcean762 author-training partition only: 2,500 source clips from 125
speakers. Only training score objects are decoded. Selected WAVs are verified
against the pinned official archive; no author-test audio is decoded or used
for inference. Existing source terms and private-research scope remain in
force. The initial frozen-feature matrix reused cached media and weights.
The later phonetic follow-up downloaded a pinned upstream checkpoint, as
recorded in the [run log](model-training-run-log.md); all fitting and inference
remain local. No new media or model artifacts have been published.

A row is included only when its canonical target phone occurs exactly once
in the entire utterance. Other phones may still have rows for that utterance.
The detailed annotation syntax is decoded using the established convention:
parentheses → 0, braces → 1, and unmarked canonical tokens → 2. Bracketed
insertions are ignored for canonical-position indexing. Every reconstructed
five-rating mean must equal its published aggregate. These ratings do not
become produced-phone transcriptions through this decoding.

The resulting manifest has **14,843 rows across 2,495 clips**. Primary fitting
and metrics require at least 100 rows and 50 speakers for a target, a support
rule declared from the metadata before training. This excludes only /ZH/:
**14,837 rows across 23 eligible targets** remain. /ZH/ keeps its stable target
ID and six visible manifest rows, with both training and primary-metric
eligibility false. It must not silently acquire an evidence-backed output.

| Target | Rows | Speakers | Class 0 ratings | Class 1 ratings | Class 2 ratings |
| --- | ---: | ---: | ---: | ---: | ---: |
| B | 660 | 124 | 74 | 5 | 3221 |
| P | 482 | 123 | 92 | 22 | 2296 |
| M | 828 | 124 | 176 | 80 | 3884 |
| T | 810 | 125 | 201 | 40 | 3809 |
| D | 835 | 125 | 267 | 60 | 3848 |
| N | 960 | 125 | 254 | 15 | 4531 |
| K | 827 | 125 | 175 | 14 | 3946 |
| G | 491 | 125 | 58 | 7 | 2390 |
| F | 605 | 124 | 105 | 6 | 2914 |
| V | 590 | 122 | 142 | 199 | 2609 |
| S | 941 | 125 | 216 | 26 | 4463 |
| Z | 841 | 125 | 254 | 585 | 3366 |
| SH | 314 | 113 | 126 | 19 | 1425 |
| CH | 157 | 83 | 53 | 12 | 720 |
| JH | 173 | 89 | 65 | 4 | 796 |
| L | 943 | 125 | 363 | 45 | 4307 |
| R | 766 | 124 | 369 | 37 | 3424 |
| W | 861 | 124 | 177 | 7 | 4121 |
| Y | 477 | 122 | 54 | 8 | 2323 |
| HH | 637 | 125 | 72 | 3 | 3110 |
| TH | 260 | 109 | 157 | 132 | 1011 |
| DH | 955 | 125 | 268 | 195 | 4312 |
| NG | 424 | 121 | 193 | 17 | 1910 |
| ZH — excluded | 6 | 6 | 11 | 1 | 18 |

The source ages are 6–37, with no age 2–5 recordings and no established child
speech-sound-disorder reference cohort. A corpus child band of age ≤15 remains
distinct from Cadence's intended ages 2–12. Class-1 observations are sparse for
many targets, including some zero-observation validation/holdout cells. Keep
those denominators visible; the support rule is not clinical adequacy.

## Fixed speaker splits and lexical limitations

All rows of a waveform and all recordings of a speaker stay together.
The new five-fold speaker map is hash-ranked with seed `20260926` across all
125 speakers. Each outer fit assigns 20% of its speakers to inner validation,
using a fold-specific hash rank. Every eligible row receives exactly one
outer holdout prediction. Cross-partition duplicate WAV hashes fail validation.

| Fold | Outer fit clips | Outer holdout clips | Inner fit clips | Inner validation clips | Outer holdout rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 1996 | 499 | 1597 | 399 | 3026 |
| 1 | 1997 | 498 | 1598 | 399 | 2968 |
| 2 | 1996 | 499 | 1598 | 398 | 2855 |
| 3 | 1996 | 499 | 1596 | 400 | 2991 |
| 4 | 1995 | 500 | 1595 | 400 | 2997 |

This differs from the earlier /R/ map of 124 speakers. Adding one speaker to
a hash-rank/modulo assignment can move existing speakers between folds; old
/R/ out-of-fold metrics cannot be used as paired baselines here. Refit all
comparison methods on the new exact splits.

No exact or normalized prompt text repeats across the selected clips, but
461–519 target-word types overlap each outer fit and holdout. This is a
speaker-disjoint study, **not a word-disjoint result**. Report lexical overlap
and compare against target/word/age/capture controls. A later word-purge study
would need to prevent exposure through every target row of shared waveforms;
purging only one phone's supervised rows does not remove those words from
other training audio. Earlier per-target word purges also left very small
fit sets, especially for common function words, so they are not a substitute
for a well-designed new evaluation cohort.

Only inner validation may select settings, stopping epochs, or adaptation
choices. Any feature normalization, vocabulary, priors, and capture controls
must be fitted on that split's fit rows. Save the selected inner configuration
before evaluating the locked outer matrix. Once an outer result informs a new
architecture or choice, label the subsequent comparison exploratory and do
not present it as a fresh confirmatory score.

## Training matrix and useful checkpoints

The fixed data/split artifacts are ready. Each training stage must save its
own exact model, optimizer, seed, stopping, and compute recipe before fitting;
this plan does not substitute for those executable run configurations.

| Stage | Concrete model work | Required checkpoint/evidence |
| --- | --- | --- |
| 1. Corpus baselines | Fit per-target priors; target-word/age/capture controls; shared phone-conditioned mean-pooling heads on frozen wav2vec2 and WavLM features. | Saved fitted parameters, inner learning/selection results, and all eligible-target denominators. Reproduce the same splits for every method. |
| 2. Contextual pooling | Train a small phone-query attention head on full contextual frame sequences, with the same label objective and a capacity-comparable mean-pooling head. The requested phone embedding conditions the pool; repeated phone IDs are rejected. | At least one completed five-fold comparison and additional initialization seeds, with named head checkpoints and full loss curves. Attention weights remain unverified contextual weights, never target-time labels. |
| 3. Limited encoder adaptation | If inner results show learnable signal and the baseline is stable, compare frozen features with partial unfreezing of the upper encoder layer(s) on local MPS. Keep the lower encoder frozen and save separate optimizer/learning-rate settings. | Real gradient updates, train/inner-validation curves, selected step counts, memory/runtime, and a restartable checkpoint. Retain a frozen comparator. Do not select from outer holdouts. |
| 4. Replication and evaluation | Complete the predeclared fold/seed matrix, verify saved-head replay, and evaluate capture sensitivity on selected research checkpoints. | Paired per-target results, speaker-clustered uncertainty, seed variability, failures, and explicit underpowered cells. No learner decision threshold is fitted. |

Start with the cached encoders already present locally. The selected 172.3
minutes of audio require approximately 1.474 GiB per encoder for float32
768-wide full contextual frames, before indexes and filesystem overhead.
Cache extraction should resume at verified clip boundaries. Keep unpooled
frames available for attention; a whole-clip mean cannot reconstruct them.

Use a proper three-class soft-label objective: for each row with counts
`c0,c1,c2`, minimize `−Σ(cj/5) log(pj)`. Report macro-average per-target log loss
as well as the micro/per-rater result, expected-rating error, and per-rater
multiclass Brier score. The latter scores each observed rater judgment; it is
not merely squared error to the averaged soft label. Preserve each target's
class counts and mixed-rater slice. Speaker resampling must keep all target
rows and clips from a speaker together. Do not treat five raters or multiple
phones from one waveform as independent participants.

Gain/noise evaluations measure sensitivity only because transformed recordings
have no new qualified ratings. They cannot supply an accuracy gain, and
noise-consistency training should not be introduced as if noisy speech had
independently verified unchanged labels.

## Final evaluation and artifact handoff

The historical metadata audit decoded and validated the full published score
files, and prior /R/ research evaluated published-test recordings from their
speakers. Non-/R/ test recordings may be new to acoustic inference, but they
cannot honestly be relabeled an untouched corpus or independent speaker
cohort. **No author-test scoring or inference is part of this six-hour study.**
A genuinely independent final evaluation cohort remains reserved for future
access or collection, after its task, rights, reference labels, and selection
rules are settled. All current fold results remain research evidence within a
previously used corpus.

The [SLP handoff](slp-handoff.md) remains useful for content review and eventual
reference annotations; those activities are not prerequisites for the valid
whole-clip rating task defined here. Learner feedback stays disabled.

Ignored local manifests:

- [`cohort.json`](../../research/audio-head/outputs/multiphone-20260926/cohort.json): SHA-256 `33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805`.
- [`splits.json`](../../research/audio-head/outputs/multiphone-20260926/splits.json): SHA-256 `b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf`.

`load_training_cohort()` returns JSON-serializable clips, rows, target support,
and source provenance. Clip `audioPath` values are absolute paths under the
verified local public-corpus root. `build_splits(cohort)` returns per-fold
`outerFit`, `outerHoldout`, `innerFit`, and `innerValidation` arrays suffixed by
`Rows`, `Clips`, or `Speakers`; row/clip arrays contain manifest indices.
All 24 target IDs retain the order of `TARGETS`, with ID 23 (/ZH/) masked.

The builder refuses to overwrite existing manifests. Six synthetic metadata
and split tests cover rating decoding, repeated-target exclusion, invalid
annotations, support thresholds, speaker/clip cohesion, and cross-split WAV
duplicates. No training or acoustic inference was run while preparing these
manifests.
