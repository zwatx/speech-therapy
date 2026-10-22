# Fixed descriptive input-support analysis

Prior feature validation already checked eligible row identities, canonical
word/phone indices, estimated windows, assembled/per-clip vector equality and
original scalar binding. It did not establish true acoustic phone boundaries.
This follow-up diagnoses input support, not verified alignment accuracy. The
speaker concentration was observed before this protocol; this is adaptive
exploration without new validation data.

Use every 5,654 original child position from 52 children and all 23 phones in
both fixed lexical regimes. Preserve all 50 original speaker×word cells and
whole-utterance exclusions. Use each cell's exact refit rows as its reference,
its saved scalar normalization and saved compact PCA transform. These states
were fitted before that cell's outer predictions; do not fit a new transform,
head, calibration, threshold or mixture weight. Keep all ratings/participants.

Compute two descriptive axes in float64:

1. Maximum absolute scalar z score across the 13 original features, using saved
   scalar refit mean/std. Save all 13 signed z scores and the first maximum's
   feature name; this is diagnostic arithmetic, not a replay of float32 head
   normalization.
2. Mean squared residual across all 1,024 phonetic coordinates after subtracting
   the saved PCA center and reconstructing through the saved 16-column basis.
   Use explicit residual vectors rather than subtracting squared norms.

For each axis retain the raw score, empirical midrank percentile in the entire
exact refit population, and percentile among refit positions of the same phone:
(count strictly below + half count exactly equal) / reference count. A value
above every reference value receives 1; a value tied with a constant reference
receives .5. Retain exact reference row IDs, counts and score vectors. Do not
assume these empirical ranks are calibrated out-of-distribution probabilities.
The transform and reference scores use the same fitting observations, so
fit-versus-held-out asymmetry is expected even without data defects.

For each of four fixed comparisons (two axes × global/same-phone), mark ranks
strictly greater than .99 as descriptive high-reference-tail membership. The
threshold is fixed before calculation and is not a candidate withholding rule.
Save every position and complete summaries for both tail and complement,
including zero-count groups, all 52 children, all 23 phones, all five speaker
folds and word groups. Show original five-vote support, mean NLL difference
(mixture minus scalar), additive NLL contribution and fraction with positive
NLL difference. Additive contributions always use the full regime's child
position denominator, so every complete partition sums to the pooled delta.
Retain original fold-4 and corpus-child-1435 results alongside the complete
cohort, never as the only reported subset. Report the 13-feature dominant-scalar
counts across all rows and each child. No diagnostic association establishes
causation, a recording defect, a label defect or a reason to exclude a child.

Declare inputs/source/tests/protocol before actual score calculation. Hash-bind
all source phases, features, transforms/checkpoints, previous predictions and
this declaration; keep them immutable thereafter. Test analytic residuals,
transform invariance, tie ranks, absent references, input guards, denominators
and no calculation before declaration. Reconstruct all output offline and use
an independent reviewer for artifacts and report claims. No raw audio, encoder
or head inference, author-test access, Colab use or learner-policy change.
