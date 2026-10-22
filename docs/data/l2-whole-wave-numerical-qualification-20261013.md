# Whole-recording numerical qualification — October 13, 2026

The fixed signal qualification passed all eleven positive cases and both expected rejection cases. Actual host execution returned exit 0 (`8f2730`); independent root collection returned exit 0 (`229af3`). Current source, all 3,718 selected dependency files, saved output pins, confirmed cleanup and absence of the two known processes were checked. Postwrite checks completed after 16.298 seconds within the original 150-second boundary. No process-group absence was claimed.

The tests used generated PCM signals, with no research recording, reference annotation or model call. They cover exact-zero outputs and full-length boundaries at 16 kHz and 44.1 kHz; bit-exact 16 kHz PCM extrema; whole one-second 44.1 kHz impulse timing, constant level and 1 kHz/12 kHz sine behavior. Inputs producing 1,599 or 64,001 output samples were rejected with the fixed header-not-eligible reason. No cropping, clipping, gain rescue, changed thresholds or substituted signals were used.

| Fixed observation | Actual result | Frozen criterion |
| --- | ---: | --- |
| Impulse peak index | 3,628 | Within one sample of 3,628 |
| Interior constant-level maximum error | 0.0000146627 | At most 0.002 |
| Interior 1 kHz error RMS | 0.0000786867 | At most 0.001 |
| Interior 12 kHz output RMS | 0.0000241594 | At most 0.001 |

The first runner's import-guard failure is preserved. A separately closed observation-only diagnostic found the missing installed encoding-helper dependency. The successor added its exact files to the inventory; its namespace rule, numerical validator, thirteen cases, thresholds and ownership controls are unchanged. Independent source review cleared that narrow change before execution.

The root qualification is `work/l2-resampler-runtime-v2/ROOT-ACTUAL-QUALIFICATION-v2.json`, 1,171 bytes, SHA-256 `fcf3d2470ca02e53f822ae30706af6cc8240ef22f0a2f7a5158aef052ecd145d`. It binds the private fixed-case result, parent collection, supervision and original start. The generated result is 1,771 bytes, SHA-256 `56bdccb1aba5d656f860ae5ddb96d8b228a5c208c6a955369e2f91808c3e1047`.

This qualifies the fixed sample preparation on this selected local runtime. It does not measure pronunciation accuracy, independent phone recognition, clinical diagnosis or mobile inference. The next distinct step is whole-recording preparation for the already frozen 48-item adult research cohort, followed by prompt-blind predictions and an immutable prediction/failure lock before reading its reference annotations. Reserve recordings and references remain closed.
