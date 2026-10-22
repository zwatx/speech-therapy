# Cadence multiphone research model card

Checkpoint version: September 26, 2026. Evidence notes updated September 27, 2026.
Status: **four completed research checkpoints; no learner pronunciation judgment**.

This card describes the four original full-data bundles. Later
[complete-utterance word exclusions](multiphone-lexical-head-report.md) found that
their feature architecture performed worse than the scalar reference under that
different development evaluation. The speaker-held-out results below must retain
that lexical limitation. Newer scalar/PCA mixtures and expanded-fitting candidates
are separate cross-fit research checkpoints; their scores do not describe these
four bundles. See the [current decision](current-multiphone-decision.md) for the
latest verified comparisons and the completed seed replication.

The [occurrence-aware raw-audio adapter](multiphone-position-audio-report.md) and
[optional research filter](multiphone-position-filter-report.md) extend the
research interface around the original bundles. Their tested replay and rejection
behavior do not establish clinical correctness or a validated learner-feedback
policy. In particular, the tested filter still admits a dog recording.

## Intended use and output meaning

These heads support local research into predicting a distribution of five
SpeechOcean762 raters' scores at a requested canonical consonant. Output columns
are probabilities for corpus rating classes **0, 1 and 2**. They are not
probabilities that a child produced a particular phone, clinical error labels,
or calibrated pronunciation-correctness probabilities. No decision threshold,
diagnosis, treatment recommendation or learner feedback is supplied.

Permissible descriptions include “trained on public author-training ratings,”
“predicts the source rating distribution,” and the specifically qualified
development comparisons below. “Detects a child's sound errors,” “validated for
SSD,” “accurate for ages 2–12,” or a pronunciation-accuracy percentage are not
supported. Recording quality and pronunciation assessment remain separate.

## Completed checkpoints and selection

All four variants were fixed before final fitting; none was chosen as a winner
from outer outcomes. Each uses target-window phonetic features plus 13 CTC
scalars. The [final declaration](../../research/audio-head/outputs/multiphone-20260926/phonetic-final-plan-v1.json)
binds all 100 verified inner trials and 706 artifact digests. For each variant,
the learning rate minimizes mean same-population macro-phone NLL across five
inner folds; exact ties prefer 0.0003. Final epochs are the integer median of
the five selected best epochs at that rate. This differs from the per-fold LR
selection used in the earlier comparison tables.

| Bundle manifest | Objective | Fit ages | Target rows / speakers | LR | Fixed epochs |
| --- | --- | --- | ---: | ---: | ---: |
| [unweighted-all-age](../../research/audio-head/outputs/multiphone-20260926/phonetic-final/unweighted-all-age/manifest.json) | Ordinary soft-label NLL | 6–37 | 14,837 / 125 | 0.0003 | 4 |
| [unweighted-child-only](../../research/audio-head/outputs/multiphone-20260926/phonetic-final/unweighted-child-only/manifest.json) | Ordinary soft-label NLL | 6–12 | 5,654 / 52 | 0.0003 | 5 |
| [weighted-all-age](../../research/audio-head/outputs/multiphone-20260926/phonetic-final/weighted-all-age/manifest.json) | Fit-class weighted NLL | 6–37 | 14,837 / 125 | 0.0003 | 4 |
| [weighted-child-only](../../research/audio-head/outputs/multiphone-20260926/phonetic-final/weighted-child-only/manifest.json) | Fit-class weighted NLL | 6–12 | 5,654 / 52 | 0.001 | 2 |

Every fit starts a fresh seed-7 head and AdamW optimizer. The head uses a
128-wide acoustic projection, 128-wide phone embedding, 128-wide classifier,
GELU activations, training dropout 0.1, weight decay 0.01 and target-row batches
of 64. The pretrained encoder stays frozen. Column mean/population standard
deviation, per-phone +1/class priors and class weights use only the corresponding
complete fitting population; standard deviations below 1e-6 become one.

Weighted variants use inverse-square-root observed class prevalence, maximum
weight ratio 10 and prevalence-weighted mean one, without renormalizing each
row's target. Inference computes `softmax(logits − log(classWeights))`;
unweighted weights equal one. This reverses the objective's population-optimum
weighting transformation and does **not** establish empirical calibration.

The [completed queue](../../research/audio-head/outputs/multiphone-20260926/phonetic-final-queue-v1.json)
records four successful fits and exact full-audit replays. A separate read-only
audit checked all bundle and source pins, actual inner score/epoch selections,
full-fit row/speaker counts, feature moments, priors, class weights, supported
targets and optimizer step counts (928, 445, 928, 178). All matched. This audit
performed no forward inference. In-sample probabilities in each bundle's
`verification.json` are artifact checks, not performance estimates.

