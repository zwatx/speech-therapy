# Fixed compact phonetic features on canonical lexical splits

The [fresh lexical comparison](multiphone-lexical-head-report.md) favored
scalar-confidence features on pooled child NLL and rare-rating AP over the
1,024-dimensional phonetic representation. This follow-up tests one fixed
compact representation. It does not establish that dimensionality caused the
previous result, and uses already studied development speakers and outcomes.

## Fixed transform and model

Use exactly the previous canonical whole-utterance word exclusions, speaker
partitions, five word groups, five speaker folds and both fitting age regimes.
There are 50 candidate inner fits, 50 fresh refits and 50 outer prediction
passes. Reuse the complete, hash-pinned scalar, full-phonetic and fitting-prior
results as reference controls; do not train or select new controls.

The sole candidate concatenates 16 principal-component scores of the raw
1,024-dimensional cached target-local phonetic vector with the original 13
confidence scalars. The dimension is fixed at 16 before fitting; there is no
dimension, variance-retention, seed, regularization or architecture search.

For each fitting set, take only its retained rows, cast target vectors to
float64, subtract their mean, and form the population covariance XᵀX/n.
Use deterministic CPU Torch with two threads and `torch.linalg.eigh`; retain
the 16 largest-eigenvalue eigenvectors in descending order. Resolve each
eigenvector's sign by making its largest-absolute coordinate positive, taking
the first index on ties. Do not standardize raw target dimensions or whiten
before projection. Reject a nonfinite transform or a 16th eigenvalue at most
1e-12 times max(1, largest eigenvalue). Do not reduce rank adaptively on failure.

Apply the same fitting center and basis to every input row, cast the 16 scores
to float32, then concatenate the 13 float32 scalars. Compute the usual head
normalization from the fitting rows of these 29 features only: float64
population mean/std, replace std below 1e-6 by 1, and store float32. Fit-only
per-phone priors use one pseudocount per class. Labels, selection rows and
outer rows do not determine any PCA parameter. Store the center, basis, all
descending eigenvalues, fixed rank, fitting indices and explained-variance
fraction; the latter is descriptive and never changes the chosen rank.

Keep the previous phone-conditioned hidden-128 architecture, 24 embedding
slots, dropout .1, fresh seed 7, AdamW learning rate .0003 and weight decay .01,
batch size 64, gradient cap 5 and deterministic CPU two-thread execution.
The new width is 29; its parameter count is 40,195, versus scalar 38,147 and
full combined 169,219. Capacity and representation change together.

Inner fitting selects by five-vote per-rater NLL with float64 log-softmax of
float32 logits. Maximum 100 epochs, improvement greater than 1e-7, patience
15 since the last improvement, and no eligible epoch-zero checkpoint. Preserve
the original equal-position soft cross-entropy and all original rater counts.

## Phase separation and saved evidence

Freeze all 50 inner transforms, checkpoints and selected epoch counts before
refitting. Every refit fits a new PCA on its exact purged outer-fit rows,
recomputes normalization/priors, initializes a new head and trains for the
previously selected epoch count. No validation stopping or outer prediction
is allowed during refitting. Freeze all 50 refits before outer inference.

Save `transform.pt` before its run configuration; the configuration binds its
content hash and every checkpoint binds that hash. Persist initial/best/last
states, optimizer and RNG records, every completed epoch's permutation digest,
update counts, training loss and inner selection predictions. Replay must
validate the saved transform exactly against an independently re-prepared
fit-only state, then reproduce selected predictions exactly. Keep failures and
partial histories in exclusive directories; never overwrite the previous study.

The transform and refit basis need not agree: their fitting rows differ.
This makes the method a training pipeline evaluated after refitting, with a
selected duration transferred to a newly fitted basis and fresh head. No state
or head weights are transferred between bases.

## Outcomes and fixed assessment

All 25 cells per regime are retained. Pool exactly 14,837 positions from 125
speakers, including 5,654 positions from 52 children aged 6–12, once per regime.
Reference row, speaker-fold and word-group identities must match exactly.
Preserve all 23 phone cells, absent metrics, undefined rare-rating quantities,
and age/word/speaker/vote support. Save raw float32 probabilities and stable
float64 probabilities/logs; use unclipped NLL throughout the report.

Report candidate-versus-scalar and candidate-versus-full-combined child
differences, plus candidate-minus-prior. The primary consistency screen is
candidate versus scalar: pooled child NLL improves by more than 1e-7, all five
speaker-fold child NLL values are no worse within 1e-7, pooled child macro-phone
NLL and Brier are no worse within 1e-7, and pooled child rating-0/below-2 AP are
no worse within 1e-7. Report the same checks against the full combined reference
as a secondary descriptive comparison. No improvement over the weaker reference
can replace the primary scalar comparison. Neither screen enables promotion.

Keep 25 cell summaries, five speaker-fold summaries pooling word groups and
pooled all-age/child/13-plus metrics, including NLL, Brier, AP/AUROC, reliability,
confidence and support. The 25 cells share training populations and do not
create new independent participants. No per-phone model mixing or reselection
is permitted after seeing outcomes.

## Verification and limits

Test PCA against a known eigensystem and an independent SVD/projector oracle,
fit-only row/label invariance, sign/rank rules, transform tamper rejection,
29-feature ordering, deterministic initialization and updates, stopping and
phase-order guards. Independently review source and reconstruct transforms,
saved histories, selected/final outputs, metrics, comparisons and interpretation.
The numerical training check must not use the new trainer as its own oracle.

This is a fixed adaptive research follow-up, not untouched validation. Previously
studied architecture and outcomes motivated the hypothesis; unknown pretrained
encoder lexical exposure remains. Fitting-set reduction and capacity changes
prevent causal attribution to word memorization or dimension alone. There is no
established child-SSD cohort or age-2–5 coverage. Ratings remain subjective
corpus judgments rather than produced-phone ground truth. No new data access,
encoder inference, author-test read, Colab allocation or learner judgment is
authorized by this protocol. Existing research bundles remain unchanged. App
build/UI tests are unnecessary for this research-code-only change.
