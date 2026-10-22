# Input support does not justify excluding the regressing child

The fixed input-support diagnostic does not isolate the concentrated regression
as an extreme-input problem. Corpus child 1435 has zero globally high PCA
residual positions in both training regimes. Same-phone PCA tails contain zero
of its 110 positions for all-age fitting and two for child-only fitting. Scalar
tails identify one global position in each regime and three/four same-phone
positions. These facts do not verify the recordings or ratings, but they supply
no basis for removing this child or treating the regression as solved.

Across the full cohort, each of the eight fixed high-tail groups has a negative
mean mixture-minus-scalar NLL difference: the mixture improves mean loss there.
Every corresponding complement also improves. Thus a high reference percentile
does not, at this aggregate level, identify where this mixture loses to scalars.
Individual regressions remain in the saved position-level results.

## Fixed method and existing evidence

The [protocol](multiphone-lexical-support-protocol.md) defines 50 matched cells,
all 5,654 original child positions, all 52 children and all 23 supported phones
in each training regime. Each position is compared only with its model's exact
refit population, which excludes its held-out speakers and complete word group.
No child, rating, word or position is removed. All previous success screens
remain unchanged and failed; no learner model is promoted.

The scalar axis is the largest absolute z score across the original 13 features,
using saved scalar-refit moments promoted to float64. The phonetic axis is mean
squared residual over 1,024 raw coordinates after reconstruction through the
saved 16-component refit PCA basis. No new transform, head or encoder is fitted.
The report retains every signed scalar z score, its first maximum feature,
all reference vectors and IDs, and every held-out score/rank.

Reference percentiles use exact empirical midranks: strictly lower scores plus
half the tied scores, divided by the reference count. Global and same-phone
references remain separate. The fixed high-tail flag is strictly greater than
.99. It is a descriptive flag, not a validated withholding rule or calibrated
outlier probability. Small same-phone reference sets have limited resolution.
Reference examples helped fit the transform, so training-versus-held-out
asymmetry can occur without a data defect. All findings are adaptive development
observations, not independent validation or causal explanations.

Earlier [scalar](multiphone-position-geometry-report.md) and
[phonetic-vector](multiphone-position-phonetic-report.md) parity checks and frozen
feature validation already establish row identity, finite matrices, estimated
window consistency, and exact assembly from saved units. This analysis does not
repeat encoder inference or claim correct acoustic boundaries. The earlier
[audio adapter check](multiphone-position-audio-report.md) covered seven selected
recordings; it also did not adjudicate phone timing or pronunciation.

## All fixed tails and complements

Differences are mixture minus scalar; negative NLL is favorable. Additive
contributions use all 5,654 child positions as denominator. Each tail/complement
pair therefore sums to the original pooled difference, with rounding in this
display. The two axes and two reference definitions are fixed across regimes.

| Regime | Axis / reference | High tail? | Positions | Mean NLL difference | Additive pooled contribution |
| --- | --- | --- | ---: | ---: | ---: |
| all-age | scalarMaxAbsZ/globalPercentile | false | 5603 | -0.001363 | -0.001351 |
| all-age | scalarMaxAbsZ/globalPercentile | true | 51 | -0.019833 | -0.000179 |
| all-age | scalarMaxAbsZ/samePhonePercentile | false | 5594 | -0.001315 | -0.001301 |
| all-age | scalarMaxAbsZ/samePhonePercentile | true | 60 | -0.021524 | -0.000228 |
| all-age | pcaResidualMSE/globalPercentile | false | 5552 | -0.001289 | -0.001266 |
| all-age | pcaResidualMSE/globalPercentile | true | 102 | -0.014648 | -0.000264 |
| all-age | pcaResidualMSE/samePhonePercentile | false | 5547 | -0.001406 | -0.001379 |
| all-age | pcaResidualMSE/samePhonePercentile | true | 107 | -0.007948 | -0.000150 |
| child-only | scalarMaxAbsZ/globalPercentile | false | 5595 | -0.002121 | -0.002099 |
| child-only | scalarMaxAbsZ/globalPercentile | true | 59 | -0.000737 | -0.000008 |
| child-only | scalarMaxAbsZ/samePhonePercentile | false | 5535 | -0.001672 | -0.001637 |
| child-only | scalarMaxAbsZ/samePhonePercentile | true | 119 | -0.022353 | -0.000470 |
| child-only | pcaResidualMSE/globalPercentile | false | 5534 | -0.001744 | -0.001707 |
| child-only | pcaResidualMSE/globalPercentile | true | 120 | -0.018853 | -0.000400 |
| child-only | pcaResidualMSE/samePhonePercentile | false | 5454 | -0.001500 | -0.001447 |
| child-only | pcaResidualMSE/samePhonePercentile | true | 200 | -0.018651 | -0.000660 |

