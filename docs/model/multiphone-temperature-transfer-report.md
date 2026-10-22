# Frozen temperature transfer result

The temperature correction also fails the fixed consistency screen when applied
to the original inner heads on the same held-out speakers. Both models' pooled
child log loss worsens, and both lose below-2 ranking. The child-only model loses
rating-0 ranking as well. Refitting the head is therefore not required for these
observed failures. This does not show that transfer has no effect or establish
a unique cause of the difference between the original and refitted models.

The [protocol](multiphone-temperature-transfer-protocol.md) fixed this follow-up
after the [first temperature study](multiphone-temperature-report.md). It reused
all ten frozen inverse temperatures and original selected checkpoints, with no
new parameter fitting or selection. Each checkpoint exactly replayed its saved
inner validation predictions and metrics before a new outer-head pass. No
acoustic encoder ran. All 14,837 positions are represented exactly once per
pipeline; the primary child subset has 5,654 positions from 52 children aged
6–12. All 23 consonants and original five-vote labels remain represented.

## Child probability quality and rare-rating ranking

Lower NLL, macro-phone NLL and Brier are better; higher AP is better. AP here is
pooled vote-weighted ranking, not an equal-phone average or a clinical accuracy
percentage. “Original” means the selected inner head; “refit” is the existing
head refitted on outer fitting speakers. Each correction is compared with its
own normalized baseline on identical outer positions.

| Pipeline / head / probabilities | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / original / normalized | 0.172174 | 0.177524 | 0.081330 | 0.112413 | 0.198567 |
| all-age / original / corrected | 0.172895 | 0.178347 | 0.081011 | 0.112568 | 0.198348 |
| all-age / refit / normalized | 0.169242 | 0.175675 | 0.079533 | 0.121307 | 0.205399 |
| all-age / refit / corrected | 0.170879 | 0.177421 | 0.079462 | 0.121313 | 0.205158 |
| child-only / original / normalized | 0.170193 | 0.178679 | 0.077248 | 0.092311 | 0.210382 |
| child-only / original / corrected | 0.170329 | 0.179398 | 0.077502 | 0.084271 | 0.205663 |
| child-only / refit / normalized | 0.172332 | 0.180729 | 0.077457 | 0.111119 | 0.210628 |
| child-only / refit / corrected | 0.171156 | 0.179905 | 0.077420 | 0.107377 | 0.210079 |

The original all-age model passes only the pooled Brier and rating-0 AP checks.
The original child-only model fails all six checks. No model or corrected
variant is selected from these outcomes; the four existing bundles are retained.

## Fold consistency and comparison with refitting

The entries below are corrected minus normalized child NLL. Positive values
are worse. Fold numbers are the original zero-based speaker splits.

| Pipeline / fold | Original-head NLL change | Refit-head NLL change |
| --- | ---: | ---: |
| all-age / 0 | -0.000761 | 0.000777 |
| all-age / 1 | -0.000478 | 0.000285 |
| all-age / 2 | 0.003927 | 0.004872 |
| all-age / 3 | 0.000058 | -0.000200 |
| all-age / 4 | -0.000497 | 0.000990 |
| child-only / 0 | -0.000501 | -0.000116 |
| child-only / 1 | 0.000214 | 0.000324 |
| child-only / 2 | -0.000735 | -0.000684 |
| child-only / 3 | 0.001981 | -0.007284 |
| child-only / 4 | 0.000214 | 0.001123 |

The original all-age head loses child NLL in folds 2 and 3, versus four folds
for its refit. The original child-only head loses in folds 1, 3 and 4. Its fold-3
correction worsens NLL by 0.001981 on the original head but improves it by
0.007284 on the refit. The original child-only correction's pooled NLL change
is +0.000136, compared with -0.001176 on the refit. These are different trained
states and fitting populations. This comparison removes the need to transfer
a correction to a new head in one arm; it is not a causal experiment that
isolates all effects of refitting.

## Unfamiliar words

Word membership uses each original inner head's actual fit rows. Calibration
and other inner-validation words are not added to the fitting vocabulary solely
because they occur there. The
child all-age slice has 707 positions, 51 children and 342 word types; the
child-only slice has 1,019 positions, 52 children and 500 word types. These
are descriptive slices, not word-disjoint experiments. They differ from the
refit study's 614 and 914 positions, so the two word slices are not matched
populations.

| Original head / unfamiliar child words | NLL | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: |
| all-age / normalized | 0.273962 | 0.225411 | 0.306554 |
| all-age / corrected | 0.281082 | 0.223146 | 0.303197 |
| child-only / normalized | 0.248650 | 0.138182 | 0.253623 |
| child-only / corrected | 0.249383 | 0.127475 | 0.240238 |

Both original heads lose NLL and both rare-event ranking measures on their
unfamiliar child-word slices after correction.

## Phone support and child changes

All 23 phones remain visible. Vote counts below are original rating-0 / below-2
votes; the latter includes rating 0. A position contributes five votes, so
these are not independent participants. NLL changes are corrected minus baseline.
Complete per-phone ranking, age and word support remain in the machine report.

