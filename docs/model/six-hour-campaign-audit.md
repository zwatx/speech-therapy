# Six-hour model campaign audit

**Status: COMPLETED RESEARCH CAMPAIGN. Final audit: September 26, 2026, 14:14:15 UTC.**
The recorded start is **08:13:14 UTC** and the minimum six-hour point was
**14:13:14 UTC**. The final clock check records **6h01m01s** since that start.
All declared training queues, diagnostics, coverage and presentation work are
complete, with independent artifact review. The requirement audit below is
complete. This closes the bounded local development/training/evaluation
campaign, not the ultimate child-pronunciation product goal. Qualified child/SSD
labels, ages 2–5, an independent final cohort, speech-presence/abstention
validation and physical-device checks remain explicitly outstanding.
Elapsed campaign time is not continuous GPU time or a sum of overlapping jobs.

This audit inspected current source, local manifests, completed ledgers,
checkpoint/report bindings, and native test-result bundles. It did not train,
run new acoustic inference, obtain new labels, or inspect author-test audio.
Paths beginning `outputs/` below are relative to
[`research/audio-head`](../../research/audio-head/README.md). Completed evidence
is distinguished from a declaration, a stored verification result, and a
measurement independently rechecked for this audit.

## Completion boundary

The active objective is at least six hours of substantive local development,
training and evaluation **toward** reliable pronunciation judgment, with the
model as the primary deliverable, reproducible experiments, preserved evaluation
boundaries, an honest account of data/label gaps, a concrete annotation handoff,
and the existing native demo intact. It does not authorize replacing missing
qualified labels with model predictions or calling corpus ratings clinical
correctness. The Mac supplied the local CPU/MPS work; the authorized Dell was
available but unnecessary. No paid compute was used.

The strongest defensible deliverable here is a set of reproducible research
models, measured limitations and prepared next steps. An untouched independent
child/SSD final cohort was not available at the start and has not been created.
Keeping author-test closed during this campaign preserves the current boundary;
historical exposure means that public partition is not an untouched final set.
A later campaign-completion statement must carry this unmet external evidence
requirement forward. It cannot mean the ultimate child-pronunciation objective
has been achieved.

## Requirements and present evidence

