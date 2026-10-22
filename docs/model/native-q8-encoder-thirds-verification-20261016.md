# Native q8 encoder diagnostic, October 16

The bounded diagnostic completed successfully. The q8 model remains withheld: successful instrumentation does not resolve its numerical mismatch or qualify it for learner feedback.

Two fresh iOS simulator calls used the unchanged periodic-ramp and impulse controls, each containing 1,600 samples and four frames. Two saved, normally closed Mac calls supplied the comparison. There were no new Mac forwards, reference forwards, conversions or compiler invocations. All sixteen checks preserving prior final outputs and encoder endpoints were byte exact.

The periodic ramp matched byte for byte at every measured internal anchor and both final outputs. The impulse matched at encoder entry, then showed these differences:

| Measured output | Maximum absolute difference | Mean absolute difference |
| --- | ---: | ---: |
| Block 7 residual | 0.000003814697 | 0.000000098633 |
| Block 15 residual | 0.000015258789 | 0.000001095406 |
| Final encoder anchor | 0.070645154 | 0.003212179 |
| Final logits | 0.077786446 | 0.028665909 |
| Final log probabilities | 0.115947723 | 0.036985950 |

“FirstEncoderThird” names the first measured byte variation between encoder entry and block 7. It does not identify a faulty operator, locate the first tolerance failure, or establish why the small early differences become larger later. Internal differences are observations. The impulse's final outputs still fail the unchanged maximum/mean budgets, even though their frame choices and collapsed token sequences match. The earlier 22-of-27 withheld result is unchanged; this diagnostic did not repeat or qualify that full suite.

The workflow completed in 59.156 seconds, with native observation in 5.936 seconds and comparison in 14.380 seconds. A separate independent numerical auditor completed in 19.064 seconds and reconciled all sixteen preservation checks, 24 arrays, 312,320 array bytes and 34 output names. Native registration, readiness, bound exit and fresh absence were verified. Five real provisional startup observations were reconciled with the later process identity. Recorded signals, cleanup errors and owned process remnants were empty. The dedicated iOS 26.5 simulator was available and shut down before and after. Sampled native process RSS reached 964,192 KiB; this is not a continuous peak or app/phone performance measurement.

Earlier failed execution and freeze attempts remain failed. Seven inactive historical tool attestations are explicitly separated from current dependencies; their old evidence was not rewritten. The current source freeze contains 3,677 bindings, and the independent audit checks 3,760 file bindings.

Those 3,760 audit entries describe a checked snapshot: 3,759 remain unchanged, while the auditor's own initially empty output log receives its final report after that check. Final aggregation pins the completed log separately and verifies that its entire JSON object equals the audit report's prescribed projection. It preserves the original snapshot and does not claim that all 3,760 snapshot entries equal their post-exit bytes.

The evidence is in `work/native-q8-encoder-thirds-reobservation-v6-20261016/`: `ROOT-TERMINAL.json`, `ROOT-AUDIT.json`, `compare/comparison.json` and independent `RESULT-REVIEW.md`. The latter is SHA-256 `198d43ee8f51fe59e6e445248db888975f6e0f65b79b2dd05bafa298407c1c1e`; its verdict is clear for this diagnostic interpretation only. No app, clinical or corrective-feedback eligibility follows.

The next model investigation should distinguish later encoder accumulation from the final normalization boundary before attributing a cause. The separate full-precision hidden worker can continue app ownership and numerical integration checks without substituting its features for the withheld q8 CTC recipe.
