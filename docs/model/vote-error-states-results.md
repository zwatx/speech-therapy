# Observed vote agreement and model-mode results

Completed September 28, 2026. **Most prediction loss falls on mixed-rating positions, while the matched reference mixtures miss every unanimous rating-0 position by model mode.** This is descriptive evidence for pursuing stronger supervision, not a new model improvement or a clinical correctness result.

The [prospective protocol](vote-error-states-v1.md) fixed all three states, tie handling, outputs and coverage before calculation. All 5,654 original positions remain included across all three seeds and five saved model outputs, with every fold, age, consonant and child shown. The states are unanimous observed votes with matching model mode, unanimous votes with differing mode, and mixed votes. Exact stable-log ties choose class 0 before 1 before 2. The mode partition introduces no operating threshold.

## Matched reference mixture

| Seed | State | Positions | Share of NLL | Share of empirical NLL excess | Mean maximum predicted probability | Mean probability of unanimous observed class |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 17 | Unanimous, mode agrees | 4847 | 16.158% | 29.968% | 0.968950 | 0.968950 |
| 17 | Unanimous, mode differs | 11 | 3.130% | 5.804% | 0.817923 | 0.126129 |
| 17 | Mixed votes | 796 | 80.712% | 64.228% | 0.862682 | — |
| 29 | Unanimous, mode agrees | 4847 | 16.839% | 31.327% | 0.967743 | 0.967743 |
| 29 | Unanimous, mode differs | 11 | 3.135% | 5.833% | 0.826648 | 0.115845 |
| 29 | Mixed votes | 796 | 80.026% | 62.840% | 0.861250 | — |
| 43 | Unanimous, mode agrees | 4847 | 16.500% | 30.913% | 0.968569 | 0.968569 |
| 43 | Unanimous, mode differs | 11 | 3.007% | 5.633% | 0.812474 | 0.127466 |
| 43 | Mixed votes | 796 | 80.494% | 63.454% | 0.861523 | — |

The 796 mixed positions (14.1% of the population) contribute about 80% of NLL and 63% of the gap above the empirical five-vote entropy floor. This does not show that their error is irreducible noise: the empirical floor is biased low with only five votes, and the model may also miss learnable structure.

At all three seeds the reference mixture has the same unanimous-class by model-mode count matrix:

| Unanimous observed class | Model mode 0 | Model mode 1 | Model mode 2 |
| --- | ---: | ---: | ---: |
| 0 | 0 | 0 | 9 |
| 1 | 0 | 0 | 0 |
| 2 | 2 | 0 | 4,847 |

Thus all nine unanimous rating-0 positions receive mode 2, and two unanimous rating-2 positions receive mode 0. These eleven disagreements contribute roughly 3% of total NLL and 6% of the empirical excess. Their mean maximum predicted probability is about 0.81–0.83, while the mean probability assigned to the unanimous observed class is about 0.12. Nine positions are far too few to establish broad rare-error utility, and model mode is not a validated learner decision.

The matched reference models are the three fresh hard-control acoustic/scalar mixtures from the completed [pooling comparison](posterior-pooling-model-comparison-results.md). This is not a fresh test of the retained seed-7 full-data research export. The candidate and scalar-only outputs remain in the detailed result; no arm or state is selected as a winner.

## Verification and implications

Eleven focused tests passed before declaration and review (five new state tests and six frozen parent tests). The declared calculation binds 166 inputs and six sources, plus the original ordered 75 cells, 5,654 child positions, seeds and runtime. Actual Opus 5.5 independently reviewed the supplied source and actual declaration before execution. Calculation completed successfully with exclusive outputs. Every state partition and confusion matrix is complete, and recombining states recovers all parent loss/decomposition means within the fixed 1e-12 arithmetic tolerance.

Root independently rebuilt 84,810 position-by-model state assignments using separate scalar classification, 50-digit Decimal loss arithmetic and separately reconstructed mixture logits. It verified all 264 views across five outputs, supports, confusion matrices, totals, means, shares, probabilities and parent recombination, then rechecked all input/source/plan/review hashes. No model fit, inference or Colab allocation occurred.

Actual Opus 5.5 independently reviewed the result interpretation with no blocking findings. Its tool-free review covered pooled outputs for every arm and subgroup outputs for the two mixtures; checks of the other three arms’ subgroups rely on the complete root reconstruction. It independently performed no execution or hashing.

State membership can differ across model arms, so their conditional losses are not paired comparisons. Unanimity of five observed votes does not demonstrate population certainty, produced-phone truth, clinical correctness or acoustic learnability. Mixed votes do not prove irreducibility. Children, raters and recordings recur; this cohort is extensively explored. No subgroup exclusion, threshold, noise model, speaker effect, model-family closure, promotion or learner feedback follows. The failed pooling recipe stays closed and the existing research bundle stays unchanged.

A practical next direction is to establish stronger human phonetic/error supervision that is actually accessible. Adult L2 annotation would not validate children; automatic phone alignments are not human production labels. Provider access and actual released annotation fields must be verified before any new corpus or learning recipe is declared.

## Evidence

- [Frozen plan](../../research/audio-head/outputs/multiphone-20260928/vote-error-states-v1/plan.json): `59ca5ef49414178d629eb233343308a0caa61bc3467b04aabad7b6c0f775bba8`.
- [Detailed results](../../research/audio-head/outputs/multiphone-20260928/vote-error-states-v1/results.json): `0af8cf9881fe900eefed17b3a10d4d53d7cd675bedeb06306b5423d3f891319a`.
- [Actual Opus 5.5 source/declaration review](../../work/core-model-next-method-20260927/opus-vote-error-states-review.json): `3a9571bcf357f1eeab3bc453c67bd127cac9e81b87db8297d105c85b0b4d5118`.
- [Independent root reconstruction](../../work/core-model-next-method-20260927/vote-error-states-results-root-observation.json).
- [Actual Opus 5.5 results review](../../work/core-model-next-method-20260927/opus-vote-error-states-results-review.json): `9d7fe4cd2d64ad491ab6ddd180e1117a8ccebbb63af8c6728ee7c72f13698dda`.
