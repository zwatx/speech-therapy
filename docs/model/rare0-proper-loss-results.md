# Rating-zero proper-loss results

September 27, 2026. **The fixed candidate fails the development screen and is not a replacement for the retained research model.** Independent post-fit integrity review cleared, as did the preceding source, pilot and full-plan reviews.

## Fixed comparison

The candidate changes only the compact head’s training loss: ordinary five-vote categorical NLL plus a coefficient-1 proper rating-zero Bernoulli NLL. It uses the same frozen final-layer PCA16 plus 13 alignment scalars, architecture, initial weights, ordered batch prefixes, phone priors and three seeds as its matched historical compact controls. The primary comparison is the equal-probability candidate/scalar mixture against the same-seed historical compact/scalar mixture. Ordinary categorical NLL still chooses the stopping epoch. No coefficient, seed or outcome was selected after scoring. See the [predeclared protocol](rare0-proper-loss-protocol.md).

The permitted author-training data covers ages 6–12 and all 23 consonants. Each seed evaluates the same 5,654 original child positions, 1,037 recordings and 52 children, with 532/705/27,033 rating votes for classes 0/1/2. Rating zero accounts for 1.882% of votes. These are subjective ratings, not produced-phone or clinical labels. This cohort has informed previous development experiments; the results are not independent confirmation.

## Pooled outcomes

NLL measures probability quality; lower is better. Average precision (AP) measures event ranking; higher is better. Deltas below are candidate minus matched reference.

| Seed | Reference mixture NLL | Candidate mixture NLL | Relative NLL reduction | Rating-0 AP delta | Strict pass |
| --- | ---: | ---: | ---: | ---: | --- |
| 17 | 0.178283244 | 0.177945111 | +0.190% | +0.003641 | No |
| 29 | 0.177644011 | 0.177590363 | +0.030% | +0.002041 | No |
| 43 | 0.176203103 | 0.176488375 | -0.162% | -0.000270 | No |

All three seeds fail the requirement that every speaker fold’s mixture NLL be nonworsening. Seed 17 also fails the age-6 macro-phone NLL safeguard. Seeds 29 and 43 fail the compact-head NLL co-condition. Seed 43 worsens pooled mixture NLL, macro-phone NLL, Brier and rating-0 AP. No seed meets the stronger 5% relative NLL reduction plus +0.01 rating-0 AP target. Averaging seeds cannot rescue these failures.

| Speaker fold | Mixture NLL delta, seed 17 | Seed 29 | Seed 43 |
| --- | ---: | ---: | ---: |
| 0 | +0.000388 | +0.000344 | +0.000182 |
| 1 | -0.000275 | +0.000393 | +0.000659 |
| 2 | -0.000569 | -0.000858 | +0.000483 |
| 3 | -0.000726 | -0.000199 | -0.000529 |
| 4 | -0.000429 | +0.000362 | +0.000472 |

## Age safeguards

Age 11 is worse at every seed, so the predeclared all-age guard fails. This group has seven children and 27 rating-zero votes. Ages 8 and 10 have only two children each; their results remain especially uncertain.

| Age | Children | Positions | Rating-0 votes | Mixture NLL delta, seed 17 | Seed 29 | Seed 43 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 13 | 1389 | 193 | -0.000528 | -0.000788 | +0.000183 |
| 7 | 10 | 1020 | 128 | -0.000704 | +0.000204 | +0.000437 |
| 8 | 2 | 232 | 37 | -0.000932 | +0.000164 | -0.001088 |
| 9 | 11 | 1191 | 71 | -0.000198 | +0.000300 | +0.000632 |
| 10 | 2 | 226 | 18 | -0.000372 | -0.000430 | +0.000096 |
| 11 | 7 | 792 | 27 | +0.000412 | +0.000191 | +0.000345 |
| 12 | 7 | 804 | 58 | -0.000310 | +0.000167 | +0.000146 |

| Seed | Age-6 rating-0 AP delta | Age-6 macro-phone NLL delta | Equal-phone rating-0 AP delta | Extra safeguards pass |
| --- | ---: | ---: | ---: | --- |
| 17 | +0.005894 | +0.000079 | +0.005004 | No |
| 29 | +0.008571 | -0.000372 | +0.001354 | Yes |
| 43 | +0.001398 | -0.001157 | +0.004332 | Yes |

All 23 phone-specific rating-zero AP endpoints are defined, and their equal-phone mean improves at every seed. That positive ranking result does not override the probability and subgroup failures.

## Phone ranking diagnostics

The table reports mixture rating-0 AP changes. Votes and event-positive children show support; repeated ratings and seeds are not independent children.

