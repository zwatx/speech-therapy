# Multiphone development cross-fit evaluation protocol

Prepared September 26, 2026, before releasing this campaign's outer predictions.
This document fixes the comparison and reporting rules. The orchestrator must
also write an immutable machine-readable release manifest containing every
selected inner setting and refit checkpoint before running the evaluation.
This protocol does not assert complete selections for every phonetic-head
family; their exact settings must come from completed, pinned inner runs.

## What the evaluation can establish

Call the result **speaker-disjoint development cross-fit comparison**. Each
prediction must come from a model whose fitting, normalization, learned
word/age control vocabulary, prior and fold-specific setting selection
excluded that speaker. The prespecified canonical target inventory and
eligibility mask are shared metadata decisions made from the whole author-
training partition; they are not fit-specific target selections. However,
architecture and feature choices already used results across overlapping
inner folds: a speaker in one fold's outer holdout can appear in another
fold's inner training or validation. This campaign therefore cannot claim
pristine nested cross-validation, an untouched validation corpus, or an
unbiased estimate after architecture selection. Speaker-disjoint predictions
remain useful for a paired development comparison if this limitation stays
attached to the results.

The target remains the distribution of five subjective source ratings at a
canonical phone position. It is not a produced-phone transcription, a
pronunciation-correctness label, or a child speech-sound-disorder assessment.
Forced CTC occupancy is an estimated pointer; 91.1% of target occupancies
contain one frame. Both local WavLM and phonetic vectors are contextual and
can contain surrounding-utterance information. No learner threshold or
clinical-use decision is part of this protocol.

## Fixed comparison, with no outer winner selection

Keep the following **19 pipelines** as separate rows, plus a child-fit prior
comparator. Every pipeline uses the same five existing speaker folds and
predicts all 14,837 eligible outer rows exactly once. Do not choose the best
architecture, age regime, seed, feature subset or ensemble from outer scores.

| Pipeline family | Fixed variants | Fit population and inner selection | Rows in comparison |
| --- | --- | --- | ---: |
| Frozen global WavLM mean | WavLM-base-plus, mean head, seed 7 | All ages; all-age macro-phone NLL | 1 |
| CTC scalar softmax | Full 13; local 11; target mean posterior only | All ages; all-age macro-phone NLL | 3 |
| Estimated local WavLM head | Embedding; embedding plus 13 scalars | Each with all-age fit/all-age selection and ages 6–12 fit/child selection | 4 |
| Frozen phonetic 1024 head | Target; target plus scalars; global; global plus scalars | Each with the same two age regimes | 8 |
| Fit-only controls | Per-phone +1 prior; word/age backoff; phone/word/age/duration/RMS softmax | All ages; fixed prior or all-age inner macro-phone NLL | 3 |

The extra child prior is per-phone observed counts plus one per class fitted
on exactly the ages 6–12 outer-fit rows. It is the matched comparator for
every child-only pipeline. The all-age prior is the matched comparator for
every all-age pipeline. A global prior cannot replace a regime-matched one.
Retain observed counts separately from pseudocounts; absent fit-phone support
uses a visibly marked uniform prior only where the declared implementation
supports it. Never hide unsupported targets from a model's score.

This is a compact factorial comparison, not 19 candidates from which to
publish one winner. Seed 7 matches the later local and phonetic studies;
the original seeds 17 and 29 remain inner sensitivity evidence. Attention,
weighted child probes, utterance-context-only scalar ablation and partial
encoder adaptation remain separate inner experiments. In particular, the
fold-0 adaptation pilots cannot become a five-fold result. Adding any family
requires a new release manifest before any outer result is read; additions
after release must be labeled subsequent exploratory work.

The fixed reference columns are matched prior and full13 all-age scalars.
Preserve the following mechanistic contrasts rather than searching all pairs:
full13 versus local11; target posterior versus prior; WavLM embedding plus
scalars versus full13; phonetic target plus scalars versus full13; and
phonetic target versus global within the same feature/age regime. Child-only
versus all-age comparisons change both fitting population and selection
criterion, so do not attribute a difference solely to age specialization.

## Selection, refitting and release gate

1. Select settings independently within each family/regime/fold using that
   fold's inner validation only. Neural runs select LR from 0.001 and 0.0003
   using the declared regime metric; exact LR ties prefer 0.0003, and epoch
   ties retain the earlier epoch according to the frozen trainer tolerance.
   Scalar models select L2 from 0.0001, 0.001, 0.01 and 0.1; exact ties prefer
   stronger L2. Word/age backoff selects smoothing from 1, 5, 20 and 100;
   exact ties prefer greater smoothing. The prior has no tuned setting.
   Do not average inner results across folds to choose a setting for a fold.
