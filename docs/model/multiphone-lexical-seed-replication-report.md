# Seed replication: recording/sound weighting remains a tradeoff

None of the 18 same-seed primary comparisons passes the fixed six-part screen.
The sign of pooled child NLL changes across seeds for each of the six model/regime
contrasts. In the child-only equal mixture, Brier is worse and below-2 average
precision is lower at all three seeds. The /W/ gain repeats, alongside losses on
/T/, /K/, /R/ and /NG/. This does not establish a general improvement from weighting.

The secondary comparison with the older corrected seed-7 mixture is more
favorable on pooled child metrics, but neither objective passes the complete
screen at every seed. Preserve that result separately from the primary comparison.
No seed is selected and no research model is promoted to learner feedback.

## What was fixed

The [protocol](multiphone-lexical-seed-replication-protocol.md) prescribes seeds
17, 29 and 43 for unweighted and recording/sound-unit-weighted fitting, using two
feature families, two fitting age regimes and 25 speaker/word cells. All 600
initial fits were frozen before 600 fresh refits; all refits were frozen before
600 held-out prediction jobs. PCA, moments and priors use fitting data only.
The mixture remains an equal average of scalar and PCA16/scalar probabilities.

Weighting equalizes the complete canonical recording/sound groups' fitting
contribution with `(n/g)/k` per position. It does not use the rating-class weights
of the older portable bundles. Original-example checkpoint selection, data
exclusions and all other recipe settings remain fixed. Training losses across
objectives are not directly comparable.

Expanded fitting retains 28,227 positions from the same 125 speakers. Matched
primary evaluation retains the original 14,837-position population, including
5,654 positions from 52 children aged 6–12. Added/all-position views remain
separate descriptive results. These are reused development folds, not an
independent cohort. Original-data baselines were not retrained at the new seeds;
this study cannot establish seed-robust expanded-versus-original-data gains.

## Every primary comparison

Differences are weighted minus the corresponding same-seed unweighted model.
Lower NLL, macro NLL and Brier are better; higher AP is better. The unchanged
screen requires NLL improvement beyond 1e-7 and no worsening beyond 1e-7 in the
other four pooled metrics or any speaker-fold NLL. Rounded values below do not
replace the unrounded screen. All five fold values are in the full result tables.

| Fitting regime | Model / objective | Seed | NLL Δ | Macro NLL Δ | Brier Δ | AP0 Δ | AP<2 Δ | Worse NLL folds | Screen passes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all-age | scalars | 17 | -0.000404 | -0.000411 | -0.000272 | +0.000372 | -0.000994 | 4 | False |
| all-age | scalars | 29 | +0.000522 | +0.000628 | +0.000343 | +0.001052 | -0.001688 | 1,2,3 | False |
| all-age | scalars | 43 | -0.000443 | -0.000554 | -0.000492 | -0.000987 | -0.002649 | 4 | False |
| all-age | pca16-scalars | 17 | +0.000007 | -0.000092 | +0.000227 | +0.003375 | +0.000786 | 0,3,4 | False |
| all-age | pca16-scalars | 29 | -0.000102 | -0.000058 | -0.000323 | -0.001323 | -0.000994 | 1,3,4 | False |
| all-age | pca16-scalars | 43 | -0.000631 | -0.000676 | -0.000264 | +0.005180 | +0.001549 | 0,1,4 | False |
| all-age | equal-mixture | 17 | +0.000140 | +0.000080 | +0.000134 | +0.000604 | -0.000037 | 0,1,3,4 | False |
| all-age | equal-mixture | 29 | +0.000229 | +0.000338 | -0.000013 | -0.000872 | -0.001072 | 1,3,4 | False |
| all-age | equal-mixture | 43 | -0.000359 | -0.000586 | -0.000241 | +0.001685 | +0.000388 | 0,4 | False |
| child-only | scalars | 17 | -0.000423 | -0.001060 | -0.000122 | +0.002446 | +0.000239 | 2 | False |
| child-only | scalars | 29 | +0.000738 | +0.000606 | +0.000375 | -0.002219 | -0.002715 | 0,2,3,4 | False |
| child-only | scalars | 43 | +0.000107 | +0.000306 | +0.000039 | -0.000188 | +0.000289 | 2,3,4 | False |
| child-only | pca16-scalars | 17 | -0.000755 | -0.000450 | +0.000010 | -0.000743 | -0.004239 | 2,4 | False |
| child-only | pca16-scalars | 29 | +0.000271 | +0.000085 | +0.000054 | -0.002190 | -0.003817 | 0,2,4 | False |
| child-only | pca16-scalars | 43 | -0.000007 | +0.000415 | +0.000112 | +0.001003 | -0.001867 | 1,2,4 | False |
| child-only | equal-mixture | 17 | -0.000294 | -0.000314 | +0.000046 | +0.000783 | -0.001703 | 2 | False |
| child-only | equal-mixture | 29 | +0.000148 | -0.000079 | +0.000124 | -0.002408 | -0.002990 | 1,2,4 | False |
| child-only | equal-mixture | 43 | -0.000009 | +0.000168 | +0.000047 | -0.000743 | -0.001270 | 1,2,3,4 | False |

