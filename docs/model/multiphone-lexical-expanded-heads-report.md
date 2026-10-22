# Expanded lexical fitting: a child-mixture development gain

Adding permitted canonical occurrences while keeping checkpoint-selection examples
fixed improves the child-trained equal scalar/PCA mixture against its original-data
counterpart. All six declared primary checks pass: child pooled NLL changes
.180393→.177459, Brier .081363→.080372, rating-0 AP .082126→.092080 and below-2
AP .157546→.169876, with lower child NLL in every speaker fold. This is one
consistent development comparison, not a promotion or independent final validation.

The stronger corrected-projection mixture remains a difficult secondary reference:
child pooled endpoints improve, but fold 0 NLL worsens .000150, failing that screen.
All-age expanded mixture improves all five pooled endpoints against the original
mixture but worsens fold 2 and 3 NLL. Neither individual family passes its primary
screen in either regime. Every outcome is retained; no family, fold or sound is
removed to improve the result.

## Method and matched population

The [protocol](multiphone-lexical-expanded-heads-protocol.md) fixes 100 inner fits,
100 fresh refits and 100 outer prediction jobs: two families, two fitting age
regimes, five speaker folds and five word groups. It follows the verified
[occurrence inventory](multiphone-lexical-expansion-report.md), using 28,227 positions
in 2,500 recordings from the same 125 speakers, including 9,891 positions from
52 children aged 6–12. It adds occurrences and five recordings, not participants.

Complete-utterance canonical word exclusions and speaker roles stay fixed.
Checkpoint selection uses exactly the original retained examples in their original
order. Added positions from validation speakers enter only the final refit.
Scalar heads use 13 features; compact heads use 16 fit-only PCA components plus
those features. Every refit estimates fresh transforms/moments and initializes a
fresh head, training for its inner-selected epoch count. The mixture is fixed at
.5/.5. There is no projection correction, class weighting or parameter search.

Primary and secondary historical comparisons use exactly the original 14,837
positions, including 5,654 child positions. Original IDs, labels and ordering are
verified. Added 13,390 positions and full 28,227 positions are separate descriptive
populations. Lower NLL, macro-phone NLL and Brier are better; higher AP is better.
AP pools child rating votes across phones for the declared screen; per-phone
measures remain below and in the full artifact. These are subjective rating
predictions, not percentages of correct pronunciation.

## Original-population outcomes

### ages6to12

| Fitting regime / model | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | --- | --- | --- | --- | --- |
| all-age / prior | 0.201359 | 0.212504 | 0.083731 | 0.029229 | 0.122453 |
| all-age / scalars | 0.181136 | 0.190878 | 0.083846 | 0.110757 | 0.176673 |
| all-age / pca16-scalars | 0.180123 | 0.188924 | 0.082344 | 0.127981 | 0.194526 |
| all-age / equal-mixture | 0.178358 | 0.187648 | 0.082063 | 0.122710 | 0.190163 |
| child-only / prior | 0.192527 | 0.205560 | 0.082727 | 0.024605 | 0.117092 |
| child-only / scalars | 0.180124 | 0.193114 | 0.081605 | 0.088432 | 0.160207 |
| child-only / pca16-scalars | 0.179231 | 0.190216 | 0.080453 | 0.088972 | 0.173905 |
| child-only / equal-mixture | 0.177459 | 0.189095 | 0.080372 | 0.092080 | 0.169876 |

### allAges

| Fitting regime / model | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | --- | --- | --- | --- | --- |
| all-age / prior | 0.291480 | 0.300451 | 0.136441 | 0.063084 | 0.126027 |
| all-age / scalars | 0.227537 | 0.231242 | 0.112853 | 0.399564 | 0.390616 |
| all-age / pca16-scalars | 0.226723 | 0.230820 | 0.110576 | 0.424961 | 0.413751 |
| all-age / equal-mixture | 0.223495 | 0.227211 | 0.110326 | 0.426899 | 0.415437 |
| child-only / prior | 0.310051 | 0.317479 | 0.138156 | 0.070853 | 0.131497 |
| child-only / scalars | 0.262282 | 0.267479 | 0.123027 | 0.341159 | 0.310476 |
| child-only / pca16-scalars | 0.273565 | 0.277960 | 0.125763 | 0.290569 | 0.278230 |
| child-only / equal-mixture | 0.262780 | 0.267374 | 0.123477 | 0.334563 | 0.302423 |

