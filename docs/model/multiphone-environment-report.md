# ESC-10 environmental challenge results

Completed September 27, 2026. **9/12 abstained,
3/12 accepted, 0 pipeline failures.**
Acceptance means recognized-phone evidence under the fixed gate, not verified
speech, prompt match, or correct pronunciation. The environmental labels are
not VAD ground truth and do not establish absence of incidental speech.

The [predeclared protocol](multiphone-environment-protocol.md) selected two
lexicographically first distinct source recordings from each of six categories,
ESC-10 only, fold 1. No selection changed after inference. All clips retained
their complete five seconds; conversion used mono 16-kHz PCM16 without trimming
or amplitude normalization. The unchanged raw adapter ran once per clip on CPU
with two threads, BALL /B AO1 L/, target B, and `unweighted-all-age`.
The pinned hardened evidence gate filtered each completed report. No training,
threshold adjustment, feedback, cloud use, or promotion occurred.

| Category | Clips | Accepted | Abstained | Pipeline failures |
| --- | ---: | ---: | ---: | ---: |
| dog | 2 | 2 | 0 | 0 |
| rain | 2 | 0 | 2 | 0 |
| sea_waves | 2 | 0 | 2 | 0 |
| crackling_fire | 2 | 1 | 1 | 0 |
| helicopter | 2 | 0 | 2 | 0 |
| chainsaw | 2 | 0 | 2 | 0 |

Recognized tokens below are greedy CTC outputs excluding special token IDs
0–3. They are model outputs, not manual transcripts. Every abstention had
`no-recognized-phone-evidence`; no category received a correctness label.

| Filename | Category | Gate outcome | Token count | Recognized tokens |
| --- | --- | --- | ---: | --- |
| 1-100032-A-0.wav | dog | accepted | 2 | p a |
| 1-110389-A-0.wav | dog | accepted | 1 | a |
| 1-17367-A-10.wav | rain | abstained | 0 | none |
| 1-21189-A-10.wav | rain | abstained | 0 | none |
| 1-28135-A-11.wav | sea_waves | abstained | 0 | none |
| 1-39901-A-11.wav | sea_waves | abstained | 0 | none |
| 1-17150-A-12.wav | crackling_fire | abstained | 0 | none |
| 1-17565-A-12.wav | crackling_fire | accepted | 2 | k a |
| 1-172649-A-40.wav | helicopter | abstained | 0 | none |
| 1-181071-A-40.wav | helicopter | abstained | 0 | none |
| 1-116765-A-41.wav | chainsaw | abstained | 0 | none |
| 1-19898-A-41.wav | chainsaw | abstained | 0 | none |

## Interpretation

The gate withholds some environmental inputs but also admits other environmental
recordings. It must remain a necessary input check, with no claim of validated
speech detection or clinical safety. These 12 deliberately small fixed examples
do not estimate population false-acceptance rates, microphone robustness,
child-speech retention, or child SSD performance. Do not tune a threshold on
these observed outcomes and then present them as independent validation.

## Reproducibility and attribution

- Source: [Karol J. Piczak's ESC-50 repository](https://github.com/karolpiczak/ESC-50/tree/33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6), commit `33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6`.
- ESC-10 is [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/); the complete source LICENSE, README and each original Freesound contributor attribution are retained in the ignored output plan. Credit Karol J. Piczak, *ESC: Dataset for Environmental Sound Classification*, ACM Multimedia 2015, and those contributors. The only audio modification is the documented resampling/PCM conversion.
- Output directory: `research/audio-head/outputs/multiphone-20260927/environment-v1/`.
- Plan SHA-256: `1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9`.
- Result SHA-256: `a2bec929eacd4978b36c5c15b2eddc73f9c83a24d6127fb7d4f78e3857e0b9a9`.
- Gate source SHA-256: `831081804ed7564f7afe2a61f1346d09d338be97317f113f7dbe4a49607710ea`.
- Converter: `ffmpeg version 8.1.2 Copyright (c) 2000-2026 the FFmpeg developers`; exact per-file commands and original/converted hashes are in `plan.json`.
- `multiphone_environment_challenge.py` implements selection, acquisition, declaration and inference; `multiphone_environment_report.py` verifies bound outputs and renders this report.

Verified: four focused selection/conversion/error tests; all 12 original and
converted WAV headers/durations; pinned input hashes; all saved raw artifact
hashes; zero model fetch attempts; exact selected clip order; category totals;
CTC token counts; CPU/head/prompt identity. The report check performs no new
inference. The broader app test suite was not run because only isolated research
scripts and documentation were added.
