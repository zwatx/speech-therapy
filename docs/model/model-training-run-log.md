# Active model training run

User requested at least six hours of sustained local model work, September 26,
2026. Start: **08:13:14 UTC** (03:13:14 America/Chicago). Minimum six-hour point:
**14:13:14 UTC** (09:13:14 America/Chicago). The goal stays active; earlier demo
completion does not complete this model goal. Work time and actual training job
runtime are tracked separately. No idle padding or unbounded repeated fitting.

## Current workstreams

- Expand from single-/R/ whole-clip ratings to a shared model for the 24 demo
  consonants. Existing author-training data supplies 14,843 single-occurrence
  phone/clip examples across 2,495 clips and 125 speakers. The ZH target has only
  six examples; 23 targets meet the fixed support rule for this training study.
- Train pooled and phone-conditioned attention heads over pinned frozen speech
  representations, with matched speaker splits and prompt/capture baselines.
  Evaluate whether acoustic training adds evidence beyond easy confounds.
- Investigate partial encoder adaptation on the Mac GPU after baseline and
  gradient/memory checks. Record checkpoints and loss curves, including failed
  runs and negative results. Later experiments must respond to measured results.
- Parallel user-requested UI redesign: black/white, minimal, no cards, caps
  labels, status lights, or eyebrows; reference local The Lab/CS Club projects.
  This does not reduce the six-hour model objective.

## Resource observations

- Mac: Apple M3 Max, 48 GiB unified RAM, 16 CPU cores, approximately 147 GiB free.
  PyTorch 2.8.0, MPS available. Existing local model/data artifacts are present.
- Dell: Tailscale 100.64.0.1, username zwatx; 20 CPU cores, about 15 GiB RAM with 11 GiB
  available, 301 GiB disk free, Intel Iris Xe graphics. Python 3.14.4, no existing
  system Torch. No paid compute. No training data moved to Dell yet.

## Evidence boundaries

Targets are five-rater subjective pronunciation ratings at canonical phone
positions, not complete produced-phone transcriptions or verified boundaries.
Single occurrence avoids conflicting token labels for a phone-type-only query.
Attention weights do not establish sound timing or clinical correctness.

Model selection uses only inner speaker partitions of author-training data.
All examples from a clip/speaker stay together. New all-speaker splits replace,
  and cannot be numerically compared directly with, the earlier 124-speaker /R/
folds. No author-test inference is planned. The historical corpus/holdout was
already inspected; no subset will be relabeled as pristine confirmatory evidence.
A genuinely independent final child/SSD cohort remains a separate requirement.

## Activity

- 08:13 UTC: Goal reset; training/data/compute audits delegated. Existing app
  retained. Current repository still has no tracked history; no staging or commits.
- 08:17–08:21 UTC: Confirmed MPS, local data, broad target support, and selected
  genuine multitask training direction. Cohort/split builder, neural heads, and
  resumable feature cache are being implemented in separate new research files.
- 08:21–08:42 UTC: Built both complete 2,495-clip frame caches. Wav2vec2 CPU
  extraction took 277.71 seconds; WavLM MPS extraction took 936.30 seconds under
  concurrent CPU fitting. These are different checkpoints and workloads, not a
  controlled CPU-versus-GPU speed comparison. Cache hashes and waveform hashes
  are retained. Both frozen-head matrices are now fitting, 60 inner trials each.
- First wav2vec2 mean-head run: 16 epochs, 20.86 seconds, best epoch 1,
  inner macro-target NLL 0.287292. Independent checkpoint replay reproduced all
  2,401 predictions across 399 validation clips exactly. Every hard argmax was
  rating 2; this is not evidence of detecting errors. Validation loss worsened
  while training loss improved, confirming early overfitting. Ranking analysis
  and paired controls are being added before interpretation.
- Five folds of inner control fitting completed (45 fits total: one prior,
  four backoff, and four linear settings per fold). Prior macro NLL by fold:
  0.33068, 0.37684, 0.34564, 0.27092, 0.31218. Selected word/age backoff:
  0.31224, 0.35253, 0.32541, 0.27344, 0.29703. These are inner selection scores,
  not final generalization results. No outer or author-test scoring occurred.
- Read-only reviews verified the frozen trainer and controls, and identified
  queue provenance checks that need strengthening before accepting the matrix.
  A separate verifier is being implemented without changing running sources.
  The partial-adaptation reviewer caught a crash window between selected and
  last checkpoint writes; transactional checkpoint handling is being fixed
  before long runs start.
- Parallel app work finished: monochrome native practice is installed in the
  simulator; six direct-flow tests and additional dark/large-text accessibility
  checks pass. This completes only the UI request, not the model goal.
- 08:48 UTC: Started actual partial-encoder training, wav2vec2 upper one layer,
  attention head, inner fold 0, seed 7. The declared pilot uses fresh head
  initialization, encoder learning rate 1e-5, head learning rate 3e-4, four-clip
  gradient accumulation, a 12-epoch ceiling and three-epoch patience. At the
  first saved update, 100 of 1,597 fit clips had been processed with finite
  gradients. Process ID 93348; durable artifacts are under
  `outputs/multiphone-20260926/adapt-wav2vec-u1-f0-s7`.
- Before launch, both actual MPS encoders updated their allowed upper tensors
  while complete frozen-weight hashes stayed unchanged. The longest inner-fit
  clip (20.408 seconds) passed a two-layer WavLM update in 2.65 seconds; driver
  memory afterward was 1.40 GB. This is not a full-epoch or peak-memory estimate.
  Nine interruption/resume/binding tests and 21 existing head/trainer tests pass.
- A separate target-local feature study is being prepared using the already
  pinned phonetic CTC checkpoint. It will compare estimated phone-window
  statistics with whole-clip features. Expected-phone forced alignment cannot
  establish that a sound was produced; these remain research features without
  reviewed timing labels. No new correctness labels are being invented.
- 08:53 UTC: An independent integrity snapshot accepted 57 completed frozen
  trials against the exact recipe, full settings, source/cache identities,
  checkpoints, stopping curves and saved predictions; 63 remained pending.
  This verification does not rehash every feature file or replay every model.
- The first saved run has within-phone rating-ranking signal despite an
  all-rating-2 argmax. Macro-phone AUROC/AP for rating 0: 0.8341/0.2886 versus
  phone-prior 0.5000/0.06663; for ratings below 2: 0.7815/0.2868 versus
  0.5000/0.08814. All 23 phones had both event classes in this inner partition.
  Five hundred paired speaker-bootstrap draws retain all positions/raters
  within each of 20 validation speakers. These are descriptive results
  conditional on inner selection, not independent or selection-adjusted
  confidence intervals and not child pronunciation-error validation. The
  saved report is `outputs/multiphone-20260926/first-inner-discrimination-v1.json`.
- 08:57 UTC: Age slicing materially limits that optimistic overall result.
  Across all five seed-7 wav2vec2 mean-head inner runs (learning rate selected
  by the original all-age criterion), ages 6–12 have macro-phone rating-0
  AUROC 0.519–0.584 and below-2 AUROC 0.511–0.598. There are only 5–11 children
  per validation partition and some phones lack either event class. Older
  speakers have rating-0 AUROC 0.777–0.837. Child proper-score gains over the
  phone prior are small and reverse in fold 3. The study must not transfer the
  stronger overall ranking claim to the intended child population. These
  inner partitions overlap across folds and are not pooled as independent
  predictions. Full per-phone support and scores are saved in
  `outputs/multiphone-20260926/wav2vec-mean-s7-five-inner-age-slices-v1.json`.
- 09:13 UTC: All 60 wav2vec2 frozen-head trials completed and passed the
  independent recipe/source/checkpoint/history/prediction integrity audit.
  The second 60-trial encoder matrix is still finishing. The first actual
  partial-encoder pilot completed 1,600 optimizer updates over four epochs
  in 1,329.99 seconds. Its selected epoch was 1: macro-target NLL 0.300183,
  worse than the same-fold frozen attention and mean heads (0.289807 and
  0.285644). The result is retained as a negative result; later epochs were
  stopped by the declared patience rule. Saved-checkpoint MPS replay is
  running before the second-encoder pilot. There is no justification yet
  for launching every adaptation configuration.
- 09:14 UTC: Independent review cleared the child-focused frozen-head
  comparison: child-only fitting versus fit-derived class balancing with
  corrected probabilities, both selected using ages 6–12 inner macro NLL.
  Eight synthetic tests cover fit-only statistics, objective correction,
  matching-fit priors, stopping and exact checkpoint replay. All five real
  splits have child-fit support for each child-validation target. The fixed
  40-trial recipe is `experiments/multiphone-child-heads-v1.json`. These are
  targeted follow-up experiments prompted by weak child ranking, not new
  child correctness labels or calibrated clinical decisions.
- The full local CTC extraction is processing all 2,495 author-training
  clips using the pinned, local-only phonetic checkpoint. Root review fixed
  resume/index authority and independently binds target rows to the cohort.
  Forced-state occupancy is explicitly named CTC occupancy: the preflight
  often occupies one spiky frame, so it is not a phone-duration measurement.
  The scalar trainer passed all 13 independently rerun synthetic tests;
  full coverage is mandatory and the partial preflight is rejected. Its
  four fixed regularization settings and all five inner folds will be fit
  only after complete extraction and source checks pass.
- 09:18–09:27 UTC: All 120 original frozen trials passed the complete
  integrity audit. The comparison report retains 60 within-family/seed/fold
  learning-rate selections and all controls. Mean pooling generally beats
  attention, while child performance remains inconsistent. There are only
  27 distinct children across 39 inner-validation fold memberships; these
  overlapping partitions are not pooled as independent observations.
- Full CTC extraction finished in 504.14 seconds with zero network fetches;
  all 2,495 clips and 14,837 eligible target rows were retained. Subsequent
  scalar/window extraction took 31.77 seconds. All features are finite.
  91.14% of forced target states occupy one frame, reinforcing the decision
  not to describe these states as measured phonetic boundaries or durations.
- All 20 scalar fits completed and every saved checkpoint replayed exactly.
  All five folds selected L2 0.01 using the declared all-age inner criterion.
  Macro NLL was 0.26250, 0.28034, 0.24799, 0.21312, 0.24780. Ages 6–12
  within-phone rating-0 AUROC was 0.752, 0.772, 0.824, 0.768, 0.778; below-2
  AUROC was 0.747, 0.751, 0.799, 0.694, 0.737. This is a promising change
  from whole-clip features, but ranking and probability quality differ:
  child macro NLL still loses to the word/age control in folds 0–2 and to
  the phone prior in fold 0. These are subjective-rater research outcomes,
  not validated child pronunciation decisions. Full evidence is in
  `outputs/multiphone-20260926/local-scalar-five-inner-age-slices-v1.json`.
- Five hundred paired child-speaker bootstrap draws per fold compared the
  selected scalar model with the same-fold, seed-7 selected WavLM mean head.
  Rating-0 and below-2 macro-AUROC differences had positive percentile
  intervals in all five folds. These intervals are conditional on the
  selected inner fits, not independent, selection-adjusted or corrected for
  multiple comparisons. Sparse target support changes with resampled
  speakers and remains explicit in the report. No cross-fold pool was used.
