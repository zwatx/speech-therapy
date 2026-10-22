# Cadence audio-model research

This directory contains local training and evaluation, separate from the native
practice app. The September 26 study predicts a five-rater distribution
over scores 0/1/2 at a requested canonical consonant position. It does not infer
a verified produced-phone sequence or authorize learner correctness feedback.

Current target: **ages 6–12**. The new
[full-fit expanded child mixture](../../docs/model/ages-6-12-model.md) provides a
portable feature-only loader, explicit age validation and verified prediction
parity. Its full-fit weights have no independent performance score. The older
bundles and cross-fit studies below remain distinct historical artifacts.

Start with the [artifact handoff](../../docs/model/research-artifact-handoff.md),
[current decision](../../docs/model/current-multiphone-decision.md),
[experiment log](../../docs/model/model-training-run-log.md), and
[data/training plan](../../docs/model/multiphone-training-plan.md).
The [research model card](../../docs/model/multiphone-research-model-card.md)
documents the completed four-bundle release and its exact scope.
The [nonspeech check](../../docs/model/multiphone-nonspeech-report.md) records
high corpus-rating confidence on silence; raw output does not verify speech.
The [comparison figure](outputs/multiphone-20260926/child-rating-figure-v1/child-rating-comparison.png)
and [follow-up tradeoffs](outputs/multiphone-20260926/followup-tradeoffs-figure-v1/followup-tradeoffs.png)
present saved results; the [app-word coverage handoff](../../docs/model/practice-model-coverage.md)
maps the 72 native prompts to retained corpus evidence.
The older `/R/` study is documented [separately](../../docs/model/local-training.md).

Completed experiment: [fixed seed replication](../../docs/model/multiphone-lexical-seed-replication-report.md)
of both expanded fitting objectives at seeds 17/29/43. All 600 initial fits,
600 fresh refits and 600 held-out predictions are complete. Independent saved-state,
exact prediction replay, all 4,464 metric summaries, aggregate reconstruction and
exact offline report verification passed. None of the 18 primary comparisons
passes; retain the unweighted expanded objective as the research reference and
the weighted results as a documented tradeoff. No seed or model was promoted.

## Local environment

The measured campaign uses Python 3.13.14, PyTorch 2.8.0, NumPy 2.2.6 and
Transformers 4.57.6 in `.venv`. Direct dependencies are in `requirements.txt`;
the resolved environment is in `requirements.lock.txt`. CPU heads use two
threads. Encoder adaptation uses the Mac's MPS device, with one shared device
lock and serial jobs. No paid compute or external experiment logging is used.

All commands below run from this directory. The ignored local output root is
`outputs/multiphone-20260926/`. Source, data, feature, recipe and checkpoint
hashes bind these completed runs. They are an exact local study, not a portable
download-and-train SDK. Preserve completed sources and artifacts; a changed
experiment needs its own declaration and fresh destination. Existing partial
queues require explicit inspection and recovery, not an automatic restart.

## What was fitted

| Study | Main implementation | Evidence |
| --- | --- | --- |
| Global wav2vec2/WavLM mean and attention heads | `multiphone_train.py` | 120 frozen-head trials; three initializations, five speaker folds, two learning rates |
| Word, age and capture controls | `multiphone_controls.py` | 45 inner candidates, with fit-only vocabularies and statistics |
| Estimated local CTC scalar features | `multiphone_local_features.py`, `multiphone_local_train.py`, `multiphone_local_ablation.py` | 20 full-scalar trials and 60 ablations; exact checkpoint replay |
| Local WavLM heads | `multiphone_local_head.py` | 40 embedding/embedding-plus-scalar trials across both fitting populations |
| Local versus global phonetic heads | `multiphone_phonetic_features.py`, `multiphone_phonetic_head.py` | 80 trials, all exactly replayed; pinned 1,024-dimensional encoder features |
| Rare-rating objective | `multiphone_phonetic_balanced.py` | Separate 20-trial inner study; actual-fit class weights and explicit probability correction |
| Full author-training research heads | `multiphone_phonetic_final.py`, `multiphone_research_inference.py` | Four fixed objective/population variants; exact replay from copied bundles without training-archive access |
| Standalone raw-WAV research inference | `multiphone_research_audio.py`, `multiphone_research_ctc.ts` | Four real-audio checks across all final variants; exact CTC/scalar/window/embedding/probability parity |
| Recording-consistency follow-up | `multiphone_consistency_features.py`, `multiphone_consistency_train.py`, `multiphone_consistency_replication.py` | All 30 fixed arms complete with exact replay across five inner folds; descriptive comparison retains every coefficient |
| Child ranking objective | `multiphone_ranking_train.py`, `multiphone_ranking_report.py` | Five fixed auxiliary fits and retained matched controls; actual update-equivalence preflight and exact replay |
| Corpus rating reliability | `multiphone_rating_reliability.py` | Four saved development prediction sets, fixed vote-event bins and per-phone/fold support; no calibration correction or new inference |
| Word-context sensitivity | `multiphone_word_context_sensitivity.py` | 17 fixed estimated word crops, 23 positions across 16 consonants; exact PCM and original parity, no transferred labels |
| Nonspeech input boundary | `multiphone_nonspeech.py` | Three fixed silence/noise/tone inputs, unchanged adapter and four final heads; no speech-presence or correctness claim |
| Child target evidence | `multiphone_target_evidence.py` | Distinct child/clip/position support for all 24 IDs and retained per-phone development metrics; no new inference |
| Raw encoder continuation | `multiphone_adapt.py`, `multiphone_phonetic_adapt.py` | Completed cold/warm studies and six-arm phonetic comparison, saved update state and exact checkpoint replay; negative results retained |
| Fixed development speaker comparison | `multiphone_outer_release.py`, `multiphone_outer_evaluate_queue.py`, `multiphone_outer_report.py` | 95 refits, 85 evaluation jobs, 19 pipelines plus a child-fit prior |

