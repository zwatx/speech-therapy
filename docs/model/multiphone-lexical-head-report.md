# Fresh-head word and speaker exclusion result

The richer phonetic representation does not beat the scalar-confidence baseline
under the declared whole-word and speaker exclusions. In both fitting regimes,
it worsens pooled child log loss, macro-phone log loss and both rare-rating AP
measures. Child-only fitting improves Brier score, but both fixed consistency
screens fail. Keep the scalar-only model as a required baseline for further
unfamiliar-word research; do not promote either family into learner judgments.

This experiment completed 100 fresh inner fits, 100 fresh outer refits and 100
held-out head passes. It tests the existing representation under stricter
supervised word separation. It does not establish that the scalar model is
universally better or that word memorization caused previous results: whole-
utterance exclusion also substantially reduces fitting data, model capacities
differ, and the pretrained encoder's lexical exposure is unknown.

## Matched design

The [protocol](multiphone-lexical-head-protocol.md) and source were fixed before
fitting. The [canonical inventory](multiphone-lexical-feasibility-report.md)
crosses five speaker folds with five fixed word groups, in both all-age and
child-only fitting. Every word in a fitting or selection utterance must be
outside that cell's held-out group. Speaker sets are disjoint. Both neural
families use exactly the same retained memberships and original five-rater
labels. No cell is dropped for missing phones or rare ratings.

The scalar model has 13 inputs and 38,147 parameters. The combined model adds
1,024 estimated target-local phonetic features and has 169,219 parameters.
Both use the existing phone-conditioned hidden-128 MLP and fresh seed-7 states.
The recipe fixes AdamW, learning rate .0003, weight decay .01, batch size 64,
clip norm 5, dropout .1, maximum 100 epochs and patience 15. Fit-only population
normalization and per-phone Laplace priors are recomputed for each fitting set.

Each inner run selects by five-vote per-rater NLL on its purged selection rows.
All 100 selected checkpoints and epoch counts were frozen before any refit.
Each refit starts fresh, uses its selected duration and has no validation
stopping. All 100 refits were frozen before outer predictions. No old trained
head or temperature correction was loaded into a fitting trajectory. Cached
encoder features were reused without running or updating an encoder.

Each family/regime covers every original eligible position exactly once across
25 outer cells: 14,837 positions from 125 speakers, including 5,654 positions
from 52 children aged 6–12. All 23 supported consonants remain represented.
The per-phone prior uses only the matching refit rows and is identical between
neural families in each cell. It is a fitting-data baseline, not a constant
population prevalence or chance-ranking score.

## Child probability quality and rare-rating ranking

Lower NLL, macro-phone NLL and Brier are better; higher AP is better. AP is
pooled vote-weighted ranking, not accuracy or an equal-phone average. Stable
float64 log-softmax of float32 logits supplies unclipped NLL; raw float32
probabilities are also saved. Scalar means confidence features alone;
target-scalars means the combined phonetic/confidence representation.

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.201926 | 0.213326 | 0.084075 | 0.028153 | 0.117063 |
| all-age / scalars | 0.180497 | 0.190224 | 0.083251 | 0.109133 | 0.174946 |
| all-age / target-scalars | 0.185832 | 0.194166 | 0.083579 | 0.073270 | 0.157082 |
| child-only / prior | 0.193713 | 0.206017 | 0.082935 | 0.022874 | 0.114274 |
| child-only / scalars | 0.182500 | 0.195113 | 0.082266 | 0.081084 | 0.153376 |
| child-only / target-scalars | 0.185655 | 0.197189 | 0.081253 | 0.057136 | 0.147690 |

Compared with scalars, the combined all-age head increases child NLL from
.180497 to .185832 and lowers rating-0 AP from .109133 to .073270. The combined
child-only head increases NLL from .182500 to .185655 and lowers rating-0 AP
from .081084 to .057136. Below-2 AP falls in both regimes. Child-only Brier
improves from .082266 to .081253, while all-age Brier worsens.

Both neural families improve pooled child NLL and both AP endpoints relative
to their matching priors. These pooled gains do not establish clinical utility,
per-phone reliability or consistent improvement across independent populations.

## Fixed screen and speaker folds

The table retains all six predeclared checks. All-age combined fitting fails
all six. Child-only combined fitting passes only Brier. Deltas are combined
minus scalar; positive NLL/Brier differences and negative AP differences are
worse. Speaker folds pool their five word groups.

