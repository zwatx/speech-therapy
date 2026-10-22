# Retained ages 6–12 bundle: cached-noise sensitivity result

**This is a descriptive replay, not an accuracy result.** The unchanged retained full-fit mixture was scored on existing clean features and on the existing 20 dB Gaussian-noise features. The positions are 5,654 legacy-cache child positions (1,037 recordings, 52 children, 23 consonants) that the bundle was **fitted on**. The noise condition was already consumed by earlier studies.

No human rating was used as the truth for noisy audio. There are no intervals or hypothesis tests. The [protocol](retained-noise-replay-protocol-20260929.md) was fixed before any prediction. The legacy cache doesn't cover all 9,891 fitting positions; three fitting recordings have no eligible legacy-cache target.

## What moved

Across all 5,654 positions:

| Measure | Value |
| --- | --- |
| Mean / max total variation | .0168 / .4649 |
| Mean signed expected-rating drift (noisy − clean) | −.0116 |
| Mean absolute drift / max absolute drift | .0263 / .8703 |
| Most likely class changed | 5 / 5654 positions |
| Positions drifting down / up | 4,164 / 1,490 |
| Positions with total variation > .10 | 181 |
| Positions with total variation > .25 | 18 |

The expected rating is p1 + 2·p2 on the corpus 0/1/2 scale.

Mean class probabilities moved from [.0171, .0239, .9589] clean to [.0222, .0254, .9524] noisy. **Noise mostly moved probability toward lower ratings**: the mean rating-0 probability rose from .0171 to .0222.

- **Consonants.** Downward drift appears for 21 of 23 consonants. The two exceptions are NG (+.0028) and W (+.0052).
- **Largest mean movement:** TH (.048), Z (.039) and CH (.038). **Smallest:** HH (.004) and G (.005).
- **Age.** Movement was largest at ages 6–7 (mean total variation .022 and .019) and smallest at 11–12 (.011 and .012). All 5 changes in most-likely class were at ages 6–7.
- **Children.** Mean total variation per child ranged from .005 to .042. Mean signed drift per child ranged from −.029 to +.003, and 4 of 52 children drifted upward on average.
- **Recordings.** Mean total variation per recording ranged from .0002 to .143. The 5 class changes came from 5 different recordings.

### By consonant

| Phone | Positions | Mean TV | Max TV | Mean signed drift | Mean abs drift | Argmax changes | Mean p(rating 0) clean → noisy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| B | 236 | 0.0135 | 0.4649 | -0.0203 | 0.0246 | 0 | 0.0087 → 0.0178 |
| CH | 42 | 0.0378 | 0.4112 | -0.0310 | 0.0690 | 0 | 0.0324 → 0.0457 |
| D | 322 | 0.0201 | 0.3051 | -0.0190 | 0.0316 | 0 | 0.0164 → 0.0235 |
| DH | 333 | 0.0165 | 0.2510 | -0.0086 | 0.0226 | 0 | 0.0139 → 0.0168 |
| F | 191 | 0.0106 | 0.1914 | -0.0153 | 0.0174 | 0 | 0.0035 → 0.0096 |
| G | 195 | 0.0052 | 0.0737 | -0.0080 | 0.0093 | 0 | 0.0029 → 0.0065 |
| HH | 237 | 0.0037 | 0.0596 | -0.0045 | 0.0064 | 0 | 0.0049 → 0.0069 |
| JH | 76 | 0.0210 | 0.1687 | -0.0213 | 0.0395 | 0 | 0.0268 → 0.0366 |
| K | 330 | 0.0061 | 0.2148 | -0.0058 | 0.0110 | 0 | 0.0080 → 0.0105 |
| L | 357 | 0.0228 | 0.4356 | -0.0169 | 0.0411 | 0 | 0.0311 → 0.0384 |
| M | 341 | 0.0211 | 0.2601 | -0.0247 | 0.0336 | 0 | 0.0200 → 0.0290 |
| N | 402 | 0.0115 | 0.2113 | -0.0048 | 0.0201 | 0 | 0.0197 → 0.0217 |
| NG | 119 | 0.0122 | 0.2986 | +0.0028 | 0.0201 | 1 | 0.0166 → 0.0149 |
| P | 153 | 0.0170 | 0.2765 | -0.0053 | 0.0303 | 1 | 0.0210 → 0.0232 |
| R | 304 | 0.0239 | 0.3051 | -0.0210 | 0.0416 | 0 | 0.0354 → 0.0445 |
| S | 378 | 0.0225 | 0.4280 | -0.0260 | 0.0386 | 1 | 0.0178 → 0.0285 |
| SH | 134 | 0.0162 | 0.1933 | -0.0165 | 0.0270 | 0 | 0.0267 → 0.0333 |
| T | 378 | 0.0085 | 0.1072 | -0.0047 | 0.0141 | 0 | 0.0115 → 0.0133 |
| TH | 75 | 0.0480 | 0.2125 | -0.0210 | 0.0669 | 1 | 0.0643 → 0.0716 |
| V | 200 | 0.0287 | 0.1625 | -0.0109 | 0.0336 | 0 | 0.0164 → 0.0210 |
| W | 323 | 0.0062 | 0.2366 | +0.0052 | 0.0114 | 0 | 0.0089 → 0.0064 |
| Y | 190 | 0.0074 | 0.2251 | -0.0009 | 0.0122 | 1 | 0.0108 → 0.0108 |
| Z | 338 | 0.0387 | 0.2855 | -0.0061 | 0.0417 | 0 | 0.0204 → 0.0296 |