## Focus child in the complete cohort

The table compares child 1435 with the complete child population, including
that child. Mean percentiles are descriptive averages over position-specific
refit references; they are not the percentile of a child-level anomaly score.

| Regime | Axis / reference | Child 1435 mean percentile | Child tail positions / 110 | All-child mean percentile | All-child tail positions / 5654 |
| --- | --- | ---: | ---: | ---: | ---: |
| all-age | scalarMaxAbsZ/globalPercentile | 0.454029 | 1 | 0.486823 | 51 |
| all-age | scalarMaxAbsZ/samePhonePercentile | 0.458960 | 3 | 0.485957 | 60 |
| all-age | pcaResidualMSE/globalPercentile | 0.493937 | 0 | 0.513363 | 102 |
| all-age | pcaResidualMSE/samePhonePercentile | 0.492750 | 0 | 0.505415 | 107 |
| child-only | scalarMaxAbsZ/globalPercentile | 0.453797 | 1 | 0.496620 | 59 |
| child-only | scalarMaxAbsZ/samePhonePercentile | 0.468164 | 4 | 0.497328 | 119 |
| child-only | pcaResidualMSE/globalPercentile | 0.520601 | 0 | 0.537779 | 120 |
| child-only | pcaResidualMSE/samePhonePercentile | 0.525203 | 2 | 0.531680 | 200 |

## Every child retained

Counts below are global / same-phone high-tail positions. The original votes,
all 13 dominant-scalar counts, raw score summaries and additive contributions
for every child are included in the complete saved report. A positive mean NLL
difference remains a regression, regardless of percentile flags.

