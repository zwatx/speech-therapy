# PERCEPT-R retained-model external check and child-speech retention

**Executed, independently verified and reviewed CLEAR on 2026-10-01.**

The unchanged retained model passes both predeclared **pooled /r/ ranking** criteria on 4,534 selected word tokens from 119 DEV children. Primary vote-weighted AUROC is **0.782** (95% whole-child bootstrap **0.755–0.804**), compared with **0.536** for the descriptive leave-one-child-out word baseline. This supports transferable pooled ranking on this corpus; it does not establish reliable decisions for each child. Within-child AUROC has a descriptive median of **0.605**, and study results vary substantially.

The unchanged speech-admission path processed all 357 selected child words. It lost **31/357 (8.68%)** at 250 ms and **15/357 (4.20%)** at 100 ms. The earlier nonspeech panel admitted **3/60** and **8/60**, respectively. These are the two halves of the fixed panel check; no policy was selected, threshold changed, model trained, or learner behavior deployed. The broader nonspeech-rejection requirement remains open.

## Fixed design and coverage

The [protocol](/Users/zacharywilson/Documents/speech-therapy/docs/model/percept-r-external-check-protocol-draft-20260930.md) fixed the numeric-speaker split, selections, unchanged model/extractor, exclusions, scoring and bootstrap before this run. The 80 TEST children remain sealed: acquisition used headers and hashes only, with no TEST decoding, features, predictions, listening or ratings. All analysis below uses DEV. The cap is 40 Part 1 tokens per child; Part 2 selects three words per child with duration at least 0.3 s. These are selected corpus tokens, not 4,534 independent children or necessarily unique utterances.

| Stage | Selected / prepared | Complete | Excluded | Failed |
| --- | ---: | ---: | ---: | ---: |
| Word clips, union of both parts | 4,746 | 4,746 | 0 | 0 |
| Part 1 extraction | 4,539 | 4,534 | 5 | 0 |
| Part 1 predictions and rated evaluation | 4,534 | 4,534 | 0 malformed ratings | 0 |
| Part 2 admission path | 357 | 357 | 0 | 0 |

The five Part 1 exclusions contain unsupported AX0 and follow the pre-audio rule. The corpus has one DEV token below the 0.1 s reader minimum, but it was outside the selected sample; there was no selected reader failure. No substitutions, inference retries, listening screen or outcome-driven exclusions occurred. Earlier format-only validation inspected rating-field validity without displaying its distribution; evaluation performed the sole outcome-rating join after predictions were saved and externally hash-locked. Joined records are preserved and pinned for verification, rather than reading archive ratings again.

Acquisition completed 3,258 WAV/TextGrid files in 204 folders, representing 1,629 sessions and 9,237,815,645 bytes, with zero failures. Independent acquisition verification checked every file. A saved-WAV byte-hash diagnostic found 1,553 unique hashes, with 22 repeated groups and 76 duplicate file occurrences beyond unique hashes; every repeated group belongs to the same numeric child ID. No byte-identical WAV group spans different child IDs or DEV/TEST. This does not establish decoded-audio or perceptual distinctness, and no duplicate-based exclusion was added.

## Part 1: listener-vote ranking

Positive weights are derhotic listener votes, n−k; negative weights are rhotic votes, k. There are **15,671 derhotic and 17,404 rhotic votes**, giving vote-weighted prevalence **0.474**. Scores rank these votes; SpeechOcean 0/1/2 probabilities are not calibrated to the corpus’s binary judgments. Spearman correlation uses each token’s derhotic vote fraction.

| Fixed score | AUROC | AUROC 95% child bootstrap | Weighted AP | AP 95% child bootstrap | Spearman | Spearman 95% child bootstrap |
| --- | ---: | --- | ---: | --- | ---: | --- |
| Primary: p0+p1 | 0.782 | 0.755–0.804 | 0.719 | 0.671–0.764 | 0.568 | 0.511–0.610 |
| Secondary: p0 | 0.779 | 0.753–0.802 | 0.715 | 0.666–0.760 | 0.564 | 0.505–0.607 |
| Word-only baseline, descriptive | 0.536 | Not declared | 0.490 | Not declared | 0.085 | Not declared |

