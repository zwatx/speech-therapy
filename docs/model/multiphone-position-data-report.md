# Complete position-aware research dataset

The new dataset contains **28,227 labeled consonant positions in 2,500
recordings**, including **9,891 positions from 52 children aged 6–12**.
Each occurrence has its own utterance, word and phone index. Repeated sounds
with different ratings now remain distinct. This is verified data preparation;
no model has yet been trained on the expanded set.

The [fixed protocol](multiphone-position-data-protocol.md) preserves the
existing 23 supported consonants, all original speaker assignments and each
fold's fitting/validation membership. It adds 13,390 positions from the same
125 speakers, rather than introducing new independent participants.

| Evidence | Original eligible set | Expanded set |
| --- | ---: | ---: |
| Labeled positions | 14,837 | 28,227 |
| Recordings | 2,495 | 2,500 |
| Child positions, ages 6–12 | 5,654 | 9,891 |
| Child recordings | 1,037 | 1,040 |
| Child rating-0 votes | 532 | 918 |
| Child below-2 votes | 1,237 | 2,004 |

All five rater sequences and published averages were reconciled. Every original
eligible row matches its old phone, word, speaker, age and rating counts,
with its legacy row index retained. Sparse production notes preserve their
literal labels; missing notes remain unknown. None of these changes creates
verified phone timing, an SSD cohort or ages 2–5 coverage.

The actual build verified every selected train WAV against its member in the
pinned source archive, including the five newly included recordings. Format,
sample count, full sample payload and acoustic measurements passed. The
original 2,495 clips' hashes and measurements matched exactly. All folds retain
speaker separation and reject identical waveform hashes crossing a split.

Eleven focused builder tests pass, including differing ratings for repeated
sounds, repeated words, metadata errors, legacy reconciliation, split
membership, tamper detection and failed-run retention. Independent source
review also reconstructed all position labels and original joins. A separate
actual offline run rebuilt cohort, splits and report byte for byte. Independent
[saved-artifact audit](../../work/position-data-audit-20260927/verification.json)
also passed: 2,515 input bindings, every position, all 2,500 waveform payloads
and archive members, 460 split phone-support cells and 46 summary phone tables.

## Saved evidence

- [Plan](../../research/audio-head/outputs/multiphone-20260927/position-data-v1/plan.json): `47c0c094bd6df03912b488db3223c1501404456657df3efa47f9019bdd846e9a`.
- [Verified build report](../../research/audio-head/outputs/multiphone-20260927/position-data-v1/report.json): `49880e24288f09dc135cf6f02286320a057d84f24847e585a6eef5a70e43a0a8`.
- Cohort SHA-256: `3b70d6822cf02e3d4be50274b99853784a454d8fb80f939ade3940cb7b2a6864`.
- Splits SHA-256: `39d05840ce0b8fef1b90a3c90cb45a41f263595c8d1be9ac4b4cc002e98fbcd2`.

The next stage is [position-specific feature extraction](multiphone-position-geometry-protocol.md),
with exact comparison to the old positions before downstream fitting. Source,
tests and this build's protocol are pinned; the old datasets and models remain
reproducible. No author-test score objects or WAV payloads were opened, no
training or Colab allocation occurred, and learner judgments remain disabled.
Broad app tests were not run because this work is isolated research data preparation.
