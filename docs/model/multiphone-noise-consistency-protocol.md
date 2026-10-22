# Bounded recording-consistency experiment

Declared September 26, 2026, after the five-child capture diagnostic and before
any fitting or outcomes from this follow-up. This is a separate exploratory
study. It does not alter the frozen 19-pipeline speaker comparison, select an
outer winner, or supply new human pronunciation labels.

## Question and fixed scope

Can a frozen-feature rating head become less sensitive to one controlled
recording perturbation without harming its fit to clean human ratings? The
earlier capture check found substantial shifts for some targets under additive
noise. It cannot establish that all such shifts are undesirable: noise can
mask audible evidence. This experiment tests a regularization hypothesis,
not a validated pronunciation-invariance rule.

Use fold zero only. The union of inner-fit and inner-validation rows contains
11,811 targets in 1,996 author-training clips. All-age fitting has 9,410 targets
in 1,597 clips. Child-only fitting is the corresponding ages 6–12 subset:
4,073 targets in 758 clips. Clean inner validation has 2,401 targets in 399
clips; its child slice has 545 targets in 99 clips from five speakers. Speakers,
clips and audio hashes remain disjoint across fit and validation. No outer
holdout or author-test waveform is processed by this follow-up.

Create exactly one 20 dB white-noise view per clip, using the prior capture
diagnostic's source-hash-seeded Gaussian draw, whole-waveform SNR, common
signal/noise attenuation if necessary, and PCM16 quantization. Preserve source
audio. No trimming, resampling, synthetic articulation error or new auditory
judgment is introduced. Recompute the complete q8 CTC alignment, all 13 scalar
values and the full-precision 1,024-dimensional phonetic target vector from
the noisy waveform. Only the feature definitions are unchanged; scalar values
and estimated windows are not copied from clean audio.

Before full extraction, original first and longest fitting clips in each
population must reproduce their cached posterior arrays, scalars and windows
exactly, and phonetic vectors within absolute 2e-6. Duplicated preflight clips
may be computed once. A failure stops the run for diagnosis; tolerances are
not loosened after observing results. Extraction uses CPU with two threads,
pinned local model bytes and no network fetches. Complete coverage and hashes
are verified before any trainer can consume the noisy features.

## Six fixed continuation arms

For each fitting population, initialize the same original fold-zero
target-plus-scalar head at learning rate 0.0003, selected epoch five. Retain
its clean fit-only normalization, phone inventory and architecture. Compare
three fixed consistency coefficients: **0, 0.1 and 1**. Retain all six arms;
there is no coefficient selection or later expansion based on these outcomes.

Each arm has a fresh seed-7 optimizer and identical target-row shuffling,
AdamW learning rate 3e-5, weight decay 0.01, batch size 64, gradient norm limit
5, at most six epochs and patience two. The original checkpoint is eligible
as epoch zero. Both the supervised clean branch and noisy student branch run
with dropout disabled, while student gradients remain enabled. Coefficient
zero is the matched dropout-free continuation control. This is not a claim
that any difference from the original head is uniquely caused by noise.

The teacher is a **fixed copy of the original warm head in evaluation mode**.
Cache its predictions on clean fitting rows only, with no gradients. Do not
update the teacher, average it with the student, or use validation teacher
outputs in optimization. The loss per fitting row is:

`NLL(clean human rater distribution, student(clean))`
`+ coefficient * KL(fixed teacher(clean) || student(noisy))`.

Average each term over the same rows; do not class-weight, sharpen, threshold,
sample from, or renormalize human labels. Teacher probabilities are model
references for distillation, not qualified annotations of noisy speech. The
fixed teacher may preserve its own mistakes. Coefficient zero performs only
the clean objective and does not use noisy inputs for its parameter updates.

Select an epoch solely by clean inner-validation macro-phone NLL: all ages for
all-age fitting, ages 6–12 for child-only fitting. Require improvement greater
than 1e-7; ties retain the earlier checkpoint. Evaluate no transformed metric
for early stopping, epoch choice or coefficient choice. Noisy validation
inference occurs only after selecting the saved checkpoint.

## Reporting and verification

Report all six arms plus their original epoch-zero models. On original clean
validation audio, retain NLL, per-rater Brier and within-phone rare-rating
ranking with denominators and missing-class support. On paired noisy audio,
report probability total variation, expected-rating drift, confidence and
entropy changes for all ages and children, plus target/clip summaries. Report
shifts from each arm's own clean predictions and drift from the original
teacher's clean predictions. Reduced sensitivity alone can reflect an
uninformative or overconfident model; show these measurements together.

No noisy NLL, Brier, pronunciation accuracy or calibration is computed against
the original human ratings. No inference about physical microphone/room
robustness or clinical safety follows. One fixed noise realization and five
child validation speakers do not support a broad robustness claim or a new
independent confidence interval. These inner speakers were already used for
model selection. Author-test remains closed.

Bind sources, feature artifacts, recipes, teacher checkpoints, normalization,
fit/validation rows, optimizer state, histories and selected predictions.
Separate saved-checkpoint replay must exactly reproduce clean and noisy
predictions before an arm is reported complete. Preserve failed/partial runs;
do not silently restart or overwrite them. Actual numerical preflight,
extraction, fitting and replay status belongs in the experiment log.