Recipes live in `experiments/`. The plan, queue ledger, individual `config.json`,
checkpoints, history, predictions and replay proof together establish a run.
A model filename or a `complete` flag alone is insufficient evidence.

## Read the completed comparison

The [comparison table](outputs/multiphone-20260926/outer-comparison-v1/report.md)
is backed by `report.json`, which retains all phone/age support, fold results,
paired intervals and fit-vocabulary slices. Its frozen input bindings are:

- `outer-release-v1.json`: `971bbc06a79847a69042b88abc750240b4b13917016ace4ee7a568807a6b0843`
- `outer-evaluate-queue-v1.json`: `f7b5695e094d7456944e53bc1787ae997db9d8a6d6bf7edcf7330e5e869deab8`
- `outer-comparison-v1/report.json`: `c12a0562ffec6f9783c231950a7099dee3a0b0e196cf0a2bc0c7ae810077c542`

The [protocol](../../docs/model/multiphone-outer-evaluation-protocol.md) was fixed
before these predictions. Each fitted model holds out its evaluation speakers,
but architecture choices used overlapping inner outcomes: this is development
cross-fitting, not pristine nested or independent final validation. Author-test
was not opened by this campaign; historical `/R/` use prevents calling that
public partition entirely untouched.

The 2,000 paired bootstrap draws resample speakers within fold and age strata,
conditional on the frozen models. Child ranking intervals were withheld because
too many draws lost required rare-event support. Do not read AUROC as the
percentage of correctly pronounced sounds. The combined model's overall gain
also reverses on the descriptive unfamiliar-target-word child slice; consult
the decision document before quoting a headline result.

To independently rebuild the report from the saved probabilities into a fresh
directory, without training or new acoustic inference:

```sh
.venv/bin/python multiphone_outer_report.py \
  --release outputs/multiphone-20260926/outer-release-v1.json \
  --release-sha256 971bbc06a79847a69042b88abc750240b4b13917016ace4ee7a568807a6b0843 \
  --ledger outputs/multiphone-20260926/outer-evaluate-queue-v1.json \
  --ledger-sha256 f7b5695e094d7456944e53bc1787ae997db9d8a6d6bf7edcf7330e5e869deab8 \
  --output outputs/multiphone-20260926/outer-comparison-replay
```

For a single completed frozen phonetic head, exact cached-feature replay is:

```sh
.venv/bin/python multiphone_phonetic_head.py replay \
  --output outputs/multiphone-20260926/phonetic-head-target-scalars-all-age-f0-s7-lr0003
```

This checks saved predictions, normalization, selection, artifact hashes and
sources. It is not performance on newly recorded speech. Raw MPS replay must
also respect the shared device lock; do not launch a second live GPU job.

## Use a completed research head

The four bundles in `outputs/multiphone-20260926/phonetic-final/` are complete.
Their settings were selected from inner results only, then freshly fitted on
all eligible author-training rows. The full-data fits have no independent
performance score. All-age fits use 14,837 targets from 125 speakers ages 6–37;
child fits use 5,654 targets from 52 speakers ages 6–12.

| Bundle | Learning rate / epochs | Caller-pinned manifest SHA-256 |
| --- | --- | --- |
| `unweighted-all-age` | 0.0003 / 4 | `d3c95f8d42fddb692708f7431ef4cf48a5abc4ab1be6a5e1afc4f5f705bb0be6` |
| `unweighted-child-only` | 0.0003 / 5 | `6eb0f632aca8ee01d1d2da423c5fb13d62cc6a5340be1abcfb8325dc7ba735ff` |
| `weighted-all-age` | 0.0003 / 4 | `459909d6b879208f4ef4a25a6cb77858ac1728bd4ecf077f59bcf3057163caa8` |
| `weighted-child-only` | 0.001 / 2 | `4b74d2351413d3e11a7fd82480d629826a21ae11423372134ce84c93b29727b1` |

The portable feature loader needs the seven bundle files, PyTorch, NumPy and
the pinned `multiphone_models.py` implementation. It does not open the original
training archive. `load_head(Path(bundle), expected_manifest_sha256)` returns
a predictor whose `predict(features, target_ids)` accepts raw float32
`[N,1037]` features and integer `[N]` canonical target IDs. The first 1,024
columns are the pinned phonetic target-window vector; the remaining 13 are the
ordered CTC scalars in `head.feature_columns`. The loader applies the saved
normalization and objective correction. It rejects `/ZH/`, unsupported IDs,
wrong feature dimensions, nonfinite values and changed bundle contents.

Outputs are three probabilities for subjective corpus scores 0/1/2. They do
not identify produced phones, calibrated error risk or learner correctness.
Correct array dimensions cannot prove that the caller used the right feature
extractor or supplied the right canonical prompt. This interface takes
features, not an arbitrary waveform.