- Follow-up studies now separate the 11 estimated local scalar features
  from the two utterance-context features, and test pooled local WavLM
  embeddings. These distinguish whether the promising signal is specific
  to the prompted sound or generic utterance confidence. Both protocols
  retain the original data/speaker boundaries and matching-fit priors.
- The first adapted wav2vec checkpoint reproduced all 2,401 saved inner
  probabilities exactly on MPS. The second-encoder cold pilot is running
  serially on MPS. An independent warm-start review found no binding or
  normalization mismatch for ordinary same-fold mean heads. Four smaller
  warm-update trials are declared in `experiments/multiphone-warm-adaptation-v1.json`;
  the immutable frozen head remains a no-adaptation candidate, because the
  current trainer cannot select epoch zero internally. Any improvement is
  joint continued-training benefit, not uniquely attributable to the encoder.
- Downloaded the trainable upstream version of the phonetic checkpoint
  behind the useful CTC features, pinned to revision
  `ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`. Its 1,263,535,127-byte weights
  match the published SHA-256. This is a candidate for a separate feature
  and adaptation study; it has not replaced the existing models. The
  [upstream model card](https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft)
  identifies an Apache-2.0 multilingual phoneme recognizer trained from
  wav2vec2 large with Common Voice. That training scope does not establish
  child/SSD performance. The first CPU geometry-only preflight is running.
- 09:34–09:47 UTC: The 40 child-focused global-head trials completed in
  890.65 seconds, with all eight fold-zero checkpoints replaying exactly.
  Descriptive five-fold mean child macro NLL improved only modestly over
  matching-fit priors: wav2vec child-only 0.20934 versus 0.21236; WavLM
  child-only 0.20438 versus 0.21236. Within-phone rating-0 AUROC remained
  weak (0.542 and 0.591 respectively). This limits the value of simply
  retraining global features on children.
- The 40 local WavLM-head trials completed in 245.0 seconds wall time,
  with eight fold-zero checkpoints replaying exactly. Combining estimated
  local embeddings and CTC scalars improved all-age macro NLL in all five
  folds (mean 0.242918 versus scalar-only 0.250350). The child-only combined
  model improved mean child macro NLL to 0.186061, versus scalar-only
  0.203760 and its child-fit prior 0.212363. Ranking is mixed: child
  rating-0 AUROC 0.752984 versus scalar-only 0.778841, while below-2 AUROC
  improves to 0.756530 versus 0.745523. These are descriptive means over
  overlapping inner folds, not pooled independent estimates or calibration
  evidence. The complete comparison is `local-head-selected-v2.json`.
- All 60 scalar ablations completed in 129.67 seconds, and all 60
  checkpoints replayed exactly. The 11 estimated local scalars achieve
  child mean macro NLL 0.20259 and within-phone rating-0 AUROC 0.7877;
  the two explicit utterance-context scalars give 0.22291 and 0.6063.
  Target posterior alone gives AUROC 0.7851. This supports a useful local
  phonetic-confidence signal, while contextual encoder and forced-path
  dependencies remain. Local-11 child Brier is still worse than the prior
  (0.08806 versus 0.08453), so the stronger ranking is not a calibration
  claim. Full evidence and sparse phone support are retained in
  `local-ablation-summary-v1.json`.
- The WavLM cold adaptation pilot completed four epochs in 1,557.51
  seconds, selected epoch 1 (macro NLL 0.304655), and again failed to beat
  its frozen mean baseline. Its saved probabilities replayed exactly on
  MPS. The two negative cold starts motivate the declared smaller warm
  updates, rather than expansion of the original cold-attention grid.
- Added a separate scalar outer-refit/evaluation tool; no real outer
  predictions have been computed. Refit locks each fold's inner-selected
  L2, uses only outer-fit rows for optimization and normalization, and
  publishes a frozen checkpoint before a separate evaluation command.
  Review exposed a checkpoint/prediction provenance gap; all four inner
  candidates now replay exactly before selection is accepted. All eight
  synthetic tests and an independent read-only review pass, including
  changed-outer-label invariance and rejection before scoring when the
  output destination already exists. Keep real outer outcomes closed until
  the candidate families and their selection rules are frozen.
- The full-precision phonetic checkpoint passed three CPU geometry checks
  at 1.59, 3.502 and 20.408 seconds (79, 174, 1,020 frames; width 1,024).
  Its full pooled-feature extraction is now running on CPU, with exact
  existing windows, one local and one global vector per target, and no
  labels used for extraction. Twelve synthetic tests and independent review
  cover complete row mapping, waveform identity, resumability and a fixed
  publication race. The GPU remains reserved for adaptation.


## 2026-09-26 10:14 UTC — warm adaptation and development refits

The four prespecified warm upper-layer trials are now running serially on MPS. Both original frozen baselines passed exact CPU cached-feature replay and fit-only normalization checks before launch; they remain eligible epoch-zero candidates. The first wav2vec2 1e-6 trial is in epoch two. The phonetic target/global extractor completed all 2,495 clips and 14,837 rows in 572.49 seconds, with no new alignment or label filtering. Its 80-trial CPU head matrix is running with exact checkpoint replay after every fit.

The fixed 19-pipeline development cross-fit protocol is documented in `multiphone-outer-evaluation-protocol.md`. This is not pristine nested validation: architecture choices already used overlapping inner outcomes. Five full13 scalar refits and 20 local-WavLM head refits are complete; no outer predictions have been computed. Neural outer refits use fresh seed7 initialization and exactly their same-fold inner-selected epoch count. The new head refit/evaluation helper passed ten focused tests and independent review, including holdout-label/value invariance and rejection of mutated provenance. All frozen source files remain unchanged.

A local blinded SLP audit pack contains 15 whole-utterance clips from five inner-validation children and 13 targets. Model/corpus scores are separate from the reviewer queue; recording quality and auditory target judgment are separate fields. Sparse planned strata were left unfilled. This purposeful review sample is not an accuracy cohort, and no new judgments or training labels have been entered.

The minimum six-hour completion time remains 14:13:14 UTC. The goal is active.


## 2026-09-26 10:33 UTC — phonetic matrix complete; controlled continuation prepared

All 80 phonetic frozen-head trials completed in 1,166.7 seconds and each checkpoint replayed exactly. The five-fold inner mean for target+scalar all-age macro NLL was .22916, versus .25035 for full13 scalars and .24292 for local WavLM+scalars. Child-only target+scalar child macro NLL was .18364, versus .21236 for the matched prior and .18606 for local WavLM child-only. Its child rating0 ranking remained lower than scalar ranking (.7539 versus .7788 AUROC), while below2 ranking improved (.7646 versus .7455). These inner folds overlap and are conditional model-selection evidence, not independent child accuracy. The full report retains fold and target support.

Twenty local head refits, five full13 scalar refits, ten scalar-variant refits, fifteen control refits and five global WavLM refits are now complete (55 pipeline/fold fits). Forty phonetic head refits are running. No real outer or author-test predictions have been opened. The release coordinator requires all 95 pipeline/fold refits and will pin report/statistics/queue source before evaluation. Paired speaker-bootstrap analysis passed nine synthetic tests and independent reviews; a synthetic full-size 20-model/14,837-row/2,000-replicate benchmark took 46 seconds and 74 MiB, not an evaluation result.

The first warm-start wav2vec trial finished three epochs in 992.8 seconds; its selected first epoch macro NLL was .284774 versus the unchanged frozen baseline .285644. This small inner improvement is provisional. The remaining warm trials continue serially on MPS. A six-arm raw phonetic continuation study is implemented and independently reviewed: both age regimes compare head-only continuation with final-layer adaptation at 1e-6 and 3e-6. The actual raw epoch-zero checkpoint remains eligible. Ten focused tests include exact synthetic resume, fit/window/scalar identity, gradient restrictions and configuration mutation rejection. Actual MPS parity, memory and first/longest-fit gradient preflight have not run; they wait for the existing queue to release the device lock.

Goal remains active; minimum completion 14:13:14 UTC.


## 2026-09-26 10:50 UTC — fixed release and evaluation

All 95 fixed pipeline/fold refits are complete. The release manifest `outer-release-v1.json` (SHA-256 `971bbc06a79847a69042b88abc750240b4b13917016ace4ee7a568807a6b0843`) pins all 85 refit directories, sources, recipes, feature bindings and child priors before any outer prediction. The 85-job serial CPU evaluation queue is running, with the first two folds verified. The report loader and paired statistics passed their focused tests and independent reviews; final inference output will be bound by the completed ledger before reporting. Author-test remains closed.

A separately declared 20-fit phonetic target-plus-scalar study will test rare-rating weighting in both fit populations, using only each inner fit for class statistics and correcting the output probabilities before unweighted inner selection. Its seven focused tests and independent review pass; no real fits have launched yet. It is outside the fixed outer comparison. The six-arm raw phonetic preflight and queue also passed independent review; the encoder agent now owns the transition after the existing warm queue completes and releases MPS.

Added the current multi-sound decision document and linked the blinded 15-clip SLP audit from the handoff. No qualified labels have been added. Goal remains active through at least14:13:14UTC.


## 2026-09-26 11:00 UTC — completed development comparison

All 85 evaluation jobs completed successfully and the pinned report now aligns every eligible row for 19 fixed pipelines plus the child-fit prior. Report SHA-256 is `c12a0562ffec6f9783c231950a7099dee3a0b0e196cf0a2bc0c7ae810077c542`. For children, all-age phonetic target+scalar macro NLL is .175675 versus .188806 for full13 scalars; paired delta−.013131, conditional95% interval[−.019186,−.006995]. Each of the five child fold comparisons favors the combined model on NLL. Brier also improves (.079533 versus .082215). Rating0 ranking is nearly unchanged (.8000 versus .7971); its fixed-phone interval is withheld because only1082/2000 resamples preserve required class support. Below2 ranking intervals also fail the declared95% valid-draw rule (1831/2000). These are development cross-fit results, not clinical accuracy, calibration or final independent validation. The decision document records the limitations and paired evidence.

The weighted20fit queue is active on CPU with exact replay after each fit. Warm MPS adaptation has completed2/4 arms: WavLM1e-6 slightly improves all-age NLL but worsens the child NLL/rating0 ranking; no order or settings changed. The six-arm phonetic study still waits for that queue. A final research export helper is being prepared for all four fixed target+scalar objective/population variants, selecting settings solely from their five inner folds and fitting all eligible author-training rows; no outer winner is chosen. A bounded capture-sensitivity diagnostic is also being prepared, with transformed audio used only for sensitivity, never as new labeled accuracy examples. Goal remains active until at least14:13:14UTC and completion audit.

Independent review reconstructed all20 saved probability sets, checked80 age/model point summaries and paired differences, and cleared the report. It identified a material word-slice reversal: on614 child targets absent from each all-age fitting target vocabulary, combined phonetic NLL.31635 is worse than scalar.30029; on5040 seen-word targets it improves to.16060 versus.17647. Root independently confirmed these numbers and added the limitation to the decision document. There are no paired intervals for these descriptive slices; words may occur elsewhere in fitting utterances. The capture diagnostic has only5 eligible distinct child inner-validation speakers, so its fixed all-if-fewer-than-eight rule gives20 variants, not32.

## 2026-09-26 11:27 UTC — completed exports and recording diagnostic

