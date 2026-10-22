# Middle-layer candidate: fixed-seed confirmation

Completed September 27, 2026. **The fixed candidate fails confirmation.** Overall mixture NLL improves at all three new seeds, but rating-0 average precision worsens at seeds 17 and 29, and one speaker fold worsens at seed 17. Only seed 43 passes the complete per-seed screen. The existing packaged model remains retained.

The [frozen protocol](middle-layer-replication-protocol.md) required all three seeds to pass and an all-age guard. This was a repeatability study on the same 5,654 original positions, 1,037 recordings and 52 children ages 6–12, covering 23 consonants. It used 532/705/27,033 rating votes for classes 0/1/2. It does not provide independent participant confirmation.

## Same-seed mixture comparison

Each middle and final compact head is mixed equally with the same seed’s frozen scalar head. Lower NLL, macro-phone NLL and Brier are better; higher AP is better. Changes below are middle minus final.

| Seed | Final NLL | Middle NLL | Relative reduction | Rating-0 AP change | Below-2 AP change | Six-part screen | Compact NLL co-condition |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 17 | 0.178283 | 0.176687 | 0.90% | -0.000624 | +0.011520 | FAIL | PASS |
| 29 | 0.177644 | 0.176244 | 0.79% | -0.000657 | +0.011348 | FAIL | PASS |
| 43 | 0.176203 | 0.174983 | 0.69% | +0.001562 | +0.013586 | PASS | PASS |

All three seeds improve pooled mixture NLL, macro-phone NLL, Brier and below-2 AP. All three compact NLL co-conditions pass. The stronger target of at least 5% relative NLL reduction and +.01 rating-0 AP gain fails at every seed. No seed is selected for replacement.

| Mixture change | Seed 17 | Seed 29 | Seed 43 | Mean | Minimum | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| nll | -0.001597 | -0.001400 | -0.001220 | -0.001405 | -0.001597 | -0.001220 |
| macroNll | -0.000206 | -0.000815 | -0.000419 | -0.000480 | -0.000815 | -0.000206 |
| brier | -0.000685 | -0.000829 | -0.000731 | -0.000749 | -0.000829 | -0.000685 |
| rating0Ap | -0.000624 | -0.000657 | +0.001562 | +0.000094 | -0.000657 | +0.001562 |
| below2Ap | +0.011520 | +0.011348 | +0.013586 | +0.012152 | +0.011348 | +0.013586 |

The mean rating-0 AP change is slightly positive, but the predeclared decision requires each seed to pass. This mean is a descriptive statistic, not an ensemble or evidence that the failures can be ignored.

| Speaker fold | NLL change, seed 17 | Seed 29 | Seed 43 |
| --- | ---: | ---: | ---: |
| 0 | -0.003170 | -0.001719 | -0.003811 |
| 1 | -0.001685 | -0.001165 | -0.001630 |
| 2 | +0.000608 | -0.001340 | -0.000177 |
| 3 | -0.001611 | -0.000166 | -0.000221 |
| 4 | -0.003028 | -0.002514 | -0.000667 |

## Age and phone behavior

The all-age NLL guard passes: no age worsens at all three seeds. Age 6 worsens in one new seed; age 12 worsens in two. This guard only concerns NLL. **Age-6 rating-0 AP and macro-phone NLL worsen at all three seeds**, so the passing age guard does not establish age-6 nonregression on other endpoints. Ages 8 and 10 each contain only two children.

| Age | Children | Positions | NLL change, seed 17 | Seed 29 | Seed 43 | Seeds worse |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 13 | 1389 | -0.000055 | -0.000520 | +0.000350 | 1/3 |
| 7 | 10 | 1020 | -0.004503 | -0.002742 | -0.003157 | 0/3 |
| 8 | 2 | 232 | -0.000853 | -0.002464 | -0.001188 | 0/3 |
| 9 | 11 | 1191 | -0.002289 | -0.001462 | -0.000671 | 0/3 |
| 10 | 2 | 226 | -0.002671 | -0.002238 | -0.001748 | 0/3 |
| 11 | 7 | 792 | -0.001225 | -0.002094 | -0.002710 | 0/3 |
| 12 | 7 | 804 | +0.000175 | +0.000104 | -0.000680 | 2/3 |

| Age-6 change | Seed 17 | Seed 29 | Seed 43 |
| --- | ---: | ---: | ---: |
| macroNll | +0.001875 | +0.001380 | +0.001430 |
| rating0Ap | -0.014170 | -0.005119 | -0.005874 |
| below2Ap | -0.003263 | +0.003263 | +0.002979 |

Each seed worsens NLL for 11 of 23 phones. The number of children with worse NLL is 17, 18 and 18 at seeds 17, 29 and 43. Phone and child comparisons are descriptive; they were not used to select a seed, alter the recipe or change an age policy.