### By recorded age

| Age | Positions | Mean TV | Max TV | Mean signed drift | Mean abs drift | Argmax changes | Mean p(rating 0) clean → noisy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 1389 | 0.0223 | 0.4649 | -0.0118 | 0.0352 | 3 | 0.0235 → 0.0286 |
| 7 | 1020 | 0.0186 | 0.2841 | -0.0117 | 0.0291 | 2 | 0.0189 → 0.0241 |
| 8 | 232 | 0.0162 | 0.3044 | -0.0177 | 0.0264 | 0 | 0.0209 → 0.0293 |
| 9 | 1191 | 0.0172 | 0.4280 | -0.0143 | 0.0269 | 0 | 0.0148 → 0.0210 |
| 10 | 226 | 0.0127 | 0.1121 | -0.0161 | 0.0195 | 0 | 0.0125 → 0.0188 |
| 11 | 792 | 0.0110 | 0.2601 | -0.0066 | 0.0169 | 0 | 0.0121 → 0.0149 |
| 12 | 804 | 0.0116 | 0.2765 | -0.0089 | 0.0178 | 0 | 0.0125 → 0.0166 |

### By child

| Child | Positions | Mean TV | Max TV | Mean signed drift | Mean abs drift | Argmax changes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0001 | 101 | 0.0173 | 0.2324 | -0.0103 | 0.0237 | 0 |
| 0005 | 102 | 0.0294 | 0.4649 | -0.0181 | 0.0455 | 0 |
| 0006 | 102 | 0.0075 | 0.1985 | -0.0090 | 0.0108 | 0 |
| 0026 | 109 | 0.0178 | 0.3051 | -0.0120 | 0.0240 | 0 |
| 0048 | 103 | 0.0416 | 0.4356 | +0.0013 | 0.0745 | 2 |
| 0053 | 102 | 0.0209 | 0.1152 | -0.0263 | 0.0332 | 0 |
| 0054 | 105 | 0.0159 | 0.1325 | -0.0148 | 0.0237 | 0 |
| 0056 | 100 | 0.0230 | 0.2132 | -0.0160 | 0.0341 | 0 |
| 0070 | 97 | 0.0172 | 0.2498 | -0.0105 | 0.0266 | 0 |
| 0075 | 105 | 0.0217 | 0.3037 | +0.0021 | 0.0349 | 0 |
| 0103 | 119 | 0.0194 | 0.2986 | -0.0152 | 0.0320 | 1 |
| 0104 | 109 | 0.0250 | 0.1824 | -0.0286 | 0.0399 | 0 |
| 0131 | 104 | 0.0196 | 0.2308 | -0.0128 | 0.0292 | 0 |
| 0145 | 96 | 0.0140 | 0.1314 | -0.0036 | 0.0220 | 1 |
| 1042 | 115 | 0.0140 | 0.1526 | -0.0093 | 0.0204 | 0 |
| 1044 | 110 | 0.0082 | 0.0780 | -0.0068 | 0.0122 | 0 |
| 1092 | 109 | 0.0210 | 0.3044 | -0.0288 | 0.0354 | 0 |
| 1197 | 99 | 0.0296 | 0.2841 | -0.0194 | 0.0461 | 0 |
| 1203 | 101 | 0.0214 | 0.2071 | -0.0256 | 0.0324 | 0 |
| 1418 | 91 | 0.0134 | 0.2148 | -0.0015 | 0.0222 | 0 |
| 1419 | 99 | 0.0165 | 0.1499 | -0.0164 | 0.0261 | 0 |
| 1435 | 110 | 0.0160 | 0.2251 | +0.0034 | 0.0267 | 1 |
| 1439 | 135 | 0.0311 | 0.2677 | +0.0009 | 0.0499 | 0 |
| 1447 | 95 | 0.0350 | 0.1914 | -0.0267 | 0.0580 | 0 |
| 2034 | 123 | 0.0118 | 0.1406 | -0.0079 | 0.0185 | 0 |
| 2179 | 96 | 0.0232 | 0.1781 | -0.0155 | 0.0369 | 0 |
| 3002 | 102 | 0.0094 | 0.1269 | -0.0065 | 0.0129 | 0 |
| 3020 | 122 | 0.0163 | 0.3051 | -0.0190 | 0.0260 | 0 |
| 3021 | 104 | 0.0195 | 0.4112 | -0.0119 | 0.0312 | 0 |
| 3046 | 112 | 0.0159 | 0.1748 | -0.0025 | 0.0249 | 0 |
| 3049 | 110 | 0.0243 | 0.3477 | -0.0233 | 0.0405 | 0 |
| 3068 | 108 | 0.0199 | 0.4280 | -0.0256 | 0.0334 | 0 |
| 3083 | 94 | 0.0191 | 0.1121 | -0.0268 | 0.0302 | 0 |
| 3088 | 96 | 0.0129 | 0.2777 | -0.0122 | 0.0195 | 0 |
| 3208 | 114 | 0.0105 | 0.1275 | -0.0085 | 0.0149 | 0 |
| 3423 | 123 | 0.0192 | 0.1907 | -0.0163 | 0.0284 | 0 |
| 3636 | 104 | 0.0181 | 0.2510 | -0.0150 | 0.0279 | 0 |
| 3837 | 122 | 0.0102 | 0.1444 | -0.0056 | 0.0160 | 0 |
| 5195 | 132 | 0.0082 | 0.0586 | -0.0085 | 0.0119 | 0 |
| 5218 | 129 | 0.0060 | 0.1240 | -0.0036 | 0.0084 | 0 |
| 5401 | 111 | 0.0180 | 0.2452 | -0.0065 | 0.0279 | 0 |
| 5408 | 132 | 0.0128 | 0.2601 | -0.0049 | 0.0195 | 0 |
| 5414 | 116 | 0.0165 | 0.1607 | -0.0196 | 0.0251 | 0 |
| 5418 | 105 | 0.0078 | 0.1880 | -0.0005 | 0.0128 | 0 |
| 5424 | 103 | 0.0093 | 0.1705 | -0.0092 | 0.0140 | 0 |
| 5551 | 121 | 0.0070 | 0.0761 | -0.0034 | 0.0106 | 0 |
| 6010 | 124 | 0.0105 | 0.1315 | -0.0035 | 0.0152 | 0 |
| 6048 | 97 | 0.0115 | 0.1113 | -0.0072 | 0.0163 | 0 |
| 6121 | 104 | 0.0051 | 0.0535 | -0.0018 | 0.0070 | 0 |
| 6401 | 117 | 0.0216 | 0.2765 | -0.0234 | 0.0345 | 0 |
| 6504 | 105 | 0.0118 | 0.2059 | -0.0133 | 0.0186 | 0 |
| 6912 | 110 | 0.0102 | 0.1256 | -0.0065 | 0.0166 | 0 |