Provenance anchors: final plan SHA-256
`cff6a0514e2c46cd9a0e9a3473570203b789ebada92bae06f42301c1217c9146`;
completed queue SHA-256
`8b9a2c51e0e9b47c7ceccd904a7257b1901b9c7ea70f0ae9d048ee23354aa280`.

## Data and supported targets

All supervision comes from English L2 speech in the pinned **author-training** partition: 2,495
utterances, 125 speakers and 14,837 eligible target positions. Cohort selection
retains single occurrences of each target phone within a clip. Labels preserve
all five raters' counts; no automatic transcription or transformed recording
was assigned a new human judgment.

Canonical target IDs 0–22, in order, are:
`B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG`.
These are the repository's ARPAbet-style symbols. All 23 have observed support
in both final fit populations. **ID 23, `ZH`, is unsupported**: its six source
rows failed the prespecified support rule. Vowels and other IDs are unsupported.

| Ages | Target rows | Speakers | Rater counts 0 / 1 / 2 |
| --- | ---: | ---: | --- |
| 6–12 | 5,654 | 52 | 532 / 705 / 27,033 |
| 13–15 | 767 | 6 | 46 / 73 / 3,716 |
| 16–37 | 8,416 | 67 | 3,333 / 760 / 37,987 |

Approximately 95.6% of child judgments are class 2. Ages 2–5, a verified child
speech-sound-disorder cohort, representative dialect coverage and reliable
produced-phone/timing references are absent. The age distribution does not
establish suitability for any individual child. Author-test data stayed closed
in this campaign; historical /R/ work already used that public test partition,
so it is not a newly untouched final cohort.

The [per-target child support table](../../research/audio-head/outputs/multiphone-20260926/target-evidence-audit-v1/report.md)
separates rater votes, positions, clips and distinct children. The 532 child
class-0 votes occupy 331 positions in 258 clips; per-target support can be as
small as one child and one vote for /G/. Model output coverage does not imply
reliable detection of each target's errors.

## Feature-input contract and operation

The [portable loader](../../research/audio-head/multiphone_research_inference.py)
accepts a copied bundle directory and its caller-pinned **full manifest SHA-256**.
It needs the matching frozen `multiphone_models.py`, NumPy and PyTorch; it does
not open the original training paths. The separate
[full audit/replay helper](../../research/audio-head/multiphone_phonetic_final.py)
requires the original pinned study archive. Bundle files must remain unchanged.

Prediction takes finite, raw `float32[N,1037]` features plus integer `target_ids[N]`:
the first 1,024 columns are the pinned full-precision phonetic encoder's pooled
target representation; the last 13 follow `feature_columns` exactly. The loader
applies saved normalization, uses one target per singleton input frame, and
returns `float64[N,3]` probabilities computed by the float32 CPU model in
evaluation mode, in batches of 64. It rejects malformed/nonfinite inputs and
unsupported or unobserved target IDs. The feature-source binding SHA is
`360c829d179f9c66b66c900fdcf3db2cb0897fdc5724feb642100802d3da4985`.

