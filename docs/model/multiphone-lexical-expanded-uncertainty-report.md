# Expanded fitting uncertainty: child gains with sound-specific limits

The child-trained equal scalar/PCA mixture has favorable conditional 95% intervals
for all five pooled endpoints against its original-data counterpart. Its NLL
difference is −.002934 with interval [−.006236, −.000608]; rating-0 AP difference
is +.009953 with interval [.000543, .021860]. All 52 leave-one-child-out NLL
contrasts remain favorable. This strengthens the descriptive development evidence
for the prior study's passing primary comparison.

This does not establish improvement for every sound or population. Child-mixture
/W/ NLL worsens with an interval entirely above zero. Against the stronger
corrected-projection mixture, the child macro-phone NLL interval includes zero
and the prior fold-0 consistency failure remains. Every all-age pooled endpoint
interval includes zero across all four contrasts. No consistency decision, model,
weight or learner policy is changed by these intervals.

## Fixed method and interpretation

The [protocol](multiphone-lexical-expanded-uncertainty-protocol.md) declares all
eight comparisons from the [expanded head study](multiphone-lexical-expanded-heads-report.md),
including failed primary and stronger secondary contrasts. All use exactly the
same original 5,654 positions, 52 children aged 6–12 and 23 consonants. The common
2,000×52 PCG64 seed20260927 multiplicity matrix resamples whole children within
the original five speaker folds, preserving each fold's number of sampled children.
Every recording, position and five-vote vector from a child shares its multiplicity.

Predictions remain fixed. Intervals are linear 2.5/97.5 percentiles conditional
on these models, children, folds and adaptive development choices. They exclude
training variability, new populations, overlapping training-set uncertainty and
repeated model-search effects. There is no simultaneous-coverage or multiplicity
correction claim. Sign fractions are descriptive resample frequencies, not p-values
or posterior probabilities. This is not independent final or clinical validation.

All 2,000 replicates retain all 23 phones and positive pooled support for both AP
endpoints. Every pooled and phone NLL interval therefore has 2,000 valid and zero
undefined replicates; null cases remain supported and tested. Positive vote support
does not make rare errors plentiful. Per-position averaging means children with
more positions still contribute more loss mass within a sampled multiplicity.

Differences below are expanded minus the corresponding original-data model.
`mixtureVsCorrectedMixture` is the secondary expanded equal mixture minus the
original corrected-projection mixture. Lower NLL/macro NLL/Brier and higher AP
favor the expanded model. AP measures ranking of subjective rating votes, not
pronunciation correctness.

## Complete pooled child intervals

### all-age fitting