### ages13plus

| Fitting regime / model | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | --- | --- | --- | --- | --- |
| all-age / prior | 0.346967 | 0.354568 | 0.168896 | 0.084523 | 0.136098 |
| all-age / scalars | 0.256106 | 0.257715 | 0.130713 | 0.476603 | 0.464361 |
| all-age / pca16-scalars | 0.255415 | 0.257993 | 0.127959 | 0.504179 | 0.488437 |
| all-age / equal-mixture | 0.251287 | 0.253130 | 0.127728 | 0.504967 | 0.490438 |
| child-only / prior | 0.382412 | 0.386230 | 0.172284 | 0.098627 | 0.144866 |
| child-only / scalars | 0.312866 | 0.313992 | 0.148531 | 0.435127 | 0.381998 |
| child-only / pca16-scalars | 0.331646 | 0.332376 | 0.153661 | 0.378334 | 0.332760 |
| child-only / equal-mixture | 0.315312 | 0.316135 | 0.150016 | 0.430292 | 0.368904 |

## Primary changes against matching original-data models

Differences are expanded minus original-data model on identical outer positions.

| Fitting regime / family | NLL Δ | Macro NLL Δ | Brier Δ | AP0 Δ | AP<2 Δ | Six checks pass |
| --- | --- | --- | --- | --- | --- | --- |
| all-age / equal-mixture | -0.000609 | -0.000492 | -0.000117 | 0.001416 | 0.004275 | False |
| all-age / pca16-scalars | -0.000933 | -0.000740 | -0.000412 | 0.002808 | 0.008071 | False |
| all-age / scalars | 0.000639 | 0.000654 | 0.000594 | 0.001624 | 0.001727 | False |
| child-only / equal-mixture | -0.002934 | -0.002590 | -0.000991 | 0.009953 | 0.012329 | True |
| child-only / pca16-scalars | -0.003867 | -0.003470 | -0.001310 | 0.011719 | 0.018490 | False |
| child-only / scalars | -0.002376 | -0.001998 | -0.000660 | 0.007348 | 0.006831 | False |

The child scalar fails because fold 4 NLL worsens; child compact fails because
fold 0 NLL worsens .000014. All-age scalar also worsens pooled NLL, macro NLL
and Brier. All-age compact and mixture fail the fold requirement despite improving
all five pooled endpoints. The child mixture passes the declared screen even
though fold 3 rating-0 AP worsens and fold 4 macro NLL worsens: those are not
per-fold requirements in the fixed screen, and remain explicit here.