| Child | Positions | All-age scalar tails | All-age PCA tails | All-age NLL difference | Child-only scalar tails | Child-only PCA tails | Child-only NLL difference |
| --- | ---: | --- | --- | ---: | --- | --- | ---: |
| 0001 | 101 | 2 / 0 | 0 / 2 | -0.003816 | 1 / 1 | 2 / 11 | -0.006444 |
| 0005 | 102 | 1 / 1 | 1 / 2 | -0.003276 | 1 / 1 | 3 / 4 | -0.004203 |
| 0006 | 102 | 1 / 0 | 0 / 0 | -0.002501 | 1 / 0 | 0 / 2 | -0.000509 |
| 0026 | 109 | 1 / 1 | 0 / 1 | 0.001412 | 1 / 1 | 0 / 0 | 0.000880 |
| 0048 | 103 | 5 / 12 | 48 / 53 | -0.017588 | 10 / 29 | 50 / 57 | -0.033886 |
| 0053 | 102 | 1 / 1 | 0 / 1 | -0.004264 | 1 / 2 | 0 / 1 | -0.001350 |
| 0054 | 105 | 0 / 0 | 2 / 2 | -0.000147 | 0 / 0 | 3 / 5 | -0.002684 |
| 0056 | 100 | 0 / 0 | 0 / 0 | -0.002880 | 0 / 1 | 0 / 0 | 0.000641 |
| 0070 | 97 | 1 / 1 | 2 / 1 | 0.000252 | 1 / 1 | 2 / 5 | -0.000592 |
| 0075 | 105 | 2 / 1 | 4 / 3 | -0.005223 | 2 / 3 | 4 / 7 | 0.000453 |
| 0103 | 119 | 0 / 1 | 0 / 1 | -0.000131 | 1 / 1 | 0 / 3 | 0.004936 |
| 0104 | 109 | 1 / 1 | 0 / 0 | -0.000377 | 1 / 2 | 0 / 0 | -0.004556 |
| 0131 | 104 | 0 / 0 | 4 / 4 | -0.002420 | 0 / 1 | 3 / 5 | -0.003453 |
| 0145 | 96 | 0 / 0 | 0 / 0 | 0.003585 | 0 / 0 | 0 / 1 | 0.002033 |
| 1042 | 115 | 1 / 0 | 2 / 1 | -0.001273 | 1 / 1 | 3 / 6 | -0.004144 |
| 1044 | 110 | 0 / 0 | 0 / 0 | 0.001029 | 0 / 1 | 0 / 0 | -0.004394 |
| 1092 | 109 | 4 / 3 | 0 / 1 | -0.005884 | 4 / 6 | 0 / 1 | -0.014113 |
| 1197 | 99 | 2 / 3 | 2 / 4 | -0.004288 | 2 / 6 | 1 / 3 | -0.001833 |
| 1203 | 101 | 0 / 0 | 0 / 0 | -0.000462 | 0 / 0 | 0 / 0 | -0.001033 |
| 1418 | 91 | 0 / 0 | 9 / 9 | -0.005938 | 0 / 2 | 9 / 10 | -0.003859 |
| 1419 | 99 | 3 / 1 | 0 / 1 | -0.011321 | 2 / 2 | 0 / 2 | -0.002746 |
| 1435 | 110 | 1 / 3 | 0 / 0 | 0.016481 | 1 / 4 | 0 / 2 | 0.017608 |
| 1439 | 135 | 6 / 5 | 0 / 0 | 0.001115 | 6 / 9 | 1 / 2 | -0.010216 |
| 1447 | 95 | 0 / 1 | 1 / 1 | -0.007634 | 1 / 2 | 3 / 3 | 0.008715 |
| 2034 | 123 | 0 / 0 | 0 / 0 | -0.002905 | 0 / 0 | 0 / 0 | 0.005940 |
| 2179 | 96 | 1 / 0 | 2 / 2 | 0.003412 | 1 / 3 | 4 / 6 | -0.005228 |
| 3002 | 102 | 1 / 1 | 0 / 1 | -0.006196 | 1 / 2 | 0 / 3 | -0.005579 |
| 3020 | 122 | 1 / 4 | 1 / 0 | -0.000666 | 2 / 5 | 2 / 2 | -0.002635 |
| 3021 | 104 | 0 / 1 | 0 / 0 | 0.001044 | 0 / 1 | 1 / 0 | -0.001968 |
| 3046 | 112 | 1 / 0 | 0 / 0 | 0.002186 | 1 / 0 | 2 / 3 | 0.000929 |
| 3049 | 110 | 3 / 3 | 2 / 0 | -0.004713 | 3 / 4 | 2 / 0 | -0.003083 |
| 3068 | 108 | 0 / 1 | 1 / 1 | 0.006530 | 0 / 2 | 1 / 3 | -0.012855 |
| 3083 | 94 | 1 / 1 | 2 / 2 | 0.002242 | 2 / 3 | 2 / 2 | 0.002231 |
| 3088 | 96 | 1 / 0 | 4 / 4 | -0.005729 | 1 / 3 | 5 / 5 | -0.000952 |
| 3208 | 114 | 0 / 0 | 1 / 1 | -0.001149 | 0 / 0 | 1 / 5 | -0.003514 |
| 3423 | 123 | 0 / 2 | 0 / 0 | -0.007667 | 0 / 4 | 0 / 2 | 0.002344 |
| 3636 | 104 | 0 / 0 | 5 / 3 | -0.005729 | 0 / 1 | 3 / 8 | -0.002608 |
| 3837 | 122 | 0 / 2 | 0 / 0 | -0.003456 | 0 / 2 | 0 / 0 | -0.002035 |
| 5195 | 132 | 2 / 1 | 0 / 0 | 0.002136 | 2 / 1 | 0 / 2 | 0.001754 |
| 5218 | 129 | 1 / 1 | 1 / 0 | 0.001167 | 1 / 1 | 1 / 2 | -0.000011 |
| 5401 | 111 | 1 / 1 | 2 / 2 | 0.002704 | 1 / 1 | 3 / 4 | -0.006109 |
| 5408 | 132 | 1 / 0 | 0 / 0 | -0.002052 | 2 / 2 | 0 / 1 | -0.002329 |
| 5414 | 116 | 1 / 1 | 1 / 0 | -0.002064 | 1 / 0 | 3 / 2 | -0.001897 |
| 5418 | 105 | 0 / 1 | 0 / 0 | -0.000218 | 0 / 1 | 1 / 2 | 0.000729 |
| 5424 | 103 | 1 / 0 | 0 / 0 | 0.001332 | 1 / 0 | 0 / 1 | -0.002619 |
| 5551 | 121 | 0 / 1 | 2 / 1 | -0.005496 | 0 / 1 | 2 / 3 | 0.000821 |
| 6010 | 124 | 2 / 2 | 1 / 1 | 0.000858 | 2 / 3 | 1 / 2 | -0.001901 |
| 6048 | 97 | 0 / 0 | 0 / 0 | -0.000785 | 0 / 0 | 0 / 1 | 0.000310 |
| 6121 | 104 | 0 / 0 | 0 / 0 | 0.000595 | 0 / 0 | 0 / 2 | -0.001085 |
| 6401 | 117 | 0 / 2 | 1 / 1 | 0.004087 | 1 / 2 | 1 / 4 | 0.000565 |
| 6504 | 105 | 0 / 0 | 0 / 0 | -0.001007 | 0 / 0 | 0 / 1 | -0.001634 |
| 6912 | 110 | 1 / 0 | 1 / 1 | -0.006588 | 0 / 1 | 1 / 4 | -0.003915 |

