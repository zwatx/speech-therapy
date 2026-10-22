# PERCEPT-R binary /r/ development head — result

The new /r/ specialist passed its fixed development screen. Mean within-child vote-weighted AUROC increased from **0.609382 to 0.645472**, a paired gain of **0.036090**. Pooled AUROC increased from **0.781920 to 0.839268**. The independent offline audit verified all 91 saved fits, predictions, input bindings, nested selection and reported statistics. A full-DEV research checkpoint was fitted using the predeclared rule. Pooled AUROC mixes between-child and between-study derhotic rates with token ranking. Child folds do not require study disjointness, so pooled gains may reflect cohort, speaker or recording cues; they do not isolate within-child token discrimination. The within-child result is primary.

This is DEV-informed development evidence. The 80-child sealed TEST group remains untouched. The result estimates the cross-validated training procedure; it does not evaluate the exported full-DEV coefficients on new children. There is no clinical or learner-feedback eligibility, product replacement, publication or redistribution.

## Fixed experiment

[Protocol](/Users/zacharywilson/Documents/speech-therapy/docs/model/percept-r-binary-head-protocol-20261002.md), binary-head attempt 1, declared on 2026-10-02 before candidate fitting. The previous external check had already exposed DEV outcomes and motivated this direction. This attempt reuses all 4,534 complete selected /r/ feature/vote pairs from 119 numeric DEV children, with the same five predetermined AX0 exclusions from 4,539 selected words. No new exclusions, processing failures, retries or outcome-driven changes occurred. DEV-informed design can make OOF figures optimistic relative to a fresh confirmatory comparison. The original selection capped words at 40 per child.

The response is derhotic listener fraction `(n-k)/n`; it is not SpeechOcean's three-category rating. All 1,037 feature columns, token/clip bindings, feature hashes, retained predictions, counts and metadata passed preflight. Cross-corpus participant identity overlap between retained training and PERCEPT-R has not been independently established. Selected clip or feature hashes do not cross child IDs. No original archive, audio, encoder inference, retained rescoring or speech-filter run was used in this experiment. The relationship between retained training features and the occurrence-aware extraction remains documented rather than hash verified, inherited from the closed external check.

Five outer child folds and four inner child folds were fixed by salted hashes. The candidate uses fit-only PCA16 of 1,024 embeddings, 13 scalars and retained-score logit, then fit-only standardization and ridge logistic regression. Binomial log loss gives each child equal total weight and weights words by listener counts within child. Four fixed ridge values were chosen using inner validation log loss. All 80 inner fits, five outer candidate fits and five monotonic retained-score calibration fits converged under the fixed stationarity criterion. Candidate and all control OOF predictions were saved and externally hash-recorded before final evaluation.

Outer selected ridge values were **0.01, 0.001, 0.01, 0.01, 0.01**. None lies at a grid boundary. The fixed mode rule therefore used **0.01** for the full-DEV fit. All 18 synthetic tests passed before declaration, including an actual synthetic 91-fit pipeline/audit, held-out feature/label/selection invariance, numeric replay and artifact tamper rejection. Fable 5.1 reviewed the plan and source; its blockers were resolved before declaration, and both final read-only checks passed. Claude CLI response model-usage metadata verifies model identity `claude-fable-5-1`; this is not model self-report.

## OOF results

AUROC and AP weight positive/negative listener votes, including half-credit ties within a token. Derhotic is the positive class for AP. Conflicting listener votes within a word can cap vote-weighted AUROC below 1 even at perfect ordering of word-level vote fractions. Log loss and expected per-vote Brier weight children equally. These are binary corpus-judgment metrics, not percent-correct accuracy.

| Model | Mean within-child AUROC | Median within-child AUROC | Pooled AUROC | Pooled AP | Child-balanced log loss | Child-balanced Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Unchanged retained score | 0.609382 | 0.605405 | 0.781920 | 0.719143 | 1.079566 | 0.357350 |
| Monotonic retained calibration | 0.609382 | 0.605405 | 0.780929 | 0.717295 | 0.580880 | 0.196173 |
| Fit-only prior | 0.500000 | 0.500000 | 0.454057 | 0.447117 | 0.692835 | 0.249844 |
| New binary /r/ candidate | **0.645472** | **0.624015** | **0.839268** | **0.806890** | **0.513992** | **0.167927** |

The calibration control is the useful proper-score comparison: the retained score originally represents a different target. Candidate pooled Spearman is 0.694918, versus retained 0.568172.

All five improvement gates passed, with definedness checked separately as a prerequisite:

| Predeclared gate | Observed |
| --- | --- |
| Within-child mean gain >=0.02 | 0.036090 |
| Paired child-bootstrap lower gain >0 | 95% interval **[0.021681, 0.051668]** |
| Every whole-child study omission leaves positive mean gain | All 20; range **0.032620–0.041368** |
| Pooled candidate AUROC >= retained minus 0.01 | 0.839268 vs required 0.771920 |
| Candidate balanced log loss <= monotonic calibration | 0.513992 <= 0.580880 |

All 119 per-child AUROCs are defined. **84 children improved, 34 worsened, one tied.** Individual gains range from -0.181818 to +0.401408. Mean gains after removing one child range from 0.032994 to 0.037937; those deletion results are descriptive, not an additional gate. There were zero exact retained-score ties between distinct words within any child.