All 20 rare-rating fits completed in 627.6 seconds with exact saved-checkpoint
replay. All-age fitting's mean child macro NLL improved .18964→.18653 while
overall all-age NLL slightly worsened; child-only NLL moved .18364→.18332 but
rating-0 average precision and below-2 ranking worsened. The mixed descriptive
inner result does not justify expanding the weight grid. The fixed outer
comparison remains unchanged.

Four fresh full-author-training research heads are complete: ordinary all-age
LR.0003/4epochs, ordinary child LR.0003/5epochs, weighted all-age LR.0003/4epochs,
and weighted child LR.001/2epochs. Settings use only mean five-fold inner loss
and median selected epoch, with no outer winner. Each completed a separate full
provenance replay; ledger SHA-256 is
`8b9a2c51e0e9b47c7ceccd904a7257b1901b9c7ea70f0ae9d048ee23354aa280`.
An independent audit checked the actual 100 inner trials, all 706 bindings,
full-fit moments/priors/weights and optimizer steps. Ten final-export tests pass.

The new portable feature loader passed six tests and independent review. A
separate actual-artifact check copied all four bundles outside the archive,
prohibited training-archive reads, and reproduced every saved fit-row
probability exactly: 14,837 rows per all-age bundle and 5,654 per child bundle,
zero archive-read attempts. This verifies deployable research-head mechanics,
not a new generalization result. The research README and model card record
supported targets, bundle hashes and the feature contract.

The independently reviewed capture diagnostic completed all 20 waveforms with
zero network attempts. Unmodified CTC/scalars/windows/phonetic vectors match
their cache exactly; saved probabilities differ by at most1.863e-9. All-age
mean total variation is .00364 at quarter gain, .03106 at20dB white noise and
.09217 at10dB; its largest10dB change is .70831. Estimated windows move for
4/23 and13/23 targets under20dB and10dB respectively. Root independently
reconstructed every reported mean/max probability movement and argmax count,
and rehashed all bindings. Report SHA-256 is
`162827b916ca1ab167c131a05d148b2acb12c9351befe9d2872e97e02fd815df`.
The report does not transfer original ratings to noisy audio or claim accuracy.

The fourth warm MPS arm is still running; the encoder agent owns its automatic
transition to the reviewed raw-phonetic preflight and six-arm study. A raw-WAV
research adapter is being implemented separately from the app, using explicit
canonical prompts and pinned offline extraction. A possible bounded
noise-consistency follow-up is under design review, not yet declared or run.
Goal remains active; minimum completion14:13:14UTC plus final audit.

## 2026-09-26 12:04 UTC — raw-audio parity and continued training

All four warm upper-layer trials finished with exact replay. The final report
`warm-observation-final-v1.json` has SHA-256
`ed9281d3c728bd4e06a4e1566e8d178800bce783c137f932a07b0d080517afcd`.
Wav2vec2 at3e-6 moved child NLL .195255→.192181 and rating-0 AUROC
.5836→.5981; WavLM at3e-6 moved child NLL .216129→.211198 and AUROC
.5431→.5454. These are small joint head/encoder continuation effects, not
encoder-only causal estimates. Every child argmax prediction remains class2.

The separate raw phonetic preflight passed all four fitting-only cases on MPS,
including the longest all-age20.408s and child10.717s clips. Maximum raw/cache
probability difference was4.77e-6, within the declared.001 tolerance. Exactly
the16 allowed final-layer tensors and7 head tensors changed; lower layers
stayed fixed. The six-arm queue is running, with the all-age head-only control
complete and exactly replayed. It selected epoch1 of3: all-age NLL
.241715→.241329, but child NLL worsened .194696→.200014. The next upper-layer
arm is active. These preliminary outcomes do not change the fixed queue.

The standalone raw-WAV adapter now has actual parity evidence for all four
final research bundles. Four cases cover three unique fold-zero fitting
recordings, ages6/6/26, durations2.58–20.408s,22 unique targets and28 case-target
scores. Full392-way CTC arrays,13 scalars, estimated windows,1,024-dimensional
vectors and final probabilities all exactly reproduce cached artifacts, with
zero network attempts. Cold/load-inclusive case times were5.953–9.246s.
Verification SHA-256 is
`83852b275cd451e72e2e7a94fbc8d00ec1ef240ef07079a8d2586890205f22a3`.
Independent review rehashed105 unique source/model/case/bundle artifacts and
reconstructed the input selection and saved values without new inference.
This verifies the research interface; it is not generalization or app latency.

The fixed20dB noisy-feature extraction is active over1,996 clips/11,811 target
rows. Its three original fitting-clip parity checks passed exactly for all
posteriors/scalars/windows/phonetic vectors. The separate six-arm consistency
trainer and queue are reviewed:18 trainer/binding tests and8 queue tests pass,
plus a declaration regression for equivalent protocol-path spellings. Trainer
SHA-256 is `7058da214a4f072eb008be5975c9c50786fff4ee4d5528d48bf0ee71286d116f`;
queue SHA-256 is `4a4cf7db85ba129f0c4b458dd8293aff455c10ae524ddc639d96d1abb3ab25a0`.
No consistency head fit has run yet. A separate all-six reporting reader is
under independent review, preserving matched controls and clean-only labels.

The [preliminary campaign audit](six-hour-campaign-audit.md) independently
checked255 fixed-evaluation files, all four export manifests and selections,
all five split maps, blank SLP judgments, pending72-word content and the actual
native test bundles. It remains explicitly incomplete before the deadline.
The original training plan now distinguishes initial cached weights from the
later recorded upstream phonetic checkpoint download. Goal remains active
through at least14:13:14UTC and completion of the finite studies/final audit.

## 2026-09-26 12:30 UTC — completed consistency study and fixed replication

The original noisy-feature extraction finished successfully in 1,316.844
seconds: 1,996 clips and 11,811 target rows, with exact original parity and
zero CTC network fetches. Independent review checked all 10,064 file bindings
and every per-clip-to-matrix row. The complete feature manifest SHA-256 is
`db29e07aaccfff4a1b2400e1c3c0670cc19e99b47c71bb8ea9368d72baa16a52`.

All six fixed consistency fits and separate exact replays completed in
327.675 seconds. Completed ledger SHA-256:
`727e071a5276b7f0c6ab045ce4d92c349f95474ac48f742a387ba6c12b546000`.
The reviewed reader produced comparison SHA-256
`a9528724ea614dda419802e3892516a51004976f9639e272e55f0266383d7c0e`.
An independent audit reconstructed every metric, selected epoch, denominator,
signed comparison and Markdown value without new inference. All-age arms
selected/run epochs are 2/4, 2/4 and 3/5; child-only arms are 0/2, 1/3 and 5/6.

At coefficient one, child-only clean macro NLL moves .169948→.167514 and mean
20 dB total variation .031904→.024502, but rating-0 AUROC moves .719828→.712912.
Its all-age NLL worsens .331895→.339547. Every child-only model gives class 2
the highest probability on all 545 child rows, both clean and noisy; root
independently checked this from saved probabilities. Mean clean class-2
probability rises .949147→.953894 and class-0 probability falls .021546→.017218.
The all-age coefficient-one model improves child NLL versus the matched
continuation control and reduces mean noise movement, but its maximum child
movement remains .637272. These are tradeoffs, not a chosen winning model.

The [fixed replication protocol](multiphone-consistency-replication-protocol.md),
SHA-256 `21fbf98b3d778ae333a87aab9ca17c8ee5a36b1d64a3dc5903c11aec0d15de87`,
declares exactly 24 additional fits: the other four existing inner folds,
both fitting populations, and the same three coefficients. Scientific review
accepted this as a test of whether the fold-zero directions recur. It adds no
architecture or coefficient search. The full noisy cache will reuse 1,996
clips and extract only the remaining 499. All 30 original/additional arms will
remain visible; overlapping inner speakers preclude independent-fold claims.
Implementation is underway; no additional extraction or fit has started yet.

A metadata-only word-purge assessment was reviewed and reproduced exactly.
Full validation-vocabulary purging leaves only 8–20 fitting clips; one fixed
three-word design preserves fitting data but has only 27 child targets from
four children and four sounds in fold zero. No new training was launched.
An ordinal-head proposal was also deferred: its one-latent output restriction
would force identical within-phone ordering for two distinct error events,
while reducing total parameters only 0.12%. Neither more fits nor that capacity
change establishes data efficiency or replaces missing qualified labels.

A monochrome [research comparison figure](../../research/audio-head/outputs/multiphone-20260926/child-rating-figure-v1/child-rating-comparison.png)
now presents the fixed outer report's proper-score/ranking tradeoff and
unfamiliar-word reversal. Root inspected the image and independently matched
all 16 plotted values, 12 interval records, support fields and image hashes.
No training environment or dependency manifest changed.

The raw phonetic MPS queue has four completed and exactly replayed arms; both
1e-6 encoder arms and the child head-only control retained epoch zero. The
two fixed 3e-6 arms remain in progress/pending. The summary reader passed
seven tests, independent review and an actual two-arm schema check. Goal
remains active until at least 14:13:14 UTC and the final requirements audit.

## 2026-09-26 12:51 UTC — raw encoder study complete; noise replication ready

All six raw phonetic continuation arms completed in 4,296.24 seconds, with
13 training epochs and 3,940 optimizer updates. All six selected checkpoints
replayed exactly on MPS. Completed ledger SHA-256 is
`6951091ad00a9d620245fda674c83cba481196d6833fb78764af05966fe3bb33`;
the frozen summary SHA-256 is
`609400189cb9e34548a3ab24decc2bfe44361c5c06a692332a740f7a2ae4c894`.
Root independently rehashed 102 summary bindings and recomputed proper scores
and per-phone/macro AUROCs for 54 selected/starting/prior age combinations.
Epoch-selection and update totals also matched. No extra inference was run.

All four upper-layer arms and child-only head continuation retained epoch zero.
All-age head continuation selected epoch one: all-age NLL .241715→.241329,
but child NLL .194696→.200014, Brier .090511→.092534, and rating-0 AUROC
.677741→.669848. Its child argmax counts are 8/0/537; the retained original
all-age model has 7/0/538. Every child-only arm remains 0/0/545. Better child
scores for the unchanged upper-layer arms than the continued control are not
an encoder-adaptation gain. No further MPS run is scheduled from this result.

The full noisy feature extension completed in 326.204 seconds, extracting only
499 new clips and preserving all 1,996 existing clip units and their original
provenance. Full coverage is 2,495 clips / 14,837 target rows. Feature report
SHA-256 is `70143aa6e39bed17d498046fe676a8888d4339e9fb4bc70bab8a0cd477c9b426`;
the completed extraction ledger is
`d72fec4dc9f39887a86f81abe73a3984476308fff414b1ef9db4bec501ad74cc`.
Producer inspection checked all mixed-origin unit/matrix joins and 43,054
named bindings, including repeated path aliases. New-clip CTC extraction
made zero network fetch attempts. Independent consumer audit is pending before
the fixed 24-arm replication declaration and fitting.

The replication trainer and queue are frozen after root and separate reviews;
19 synthetic tests pass. The combined 30-arm reader has seven calculation
tests plus four full synthetic queue/report integration tests. Root reran the
four integration tests successfully, including late input/output/log mutation
rejection and both queue schemas. Reporter source SHA-256 is
`296819b87f7bbc33b4dd77f322c32b8c2fc3eb7b54d9e72d84937e0bc37a4b4b`.
Its actual original-six loader path already passes. No additional fit is
claimed by those synthetic tests.