| Fitting regime / family / fold | NLL Δ | Macro NLL Δ | Brier Δ | AP0 Δ | AP<2 Δ |
| --- | --- | --- | --- | --- | --- |
| all-age / equal-mixture / 0 | -0.000744 | -0.001032 | -0.000853 | 0.028662 | 0.020890 |
| all-age / equal-mixture / 1 | -0.000521 | -0.000198 | -0.000200 | 0.007697 | 0.008513 |
| all-age / equal-mixture / 2 | 0.000138 | 0.000840 | 0.000505 | -0.017818 | -0.007747 |
| all-age / equal-mixture / 3 | 0.002099 | -0.000103 | 0.001138 | -0.002839 | -0.002662 |
| all-age / equal-mixture / 4 | -0.004025 | -0.002873 | -0.001315 | 0.003070 | 0.007823 |
| all-age / pca16-scalars / 0 | -0.002198 | -0.002295 | -0.001421 | 0.013727 | 0.022109 |
| all-age / pca16-scalars / 1 | -0.002443 | -0.002451 | -0.001031 | 0.023104 | 0.018930 |
| all-age / pca16-scalars / 2 | 0.002805 | 0.002782 | 0.002239 | -0.025552 | -0.027086 |
| all-age / pca16-scalars / 3 | 0.001745 | 0.000401 | -0.000397 | -0.004905 | -0.000601 |
| all-age / pca16-scalars / 4 | -0.005778 | -0.003523 | -0.002498 | 0.002665 | 0.012023 |
| all-age / scalars / 0 | 0.001162 | 0.000755 | 0.000147 | 0.007045 | 0.018236 |
| all-age / scalars / 1 | 0.000827 | 0.001524 | 0.000713 | 0.008774 | -0.003312 |
| all-age / scalars / 2 | -0.000698 | 0.000634 | -0.000493 | 0.005604 | 0.006373 |
| all-age / scalars / 3 | 0.003732 | 0.000675 | 0.003201 | -0.003372 | -0.008690 |
| all-age / scalars / 4 | -0.000979 | -0.000616 | 0.000065 | -0.009336 | -0.003697 |
| child-only / equal-mixture / 0 | -0.000336 | -0.000974 | -0.000656 | 0.006447 | 0.018229 |
| child-only / equal-mixture / 1 | -0.002891 | -0.002557 | -0.001043 | 0.017537 | 0.013484 |
| child-only / equal-mixture / 2 | -0.007003 | -0.007075 | -0.001772 | 0.022439 | 0.018933 |
| child-only / equal-mixture / 3 | -0.001356 | -0.000289 | -0.000709 | -0.003063 | 0.006859 |
| child-only / equal-mixture / 4 | -0.001271 | 0.001117 | -0.000440 | 0.007501 | 0.006673 |
| child-only / pca16-scalars / 0 | 0.000014 | -0.002069 | -0.000217 | 0.020872 | 0.027277 |
| child-only / pca16-scalars / 1 | -0.004104 | -0.003752 | -0.001666 | 0.012741 | 0.020400 |
| child-only / pca16-scalars / 2 | -0.006971 | -0.007068 | -0.001967 | 0.025842 | 0.022367 |
| child-only / pca16-scalars / 3 | -0.001201 | 0.000935 | -0.000733 | -0.004995 | 0.009895 |
| child-only / pca16-scalars / 4 | -0.005460 | -0.002519 | -0.001618 | 0.010835 | 0.008384 |
| child-only / scalars / 0 | -0.000767 | -0.000242 | -0.001291 | -0.002112 | 0.000299 |
| child-only / scalars / 1 | -0.002127 | -0.002041 | -0.000348 | 0.025612 | 0.005337 |
| child-only / scalars / 2 | -0.006739 | -0.007159 | -0.001127 | 0.027882 | 0.014687 |
| child-only / scalars / 3 | -0.001878 | -0.001168 | -0.000903 | 0.002260 | 0.008758 |
| child-only / scalars / 4 | 0.001404 | 0.003499 | 0.000495 | -0.006570 | -0.007159 |

## Secondary mixture comparison against corrected projection

| Fitting regime | NLL Δ | Macro NLL Δ | Brier Δ | AP0 Δ | AP<2 Δ | Six checks pass |
| --- | --- | --- | --- | --- | --- | --- |
| all-age | -0.000261 | -0.000063 | 0.000068 | 0.000659 | 0.003429 | False |
| child-only | -0.002839 | -0.002358 | -0.000927 | 0.010023 | 0.011790 | False |

| Fitting regime / fold | NLL Δ | Macro NLL Δ | Brier Δ | AP0 Δ | AP<2 Δ |
| --- | --- | --- | --- | --- | --- |
| all-age / 0 | -0.000355 | -0.000649 | -0.000680 | 0.028891 | 0.021279 |
| all-age / 1 | -0.000261 | 0.000113 | -0.000017 | 0.002362 | 0.006994 |
| all-age / 2 | 0.000077 | 0.000789 | 0.000483 | -0.017209 | -0.007192 |
| all-age / 3 | 0.002958 | 0.001102 | 0.001610 | -0.003480 | -0.004924 |
| all-age / 4 | -0.003523 | -0.002430 | -0.001085 | 0.002401 | 0.006807 |
| child-only / 0 | 0.000150 | 0.000005 | -0.000426 | 0.005256 | 0.015411 |
| child-only / 1 | -0.002657 | -0.002363 | -0.000974 | 0.019559 | 0.013812 |
| child-only / 2 | -0.007113 | -0.007155 | -0.001745 | 0.024311 | 0.017741 |
| child-only / 3 | -0.001293 | -0.000177 | -0.000656 | -0.003185 | 0.006794 |
| child-only / 4 | -0.001376 | 0.001047 | -0.000477 | 0.008349 | 0.006808 |