| Phone | Positions | Mean NLL change | Minimum | Maximum | Seeds worse |
| --- | ---: | ---: | ---: | ---: | ---: |
| B | 236 | +0.001931 | +0.000204 | +0.004174 | 3/3 |
| CH | 42 | +0.013139 | +0.004569 | +0.025857 | 3/3 |
| D | 322 | +0.001416 | +0.000053 | +0.002742 | 3/3 |
| DH | 333 | -0.001119 | -0.003616 | +0.000652 | 1/3 |
| F | 191 | +0.000402 | -0.000297 | +0.001407 | 2/3 |
| G | 195 | +0.000593 | +0.000253 | +0.001264 | 3/3 |
| HH | 237 | +0.001601 | +0.001138 | +0.001872 | 3/3 |
| JH | 76 | +0.001818 | -0.003178 | +0.005038 | 2/3 |
| K | 330 | +0.000629 | -0.000447 | +0.001234 | 2/3 |
| L | 357 | -0.000632 | -0.000986 | -0.000283 | 0/3 |
| M | 341 | -0.002120 | -0.003019 | -0.001324 | 0/3 |
| N | 402 | -0.000694 | -0.001423 | +0.000521 | 1/3 |
| NG | 119 | +0.002568 | -0.000804 | +0.004822 | 2/3 |
| P | 153 | -0.002523 | -0.004125 | -0.001479 | 0/3 |
| R | 304 | -0.002689 | -0.006261 | +0.000449 | 1/3 |
| S | 378 | -0.000419 | -0.001898 | +0.001495 | 1/3 |
| SH | 134 | -0.002796 | -0.004005 | -0.002018 | 0/3 |
| T | 378 | +0.001468 | +0.000947 | +0.002490 | 3/3 |
| TH | 75 | +0.004111 | +0.000741 | +0.010445 | 3/3 |
| V | 200 | -0.007089 | -0.008173 | -0.005928 | 0/3 |
| W | 323 | -0.002880 | -0.005633 | -0.000715 | 0/3 |
| Y | 190 | -0.001305 | -0.002336 | -0.000196 | 0/3 |
| Z | 338 | -0.016457 | -0.017038 | -0.015860 | 0/3 |

All per-seed pooled, fold, age, phone and child metrics, including event support and undefined subgroup AP values, are preserved in the [complete result](../../research/audio-head/outputs/multiphone-20260927/middle-layer-replication-v1/results.json). Its across-seed summaries include all 52 children, per-seed changes, regression counts and mean/minimum/maximum NLL changes.

## Controls and verification

The independent source review verified all 9,891 cached final feature vectors and scalar rows against the historical arrays, unchanged training sources and recipes, all 75 fitting partitions and speaker separation. Twelve tests passed, including exact reconstruction of all 88 discovery metric views and decisions.

Six predetermined scalar/final control cells were retrained at seeds 17, 29 and 43: six inner fits and six fresh refits. Selected epochs, model tensors and full historical outer predictions matched exactly. All 150 saved controls replayed exactly. New training then completed all 75 inner fits, all 75 fresh refits and all 75 outer prediction sets in separate frozen phases. The new and corresponding final-layer initial model tensors match in both fitting phases.

Final evaluation validated saved fitting lineage and exactly replayed selected and outer predictions for all 75 new heads and all 150 controls. CPU wall times, including each command’s preparation and checks, were 84.34 seconds for control parity, 161.59 for inner fitting, 86.93 for refitting, 34.94 for outer predictions and 101.83 for evaluation. No Colab allocation was needed. The [independent post-run review](../../work/middle-layer-replication-review-20260927/results-review.json) is recorded separately.

## Interpretation and next action

The [seed-7 discovery](middle-layer-results.md) showed a 0.84% NLL reduction and passed its screen; it is not included in the three-seed summaries. This replication supports a small repeatable loss reduction and better below-2 ranking, but it does not confirm the candidate as a general replacement. The unchanged equal-weight mixture does not consistently preserve rating-0 discrimination. The compact component also worsens macro-phone NLL at all three seeds despite improving its pooled NLL. These are useful failure details, not permission to retune this test.

This fixed recipe is closed as an automatic replacement. No new seeds, seed ensemble, age gating, threshold changes or alternative recipe were tried to rescue it. The existing package remains available, and the broader model-quality goal remains active. Further work needs a separately justified improvement aimed at rare-error and per-phone consistency. No author-test audio was opened; promotion, clinical use and learner-feedback eligibility remain false.

Evidence: [plan](../../research/audio-head/outputs/multiphone-20260927/middle-layer-replication-v1/plan.json), [control parity](../../research/audio-head/outputs/multiphone-20260927/middle-layer-replication-v1/controls-freeze.json), [inner freeze](../../research/audio-head/outputs/multiphone-20260927/middle-layer-replication-v1/inner-freeze.json), [refit freeze](../../research/audio-head/outputs/multiphone-20260927/middle-layer-replication-v1/refit-freeze.json), [outer freeze](../../research/audio-head/outputs/multiphone-20260927/middle-layer-replication-v1/outer-freeze.json), [source review](../../work/middle-layer-replication-review-20260927/source-review.json).