| Requirement | Status | Evidence and practical limit |
| --- | --- | --- |
| At least six hours of useful model work | **Completed campaign** | Actual final clock: 14:14:15 UTC, 6h01m01s after the recorded start. The [run log](model-training-run-log.md) and successive completed studies document development, fitting, evaluation, independent review and handoff work. Recorded process intervals are reported separately below; no six-hour continuous-GPU claim is made. |
| Actual supervised training and saved models | **Proved** | Four unchanged final exports have nonempty histories, fitted normalization/priors, checkpoints and exact replays. Completed follow-ups include six raw phonetic arms, 30 consistency arms and five new ranking arms; counts and update evidence appear below. The supervised task remains five-rater 0/1/2 canonical-position rating distributions, not produced-phone recognition. |
| Local resources, no paid compute or user-audio uploads | **Supported within inspected scope** | Fit commands in the ledgers use the local Python environment and CPU or MPS; feature extraction uses pinned local weights. No cloud training or private Cadence recordings enter the cohort. A pinned upstream phonetic-weight download is recorded: this campaign must not be described as network-free or download-free. Local computation alone does not confer data rights. |
| Reproducible, usable research artifacts | **Proved within recorded environments** | All 28 final-export ledger file pins and all four manifests' six-file maps match. Stored replay and copied-bundle verification report exact probabilities for every fitted row with training-archive reads forbidden. Raw-WAV verification covers four bundle/case checks across three distinct clips, spanning 2.58–20.408 seconds. This is implementation parity, not model performance or app latency. |
| Speaker and waveform separation | **Proved for fixed split membership; interpretation limited** | This audit independently recomputed five folds' row, clip, speaker and WAV-hash separation. Inner fit/validation exactly subdivide outer fit; every eligible row occurs once in outer holdout. Architecture choices used overlapping inner outcomes, so the speaker comparison is development cross-fitting rather than pristine nested validation. |
| Meaningful comparative evaluation | **Completed, with limitations** | The frozen release specifies 19 pipelines and 95 fitted pipeline/fold combinations. All 85 evaluation jobs are complete; this audit rehashed all 255 ledger-bound output files. The aligned report contains 14,837 rows per pipeline plus the child-fit prior, fixed paired speaker resampling, age support and word-familiarity slices. No outer winner is selected. |
| Author-test remains closed; untouched final evaluation | **Campaign boundary supported; untouched cohort missing** | Cohort and splits require `authorPartition: train`; releases forbid author-test inference. Historical /R/ work already exposed that public test population. No independent child/SSD final cohort exists here; used public data cannot be renamed untouched. This is not a host-wide forensic audit of every process. |
| Negative results and tradeoffs retained | **Proved in saved reports** | Cold encoder pilots lose to frozen comparators; all four raw phonetic upper-layer arms retain epoch zero. Consistency reduces average synthetic-noise movement without a consistent rare-rating gain; ranking has mixed proper-score/ranking effects. Unseen-word and cropped-word evidence limits app transfer. No training percentage is relabeled pronunciation accuracy. |
| Ages roughly 2–12 and SSD relevance | **Limited / missing** | Current eligible data contain 52 speakers aged 6–12, with 5,654 target rows. There are no ages 2–5 and no verified SSD cohort. Of 28,270 child rater judgments, 27,033 are class 2, 705 class 1 and 532 class 0. Sparse per-phone errors constrain ranking uncertainty and thresholds. |
| Broad sound coverage | **Research coverage proved; clinical readiness missing** | The stable inventory has 24 consonants; 23 meet the predeclared metadata support rule. ZH has six rows and stays unsupported. Each export rejects unsupported targets. These counts do not establish age readiness, dialect validity, or a treatment sequence. |
| Speech-presence/input-suitability boundary | **Measured gap; no verified policy** | The [fixed nonspeech diagnostic](multiphone-nonspeech-report.md) processes silence, noise and a tone through unchanged raw extraction and four final heads. All three return scores; silence has class-2 probability .67470–.91900. Exact input/output and feature reuse audits passed. Neither forced alignment nor high corpus-rating confidence verifies speech; three synthetic cases do not validate a rejection threshold. |
| Native-prompt/model coverage handoff | **Completed metadata check** | The [coverage handoff](practice-model-coverage.md) checks all 72 literal native prompts against the pending SLP worksheet and retained corpus rows. Exact word/phone matches occur for 29 pairs at any age and 17 pairs among children, covering 67 and 33 positions respectively. Intended word position is shown but not validated by this join. All 72 rows and distinct support/vote counts passed independent reconstruction; no inference or clinical readiness labels are involved. |
| Qualified annotation and content handoff | **Prepared; review missing** | The [SLP handoff](slp-handoff.md) links the exact 72-prompt worksheet, all pending, and a blinded 15-clip/13-target listening pack. The current reviewer CSV has blank reviewer, judgment, heard-sound and recording-quality fields. No new qualified labels or reviewer approvals exist. The separate 40-clip /R/ timing protocol remains distinct. |
| Data/model rights and provenance recorded | **Recorded, not a new permission grant** | The [model card](multiphone-research-model-card.md) retains SpeechOcean/OpenSLR and encoder attribution; byte/revision pins are in executable recipes. The [child-data assessment](child-pronunciation-data-options.md) identifies restricted candidates and conflicting BabAR license signals. None of those child corpora was imported into this campaign. Research records do not authorize redistribution, commercial deployment, or clinical use. |
| Polished native practice remains usable and separate | **Observed simulator evidence; device limits remain** | Saved results were reread: 86/86 integrated tests, later monochrome small-phone 6/6 direct-flow tests, and dark-appearance 1/1 test. The currently installed monochrome home was visually checked on iPhone 17 Pro / iOS 26.5; Start practice is visible without enrollment. The [native delivery record](../implementation/native-demo-checkpoint.md) retains real recording/replay/cleanup, baseline legacy failures and physical-device limits. Research is not connected to learner correctness feedback. |
| Existing repository work preserved and changes reviewable | **Limited by absent history** | `git status --short` still lists the repository content as untracked; `git rev-parse --verify HEAD` reports no revision. An empty Git diff cannot establish that nothing changed. Review uses actual files, pre-edit snapshots where available, tests and immutable artifact hashes. No staging, commits or publishing occurred in this audit. |

## Completed training and export evidence

The current ledgers mark these finite inner matrices complete: 120 original
wav2vec2/WavLM head trials, 40 child-focused global trials, 20 full scalar fits,
60 scalar ablation fits, 40 local-WavLM head trials, 80 phonetic head trials and
20 weighted phonetic trials. A queue job can contain several fits, so queue
length must not be reported as a model count without checking its recipe.
The original matrix also has a separate completed integrity report. These
counts describe distinct research trials, not independent datasets or clinical
replications.