The [actual portable verification](outputs/multiphone-20260926/phonetic-final-portable-verification-v1.json)
copied all four bundles outside the output archive and prohibited archive reads
in each prediction process. Every fitted row matched its saved probability
exactly, with zero forbidden read attempts. For a full provenance re-audit,
including training inputs and inner-selection artifacts, use:

```sh
.venv/bin/python multiphone_phonetic_final.py replay \
  --output outputs/multiphone-20260926/phonetic-final/unweighted-all-age \
  --manifest-sha256 d3c95f8d42fddb692708f7431ef4cf48a5abc4ab1be6a5e1afc4f5f705bb0be6
```

The [recording sensitivity report](../../docs/model/multiphone-capture-sensitivity-report.md)
documents the separate five-child, 20-waveform test using the original inner
heads. It measures prediction changes only; transformed waveforms never inherit
human labels or supply pronunciation-accuracy measurements.

## Explicit raw-WAV research inference

The September 27 [input-evidence filter](../../docs/model/multiphone-evidence-gate-report.md)
can withhold ratings from completed raw reports when PCM is constant or the
recognizer decoded no non-special phone. Use `multiphone_evidence_gate.py`
with `--report`, its caller-pinned `--sha256`, and a fresh ignored `--output`.
Consumers must read the filtered report: abstained target probabilities are
`null`; the historical raw diagnostic artifacts still contain unfiltered
ratings. Passing this research check does not verify speech, prompt match or
pronunciation. All 2,495 corpus recordings were retained; the three known
generated nonspeech cases were withheld. See the report for scope and tests.

The optional [combined speech-detector filter](../../docs/model/multiphone-vad-report.md)
also requires a speech segment from the fixed, pinned Silero model:

```sh
.venv/bin/python multiphone_vad_filter.py \
  --report <completed-raw-report.json> --sha256 <raw-report-sha256> \
  --output <fresh-directory-under-outputs>
```

Consume `finalreport.json`, whose target probabilities are `null` on either
rejection. Its intermediate `phone-evidence.json` may still contain scores.
The fixed check retained the full corpus and withheld all twelve known
environmental clips. The [short-word check](../../docs/model/multiphone-vad-crop-report.md)
retained only 12/17 estimated word crops. Keep it an explicit research option;
it is unsuitable as the default for short practice words. Whole-recording
retention also does not validate target-level speech presence.

The explicit [100 ms research option](../../docs/model/multiphone-short-vad-report.md)
uses `multiphone_short_vad_filter.py` with the same three arguments. It
resegments the same VAD probabilities once and still requires phone evidence.
It retained all 17 observed crops; both combined policies admitted one of 24
fresh environmental clips. A real BE-crop check recovered the exact original
score vector when 250 ms rejected it. This is development evidence, not
validation on naturally spoken practice words. Read only its `finalreport.json`;
raw and intermediate files may contain scores subsequently withheld.

`multiphone_research_audio.py` connects an explicit WAV and canonical prompt to
the portable head. It accepts only mono 16 kHz PCM16, 0.1–30 seconds, and never
resamples, trims or modifies the original file. The caller supplies each word's
canonical ARPAbet phones and the target's word/phone positions. Requested
consonants must be supported and occur exactly once in the entire canonical
sequence. There is no dictionary lookup, inferred pronunciation, correctness
threshold or app integration.

The separate CPU2 worker runs the pinned q8 phoneme recognizer offline. The
adapter recomputes all 13 scalars, forced canonical windows and the official
1,024-dimensional phonetic vectors, then applies the selected research bundle.
Its fresh output directory contains `features.npy`, CTC artifacts and a report
with corpus-rating probabilities, separate recording measurements, input/source
hashes and timings. Failed runs retain their `.partial` directory for inspection.

Four [real-audio verification cases](outputs/multiphone-20260926/raw-research-verification-v1/verification.json)
cover all four bundles and three original fitting clips of 2.580, 10.717 and
20.408 seconds. CTC arrays, scalars, windows, phonetic vectors and final
probabilities match the existing cache exactly in every case. No test audio or
new performance labels were used. Observed one-shot CPU wall times were
5.95–9.25 seconds, including startup and provenance checks; this is not a
mobile latency guarantee. Nine Python and four Node tests plus independent
source review cover the adapter's numerical and failure paths.

This concrete command repeats one verified corpus case into a new directory:

```sh
.venv/bin/python multiphone_research_audio.py \
  --wav outputs/speechocean762-audio-v1/speechocean762/WAVE/SPEAKER0001/000010011.WAV \
  --wav-sha256 b9486ce67a0310dd6677f6bce98b076b213e1cefdf00d5786827c1f8af141809 \
  --prompt outputs/multiphone-20260926/raw-research-verification-v1/prompt-0.json \
  --prompt-sha256 cb9780f403288ef4e8a2f85972752ce8e5f2223403a93d383a707b842985f9d8 \
  --bundle outputs/multiphone-20260926/phonetic-final/unweighted-all-age \
  --manifest-sha256 d3c95f8d42fddb692708f7431ef4cf48a5abc4ab1be6a5e1afc4f5f705bb0be6 \
  --phonetic-snapshot outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4 \
  --contract-sha256 c077e68e37fa68da36a44194094e5c07c40e1866148834c68b6fbd24a5da9782 \
  --output outputs/multiphone-20260926/raw-research-example
```

For another recording, provide its actual content hash and an explicit prompt
matching the [contract schema](experiments/multiphone-research-audio-v1.json).
The schema's example describes the intended word, not a verified transcription
of what was spoken. Generic caller audio has unspecified data provenance;
the adapter does not infer a dataset partition from a filename.