| Contrast | Endpoint | Observed Δ | Conditional 95% interval | Fraction below zero | Fraction above zero | Valid / undefined |
| --- | --- | --- | --- | --- | --- | --- |
| scalars | NLL | 0.000639 | [-0.000777, 0.001933] | 0.179500 | 0.820500 | 2000 / 0 |
| scalars | Brier | 0.000594 | [-0.000182, 0.001353] | 0.068000 | 0.932000 | 2000 / 0 |
| scalars | macroNLL | 0.000654 | [-0.000725, 0.001978] | 0.170500 | 0.829500 | 2000 / 0 |
| scalars | rating0AP | 0.001624 | [-0.009111, 0.011831] | 0.386000 | 0.614000 | 2000 / 0 |
| scalars | below2AP | 0.001727 | [-0.005003, 0.010289] | 0.306000 | 0.694000 | 2000 / 0 |
| pca16-scalars | NLL | -0.000933 | [-0.002627, 0.000797] | 0.862500 | 0.137500 | 2000 / 0 |
| pca16-scalars | Brier | -0.000412 | [-0.001433, 0.000659] | 0.781000 | 0.219000 | 2000 / 0 |
| pca16-scalars | macroNLL | -0.000740 | [-0.002887, 0.001405] | 0.760000 | 0.240000 | 2000 / 0 |
| pca16-scalars | rating0AP | 0.002808 | [-0.013323, 0.019926] | 0.375500 | 0.624500 | 2000 / 0 |
| pca16-scalars | below2AP | 0.008071 | [-0.003678, 0.019130] | 0.087500 | 0.912500 | 2000 / 0 |
| equal-mixture | NLL | -0.000609 | [-0.001731, 0.000513] | 0.857500 | 0.142500 | 2000 / 0 |
| equal-mixture | Brier | -0.000117 | [-0.000767, 0.000519] | 0.630500 | 0.369500 | 2000 / 0 |
| equal-mixture | macroNLL | -0.000492 | [-0.001812, 0.000812] | 0.766500 | 0.233500 | 2000 / 0 |
| equal-mixture | rating0AP | 0.001416 | [-0.009883, 0.012493] | 0.429000 | 0.571000 | 2000 / 0 |
| equal-mixture | below2AP | 0.004275 | [-0.002921, 0.010465] | 0.118500 | 0.881500 | 2000 / 0 |
| mixtureVsCorrectedMixture | NLL | -0.000261 | [-0.001363, 0.000868] | 0.683000 | 0.317000 | 2000 / 0 |
| mixtureVsCorrectedMixture | Brier | 0.000068 | [-0.000575, 0.000705] | 0.414000 | 0.586000 | 2000 / 0 |
| mixtureVsCorrectedMixture | macroNLL | -0.000063 | [-0.001338, 0.001205] | 0.550000 | 0.450000 | 2000 / 0 |
| mixtureVsCorrectedMixture | rating0AP | 0.000659 | [-0.010846, 0.011626] | 0.495000 | 0.505000 | 2000 / 0 |
| mixtureVsCorrectedMixture | below2AP | 0.003429 | [-0.003869, 0.009768] | 0.174000 | 0.826000 | 2000 / 0 |

### child-only fitting

| Contrast | Endpoint | Observed Δ | Conditional 95% interval | Fraction below zero | Fraction above zero | Valid / undefined |
| --- | --- | --- | --- | --- | --- | --- |
| scalars | NLL | -0.002376 | [-0.006051, 0.000165] | 0.964000 | 0.036000 | 2000 / 0 |
| scalars | Brier | -0.000660 | [-0.001292, -0.000162] | 0.996000 | 0.004000 | 2000 / 0 |
| scalars | macroNLL | -0.001998 | [-0.006480, 0.001214] | 0.842000 | 0.158000 | 2000 / 0 |
| scalars | rating0AP | 0.007348 | [-0.001892, 0.018335] | 0.066500 | 0.933500 | 2000 / 0 |
| scalars | below2AP | 0.006831 | [0.000791, 0.013593] | 0.008500 | 0.991500 | 2000 / 0 |
| pca16-scalars | NLL | -0.003867 | [-0.007323, -0.001329] | 1.000000 | 0.000000 | 2000 / 0 |
| pca16-scalars | Brier | -0.001310 | [-0.002102, -0.000647] | 1.000000 | 0.000000 | 2000 / 0 |
| pca16-scalars | macroNLL | -0.003470 | [-0.007529, -0.000466] | 0.992000 | 0.008000 | 2000 / 0 |
| pca16-scalars | rating0AP | 0.011719 | [-0.000532, 0.025455] | 0.032000 | 0.968000 | 2000 / 0 |
| pca16-scalars | below2AP | 0.018490 | [0.009981, 0.026837] | 0.000000 | 1.000000 | 2000 / 0 |
| equal-mixture | NLL | -0.002934 | [-0.006236, -0.000608] | 0.998000 | 0.002000 | 2000 / 0 |
| equal-mixture | Brier | -0.000991 | [-0.001675, -0.000476] | 1.000000 | 0.000000 | 2000 / 0 |
| equal-mixture | macroNLL | -0.002590 | [-0.006388, -0.000039] | 0.978500 | 0.021500 | 2000 / 0 |
| equal-mixture | rating0AP | 0.009953 | [0.000543, 0.021860] | 0.019000 | 0.981000 | 2000 / 0 |
| equal-mixture | below2AP | 0.012329 | [0.005950, 0.019211] | 0.000000 | 1.000000 | 2000 / 0 |
| mixtureVsCorrectedMixture | NLL | -0.002839 | [-0.006309, -0.000457] | 0.995000 | 0.005000 | 2000 / 0 |
| mixtureVsCorrectedMixture | Brier | -0.000927 | [-0.001650, -0.000406] | 1.000000 | 0.000000 | 2000 / 0 |
| mixtureVsCorrectedMixture | macroNLL | -0.002358 | [-0.006263, 0.000210] | 0.954500 | 0.045500 | 2000 / 0 |
| mixtureVsCorrectedMixture | rating0AP | 0.010023 | [0.000617, 0.022010] | 0.017000 | 0.983000 | 2000 / 0 |
| mixtureVsCorrectedMixture | below2AP | 0.011790 | [0.005404, 0.018738] | 0.000000 | 1.000000 | 2000 / 0 |

