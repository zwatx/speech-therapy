# Supervised projection correction: pooled all-age gains, inconsistent folds

The projection-only correction improves all five pooled child endpoints over
the frozen PCA head with all-age fitting: NLL .181056→.180451, macro NLL
.189664→.188898, Brier .082755→.082410, rating-0 AP .125172→.126397 and below-2
AP .186455→.188015. It still fails the primary consistency screen because child
NLL worsens in speaker fold 2. With child-only fitting, pooled NLL and rating-0
AP worsen slightly, and folds 2 and 4 regress. Neither regime passes.

The secondary scalar and existing-mixture screens also fail in both regimes.
All-age correction has better pooled child AP than the existing mixture but
worse NLL, macro NLL and Brier. Child-only correction loses all five pooled child
endpoints to that mixture. Preserve the measured gains and these tradeoffs;
no research bundle or learner policy is promoted.

## One declared adjustment with an unchanged-model option

The [protocol](multiphone-lexical-projection-protocol.md) fixed one correction
recipe before fitting. Each original selected PCA16/scalar head stays frozen
in evaluation mode. Its center, base basis, normalization and 13 scalar inputs
remain fixed. The only learned state is a zero-initialized 1024×16 float64
projection correction: 16,384 parameters. The correction is applied to the
first 16 coordinates using the declared cast/add order; zero correction exactly
reproduces the original model. No encoder or PCA decomposition is refitted.

Adaptation uses seed 7, CPU with two threads, batch 64, AdamW at 0.0001 with
0.01 weight decay, clip norm 5, maximum 20 epochs and patience 5. Inner selection
uses equal-position five-vote NLL, minimum improvement 1e-7 and earlier-epoch tie
preference. Epoch zero remains eligible. The original selection data has already
selected the starting head; this additional reuse remains explicit development
selection, not a new independent validation set.

All 50 inner runs completed before the selection freeze. In each regime,
9 of 25 cells selected epoch zero and 16 selected a positive adaptation count.
All 50 refit runs then started from their corresponding original refit head,
reset the correction to zero and used exactly the selected adaptation count.
The 18 zero-count refits performed no optimizer update; head weights were never
updated. Every refit finished before new outer predictions. The original
speaker and whole-utterance word exclusions were unchanged in every phase.

The evaluation retains 14,837 eligible positions from 125 speakers in each
regime, including 5,654 positions from 52 children aged 6–12 and all 23 phones.
Each regime retains 25 speaker×word cells, five speaker-fold summaries and a
pooled summary. No row is removed because the model or diagnostic did poorly.
All 50 source selection anchors and all 50 source outer anchors replay exactly.

## Outcomes and complete support

NLL, macro-phone NLL and Brier are better when lower; AP is better when higher.
AP is ranking performance on rater votes, not an accuracy percentage. The
primary delta tables compare the correction with its frozen compact source.
The scalar, original fixed mixture and fitting-prior controls retain their
previously audited predictions. No representation is selected per phone.

## ages6to12

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.201926 | 0.213326 | 0.084075 | 0.028153 | 0.117063 |
| all-age / scalars | 0.180497 | 0.190224 | 0.083251 | 0.109133 | 0.174946 |
| all-age / pca16-scalars | 0.181056 | 0.189664 | 0.082755 | 0.125172 | 0.186455 |
| all-age / equal-mixture | 0.178968 | 0.188141 | 0.082181 | 0.121294 | 0.185888 |
| all-age / projection | 0.180451 | 0.188898 | 0.082410 | 0.126397 | 0.188015 |
| child-only / prior | 0.193713 | 0.206017 | 0.082935 | 0.022874 | 0.114274 |
| child-only / scalars | 0.182500 | 0.195113 | 0.082266 | 0.081084 | 0.153376 |
| child-only / pca16-scalars | 0.183098 | 0.193685 | 0.081764 | 0.077252 | 0.155416 |
| child-only / equal-mixture | 0.180393 | 0.191686 | 0.081363 | 0.082126 | 0.157546 |
| child-only / projection | 0.183119 | 0.193407 | 0.081669 | 0.077025 | 0.156278 |

