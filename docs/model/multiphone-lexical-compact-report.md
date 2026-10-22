# Compact phonetic features: ranking gains with probability tradeoffs

The fixed 16-component phonetic representation improves pooled child rare-rating
ranking over scalars in the all-age fitting regime, but slightly worsens child
log loss. Both age regimes fail the primary consistency screen against scalars.
This is a measured research tradeoff, not a uniformly improved model or a reason
to enable learner judgments.

For all-age fitting, child rating-0 AP rises from .109133 to .125172 and below-2
AP from .174946 to .186455, while NLL rises from .180497 to .181056. Child-only
fitting improves below-2 AP, Brier and macro-phone NLL, but worsens pooled NLL
and rating-0 AP. Results vary by speaker fold and consonant. No per-phone family,
rank threshold or mixture weight is selected from these exposed outcomes.

## Fixed design and compression

The [protocol](multiphone-lexical-compact-protocol.md) fixed one 16-component
candidate before fitting, with no component-count, seed, variance-retention,
regularization or architecture search. It uses exactly the whole-utterance
word and speaker exclusions from the [canonical inventory](multiphone-lexical-feasibility-report.md).
The [previous scalar/full-phonetic/prior results](multiphone-lexical-head-report.md)
are hash-pinned controls on identical memberships; they were not retrained.

Every fitting set supplies its own float64 mean and population covariance of
the 1,024 raw phonetic features. The 16 largest eigenvectors are ordered by
eigenvalue and signed by their largest-absolute loading. A fixed rank check
rejects deficient transforms rather than changing the dimension. No labels,
selection rows or outer rows determine the compression. The 16 projected
float32 scores are concatenated with the 13 original confidence scalars.
Head normalization then scales all 29 features using fitting rows only; thus
retained component scores are normalized to their fitting standard deviations.
The PCA itself does not whiten the raw input before projection.

The hidden-128 phone-conditioned head has 40,195 parameters, versus 38,147 for
scalars and 169,219 for full phonetic/scalar inputs. The same seed-7 AdamW recipe,
soft five-vote loss, stopping criterion and batch ordering are retained.
Inner selection uses per-rater NLL with maximum 100 epochs and patience 15.
All 50 inner choices and transforms were frozen before 50 fresh refits. Every
refit recomputes PCA and normalization on its purged refitting rows, starts a
fresh head and uses its selected duration. All refits were frozen before the
50 outer passes. No weights are transferred between bases.

Each regime covers 14,837 outer positions from 125 speakers, including 5,654
positions from 52 children aged 6–12, exactly once over 25 speaker×word cells.
All 23 supported consonants remain visible. Capacity and representation change
together; this is a practical pipeline comparison rather than a causal test
of dimensionality or word memorization. Exclusions also reduce fitting data.

## Child outcomes

Lower NLL, macro-phone NLL and Brier are better; higher AP is better. AP uses
pooled original rater votes and is not a clinical accuracy percentage. Scalars
uses 13 confidence features; target-scalars uses the full phonetic vector;
pca16-scalars is this compact candidate. Prior is the matching fitting-data
per-phone Laplace prior. Reference metrics are copied from their pinned report.

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.201926 | 0.213326 | 0.084075 | 0.028153 | 0.117063 |
| all-age / scalars | 0.180497 | 0.190224 | 0.083251 | 0.109133 | 0.174946 |
| all-age / target-scalars | 0.185832 | 0.194166 | 0.083579 | 0.073270 | 0.157082 |
| all-age / pca16-scalars | 0.181056 | 0.189664 | 0.082755 | 0.125172 | 0.186455 |
| child-only / prior | 0.193713 | 0.206017 | 0.082935 | 0.022874 | 0.114274 |
| child-only / scalars | 0.182500 | 0.195113 | 0.082266 | 0.081084 | 0.153376 |
| child-only / target-scalars | 0.185655 | 0.197189 | 0.081253 | 0.057136 | 0.147690 |
| child-only / pca16-scalars | 0.183098 | 0.193685 | 0.081764 | 0.077252 | 0.155416 |