Bootstrap: 2,000 whole-child resamples, seed 20260930, linear 2.5/97.5 percentiles; zero undefined replicates for all reported ranking intervals. The word baseline pools exact word-string vote rates from other DEV children and falls back to other children’s overall rate. Its point estimate is descriptive; no paired difference interval or significance test was declared. It does not control study, recording conditions, rater effects or speaker-level cues.

Both protocol readings pass: the primary lower AUROC endpoint exceeds 0.50 and **119/119** pooled leave-one-child-out deletions remain above 0.50; primary AUROC also exceeds 0.70 with its lower endpoint above 0.60. The deletion AUROC range is **0.779–0.785**. These deletions measure the stability of the pooled result. They are distinct from performance inside each child’s recordings: **97/119** within-child AUROCs exceed 0.50, their unweighted median is **0.605**, and their range is **0.225–0.925** (all 119 defined). These per-child values have at most 40 selected words and are descriptive, without individual reliability claims.

## Descriptive breakdowns

Primary-score breakdowns are descriptive, with no additional tests or threshold choice. Children may occur in multiple context, phase, listener-count or study groups; their child-count columns cannot be summed as independent children. Age 6 has only two children and age 7 only eight; the overall result does not validate the youngest ages separately.

### Rhotic context

| Group | Tokens | Children | AUROC | AP | Derhotic vote prevalence |
| --- | ---: | ---: | ---: | ---: | ---: |
| intervocalic | 35 | 19 | 0.795 | 0.716 | 0.405 |
| postvocalic | 1892 | 117 | 0.762 | 0.727 | 0.498 |
| prevocalic | 2607 | 116 | 0.799 | 0.713 | 0.454 |

### Phase group

| Group | Tokens | Children | AUROC | AP | Derhotic vote prevalence |
| --- | ---: | ---: | ---: | ---: | ---: |
| PRE | 2649 | 115 | 0.823 | 0.717 | 0.385 |
| notPRE | 1885 | 69 | 0.716 | 0.724 | 0.573 |

### Age year

| Group | Tokens | Children | AUROC | AP | Derhotic vote prevalence |
| --- | ---: | ---: | ---: | ---: | ---: |
| 6 | 80 | 2 | 0.635 | 0.770 | 0.683 |
| 7 | 293 | 8 | 0.779 | 0.787 | 0.580 |
| 8 | 668 | 20 | 0.716 | 0.613 | 0.446 |
| 9 | 819 | 21 | 0.758 | 0.796 | 0.619 |
| 10 | 1168 | 30 | 0.816 | 0.758 | 0.430 |
| 11 | 829 | 21 | 0.749 | 0.702 | 0.527 |
| 12 | 677 | 17 | 0.793 | 0.630 | 0.318 |

### Listener count

| Group | Tokens | Children | AUROC | AP | Derhotic vote prevalence |
| --- | ---: | ---: | ---: | ---: | ---: |
| n=2-4 | 1841 | 52 | 0.755 | 0.776 | 0.598 |
| n=5-9 | 1709 | 68 | 0.773 | 0.737 | 0.520 |
| n>=10 | 984 | 56 | 0.807 | 0.667 | 0.356 |

### Study

