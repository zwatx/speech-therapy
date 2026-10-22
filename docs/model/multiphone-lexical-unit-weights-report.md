# Recording/sound-unit weighting: a verified tradeoff

Equalizing each recording/sound group's training contribution does not improve
overall on the corresponding unweighted expanded models. None of the six primary
comparisons passes the fixed six-part screen. The child-trained equal mixture
is slightly worse on all five pooled child endpoints and has worse NLL in speaker
folds 1, 2 and 3. Its /W/ NLL improves, with regressions elsewhere.

The separately declared comparison against the older corrected-projection mixture
is favorable: the weighted child mixture passes all six checks, including lower
NLL in every speaker fold. Preserve that secondary result without replacing the
primary comparison. This is a research tradeoff, not a promoted model.

The [fixed protocol](multiphone-lexical-unit-weights-protocol.md) retains all 28,227
expanded positions and the same 100 jobs: two model families, two fitting age
regimes, five speaker folds and five whole-utterance word exclusions. The loss
uses `(n/g)/k` for each of k canonical same-sound positions in a recording, with n
fit positions and g fit recording/sound units. All group totals are equal and the
fit mean weight is one. Every retained recording contributes all its supported
canonical positions. Refit weights are recomputed using refit metadata alone.

Unweighted feature moments, PCA16, priors, seed 7, optimizer, original-example
checkpoint selection and the equal .5/.5 probability mixture stay fixed. There
are 100 inner fits, 100 fresh refits and 100 frozen outer prediction jobs. Weighted
training losses are not directly comparable with unweighted training losses.

Primary evaluation uses the same original 5,654 positions from 52 children aged
6–12, within the original 14,837-position population. Added and all-position views
remain separate descriptive summaries. Lower NLL, macro NLL and Brier are better;
higher rating-0 AP and below-2 AP are better. These are subjective rating predictions.

## All declared child comparisons

Differences are weighted minus the stated reference. Primary references are the
corresponding unweighted expanded models; secondary references are the original
corrected-projection mixtures. Screen tolerances are unchanged: pooled NLL must
improve by more than 1e-7; the other pooled endpoints and every speaker-fold NLL
must not worsen beyond 1e-7.

| Regime | Model / contrast | Reference | NLL Δ | Macro NLL Δ | Brier Δ | AP0 Δ | AP<2 Δ | Six checks pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all-age | scalars | primary | -0.000161 | +0.000025 | -0.000201 | -0.000443 | +0.002577 | False |
| all-age | pca16-scalars | primary | -0.000049 | +0.000207 | +0.000319 | -0.001444 | -0.003806 | False |
| all-age | equal-mixture | primary | -0.000041 | +0.000089 | +0.000081 | -0.000780 | +0.000413 | False |
| all-age | mixture vs corrected | secondary | -0.000302 | +0.000026 | +0.000149 | -0.000121 | +0.003842 | False |
| child-only | scalars | primary | +0.000299 | +0.000302 | +0.000150 | -0.001114 | -0.001372 | False |
| child-only | pca16-scalars | primary | -0.000363 | -0.000224 | +0.000193 | -0.001468 | -0.005602 | False |
| child-only | equal-mixture | primary | +0.000028 | +0.000132 | +0.000167 | -0.000266 | -0.003251 | False |
| child-only | mixture vs corrected | secondary | -0.002811 | -0.002226 | -0.000760 | +0.009758 | +0.008539 | True |


## Speaker-fold NLL differences

All five folds are retained, including failures.


