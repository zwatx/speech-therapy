# Checkpoint selection: modest gains, mixed evidence

The [fixed study](multiphone-selection-policy-protocol.md) tested whether
selecting a checkpoint for lower-rating detection improves held-out-speaker
results compared with selecting for overall probability accuracy. Both
objectives improve the primary pooled metric slightly, but the complete
comparison fails the predeclared consistency rule. No model is promoted.

## What ran

Ten child-only trajectories crossed five existing speaker folds with ordinary
negative log likelihood (NLL) and NLL plus the unchanged 0.1 pairwise auxiliary.
Each ran six epochs from its original warm checkpoint with identical fitting
rows, fit-only normalization, supervised order and fixed optimizer settings.
The run retained all 70 checkpoints, 3,468 updates and 110,976 sampled pairs.

All available historical prefix metrics and historical best/last model and
optimizer states matched exactly. Full validation metrics are now available
for both objectives at every epoch. Twenty NLL/AP selections were frozen
before any new outer prediction; each selected checkpoint replayed exactly.
The outer audit covers each of 14,837 eligible positions exactly once per
pipeline, including all 23 supported consonants. Six unsupported ZH positions
are excluded. Each row is scored by a model whose fitting and selection
speakers exclude that row's speaker. No outer-fit retraining occurred.

An initial setup attempt failed while hashing the Python executable, before
writing a declaration or fitting. That failure is retained. The corrected
runner passed a regression test and independent review before the successful
declaration; it did not change the training matrix or selection rules.

## Primary child results

These pooled cross-fitted results cover 5,654 positions in 1,037 recordings
from 52 children aged 6–12. AP is average precision over five-rater votes,
computed within each phone and averaged with equal phone weight. NLL and
Brier measure probability fit; lower is better. AP measures ranking; higher
is better. These are corpus ratings, not clinical correctness.

| Training objective | Selection | Macro NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | --- | ---: | ---: | ---: | ---: |
| NLL | NLL | .179402 | .077448 | .154335 | .189335 |
| NLL | Below-2 AP | .179352 | .077270 | .148006 | .194664 |
| NLL + .1 pairwise | NLL | .179649 | .077371 | .143569 | .186936 |
| NLL + .1 pairwise | Below-2 AP | .179479 | .077255 | .149805 | .192756 |

The primary AP-selected minus NLL-selected below-2 AP differences are
**+.005329** for ordinary NLL and **+.005820** for the pairwise objective.
Neither average is substituted for the per-fold results:

| Objective | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| NLL | −.000545 | +.004384 | +.000595 | .000000 | +.032081 |
| NLL + .1 pairwise | .000000 | +.006914 | +.001003 | +.000294 | +.004246 |

The declared consistency rule required positive pooled differences for both
objectives and no negative fold difference. Ordinary NLL's fold-0 decrease
therefore makes the overall result mixed. The pairwise branch's nonnegative
fold results remain visible; they do not justify selecting that branch after
seeing the audit. Ordinary NLL's rating-0 AP falls by .006329, while the
pairwise branch's rises by .006236. Probability scores improve slightly in
the pooled summaries but worsen in some individual folds. All four pipelines
still choose class 2 on 5,652 of 5,654 child positions and class 1 on two;
none chooses class 0.

## Unfamiliar words and support

There are 1,019 child target positions whose target word is absent from that
fold's child fitting vocabulary, versus 4,635 seen-word positions. The unseen
slice contains 500 word types and includes all 52 children. Word types may
appear in the seen slice of another fold; this is not word-disjoint testing.

| Objective | Unseen-word below-2 AP, NLL selection | AP selection | Difference |
| --- | ---: | ---: | ---: |
| NLL | .257502 | .256558 | −.000944 |
| NLL + .1 pairwise | .258311 | .261393 | +.003082 |

Unseen-word macro NLL gets slightly worse with AP selection in both objectives
(.268066→.269496 and .270116→.270438), although Brier improves slightly. The
higher absolute AP in the unseen slice is not evidence of better generalization:
its low-rating prevalence and phone support differ from the seen slice.
Below-2 votes are 333/5,095 unseen versus 904/23,175 seen.

All 23 phones have both positive and negative child votes in the pooled audit,
but /G/ rating-0 positives come from only one child. In the unseen slice, /DH/
has no lower-rating positive votes, so ranking is undefined there; /HH/ and
/SH/ below-2 positives each come from one child. Per-phone and per-fold
positive-speaker counts are retained in the machine-readable report. Pooling
does not remove these limitations.

## Decision and evidence

Close this continuation-selection lead for now under the predeclared rule.
Retain the small ranking gains and their tradeoffs as development evidence;
do not silently change the rule, continue the epoch search, select an objective
from the outer results, or replace a research bundle. The next useful work
should address the remaining data and representation limitations rather than
repeat this checkpoint search.

The outer speakers were held out from their own fold's fitting and selection,
but this author-training cohort has appeared in previous development studies.
Warm heads also inherited earlier NLL-based selection. Overlapping fold
training sets are not independent repetitions. No independent final-validation
claim or significance interval follows. Author-test data remains untouched and
learner pronunciation judgments remain disabled.

The [complete audit](../../research/audio-head/outputs/multiphone-20260927/selection-policy-audit-v1/report.md)
links to local saved results; its JSON retains all age/word/phone summaries,
prediction bindings and both primary contrasts. Evidence identifiers:

- Declaration: `4527193a16621aab3fea6d6b18257749088b56364cbdfdaca0663c64621c87d0`.
- Frozen selections: `731eef9f761eee495acc9714f4116bf9fcf062bf0b39ca045e6dda13a89191e8`.
- Audit JSON: `c0c8cdb649ba69e4eb1674e14c0b016e53200a0c9cfb647da329c89dc29a24e4`.

Fifteen focused tests passed. Training, selected-checkpoint replay and outer
prediction replay completed on the Mac; no Colab units were used. Independent
artifact/result review reconstructed all 20 fold outputs, four pooled pipelines,
216 age/word metric-support tables and 4,968 phone-support cells exactly. The
[verification record](../../research/audio-head/outputs/multiphone-20260927/selection-policy-audit-v1/verification.json)
binds these checks to the declaration, frozen selections and result JSON.
Broader application tests did not run because this change is confined to
research scripts, tests and documentation.
