# Paired child uncertainty: pooled gains with a concentrated regression

The all-age mixture's five pooled child endpoints have descriptive 95%
bootstrap intervals entirely in the favorable direction versus scalar. The
child-only mixture's NLL, macro NLL and Brier intervals favor the mixture, but
both rare-rating AP intervals cross zero. The primary consistency screens
remain failed because speaker fold 4 regresses. No model or learner policy is
promoted, and these intervals do not establish clinical performance.

The [fixed protocol](multiphone-lexical-uncertainty-protocol.md) resamples 52
whole children within five original speaker folds, 2,000 times with PCG64 seed
20260927. Each child's complete positions and five-rater counts share one
multiplicity. Identical saved draws apply to both models and training regimes.
All 5,654 child positions and 23 phones are retained. Every actual replicate
contains all 23 phones and positive votes for both pooled ranking endpoints;
there are zero undefined replicates here. The implementation still records
missing support explicitly and never retries a draw to obtain a desired result.

These are percentile intervals conditional on existing predictions, corpus and
folds. They omit training variability, dependence from overlapping training
sets, selection across prior experiments, and uncertainty about new clinical
populations. The outcomes were already exposed during adaptive development.
Intervals are marginal, with no simultaneous coverage or multiplicity claim.
Sign frequencies are resampling frequencies, not p-values or probabilities
that a model is truly better.

## Paired pooled child differences

All differences are mixture minus scalar. Negative NLL/macro NLL/Brier and
positive AP are favorable. AP measures vote-ranking performance, not accuracy.
Each interval below uses all 2,000 valid replicates and linear quantiles.

| Training regime | Endpoint | Observed difference | Descriptive 95% interval | Fraction below / above zero |
| --- | --- | ---: | --- | --- |
| all-age | NLL | -0.001530 | [-0.002692, -0.000321] | 0.9900 / 0.0100 |
| all-age | Brier | -0.001071 | [-0.001748, -0.000472] | 0.9995 / 0.0005 |
| all-age | macroNLL | -0.002083 | [-0.003549, -0.000644] | 0.9975 / 0.0025 |
| all-age | rating0AP | 0.012161 | [0.001202, 0.025273] | 0.0155 / 0.9845 |
| all-age | below2AP | 0.010942 | [0.003990, 0.021806] | 0.0010 / 0.9990 |
| child-only | NLL | -0.002107 | [-0.003984, -0.000584] | 0.9940 / 0.0060 |
| child-only | Brier | -0.000903 | [-0.001486, -0.000364] | 1.0000 / 0.0000 |
| child-only | macroNLL | -0.003427 | [-0.006574, -0.001099] | 1.0000 / 0.0000 |
| child-only | rating0AP | 0.001043 | [-0.009447, 0.008914] | 0.4320 / 0.5680 |
| child-only | below2AP | 0.004170 | [-0.002889, 0.009839] | 0.1240 / 0.8760 |

## All 23 phone NLL differences

The paired phone intervals use the same whole-child draws. Each has 2,000
valid and zero absent-phone replicates. Original support is unchanged across
regimes. The votes column lists rating 0 / rating 1 / rating 2 counts. Support
does not establish adequate power: G still has only one rating-0 vote.

