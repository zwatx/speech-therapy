# Expanded fitting data with fixed lexical selection examples

This experiment follows the completed
[full occurrence support inventory](multiphone-lexical-expansion-report.md).
Its hypothesis is that additional permitted canonical occurrences improve the
existing scalar and compact phonetic pipelines under the same unfamiliar-word
and speaker exclusions. This is an adaptive development follow-up, not untouched
final validation. No data-support increase is itself a model improvement.

## Fixed populations and fitting policy

Use all 28,227 expanded author-training occurrences in 2,500 recordings, the
same five speaker folds and complete-utterance canonical lexical exclusions,
five word groups and both all-age and child-only fitting regimes. Keep all
23 supported phones. Do not change speaker assignments, word hashes, labels,
age restrictions or recording exclusions. No new audio extraction, author-test
decoding, participant collection or Colab allocation is needed.

For each of the 50 regime/speaker/word cells, inner fitting uses all expanded
retained inner-fit occurrences. Checkpoint selection uses exactly the original
retained selection examples in their original order, mapped to expanded row
indices. The added occurrences from inner-validation speakers are excluded
from both inner fitting and selection. Preserve those indices explicitly as
`addedValidationRows`; do not silently put them into fitting or discard them
from the final refit.

After every inner run is frozen, each refit uses the complete expanded retained
outer-fit set. Its exact union is expanded inner fit, original selection, and
added inner-validation occurrences. These groups are position-disjoint; inner
fit and validation speakers are disjoint, and all refit speakers are disjoint
from outer speakers. The child-only restriction applies to all three supervised
groups. Outer membership stays all ages. This tests expanded fitting data while
keeping the selection population fixed; it is not the alternative experiment of
selecting on expanded validation examples.

The original 14,837 outer occurrences, including 5,654 child occurrences, are
the common primary comparison population. Report the 13,390 added occurrences
and all 28,227 occurrences separately as descriptive populations. Never compare
their scores to historical original-only scores as if populations were equal.
All 125 speakers, including 52 children aged 6–12, were already present. Repeated
occurrences are not independent participants. Preserve sparse or absent sounds
and event classes, including the seven child selection cells missing a sound.

## Fixed models and budget

There are exactly 100 inner runs and 100 fresh refits: scalar and PCA16-plus-scalar
families × two age regimes × five speaker folds × five word groups. Use the
immutable `lexical_heads.core` and `lexical_compact.core` training implementations.
The scalar head uses 13 existing confidence features; the compact head uses
16 fit-only phonetic principal components plus those 13 scalars. Reuse the exact
float64 covariance/eigensolver/sign/rank policy in the
[compact protocol](multiphone-lexical-compact-protocol.md). Fit normalization,
PCA and one-pseudocount-per-class phone priors only on the current fitting rows.
Every refit learns its own transform and normalization from its expanded refit
rows and initializes a fresh head; do not transfer a head across PCA bases.

Keep seed 7, hidden width 128, dropout .1, 24 phone embedding slots with only
the supported 23 targets, AdamW learning rate .0003 and weight decay .01,
batch size 64, gradient norm cap 5, deterministic CPU execution with two threads,
equal-position five-vote soft cross-entropy, and no class reweighting. Select
inner epochs by original-selection five-vote per-rater NLL using unclipped
float64 log-softmax of float32 logits. Maximum 100 epochs, patience 15, improvement
greater than 1e-7, no eligible epoch-zero checkpoint. Refit for the corresponding
selected epoch count, without selection or outer predictions during refitting.

This preserves the epoch-selection rule, not the number of gradient updates.
Expanded epochs have more batches and different shuffles; fitted moments/PCA
also change. Report selected epochs and update counts. Do not attribute a
difference solely to the informational content of added recordings or ratings.
No learning-rate, rank, weight, architecture, seed, duration or exclusion sweep.

## Phase separation and evidence

Pin the completed expansion declaration/report and every bound upstream source,
metadata and feature artifact. Check the full original label/feature join,
the exact original fit/selection/refit/outer membership against the historical
head declarations, the complete new 100-job matrix, and every whole-utterance
word exclusion before declaration. Reference reports and plans are hash-bound;
their outer outcomes are opened for comparison only after candidate outer
predictions freeze. Prior development outcomes have already informed this
hypothesis; this sequencing does not make them untouched validation.

Save initial/best/last checkpoints, optimizer and RNG states, every epoch's
shuffle digest/update count/loss and all original-selection probabilities/logs.
Compact runs also save and bind their transform. Replay selected checkpoints
exactly. Check checkpoint configuration, epoch, best epoch/loss, normalization,
prior and optimizer update lineage. Preserve failed runs in exclusive outputs.

Freeze all 100 inner runs before any refit. Freeze all 100 refits before any
outer inference. Run one outer prediction pass per refit on the full assigned
expanded outer set. Freeze all 100 prediction records before metrics and
historical comparisons. All original and added outer examples occur exactly
once per family and regime. Save raw float32 probabilities plus stable float64
probabilities/logs, fitting priors, row/fold/word identity and checkpoint lineage.

## Declared comparisons

For each age regime, report scalar, compact, fitting-prior and one fixed equal
scalar/compact probability mixture. Use the existing float64 log-add-exp mixture
arithmetic and weights .5/.5; do not select weights, phones or regimes. No
supervised projection correction is added to these new heads.

Primary original-population comparisons are expanded scalar versus original
scalar, expanded compact versus original compact, and expanded equal mixture
versus the original equal mixture. The stronger prior corrected-projection
mixture is an explicit secondary reference for the new equal mixture. Also
report original-population neural-minus-expanded-fit-prior differences.

Use the existing six-part development consistency rule separately for each
declared comparison: child pooled NLL improves by more than 1e-7; every child
speaker-fold NLL is no worse within 1e-7; pooled child macro-phone NLL and Brier
are no worse within 1e-7; pooled child rating-0 and below-2 AP are no worse within
1e-7. Preserve the inherited AP definition in `rating_temperature.study.primary`:
these AP endpoints pool child rating votes across phones, while per-phone and
macro-phone discrimination remain in the full summaries. Report all comparisons
and failures; a secondary pass cannot replace a failed primary comparison.

Retain original/added/all per-position outputs, all 25 cells, five speaker folds,
three age groups, all 23 phone metrics/support, NLL, Brier, AP/AUROC, reliability
and confidence. Original rows are explicitly mapped back to historical indices;
added/all indices remain expanded indices. Empty added cells retain null metrics
and zero support. Undefined rare-event quantities stay explicit.

## Verification and interpretation

Test original selection mapping, added-validation withholding/refit inclusion,
speaker/word/age exclusions, phase barriers, checkpoint metadata, declaration
integrity, full job/outer coverage, legacy label/identity changes, prior mismatch,
probability/log validation, old-index gaps/reordering, empty added cells and
unclipped underflow loss. Reuse the frozen tested optimization/PCA implementations;
run a small synthetic integration fit through each family and the new validator.
Perform a separate read-only review before declaration and independently verify
real transforms/checkpoints/predictions, memberships and reported comparisons.

More support does not resolve sparse child errors, absent age-2–5/established SSD
coverage, uncertain phone timing, unknown pretrained lexical exposure or subjective
rating labels. No model is promoted and learner judgments remain disabled.
App/UI builds are not required for this research-only change. The full campaign
objective remains active regardless of whether this bounded hypothesis succeeds.