2. Verify all candidates used for each inner choice, including non-winning
   candidates. Bind config, checkpoint, saved predictions and selection;
   recompute the selection metric and replay saved heads. Record the precise
   selected LR/epoch/L2/smoothing, source and input hashes.
3. Refit fresh models on the corresponding `outerFitRows`, filtered to ages
   6–12 only for child regimes. Recompute moments, categorical vocabularies,
   capture-feature scales and priors on these actual fit rows. Use the same
   target eligibility mask. Neural refits start from the declared seed with
   fresh optimizer state and run exactly the inner-selected epoch count;
   do not rescale epochs, stop on outer loss, or warm-start the inner head.
   Precomputed frozen per-utterance features may be reused: they contain no
   cohort-fitted statistics or rating supervision from this campaign.
4. Save complete refits and verify replay/integrity before release. The
   release manifest lists every fixed pipeline/fold, exact fit/evaluation row
   IDs, selected inner artifacts, refit checkpoint, sources, recipe, cohort,
   splits, feature/index/model digests, runtime versions, seeds and metrics
   policy. Bind this protocol's digest too. The existing five full13 refits
   can be reused only when their frozen config/checkpoint pins match this
   release. No missing or failed pipeline is silently removed.
5. Only after the whole release manifest is frozen, produce one prediction
   artifact per pipeline/fold and then the complete report. Enforce expected
   row identity/order and speaker exclusion, finite probabilities summing to
   one, unchanged sources/inputs and exactly one prediction per eligible row.
   Refuse partial coverage; a technical failure may be repaired and replayed
   with an explicit superseding artifact, not a different model choice.

For transparency, the existing full13 refits all selected L2 0.01 from their
own inner folds. At this audit, all five `local-outer/fold-*-refit/frozen.json`
files declared complete with `holdoutPredictionsComputed: false`; no
`predictions.json` existed beneath `local-outer`. This observation does not
certify the state of future evaluations or other directories.

## Measures and support

Use the union of the five outer holdouts, in original cohort row order, for
the principal cross-fit table. Also publish all five fold results; their
training sets overlap, so five fold estimates are not five independent
replications. The pooled score is not the arithmetic mean of fold macro
scores. Keep inner discovery and outer development tables separate.

The primary task metric is equal-phone macro NLL of the original five-rater
distribution, using natural logarithms. Report it for all ages and ages 6–12
side by side; the child result is the product-relevant slice and cannot be
replaced by a favorable all-age score. Also report micro per-rater NLL,
per-rater multiclass Brier score, expected-rating MAE, and per-phone versions.
Brier score averages squared distance to each observed one-hot rating, not
only squared distance to the mean soft target.

Ranking is a distinct result. Use scores `p0` for rating 0 and `p0+p1` for
rating below 2, with original rater counts as positive/negative weights.
Publish within-phone AUROC and grouped-threshold average precision, their
equal-phone macros, prevalence and denominators. Pooled cross-phone ranking
is secondary because target prevalence can explain it. Keep NLL and ranking
tradeoffs visible; a better proper score does not establish better detection
of low ratings. Do not invent a binary clinical truth from these events.

Retain all 23 eligible targets for proper scores wherever evaluation rows
exist. For ranking, a phone/event needs both positive and negative rater
support; return null when undefined and list excluded phones explicitly.
For every slice/phone, include speakers, clips, target rows, class-0/1/2 rater
counts, mixed-rater rows, fit support and evaluation support. /ZH/ remains
visibly excluded by the original metadata support rule, not by performance.

Preserve these mutually exclusive age slices in addition to the all-age
summary; do not use the corpus's age-≤15 `ageBand` as a synonym for ages 6–12.

| Ages | Eligible target rows | Speakers | Clips | Rater counts 0 / 1 / 2 |
| --- | ---: | ---: | ---: | --- |
| 6–12 | 5,654 | 52 | 1,037 | 532 / 705 / 27,033 |
| 13–15 | 767 | 6 | 120 | 46 / 73 / 3,716 |
| 16–37 | 8,416 | 67 | 1,338 | 3,333 / 760 / 37,987 |

Ages 2–5 and a verified child speech-sound-disorder cohort are absent. The
13–15 slice has only six speakers and is descriptive. Report fit/holdout
target-word overlap and separate seen/unseen-target-word proper scores as
descriptive slices with support; these are not word-disjoint experiments.
Define seen words only against that prediction's fold/regime fit vocabulary.
Any metadata-only age/capture association remains a nuisance control, not an
age-specific correctness rule.

## Paired uncertainty