Three primary rows improve all five pooled endpoints but still fail: all-age
mixture seed 43 (folds 0/4), all-age PCA16/scalars seed 43 (folds 0/1/4), and
child-only scalars seed 17 (fold 2). Child-only fold 2 worsens in all nine primary
rows. A pooled mean cannot replace those fold failures.

The child mixture's mean NLL difference across seeds is -0.000052, with range
[-0.000294, +0.000148]. Its mean Brier difference is +0.000073 and mean below-2
AP difference is -0.001987. These descriptive averages do not erase the seed
reversals or repeated losses. Three seeds do not provide a participant-level
uncertainty interval or a significance claim.

## Separate comparison with the fixed corrected seed-7 mixture

Each row compares the named expanded equal mixture with its fitting-regime
counterpart from the older corrected-projection study. Training seed and model
recipe/data differ from that fixed reference. This is not a paired-seed estimate
of the effect of weighting or data expansion alone.

| Fitting regime | Model / objective | Seed | NLL Δ | Macro NLL Δ | Brier Δ | AP0 Δ | AP<2 Δ | Worse NLL folds | Screen passes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all-age | unweighted | 17 | -0.000037 | -0.000057 | +0.000029 | -0.003084 | -0.000289 | 0,2,3 | False |
| all-age | unweighted | 29 | -0.000988 | -0.000819 | -0.000165 | +0.001732 | +0.003253 | 0,3 | False |
| all-age | unweighted | 43 | -0.000377 | +0.000139 | +0.000215 | +0.002460 | +0.003047 | 0,2,3 | False |
| all-age | unit-weighted | 17 | +0.000103 | +0.000022 | +0.000163 | -0.002480 | -0.000326 | 0,2,3 | False |
| all-age | unit-weighted | 29 | -0.000759 | -0.000481 | -0.000178 | +0.000860 | +0.002182 | 0,3 | False |
| all-age | unit-weighted | 43 | -0.000736 | -0.000447 | -0.000027 | +0.004145 | +0.003435 | 0,3 | False |
| child-only | unweighted | 17 | -0.002015 | -0.001231 | -0.000801 | +0.009542 | +0.008045 | 3 | False |
| child-only | unweighted | 29 | -0.002654 | -0.001617 | -0.000694 | +0.017301 | +0.011701 | 0 | False |
| child-only | unweighted | 43 | -0.004095 | -0.004194 | -0.001118 | +0.010994 | +0.009623 | none | True |
| child-only | unit-weighted | 17 | -0.002309 | -0.001545 | -0.000755 | +0.010326 | +0.006342 | none | True |
| child-only | unit-weighted | 29 | -0.002506 | -0.001696 | -0.000569 | +0.014893 | +0.008711 | 0 | False |
| child-only | unit-weighted | 43 | -0.004104 | -0.004026 | -0.001071 | +0.010251 | +0.008354 | none | True |

