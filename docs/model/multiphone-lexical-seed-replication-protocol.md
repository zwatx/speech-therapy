# Fixed seed replication of expanded fitting objectives

This study follows the completed [recording/sound-unit weighting comparison](multiphone-lexical-unit-weights-report.md).
At seed 7, the weighted child mixture fails every primary check against the
unweighted expanded mixture but passes its older corrected-mixture secondary
screen. Some sounds improve and others worsen. Replicate both objectives before
changing the weight rule or selecting a candidate. All earlier source, tests,
protocols and numerical artifacts remain immutable.

## Population and fixed matrix

Use new seeds **17, 29 and 43**, independently resetting Python, NumPy global,
NumPy permutation and Torch streams at each fresh initialization. Keep every
existing expanded job: two feature families (13 scalars, or fit-only PCA16 plus
13 scalars), both all-age/child-only fitting regimes, five speaker folds crossed
with five word groups. Run both unweighted and recording/sound-unit weighted
objectives at each seed. This is 600 inner fits, 600 fresh refits and 600 outer
prediction jobs. Seed 7 remains historical and is excluded from the new-seed
aggregate. Do not discard a seed or choose a deployment seed after seeing results.

Keep all 28,227 expanded positions and original 14,837-position mapping. Preserve
complete-utterance word exclusions, speaker roles, all 23 sounds, age restrictions,
and exactly the original selection examples/order. Added validation positions
enter refitting only. No new data or annotations, changed split, per-phone rule,
calibration, weighting-strength search or mixture search.

## Exactly two objectives

Unweighted fitting assigns weight one to every position. Weighted fitting retains
the fixed complete-canonical recording/sound-unit rule: with n fit positions,
g recording/sound groups, and k same-sound positions in a recording, each weight
is `(n/g)/k`. Recompute using only the current fit/refit partition. Every selected
recording must contribute every supported canonical position exactly once.
Save ordered canonical multiplicities, unit count, normalization, recipe and
weights for both objectives, binding those bytes into configuration/checkpoints.
In the unweighted state, canonical counts remain provenance and normalization is
one; equal group mass is a property only of the weighted objective.

Both objectives keep unweighted feature normalization, fit-only PCA, priors,
original-example selection and evaluation. The training loss remains the batch
mean of fixed fitting weight times five-vote cross entropy, without dividing by
batch weight sum. Keep last-partial-batch behavior. Unweighted and weighted training
loss values are not directly comparable across objectives.

Everything except objective weights and the prescribed seed stays fixed: fresh
128-hidden heads, dropout .1, AdamW learning rate .0003/decay .01, batch 64,
gradient norm cap 5, deterministic CPU execution with two Torch threads. Inner
selection uses original unweighted stable-log NLL, maximum 100 epochs, patience
15, strict improvement beyond 1e-7, and excludes epoch zero. Each job selects its
own epoch. Refit estimates fresh transforms, moments and weights, creates a fresh
seeded model, and trains for that selected positive epoch count without selection.

## Barriers, artifacts and compute

Declare the complete 600-job plan, reviewed trainer, all new source/tests, this
protocol, immutable parent result/joint audit, runtime and inputs before actual
fitting. All 600 inner jobs must freeze successfully before any refit; all 600
refits must freeze successfully before new outer inference. Keep initial/best/last
models, optimizer states, full RNG states, epoch losses/selections, order hashes,
fit weights, transforms and replay artifacts. Use exclusive phase starts/results
and preserve failures. Poll actual live processes; never restart solely because
a wait expired. Do not overwrite or silently resume a partial experiment.

Run on the Mac's existing Python 3.13/NumPy 2.2.6/Torch 2.8.0 CPU environment.
The preceding 100-job study's saved inner/refit spans were approximately 4.31 and
1.67 minutes; six times those spans suggests about 36 minutes of fitting, subject
to different selected epochs and machine load. Scoring and independent checks add
time. Its fit artifacts used about 838 MB and report about 1.6 GB. The Mac had
120 GiB free at preparation, sufficient for this matrix and separate per-seed
reports. This study allocates no Dell or Colab job; neither is required to preserve
the verified environment. Existing 100 Colab units/month authorization remains.

## Matched evaluation and every outcome

Use the frozen evaluator's original, added and all-position views, fixed .5/.5
probability mixture, all metrics/support/reliability summaries, five folds and 25
word cells. Comparisons use only the original matched population, including
5,654 child positions from 52 children aged 6–12. Added/all views remain descriptive.

For each seed and age regime, the three primary contrasts are weighted minus
same-seed unweighted scalar, PCA/scalar and equal mixture. For each objective and
age regime, separately compare its equal mixture with the fixed original corrected-
projection mixture trained at seed 7. That is six primary and four secondary
contrasts per seed. The secondary benchmark's different training seed remains
explicit; it is not a paired-seed weighting effect. Retain neural-minus-fit-prior
differences separately for both objectives.

Apply the unchanged six-part screen to every comparison: pooled child NLL delta
< −1e-7; macro NLL and Brier deltas <= 1e-7; rating-0 AP and below-2 AP deltas
>= −1e-7; and every speaker-fold child NLL delta <= 1e-7. Never replace fold
failures by a favorable pooled mean. For all ten contrasts per seed, retain every
sound's three rating-class loss contributions, five folds, 25 word cells, all-child
contributions and exact support. Reconcile response losses to the metric screen.
Missing means remain null, empty additive contributions zero.

Save a full report for each seed and bind them in one compact aggregate report.
For every contrast, preserve each seed's decision and compute descriptive
mean/minimum/maximum of the five pooled endpoint differences, five fold NLL
differences and all 23 sound NLL differences. Keep per-seed sound values/support.
Record whether every seed passes without treating that flag as a promotion rule.
Do not pool seeds as independent participants, report an uncertainty interval from
three seeds, average seed 7 into these results, or select the most favorable seed.

## Required verification

Before declaration, require full synthetic seed-7 inner and refit equivalence
against the frozen unweighted scalar/compact and unit-weighted trainers, including
repeated positions and partial batches. Compare every epoch/history, initialization,
selected/last model, optimizer, RNG, normalization, PCA, priors and predictions
bit-exactly, ignoring only deliberately changed provenance fields. Test same-seed
repeatability, changed-seed differences, caller/config/weight/seed tampering,
unchanged helper globals, full canonical geometry and fitting-only transforms.

Test the complete matrix, unique seed/objective IDs, phase barriers before any
prepare/train/replay, exclusive declaration, actual synthetic seeded state
validation, original/added index mapping, same-seed pairing, secondary separation,
all ten responses, all three descriptive seed ranges and missing/changed support
rejection. Real metadata preflight must forbid fitting, PCA, inference and scoring.
Obtain substantive source review before freezing the study.

After fitting, independently verify all weight/seed/initialization/optimizer/RNG/
selection/PCA states and exact outer replay, then reconstruct every metric and
response from the saved arrays. Full optimizer trajectories are not claimed unless
actually reconstructed. Rebuild per-seed and aggregate reports offline. Explicitly
tie metric receipts to the same exact plan, outer freeze and prediction artifacts
certified by replay; verify executed helper provenance and all published claims.
No historical source or numerical tolerance may change to obtain a pass.

Training-randomness stability on repeatedly used development folds does not prove
independent generalization or clinical validity. Subjective rating targets, missing
expert produced-phone truth, no ages 2–5 cohort and no established speech-sound
disorder validation remain limits. Keep learner judgments disabled and author-test
closed. No app change, new audio or encoder inference is required. The broader
improvement goal remains active regardless of this experiment's outcome.
