# Cadence model development roadmap

**Milestone steering, October 14, 2026:** target a reviewable prototype by Sunday,
October 18: real in-app recording → validated pronunciation judgment → practice
→ recheck across multiple common sounds. Model integration takes priority over
UI polish. Experimental observations do not meet the owner's acceptance bar;
no additional validation evidence is available. The [current milestone decision
and checkpoints](../consumer-assessment/sunday-prototype-20261018.md) record why
the full validated target is not realistic on current evidence, what already
works, and the independent validation and integration dependencies. Learner
pronunciation judgments remain disabled.

**Engineering update, October 15:** the explicitly authorized same-Mac path now
connects actual simulator recording, native whole-word admission, complete model
processing, selected practice and fresh recheck. Controlled virtual-input T/N
journeys passed with six actual takes and six real model calls; these replay
existing permitted training recordings and provide no new accuracy evidence.
The [current integration report](../consumer-assessment/native-guided-model-integration-20261014.md)
preserves failed word admissions and silent-input attempts. The guided adapter
now retains nine exact cleanup-safe rejection causes with specific recording or
service guidance; 32 generated focused simulator checks passed. No pronunciation
threshold, model or cleanup rule changed. Independent sound-level references,
fixed evaluation and measurement-reliability evidence still block validated
pronunciation/improvement claims. A subsequent fixed four-call fresh-worker bridge
measurement processed the existing T/N inputs in 6.396–8.300 seconds under the
unchanged 90-second limit, with approximately 1.57 GiB maximum sampled descendant
RSS and confirmed cleanup. Disk cache was uncontrolled; machine-cold latency,
broader runtime coverage, physical microphone behavior and Release media runtime
remain open. A bounded no-audio local-service preflight now prevents an absent
service from pausing later guided checks before audio submission. Its 48 focused
simulator tests passed; existing cleanup pauses and post-submission failure
handling remain conservative. See the integration report's
[readiness and recovery evidence](../consumer-assessment/native-guided-model-integration-20261014.md#service-readiness-and-recovery-october-15).
A separate [Release word-runtime check](../consumer-assessment/native-release-word-verification-20261015.md)
matched one existing licensed public word with confirmed worker/timer return and
file deletion. Nine Debug and ten Release checks passed after a test-only
compilation fix. This testable simulator build leaves physical capture, full
Release media runtime and independent pronunciation validation open.

**Direction update 2026-10-02:** the [consumer app plan](../../.plans/2026-10-02_consumer_speech_app_direction.html)
is the current product direction: children6–12 first, optional accounts, immediate
assessment and results-guided practice; no required clinician enrollment. Speech
scores, condition assessment, movement cues and exercises need their own labels
and validation. RGB/audio learning and actual TrueDepth feasibility are now
parallel priorities; see [the new visible-speech tool](../../research/visual-speech/README.md).
The roadmap below preserves earlier research detail; it does not reinstate the
superseded clinician-first product entry. The /r/ specialist result is complete,
and its80childTESTgroup remains sealed.

**Progress update 2026-10-13:** the native guided flow retains each entry's first
word-check observation through practice and recheck; its [current simulator evidence](../consumer-assessment/native-guided-continuity-20261013.md)
contains 24 passing unit tests and 14 passing UI tests. Apple English assets are
installed, but the recognition test stopped at denied speech authorization; the
bundled recognizer remains the working word-check route. The separate
[exposed adult pilot development measurement](../data/l2-exposed-pilot-development-result-20261013.md)
resolved 31 of 48 complete references and measured 191 edits over 853 tokens.
It preserves the original inconclusive strict result and does not establish
child-sound feedback. The [native interface investigation](native-input-interface-diagnostic-20261013.md)
identified an incorrect shape-constraint check. Its narrow repair passed source
review and native compilation. Two finite, identical synthetic predictions now
have a closed separate saved-evidence observation; the original verification
timeout remains a failure. Numerical parity, real-speech accuracy and learner
integration remain pending. These engineering checks do not establish sound
correctness.

As of September 23, 2026. The first local engineering implementation now exists:
a frozen wav2vec2 encoder and small CTC head have run on generated tone fixtures
and public CMU Arctic read-speech clips with explicitly automatic labels. The
initial 56-clip corpus was expanded to 216 clips, including 192 training clips
from four speakers and the same 24 already-inspected held-out recordings.
Matched-head wav2vec2 and WavLM runs at 200/800 steps, plus fixed gain/noise
checks, now exist as additional private engineering evidence.
The clean paired comparison also repeats with head seeds 7, 17, and 29 while
keeping the global seed and all other recipe settings fixed.
An additional pinned HuBERT Base encoder has now completed the same six
head-seed/budget combinations on that already-inspected adult-speech set; the
three-encoder report retains every run and selects no winner.
A separate train-only [automatic /r/ crop preflight](local-training.md#train-only-automatic-r-crop-preflight)
exercised exact timed cropping and frozen wav2vec2 extraction on CMU Arctic:
276 of 279 automatically aligned `r` intervals yielded valid encoder frames;
three were too short. It is an engineering check, not produced-phone evidence.
See [local training](local-training.md) for commands and observed results.
This roadmap's representative speech experiments remain proposed; no clinical
model or learner-feedback release exists. Source cards below were checked on
this date. No patient recordings, paid compute, or new data collection were used.

## Decision

Build an owned phone-scoring head on a frozen open-weight speech encoder first.
Keep the existing wav2vec2 phoneme adapter as the executable reference. The
current engineering comparison includes wav2vec2 Base, WavLM Base+, and HuBERT
Base with the same small head recipe and adult-speech manifest. A compact
Conformer remains a possible later architecture candidate. Select for product
use only from target-error detection, uncertainty, and runtime evidence on a
representative, appropriately labeled cohort. General transcription accuracy
cannot make that decision.

Our first custom model is the phone head, lexicon, and calibration layer. Only
try partial encoder fine-tuning after the frozen-head experiments identify a
representation limitation. Training a foundation encoder from scratch is out
of scope for the first product. A general language model is unnecessary for
the scoring path; feedback should continue to come from reviewed content.

This turns the existing [Lab plan](../../.plans/2026-07-10_ai_speech_therapy_app_plan.html)
into an implementation sequence. The existing [bake-off](audio-model-bakeoff.md)
and [artifact registry](artifact-registry.md) remain the evaluation and artifact
boundaries; do not create a second registry or approval framework.

## What exists and what is missing

| Capability | Current implementation | Next work |
| --- | --- | --- |
| Real acoustic inference | `packages/audio-model-adapter` verifies SHA-256 and byte size for the pinned q8 ONNX model, configuration, preprocessor, and vocabulary before loading one private snapshot. A populated cache passed actual inference with network access denied. | Extend local fresh/reused-runtime measurements to representative clips, concurrency, and deployment hardware. |
| Constrained scoring | `packages/audio-scoring/src/ctc.ts` scores the permitted phone paths and preserves uncertainty outside them. Its CTC arithmetic matches PyTorch on 38 synthetic and preserved public-export checks across three held-out recordings and four heads (maximum finite difference 1.42 × 10⁻¹⁴). | Supply reviewed target protocols and empirical calibration. |
| Web integration | `BenchmarkAttemptScorer` is wired into consent-bound uploads behind an off-by-default research flag. | Keep the learner receipt neutral; do not turn prototype output into feedback. |
| Evaluation | Manifest validation, metrics, candidate manifests, ranking, and adaptation-lineage checks are executable. | Run actual candidates on permitted labeled data; current fixture results are synthetic. |
| Owned model training | `research/audio-head` implements pinned frozen wav2vec2, WavLM, and HuBERT encoders, independently seeded linear heads, manifest checks, checkpoints, and posterior export. All three now have matched 200/800-step, three-head-seed runs on automatic adult labels with exact initial-head matching. Earlier paired gain/noise checks remain separate; WavLM and HuBERT identities retain source-card license evidence. | Add expert-produced-phone labels, representative speaker coverage, grouped-fold selection, calibration, and governed research integration. Existing heads remain engineering artifacts only. |
| Deployment | CPU research adapter, with roughly 318 MB pinned model artifact. | Measure serving needs; mobile distillation and Core ML export are later experiments. |

The owned Python heads now also have actual local runtime measurements on the
same 24 public holdout clips, three passes each, in separate fresh processes.
On an M3 Max using two CPU threads, wav2vec2/WavLM repeated inference medians
were 65.51/67.70 ms and p95 values were 81.37/83.77 ms. Whole-process peaks were
1,313.69/1,321.72 MiB, including validation and model loading. These measurements
cover the research Python path, not the web adapter, mobile hardware, concurrent
serving, or clinical latency guarantees; see [runtime scope and reproduction](local-training.md#local-runtime-measurements-on-public-speech).
The same script later measured the HuBERT 200-step head in a supplementary fresh
process: 72 warm calls had a 62.99 ms median and 78.22 ms nearest-rank p95,
with 1,309.95 MiB whole-process peak. This does not extend the earlier locked
two-encoder runtime recipe or justify deployment selection.

The [cross-language CTC check](local-training.md#python-and-application-ctc-score-parity)
uses twelve preserved posterior exports from three distinct held-out public
recordings. It verifies scorer arithmetic and invalid-input behavior, not
waveform accuracy, clinical feedback, or model selection.

The benchmark target `foundation-ball-initial-b-v1` is a synthetic fixture,
not a clinical protocol. All four acoustic checkpoint assets are now verified
before runtime loading; see the [checkpoint inventory](checkpoint-inventory.md)
for corruption checks and measured offline fresh/reused-runtime smoke evidence.

## Candidate shortlist

These are experiment choices, not winners. License labels below describe the
linked upstream release; they do not settle dataset, conversion, derivative,
redistribution, or intended-use rights for the final artifact.

| Candidate | Released interface and license evidence | Experiment and limitation |
| --- | --- | --- |
| Existing `facebook/wav2vec2-lv-60-espeak-cv-ft`, pinned ONNX conversion | 16 kHz phonetic CTC labels; upstream card lists Apache-2.0. The converter also lists Apache-2.0. [Meta card](https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft), [conversion card](https://huggingface.co/onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX). | Run the current adapter unchanged as the baseline. Multilingual phoneme recognition does not establish child/SSD error detection. Preserve its full vocabulary and residual probability mass. |
| `facebook/wav2vec2-base` | 16 kHz pretrained representation without a downstream tokenizer; card lists Apache-2.0. [Meta card](https://huggingface.co/facebook/wav2vec2-base). | First frozen encoder plus owned phone head. It needs real produced-phone labels; the released encoder alone cannot score a target. |
| `microsoft/wavlm-base-plus` | 16 kHz feature encoder requiring a downstream head. The [exact pinned card](https://huggingface.co/microsoft/wavlm-base-plus/blob/4c66d4806a428f2e922ccfa1a962776e232d487b/README.md) links [Microsoft UniSpeech CC BY-SA 3.0 terms](https://github.com/microsoft/UniSpeech/blob/6112826ac13a4327f4c9a7afa2a505e35b763514/LICENSE); the separate UniLM code MIT license is not treated as the weight license. | Private engineering comparison under the card-linked terms with attribution retained; no redistribution or production authorization. Preserve its official unnormalized waveform preprocessing. Noise behavior is an experiment, not an established cohort advantage. |
| `facebook/hubert-base-ls960` | Frozen 16 kHz speech representation with a downstream linear phone head. The [exact pinned Meta card](https://huggingface.co/facebook/hubert-base-ls960/blob/dba3bb02fda4248b6e082697eee756de8fe8aa8a/README.md) carries an Apache-2.0 tag; no separate license file was present in the snapshot. | Third matched engineering encoder on the same automatic-label adult corpus. Preserve official clip normalization and keep private engineering scope until rights and representative-label questions are resolved. |
| `nvidia/stt_en_conformer_ctc_small` | About 13M parameters; released English text decoder, not phone labels; card lists CC BY 4.0. [NVIDIA card](https://huggingface.co/nvidia/stt_en_conformer_ctc_small). | Compact challenger after replacing the text head with the same phone-head recipe. Check export support and attribution. Never reinterpret grapheme logits as phone probabilities. |
| Whisper, one pinned small English checkpoint | Autoregressive transcription; MIT code and weights. [Official repository](https://github.com/openai/whisper). | Transcript reference only. A recognized intended word is not evidence that its phones were produced correctly. Excluded from clinical-path selection. |
| GOPT | Phone/word/utterance scores from GOP features; BSD-3-Clause code, separate acoustic assets. [Authors' repository](https://github.com/YuanGongND/gopt). | Offline reference. Its non-native English assessment task is different; its own-data instructions also carry a reported-bug warning. Reproduce and inspect before relying on it. |

Use exact checkpoint IDs, revisions, hashes, and per-asset terms in candidate
manifests. Family-level names and toolkit licenses in the older registry are
discovery hints. The frozen-encoder comparison needs at least three primary
candidates and two references to satisfy the current bake-off charter; a quick
one-model experiment is exploratory and must not claim an official selection.

## First owned model

```text
Validated mono 16 kHz waveform
  -> frozen encoder -> frame embeddings
  -> shared head recipe -> phone + blank logits -> frame posteriors
  -> existing allowed-path CTC scorer
  -> calibration fitted on the separate calibration cohort
  -> existing uncertain / review-needed result boundary
```

The local implementation starts with a linear phone projection. Compare dropout or a two-layer head
only if the linear baseline underfits. Use the same vocabulary, optimization
budget, training partitions, and head recipe across encoders; the projection's
input width necessarily follows each encoder. Encoder parameters and encoder
normalization state remain frozen. Tune within speaker/household-grouped folds
inside the training partition, never on the calibration or test partition.

Train CTC against **what was actually spoken**, including substitutions and
omissions. Training against the prompted word would teach the model to erase
the errors we need to detect. Keep accepted dialect variants explicit. A small
phone vocabulary must still represent plausible competing productions; do not
renormalize solely over the expected word. Preserve the existing low-coverage
abstention behavior.

Do not represent a subtle distortion as a clean phone substitution without
label evidence. Distortion/timing models are later target-specific experiments
and may require additional acoustic labels; unresolved cases remain uncertain.
Produced-phone CTC targets do not require exact manual frame boundaries, but a
reviewed alignment subset is useful for diagnosing timing and encoder failures.

The isolated implementation directory `research/audio-head/` now has a pinned
Python environment, frozen feature extraction, linear CTC training, strict
engineering manifests, and JSON posterior export. These are local engineering
tools, with no Python training dependency in the web application. The broader
research deliverables below are only partially implemented; authenticated
dataset authorization, feature caching, governed adaptation, and model export
remain future work:

1. A dataset reader that validates consent/lineage references, audio format,
   produced-phone vocabulary, and speaker/household-disjoint splits before
   feature extraction. Reject duplicate audio hashes across partitions.
2. An offline feature extractor keyed by audio digest, preprocessing version,
   checkpoint digest, and layer choice. Treat cached features as sensitive
   derivatives with the source recording's retention/deletion scope.
3. A seeded CTC head trainer that records the recipe, training manifest,
   checkpoint digest, and learning curves. Run at least three seeds for an
   adaptation candidate; select hyperparameters on training-only grouped folds.
4. An inference/export bridge producing the existing `FramePosterior[]` shape,
   with explicit phone mapping and blank token. Posterior sums, variable-length
   masks, repeat/blank behavior, unsupported phones, and exported-versus-Python
   CTC score parity have engineering checks across three held-out public
   recordings. Validate any future model format separately.
5. A report exporter supplying actual samples and measurements to the existing
   bake-off harness. Do not sign placeholder evidence or weaken that harness
   just to manufacture a winner.

## Data and annotation work

Begin with synthetic tones for integration and explicitly permitted non-patient
engineering fixtures. These establish loading, shapes, failure handling, and
export parity only. Public [SpeechOcean762](https://www.openslr.org/101/) offers
expert pronunciation ratings under CC BY 4.0 for reproducing the GOPT comparison;
those ratings are not pediatric SSD ground truth or calibration for Cadence.
Its [authors' schema](https://github.com/jimbozhang/speechocean762) records
canonical phone sequences and five expert pronunciation ratings, not complete
transcripts of phones actually produced. A direct import as CTC `targetPhones`
would mislabel errors. The next exploratory evaluation should use a separate,
source-pinned rating reader with speaker-disjoint selection, explicit mapping
from stress-marked ARPAbet, and preserved per-rater evidence; it must not feed
the current produced-phone trainer. The [L2-ARCTIC corpus](https://psi.engr.tamu.edu/l2-arctic-corpus/)
offers manually corrected phone errors but has CC BY-NC 4.0 terms and a gated
download form, so it is only a possible noncommercial research source pending
the applicable access and intended-use review. Its manually reviewed
`/annotation` TextGrids, unlike the automatic `/textgrid` alignments, include
corrected phone times and canonical/perceived error tags. The
[candidate assessment](produced-phone-corpus-candidates.md) defines the
conditional /R/ coverage audit and speaker-disjoint method comparison; the
published corpus documentation does not report its /R/ class balance.
The [PERCEPT-R](https://talkbank.org/phon/access/Clinical/PERCEPT-R.html) and
[PERCEPT-GFTA](https://talkbank.org/phon/access/Clinical/PERCEPT-GFTA.html)
corpora are closer to the intended child speech-sound-disorder population.
Their public subset was released with documented consent and assent for sharing,
but the [corpus research note](https://pmc.ncbi.nlm.nih.gov/articles/PMC12510240/)
describes noncommercial distribution. PERCEPT-R records perceptual /ɹ/ ratings
in place of produced-phone transcriptions, and PERCEPT-GFTA has IPA targets but
no transcriptions of participants' actual productions. These are candidates
for a separately licensed, target-specific rating evaluation, not direct
`targetPhones` for the present CTC trainer or evidence for commercial release.
The [PERCEPT-R research preflight](percept-r-research-plan.md) records the
registration, source-version, consent, citation, split, and model-comparison
checks needed before using that child-clinical corpus; no media was acquired.
The [Cummings corpus](https://talkbank.org/phon/access/Clinical/Cummings.html)
is a second, narrower lead for a metadata-only audit: it contains single-word
probes from about 30 children with speech sound disorders, including repeated
sessions. A [linked study](https://talkbank.org/phon/access/Clinical/0docs/cummings2011.pdf)
used narrow transcription of actual productions in four children, but that
does not establish populated, reviewed actual-production labels or phone
times for every deposited record. Check the transcript tiers and provenance
before acquiring media or proposing CTC training. The
[TalkBank rules](https://talkbank.org/0share/rules.html) default to CC
BY-NC-SA 3.0 and require separate care for identifiable local data and model
use; no Cummings data has been acquired for this project.
The first separate SpeechOcean metadata audit now pins the authors' nine
metadata files, verifies the published speaker-disjoint split and all five
phone-rating means, and reports score and rater-agreement counts without
importing audio. Of 94,445 canonical positions, five raters agreed at 78,492
and differed at 15,953; this is descriptive, not a clinical threshold. See
[the local audit](local-training.md#public-expert-rating-metadata-audit).
The first separate [real-audio /R/ rating probe](local-training.md#public-r-rating-probe-with-real-audio)
now defines one exploratory task without feeding the produced-phone trainer:
1,525 public utterances with exactly one canonical `R`, their five-rater mean
rating, frozen wav2vec2 Base features, and a locally fitted ridge head. The
author's 766/759 train/test partition is speaker-disjoint; 25 training speakers
provide validation for the ridge penalty. The source archive and all selected
WAVs are hash-bound to the saved feature cache and model report. Held-out MAE
was 0.2713, versus 0.2730 for the train-mean constant, 0.2658 for the
target-word baseline, and 0.1462 for always predicting 2.0 on this skewed
set. The head predicts outside the 0–2 scale for 125 test utterances. This is
no useful improvement over strong simple baselines, and the previously
inspected test distribution makes it a known exploratory holdout rather than
a fresh confirmatory one. Research-only eligibility flags stay false.
The predeclared matched WavLM Base+ run lowered that same known-test MAE to
0.2589, but produced 163 out-of-range predictions and still lagged the
constant-2 MAE baseline. The contrast does not establish an encoder winner.
The separate [train-only probabilistic rater experiment](local-training.md#train-only-probabilistic-expert-rating-probe)
used all five 0/1/2 judgments per clip and nested speaker-held-out folds.
Its wav2vec2/WavLM out-of-fold per-rater log loss was 0.3180/0.3218 versus
0.3717 for a training-fold class prior. This suggests predictive signal for
the corpus's expert-rating distribution under that split, but seven of ten
outer fits hit their original optimizer cap. A locked 400-iteration sensitivity
run kept all fold selections and changed pooled log loss by less than 0.000002;
zero outer fits and one unselected inner trial hit the new cap. It remains a
whole-utterance, subjective
rating task; it neither identifies /R/ timing nor establishes child SSD
validity, calibration, or feedback suitability.
A [saved-prediction agreement diagnostic](local-training.md#rater-disagreement-diagnostics-on-saved-predictions)
found that the wav2vec2 log-loss gain is substantial for unanimous-zero clips
and modest for the 126 mixed-rater clips. Paired speaker resampling of fixed
out-of-fold predictions shows a descriptive gain over simple priors, while its
WavLM-versus-wav2vec2 interval crosses zero. This reinforces the need for
qualified target-interval/production review before architecture selection for
learner-facing use.
A [locked word-plus-age categorical control](local-training.md#train-only-word-and-age-categorical-negative-control)
now scores 0.3484 per-rater log loss on the same 766 train-side OOF rows,
better than the target-word-only 0.3675 and fold-prior 0.3717 baselines. The
saved wav2vec2/WavLM heads remain lower at 0.3180/0.3218. This pooled acoustic
gain survives the tested metadata control. A paired speaker bootstrap of fixed
OOF predictions places wav2vec2 minus word-plus-age at −0.0303
[−0.0550, −0.0046] and WavLM at −0.0266 [−0.0550, +0.0027]; the latter
interval crosses zero. These are exploratory intervals without retraining or
selection uncertainty. Word and age are corpus
confound probes, not proposed inference inputs or clinically appropriate
attributes. With 301/349 child-band clips unanimously top rated and no
independent target-time or produced-phone reference, the comparison cannot
identify an acoustic /R/ cue or support child clinical use.
A subsequent [train-only duration/RMS confound probe](local-training.md#train-only-duration-and-rms-confound-probe)
uses the identical 766 clips and five speaker folds. Adding full-clip duration
and RMS to a paired word-plus-age softmax improves per-rater OOF log loss from
0.3699 to 0.3319; the saved wav2vec2/WavLM acoustic heads remain lower at
0.3180/0.3218. This shows that simple clip-level signals explain some of the
rating association under these folds, while leaving an exploratory acoustic
gap. Duration and RMS do not identify /R/ production, and these previously
inspected training speakers cannot select a clinical model. A fixed-prediction,
whole-speaker [paired bootstrap](local-training.md#train-only-duration-and-rms-confound-probe)
puts capture-minus-wav2vec2 log loss at +0.0139 [−0.0106, +0.0378] and
capture-minus-WavLM at +0.0102 [−0.0185, +0.0389]; both intervals cross zero
and omit refitting and model-selection uncertainty. The qualified
target-time/production annotation pilot remains the next label dependency.
A newer [paired incremental fit](local-training.md#incremental-frozen-audio-beyond-the-capture-control)
adds each frozen encoder to the word, corpus-age, duration, and RMS control
within the same 766 author-training clips. Under speaker-held-out folds,
combined-model log loss is 0.3131/0.3108 for wav2vec2/WavLM versus 0.3319
for the capture control. A separate
[speaker-and-word-purged comparison](local-training.md#incremental-audio-with-unseen-speakers-and-target-words)
gives 0.3343/0.3321 versus 0.3610. These are exploratory paired point
estimates on previously inspected folds; the purged fits retain only 264–318
clips and 7–20 class-1 ratings. They do not establish a reliable gain,
encoder choice, or localized /R/ evidence. A
[paired whole-speaker bootstrap](local-training.md#paired-speaker-uncertainty-for-both-incremental-runs)
of fixed predictions puts all eight log-loss and Brier intervals across zero;
it omits refitting and selection uncertainty.
The [capture-control age slices](local-training.md#capture-control-by-corpus-age-band)
also show intervals crossing zero for both acoustic heads in each public-corpus
age band. They do not establish an age-specific model winner or child SSD
performance.
The [locked final research fit](local-training.md#fixed-research-only-rater-head-fit-on-author-training)
uses the fixed α=0.1 selected in every train-side outer fold and all 766
author-training clips. Both saved heads were independently refitted byte for
byte; no author-test inference, calibration, or release decision followed.
An [offline replay command](local-training.md#offline-replay-of-the-final-r-rater-heads)
checks both heads against exact pinned author-training WAVs; it is an artifact
smoke check on in-sample audio, not a new performance result.
An independent [train-only nested speaker CV](local-training.md#train-only-speaker-cross-validation)
refit both ridge heads in five outer folds without using author-test labels or
metrics: pooled out-of-fold MAE was 0.29423 for wav2vec2 and 0.29427 for
WavLM, versus 0.20235 for always predicting 2. The encoders were effectively
tied across those training speakers. This weakens the case for choosing WavLM
from the earlier known-test difference and keeps model selection open.

The result points to target localization and label validity as the next
research questions. A whole-utterance mean cannot tell whether the target /R/
was produced accurately, while repeated prompts and a heavily top-scored
label distribution can obscure any acoustic contribution. Before another
architecture sweep, predeclare an evaluation that isolates the target segment
or target-relevant frames, retains speaker grouping and prompt-aware baselines,
uses independently reviewed target times, and keeps a genuinely untouched
final cohort. A deterministic
[train-only 40-clip feasibility sample](local-training.md#blinded-r-annotation-feasibility-sample)
and two locally prepared blinded public-audio packs now make target-time
review possible once qualified SLPs approve the annotation task. Neither the
five-rater aggregate scores nor the CTC-forced paths supply target-time truth.
The [provisional intake contract](r-target-annotation-plan.md#draft-local-intake-contract)
can validate future blinded reviewer exports against the pinned queue and WAV
durations. A [draft signoff worksheet](r-annotation-signoff-draft.md) records the
qualified decisions on sound and interval meanings, playback procedure,
agreement coverage and permitted use before either reviewer starts. No new
labels exist or are approved for training.
Validate any candidate against
the intended child SSD population before considering calibration or learner
feedback. The present corpus supplies neither complete produced-phone labels
nor that clinical evidence.

A [training-only constrained-alignment pilot](local-training.md#training-side-target-location-feasibility-check)
tested whether the existing WavLM phone heads could supply those target
intervals. All 766 eligible train prompts mapped to the vocabulary, but 9 of
20 sampled train clips raised internal /R/ support or stability flags and none
of three heads greedily decoded an entire canonical prompt exactly. A forced
CTC path exists even when the target was not produced; without verified phone
times, its interval accuracy is unknown. Do not train a target-localized rating
head on these intervals as if they were ground truth. Obtain independently
reviewed target-time/produced-phone annotations or an appropriately licensed
source with those references before using segment labels.
The [train-only /R/ rater audit](local-training.md#training-label-agreement-at-r)
adds a second label warning: 611 of 766 selected clips are unanimously rated
2, while 126 of the 155 clips below 2 have mixed ratings. Treating every
below-2 aggregate as a verified binary production error would discard that
disagreement. The [target-interval annotation plan](r-target-annotation-plan.md)
defines a 40-clip, train-side, blinded SLP feasibility pilot as the next
reference-label step; it is a planning draft pending qualified approval, not
collected labels.
The separate [train-only age-slice diagnostic](../../research/audio-head/speechocean_r_age_diagnostics.py)
reuses the saved speaker-held-out three-class predictions without fitting or
selecting a model. Of 349 child-band clips, 301 have unanimous top ratings;
the WavLM head's per-rater log loss is 0.2556 versus 0.2521 for the train-fold
prior. On 417 adult-band clips WavLM is 0.3771 versus 0.4717 for that prior.
Wav2vec2 is below the prior in both bands (0.2144 versus 0.2521 for children;
0.4048 versus 0.4717 for adults). This slice does not establish a clinical
child result or a model winner; it exposes an age-dependent generalization
concern within the public corpus. A separate [speaker-resampled age-band
diagnostic](local-training.md#corpus-age-slices-of-saved-r-rating-predictions)
puts a fixed-prediction interval around each acoustic-versus-prior comparison;
the child WavLM interval crosses zero. These intervals omit refitting and
model-selection uncertainty and do not describe clinical child performance.
The [train-only label-permutation sensitivity](local-training.md#twenty-train-only-rating-permutations)
retrained the same nested speaker-fold procedure after 20 fixed speaker-block
rating shuffles. Both audio heads scored worse than their unchanged OOF result
in all 20, while the fold-prior score stayed fixed. Only 228–236 of 766 rating
vectors changed per shuffle because top ratings dominate. This supports a
feature–rating association in the public data; it cannot identify an /R/ cue,
rule out prompt or recording effects, or serve as a confirmatory significance
test. The locked report and replay were independently reviewed.
The [fixed-alpha age-transfer check](local-training.md#directional-age-transfer-within-author-training)
trained on one age band and evaluated the other using only author-training
clips. Adult→child wav2vec2 log loss was 0.2510 versus 0.2949 for its
source-training prior, but child→adult rose to 0.6707 versus a 0.5664 prior;
WavLM was 0.2922 versus 0.2949 and 0.7020 versus 0.5664, respectively.
The child-trained heads' loss of advantage is a concrete transfer warning,
not evidence about a child SSD clinical population. Independent replay matched
all four fits and metrics; no setting was selected from this result.
The implemented engineering importer now downloads a small CMU Arctic subset
from its official host and retains its notices and source hashes. Its automatic
phone alignments are explicitly separate from produced-phone reference labels;
see [local training](local-training.md) for all three measured speaker-held-out
recipes. The four-speaker 200/800-step expansion lowers greedy automatic-label
token error versus the one-speaker baseline on the repeated holdouts, but the
longer run increases held-out CTC loss versus 200 steps. No complete held-out
sequence is matched, no winner is selected, and the repeated holdouts are not
fresh confirmatory evidence.

The fixed engineering stress check now evaluates all three preserved heads on
those same 24 holdout clips at original level, −6 dB gain, and deterministic
20/10 dB white-noise SNR. It loads the frozen encoder once and shares transformed
features across heads without training or a persistent cache. Gain left greedy
edit counts unchanged; noise worsened all heads, and the longer expanded run
had more test edits than the shorter expanded run under both noise levels.
This is a sensitivity check against automatic labels, not a representative
environmental-noise or clinical robustness evaluation. All runs and conditions
remain reported with no winner selection.

A subsequent predeclared paired comparison controls the initial linear weights
independently of encoder-construction randomness. WavLM's clean held-out test
edit counts were 50/379 and 40/379 at 200/800 steps, versus wav2vec2's 232/379
and 196/379 with matching initial heads. At fixed 10 dB white noise the WavLM
test rates were 21.11% and 23.75%; both budgets remain reported without selecting
a winner. These are automatic-label agreement measurements on repeated adult
studio speech. Different upstream pretraining and official preprocessing remain
part of the comparison, and pretraining-corpus overlap was not audited. The
card-linked CC BY-SA 3.0 terms and retained notices accompany the private WavLM
experiment; separate code licenses do not authorize production distribution.

The subsequent fixed head-initialization check retains all twelve encoder ×
step-budget × head-seed runs. Across seeds 7, 17, and 29, mean test token error
rates were 59.54% / 51.10% for wav2vec2 at 200/800 steps and 12.75% / 10.64% for
WavLM. Sample standard deviations were 1.50 / 0.66 and 0.40 / 0.66 percentage
points respectively. These describe initialization variability on the same
already-inspected recordings only, not population confidence intervals. The
eight added runs used existing cached weights and clean evaluation; no further
noise tests, downloads, tuning, or model selection were performed.

The third-encoder [HuBERT Base run](local-training.md#third-frozen-encoder-hubert-base)
adds six locked fits to those twelve anchors. Mean test automatic-label token
error was 15.83%/14.86% at 200/800 steps across head seeds 7/17/29. This is
between the earlier WavLM and wav2vec2 figures on the same reused adult-speech
recordings. An independent post-fit replay matched all six HuBERT calibration
and test metrics; two exported recordings also passed TypeScript/PyTorch CTC
arithmetic parity. These checks make the engineering pipeline reproducible,
but they do not select a production encoder or establish target-error detection.

A separately scoped research cohort is required for the intended child-speech
question. Define one or two target protocols with an SLP before collection.
Each recording needs a target/prompt ID, produced-phone annotation, acceptable
variant/error/uncertain label, capture-quality label, speaker and household
identifiers, device/noise metadata, annotation version, and permitted-use and
deletion lineage. Keep real identities outside model manifests. Ask two blinded
raters to label independently and adjudicate disagreements; measure agreement
per target and error class before treating labels as a training signal.

Use an initial planning allocation of 70% training, 15% calibration, and 15%
locked test **by household**, with all sessions and augmentations from a
household kept together. The split ratios are adjustable before locking;
representation and minimum correct/error counts per subgroup matter more than
the percentages. Stratify the assignment where feasible by target, age band,
language/dialect, device, and capture conditions. Check duplicate or overlapping
audio across sources. Reserve a later independently collected prospective
cohort for release work.

Do not set a universal number of recordings as proof of readiness. Start with
a small annotation pilot, inspect label agreement and class balance, then
produce learning curves by household and target. Expand until the planned
confidence intervals and subgroup cells support the question. Preserve
uncertain labels separately; do not silently coerce them into the existing
binary evaluation labels. Report how many are excluded from binary error-rate
metrics and evaluate abstention on them separately.

## Experiments and decision gates

| Order | Experiment | Decision it answers |
| --- | --- | --- |
| 0 | Run the existing real-checkpoint synthetic smoke and profile cold/warm inference. | Does the integration execute and remain research-only? |
| 1 | Establish current phone-CTC plus simple engineered-acoustic baselines; reproduce the two references. | Is the new head improving meaningful behavior rather than just producing different scores? |
| 2 | Train identical head recipes on the three frozen encoders; fit each calibration artifact separately on the same calibration cohort. | Which representation provides useful error discrimination at comparable coverage and cost? |
| 3 | Inspect learning curves and blinded errors on training folds; try limited layer unfreezing or parameter-efficient adaptation only when justified. | Is the limitation in representation, annotation, target definition, or data coverage? |
| 4 | Export, quantize, and eventually distill the selected teacher. Recalibrate and repeat held-out/device checks. | Can the measured behavior survive a smaller runtime? |

For each run report false passes (passing reference errors), false rejects
(rejecting reference-correct productions), abstention, conditional calibration
error, per-target confusion, and the same subgroup slices. Match metric
denominators to `evaluation.ts`; report both the rates and their counts so
abstention cannot hide a small decided cohort. Compare risk versus coverage,
not raw accuracy alone. Use household-clustered uncertainty estimates for
differences and subgroup gaps; repeated attempts from one child are not
independent participants. Confidence-interval reporting is additional work,
not an existing harness capability.

Before opening the locked test set, put numeric allowable false-pass,
false-reject, abstention, calibration, subgroup-gap, and minimum-cell limits in
the existing charter with the clinical lead. Those limits are intentionally
not invented here. An underpowered subgroup or missing required label cell
blocks a conclusion. If a test result changes the model recipe, a fresh test
cohort is needed for the next confirmatory comparison.

Engineering targets inherited from the product direction are average serving
cost below $0.01 per completed attempt and prompt feedback latency; use an
initial proposed warm p95 inference budget of 1 second for short clips. These
are design budgets, not observed performance or clinical acceptance criteria.
Record clip duration, hardware, concurrency, cold starts, memory, model bytes,
and end-to-end request latency separately. Do not report inference-only latency
as the learner's total wait.

## Milestones and resource assumptions

These are rough engineering estimates for one ML engineer with platform support;
they exclude dataset access, labeling, legal review, recruitment, and clinical
validation lead time. Dependencies, not dates, determine readiness.

| Milestone | Proposed effort | Deliverable and exit condition |
| --- | --- | --- |
| M0: baseline reproducibility | 2–3 days | Digest-verified loading, synthetic smoke evidence, cold/warm profile, explicit failures for corrupt artifacts. |
| M1: first owned head | 1–2 weeks after permitted fixtures exist | Isolated trainer and feature cache, small-set overfit check, grouped-fold evaluation, export parity. Engineering result only. |
| M2: representative comparison | 2–3 weeks after labeled cohort and charter exist | Three primary encoders, two references, measured three-seed runs, calibration, subgroup intervals, rebuilt bake-off report. No winner if gates fail. |
| M3: adaptation experiment | 1–2 weeks after a supported selection | Authorized lineage, limited tuning versus frozen-head control, new held-out evidence. |
| M4: deployment optimization | Separate scoped phase | Serving profile or mobile student, recalibration, real-device measurements, prospective release evaluation. |

Assume CPU-only local runs for adapter smoke tests. For feature extraction and
head experiments, provisionally size one 16–24 GB GPU and reduce batch size or
clip length if profiling demands it; this is a sizing assumption, not a fit
guarantee. No multi-GPU setup is needed to begin. Cache each frozen encoder's
features once for reusable training runs. Estimate cache size from measured
frame rate × clip seconds × embedding width × bytes per value × recording count.

Budget each experiment as measured GPU-hours × a current approved hourly quote,
plus storage and data transfer. Record the quoted provider/region/date before
booking capacity. No dollar estimate here implies a current cloud price. Count
idle capacity and cold starts in serving cost, not only active inference time.
Do a bounded profiling batch before setting the full run budget.

## Commands available today

From the repository root, these scripts already exist:

```sh
pnpm --filter @speech-therapy/audio-model-adapter test
pnpm --filter @speech-therapy/audio-scoring test
pnpm --filter clinician-web smoke:benchmark
```

The smoke command executes the actual checkpoint on a generated tone and may
download its pinned model into the runtime cache. It does not train a model or
measure pronunciation quality. A successful result must stay ambiguous,
uncalibrated, and ineligible for learner feedback.

After actual charter, candidate, cohort, and run files have been prepared:

```sh
pnpm --filter @speech-therapy/audio-scoring bakeoff -- select \
  charter.json evaluation-manifest.json candidates.json runs.json
```

Those JSON files are required inputs, not files supplied by this roadmap.
The isolated M1 engineering path has started; both the new Python encoder and
the web adapter now verify model bytes before loading. Complete M0 with
deployment profiling and representative failure checks. Continue
with permitted speech data and reproducible evaluation; do not enable scoring
feedback, collect patient speech, or initiate paid training as a side effect of
the interface redesign.
