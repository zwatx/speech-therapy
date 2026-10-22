# Fixed temperature-calibration result

A single shared temperature did not pass the declared consistency screen for
either existing model. On held-out child speakers, the child-only model's
per-rater log loss improves from .172332 to .171156, but its rating-0 average
precision falls from .111119 to .107377 and two folds have worse log loss.
The all-age model's child log loss worsens from .169242 to .170879. Neither
correction replaces the existing research bundles or enables learner judgments.

The [protocol](multiphone-temperature-protocol.md) fixed ten scalar fits:
all-age and child-only target-plus-scalars models across five existing speaker
folds. Each temperature was fitted using children in the original selected
inner model's validation predictions. All ten checkpoints were actually replayed
exactly before fitting. The complete correction set was frozen before the
separate outer-evaluation command opened outer prediction payloads.

This tests an adaptation of [temperature scaling](https://proceedings.mlr.press/v70/guo17a.html)
to five-rater soft corpus labels. It is an exploratory probability correction,
not an estimate of clinically correct pronunciation. The same inner validation
sets previously selected checkpoints, and these outer development folds were
already examined in earlier research. Author-test data stayed closed.

## Child results, all original eligible positions

All comparisons below use the same 5,654 positions from 52 children ages 6–12
and all 23 consonants. “Baseline” is the explicitly float64-normalized original
probability vector. Lower NLL and Brier are better; higher AP is better. AP in
this table pools corpus votes across phones; the saved report also retains
separate per-phone and equal-phone macro ranking results.

| Model / vector | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / baseline | 0.169242 | 0.175675 | 0.079533 | 0.121307 | 0.205399 |
| all-age / temperature | 0.170879 | 0.177421 | 0.079462 | 0.121313 | 0.205158 |
| child-only / baseline | 0.172332 | 0.180729 | 0.077457 | 0.111119 | 0.210628 |
| child-only / temperature | 0.171156 | 0.179905 | 0.077420 | 0.107377 | 0.210079 |

The all-age correction passes only the pooled child Brier and rating-0 AP
parts of the screen; it loses on pooled NLL, macro NLL, below-2 AP and four
fold NLL values. The child-only correction improves pooled NLL, macro NLL and
Brier but fails the every-fold NLL and both pooled AP requirements. Average
probability improvement does not establish better rare-rating detection.
Positive temperatures preserve all argmax labels, but multiclass event ranking
can still change, particularly when pooling different fold temperatures.

## Frozen temperatures and fold behavior

Each scalar uses the original five-vote distribution for every child target in
that fold's inner validation set. Per-fold membership is 545/967/784/753/1,196
positions from 5/9/7/7/11 children. The sets overlap across folds and represent
2,954 distinct positions from 27 children; summing fold counts would overstate
independent support. Every fold retains all 23 phones.

All ten constrained optima are interior to the fixed inverse-temperature
bounds [.05,20]. None required a new bound or outcome-driven extension. The
improvement in fitting NLL is expected from optimization and is not the test
of generalization. Outer NLL changes below are corrected minus baseline.

| Head / fold | Temperature | Inner NLL before | Inner NLL after | Outer child NLL change |
| --- | ---: | ---: | ---: | ---: |
| all-age / 0 | 0.917848 | 0.191103 | 0.189898 | +0.000777 |
| all-age / 1 | 0.920075 | 0.153472 | 0.152412 | +0.000285 |
| all-age / 2 | 0.907409 | 0.143220 | 0.141848 | +0.004872 |
| all-age / 3 | 1.017181 | 0.219371 | 0.219319 | -0.000200 |
| all-age / 4 | 0.921556 | 0.188087 | 0.186960 | +0.000990 |
| child-only / 0 | 0.964757 | 0.166073 | 0.165859 | -0.000116 |
| child-only / 1 | 0.989685 | 0.145071 | 0.145055 | +0.000324 |
| child-only / 2 | 1.010985 | 0.139232 | 0.139214 | -0.000684 |
| child-only / 3 | 1.222018 | 0.223166 | 0.215032 | -0.007284 |
| child-only / 4 | 0.983561 | 0.183083 | 0.183031 | +0.001123 |

The largest child-only improvement is fold 3; folds 1 and 4 worsen. The model
receiving each correction is an outer refit, rather than the inner model on
which that correction was fitted. These data do not distinguish correction
overfitting from changes caused by refitting the head or other fold variation.

## Probability reliability and unfamiliar words

Observed child vote frequencies are .018819 for rating 0 and .043757 for
ratings below 2. Both corrections move their average lower-rating predictions
toward those frequencies, but matching an overall average is not sufficient.
For example, the all-age corrected below-2 mean nearly matches prevalence,
while its binned residual and NLL worsen.

| Model / event | Baseline mean | Corrected mean | Baseline binned residual | Corrected binned residual |
| --- | ---: | ---: | ---: | ---: |
| all-age / rating0 | 0.028220 | 0.025133 | 0.009401 | 0.008205 |
| all-age / ratingBelow2 | 0.049488 | 0.043738 | 0.009765 | 0.011776 |
| child-only / rating0 | 0.013304 | 0.014506 | 0.006482 | 0.005821 |
| child-only / ratingBelow2 | 0.035408 | 0.037940 | 0.010841 | 0.009730 |

Residuals use ten fixed equal-width bins and are descriptive, not a calibration
certificate. Every age/phone/fold table retains empty bins and distinct-child
support. Sparse high-probability bins do not create independent participants.

The unseen-word slices use each original outer fitting vocabulary. They are
not word-disjoint experiments, and the two fitting regimes have different
unseen sets. In each model's child unseen slice:

| Model | Positions / children | NLL before → after | Rating-0 AP before → after | Below-2 AP before → after |
| --- | ---: | --- | --- | --- |
| all-age | 614 / 51 | 0.295383 → 0.304781 | 0.222299 → 0.221705 | 0.317769 → 0.315563 |
| child-only | 914 / 52 | 0.272688 → 0.271542 | 0.171146 → 0.162467 | 0.272422 → 0.265477 |

## Every phone's child support and log-loss change

The three vote columns are original ratings 0/1/2, not independent children or
majority labels. Changes are corrected minus baseline NLL. All per-phone ranking
and reliability results are retained in the complete JSON, including undefined
ranking cells; no phone was removed based on its result.

| Phone | Positions | Votes 0 / 1 / 2 | All-age NLL change | Child-only NLL change |
| --- | ---: | --- | ---: | ---: |
| B | 236 | 13 / 3 / 1164 | +0.000967 | -0.002935 |
| CH | 42 | 8 / 2 / 200 | +0.001643 | +0.007391 |
| D | 322 | 37 / 27 / 1546 | +0.003041 | -0.002471 |
| DH | 333 | 29 / 97 / 1539 | +0.003115 | -0.004486 |
| F | 191 | 5 / 2 / 948 | +0.000067 | +0.001294 |
| G | 195 | 1 / 2 / 972 | -0.001620 | -0.001468 |
| HH | 237 | 7 / 2 / 1176 | +0.001517 | -0.000694 |
| JH | 76 | 13 / 1 / 366 | +0.001178 | +0.000959 |
| K | 330 | 9 / 7 / 1634 | +0.001234 | -0.001447 |
| L | 357 | 60 / 16 / 1709 | +0.002805 | -0.001020 |
| M | 341 | 32 / 35 / 1638 | +0.002912 | +0.005186 |
| N | 402 | 52 / 9 / 1949 | +0.004146 | +0.003195 |
| NG | 119 | 10 / 8 / 577 | +0.004406 | +0.001742 |
| P | 153 | 15 / 10 / 740 | +0.002542 | +0.003018 |
| R | 304 | 60 / 22 / 1438 | -0.000972 | -0.005209 |
| S | 378 | 35 / 10 / 1845 | +0.000149 | +0.000681 |
| SH | 134 | 18 / 7 / 645 | -0.001287 | -0.000754 |
| T | 378 | 27 / 19 / 1844 | +0.002318 | -0.000195 |
| TH | 75 | 19 / 75 / 281 | +0.009358 | -0.005188 |
| V | 200 | 17 / 76 / 907 | +0.001127 | -0.004487 |
| W | 323 | 18 / 4 / 1593 | +0.001854 | +0.000470 |
| Y | 190 | 9 / 6 / 935 | +0.000422 | -0.000936 |
| Z | 338 | 38 / 265 / 1387 | -0.000756 | -0.011585 |

All-age and ages-13-plus outcomes also remain reported. On all ages, NLL changes
from .216152 to .219326 for the all-age head and .304056 to .296987 for the
child-only head. Those summaries do not override the child endpoints or establish
adult or clinical suitability.

## Numerical correctness and verification

Saved float32 probability sums have small roundoff. Explicit normalization
changes an individual value by at most 1.20e-7 for the all-age model and 8.87e-8
for the child-only model. The child baseline NLL changes from raw historical
reporting by about -6.17e-10 and -1.49e-10, respectively. Raw historical vectors
and metrics are preserved alongside normalized and corrected outputs.

Independent source review caught a metric issue before real fitting: historical
NLL reporting uses a 1e-12 probability floor. Temperature scaling can cross that
floor. All new NLL, conditional NLL and entropy copies now use stable finite log
probabilities, including every word/age/phone slice. A synthetic regression has
exact NLL 137.9541 where the old capped calculation gives 27.6310. Neither actual
model's raw or corrected outer values falls below the old floor, but the new
implementation remains correct for that supported numerical case.

Sixteen focused tests pass. A separate 55-digit Decimal, derivative-free check
reproduced 24 synthetic optima with maximum inverse-temperature error 8.33e-17.
The ten actual selected checkpoints replayed saved inner predictions and metrics
exactly; no encoder was run or head refitted. A separate Python math/fsum
implementation reconstructed all ten actual scalar optima and objectives
exactly. Actual fitting, outer calculation and offline reconstruction completed
with exit zero. Independent saved-artifact review passed 264,534 checks across
both models, all five folds, pooled results and all age/phone/word slices.
Independent narrative review also passed. The [audit record](../../work/temperature-audit-20260927/audit-result.jsonl)
has SHA256 `846757fcb6cecaee9bd88c02987b2c1024fe952a265c10373f405faa84674483`.

Review limitation: the requested GPT-6 Astra review could not start because the
native agent tool hit its task limit. GPT-6 Sol independently reviewed the parent
agent's study runner and outputs; the parent separately verified Sol's numerical
core, including the high-precision reference checks. No Astra review is claimed.

No new audio, author-test access, purchases or Colab allocation occurred.
App builds and UI tests were not run because app behavior did not change.

## Decision and next step

Retain the four existing research bundles and keep learner pronunciation
judgments disabled. Do not extend the temperature search or select a correction
from these outer outcomes. The observed improvement in one proper-score average
comes with rare-rating ranking losses and inconsistent fold behavior.

The subsequent [same-head control](multiphone-temperature-transfer-report.md)
is now complete. It reused these exact frozen temperatures on the corresponding
original inner heads and the same outer speakers. Both screens still fail.
Refitting is not required for these failures; this development comparison does
not uniquely identify their causes or establish clinical calibration.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/temperature-v1/plan.json): `b2fc54f03e246b1678f3636e7f52e89caec0b7d353b229e23109f2ce0802be59`.
- [Frozen fits](../../research/audio-head/outputs/multiphone-20260927/temperature-v1/freeze.json): `73ecdda7f807896df94a1d69871dff5fa46ea329899c3be9f6ce3c00d1e43dac`.
- [Complete outer results](../../research/audio-head/outputs/multiphone-20260927/temperature-audit-v1/report.json): `9ab82dd8af7bfeedad2ee44204cce249ad07e699c3aef54fffbd630ee516ee33`.

Reconstruct all fits and outer metrics without head or encoder inference, from
`research/audio-head`:

```sh
.venv/bin/python -m rating_temperature.study verify \
  --plan outputs/multiphone-20260927/temperature-v1/plan.json \
  --plan-sha256 b2fc54f03e246b1678f3636e7f52e89caec0b7d353b229e23109f2ce0802be59 \
  --freeze outputs/multiphone-20260927/temperature-v1/freeze.json \
  --freeze-sha256 73ecdda7f807896df94a1d69871dff5fa46ea329899c3be9f6ce3c00d1e43dac \
  --output outputs/multiphone-20260927/temperature-audit-v1
```