For repeated consonants, use the separate schema-2
[`position_inference.audio` interface](../../docs/model/multiphone-position-audio-report.md).
It accepts distinct word/phone positions for the same sound, preserves caller
target order, and retains the existing feature recipe and four bundles. Seven
real child recordings covering 66 positions and all 23 consonants reproduce
the expanded feature export exactly, including reversed target orders. The
linked guide includes a complete command, prompt example and offline verifier.
Schema 1 remains unchanged. This verifies extraction and identity, not new
pronunciation accuracy or speech-presence rejection.

Apply the existing `multiphone_short_vad_filter.py` to the schema-2 raw report
when the fixed exploratory input filter is wanted. The
[thirteen-case integration check](../../docs/model/multiphone-position-filter-report.md)
verified all occurrence identities and exact masking/restoration without
runtime changes. All seven speech cases retained their 66 positions; silence,
noise, tone and helicopter each had all three requested vectors withheld.
The known dog recording still passed. Consume the final filter report; its
schema-1 envelope can reference a schema-2 raw source. This is a whole-recording
check and does not validate speech or correctness at each individual position.


The full [target-local overlap diagnostic](../../docs/model/multiphone-position-overlap-report.md)
now covers all 28,227 positions in 2,500 recordings. At the fixed 100 ms
setting, 623 positions have no occupied-frame center inside padded VAD output,
including 524 with all five ratings equal to 2; the child counts are 313 and
277. This does not justify target-local withholding. Both actual calculation
and offline reconstruction completed with exit zero, and independent artifact
review reproduced all measurements and support tables. No model, filter rule
or learner-facing behavior changed.


The completed [context breakdown](../../docs/model/multiphone-position-context-report.md)
locates 432 of the 623 zero-center cases before the first detected segment;
397 of those are the prompt's first phone and 375 have five top ratings.
One-frame states occur in 91.3% of all positions, so that warning alone is not
a selective defect indicator. Keep every training position and close the local
VAD investigation without a new rejection threshold. A bounded probability-
calibration experiment is the next candidate, using inner speaker-separated
predictions only for fitting and retaining outer rare-rating/per-phone checks.


The [fixed temperature study](../../docs/model/multiphone-temperature-report.md) completed ten
child-targeted scalar fits after exact selected-checkpoint replays. All ten
corrections were frozen before outer evaluation. Child-only child NLL improves
.172332→.171156, but rating-0 AP falls .111119→.107377 and two fold NLL values
worsen. All-age child NLL worsens .169242→.170879. Both declared consistency
screens fail; no bundle or learner policy changes. Sixteen tests, numerical
reference checks and offline reconstruction pass. The subsequent
[same-head control](../../docs/model/multiphone-temperature-transfer-report.md) is now complete
and also fails both screens without fitting another temperature.

## Recording-consistency continuation

The [fixed protocol](../../docs/model/multiphone-noise-consistency-protocol.md)
uses one deterministic 20 dB white-noise view of each fold-zero inner fitting
and validation clip. Completed extraction covers 1,996 clips and 11,811 target
rows. Three original fitting clips reproduce the existing feature cache exactly;
the noisy pass has no human ratings. The complete manifest is
`outputs/multiphone-20260926/consistency-features-v1/features/features.json`,
SHA-256 `db29e07aaccfff4a1b2400e1c3c0670cc19e99b47c71bb8ea9368d72baa16a52`.

The completed six-arm queue retains coefficients 0, 0.1 and 1 for both fitting
populations. Each head starts from its original selected checkpoint and uses
clean human supervision plus a fixed clean-teacher/noisy-student consistency
term. Coefficient zero is a matched continuation control. Clean inner loss
alone selects an epoch, including the original epoch-zero model. A separate
process must replay both clean and noisy predictions exactly before an arm is
complete. Queue status is recorded in
`outputs/multiphone-20260926/consistency-study-v1/queue-ledger.json`; the fixed
queue-plan SHA-256 is
`a04bc0ca72eb3373b66f9dfb4c17b03635961ffd88601116e6055078a925c360`.

`multiphone_consistency_report.py` consumes the caller-pinned complete ledger
(`727e071a5276b7f0c6ab045ce4d92c349f95474ac48f742a387ba6c12b546000`).
The [completed comparison](outputs/multiphone-20260926/consistency-comparison-v1/report.md)
reports every arm against its original head
and coefficient-zero control, with clean rating fit and paired probability
movement shown separately. It selects no coefficient and computes no noisy
accuracy. The experiment has one noise condition and five child validation
speakers, so it cannot establish device robustness or clinical correctness.
Its JSON report SHA-256 is
`a9528724ea614dda419802e3892516a51004976f9639e272e55f0266383d7c0e`.
Independent review reproduced the actual metrics, selected epochs, support and
probability movement. Every child-only model still has class 2 as the highest
probability on every child target; reduced movement is not error detection.
The separate [four-fold replication](../../docs/model/multiphone-consistency-replication-protocol.md)
completed all 24 additional fixed arms and exact replays. The
[combined 30-arm comparison](outputs/multiphone-20260926/consistency-replication-comparison-v1/report.md)
retains all settings and 27 distinct children in 39 overlapping fold memberships.
Its JSON SHA-256 is `a39492fe46a3a7294057f29a2bd5ad720bf4b8a8c5b548139378e48899298bcd`.
The full noisy cache is complete, reusing all 1,996 existing clips
and extracting only 499 additional clips. Its feature-manifest SHA-256 is
`70143aa6e39bed17d498046fe676a8888d4339e9fb4bc70bab8a0cd477c9b426`.
The original study and final four research bundles remain unchanged.

