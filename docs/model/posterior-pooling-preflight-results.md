# Posterior pooling preflight: historical parity failure

The fixed CPU preflight **failed** its historical exact-match gate. It provides no pronunciation accuracy result and does not clear a full extraction or training study. The retained model is unchanged.

The candidate replaces a single estimated canonical window with a posterior-weighted average of plausible canonical locations. The encoder, canonical mapping and two-frame context rule were fixed before data inspection. These locations remain transcript-conditioned hypotheses, not observed phone boundaries or produced-phone labels.

Actual Opus 5.5 independently cleared the [source and declaration](../../work/core-model-next-method-20260927/opus-preflight-source-review.json) for the small CPU preflight only. The frozen [plan](../../research/audio-head/outputs/multiphone-20260927/posterior-pooling-preflight-v1/plan.json) selected three fitting recordings by duration and the cohort's longest recording as a hardware-only probe. The latter is outside the fitting membership.

| Recording | Role | Persisted positions | Historical hard means |
| --- | --- | ---: | --- |
| 000010168 | Shortest fitting recording | 1 | Bit exact |
| 000560117 | Global longest; hardware only | 16 | Bit exact |
| 014190030 | Lower-median fitting recording | 8 | Bit exact |
| 001450051 | Longest fitting recording | 0 | Failed; maximum absolute difference 0.0000019073486328125 |

The process exited with an error after four encoder forwards and 2.79 seconds of measured run time. The planned start/end repeats were not reached. Three partial artifacts and the [failure record](../../research/audio-head/outputs/multiphone-20260927/posterior-pooling-preflight-v1/run/failure.json) are preserved; there is no successful final freeze.

Root independently checked the three artifacts' identities, hashes, shapes and exact historical control values, and replayed their CTC and weighting diagnostics using a scalar-state recurrence and a dense kernel. This replay used no additional encoder forwards and did not independently reconstruct candidate vectors. See the [observation](../../work/core-model-next-method-20260927/preflight-failure-root-observation.json). Source, declaration and model hashes remained unchanged. No ratings were read and no fitting or accuracy scoring occurred.

The small numerical discrepancy prevents reuse of the historical compact control under this experiment's rules. It does not identify the discrepancy's cause or show that posterior pooling helps or harms pronunciation prediction. The failed route remains closed: no tolerance relaxation, example exclusion or implicit restart.

A possible next route would extract candidate and fresh hard-control features in the same forwards, require exact repeatability, and fit matching controls under identical partitions and training rules. That requires a separate protocol, declaration and independent review. Historical control comparisons would be descriptive. Independent child production and localization evidence would still be needed before learner-facing claims.
