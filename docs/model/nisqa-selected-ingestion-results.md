# NISQA selected training ingestion results

The fixed 20-recording TRAIN_LIVE pilot is acquired and decoded, and its 100 selected quality ratings are complete. This establishes an import path for recording-quality research. It is not a trained model or demonstrated pronunciation improvement. The retained pronunciation candidate is unchanged.

## Actual data and checks

| Item | Observed result |
| --- | --- |
| Frozen sample | 20 degraded recordings, 10 phone and 10 Skype |
| Provenance groups | 20 approximate publisher/DNS source-code groups; not verified people |
| Age coverage | Unverified; no assertion that every speaker is an adult or a child |
| Ratings | 20 × 5 finite nominal 1–5 values; zero declared missing values |
| Audio | All 20 decoded; mono PCM16 at 48,000 Hz |
| Duration | 6.0000208333–12.0000208333 seconds, original frames retained |
| Peak absolute digital amplitude | 0.0197448730–0.6196899414 |
| Integer rail fraction | Zero on all 20; this does not establish absence of earlier clipping |
| Exact-zero sample fraction | 0.0017986080–0.0398158340 |
| Integrity | Every plaintext size, CRC32 and SHA256 verified |
| Decoder checks | 20 exact auditor replays; separate stdlib-WAV/NumPy PCM decoding matches all 20 hashes |

Overall quality ranges from 1.0 to 3.4; noise from 1.7088628 to 4.60230724; discontinuity from 2.84421628 to 4.65443724; coloration from 1.36389368 to 3.3595659; loudness suitability from 1.416941 to 4.3135588. All are higher-is-better nominal scores. These are descriptive ranges in the fixed training sample, not rejection thresholds. The [scale findings](../../work/nisqa-ingest-20260927/thesis-scale-findings.md) and [independent method review](../../work/nisqa-ingest-20260927/thesis-scale-method-review.md) distinguish nominal scale evidence from our exact serialization policy.

## Preserved download failure and recovery

The initial [selected pilot plan](../../research/audio-head/outputs/nisqa-20260927/selected-audio-target-pilot-v1/plan.json) imported all selected ratings, then audio execution stopped after eight complete files and two HTTP 429 responses during index 8. Its 134 new GET attempts and [failure snapshot](../../research/audio-head/outputs/nisqa-20260927/selected-audio-target-pilot-v1/audio-failure.json) remain preserved. The 917,504-byte incomplete output is preserved too. No file was selected again or replaced with a different identity.

Explicit recovery reused the previously verified directory, unchanged archive validators and cumulative ledger. It retained the eight original complete files and fetched the remaining twelve into fresh names. Each remaining compressed payload was below 1 MiB; larger requests and two-second GET pacing reduced recovery to 36 successful HTTP 206 requests. This was a successful mitigation, not a claim about Zenodo's precise rate policy. Automatic retries were disabled for recovery.

An unexecuted recovery declaration incorrectly asserted adulthood. Astra rejected that metadata claim; the [rejected receipt](../../work/nisqa-ingest-20260927/selected-recovery-v1-rejected-review.json), original plan and [exact source snapshot](../../work/nisqa-ingest-20260927/rejected-recovery-v1-sources/manifest.json) are retained. The [corrected plan](../../research/audio-head/outputs/nisqa-20260927/selected-audio-recovery-v2/plan.json) removes that assertion. It changes no selection, rating, byte limit or technical acquisition rule.

Recovery added 7,123,225 body bytes, including 1,460 metadata bytes. Total cumulative body spending is 27,254,714 bytes; metadata spending is 15,438,176 bytes, below the unchanged 256 MiB and 16 MiB limits. All failed partial retrieval bytes remain charged. Journal prefixes and the failed partial are unchanged; final uncertainty and reservation counters are zero. No central-directory redownload or ledger reset occurred in recovery.

## Evidence and remaining scope

The [target freeze](../../research/audio-head/outputs/nisqa-20260927/selected-audio-target-pilot-v1/targets-freeze.json), [acquisition freeze](../../research/audio-head/outputs/nisqa-20260927/selected-audio-recovery-v2/acquisition-freeze.json), [waveform audit freeze](../../research/audio-head/outputs/nisqa-20260927/selected-audio-recovery-v2/audit-freeze.json) and [root verification](../../work/nisqa-ingest-20260927/selected-results-root-verification.json) bind exact files and checks. The complete ingestion package passes 117 tests. Independent [initial source review](../../work/nisqa-ingest-20260927/selected-pilot-source-review.json) and [corrected recovery source review](../../work/nisqa-ingest-20260927/selected-recovery-source-review.json) cleared implementation before their respective executions. [Independent result review](../../work/nisqa-ingest-20260927/selected-ingestion-results-review.json) is a separate evidence requirement.

Only the selected training quality columns were numerically interpreted. Combined CSV bytes/tokenization include other splits' strings, which were skipped before target indexing. No evaluation audio member was acquired or decompressed, no model inference/fitting or GPU allocation occurred, and no learner judgment was enabled. The archive-wide advertised MD5 remains unverified; partial acquisition verifies individual members and relies on server handling of the pinned If-Range identity.

These read-speech capture-quality labels do not identify substitutions, omissions, verified phone times, nonspeech truth or age-6–12 performance. The next substantive work is a larger, separately declared quality-supervision experiment with child-domain capture and nonspeech controls and the existing pronunciation baseline. This ingestion pilot cannot establish a usable quality threshold, speaker-independent performance or completion of the broader model goal.
