# Fixed-model recording-quality replication

The recording-quality candidate passed its prespecified replication screen on 40 newly selected recordings. Without refitting or changing its recipe, it achieved mean absolute error (MAE) **0.3853**, compared with **0.5116** for the acoustic baseline: **24.68% lower error**. All four fixed guards passed. This supports the recording-quality component on NISQA TRAIN_LIVE phone/Skype read-speech recordings; it does not establish child pronunciation accuracy, recording-usability thresholds, nonspeech detection or clinical validity. The broader model goal remains active.

The first study achieved 19.83% lower error than its acoustic baseline on its original 40 confirmation recordings. That result is documented separately in [the first confirmation report](/Users/zacharywilson/Documents/speech-therapy/docs/model/nisqa-quality-confirmation-results.md). The replication decision uses the new 40 alone. No pooled pass decision was made. The candidate’s absolute error was 0.3853 versus 0.3662 in the first test; the larger relative gain mainly reflects a higher acoustic-baseline error on this sample. The two percentages do not show that the model changed or improved between tests.

## What was fixed before the replication

The [replication protocol](/Users/zacharywilson/Documents/speech-therapy/docs/model/nisqa-quality-replication-v1.md) preserves the original four saved models trained on 160 recordings: WavLM mean/std features plus six raw acoustic descriptors, acoustic descriptors alone, the pooled training mean, and capture-specific training means. The original PCA, feature scaling and feature bounds, coefficients, intercepts, regularization and control means were reused unchanged. There was no refitting, lambda change, calibration, prediction clipping or replacement draw.

The fresh set contains 40 distinct publisher-derived source components, with 20 phone and 20 Skype recordings. Metadata selection excluded the complete connected components of the earlier 20-recording pilot and all 200 first-study recordings, including unselected recordings belonging to those components. These components approximate source independence; they are not verified independent people. The recordings are age-unverified audiobook read speech.

Opus 5.5 independently reviewed the new method, exact source and declaration before acquisition or inference. After all predictions were frozen, a separate Opus 5.5 review cleared the exact prediction freeze before the new ratings were opened. The provider metadata for those completed reviews identifies `claude-opus-5-5`, with no fallback or permission denial. These were static reviews; the root ran the verification described below.

## Fresh40 results

Scores average absolute error equally across five 1–5 quality dimensions. Lower is better.

| Model | Macro MAE |
| --- | ---: |
| WavLM plus acoustics candidate | 0.385322 |
| Acoustic baseline | 0.511568 |
| Pooled training mean | 0.563030 |
| Capture-specific training means | 0.524677 |

Differences below are candidate minus control. The intervals use the original fixed 10,000 common paired component-bootstrap draws, PCG64 seed 27092026 and linear quantiles. Negative values favor the candidate.

| Control | MAE difference | Paired 95% interval |
| --- | ---: | --- |
| Acoustic baseline | −0.126246 | [−0.189918, −0.068895] |
| Pooled mean | −0.177707 | [−0.245510, −0.116870] |
| Capture-specific means | −0.139355 | [−0.193018, −0.090288] |

| Prespecified guard | Result |
| --- | --- |
| At least 0.05 lower point-estimate MAE against each of the three controls | Pass |
| Upper paired interval endpoint strictly below zero against every control | Pass |
| No dimension more than 0.10 worse than the pooled mean | Pass |
| Neither capture worse than its capture-specific mean | Pass |

| Dimension | Candidate MAE | Acoustic MAE | Pooled mean MAE |
| --- | ---: | ---: | ---: |
| Overall quality (MOS) | 0.261778 | 0.495128 | 0.583803 |
| Noisiness | 0.427746 | 0.557047 | 0.623433 |
| Discontinuity | 0.463290 | 0.580671 | 0.606660 |
| Coloration | 0.399824 | 0.458704 | 0.460001 |
| Loudness | 0.373973 | 0.466291 | 0.541250 |