| Group | Tokens | Children | AUROC | AP | Derhotic vote prevalence |
| --- | ---: | ---: | ---: | ---: | ---: |
| BCS | 280 | 7 | 0.584 | 0.681 | 0.626 |
| BFS | 19 | 1 | 0.876 | 0.790 | 0.363 |
| BFS2 | 120 | 3 | 0.690 | 0.815 | 0.707 |
| CPF | 37 | 2 | 0.865 | 0.680 | 0.340 |
| CRESULTSMOSAIC | 835 | 21 | 0.580 | 0.118 | 0.077 |
| CRESULTSRCT | 400 | 10 | 0.720 | 0.889 | 0.789 |
| CRESULTSSCED | 40 | 1 | 0.592 | 0.801 | 0.762 |
| EFIF | 120 | 3 | 0.600 | 0.719 | 0.649 |
| EPG | 91 | 3 | 0.686 | 0.735 | 0.626 |
| HFS | 80 | 2 | 0.495 | 0.107 | 0.111 |
| Lilianne | 31 | 1 | 0.800 | 0.361 | 0.140 |
| PTR | 520 | 13 | 0.667 | 0.775 | 0.693 |
| PerceptionRCT | 600 | 15 | 0.760 | 0.840 | 0.680 |
| PrestonERP | 120 | 3 | 0.598 | 0.142 | 0.078 |
| PrestonEdwards2007 | 359 | 10 | 0.790 | 0.715 | 0.419 |
| PrestonHullEdwards2013 | 340 | 13 | 0.577 | 0.696 | 0.644 |
| TD | 53 | 2 | 0.445 | 0.090 | 0.082 |
| TPT | 160 | 4 | 0.653 | 0.728 | 0.670 |
| US2014 | 169 | 5 | 0.714 | 0.863 | 0.722 |
| VAB | 160 | 4 | 0.731 | 0.875 | 0.777 |

The large pooled score coexists with weak groups: CRESULTSMOSAIC has AUROC 0.580 across 835 tokens/21 children; PrestonHullEdwards2013 has 0.577 across 340 tokens/13 children; HFS and TD are below 0.50 but each has only two children. Between-child differences in rhotic severity, recording conditions and study can contribute to pooled ranking. These summaries do not apportion their contributions, and the within-child median is unweighted across children while the pooled metric uses listener-vote weights. The selected data do not establish a universal within-child, within-study, dialect or clinical effect. Full per-child and secondary-score breakdowns are retained in the pinned report.

## Part 2 beside nonspeech Part A

“Lost speech” means a corpus-designated word clip not admitted by this path, independent of its /r/ quality. There was no listening or audibility screen; corpus segmentation/labels define this outcome. Processing failures are separate and were zero in both panels. The two panels have different sampling designs and cannot estimate a deployment-wide false-positive/false-negative rate or establish a preferred policy.

| Fixed policy | Child words admitted | Child words lost | Lost proportion | Exact clip-independent 95% interval | Whole-child bootstrap 95% interval | Part A nonspeech admitted |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| Combined 250 ms | 326/357 | 31/357 | 8.68% | 5.98%–12.10% | 5.88%–12.32% | 3/60 |
| Combined 100 ms | 342/357 | 15/357 | 4.20% | 2.37%–6.84% | 1.96%–6.72% | 8/60 |

Exact intervals are two-sided Clopper–Pearson intervals treating clips as independent. The adjacent 2,000-resample child bootstrap accounts for three selected words per child (seed 20260930, zero undefined replicates). The earlier [Part A result](/Users/zacharywilson/Documents/speech-therapy/docs/model/nonspeech-robustness-result-20260929.md) supplies the nonspeech counts. Its historical user-signed-form blocker was incorrect; registered access has since been completed. This result supplies the missing retention panel, while leaving the broader rejection requirement open.

### Lost-word breakdown: Age year

| Group | Complete words | Lost at 250 ms | Lost at 100 ms |
| --- | ---: | ---: | ---: |
| 6 | 6 | 1 | 0 |
| 7 | 24 | 0 | 0 |
| 8 | 60 | 3 | 2 |
| 9 | 63 | 4 | 2 |
| 10 | 90 | 6 | 3 |
| 11 | 63 | 6 | 2 |
| 12 | 51 | 11 | 6 |

### Lost-word breakdown: Phase group

| Group | Complete words | Lost at 250 ms | Lost at 100 ms |
| --- | ---: | ---: | ---: |
| PRE | 216 | 14 | 5 |
| notPRE | 141 | 17 | 10 |

### Lost-word breakdown: Study

