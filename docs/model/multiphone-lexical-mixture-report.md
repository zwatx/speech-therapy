# Equal-weight mixture: pooled child gains, one speaker-fold regression

The fixed 50/50 scalar/compact probability mixture improves all five pooled
child endpoints against scalars in both training regimes: NLL, macro-phone NLL,
Brier, rating-0 AP and below-2 AP. It does not pass either primary consistency
screen because child NLL worsens in speaker fold 4. Keep the pooled gains and
that regression together; this is not a uniformly improved or clinically
validated model, and no learner judgment or research bundle is promoted.

For all-age training, child NLL changes .180497→.178968, rating-0 AP
.109133→.121294 and below-2 AP .174946→.185888. For child-only training, NLL
changes .182500→.180393, rating-0 AP .081084→.082126 and below-2 AP
.153376→.157546. These are paired development outcomes on the same positions.
AP is ranking performance using original rater votes, not an accuracy percentage.

## One declared calculation

The [protocol](multiphone-lexical-mixture-protocol.md) fixed equal weights before
any mixture calculation. It reuses the frozen [scalar](multiphone-lexical-head-report.md)
and [PCA16/scalar](multiphone-lexical-compact-report.md) predictions on exactly
matching inner-fit, selection, refit and outer memberships. Every source head
inherits the canonical whole-utterance word exclusions and speaker separation.
All 50 model pairs, checkpoints, source predictions, declarations and reference
reports are hash-bound. No model, PCA, calibration, threshold or mixture weight
was fitted, and there was no weight grid or per-phone selection.

The class probability is half scalar plus half compact. Computation uses stable
float64 `logaddexp(logScalar, logCompact) - log(2)`, then exponentiation for
ordinary probabilities. This averages probabilities, not logits or logs.
NLL uses finite stable logs without clipping or probability floors, including
when exponentiation underflows. Source float32 probabilities remain available
in their original artifacts; this calculation does not generate a new network
output or rerun either head.

Each regime contains 25 speaker×word cells, pooled to 14,837 positions from 125
speakers, including 5,654 child positions from 52 children aged 6–12. Each
position occurs once per regime. All 23 supported phones, five-vote counts,
sparse cells and undefined metrics are retained. Five word groups within a
speaker fold are pooled for the fold analysis; overlapping fitting populations
and multiple rater votes are not extra independent participants.

## Child outcomes

Lower NLL, macro-phone NLL and Brier are better; higher AP is better. Scalars
uses confidence features; pca16-scalars is the compact phonetic/confidence head;
equal-mixture is this fixed average. Prior is the matching fitting-data
per-phone Laplace prior. Component/prior values are from their frozen reports.

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.201926 | 0.213326 | 0.084075 | 0.028153 | 0.117063 |
| all-age / scalars | 0.180497 | 0.190224 | 0.083251 | 0.109133 | 0.174946 |
| all-age / pca16-scalars | 0.181056 | 0.189664 | 0.082755 | 0.125172 | 0.186455 |
| all-age / equal-mixture | 0.178968 | 0.188141 | 0.082181 | 0.121294 | 0.185888 |
| child-only / prior | 0.193713 | 0.206017 | 0.082935 | 0.022874 | 0.114274 |
| child-only / scalars | 0.182500 | 0.195113 | 0.082266 | 0.081084 | 0.153376 |
| child-only / pca16-scalars | 0.183098 | 0.193685 | 0.081764 | 0.077252 | 0.155416 |
| child-only / equal-mixture | 0.180393 | 0.191686 | 0.081363 | 0.082126 | 0.157546 |

The pooled gains against scalars occur in both regimes. Against compact, the
all-age mixture improves NLL, macro NLL and Brier but loses both ranking endpoints:
rating-0 AP changes .125172→.121294 and below-2 AP .186455→.185888. The child-only
mixture improves all five pooled child endpoints against compact. Both regimes
improve all five pooled endpoints against their fitting-data priors. None of
those comparisons removes the primary fold-consistency failure.

## Primary consistency screen and speaker folds

Both regimes pass five of six checks against scalars. The one failed check
requires child NLL to be no worse in every speaker fold. Deltas below are
mixture minus scalar; positive NLL/Brier and negative AP differences are worse.