A new [child target evidence audit](../../research/audio-head/outputs/multiphone-20260926/target-evidence-audit-v1/report.md)
reconstructs distinct child/clip/position support and preserves two fixed
pipelines' published per-phone results. Source and in-memory output were
independently reviewed before publication. JSON SHA-256 is
`adb671304a7263c41fa08d18258419d3396d9d3038108b5743705fec55d36107`.
The 532 child rating-0 votes occupy 331 positions in 258 clips, but per-target
support can be one child/one vote for /G/, or two children/three positions for
/CH/. /ZH/ has no child rows. The audit adds no adequacy threshold, new labels,
inference, clinical diagnosis or selection.

## 2026-09-26 13:09 UTC — replication running; fixed ranking follow-up approved

The independent full-cache consumer audit passed: 43,054 named bindings over
12,563 unique paths, all 14,837 finite 1,037-column rows, all 1,996 reused clip
descriptors and 11,811 reused feature rows exactly preserved. The 499 new clips
are precisely the old fold-zero outer waveforms, now used only as label-free
feature input for the other inner folds. No new outer model scoring occurred.

The 24-arm replication declaration completed successfully. Queue-plan SHA-256
is `d588f8aad315b361d04fd44a381b7069bcdadfc1c4086a34865cbf0af1b1a3d4`;
training-plan SHA-256 is
`3d1d903153cf3e899e58a4c0d198300ee0dfbc8a4aecf355a30a4e76f3fe666c`.
Root launched the reviewed CPU queue at 12:59 UTC, PID 32437. Five arms had
completed exact replay and the sixth was replaying at the last status read.
The remaining fixed arms stay queued; no complete replication outcome is
claimed before all 24 have passed.

Two independent methodological assessments accepted one additional objective
comparison, now frozen in the [ranking protocol](multiphone-ranking-objective-protocol.md),
SHA-256 `dc94968abf6497516e67cea3df764fe5d0c47c40c9005345336765dba8aad2ac`.
Exactly five new child-only fits add a .1 within-phone pairwise ranking loss;
the already declared five child-only NLL continuation controls are reused,
subject to an exact disabled-auxiliary update-equivalence preflight. There is
no new architecture, population, learning-rate or coefficient search. Clean
child macro-NLL still selects the epoch, with epoch zero eligible. This tests
objective alignment with corpus rating events, not new pronunciation labels.

The fit-only sampling support assessment is pinned at
`cefb950e7cfddc80ca3de7bbbc1775240f3fbd31c199085668545cfbc60c7d92`.
Root and a separate reviewer independently reconstructed all 230 phone/event/
fold cells. Sixteen have only one positive child; /G/ rating 0 has zero pair
mass in folds zero and three. Same-speaker pair mass is 2.36–3.07% by fold,
while the most represented child participates in 15.16–17.50% of draws.
Retaining and reporting that dependence is preferable to pretending that many
sampled pairs create more independent participants.

New trainer and queue implementation is delegated in separate files, with a
separate reviewer. No real ranking preflight, declaration or fit has run.
Root's report scaffold preserves full per-phone metrics, three age slices,
confidence profiles and five signed comparisons; five pure calculation tests
pass. Producer/queue integration, independent source review and actual report
generation remain pending. The minimum campaign endpoint is still 14:13:14 UTC.

## 2026-09-26 13:24 UTC — exact ranking preflight and five-arm launch

The ranking trainer, queue and recipe passed separate read-only review and
21 synthetic tests, including an actual synthetic fit followed by separate
checkpoint replay. Source hashes are
`27e88bb197b1117170ad67628ab1d45ff3fedb35444512fcbff8f1be02d33699`
and `bed60725c072275f2bb002463bb54377cdb46ad96ffc8f39ded41cf1716137d8`;
recipe SHA-256 is
`5ebb8c54865be895058b0cb684e8dcb6eb45351009dab3a6dc18b99145579ddb`.

The actual fold-zero fitting-only preflight passed all seven exact checks
across 4,073 fitting rows and 64 optimizer updates. Clean NLL, model state,
optimizer state, normalization, target IDs and supervised order match the
original coefficient-zero implementation; the separate pair RNG remains
untouched with the auxiliary loss disabled. No validation inference occurred.
Preflight SHA-256 is
`cdc6e8f18d10a7d8fbdf75145d721af57f07ae7b9bc387be490ca35988c4ac18`.

The complete five-arm declaration was inspected before launch. Queue-plan
SHA-256 is `119582bc11d297f22f745adb231fe106f29c2970a8b2b4fa7da762e7c78e75c7`;
training-plan SHA-256 is
`fa16ccf2d01b1993eede9dbf91d4040fa673ea746e82bf041f979010b7d4a6ba`.
Root launched the CPU queue in session 77333. The existing 24-arm noise queue
continues separately; 14 arms were complete and the fifteenth was replaying
at the last read. Neither whole-study result is available yet.

The ranking comparison reader also passed independent review. Root reran its
11 pure/integration tests successfully in 3.854 seconds. The integration tests
exercise all three real queue-reader APIs on 35 synthetic artifact sets and
reject changed moments, original predictions, context bindings, absent replay,
partial ledgers and late mutation of an earlier artifact. Reporter SHA-256 is
`c370efd7b9c6d20ab3fed72df324b2ecdacec2374bdcabfcbe8285c01a989e39`.
This verification adds no real model-performance result.

A bounded context-sensitivity diagnostic is being prepared for the native
app's short-word setting: all 17 target-bearing words and 23 existing targets
from the fixed five inner-validation children. Crops will use fixed geometry
and padding, with no transferred human labels or accuracy calculation. This
can measure whole-pipeline dependence on surrounding context, not validate
isolated-word pronunciation or a word boundary. Implementation and independent
review remain prerequisites to inference.

## 2026-09-26 13:44 UTC — all fixed follow-ups complete; independent results checked

All five ranking arms completed in 107.005 seconds with separate exact replay.
Ledger SHA-256 is
`a15ef495bfab20eab545304388cc84e5ab8d644a8cca3f4f54d46effab5779c2`.
Independent saved-artifact inspection reconstructed all row orders, sampled
pairs, best/last RNG states and stopping decisions: 12 epochs, 695 updates and
44,480 sampled pairs. Selected/run epochs by fold are 1/3, 0/2, 1/3, 0/2, 0/2.
No model forward was used in that audit.

The 24-arm consistency replication finished after 2,259.336 seconds, every
arm exactly replayed. Ledger SHA-256 is
`3ec22f795964256954ef7f1e8ebc5c287b7a6707d32653cf73a792bf5a0fb1ab`.
The full 30-arm report, SHA-256
`a39492fe46a3a7294057f29a2bd5ad720bf4b8a8c5b548139378e48899298bcd`,
retains the original six arms and all 24 added arms. A separate auditor checked
12,640 unique authoritative inputs, every clean proper/ranking result, paired
noise movement, confidence, epoch selection and descriptive fold difference.
All matched; independent proper-score formulas differed by at most 2e-15.

For child-only coefficient one, the mean NLL difference from coefficient zero
is −.000373, driven by fold zero. The other folds are worse or unchanged. Mean
TV drops .026504→.024285 but rating-0 AUROC drops .753201→.750422; mean class-2
probability rises. Every child-only coefficient still chooses class 2 on every
clean and noisy child row. All-age coefficient one improves mean child NLL,
Brier and TV, while rating-0 AUROC falls in three folds. Worst individual child
TV remains .76500. There is no coefficient winner or noisy accuracy claim.

The complete ranking comparison SHA-256 is
`ab6fdb53b3641c62d364bc8a97f0d31f84330db61ee96c820736648cd37e3c55`.
Independent audit rehashed 400 source/artifact/ledger/log pins, checked 15
model/fold records across three age slices, and reconstructed 2,070 phone/event
AUROC/AP cells from explicit weighted pairs and grouped thresholds. The
comparison's 39 child memberships are 27 unique children. Mean child macro
NLL improves .183822→.183634, while per-rater NLL worsens .171523→.171753 and
rating-0 AUROC falls .753201→.750896. Average precision and below-2 metrics
also trade off. Every child argmax stays class 2, with increased mean class-2
probability. No later ranking-best checkpoint or new export is chosen.

The fixed [corpus rating reliability diagnostic](multiphone-rating-reliability-protocol.md)
addresses a separate reporting question using four saved development prediction
sets. Protocol SHA-256 is
`0e6de8ab2b07dcff436c0aebd4cbef022a30ed8425b2e4a4f9966c6990955462`;
reviewed source is `8b0a71af50e994bfd1eb0da395f00600d1e4e9a4c3f2ccd737fee18a54b7d7bd`.
Five numerical/boundary tests pass. The actual report is
`26a918151612ccfd7436dc4d00296da25cb5418d242ae3094439b077dc476445`.
Independent reconstruction checked all 232 tables, 2,320 bins and 4,135 file
hashes. All-age combined predictions average .02822 for rating 0 versus the
observed .01882; child-only predictions average .01330. Coarse deciles hide
detail: 93.4% and 97.7% respectively fall below .1, and every child-prior rating-0
prediction occupies that same bin. Small residuals are not useful acoustic
discrimination or clinical calibration. No fit, inference or correction occurs.

The [word-context diagnostic](multiphone-word-context-sensitivity-report.md)
completed in 92.126 seconds after all five original parity checks passed.
All 17 estimated crops / 23 positions across 16 consonants succeeded. Plan,
report and completed ledger SHA-256 values are, respectively,
`7c00c70ca2de98624d7e0957ff821059c8f9780feee69cc18b1434b237b50736`,
`6b3df8d70231cd2ee23f3c79dfb645524d5ad94ff4167f8e8a446de4a21b219e`,
and `ae358074efbab82de55c17a782ab12827e81f44e785a15546c9b4a1eb4b150ac`.
Independent inspection checked all 454 input/derived pins, exact PCM samples,
crop geometry, original parity and all probability/confidence/alignment metrics.
Mean TV is .108499 all-age and .055598 child-only; maxima are .476347 and .514125.
Argmax changes are 2/23 and 1/23. These are pipeline/context shifts with no
human crop labels, verified word boundaries or isolated-word readiness claim.

All sources and the four full-data research bundles remain frozen. The final
requirement audit is being updated and the native demo remains unchanged.
A bounded metadata join of the exact 72 app prompts against corpus word/phone
evidence is being prepared for the SLP handoff. The goal remains active; this
snapshot is still before the minimum 14:13:14 UTC completion time.

## 14:04 UTC — app coverage, presentation and timing evidence

The exact native-prompt/corpus join is complete and independently reconstructed:
29 of 72 word/phone pairs match retained all-age positions and 17 match child
positions, with 67 and 33 positions respectively. Source/worksheet identity,
all 72 joins, distinct support and original rater counts match. Intended word
position is shown, not verified by the join. The final report hash is
`5dbbcf51b716ec388acfa55815cb824e9e67362ca67ac52b2fe00712ec40b609`.
The [coverage handoff](practice-model-coverage.md) and SLP guide preserve all
pending content decisions; no absent pair is declared unlearnable or ready.

The follow-up figure contains exactly 30 saved per-fold signed differences
from the consistency and ranking studies. Independent reconstruction and
visual review passed. PNG SHA-256 is
`3baa5cee9d6330db825446907a0a8860db829e2cf5d9466b7033a02c61bc37fb`;
provenance is
`00d277ccc611df333b9c42390dab0b628d3c3fd65d61b0a5553c841c1e2086b2`.
No new metric, interval, winner or inference was introduced by presentation.