## Later objective and input diagnostics

The [five-arm ranking comparison](outputs/multiphone-20260926/ranking-comparison-v1/report.md)
adds a fixed .1 pairwise loss to clean NLL and reuses the matched five ordinary-
NLL controls. The actual fitting-only equivalence preflight passed before
launch. All five fits and separate replays completed; independent review
reconstructed sampled-pair/order records and every saved comparison. The JSON
SHA-256 is `ab6fdb53b3641c62d364bc8a97f0d31f84330db61ee96c820736648cd37e3c55`.
Macro NLL improves slightly while rating-0 AUROC worsens. Every child argmax
remains class 2; no new winner or full-data export is selected.

The later [checkpoint-selection study](../../docs/model/multiphone-selection-policy-report.md)
uses new `multiphone_selection_train.py` and `multiphone_selection_audit.py`.
Ten fixed six-epoch trajectories retain all 70 checkpoints; the caller-pinned
declaration and complete twenty-selection freeze are required before outer
evaluation. Historical prefixes and selected predictions replay exactly.
Pooled child below-2 AP improves modestly under AP selection, but one fold and
other metrics trade off, failing the declared consistency rule. No promotion.
The audit retains all 23 sounds, positive-speaker support and same-fold
seen/unseen target-word slices. This is previously used development data.
Run the focused checks with
`.venv/bin/python -m unittest test_multiphone_selection_train test_multiphone_selection_audit`.

The [sequence-likelihood preflight](../../docs/model/multiphone-sequence-ctc-preflight-report.md)
adds `multiphone_sequence_ctc.py` and `multiphone_sequence_preflight.py`.
Shared canonical prefix/suffix CTC sums compute each token-slot replacement
and deletion likelihood; source probabilities remain unrenormalized. The fixed
three-fitting-clip preflight retains 7,005 comparisons against full-sequence
PyTorch CTC loss, exact repeat hashes and timings. It does not measure rating
performance or infer produced-phone truth. Run its focused tests with
`.venv/bin/python -m unittest test_multiphone_sequence_ctc test_multiphone_sequence_preflight`.

The subsequent [sequence-feature comparison](../../docs/model/multiphone-sequence-feature-report.md)
adds a complete cached feature exporter, a zero-initialized projection branch,
fixed training and a held-out auditor in the new `multiphone_sequence_*` modules.
All 14,837 rows exported with exact artifact reconstruction. Five six-epoch
fits and ten frozen candidate/control selections completed; child below-2 AP
declined slightly despite a small NLL/Brier improvement. The fixed gain rule
failed, so no existing research bundle or learner eligibility changed. All
33 sequence tests and independent source/export/result reviews passed. The
saved [result](outputs/multiphone-20260927/sequence-audit-v1/report.json) retains
all 23 phones, age/word slices and support. No new encoder inference or Colab
allocation was needed. Use fresh output directories with explicit plan hashes;
these reviewed sources and the protocol are now pinned to their artifacts.

The [corpus rating reliability diagnostic](outputs/multiphone-20260926/rating-reliability-v1/report.md)
reuses four saved development prediction sets, with fixed-decile bins for
rating 0 and below 2. Every phone/fold table and empty bin remains explicit.
Its JSON SHA-256 is `26a918151612ccfd7436dc4d00296da25cb5418d242ae3094439b077dc476445`.
It performs no inference, fitting or calibration correction. Most rare-event
predictions occupy the first broad bin; a small binned residual does not
establish acoustic discrimination or pronunciation confidence.

The [word-context report](../../docs/model/multiphone-word-context-sensitivity-report.md)
compares full recordings with 17 fixed estimated word crops covering 23 target
positions across 16 consonants. Original parity and exact PCM slicing passed;
both unchanged heads show material probability movement. This checks a real
short-word app mismatch but has no verified crop boundaries or transferred
ratings. Its JSON SHA-256 is
`6b3df8d70231cd2ee23f3c79dfb645524d5ad94ff4167f8e8a446de4a21b219e`.

## Data and next labels

The [direct pronunciation-note diagnostic](../../docs/model/multiphone-note-likelihood-report.md)
compares exact annotated substitutes with saved complete-sequence hypotheses.
`multiphone_note_likelihood.py` preserves all exclusions, context/mapping limits
and per-phone age support. Eight focused tests, exact offline reconstruction
and independent artifact audit passed. The narrow result does not measure
false positives or authorize produced-phone feedback. Its metadata audit found
13,390 additional rating positions omitted by the original single-occurrence
rule; the [all-position feasibility assessment](../../docs/model/multiphone-all-position-feasibility.md)
led to the completed expanded-data comparison below.

The [position-aware cohort](../../docs/model/multiphone-position-data-report.md)
now contains all 28,227 supported positions with original speaker splits and
archive-verified train audio. The [complete scalar export](../../docs/model/multiphone-position-geometry-report.md)
reuses 2,495 CTC arrays and adds five recordings, preserving exact original
feature parity. `multiphone_position_data.py`, `multiphone_position_geometry.py`
and `multiphone_position_scalar_export.py` are separate from the pinned legacy
pipeline. The [full phonetic export](../../docs/model/multiphone-position-phonetic-report.md)
and [twenty-fit comparison](../../docs/model/multiphone-position-training-report.md)
are complete. `multiphone_position_phonetic.py` provides declare/run/offline-verify;
`multiphone_position_train.py` provides declare/run/separate-frozen-audit. The
original vectors and ten baseline refits reproduce exactly. Both declared
consistency gates fail despite useful within-fold and word-slice signals; no
expanded model is promoted. All sources/tests/protocols and study artifacts
are pinned; use new files/output versions for further experiments.