Phone candidate MAE was 0.349831, versus 0.545828 for the phone training mean (difference −0.195997). Skype candidate MAE was 0.420814, versus 0.503526 for its training mean (difference −0.082712). All 200 selected rating values were present and valid; no rows were dropped or replaced. The formal outcome is **replicated**.

## Verification and interpretation

The root checked all 40 original file hashes, sizes, member CRCs, identity joins and exact waveform audits, and independently decoded their PCM16 samples. All 120 new range requests completed with HTTP 206. The shared transfer ledger and earlier directory bindings were preserved. Cumulative body transfer was 168,482,155 bytes and metadata transfer was 15,467,301 bytes, below their fixed caps. The partial archive's global MD5 remains unverified.

Before the 40 new forwards, four original fitting recordings reproduced their saved CPU pooled features, raw scalars and preprocessing metadata bit for bit. All new per-recording arrays were then checked against the combined feature archive and recorded hashes. Independent PCM16 raw-descriptor, downmix/resampling, processor-input, attention-mask and frame-count checks passed. The root independently replayed the saved feature transformations and coefficient predictions exactly, together with both mean controls and clamping diagnostics. This verifier did not rerun all 40 encoder forwards or refit models.

After the reviewed label barrier, a separate root verifier replayed the selected target parser, MAE and dimension RMSE, common bootstrap indices, intervals, capture comparisons, four guards and outcome exactly. It did not perform a new fit or select another recipe.

The original saved feature bounds clamped 677 SSL entries in total, including 212 of 1,536 entries in zero-based row 19 and 69 in row 36. Final feature scaling clamped three candidate and two acoustic entries, all in row 19. These rows were retained without reweighting. Predictions remained unbounded and unclipped. This behavior was fixed before the replication and is not a reason to adjust the test after seeing results.

The effect is uneven across dimensions, and the sample is small. Against the acoustic baseline, 8 of 40 recordings favored the baseline, and four recordings (zero-based rows 9, 13, 18 and 36) account for about half of the summed gain. Row 36 also had feature clamping. This is a descriptive observation; no recordings were removed and no alternative pass decision was calculated. Publisher-code components do not establish verified speaker independence; possible overlap with encoder pretraining remains unresolved. The second test uses additional recordings from the same corpus and task, not a new child population or collection setting. No quality score threshold has been validated for rejecting recordings or delivering learner feedback. The two confirmation sets are now used, and cannot become untouched tests again.

## Frozen artifacts

- [Replication declaration](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-replication-v2/plan.json): SHA256 `712e74f886261897bfd1b30dbb06119661ced42466773fe84dfbbb7e4a4a8939`.
- [Prediction freeze](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-replication-v2/predict-freeze.json): SHA256 `b48c429ffdf7f587374ebbd4e4348fd208b1cca5f340df8790608eb02fb8e937`.
- [Confirmation freeze](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-replication-v2/confirm-freeze.json): SHA256 `3e5a59fe0aef6c9468f946d5fa60b80af85dd6597d95b733b2613dc5bcdb9c15`.
- [Full numerical results](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-replication-v2/confirm/results.json).
- [Source review](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-replication-20260927/opus-source-review.json), [selection verification](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-replication-20260927/selection-root-verification.json), and [audio verification](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-replication-20260927/ingestion-root-verification.json).
- [Root prediction verification](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-replication-20260927/prediction-root-verification.json), [root results verification](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-replication-20260927/confirmation-root-verification.json), and [Opus prediction review](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-replication-20260927/opus-prediction-review.json).

The next primary pronunciation hypothesis is separately described in [the method advice](/Users/zacharywilson/Documents/speech-therapy/work/core-model-next-method-20260927/advice.md) and [Opus's corrections](/Users/zacharywilson/Documents/speech-therapy/work/core-model-next-method-20260927/opus-method-review.json). It changes acoustic pooling over uncertain canonical locations. No improvement from that method has yet been measured.
