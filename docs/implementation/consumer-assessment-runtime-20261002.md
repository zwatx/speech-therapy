# Consumer assessment runtime checkpoint — October 2, 2026

The pinned local assessment pipeline now has repeated end-to-end runtime and sampled memory evidence, plus an actual simulator-to-model processed-response check. Research predictions remain unverified and all learner, clinical and production eligibility flags remain false. The owner selected **simulator checks only**; physical checks remain unexecuted.

## Measured host baseline

Three calls reused only the previously permitted age-6, 2.58-second fitting engineering fixture with six targets. Every call started a fresh model worker and returned all six targets. No deliberate raw-audio, feature or probability export was requested. The Mac reports Apple M3 Max, 16 logical CPUs.

| Call | End-to-end seconds | Sampled descendant RSS, KiB | Successful samples | Maximum sample-start gap, ms |
| --- | ---: | ---: | ---: | ---: |
| First | 8.179 | 1,690,272 | 100 | 92.29 |
| Repeated, fresh worker | 6.381 | 1,689,312 | 79 | 93.18 |
| Repeated, fresh worker | 6.454 | 1,689,008 | 79 | 89.27 |

All-attempt denominator: 3; processed: 3; unavailable: 0. Mean time was 7.004 seconds, median 6.454 seconds. Descendant sampled RSS was about 1.61 GiB; the benchmark parent was separately around 28.4 MiB. Those independently observed peaks must not be summed.

The sampler requested 50 ms intervals and observed no sampling errors. It includes the Python worker and Node descendants. Shared pages can be counted twice, finite sampling can miss peaks, and `ps` rows can reflect different instants. This is sampled aggregate RSS, not an exact high-water mark. Background activity was uncontrolled; native builds/tests overlapped part of the benchmark. Disk cache was uncontrolled. No machine-cold, resident-model warm, idle-host, broad latency distribution or iPhone performance claim follows from three calls on one fixture. The current measurement does not establish a product latency target or an optimization gain.

Private temporary fixture copies were removed, no bridge stages remained, and all 13 preserved scientific source/document bindings matched before and after. Closed fitting studies were not rerun; sealed TEST was untouched. The separate preserved /r/ candidate was not evaluated here.

## Simulator verification

- **26 Python checks passed:** 16 existing bridge tests plus 10 benchmark tests, including real synthetic Python/Node process-tree sampling, bounded reports, exclusive output and failure denominators.
- **Two Apple-file checks passed:** actual mono 16 kHz PCM16 WAV bytes and known duration/power through the app reader, plus exact native transport and independently hashed unavailable response through an intercepting protocol. No network was used by those two tests.
- **Two real local-service checks passed, neither skipped:** a silence response and an Apple-generated nonspeech WAV through the native reader/client, local service, frozen extraction and retained model. The latter returned `processedUnverified`, with finite positive timing, and its local file was discarded. It completed in 6.069 seconds as reported by XCTest; this is a test duration, separate from the three-call benchmark.
- **One physical-protection check skipped explicitly on the simulator.** Complete-protection attributes, locked-device access and actual backup behavior remain unverified on hardware.
- Strict formatting passed for both affected Swift test files. Production native sources did not change in this tranche; prior full native 139-check and unsigned Release results retain their earlier scope. Three new passing methods give 142 distinct passing native unit checks across recorded runs, plus the physical-only skip. No single final 143-method suite or new UI/Release run is claimed.

The WAV is deliberately synthetic nonspeech, not the requested word. This demonstrates why processing cannot itself establish speech presence or prompt matching. These checks request no microphone/camera permission, recording or playback and collect no participant data. The parent-owned local service was stopped afterward.

Astra independently reviewed benchmark code and synthetic tests. Final metadata refinements document non-atomic sampling and bind the worker source; the parent then ran the combined 26-check suite. The final delta review is CLEAR on the exact final benchmark and Swift test bytes, aggregate report and saved logs. It traced capture/client seams, ran no tests and accessed no corpus/model/device. It inspected the cleanup receipt without independently repeating cleanup; the task-local receipt retains exact review hashes.

## Goal completion audit

| Required deliverable | Current state | Remaining work |
| --- | --- | --- |
| Assessment specification and coverage | Delivered engineering specification; compiled 892-word / 2,398-entry audit; proposed 15-entry pack | Qualified age/dialect/reference/content decisions |
| Versioned real bridge | Delivered binding, parity, failures, cleanup and repeated runtime/memory evidence | Prompt matching, speech admission and product-domain evidence before learner findings |
| Native no-account internal integration | Debug simulator consent, recorder, client, accounting and real processed/unavailable integration verified | Physical capture deferred per owner; no product assessment eligibility |
| Local participation history | Persistence, recovery, clear and capped history implemented and simulator-tested | Actual protection/backup hardware behavior deferred per owner |
| Reviewable frozen /r/ preparation | Candidate/source bytes and synthetic-tested evaluator have a reviewed hash-bound preparation snapshot | Calibration code/coefficients/fit receipt, exact reserved selection and denominator, acceptance/coverage/multiplicity decisions, qualified statistical review, new dated declaration and separately authorized execution |
| Qualified content-review materials | Pack worksheet and annotation preparation delivered | Actual qualified decisions, labels, reference audio/images and approved cues; no contact authorized |

The active goal remains incomplete. The next safe implementation step is isolated calibration preparation with synthetic numerical checks and review, preserving closed studies and sealed TEST. Preparation code does not authorize fitting or TEST evaluation. Broader learner findings, scores, diagnosis, accounts and depth/fusion retain their separate roadmap gates.

## Evidence

- [Aggregate runtime report](../../work/assessment-runtime-20261002/runtime-three-attempts.json) and [cleanup/binding receipt](../../work/assessment-runtime-20261002/runtime-input-cleanup-receipt.json).
- [Python test log](../../work/assessment-runtime-20261002/bridge-benchmark-final-tests.log), [Apple-file simulator log](../../work/assessment-runtime-20261002/hardware/simulator-final.log), [actual model-loopback log](../../work/assessment-runtime-20261002/native-model-loopback.log); corresponding saved `.xcresult` bundles remain task-local.
- [Checkpoint receipt](../../work/assessment-runtime-20261002/verification.json), prior [implementation checkpoint](consumer-assessment-milestone-20261002.md), [bridge instructions](../../research/audio-head/consumer_assessment/README.md).