The [campaign audit](six-hour-campaign-audit.md) now distinguishes campaign
wall time from saved process intervals. The 13:57:47 UTC timing snapshot's
narrower job/process windows merge to 4h32m50.894s; MPS-labelled windows merge
to 3h06m51.807s and overlap other work. These include setup, replay and possible
waiting, not hardware-busy telemetry. Elapsed-only records cannot be located
on the wall clock. Independent verification reconciled all 720 source interval
records and five unions within the stated serialization tolerance. Exact
audits/scripts have been copied into the durable campaign-closeout directory.

Final integration review found one stale implementation filename in the
research guide; it now names the actual `multiphone_consistency_replication.py`.
Other reviewed links, 12 displayed hashes and loader commands matched. The
review also identified a distinct unmeasured input boundary: raw inference
accepts valid audio without verifying speech presence. A fixed three-signal
silence/tone/noise diagnostic is being prepared against unchanged final heads;
it will not train, introduce a rejection threshold or assign correctness labels.
The goal is still active and this entry is before 14:13:14 UTC.

## 14:14:15 UTC — campaign final audit

The actual clock is 6h01m01s after the 08:13:14 UTC start, beyond the required
six-hour point. All declared studies and independent reviews are complete.
The [requirement audit](six-hour-campaign-audit.md) records the disposition of
every objective and distinguishes campaign time from saved compute intervals.

The final fixed nonspeech diagnostic completed in 19.583 seconds on CPU2.
All three generated signals returned scores. All four unchanged final heads
gave silence class-2 probability .67470–.91900, despite zero greedy CTC tokens.
This is a concrete missing speech-presence boundary, not a correctness result
or a validated rejection rule. Four synthetic tests and two saved-artifact
audits passed; the independent audit checked 81 distinct paths and exact PCM,
CTC paths, measurements, feature reuse and all 12 probability distributions.
Report SHA-256 is
`0af3245208602f10291c2759723ec9a9526a371399f978912eef422f77ef82cf`.
No new training or model selection occurred during that diagnostic.

The final saved-file/document check verified 140 local links in 11 documents,
33 displayed evidence hashes, 20 exact durable audit copies and the 12 printed
nonspeech probabilities. The four exported models and native monochrome demo
remain unchanged. No queue remains active; no paid compute, publishing or
new private child-audio collection occurred.

The bounded research campaign is complete. The ultimate pronunciation-judgment
product remains unvalidated: qualified child/SSD labels, ages 2–5, natural
isolated-word evidence, independent final evaluation and input abstention are
still needed. The prepared SLP content/listening handoff is the next concrete
step. Simulator evidence remains separate from pending physical-device checks.


## September 27 continuation: complete occurrence training

The user-authorized continuation recovered all 28,227 consonant positions
from the same permitted author-train corpus, including 13,390 previously
excluded repeated occurrences. The dataset, all audio payloads, estimated
geometry and full-precision phonetic vectors were independently verified;
every original vector matched exactly. A [fixed twenty-fit comparison](multiphone-position-training-report.md)
completed 78 epochs and 14,100 updates, followed by independent artifact and
prediction/metric audits. The ten original-row models reproduced historical
weights, normalization and every epoch loss exactly.

Both predeclared gates failed: child within-fold ranking and some probability
metrics improved, but pooled child average precision weakened. Unseen-target-
word slices retain a research signal, including a separately labeled
retrospective subset absent from both fitting vocabularies. No expanded model
was promoted, learner judgments remain disabled, and Colab was not used.
The follow-up below preserves this fixed comparison and its failed gates.

## September 27 continuation: expanded-data inner selection

The [declared selection follow-up](multiphone-position-selection-report.md)
completed twenty inner trials (359 epochs, 68,798 updates) and ten selected
outer refits (33 epochs, 7,991 updates). Every selected setting was frozen
before refitting, and all ten refits were frozen before outer predictions.
Independent verification reproduced all 359 inner checkpoint predictions and
stopping decisions, ten refit memberships/normalizations and twenty inner
diagnostic predictions. Final independent outer and narrative review passed:
thirty prediction replays, six pooled pipelines, 1,944 metric/support tables
and 44,712 phone-support cells reproduce exactly; 216 primary child tables
were also independently recomputed.

Child-only all-position NLL improves .18630 to .18089 versus original fitting,
while below-2 AP decreases .19408 to .18252. Four folds gain in that ranking
metric, but fold zero loses. Both new consistency gates fail; the previous
twenty control prediction/metric records and four pooled controls reproduce
exactly. Word-slice gains persist descriptively. Inner probability diagnostics
do not establish a causal explanation or calibrated model. Seven focused tests
pass; no app behavior changed and no app checks ran. All actual processes
completed with exit zero. Colab was not used.

The two-rate follow-up is closed without an outcome-driven search extension.
The broader goal remains active; the next engineering step is an explicit
occurrence-aware research WAV contract, preserving legacy guards and bundles.

## September 27 continuation: occurrence-aware research WAV interface

The separate schema-2 [adapter](multiphone-position-audio-report.md) now accepts
repeated supported consonants at distinct word/phone positions while preserving
caller IDs and order. The frozen schema-1 guard and all four bundles remain
unchanged. Thirteen new tests and nine legacy tests pass. A declaration fixed
seven metadata-selected child recordings, 66 positions, all 23 phones and all
four bundles before actual raw inference. All seven cases completed with exit
zero and exact CTC, 1,037-value feature and geometry parity against
the expanded export, with exact bundle probability replay from those reference
features. The cases include 28 added occurrences and reverse target
order in three prompts. No new training, author-test reads or Colab allocation
occurred. Offline replay and independent artifact/narrative verification passed:
all 68,442 feature values, seven CTC chains, 66 identities, recording measurements
and direct saved-head predictions were checked. Independent tests passed all
22 cases. The broader model-improvement goal remains active.

## September 27 continuation: filtering repeated-position reports

The [fixed integration check](multiphone-position-filter-report.md) exercised
the existing 100 ms filter without runtime or threshold changes. Thirteen
cases comprise seven schema-2 speech reports (66 targets), a schema-1 BE crop,
and five fresh schema-2 raw inferences on known challenge WAVs with three
explicit B positions. All five new CTC outputs exactly match the old same-WAV
arrays. Thirteen actual VAD passes supply both duration segmentations.

All speech positions and the BE crop retain exact vectors under 100 ms.
Silence, Gaussian noise, tone and helicopter each have all three vectors set
to null; the known dog admission retains all three. The baseline additionally
withholds BE. Seventeen distinct tests pass. Actual inference and offline
verification completed with exit zero. Independent artifact/narrative review
passed, including a direct frozen-VAD replay: all 1,269 probabilities, 26
segmentations, 164 target outputs, thirteen saved-head replays and five
same-WAV CTC comparisons match exactly.
No app change, model fitting, threshold tuning, author-test access or Colab
allocation occurred. Whole-recording evidence is not per-target speech or
prompt-match validation; learner judgments remain disabled.

## September 27 continuation: target-local VAD overlap

The full [target-local overlap diagnostic](multiphone-position-overlap-report.md)
now covers all 28,227 positions in 2,500 recordings. At the fixed 100 ms
setting, 623 positions have no occupied-frame center inside padded VAD output,
including 524 with all five ratings equal to 2; the child counts are 313 and
277. This does not justify target-local withholding. Both actual calculation
and offline reconstruction completed with exit zero, and independent artifact
review reproduced all measurements and support tables. No model, filter rule
or learner-facing behavior changed.

Only four missing frozen VAD passes were needed; 2,496 records were reused.
Seven focused tests passed. All 23 phones and original/added populations retain
complete age, clip/speaker and five-vote support. No Colab allocation occurred.

## September 27 continuation: context of missing VAD overlap

The completed [context breakdown](multiphone-position-context-report.md)
locates 432 of the 623 zero-center cases before the first detected segment;
397 of those are the prompt's first phone and 375 have five top ratings.
One-frame states occur in 91.3% of all positions, so that warning alone is not
a selective defect indicator. Keep every training position and close the local
VAD investigation without a new rejection threshold. A bounded probability-
calibration experiment is the next candidate, using inner speaker-separated
predictions only for fitting and retaining outer rare-rating/per-phone checks.

Ten focused tests and 3,000 independent synthetic checks passed before the
declaration. Actual calculation and offline reconstruction completed with exit
zero. This used saved results only: no inference, fitting or Colab allocation.

## September 27 continuation: child-targeted temperature calibration

The [fixed temperature study](multiphone-temperature-report.md) completed ten
child-targeted scalar fits after exact selected-checkpoint replays. All ten
corrections were frozen before outer evaluation. Child-only child NLL improves
.172332→.171156, but rating-0 AP falls .111119→.107377 and two fold NLL values
worsen. All-age child NLL worsens .169242→.170879. Both declared consistency
screens fail; no bundle or learner policy changes. Sixteen tests, numerical
reference checks and offline reconstruction pass. The next controlled check
can reuse the frozen corrections on the original inner heads to separate the
head-refit transfer from the comparison, without fitting another temperature.

Stable unclipped NLL reporting was verified before fitting; source/protocol and
all resulting parameters are pinned. No encoder inference, head refitting,
author-test reads or Colab usage occurred.

## September 27 continuation: frozen calibration transfer control

The [original-head control](multiphone-temperature-transfer-report.md) completed
ten exact inner prediction replays and ten new outer head passes using the
same ten frozen temperatures. No model parameter, correction or stopping rule
was fitted or selected. Both fixed screens fail again: child NLL changes
.172174→.172895 for all-age and .170193→.170329 for child-only heads; below-2 AP
worsens in both. Child-only rating-0 AP also falls .092311→.084271. Refitting is
not necessary for these failures, without establishing a unique causal account.
All 14,837 positions, 52 children and 23 consonants remain represented. Actual
inner-fit unfamiliar-word child slices have 707 and 1,019 positions, distinct
from the refit vocabularies. All 23 focused tests and offline reconstruction
passed; independent Astra review reproduced ten inner/ten outer tensor outputs
and passed 262,564 artifact/metric checks. No bundle promotion, author-test read,
encoder inference or Colab usage occurred. The next step is word/speaker-disjoint
split feasibility with whole-utterance exclusion before any new model fitting.

## September 27 continuation: canonical lexical feasibility

The [fixed split inventory](multiphone-lexical-feasibility-report.md) now covers
all 25 speaker×word cells per age regime. Literal transcript tokenization failed
before grouping on 531 target rows/305 clips; that declaration and failure remain
saved. The revised source uses complete verified canonical annotations, checking
all 14,843 original positions and 14,837 eligible legacy/vote identities. It records
419 raw/canonical transcript differences and fixes 1,884 word types into five
groups without a support-based search. Whole-recording exclusions retain all 23
phones in each fitting/refit cell. Child selection has 143–475 positions and is
missing phones in seven cells; only six child outer cells have all 23 phones.
No child-only fitting or child outer cell has both rating-0 vote classes for every
phone. Pooled outer coverage remains exact at 5,654 child positions/52 children.
Fourteen distinct tests, actual inventory and offline reconstruction passed;
independent Astra reconstruction passed 6,054,896 checks. No model fit, prediction
read, audio access, Colab allocation or learner-feedback change occurred. Next is
a separate fresh-head comparison with fixed per-rater NLL selection on these
purged memberships and explicit sparse-support results.