| Phone | Positions | Children | Votes 0 / 1 / 2 | All-age difference | All-age interval | Child-only difference | Child-only interval |
| --- | ---: | ---: | --- | ---: | --- | ---: | --- |
| B | 236 | 51 | 13 / 3 / 1164 | 0.000161 | [-0.001464, 0.001751] | 0.000077 | [-0.001300, 0.001716] |
| CH | 42 | 29 | 8 / 2 / 200 | 0.005997 | [0.000001, 0.013084] | -0.016360 | [-0.029954, -0.004372] |
| D | 322 | 52 | 37 / 27 / 1546 | -0.002363 | [-0.006895, 0.001985] | -0.000592 | [-0.003738, 0.002852] |
| DH | 333 | 52 | 29 / 97 / 1539 | -0.007660 | [-0.011479, -0.004164] | -0.002097 | [-0.006844, 0.003990] |
| F | 191 | 51 | 5 / 2 / 948 | 0.000816 | [-0.000603, 0.001969] | -0.000512 | [-0.002434, 0.001376] |
| G | 195 | 52 | 1 / 2 / 972 | 0.000070 | [-0.000946, 0.001149] | 0.000158 | [-0.000722, 0.001052] |
| HH | 237 | 52 | 7 / 2 / 1176 | 0.002581 | [0.000508, 0.005188] | -0.003748 | [-0.006791, -0.001224] |
| JH | 76 | 31 | 13 / 1 / 366 | -0.014971 | [-0.028242, -0.002824] | -0.011305 | [-0.019996, -0.003189] |
| K | 330 | 52 | 9 / 7 / 1634 | 0.001785 | [-0.000478, 0.004127] | 0.001290 | [-0.000504, 0.003577] |
| L | 357 | 52 | 60 / 16 / 1709 | -0.001504 | [-0.005387, 0.002089] | 0.000218 | [-0.005911, 0.006156] |
| M | 341 | 51 | 32 / 35 / 1638 | 0.000653 | [-0.002673, 0.004458] | 0.001087 | [-0.001759, 0.004301] |
| N | 402 | 52 | 52 / 9 / 1949 | -0.000241 | [-0.003584, 0.003185] | -0.003023 | [-0.004782, -0.001308] |
| NG | 119 | 48 | 10 / 8 / 577 | -0.002179 | [-0.007616, 0.002420] | -0.004279 | [-0.012793, 0.002401] |
| P | 153 | 50 | 15 / 10 / 740 | 0.001899 | [-0.002887, 0.007215] | 0.004479 | [-0.001313, 0.012508] |
| R | 304 | 51 | 60 / 22 / 1438 | -0.003572 | [-0.010992, 0.003188] | -0.001953 | [-0.011398, 0.005644] |
| S | 378 | 52 | 35 / 10 / 1845 | 0.001124 | [-0.001390, 0.003827] | 0.000657 | [-0.004284, 0.004805] |
| SH | 134 | 49 | 18 / 7 / 645 | -0.000335 | [-0.005132, 0.003987] | -0.003114 | [-0.016539, 0.008222] |
| T | 378 | 52 | 27 / 19 / 1844 | 0.002704 | [-0.000383, 0.006266] | -0.002089 | [-0.004737, 0.000306] |
| TH | 75 | 40 | 19 / 75 / 281 | -0.014103 | [-0.026606, -0.003044] | -0.016743 | [-0.056794, 0.009571] |
| V | 200 | 49 | 17 / 76 / 907 | -0.007229 | [-0.015785, 0.000999] | -0.007949 | [-0.021168, 0.002387] |
| W | 323 | 51 | 18 / 4 / 1593 | -0.000706 | [-0.007049, 0.006095] | 0.000124 | [-0.006842, 0.007719] |
| Y | 190 | 49 | 9 / 6 / 935 | -0.004047 | [-0.012050, 0.002480] | -0.002867 | [-0.006025, 0.000196] |
| Z | 338 | 52 | 38 / 265 / 1387 | -0.006790 | [-0.011208, -0.001820] | -0.010276 | [-0.017379, -0.003695] |

## Fold 4: a concentrated, retained regression

Fold 4 contains 1,083 positions from ten children. Its observed NLL difference
is +0.000446 for all-age fitting and +0.001554 for child-only fitting. Child
1435 contributes +0.001674 and +0.001788 to those fold means, respectively—the
largest positive child contribution in both regimes. Other children partly
offset that increase. Removing this child only as an influence calculation
changes the fold differences to -0.001367 and -0.000261; removing any other
single fold-4 child leaves a positive difference. All original children remain
included in every reported comparison and success screen.

This identifies concentration, not a defective recording or incorrect label.
No audio or annotation adjudication was performed. The identities are public
corpus speaker codes, not clinical diagnoses. Pooled NLL remains favorable
under every one-child omission: all-age differences range -0.001887 to
-0.001232; child-only differences range -0.002498 to -0.001517.

Contribution is a group's summed per-position NLL difference divided by all
1,083 fold positions; it is not that group's standalone mean. Each complete
partition below sums to the fold's difference. Rounding can affect displayed
sums. The saved report includes the within-group means, all five fold means,
support and every pooled/fold-4 leave-one-child-out result.

| Child | Positions | Votes 0 / 1 / 2 | All-age contribution | Child-only contribution |
| --- | ---: | --- | ---: | ---: |
| 0054 | 105 | 7 / 12 / 506 | -0.000014 | -0.000260 |
| 0075 | 105 | 16 / 14 / 495 | -0.000506 | 0.000044 |
| 1435 | 110 | 49 / 6 / 495 | 0.001674 | 0.001788 |
| 2034 | 123 | 23 / 11 / 581 | -0.000330 | 0.000675 |
| 3020 | 122 | 5 / 13 / 592 | -0.000075 | -0.000297 |
| 3021 | 104 | 6 / 14 / 500 | 0.000100 | -0.000189 |
| 3049 | 110 | 9 / 14 / 527 | -0.000479 | -0.000313 |
| 3083 | 94 | 6 / 8 / 456 | 0.000195 | 0.000194 |
| 5418 | 105 | 1 / 9 / 515 | -0.000021 | 0.000071 |
| 6504 | 105 | 1 / 8 / 516 | -0.000098 | -0.000158 |