Against scalars, compact all-age fitting improves four of the six fixed checks:
macro-phone NLL, Brier and both AP endpoints. It fails pooled NLL and the
all-speaker-fold NLL check. Compact child-only fitting improves macro-phone NLL,
Brier and below-2 AP; it fails pooled NLL, rating-0 AP and fold consistency.
The primary screens therefore both fail, despite useful individual gains.

## Primary screen and speaker folds

Differences below are compact minus scalar. Positive NLL/Brier changes are
worse; positive AP changes are better. Five word groups are pooled within each
speaker fold; the 25 cells are not independent participant replications.

| Check | all-age | child-only |
| --- | ---: | ---: |
| everySpeakerFoldChildNLLNoWorse | False | False |
| pooledChildBelow2APNoWorse | True | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildNLLImproves | False | False |
| pooledChildRating0APNoWorse | True | False |

| Regime / speaker fold | NLL change | Macro NLL change | Brier change | Rating-0 AP change | Below-2 AP change |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / 0 | 0.001235 | 0.000497 | -0.000641 | 0.028286 | 0.008181 |
| all-age / 1 | 0.001171 | 0.001930 | -0.000030 | -0.033906 | -0.013713 |
| all-age / 2 | -0.003325 | -0.004359 | -0.002682 | 0.072756 | 0.056468 |
| all-age / 3 | -0.000337 | -0.003261 | 0.000362 | -0.009991 | -0.004293 |
| all-age / 4 | 0.005459 | 0.003285 | 0.001425 | 0.000620 | 0.006672 |
| child-only / 0 | -0.003877 | -0.007181 | -0.002105 | -0.005031 | -0.002117 |
| child-only / 1 | 0.000748 | 0.005056 | -0.001033 | -0.000402 | 0.000896 |
| child-only / 2 | -0.000639 | -0.004624 | -0.000271 | -0.002264 | -0.000428 |
| child-only / 3 | -0.002205 | -0.005971 | -0.000989 | 0.005175 | 0.008159 |
| child-only / 4 | 0.008951 | 0.010302 | 0.001675 | -0.035746 | -0.016046 |

All-age compact NLL worsens in folds 0, 1 and 4; child-only compact NLL worsens
in folds 1 and 4. The pooled all-age AP gain does not mean every fold's ranking
improves: rating-0 and below-2 AP both worsen in folds 1 and 3. Do not replace
these mixed observations with a uniform-improvement claim.

## Comparison with the full phonetic model and priors

Compact features improve pooled child NLL, macro-phone NLL and both AP endpoints
against the full phonetic model in both regimes. However, the secondary screen
also fails in both: all-age compact NLL is worse in folds 3 and 4; child-only
compact NLL is worse in fold 4 and pooled Brier worsens .081253→.081764. Success
against the weaker reference cannot replace the primary scalar comparison.

Both compact regimes improve pooled child NLL, macro-phone NLL, Brier and both
AP endpoints over their matched fitting-data priors. Those gains do not establish
reliable diagnosis, phone-level clinical accuracy or generalization to a new
child-SSD population.

## All 23 child phone cells

These are compact-minus-scalar differences. Every position supplies five votes;
votes are not independent participants. The children column counts all children
contributing the sound, not only children supplying a rare rating.