| Regime | Model / contrast | Reference | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all-age | scalars | primary | +0.000097 | -0.002792 | -0.000713 | +0.002101 | +0.000927 |
| all-age | pca16-scalars | primary | +0.001210 | -0.000979 | -0.001920 | +0.000901 | +0.001392 |
| all-age | equal-mixture | primary | +0.000495 | -0.001980 | -0.001107 | +0.001579 | +0.001378 |
| all-age | mixture vs corrected | secondary | +0.000140 | -0.002241 | -0.001029 | +0.004537 | -0.002145 |
| child-only | scalars | primary | -0.000927 | +0.000086 | +0.001806 | +0.000844 | -0.000884 |
| child-only | pca16-scalars | primary | -0.000893 | +0.000181 | -0.000903 | +0.000517 | -0.000441 |
| child-only | equal-mixture | primary | -0.001539 | +0.000239 | +0.000930 | +0.000379 | -0.000238 |
| child-only | mixture vs corrected | secondary | -0.001389 | -0.002418 | -0.006183 | -0.000914 | -0.001613 |


## Every sound in the mixture comparison

The table uses original child positions. Primary columns compare with the
unweighted expanded mixture; the final column keeps the child secondary comparison
visible. Support is identical across those contrasts. All eight full model
contrasts retain class, fold, 25 word-cell and all-child contributions in the artifact.


| Sound | Positions | Children | Votes 0/1/2 | All-age primary NLL Δ | Child primary NLL Δ | Child secondary NLL Δ |
| --- | --- | --- | --- | --- | --- | --- |
| B | 236 | 51 | 13/3/1164 | -0.001320 | +0.000767 | -0.002582 |
| P | 153 | 50 | 15/10/740 | +0.000019 | -0.001698 | -0.006480 |
| M | 341 | 51 | 32/35/1638 | -0.000712 | -0.001285 | -0.002947 |
| T | 378 | 52 | 27/19/1844 | +0.003042 | +0.003542 | -0.011300 |
| D | 322 | 52 | 37/27/1546 | -0.003079 | +0.000549 | +0.000871 |
| N | 402 | 52 | 52/9/1949 | -0.000802 | -0.001198 | -0.001621 |
| K | 330 | 52 | 9/7/1634 | +0.000887 | +0.000334 | -0.002397 |
| G | 195 | 52 | 1/2/972 | -0.000288 | -0.000151 | -0.000550 |
| F | 191 | 51 | 5/2/948 | +0.000864 | +0.001305 | -0.001343 |
| V | 200 | 49 | 17/76/907 | +0.003724 | +0.000880 | -0.010531 |
| S | 378 | 52 | 35/10/1845 | +0.000604 | -0.000579 | -0.002106 |
| Z | 338 | 52 | 38/265/1387 | -0.000373 | +0.002049 | -0.003662 |
| SH | 134 | 49 | 18/7/645 | -0.007771 | -0.003114 | -0.005173 |
| CH | 42 | 29 | 8/2/200 | +0.002472 | +0.003346 | +0.002290 |
| JH | 76 | 31 | 13/1/366 | +0.011825 | -0.001604 | +0.006074 |
| L | 357 | 52 | 60/16/1709 | +0.000102 | -0.002148 | -0.005456 |
| R | 304 | 51 | 60/22/1438 | +0.000963 | +0.005452 | -0.008025 |
| W | 323 | 51 | 18/4/1593 | -0.001587 | -0.006224 | +0.001680 |
| Y | 190 | 49 | 9/6/935 | +0.000047 | +0.002134 | +0.003306 |
| HH | 237 | 52 | 7/2/1176 | +0.002231 | +0.001738 | -0.000028 |
| TH | 75 | 40 | 19/75/281 | -0.008044 | -0.001599 | +0.003332 |
| DH | 333 | 52 | 29/97/1539 | -0.001827 | -0.002714 | +0.001404 |
| NG | 119 | 48 | 10/8/577 | +0.001078 | +0.003255 | -0.005949 |


Child /W/ improves by .006224 NLL against the unweighted expanded mixture, but
remains .001680 worse against the older corrected mixture. Its rating-0 and
rating-1 contributions improve while rating-2 contribution worsens. The scarce
support is 18/4/1,593 votes across 323 positions and 51 children. This does not
establish a reliable general-purpose /W/ correction. Child /R/, /T/ and /NG/
regress against the primary reference by .005452, .003542 and .003255 NLL.

## Verification and provenance

