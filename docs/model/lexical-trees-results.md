# Child scalar boosted-tree results

Completed September 27, 2026. **Neither fixed tree model replaces the retained
scalar/PCA mixture.** Both improve rating-0 ranking slightly but worsen pooled
prediction loss, Brier score and below-2 ranking. Both fail the declared
directional and material-gain screens. This development comparison does not
establish clinical pronunciation correctness.

## What ran

The [fixed protocol](lexical-trees-protocol.md) used 13 existing speech features
and 23 one-hot canonical-phone columns. CatBoost 1.2.10 fitted depths 4 and 6 on
all 25 existing speaker/word-group cells. Every fitting utterance containing a
held-out word group was excluded, and outer children were disjoint from fitting.
No new audio, labels, acoustic features or author-test data were used.

All 50 initial fits completed with 400 trees. Selection chose 100 trees for
three jobs, 200 for 15 and 400 for 32. All selections were frozen before 50
fresh refits; all refits were frozen before outer predictions. The respective
fitting phases took 13.39 and 12.28 seconds on the Mac CPU. No Colab allocation
was needed. Quantization used unexpanded fitting positions; weighted class
copies preserved total fitting weight one per position.

Evaluation covers exactly 5,654 original positions, 1,037 recordings, 52
children ages 6–12, 837 target words and all 23 consonants. There are
532/705/27,033 votes for ratings 0/1/2. These are subjective rater votes, not
independent participants or verified speech-error diagnoses.

## Fixed primary comparison

Lower loss and Brier are better; higher average precision (AP) is better.

| Measure | Retained mixture | Depth 4 | Depth 6 |
| --- | ---: | ---: | ---: |
| Per-rater NLL | 0.177459 | 0.177830 | 0.178438 |
| Phone-macro NLL | 0.189095 | 0.188565 | 0.190185 |
| Per-rater Brier | 0.080372 | 0.080845 | 0.080972 |
| Rating-0 AP | 0.092080 | 0.097585 | 0.095461 |
| Below-2 AP | 0.169876 | 0.168763 | 0.164721 |

Pooled NLL worsened by 0.209% and 0.552% for depths 4 and 6. Each worsened NLL
in three of five speaker folds and 14 of 25 cells. Depth 4 worsened it for
30/52 children, 11/23 phones and 6/7 ages; depth 6 for 29/52 children,
13/23 phones and 5/7 ages. These descriptive counts use the declared 1e-7
tolerance and do not make small subgroups precise estimates.

Both candidates beat the scalar-only head on all five pooled endpoints, a
useful descriptive result. That weaker reference was not the primary promotion
comparison. The current mixture remains preferable under the fixed screen.
No depth, blending weight, seed or threshold was selected from outer outcomes.
All phone, age, fold, cell and child results, including missing-class nulls,
remain in the [machine-readable results](../../research/audio-head/outputs/multiphone-20260927/lexical-trees-v1/results.json).

## Verification and limits

Sixteen focused tests passed for features, five-vote objective equivalence,
label-independent quantization, saved-state replay, stage selection, tied-score
AP, per-rater Brier and phase-integrity rejection. Independent pre-fit review
verified exact source/plan bindings, all memberships and a bounded synthetic
inner/refit/outer rehearsal. All 50 real refits passed exact saved-model replay.
Independent post-fit artifact and metric verification is recorded separately.

This is another comparison on reused development data, not independent final
validation. Ages 8 and 10 each have only two children in the available cohort.
No learner feedback, clinical eligibility or automatic model promotion changed.
The experiment tests a different learner on the same information; its failure
does not imply that larger trees, more GPU spending or further tuning would
solve missing error supervision or recording-quality weaknesses.

Evidence: [declared plan](../../research/audio-head/outputs/multiphone-20260927/lexical-trees-v1/plan.json),
[selection freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-trees-v1/inner-freeze.json),
[refit freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-trees-v1/refit-freeze.json),
[outer freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-trees-v1/outer-freeze.json),
and [source review](../../work/lexical-trees-review-20260927/source-review.json).
