# MDD v1 local research baseline

Prompt-blind broad-phone CTC and canonical-position MDD. No app integration or
learner feedback. See `../../../work/mdd-v1/protocol.md` and the result report for
source permissions, score-derived supervision, exclusions and limits.

Run from `research/audio-head` with the existing `.venv`:

```sh
.venv/bin/python -B -W error -m unittest mdd_v1.test_manifest mdd_v1.test_runtime test_l2_arctic_annotations
HF_HUB_OFFLINE=1 .venv/bin/python -B -m mdd_v1.manifest
HF_HUB_OFFLINE=1 .venv/bin/python -B -m mdd_v1.baseline
HF_HUB_OFFLINE=1 .venv/bin/python -B -m mdd_v1.train_ctc A
HF_HUB_OFFLINE=1 .venv/bin/python -B -m mdd_v1.train_ctc B
HF_HUB_OFFLINE=1 .venv/bin/python -B -m mdd_v1.train_ctc select
.venv/bin/python -B -m mdd_v1.report
```

These commands describe the completed declaration, not authorization to repeat
an evaluation. `select` refuses to overwrite completed selected L2 artifacts.
Use the saved predictions for metric/report reanalysis. A new scientific run
needs a new declaration/output destination rather than deleting old evidence.
The current output destination is `outputs/mdd_v1/` and the four-speaker L2
allowlist is fixed in `manifest.py`; do not widen it to reserved speakers.

`manifest.py` preserves raw and normalized labels; `inventory.py` owns explicit
mapping; `evaluate.py` performs deterministic edit alignment and MDD;
`runtime.py` provides offline loading and audio preprocessing. `baseline.py`
keeps raw espeak tokens. `train_ctc.py` caches only frozen computation, fits
fixed-budget heads/upper blocks, and selects on official SpeechOcean test-speaker
development PER. `report.py` uses saved predictions/checkpoints, with no inference.

The L2 metric denominator includes adult manually annotated speech; SpeechOcean
is scores rather than produced-phone truth. Unknown identities are never filled
in. Primary and review-added descriptive metrics are separate. Nothing here
establishes child MDD performance or the prospective feedback gates.

### All-optimal edit-alignment diagnostics

`alignment_ambiguity.analyze_alignment(reference, hypothesis)` is an additive,
model-free diagnostic for sequences of nonblank string phone tokens. Each
reference occurrence exposes all hypothesis indices/deletion and distinct phone
identities/deletion allowed by minimum-cost unit-edit alignments. Index ambiguity,
identity ambiguity and agreement (`match`, `mismatch`, `ambiguous`) are separate:
`['N', 'N']` versus `['N']` cannot localize the deletion; `['N']` versus
`['N', 'N']` has two possible indices but the same matching identity.

These choices are marginals and cannot be freely combined into one alignment.
They do not measure acoustic confidence, phone timing, intended pronunciation or
clinical correctness. Insertion-location ambiguity is outside this per-reference
API. Results are immutable; empty inputs work; grids above 250,000 cells fail
before distance-grid allocation. Existing `align`, `anchored`, features, metrics
and model behavior remain unchanged for historical replay.

```sh
.venv/bin/python -B -W error -m unittest mdd_v1.test_alignment_ambiguity
```

Ten generated tests include independent exhaustive enumeration of all edit paths
for 225 sequence pairs. The [saved TRAIN audit and separate constrained-scorer
tie repair](../../../docs/model/model-scoring-ambiguity-verification-20261025.md)
record the observed ambiguity without promoting a learner feedback rule.

## Stage C: child adaptation and prompt-aware detection

JIBO Kids (CC BY 4.0) uses manually transcribed produced phones, ages 4–7,
with no clinical/error labels. See `../../../work/mdd-v1/stage-c-protocol.md`.
`jibo.py` freezes 87/11/11 child IDs across sessions before fitting and excludes
unknown symbols rather than guessing. `inventory.py` adds the explicit
`arpabet39-jibo-ipa-v2` tokenizer without changing the round-2 head IDs.

Run these sequentially from this directory (all corpus/model operations offline):

```sh
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m unittest mdd_v1.test_manifest mdd_v1.test_runtime mdd_v1.test_stage_c test_l2_arctic_annotations
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.jibo
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_c
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_c_eval recognition
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_c_eval posteriors
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_c_eval detect
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_c_report
```

One declared top-four-block variant starts from selected A and mixes each JIBO
train utterance once with each of the 222 all-correct SpeechOcean train clips
per epoch; selection uses JIBO dev only. The 45-minute loop budget excludes
one-time frozen-feature extraction and final evaluation, matching round 2.
Completed fit/evaluation commands refuse overwrites; the CPU GOP phase can
resume cached per-utterance features after interruption. Do not delete completed
artifacts to rerun. Reporting uses saved outputs only.