| Phone | Positions | Children | Rating-0 / below-2 votes | All-age NLL Δ | All-age AP0 Δ | All-age AP<2 Δ | Child-only NLL Δ | Child-only AP0 Δ | Child-only AP<2 Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 51 | 13 / 16 | 0.000840 | -0.032316 | -0.036345 | 0.000612 | -0.042593 | -0.100423 |
| CH | 42 | 29 | 8 / 10 | 0.015427 | 0.027579 | 0.038257 | -0.030058 | 0.206750 | 0.129574 |
| D | 322 | 52 | 37 / 64 | -0.000356 | -0.015989 | -0.010928 | 0.002062 | -0.005157 | -0.007766 |
| DH | 333 | 52 | 29 / 126 | -0.011022 | 0.014213 | 0.000935 | 0.002088 | -0.002180 | 0.010220 |
| F | 191 | 51 | 5 / 7 | 0.002153 | -0.002145 | -0.008500 | -0.000369 | 0.005411 | -0.001801 |
| G | 195 | 52 | 1 / 3 | 0.000656 | -0.005121 | -0.004960 | 0.000423 | -0.000878 | -0.000548 |
| HH | 237 | 52 | 7 / 9 | 0.006846 | -0.003698 | -0.007279 | -0.005855 | 0.045599 | 0.087931 |
| JH | 76 | 31 | 13 / 14 | -0.026201 | 0.313824 | 0.285944 | -0.020647 | 0.042387 | 0.079248 |
| K | 330 | 52 | 9 / 16 | 0.004159 | -0.004458 | 0.002249 | 0.003451 | -0.001176 | -0.002361 |
| L | 357 | 52 | 60 / 76 | 0.001825 | 0.025733 | 0.019665 | 0.010222 | 0.009417 | 0.002692 |
| M | 341 | 51 | 32 / 67 | 0.003803 | -0.015530 | -0.020163 | 0.005836 | -0.034219 | -0.028993 |
| N | 402 | 52 | 52 / 61 | 0.003282 | -0.034800 | -0.032665 | -0.003658 | 0.023713 | 0.013474 |
| NG | 119 | 48 | 10 / 18 | 0.000297 | 0.119458 | 0.047461 | -0.002733 | 0.000694 | 0.006736 |
| P | 153 | 50 | 15 / 25 | 0.006283 | 0.025421 | 0.019304 | 0.014737 | -0.034107 | -0.014466 |
| R | 304 | 51 | 60 / 82 | -0.000141 | 0.000342 | 0.015784 | 0.004508 | 0.011839 | 0.020879 |
| S | 378 | 52 | 35 / 45 | 0.005362 | 0.028457 | -0.004968 | 0.004392 | -0.083751 | -0.082053 |
| SH | 134 | 49 | 18 / 25 | 0.001127 | 0.031081 | 0.040116 | 0.007260 | -0.052596 | -0.048206 |
| T | 378 | 52 | 27 / 46 | 0.008667 | -0.032726 | -0.038068 | -0.001791 | 0.005260 | 0.003351 |
| TH | 75 | 40 | 19 / 94 | -0.021037 | 0.085129 | 0.014639 | -0.008190 | -0.014833 | -0.008524 |
| V | 200 | 49 | 17 / 93 | -0.005894 | 0.010848 | 0.020190 | -0.004748 | 0.047767 | 0.021233 |
| W | 323 | 51 | 18 / 22 | 0.002939 | 0.003109 | 0.002770 | 0.005102 | -0.027814 | -0.013104 |
| Y | 190 | 49 | 9 / 15 | -0.004783 | -0.006926 | 0.134704 | -0.004521 | 0.064286 | 0.070647 |
| Z | 338 | 52 | 38 / 303 | -0.007117 | 0.002505 | 0.024527 | -0.010947 | -0.027371 | 0.015499 |

Tradeoffs remain substantial. For example, JH improves NLL and both AP endpoints
in both regimes; all-age CH gains AP while losing NLL. Child-only CH improves
all three. G still has only one child rating-0 vote. Such sparse support cannot
justify selecting a different model for each sound from these outer results.

Seven child selection cells lack phones; only six of 25 child outer cells and
20 of 25 all-age outer cells contain all 23 phones. Missing phone metrics and
undefined rare-rating quantities remain explicit, with complete position,
recording, word, speaker and five-vote support in the machine report. No cell
or speaker was dropped because a result or metric was inconvenient.

## Other age slices