## September 27 continuation: fresh lexical-head comparison

The [declared whole-word/speaker comparison](multiphone-lexical-head-report.md)
completed 100 inner fits, 100 fresh refits and 100 outer passes. Each phase was
frozen before the next; no supervised state was reused. Compared with scalars,
combined features worsen child NLL .180497→.185832 and rating-0 AP
.109133→.073270 for all-age fitting, and NLL .182500→.185655 and AP
.081084→.057136 for child-only fitting. Below-2 AP worsens in both regimes;
child-only Brier improves. Both consistency screens fail, with combined NLL
worse in four of five speaker folds per regime. Both neural families beat
matching fit-only priors on pooled child NLL and both AP endpoints. Per-phone
tradeoffs and undefined rare-support cells remain explicit; no family is chosen
per phone from these outcomes.

Thirteen focused tests and a separate direct two-update oracle passed.
Declaration60454, inner36630, refit44148, outer15496, audit63011 and
verify8240 all finished with exit zero. GPT-6 Sol independently reviewed the
parent-authored runner/protocol and artifacts; parent independently reviewed
Sol's core and numerical training updates. Astra attempts hit the agent limit.
Independent artifact review passed 34,622 inner, 11,732 refit, 93,021 outer and
1,885,068 metric/support checks, with 100 exact inner and 100 exact outer replays.
A separate auxiliary-metric reconstruction passed 1,475,025 checks across186
summaries; narrative review checked all61 numerical table rows. Actual optimizer
step counters and selected RNG states were checked; actual optimizer moments
at every training step were not independently reconstructed. The two-update
synthetic oracle separately checked moment values for both model families.
A display-only auditor stdout count discrepancy is documented with the original
log retained. All source/protocol hashes are unchanged since declaration.
No author-test, new audio, encoder inference, Colab allocation, app change or
learner promotion occurred. Keep the scalar baseline for future word novelty
work; a compact phonetic representation requires its own fixed protocol and
inner-only fitting before another bounded development comparison.

## September 27 continuation: fixed compact phonetic features

The [PCA16 comparison](multiphone-lexical-compact-report.md) completes 50 inner
fits,50 fresh refits and50 outer passes on the same purged word/speaker partitions.
Every transform uses fitting rows only; all inner choices were frozen before
refitting, and all refits before outer inference. All-age child rating-0 AP
improves .109133→.125172 and below-2 AP .174946→.186455 versus scalars, while
NLL worsens .180497→.181056. Child-only NLL worsens .182500→.183098 and rating-0
AP falls .081084→.077252, despite better macro NLL/Brier/below-2 AP. Both primary
screens fail. Full-phonetic comparisons improve pooled child NLL and both AP
endpoints but fail complete secondary screens. No per-phone selection or
promotion follows. Close this fixed-rank lead without searching component count.

Eleven tests, a separate SVD/update oracle and offline reconstruction passed.
Declaration 90473, inner 14081, refit 68961, outer 26456, audit 82285 and verify 31993 all
finished with exit zero. Independent artifact review passed 21,834 inner checks,
8,316 refit checks,32,294 outer lineage checks,628,356 primary and491,674 auxiliary
metric/support checks. All 100 transforms were independently SVD-checked;50 inner
and50 outer outputs replayed exactly. Actual optimizer step counters/selected RNG
records were checked; full moment trajectories were not reconstructed. The
parent independently checked Sol's core; Sol reviewed the parent runner and
actual artifacts. Astra was unavailable after prior agent-limit failures.

No author-test read, new audio, encoder inference, Colab use, app change or
learner-feedback change occurred. A separately declared equal-weight scalar/
compact probability average is a concrete next test of complementary predictions;
no mixture or weight search has been evaluated here.

## September 27 continuation: fixed scalar/compact mixture

The [equal-weight comparison](multiphone-lexical-mixture-report.md) combines 50
frozen scalar/PCA16 pairs with stable logaddexp arithmetic. All five pooled child
endpoints improve against scalars in both age regimes: all-age NLL
.180497→.178968, AP0 .109133→.121294 and APbelow2 .174946→.185888; child-only
NLL .182500→.180393, AP0 .081084→.082126 and APbelow2 .153376→.157546. Both
primary screens fail because fold-4 child NLL worsens .000446/.001554. Both
secondary screens fail too: all-age pooled AP declines versus compact, while
child-only mixture NLL worsens versus compact in fold 0. Preserve pooled gains,
fold/phone/age tradeoffs and the unchanged success screen; no weight search.

Declaration 16462, actual 72725 and offline verify 25039 all finished with exit zero.
Six tests and a separate 80-digit Decimal oracle on 60 synthetic cases passed;
max log error 7.105e-15 and max NLL error 4.547e-13. Preflight 22297 verified 423 pins
and 50 paired partitions without mixture/PCA/training/inference calls. Independent
audit 69862 finished with exit zero: 34,824 lineage/arithmetic checks, 628,356
primary and 491,674 ancillary metric checks across 50 pairs and 62 summaries.
Stable logs and NLL match exactly; ordinary-mean error is at most 2.22e-16.
No source head was rerun; prior
studies retain that replay evidence. No author-test, new audio, Colab, app or
learner-judgment change occurred. A fixed speaker-level uncertainty analysis
and fold-4 contribution breakdown are the next evidence step, without fitting
weights or claiming a new independent cohort.

## September 27 continuation: paired child uncertainty

The [fixed analysis](multiphone-lexical-uncertainty-report.md) completed 2,000
whole-child resamples within the original five folds, identical across both
models and regimes. All-age intervals favor the mixture on all five pooled
endpoints; child-only intervals favor NLL, macro NLL and Brier, while both AP
intervals cross zero. Every draw retains all 23 phones and positive vote support
for both pooled AP endpoints; no undefined replicates were discarded.

Fold 4 contains 1,083 positions from ten children. Corpus child 1435 has the
largest positive additive contribution in both regimes. Only its omission
reverses that fold's NLL difference; all 52 pooled omissions still favor mixture
NLL. Every child remains in the main results. This is concentration, not proof
of a recording or label defect. Conditional intervals do not repair the failed
consistency screens or account for repeated development/model-fitting variation.

Eleven tests and a separate 60-case/300-endpoint explicit-vote oracle pass
(max error 4.44e-16). Preflight 36084 checked 431 pins with numerical calculation
forbidden; declaration finished with exit zero. Actual 64811 and exact offline
verification 90091 also finished with exit zero. Independent artifact audit
80297 finished with exit zero: 671,573 checks, exact 2,000×52 sampling matrix,
all 112,000 replicate contrasts and complete intervals/contributions/omissions;
max discrepancy 1.67e-16. No audio, author-test, model fitting/inference, Colab or app work
occurred. Next inspect occurrence alignment and input support across all child
positions, without excluding the concentrated speaker or retuning weights.

## September 27 continuation: frozen input support

The [fixed diagnostic](multiphone-lexical-support-report.md) computes all 50
cells using saved scalar moments and compact PCA transforms. Global and
same-phone refit midranks compare scalar maxima and raw reconstruction MSE,
with strict >.99 descriptive flags. All 5,654 positions/52 children/23 phones
remain in both regimes. Corpus child 1435 has zero globally high PCA residuals
in either regime; all eight high-tail subsets and their complements improve
mean NLL with mixture versus scalar. No exclusions, threshold search or claim
of a recording/label defect follows.

Seven root and independent tests pass; source/protocol review is clear.
Preflight 57951 checked 688 pins/50 cells with score calculation forbidden.
Declaration 94573 and actual 43036 finished with exit zero. Offline verify
92760 finished with exit zero. Independent audit 43568 also finished with
exit zero: 303,083 checks, all 688 bindings/50 cells/11,308 regime-position
records; scalar scores exact, PCA residual error at most 1.39e-17 and summary
error at most 1.78e-15. The new package and
protocol are pinned. Existing full feature-assembly parity is not acoustic
boundary validation. No raw audio, author-test, model fitting/inference, Colab
or app changes occurred. A separately declared supervised compact projection
is a possible next comparison; no new projection has been trained.

## September 27 continuation: supervised projection correction

The [fixed recipe](multiphone-lexical-projection-report.md) learns only a
zero-initialized 1024×16 correction through frozen original PCA heads. All-age
child NLL .181056→.180451 and AP0 .125172→.126397 / APbelow2 .186455→.188015
improve, but fold 2 NLL worsens .000163. Child-only pooled NLL .183098→.183119
and AP0 .077252→.077025 worsen; folds 2/4 NLL regress. Both primary and all
scalar/mixture secondary screens fail. All 23 phone and age/cell tradeoffs remain.

All 50 inner runs completed; 9/25 cells per regime selected epoch zero. Refits
reset the correction and use exactly the selected count, including 18 zero-count
runs. Frozen-head/zero-correction replay is exact. Preflight 6489 verified 783
pins/50 jobs without preparation/training/prediction. Declaration 51972, inner
32712, refit 20543, outer 22115, metric calculation 68179 and offline verification
45297 all finished with exit zero. Ten tests and the parent's independent
2-update AdamW oracle pass; all correction values and both moment arrays match
exactly. Source/history guard findings were fixed and reviewed before declaration.

Independent inner 78534, refit 82673, outer 76457 and metrics 39870 all finished
with exit zero: 10,259 / 5,697 / 2,767 phase checks, 200 exact tensor replays,
30,618 mapping checks, 628,356 primary and 491,674 ancillary metric checks.
Actual optimizer metadata was checked; full intermediate update trajectories
were not reconstructed. No source edits followed declaration. No author-test,
new audio/encoder work, Colab, app or learner-feedback change occurred. The
single projection recipe is closed without a parameter sweep. One separately
declared fixed scalar/corrected-projection mixture is the next composition
hypothesis; no such average has been calculated yet.

## September 27 continuation: fixed corrected-projection mixture

The [fixed .5/.5 combination](multiphone-lexical-projection-mixture-report.md)
improves all-age pooled child NLL .178968→.178619 and the other four pooled
endpoints over the existing scalar/PCA mixture. Fold 2 NLL worsens .000061,
so the primary screen fails. Child-only pooled NLL improves .180393→.180298
but AP0 falls .082126→.082056 and folds 2/4 NLL worsen. The all-age secondary
scalar comparison passes all six checks, including every-fold child NLL;
child-only scalar and both projection-only secondary comparisons fail.
All 23 phones and every age/cell/fold remain. No primary gate was changed.

Astra source/protocol review and independent ten-test run passed before the
freeze. Root ten tests pass too. Preflight 63676 terminal exit zero verifies
891 inputs/50 pairs with mixture calculation and model operations forbidden.
Declaration 37984, actual calculation 74372 and exact offline reconstruction
22717 all finish with exit zero. New source/protocol remains immutable.
Independent artifact audit 67757 finishes with exit zero: 35,623 lineage and
arithmetic checks, 628,356 primary metric checks, 491,674 ancillary checks,
62 summaries and 558 slices. All mixture vectors and logs match separate
max/log1p arithmetic exactly. Initial audit 52623 stopped on its own scalar
config-schema assumption, corrected in the auditor before the successful run;
no study artifact changed. Historical source-head replays are not rerun here.

