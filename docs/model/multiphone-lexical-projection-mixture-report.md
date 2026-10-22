# Fixed projection mixture: small gains, failed primary consistency

Combining scalar and corrected-projection probabilities at fixed equal weights
improves all five pooled child endpoints over the existing scalar/PCA mixture
with all-age fitting. Child NLL moves .178968→.178619; rating-0 AP moves
.121294→.122051. However, speaker fold 2 NLL worsens by .000061, so the primary
screen fails. With child-only fitting, pooled NLL improves .180393→.180298 but
rating-0 AP worsens .082126→.082056, and folds 2 and 4 NLL worsen. Neither
regime passes the primary comparison.

There is a concrete secondary gain: the all-age combination passes all six
predeclared checks against the scalar baseline, including better child NLL in
every speaker fold and all five pooled endpoints. That does not replace the
failed primary comparison against the stronger existing mixture, establish an
independent replication, or authorize learner judgments. The child-only scalar
screen and both projection-only secondary screens fail.

## Fixed method and population

The [protocol](multiphone-lexical-projection-mixture-protocol.md) fixed one
combination before calculation: .5 scalar probabilities plus .5 corrected
projection probabilities for every class, sound, speaker and recording. The
existing stable log-space average is reused without fitting, weight searches,
calibration, probability floors or extra normalization. NLL uses stable logs;
ranking and Brier use their exponentiated probabilities. No head or encoder is
run and no transformed recordings acquire human labels.

All 50 frozen source pairs retain identical original inner-fit, selection,
refit and outer populations, whole-utterance word exclusions and speaker
separation. Projection predictions bind the selected correction checkpoint and
the original PCA source; the historical zero-correction replay remains exact.
The new declaration binds 891 inputs. All prior sources and protocols stay
unchanged, and the new source/protocol is immutable after declaration.

Each regime includes every original eligible outer position exactly once:
14,837 positions from 125 speakers, including 5,654 positions from 52 children
aged 6–12. All 23 consonants, 25 speaker×word cells, five speaker folds and
all-age/child/age-13-plus outcomes remain. Sparse and undefined cell measures
are retained. Five rater votes do not create five independent participants.

## Complete outcomes

Lower NLL, macro-phone NLL and Brier are better; higher AP is better. AP is
ranking performance on subjective rater votes, not pronunciation accuracy.
`equal-mixture` is the primary scalar/PCA reference; `projection-mixture` is
this study's new fixed combination. Differences below are candidate minus
reference. Values are rounded here; the complete JSON retains full precision.

## ages6to12

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.201926 | 0.213326 | 0.084075 | 0.028153 | 0.117063 |
| all-age / scalars | 0.180497 | 0.190224 | 0.083251 | 0.109133 | 0.174946 |
| all-age / pca16-scalars | 0.181056 | 0.189664 | 0.082755 | 0.125172 | 0.186455 |
| all-age / equal-mixture | 0.178968 | 0.188141 | 0.082181 | 0.121294 | 0.185888 |
| all-age / projection | 0.180451 | 0.188898 | 0.082410 | 0.126397 | 0.188015 |
| all-age / projection-mixture | 0.178619 | 0.187712 | 0.081995 | 0.122051 | 0.186734 |
| child-only / prior | 0.193713 | 0.206017 | 0.082935 | 0.022874 | 0.114274 |
| child-only / scalars | 0.182500 | 0.195113 | 0.082266 | 0.081084 | 0.153376 |
| child-only / pca16-scalars | 0.183098 | 0.193685 | 0.081764 | 0.077252 | 0.155416 |
| child-only / equal-mixture | 0.180393 | 0.191686 | 0.081363 | 0.082126 | 0.157546 |
| child-only / projection | 0.183119 | 0.193407 | 0.081669 | 0.077025 | 0.156278 |
| child-only / projection-mixture | 0.180298 | 0.191453 | 0.081299 | 0.082056 | 0.158086 |

