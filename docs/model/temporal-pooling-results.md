# Temporal pooling candidate: fixed comparison

Completed September 27, 2026. **The fixed temporal candidate fails its development screen.** Its mixture lowers pooled negative log loss (NLL) at all three seeds, but individual speaker folds regress and age 8 regresses at every seed. The existing packaged research model remains the usable candidate. This experiment does not establish learner or clinical validity.

The [predeclared protocol](temporal-pooling-protocol.md) compares three final-layer means from the before, estimated interval, and after portions of each original window against its one-window mean. Both compact heads use 16 separately fitted PCA components plus the same 13 alignment scalars, the same 29-input head, the same three seeds and speaker/word partitions, and the same-seed scalar mixture. The estimated interval is not an observed produced-phone boundary. The study uses the same development cohort previously examined: 5,654 held-out positions from 1,037 recordings by 52 children ages 6–12, all 23 supported consonants, and 532/705/27,033 rating votes in classes 0/1/2. Its seeds do not constitute new participants.

## Primary comparison

Changes are temporal mixture minus historical final-mean mixture; lower NLL, macro-phone NLL and Brier are better, and higher average precision (AP) is better. Every seed improves pooled NLL and the temporal compact head alone also improves NLL. None passes the complete six-part mixture screen. The additional material target of at least 5% relative NLL improvement and +0.01 rating-0 AP improvement fails at every seed.

| Seed | Final mixture NLL | Temporal mixture NLL | Relative NLL reduction | Rating-0 AP change | Below-2 AP change | Failed screen checks |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 17 | 0.178283 | 0.177643 | 0.36% | -0.000885 | +0.000677 | One fold; rating-0 AP |
| 29 | 0.177644 | 0.176608 | 0.58% | +0.003294 | +0.002993 | One fold |
| 43 | 0.176203 | 0.175733 | 0.27% | +0.005039 | +0.000872 | Three folds; macro NLL; Brier |

The mean mixture NLL change is -0.000715, a descriptive average across optimization seeds. Compact-head NLL changes are -0.001539, -0.002087 and -0.001168. The equal-weight mixture does not preserve every compact-head gain. All three seeds were required to pass; a favorable mean cannot rescue a failed seed or subgroup guard.

| Speaker fold | Positions | Seed 17 NLL change | Seed 29 | Seed 43 |
| --- | ---: | ---: | ---: | ---: |
| 0 | 1,036 | +0.000358 | -0.000684 | +0.000108 |
| 1 | 1,072 | -0.000968 | -0.001291 | -0.001505 |
| 2 | 1,492 | -0.001408 | -0.002025 | -0.001612 |
| 3 | 971 | -0.000693 | +0.000469 | +0.000857 |
| 4 | 1,083 | -0.000164 | -0.001108 | +0.000383 |

## Ages and consonants

The predeclared all-age guard fails because age 8 worsens at all three seeds. There are only two age-8 children here, so this is a reason to avoid claiming universal benefit, not a reliable estimate for all eight-year-olds. Age 6 improves NLL at seeds 17 and 29, but worsens slightly at seed 43. Age-6 rating-0 AP changes are -0.001520, +0.006393, +0.004964, and its macro-phone NLL changes are -0.001700, -0.000036, +0.000819. Age-6 below-2 AP changes are -0.003265, +0.008248, -0.000388. These mixed endpoints preclude an age-6 nonregression claim.

| Age | Children | Positions | Seed 17 NLL change | Seed 29 | Seed 43 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 6 | 13 | 1,389 | -0.001490 | -0.001557 | +0.000091 |
| 7 | 10 | 1,020 | -0.001416 | -0.001680 | -0.002567 |
| 8 | 2 | 232 | +0.001843 | +0.000504 | +0.001391 |
| 9 | 11 | 1,191 | +0.000245 | -0.000183 | +0.000008 |
| 10 | 2 | 226 | -0.002771 | -0.001473 | -0.000442 |
| 11 | 7 | 792 | +0.000013 | -0.000335 | -0.000279 |
| 12 | 7 | 804 | -0.000258 | -0.001594 | -0.000223 |

