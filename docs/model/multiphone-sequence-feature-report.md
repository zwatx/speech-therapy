# Sequence-evidence augmentation study

The complete five-fold comparison does **not** meet the declared consistent-gain
rule. The sequence augmentation slightly improves probability fit but slightly
reduces the primary pooled child below-2 ranking measure. Existing research
bundles remain unchanged. This result applies to this fixed augmentation and
training recipe; it does not establish that all sequence evidence is useless.
The [fixed protocol](multiphone-sequence-feature-protocol.md) defines the four
columns, model branch, matched controls, selection and decision rule.

## Held-out development result

All five candidate trajectories completed six epochs: 30 epochs, 1,734
optimizer updates and 35 saved states including initialization. Each starts
from its original warm head. All five actual initial predictions match exactly;
the separately budgeted disabled-branch fold-0 epoch reproduces the retained
control's parameters, optimizer, RNG, metrics and probabilities exactly.

NLL selection retained epochs **[0, 2, 1, 0, 0]**, the same epoch numbers as the
matched ordinary-NLL controls. Three folds therefore keep the original model,
while two use a learned sequence branch. All ten selections and exact selected
replays were frozen before the new outer predictions. Both pipelines cover
each of the 14,837 eligible positions exactly once, using same-fold held-out
speakers. These are previously used development speakers, not an untouched
final cohort.

The child comparison covers 5,654 positions, 1,037 recordings and 52 children:

| Pooled child measure | Retained control | Sequence augmentation | Change |
| --- | ---: | ---: | ---: |
| Macro-phone NLL, lower is better | 0.179402 | 0.179379 | −0.000023 |
| Per-rater Brier, lower is better | 0.077448 | 0.077446 | −0.000002 |
| Rating-0 average precision | 0.154335 | 0.154340 | +0.000004 |
| Below-2 average precision, primary | 0.189335 | 0.189295 | −0.000040 |

Per-fold below-2 AP changes are **0, +0.000045, −0.000222, 0, 0**. The primary
pooled contrast is negative and fold 2 declines, so the predeclared rule fails.
The very small NLL/Brier differences do not justify describing this as a
reliable rare-error improvement. Both pipelines still have child argmax counts
**[0, 2, 5,652]** for ratings 0/1/2. Subjective rating distributions are not
clinical error labels; argmax counts alone are not an accuracy measurement.

The unfamiliar-word slice contains 1,019 child positions, 460 recordings and
500 target word types across 52 children. Its below-2 AP is unchanged at
0.257502; macro NLL changes from 0.268066 to 0.268014. Words are classified using
each fold's child fitting target vocabulary, so this is not a word-disjoint
experiment. The saved report retains seen-word, all-age and adult results,
all 23 phone cells with missing values explicit, positive-vote/speaker support,
AUROC, entropy and confidence. The five overlapping fitting sets are not
independent replicates; no significance claim is made.

## Complete feature coverage

All 2,495 author-training recordings produced four finite features for every
one of the 14,837 eligible positions across 23 consonants. The export retained
5,771,593 single-slot replacement/deletion likelihoods. No recording or eligible
row was dropped; no undefined value was imputed or clipped. The feature matrix
is float32 with shape 14,837 × 4. The underlying likelihoods remain in float64
JSON records, with impossible individual paths explicit where applicable.

The original three preflight recordings reproduced their saved numerical
evidence exactly. A second pass over those three again matched exactly. The
read-only artifact verifier reconstructed every feature from saved likelihoods,
checked row identities and matrix bytes, and rechecked bound input and output
hashes. This is verification of the calculation and export, not evidence of
pronunciation-rating accuracy. No new recognizer inference was needed.

The model branch adds 512 trainable weights and begins at zero contribution.
Synthetic tests verify exact original predictions at initialization, nonzero
branch gradients, identical original updates when the branch is disabled,
and fitting-only normalization. The full augmentation includes both new
information and added capacity; this comparison does not isolate those causes.

## Verification and next step

All 33 focused sequence tests passed. The new exporter, model, trainer and
auditor received separate review before execution. The saved full export was
independently audited across 5,022 input bindings, all clip artifacts, all
hypotheses and the reconstructed matrix. A fit-only row preparation bug and
test-fixture issue were fixed before training declaration; no extra candidate
fit or changed recipe was needed. The independent saved-study audit passed:
35 candidate states, ten frozen selections, exact disabled-branch equivalence,
ten outer outputs, 108 age/word metric-support tables and 2,484 phone-support
cells. All five control outputs match the earlier audit exactly. The reviewer
used saved evidence without repeating inference or fitting.

Retain the implementation and the fixed result as research evidence, with no
promotion. The next direction is the accessible phone-annotation data path:
verify an actually available annotated sample and its supervision contract,
then assess whether available labeled errors can support a distinct experiment.
A sample alone cannot supply a representative child error cohort. The current
result provides no reason to expand this warm-continuation hyperparameter search.

## Evidence

- [Feature declaration](../../research/audio-head/outputs/multiphone-20260927/sequence-features-v1/plan.json): `5924c3117bc9dcf30e5c67e1e96d3762088bf2c28f787c324dd769c39760cc84`.
- [Complete export](../../research/audio-head/outputs/multiphone-20260927/sequence-features-v1/features.json): `6f7ec75697d2f6502805f5e43965200a2683c49c78aa6208c6287f5eaa025114`.
- Matrix SHA-256: `cafb35ab5952993ae3630ba13b535199b4246f2fda5d66844dc5b95d554a585e`.
- [Training declaration](../../research/audio-head/outputs/multiphone-20260927/sequence-study-v1/declaration.json): `af761b2a84754f3e300cc528015e87d52d6ecb0e5280a919a9d404077f8ea18f`.
- [Frozen selections](../../research/audio-head/outputs/multiphone-20260927/sequence-study-v1/freeze.json): `f15d7587aefe392f0348503037832bf83b789fa8632ad356db8eeb9e80d987bd`.
- [Held-out development report](../../research/audio-head/outputs/multiphone-20260927/sequence-audit-v1/report.json): `700ab250579fc08f482ad9ac40f7dfedb413175b2771d60df6b024fec5be2930`.

All work in this study uses the Mac CPU. No Colab units, author-test data,
participant recordings or learner judgments are involved. Existing research
bundles are unchanged. Broader application checks do not apply to these new
research scripts and documents.
