# One fixed scalar/corrected-projection probability mixture

The [projection correction study](multiphone-lexical-projection-report.md)
showed small all-age child gains over PCA while losing calibration metrics to
the existing scalar/PCA mixture. This study tests whether the same fixed
scalar combination retains useful correction. It is an adaptive development
comparison prompted by exposed results, not untouched validation.

## Fixed inputs and computation

Use all 50 frozen scalar and corrected-projection outer prediction pairs:
25 original speaker-fold × canonical whole-utterance word-group cells in each
of the all-age and child-only training regimes. Verify the complete original
source declarations, inner-selection/refit/outer freezes, checkpoint lineage
and hashes. The corrected projection must descend from the matching original
PCA head, and its saved zero-delta outer replay must be exact. Require identical
inner-fit, selection, refit and outer memberships, speaker folds, word groups,
cohort and five-rater labels. All original whole-utterance lexical exclusions
and speaker separation remain unchanged, including missing-phone cells.

Calculate exactly half scalar probabilities plus half corrected-projection
probabilities, using the same weights for every class, phone, speaker, word and
row. Reuse the frozen, independently tested `lexical_mixture.study.mixture`
function: float64 `logaddexp(logScalar, logProjection) - log(2)`, then exponentiate
for ordinary probabilities. NLL uses stable logs and original five-vote counts.
Do not average logits, fit or search weights, add probability floors, renormalize,
calibrate, fit transforms, run head/encoder inference or train any parameters.
Preserve finite logs when ordinary probabilities underflow. No artificial raw
float32 network output is introduced.

Pin this protocol, new source/tests, all original source inputs, exact prediction
pairs, freezes and reference reports before calculating mixtures. Use a fresh
ignored output directory, preserve failures and reconstruct the full report
offline. Original model parameters, source packages and protocols are immutable.

## Fixed comparisons and complete reporting

The primary comparison is against the **existing half-scalar/half-PCA mixture**.
Apply the unchanged six-part screen: pooled child NLL improves by more than
1e-7; each of five speaker-fold child NLL values is no worse within 1e-7;
pooled child macro-phone NLL and Brier are no worse within 1e-7; pooled child
rating-0 AP and below-2 AP are no worse within 1e-7. Report every check and
signed difference. Apply identical secondary descriptive screens against scalar
and corrected projection, plus pooled child differences against matched priors.
Secondary gains cannot replace a failed primary comparison. No result permits
promotion or outcome-based selection of folds, phones, regimes or weights.

Retain all 14,837 eligible outer positions from 125 speakers, including 5,654
positions from 52 children aged 6–12, exactly once in each training regime.
Report all 23 consonants; all-age, child and age-13-plus populations; all 25 cells;
all five speaker folds; and pooled results. Preserve absent-phone and undefined
rare-event quantities, canonical word/recording/vote support, per-phone
NLL/Brier/AP/AUROC, conditional NLL, reliability and confidence. Five votes and
repeated overlapping training populations are not independent participants.

## Verification and interpretation

Run the frozen mixture arithmetic tests (ordinary mean, high-precision Decimal,
extreme logs, identity, malformed inputs) alongside new partition/provenance,
fresh-output and declaration-before-calculation guards. Independently review
source and protocol before declaration. Independently reconstruct all 50 new
mixture vectors from pinned source predictions with separate arithmetic; check
full source/checkpoint/partition lineage, all nested metrics/support and every
comparison. Review final numerical tables and claims independently. Prior
source-head replays remain historical evidence; this study does not replay heads
or reconstruct their complete optimizer trajectories.

A retrospective saved-prediction mixture does not provide a deployed two-head
adapter or measured end-to-end latency. Development speakers have been reused
repeatedly; pretrained lexical exposure is unknown. No ages 2–5, established
child-SSD cohort or verified produced-phone ground truth is added. Close this
single-combination experiment after its declared result, without a weight sweep.
Keep learner judgments disabled. No author-test, new audio, Colab allocation or
app changes; app builds/UI tests are unnecessary for this research calculation.