The paired bootstrap used 2,000 whole-child draws with the fixed generator/seed. It conditions on saved OOF fits and does not estimate refitting, overlapping-fold or study-level uncertainty. Study omission removes every child with any selected token from that study, including their other-study tokens, and averages remaining saved gains without refitting. It is **not study-held-out training**; small study omissions can pass trivially under the mean-gain gate.

Descriptive pooled results still show substantial weaknesses:

| Study | Children | Tokens | Retained AUROC | Candidate AUROC |
| --- | ---: | ---: | ---: | ---: |
| BCS | 7 | 280 | 0.583872 | 0.686720 |
| CRESULTSMOSAIC | 21 | 835 | 0.579822 | 0.625853 |
| PrestonHullEdwards2013 | 13 | 340 | 0.576822 | 0.651387 |
| CRESULTSSCED | 1 | 40 | 0.591950 | 0.571505 |

Probability scores also reverse in some studies. Both log loss and Brier are worse than the unchanged retained score in these saved breakdowns:

| Study | Children | Candidate log loss / Brier | Unchanged retained log loss / Brier |
| --- | ---: | ---: | ---: |
| CRESULTSMOSAIC | 21 | 0.380127 / 0.110342 | 0.291407 / 0.072019 |
| TD | 2 | 0.381796 / 0.109286 | 0.297833 / 0.069472 |
| Lilianne | 1 | 0.623737 / 0.196131 | 0.338655 / 0.106816 |

CRESULTSMOSAIC is the largest study; even the monotonic calibration control is worse than the unchanged score there (log loss 0.514763). Candidate log loss also loses to calibration in CRESULTSSCED (0.651508 vs 0.601311) and EFIF (0.688679 vs 0.668902), and exceeds the fit-only prior in EFIF (0.683546). These descriptive reversals do not change the fixed overall screen or trigger exclusions, thresholds or additional fits. Overall proper-score improvement is not uniform probability improvement.

The candidate's overall gain is not improvement for every child or study. All predeclared study/context/age/phase breakdowns are retained in the evaluation JSON. Ages 6 and 7 have only 2 and 8 children, and the intervocalic group only 35 words. Canonical-prompt features and embeddings can encode word identity, so a within-child gain may reflect word difficulty as well as acoustics. Words and studies are not independently held out. The other 22 supported consonants, syllabic ER, unfamiliar corpora, recording robustness and non-speech rejection receive no new evidence here. No extra runs, subgroup exclusions or thresholds were selected from these results.

## Saved candidate and verification

[Research checkpoint](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-binary-head-20261002/v1/final/full-dev-candidate.npz) and [metadata](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-binary-head-20261002/v1/final/final.json) describe an R-only binary derhotic/rhotic head. Its 30 columns and required retained `p0+p1` logit input, clipped at 1e-6 for that input, are explicit. It requires the original retained bundle manifest `bc62f1e4…`; it is incompatible with SpeechOcean 0/1/2 categories. PCA/moments/coefficients and fit indices are safe numeric NPZ arrays. The screen justified preserving this research candidate, not replacing the product model. Baseline and retained-logit comparisons are conditional on the cached research extraction; equivalence to prospective product behaviour is not established by this study.

[Evaluation](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-binary-head-20261002/v1/evaluate/evaluation.json) and [independent audit](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/percept-r-binary-head-20261002/v1/offline-audit.json) contain the complete numeric evidence. Audit recomputed fit-only transforms, coefficients' stationarity and predictions, all inner losses/selections, priors/calibration, full OOF coverage, every statistic/gate and final-fit eligibility. It shares only hash/input plumbing with the producer and independently implements numerical calculations; independence refers to the implementation, not a separate institution. Externally recorded completion/journal hashes anchor the saved chain. Neither audit nor this result involved new inference or TEST access.

| Artifact | SHA-256 |
| --- | --- |
| Declaration | `acfc03efc1ed349f206e8e98be9500fb1232c9a9928b5400401956bc57502610` |
| Locked OOF predictions | `64c0c7b94db969322dea20740435de0abc46453966c6627632ec511b7ce6426a` |
| Evaluation | `9ec72ff0bb388b22c4566c30588ab7def644fc12f486a58d5bffe08bc4ecf76e` |
| Final completion | `c6d05b849527b7e4cb89024876fc20556afebb52c22e7556bdc1e41907849dfa` |
| Journal | `d6bfe53b5c0cd94ae0caad678537326c709b44618251b0cd4d895e81fc781765` |
| Independent audit | `7542efa15448cc60783f49966775b5427d60d4a44383e020ee7c400752e35b6b` |

Actual journal starts/completions: declare 06:30:43–06:30:46 UTC; train 06:31:04–06:31:17; evaluate 06:32:02–06:32:06; final 06:32:36–06:32:39 on 2026-10-02. Parent milestone observations are later timestamps, not substituted stage completion times. Work/review evidence is in `work/percept-r-binary-head-20261002/`; scientific sources and the declared protocol remain immutable.

The next validation step is a separately fixed blind comparison of this preserved candidate against the retained model on reserved children. The broader usable-model objective remains open.