Fifteen synthetic tests passed independently before declaration, including exact
all-one inner/refit trajectories against both frozen trainers, nonuniform gradients
and manual AdamW updates, complete canonical weights, tampering and phase guards.
Real preflight checked 40,342 input bindings with fitting and inference forbidden.
Independent prefit geometry verified all 200 fitting weight states.

All 200 completed fit/refit runs pass independent saved-state audits: 600
checkpoints, 100 PCA certificates, ordered weights/config bindings, initialization,
optimizer schema/counts, permutation/dropout RNG, stopping rules and 100 exact
selected prediction replays. This does not reconstruct every optimizer trajectory.
A separate auditor reconstructed four fixed s0-w0 inner jobs through their selected
checkpoints: 100 aggregate epochs and 3,900 gradient/clipping/AdamW updates, with
nonuniform weights and partial batches. Every epoch's loss/selection and selected
model, optimizer and RNG matched bit-exactly. Post-selection epochs, last.pt,
refit trajectories and the other runs were not replayed in that trajectory audit.

Independent functional replay reproduced all 100 outer files and 112,908 row
predictions exactly, including raw probabilities, stable logs and NLL. Separate
metric reconstruction passed all 744 original/added/all summaries, priors, fixed
mixtures, six primary/two secondary comparisons and all eight full child responses:
1,744,610 lineage/response checks, 7,502,256 primary metric checks and 5,807,160
ancillary checks. These counts are audit assertions, not independent observations.
Exact offline report reconstruction also passed.

Opus 5.5 reviewed the training/trajectory source and authored the saved-state
auditor; runtime metadata verifies claude-opus-5-5 with no fallback. Its final
audit review found a missing explicit connection between the metric and prediction
receipts. The numerical auditor had already begun and remains immutable. A new
supplemental check pins both receipts to the same exact report, plan and outer
freeze, verifies executed helper provenance and scope/schema, and rehashes 2,353
files. That check passes; its five corruption cases also reject. An independent Astra
follow-up source/artifact review passes, including 4,838 checks and rehashing all
2,353 bound files. An Opus follow-up response claimed
access outside its supplied snapshot, so it was rejected as approval. The numerical result was unchanged by this audit fix.

No actual fit or numerical audit failed. Before declaration, one synthetic fixture
failed on equivalent /var versus /private/var paths and was corrected. An initial
outer-test discovery invocation checked the old module; explicit import verification
then ran the two guards against the new auditor successfully. These limitations
are retained in the run log. App build/UI tests were not run because no app changed.

- [Frozen plan](../../research/audio-head/outputs/multiphone-20260927/lexical-unit-weights-v1/plan.json): `8bf68c8a8738abe238ee9992949db4a3fbf8a2733fe082f25732e2dcf626ca8a`.
- [Complete result](../../research/audio-head/outputs/multiphone-20260927/lexical-unit-weights-audit-v1/report.json): `d5ba68decc6b9e5bf514b9eece85316f71b03f073b13e7ee5cb1cb3b74669aed`.
- [Independent audit directory](../../work/lexical-unit-weights-audit-20260927/): state, trajectory, outer, metrics and joint-binding receipts; source hashes; Opus review snapshots.

## Decision and next step

Retain both expanded child mixtures as research candidates with explicit tradeoffs.
Do not replace the unweighted expanded primary candidate or claim that weighting
improves everything. The weighted mixture clears the older corrected benchmark,
but that does not erase its primary failures or individual-sound regressions.

Next, predeclare a fixed seed-replication study of both expanded objectives, with
unchanged data exclusions and evaluation, to test whether these small differences
persist across initialization and batch-order randomness. Do not tune weighting
strength or remove sounds using this result. That follow-up is not yet declared
or run. Reused development folds, subjective targets, no expert produced-phone
truth, no ages 2–5 cohort and no established speech-sound disorder validation remain
limits. Learner judgments stay disabled; existing bundles and author-test stay
unchanged. No new audio, encoder run or Colab allocation was used.