## allAges

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.293177 | 0.302118 | 0.136786 | 0.062471 | 0.124480 |
| all-age / scalars | 0.229729 | 0.233841 | 0.112958 | 0.401063 | 0.392335 |
| all-age / pca16-scalars | 0.230477 | 0.234239 | 0.111675 | 0.415324 | 0.402461 |
| all-age / equal-mixture | 0.227034 | 0.230927 | 0.111159 | 0.420423 | 0.407854 |
| all-age / projection | 0.230495 | 0.234071 | 0.111563 | 0.416693 | 0.403545 |
| child-only / prior | 0.309989 | 0.317467 | 0.138177 | 0.069503 | 0.127944 |
| child-only / scalars | 0.265951 | 0.271810 | 0.124078 | 0.318731 | 0.295106 |
| child-only / pca16-scalars | 0.278627 | 0.282125 | 0.126541 | 0.278487 | 0.269325 |
| child-only / equal-mixture | 0.266718 | 0.271344 | 0.124388 | 0.317157 | 0.289972 |
| child-only / projection | 0.279963 | 0.283378 | 0.126704 | 0.277915 | 0.268600 |

## ages13plus

| Regime / representation | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / prior | 0.349360 | 0.356764 | 0.169241 | 0.083654 | 0.135088 |
| all-age / scalars | 0.260041 | 0.261913 | 0.131249 | 0.477197 | 0.465610 |
| all-age / pca16-scalars | 0.260906 | 0.262993 | 0.129481 | 0.490335 | 0.474455 |
| all-age / equal-mixture | 0.256629 | 0.258578 | 0.129001 | 0.496050 | 0.480863 |
| all-age / projection | 0.261307 | 0.263181 | 0.129512 | 0.491609 | 0.475129 |
| child-only / prior | 0.381581 | 0.386047 | 0.172190 | 0.098105 | 0.141196 |
| child-only / scalars | 0.317333 | 0.319677 | 0.149823 | 0.415578 | 0.365596 |
| child-only / pca16-scalars | 0.337445 | 0.337180 | 0.154111 | 0.363167 | 0.326924 |
| child-only / equal-mixture | 0.319869 | 0.320964 | 0.150879 | 0.412273 | 0.356795 |
| child-only / projection | 0.339590 | 0.339372 | 0.154431 | 0.362501 | 0.325031 |

## Child projection-minus-compact consistency

| Check | all-age | child-only |
| --- | ---: | ---: |
| pooledChildNLLImproves | True | False |
| everySpeakerFoldChildNLLNoWorse | False | False |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildRating0APNoWorse | True | False |
| pooledChildBelow2APNoWorse | True | True |

| Regime / speaker fold | NLL change | Macro NLL change | Brier change | Rating-0 AP change | Below-2 AP change |
| --- | ---: | ---: | ---: | ---: | ---: |
| all-age / 0 | -0.000704 | -0.000701 | -0.000316 | 0.000039 | 0.000845 |
| all-age / 1 | -0.000347 | -0.000465 | -0.000301 | -0.001392 | 0.001657 |
| all-age / 2 | 0.000163 | 0.000134 | 0.000057 | -0.001340 | -0.000180 |
| all-age / 3 | -0.001561 | -0.002242 | -0.000926 | 0.000707 | 0.002813 |
| all-age / 4 | -0.000965 | -0.000645 | -0.000450 | 0.001433 | 0.000850 |
| child-only / 0 | -0.000964 | -0.001876 | -0.000419 | 0.004508 | 0.005122 |
| child-only / 1 | -0.000200 | -0.000210 | -0.000102 | 0.001481 | -0.000011 |
| child-only / 2 | 0.000495 | 0.000407 | 0.000017 | 0.000137 | 0.001016 |
| child-only / 3 | -0.000086 | -0.000193 | -0.000113 | -0.000405 | 0.000141 |
| child-only / 4 | 0.000622 | 0.000483 | 0.000088 | -0.002670 | -0.000911 |

## Child phone support and projection-minus-compact differences