| Check | all-age | child-only |
| --- | ---: | ---: |
| everySpeakerFoldChildNLLNoWorse | False | False |
| pooledChildBelow2APNoWorse | False | False |
| pooledChildBrierNoWorse | False | True |
| pooledChildMacroNLLNoWorse | False | False |
| pooledChildNLLImproves | False | False |
| pooledChildRating0APNoWorse | False | False |

| Regime / speaker fold | NLL change | Macro NLL change | Brier change | Rating-0 AP change | Below-2 AP change |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / 0 | 0.010003 | 0.011923 | 0.002686 | -0.063456 | -0.055424 |
| all-age / 1 | 0.004389 | 0.004195 | 0.001565 | -0.069036 | -0.043413 |
| all-age / 2 | 0.011998 | 0.008684 | 0.002874 | -0.062455 | -0.041611 |
| all-age / 3 | -0.005253 | -0.011281 | -0.005356 | -0.014333 | 0.010270 |
| all-age / 4 | 0.002118 | 0.002584 | -0.001566 | 0.002792 | 0.023177 |
| child-only / 0 | -0.003756 | -0.005609 | -0.003394 | 0.004882 | 0.012619 |
| child-only / 1 | 0.000844 | 0.002355 | -0.001564 | -0.035517 | 0.006583 |
| child-only / 2 | 0.006681 | 0.006923 | 0.001228 | -0.030942 | -0.022712 |
| child-only / 3 | 0.001319 | -0.005879 | -0.003452 | -0.013690 | 0.007371 |
| child-only / 4 | 0.008844 | 0.012100 | 0.000909 | -0.053490 | -0.037722 |

Combined child NLL is worse in four of five speaker folds for each regime.
It improves in all-age fold 3 and child-only fold 0. Consequently, the reverse
claim that scalars improve every fold is also unsupported. The 25 cells share
fitting populations and are not 25 independent participant replications.

## All 23 phones and sparse support

The table gives pooled child support and combined-minus-scalar changes. Each
position has five original votes; those votes are not independent participants.
The child count is all children contributing that phone, not children with a
rare rating. Positive NLL deltas are worse; positive AP deltas are better.

| Phone | Positions | Children | Rating-0 / below-2 votes | All-age NLL Δ | All-age AP0 Δ | All-age AP<2 Δ | Child-only NLL Δ | Child-only AP0 Δ | Child-only AP<2 Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 51 | 13 / 16 | 0.000440 | -0.030780 | -0.028966 | 0.000208 | -0.107313 | -0.180190 |
| CH | 42 | 29 | 8 / 10 | 0.020057 | -0.277976 | -0.197229 | -0.029527 | 0.018194 | 0.117715 |
| D | 322 | 52 | 37 / 64 | 0.028703 | -0.076745 | -0.062989 | 0.011764 | -0.031067 | -0.020375 |
| DH | 333 | 52 | 29 / 126 | 0.004927 | -0.025262 | -0.027677 | -0.010109 | 0.014140 | 0.023913 |
| F | 191 | 51 | 5 / 7 | -0.000056 | 0.019112 | 0.000755 | -0.004840 | 0.013761 | 0.042302 |
| G | 195 | 52 | 1 / 3 | -0.002378 | -0.004276 | 0.008098 | 0.005729 | -0.001834 | -0.007016 |
| HH | 237 | 52 | 7 / 9 | 0.000823 | 0.023949 | 0.044687 | -0.014792 | 0.112215 | 0.238002 |
| JH | 76 | 31 | 13 / 14 | -0.046545 | 0.123432 | 0.111773 | -0.018516 | 0.327043 | 0.358186 |
| K | 330 | 52 | 9 / 16 | 0.002441 | -0.003129 | -0.007797 | 0.001401 | 0.005259 | 0.000762 |
| L | 357 | 52 | 60 / 76 | 0.008530 | -0.012902 | -0.016258 | 0.016212 | -0.007908 | -0.019120 |
| M | 341 | 51 | 32 / 67 | 0.006302 | -0.050297 | -0.046763 | 0.015460 | -0.060093 | -0.061194 |
| N | 402 | 52 | 52 / 61 | 0.006593 | -0.074489 | -0.077918 | 0.007310 | -0.053769 | -0.094419 |
| NG | 119 | 48 | 10 / 18 | -0.003555 | -0.086700 | -0.081205 | -0.004802 | -0.012429 | -0.006685 |
| P | 153 | 50 | 15 / 25 | 0.021042 | -0.184655 | -0.132783 | 0.000104 | 0.160723 | 0.103976 |
| R | 304 | 51 | 60 / 82 | 0.003999 | -0.008703 | 0.028079 | 0.001394 | 0.024366 | 0.097321 |
| S | 378 | 52 | 35 / 45 | 0.021810 | -0.062146 | -0.106076 | 0.020011 | -0.218308 | -0.240646 |
| SH | 134 | 49 | 18 / 25 | -0.010190 | 0.036910 | -0.017335 | -0.016785 | -0.108045 | 0.158661 |
| T | 378 | 52 | 27 / 46 | 0.010017 | -0.035786 | -0.043682 | -0.005561 | 0.010518 | 0.009962 |
| TH | 75 | 40 | 19 / 94 | 0.034045 | -0.038316 | -0.026081 | 0.064813 | 0.008081 | -0.029737 |
| V | 200 | 49 | 17 / 93 | -0.006275 | 0.005381 | 0.023607 | 0.013366 | 0.004466 | 0.010033 |
| W | 323 | 51 | 18 / 22 | 0.010213 | -0.080328 | -0.097325 | 0.010400 | -0.047775 | -0.043119 |
| Y | 190 | 49 | 9 / 15 | -0.007284 | 0.112862 | 0.145202 | -0.000837 | -0.157937 | -0.144628 |
| Z | 338 | 52 | 38 / 303 | -0.012994 | -0.019947 | 0.036990 | -0.014634 | -0.065615 | 0.041896 |

