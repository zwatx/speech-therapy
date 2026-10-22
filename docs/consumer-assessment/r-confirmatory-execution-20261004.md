# Frozen /r/ confirmation execution — October 4

The dedicated research pipeline now connects the frozen selection and fixed models to private prediction locking, a sole outcome-access attempt, evaluation, independent audit and the exact saved-policy verdict. This document is an implementation addendum. It does not change the October 3 protocol or authorize reserved recordings/outcomes.

The owner currently prohibits all mobile work because the mobile environment is in use. No app files, builds, simulators, devices, microphone or camera operations were used for this milestone. No fitting, policy tuning, reserved-study execution, participant collection, reviewer contact, commit, push or deployment is included.

## Execution order

| Phase | Entry point | Required predecessor | Result |
| --- | --- | --- | --- |
| Declare | `stages.declare_run(profile, freshroot)` | Complete frozen roster, purpose-bound inputs, explicit runtime/source pins | Immutable declaration; capture its SHA outside the run root |
| Predict | `execution.generate_predictions(root, declsha, execution_inputs_binding)` | Declared execution-input pin | Actual fixed inference, complete three-arm terminal roster, completion SHA |
| Lock | `stages.lock_predictions(root, declsha, predictions_pin, prediction_completion_sha)` | Externally captured prediction completion | Frozen prediction lock; capture lock SHA externally |
| Read outcomes and join | `stages.join_reserved_outcomes(root, declsha, lock_sha)` | Exact externally anchored lock | Outcome-access claim before opening the archive or extracting ratings; saved ratings and joined input |
| Evaluate | `stages.evaluate_run(root, declsha, join_completion_sha)` | Externally captured join completion | Saved unrounded report |
| Audit and decide | `stages.audit_run(root, declsha, evaluation_completion_sha)` | Externally captured evaluation completion | Frozen independent numerical audit, then saved verdict |

Choose a fresh reserved run root under `research/audio-head/outputs`; the frozen extractor accepts outputs only there. Synthetic run roots may use a task-local directory. Only the synthetic test mode accepts supplied ratings files through `join_outcomes`. A reserved run uses the source-pinned archive reader inside the claimed outcome stage. Every phase has a fresh exclusive directory, a started marker and either completion or terminal failure. Repeating a phase, malformed ratings, interruption and concurrent attempts cannot resume the same attempt. An abrupt process death also leaves the directory consumed. No tool automatically chooses another root to retry a study.

The caller must capture anchors immediately after each successful phase in a separate record before invoking the next phase. This is a local lifecycle with caller-retained hashes. It is not a digital signature, proof of global chronology, protection against an operator fabricating all receipts, or proof of the origin of already loaded runtime modules. Execution should occur in a fresh process using the reviewed source snapshot.

## Declared inputs and recording path

`reserved_test` requires all 80 children and all 3,066 selected tokens from the unchanged prepared selection. There are six purpose-bound inputs: `preparedTokens`, `candidate`, `retained`, `calibration`, `policy`, `frozenProtocol`. The public frozen protocol SHA is `458872741505a761719ff29d6be48abc8e06d4b402566a8e0625612b259b9940`. Production role/path/hash assignments are validated against that public protocol before opening supplied private inputs. Arbitrary source roles are rejected before access.

The profile also contains `executionInputs: {path, sha256}`. Declaration validates this pin's shape/path without opening the body. The prediction phase first opens it after claiming its exclusive directory. Its reserved schema is:

```json
{
  "schemaVersion": 1,
  "mode": "reserved_test",
  "archive": {"path": "canonical fixed archive path", "sha256": "frozen archive SHA"},
  "sessions": [
    {
      "folder": "declared folder",
      "session": "declared session",
      "xmlMember": "0phon/folder/session.xml",
      "recording": {"path": "fixed session WAV path", "sha256": "declared recording SHA"}
    }
  ],
  "runtime": {
    "python": {"path": "resolved Python binary", "sha256": "binary SHA"},
    "pythonInvocation": "research virtual-environment interpreter path",
    "node": {"path": "fixed installed Node binary", "sha256": "binary SHA"},
    "ffmpeg": {"path": "fixed installed ffmpeg binary", "sha256": "binary SHA"},
    "contract": {"path": "fixed position contract", "sha256": "frozen contract SHA"},
    "extractorManifest": {"path": "fixed historical extractor manifest", "sha256": "frozen manifest SHA"},
    "phoneticSnapshot": "fixed cached checkpoint directory",
    "sourceBindings": {"fixed extractor source path": "frozen source SHA"}
  }
}
```

This is a shape illustration, not an executable declaration. Supply every selected session exactly once; `recording: null` explicitly preserves an unavailable recording. Use the existing downloaded-recording provenance to prepare the session manifest after separate authorization, without substituting files or discovering a new cohort. Bind the actual Python binary separately from the virtual-environment invocation so the frozen environment remains in use. The reviewed host uses the installed mise Node 24 binary. Executable versions and byte pins belong in the concrete execution record; no downloader or automatic runtime update is invoked.

