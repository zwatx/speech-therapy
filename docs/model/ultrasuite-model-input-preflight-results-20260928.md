# UltraSuite model inputs and real feature preflight

All **518 recordings** have been resampled in full and independently checked.
There are **515 input-ready recordings and 786 target items**. Three recordings
with previously identified manual-reference geometry anomalies remain unresolved,
with all six affected items and their audio retained. All 792 original item identities
and 1152 rating-row metadata records remain represented.

The actual acoustic-model preflight passed on the fixed shortest, lower-median and
longest ready recordings, plus one repeat of the shortest. Both recordings within
the original resource limit produced features byte-for-byte identical to the frozen
occurrence adapter. The shortest repeat produced identical q8 posteriors, hidden
states and features. The 39.8-second recording ran intact under the expanded bound.

| Recording | Original duration | Derived samples | CTC frames | Observed checks |
| --- | ---: | ---: | ---: | --- |
| UXSSD 02M-Post-013A | 1.811 s | 28,979 | 90 | Exact frozen-feature parity; exact repeat |
| UXSSD 04M-BL1-138A | 8.452 s | 135,234 | 422 | Exact frozen-feature parity |
| UXSSD 06M-Post-007A | 39.845 s | 637,528 | 1,992 | Complete signal, finite features, expanded bound |

The preflight took **21.75 seconds** on this Mac, including loading, integrity
checks, q8 extraction, the repeat and full-precision feature extraction. This is
not a full-corpus runtime guarantee or a Mac-versus-GPU benchmark. The longest
recording is under age six and was used only for acoustic extraction, without
an age-ineligible rating prediction.

## Opus 5.5 and verification

Actual Claude Code calls used `claude-opus-5-5` through the configured Claude Max
account. Call 31 authored the preparation implementation, tests and protocol.
Its original files and model-identity receipt are preserved. Root added strict
RIFF/container and exact PCM-header checks during integration. Independent
GPT-6 Astra reviews checked the actual preparation and feature declarations before
their respective runs. The retired, unexecuted preparation declaration remains
preserved with its source and review finding.

Call 32 proposed the prospective ordinal evaluation design. Its useful core is
ranking the frozen head's native expected score against original 1–5 clinical
ratings, with a fixed CTC confidence control, first-presentation handling and
comparisons within child and target phone. Root preserved the response and recorded
corrections to its unresolved-item sensitivity, confounding claims, sign-flip
interpretation and repeat handling. It is a proposal, not an executed or fully
adopted evaluation protocol.

- 15 preparation tests, four feature-bridge tests and three Node tests passed.
- Independent reviewers verified all 527 preparation and 1087 feature declaration
  bindings. Root independently reconstructed every resampled waveform byte from
  its original RIFF payload, every prompt and all 792 target links, retaining all rows.
- After the preflight, root rechecked 1089 input/declaration/review bindings, nine
  derived artifacts, posterior normalization, feature shapes/targets and shortest
  q8 repeat bytes. Hidden frames were not retained or re-forwarded by that checker;
  their repeat and short-feature parity passed the actual reviewed runner's assertions.

Signal conversion is PCM16/32768 to float64, fixed 320/441 polyphase resampling and
little-endian float32 output. There is no trimming, clipping or denoising. Source
files remain unchanged. The feature recipe remains raw 1024-column full-precision
phonetic hidden-state means plus 13 original q8 CTC statistics. Only resource bounds
expand from 30 to 60 seconds and 1500 to 3000 frames; the checkpoints remain distinct.

## Limits and next step

Canonical mappings across dialects and forced CTC locations remain hypotheses.
The [provider paper](https://arxiv.org/html/2103.00324v1) describes pre-vocalic /r/
and clinical 1–5 ratings; it does not turn canonical inputs into observed production
transcripts. This corpus supplies narrow /g/, /k/ and /r/ ratings, with ages 11–12
absent and child/rater confounding.

**No head prediction, individual grade comparison, fitting, accuracy improvement,
clinical validity or learner-feedback eligibility was established here.** The retained
ages 6–12 model is unchanged. Next is a separately declared complete extraction and
frozen-head ordinal check. Actual session identifiers include underscores; a full
worker must preserve those without changing this frozen three-recording preflight.

Colab's fresh read-only usage check reported **299.97 units remaining, zero active
assignments and zero usage rate**. This preflight allocated no Colab compute.

Evidence is in `work/ultrasuite-model-transfer-20260928/`: Opus originals/receipts,
declarations/reviews, `prepared/metadata.json`, independent preparation verification,
`feature-preflight/result.json`, independent preflight verification and preserved
ordinal-protocol proposal/assessment.

Preparation metadata SHA-256:
`a9ad39c2c6ab2374e1e55fd753141fd91baa3392bb9fd20aec4e6985a25542a4`.
Feature-preflight result SHA-256:
`5da8a2dd6fa7da819613b4e3b0db5dcf63f793ea1b1b18cfb8c7b7f1b65e38da`.
