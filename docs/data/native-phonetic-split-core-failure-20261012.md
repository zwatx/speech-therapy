# Phonetic split-core attempt — October 12, 2026

The reviewed split-core model attempt failed. It does not establish full model parity or pronunciation accuracy. The existing app and bundled word recognizer were not changed by this attempt.

The source manifest was 1,882 bytes, SHA-256 `8e0402035afe2728c9be047b837c91df70258a07ef1b4fcccd4e1c1b9c694bea`. Independent source review passed 42 supplied and 17 additional mocked checks. Root preflight then verified 27,793 current source, runtime, model, compiled preprocessing and evidence pins. Those checks did not substitute for actual model execution.

Actual host session 14403 returned exit 1 (`41660e`). Its owned worker terminated with signal 11 after 72.457 seconds. Immediate collector session 78480 returned exit 1 (`0cf7ad`), preserving a failed-or-unknown result. The worker left no complete generated receipt or C provenance document. Planned comparisons remain 304; independently completed and unreached comparison counts remain unknown. Both split-core acceptance and original native-304 acceptance remain false.

Partial files include 20 generated inputs, 80 normalized arrays, 80 masks, original and traced outputs, a converted package and the first Core ML prediction output. These are artifact-presence observations, not independently accepted numerical comparisons or successful repeated prediction.

Root closure session 99790 returned exit 0 (`b3731e`) after checking current guards, the collected direct-child exits, no sent signals and absence of all four known controller/worker PIDs. Observation through the actual terminal qualified within 301.776 seconds of the host's 3,600-second interval and 216.545 seconds of the collector's 300-second interval. The initial closure read failed because it assumed a generated receipt existed; the corrected closure explicitly retains that missing receipt. Cleanup of unknown descendants is not claimed.

The operating-system crash report matched the exact worker. Its crashed thread passed through Python thread detachment, PyTorch tensor destruction, NumPy array destruction and Core ML input reset on a dispatch queue. This supports an input-buffer ownership hypothesis: the NumPy inputs supplied to Core ML shared storage with PyTorch tensors, and delayed release may invoke their destructors on a background thread. Output ownership is a second possibility. A narrow fresh successor will use independently owned NumPy buffers with identical values, retaining the existing model, runtime, cases, preprocessing, comparison rules and budgets. This is a prospective repair, not a verified cause or fix. No unchanged retry is planned.

The failed source, outputs, private logs and aggregate crash evidence remain local and preserved. No real recording or annotation was used, no recording was uploaded, and signing and account settings were unchanged. Desktop research evaluation remains a separate path.
