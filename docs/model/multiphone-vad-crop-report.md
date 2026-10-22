# Frozen speech-detector short-word sensitivity results

September 27, 2026. With exactly the same settings that retained all 2,495 full corpus recordings, the candidate retained **12/17 short word crops and 18/23 target positions**. The phone-evidence check alone retained all 17 crops and 23 positions. All five original recordings passed the full-recording VAD check. This is a material limitation for the proposed short-word practice flow.

The [fixed protocol](multiphone-vad-crop-protocol.md) includes every previously saved crop, with no recropping, changed audio, additional padding or parameter adjustment. The 17 crops cover 16 sounds across five children. Boundaries were estimated from canonical alignment; these are not natural isolated-word recordings or human-verified articulation labels.

| Child age | Source recording | Word | Duration (s) | Target phones | Phone gate | VAD / combined |
| ---: | --- | --- | ---: | --- | --- | --- |
| 6 | 001040136 | HE | 0.325 | HH | Retained | Withheld |
| 6 | 001040136 | WANT | 0.505 | N, W | Retained | Retained |
| 6 | 001040136 | BE | 0.285 | B | Retained | Withheld |
| 6 | 001040136 | SINGER | 0.645 | S, NG | Retained | Retained |
| 8 | 010920025 | TIM | 0.565 | T | Retained | Retained |
| 8 | 010920025 | IS | 0.365 | Z | Retained | Withheld |
| 8 | 010920025 | FRIEND | 0.505 | D | Retained | Retained |
| 8 | 010920025 | GERMAN | 0.605 | JH | Retained | Retained |
| 10 | 030830135 | AND | 0.445 | D, N | Retained | Retained |
| 10 | 030830135 | THERE | 0.545 | R, DH | Retained | Retained |
| 11 | 054140104 | NEVER | 0.465 | N, V | Retained | Retained |
| 11 | 054140104 | PART | 0.465 | P, T | Retained | Retained |
| 11 | 054140104 | WITH | 0.385 | W | Retained | Retained |
| 11 | 054140104 | THEM | 0.445 | M | Retained | Retained |
| 12 | 064010173 | AFTER | 0.545 | F | Retained | Retained |
| 12 | 064010173 | WENT | 0.425 | W | Retained | Withheld |
| 12 | 064010173 | BY | 0.285 | B | Retained | Withheld |

## Rejected cases and implication

The rejected crops were HE, BE, IS, WENT and BY, covering HH, B, Z, W and B respectively. Every one had at least one frame at or above the fixed 0.5 speech threshold. From that first qualifying frame to the actual crop end, only 133, 157, 237, 233 and 125 ms remained respectively. Thus none could satisfy the unchanged requirement for a segment longer than 250 ms, even if every remaining sample were classified as speech. No counterfactual threshold or duration sweep was run.

This identifies a duration/context failure mode; it does not establish that the crops contain complete valid target productions. Do not use this fixed combined policy as the default for short practice words. It remains an explicit research option. A next experiment can compare a separately declared short-speech rule, with fresh environmental checks and no claim that these observed crops provide independent validation. Learner pronunciation judgments remain disabled.

That subsequent [100 ms comparison](multiphone-short-vad-report.md) is now
complete: all seventeen observed crops were retained, and the conditional
combined check admitted one of 24 fresh environmental recordings under either
duration rule. These later results do not alter the frozen 250 ms findings here.

## Verification

The run processed all 17 declared crops with zero pipeline failures. All exact original sample slices and cached CTC hashes were verified before inference. The model, utility, runtime, parameters and original decisions match the approved full-recording study. No additional CTC or pronunciation-head inference was performed; no ratings were transferred to crops.

A separate process reconstructed every interval and decision from saved probabilities and verified the stored report. The shared model-state, frame-padding and interval-validation helpers were reused without changes.

- Declaration SHA-256: `e39934ee868ea82f5cabab7353d7125384ac199f36c6576c85f4ad2951b79276`.
- Result SHA-256: `9b7af6bffa4c61753bdc19a2c907ef957f616a21d25402557f6beaa05a56e162`.
- Evidence: `research/audio-head/outputs/multiphone-20260927/vad-crops-v1/`.
- Original crop report SHA-256: `6b3df8d70231cd2ee23f3c79dfb645524d5ad94ff4167f8e8a446de4a21b219e`.