The child scalar NLL, macro NLL and rating-0 AP intervals include zero; its Brier
and below-2 AP intervals favor improvement. Child compact NLL, macro NLL, Brier
and below-2 AP intervals favor improvement; its rating-0 AP interval includes
zero. Neither changes its failed original fold consistency check. For the child
mixture's primary contrast, the macro NLL upper endpoint is close to zero
(−.000039), and the AP0 lower endpoint is small (+.000543). The entire intervals,
not just their signs, matter.

Against the corrected mixture, child NLL, Brier and both AP intervals favor the
expanded mixture, while macro NLL spans [−.006263, +.000210]. Its fold-0 NLL
regression remains +.000150. The original child-mixture-versus-original-mixture
six-check pass remains the only primary pass; the new analysis does not replace
that fixed screen with an interval rule.

## Every child retained: leave-one-child-out NLL

Each row summarizes all 52 deletions for the same pooled comparison. These are
influence diagnostics, not a selection or exclusion policy. Full child IDs,
removed/remaining counts and all five fold contributions are in the JSON artifact.

| Fitting regime / contrast | Minimum NLL Δ | Maximum NLL Δ | Below zero | Above zero | Exactly zero |
| --- | --- | --- | --- | --- | --- |
| all-age/scalars | 0.000470 | 0.001048 | 0 | 52 | 0 |
| all-age/pca16-scalars | -0.001309 | -0.000610 | 52 | 0 | 0 |
| all-age/equal-mixture | -0.000839 | -0.000260 | 52 | 0 | 0 |
| all-age/mixtureVsCorrectedMixture | -0.000507 | 0.000077 | 51 | 1 | 0 |
| child-only/scalars | -0.002603 | -0.000857 | 52 | 0 | 0 |
| child-only/pca16-scalars | -0.004280 | -0.002505 | 52 | 0 | 0 |
| child-only/equal-mixture | -0.003230 | -0.001570 | 52 | 0 | 0 |
| child-only/mixtureVsCorrectedMixture | -0.003166 | -0.001409 | 52 | 0 | 0 |

All four child-trained contrasts remain favorable after removing any one child.
All-age scalar remains unfavorable in all 52 deletions. All-age compact and
primary mixture remain favorable in every deletion, although their bootstrap
intervals include zero; those are different diagnostics. All-age mixture versus
corrected mixture changes sign in one deletion. No child is removed from any
reported primary or secondary result.

## All 23 sounds: mixture NLL intervals and support

These tables show both mixture references in each fitting regime. The complete
artifact also retains all 23 scalar/compact intervals, every replicate and their
support. All phone intervals have 2,000 valid/zero undefined draws. A sound's
position count and three-class vote totals do not represent independent people.

