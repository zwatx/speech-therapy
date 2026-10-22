# Noise sensitivity: smaller average movements, unresolved large shifts

The corrected mixture has slightly lower mean child total variation than the
existing mixture: .030523→.030329 with all-age training and .017917→.017774
with child-only training. However, the worst child shift increases
.881108→.887614 in the all-age regime and stays .691463 in the child-only
regime. Child argmax changes are 58→57 and 10→11 respectively. These mixed
stability findings do not establish more accurate noisy predictions or change
the failed primary quality screen from the clean comparison.

This study measures prediction movement under one fixed 20 dB synthetic white-noise
condition. It does not measure transformed-recording accuracy or establish that
more stable predictions are more correct. No human ratings were transferred to
noisy recordings, and no supervised noisy metric or promotion gate was used.

The [protocol](multiphone-lexical-noise-protocol.md) retains both training regimes,
all 50 canonical speaker/word cells, 14,837 eligible positions from 125 speakers,
and all 5,654 child positions from 52 children aged 6–12. Each position uses its
original held-out head and original whole-utterance word exclusions. All 23
phones remain, including empty/null slices within smaller groups.

The existing noise cache uses its previously fixed seed and extraction recipe.
Its complete producer lineage, file hashes, every clip-to-array join and canonical
identity were checked. Clean feature source and recipe hashes match the current
models. The new forward path takes only arrays, offsets and canonical phone IDs.
Saved head weights, normalization, PCA basis/center and correction remain frozen;
no model fitting, new encoder inference, audio regeneration or Colab allocation
is performed. Clean exact replay precedes every noisy prediction phase.

## How to read the results

TV is half the sum of absolute probability changes, from zero for identical
distributions to one for disjoint distributions. Expected-rating movement uses
class values 0, 1 and 2. Argmax counts refer to model-class changes, not diagnosed
pronunciation errors. Every mixture is compared with its own clean prediction.
Paired differences are corrected-mixture minus existing-mixture. Negative TV
movement differences describe less movement only. Maxima differences subtract
the two slice maxima; they are not maxima of paired differences. Pooled means
weight positions equally. Lower/tied/higher counts use fixed tolerance 1e-12.

## ages6to12

| Regime / mixture | Positions | Speakers | Mean TV | Max TV | Mean absolute rating shift | Argmax changes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all-age / existingMixture | 5654 | 52 | 0.030523 | 0.881108 | 0.054925 | 58 |
| all-age / correctedMixture | 5654 | 52 | 0.030329 | 0.887614 | 0.054573 | 57 |
| child-only / existingMixture | 5654 | 52 | 0.017917 | 0.691463 | 0.028490 | 10 |
| child-only / correctedMixture | 5654 | 52 | 0.017774 | 0.691463 | 0.028260 | 11 |

## allAges

| Regime / mixture | Positions | Speakers | Mean TV | Max TV | Mean absolute rating shift | Argmax changes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all-age / existingMixture | 14837 | 125 | 0.037057 | 0.895422 | 0.068058 | 306 |
| all-age / correctedMixture | 14837 | 125 | 0.036817 | 0.895427 | 0.067618 | 310 |
| child-only / existingMixture | 14837 | 125 | 0.020287 | 0.770126 | 0.032964 | 53 |
| child-only / correctedMixture | 14837 | 125 | 0.020117 | 0.770126 | 0.032680 | 51 |

## ages13plus

| Regime / mixture | Positions | Speakers | Mean TV | Max TV | Mean absolute rating shift | Argmax changes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| all-age / existingMixture | 9183 | 73 | 0.041080 | 0.895422 | 0.076144 | 248 |
| all-age / correctedMixture | 9183 | 73 | 0.040812 | 0.895427 | 0.075650 | 253 |
| child-only / existingMixture | 9183 | 73 | 0.021746 | 0.770126 | 0.035718 | 43 |
| child-only / correctedMixture | 9183 | 73 | 0.021560 | 0.770126 | 0.035402 | 40 |

## Child speaker-fold paired movement differences

| Regime / fold | Positions | Mean TV Δ | Maxima TV Δ | Mean absolute rating shift Δ | Argmax count Δ | Lower TV | Tied TV | Higher TV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all-age / 0 | 1036 | -0.000219 | -0.002912 | -0.000394 | 0 | 625 | 0 | 411 |
| all-age / 1 | 1072 | -0.000288 | 0.006506 | -0.000548 | -1 | 362 | 489 | 221 |
| all-age / 2 | 1492 | 0.000086 | 0.000000 | 0.000193 | 0 | 142 | 1222 | 128 |
| all-age / 3 | 971 | -0.000382 | -0.000508 | -0.000725 | -1 | 455 | 201 | 315 |
| all-age / 4 | 1083 | -0.000290 | 0.000000 | -0.000537 | 1 | 416 | 463 | 204 |
| child-only / 0 | 1036 | -0.000234 | 0.006417 | -0.000308 | 0 | 391 | 408 | 237 |
| child-only / 1 | 1072 | -0.000071 | 0.000000 | -0.000112 | 0 | 493 | 252 | 327 |
| child-only / 2 | 1492 | -0.000194 | 0.009206 | -0.000353 | 1 | 918 | 0 | 574 |
| child-only / 3 | 971 | -0.000037 | 0.000000 | -0.000068 | 0 | 108 | 788 | 75 |
| child-only / 4 | 1083 | -0.000149 | -0.001000 | -0.000249 | 0 | 432 | 418 | 233 |