The full report retains source/plan/report hashes and receipts. No training,
inference, audio, author-test, Colab, app or learner-feedback changes. Close
this fixed-combination lead without weight search. The next bounded direction
is checking existing feature artifacts for a declared clean/volume/noise
sensitivity comparison; no such robustness result has been calculated yet.

## September 27 continuation: full-cohort 20 dB lexical sensitivity

The [fixed label-free comparison](multiphone-lexical-noise-report.md) applies
original scalar/PCA/correction states to the complete saved 20 dB feature cache.
Child mean TV existing→corrected is .030523→.030329 with all-age fitting and
.017917→.017774 with child-only fitting. Worst child TV rises .881108→.887614
or remains .691463; child argmax counts are 58→57 or 10→11. Four/five and
five/five child fold means respectively decrease. All 23 all-age child phone
means decrease, while child-only G and TH increase. No noisy human labels or
supervised noisy metrics, sensitivity gate or promotion follow.

Complete producer inspection 72696 checked 43,054 references/2,495 clips/all
14,837 rows. Preflight 55835 checked 44,303 inputs/50 jobs with prediction,
mixture calculation, encoder construction and training forbidden. Twelve tests
pass after a predeclaration unsupported-ZH inventory correction. Astra source
review and independent tests pass. Declaration 99157, clean anchors 89519,
noise 96335 and metric calculation 52076 all finish with exit zero. All clean
component probabilities/logs and both mixtures exactly match historical sources;
all 50 clean anchors freeze before noisy passes. Sources remain immutable.

Independent cache-only 5632 completes 124,783 checks with no forward pass.
Clean audit 96462 and noisy audit 47449 finish with exit zero: 141,396 and
140,300 checks, respectively, with 150 component replays plus 100 mixture
vectors each, all exact. Metric audit 87361 finishes with exit zero:
1,698,153 checks across every per-position movement and every reported slice.
Auditor sources remain frozen; no independent audit failure occurred.
Exact offline reconstruction 84366 finishes with exit zero. No new training, audio/encoder
extraction, author-test, Colab, app or learner-feedback change occurred.
Close the fixed sensitivity comparison; next inventory already-extracted
additional occurrences under current lexical/speaker exclusions before a
separate data-expansion study. No such new training has occurred.


## September 27 continuation: expanded lexical support

The [full occurrence inventory](multiphone-lexical-expansion-report.md) preserves
all 50 original speaker/word cells and exact original base/retained/excluded
memberships. All 28,227 rows and 2,500 clips are included, with five extra clips
assigned to their existing speaker roles and canonical word groups. Only `COVER`
is a newly visible canonical word type, assigned group 1 by the unchanged hash.
Child positions rise 5,654→9,891, rating-0 votes 532→918 and below-2 votes
1,237→2,004, with the same 52 children. Child /CH/ gains no rows; seven child
selection cells still miss a sound and all 25 have event-class gaps.

Root and independent source checks pass eight tests. Preflight 52351 verifies
37,891 input bindings with inventory derivation disabled. Declaration 77104 and
actual inventory 28859 finish with exit zero. The actual calculation reconstructs
all saved phonetic units and matrices, exact original vectors/scalars and old
lexical/speaker memberships. Earlier standalone feature verification 38129 also
passes with encoder construction and audio decoding forbidden. Offline replay
21643 finishes with exit zero. Independent audit 76618 finishes with exit zero:
15,121,637 checks, 37,891 pins, 17,825 unique paths, 750 original membership lists,
1,420 support views and all 2,500 feature units. No audit failure or blocker.
The standalone reviewer checks direct word hashes, speaker roles, integer support
and exact scalar/target/global/unit joins without the study calculation.
No head inference, fitting,
encoder extraction, author-test decoding, Colab or app changes occurred.


## September 27 continuation: expanded fitting, fixed original selection

The [expanded lexical head study](multiphone-lexical-expanded-heads-report.md)
uses all 28,227 occurrences for the declared fitting/refit populations while
retaining the original checkpoint-selection examples. All 100 inner fits (13149),
100 fresh refits (30055), 100 outer prediction jobs (98214) and report calculation
(74191) finish with exit zero. Four new Python files and the protocol are frozen
under plan 8acf9c21ac69ef8c1aec9518ab4a8a75b27049322d6d8fe7733a5373fb97154c.
Fourteen focused tests pass after fixing a predeclaration temporary-path test
fixture; preflight validates 40,301 input bindings with fitting/evaluation forbidden.
Separate read-only Astra CLI source review 80648 is CLEAR; it inspected source
and parsed syntax, without independently running project tests.

On original child positions, the child-trained equal mixture passes its six-part
primary screen versus the original-data equal mixture. Child NLL decreases
.180393→.177459 and both pooled rare-rating AP measures improve, with lower NLL
in all five speaker folds. The stronger corrected-mixture secondary screen fails
fold 0; the all-age mixture and all four single-family primary comparisons fail.
No result authorizes promotion, learner feedback or an independent validation claim.

Sol independent state audits 50881/53961 finish with exit zero: 145,520/125,280
checks over all inner/refit jobs and 600 saved checkpoint states. All 100 selected
inner predictions replay exactly and all 100 PCA transforms pass independent
NumPy certificates. Independent outer audit 7962 finishes with exit zero:
113,431 checks, 100 exact functional replays covering 112,908 row predictions,
50 PCA recertifications and 2,121 final-rehashed file bindings. Full gradient and
optimizer trajectories were not reconstructed. Offline reconstruction 41830 and
independent report audit 75400 both finish with exit zero. Separate metric helpers
pass 1,345,931 lineage/arithmetic, 7,502,256 primary and 5,807,160 ancillary checks
across all 744 summaries, with 19,329 unique artifact paths rehashed. Empty summary
and missing-phone rejection checks 79958 pass. No independent artifact audit failed.

No audio/encoder extraction, author-test access, Colab, app or learner policy change.
The next bounded direction is a separately declared paired child-speaker uncertainty
analysis of the fixed original-population comparisons, not further weight tuning.


## September 27 continuation: expanded-fitting uncertainty

The [fixed uncertainty study](multiphone-lexical-expanded-uncertainty-report.md)
retains all eight primary/secondary contrasts on the original 5,654 child positions,
52 children and 23 sounds. A single 2,000×52 PCG64seed20260927 whole-child matrix
preserves original five-fold stratum counts. All five child-mixture primary endpoint
intervals favor improvement; NLL is [−.006236, −.000608] and AP0 [.000543, .021860].
Every pooled child leave-one-out NLL contrast stays favorable. Corrected-mixture
secondary macro NLL includes zero and the original fold-0 failure remains. Every
all-age pooled interval includes zero. Child W has unfavorable NLL intervals.
No primary/secondary decision, weight, example or learner policy is changed.

Sol implemented analysis.py/test_analysis.py; root implemented runner/tests/protocol.
Root14tests28769exit0 and native Astra independent14tests pass; source/spec review
CLEAR. Preflight25758exit0 validates40319inputbindings/eightmatches while analysis,
sampling and endpoint preparation are forbidden. Declaration94814exit0 freezes
plan347070d614db0ad885e072181fe076bbffcd394882a50975b37240fe9fca8ebf and all four
new Python files/protocol. Root's predeclaration edit command once used a wrong
relative path and changed no file; it was corrected before final tests/review.
No test or actual study failure followed. Independent synthetic oracle da3000
passes796checks with maximum error4.44e-16 and no actual-data reads.

Actual37203 and exactoffline75981 finish with exit zero. ReportSHA is
5d6e693cfe1ce7bb1b8cd4c5be604524226ead6c21b92def72f5602b99bf3d1c.
Independent actual audit22194 finishes with exit zero:1,240,048checks,
80,000pooled/368,000phone replicate differences, manual quantiles/null counts,
all-fold/all-child influence and unchanged consistency records. All2000draws retain
all23phones and positive pooled AP support; undefined endpoint/phone counts0.
The auditor uses a separate metric path, exactly reproduces the sampling matrix,
verifies40319inputbindings and rehashes18493unique paths. Maximum numerical
error2.22e-16. No independent artifact audit failed.

No training/model/audio/encoder inference, author-test, Colab or app changes.
App builds/UI tests not run for isolated saved-prediction analysis. The next bounded
investigation is complete per-sound fitting support/composition and loss contribution,
including W's regression, without excluding examples or per-sound tuning.


## Complete phone-response diagnosis — 2026-09-27

Completed [phone-response analysis](multiphone-lexical-phone-response-report.md)
under its separate protocol, preserving eight fixed contrasts and 5,654 original
child positions, all 23 sounds/five folds/25 cells/52 children. Composition joins
original/added/all corpus and every inner-fit/outer-refit cell to complete canonical
same-phone counts. No training, new inference, row exclusion or per-sound tuning.

Sol authored the pure helper/tests; root authored the runner/tests/protocol.
Root 12 tests c59c35 and separate native Astra 12 tests705cdf pass. Source review
CLEAR; initial reviewer discovery command collected no tests due to namespace
layout, then explicit modules passed. Preflight38268exit0 verifies40,329pins and
all8matches/50cells with response grouping forbidden. Declaration78792exit0
freezes plan a710cd6d849037e55c6b3df659718a7e1820979ef529d871918c51ff5b279cb5.
All five reviewed source/protocol hashes match the plan. Actual85461 and exact
offline28682 exit0; report7fadd79901f745739ae7862e64fff66af5dcd34ae9ea34183416259597122831.

Attempted Sol artifact-audit followup failed agent thread limit; root prepared a
separate no-project-import reconstruction. Its explicit-vote/canonical synthetic
oracle passes33,198comparisons, max1.11e-16. Native Astra auditor-source review
CLEAR. Actual independent90380exit0:2,037,852checks,18,503uniquehashes, maximum
numerical error2.22e-16; all corpus/fitting composition and every sound/class/fold/
word/child support/contribution checked. No actual study or numerical audit failed.

Child mixture W NLL+.008155 decomposes into rating0+.006586, rating1+.002699,
rating2−.001130; W support323positions51children with votes18/4/1593. Four folds
worsen;13children worsen,38improve,1absent. Alladded4,237childpositions are repeated
canonical sound occurrences; original5,654are singles. AddedT/Nmass is much larger,
CHadds0. This does not prove a cause. Next separately declare a global per-recording/
sound inverse-occurrence loss weight, retaining all examples and unchanged controls.
No fit under that hypothesis yet. All old failures remain. App builds/UI tests not
run for isolated saved-prediction analysis; no Colab, audio or learner policy change.


## Recording/sound-unit weighting — implementation and inner phase

The [fixed weighting protocol](multiphone-lexical-unit-weights-protocol.md) declares
one metadata-only inverse-canonical-occurrence objective for the same 100 expanded
jobs. Root implemented weights/core/runner/tests after the requested Sol agent
spawn failed the thread limit. Core11tests43416exit0 plus independent Astra11tests
49075exit0 pass; core-review receiptfda859b7f70048834668df0b1c3c4e478729c24b328b85ca1ee1f26fc7180f5a.
Actual all-one inner/refit trajectories match both frozen trainers exactly,
including partial batches and model/optimizer/RNG/history/selection/predictions.
Nonuniform gradients and four AdamW updates match independent manual references.