| Phone | Fold positions | All-age contribution | Child-only contribution |
| --- | ---: | ---: | ---: |
| B | 46 | 0.000073 | 0.000022 |
| CH | 4 | 0.000002 | -0.000022 |
| D | 58 | 0.000334 | 0.000026 |
| DH | 62 | -0.000005 | -0.000556 |
| F | 38 | 0.000028 | 0.000047 |
| G | 42 | -0.000030 | 0.000047 |
| HH | 48 | 0.000015 | -0.000176 |
| JH | 8 | -0.000015 | -0.000195 |
| K | 64 | -0.000018 | -0.000050 |
| L | 74 | 0.000135 | 0.000960 |
| M | 65 | 0.000315 | 0.000330 |
| N | 72 | -0.000484 | -0.000340 |
| NG | 31 | -0.000090 | -0.000089 |
| P | 26 | 0.000114 | 0.000240 |
| R | 57 | -0.000047 | 0.000237 |
| S | 70 | 0.000356 | 0.000207 |
| SH | 24 | -0.000027 | 0.000539 |
| T | 80 | -0.000097 | 0.000044 |
| TH | 5 | -0.000048 | 0.000174 |
| V | 35 | -0.000489 | -0.000210 |
| W | 63 | 0.000674 | 0.000825 |
| Y | 46 | 0.000147 | 0.000180 |
| Z | 65 | -0.000397 | -0.000687 |

| Word group | Fold positions | All-age contribution | Child-only contribution |
| --- | ---: | ---: | ---: |
| 0 | 211 | -0.000112 | 0.000705 |
| 1 | 202 | -0.000799 | -0.000297 |
| 2 | 230 | 0.000015 | -0.000895 |
| 3 | 252 | 0.001339 | 0.001670 |
| 4 | 188 | 0.000004 | 0.000371 |

| Rating class | Positions with any such vote | Votes | All-age contribution | Child-only contribution |
| --- | ---: | ---: | ---: | ---: |
| 0 | 65 | 123 | 0.000327 | 0.002412 |
| 1 | 91 | 109 | -0.001230 | 0.000234 |
| 2 | 1080 | 5183 | 0.001348 | -0.001092 |

Class supports can overlap because a position can have different rater votes.
The patterns differ between regimes: all-age class-1 improvement offsets
class-0 and class-2 deterioration; child-only class-2 improvement offsets
class-0 and class-1 deterioration. Thus there is no single rating-class
explanation shared by both regimes.

## Verification and decision

Eleven synthetic tests pass, covering paired strata, duplicated-row equivalence,
exact AP ties, stable extreme logs, absent support, input/declaration guards,
contribution denominators and whole-child omissions. A separate explicit-vote
reference checked 60 synthetic cases and 300 endpoint values; maximum absolute
error was 4.44e-16. The input preflight checked 431 pins with numerical routines
and actual calculation forbidden. Declaration, calculation and exact offline
reconstruction finished with exit zero. A separate artifact audit passed
671,573 checks, including all 431 input bindings, the exact 2,000×52 sampling
matrix, 20,000 pooled endpoint contrasts and 92,000 phone contrasts, intervals,
contribution partitions and whole-child omissions. Its largest numerical
discrepancy was 1.67e-16. The [audit receipt](../../work/lexical-uncertainty-audit-20260927/result.json)
binds the executed independent source and both study artifacts; it imports
neither study nor numerical-core code.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-uncertainty-v1/plan.json): `90995285814308f5cb864045fba25eaba02d1f2e9ac224679b95227b81e85fe4`
- [Complete results and draws](../../research/audio-head/outputs/multiphone-20260927/lexical-uncertainty-v1/report.json): `bf173f044a9f795be56d8a6d92f91450d463b670e376011c337ff374e205df3c`
- [Original mixture comparison](multiphone-lexical-mixture-report.md) retains every primary and secondary screen unchanged.

From `research/audio-head`, use `.venv/bin/python -m lexical_uncertainty.study`.
`declare` requires a fresh `--output`; `run` and `verify` require `--plan` and
`--plan-sha256`. Source/tests/protocol are immutable after declaration.
GPT-6 Sol authored the numerical routines and reviewed the parent-authored
runner; the parent independently checked the numerical routines. Astra did not
review this study; native reviewer capacity had been unavailable.

The next useful diagnostic is to check occurrence alignment and input support
across the complete child cohort, retaining the concentrated speaker and every
other child. This can test whether the apparent concentration accompanies a
reproducible input problem before proposing a new training change. It must not
reinterpret ratings as adjudicated errors, exclude difficult examples or tune
weights on these outcomes. No such diagnostic or new fit is included here.

No new participants, author-test access, audio processing, model/PCA fitting,
head/encoder inference, Colab allocation or app changes occurred. Learner
judgments remain disabled. App builds/UI tests were not run because this
analysis only uses saved research predictions.