The number of children whose NLL worsens is 23, 21 and 23 at seeds 17, 29 and 43. The corresponding number of consonants is 8, 7 and 11. CH and Y worsen at all three seeds; CH has only 42 held-out positions. The table gives each consonant's mean NLL change across seeds and the number of seeds with a positive change. Support and all per-seed phone and child metrics are in the [complete results](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-heads-v1/results.json).

| Consonant | Positions | Mean NLL change | Seeds worse |
| --- | ---: | ---: | ---: |
| B | 236 | +0.000538 | 1/3 |
| CH | 42 | +0.005043 | 3/3 |
| D | 322 | -0.000961 | 0/3 |
| DH | 333 | -0.001285 | 1/3 |
| F | 191 | +0.000151 | 2/3 |
| G | 195 | +0.000139 | 2/3 |
| HH | 237 | +0.001513 | 2/3 |
| JH | 76 | +0.002489 | 2/3 |
| K | 330 | -0.000641 | 0/3 |
| L | 357 | -0.000984 | 1/3 |
| M | 341 | -0.002163 | 0/3 |
| N | 402 | -0.002608 | 0/3 |
| NG | 119 | -0.001446 | 0/3 |
| P | 153 | -0.002878 | 0/3 |
| R | 304 | -0.000092 | 2/3 |
| S | 378 | -0.002237 | 0/3 |
| SH | 134 | +0.001038 | 2/3 |
| T | 378 | +0.000858 | 2/3 |
| TH | 75 | -0.003208 | 0/3 |
| V | 200 | +0.000485 | 2/3 |
| W | 323 | -0.001250 | 0/3 |
| Y | 190 | +0.000599 | 3/3 |
| Z | 338 | -0.001317 | 1/3 |

## Execution and interpretation

The [feature extraction report](temporal-pooling-feature-results.md) covers all 1,040 recordings and 9,891 expanded positions. The newly computed old-window means equal the historical cache exactly; the three-bin count-weighted reconstruction has zero maximum residual before float32 storage. There are no empty context bins in this cohort. The 16-component PCA, fit only on fitting rows in each training cell, retains 74.27–75.74% of the centered three-bin variance across inner and refit transforms. Component loading shares are descriptive, not evidence that one temporal block causally matters more.

The [training plan](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-heads-v1/plan.json) fixed seeds, partitions, recipe, comparisons and acceptance rules before fitting. All 150 historical control predictions were replayed, followed by 75 inner fits, 75 fresh refits and 75 complete outer prediction sets. The [control](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-heads-v1/controls-freeze.json), [inner](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-heads-v1/inner-freeze.json), [refit](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-heads-v1/refit-freeze.json) and [outer](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-heads-v1/outer-freeze.json) manifests bind each stage. The independent source review is [here](../../work/temporal-pooling-training-review-20260927/source-review.json). Training-phase elapsed times recorded by those manifests are 53.0, 305.4, 212.0 and 175.0 seconds respectively, including the phase checks.

The [independent post-fit review](../../work/temporal-pooling-training-review-20260927/results-review.json) found no execution or arithmetic blocker. It independently replayed all 75 new selected/outer heads and all 150 historical selected/outer controls, recomputed all 264 subgroup views for five models, and checked screens, support and all 150 fit-only PCA diagnostics. This verifies that the observed failure is a model-quality outcome under the declared recipe, not a broken or incomplete comparison. The immutable result has SHA-256 `cc815e5dfbebcf36bd9f40810c0199599e7c33d66485c7e21115265103be22c9`.
The exact result verifier also rebuilt the complete result from the frozen plan and outer manifest and matched the saved JSON, finishing with exit code 0. No code or frozen experiment file was changed after declaration.

This fixed recipe is closed as an automatic replacement candidate. The result shows a repeatable small pooled-loss gain, but not robust benefit across all predeclared checks. It does not rule out other temporal representations. This development cohort has informed multiple prior experiments, so a revised candidate needs a separate protocol and eventually independent participant confirmation. The existing research package is unchanged; author-test data was not opened, and learner-feedback, promotion and clinical eligibility remain false.
