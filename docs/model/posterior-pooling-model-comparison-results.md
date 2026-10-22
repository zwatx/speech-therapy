# Posterior pooling matched model results

Completed September 28, 2026. **The fixed posterior-pooling recipe failed the development screen at all three seeds.** Preserve the existing private research bundle. This result closes automatic replacement for this recipe; it does not justify another seed, kernel, objective or subset search.

The [protocol](posterior-pooling-model-comparison-v1.md) was fixed before fitting. The candidate averages acoustic features using canonical CTC posterior occupancy and a fixed context kernel; the control averages fresh hard intervals from the same encoder forwards. Both use fit-only PCA16, the same 13 scalar features, matching head recipes and identical paired initial weights/random streams. Each refit uses its own inner-selected duration. Both equal acoustic/scalar mixtures share the same validated scalar head.

## Primary matched results

AP ranks five experts’ subjective ratings; it is not pronunciation accuracy or produced-phone truth. Lower NLL, macro-phone NLL and Brier are better; higher AP is better.

| Seed | Method | NLL ↓ | Macro NLL ↓ | Brier ↓ | Rating-0 AP ↑ | Below-2 AP ↑ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 17 | Fresh hard control | 0.17828324 | 0.19022268 | 0.08049750 | 0.09159853 | 0.16613064 |
| 17 | Posterior candidate | 0.17826681 | 0.19026973 | 0.08055470 | 0.08764973 | 0.16494114 |
| 29 | Fresh hard control | 0.17764401 | 0.18983601 | 0.08060514 | 0.09935750 | 0.16978662 |
| 29 | Posterior candidate | 0.17758147 | 0.18960480 | 0.08066113 | 0.09821966 | 0.16965578 |
| 43 | Fresh hard control | 0.17620310 | 0.18725952 | 0.08018095 | 0.09305023 | 0.16770919 |
| 43 | Posterior candidate | 0.17602033 | 0.18764373 | 0.08027382 | 0.09233012 | 0.16563560 |

| Seed | Relative NLL reduction | Rating-0 AP change | Compact NLL condition | Development seed pass |
| --- | ---: | ---: | --- | --- |
| 17 | 0.009216% | -0.00394881 | Pass | Fail |
| 29 | 0.035207% | -0.00113784 | Fail | Fail |
| 43 | 0.103730% | -0.00072011 | Pass | Fail |

Each seed required at least 5% matched mixture NLL reduction and +0.01 absolute rating-0 AP, together with nonworsening fold NLL, macro NLL, Brier and below-2 AP, plus compact-head NLL improvement. The actual NLL changes were tiny and rating-0 AP, below-2 AP and Brier worsened at every seed. No seed passed even the directional screen. Seed 29 also failed the compact NLL condition. Means across seeds are descriptive and cannot rescue the result.

## Coverage and regressions

Every seed scored the same 5,654 original child positions from 1,037 recordings and all 52 children. Votes were 532 rating-0, 705 rating-1 and 27,033 rating-2. All five speaker folds, seven ages and 23 consonants remain included. Whole-utterance word purging and ordered memberships are unchanged. Added-validation rows were included only in refits, after epoch selection.

Age 11 worsened in mixture NLL at all three seeds. The same consistent regression occurred for B, G, S, SH, HH and TH, failing both age and phone guards. Thirteen children regressed consistently; these child results are descriptive and no child was excluded. Individual seeds showed 24–28 child regressions, 12–14 phone regressions and 2–4 age regressions. All subgroup supports, undefined AP values, three-seed changes and less-consistent regressions remain in the detailed results.

| Age 6, seed | Candidate mixture rating-0 AP | Control mixture rating-0 AP | Candidate macro NLL | Control macro NLL |
| --- | ---: | ---: | ---: | ---: |
| 17 | 0.12083608 | 0.12422095 | 0.24337223 | 0.24384556 |
| 29 | 0.13697784 | 0.13457860 | 0.23944678 | 0.24029382 |
| 43 | 0.13346859 | 0.13168477 | 0.23884291 | 0.23937400 |

## Execution and verification

All 94 focused synthetic checks passed before the declaration. Independent GPT-6 Astra reviewed the final source and actual declaration before execution. All 75 historical scalar controls passed full saved-state validation and exact replay, permitting reuse in every cell. All 150 acoustic inner fits, 150 fresh refits and 150 outer passes completed successfully. Inner-selected/refit durations ranged from 5 to 57 epochs. Corresponding acoustic heads had bit-exact initial model tensors and random streams. The runner validated optimizer/history/checkpoint lineage, fit-only PCA, normalization and priors.

Phase work took 22.11 seconds for scalar controls, 352.11 for inner fits, 153.43 for refits and 23.99 for outer inference. These phase timings exclude declaration rebuilding and predecessor-validation overhead. This study used the Mac CPU with cached features and allocated no Colab compute. Earlier real Colab training remains separately recorded in the [GPU pilot results](colab-expanded-pilot-results.md).

The evaluator replayed every saved acoustic head and all historical scalar controls, then checked the complete artifact chain. Root separately rebuilt saved predictions, equal mixtures, NLL, macro NLL, Brier, weighted AP/AUC, all support counts and gates across 264 pooled/subgroup views and five model outputs. The root audit added no fits or head forwards; it did not independently replay full optimizer trajectories. All bound source/input/review/current and consumed artifact hashes remained unchanged.

The upstream extraction independently reconstructed acoustic pooling only on 37 probe positions; full-cohort diagnostics and cross-process probes share the original encoder. This comparison uses extensively explored development data. Small descriptive improvements are not statistical superiority, independent confirmation, child speech-sound-disorder validity or clinical benefit. No promotion, learner feedback or clinical use follows.

## Evidence

- [Frozen training plan](../../research/audio-head/outputs/multiphone-20260927/posterior-pooling-model-comparison-v1/plan.json): `bccaf64d0ca431913f073c5c6e6042dd7054dd427235e1bf109528a83ea017df`.
- [Complete outer freeze](../../research/audio-head/outputs/multiphone-20260927/posterior-pooling-model-comparison-v1/outer-freeze.json): `d565d91f95504507ae703fd161673f1da43a01e20765ce2d6234b6f562546411`.
- [Detailed results](../../research/audio-head/outputs/multiphone-20260927/posterior-pooling-model-comparison-v1/results.json): `3bcdbdfc4f717f24aaca78994bb56d568f6275dff5690dcf4e325078bc3c3ee3`.
- [Independent root arithmetic audit](../../work/core-model-next-method-20260927/training-results-root-observation.json).
- [Pre-execution Astra source/declaration review](../../work/core-model-next-method-20260927/astra-training-source-review.json).
- [Independent Opus 5.5 interpretation review](../../work/core-model-next-method-20260927/opus-training-results-review.json): `b23f7e5cecd029749797dd9a1aa04ca44f1d2fbcfb474f4b2c90cffd34ab2770`.

A separate tool-free Claude Code call reported only `claude-opus-5-5`, completed successfully and reviewed the supplied source, frozen protocol, actual result packet and root/Astra receipts. It cleared integrity and interpretation while confirming scientific failure. It did not execute, hash, replay or independently recompute the results. Opus also authored the original training source, so the same-model-family limitation is explicit; root repairs and the separate Astra source review remain distinct evidence.

Opus recommended checking existing rating-reliability outputs before a descriptive headroom audit. Finite-vote entropy is an empirical oracle floor, not proof of population irreducible loss. A leave-one-rater-out vote predictor is not a guaranteed achievable acoustic ceiling and cannot alone close all possible model families. Any new audit or fitting study needs its own declared question and independent review; the present pooling recipe remains closed.