The completed [expanded-data selection follow-up](../../docs/model/multiphone-position-selection-report.md)
adds the separate `position_selection` package. Twenty inner trials retain all
359 epoch states; ten selected outer refits complete another 33 epochs. The
child-only models improve probability losses but both regimes fail the unchanged
ranking consistency rule. Three arms per regime are retained, with all previous
control predictions and summaries exactly reproduced. `position_selection.study`
provides declare/inner/refit phases; `position_selection.audit` provides inner
diagnostics and the separately frozen outer comparison. Use the report's exact
plan/freeze bindings and fresh output directories. Neither command resumes or
overwrites a completed study. These sources and protocol are now pinned too.

Verify the complete saved feature matrices without encoder inference:

```sh
.venv/bin/python multiphone_position_phonetic.py verify \
  --plan outputs/multiphone-20260927/position-phonetic-v1/plan.json \
  --plan-sha256 b3f1884a54b1fa25777eb9578155b9923eed9ce61ff1762e05301f6211c7f29c
```

Rebuild the saved diagnostic without inference:

```sh
.venv/bin/python multiphone_note_likelihood.py verify \
  --plan outputs/multiphone-20260927/note-likelihood-v1/plan.json \
  --plan-sha256 32246fad19a4af2d623a5fb121cfe69e5815c0ca090866a6d1b5f3f9ca5ee5a2
```

The [public manual-annotation schema check](../../docs/model/l2-arctic-public-example-report.md)
adds `l2_arctic_annotations.py` and `l2_arctic_public_example.py`. The strict
long-text TextGrid reader preserves expected/perceived phones, stress, unknown
identity, deviation, deletion/insertion semantics, auxiliary tiers and word
overlaps. The one official L2-ARCTIC annotation example was acquired with its
source/terms documentation and re-parsed offline; all 12 focused tests and
independent source/artifact review passed. No audio was fetched and the sample
is excluded from fitting, evaluation and learner feedback. Its three observed
substitutions do not establish corpus-scale or child-error coverage. The fixed
source scripts/protocol are pinned; verify retained output with
`l2_arctic_public_example.py verify --report <report.json> --report-sha256 <sha256>`.

All fitting here uses the pinned public SpeechOcean762 author-training data:
2,495 clips, 125 speakers and 23 eligible consonants. `/ZH/` has six rows and
remains excluded from fitting and supported outputs. The 52 children ages 6–12
are not an established child-SSD cohort; ages 2–5 are absent. Estimated canonical
CTC windows and contextual embeddings are not verified phone boundaries.

The [child target evidence audit](outputs/multiphone-20260926/target-evidence-audit-v1/report.md)
separates rating votes, positions, clips and children for all 24 target IDs.
It also retains the scalar and combined pipelines' existing per-phone point
metrics. A trained ID is not a clinically supported error-detection capability.

The [native-prompt coverage audit](../../docs/model/practice-model-coverage.md)
matches all 72 implemented word/target pairs to retained canonical positions:
29 pairs have all-age matches and 17 have child matches. It preserves sparse,
absent and unsupported entries, uses no audio or model inference, and verifies
the unchanged Swift library against the pending SLP worksheet. Intended word
position and clinical readiness are not established by this spelling/phone join.

The [SLP handoff](../../docs/model/slp-handoff.md) includes a blinded 15-clip
multi-sound audit and draft content review. The [child-data assessment](../../docs/model/child-pronunciation-data-options.md)
separates produced-phone labels, auditory judgments, timing and usage rights.
Neither purposefully sampled review packs nor synthetic audio perturbations
create a representative accuracy cohort. No qualified labels, clinical decision
threshold or learner-facing pronunciation model has been silently enabled.
The [word-separation feasibility check](../../docs/model/word-generalization-feasibility.md)
documents why the current unfamiliar-word result needs a better evaluation
cohort: complete vocabulary purging leaves only 8–20 fitting clips, while the
fixed smaller exclusion covers only four sounds. No new training was launched
from that metadata-only assessment.

### Frozen calibration transfer control

The [same-head control](../../docs/model/multiphone-temperature-transfer-report.md)
uses `temperature_transfer/study.py` to apply the ten already frozen corrections
to the original inner checkpoints on the same outer speakers. Ten exact inner
replays and ten new outer head passes completed, with no new fitting or encoder
inference. Both consistency screens still fail; child log loss and below-2 AP
worsen for both original heads. No bundle changes follow. The report preserves
all 23 phones, actual inner-fit vocabulary slices, fixed reliability bins and
matched original-vs-refit comparisons. Source/protocol are now pinned; commands
and exact declaration/freeze/report hashes are linked from the report.

### Canonical word and speaker split feasibility

