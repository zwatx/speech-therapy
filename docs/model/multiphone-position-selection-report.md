# Selecting training settings on complete occurrence data

Applying the existing inner selection procedure to the expanded dataset
improves child probability losses, but **does not produce a consistent
rare-rating ranking gain**. Both age regimes fail the unchanged research-lead
rule. The earlier fixed-setting results remain intact, and no model is
promoted for learner judgments.

## What ran

The [declared protocol](multiphone-position-selection-protocol.md) used the
same two learning rates, architecture, objective, seed and speaker splits as
the original selection procedure. Twenty expanded-data inner trials completed
359 actual epochs and 68,798 optimizer updates. Every epoch's checkpoint and
validation probabilities were retained. An independent reviewer reproduced
all 359 prediction arrays exactly, reconstructed every selection loss and
stopping decision, and independently recovered the ten chosen settings.

| Fit regime | Learning rates, folds 0–4 | Selected epochs, folds 0–4 |
| --- | --- | --- |
| all-age | .0003, .0003, .0003, .0003, .0003 | 3, 4, 3, 5, 2 |
| child-only, ages 6–12 | .0003, .001, .0003, .001, .0003 | 3, 2, 3, 3, 5 |

The ten selected models were refitted from fresh initialization using only
their outer fitting speakers: 33 epochs and 7,991 updates. All ten were frozen
before outer predictions. Child-only fold 3 selected the same learning rate
and epoch count as its preceding expanded control; normalization, training
history and model tensors reproduced exactly. Other settings changed.

The held-out development comparison includes all three arms: original-row
fitting, expanded fitting with the old settings, and expanded fitting with
new inner-selected settings. Each of the six pipelines predicts all 28,227
positions exactly once across five held-out speaker folds. Normalization and
priors use fitting rows only. The twenty preceding control prediction records,
their metric/prior summaries and all four pooled control records match exactly.
The preceding expanded-versus-original control gates remain false.

## Child results

AP is macro-phone average precision, with higher values better. NLL and Brier
are probability losses, with lower values better. These measure corpus-rating
prediction, not the percentage of children pronouncing a sound correctly.
All comparisons within a population use exactly the same positions.

| Fit regime | Child positions | Fitting arm | Below-2 AP | Rating-0 AP | Macro NLL | Brier |
| --- | --- | --- | --- | --- | --- | --- |
| all-age | Original 5,654 | Original rows | .22138 | .18925 | .17567 | .07953 |
| all-age | Original 5,654 | Expanded, old settings | .22026 | .16436 | .17751 | .07913 |
| all-age | Original 5,654 | Expanded, selected | .20489 | .16555 | .17656 | .07876 |
| all-age | All 9,891 | Original rows | .22006 | .18145 | .18212 | .07533 |
| all-age | All 9,891 | Expanded, old settings | .21379 | .15407 | .18320 | .07448 |
| all-age | All 9,891 | Expanded, selected | .20268 | .15296 | .18181 | .07404 |
| child-only | Original 5,654 | Original rows | .20074 | .15026 | .18073 | .07746 |
| child-only | Original 5,654 | Expanded, old settings | .18400 | .12939 | .17912 | .07720 |
| child-only | Original 5,654 | Expanded, selected | .18945 | .14221 | .17580 | .07677 |
| child-only | All 9,891 | Original rows | .19408 | .14160 | .18630 | .07269 |
| child-only | All 9,891 | Expanded, old settings | .19079 | .13651 | .18410 | .07244 |
| child-only | All 9,891 | Expanded, selected | .18252 | .14930 | .18089 | .07212 |

New child-only selection improves NLL and Brier over both controls on both
primary populations. Rating-0 AP improves over both controls on all positions,
but remains below the original control on original positions. Below-2 AP is
below the original control on both populations. Four child-only folds improve
below-2 AP, while fold 0 loses .05845 on original positions and .03500 on all
positions. This differs from the previous fixed-setting expansion, whose five
child-only folds all improved that metric. Selection has not resolved the
consistency problem.

All-age selection improves child Brier but worsens pooled below-2 AP on both
primary populations. Original-position child NLL and both populations'
rating-0 AP also remain worse than the original control. Across all ages and
all positions, its NLL is .22426 versus .22477 for original fitting and .21997
for the preceding expanded control; below-2 AP is .45004 versus .44960 and
.46995. It does not retain that control's aggregate improvement in full.