Values for every recording are in the verified report JSON (`byClip` and `rows`).

## What this does and doesn't mean

- **The direction matters for a future product.** Under this synthetic noise, the model leans toward lower ratings, so recordings under this condition would tend to look like *more* errors, not fewer. That is a false-error risk worth carrying into any recording-quality gating design. It is a sensitivity observation, not a measured error rate.
- **Movement is not correctness.** Small movement can preserve mistakes or reflect lost acoustic distinctions. Age and consonant differences are confounded with each other and with the fitting data. The ages 8 and 10 fitting groups each contain only two children.
- **What it does not establish:** pronunciation correctness, physical-microphone robustness, generalization to new speakers or words, clinical validity, speech retention or nonspeech rejection.
- **What does not follow from it:** no threshold, filter, model, app or learner-feedback change. The worst cases are not selected for any further experiment.

## Verification

- **Execution.** The run executed once on the Mac CPU (2 threads; Python 3.13.14, NumPy 2.2.6, PyTorch 2.8.0) and completed with no failure record.
  - Declared: 2026-09-30 03:22:25Z.
  - Run: started 03:22:56Z (`started.json`). File modification times: `clean.npy` 03:24:06Z, `noisy.npy` 03:24:27Z, `report.json` 03:24:48Z. The report itself carries no timestamps.
  - Colab was unused. No audio, encoder inference or fitting was involved.