Final export selection is separate from the outer comparison. The final plan
audits all 100 original/weighted phonetic inner trials; each of four fixed
variants selects one learning rate by its five same-regime inner-fold mean
macro NLL, breaking exact ties toward the lower learning rate. Fixed epochs
are the integer median of the selected five best epochs. Fresh seed-7 models
then fit the full eligible author-training population for that variant.

| Final research variant | Learning rate | Fixed epochs | Fit rows / speakers | Ages |
| --- | ---: | ---: | ---: | --- |
| Unweighted, all age | 0.0003 | 4 | 14,837 / 125 | 6–37 |
| Unweighted, child only | 0.0003 | 5 | 5,654 / 52 | 6–12 |
| Weighted, all age | 0.0003 | 4 | 14,837 / 125 | 6–37 |
| Weighted, child only | 0.001 | 2 | 5,654 / 52 | 6–12 |

The [research model card](multiphone-research-model-card.md) records intended
use, the 1,037-value feature contract, objective correction, unsupported ZH,
and individual checkpoint/manifest identities. In-sample export replay is
only artifact verification. No holdout performance is attached to these
full-author-training checkpoints. The four final fits' recorded optimizer-step
counts are 928, 445, 928 and 178 respectively. Later continuation and diagnostic
results do not replace or modify these exports.

## Results that constrain the next claim

The [fixed speaker comparison](../../research/audio-head/outputs/multiphone-20260926/outer-comparison-v1/report.md)
reports child macro NLL 0.17567 for all-age phonetic target-plus-scalar heads,
versus 0.18881 for full13 scalars; the paired conditional interval for the
difference is −0.01919 to −0.00700. Child per-rater Brier also improves. This
supports useful development evidence for predicting corpus ratings.

It does not establish broad error detection. Child rating-0 AUROC is nearly
unchanged, 0.79997 versus 0.79710. Only 1,082/2,000 speaker bootstrap samples
retain both classes for every fixed rating-0 phone, so its interval is withheld
under the predeclared 95% validity requirement. Below-2 has 1,831/2,000 valid
draws and is also withheld. One child /G/ rating is class 0. On the same 614
child target rows with unseen fitting target words, combined-head macro NLL
is worse than scalar-only: 0.31635 versus 0.30029. That slice is not a
word-disjoint experiment; words can appear elsewhere in fitting utterances.

The [weighted comparison](../../research/audio-head/outputs/multiphone-20260926/phonetic-balanced-comparison-v1/report.md)
retains small proper-score improvements and mixed rare-rating rankings.
The [capture diagnostic](multiphone-capture-sensitivity-report.md) retains
large shifts for some individual noisy examples. It never reuses clean human
ratings as noisy correctness labels. The stated evidence does not justify
learner thresholds, calibration, correct/incorrect feedback, or diagnosis.

## Completed bounded follow-ups

- **Raw phonetic continuation completed:**
  `outputs/multiphone-20260926/phonetic-adaptation-queue-v1.json` now marks all six
  arms and the queue complete. The pinned comparison records 13 epochs and
  3,940 updates, with exact same-device checkpoint replay for all six arms.
  Only all-age head-only continuation selects a post-initialization epoch
  (epoch 1); the other five retain epoch zero. Upper-layer adaptation did not
  improve its clean stopping criterion in this fixed study. Root independently
  checked the 102 artifact pins, epoch selection and 54 model/age metric
  combinations; this audit reread the completed queue/report and their hashes.
  No further GPU experiment is declared.
- **Recording-consistency features and original six arms completed:**
  The 1,996-clip/11,811-row noisy feature extraction finished at 12:12:12 UTC,
  exit 0, in 1,316.84 seconds of measured extraction. Original fitting-clip parity
  was exact for q8 posteriors, 13 scalars, 1,024-dimensional vectors and windows.
  Its subsequent audit checked 10,064 pins and every per-clip-to-matrix join.
  The six declared head arms completed and replayed; the immutable queue
  ledger and comparison report are pinned below. The
  [protocol](multiphone-noise-consistency-protocol.md) uses a fixed clean teacher,
  clean-only human supervision and clean-only epoch selection. Smaller movement
  under synthetic noise is not transformed-audio accuracy or a general robustness
  claim. All six arms and their proper-score/ranking tradeoffs remain recorded.