All six child-only secondary rows improve all five pooled metrics. The full
screen passes for weighted seeds 17 and 43 and unweighted seed 43. At seed 29,
fold 0 fails for both objectives; unweighted seed 17 fails fold 3. All six all-age
secondary rows fail, with folds 0 and 3 worse in every row. No secondary contrast
passes at every seed, and the 2/3 versus 1/3 pass counts do not overturn the paired
primary weighting results.

## All 23 sounds in the child-mixture primary comparison

![All 23 sounds across three seeds, for both fitting regimes. Blue means lower NLL and red means higher NLL after weighting.](../../work/lexical-seed-replication-audit-20260927/figure-v1/mixture-phone-seeds.png)

The chart shows NLL only; it does not replace the full metric/fold screen.
[Vector figure](../../work/lexical-seed-replication-audit-20260927/figure-v1/mixture-phone-seeds.svg).

Support is identical across seeds. Differences remain weighted minus same-seed
unweighted NLL. These are subjective rating distributions; a lower loss is not
proof of improved detection of an actual pronunciation error.

| Sound | Positions | Children | Votes 0/1/2 | Seed 17 NLL Δ | Seed 29 NLL Δ | Seed 43 NLL Δ |
| --- | --- | --- | --- | --- | --- | --- |
| B | 236 | 51 | 13/3/1164 | -0.000686 | +0.001373 | +0.000758 |
| P | 153 | 50 | 15/10/740 | +0.002622 | -0.000409 | +0.006325 |
| M | 341 | 51 | 32/35/1638 | -0.000884 | -0.000940 | -0.001498 |
| T | 378 | 52 | 27/19/1844 | +0.001847 | +0.002301 | +0.003211 |
| D | 322 | 52 | 37/27/1546 | -0.003150 | -0.001577 | -0.000303 |
| N | 402 | 52 | 52/9/1949 | -0.000971 | -0.000495 | -0.000269 |
| K | 330 | 52 | 9/7/1634 | +0.000344 | +0.000963 | +0.000809 |
| G | 195 | 52 | 1/2/972 | -0.000787 | -0.000641 | +0.000047 |
| F | 191 | 51 | 5/2/948 | -0.000024 | -0.000054 | +0.000005 |
| V | 200 | 49 | 17/76/907 | +0.000519 | +0.001772 | -0.001124 |
| S | 378 | 52 | 35/10/1845 | -0.000221 | -0.000033 | -0.000643 |
| Z | 338 | 52 | 38/265/1387 | +0.000852 | +0.003337 | -0.000969 |
| SH | 134 | 49 | 18/7/645 | -0.004509 | +0.000792 | +0.002918 |
| CH | 42 | 29 | 8/2/200 | -0.003884 | -0.001375 | -0.008320 |
| JH | 76 | 31 | 13/1/366 | +0.000778 | -0.005695 | +0.004916 |
| L | 357 | 52 | 60/16/1709 | -0.002116 | +0.000829 | -0.001098 |
| R | 304 | 51 | 60/22/1438 | +0.003250 | +0.001460 | +0.000925 |
| W | 323 | 51 | 18/4/1593 | -0.000612 | -0.000343 | -0.001080 |
| Y | 190 | 49 | 9/6/935 | -0.000331 | +0.000537 | -0.000220 |
| HH | 237 | 52 | 7/2/1176 | +0.002158 | -0.000135 | +0.001241 |
| TH | 75 | 40 | 19/75/281 | -0.000517 | -0.000503 | +0.002257 |
| DH | 333 | 52 | 29/97/1539 | -0.003677 | -0.003947 | -0.005032 |
| NG | 119 | 48 | 10/8/577 | +0.002774 | +0.000968 | +0.001003 |

