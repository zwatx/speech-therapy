# Recovery test registry isolation correction

Later source review found that `AudioHardwareRecoveryTests.testDroppedFacadeWithFailedCleanupRemainsReachableForExplicitRetry` omitted `fileOwnership` when constructing its controlled runtime. It therefore used the process-wide in-memory registry. Statements that every selected earlier recovery case had a separate per-case file registry are too broad.

The original test still used a fresh hardware gate, an inert controlled driver and a UUID URL under `/controlled-recovery`; that driver reads no audio file and performs no AV operation. This finding does not alter the recorded pass/fail outcomes or establish existing-user file/history access. Earlier frozen source/evidence capsules and guides remain preserved. Their isolation claim must be read with this correction.

The new `process-cleanup-recovery/draft-v3` test explicitly injects a fresh `ProcessAudioFileOwnership`, preserving its URL, driver, control flow and every original assertion. Source parse and style checks passed. Semantic execution for this revised fixture remains pending; this correction does not invent a rerun or cleanup outcome.