First combined15test59628 run failed one integration fixture because /var versus
/private/var paths differed; the fixture was resolved before freeze. Runner4test
11128exit0 and separate full15test64243exit0 pass. Undeclared protocol screen prose
was corrected to the exact inherited tolerances before review/declaration. Full
seven-file Astra source review CLEAR, receiptc81aee1d6bd2f8da31a2dfccca9434e3d48619724e8a7d96ec2ca87f8c276b55.

Real preflight33672exit0:40,342inputbindings,100jobs,28,227positions and200complete
fit/refit weight states, with fitting/PCA/inference/scoring calls forbidden.
Declaration19906exit0 freezes plan8bf68c8a8738abe238ee9992949db4a3fbf8a2733fe082f25732e2dcf626ca8a.
A receipt read raced its creation after verbal CLEAR; the final receipt arrived
and all seven resolved-path/content hashes matched the plan before actual fitting.
An initial literal protocol-path comparison differed only by ../.. spelling;
resolved path and digest matched. No source changed after declaration.

Independent prefit weight geometry46314exit0:1,948,580checks over all200states,
max5.55e-17, complete canonical counts, every normalized row weight and group mass.
This is metadata verification, not completed checkpoint/trajectory validation.
Inner fitting session62384 is active. All100inner runs must freeze before refit;
all100refits before new outer inference. No held-out result or promotion yet.
User requests greater Opus5.5 use; configured ClaudeCode Max authentication and
exact official model ID verified. An additional read-only Opus snapshot review is
running separately, with tools disabled; do not yet claim its result. No Colab or
new audio/encoder/author-test use; app builds/UI tests not run for isolated research.


All100inner fits62384 now completed with exit0; freeze
8d00606b7120bfd996971fd42cdd89e5c64a5dc294dbab585b722698303d7010.
Started/plan/job-order bindings and absence of failure record checked; fresh refit
launched under that complete freeze. Opus5.5 review95432 completed successfully,
verified runtime canonicalModel claude-opus-5-5/firstParty, result47d2b3e7bc6c5e2d5ef3f11a2dedd60b417dcc7d4fc263438dcd13e89fa71cb3.
Snapshot-only source verdict CLEAR, with a useful nonblocking actual nonuniform
training-loop verification gap; add independent replay before final acceptance.
Opus is now authoring the independent checkpoint audit. Its review did not run
tests or inspect actual artifacts. No new held-out outcome exists yet.


Unit-weight all100refits3742 and all100outer34985 completed exit0. Refit freeze
173eab1878478dd19feaf8b08ceadf0c000d33eba79d2ebdd92c0fef1d9791fd;
outer freeze e6c042db921a1d9fe14fd28598e3bd0e84a5b860b190a97e9d2e4e615a51427a.
Opus5.5 authoring95938exit0 supplied the new independent states auditor; root
read/applied15 exact-context hunks and confirmed its runner/schema assumptions.
The old source stayed unchanged. New source b3b9ecd4a10c48e2b86862683a050a631017728a365afe23f45959f643f559c3
is frozen. Inner32338/refit15534 audits exit0:205408/184488checks,600states,
100 independent PCA certificates,100 exact inner prediction replays; all200
fit-local weight states and full canonical group coverage verified. Maximum
relative weight error2.17e-16. This audit checks optimizer schema, counts and RNG,
not complete optimizer trajectories. Both receipts and all their inputs rehashed.

Additional root auditor86862exit0 closes the nonuniform actual-training gap for
four prespecified s0-w0 inner jobs:100 aggregate epochs through selected checkpoints,
3900 actual gradient/clipping/AdamW updates, five weight values per job and partial
batches63/13. Every epoch loss/selection and selected model/optimizer/RNG state
matches bit-exactly. No post-selection/last/refit trajectory claim. Receipt
 a9aa1ada2da44fe4ce5966197d6ac33edf858ade2a0e8a158133530b55c9c149;
source e38cb7e587d1f355f3a8a5b5dda9f50929f50fb3e53723a054c3dd296ce9358f.
Opus5.5 trajectoryreview42432exit0 CLEAR on source/log snapshots; root independently
verified the full receipt/source/runtime/bindings in trajectory-closure.json.
All Opus invocations verify actual canonical claude-opus-5-5, firstParty, no fallback.
Confirmed exclusive phase JSON creation in multiphone_research_audio.write_json.

Independent outer62692exit0:100 exact forwards,112908position predictions,
170663checks,50 independent PCA certificates; all probability/log/raw/NLL differences0.
Root rehashed its complete input receipt. First unittest discovery passed the old
outer guards because discovery prepended its directory; explicit import assertion
then ran the same2 guards against the new weighted outer auditor and passed.
The new metric auditor's copied response-helper hash was corrected before any
execution. Metric calculation and separate Opus source review are now running;
no improvement or promotion claimed. App builds/UI checks not run: research-only.


Actual report20691 and exactoffline40055 exit0, report
d5ba68decc6b9e5bf514b9eece85316f71b03f073b13e7ee5cb1cb3b74669aed.
Independent metric85657exit0:1,744,610lineage/response,7,502,256primary and
5,807,160ancillary checks;744summaries/19,468artifactpaths. All eight full child
responses reconstructed independently. Numerical auditor source stays immutable.
Opus finalauditorreview3132exit0 found one blocker: it lacked an explicit assertion
that metric and outer replay receipts certify the same outer freeze. This arrived
after numerical checking began; retained the executed source and added a separate
joint closure instead. Synthetic corruption guards pass. Joint30707exit0 verifies
exact plan/report/freeze/outer source, metric source/helper provenance, report
schema, exactoffline receipt and2,353boundfiles. No numerical results changed.

Opus followup96063 returned pseudo-tool markup and unsupported claims about files
outside its snapshot; rejected as approval. Tools were disabled, so those text
invocations performed no file actions. NativeGPT6Astra independently inspected
actual sources/artifacts, passed4,838checks and focusedguardtest, and rehashed all
2,353files. VerdictCLEAR receipt16f08e197eb60c56ad2e7f53a41597a4f4cabca8fcdf83ff02b44f6329915212.
No frozen source was changed to obtain a pass and no numerical tolerance relaxed.

Outcomes:all six primary screens fail. Child weighted mixture worsens all five
pooled endpoints against unweighted expanded, with fold1/2/3NLL worse. /W/ improves
.006224, while /R/+.005452,/T/+.003542,/NG/+.003255 regress. Child secondary versus
older corrected mixture passes all six checks with lowerNLLinallfivefolds, but /W/
stillworsens.001680. Retain both candidates/no promotion. Nextbrief fixes seeds
17/29/43 for both objectives; not declared or executed. Final human report and
currentdecision/README written; numerical-claim/prose verification follows.


## 2026-09-27 — fixed seed replication declared

Declared plan `130992603ce99158345f31ae62f427f0230b0d5503e9ac65d5b8bad55ee6cc26`
under `lexical-seed-replication-v1`. Both objectives, seeds 17/29/43, 100 existing
base jobs per combination: 600 inner fits, 600 fresh refits, 600 outer jobs.
All new source/tests/protocol are frozen. Opus 5.5 authored the seeded trainer
and nine core tests; root supplied runner, analysis and validation. Native Astra
independently passed all 18 tests and four extra synthetic inner-state validations,
then cleared all eight source/protocol files. Exact reviewed hashes match the plan.

Metadata-only preflight checked 42,709 input bindings, 400 objective/partition
weight states, 28,227 expanded rows, 14,837 eligible original positions and 5,654
child positions. The first supplemental preflight assertion confused 14,843 raw
source rows with 14,837 eligible rows; its failure and source were preserved.
A new check uses the frozen original-row mapping and passes with fitting,
PCA, inference and scoring forbidden. No study source or population changed.

Declaration session 6914 exited 0; inner session 92020 launched on Mac CPU2.
No new result, refit or outer evaluation yet. No Colab allocation, app change or
learner promotion. Source review and declaration binding are retained under
`work/lexical-seed-replication-audit-20260927`. All prior results remain unchanged.


Independent verification tools are prepared and source-reviewed while inner
training runs. Opus 5.5 authored the new seed-aware state auditor. Root supplied
outer replay, per-seed metrics and aggregate reconstruction. Synthetic checks
cover all 12 seed/objective/family refits, four complete inner selections, 12
exact outer replays, corruption guards, real nonempty/empty metric summaries,
and three-seed support/range checks. Astra independently passed the tests and
cleared the sources. A reported-probability ranking-tie gap was corrected in a
new `report_audit_v2.py`; the earlier executed auditor remains preserved.
No actual 600-job state, prediction or metric audit has completed yet. The inner
training process remains active; these are verification-tool results, not a new
model-performance result.


Seed replication inner phase 92020 completed all 600 jobs (exit 0). Freeze
`6b475cc065d598b3584b91347d7f4ac1d545148acfe8cd00e56c706b9f8890c1`
retains exact declared job order. Root rechecked all source-review bindings.
Fresh refit session 33269 and independent inner-state audit session 30247 are
running. No outer predictions or performance conclusions yet.


Seed replication fitting and prediction are now complete: all 600 inner fits,
600 fresh refits and 600 outer jobs exited successfully. Independent saved-state
audits passed 481,519 inner checks and 385,970 refit checks, including 300 PCA
certificates per phase. The separate outer audit reproduced all 600 predictions
exactly (276,558 checks; zero probability, log-probability, raw-probability or
NLL difference). Full optimizer trajectories are not claimed.

Refit freeze `afb38a488d1fc9dc783d0204cb7e702d83f8910f8ebd8c77d550be7207469332`;
outer freeze `feb2892f062da2e525042ebfe2075dae137b65d0c4e3eae469ee95840ce9d56e`;
outer audit `af0de0f533e129530a360e307c093beec292e8727e628f4e56edfa5702bf6267`.
The full three-seed metric report is being calculated, with exact offline and
independent metric/aggregate checks still required. No new performance claim.
The new research artifact handoff passed bounded source and narrative review;
existing portable bundles and newer evaluation-only checkpoints remain distinct.


Seed replication full report17318 completed (exit0), SHA
`9bc5cb8404c6d4cada307a8a4aa01b8acb4d2913bc896519786c1502e040ca34`.
Exactoffline67507 reproduced all three full seed reports and the aggregate.
Independent metric sessions20561/78759/28990 passed all1,488summaries perseed:
4,464total, every30primary/secondaryresponse and all23sound supports. Each ran
3,162,032lineage/response,15,004,512primary and11,614,320ancillary assertions; these
are audit operations, not independent observations. Aggregate76869 passed
136,749checks/32,554bindings, receipt
`95ce07120c621fb9fb8aa3caa1315d7642b79755fbdd086eee32ab780d763a17`.
No frozen source or tolerance changed to obtain a pass.

All18primaryscreensfail. Child-mixture Brier andbelow2AP worsen atallthreeseeds;
NLL direction varies. W improves repeatedly, T/K/R/NG worsen. Childsecondary
passes weighted17/43 andunweighted43 only; neither objective passes everyseed.
Close fixedweighting as a general improvement lead, preservealloutcomes, no
bestseed orlearnerpromotion. Opus5.5 interpretation51438 used suppliedsnapshots
only; root corrected an unsupported 'new K loss' claim and rare-event wording.
NativeAstra provisional narrative reviewpassed7,594checks/53draftrows/116fulltable
rows/690CSVrows. Final humanreport/statusdocs prepared; finalpublication/binding
review follows. No appcode/Colab/newaudio orencoderexecution in this study.