`gop.py` computes exact CTC sequence likelihood ratios for all single-position
phone substitutions and deletions, plus prompt-blind recognition disagreement.
Two-feature logistic calibration and the F1 threshold use only the frozen
SpeechOcean calibration speaker group, never L2. SpeechOcean error labels use
exact aggregate scores 0/1 and correct labels use 2; fractional scores are
excluded and counted. Child reporting includes the full released official-test cohort ages6–12
(calibration overlap explicitly disclosed) and, separately, only the disjoint
reporting-speaker subset ages6–12. Both SpeechOcean groups were consumed during round 2; they are
development evidence. Full PR and verdict-coverage curves include denominators;
coverage confidence is distance from the frozen logit threshold, and abstained
errors count as missed for end-to-end recall. No app integration or clinical
qualification is implied.

JIBO attribution: Shankar et al. (2024), JASA Express Letters 4(11), 115201,
DOI 10.1121/10.0034195; balaji1312 (2026), JIBO Kids Corpus v1.0.0,
DOI 10.5281/zenodo.19604408; DrivenData (2026), JIBO Kids Corpus Transcripts,
K-12 AI Infrastructure Program, dataset13/version12. Derived artifacts modify
phone normalization, exclude unsupported labels and crop released intervals.
Original source/license evidence remains in `outputs/jibo-kids/sources/`.

The first Stage C attempt hit MPS SDPA OOM before its first adapted dev result.
The final resource correction in `stage_c.py` uses eager attention and pads
frozen frames to 64-frame buckets,
uses a finite padding-key mask and trims to the true frame count; tests check logits and
input gradients, with additional real-MPS clip parity saved locally. Unused MPS
cache is released per update. No memory guard is disabled. Failed artifacts are
retained in `stage-c/failed-variable-shapes/`. After a host interruption, the final retry has 1,910s;
667s charged for failed/interrupted attempts plus a 120s probe reserve keep the cumulative charge
below the original 2,700s cap. Do not treat the retry as a new candidate or budget.
`python -B -W error -m mdd_v1.stage_c_verify` checks saved-result invariants,
including the cumulative budget, cohort boundaries, recognition replay, and
calibration/coverage denominators.

A masked SDPA retry also failed with a nonfinite loss before its first adapted
selection checkpoint. Its trigger was not reproduced in an 800-utterance replay;
logs remain in `failed-masked-sdpa/`. Final fitting rejects nonfinite gradient
norms before optimizer updates and retains the original cumulative budget.

The interrupted attempt had 87.3s last observed progress; its exact exit time
was unobserved, so 180s is charged conservatively. Budget evidence is in
`stage-c/budget-ledger.json`; this timing uncertainty is disclosed in the report.

## Stage D: supervised full-vector phone error detection

See `../../../work/mdd-v1/stage-d-protocol.md` for the pre-fit declaration and
`stage-d-result.md` for results/limits. All 2,500 official SpeechOcean train
utterances supply exact-score phone labels (0/1 error, 2 correct; fractional
averages excluded exactly as Stage C). Frozen C posteriors feed 168 features:
full CTC substitution/deletion vector, forced emission-span statistics, canonical
identity/neighbours/positions and prompt-blind disagreement. Features never use
expert scores or reference-produced identities/timings. Independent canonical
word grouping is absent in saved L2 records and explicitly marked missing.

Additional dependencies are pinned in `mdd_v1/requirements-stage-d.txt`. Run from
`research/audio-head`, offline for all corpus/model operations:

```sh
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m unittest mdd_v1.test_stage_d
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_d prepare
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_d fit
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_d evaluate
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_d_verify
HF_HUB_OFFLINE=1 .venv/bin/python -B -W error -m mdd_v1.stage_d_report
```

These describe the declared run, not authorization to repeat evaluation. Completed
preparation/selection/reporting refuse overwrite; use saved predictions for
reanalysis. Fit receipts preserve each model and its budget charge before
calibration scoring; unaccounted interrupted/failed fits refuse automatic retry.
Three fixed candidates (logistic, HistGradientBoosting, 20-epoch small MLP) fit
only train. The same Stage C calibration speakers select by AP, then fit positive
Platt scaling and the F1 threshold. Only the selected model scores the same
reporting children and four exposed adult L2 pilot speakers, once. No L2 tuning.
The combined 30-minute candidate fit cap excludes feature extraction and final
reporting. Reports export full PR/coverage curves, ECE, target-phone metrics and
2,000 speaker-cluster bootstrap intervals. This remains score-proxy development
evidence, with previously exposed reporting cohorts, not clinical qualification.