Both secondary screens fail. All-age Brier worsens in addition to fold 2/3
NLL; child-only fold 0 NLL worsens. Against the expanded fitted prior, child
models improve all five pooled endpoints. All-age compact and mixture also do;
all-age scalar Brier is worse than its prior. These contrasts do not change the
primary comparison or create an acoustic interpretation for pooled prior ranking.

## Original child phone support and mixture changes

The deltas below compare each expanded mixture to its matching original-data
mixture. Every supported sound remains, including rare-event classes. Votes from
the same child and repeated occurrences are dependent observations.

| Phone | Positions | Children | Rating-0 / below-2 votes | All-age NLL Δ | All-age AP0 Δ | All-age AP<2 Δ | Child-only NLL Δ | Child-only AP0 Δ | Child-only AP<2 Δ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B | 236 | 51 | 13 / 16 | 0.000153 | -0.018201 | -0.005807 | -0.003679 | 0.131347 | 0.014839 |
| CH | 42 | 29 | 8 / 10 | -0.004450 | -0.029773 | -0.035996 | -0.002491 | 0.081761 | 0.173639 |
| D | 322 | 52 | 37 / 64 | 0.003770 | -0.013261 | -0.002792 | 0.000253 | 0.025601 | 0.016801 |
| DH | 333 | 52 | 29 / 126 | 0.004977 | 0.009314 | 0.014545 | 0.004549 | 0.000915 | 0.000104 |
| F | 191 | 51 | 5 / 7 | -0.003550 | -0.001282 | -0.000732 | -0.002371 | 0.002022 | 0.003289 |
| G | 195 | 52 | 1 / 3 | -0.000532 | 0.002593 | 0.002428 | -0.000408 | 0.004150 | -0.000279 |
| HH | 237 | 52 | 7 / 9 | -0.004648 | 0.028314 | 0.049684 | -0.001745 | 0.016252 | 0.018408 |
| JH | 76 | 31 | 13 / 14 | -0.004957 | 0.000420 | -0.001152 | 0.005410 | -0.012839 | -0.020244 |
| K | 330 | 52 | 9 / 16 | -0.003937 | 0.000572 | 0.003163 | -0.002718 | 0.007182 | 0.005698 |
| L | 357 | 52 | 60 / 76 | -0.001050 | -0.033355 | -0.023070 | -0.003260 | -0.001926 | -0.004988 |
| M | 341 | 51 | 32 / 67 | 0.002096 | -0.000716 | 0.000875 | -0.001400 | -0.008515 | -0.007457 |
| N | 402 | 52 | 52 / 61 | 0.000339 | 0.017609 | 0.017528 | -0.000497 | 0.011342 | -0.009886 |
| NG | 119 | 48 | 10 / 18 | -0.006326 | 0.002917 | 0.003324 | -0.009420 | 0.148589 | 0.098484 |
| P | 153 | 50 | 15 / 25 | 0.010464 | 0.046022 | 0.055551 | -0.004743 | 0.031620 | 0.016634 |
| R | 304 | 51 | 60 / 82 | -0.001110 | -0.000917 | 0.002374 | -0.013728 | 0.023775 | 0.033929 |
| S | 378 | 52 | 35 / 45 | -0.003188 | -0.004397 | -0.010387 | -0.001493 | -0.015010 | 0.043929 |
| SH | 134 | 49 | 18 / 25 | 0.011987 | -0.077871 | -0.072077 | -0.003126 | 0.018887 | 0.024331 |
| T | 378 | 52 | 27 / 46 | -0.004577 | 0.022001 | 0.018388 | -0.014747 | 0.062580 | 0.056112 |
| TH | 75 | 40 | 19 / 94 | 0.005534 | -0.028891 | -0.010952 | 0.005744 | 0.013904 | 0.030593 |
| V | 200 | 49 | 17 / 93 | -0.010020 | 0.004965 | 0.011627 | -0.012357 | 0.003283 | 0.018110 |
| W | 323 | 51 | 18 / 22 | 0.003620 | -0.032130 | -0.037420 | 0.008155 | -0.021548 | -0.028273 |
| Y | 190 | 49 | 9 / 15 | -0.001062 | -0.046825 | -0.028818 | 0.000633 | -0.002222 | -0.008220 |
| Z | 338 | 52 | 38 / 303 | -0.004861 | 0.009171 | 0.007636 | -0.006139 | -0.002652 | 0.015732 |