## Complete child phone TV support

| Phone | Positions | Children | All-age existing | All-age corrected | All-age Δ | Child-only existing | Child-only corrected | Child-only Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 51 | 0.019487 | 0.019324 | -0.000163 | 0.012306 | 0.012161 | -0.000145 |
| P | 153 | 50 | 0.025621 | 0.025226 | -0.000395 | 0.013914 | 0.013661 | -0.000253 |
| M | 341 | 51 | 0.034259 | 0.034082 | -0.000177 | 0.021324 | 0.021137 | -0.000187 |
| T | 378 | 52 | 0.020184 | 0.019934 | -0.000250 | 0.010359 | 0.010280 | -0.000078 |
| D | 322 | 52 | 0.037017 | 0.036936 | -0.000080 | 0.019413 | 0.019338 | -0.000075 |
| N | 402 | 52 | 0.022516 | 0.022435 | -0.000081 | 0.013704 | 0.013641 | -0.000063 |
| K | 330 | 52 | 0.016498 | 0.016354 | -0.000144 | 0.007300 | 0.007295 | -0.000005 |
| G | 195 | 52 | 0.016412 | 0.016251 | -0.000161 | 0.005758 | 0.005784 | 0.000026 |
| F | 191 | 51 | 0.028585 | 0.028444 | -0.000140 | 0.010910 | 0.010718 | -0.000192 |
| V | 200 | 49 | 0.055375 | 0.055036 | -0.000339 | 0.030693 | 0.030164 | -0.000529 |
| S | 378 | 52 | 0.035114 | 0.034750 | -0.000364 | 0.019581 | 0.019520 | -0.000060 |
| Z | 338 | 52 | 0.058732 | 0.058712 | -0.000020 | 0.052826 | 0.052536 | -0.000290 |
| SH | 134 | 49 | 0.024610 | 0.024134 | -0.000476 | 0.018370 | 0.017852 | -0.000518 |
| CH | 42 | 29 | 0.070319 | 0.070091 | -0.000227 | 0.017006 | 0.016689 | -0.000317 |
| JH | 76 | 31 | 0.051902 | 0.051334 | -0.000568 | 0.020122 | 0.019525 | -0.000598 |
| L | 357 | 52 | 0.032430 | 0.032313 | -0.000118 | 0.017231 | 0.017185 | -0.000046 |
| R | 304 | 51 | 0.049048 | 0.048630 | -0.000418 | 0.029552 | 0.029337 | -0.000215 |
| W | 323 | 51 | 0.012093 | 0.012024 | -0.000069 | 0.003730 | 0.003650 | -0.000080 |
| Y | 190 | 49 | 0.009434 | 0.009117 | -0.000317 | 0.005818 | 0.005591 | -0.000226 |
| HH | 237 | 52 | 0.008123 | 0.008105 | -0.000017 | 0.005698 | 0.005664 | -0.000033 |
| TH | 75 | 40 | 0.080268 | 0.080077 | -0.000191 | 0.051436 | 0.051565 | 0.000128 |
| DH | 333 | 52 | 0.035401 | 0.035291 | -0.000110 | 0.021127 | 0.020979 | -0.000147 |
| NG | 119 | 48 | 0.028179 | 0.027845 | -0.000335 | 0.016108 | 0.016079 | -0.000029 |

## Pooled child paired differences

| Regime | Mean TV Δ | Maxima TV Δ | Mean absolute rating shift Δ | Argmax count Δ | Lower TV | Tied TV | Higher TV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all-age | -0.000193 | 0.006506 | -0.000353 | -1 | 2000 | 2375 | 1279 |
| child-only | -0.000142 | 0.000000 | -0.000230 | 1 | 2342 | 1866 | 1446 |

## What the averages do and do not show

All-age fitting has lower mean child TV in four speaker folds, but fold 2
increases by .000086. Child-only fitting has lower mean child TV in all five
folds. Both regimes have lower means in all five child word groups. Across
individual children, means decrease for 40 of 52 with all-age fitting and
42 of 52 with child-only fitting; the other 12 and 10 increase, using the
same 1e-12 descriptive tolerance. No child is removed.

All 23 all-age-trained child phone means decrease. Child-only means decrease
for 21 phones but increase for G and TH. The paired position counts retain
substantial heterogeneity: 2,000 lower / 2,375 tied / 1,279 higher TV with
all-age fitting; 2,342 / 1,866 / 1,446 with child-only fitting. These are
positions from the same 52 children, not additional independent participants.