## allAges

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.293177 | 0.302118 | 0.136786 | 0.062471 | 0.124480 |
| all-age / scalars | 0.229729 | 0.233841 | 0.112958 | 0.401063 | 0.392335 |
| all-age / pca16-scalars | 0.230477 | 0.234239 | 0.111675 | 0.415324 | 0.402461 |
| all-age / equal-mixture | 0.227034 | 0.230927 | 0.111159 | 0.420423 | 0.407854 |
| all-age / projection | 0.230495 | 0.234071 | 0.111563 | 0.416693 | 0.403545 |
| all-age / projection-mixture | 0.226928 | 0.230726 | 0.111085 | 0.421077 | 0.408396 |
| child-only / prior | 0.309989 | 0.317467 | 0.138177 | 0.069503 | 0.127944 |
| child-only / scalars | 0.265951 | 0.271810 | 0.124078 | 0.318731 | 0.295106 |
| child-only / pca16-scalars | 0.278627 | 0.282125 | 0.126541 | 0.278487 | 0.269325 |
| child-only / equal-mixture | 0.266718 | 0.271344 | 0.124388 | 0.317157 | 0.289972 |
| child-only / projection | 0.279963 | 0.283378 | 0.126704 | 0.277915 | 0.268600 |
| child-only / projection-mixture | 0.267097 | 0.271689 | 0.124452 | 0.317364 | 0.289898 |

## ages13plus

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.349360 | 0.356764 | 0.169241 | 0.083654 | 0.135088 |
| all-age / scalars | 0.260041 | 0.261913 | 0.131249 | 0.477197 | 0.465610 |
| all-age / pca16-scalars | 0.260906 | 0.262993 | 0.129481 | 0.490335 | 0.474455 |
| all-age / equal-mixture | 0.256629 | 0.258578 | 0.129001 | 0.496050 | 0.480863 |
| all-age / projection | 0.261307 | 0.263181 | 0.129512 | 0.491609 | 0.475129 |
| all-age / projection-mixture | 0.256671 | 0.258520 | 0.128996 | 0.496594 | 0.481171 |
| child-only / prior | 0.381581 | 0.386047 | 0.172190 | 0.098105 | 0.141196 |
| child-only / scalars | 0.317333 | 0.319677 | 0.149823 | 0.415578 | 0.365596 |
| child-only / pca16-scalars | 0.337445 | 0.337180 | 0.154111 | 0.363167 | 0.326924 |
| child-only / equal-mixture | 0.319869 | 0.320964 | 0.150879 | 0.412273 | 0.356795 |
| child-only / projection | 0.339590 | 0.339372 | 0.154431 | 0.362501 | 0.325031 |
| child-only / projection-mixture | 0.320540 | 0.321665 | 0.151021 | 0.412310 | 0.356174 |

## Child projection-mixture-minus-existing-mixture consistency

| Check | all-age | child-only |
| --- | ---: | ---: |
| pooledChildNLLImproves | True | True |
| everySpeakerFoldChildNLLNoWorse | False | False |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildRating0APNoWorse | True | False |
| pooledChildBelow2APNoWorse | True | True |

| Regime / speaker fold | NLL change | Macro NLL change | Brier change | Rating-0 AP change | Below-2 AP change |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / 0 | -0.000389 | -0.000383 | -0.000173 | -0.000229 | -0.000389 |
| all-age / 1 | -0.000260 | -0.000310 | -0.000183 | 0.005335 | 0.001519 |
| all-age / 2 | 0.000061 | 0.000051 | 0.000023 | -0.000608 | -0.000555 |
| all-age / 3 | -0.000859 | -0.001205 | -0.000472 | 0.000641 | 0.002263 |
| all-age / 4 | -0.000502 | -0.000443 | -0.000230 | 0.000670 | 0.001016 |
| child-only / 0 | -0.000486 | -0.000978 | -0.000230 | 0.001191 | 0.002818 |
| child-only / 1 | -0.000234 | -0.000194 | -0.000068 | -0.002022 | -0.000328 |
| child-only / 2 | 0.000110 | 0.000080 | -0.000027 | -0.001872 | 0.001193 |
| child-only / 3 | -0.000063 | -0.000112 | -0.000053 | 0.000122 | 0.000064 |
| child-only / 4 | 0.000105 | 0.000070 | 0.000037 | -0.000848 | -0.000136 |

## Child phone support and projection-mixture-minus-existing-mixture differences