## Added and full populations: descriptive child outcomes

These populations differ from the original comparison, so smaller values here
cannot be treated as gains over historical original-only outcomes. Added child
positions number 4,237; full child positions number 9,891. The complete artifact
also retains all-age and age-13-plus outcomes, all 25 cells, five folds, phone
support, confidence, calibration bins and explicit undefined quantities.

| Population / fitting regime / model | NLL | Macro-phone NLL | Brier | AP0 | AP<2 |
| --- | --- | --- | --- | --- | --- |
| added / all-age / prior | 0.180247 | 0.250320 | 0.069913 | 0.033849 | 0.117620 |
| added / all-age / scalars | 0.157306 | 0.227766 | 0.069465 | 0.096858 | 0.176753 |
| added / all-age / pca16-scalars | 0.159422 | 0.229567 | 0.070392 | 0.092037 | 0.180634 |
| added / all-age / equal-mixture | 0.156469 | 0.226620 | 0.069229 | 0.096833 | 0.182574 |
| added / child-only / prior | 0.168750 | 0.244303 | 0.068181 | 0.029123 | 0.117386 |
| added / child-only / scalars | 0.151625 | 0.227992 | 0.065992 | 0.102316 | 0.185649 |
| added / child-only / pca16-scalars | 0.156198 | 0.222592 | 0.066484 | 0.079829 | 0.177984 |
| added / child-only / equal-mixture | 0.151922 | 0.222730 | 0.065802 | 0.097012 | 0.188104 |
| all / all-age / prior | 0.192315 | 0.217253 | 0.077812 | 0.029465 | 0.117400 |
| all / all-age / scalars | 0.170928 | 0.194331 | 0.077685 | 0.103648 | 0.175925 |
| all / all-age / pca16-scalars | 0.171255 | 0.192919 | 0.077224 | 0.107764 | 0.188223 |
| all / all-age / equal-mixture | 0.168982 | 0.191435 | 0.076566 | 0.110001 | 0.186991 |
| all / child-only / prior | 0.182341 | 0.210197 | 0.076496 | 0.024824 | 0.113538 |
| all / child-only / scalars | 0.167916 | 0.195907 | 0.074917 | 0.092237 | 0.166254 |
| all / child-only / pca16-scalars | 0.169364 | 0.193474 | 0.074469 | 0.084442 | 0.173973 |
| all / child-only / equal-mixture | 0.166520 | 0.192089 | 0.074130 | 0.092118 | 0.174016 |

## Actual fitting budget

Each row represents 25 independent inner jobs and 25 fresh refits. Epoch-zero
heads are ineligible. Inner patience is 15, maximum 100 epochs, seed 7; refits
use selected epoch counts without further selection. Expanded epochs contain
more updates and different shuffles, while PCA and normalization also change.
This study does not isolate a pure information-content effect of extra data.

| Fitting regime / family | Selected epochs range | Inner epochs | Inner updates | Refit epochs | Refit updates |
| --- | --- | --- | --- | --- | --- |
| all-age / scalars | 4–34 | 724 | 49686 | 349 | 29917 |
| all-age / pca16-scalars | 5–26 | 726 | 50595 | 351 | 31022 |
| child-only / scalars | 5–66 | 935 | 28705 | 560 | 21147 |
| child-only / pca16-scalars | 8–43 | 904 | 27671 | 529 | 20083 |

## Verification and artifacts

Fourteen focused tests pass, including synthetic fitting through both families,
original selection ordering, added validation withholding/refit inclusion, phase
barriers, checkpoint guards, original-index gaps, empty cells and stable-log loss.
The initial test run failed because a temporary-directory path used the macOS
`/var` alias rather than its resolved `/private/var` path. The fixture was fixed
before declaration; the study behavior was unchanged. No actual run failed.
Preflight verified 40,301 input bindings and the complete 100-job matrix with
fitting and evaluation forbidden.