| Check | all-age | child-only |
| --- | ---: | ---: |
| everySpeakerFoldChildNLLNoWorse | False | False |
| pooledChildBelow2APNoWorse | True | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildNLLImproves | True | True |
| pooledChildRating0APNoWorse | True | True |

| Regime / speaker fold | NLL change | Macro NLL change | Brier change | Rating-0 AP change | Below-2 AP change |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / 0 | -0.000691 | -0.001155 | -0.001088 | 0.007235 | 0.007188 |
| all-age / 1 | -0.000916 | -0.000370 | -0.000722 | -0.013158 | 0.001156 |
| all-age / 2 | -0.003770 | -0.004355 | -0.002325 | 0.043757 | 0.036828 |
| all-age / 3 | -0.001863 | -0.003439 | -0.000743 | -0.005688 | -0.001500 |
| all-age / 4 | 0.000446 | -0.000309 | 0.000035 | 0.000027 | 0.006785 |
| child-only / 0 | -0.003439 | -0.005188 | -0.001616 | 0.003287 | -0.002470 |
| child-only / 1 | -0.002118 | -0.000977 | -0.001184 | 0.007201 | 0.002944 |
| child-only / 2 | -0.003334 | -0.005542 | -0.000685 | 0.006548 | 0.001082 |
| child-only / 3 | -0.002872 | -0.004976 | -0.001264 | 0.004634 | 0.009076 |
| child-only / 4 | 0.001554 | 0.002127 | 0.000083 | -0.017787 | -0.005577 |

Fold 4 worsens child NLL by .000446 with all-age training and .001554 with
child-only training. Both mixtures improve NLL in folds 0–3. Ranking has further
tradeoffs: all-age rating-0 AP worsens in folds 1 and 3, and child-only rating-0
AP worsens in fold 4. All-age below-2 AP worsens in fold 3; child-only below-2
AP worsens in folds 0 and 4. Pooled gains cannot be described as gains for
every speaker group or every sound.

## Secondary comparison against compact

The secondary screens fail too. All-age mixture NLL improves in every speaker
fold against compact, but both pooled AP endpoints decline. Child-only pooled
endpoints improve, but its mixture-versus-compact NLL worsens in fold 0. The
primary comparison remains mixture versus scalar regardless of these results.

| Check | all-age | child-only |
| --- | ---: | ---: |
| everySpeakerFoldChildNLLNoWorse | True | False |
| pooledChildBelow2APNoWorse | False | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildNLLImproves | True | True |
| pooledChildRating0APNoWorse | False | True |

## All 23 child phone cells

These are mixture-minus-scalar changes. Each position has five votes. The
children column counts all children contributing that sound, not just children
with a low rating. A positive NLL delta is worse; a positive AP delta is better.