Mean absolute expected-rating movement decreases .054925→.054573 and
.028490→.028260 for children. Mean signed expected-rating shifts remain
negative: -.030506→-.030252 and -.013155→-.013088, indicating that this noise
condition shifts average model output toward lower rating classes. It does
not establish an actual change in pronunciation. Maximum absolute child
expected-rating movement rises 1.753576→1.769237 in the all-age regime and
stays 1.336820 in the child-only regime, on a class scale spanning 0–2.

Whole-population mean TV also decreases, while all-age-trained argmax changes
increase 306→310; child-only changes decrease 53→51. The age-13-plus table
retains the corresponding differences. Large individual changes remain even
where means move slightly less. Stability cannot identify which original or
noisy judgment is correct, and a nearly constant model could be stable without
being useful. There are no supervised noisy metrics, statistical significance
claims, pass/fail sensitivity gates, new rejection thresholds or promotions.

## Verification and artifacts

Twelve focused tests pass. They cover direct label-free scalar inference,
zero/nonzero projection casts, two-batch execution, saved-state preservation,
invalid inputs, hand-calculated movement and argmax ties, extreme stable logs,
empty support, paired maxima interpretation, canonical feature identity and
phase-order guards. An initial test caught accidental inclusion of unsupported
ZH through the broader 24-token inventory; the runner now uses the established
23-phone inventory. The correction preceded declaration. Separate GPT-6 Astra
source/protocol review and an independent run of all twelve tests passed.

The complete producer validator checked 43,054 pinned references, all 2,495
recordings and every 14,837-row unit-to-array join. The new no-inference
preflight checked 44,303 inputs and 50 jobs with head prediction, mixture
calculation, encoder construction and training forbidden. The independent
cache-only preflight also checked all 2,495 units: 124,783 checks across 13,557
unique paths, without head replay. Hashes and producer records verify saved
provenance; they do not re-extract audio or verify true acoustic phone boundaries.

Declaration, all 50 clean anchor cells, all 50 noisy cells and complete summary
calculation finished with exit zero. Every clean scalar/PCA/corrected component
matches historical raw float32 probabilities and stable float64 probabilities
and logs exactly; both clean mixtures match their existing saved vectors exactly.
The complete clean freeze preceded the noisy phase. Independent verification
using functional tensor operations, without importing the study prediction core
or model class, passed:

- Clean anchors: 141,396 checks, 150 component replays and 100 independent mixtures, all exact against saved and historical predictions.
- Noisy predictions: 140,300 checks, 150 component replays and 100 independent mixtures, all exact.
- Full report: 1,698,153 checks covering per-position movements, paired differences and all age/phone/cell/fold/word-group/child summaries, memberships and null support. Expected-rating movement and reductions use separate arithmetic, with floating-point tolerance; replayed probabilities are exact.

The executed auditor sources remain unchanged and hash-bound after the first
phase audit. No actual training trajectory or new encoder/audio extraction is
claimed. Exact offline report reconstruction completed with exit zero.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-noise-v1/plan.json): `64a1ce5bfab4de1f0601ddb410cf58b4f6d5981aea18bb6c8220773046f3314e`
- [Clean freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-noise-v1/anchors-freeze.json): `01b89288d8b457fcb71f94e958150f0a946023f3d54c7d35364777f64353e791`
- [Noisy freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-noise-v1/noise-freeze.json): `98d74c0f1b34caa6535f32cc409000f244d1ac924a91d433034d2ac5665a9af3`
- [Full report](../../research/audio-head/outputs/multiphone-20260927/lexical-noise-v1/report.json): `5a74261d289fde7ee580e74c546038ad26d57b58e488941480c42df7243e517c`
- Independent [source](../../work/lexical-noise-audit-20260927/source-review.json), [clean](../../work/lexical-noise-audit-20260927/anchors-result.json), [noisy](../../work/lexical-noise-audit-20260927/noise-result.json) and [metric](../../work/lexical-noise-audit-20260927/report-result.json) receipts.

From `research/audio-head`, run `.venv/bin/python -m lexical_noise.study`.
Its separate phases are `declare`, `anchors`, `noise`, `audit` and `verify`.
The plan and relevant complete preceding freeze require their SHA256 values.
All source/tests/protocol files are immutable after declaration.

## Next evidence and remaining limits

Close this fixed noise comparison without a noise-level or withholding-threshold
search. The next concrete data direction is to inventory additional already
extracted consonant occurrences under the current whole-utterance word and
speaker exclusions. The [expanded feature export](multiphone-position-phonetic-report.md)
contains 28,227 positions; the previous [expansion comparison](multiphone-position-training-report.md)
used five speaker folds and full 1,037-feature heads, and had mixed results.
It does not establish what those additional occurrences do under the current
compact lexical design. First check exact original-row/feature joins, permitted
speaker membership and per-cell fitting/selection support. No new expanded
lexical training or resulting quality gain is claimed here.

This condition does not cover rooms, microphones, clipping, volume changes or
natural short-word recordings. Outcomes and speakers have been reused across
studies. Corpus ratings are subjective; no produced-phone ground truth,
established child-SSD cohort or age-2–5 evidence is added. Author-test stays
closed and learner judgments remain disabled. App builds/UI tests were not run
because all changes are isolated research code and reports.