## All 23 phones

The same full-cohort comparison is retained by sound, including original vote
support and separate global / same-phone high-tail counts. Same-phone references
reduce variation due to phone identity; they do not account for every speaker,
word or recording difference.

| Phone | Positions | Votes 0 / 1 / 2 | All-age scalar tails | All-age PCA tails | All-age NLL difference | Child-only scalar tails | Child-only PCA tails | Child-only NLL difference |
| --- | ---: | --- | --- | --- | ---: | --- | --- | ---: |
| B | 236 | 13 / 3 / 1164 | 2 / 3 | 5 / 7 | 0.000161 | 3 / 6 | 5 / 14 | 0.000077 |
| CH | 42 | 8 / 2 / 200 | 0 / 3 | 0 / 2 | 0.005997 | 0 / 6 | 0 / 8 | -0.016360 |
| D | 322 | 37 / 27 / 1546 | 2 / 4 | 6 / 5 | -0.002363 | 3 / 3 | 6 / 8 | -0.000592 |
| DH | 333 | 29 / 97 / 1539 | 0 / 0 | 5 / 4 | -0.007660 | 0 / 6 | 6 / 12 | -0.002097 |
| F | 191 | 5 / 2 / 948 | 1 / 2 | 2 / 4 | 0.000816 | 2 / 2 | 2 / 8 | -0.000512 |
| G | 195 | 1 / 2 / 972 | 1 / 3 | 3 / 3 | 0.000070 | 0 / 9 | 4 / 19 | 0.000158 |
| HH | 237 | 7 / 2 / 1176 | 2 / 3 | 3 / 3 | 0.002581 | 3 / 5 | 2 / 5 | -0.003748 |
| JH | 76 | 13 / 1 / 366 | 0 / 0 | 2 / 5 | -0.014971 | 0 / 7 | 2 / 11 | -0.011305 |
| K | 330 | 9 / 7 / 1634 | 0 / 0 | 5 / 6 | 0.001785 | 1 / 8 | 5 / 7 | 0.001290 |
| L | 357 | 60 / 16 / 1709 | 9 / 5 | 13 / 6 | -0.001504 | 8 / 4 | 19 / 12 | 0.000218 |
| M | 341 | 32 / 35 / 1638 | 0 / 4 | 3 / 6 | 0.000653 | 0 / 2 | 3 / 7 | 0.001087 |
| N | 402 | 52 / 9 / 1949 | 3 / 3 | 7 / 10 | -0.000241 | 3 / 5 | 8 / 11 | -0.003023 |
| NG | 119 | 10 / 8 / 577 | 1 / 1 | 1 / 1 | -0.002179 | 1 / 5 | 4 / 7 | -0.004279 |
| P | 153 | 15 / 10 / 740 | 6 / 1 | 3 / 5 | 0.001899 | 6 / 2 | 4 / 5 | 0.004479 |
| R | 304 | 60 / 22 / 1438 | 15 / 1 | 11 / 8 | -0.003572 | 15 / 2 | 14 / 8 | -0.001953 |
| S | 378 | 35 / 10 / 1845 | 1 / 5 | 3 / 7 | 0.001124 | 1 / 6 | 4 / 8 | 0.000657 |
| SH | 134 | 18 / 7 / 645 | 1 / 7 | 2 / 3 | -0.000335 | 3 / 11 | 2 / 7 | -0.003114 |
| T | 378 | 27 / 19 / 1844 | 1 / 2 | 9 / 8 | 0.002704 | 2 / 5 | 9 / 11 | -0.002089 |
| TH | 75 | 19 / 75 / 281 | 0 / 1 | 1 / 1 | -0.014103 | 0 / 7 | 1 / 7 | -0.016743 |
| V | 200 | 17 / 76 / 907 | 0 / 0 | 5 / 6 | -0.007229 | 1 / 2 | 5 / 4 | -0.007949 |
| W | 323 | 18 / 4 / 1593 | 1 / 2 | 0 / 2 | -0.000706 | 1 / 6 | 1 / 9 | 0.000124 |
| Y | 190 | 9 / 6 / 935 | 1 / 8 | 10 / 1 | -0.004047 | 1 / 7 | 10 / 5 | -0.002867 |
| Z | 338 | 38 / 265 / 1387 | 4 / 2 | 3 / 4 | -0.006790 | 5 / 3 | 4 / 7 | -0.010276 |

