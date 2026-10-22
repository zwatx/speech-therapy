# Full-utterance versus word-context sensitivity

September 26, 2026. The bounded diagnostic completed in 92.1 seconds with
**17/17 word crops and 23/23 target positions** processed successfully. These
positions cover 16 consonants in five previously selected inner-validation
children aged 6, 8, 10, 11 and 12. They are not a new independent cohort.

This checks a concrete app mismatch: native practice presents short words,
whereas the research models were fitted on target positions in full utterances.
It measures changes in predictions, not whether either prediction is correct.

## Fixed method and observed changes

The [protocol](multiphone-word-context-sensitivity-protocol.md) fixes every
target-bearing word before inference. Each crop spans the original estimated
canonical word emissions' convolution support plus 100 ms on each side,
clipped to the recording. The 17 crops are 0.285–0.645 seconds long. Samples
are copied exactly; there is no resampling, fading, gain change, adaptive
widening or replacement of unsuccessful cases.

Both original heads are unchanged. Each shortened waveform receives a new
word-only canonical alignment, 13 scalar features and 1,024 encoder features.
All five full recordings passed the original-pipeline parity checks before
any crop inference. Original posteriors, scalars, windows and vectors match
exactly; the maximum probability difference is 1.87e-9, below the fixed 2e-6
tolerance. No clean human rating is assigned to a crop.

| Head | Mean probability TV | Largest TV | Mean expected-rating change | Argmax changes |
| --- | ---: | ---: | ---: | ---: |
| All-age fitting | 0.108499 | 0.476347 | −0.154843 | 2 / 23 |
| Child-only fitting | 0.055598 | 0.514125 | −0.079834 | 1 / 23 |

TV is half the sum of absolute differences between the three corpus-rating
probabilities. Expected-rating changes use the numeric 0/1/2 rating scale and
are crop minus full recording. Neither measure is pronunciation accuracy.
Both heads initially assign class 2 the highest probability on all 23 positions.
After cropping, the all-age head assigns class 0 on two positions and the child
head on one. No evidence identifies those changes as correct or incorrect.

## Interpretation and verification

The shifts are material for a proposed short-word app. Cropping changes waveform
context, encoder preprocessing, canonical sequence, alignment and utterance
features together. Estimated CTC emissions are not validated word boundaries;
the crop may truncate speech, preserve neighboring speech or retain original
coarticulation. This cannot isolate an encoder-only effect or establish that
these are representative naturally spoken isolated words. The smaller child
mean shift does not establish a better model.

An independent read-only audit rehashed all 454 input/derived bindings, checked
all 17 exact PCM slices and sample ranges, reproduced the five original parity
checks from saved arrays, and recomputed every word, clip and overall probability,
confidence, argmax and alignment-shift summary. All matched; all CTC jobs record
zero network fetches. The audit performed no new model inference.

The [machine-readable report](../../research/audio-head/outputs/multiphone-20260926/word-context-sensitivity-v1/diagnostic/report.json)
retains the complete cases, arrays, waveform identities and per-target outputs.
Report SHA-256:
`6b3df8d70231cd2ee23f3c79dfb645524d5ad94ff4167f8e8a446de4a21b219e`.
Plan SHA-256:
`7c00c70ca2de98624d7e0957ff821059c8f9780feee69cc18b1434b237b50736`.
Completed execution ledger SHA-256:
`ae358074efbab82de55c17a782ab12827e81f44e785a15546c9b4a1eb4b150ac`.

Human listening/boundary review and purpose-collected isolated-word child/SSD
examples remain necessary before using app recordings to make pronunciation
judgments. No label transfer, training, calibration, model selection, new export
or learner-feedback change follows from this diagnostic.