All ages:

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.293177 | 0.302118 | 0.136786 | 0.062471 | 0.124480 |
| all-age / scalars | 0.229729 | 0.233841 | 0.112958 | 0.401063 | 0.392335 |
| all-age / target-scalars | 0.247361 | 0.248918 | 0.119112 | 0.330458 | 0.330806 |
| all-age / pca16-scalars | 0.230477 | 0.234239 | 0.111675 | 0.415324 | 0.402461 |
| child-only / prior | 0.309989 | 0.317467 | 0.138177 | 0.069503 | 0.127944 |
| child-only / scalars | 0.265951 | 0.271810 | 0.124078 | 0.318731 | 0.295106 |
| child-only / target-scalars | 0.306788 | 0.311951 | 0.134237 | 0.172329 | 0.199275 |
| child-only / pca16-scalars | 0.278627 | 0.282125 | 0.126541 | 0.278487 | 0.269325 |

Ages 13 and older:

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.349360 | 0.356764 | 0.169241 | 0.083654 | 0.135088 |
| all-age / scalars | 0.260041 | 0.261913 | 0.131249 | 0.477197 | 0.465610 |
| all-age / target-scalars | 0.285245 | 0.284600 | 0.140990 | 0.405247 | 0.396719 |
| all-age / pca16-scalars | 0.260906 | 0.262993 | 0.129481 | 0.490335 | 0.474455 |
| child-only / prior | 0.381581 | 0.386047 | 0.172190 | 0.098105 | 0.141196 |
| child-only / scalars | 0.317333 | 0.319677 | 0.149823 | 0.415578 | 0.365596 |
| child-only / target-scalars | 0.381371 | 0.383696 | 0.166860 | 0.236862 | 0.237137 |
| child-only / pca16-scalars | 0.337445 | 0.337180 | 0.154111 | 0.363167 | 0.326924 |

These are descriptive slices of the same positions, not additional cohorts.

## Selected duration and retained variance

The durations below were selected before refitting or outer predictions.

| Regime / representation | Runs | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: | ---: |
| all-age / pca16-scalars | 25 | 6 | 15 | 25 |
| child-only / pca16-scalars | 25 | 10 | 21 | 51 |

The 16 components retain roughly 85% of raw phonetic fitting variance. Variance
retention is a descriptive feature statistic, not the share of pronunciation
information preserved or a predictive-accuracy score. The dimension stayed 16
for every cell. Inner and refit bases differ because their fitting rows differ.

| Regime / phase | Transforms | Minimum fraction | Median fraction | Maximum fraction |
| --- | ---: | ---: | ---: | ---: |
| all-age / inner | 25 | 0.848073 | 0.853305 | 0.859014 |
| child-only / inner | 25 | 0.850491 | 0.857616 | 0.865783 |
| all-age / refit | 25 | 0.848253 | 0.853464 | 0.857922 |
| child-only / refit | 25 | 0.850834 | 0.857822 | 0.864701 |

## Verification and reproducibility

Eleven focused tests passed. They cover a known eigensystem/projector,
fit-only row/label invariance, rank and sign rules, 29-feature ordering,
deterministic fresh refits, transform tampering, exact replay, failure-history
retention, checkpoint lineage, reference membership and phase-order guards.
A separate synthetic SVD oracle agreed with the spectrum within 2.842e-14 and
the top-16 projector within 5.138e-15. A direct two-update training calculation
reproduced initial/final weights, AdamW moments and loss exactly.

GPT-6 Sol authored the numerical core and independently reviewed the parent-
authored runner and protocol. The parent independently reviewed the core and
numerical calculations. Astra was unavailable after prior native agent-limit
failures; it did not review this study. The Mac ran all fitting and evaluation.
Declaration, 50 inner fits, 50 refits, 50 outer passes, report calculation and
offline reconstruction all completed with exit zero. The independent
[artifact audit](../../work/lexical-compact-audit-20260927/summary.json) passed
21,834 inner checks, 8,316 refit checks and 32,294 outer lineage/mapping checks.
All 100 inner/refit PCA transforms were checked by a separate SVD: maximum
spectrum discrepancy 2.398e-14, projector discrepancy 2.567e-15, covariance
eigen-equation residual 7.498e-15 and orthogonality discrepancy 5.773e-15; fitting
centers matched exactly. All 50 selected inner and 50 final outer probability,
raw-float32, stable-log and NLL outputs replayed exactly through a separate
tensor path using only the low-level model architecture.