The complete report also retains all five speaker folds, all five word groups,
and all 16 joint flag patterns including empty patterns. Empty groups have
zero additive contribution and null within-group mean; they are not discarded.
These descriptive subsets are not extra independent samples.

## Verification and next model question

Seven synthetic tests pass, including an analytic residual example, basis
rotation/translation invariance, exact-tie ranks, missing-reference and invalid
transform rejection, summary denominators, strict thresholds, empty groups,
and declaration-before-calculation guards. GPT-6 Sol independently reviewed
all new source and protocol and reran the tests. The 688-pin/50-cell preflight
forbade score calculation. Declaration and actual calculation completed with
exit zero. Exact offline reconstruction also completed with exit zero. The
independent artifact audit passed 303,083 checks across all 688 pins, 50 cells
and 11,308 regime-position records. Scalar scores and all 13 z values match
exactly; an independent sum of rank-one projections reproduced PCA residuals
within 1.39e-17. All empirical ranks were checked exactly against the validated
saved score vectors; complete summaries differ by at most 1.78e-15. The
[audit receipt](../../work/lexical-support-audit-20260927/result.json) binds its
executed source and both study artifacts. It imports neither study nor core.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-support-v1/plan.json): `93ae0065ef83d1be5a13ae14a316a6ba96ff9cc4a0d58b9311aa3a9bc145e282`
- [Complete scores, references and summaries](../../research/audio-head/outputs/multiphone-20260927/lexical-support-v1/report.json): `3698ff50e83f21d864eb03806b52d2515ef03c5ec965aa577bb3e058fdafb269`
- [Prior uncertainty and influence analysis](multiphone-lexical-uncertainty-report.md) retains the original regression and conditional-interval limits.

From `research/audio-head`, use `.venv/bin/python -m lexical_support.study`.
`declare` requires a fresh `--output`; `run`/`verify` require `--plan` and
`--plan-sha256`. All new source/tests/protocol are immutable after declaration.
Astra did not review this study; existing native reviewer capacity had been
unavailable. The independent review uses the available GPT-6 Sol agent.

Close this bounded high-reference-tail diagnostic without searching thresholds
or creating exclusions. One next model hypothesis is to adapt a compact
projection using only fitting labels, rather than retain directions solely for
input variance. The existing evidence does not prove that PCA discarded useful
rating information. Any supervised-projection comparison needs its own fixed
recipe, inner-only selection, fresh refits and unchanged speaker/word holdouts.
No such training or new model result is included here.

No raw audio, author-test data, training, transform fitting, head/encoder
inference, Colab allocation, app changes or learner judgments occurred. App
builds/UI tests were not run for this saved-feature research diagnostic.