| Phone | Child positions | Rating-0 / below-2 votes | All-age NLL change | Child-only NLL change |
| --- | ---: | ---: | ---: | ---: |
| B | 236 | 13 / 16 | -0.000196 | -0.001515 |
| CH | 42 | 8 / 10 | +0.000118 | +0.009439 |
| D | 322 | 37 / 64 | +0.003612 | -0.000908 |
| DH | 333 | 29 / 126 | +0.003794 | -0.001769 |
| F | 191 | 5 / 7 | -0.000901 | +0.002213 |
| G | 195 | 1 / 3 | -0.001608 | -0.001280 |
| HH | 237 | 7 / 9 | +0.001134 | -0.000272 |
| JH | 76 | 13 / 14 | +0.000654 | +0.002991 |
| K | 330 | 9 / 16 | +0.000662 | -0.000744 |
| L | 357 | 60 / 76 | +0.000912 | -0.001247 |
| M | 341 | 32 / 67 | -0.000616 | +0.002594 |
| N | 402 | 52 / 61 | +0.003441 | +0.002191 |
| NG | 119 | 10 / 18 | +0.001179 | -0.000416 |
| P | 153 | 15 / 25 | +0.001342 | +0.006230 |
| R | 304 | 60 / 82 | -0.001785 | -0.002205 |
| S | 378 | 35 / 45 | -0.000781 | +0.002678 |
| SH | 134 | 18 / 25 | -0.001108 | +0.000821 |
| T | 378 | 27 / 46 | +0.002719 | +0.003566 |
| TH | 75 | 19 / 94 | +0.009825 | +0.004032 |
| V | 200 | 17 / 93 | -0.002820 | -0.001460 |
| W | 323 | 18 / 22 | +0.000746 | +0.000005 |
| Y | 190 | 9 / 15 | +0.001235 | -0.002228 |
| Z | 338 | 38 / 303 | -0.002644 | -0.006188 |

## Verification and limits

Twenty-three focused tests passed, including seven new identity, speaker,
vocabulary, partial-failure and freeze guards. Source and protocol received an
independent GPT-6 Astra review before declaration. All ten original validation
replays and ten new outer passes completed successfully; corrected argmax labels
are unchanged. Saved results include ordinary and stable log probabilities,
normalization drift, all nested exact NLL/entropy metrics, AP/AUROC, fixed ten-bin
reliability and empty phone/word/age cells. No new optimizer was called.

Offline reconstruction completed with exit zero, without head inference or
optimization. Independent GPT-6 Astra artifact review passed 262,564 checks,
including ten exact inner and ten exact outer direct tensor replays, fit-only
moments, all correction bindings, nested metrics and between-arm contrasts.
The [audit record](../../work/temperature-transfer-audit-20260927/audit-result.jsonl)
has SHA256 `493d01474b85979099d21b4cc297c73f5cf4e2608b350f5b55586aa173885b2e`.
Independent narrative review passed, including all 45 numerical table rows
and the limits on interpretation.

These are repeatedly examined development folds. The inner validation data
previously selected each checkpoint and fitted each correction. No author-test
recording was accessed, no clinical cohort was added, and no claim of clinical
calibration or reliable pronunciation judgments follows. No Colab compute was
used. App builds and UI tests were not run because app behavior did not change.

## Decision

Close the bounded scalar-temperature lead without another temperature sweep or
selecting a correction on outer outcomes. Retain existing bundles and keep
learner judgments disabled. These tests address probability correction, and do
not resolve the broader rare-error, unfamiliar-speaker or recording-robustness
requirements. The next step is a metadata-only feasibility check for speaker- and word-
disjoint evaluation: reserve target words deterministically, exclude every
fitting and selection utterance containing those words, and measure remaining
phone/child/rare-vote support before declaring new model fits. That would
address a limitation of the current descriptive unfamiliar-word slices. It
would still use development data and would not create independent clinical
validation.

## Artifacts

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/temperature-transfer-v1/plan.json): `d81ef07a7b976eb901455f3ff8f5130fd5cd142dc84b95796e383ae71abafb65`.
- [Frozen predictions](../../research/audio-head/outputs/multiphone-20260927/temperature-transfer-v1/freeze.json): `161a72770091117dbcedc58383ee58100296764da1612ec88568460fea6149b4`.
- [Complete comparison](../../research/audio-head/outputs/multiphone-20260927/temperature-transfer-audit-v1/report.json): `7c21e70cbf6f12bb61fe10d8d5729e5a21bf89e156f05d42024defdf77a432fb`.

Reconstruct the saved result from `research/audio-head`:

```sh
.venv/bin/python -m temperature_transfer.study verify \
  --plan outputs/multiphone-20260927/temperature-transfer-v1/plan.json \
  --plan-sha256 d81ef07a7b976eb901455f3ff8f5130fd5cd142dc84b95796e383ae71abafb65 \
  --freeze outputs/multiphone-20260927/temperature-transfer-v1/freeze.json \
  --freeze-sha256 161a72770091117dbcedc58383ee58100296764da1612ec88568460fea6149b4 \
  --output outputs/multiphone-20260927/temperature-transfer-audit-v1
```