The independent report reconstruction passed 628,356 primary metric/support
checks and 491,674 auxiliary checks across 62 summaries and 558 metric slices.
It covers NLL/conditional NLL, Brier, AP/AUROC, macro measures, all support,
reliability, entropy, MSE/MAE/PCC, argmax recalls, prevalence, confidence and
empty-slice behavior. Candidate/reference memberships, matching priors and
all primary/secondary comparisons agree. Saved optimizer step counters,
permutation RNG and fresh initial Python/Torch RNG were checked; full actual
optimizer-moment trajectories were not independently reconstructed. The separate
synthetic update oracle supplies that numerical check for two updates. Audit
source hashes and all phase receipts are retained unchanged.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-compact-v1/plan.json): `93796077be5af479c07d4e84e15d87c5c96c8d05664a89bd16ab0b7c70550f16`
- [Inner freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-compact-v1/inner-freeze.json): `e26ad1a9077667cfd3dc1bcc094659f9ebda81ec2b2d35b002aea2cc44d3406e`
- [Refit freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-compact-v1/refit-freeze.json): `bbbbe20442023ec2cb3b244a95562c2946413b0f0ea7162175953f874e68c102`
- [Outer freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-compact-v1/outer-freeze.json): `abd4b4d7f4e7ead2bca964122a217259ad84591c9be250bce9d49a57ef19a37d`
- [Candidate result](../../research/audio-head/outputs/multiphone-20260927/lexical-compact-audit-v1/report.json): `143450faa46e98a9e091972b906de69a00488cdb8f885adb3ddf8d88d04cd4cd`
- [Frozen reference result](../../research/audio-head/outputs/multiphone-20260927/lexical-head-audit-v1/report.json): `6f4680ddf6b3f89b4e9796d7bd21d2b0f44c2232cd1cf361efbf38c3c45291fb`

From `research/audio-head`, the runner is `.venv/bin/python -m
lexical_compact.study`. `declare` takes a fresh `--output`; `inner` takes
`--plan` and `--plan-sha256`; `refit`/`outer` also take the preceding `--freeze`
and `--freeze-sha256`; `audit` takes a fresh `--output`; `verify` uses the saved
audit output. All hashes are above. Existing directories and frozen source
must not be overwritten. Every run binds its own saved transform to its config
and all three checkpoints. The reference pipeline memberships are checked
before comparison, and no reference control is refitted or silently substituted.

## Decision and next step

Retain this compact candidate as research evidence of an all-age ranking gain
with probability-quality costs. Keep the scalar baseline and existing four
research bundles; neither primary screen supports promotion. Learner judgments
remain disabled. Close the fixed-rank comparison without a dimension sweep.

A useful next bounded test is one predeclared equal-weight average of scalar
and compact probabilities, checking whether their complementary predictions
improve probability quality while retaining ranking gains. It would need its
own declaration, stable-log arithmetic, matched memberships and the same
consistency assessment. No mixture has been evaluated here, and no weight
should be tuned on these exposed outer outcomes.

The whole campaign uses repeatedly studied development speakers. Previous
results motivated this adaptive follow-up; these are not untouched final tests.
Pretrained lexical exposure is unknown. The corpus contains ages 6–12 but no
established child-SSD cohort or ages 2–5. Labels remain subjective corpus ratings,
not verified produced-phone transcriptions. No author-test recording, new audio,
encoder inference, Colab allocation, app code or learner-feedback behavior was
used or changed. App builds/UI tests were not run for this research-only change.