Phone-level tradeoffs remain visible. For example, combined all-age fitting
improves JH log loss and both AP measures but worsens those three measures for
CH; child-only combined fitting improves all three for CH. Such contrasts have
little rare-event support: G has just one child rating-0 vote and CH has eight.
No phone-specific family is selected from these outer outcomes.

All fitting/refit cells contain all 23 phones, but seven child selection cells
lack phones. Only six of 25 child outer cells and 20 of 25 all-age outer cells
contain all 23 phones. Missing-phone metrics remain null. Rare-rating cells
without both vote classes retain undefined ranking quantities according to the
metric's definition; they are neither treated as successful predictions nor
removed from the report. Complete per-cell phone/age/word support, reliability,
AUROC and conditional NLL are retained in the machine report.

## Other age slices

These are descriptive slices of the same held-out predictions. They do not add
new participants or a new external validation cohort.

All ages:

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.293177 | 0.302118 | 0.136786 | 0.062471 | 0.124480 |
| all-age / scalars | 0.229729 | 0.233841 | 0.112958 | 0.401063 | 0.392335 |
| all-age / target-scalars | 0.247361 | 0.248918 | 0.119112 | 0.330458 | 0.330806 |
| child-only / prior | 0.309989 | 0.317467 | 0.138177 | 0.069503 | 0.127944 |
| child-only / scalars | 0.265951 | 0.271810 | 0.124078 | 0.318731 | 0.295106 |
| child-only / target-scalars | 0.306788 | 0.311951 | 0.134237 | 0.172329 | 0.199275 |

Ages 13 and older:

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.349360 | 0.356764 | 0.169241 | 0.083654 | 0.135088 |
| all-age / scalars | 0.260041 | 0.261913 | 0.131249 | 0.477197 | 0.465610 |
| all-age / target-scalars | 0.285245 | 0.284600 | 0.140990 | 0.405247 | 0.396719 |
| child-only / prior | 0.381581 | 0.386047 | 0.172190 | 0.098105 | 0.141196 |
| child-only / scalars | 0.317333 | 0.319677 | 0.149823 | 0.415578 | 0.365596 |
| child-only / target-scalars | 0.381371 | 0.383696 | 0.166860 | 0.236862 | 0.237137 |

## Selection duration

These are the frozen inner choices, before refitting and outer prediction.
Fewer epochs alone do not establish better generalization.

| Regime / representation | Runs | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: | ---: |
| all-age / scalars | 25 | 4 | 13 | 32 |
| all-age / target-scalars | 25 | 3 | 6 | 10 |
| child-only / scalars | 25 | 8 | 21 | 46 |
| child-only / target-scalars | 25 | 3 | 7 | 13 |

## Verification and artifacts

Thirteen focused tests passed, including extreme-logit NLL, fit-only moments,
repeatable training, stopping/tie semantics, failure-history retention, whole-
utterance exclusion, freeze guards and malformed-history rejection. A separate
manual two-update calculation exactly reproduced both model families' initial
weights, final parameters, optimizer state and training loss on synthetic data.
Independent GPT-6 Sol reviewed the parent-authored runner and protocol; the
parent independently reviewed Sol's core. Astra review attempts hit the native
agent limit; Astra did not review this study.

