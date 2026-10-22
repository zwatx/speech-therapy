# Empirical vote-loss headroom results

Completed September 28, 2026. **The evaluated models are above the mathematical minimum loss on these five observed ratings.** A 5% NLL reduction is not ruled out by that finite target. This does not demonstrate that an acoustic model can attain the gap, estimate population irreducibility or improve any model.

The [prospective protocol](vote-headroom-v1.md) fixed the calculation before per-position entropy analysis. It decomposes saved model loss into the empirical vote-distribution entropy plus KL divergence, and per-rater Brier into the empirical floor plus squared prediction error. It fits no model, selects no winner, applies no probability correction and uses no Colab compute.

## Observed decomposition

All three seeds evaluate the identical 5,654 positions, 1,037 recordings, 52 children ages 6–12 and 23 consonants. Of these positions, 4,858 have unanimous votes and 796 have mixed votes. Rating-0/1/2 vote totals are 532/705/27,033. The loss floor is identical across seeds because the observed votes are identical.

| Seed | Fresh hard-control mixture NLL | Empirical vote NLL floor | NLL excess | Excess / model NLL |
| --- | ---: | ---: | ---: | ---: |
| 17 | 0.17828324 | 0.08215639 | 0.09612685 | 53.918% |
| 29 | 0.17764401 | 0.08215639 | 0.09548762 | 53.752% |
| 43 | 0.17620310 | 0.08215639 | 0.09404671 | 53.374% |

The empirical per-rater Brier floor is 0.05334277. Fresh hard-control mixtures have Brier 0.08049750, 0.08060514 and 0.08018095, with excess 0.02715473, 0.02726237 and 0.02683818. The posterior candidate mixtures likewise have substantial arithmetic gaps. Their previous failure to improve the matched controls remains unchanged.

These are the three matched development controls from the [posterior-pooling study](posterior-pooling-model-comparison-results.md), not a fresh evaluation of the retained full-data research bundle. The detailed output preserves all five saved arms, three seeds, five folds, seven ages, 23 phones and 52 children, plus equal-phone means and complete supports.

## What this establishes

The present model loss is not already at the empirical five-vote NLL floor. We therefore cannot explain the failed feature/head experiments by claiming that a material NLL gain is mathematically impossible on the observed target.

The empirical floor is an optimistic bound: only five votes are observed per position, and plug-in entropy understates the uncertainty of the underlying rating population. Unanimous observed votes can occur even when future raters would disagree. The roughly 53–54% excess fractions are not forecasts of achievable improvement. They mix model mismatch with finite-sample rating uncertainty. No estimate of population Bayes loss, independent acoustic learnability, statistical superiority or clinical pronunciation correctness follows. A smoothed leave-one-rater-out vote predictor would not establish an achievable acoustic ceiling.

## Verification

Six focused tests passed before declaration and review, covering unanimous/mixed ratings, the zero-gap case, extreme finite logs, invalid counts/probabilities, repeated-child support and changed-input rejection. Actual declaration bound 160 inputs, three sources, all original ordered cells and positions, and the Python/NumPy runtime. A separate actual Opus 5.5 source/declaration review cleared arithmetic execution.

The completed calculation cross-checked every pooled/subgroup NLL and Brier against the frozen prior results within 1e-12. That tolerance checks arithmetic and changes no model improvement rule. Every bound input/source/plan/review hash passed the final guards.

Root then independently rebuilt all 84,810 position-by-arm calculations using 50-digit Decimal entropy/NLL/Brier and separate scalar mixture arithmetic, regrouped all 264 views across five outputs, and checked support, gap fractions, 5% flags and equal-phone means. It performed no model forwards or fitting. This is independent arithmetic verification, not independent final validation of the underlying cohort.

## Evidence

- [Frozen declaration](../../research/audio-head/outputs/multiphone-20260928/vote-headroom-v1/plan.json): `36a613e6946f10452e3e42ac7072b9c9e71bc71129561f3c294cd71df3be438f`.
- [Detailed results](../../research/audio-head/outputs/multiphone-20260928/vote-headroom-v1/results.json): `4da4edb8a68ab1054fc5edfe3934d5f999cd45bb20efb710b3c3728d4d8d980e`.
- [Actual Opus 5.5 source/declaration review](../../work/core-model-next-method-20260927/opus-vote-headroom-review.json): `9639aca87c4277d42895683ffaf5968da9962314e7d7e4712cc3e6e48b6c1be1`.
- [Independent root arithmetic verification](../../work/core-model-next-method-20260927/vote-headroom-results-root-observation.json).
- [Independent Opus 5.5 result interpretation review](../../work/core-model-next-method-20260927/opus-vote-headroom-results-review.json): `dda808eb11896f3dfbf52983f40c49b24d3f7aa83148e53c81e30d097b8da944`.

A separate actual Opus 5.5 call cleared the result interpretation from the supplied packet and root receipt. It did not execute or independently hash/recompute results. The suggested next question is to distinguish model disagreement with unanimous observed votes from error on mixed-vote positions. This requires a separate prospective diagnostic. Unanimity among five observed votes does not establish population certainty, acoustic learnability or clinical truth. No model family is closed by this headroom audit, and no new fitting recipe follows automatically.