The complete artifacts retain added-only results, all ages and ages 13-plus,
each fold, all 23 phone cells, actual speaker/vote support, undefined metrics,
fit-only priors, confidence summaries and word slices. Neither age regime is
selected as an outer winner.

## Word familiarity and probability diagnostics

The common word slices retain the original fitting target-word vocabulary.
For 914 original child positions outside the child-only fitting vocabulary,
selected expansion improves NLL from .28493 to .26339, below-2 AP from .25135
to .27038, rating-0 AP from .19901 to .24542 and Brier from .12151 to .11828.
Compared with the preceding expanded control, NLL/rating-0 AP/Brier improve
but below-2 AP slightly decreases (.27366 to .27038).

The corresponding 614 positions for all-age fitting remain mixed: original
to selected NLL .31635 to .31256, below-2 AP .30857 to .32600, rating-0 AP
.27020 to .29413, but Brier .13886 to .13977. Some target words become seen
in expanded fitting; these are common-denominator vocabulary slices, not
word-disjoint evidence. The earlier retrospective slice excluding words seen
in either fitting arm is not recalculated or claimed for these new models.

The separate inner diagnostics compare each selected expanded model with its
original inner counterpart on identical expanded inner-validation positions.
They retain per-phone observed vote frequencies, mean probabilities and their
differences. For all-age fits, mean predicted child rating-0 probability falls
in all five folds but remains above the observed frequency in each. Child-only
changes are mixed. For example, fold 1's mean below-2 probability rises from
.03938 to .05366 against an observed frequency of .03715; fold 3 rises from
.03609 to .04497 against .05222.

These selection-set comparisons have overlapping validation speakers and
different selected settings. No calibrated model was fitted, no duplicated
inner rows were pooled into an external test, and no causal explanation for
the earlier pooled ranking reversal has been established.

## Evidence and next step

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/position-selection-v1/plan.json): `93e1ad80c9860ad8bd6daeed6d22f5f7620f80bca4b3708667768c5b90db48ee`.
- [Inner selection freeze](../../research/audio-head/outputs/multiphone-20260927/position-selection-v1/inner-freeze.json): `b9ff0573bbf42cecc88c3e0c1c14d9129c120206cce0d82c9c159314d88eb027`.
- [Ten-refit freeze](../../research/audio-head/outputs/multiphone-20260927/position-selection-v1/outer-freeze.json): `3eb0fe0c7f15c71e02ad090d78671edbf7e0e7d87f7adfaef270be2e2dbf4084`.
- [Inner probability diagnostics](../../research/audio-head/outputs/multiphone-20260927/position-selection-diagnostics-v1/report.json): `6ffd0e7e8604bcf2be1961d6f53a0f486eb77614681bc9337d81129dbe33593f`.
- [Held-out development comparison](../../research/audio-head/outputs/multiphone-20260927/position-selection-audit-v1/report.json): `654fb2dc85764911f454e743fe191bed39c1c463f4f1c711bb667f391188c914`.

Seven focused tests passed. Independent refit, diagnostic, outer artifact and
narrative review passed: thirty held-out prediction replays, six pooled
pipelines, 1,944 metric/support tables and 44,712 phone-support cells reproduce
exactly. An additional 216 primary child tables were independently recomputed.
The inner diagnostics reproduce twenty complete prediction arrays, ten original
subset replays, 540 metric/support tables and 4,140 marginal-bias cells (4,044
nonempty). The reviewer independently reconstructed both failed new gates.

The [independent outer verification](../../work/position-selection-audit-20260927/outer-verification.json)
has SHA-256 `0930cd01dd2d3c08dfa3074ba12931cc182d18f735a1ae232ed1335009b6f728`.
The [refit/diagnostic verification](../../work/position-selection-audit-20260927/refit-diagnostics-verification.json)
and [inner checkpoint verification](../../work/position-selection-audit-20260927/inner-verification.json)
retain the preceding checks. No app behavior changed, so app builds and UI
tests were not run. No author-test recordings or Colab compute were used.
Sources, protocol and generated artifacts are pinned.

This closes the declared two-rate selection follow-up without extending its
search after seeing outcomes. Useful probability and word-slice gains remain
research evidence, with persistent rare-rating and speaker-fold limitations.
The next engineering step is a separate occurrence-aware research inference
contract: identify the exact word/phone position when a consonant repeats and
verify raw-WAV feature parity against the completed position export. Preserve
the legacy duplicate-phone guard and all four existing bundles. This improves
research usability; it does not establish clinical accuracy or enable learner
judgments. The broader model-improvement goal remains active.
