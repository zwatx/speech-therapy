# Temporal feature extraction

The fixed before/interval/after representation was extracted successfully for all **9,891 positions, 1,040 recordings, 52 children ages 6–12 and 23 consonants**. This establishes usable, audited features for the next model experiment; it does not establish better rating prediction.

The final-layer vectors use the existing encoder and cached alignment windows. Each position now has three 1,024-dimensional means, concatenated in before/interval/after order. These are positions around estimated alignment intervals, not verified produced-phone boundaries. The 13 cached alignment scalars are unchanged. See the [protocol](temporal-pooling-protocol.md).

| Check | Observed result |
| --- | --- |
| Fresh padded mean versus historical cache | Exact array equality for every position |
| Float64 count-weighted reconstruction before casting | Maximum absolute error 0 |
| Reconstruction from persisted float32 bins | Maximum absolute error 3.8146972691777137e-7 |
| One-frame estimated intervals | 8,990 of 9,891 |
| Empty before/after bins | 0 / 0 |
| First and longest recording replays | Exact stored arrays; independently repeated |
| Authoritative extraction elapsed time | 215.436 seconds on Mac CPU |

Both context-edge fallback behavior and rejection of malformed windows were tested synthetically. The fallback was not needed in the actual recordings. The float64 and float32 checks have different purposes: rounding explains the latter residual, and the declared `1e-10` tolerance applies only before casting.

An independent GPT-6 Astra audit reconstructed every per-recording/global-array join, row identity, bin count, cached scalar/final comparison and persisted reconstruction residual. It also re-extracted the first and longest recordings and independently pooled all 22 positions in those recordings. The audit was clear. No recording was dropped, no labels were invented, and no author-test audio was read.

The extraction ran while some synthetic implementation checks were active, so its elapsed time is a workflow measurement, not an isolated hardware benchmark. The separately reviewed 22-recording CPU timing sample ran after extraction and other heavy local checks finished. Colab timing is tracked separately; it must not be inferred from this report.

The next experiment keeps PCA16 plus the same 13 scalars and the same prediction-head size. Its larger raw PCA input changes preprocessing complexity and may retain or discard temporal contrasts. The matched training study has its own declaration and independent review; the extraction audit does not authorize model promotion.

## Evidence

- [Extraction plan](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-v1/plan.json), SHA-256 `76ce734cf674c21b4d4e2f2c02c8db57461fb43adf63fedd3380bcc08c7cc88d`.
- [Completed feature report](../../research/audio-head/outputs/multiphone-20260927/temporal-pooling-v1/features/report.json), SHA-256 `33fc0c5b2936f546cdbd20304e58cd2d4e674362543c9458b08a0bc20a4992e0`.
- [Independent source review](../../work/temporal-pooling-review-20260927/source-review.json), SHA-256 `6295e3e597c31ecd350e1e28e2c0a032f0dd8be4fe1c38524ab68c76dae5686b`.
- [Independent results review](../../work/temporal-pooling-review-20260927/results-review.json), SHA-256 `106f9b33a5ccbc6b71523e6f76bd2bb7d076e6c8d121705f4929b425efeb12f7`.
- [Rating-free interval inventory](../../work/temporal-pooling-20260927/interval-inventory.json).
