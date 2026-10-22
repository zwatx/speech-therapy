# Training on every consonant occurrence

The complete position dataset is usable for real training, but the first
fixed comparison gives **mixed results and no model promotion**. Expanding
child-only training improves within-fold below-2 ranking in every fold and
slightly improves pooled child probability fit. However, pooled child
below-2 and rating-0 average precision decrease. Both age regimes fail the
predeclared consistency rule. The unfamiliar-word slices show a useful
research signal, described with their limitations below.

## What ran

The [fixed protocol](multiphone-position-training-protocol.md) compared
original-row and all-position fitting under both all-age and ages 6–12-only
regimes across the same five speaker folds. All **twenty fresh fits**, **78
total epochs** and **14,100 optimizer updates** completed. Every original-row
fit exactly reproduced its historical normalization, every epoch's training
loss and final model tensors. This is a direct check that the expanded feature
pipeline did not silently alter the baseline.

All twenty checkpoints were frozen before new held-out predictions. Every
pipeline covers all 28,227 positions exactly once across its own held-out
speakers. The encoder, 1,037 features, head architecture and original selected
learning rates/epoch counts remained fixed. Expanded fits necessarily make
more optimizer updates per epoch; this tests the complete data expansion,
not data value at a fixed update budget. Six training tests and 31 associated
position-data/feature tests pass. No author-test data or Colab was used.

## Child results, ages 6–12

Each cell shows original-row fitting → expanded fitting on the **same**
evaluation population. AP is macro-phone average precision (higher is better);
NLL and Brier are probability losses (lower is better). These are corpus-rating
metrics, not percentages of correctly pronounced sounds.

| Fit regime | Child evaluation positions | Below-2 AP | Rating-0 AP | Macro NLL | Brier |
| --- | --- | --- | --- | --- | --- |
| all-age | Original 5,654 | 0.22138 → 0.22026 | 0.18925 → 0.16436 | 0.17567 → 0.17751 | 0.07953 → 0.07913 |
| all-age | All 9,891 | 0.22006 → 0.21379 | 0.18145 → 0.15407 | 0.18212 → 0.18320 | 0.07533 → 0.07448 |
| all-age | Added 4,237 | 0.21649 → 0.21322 | 0.12585 → 0.12395 | 0.22732 → 0.22512 | 0.06973 → 0.06827 |
| child-only | Original 5,654 | 0.20074 → 0.18400 | 0.15026 → 0.12939 | 0.18073 → 0.17912 | 0.07746 → 0.07720 |
| child-only | All 9,891 | 0.19408 → 0.19079 | 0.14160 → 0.13651 | 0.18630 → 0.18410 | 0.07269 → 0.07244 |
| child-only | Added 4,237 | 0.18441 → 0.19481 | 0.11476 → 0.12298 | 0.22955 → 0.22257 | 0.06634 → 0.06608 |

The original and all-position populations are the two declared primary
comparisons. Added-only results are descriptive. The full artifacts retain
all-age and ages 13-plus results, all 23 phone cells, actual vote/speaker
support, undefined metrics, each model's fit-only prior, confidence summaries,
word slices and individual folds. Neither fitting regime is selected from
these outcomes.

All five child-only folds improve below-2 AP on both original and all-position
child populations. On original positions, the fold differences are
+0.01391, +0.02605, +0.02198, +0.01453 and +0.00610; their pooled difference
is nevertheless −0.01675. Pooled AP is not the mean of fold APs: it also
compares scores from separately fitted models across folds. Both views are
retained. This reversal warrants a fit-only investigation of score
comparability, not rewriting the declared decision rule after seeing results.

All-age aggregate performance improves with expanded all-age fitting: on all
28,227 positions, macro NLL changes from 0.22477 to 0.21997 and below-2 AP from
0.44960 to 0.46995. The weaker child results prevent treating this as a uniform
benefit across the intended population.

## Word familiarity

The declared word slices use the original arm's fitting target-word vocabulary
for both arms, preserving their evaluation denominators. Among 614 original
child positions outside that all-age vocabulary, NLL improves from 0.31635 to
0.29908 and below-2 AP from 0.30857 to 0.33341. The child-only counterpart has
914 positions: NLL 0.28493 → 0.27421 and AP 0.25135 → 0.27366.

Some of those words become represented in expanded fitting: 53 of the 614
positions and 75 of the 914. A **retrospective diagnostic**, separate from the
declared gate, removes these positions. On the remaining 561 original child
positions absent from both all-age fitting vocabularies, NLL changes from
0.33302 to 0.31566 and below-2 AP from 0.31538 to 0.33308. On the corresponding
839 child-only positions, NLL changes from 0.30203 to 0.29025 and AP from
0.24514 to 0.27010. This makes the expansion worth investigating further.

These are target-row vocabulary slices, not word-disjoint validation: a word
can still occur elsewhere in a fitting recording. The same speakers/prompts
have been used in development, there is no new independent cohort, and no
significance or clinical generalization claim follows from these descriptive
changes. The [saved diagnostic](../../work/position-training-diagnostics-20260927/report.json)
retains all population summaries and bindings to the saved fold membership flags; SHA-256
`8074e29204bed4312b741f19124b648ca9e1b82d1d70b87dde388ae47d828515`.

## Evidence and next step

- [Feature export and verification](multiphone-position-phonetic-report.md).
- [Training declaration](../../research/audio-head/outputs/multiphone-20260927/position-study-v1/plan.json): `ed9e72662331ea42261170c7c4c825c67d00c491b7b657c60646f35153f7d80b`.
- [Twenty-model freeze](../../research/audio-head/outputs/multiphone-20260927/position-study-v1/freeze.json): `3077f3a4cb2059e6b784de0e09284a31781b9a4a580b28e954b6a4731e037e7e`.
- [Complete comparison](../../research/audio-head/outputs/multiphone-20260927/position-audit-v1/report.json): `6f36e527cab803008bc25596436546992fc4b10d0082734848881334e2058fe2`.

Independent source and feature audits passed before fitting. Independent
verification of the saved training, predictions and metric tables passed:
all twenty checkpoints, ten historical reproductions, twenty exact prediction
replays, four pooled pipelines, 1,296 metric/support tables and 29,808 phone
cells. The retrospective diagnostic also reproduced exactly. The
[verification record](../../work/position-training-audit-20260927/verification.json)
has SHA-256 `61540e517f17bab61bfb08eb6d32c328f2ddcbc45f63dd2556c3b1475c012eca`.

The next bounded investigation should use only inner fitting/validation
speakers to assess expanded-data stopping and score comparability. Preserve
this twenty-fit comparison and its failed consistency gates. No expanded
model has been exported for learner use, and learner judgments remain disabled.
Broader app checks were not run for these isolated research changes.
