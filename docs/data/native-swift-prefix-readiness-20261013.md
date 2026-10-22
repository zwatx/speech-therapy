# Native Swift diagnostic readiness — October 13, 2026

The standalone Swift diagnostic compiled successfully with the installed Swift 6.4 toolchain and Core ML APIs. This is a source-compatibility result. The subsequent model package compilation succeeded, but the two-call diagnostic produced a failed receipt before any invocation marker. Native transport remains unqualified.

The diagnostic uses Core ML allocated input arrays, retains the input and output owners through two synchronous calls, and returns from its teardown scopes before writing a complete receipt. It is intended to investigate the native transport route after the earlier Python/Core ML crashes. It does not establish the cause of those crashes or qualify the original 304-case parity test.

The first compilation preflight stopped before launching the compiler because the installed versioned SDK path is a symlink. That negative result is preserved. A fresh compilation used the canonical SDK and verified the versioned alias still resolved to it.

The successful compiler job exited normally. Independent collection checked the current source, compiler, SDK metadata, compiled product and original output-directory identity. All five tracked or outer process IDs were absent; cleanup was confirmed within the original 180-second budget, at 10.792 seconds. Diagnostics were empty. No process-group absence is claimed. The installed framework and compiler dependencies remain a trusted system boundary, rather than a complete cryptographic inventory of macOS.

The next native diagnostic will use the currently observed model package and two zero-input artifacts. Their current hashes and inventory are established, but the failed earlier converter did not leave complete checkpoint, conversion or C-output provenance. Consequently this diagnostic can establish observed-artifact transport behavior only. It cannot establish checkpoint correctness, Hugging Face parity, mobile sound accuracy or clinical validity.

No signing or account settings changed, and no recordings were uploaded.

Evidence: `work/native-swift-prefix-compile-v2/ROOT-ACTUAL-QUALIFICATION-v1.json`, `COMPILE-v1.json` and `SUPERVISION-v1.json`; independent source review in `work/native-swift-prefix-draft-v1/ASTRA-SOURCE-REVIEW-v1.md`; current observed-artifact inventory in `work/native-swift-prefix-provenance-v1/OBSERVED-INPUTS-v2.json`.

The October 13 bounded native attempt returned parent exit 1 (session 19922, terminal `80518a`). The compiler and Swift worker each returned exit 0 with confirmed recorded cleanup, but Swift wrote only `RECEIPT.json` with `status: failedOrUnknown`; neither call was committed or returned in the saved evidence. A normal worker exit alone was correctly rejected. The current diagnostic does not identify the exact failing stage, so no model-call or crash-repair success is claimed.

Immediate independent negative collection returned exit 0 (session 58716, terminal `7e64be`). Current source/tool/SDK/package/input and available original-directory checks passed, both historical supervision receipts reported cleanup, and all three known PIDs were absent at 79.908 seconds within the original 1,200-second interval. Complete transitive job-set closure remains unproved and is reported separately. The private negative report is `work/native-swift-prefix-root-controller-v1/execution-v1/ROOT-ACTUAL-NEGATIVE-v1.json`: 10,062 bytes, SHA256 `7e13b11681d1c74964cd45eed7c6dd229dc0899fb8fe3daba724d22f10880124`. No unchanged retry was performed. The next source change will report a precise failure stage without changing model or acceptance rules.