- **Pre-run checks.** Before declaration, the worker checked 44,134 bindings, and every joined row passed the exact clean-feature parity gate (all 1,024 target and 13 scalar columns) against the original head inputs.
- **Offline `verify`.** Rebuilt all 5,654 rows and every summary from the saved probabilities without inference, and matched the report hash supplied by the caller.
- **Independent audit (`audit/verify.py`).** A separate script that never imports the worker recomputed 1,120 summaries with `math.fsum` (tolerance 1e-12) and re-hashed all inputs and artifacts. It passed.
- **Freeze check.** `clean-freeze.json` pins the saved clean array.
- **Tests.** 15 synthetic tests pass. Three were added this session: `started.json` plus once-only execution (one test), the failure record, and a wrong declaration hash creating no output.
- **Reviews.** Two reviews (Fable 5.1 protocol and source, both confirmed as `claude-fable-5-1`) were done during the GPT-6.1 Sol build. A Fable 5.1 delta review of the final source returned **CLEAR**, also confirmed as `claude-fable-5-1` from usage metadata.

## Artifacts

All paths are under `work/retained-noise-replay-20260929/`.

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| Declaration | `v1/declaration.json` | `2694474a5784f936cb40fbe937579b3642a94ddea5c0128131d029175155e3ac` |
| Report | `v1/run/report.json` | `ebc29bac8605ff5f7adece44e46f9a8d9fac5aa812a11b6114ea2919b7906aee` |
| Worker | `study.py` | `4250087acdde973184e4b36306cdd6cff5930487f104ef78533292a7854ce27c` |
| Tests | `test_study.py` | `c33613d04e3939ff93c7242493684bedb7be97112d3ed3446e17ed7d3045feb6` |
| Audit script | `audit/verify.py` (not pinned by the declaration) | `d7f7445dbdad39fdb7e81436cec38750ad127ed4fa6b12723cd044ea331d4e2d` |

Logs: `prepare.log`, `run.log`, `verify.log`, `audit.log`. Reviews: `protocol-review.md`, `source-review.md`, `delta-review.md`, `result-review.md`. The result review (Fable 5.1, `claude-fable-5-1`) confirmed every statistical number against `report.json` and found no forbidden claims. It flagged an unsupported run-window timestamp, which is now corrected above from durable records.