- **All 30 consistency arms completed:**
  The [replication protocol](multiphone-consistency-replication-protocol.md)
  fixed exactly 24 additional fits: four remaining folds, two fitting populations,
  and the same three coefficients. The reviewed shared-cache extension under
  `outputs/multiphone-20260926/consistency-features-extension-v1/` finished at
  12:49:03 UTC, exit 0, after 326.20 seconds including its starting verification.
  It contains 2,495 author-training clips and 14,837 eligible rows, reusing the
  exact 1,996 original clip units and extracting only 499 missing clips. A
  post-run inspection verified all 43,054 named pins (including repeated path
  aliases), original-plan identities and exact complete per-unit-to-matrix joins.
  The added clips' CTC pass reports zero network attempts. The independent
  consumer audit also passed: 12,563 unique paths, the 1,996 original clip
  descriptors and 11,811 original feature rows remain exact. The extension includes
  former fold-zero outer waveforms for other folds' inner studies; it performs
  no new outer model-performance evaluation or author-test inference.
  The 24-arm queue completed in 2,259.34 seconds with separate exact replay for
  every selected checkpoint. Together with the original six, the histories
  record 103 training epochs. No new coefficient, architecture or learning-rate
  grid was added. The [combined report](../../research/audio-head/outputs/multiphone-20260926/consistency-replication-comparison-v1/report.md)
  independently passed all 30 checkpoint/replay/log checks and 12,640 unique
  authoritative input pins. Every clean metric, phone/clip noise movement,
  confidence profile, fold mean and signed difference was recomputed from saved
  probabilities without model inference.

  Child-only coefficient one changes equal-fold clean child NLL from 0.183822
  to 0.183449 and mean noise TV from 0.026504 to 0.024285. The NLL gain is driven
  by fold zero: the four new fold differences are +0.000008, +0.000562, zero and
  zero. Rating-0 AUROC falls from 0.753201 to 0.750422 while mean class-2
  probability rises from 0.957285 to 0.958569. All child-only coefficients assign
  class 2 the highest probability on every child target, clean and noisy; zero
  argmax changes do not prove robustness. The largest child-only TV remains
  0.470951. All-age coefficient one reduces mean child NLL and noise TV, but
  mean rating-0 AUROC also falls; its largest individual child TV is 0.764996.
  These are retained tradeoffs, not a coefficient winner.

  The inner validation sets contain 27 unique children, 539 clips and 2,954
  targets, versus 39 child, 778 clip and 4,245 target fold memberships. Shared
  participants preclude interpreting the five means as independent replications.
- **Five ranking-objective arms completed:**
  The [fixed protocol](multiphone-ranking-objective-protocol.md) reuses the five
  child-only NLL controls above. Before fitting, the actual auxiliary-disabled
  preflight matched clean loss, model/optimizer state, moments, target IDs and
  supervised order across 4,073 fitting rows and 64 updates; the separate pair
  RNG was untouched and no validation inference occurred. The five new arms
  completed in 107.01 seconds, with 12 training epochs, 695 updates, 44,480
  sampled pairs and separate exact checkpoint replays. Saved order/pair digests
  and best/last RNG states were independently reconstructed. Selected epochs
  are 1, 0, 1, 0 and 0, retaining warm epoch zero when clean stopping warrants it.

  The [comparison](../../research/audio-head/outputs/multiphone-20260926/ranking-comparison-v1/report.md)
  passed a separate audit of 400 artifact pins, 15 model/fold records across
  three age slices and 2,070 explicit weighted phone/event ranking checks.
  Against matched NLL controls, child macro NLL changes 0.183822→0.183634, but
  per-rater NLL worsens 0.171523→0.171753. Rating-0 AUROC falls
  0.753201→0.750896 while AP rises 0.157253→0.159605; below-2 AUROC rises
  slightly while AP falls. Every child argmax remains class 2, and its mean
  probability rises 0.957285→0.958105. Pair draws are dependent samples from
  existing votes, not new labeled children. No coefficient or ranking-best
  checkpoint was selected, and no export changed.