The selected-word reader first reconciles age, record identity, phones and timing with the frozen structural projection, then projects only selected orthography from a second identical-byte pass. It never extracts or interprets outcome values at prediction time. The first structural pass inspects tier names to identify target phones; other outcome text is opaque. Both passes are bounded and reject DTDs/entities, namespace ambiguity, duplicate structures and changed bytes. Missing or unusable word labels remain explicit failures; no label or replacement token is invented.

The archive is consumed through one held, hash-verified descriptor. Each declared source recording is copied through a held verified descriptor into a private exclusive file, and ffmpeg decodes those verified copied bytes. Conversion preserves the historical input-side `-ss`/`-to` at six decimals, first audio track, mono 16 kHz PCM16; no padding, trimming rule, loudness normalization or app capture guard is added. Converter and extractor waits are bounded at 120 and 180 seconds respectively. Decoder failure or timeout is an explicit processing failure. Unknown extractor failures and source/output/schema/hash violations stop the phase as integrity failures. Interruptions kill/reap child process groups and propagate to a terminal stage.

The frozen occurrence-aware extractor must serialize one float32 vector of 1,037 features with the exact audio/prompt/contract/head/column/occurrence bindings and no model fetching. Its incidental historical head scores are not another comparison arm. The fixed prediction factory applies the retained ages 6–12 mixture, the unchanged candidate PCA16 plus 13 scalars plus retained-logit transformation, and the audited saved calibration transform. It never fits or optimizes. Candidate failure preserves successful retained/calibration predictions; common input failure affects all three arms. All selected tokens remain in every arm, including the seven unsupported-phone selections, with no replacement.

## Outcomes and verdict

Only after the exact lock is verified and the outcome-access marker exists does the pinned reader open selected archive sessions and project `responseCorrect` (`k`) and `responseTotal` (`n`). It saves derhotic-positive votes `n-k` and rhotic-negative votes `k`. Missing ratings are explicit unavailable rows; malformed, duplicate or inconsistent counts are integrity errors. Unselected records and other tier values are never retained by the reader.

The wrapper executes the unchanged independent evaluation auditor before applying the decision kernel to saved unrounded values. Integer coverage requires `100 * processed >= 95 * selected` overall and `>= 90 * selected` for every child, with all 80 primary gains defined. Integrity failure is invalid; insufficient coverage is inconclusive. Otherwise mean paired AUROC gain at least 0.02 with lower conditional 95% bound greater than zero passes ranking. If not passed, an upper bound below 0.02 fails below target; the remaining result is inconclusive precision. A negative gain for one child adds no new rule. Proper scores are descriptive and cannot rescue ranking.

Bootstrap remains the frozen PCG64/default_rng seed 20261002, 2,000 replicates and linear quantiles, conditional on the fixed models and supplied children. No power, type-I error, clinical minimum, biological independence, age-specific accuracy or product-domain claim follows. Research, learner, clinical and production flags retain their frozen meanings; learner/clinical/production eligibility remain false.

## Observed verification and remaining gate

The saved synthetic run uses two invented children, four invented feature rows, fabricated fixed checkpoints and three genuine inference arms. It passes through locking, ratings join, numerical evaluation and the actual independent auditor, then correctly returns `fail_below_target`. It is evidence of execution fidelity, not a research result.

One previously approved SpeechOcean fitting fixture (`000010011`) completed the new recording extraction exactly once. All 1,037 selected /r/ feature values equal the historical engineering reference. The actual fixed retained predictions equal the direct frozen loader, candidate prediction differs from an independent scalar formula replay by `1.1102230246251565e-16` (declared tolerance `1e-12`), and saved calibration prediction matches exactly. The initial verification script stopped on a receipt-shape comparison after extraction had completed; saved output was verified without another extraction attempt. Its completion hash was captured afterward, so no initial external chronology is claimed for that bounded engineering check. All temporary recording copies, cut audio and worker intermediates were removed; the permitted numeric feature and private receipts remain local.

All 49 new pipeline checks and all 126 unchanged frozen-helper checks passed with warnings treated as errors. Independent GPT-6 Astra source/document review cleared the final implementation; the reviewer ran no tests or real inputs. Final source/test checks, preservation receipts and independent review are recorded under `work/confirmation-execution-20261004`. The hash audit verified 141 prior bindings and all 121 October 3 protocol bindings without opening reserved source archives/recordings or mobile files. No real reserved cohort prediction, outcome extraction or evaluation was performed. The next research action needs separate authorization to open those sealed inputs against a concrete declaration and reviewed source snapshot. Qualified content/reference approval, prospective app-domain evidence, rights, prompt matching, abstention and correction safety remain separate product gates.