### all-age fitting

| Phone | Positions | Children | Votes 0 / 1 / 2 | Primary NLL Δ | Primary interval | Secondary NLL Δ | Secondary interval |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B | 236 | 51 | 13 / 3 / 1164 | 0.000153 | [-0.002414, 0.003245] | 0.000322 | [-0.002248, 0.003357] |
| CH | 42 | 29 | 8 / 2 / 200 | -0.004450 | [-0.012188, 0.002374] | -0.003659 | [-0.011397, 0.003371] |
| D | 322 | 52 | 37 / 27 / 1546 | 0.003770 | [-0.003163, 0.009134] | 0.004128 | [-0.002784, 0.009488] |
| DH | 333 | 52 | 29 / 97 / 1539 | 0.004977 | [-0.000610, 0.010580] | 0.005864 | [0.000526, 0.011173] |
| F | 191 | 51 | 5 / 2 / 948 | -0.003550 | [-0.006035, -0.000523] | -0.003600 | [-0.006057, -0.000622] |
| G | 195 | 52 | 1 / 2 / 972 | -0.000532 | [-0.002576, 0.001467] | -0.000133 | [-0.002166, 0.001865] |
| HH | 237 | 52 | 7 / 2 / 1176 | -0.004648 | [-0.009365, -0.000338] | -0.004828 | [-0.009563, -0.000481] |
| JH | 76 | 31 | 13 / 1 / 366 | -0.004957 | [-0.015672, 0.005424] | -0.003249 | [-0.014498, 0.007803] |
| K | 330 | 52 | 9 / 7 / 1634 | -0.003937 | [-0.007854, -0.000396] | -0.003591 | [-0.007536, -0.000142] |
| L | 357 | 52 | 60 / 16 / 1709 | -0.001050 | [-0.007019, 0.005344] | -0.001044 | [-0.007079, 0.005396] |
| M | 341 | 51 | 32 / 35 / 1638 | 0.002096 | [-0.002510, 0.006401] | 0.002007 | [-0.002595, 0.006261] |
| N | 402 | 52 | 52 / 9 / 1949 | 0.000339 | [-0.004951, 0.005601] | 0.000522 | [-0.004740, 0.005866] |
| NG | 119 | 48 | 10 / 8 / 577 | -0.006326 | [-0.012558, -0.000667] | -0.005822 | [-0.011861, -0.000338] |
| P | 153 | 50 | 15 / 10 / 740 | 0.010464 | [0.004794, 0.017490] | 0.010687 | [0.005039, 0.017739] |
| R | 304 | 51 | 60 / 22 / 1438 | -0.001110 | [-0.007195, 0.005316] | -0.000557 | [-0.006861, 0.005856] |
| S | 378 | 52 | 35 / 10 / 1845 | -0.003188 | [-0.006412, -0.000549] | -0.002960 | [-0.006088, -0.000251] |
| SH | 134 | 49 | 18 / 7 / 645 | 0.011987 | [0.004226, 0.020165] | 0.011965 | [0.004584, 0.019525] |
| T | 378 | 52 | 27 / 19 / 1844 | -0.004577 | [-0.009834, -0.000078] | -0.004016 | [-0.009381, 0.000373] |
| TH | 75 | 40 | 19 / 75 / 281 | 0.005534 | [-0.006995, 0.016724] | 0.006849 | [-0.005434, 0.018126] |
| V | 200 | 49 | 17 / 76 / 907 | -0.010020 | [-0.017739, -0.002133] | -0.008997 | [-0.016703, -0.001304] |
| W | 323 | 51 | 18 / 4 / 1593 | 0.003620 | [-0.000317, 0.008281] | 0.003709 | [-0.000266, 0.008384] |
| Y | 190 | 49 | 9 / 6 / 935 | -0.001062 | [-0.003366, 0.001569] | -0.000979 | [-0.003336, 0.001685] |
| Z | 338 | 52 | 38 / 265 / 1387 | -0.004861 | [-0.011401, 0.001265] | -0.004071 | [-0.010711, 0.002000] |

