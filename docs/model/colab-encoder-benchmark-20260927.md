# Mac CPU versus Colab T4 encoder timing

An independently reviewed, fixed 22-recording sample was run on the Mac and a Colab Tesla T4 using the same frozen final-layer encoder. The sample contains one recording from each of 20 equal-count duration strata, plus the first and longest recordings. It comes only from the existing 1,040-recording child research cohort. This measures **encoder throughput**, not pronunciation quality or the full temporal feature extractor.

| Measure | Mac CPU, two threads | Colab T4 |
| --- | ---: | ---: |
| Forward inference over the 22 recorded clips | 4.36054 s | 1.34603 s |
| Duration-stratified projected inference over 1,040 clips | 190.276 s | 60.323 s |
| Duration-stratified projected per-clip pipeline over 1,040 clips | 191.052 s | 63.059 s |
| Model load | 0.207 s | 0.941 s |
| Warmup | 0.226 s | 0.994 s |

The projected inference ratio is **3.15×** and projected per-clip pipeline ratio is **3.03×** in favor of the T4. Both projections come from one representative sample per stratum, not repeated trials or a confidence interval. The full temporal extraction actually completed on the Mac in **215.436 s**; its workflow and concurrent activity differ from this benchmark.

The completed T4 sample took **114.427 s end to end**, including allocation, the small upload, downloading and verifying the exact model checkpoint, dependency setup, inference, result transfer, and cleanup. Allocation lasted **113.235 s**. Downloading the checkpoint took 18.002 s, dependency setup 19.530 s, and the remote benchmark process 27.907 s. The latter includes imports, checksums, model load, warmup, 22 recordings and output work; those parts were not all separately instrumented. The 114-second figure is the **22-recording attempt**, not a measured full-cohort runtime. The account showed an unchanged 299.97-unit balance immediately afterward; conservative elapsed-rate accounting estimates **0.03366 units**, and displayed billing may lag.

For each of the 22 recordings, CPU and T4 produced the same final-frame grid shape and finite float32 global mean. Maximum absolute difference among the saved means was **9.1493e-6**, below the fixed `1e-4` gate. This does not establish equality of every frame or the three temporal bin means, and the Mac remains the authoritative source for this experiment's frozen features. No pronunciation model was trained on Colab in this benchmark.

Two preceding bounded attempts are preserved as operational failures. The first tried a 1.27 GB CLI upload, which failed before inference; its exact transport error was not retained. The second uploaded the small payload but failed to parse a multiline remote status response before any GPU result was saved. Each named T4 session was stopped and verified absent with zero active assignments and rate. The third, separately declared and reviewed attempt succeeded. These failures are included in compute accounting; they are not alternate timing samples or model-quality evidence.

The independent GPT-6 Astra post-run audit rehashed all 44 output vectors, recomputed all 22 parity differences and both duration-stratified projections, and checked the reviewed sources, payload/result bindings, ledger and cleanup. It cleared the hardware/global-mean benchmark only. The observed GPU advantage supports considering Colab for larger frozen-encoder workloads after their own setup and parity checks; it does not change the current predeclared CPU training recipe.

## Evidence

- [Fixed 22-recording plan](../../work/colab-temporal-benchmark-v3-20260927/plan.json), SHA-256 `f8ed68bc30abf6f6431bcc32d8f9ce5f311178e40cff8c251088f7874e55b3af`.
- [CPU report](../../work/colab-temporal-benchmark-20260927/cpu-results/report.json), SHA-256 `5590f56cc1a88b05b5c3b817b1aa12d890fe7cecbb2c1b423d2bca2f8cb9244f`.
- [T4 report](../../work/colab-temporal-benchmark-v3-20260927/gpu-results/report.json) and [parity record](../../work/colab-temporal-benchmark-v3-20260927/parity.json).
- [Independent launch review](../../work/colab-temporal-benchmark-v3-20260927/launch-review.json), SHA-256 `453c330f0da4a3f2af7b0fc0bbe145e720b94fb059b8a2884f4038f42275c81d`.
- [Independent results review](../../work/colab-temporal-benchmark-v3-20260927/results-review.json), SHA-256 `5ec3c5d56147a67df51cbd0ea5f0ec84755ca994c25511c7f82379f87a52b598`.