A separate GPT-6 Astra read-only source review found no blockers before
freezing the four new Python files and protocol. It inspected all five new files
and seven dependencies and parsed all four Python files; it did not independently
run project tests. The installed Codex CLI supplied that review after native
reviewer capacity failed. The receipt records the verified model and limitations.

Independent saved-state checks pass for all 100 inner and 100 refit jobs:
145,520 and 125,280 checks respectively, 600 checkpoint states total, 100 NumPy
PCA certificates, exact selection replay for all 100 inner heads, saved epoch,
shuffle, update and RNG consistency. Full gradient and optimizer trajectories
were not reconstructed. Independent outer replay passes all 100 jobs and
112,908 row predictions with zero differences in probabilities, stable logs,
raw probabilities or NLL. It also recertifies 50 PCA transforms and rehashes
2,121 files; 113,431 checks pass. The largest PCA projector discrepancy is
8.88e-16. This replay uses a separate functional tensor path, not the trainer
or model class.

Actual report calculation and exact offline reconstruction both finish with exit
zero. A separate metric implementation passes 1,345,931 lineage/arithmetic,
7,502,256 primary metric and 5,807,160 ancillary checks over all 744 summaries,
with 19,329 unique bound artifact paths rehashed after calculation. It verifies
integer fitted priors, original/added/all joins, stable equal mixtures, per-phone
support, rating discrimination, calibration/confidence and every primary/secondary
comparison. It does not invoke the project's evaluation or scoring functions.
Mixture agreement uses relative/absolute tolerances 2e-13/2e-14; metric checks
use 2e-11/2e-12. Saved probabilities preserve exact ranking ties. There were no
independent artifact-audit failures. Empty summaries and missing-phone rejection
were also checked synthetically.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-expanded-heads-v1/plan.json): `8acf9c21ac69ef8c1aec9518ab4a8a75b27049322d6d8fe7733a5373fb97154c`.
- [Inner freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-expanded-heads-v1/inner-freeze.json): `3afea90b57ebe5ab60f9cb5da3a4451e3f8e9a4c979edf9c87ad0d26dc873bf1`.
- [Refit freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-expanded-heads-v1/refit-freeze.json): `6450ee83727f1e3d06254286611672ff511a7eef3cc37da2e233b8f5f5b855bc`.
- [Outer freeze](../../research/audio-head/outputs/multiphone-20260927/lexical-expanded-heads-v1/outer-freeze.json): `6bf403e910d7330db3892c7366c6a4bcd7a694927d9c4c1cd467dad2ab2515df`.
- [Complete report](../../research/audio-head/outputs/multiphone-20260927/lexical-expanded-heads-audit-v1/report.json): `bfc6329c98a212c1b93fa765cc4c3b4419adb30b981f04999d5d138f1f6eea6f`.
- [Outer replay](../../work/lexical-expanded-heads-audit-20260927/outer-result.json) and [independent metric audit](../../work/lexical-expanded-heads-audit-20260927/report-result.json).
- [Source review](../../work/lexical-expanded-heads-review-20260927/source-review-receipt.json), [inner state audit](../../work/lexical-expanded-heads-audit-20260927/inner-result.json), [refit state audit](../../work/lexical-expanded-heads-audit-20260927/outer-refit-result.json).

## Decision and limits

Retain the child expanded mixture as a promising development candidate because
it passes its declared original-mixture comparison. Preserve the failed stronger
secondary check and all other results. No existing deployment bundle is replaced.
Learner judgments remain disabled and author-test remains closed.

More occurrences do not supply new speakers, ages 2–5, an established speech-sound
disorder cohort or expert-produced-phone ground truth. Seven child selection cells
still lack a supported sound, and rare error classes remain sparse. Repeated use
of these development folds, subjective ratings, uncertain local phone timing and
unknown pretrained lexical exposure limit generalization claims.

The next bounded step is a separately declared paired child-speaker uncertainty
analysis of the fixed original-population contrasts, including the stronger
secondary reference and all phone support. It will quantify dependence and
uncertainty without tuning weights, changing the screen or removing regressions.
No such new uncertainty result is claimed here. No audio or encoder extraction,
Colab allocation, app or learner policy changed; app builds/UI tests were not run
because this change is isolated research fitting and evaluation.