| Phone | Positions | Children | Rating-0 / below-2 votes | All-age NLL Δ | All-age AP0 Δ | All-age AP<2 Δ | Child-only NLL Δ | Child-only AP0 Δ | Child-only AP<2 Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 236 | 51 | 13 / 16 | -0.000336 | -0.000338 | 0.000347 | -0.000668 | 0.001665 | -0.029551 |
| CH | 42 | 29 | 8 / 10 | -0.001608 | 0.000327 | 0.000135 | -0.002815 | 0.312500 | 0.081333 |
| D | 322 | 52 | 37 / 64 | -0.000636 | 0.014780 | 0.009079 | 0.000111 | 0.001243 | 0.000227 |
| DH | 333 | 52 | 29 / 126 | -0.001687 | -0.000780 | 0.007518 | 0.001513 | -0.000180 | 0.000462 |
| F | 191 | 51 | 5 / 7 | -0.000008 | -0.001413 | 0.001190 | 0.000424 | -0.001807 | -0.002138 |
| G | 195 | 52 | 1 / 3 | -0.000780 | 0.000000 | 0.000030 | -0.000036 | 0.000000 | 0.002219 |
| HH | 237 | 52 | 7 / 9 | 0.000366 | -0.001123 | -0.001609 | 0.000062 | 0.000046 | -0.033659 |
| JH | 76 | 31 | 13 / 14 | -0.003325 | 0.001659 | 0.001525 | -0.003780 | 0.020526 | -0.009139 |
| K | 330 | 52 | 9 / 16 | -0.000703 | 0.000170 | -0.006072 | 0.000079 | 0.000341 | -0.000027 |
| L | 357 | 52 | 60 / 76 | 0.000102 | 0.000338 | -0.001615 | 0.000593 | 0.000525 | 0.001448 |
| M | 341 | 51 | 32 / 67 | 0.000176 | -0.000775 | -0.000022 | 0.000921 | -0.003030 | -0.001556 |
| N | 402 | 52 | 52 / 61 | -0.000313 | 0.000492 | 0.001953 | 0.000157 | -0.001499 | 0.002466 |
| NG | 119 | 48 | 10 / 18 | -0.000795 | 0.002793 | 0.001984 | -0.000580 | 0.017520 | 0.005587 |
| P | 153 | 50 | 15 / 25 | -0.000461 | 0.000000 | 0.000077 | 0.000566 | 0.001779 | 0.003283 |
| R | 304 | 51 | 60 / 82 | -0.000694 | 0.004875 | 0.003288 | 0.000075 | 0.002145 | 0.000210 |
| S | 378 | 52 | 35 / 45 | -0.000307 | 0.005725 | 0.004910 | 0.000156 | -0.005608 | -0.017273 |
| SH | 134 | 49 | 18 / 25 | 0.000346 | -0.006075 | -0.013830 | -0.002352 | 0.008242 | 0.007539 |
| T | 378 | 52 | 27 / 46 | -0.001043 | 0.001044 | 0.000538 | 0.000406 | -0.000099 | -0.000467 |
| TH | 75 | 40 | 19 / 94 | -0.002240 | 0.002492 | 0.012567 | 0.001979 | -0.000790 | -0.000852 |
| V | 200 | 49 | 17 / 93 | -0.002015 | 0.003604 | 0.001405 | -0.002118 | -0.017678 | -0.005893 |
| W | 323 | 51 | 18 / 22 | -0.000130 | 0.001126 | 0.001246 | 0.000713 | 0.000103 | -0.001977 |
| Y | 190 | 49 | 9 / 15 | -0.000280 | -0.014286 | 0.000456 | -0.001038 | -0.177778 | 0.001183 |
| Z | 338 | 52 | 38 / 303 | -0.001236 | -0.000425 | 0.002053 | -0.000773 | 0.007405 | 0.001044 |

## Secondary screen versus scalar

| Check | all-age | child-only |
| --- | ---: | ---: |
| pooledChildNLLImproves | True | False |
| everySpeakerFoldChildNLLNoWorse | False | False |
| pooledChildMacroNLLNoWorse | True | True |
| pooledChildBrierNoWorse | True | True |
| pooledChildRating0APNoWorse | True | False |
| pooledChildBelow2APNoWorse | True | True |

## Secondary screen versus mixture

| Check | all-age | child-only |
| --- | ---: | ---: |
| pooledChildNLLImproves | False | False |
| everySpeakerFoldChildNLLNoWorse | False | False |
| pooledChildMacroNLLNoWorse | False | False |
| pooledChildBrierNoWorse | False | False |
| pooledChildRating0APNoWorse | True | False |
| pooledChildBelow2APNoWorse | True | False |

Report SHA256: `309861819be78be994ca00f2bc0a68ab656414c67aaf49efdfed9e8495939c41`

## Interpretation

All-age projection-versus-compact NLL improves in four speaker folds, but fold 2
worsens by .000163. The same fold loses Brier and both AP endpoints. All-age
fold 1 also loses rating-0 AP. Child-only NLL worsens by .000495 in fold 2 and
.000622 in fold 4, while its pooled change is +.000020. Macro NLL, Brier and
below-2 AP improve in that regime, but rating-0 AP declines .000227.

Against scalar, all-age pooled child NLL improves only .000046 and worsens in
folds 0, 1 and 4. Child-only NLL is worse in folds 1 and 4 and pooled, with worse
pooled rating-0 AP. Against the existing mixture, all-age NLL is worse in folds
0, 1, 2 and 4; child-only is worse in folds 1–4. Both corrected regimes improve
all five pooled child endpoints over their original fitting priors, which does
not remove the stronger-control regressions.

