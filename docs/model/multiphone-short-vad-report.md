# Fixed 100 ms versus 250 ms speech segmentation

September 27, 2026. The 100 ms rule retained **17/17 estimated word crops and 23/23 target positions**, versus **12/17 and 18/23** for the original 250 ms rule. Both retained every corpus recording. On the 24 fresh environmental recordings, the shorter rule admitted **two**, versus **one** for the original rule. This is a measured tradeoff, not an unconditional improvement.

The [protocol](multiphone-short-vad-protocol.md) changes only minimum speech duration. Model, probability thresholds, silence handling, padding and runtime stay fixed. The shorter rule was chosen after observing the original crop failures; crop results are development evidence. There was no fitting, duration sweep, pronunciation-head change or learner-feedback enablement.

## Existing speech and known challenges

| Input | 250 ms retained | 100 ms retained |
| --- | ---: | ---: |
| Full corpus recordings | 2,495 / 2,495 | 2,495 / 2,495 |
| Child recordings, ages 6–12 | 1,037 / 1,037 | 1,037 / 1,037 |
| All-age target positions | 14,837 / 14,837 | 14,837 / 14,837 |
| Child target positions | 5,654 / 5,654 | 5,654 / 5,654 |
| Word crops | 12 / 17 | 17 / 17 |
| Crop target positions | 18 / 23 | 23 / 23 |
| Previously observed environmental recordings | 0 / 12 | 0 / 12 |
| Known synthetic negatives | 0 / 3 | 0 / 3 |

These counts are identical for the measured conjunction with the existing phone-evidence gate. All 23 corpus consonants retain their complete support, including all 1,577 rating-0 positions/3,911 votes across ages and 331 positions/532 votes in children. The report preserves all per-phone and age tables. Crop targets span sixteen sounds from five children; no corpus ratings were transferred to crops. Whole-recording retention does not establish speech at every target.

## Fresh environmental extension

The [extension protocol](multiphone-environment-extension-protocol.md) fixes four recordings per category with 24 distinct original source IDs, excluding all twelve prior sources. Selection was metadata-only before audio download or inference. The original fold-two proposal lacked enough distinct helicopter sources; fold four was the first feasible single split. All 24 complete five-second recordings were processed; zero pipeline failures occurred.

| Category | Recordings | 250 ms admitted | 100 ms admitted |
| --- | ---: | ---: | ---: |
| chainsaw | 4 | 0 | 0 |
| crackling_fire | 4 | 0 | 0 |
| dog | 4 | 1 | 1 |
| helicopter | 4 | 0 | 1 |
| rain | 4 | 0 | 0 |
| sea_waves | 4 | 0 | 0 |

Both rules admitted dog recording `4-182395-A-0.wav`. Only the 100 ms rule admitted helicopter recording `4-161579-A-40.wav`. The latter output interval spans samples 49,184–52,704, including the fixed padding. These are model outputs, not human-confirmed speech boundaries.

This study did not run the phone-evidence gate on the fresh recordings. Combined fresh outcomes are therefore unmeasured in this study's report. The separately declared [conditional follow-up](multiphone-short-vad-followup-report.md) subsequently measured the two admitted clips: the helicopter was withheld and the dog remained admitted, giving one combined admission under each rule. The other 22 retain null phone-evidence fields; conjunction is false because VAD is false. Do not describe that unmeasured phone evidence as observed rejection.

Environmental category labels are not speech-detection ground truth and do not guarantee absence of incidental speech. These clips are new to this experiment and source-disjoint from the earlier challenge; overlap with the pretrained detector’s training data is unknown. The counts do not estimate a population false-acceptance rate.

## Evidence and verification

Historical probabilities were reused for all 2,527 previously evaluated recordings/crops. Only 24 new VAD acoustic passes occurred. Both duration rules were applied to identical probabilities and true waveform lengths. Every historical 250 ms decision reproduced before new inference.

- Declaration SHA-256: `a80c2bb6fcd3d7ebfaad62c932a9e402c997710143b6c0f2f14da71b4577818f`.
- Report SHA-256: `936814170ea54b37addb84211b99d80153e53096b6c8892bc1b0b936710e9bae`.
- Extension plan SHA-256: `8c8c7eae446abe6277109335143547d2697726c9078c7d43fca20c88dea0e00f`.
- Selection SHA-256: `4d3e491f53ed3c1d3b59af73ae67dbe3d9d03e0a9305446a1c6a62f6c9597a53`.
- Outputs: `research/audio-head/outputs/multiphone-20260927/short-vad-v1/`.
- Five focused comparison tests and nine acquisition/conversion tests passed.
- Original and converted WAV headers, hashes, exact source exclusions and per-file CC BY attribution were verified.
- A separate process reconstructed every interval, decision and table from saved probabilities and matched the stored report.
- Independent review reproduced all 2,551 probability sequences, both segmentations and 288 retention tables, and verified the fresh selection and all 48 waveform headers/hashes. No blocker remained.

## Decision

Keep both fixed policies and their evidence. The shorter rule repairs the observed crop-retention failure; the conditional follow-up found no additional combined admission on this extension. This supports an explicit research option, not a silent app-default replacement or a claim of equal real-world rejection rates. Naturally spoken isolated words, child SSD, ages 2–5 and unseen-source pronunciation performance still need suitable evidence; learner judgments remain disabled.

The reusable `multiphone_short_vad_filter.py` accepts the same `--report`,
caller-pinned `--sha256` and fresh `--output` arguments as the original filter.
It runs VAD once through the unchanged baseline implementation, then applies
the fixed 100 ms segmentation to the saved probabilities. Passing both checks
preserves the original raw vectors exactly; either rejection produces null
vectors in `finalreport.json`. It never changes the caller's raw report or
historical 250 ms evidence.

Seven focused filter tests passed. Four actual integration checks preserved
real and dog-recording vectors, recovered the exact original BE-crop vector
after the 250 ms filter had withheld it, and withheld the helicopter vectors
despite its positive 100 ms VAD result. This is behavior verification, not
pronunciation evaluation. Evidence:
`outputs/multiphone-20260927/short-filter-integration-v1/verification.json`,
SHA-256 `097f7cfe66f7de0a133a8d5745e46f50e0ed706b20b897646539eee354683341`.
The final independent audit reconstructed all four filter report chains and
both segmentations, including exact score recovery and masking. The combined
focused test run passed 38 tests; no blocker remained.