- **Fixed corpus-rating reliability diagnostic completed:**
  The [diagnostic](../../research/audio-head/outputs/multiphone-20260926/rating-reliability-v1/report.md)
  uses four named saved out-of-speaker prediction sets, two fractional-vote
  events and ten declared probability bins. An independent reconstruction of
  all 232 pooled/phone/fold tables and 2,320 bins had maximum numerical difference
  1.11e-16 (rounded); all
  4,135 authoritative pins matched. There was no fitting, inference, correction,
  threshold or model selection. These are earlier development fold refits,
  not evaluations of the four full-data exports.

  The observed child rating-0 vote fraction is 0.018819. Mean predictions are
  0.028220 for all-age target-plus-scalars, 0.013304 for child-only,
  0.039818 for scalars and 0.019602 for the child-fit prior. The all-age and
  scalar heads overpredict this average corpus frequency; child-only
  underpredicts it. Coarse bins matter: 93.42%, 97.70%, 90.41% and 100% of those
  respective predictions lie in [0, 0.1). The prior's small 0.000784 binned
  residual is entirely a one-bin result, not acoustic discrimination evidence.
  Some occupied all-age tail bins contain only two positions from one child.
  Empty bins, phone/fold mixtures and repeated children limit any calibration claim.
- **Short-word context sensitivity completed:**
  The [context report](multiphone-word-context-sensitivity-report.md) processes
  all 17 fixed word crops and 23 target positions across 16 consonants from five
  previously selected children. All five original recordings passed parity;
  all 454 pins, exact PCM slices/ranges, per-word/clip/global summaries and zero
  network-fetch records passed independent review. No new inference was needed
  for that audit. Crops span 0.285–0.645 seconds.

  Full-utterance versus crop mean/max probability TV is 0.108499/0.476347 for
  the all-age head and 0.055598/0.514125 for the child head; argmax changes occur
  on two and one of 23 positions. This exposes a material mismatch with native
  short-word practice. Cropping changes waveform context, alignment and
  utterance features together. Estimated emissions are not reviewed word
  boundaries, and no full-recording rating was transferred to a crop. These
  results neither isolate an encoder effect nor validate naturally spoken
  isolated words, pronunciation correctness or the smaller-shift head.

- **Fixed nonspeech boundary diagnostic completed:**
  Three predeclared two-second signals use the exact BALL/B prompt and unchanged
  raw adapter, with one extraction each and the saved features reused across
  all four final heads. Actual inference took 19.583 seconds on CPU with two
  threads. All three cases returned outputs; each had zero greedy CTC tokens.
  All four heads assigned silence their highest probability to class 2
  (.67470–.91900). Four synthetic tests passed independently. Saved-artifact
  review checked 180 input entries and 15 derived artifacts across 81 paths,
  exact regenerated PCM, all 12 distributions, feature reuse and CTC paths.
  This exposes the missing speech-presence boundary; no threshold, correctness
  label or new model was introduced. The [report](multiphone-nonspeech-report.md)
  preserves every result and its limited interpretation.

The [ordinal-head assessment](ordinal-head-assessment.md) records a considered
but deferred architecture comparison; no ordinal training occurred. A
[monochrome research figure](../../research/audio-head/outputs/multiphone-20260926/child-rating-figure-v1/child-rating-comparison.png)
reproduces the fixed report's child probability-fit/ranking tradeoff and matched
seen/unseen-word slices. Its script, exact extracted values, source digests and
runtime versions are retained beside the PNG and SVG. It adds no new metric or
model-selection rule.

A second [monochrome figure](../../research/audio-head/outputs/multiphone-20260926/followup-tradeoffs-figure-v1/followup-tradeoffs.png)
shows the completed consistency and ranking follow-ups. All 30 signed values
were independently recomputed from original arm records, with exact CSV/data
and provenance checks. It preserves overlapping-child support and contrasts
probability fit with rare-rating ranking without selecting a winner.

## Recorded computation time

The [timing audit](../../research/audio-head/outputs/multiphone-20260926/campaign-closeout-v1/cadence-campaign-compute-interval-audit.json)
at 13:57:47 UTC reads 39 major completed artifacts, with 27
study windows and 693 recorded job/replay/process intervals. Clipping explicit
start/end times to the 08:13:14 UTC goal start and merging overlaps gives
**4h35m36.806s** of study windows, or **4h32m50.894s** of the narrower recorded
job/standalone-process windows. These are alternative overlapping summaries,
not quantities to add. The MPS-labelled job union is **3h06m51.807s** and can
overlap CPU-labelled work.

The later 19.583-second nonspeech run occurred after this timing snapshot and
is recorded separately; the historical timing JSON is unchanged.

