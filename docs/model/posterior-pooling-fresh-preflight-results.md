# Fresh posterior pooling CPU preflight

The fixed posterior acoustic representation passed its small CPU integrity test. This is feasibility and repeatability evidence, not a measured pronunciation improvement. No ratings were read, heads fitted, expert scores predicted, or learner judgments enabled.

The runner made eight real encoder forwards: four predetermined recordings, then all four again. Both the candidate and its fresh padded-window control repeated bit for bit on every recording. A distinct Python process made four more forwards; fresh hard controls matched bit for bit across processes. Independent scalar-state CTC tables, a dense context kernel and sequential float64 acoustic summation reproduced all 37 probe candidate vectors exactly after float32 persistence. The original encoder and processor were shared.

The runner took 7.28 seconds including its checks; the verifier took 7.42 seconds. Their process-lifetime peak memory was 2.79 GB and 2.77 GB respectively. Four recordings cover the shortest, lower-median and longest fitting recordings plus the global longest hardware-only recording; they do not establish reliability or model benefit across the full cohort.

Historical hard vectors differed on the 12 positions in the longest fitting recording, at maximum absolute difference 0.0000019073486328125. These differences are descriptive. The original historical-parity experiment remains failed and preserved; this new route uses fresh controls measured in the same forwards as its candidates.

Astra independently reviewed the exact source/declaration before execution. Root verified all 70 review pins immediately before running, and independently audited all eight saved arrays, hashes, shapes, order, repeats and historical diagnostics afterward. Opus 5.5 reviewed the results and cleared preparation of a separate full extraction declaration. Neither review measures pronunciation accuracy or authorizes training by itself.

Evidence:

- [Frozen protocol](posterior-pooling-fresh-controls-v1.md)
- [Runner report](../../research/audio-head/outputs/multiphone-20260927/posterior-pooling-fresh-controls-preflight-v1/run/report.json), SHA256 bd6fb43cfa8fd88089c02403bf3203c9a1e25a7d1f2a61ad891be9911999db70.
- [Separate-process verification](../../work/core-model-next-method-20260927/fresh-preflight-verification.json), SHA256 8bf83966290bbbddee2073ad3b55f9f324324235f57ca25ce629cf2b68497977.
- [Root artifact audit](../../work/core-model-next-method-20260927/fresh-preflight-root-observation.json), SHA256 9098fab1ec4aeec417f526d6c20078399517b209ad37b10aebcef5c1645af77e.
- [Opus results review](../../work/core-model-next-method-20260927/opus-fresh-results-review.json), SHA256 3d6514a116a4cd4a0dec961338b26f1bfa698aad97dbb582853588883c06ab66.

The next stage extracts paired candidate/control features for all 1,040 child recordings with fixed start/end probes and independent verification. The later comparison must use identical original speaker/word partitions, fitting recipes and strict numerical gates fixed before any fits. This heavily explored cohort supplies development evidence, not independent confirmation. Independent child production/localization, recording-usability and nonspeech evidence remains missing.