Actual declaration, 100 inner fits, 100 refits, 100 outer predictions, report
calculation and offline reconstruction finished with exit zero. The independent
[artifact audit](../../work/lexical-head-audit-20260927/summary.json) passed
34,622 inner checks, 11,732 refit checks, 93,021 outer checks and 1,885,068
metric/support checks. It imported only the frozen low-level model architecture,
not the training core, runner or reporting helpers. All 100 selected inner
checkpoints and all 100 final refit checkpoints reproduced their probabilities,
raw float32 probabilities, stable logs and NLL exactly through a separate tensor
path. Fit-only moments/priors, fresh initialization and its Python/Torch RNG,
optimizer step counters, permutation RNG/history, update counts and stopping
matched. The audit independently checked NLL/conditional NLL, Brier, AP/AUROC,
macro-phone measures, entropy, reliability and support across all cells, folds
and pooled outputs, including undefined slices and the fixed comparisons. The
complete report also reproduced exactly through the separate offline run of the
frozen reporting code. Actual optimizer moment values at every training step
were not independently reconstructed; the two-update synthetic oracle checks
those values for both families.

A separate [auxiliary-metric reconstruction](../../work/lexical-head-audit-20260927/ancillary-result.json)
passed 1,475,025 checks across 186 summaries and 1,674 metric slices. It covers
MSE/MAE/PCC, metric examples/speakers/vote counts, argmax weights and recalls,
class/event prevalence, macro support/exclusions, remaining confidence fields,
reliability bin metadata and empty-slice behavior. It performed no training or
model inference. Independent narrative review checked all 61 numerical table
rows, complete-phone cell counts and the limits stated in this report.

The retained outer audit stdout has a display-only final counter of zero;
its artifact records `jobsAudited:100` and its log contains 100 replay receipts.
The audit summary explicitly records this display discrepancy, and the original
log and result are retained. It does
not affect the successful replay count or metric evidence.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-heads-v1/plan.json): `bd55f8ab41f52137c6be6f5f9bfefbad64c3855d4ed84077a26245a600edfa18`
- [Inner freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-heads-v1/inner-freeze.json): `5058514d26211fafbd23f89a99ec39d7167d28f9063e61b857596902c18fbe53`
- [Refit freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-heads-v1/refit-freeze.json): `d3f3767aceb74d7157d0a2093d5b6f6d5accd7ba426f59aebfeccfb54c236676`
- [Outer freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-heads-v1/outer-freeze.json): `53b1ac63258dc7c09804cd64572ac2ac2628646e528cf79ed0bb3076d0a6bbb0`
- [Complete result](../../research/audio-head/outputs/multiphone-20260927/lexical-head-audit-v1/report.json): `6f4680ddf6b3f89b4e9796d7bd21d2b0f44c2232cd1cf361efbf38c3c45291fb`

The frozen runner is `research/audio-head/lexical_heads/study.py`. From the
research directory, use `.venv/bin/python -m lexical_heads.study`: `declare`
accepts a fresh `--output`; `inner` accepts `--plan` and `--plan-sha256`;
`refit` and `outer` additionally require the immediately preceding `--freeze`
and `--freeze-sha256`; `audit` adds a fresh `--output`; `verify` uses the existing
audit output. All corresponding artifact hashes are listed above. Training
phases reject existing run directories. Do not rerun them against these outputs.

## Decision and limits

Retain the existing four research bundles and keep learner pronunciation
judgments disabled. This comparison supports using the scalar model as a
mandatory baseline for unfamiliar-word work and rejects treating the larger
representation as an automatic improvement. It does not choose a new deployed
model, a phone-specific mixture or a learner-feedback threshold.

These are repeatedly studied author-training speakers; hyperparameters and
architecture have already been developed on this corpus. The new exclusions
apply to supervised fitting and selection, not the pretrained model's lifetime.
The fixed screen is descriptive development evidence, not an untouched final
test or clinical validation. The corpus has children aged 6–12 and no established
SSD cohort or ages 2–5. All labels remain subjective corpus ratings rather than
verified produced-phone transcriptions. No author-test recordings, new audio,
Colab allocation, app code or learner-feedback behavior were used or changed.
App builds/UI tests were not run because this work only changes research code
and documents.

A useful next step is a separately declared test of a compact phonetic
representation against the scalar baseline, with dimensionality reduction fitted
only on inner fitting rows and no search over the exposed outer results. That
would test whether the current high-dimensional representation can contribute
under limited fitting data. It remains an untested research hypothesis; the
present result does not establish that dimensionality is the cause.