Phone-level effects remain heterogeneous. Child-only CH rating-0 AP rises
.312500, but CH has only eight rating-0 votes; child-only Y rating-0 AP falls
.177778. G has a single child rating-0 vote. Those effects cannot support broad
sound-level or clinical claims. Seven inherited child selection cells lack
phones; only six of 25 child outer cells and 20 of 25 all-age outer cells contain
all 23 phones. Missing and undefined metrics remain explicit in the complete
artifact. Pooled phone coverage does not make every cell adequately supported.

The older-age results also limit generalization: all-age correction worsens
13-plus NLL, macro NLL and Brier versus compact despite both AP improvements.
Child-only correction worsens all five 13-plus endpoints. All-age pooled NLL
also worsens slightly versus compact. These are separate age slices of the
existing corpus, not new participants or a confirmatory replication.

## Verification and artifacts

Ten distinct synthetic tests pass. The parent independently reconstructed two
AdamW updates and exactly matched all 16,384 correction parameters plus both
optimizer moment arrays; the head remained unchanged. Source review found
history/checkpoint guard gaps before declaration. The corrected guard recomputes
selection NLL and validates row/probability identity, shuffle digests, update
counts, every stopping decision and report/checkpoint running-best metadata.
Malformed-history tests pass. All fixes preceded the immutable declaration.

Preflight checked 783 pins and 50 jobs with preparation, training and prediction
forbidden. Declaration, inner fitting, refitting, outer prediction, metric
calculation and complete offline reconstruction all finished with exit zero.
Independent artifact verification passed:

- Inner: 10,259 checks and 100 exact direct tensor replays (50 zero anchors and 50 selected corrections).
- Refit: 5,697 checks of the selected-epoch chain, zero reset, exact budgets, lack of validation use and saved source/optimizer metadata.
- Outer: 2,767 checks and 100 exact direct tensor replays (50 zero anchors and 50 corrected predictions), including float64 probabilities/logs, raw float32 probabilities, NLL and row identity.
- Metrics: 30,618 mapping checks, 628,356 primary and 491,674 ancillary checks across 62 summaries and 558 slices, including every comparison and absent/undefined support.

The audit checks optimizer recipes, initialization, counters, finite moment
states and permutation RNG records; it does not reconstruct every actual
intermediate optimizer update. The separate synthetic two-step oracle checks
that numerical update path. GPT-6 Sol authored the correction core and reviewed
the parent-authored runner; the parent independently reviewed the core/math.
Astra did not review this study; previously unavailable native reviewer capacity
was not represented as participation. Audit sources are separately bound and
unchanged after execution.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-projection-v1/plan.json): `7d9941d73c94c63873fdac8ec606b2ca871cd47c3b5fcb14a7a1a2a2becf3d7e`
- [Inner freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-projection-v1/inner-freeze.json): `1e0a9afc34a9b69630dfb4c9c5b89db618cae53c0e0e3f959ee524384ee45b6a`
- [Refit freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-projection-v1/outer-refit-freeze.json): `947ee6003cb1cdd3cc8046a6163a86e5de3c79ffa64fb8426ede7754c4a0661b`
- [Outer freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-projection-v1/outer-freeze.json): `69e34e265416eb4db20eed617395772eb2f54f47c202a2aa4403bd50edb79f92`
- [Complete report](../../research/audio-head/outputs/multiphone-20260927/lexical-projection-v1/report.json): `309861819be78be994ca00f2bc0a68ab656414c67aaf49efdfed9e8495939c41`
- Independent [inner](../../work/lexical-projection-audit-20260927/inner-result.json), [refit](../../work/lexical-projection-audit-20260927/outer-refit-result.json), [outer](../../work/lexical-projection-audit-20260927/outer-result.json) and [metric](../../work/lexical-projection-audit-20260927/report-result.json) receipts.

From `research/audio-head`, use `.venv/bin/python -m lexical_projection.study`.
The phases are `declare`, `inner`, `refit`, `outer`, `audit` and `verify`. The
plan and relevant preceding complete freeze require their SHA256 values. Source,
tests and protocol are immutable after declaration. Retained failure records
are never overwritten to make a study appear successful.

Close this single projection recipe without a learning-rate or rank sweep.
One separately declared equal-probability scalar/corrected-projection mixture
is a concrete composition hypothesis, to compare with the existing mixture and
scalar controls using the same screen and fixed weights. No such mixture has
been calculated here; this is a next step, not an inferred improvement.

Repeatedly studied outer data and unknown pretrained lexical exposure limit all
claims. Ratings are subjective, not verified produced-phone ground truth; there
is no established child-SSD or age-2–5 cohort. No author-test audio, new encoder
processing, Colab allocation, app code or learner feedback was used or changed.
App builds/UI tests were not run for this isolated research training study.