These windows include setup, verification, I/O, replay and possible device-lock
waiting; they do not measure continuously busy hardware. Several extraction
runs and an encoder pilot retain elapsed durations without absolute timestamps,
so they cannot be placed or added to these unions. No filesystem modification
times, downloads, tests, documentation or code-review time were counted as ML
process time. The campaign combines model engineering, actual training and
evaluation, review and handoff preparation. It must not be described as six
continuous hours of GPU training.

An [independent reconstruction](../../research/audio-head/outputs/multiphone-20260926/campaign-closeout-v1/cadence-compute-interval-independent-audit.json)
checked all 720 source timestamp/clipping records, 513 recorded device fields,
223 small configuration pins and all five overlap unions. Integer-microsecond
endpoint calculations agree within the declared five-microsecond serialization
tolerance. Historical observation times and `goalComplete: false` are retained;
copying those audits does not retrospectively change their scope. The
[audit index](../../research/audio-head/outputs/multiphone-20260926/campaign-closeout-v1/index.json)
preserves exact durable copies of the independent checks and their hashes.

## Campaign disposition and next steps

All declared training and diagnostic jobs have finished. Final integration
review resolved the stale implementation filename, preserved all four original
export identities, and verified 140 local links across 11 delivery documents,
33 displayed evidence hashes, 20 durable audit copies and all 12 nonspeech
probabilities in the readable table. The recorded
[final validation](../../research/audio-head/outputs/multiphone-20260926/campaign-closeout-v1/root-final-validation.json)
is a saved-file/document audit; no completed training or inference was repeated.
The actual clock is past the minimum six-hour point. Every requirement above
has a disposition, and missing external qualifications remain visible rather
than being marked achieved. No new model was selected from diagnostic outcomes.

Do not expand a search or rerun finished work merely to reach the clock target.
Missing SLP judgments, ages 2–5, verified SSD labels, real isolated-word evidence
and an untouched independent final cohort cannot be manufactured by more local
optimization. The next concrete external step is the prepared content/listening
annotation and data-rights handoff, followed by a genuinely reserved evaluation
cohort and evaluated speech-presence/abstention policy. Native physical-device routing/camera and manual VoiceOver/child
usability checks also remain outside the simulator evidence. Campaign completion
must distinguish those missing qualifications from the completed research work.

## Evidence identities checked at this snapshot

All paths below are under `research/audio-head/outputs/multiphone-20260926/`.
These hashes identify completed artifacts or immutable plans; mutable live
ledgers are deliberately not treated as final evidence. Earlier entries were
rechecked during the audit preparation; the newly completed studies received
the separate actual-artifact audits described above. This documentation update
does not repeat completed training or model forward passes.