Use 2,000 paired speaker-cluster bootstrap replicates with seed 20260926.
Resample speakers with replacement within each outer-fold × age-slice
stratum, retaining that stratum's speaker count. Keep every selected speaker's
clips, target rows and all five ratings together. Use the identical sampled
speaker multiplicities for every model and comparator. Child strata contain
9, 10, 14, 9 and 10 speakers in folds 0–4. Never bootstrap rows, clips, rating
votes or the five fold means as independent subjects.

Report percentile 95% intervals for the fixed measures and paired model-minus-
reference differences, with valid-replicate counts. Freeze each ranking
summary's phone set from the complete evaluation slice using the support
rule above. If a resample loses required positive/negative support, mark that
summary replicate undefined rather than silently averaging a different phone
set. Withhold its interval when fewer than 95% of replicates are valid and
show that count. Use the analogous fixed-phone requirement for macro proper
scores if a bootstrap replicate has no rows for an included phone.

These are descriptive intervals conditional on the frozen pipelines and
observed corpus. They do not incorporate architecture search, overlapping
training-set dependence, training-seed uncertainty, or new-cohort shift.
Do not use significance stars, a post-hoc best-versus-rest comparison, or
these intervals to certify clinical accuracy. No bootstrap refitting or
selection is performed. Existing inner bootstrap output is not a substitute
for the paired cross-fit analysis specified here.

## Author-test and future independent evidence

Keep SpeechOcean author-test inference and scoring closed throughout this
campaign. Historical /R/ work already evaluated that partition, and the
published score metadata was audited. Unused non-/R/ audio is therefore not
a pristine independent corpus, and corpus speakers cannot be represented as
new merely because a target has not previously been scored.

A later independent evaluation needs prospectively frozen models and task,
permission to use the recordings, new speakers covering the intended ages
and relevant speech-sound disorders, dialect/context documentation, and
qualified independent labels with disagreement retained. The blinded SLP
audit pack drawn from inner-validation children is useful for interpretation
and protocol development; it is not this independent final cohort. Content
review of the 72 demo words also does not validate model decisions.

## Audited provenance

Paths below are relative to `research/audio-head/`. These artifacts are local
research outputs; raw audio, weights and participant details are not published
by this document. No inference, fitting or outer prediction was run to prepare
this protocol. The audit read source, recipe, manifests, inner summaries and
full13 refit status only.

| Artifact | SHA-256 |
| --- | --- |
| `outputs/multiphone-20260926/cohort.json` | `33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805` |
| `outputs/multiphone-20260926/splits.json` | `b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf` |
| `outputs/multiphone-20260926/ctc-local-full/features/features.json` | `d6dbcb1d4d36153af2e13577fb4e39d4c23e6cabcb511f69990b968dbde6279a` |
| `outputs/multiphone-20260926/local-head-selected-v2.json` | `3fee0ead4d5fe8a85e949b066bc6248a3b2e18cacf371d35af60dae3573b6d2f` |
| `outputs/multiphone-20260926/local-ablation-summary-v1.json` | `cf4882097c1b8594f855efd158e332b3412156443c415a4d06288aa717a9d804` |
| `outputs/multiphone-20260926/phonetic-head-binding-v1.json` | `360c829d179f9c66b66c900fdcf3db2cb0897fdc5724feb642100802d3da4985` |
| `outputs/multiphone-20260926/phonetic-features-v1/features.json` | `84f905b6afb3e735daab8a60cb9b894c04a93442d7b88a1472bebbcc653beaa4` |
| `experiments/multiphone-heads-v1.json` | `08a456a102fe2b59ef85a9b8564c246975db214edd2baf74cdc329f12fc60d1d` |
| `experiments/multiphone-local-train-v1.json` | `1d5e2c9eead77143abefb5900a7b1728a16ceea1a6daa7bb523209f09e14cc20` |
| `experiments/multiphone-local-ablation-v1.json` | `254ee3c974adbab2ae1f62e1550bd6329e177c5016bbbd0b6c4d6445d5397afa` |
| `experiments/multiphone-local-heads-v1.json` | `95a3f40da66f20beee4d563b12a790a7dc3b2a702a76d601a63ffc2d0ebb9283` |
| `experiments/multiphone-phonetic-heads-v1.json` | `771bdf7c231ff233e6306301aa18c3375f85e26bef29f92a529f1355e65428b3` |
| `experiments/multiphone-local-outer-v1.json` | `343925a58777fb912aed8054d4f9ea40a3d6cf2e6ce7ab6c90ec70d31bf37df6` |

Source semantics were checked in `multiphone_controls.py`,
`multiphone_verify.py`, `multiphone_child_train.py`,
`multiphone_local_outer.py` and `multiphone_local_head_report.py`, alongside
the recipes above. The executable release manifest must pin their actual
relevant source dependencies and the new evaluation implementation; this
document's artifact table does not replace those runtime guards.
