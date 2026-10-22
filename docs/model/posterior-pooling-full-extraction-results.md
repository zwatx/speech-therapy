# Full posterior pooling extraction

The source-reviewed fresh-control CPU extraction and separate-process verification passed on all 1,040 recordings and 9,891 positions from 52 children ages 6–12, covering all 23 supported consonants. This supplies paired features for the next model comparison. No ratings were read during extraction, heads fitted, pronunciation accuracy measured, or learner judgments enabled.

Four fixed start probes matched the frozen passing preflight bit for bit. Every cohort recording produced both candidate posterior-weighted vectors and fresh original padded-window means from one encoder forward. The four probes matched again when encountered in cohort order and at the end. Exactly 1,048 runner forwards produced two finite float32 matrices of shape (9891,1024), retaining every position and the unchanged 13 scalars and row identities.

The run took 244.43 seconds, including checks. Process-lifetime peak memory was 3.05 GB. A distinct process made four additional forwards and finished in 29.65 seconds, including 19.86 seconds independently replaying every recording's scalar-state CTC tables, full-vocabulary invariants, dense context kernel, occupancies, weight/support/centroid/displacement diagnostics, vector distances and historical differences. It also checked all artifact hashes, matrix slices, row coverage, scalar/reference lineage and repeat relations.

Independent acoustic summation reproduced the 37 fixed probe positions exactly. Fresh hard controls matched across processes bit for bit. The original encoder and processor were shared. Independent acoustic reconstruction covers those 37 positions, not all 9,891; the remaining vectors have full artifact/coverage/diagnostic checks. Total actual forwards were 1,052. Root independently audited every saved cohort array, matrix slice, identity, shape, historical diagnostic and probe equality without additional encoder calls.

Historical hard values differ on 2,094 positions, with maximum absolute difference 0.000022917985916137695. These are descriptive differences with no acceptance threshold or exclusions. Historical compact controls remain descriptive. The fresh paired hard matrix is the acoustic control for later fitting. The old historical-parity preflight remains failed and preserved.

All 61 synthetic checks passed after correcting a test fixture and closing a final artifact-recheck gap before declaration. Astra independently reviewed the exact final code, actual declaration, all 9,891 position identities and 82 textual bindings before execution. Root reverified those bindings before the run and afterward. Actual Opus 5.5 reviewed the completed evidence and cleared preparation of a separate training declaration, with no training execution clearance.

Evidence:

- [Full protocol](posterior-pooling-full-extraction-v1.md).
- [Runner report](../../research/audio-head/outputs/multiphone-20260927/posterior-pooling-full-extraction-v1/run/report.json), SHA256 456802fb6b6519dc170d59a66896a9176ec2af7b5395639fcd383d0ae987bd0a.
- [Separate-process verification](../../work/core-model-next-method-20260927/full-extraction-verification.json), SHA256 6da9d0a19ccfc5431a4dc94908571c0fc1cc96622336f8271e86c8c9580db59b.
- [Root observation](../../work/core-model-next-method-20260927/full-extraction-root-observation.json), SHA256 87a0910fc7791526b588eb466958d448e43ee7c2f11dc257378be340e68e1eae.
- [Opus results review](../../work/core-model-next-method-20260927/opus-full-results-review.json), SHA256 2fb67584d72dd5ee92e33a73173a830d99a2b39da7dd9f9af17efda0877bead2.
- [Prospective model comparison](posterior-pooling-model-comparison-v1.md).

The next comparison trains both acoustic arms on identical original speaker/word partitions and recipes, with the same scalar component. Strict material gains and subgroup safeguards are fixed before fitting. No averaged-seed rescue or historical acoustic-control reuse is permitted. This extensively explored cohort supplies development evidence, not untouched confirmation; independent child production/localization, recording-usability and nonspeech evidence remains missing. The retained research bundle has not been replaced.
