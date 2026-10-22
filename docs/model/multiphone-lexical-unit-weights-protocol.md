# Equal recording/sound-unit loss under fixed lexical exclusions

This fixed experiment follows the [complete sound-response diagnosis](multiphone-lexical-phone-response-report.md).
That diagnosis motivates a hypothesis about contribution from repeated occurrences;
it does not establish causation or identify defective examples. Keep every example,
every sound and every failed comparison. Declare all source/tests, this protocol,
input hashes and reviewed core before actual fitting. Keep them immutable thereafter.

## Fixed objective and population

Reuse every expanded occurrence and exactly the same 100 jobs as the completed
[expanded fitting experiment](multiphone-lexical-expanded-heads-report.md): scalar
and PCA16/scalar, all-age and child-only, five speaker folds crossed with five word
groups. Preserve all 28,227 positions, original 14,837-position correspondence,
original selection examples/order, complete-utterance word exclusions, speaker
separation and age restrictions. Added validation positions enter refitting only.
No changed partition, per-sound rule, weighting search or removal of examples.

For each current fit/refit partition, count complete canonical same-sound occurrences
in every retained recording. Normalize only terminal stress digits 0/1/2, retain
unsupported-phone gaps in geometry, and require all supported canonical positions
of every selected recording exactly once. Verify row word/phone/canonical index,
raw/normalized sound, speaker and age against the complete ordered canonical chain.
If a recording/sound group has k positions, each raw weight is 1/k. With n fitting
positions and g recording/sound units, each final weight is `(n/g)/k`. Every group
therefore contributes n/g total weight and mean position weight is one. Use only
current fitting metadata. Do not inspect ratings to compute weights. Recompute at
refit; never reuse inner weights or normalize on selection/outer examples.

Training loss is batch mean of fixed normalized weight times the existing five-vote
cross entropy. Do not divide by each batch's weight sum. Keep the existing last
partial-batch convention. Weights enter no class-prior correction, prediction,
checkpoint selection or evaluation metric. Save full ordered weight states and
bind them in configuration/checkpoints; rederive them for validation and replay.

## Fixed training and phase order

Keep seed7, fresh initialization,128hidden/dropout.1, AdamW lr.0003/decay.01,
batch64, gradient norm cap5, CPU2 and deterministic arithmetic. Keep original
unweighted feature moments/priors and compact fit-only PCA16, including float64
covariance, canonical sign and rank rule. This isolates the loss change; it does
not test weighted PCA or weighted normalization. Selection is original unweighted
stable-log NLL, up to100epochs/patience15/minimum gain1e-7; epoch0 ineligible.

Freeze all100 completed inner fits before any fresh refit. Refits use all original
and added refit positions, freshly initialized model, transform and weight state,
for exactly the selected positive epoch count. Freeze all100refits before any new
outer inference. Retain initial/best/last models, optimizer/RNG states, epoch histories,
permutation hashes, full configs, weight/PCA states and exact selected replay.
Exclusive outputs and failure records preserve partial work; never silently restart
an uncertain live process or overwrite an earlier experiment.

## Evaluation and fixed comparisons

Use the existing complete evaluator for original, added and all expanded views.
Primary contrasts are weighted minus corresponding unweighted **expanded** scalar,
compact and equal-probability mixture in each regime. The original corrected-
projection mixture remains a separately labeled secondary mixture control. No
fitted mixture weight, calibration, threshold or extra model family.

All primary matched comparisons use original indices and original child population
of 5,654 positions/52children aged6–12. Retain stable NLL, Brier, fixed23macro NLL,
rating0AP, below2AP, full support/reliability and all five speaker-fold deltas. Reuse
the same six-part development screen: pooled NLL difference < −1e-7; macro NLL
and Brier differences <=1e-7; both AP differences >=−1e-7; and every speaker-fold
NLL difference <=1e-7. Preserve exact failures and these existing tolerances.
Added/all expanded summaries stay descriptive; do not substitute them for original
matched evaluation. Keep all23phone class/fold/word-cell/child NLL contributions for
all eight fixed contrasts using the frozen response implementation. Missing means
remain null and empty additive contributions zero. Reconcile pooled response NLL
to the evaluator's child contrast. No automatic promotion or clinical claim.

## Verification and limits

Before declaration: test complete canonical group weights/order, rational group-mass
identities, all-single weights, partial-group rejection, fitting-only metadata and
refit normalization. Compare weighted loss gradients against independent arithmetic
and four AdamW updates against a manual reference. Run actual synthetic all-one
inner and refit trajectories against both frozen trainers, including partial batches;
require exact histories, selected epochs, models, optimizer states, RNG/permutation
states and predictions. Test weight/config/checkpoint tampering, phase barriers,
exclusive declaration, all-eight response pairing and substantive source review.
Validate actual input membership and weight geometry with training/PCA/prediction
calls forbidden before actual fitting. No actual corpus training has run merely
because synthetic tests or declaration succeed.

After fitting: independently check weight derivation, normalization/group mass,
checkpoint and optimizer/selection/permutation states, PCA lineage, exact outer
prediction replay and all numerical summaries against raw saved arrays. Reconstruct
the report offline and review every published numerical claim. Record tests and
actual process termination truthfully. No claim of full independent optimizer-
trajectory replay unless it was actually performed.

The weight rule may harm rare-rating information even while reducing repetition
mass. Evaluate the full tradeoff; do not claim that it fixes /W/ in advance. These
are repeatedly used development folds with subjective rating targets, no expert
produced-phone truth, no ages2–5 cohort and no established speech-sound disorder
validation. No new audio/encoder/author-test/Colab work or application change is
needed. Learner judgments remain disabled and the full improvement goal stays active.