This loader is a **feature-level interface**. A separate
[raw-WAV research adapter](../../research/audio-head/README.md#explicit-raw-wav-research-inference)
now performs pinned offline extraction from an explicit canonical prompt; it
provides no app integration or pronunciation decision. Its four actual corpus
checks across all bundle variants reproduce cached features and predictions
exactly. Matching array dimensions alone does not prove correct extraction.
Research extraction uses mono 16 kHz
PCM16, the pinned 392-output q8 CTC model, full-vocabulary normalization,
explicit canonical-phone mapping and forced CTC occupancy plus two contextual
frames on each side. It pools the separate full-precision phonetic encoder on
the verified same frame grid. Its research waveform bounds are 0.1–30 seconds;
these do not change application capture policy. No app integration, mobile
export, real-time latency guarantee or hardware robustness claim follows.
About 91.1% of original target occupancies span one frame: they are estimated
pointers, not measured phone durations. Contextual vectors also contain
surrounding-utterance information.

The adapter has no verified speech-presence or semantic-abstention mechanism.
In a [fixed nonspeech diagnostic](multiphone-nonspeech-report.md), all three
two-second inputs (silence, noise and a tone) produced outputs. All four heads
gave silence class-2 probability between .67470 and .91900, despite zero greedy
CTC tokens. Forced alignment and rating confidence cannot establish speech or
correctness. These three observations do not define a validated rejection rule.

## Evidence and limitations

The [fixed development comparison](../../research/audio-head/outputs/multiphone-20260926/outer-comparison-v1/report.md)
evaluates separate fold refits, **not these four full-fit checkpoints**. Each
prediction excludes its speaker from fitting, but earlier architecture choices
used overlapping inner folds. It is speaker-disjoint development cross-fitting,
not pristine nested validation or independent child/SSD generalization. No outer
winner was selected.

| Child slice, 5,654 target rows | Macro NLL ↓ | Per-rater Brier ↓ | Rating-0 within-phone AUROC ↑ |
| --- | ---: | ---: | ---: |
| Full13 scalar reference | 0.18881 | 0.08221 | 0.79710 |
| Unweighted phonetic target+scalars, all-age fit | 0.17567 | 0.07953 | 0.79997 |
| Unweighted phonetic target+scalars, child-only fit | 0.18073 | 0.07746 | 0.75194 |
| Matched child-fit prior | 0.19894 | 0.08083 | 0.29029 |

A [standalone comparison figure](../../research/audio-head/outputs/multiphone-20260926/child-rating-figure-v1/child-rating-comparison.png)
shows these saved values, conditional proper-score intervals and the
unfamiliar-word reversal together. It adds no new model selection or metrics.

For the all-age combined family versus scalars, child macro-NLL difference is
−0.01313 with conditional paired-speaker 95% interval [−0.01919, −0.00700].
These 2,000 resamples hold models/selection fixed. Ranking intervals are
withheld: only 1,082 rating-0 and 1,831 below-2 draws retain both classes for
every fixed phone, below the required 1,900. Child `/G/` has one rating-0
judgment. Pooled fold-specific priors can rank above or below 0.5 without any
acoustic information. Preserve proper-score/ranking tradeoffs.

Word familiarity exposes another limit: for the same 614 child targets whose
word is absent from all-age fitting target-row vocabularies, combined-family
macro NLL is **0.31635 versus 0.30029** for scalars. For 5,040 seen-word targets,
it is **0.16060 versus 0.17647**. The unseen slice covers 22 phones and has no
paired interval; words can still occur elsewhere in fitting utterances. It is
not a word-disjoint experiment. Child-only fits have a different unseen set.

The separate [20-fit weighted study](../../research/audio-head/outputs/multiphone-20260926/phonetic-balanced-comparison-v1/report.md)
is inner-only and was excluded from that fixed outer release. Across five
overlapping inner folds, all-age fitting's child NLL changes 0.18964→0.18653;
child-only fitting changes 0.18364→0.18332. Child-only rating-0 AUROC improves
slightly while average precision and below-2 ranking worsen. These per-fold
selected means are not independent evaluation of the final aggregate-selected
LRs, and do not establish a universally preferable weighting objective.

The [capture diagnostic](../../research/audio-head/outputs/multiphone-20260926/capture-sensitivity-v2/diagnostic/report.json)
uses fixed original inner-selected heads on 23 targets from five children,
with all original-cache parity checks passing. For the all-age head, mean
probability total variation from clean audio is 0.00364 at quarter gain,
0.03106 under 20 dB white noise and 0.09217 under 10 dB noise; the largest
10 dB shift is 0.70831. Child-head mean noise shifts are 0.01376 and 0.05955.
These small-sample synthetic sensitivities are not microphone/room robustness,
pronunciation changes or accuracy: transformed audio has no human labels.

The [word-context diagnostic](multiphone-word-context-sensitivity-report.md)
uses the same five children and fixed original heads, with 17 exact waveform
crops covering 23 positions and 16 consonants. All original parity checks and
crop audits pass. Recomputing the pipeline with each estimated word alone
changes probabilities by mean TV .10850 (all-age) and .05560 (child-only), with
maximum shifts .47635 and .51413. Crops lack human timing and correctness
judgments. This exposes context sensitivity without establishing natural
isolated-word performance or a causal encoder-only effect.

A separate [corpus rating reliability check](../../research/audio-head/outputs/multiphone-20260926/rating-reliability-v1/report.md)
uses the earlier saved development predictions for all 5,654 child positions.
The observed rating-0 vote frequency is .01882; the all-age combined model
averages .02822 and the child-only model .01330. Both directions of frequency
error remain possible despite useful proper scores. Fixed deciles place 93.4%
and 97.7% of those respective predictions below .1; coarse bins and sparse tails
limit interpretation. Every phone/fold table is retained and independently
recomputed. No calibration correction or pronunciation probability follows.

A separate [six-arm raw encoder continuation study](../../research/audio-head/outputs/multiphone-20260926/phonetic-adaptation-comparison-v1.json)
completed 13 epochs and 3,940 optimizer updates with exact MPS replay of all
selected checkpoints. All four upper-layer adaptation arms retained their
starting checkpoint. All-age head-only continuation improved all-age NLL
slightly but worsened child NLL, Brier and rating-0 ranking. This experiment
does not demonstrate an encoder-adaptation benefit and does not change the
four full-data bundles above.

The subsequent [six-arm consistency experiment](../../research/audio-head/outputs/multiphone-20260926/consistency-comparison-v1/report.md)
is a separate fold-zero continuation study, not a modification of the four
full-data bundles in this card. It uses clean human ratings and a fixed model
teacher on one 20 dB noisy view. All six arms replay exactly. Child-only
coefficient one improves clean NLL and average probability stability but
worsens rating-0 AUROC, raises average class-2 confidence and still assigns
class 2 the highest probability on every child validation target. The five
child validation speakers cannot establish a general robustness gain. The fixed
[four-fold replication](multiphone-consistency-replication-protocol.md) is now
complete, with all 30 arms exactly replayed and independently audited. Child-only
coefficient one's mean clean-NLL gain is driven by fold zero; the remaining
folds are worse or unchanged. Its mean rating-0 AUROC falls .75320→.75042 despite
lower mean noise TV. All-age coefficient one improves child Brier and mean TV
in all five folds but lowers rating-0 AUROC in three. Individual shifts remain
large. The [complete comparison](../../research/audio-head/outputs/multiphone-20260926/consistency-replication-comparison-v1/report.md)
keeps all coefficients and 27 distinct children/39 overlapping memberships.
No coefficient was selected and no noisy correctness label was introduced.

The later [five-fit ranking comparison](../../research/audio-head/outputs/multiphone-20260926/ranking-comparison-v1/report.md)
also completes with exact replay and independent numerical audit. Under its
fixed NLL stopping rule, child macro NLL improves slightly versus matched
continuation (.183822→.183634), while rating-0 AUROC worsens (.753201→.750896).
Rating-0 average precision and below-2 metrics have mixed changes. Only two
folds select updated checkpoints; all child argmax predictions remain class 2.
The study retains its 27 distinct children/39 overlapping memberships and all
per-phone support. It does not select a new full-data export or demonstrate
reliable lower-rating detection.

The [follow-up tradeoff figure](../../research/audio-head/outputs/multiphone-20260926/followup-tradeoffs-figure-v1/followup-tradeoffs.png)
puts those fixed per-fold NLL and rating-0 ranking changes together. Its 30
values reproduce saved arm records exactly; it adds no model selection.

The [native prompt coverage handoff](practice-model-coverage.md) finds exact
word/phone matches for 17 of the 72 app prompts in the retained child cohort
(33 positions), compared with 29 prompts at any age (67 positions). This is
an inventory overlap, not isolated-word validation or verified target position.
The app content remains pending SLP review, and ZH remains unsupported.

Before pronunciation use, obtain permissioned, independently reserved child/SSD
data with qualified produced-phone/error judgments, dialect policy and reviewed
timing; evaluate unseen speakers, prompts and sources, rare-error support,
calibration, abstention and relevant devices. The [SLP handoff](slp-handoff.md)
and [child-data options](child-pronunciation-data-options.md) describe concrete
next work. No qualified new labels have yet been incorporated.

## Attribution and usage posture

Source attribution follows the repository's existing
[source/rights inventory](model-development-roadmap.md), not a new rights review:
[SpeechOcean762 / OpenSLR 101](https://www.openslr.org/101/) and its
[authors' annotation schema](https://github.com/jimbozhang/speechocean762)
provide the public ratings, recorded here under CC BY 4.0. The frozen encoder is
[Meta's wav2vec2-lv-60-espeak-cv-ft](https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft)
at revision `ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`; alignment uses the
[ONNX Community conversion](https://huggingface.co/onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX)
at `c69750f5043e5e1f8a71ab95dd3b98338c280c92`. Their recorded model-card metadata
lists Apache-2.0. Exact bytes and preprocessing are pinned in the
[feature recipe](../../research/audio-head/experiments/multiphone-phonetic-features-v1.json)
and [adapter manifest](../../packages/audio-model-adapter/src/manifest.ts).
The adapter remains benchmark-only with legal/data-lineage review pending.
Retain upstream attribution and notices; this card grants no additional
distribution rights or clinical release authorization.
