# Confirmation artifact stages — reviewed preparation

Prepared 2026-10-03. This addendum records supplied-artifact tooling and synthetic verification. It does not alter the frozen scientific protocols, declare a new study, authorize a real fit or open sealed TEST. Research-only status remains true; learner, clinical and production eligibility remain false. Physical checks remain deferred under the owner's simulator-only instruction.

## Implemented stages

| Stage | Public boundary | What it establishes | Remaining evidence |
| --- | --- | --- | --- |
| Selection | `select.prepare_selection` in the prior tooling snapshot | Supplied metadata selection, fixed cap and post-cap exclusions without substitution; zero-token children retained | Authentic complete reserved metadata, applicability and permission to inspect it |
| Calibration | `calibrate.fit_calibration` and saved-transform prediction | Declared numerical recipe on explicit supplied inputs; independent scalar control audit | Authorized full-DEV fit, actual fixed coefficients and complete provenance |
| Prediction lock | `locking.create_prediction_lock(payload, output_directory)` | Complete child/token roster, three terminal arm rosters, private canonical artifact and exact SHA-256 | Authenticated provenance, predictions from the declared fixed models, external anchor recorded before outcomes |
| Outcome join | `locking.join_locked_outcomes(lock_path, expected_sha256, ratings, output_directory)` | One attempted join per physical lock directory, consumed failure and complete outcome roster | Independently controlled outcomes, verified chronology and study authority |
| Evaluation | Existing frozen `evaluate.evaluate(payload)` | Descriptive own-arm and identical-token paired metrics, complete failure denominators and conditional child bootstrap | Agreed decision criteria and qualified interpretation |
| Independent audit | `evaluation_audit.audit_evaluation(payload, report)` | Separate numerical replay and exact terminal-input/metadata consistency | Original corpus provenance, biological independence and scientific approval |

The first two rows refer to the [prior tooling addendum](r-confirmation-tooling-preparation.md). The new modules import no models, corpus loaders or closed study stages. They do not discover inputs or execute fitting/inference. Their public boundaries accept explicit supplied objects. Metadata or descriptors could contain covert outcome information; schema validation cannot establish blinding.

## Prediction and outcome artifacts

Prediction inputs contain exactly `children`, `selectedTokens` and candidate/retained/calibration `arms`. Every selected pair needs one terminal row per arm: a finite probability in [0,1], or an unavailable/failed reason. The full child denominator includes children with no selected tokens. IDs must be nonempty strings without surrounding whitespace; rows are lexically ordered, probabilities become floats and signed zero normalizes to `0.0`.

`prediction-lock.json` binds canonical inputs, membership, complete per-child/per-arm terminal coverage and current locking source bytes. Its returned `lockSha256` hashes exact file bytes. The caller must record that digest in a trusted external anchor before supplying outcomes. The API cannot prove this chronology or authenticate an external anchor. Source-byte binding also cannot attest the loaded runtime.

Exports use sorted-key compact UTF-8 JSON, no trailing newline and no nonfinite values. New directories have mode 0700 and files 0600. Joining requires a private owned physical lock path, a regular single-link lock file, no symlink components, canonical bytes and matching internal/source/external digests. On macOS, callers must resolve temporary-root aliases before passing paths. Lock reads are bounded at 10 MiB. Existing output directories are refused without merging, overwriting or deleting their contents.

After checking the lock and reserving a fresh output directory, the join creates an exclusive adjacent `outcome-join-claim.json` **before hashing or validating outcomes**. A claim in any state blocks another attempt. Complete valid outcomes produce `joined-input.json`, a success receipt and a terminal success claim. Invalid outcomes leave a failed claim and a safe failure receipt, without joined data. Filesystem failure can leave a started or partial marker/evidence rather than a completed failure receipt; the marker still blocks retry.