### child-only fitting

| Phone | Positions | Children | Votes 0 / 1 / 2 | Primary NLL Δ | Primary interval | Secondary NLL Δ | Secondary interval |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B | 236 | 51 | 13 / 3 / 1164 | -0.003679 | [-0.006986, -0.000344] | -0.003349 | [-0.006730, 0.000126] |
| CH | 42 | 29 | 8 / 2 / 200 | -0.002491 | [-0.022711, 0.013594] | -0.001056 | [-0.020673, 0.014227] |
| D | 322 | 52 | 37 / 27 / 1546 | 0.000253 | [-0.004424, 0.004510] | 0.000322 | [-0.004263, 0.004481] |
| DH | 333 | 52 | 29 / 97 / 1539 | 0.004549 | [-0.003930, 0.012032] | 0.004118 | [-0.004604, 0.011767] |
| F | 191 | 51 | 5 / 2 / 948 | -0.002371 | [-0.005427, 0.000618] | -0.002648 | [-0.005744, 0.000256] |
| G | 195 | 52 | 1 / 2 / 972 | -0.000408 | [-0.002313, 0.001105] | -0.000399 | [-0.002340, 0.001148] |
| HH | 237 | 52 | 7 / 2 / 1176 | -0.001745 | [-0.006643, 0.003556] | -0.001766 | [-0.006592, 0.003369] |
| JH | 76 | 31 | 13 / 1 / 366 | 0.005410 | [-0.002511, 0.013382] | 0.007678 | [-0.001298, 0.017005] |
| K | 330 | 52 | 9 / 7 / 1634 | -0.002718 | [-0.009183, 0.002270] | -0.002730 | [-0.009150, 0.002159] |
| L | 357 | 52 | 60 / 16 / 1709 | -0.003260 | [-0.009918, 0.003226] | -0.003309 | [-0.010438, 0.003376] |
| M | 341 | 51 | 32 / 35 / 1638 | -0.001400 | [-0.004262, 0.001521] | -0.001662 | [-0.004724, 0.001308] |
| N | 402 | 52 | 52 / 9 / 1949 | -0.000497 | [-0.005543, 0.004505] | -0.000424 | [-0.005507, 0.004678] |
| NG | 119 | 48 | 10 / 8 / 577 | -0.009420 | [-0.018647, -0.002468] | -0.009204 | [-0.018625, -0.002055] |
| P | 153 | 50 | 15 / 10 / 740 | -0.004743 | [-0.021569, 0.006276] | -0.004782 | [-0.021728, 0.006238] |
| R | 304 | 51 | 60 / 22 / 1438 | -0.013728 | [-0.024213, -0.005150] | -0.013477 | [-0.024248, -0.004654] |
| S | 378 | 52 | 35 / 10 / 1845 | -0.001493 | [-0.005760, 0.001961] | -0.001527 | [-0.006038, 0.001953] |
| SH | 134 | 49 | 18 / 7 / 645 | -0.003126 | [-0.021958, 0.011004] | -0.002059 | [-0.021493, 0.012296] |
| T | 378 | 52 | 27 / 19 / 1844 | -0.014747 | [-0.024513, -0.007234] | -0.014842 | [-0.024623, -0.007312] |
| TH | 75 | 40 | 19 / 75 / 281 | 0.005744 | [-0.017604, 0.023295] | 0.004931 | [-0.018615, 0.022396] |
| V | 200 | 49 | 17 / 76 / 907 | -0.012357 | [-0.022213, -0.003417] | -0.011411 | [-0.021522, -0.002092] |
| W | 323 | 51 | 18 / 4 / 1593 | 0.008155 | [0.000322, 0.018520] | 0.007904 | [0.000347, 0.017817] |
| Y | 190 | 49 | 9 / 6 / 935 | 0.000633 | [-0.003225, 0.004440] | 0.001172 | [-0.002727, 0.004828] |
| Z | 338 | 52 | 38 / 265 / 1387 | -0.006139 | [-0.010187, -0.002050] | -0.005710 | [-0.009736, -0.001542] |