| Phone | Positions | Children | Rating-0 / below-2 votes | All-age NLL Δ | All-age AP0 Δ | All-age AP<2 Δ | Child-only NLL Δ | Child-only AP0 Δ | Child-only AP<2 Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 51 | 13 / 16 | 0.000161 | -0.006889 | -0.022667 | 0.000077 | 0.000484 | 0.000602 |
| CH | 42 | 29 | 8 / 10 | 0.005997 | 0.028690 | 0.039673 | -0.016360 | 0.049397 | 0.015728 |
| D | 322 | 52 | 37 / 64 | -0.002363 | 0.000345 | 0.004896 | -0.000592 | -0.000019 | 0.000341 |
| DH | 333 | 52 | 29 / 126 | -0.007660 | 0.003515 | -0.003631 | -0.002097 | -0.001258 | 0.003066 |
| F | 191 | 51 | 5 / 7 | 0.000816 | -0.002009 | -0.002975 | -0.000512 | 0.002719 | -0.000459 |
| G | 195 | 52 | 1 / 3 | 0.000070 | -0.003119 | -0.002156 | 0.000158 | -0.000106 | 0.001996 |
| HH | 237 | 52 | 7 / 9 | 0.002581 | -0.002164 | -0.004569 | -0.003748 | 0.010520 | 0.017972 |
| JH | 76 | 31 | 13 / 14 | -0.014971 | 0.047179 | 0.043598 | -0.011305 | 0.012632 | 0.030992 |
| K | 330 | 52 | 9 / 16 | 0.001785 | -0.002527 | -0.002796 | 0.001290 | -0.000423 | -0.000943 |
| L | 357 | 52 | 60 / 76 | -0.001504 | 0.019876 | 0.013842 | 0.000218 | 0.009655 | 0.007597 |
| M | 341 | 51 | 32 / 67 | 0.000653 | -0.006114 | -0.009254 | 0.001087 | -0.015034 | -0.011339 |
| N | 402 | 52 | 52 / 61 | -0.000241 | -0.021445 | -0.017888 | -0.003023 | 0.010926 | 0.018795 |
| NG | 119 | 48 | 10 / 18 | -0.002179 | 0.031046 | 0.065745 | -0.004279 | 0.006129 | -0.000025 |
| P | 153 | 50 | 15 / 25 | 0.001899 | 0.029961 | 0.020243 | 0.004479 | -0.016227 | -0.014673 |
| R | 304 | 51 | 60 / 82 | -0.003572 | -0.004024 | 0.007638 | -0.001953 | 0.007498 | 0.011903 |
| S | 378 | 52 | 35 / 45 | 0.001124 | 0.075910 | 0.044507 | 0.000657 | -0.012000 | -0.002395 |
| SH | 134 | 49 | 18 / 25 | -0.000335 | 0.029674 | 0.021833 | -0.003114 | -0.068410 | -0.024575 |
| T | 378 | 52 | 27 / 46 | 0.002704 | -0.021140 | -0.031170 | -0.002089 | 0.001723 | 0.002915 |
| TH | 75 | 40 | 19 / 94 | -0.014103 | 0.043256 | 0.008275 | -0.016743 | -0.000934 | -0.000990 |
| V | 200 | 49 | 17 / 93 | -0.007229 | 0.005876 | 0.009620 | -0.007949 | 0.021582 | 0.003543 |
| W | 323 | 51 | 18 / 22 | -0.000706 | 0.010344 | 0.009655 | 0.000124 | -0.008131 | -0.000750 |
| Y | 190 | 49 | 9 / 15 | -0.004047 | -0.032323 | 0.090898 | -0.002867 | 0.014286 | 0.018131 |
| Z | 338 | 52 | 38 / 303 | -0.006790 | 0.001554 | 0.016075 | -0.010276 | -0.009132 | 0.008619 |

Per-phone regressions remain explicit. All-age CH improves both AP measures but
loses NLL, while child-only CH improves all three. JH improves all three in both
regimes. G still has only one child rating-0 vote. These observed differences
do not justify phone-specific weights or reliable phone-level clinical claims.

The inherited support limitations remain: seven child selection cells lack
phones; only six of 25 child outer cells and 20 of 25 all-age outer cells contain
all 23 phones. Missing-phone metrics remain null, and rare-rating quantities
without required class support stay undefined. No row, phone or cell is dropped
from the report to make the comparison appear more complete.

## Other age slices

All ages:

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.293177 | 0.302118 | 0.136786 | 0.062471 | 0.124480 |
| all-age / scalars | 0.229729 | 0.233841 | 0.112958 | 0.401063 | 0.392335 |
| all-age / pca16-scalars | 0.230477 | 0.234239 | 0.111675 | 0.415324 | 0.402461 |
| all-age / equal-mixture | 0.227034 | 0.230927 | 0.111159 | 0.420423 | 0.407854 |
| child-only / prior | 0.309989 | 0.317467 | 0.138177 | 0.069503 | 0.127944 |
| child-only / scalars | 0.265951 | 0.271810 | 0.124078 | 0.318731 | 0.295106 |
| child-only / pca16-scalars | 0.278627 | 0.282125 | 0.126541 | 0.278487 | 0.269325 |
| child-only / equal-mixture | 0.266718 | 0.271344 | 0.124388 | 0.317157 | 0.289972 |

Ages 13 and older:

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.349360 | 0.356764 | 0.169241 | 0.083654 | 0.135088 |
| all-age / scalars | 0.260041 | 0.261913 | 0.131249 | 0.477197 | 0.465610 |
| all-age / pca16-scalars | 0.260906 | 0.262993 | 0.129481 | 0.490335 | 0.474455 |
| all-age / equal-mixture | 0.256629 | 0.258578 | 0.129001 | 0.496050 | 0.480863 |
| child-only / prior | 0.381581 | 0.386047 | 0.172190 | 0.098105 | 0.141196 |
| child-only / scalars | 0.317333 | 0.319677 | 0.149823 | 0.415578 | 0.365596 |
| child-only / pca16-scalars | 0.337445 | 0.337180 | 0.154111 | 0.363167 | 0.326924 |
| child-only / equal-mixture | 0.319869 | 0.320964 | 0.150879 | 0.412273 | 0.356795 |

