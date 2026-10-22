# Four-fold replication of recording consistency

Declared September 26, 2026, after the completed fold-zero consistency study
and before any additional fitting or extraction for this extension. This is an
exploratory replication, not a fresh confirmatory evaluation. It preserves the
original [one-fold protocol](multiphone-noise-consistency-protocol.md), its six
models and all recorded outcomes unchanged.

## Question and reason

The completed six-arm report, SHA-256
`a9528724ea614dda419802e3892516a51004976f9639e272e55f0266383d7c0e`,
shows a conditional tradeoff. At coefficient one, the child-only model's clean
macro NLL decreases from .169948 to .167514 and mean paired noise probability
movement decreases from .031904 to .024502, but rating-0 AUROC decreases from
.719828 to .712912. Every child-only model still gives class 2 the highest
probability on every child validation target, both clean and noisy. This is
not demonstrated correct error detection or an overall winning model.

The question is whether those directions recur on the other four already
defined inner speaker splits. Replicate the existing objective and matched
control without opening another architecture, coefficient or learning-rate
search. Finishing more fits does not supply qualified production labels or
repair the missing ages 2–5 and child/SSD evaluation cohort.

## Fixed data and feature extension

Use the same author-training cohort and five speaker maps:

- Cohort SHA-256: `33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805`.
- Splits SHA-256: `b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf`.
- Clean feature binding SHA-256: `360c829d179f9c66b66c900fdcf3db2cb0897fdc5724feb642100802d3da4985`.
- Completed fold-zero noisy-feature manifest SHA-256:
  `db29e07aaccfff4a1b2400e1c3c0670cc19e99b47c71bb8ea9368d72baa16a52`.

Complete one shared **2,495-clip / 14,837-eligible-target** noisy cache. Reuse
the exact 1,996 existing clips and 11,811 rows; extract only the remaining 499
clips. Excluded ZH rows remain excluded. The transform is unchanged: one
source-hash-seeded Gaussian realization at 20 dB whole-waveform SNR, common
attenuation if required, and PCM16 quantization. Recompute the complete q8
posterior sequence, all 13 scalars, estimated target windows and 1,024-value
phonetic representation for each new noisy clip. No label is assigned to it.

The original three-fitting-clip parity proof and exact reused artifacts stay
bound to their original plan. New units bind to this extension's declared
plan. Do not rewrite old unit identities to make them look newly extracted.
Before publication, verify full unique row/clip coverage, feature dimensions,
finite values, waveform identities, canonical target metadata and exact
per-unit-to-matrix joins. Preserve the lexical model-snapshot pins and offline
CPU-two-thread runtime. Record all failures; no implicit restart or overwrite.

This full cache necessarily includes fold-zero outer waveforms because they
are fitting or inner-validation material in other folds. It is incorrect to
claim that this extension performs no inference on those waveforms. It performs
**no new outer model-performance evaluation and no author-test inference**.
Acoustic extraction is label-independent; each fitted teacher, normalization,
supervision and epoch selection must still obey its own fixed speaker split.

## Exactly 24 additional fits

Run folds **1, 2, 3 and 4**, each with **all-age** and **child-only ages 6–12**
fitting, each with coefficients **0, 0.1 and 1**. The fixed order is increasing
fold, then all-age/child-only, then increasing coefficient. Retain all 24
results, together with the six already completed fold-zero arms. Do not rerun
fold zero, drop a negative result or expand the coefficient grid.

Every arm initializes from its same-fold, same-population original clean
`phonetic-head-target-scalars-{regime}-f{fold}-s7-lr0003` checkpoint, at that
checkpoint's already selected original best epoch. This uniformly uses the
existing 0.0003 warm-head family; it does not select among original learning
rates using the replication outcomes. Freeze all eight warm checkpoints,
histories, predictions, configurations and original source bindings before
fitting. Verify their saved clean predictions and fit-only normalization.
Different folds may have different original best epochs.

Keep the original phone-conditioned feature body, feature order and fitting
moments. For each arm, create a fresh seed-7 optimizer and identical target-row
permutation sequence: AdamW learning rate 3e-5, weight decay .01, batch size
64, gradient norm limit 5, maximum six epochs and patience two. The warm
checkpoint is eligible as epoch zero. Disable student dropout while keeping
gradients enabled in both branches. Coefficient zero is the matched clean-only
continuation control and never uses noisy inputs for parameter updates.

The teacher is the unchanged warm head in evaluation mode. Cache its clean
predictions **only on that arm's fitting rows** and detach them. The loss is
the mean clean five-rater categorical NLL plus coefficient times
`KL(fixed teacher(clean) || student(noisy))`. There is no updated or averaged
teacher, class weighting, pseudo-human annotation, cross-fold fitted teacher,
global feature normalization or validation-based distillation target.

Select an epoch by clean inner-validation macro-phone NLL: all ages for
all-age fitting, ages 6–12 for child-only fitting. Improvement must exceed
1e-7; exact/near ties retain the earlier checkpoint. No noisy-validation
inference occurs before the selected checkpoint is frozen. No transformed
metric chooses an epoch, coefficient or next arm. Author-test remains closed.

## Verification and reporting

The declaration must bind sources, recipes, protocol, shared feature lineage,
all eight original warm heads, each fold's exact fit/validation/selection rows
and the completed fold-zero ledger
`727e071a5276b7f0c6ab045ce4d92c349f95474ac48f742a387ba6c12b546000`.
Separate processes must replay the saved clean, noisy, original-clean and
original-noisy probabilities exactly before an arm is considered complete.
Keep the fitted teacher, moments, optimizer state, all epoch losses, selected
and last checkpoints, predictions, source/config hashes and failures. A durable
queue records child process IDs before execution and requires fresh outputs.

Report every arm and original model in every fold, with signed differences
against the same-fold original and coefficient-zero control. Retain clean
NLL, per-rater Brier, rating-0 and below-2 within-phone AUROC/AP with missing
class support. On noisy audio retain mean/max total variation, expected-rating
drift, confidence/entropy changes, class probability averages and argmax counts.
Zero argmax changes alone must not be called successful discrimination.
Do not score noisy audio against clean human labels.

An equal-fold descriptive mean and the five individual differences may show
whether directions recur. Keep fold denominators and the deduplicated speaker,
clip and target counts visible; the inner validation sets overlap. Do not pool
them as independent participants, compute an independent-fold confidence
interval, or select a coefficient from the means. The known overall inner
child pool contains 27 distinct children across 39 fold memberships; verify
those counts from the pinned row maps before reporting. Rating rows and five
rater observations do not increase the number of children.

This is still one seed, one synthetic noise type and level, already used
development data and sparse child error ratings. Smaller movement can reflect
preserved teacher mistakes or loss of useful acoustic distinctions. Replication
does not establish clinical correctness, calibration, physical microphone
robustness, unseen-source generalization or learner-feedback eligibility. No
full-data deployment export or product decision follows automatically.
