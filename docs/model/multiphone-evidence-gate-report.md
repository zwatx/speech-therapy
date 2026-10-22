# Research input-evidence results

September 27, 2026. The fixed research-only policy withheld all three previously known nonspeech examples and retained all 2,495 eligible author-training recordings. No fitting or acoustic model inference occurred. These are exploratory corpus-retention results, not validation of voice activity, prompt match, or pronunciation correctness.

The policy rejects constant PCM waveforms or a greedy CTC path containing no non-special phone token. Its declaration is [the protocol](multiphone-evidence-gate-protocol.md). The historical adapter and model bundles remain unchanged.

| Population | Retained clips / speakers / positions | Rating-0 votes / positions | Below-2 votes / positions | Withheld |
| --- | ---: | ---: | ---: | ---: |
| All ages | 2495 / 125 / 14837 | 3911 / 1577 | 5449 / 2654 | 0 |
| Children 6–12 | 1037 / 52 / 5654 | 532 / 331 | 1237 / 805 | 0 |

Version 3 supersedes the initial v1 report and intermediate v2 integrity check. Review found that a malformed raw report could omit its posterior hash or combine individually hashed CTC artifacts from different recordings. The filter now requires all three CTC artifacts and verifies their runtime, job, waveform, frame-count and posterior linkage before producing output; the exact recipe and loader sources are pinned too. Original v1/v2 reports and matching source snapshots remain preserved in their output directories. All retention counts and decisions are identical across versions.

A position with any relevant rating vote counts once in the corresponding position column. Votes retain all five raters and their disagreements. All counts below were retained; withheld clips, speakers, positions, and votes are zero for every phone in both populations. Speakers and clips can appear in several phone rows and must not be summed across phones.

| Phone | All-age clips / speakers / positions | All-age rating-0 votes / positions | All-age below-2 votes / positions | Child clips / speakers / positions | Child rating-0 votes / positions | Child below-2 votes / positions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 660 / 124 / 660 | 74 / 33 | 79 / 36 | 236 / 51 / 236 | 13 / 9 | 16 / 10 |
| CH | 157 / 83 / 157 | 53 / 18 | 65 / 26 | 42 / 29 / 42 | 8 / 3 | 10 / 4 |
| D | 835 / 125 / 835 | 267 / 114 | 327 / 158 | 322 / 52 / 322 | 37 / 29 | 64 / 47 |
| DH | 955 / 125 / 955 | 268 / 136 | 463 / 270 | 333 / 52 / 333 | 29 / 19 | 126 / 96 |
| F | 605 / 124 / 605 | 105 / 43 | 111 / 49 | 191 / 51 / 191 | 5 / 5 | 7 / 7 |
| G | 491 / 125 / 491 | 58 / 23 | 65 / 27 | 195 / 52 / 195 | 1 / 1 | 3 / 3 |
| HH | 637 / 125 / 637 | 72 / 34 | 75 / 36 | 237 / 52 / 237 | 7 / 6 | 9 / 7 |
| JH | 173 / 89 / 173 | 65 / 23 | 69 / 25 | 76 / 31 / 76 | 13 / 5 | 14 / 5 |
| K | 827 / 125 / 827 | 175 / 67 | 189 / 78 | 330 / 52 / 330 | 9 / 4 | 16 / 9 |
| L | 943 / 125 / 943 | 363 / 152 | 408 / 181 | 357 / 52 / 357 | 60 / 38 | 76 / 48 |
| M | 828 / 124 / 828 | 176 / 79 | 256 / 138 | 341 / 51 / 341 | 32 / 23 | 67 / 52 |
| N | 960 / 125 / 960 | 254 / 107 | 269 / 117 | 402 / 52 / 402 | 52 / 32 | 61 / 37 |
| NG | 424 / 121 / 424 | 193 / 54 | 210 / 66 | 119 / 48 / 119 | 10 / 6 | 18 / 10 |
| P | 482 / 123 / 482 | 92 / 44 | 114 / 51 | 153 / 50 / 153 | 15 / 7 | 25 / 11 |
| R | 766 / 124 / 766 | 369 / 136 | 406 / 155 | 304 / 51 / 304 | 60 / 35 | 82 / 46 |
| S | 941 / 125 / 941 | 216 / 90 | 242 / 103 | 378 / 52 / 378 | 35 / 20 | 45 / 26 |
| SH | 314 / 113 / 314 | 126 / 48 | 145 / 57 | 134 / 49 / 134 | 18 / 9 | 25 / 10 |
| T | 810 / 125 / 810 | 201 / 74 | 241 / 105 | 378 / 52 / 378 | 27 / 15 | 46 / 30 |
| TH | 260 / 109 / 260 | 157 / 55 | 289 / 151 | 75 / 40 / 75 | 19 / 12 | 94 / 60 |
| V | 590 / 122 / 590 | 142 / 55 | 341 / 201 | 200 / 49 / 200 | 17 / 12 | 93 / 63 |
| W | 861 / 124 / 861 | 177 / 59 | 184 / 65 | 323 / 51 / 323 | 18 / 8 | 22 / 11 |
| Y | 477 / 122 / 477 | 54 / 19 | 62 / 24 | 190 / 49 / 190 | 9 / 3 | 15 / 6 |
| Z | 841 / 125 / 841 | 254 / 114 | 839 / 535 | 338 / 52 / 338 | 38 / 30 | 303 / 207 |

The saved zero, Gaussian-noise and 440 Hz tone reports all abstain and expose `null` target probabilities. The original real-recording report passes with seven recognized phone tokens and preserves its probabilities exactly. These negatives motivated the policy and are not independent test cases. Original raw diagnostic files still contain unfiltered ratings; consumers must use the separate gated result.

Every original WAV and posterior file was read and checked against its recorded SHA-256, with waveform geometry, posterior normalization, author-training membership and cache bindings checked. The JSON retains all 2,495 decisions and waveform/posterior bindings, overall counts and all 46 population/phone tables. The source, policy declaration and metadata were also pinned. No author-test recording was read.

Fourteen focused tests pass across the gate and evaluator. They cover constant and quiet waveforms, alternative phones, special-token decoding, malformed posteriors, changed waveform/posterior bytes, incorrect hashes and bindings, path escapes, changed reports, omitted CTC artifact hashes, mismatched waveform/job/runtime links, vote-versus-position counting, and withheld-score removal. A separate NumPy/standard-WAV reconstruction checked all 2,495 original decisions and all 48 overall/per-phone population tables; v3 decisions, tables and input hashes match that audited v1 result exactly.

Acceptance is not a validated speech detector: a recognizer can hallucinate phones on environmental sounds or miss a child’s genuine production. The corpus contains ages 6–12 but no established SSD cohort; long read utterances also differ from the app’s short prompts. Broader independent environmental negatives and genuine child-error recordings remain necessary.

[Complete report](../../research/audio-head/outputs/multiphone-20260927/evidence-gate-v3/report.json). SHA-256: `82c16b2a01b552b5f1382a44a6b939a011d1d44d131b076a149741ad7bba18d9`.

Reproduce into a fresh ignored output directory from `research/audio-head`:

```sh
.venv/bin/python -m unittest test_multiphone_evidence_gate test_multiphone_evidence_gate_evaluate
.venv/bin/python multiphone_evidence_gate_evaluate.py --output outputs/multiphone-20260927/evidence-gate-replay
```
