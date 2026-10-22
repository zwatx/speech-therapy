# Posterior pooling matched model comparison

This prospective training protocol follows the fresh-controls protocol and separately declared full extraction. It does not authorize fitting yet. Full extraction and verification must pass, receive independent results review, and supply fixed artifact hashes to a new training declaration. Preserve all prior studies and failures. The cohort has been explored extensively; this is development evidence, not untouched confirmation.

## Paired features and fixed jobs

Use the full extraction's candidate and fresh hard float32 matrices, each (9891,1024), unchanged 13 scalars and exact original row indices. Both matrices arise from the same per-recording encoder forwards. Historical compact features and mixtures are descriptive only. All 23 consonants and ages 6–12 remain in scope; do not select phones, ages, words, speakers or recordings from outcomes.

Use seeds 17, 29, 43 and all original five speaker folds × five word groups at each seed: 75 cells. Retain the exact ordered fitting, selection, added-validation, refit and original-child outer memberships, whole-utterance word purging and original-child outer coverage of 5,654 positions per seed. Copy memberships from the frozen declarations and validate them against the unchanged cohort; no new split or seed search.

For both acoustic arms fit the unchanged 16-component centered covariance PCA on fitting rows only, without whitening or column scaling; concatenate the same 13 scalars and use fit-only head normalization and priors. Preserve the original 1024-input compact implementation. Use the same 29-input head, phone embeddings, width128, dropout0.1, AdamW learning rate0.0003/decay0.01, batch64, clip norm5, ordinary equal-position five-vote categorical NLL, maximum100 inner epochs, patience15 and improvement tolerance1e-7. Reset identical random streams and require bit-exact initial model tensors for corresponding acoustic arms. Refits use each arm's selected inner epoch count. No epoch-zero selection, objective/PCA/kernel/layer/seed search, recalibration or across-seed ensemble.

## Scalar component and phase order

Use exactly the same scalar head in both equal compact/scalar mixtures. Before any fitting, validate and replay all 75 original scalar controls: exact recipe, ordered memberships, fitting normalization/priors, saved initial/checkpoint state and inner selection/refit/outer predictions. Source/runtime and previously reviewed trainer-parity receipts must match. Record the complete all-cell reuse decision before any inner fits.

If any scalar scientific compatibility or prediction replay fails, use fresh scalar inner fits and refits for all 75 cells under the identical recipe and memberships. Do not mix old and new scalar controls or choose a fallback from model-quality results. Source drift or malformed lineage is an integrity failure to resolve under a new declaration, not permission to silently fit a substitute. Both arms always share the chosen scalar component.

Freeze all inner fits before any refits, and all refits before outer scoring. With scalar reuse, this means 150 acoustic inner fits, 150 acoustic refits, and 150 acoustic outer passes; scalar control replays are separately recorded. The all-cell scalar fallback adds 75 inner fits, 75 refits and 75 outer passes. Preserve exclusive outputs and partial failures; no incomplete phase may be evaluated.

## Numerical decision fixed before fitting

Use the unchanged stable-log, five-vote metrics, weighted binary AP and identical support. At each of the three seeds the primary candidate mixture versus fresh hard-control mixture must satisfy every condition:

- Pooled mixture NLL decreases by more than1e-7 and by at least5% relative to its matched control.
- Rating0 average precision increases by at least0.01 absolute.
- Each of the five speaker-fold mixture NLL changes is at most1e-7.
- Pooled macro-phone NLL and Brier changes are each at most1e-7.
- Below-rating2 AP change is at least−1e-7.
- Candidate compact-head NLL decreases by more than1e-7 versus its fresh compact control.

Undefined or nonfinite primary endpoints invalidate evaluation. All three seeds must pass; no seed selection or averaged-seed rescue. Fail the age guard if any age6–12 has mixture NLL worsening by more than1e-7 at all three seeds. Apply the same consistent-regression guard to each of all23 consonants. Report smaller or less-consistent regressions explicitly. Individual-child regressions are descriptive, not a reason to exclude a child. Keep undefined subgroup AP as null with its actual positive/negative support, never zero or an unreviewed category.

Report pooled metrics, deltas and checks per seed, all five folds, seven ages,23 phones and52 children with identical support across arms; show rating0 AP and macro NLL for age6. Show each subgroup's three NLL changes and all-seed regressions, training/extraction/replay counts and timings. PCA variance and posterior-weight diagnostics are descriptive, not tuning criteria. Means across seeds may be displayed only alongside all per-seed results.

Require independent post-run review and root reconstruction of predictions, mixtures, metrics, support and gates. Failure closes automatic replacement for this fixed recipe. A passed development comparison permits preparing separate confirmation and a research candidate, not enabling learner judgments, clinical use or declaring the overall goal complete. Independent child production/localization, recording-usability and nonspeech references remain missing.