The [lexical inventory](../../docs/model/multiphone-lexical-feasibility-report.md)
uses `lexical_canonical/study.py` with the frozen `lexical_feasibility` membership
algorithm. It crosses five speaker folds with five fixed word groups and removes
whole fitting/selection/refit utterances containing held-out annotation words.
A preserved literal-transcript attempt failed before grouping because punctuation
disagreed with canonical words. The revision uses verified complete annotations.
All 23 phones remain in every fit/refit cell, but seven child selection cells
lack phones and rare-event support is sparse. Full outer coverage is preserved.
Fourteen tests, offline reconstruction and independent artifact review passed.
Both packages and protocols are pinned; the report links commands and artifacts.
No heads were trained, and no word novelty beyond downstream supervised fitting
and selection is claimed.

### Fresh heads with whole-word and speaker exclusions

The [completed comparison](../../docs/model/multiphone-lexical-head-report.md)
uses the frozen `lexical_heads` package and declared canonical partitions for
100 fresh inner fits, 100 fresh refits and 100 held-out prediction passes.
All selections are frozen before refitting, and all refits before prediction.
Combined phonetic/scalar heads worsen pooled child NLL and both rare-rating AP
endpoints against scalars in both age regimes; child-only Brier improves.
Both fixed consistency screens fail. The report preserves six model/prior
pipelines, all 23 phones, 25 cells, five speaker folds, stable unclipped NLL and
sparse/undefined support. Thirteen tests, offline reconstruction and independent
artifact review pass. All 100 inner and 100 outer outputs replay exactly.
The report links the protocol, commands and immutable declaration/freeze/result
hashes. Existing bundles and learner behavior remain unchanged.

### Fixed compact phonetic representation

The [PCA16 study](../../docs/model/multiphone-lexical-compact-report.md) uses
`lexical_compact` with fit-only compression on the same canonical lexical splits.
It completes 50 inner fits, 50 fresh refits and 50 outer passes. The candidate
uses 16 phonetic components plus 13 confidence scalars. Existing scalar/full/prior
controls remain frozen. All-age child rare-rating AP improves over scalars, but
NLL worsens slightly; child-only results are mixed. Both primary consistency
screens fail, and secondary comparisons with full phonetic features also fail
their complete screens. All 100 transforms pass independent SVD checks, 50 inner and
50 outer outputs replay exactly, and primary/auxiliary metrics reconstruct.
Eleven tests and offline verification pass. Code/protocol are pinned; commands,
hashes and complete phone/fold tradeoffs are linked in the report. No component
count sweep, bundle promotion or learner-judgment change follows.

### Fixed scalar/compact probability average

The [equal-mixture study](../../docs/model/multiphone-lexical-mixture-report.md)
uses `lexical_mixture` to average the 50 frozen scalar/compact prediction pairs
in stable log space at exactly .5/.5 weights. No model/PCA fitting, head/encoder
inference, weight search or per-phone selection occurs. All five pooled child
endpoints improve over scalars in both regimes; the fold-4 NLL regression makes
both primary consistency screens fail. Secondary compact comparisons also fail
complete screens. All 23 phones, sparse support and component lineage remain
explicit. Six tests, exact offline reconstruction and independent verification
of all 50 pairs and 62 summaries pass. This is saved-prediction
research, not an implemented ensemble inference adapter or a learner policy.

### Paired child uncertainty and contribution analysis

The [whole-child analysis](../../docs/model/multiphone-lexical-uncertainty-report.md)
uses `lexical_uncertainty` for 2,000 fixed stratified draws shared by both models
and regimes. All-age five-endpoint intervals favor the mixture; child-only AP
intervals cross zero. Fold-4 regression is concentrated in one retained child.
All 23 phone intervals, support, complete draws and additive/influence results
are saved. Eleven tests, exact offline reconstruction and an independent
671,573-check artifact audit pass. These conditional
descriptive intervals do not change the failed consistency screen or authorize
learner judgments. No training or inference occurs.

### Frozen input-support diagnostic

The [input-support report](../../docs/model/multiphone-lexical-support-report.md)
uses `lexical_support` to compare scalar z-score maxima and raw PCA residuals
with each exact refit population, globally and within phone. All 50 cells,
5,654 child positions, 52 children and 23 phones remain. Fixed >.99 empirical
rank flags do not isolate the concentrated regression; all eight high-tail
groups have favorable mean mixture-minus-scalar NLL. These are descriptive
reference ranks, not withholding rules or calibrated defect probabilities.
Seven tests, exact offline reconstruction and the independent 303,083-check
artifact audit pass. No new training, inference or learner policy is introduced.

### Supervised projection-only correction

The [projection study](../../docs/model/multiphone-lexical-projection-report.md)
uses `lexical_projection` to learn a zero-initialized 1024×16 correction through
frozen PCA16/scalar heads. All 50 inner runs and 50 fixed-count refits precede
50 outer evaluations. Epoch zero wins in nine cells per regime. All-age pooled
child endpoints improve versus PCA, but fold 2 NLL regresses; child-only results
are mixed. Both primary and all secondary consistency screens fail. Ten tests,
exact offline reconstruction, independent 200 tensor replays and all metric
checks pass. No new encoder, head-weight update, parameter sweep or learner
policy is introduced. The source/protocol and phase artifacts are immutable.

### Fixed scalar/corrected-projection mixture

The [fixed mixture report](../../docs/model/multiphone-lexical-projection-mixture-report.md)
uses `lexical_projection_mixture` to average all 50 frozen scalar/projection
pairs at .5/.5. All-age pooled child endpoints improve versus the existing
scalar/PCA mixture, but fold 2 NLL regresses; child-only results are mixed.
Both primary screens fail. The all-age secondary scalar screen passes all six
checks, including child NLL gains in every fold; it does not override the
primary failure. Ten focused tests, exact offline reconstruction and an
independent audit of 891 pins, all 50 pairs and 62 summaries pass. No head
inference, fitting, weight search or learner-policy change occurs. Sources and
protocol are frozen; saved-prediction results do not implement an ensemble
adapter or establish recording robustness.