| Phone | Positions | Children | Rating-0 / below-2 votes | All-age NLL Δ | All-age AP0 Δ | All-age AP<2 Δ | Child-only NLL Δ | Child-only AP0 Δ | Child-only AP<2 Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 51 | 13 / 16 | -0.000169 | 0.000554 | 0.000479 | -0.000330 | -0.039539 | 0.001272 |
| CH | 42 | 29 | 8 / 10 | -0.000791 | 0.000230 | -0.000830 | -0.001435 | 0.000000 | 0.022939 |
| D | 322 | 52 | 37 / 64 | -0.000358 | 0.000397 | 0.001601 | -0.000070 | 0.000329 | 0.001624 |
| DH | 333 | 52 | 29 / 126 | -0.000886 | 0.004795 | 0.007099 | 0.000431 | 0.000161 | 0.000596 |
| F | 191 | 51 | 5 / 7 | 0.000050 | -0.000035 | -0.000028 | 0.000277 | -0.000537 | -0.000931 |
| G | 195 | 52 | 1 / 3 | -0.000399 | 0.000000 | 0.000121 | -0.000009 | 0.000000 | 0.003378 |
| HH | 237 | 52 | 7 / 9 | 0.000181 | -0.001270 | -0.002027 | 0.000020 | -0.000003 | 0.000036 |
| JH | 76 | 31 | 13 / 14 | -0.001708 | -0.000549 | -0.000511 | -0.002268 | 0.012821 | 0.018027 |
| K | 330 | 52 | 9 / 16 | -0.000345 | 0.000051 | 0.000156 | 0.000012 | 0.000028 | 0.000124 |
| L | 357 | 52 | 60 / 76 | -0.000005 | -0.003595 | 0.000621 | 0.000049 | 0.000778 | 0.000196 |
| M | 341 | 51 | 32 / 67 | 0.000089 | -0.000075 | -0.003268 | 0.000262 | 0.000145 | -0.000166 |
| N | 402 | 52 | 52 / 61 | -0.000182 | -0.001914 | -0.001340 | -0.000073 | -0.000624 | -0.000047 |
| NG | 119 | 48 | 10 / 18 | -0.000504 | 0.000142 | -0.000069 | -0.000216 | -0.003122 | -0.000012 |
| P | 153 | 50 | 15 / 25 | -0.000223 | 0.000000 | 0.000454 | 0.000039 | 0.005293 | 0.003782 |
| R | 304 | 51 | 60 / 82 | -0.000552 | 0.001571 | 0.002562 | -0.000251 | 0.001357 | 0.001054 |
| S | 378 | 52 | 35 / 45 | -0.000227 | 0.000594 | -0.000482 | 0.000034 | -0.034144 | 0.001157 |
| SH | 134 | 49 | 18 / 25 | 0.000022 | -0.001794 | 0.001827 | -0.001067 | 0.003445 | 0.005904 |
| T | 378 | 52 | 27 / 46 | -0.000560 | 0.000163 | -0.000032 | 0.000095 | -0.000129 | -0.000647 |
| TH | 75 | 40 | 19 / 94 | -0.001315 | 0.009712 | 0.008773 | 0.000813 | -0.000370 | 0.004018 |
| V | 200 | 49 | 17 / 93 | -0.001024 | 0.000228 | 0.000361 | -0.000947 | -0.010845 | -0.000300 |
| W | 323 | 51 | 18 / 22 | -0.000089 | 0.001196 | -0.000117 | 0.000251 | -0.000273 | -0.001139 |
| Y | 190 | 49 | 9 / 15 | -0.000082 | 0.000000 | 0.000222 | -0.000538 | 0.020000 | 0.022693 |
| Z | 338 | 52 | 38 / 303 | -0.000790 | -0.000379 | 0.000384 | -0.000428 | -0.000468 | 0.000953 |

## Secondary screen versus scalar

| Check | all-age | child-only |
| --- | ---: | ---: |
| pooledChildNLLImproves | True | True |
| everySpeakerFoldChildNLLNoWorse | True | False |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildRating0APNoWorse | True | True |
| pooledChildBelow2APNoWorse | True | True |

## Secondary screen versus projection

| Check | all-age | child-only |
| --- | ---: | ---: |
| pooledChildNLLImproves | True | True |
| everySpeakerFoldChildNLLNoWorse | True | False |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildRating0APNoWorse | False | True |
| pooledChildBelow2APNoWorse | False | True |

Report SHA256: `ade1a17833eb84ef7c05c342c01a4acf4c6523d5f26b0e8636f0abaac6442d3c`

## Interpretation and limits

Against the primary reference, all-age pooled child NLL decreases .000348,
macro NLL .000429 and Brier .000186; rating-0 AP rises .000757 and below-2 AP
.000846. Fold 2 worsens on all five endpoints, and fold 0 loses both AP measures.
The average gain does not establish improvement for every child or sound.
Child-only pooled NLL decreases .000095, but rating-0 AP falls .000070; folds
2 and 4 have worse NLL. These small changes do not justify selecting only
favorable folds or children.