| Group | Complete words | Lost at 250 ms | Lost at 100 ms |
| --- | ---: | ---: | ---: |
| BCS | 21 | 2 | 1 |
| BFS | 2 | 0 | 0 |
| BFS2 | 9 | 0 | 0 |
| CPF | 2 | 0 | 0 |
| CRESULTSMOSAIC | 63 | 9 | 4 |
| CRESULTSRCT | 30 | 5 | 3 |
| CRESULTSSCED | 3 | 0 | 0 |
| EFIF | 9 | 0 | 0 |
| EPG | 7 | 0 | 0 |
| HFS | 6 | 0 | 0 |
| Lilianne | 2 | 0 | 0 |
| PTR | 39 | 7 | 3 |
| PerceptionRCT | 45 | 3 | 1 |
| PrestonERP | 9 | 0 | 0 |
| PrestonEdwards2007 | 30 | 0 | 0 |
| PrestonHullEdwards2013 | 39 | 1 | 1 |
| TD | 4 | 0 | 0 |
| TPT | 12 | 3 | 2 |
| US2014 | 13 | 0 | 0 |
| VAB | 12 | 1 | 0 |

All subgroup processing-failure counts are zero. Complete per-subgroup proportions and exact intervals are in the pinned report. Part 2 excludes words shorter than 0.3 s by design; these observations do not establish retention for shorter words, other phones or unrestricted child speech.

## Execution, verification and review

- All stages ran once on the local Mac CPU. No fitting, calibration, threshold selection, policy change, test opening, learner-feedback change or publication occurred.
- Declaration, cut, extraction, predictions, retention and evaluation form a hash-linked chain. External milestone records identify actual stage starts and completion observations; the declaration and frozen protocol retain pre-run wording.
- 34 worker/evaluation/statistical-auditor synthetic tests passed before declaration, including a real ffmpeg cut within two frames and metric parity on all-positive, all-negative and tied-score cases. Five additional external parent-checker integrity tests passed.
- Independent statistical audit passed: every reported metric, bootstrap, deletion, breakdown, baseline, coverage and retained-word count was recomputed from saved joined records. It did not open archive/audio, reread ratings or run inference.
- Separate parent artifact audit passed: 35,764 files checked, 4,746 clip headers/hashes/durations, 4,534 finite float32 feature matrices of shape (1,1037), and 357 raw/filter pairs. It hashed archive bytes without parsing ratings and performed no audio decoding or model replay.
- Parent verification limits: retention raw/filter hashes are not directly pinned by retention.json; the parent checks their saved directory index, clip/input bindings and decision agreement. The retained feature-source relationship remains documented rather than hash verified. Neither audit independently replays inference or compares the saved votes with a second archive read.
- Fable 5.1 pre-declaration reviews v2/v3 and the statistical-audit delta were CLEAR after fixes. The parent checker source review was CLEAR; optional extra binding guards/disclosures passed five synthetic tests and their saved diff is supplied to the result reviewer. Actual claude-fable-5-1 usage and successful exits were verified.
- Final [Fable 5.1 result review](/Users/zacharywilson/Documents/speech-therapy/work/percept-r-check-20260930/review-result-fable-v1.md) returned **CLEAR**. Exit0,is_error=false and actual `claude-fable-5-1` model usage were checked. It confirmed displayed numbers and scope; its requested timing-source clarification and optional overlapping-group clarification were applied. Source DOI and grant acknowledgment were verified against the official PhonBank pages/PDF. The reviewer did not hash files or replay inference. No main app builds ran, because this is an isolated research check without app changes. The existing Node module-type warning did not prevent any forward.

## Bound artifacts