Outcome rows require the same full selected-pair roster. Available outcomes carry nonnegative integer positive derhotic (`n-k`) and negative rhotic (`k`) votes with positive total; unavailable outcomes carry a reason. Boolean counts and floating-point-overflowing totals fail. Receipts distinguish:

- `attemptedRatingsSha256`: finite serializable supplied outcomes in their as-given array order; null if serialization is impossible. Present on success and validation failure.
- `ratingsSha256`: the complete validated lexically normalized roster; null on validation failure.
- `joinedInputSha256`: exact joined file bytes; null on validation failure.

These claims are local to one physical lock directory. A pristine copy can support another physical claim. No global once-only guarantee, signatures, trusted time, actual blinding or defense against a malicious same-user owner is established.

## Independent evaluation audit

The new auditor recomputes AUROC using grouped integer ranking credit, including mixed-vote self-pairs and ties. It independently computes proper scores with normalized listener fractions and scalar `math.fsum`, checks full terminal coverage and shared pair membership, and replays the frozen conditional bootstrap settings: PCG64 seed 20261002, 2,000 whole-child resamples of defined paired children and linear 95% quantiles. Numerical comparisons use absolute/relative tolerance 1e-10; raw terminal inputs, descriptors, flags and counts require exact agreement.

Floating-point summation can change the sign of a gain extremely close to zero. After independently checking constituent metrics, the auditor therefore requires saved gains to equal exact subtraction of the saved constituent metrics, then uses those checked gains for descriptive sign counts and bootstrap replay. This verifies report arithmetic consistently; a tiny positive gain is not evidence of meaningful improvement. The original frozen evaluator and statistical settings remain unchanged. The interval remains conditional on children with defined paired metrics and is not a full-cohort or selection-adjusted guarantee.

## Observed verification

The parent ran 65 tests with warnings treated as errors: 14 existing evaluator, 12 calibration, seven scalar calibration audit, five selection, 19 locking and eight evaluation audit tests. The eight audit tests include 60 deterministic synthetic cases. Locking checks include an actual two-process race with one winner, private paths/modes, tampering, malformed inputs, interrupted markers, copied roots and failure consumption. Independent Astra reviews cleared the exact new sources and independently ran the 19 locking and eight evaluation audit tests.

A fresh private directory contains an actual saved synthetic pipeline: three invented children (including one zero-token child), six invented tokens, three terminal arm rosters, unavailable/failed rows and invented listener votes. The external anchor was saved before outcomes were constructed. Saved joined bytes were evaluated; saved results were independently audited. Exact hashes, private modes, unchanged lock bytes and refusal of retries after success and failure were checked. This is an engineering demonstration, not a scientific run. No real data, fitting, inference, TEST access or hardware operation occurred in this checkpoint.

Evidence: [current reviewed snapshot](../../work/assessment-locking-20261003/artifact-stages-preparation-snapshot-20261003.json), [verification](../../work/assessment-locking-20261003/verification.json), [synthetic scope receipt](../../work/assessment-locking-20261003/synthetic-pipeline/scope-and-verification.json) and [actual combined test log](../../work/assessment-locking-20261003/combined-final-tests.log).

## Decisions before scientific execution

The reviewable preparation now includes selection, calibration and its audit, prediction locking, outcome joining, evaluation and independent evaluation audit. It does not supply missing real artifacts or qualified decisions. A new dated immutable declaration still needs actual fixed calibration coefficients and provenance, permitted verified reserved metadata and membership, full denominators, minimal worthwhile effect, coverage/undefinedness limits, uncertainty and multiplicity rules, and qualified approval. The existing [confirmatory preparation](r-confirmatory-preparation.md) remains draft/not declared/not executed. No thresholds, reviewer identities or approval are invented here.

The assessment specification and proposed prompt/content worksheets remain ready for qualified review; reviewed reference audio, cues and content decisions remain pending. Preparation does not authorize reviewer contact or participant collection. Findings-guided practice, learner scores and clinical claims remain later evidence gates.
