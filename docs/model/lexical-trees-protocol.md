# Child scalar boosted-tree comparison

Declared September 27, 2026, before fitting. Current goal: a substantially
better ages-6–12 model, not merely more artifacts. This study tests a different
learner on the useful low-dimensional speech features. It is a development
comparison on reused data, not an independent clinical evaluation.

## Fixed comparison

Use exactly the 25 speaker-fold/word-group cells of the completed expanded
child-only study, with its original fitting, selection and refit memberships.
Fitting and selection exclude entire utterances containing the held-out word
group; speakers are disjoint from outer evaluation. Retain original selection
positions. Compare on all 5,654 original child positions across the 25 cells;
exclude added positions and older speakers from this study's outcomes.

Inputs are the 13 existing CTC scalars plus 23 explicit numeric one-hot canonical
phone columns. No word, speaker, age, recording ID or rating-derived feature.
No additional audio extraction or pretrained encoder changes. Existing fitted
scalar/PCA heads supply the fixed reference predictions; no reference tuning.

Fit CatBoost 1.2.10 on CPU in a separate environment. Fixed candidates are depth
4 and depth 6, both on every cell: 50 inner fits followed by 50 fresh refits.
Use MultiClass, three classes ordered 0/1/2, seed7, learning_rate0.05,
l2_leaf_reg3, bootstrap_type No, boosting_type Plain, grow_policy SymmetricTree,
random_strength0, leaf_estimation_method Newton, leaf_estimation_iterations1,
thread_count2, use_best_model false and no automatic stopping. Record resolved
parameters and all relevant versions. No class weighting or target encoding.

Each original fitting position becomes one copy for each positive vote count,
with class c and weight count[c]/5. Thus each position has total weight one;
weighted MultiClass cross-entropy is the intended equal-position soft-target
NLL. This states objective equivalence, not equivalence of every regularization
or implementation detail to a native soft-label learner. Rater votes are not
independent participants or resampling units.

Learn numeric quantization borders from the unexpanded fitting feature rows,
using 64 borders, Median policy and forbidden missing values. Save them before
class-copy construction and reuse them for the copies. Prediction uses the
trained model's borders. Refit learns fresh borders from unexpanded refit rows.
This prevents label-dependent copy multiplicity from changing preprocessing.

Train exactly 400 trees in each inner fit. Evaluate only stages 25/50/100/200/400
on original selection positions, using their five-vote NLL. In ascending order,
replace the incumbent only if loss < incumbent - 1e-7. Freeze all 50 selections
before refitting. Fresh refits use the selected tree count on the exact expanded
refit population. Freeze all 50 refits before computing outer predictions.
No outer-selected depth, blend, seed or threshold is authorized.

## Evaluation and success

Report each depth separately versus the fixed unweighted expanded child
scalar/PCA probability mixture (primary) and scalar-only head (descriptive).
Use stable float64 log-softmax of raw model logits and the original-position
rater counts. Compute per-rater NLL/Brier, represented-phone macro NLL, rating-0
and below-2 pooled-vote average precision. Preserve all 23 phone cells, seven
ages, five folds, 25 cells and each child's support and regressions. Missing
classes produce null ranking metrics. Do not use the library's PRAUC as AP.

A directional consistency pass requires lower pooled NLL, macro NLL and Brier,
higher both APs, and no speaker fold's pooled NLL worse by more than 1e-7. For
strict improvements use >1e-7 magnitude to exclude numerical noise. A separate
material-gain engineering target additionally requires at least 5% relative
pooled NLL reduction and at least 0.01 absolute rating-0 AP gain. These are
pragmatic research targets, not clinical thresholds. Smaller gains must be
reported as such; they do not complete the overarching goal. A pass justifies
replication and further robustness work, not learner release.

Keep both depths and every outcome. No retrying seeds or changing the screen
after results. Source/data checks, focused objective/quantization/selection/
serialization tests and independent source review precede fitting. Independently
check actual membership, saved predictions, metrics and conclusions afterward.
CPU use is bounded to this matrix; Colab remains available for work needing it.
No new labels, author-test opening or app policy changes. Learner, clinical and
promotion eligibility remain false.

## Method sources

Checked September 27, 2026. CatBoost's [weighted multiclass objective](https://catboost.ai/docs/en/concepts/loss-functions-multiclassification)
supports the vote-copy loss construction. Its [quantization interface](https://catboost.ai/docs/en/concepts/python-reference_pool_quantized)
accepts saved input borders. The [training parameter reference](https://catboost.ai/docs/en/references/training-parameters/common)
defines the fixed recipe and best-model behavior, which this protocol disables.
[Raw predictions](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_predict)
allow the project's own stable probabilities and scoring. These documents support
API behavior; expected benefit for this small speech dataset is a hypothesis.