Against scalar, the all-age NLL differences in folds 0–4 are -.001080,
-.001176, -.003709, -.002722 and -.000056. The last is small but exceeds the
fixed tolerance in the favorable direction. The screen does not require AP
improvement in every fold: all-age AP0 still worsens in folds 1 and 3. Child-only
fitting improves all five pooled child endpoints over scalar but worsens fold-4
NLL by .001659. Against corrected projection alone, all-age NLL improves in
every fold and pooled calibration metrics improve, but both pooled AP measures
worsen. Child-only gains all five pooled endpoints but worsens fold-0 NLL by
.000916. Both regimes beat their matched priors on all five pooled child
endpoints.

Older-speaker performance also limits the story. With all-age fitting, the
age-13-plus NLL worsens slightly (.256629→.256671) against the existing mixture,
although the other four measures improve. With child-only fitting, age-13-plus
NLL, macro NLL, Brier and below-2 AP worsen; only rating-0 AP improves slightly.
Per-phone tradeoffs remain in the complete table. For example, child-only B
and S rating-0 AP fall by .039539 and .034144. G still has only one child
rating-0 vote; CH has eight. These are not adequate denominators for broad
sound-specific correctness claims.

## Verification and artifacts

Ten focused tests pass: six frozen mixture arithmetic/guard tests and four new
partition, checkpoint/source-anchor and declaration guards. The numerical
suite includes ordinary probability means, symmetry, identical components,
high-precision Decimal extreme-log comparisons and malformed inputs. The new
study introduces no alternate averaging implementation. A separate GPT-6 Astra
review found no blocking source/protocol findings and independently passed all
ten tests before declaration. Preflight verified all 891 inputs/50 pairs with
mixture calculation and model preparation, training, prediction and replay
forbidden. Actual calculation completed with exit zero.

Exact offline reconstruction completed with exit zero. The independent Astra
artifact audit also completed with exit zero: 35,623 mapping, lineage and
arithmetic checks; 628,356 primary metric checks; and 491,674 ancillary checks
across all 50 pairs, 62 summaries and 558 slices. Separate max/log1p arithmetic
matched all saved mixture probabilities and logs exactly. Full partition,
checkpoint/configuration, fit-row priors, source hashes, metric support and
all primary/secondary/prior comparisons passed. Reference metrics reuse their
previously independently audited pinned reports.

The first auditor attempt stopped on an auditor-only configuration-schema
assumption: scalar identity is nested under `job`, while projection identity
uses top-level fields. The auditor was corrected to check both actual schemas;
the subsequent complete audit passed. Study inputs, code and outputs did not
change. The executed independent auditor sources are hash-bound.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-projection-mixture-v1/plan.json): `0ea7bac5ed8dfa29da35622c21c7b1c94041520dde65e1ecfadcd75d56896a31`
- [Complete report](../../research/audio-head/outputs/multiphone-20260927/lexical-projection-mixture-v1/report.json): `ade1a17833eb84ef7c05c342c01a4acf4c6523d5f26b0e8636f0abaac6442d3c`
- Independent [source review](../../work/lexical-projection-mixture-audit-20260927/source-review.json) and [artifact receipt](../../work/lexical-projection-mixture-audit-20260927/result.json).

From `research/audio-head`, use `.venv/bin/python -m lexical_projection_mixture.study`
with `declare`, `run` or `verify`; the latter two require the plan and its SHA256.
The report is a retrospective saved-prediction comparison, not a deployed
ensemble adapter or a measured end-to-end latency result. Independent source
head replays belong to earlier studies; no new replay or complete optimizer
trajectory reconstruction is claimed here.

Close this single combination without a weight sweep. The next bounded direction
is recording sensitivity of this fixed candidate against the existing mixture:
first verify whether the previously saved clean/volume/noise feature artifacts
cover the needed canonical rows and frozen head inputs. Declare any subsequent
comparison separately. Transformed audio must not inherit pronunciation labels,
and a stable prediction is not automatically a correct one. No new robustness
result is claimed by this mixture calculation.

These speakers and outcomes have been repeatedly studied. The results remain
adaptive development evidence, with unknown pretrained lexical exposure and
no established child-SSD, age-2–5 or verified produced-phone cohort. Author-test
stays closed; learner judgments remain disabled. No raw audio, new inference,
Colab allocation or app changes occurred. App builds/UI tests were not run
because this is an isolated research calculation.
