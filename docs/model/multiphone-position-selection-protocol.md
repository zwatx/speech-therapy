# Inner selection for complete occurrence data

The preceding fixed-epoch expansion study remains intact, including both failed
consistency gates. This follow-up asks whether applying the existing inner
selection procedure to the expanded dataset changes that result. It does not
change the encoder, features, architecture, rating objective or supported
23-consonant inventory. Author-test data remains closed; learner judgments
remain disabled. All outer outcomes are reused development evidence.

## Fixed inner comparison

Run twenty fresh expanded-data inner fits: learning rates 0.0003 and 0.001 ×
all-age and ages 6–12-only fitting × the same five speaker folds. Use the
reviewed 28,227-position feature set (1,024 phonetic values plus thirteen
scalars). Fit rows and validation rows come from the preserved inner speaker
partitions; outer speakers are excluded from fitting and selection.

Keep the original procedure: seed 7; CPU two threads; batch size 64; hidden
width 128; dropout 0.1; ordinary five-vote soft-label NLL; AdamW weight decay
0.01; gradient norm limit 5; maximum 100 epochs; patience 15 epochs. Select
by macro-phone NLL on all expanded inner validation rows for all-age training,
or their ages 6–12 subset for child-only training. Epoch zero is ineligible.
An improvement must exceed 1e-7; otherwise retain the earlier epoch. Stop after
fifteen consecutive epochs without such an improvement. Across the two LRs,
choose lowest selected loss, then lower LR, then earlier epoch for exact ties.
There are no additional learning-rate candidates or outcome-dependent extensions.

Compute normalization solely from each inner fit's rows using float64
population moments cast to float32, with standard deviations below 1e-6
replaced by one. Save every epoch's model, validation probabilities and loss,
plus complete fit/validation membership, priors and source/input bindings.
Reconstruct the stopping rule from these artifacts and replay selected models
exactly. Use fresh output directories and exclusive phase markers; retain
failure records and do not implicitly retry, overwrite or resume.

## Selection diagnostics and refits

Freeze all twenty trials and ten selected LR/epoch combinations. On each
selected expanded inner model and its historically selected original-row inner
counterpart, report common inner-validation original/all/added populations,
per-phone/age support, class-frequency versus mean predicted probability and
probability losses. Bind the exact checkpoints and retain undefined/empty
cells. No temperature, bias correction or calibrated model is fitted here.
These are selection-set diagnostics with overlapping validation speakers
across folds; they are not unbiased calibration estimates, independent
observations, or a causal explanation for the previous pooled ranking reversal.
Do not pool duplicate inner-validation rows into a purported external test.

Refit ten expanded models from fresh seed-7 initialization on their full outer
fit speaker sets using only the frozen inner-selected LR and epoch count.
Recompute normalization and priors separately from each outer fitting set.
When a selected setting equals the preceding fixed-epoch expanded control,
require exact historical normalization, epoch losses and model tensor equality.
Freeze all ten new refits before producing any outer predictions.

## Complete held-out development report

Compare three arms for each age regime: the original-row control, the
expanded-row fixed-setting control, and the newly inner-selected expanded
model. Reuse the twenty pinned preceding control checkpoints. All arms use
identical outer row order, original/all/added evaluation populations and the
same original-row outer-fit target-word vocabulary for common word slices.
Retain each arm's actual vocabulary mask, its own fit-only prior and exact
checkpoint replay. Every pipeline must predict each of 28,227 positions once
across five held-out speaker folds. Report all ages, ages 6–12 and ages 13-plus,
all 23 phone support cells, NLL/Brier, rating-0/below-2 AP/AUROC, word slices,
confidence summaries, individual folds and pooled results.

The primary research-lead rule is unchanged from the previous declared
comparison and is applied separately to each age regime: versus original-row
fitting, for both original-position and all-position child populations, pooled
below-2 macro-phone AP must improve by more than 1e-7; no fold may lose more
than 1e-7 in that metric; and pooled rating-0 macro-phone AP, macro-phone NLL
and per-rater Brier must not worsen by more than 1e-7. Required metrics must
be defined. Use the exact fields defined by the preceding protocol. Preserve
the earlier fixed-setting comparisons and their failed gates. Also report the
new-versus-fixed contrasts descriptively, without selecting a regime or
rewriting the criterion. Added-only results remain descriptive.

Changing the LR and epoch count together tests the existing selection
procedure on expanded data, not duration alone. More rows imply more updates
per epoch. Neither word-vocabulary slices nor reused speakers establish
independent generalization or clinical correctness. No expanded model is
promoted for learner feedback by this experiment. Implementation lives in a
new nested directory to preserve the prior top-level Python source inventory.