| Phone | Positions | Rating-0 votes | Children with rating-0 votes | AP delta, seed 17 | Seed 29 | Seed 43 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 13 | 8 | +0.044827 | -0.000725 | +0.008218 |
| CH | 42 | 8 | 2 | +0.000741 | -0.000395 | +0.043239 |
| D | 322 | 37 | 20 | +0.001208 | +0.007030 | +0.002456 |
| DH | 333 | 29 | 12 | -0.000088 | +0.002647 | -0.000939 |
| F | 191 | 5 | 5 | +0.002060 | +0.000027 | -0.000082 |
| G | 195 | 1 | 1 | -0.000696 | +0.000000 | +0.001288 |
| HH | 237 | 7 | 6 | +0.000569 | +0.000653 | +0.009147 |
| JH | 76 | 13 | 5 | +0.000135 | -0.006314 | -0.004396 |
| K | 330 | 9 | 4 | +0.001093 | -0.000891 | -0.000381 |
| L | 357 | 60 | 25 | +0.003877 | -0.000884 | -0.001190 |
| M | 341 | 32 | 19 | +0.006796 | -0.000424 | -0.000202 |
| N | 402 | 52 | 22 | +0.009100 | -0.007465 | -0.000989 |
| NG | 119 | 10 | 6 | +0.010815 | -0.002685 | -0.016036 |
| P | 153 | 15 | 4 | -0.000067 | +0.027026 | -0.002720 |
| R | 304 | 60 | 23 | +0.009705 | +0.014623 | +0.001277 |
| S | 378 | 35 | 15 | -0.003067 | -0.000490 | +0.035406 |
| SH | 134 | 18 | 8 | +0.023506 | -0.003395 | +0.023734 |
| T | 378 | 27 | 11 | -0.002827 | -0.002791 | -0.001933 |
| TH | 75 | 19 | 10 | +0.001182 | +0.003593 | -0.000162 |
| V | 200 | 17 | 11 | -0.001283 | +0.002177 | +0.003565 |
| W | 323 | 18 | 7 | -0.001872 | -0.002561 | -0.001638 |
| Y | 190 | 9 | 3 | +0.000000 | +0.000000 | +0.000000 |
| Z | 338 | 38 | 19 | +0.009380 | +0.002382 | +0.001980 |

## Class loss decomposition

Each contribution retains fractional five-vote labels and sums to the pooled ordinary NLL change. Positive means worse probability assigned to that class’s votes. Improvement in rare-event ranking does not ensure better probabilities for rare-event votes.

| Seed | Rating-0 contribution | Rating-1 contribution | Rating-2 contribution | Total NLL delta |
| --- | ---: | ---: | ---: | ---: |
| 17 | -0.000314 | -0.000199 | +0.000175 | -0.000338 |
| 29 | +0.000191 | +0.000213 | -0.000457 | -0.000054 |
| 43 | +0.000088 | -0.000364 | +0.000561 | +0.000285 |

The saved result includes all five folds, seven ages, 23 phones and 52 children for every seed, with probability, ranking and support metrics, plus pooled/age/phone class-loss decompositions. Across seeds, mixture NLL worsens for 21/30/32 children respectively. These small development differences do not establish a clinical benefit.

## Execution and audit trail

All 15 focused tests and syntax checks passed. The independently reviewed fit-only pilot ran ten epochs on 1,997 positions from 38 children; it created no selection or outer predictions and its weights were excluded from fresh fits. All 150 historical control heads replayed exactly. All 75 inner fits, 75 fresh refits and 75 outer prediction sets completed successfully. Selected epochs range from 7 to 48. The saved-state validator checks the declared objective, ordinary-NLL selection, exact row order, optimizer and RNG state, fit-only transforms and checkpoint lineage. No new Colab allocation was needed for these cached-feature fits.

- [Full plan](../../research/audio-head/outputs/multiphone-20260927/rare0-proper-loss-heads-v1/plan.json): `3829b13646548aa1a52299fbd29d45e8b4a13271d835acd0dda696286218b3ec`.
- [Outer freeze](../../research/audio-head/outputs/multiphone-20260927/rare0-proper-loss-heads-v1/outer-freeze.json): `b21b12d300f1bfab205ed60643916773f8c6432153d6058695971f1bc5cc9811`.
- [Detailed results](../../research/audio-head/outputs/multiphone-20260927/rare0-proper-loss-heads-v1/results.json): `e039bc582c416c7742f64b782a8db71cb7c809810ae1dc714f187f04274b9b33`.

The exact result verifier completed successfully and rebuilt the identical saved result SHA. Independent GPT-6 Astra post-fit review replayed all 75 candidate and 150 control selected/outer prediction sets and separately reconstructed 264 subgroup views across five models, all support counts, screens and class-loss decompositions. Its 87,312 checks had maximum numerical difference `3.61e-16`; all 234 human-report table cells matched at the stated rounding. Root rehashed all seven receipt bindings. The [independent review receipt](../../work/rare0-proper-loss-20260927/results-review.json) has SHA-256 `8c83c0cc8a30bf883bd2f450132498a2c86eeac1a5663284befebbb1223bfef5` and clears integrity while confirming scientific failure.

No model promotion, learner judgment, calibration fit or clinical claim follows. The fixed coefficient-1 recipe is closed as an automatic replacement; further work needs a distinct rationale and protocol, rather than a coefficient search to rescue this result.