The child primary mixture has favorable NLL intervals for B, T, V, Z, R and NG;
W has an unfavorable interval. Against the corrected mixture, T, V, Z, R and NG
remain favorable and W remains unfavorable. Other child phone intervals include
zero. All-age primary mixture has favorable intervals for T, K, F, V, S, HH and NG,
but P and SH worsen; its stronger secondary comparison also has an unfavorable
DH interval. These are unadjusted descriptive comparisons, not a reason to select
favorable sounds or deploy separate per-sound weights.

## Verification and artifacts

The four new Python files and protocol were frozen before any actual resampling.
Root and a separate native GPT-6 Astra reviewer each passed all 14 synthetic tests.
The source/spec review found no blockers. Tests cover explicit duplicated rows and
five-vote numerical oracles, tied scores, absent phones/classes, stable-log underflow,
integer paired sampling, fold totals, intervals, all-fold/child influence, exact
historical joins, changed labels, complete stable arrays, exclusive outputs and
no-resampling declaration. All prior sources remain unchanged.

Preflight verified 40,319 bindings and all eight complete matched inputs while
analysis, sampling and endpoint preparation were forbidden. Root's separate audit
implementation passed 796 synthetic checks with maximum error 4.44e-16 against
the helper, including independent Brier, tied-vote ranking, manual quantiles,
phone contrasts and influence. Actual calculation completed all eight contrasts.
Exact offline reconstruction and independent actual-artifact verification both
finish with exit zero. The independent audit performs 1,240,048 checks, reproduces
the complete PCG64 matrix exactly and checks all 80,000 pooled and 368,000 phone
replicate contrasts, manual quantiles, null counts, support, all fold contributions,
all child deletions and original consistency decisions. Maximum numerical error
is 2.22e-16 with absolute/relative tolerances 2e-12/2e-11. It verifies 40,319 input
bindings and rehashes 18,493 unique paths afterward. It imports no project scoring
or analysis code. No actual calculation or independent artifact audit failed.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-expanded-uncertainty-v1/plan.json): `347070d614db0ad885e072181fe076bbffcd394882a50975b37240fe9fca8ebf`.
- [Complete report](../../research/audio-head/outputs/multiphone-20260927/lexical-expanded-uncertainty-v1/report.json): `5d6e693cfe1ce7bb1b8cd4c5be604524226ead6c21b92def72f5602b99bf3d1c`.
- [Independent artifact audit](../../work/lexical-expanded-uncertainty-audit-20260927/result.json).
- [Source review](../../work/lexical-expanded-uncertainty-audit-20260927/source-review.json) and [independent synthetic check](../../work/lexical-expanded-uncertainty-audit-20260927/synthetic-result.json).

## Decision and next step

Retain the expanded child mixture as a promising development candidate. Its
primary average gain is robust to these fixed resampling and deletion diagnostics,
while the stronger reference, individual folds and sound-specific regressions
remain explicit. Existing bundles and learner judgments are unchanged.

The next bounded investigation should explain the uneven per-sound response,
including W, through the existing fitting support, class/occurrence composition
and complete child/phone loss contributions. Include all 23 sounds and retain
all observations. Do not infer a bad recording, remove examples or assign per-sound
weights from these results alone. No such new diagnosis is claimed here.

Expert produced-phone labels, ages 2–5 and established speech-sound-disorder
coverage remain absent. No author-test, audio/encoder/model inference, training,
Colab allocation or app behavior changed. App builds and UI tests were not run
for this isolated saved-prediction analysis. The full improvement goal remains active.