| Artifact | SHA-256 |
| --- | --- |
| [Declaration](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/declaration.json) | `b04ecc2a97814e0dd6e699d1adecb74cb5e466a25a9c8a97a089f6801f549070` |
| [Media manifest](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-source/media/manifest.jsonl) | `e1b32a81ac9147df9e7191c9a9ed75b14e212f778e1224d477a70df28f242d11` |
| [Selection](/Users/zacharywilson/Documents/speech-therapy/work/percept-r-check-20260930/selection-v1.json) | `d25d2acd45692e8f1998298c5ae7b66d9843e3e8be2ce16a51382106822c0421` |
| [Clips](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/clips/clips.json) | `8a8196ef09f37538c262719cfe6960da8ede5db8c96d6329d6996676387f10da` |
| [Extraction](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/extract/extract.json) | `c71b6a675b78f2a23fd01b048905a1f590864912d3c7e570352cc38f961a0ca2` |
| [Predictions, locked before rating join](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/predict/predictions.json) | `501eaf418ab8e466043d6bbedc052f488894db263a71f8187848323841eae0a1` |
| [Retention](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/retention/retention.json) | `ad87063f6577f1aa300c7d2ddfe9a3f314c86460283fab1ede07ee1d4c803601` |
| [Saved sole rating join](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/evaluation/per-token.json) | `ae40050146505fb562ee1dfb03f10eb10e24b26020e95e15a60cdd2067382ac9` |
| [Evaluation report](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/evaluation/report.json) | `e158bc1172c14b7912b6eaa3a1f65f6ba9cfe775a0dc8c47837146dd78988384` |
| [Statistical audit](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-check-20260930/v1/evaluation/offline-audit.json) | `de599edfd28722ea89f767cd02b195947f0c138eda39e812cfa44347c56b31e8` |
| [Parent artifact audit](/Users/zacharywilson/Documents/speech-therapy/work/percept-r-media-20260930/parent-audit-v1.json) | `0dc6a8ffcc1c452563b555ae3e73172dcce80cd916ed1bc5a9a447afaf7bbb0f` |
| [Exact WAV byte diagnostic](/Users/zacharywilson/Documents/speech-therapy/work/percept-r-media-20260930/cross-partition-byte-audit-v1.json) | `8a9e462eaba42573ccae8ba625700d52cbde09dc9c9acb331336048789a1df28` |

Stage summaries record extraction completion at 07:51:30 UTC and retention completion at 08:24:00 UTC. The external [milestones](/Users/zacharywilson/Documents/speech-therapy/work/percept-r-check-20260930/run-milestones.jsonl) record later completion observations at 07:51:52 UTC and 08:24:31 UTC, respectively; extraction started at 05:47:37 UTC. The initial one-hour extraction estimate was low. Neither stage was rerun.

## Scope and research limits

This is fresh corpus evidence for the retained head’s pooled /r/ ranking on the declared DEV children, not improvement of the model itself. Word overlap with earlier fitting data and upstream phonetic-encoder/Silero exposure were not established; no unseen-word or unseen-pretraining claim follows. The other 22 supported consonants receive no fresh accuracy evidence. Listener types are mixed without per-token rater-type or agreement fields. Study, treatment phase, recordings and speaker cues may contribute to pooled separation. Selected sample counts are not population rates, and rater votes within tokens are correlated; uncertainty resamples entire children. No clinically useful threshold, calibration, clinical accuracy or learner-feedback readiness is established. The retained bundle and product remain unchanged. DEV is now consumed evidence; TEST stays sealed for a separately declared future comparison.

## Corpus citation and acknowledgment

Benway, Preston, Hitchcock, Salekin, Sharma and McAllister (2022), [PERCEPT-R corpus paper, Interspeech 2022](https://talkbank.org/phon/access/Clinical/0docs/benway22_interspeech.pdf), doi:10.21437/Interspeech.2022-10785. Source: [PhonBank PERCEPT-R corpus](https://talkbank.org/phon/access/Clinical/PERCEPT-R.html). The acquired public archive is identified by SHA-256 589535842e92a53a79c2614a0e07e9d357b79a4a421d61e5df7ecaebfd651a62; paper-era corpus counts are not substituted for this acquired version.

PhonBank support acknowledgment: NIH-NICHHD RO1-HD051698, as requested by the [PhonBank index](https://talkbank.org/phon/access/). All acquired media, transcript-derived records, features and weights remain local noncommercial research assets and are not redistributed.