M, D, N, S, CH, W and DH improve at every seed; T, K, R and NG worsen at every
seed. The other 12 sounds change direction. The seed-7 W gain and R/T/NG losses
repeat; K also worsened at seed 7. In the all-age mixture, K/G/F/R worsen at all
three seeds, while P/D/N/S/SH/W/TH/DH improve. All-age values remain in the full
tables and CSV rather than being replaced by the child-only result.

Rare-event support remains sparse: G has one rating-0 vote, F five, HH seven,
CH eight, K and Y nine each, and NG ten. CH's repeated NLL gain covers only 42
positions from 29 children. Per-sound NLL directions are descriptive and do not
apply the six-part pooled/fold screen to individual sounds.

## Artifacts and verification status

- [Full aggregate result](../../research/audio-head/outputs/multiphone-20260927/lexical-seed-replication-audit-v1/report.json), SHA-256 `9bc5cb8404c6d4cada307a8a4aa01b8acb4d2913bc896519786c1502e040ca34`, binds all three complete seed reports.
- [All result tables](../../work/lexical-seed-replication-audit-20260927/presentation-v1/summary-tables.md) retain all 30 comparisons, every fold, ten across-seed summaries and both mixtures' 23-sound tables.
- [All sound/seed differences](../../work/lexical-seed-replication-audit-20260927/presentation-v1/all-phone-seed-deltas.csv) retain 690 contrast/sound/seed rows with positions, children, recordings and rating-vote support.
- [Audit records](../../work/lexical-seed-replication-audit-20260927/) retain sources, receipts, phase bindings and presentation provenance.

All 600 initial and 600 refit saved-state checks passed; 600 selected predictions
and 600 held-out predictions replayed exactly. Fitting weights, seeded initial
states, normalization, priors, PCA certificates, optimizer-state schemas/counts
and RNG records were checked. This does not reconstruct all actual optimizer
trajectories. Independent metric audits passed all 1,488 summaries per seed: 4,464 in total,
including every original/added/all view, prior, fixed mixture and all 30 complete
child-response contrasts. Exact offline reconstruction matched all three full
seed reports and the aggregate. The separate aggregate audit passed all ten
contrasts, descriptive means/ranges, support, seed decisions and receipt bindings.
Its receipt SHA-256 is `95ce07120c621fb9fb8aa3caa1315d7642b79755fbdd086eee32ab780d763a17`.

Before declaration, root and independent Astra runs passed all 18 synthetic tests,
including seeded equivalence, altered-seed behavior and corruption/barrier guards.
Independent auditor tests and source reviews preceded actual verification.
No frozen source or numerical tolerance changed to obtain an actual audit pass.
Pre-declaration fixture/preflight failures and their corrections remain in the
[run log](model-training-run-log.md). Opus 5.5 supplied the seeded trainer and a
provisional interpretation; the published wording incorporates root corrections
and a separate review against the saved numbers.

## Research decision

Close this bounded fixed-weighting study without adopting the recording/sound-unit rule as a general improvement. Retain the
unweighted expanded objective as the research reference and preserve the weighted
results for their documented tradeoffs. Do not select a best seed, change the
weight strength or discard difficult sounds using these outcomes.

The [artifact handoff](research-artifact-handoff.md) identifies the existing
portable bundles and the separate evaluation-only checkpoints. None of the new
scores transfers to those older bundles. This study adds evidence about training
randomness; it does not validate nonspeech rejection, real-world recording
robustness, clinical pronunciation judgments or confidence-based learner feedback.

Subjective labels, sparse errors, reused folds, missing expert produced-phone
truth, no ages 2–5 cohort and no established speech-sound-disorder validation
remain limits. The [current decision](current-multiphone-decision.md) connects this
study to the broader campaign and its concrete data/validation next steps.
Learner judgments stay disabled and author-test remains closed. No new audio,
encoder run, Colab allocation or app change occurred; app builds/UI tests were
not run for this research-only milestone.
