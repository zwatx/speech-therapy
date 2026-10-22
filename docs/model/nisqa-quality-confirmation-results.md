# NISQA recording-quality candidate: first fixed confirmation

The WavLM quality candidate passed the predefined continuation screen on all 40 fixed confirmation recordings. Its mean absolute error across the five 1–5 quality ratings was **0.366238**, compared with **0.456834** for acoustic-only ridge: **19.83% lower error**. Every paired 95% bootstrap interval against the three controls stayed below zero. This supports an untouched replication of this recording-quality approach; it does not establish improved child pronunciation judgments or authorize promotion to the application.

## Fixed study and phase barriers

The [protocol](/Users/zacharywilson/Documents/speech-therapy/docs/model/nisqa-quality-study-v1.md) was fixed before selection, encoder inference and fitting. The 200 recordings are from NISQA TRAIN_LIVE: 100 phone and 100 Skype, with one recording from each metadata-derived connected component. The split was 120 fitting, 40 selection and 40 confirmation recordings, balanced by capture condition in every partition. Existing 20-recording pilot components were excluded before selection. All 200 WAVs were acquired and independently checked; all 1,000 selected quality values were valid, with no missing labels, dropped records or replacements. No evaluation-split audio or labels were used.

The candidate uses frozen WavLM base-plus final-hidden mean and population standard deviation, a fitting-only 16-component PCA, and six original-waveform acoustic scalars. The acoustic control uses those six scalars. Each ridge model selected lambda 0.01 from the declared four-value grid on the 40 selection rows. Transforms and models were then refit on the authorized 160 rows. Pooled and separate phone/Skype mean controls use the same 160 rows. All four models and 40-row prediction sets were saved and frozen before confirmation labels were opened, following a separate Opus 5.5 review of the exact prediction freeze. Predictions were neither clipped nor calibrated.

## Confirmation errors

Lower values are better. Macro MAE and macro RMSE equally weight the five rating dimensions.

| Model | Macro MAE | Macro RMSE |
| --- | ---: | ---: |
| WavLM + acoustic ridge | 0.366238 | 0.462587 |
| Acoustic-only ridge | 0.456834 | 0.574501 |
| Pooled fitting mean | 0.529876 | 0.650373 |
| Capture-condition fitting mean | 0.547353 | 0.659979 |

| Candidate minus control | MAE difference | Paired 95% interval |
| --- | ---: | ---: |
| Acoustic-only ridge | -0.090596 | [-0.138083, -0.044522] |
| Pooled fitting mean | -0.163638 | [-0.231698, -0.099891] |
| Capture-condition fitting mean | -0.181115 | [-0.234961, -0.129025] |

These intervals use the same 10,000 PCG64 draws, seed 27092026, paired by the 40 metadata components, with linear quantiles. They quantify this fixed finite sample; they do not prove independence of human speakers or population validity.

| Rating dimension | Candidate MAE | Acoustic MAE | Pooled mean MAE | Capture mean MAE |
| --- | ---: | ---: | ---: | ---: |
| Overall quality (MOS) | 0.300542 | 0.500010 | 0.620678 | 0.679363 |
| Noisiness | 0.411592 | 0.559387 | 0.562984 | 0.585850 |
| Discontinuity | 0.465721 | 0.508087 | 0.550966 | 0.574895 |
| Coloration | 0.354570 | 0.365082 | 0.415049 | 0.379393 |
| Loudness | 0.298766 | 0.351604 | 0.499702 | 0.517264 |

| Capture | Candidate MAE | Acoustic MAE | Capture mean MAE | Candidate minus capture mean |
| --- | ---: | ---: | ---: | ---: |
| phone (20 recordings) | 0.305958 | 0.388045 | 0.536706 | -0.230748 |
| Skype (20 recordings) | 0.426518 | 0.525623 | 0.558000 | -0.131482 |

The gain was uneven across dimensions, strongest in overall quality, noisiness and loudness. Both ridge models selected the lowest value in the fixed lambda grid; the grid did not bracket the selection optimum and was not widened.

