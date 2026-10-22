# Full phonetic vectors for all consonant occurrences

The research feature set now covers **28,227 positions in 2,500 recordings**,
including **9,891 positions from children ages 6–12**. Each occurrence has its
own 1,024-value acoustic vector and the same thirteen recognizer-confidence
features used by the existing research heads. This adds 13,390 usable positions
without adding speakers or establishing a model-quality improvement.

The [fixed protocol](multiphone-position-phonetic-protocol.md) retained the
original full-precision phonetic encoder, local CPU float32 eager execution,
two threads, preprocessing and estimated pooling windows. It re-extracted
2,262 recordings containing added positions, reused 238 complete old recordings,
and made one separately saved repeat pass for the predeclared recording
`000010035`. All 14,837 original target vectors and all 2,495 original
whole-recording vectors match exactly. The separate repeat also matches exactly.

The output contains a 28,227 × 1,024 target matrix and a 28,227 × 1,037 combined
matrix. Occurrence identities, word/phone indices, canonical positions, window
bindings and per-recording vectors are retained. The pooling windows remain
unvalidated forced-canonical estimates, and contextual vectors contain information
from the surrounding recording. Corpus ratings are not produced-phone labels.

Nine focused extraction tests pass, along with 28 related position-data,
geometry and training tests. Independent source review passed before execution.
The offline verifier reconstructed both matrices from saved units and checked
all original-vector joins, the separate repeat, input hashes and source bindings
without new encoder inference. Independent saved-artifact review also passed: all 10,028 input bindings,
2,500 units, vector/matrix identities, the repeat and all 46 phone-support cells.
The audit record is `work/position-phonetic-audit-20260927/verification.json`
(SHA-256 `0c7de5f7c93c377f4004dec942820a8065ef005af6491399fc5d6b96698f6cf7`).

## Evidence

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/position-phonetic-v1/plan.json): `b3f1884a54b1fa25777eb9578155b9923eed9ce61ff1762e05301f6211c7f29c`.
- [Complete export](../../research/audio-head/outputs/multiphone-20260927/position-phonetic-v1/report.json): `80a0dd901f026deebd74ea9fb66d234f14e80ca44d03ab8c0816e0d8494341be`.
- Target matrix SHA-256: `9a7725740ac9a41b2f4cde8b943a87e4ee1afbbc64646f7ead5e0213144684bc`.
- Combined matrix SHA-256: `8de5f3261511ca197b846098eb6e17667cadf2eaefb9c0e9e436f85fe3278e24`.
- [Dataset/audio verification](multiphone-position-data-report.md) and [geometry/scalar verification](multiphone-position-geometry-report.md).

The [fixed original-versus-expanded training comparison](multiphone-position-training-report.md)
is now complete, with mixed results and no model promotion.
No encoder weights changed, no author-test inference or Colab allocation occurred,
and learner feedback remains disabled. App checks were not run for this isolated
research extraction.