These slices add no new participants. With child-only fitting, mixture NLL,
Brier and both AP endpoints worsen against scalars in both the all-age and
13-plus populations. The pooled child gains therefore do not establish broader
age generalization. All-age fitting has a different descriptive pattern, as
shown in the table; no regime is selected retrospectively for deployment.

## Verification and artifacts

Six focused tests passed for probability averaging, component symmetry,
identical inputs, extreme stable logs, invalid rows/probabilities/counts,
complete partition matching and declaration-before-calculation behavior.
A separate 80-digit Decimal reference checked 60 synthetic cases: maximum
stable-log error 7.105e-15 and NLL error 4.547e-13. The actual input preflight
checked 423 bindings and 50 pairs with mixture calculation, PCA, training and
prediction patched to reject invocation.

GPT-6 Sol independently reviewed the parent-authored source and protocol and
reran the synthetic tests. Astra was unavailable after previous native agent-
limit failures; it did not review this study. Declaration, actual calculation
and complete offline reconstruction finished with exit zero. The independent
artifact audit passed all 50 pairs: 34,824 lineage/arithmetic checks, 628,356
primary metric checks and 491,674 ancillary checks across 62 summaries and 558
metric slices. Independent max/log1p arithmetic matched saved logs and NLL
exactly; ordinary probability averaging differed by at most 2.22e-16. The
[audit receipt](../../work/lexical-mixture-audit-20260927/result.json) binds its
independent sources and both study artifacts. Prior studies provide the
source-head replay evidence; no new head replay is claimed for this calculation.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-mixture-v1/plan.json): `83c31246a295db47d4cc3402e971f8e5d1199fa2bf478378a55ee104f8370bf7`
- [Mixture result](../../research/audio-head/outputs/multiphone-20260927/lexical-mixture-v1/report.json): `8df2508a7af9f728396fea41f2e34317d086cbeca773b662cc1918b37d3ced47`
- [Scalar/prior reference](../../research/audio-head/outputs/multiphone-20260927/lexical-head-audit-v1/report.json): `6f4680ddf6b3f89b4e9796d7bd21d2b0f44c2232cd1cf361efbf38c3c45291fb`
- [Compact reference](../../research/audio-head/outputs/multiphone-20260927/lexical-compact-audit-v1/report.json): `143450faa46e98a9e091972b906de69a00488cdb8f885adb3ddf8d88d04cd4cd`

From `research/audio-head`, use `.venv/bin/python -m lexical_mixture.study`.
`declare` takes a fresh `--output`; `run` and `verify` take `--plan` and
`--plan-sha256`. The declaration binds both original outer freezes and each
cell's exact source files and checkpoints. The saved report includes every
mixture cell vector plus source pins. Do not overwrite frozen sources or outputs.

## Decision and next step

Retain the fixed mixture as a research candidate with measured pooled child
gains and unresolved speaker/fold/phone tradeoffs. Keep existing bundles and
learner judgments unchanged. Close the single equal-weight comparison without
a weight search or a relaxed success screen.

The next step is a fixed speaker-level uncertainty analysis and a breakdown
of the fold-4 regression. Resampling must preserve whole speakers and paired
predictions, with explicit undefined rare-event cases. This would quantify how
much confidence the present development data support; it would not change the
mixture weights, turn a failed consistency check into a pass or provide a new
independent validation cohort. No such uncertainty calculation is included here.

This follow-up was motivated by already exposed outcomes on repeatedly studied
speakers. Whole-word exclusion applies to supervised training and selection;
pretrained lexical exposure remains unknown. Labels are subjective ratings,
not verified produced-phone ground truth. There is no established child-SSD or
age-2–5 cohort. Real use of the mixture would require both heads plus the compact
transform; a saved-prediction calculation does not implement an inference adapter
or measure latency. No author-test, new audio, head/encoder inference, transform
fitting, Colab allocation, app code or learner-feedback behavior was used or
changed. App builds/UI tests were not run for this research-only calculation.