### Label-free 20 dB recording sensitivity

The [noise comparison](../../docs/model/multiphone-lexical-noise-report.md)
uses `lexical_noise` to apply the same frozen heads and transforms to matched
clean and saved noisy features. All 50 clean cells replay exactly before noisy
inference. Both regimes have slightly lower mean child TV with the corrected
mixture, but worst child movement stays large and argmax tradeoffs remain.
No transformed ratings, supervised noisy metrics or sensitivity gate are used.
Twelve tests and independent replay of 300 component outputs/200 mixtures pass;
all complete movement and support summaries are independently verified. Sources
and protocol are immutable. No new training, encoder extraction, Colab or
learner policy change occurs.


### Expanded occurrence support with lexical exclusions

The [support inventory](../../docs/model/multiphone-lexical-expansion-report.md)
uses `lexical_expansion` to preserve all 50 original speaker/word cells while
including 28,227 occurrences from 2,500 recordings. It checks exact original
membership, vectors and scalars; includes the five extra recordings explicitly;
and retains original/added/all support in every partition. Child support grows
to 9,891 occurrences from the same 52 children. Sparse event classes and seven
selection cells with absent sounds remain. This is a data inventory, with no new
fit or model-performance claim. See the
[protocol](../../docs/model/multiphone-lexical-expansion-protocol.md) before a
separately declared training comparison.


### Expanded fitting with original selection examples

The [expanded head report](../../docs/model/multiphone-lexical-expanded-heads-report.md)
uses `lexical_expanded_heads` for 100 inner fits, 100 fresh refits and 100 outer
prediction jobs over all 28,227 positions. Original checkpoint-selection examples
and whole-utterance word/speaker exclusions stay fixed. The child-trained fixed
scalar/PCA mixture passes all six primary checks versus its original-data
counterpart on the same 5,654 original child positions. Its stronger corrected
mixture comparison still fails fold 0; all other primary screens fail. Added and
full populations are descriptive and never substituted for the matched original
comparison. Fourteen tests, independent state/prediction replay, complete independent
metric checks across 744 summaries and exact offline reconstruction pass. Source/protocol remain immutable, and
learner judgments remain disabled. No new audio/encoder extraction or Colab use.


### Fixed uncertainty for expanded fitting

The [uncertainty report](../../docs/model/multiphone-lexical-expanded-uncertainty-report.md)
uses `lexical_expanded_uncertainty` with one fixed 2,000×52 whole-child multiplicity
matrix across all eight original-population comparisons. All five child-mixture
primary pooled intervals favor improvement, and all 52 child deletions retain
favorable NLL. The corrected-mixture secondary macro interval includes zero;
all-age pooled intervals include zero; child /W/ NLL regresses. Original consistency
decisions remain unchanged. All 23 phones, null support and full replicate/influence
records remain. Fourteen tests, separate Astra source review, exact offline replay
and independent 1,240,048-check reconstruction pass. No model fitting, inference,
new data, Colab or learner policy is introduced; sources/protocol are immutable.


### Complete sound response and fitting composition

The [phone-response report](../../docs/model/multiphone-lexical-phone-response-report.md)
uses `lexical_phone_response` for all eight paired contrasts and all 23 sounds.
It reconciles class, fold, word-cell and child contributions to original-child NLL
and checks single/repeated canonical composition in every fitting/refit cell.
The child mixture’s /W/ loss increase comes from sparse rating-0/1 votes; rating-2
loss improves slightly. Repeated additions shift sound mass substantially.
These descriptions motivate an undeclared recording/sound-unit weighting hypothesis,
not a causal conclusion or exclusion rule. Twelve synthetic tests, separate Astra
source/auditor reviews, exact offline reconstruction and 2,037,852 independent
numerical checks pass. No new fit, audio, Colab or learner policy change. All
source/tests/protocol are immutable; existing consistency failures remain.


### Recording/sound-unit weighted fitting — complete numerical result

The [report](../../docs/model/multiphone-lexical-unit-weights-report.md) completes
100 inner fits, 100 fresh refits and 100 outer prediction jobs under the
[fixed protocol](../../docs/model/multiphone-lexical-unit-weights-protocol.md).
None of six primary comparisons passes against corresponding unweighted expanded
controls. The child mixture slightly worsens all five pooled endpoints and fold
1/2/3 NLL, while improving /W/ NLL by .006224. Its secondary comparison against the
older corrected mixture passes all six checks/all five fold NLLs; /W/ remains
.001680 worse against that reference. Preserve both candidates and all tradeoffs.

Fifteen synthetic tests, full state/PCA/weight audits, four actual nonuniform
training replays, 100 exact independent outer forwards, all 744 metric summaries
and all eight response decompositions pass. Exact offline reconstruction passes.
Opus 5.5 authored the state auditor and reviewed training/trajectory code. Its
later evaluation review found a missing explicit outer/metric receipt connection;
a separate joint-binding check and independent Astra source/artifact review pass. Source and
protocol stay immutable. Fixed seed replication is the next undeclared study.
No Colab allocation, new audio, learner-policy change or model promotion.
