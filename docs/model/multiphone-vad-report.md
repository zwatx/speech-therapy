# Fixed speech-detector comparison results

Completed September 27, 2026. The unchanged pretrained Silero candidate retained **all 2,495 corpus recordings** and withheld **all 12 known environmental recordings and all three synthetic negatives**. The combined phone-evidence and speech-detector rule has the same outcomes in this study. No training, threshold adjustment, pronunciation-model replacement or learner-feedback enablement occurred.

The previous phone-evidence rule alone admitted two dog recordings and one crackling-fire recording. The fixed candidate closes those three known development-challenge failures. This is evidence for an additional research input check; it is not a measured real-world speech-detection accuracy rate.

## Whole-recording retention

Every eligible position in a retained recording remains available to the research pipeline. This does not establish that speech is present at each particular target position. All three rules retain the same corpus support:

| Population | Recordings | Speakers | Positions | Rating-0 positions / votes | Below-2 positions / votes | Withheld recordings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All ages | 2,495 | 125 | 14,837 | 1,577 / 3,911 | 2,654 / 5,449 | 0 |
| Children ages 6–12 | 1,037 | 52 | 5,654 | 331 / 532 | 805 / 1,237 | 0 |

No corpus recording was withheld, so there are no withheld-clip support records to enumerate. The JSON report retains all three rules, every clip and the empty withheld sets explicitly.

| Phone | All-age positions retained / total | Child positions retained / total | Child rating-0 positions / votes retained |
| --- | ---: | ---: | ---: |
| B | 660 / 660 | 236 / 236 | 9 / 13 |
| CH | 157 / 157 | 42 / 42 | 3 / 8 |
| D | 835 / 835 | 322 / 322 | 29 / 37 |
| DH | 955 / 955 | 333 / 333 | 19 / 29 |
| F | 605 / 605 | 191 / 191 | 5 / 5 |
| G | 491 / 491 | 195 / 195 | 1 / 1 |
| HH | 637 / 637 | 237 / 237 | 6 / 7 |
| JH | 173 / 173 | 76 / 76 | 5 / 13 |
| K | 827 / 827 | 330 / 330 | 4 / 9 |
| L | 943 / 943 | 357 / 357 | 38 / 60 |
| M | 828 / 828 | 341 / 341 | 23 / 32 |
| N | 960 / 960 | 402 / 402 | 32 / 52 |
| NG | 424 / 424 | 119 / 119 | 6 / 10 |
| P | 482 / 482 | 153 / 153 | 7 / 15 |
| R | 766 / 766 | 304 / 304 | 35 / 60 |
| S | 941 / 941 | 378 / 378 | 20 / 35 |
| SH | 314 / 314 | 134 / 134 | 9 / 18 |
| T | 810 / 810 | 378 / 378 | 15 / 27 |
| TH | 260 / 260 | 75 / 75 | 12 / 19 |
| V | 590 / 590 | 200 / 200 | 12 / 17 |
| W | 861 / 861 | 323 / 323 | 8 / 18 |
| Y | 477 / 477 | 190 / 190 | 3 / 9 |
| Z | 841 / 841 | 338 / 338 | 30 / 38 |

## Known development challenges

| Category | Recordings | Previous gate retained | VAD retained | Combined retained |
| --- | ---: | ---: | ---: | ---: |
| chainsaw | 2 | 0 | 0 | 0 |
| crackling_fire | 2 | 1 | 0 | 0 |
| dog | 2 | 2 | 0 | 0 |
| helicopter | 2 | 0 | 0 | 0 |
| rain | 2 | 0 | 0 | 0 |
| sea_waves | 2 | 0 | 0 | 0 |
| gaussian | 1 | 0 | 0 | 0 |
| sine440 | 1 | 0 | 0 | 0 |
| zero | 1 | 0 | 0 | 0 |

There were **zero pipeline failures**. These environmental clips were already observed before choosing the candidate. Category labels do not guarantee absence of incidental speech, and the known synthetic negatives are not an independent test set. No threshold was selected using these outcomes.

## Reproducibility

The [predeclared protocol](multiphone-vad-protocol.md) fixes the upstream model and utility at commit `5cd7945676eb32225748052e2e6a0580e4686a08`, CPU with two threads, 16 kHz audio, and the official default segmentation settings. The model, MIT license, source, input identities, source code and runtime are pinned in the declaration. The original corpus waveform bytes and model bundles were unchanged.

- Declaration SHA-256: `4fb15cd0631c0d727da6d1c3356537f03a521e21a1329e27e3a15c5eb420ed93`.
- Result SHA-256: `e343ea03db257fbffd28fa10da8811d7e53e4ef5328842379d32fb4699b9b8c5`.
- Model SHA-256: `e1122837f4154c511485fe0b9c64455f7b929c96fbb8d79fbdb336383ebd3720`.
- Evidence: `research/audio-head/outputs/multiphone-20260927/vad-v1/`.
- Seven focused tests passed before execution, including frame padding, state reset, invalid probabilities, short inputs, record tampering and interval bounds.
- All 2,510 per-recording outputs were saved. A separate process reconstructed intervals, all three decisions and every table from recorded probabilities and verified the saved report.
- After the full run, the first recording was inferred again: probabilities and intervals matched exactly, verifying state reset across intervening recordings.
- Independent review verified all waveform headers and artifact bindings, 326,309 saved probabilities, all decisions and 144 retention tables; no blocker remained.

## Decision and next step

Retain this fixed candidate for research-only combined filtering. Its measured benefit is withholding three previously admitted environmental examples without discarding any recording in this particular corpus. Do not infer improved pronunciation accuracy, validated prompt matching or per-phone speech presence from that result.

`multiphone_vad_filter.py` applies the fixed conjunction to a caller-hashed raw
research report. Consume its `finalreport.json`: all target probabilities are
null when either check withholds the recording. Intermediate/raw diagnostic
files may still contain scores. Seven focused filter tests passed; actual
checks preserved the real-recording vectors exactly and nulled every vector for
silence, a dog recording and a fire recording. The latter two passed the old
gate, verifying the added rejection path. Original raw reports were unchanged.
Evidence is retained in `outputs/multiphone-20260927/vad-filter-verification-v1/`.

The subsequent [frozen short-word check](multiphone-vad-crop-report.md) retained
only 12 of 17 estimated word crops, versus all five original recordings. This
is a material limitation: keep the combined filter an explicit research option,
not the default for short practice words. Ages 2–5, child SSD, new microphones
and independent short-word recordings remain unsupported. Upstream pretraining
overlap with these datasets is not established. A separately declared
short-speech policy and fresh environmental checks are the next evaluations.
Learner pronunciation judgments remain disabled.