The 0.05 improvement margin applies to the point estimate. Against acoustic ridge, the interval upper endpoint of −0.044522 remains compatible with a gain smaller than 0.05, even though the predefined screen passes.

Every continuation guard passed: at least 0.05 lower macro MAE against each control; every interval upper endpoint strictly below zero; no dimension more than 0.10 worse than the pooled mean; and both capture groups no worse than the capture-condition mean.

## Verification and limits

Root verification replayed all 200 acquisition, decoding and feature bindings. The first four fitting recordings reproduced their CPU encoder features bit for bit. It replayed every selection-grid state and the refitted models, independently recomputed the saved-state projection and ridge normal equations/predictions, and reproduced the pooled/capture means and ordered confirmation identities. A separate confirmation verifier exactly replayed the fixed target parser and independently recomputed dimension MAE/RMSE, macro MAE, the paired bootstrap, capture macro MAE comparisons and all continuation guards. Source review and verification have different scopes: the fitted algorithm was reviewed and replayed; the complete PCA fitting algorithm was not independently reimplemented.

The component grouping is based on published reader, book and source codes, not verified independent people. Speaker ages are unverified, and audiobook overlap with encoder pretraining is unresolved. Whole-recording quality ratings provide neither produced-phoneme truth nor nonspeech labels. The 40 confirmation rows have now been used and must not become an untouched test for another recipe. No claim is made about ages 6–12, speech disorders, short word recordings, deployment accuracy or clinical use. The existing pronunciation package remains unchanged.

Fit-range bounding was declared before outcomes. In confirmation, the candidate had 1,475 SSL-column clamps before PCA and two final-column clamps; the acoustic model had one final-column clamp. SSL clamps were concentrated in zero-based confirmation row indices 7 (667), 12 (205) and 24 (170). These rows were retained without reweighting. The acoustic control predicted as low as 0.846 outside the label range; no prediction was clipped. This is a limitation of this fixed control and recipe, not a reason to modify it after observing results.

The actual Mac CPU feature pass took 70.53 seconds from its started artifact to complete freeze, including model loading, forward passes, saves and integrity checks. This is not a dedicated inference benchmark. This study used no Colab GPU allocation; the separately prepared controller remains prospective.

## Reviewable artifacts

- [Fitting declaration](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-training-v1/plan.json)
- [Prediction freeze](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-training-v1/refit-predict-freeze.json)
- [Confirmation results](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-training-v1/confirm/results.json)
- [Confirmation freeze](/Users/zacharywilson/Documents/speech-therapy/research/audio-head/outputs/nisqa-20260927/quality-training-v1/confirm-freeze.json)
- [Root prediction verification](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-20260927/training-prediction-root-verification.json)
- [Root confirmation verification](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-20260927/confirmation-root-verification.json)
- [Opus fitting source review](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-20260927/opus-training-source-review.json)
- [Opus specific prediction review](/Users/zacharywilson/Documents/speech-therapy/work/nisqa-quality-20260927/opus-prediction-review.json)

| Frozen artifact | SHA256 |
| --- | --- |
| plan.json | `797361b0a979a739f6d42d4d270c507d1a8e3a9de9172d613b7b6e3f2f71ebc5` |
| choose-freeze.json | `ca806a11ca7251914e0d4551ae319dbc03e0dbea0aa3ce17503be83d24327975` |
| refit-predict-freeze.json | `06658f6617bdef7370864e98251eafbb4e61d72cbd7d244c6d8dee12c6f201b6` |
| confirm-freeze.json | `257b654819760c280117ed455b38c684194cd12c8b27bf86c3715d74612ef821` |

The next scientific step is to freeze an unchanged replication recipe and use previously untouched, disjoint training-side components. A pass here is permission to test that hypothesis further; the broader pronunciation goal still needs unfamiliar children and appropriate pronunciation/nonspeech truth.