| Artifact | SHA-256 |
| --- | --- |
| `cohort.json` | `33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805` |
| `splits.json` | `b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf` |
| `outer-release-v1.json` | `971bbc06a79847a69042b88abc750240b4b13917016ace4ee7a568807a6b0843` |
| `outer-evaluate-queue-v1.json` | `f7b5695e094d7456944e53bc1787ae997db9d8a6d6bf7edcf7330e5e869deab8` |
| `outer-comparison-v1/report.json` | `c12a0562ffec6f9783c231950a7099dee3a0b0e196cf0a2bc0c7ae810077c542` |
| `phonetic-final-plan-v1.json` | `cff6a0514e2c46cd9a0e9a3473570203b789ebada92bae06f42301c1217c9146` |
| `phonetic-final-queue-v1.json` | `8b9a2c51e0e9b47c7ceccd904a7257b1901b9c7ea70f0ae9d048ee23354aa280` |
| `phonetic-final-portable-verification-v1.json` | `2f9bdb932be93fd87ca9f4869eed431bf9caab409a83210b31acae963e93575b` |
| `raw-research-verification-v1/verification.json` | `83852b275cd451e72e2e7a94fbc8d00ec1ef240ef07079a8d2586890205f22a3` |
| `consistency-features-v1/plan.json` | `e4995480d1f609a741e1cd82e9438c70ee8fb3b838fff852113b1f316fb1f8d9` |
| `consistency-features-v1/features/features.json` | `db29e07aaccfff4a1b2400e1c3c0670cc19e99b47c71bb8ea9368d72baa16a52` |
| `consistency-study-v1/queue-ledger.json` | `727e071a5276b7f0c6ab045ce4d92c349f95474ac48f742a387ba6c12b546000` |
| `consistency-comparison-v1/report.json` | `a9528724ea614dda419802e3892516a51004976f9639e272e55f0266383d7c0e` |
| `consistency-features-extension-v1/plan.json` | `75037ff28d52a351e87ab6d37338a1ff75d99aaef8d7e85fd5bb56e8f1351ea0` |
| `child-rating-figure-v1/provenance.json` | `0e29a536bd5c7b4a522e747ba21076e2926e4215ad49b7d35c6655aa4374b262` |
| `phonetic-adaptation-queue-v1.json` | `6951091ad00a9d620245fda674c83cba481196d6833fb78764af05966fe3bb33` |
| `phonetic-adaptation-comparison-v1.json` | `609400189cb9e34548a3ab24decc2bfe44361c5c06a692332a740f7a2ae4c894` |
| `consistency-features-extension-v1/features/features.json` | `70143aa6e39bed17d498046fe676a8888d4339e9fb4bc70bab8a0cd477c9b426` |
| `consistency-features-extension-v1/run-ledger.json` | `d72fec4dc9f39887a86f81abe73a3984476308fff414b1ef9db4bec501ad74cc` |
| `consistency-features-extension-v1/post-run-inspection.json` | `4af0a6cffc95652916a6597d9072320171b1ea7bfa673fbb57b94edb500340bb` |
| `consistency-replication-v1/queue-ledger.json` | `3ec22f795964256954ef7f1e8ebc5c287b7a6707d32653cf73a792bf5a0fb1ab` |
| `consistency-replication-comparison-v1/report.json` | `a39492fe46a3a7294057f29a2bd5ad720bf4b8a8c5b548139378e48899298bcd` |
| `ranking-preflight-v1.json` | `cdc6e8f18d10a7d8fbdf75145d721af57f07ae7b9bc387be490ca35988c4ac18` |
| `ranking-study-v1/queue-ledger.json` | `a15ef495bfab20eab545304388cc84e5ab8d644a8cca3f4f54d46effab5779c2` |
| `ranking-comparison-v1/report.json` | `ab6fdb53b3641c62d364bc8a97f0d31f84330db61ee96c820736648cd37e3c55` |
| `rating-reliability-v1/report.json` | `26a918151612ccfd7436dc4d00296da25cb5418d242ae3094439b077dc476445` |
| `word-context-sensitivity-v1/plan.json` | `7c00c70ca2de98624d7e0957ff821059c8f9780feee69cc18b1434b237b50736` |
| `word-context-sensitivity-v1/run-ledger.json` | `ae358074efbab82de55c17a782ab12827e81f44e785a15546c9b4a1eb4b150ac` |
| `word-context-sensitivity-v1/diagnostic/report.json` | `6b3df8d70231cd2ee23f3c79dfb645524d5ad94ff4167f8e8a446de4a21b219e` |
| `practice-coverage-v1/final/report.json` | `5dbbcf51b716ec388acfa55815cb824e9e67362ca67ac52b2fe00712ec40b609` |
| `followup-tradeoffs-figure-v1/provenance.json` | `00d277ccc611df333b9c42390dab0b628d3c3fd65d61b0a5553c841c1e2086b2` |
| `nonspeech-boundary-v1/plan.json` | `7f8bd3a7175b1e5a43dbd802637ae7f9ddde8064ca49f7e57eab8589cb625470` |
| `nonspeech-boundary-v1/results/report.json` | `0af3245208602f10291c2759723ec9a9526a371399f978912eef422f77ef82cf` |

For this audit, saved native results were read with `xcresulttool`, not rerun:
`/tmp/cadence-native-delivery.xcresult` reports 86 passed / 0 failed, and
`/tmp/cadence-monochrome-ui-3.xcresult` reports 6 passed / 0 failed. The latter
is the later visual revision; `/tmp/cadence-monochrome-dark.xcresult` reports
one passed / zero failed. The current installed monochrome home was inspected
at 13:24 UTC in `/tmp/cadence-final-audit-native-current.png`. The current app
entry and direct-session source keep accounts, assignments, uploads and model
scoring out of the default practice flow. The optional Debug camera lab shows
local ARKit expression measurements on supported phones, not Face ID enrollment
data or pronunciation judgments. Physical-device routing/camera behavior and a
manual VoiceOver/child usability study remain outside this evidence.
