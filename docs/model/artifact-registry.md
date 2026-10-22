# Research artifact registry and quarantine

Status: persistent enforcement foundation; production orchestration and review pending

Migration `0005_artifact_registry.sql` and `ArtifactRegistryService` provide a
tenant-scoped lineage registry for datasets, feature caches, checkpoints,
calibration artifacts, evaluation reports, and deployments. This registry does
not approve any model or dataset for clinical use. Every registered artifact is
database-constrained to `research-only` and `learner_feedback_eligible = FALSE`.

## Lineage and authorization

- A root dataset must name every learner, exact immutable consent snapshot, and
  processing purpose (`audio-research` or `visual-research`). Registration
  requires current research consent, affirmative/not-applicable assent, the
  matching modality permission, an undeleted learner, and an active owner or
  reviewer membership.
- Consent insertion maintains a current-consent generation on the learner row.
  Dataset and derived registration lock every dependency learner in stable ID
  order and compare that generation to the named snapshot. Consent changes and
  deletion update the same rows, preventing registration from slipping past a
  completed quarantine trigger under concurrent transactions.
- A derived artifact must name one or more active parents. It inherits the
  complete deduplicated consent dependency set and records append-only parent →
  child edges. A database trigger rejects cycles. Parent dependencies are
  reauthorized during registration, not trusted solely from their status marker.
- Every use requires a fresh `authorizeUse` call. It independently rechecks the
  active artifact, tenant and role, undeleted learners, exact latest consent,
  research permission, assent, and modality permission. Successful uses create
  an audit event and opaque authorization receipt.
- Hashes and versions describe external immutable objects. The registry does
  not store media, features, checkpoints, or reports themselves.

## Automatic impact propagation

Database triggers run in the same transaction as consent supersession and
learner deletion. They recursively traverse lineage from every affected source
dataset, change active artifacts to `quarantined`, and append an
`artifact_quarantine_events` record. Direct datasets record
`consent-superseded` or `learner-deleted`; descendants record
`ancestor-quarantined`.

The same transaction writes a durable action outbox. Required actions are
derived from artifact kind:

| Artifact | Required external actions |
| --- | --- |
| Dataset | Revoke access; purge the affected subject's data |
| Feature cache | Revoke access; purge the cache |
| Checkpoint or calibration | Revoke access; schedule retraining |
| Evaluation report | Revoke access; schedule re-evaluation |
| Deployment | Revoke access; disable deployment |

Events and actions are subject-specific. If a second participant later
withdraws from an already-quarantined dataset, the registry creates a new purge
and descendant action set for that participant rather than assuming the first
quarantine handled them.

`ArtifactQuarantineReconciler` leases one action at a time using `FOR UPDATE
SKIP LOCKED`. Claims have bounded expiry and stable idempotency keys. Successful
acknowledgement requires the adapter to echo the action, artifact hash, action
type, and idempotency key and provide a receipt reference and SHA-256. Failed
calls use bounded exponential retries; malformed receipts and permanent errors
are dead-lettered. Every claim and outcome is appended to an immutable action
event ledger. An expired worker cannot acknowledge an action after another
worker reclaims it.

`Ed25519ArtifactQuarantineReceiptVerifier` adds a provider-neutral signed path.
Its canonical versioned payload binds provider and key IDs, issuance time,
action, idempotency key, artifact hash,
receipt hash/reference, and outcome. Verification requires a configured Ed25519
public key and bounded issuance time. Tampered, stale, unknown-key, malformed,
or forged verification metadata is dead-lettered as `verification-failed`.
Successful actions and immutable transition events retain the provider/key IDs,
algorithm, issuance time, registered SPKI public-key fingerprint, and SHA-256 of
the signature; the raw signature is not retained. The local tests use ephemeral
private keys and are not provider evidence.

The unsigned adapter interface remains available for foundation tests and is
not production-eligible. Production wiring must wrap a reviewed signed adapter
with `VerifyingArtifactQuarantineAdapter` and load trusted keys from an approved
rotation and revocation process.

## Receipt signing-key lifecycle

Migration `0008_receipt_signing_key_lifecycle.sql` and
`ArtifactReceiptSigningKeyService` provide an append-only, tenant-scoped trust
registry. Only active tenant owners may register canonical Ed25519 public keys
with activation and expiry windows or append a reasoned revocation (`rotated`,
`compromised`, or `provider-disabled`). Owners and reviewers may list key
metadata and load currently active keys into a verifier; every operation is
audited. Lists expose the SPKI SHA-256 fingerprint but not the PEM value.

Overlapping activation windows support controlled rotation. Scheduled and
expired keys remain visible for governance but are not loaded. Revoked keys are
never loaded again. Signed success persistence independently rechecks, in the
same SQL statement as the action transition, that the key belongs to the
action's tenant, has the exact verified SPKI fingerprint, covered the receipt
issuance time, and remains unrevoked. A
revocation racing with an already-created verifier therefore fails closed as a
non-retryable verification error instead of persisting stale trust.

The database stores public keys only. It does not store or generate private
keys and is not evidence of KMS/HSM custody, provider ownership, key ceremony,
dual control, rotation delivery, or emergency revocation in production. Current
tests use local PGlite records and ephemeral private keys.

The queue is an enforcement and evidence boundary, not proof that an external
effect occurred. Only a reviewed adapter may convert its provider's response
into a receipt, and the current repository includes no production external
adapter or worker schedule.

Claim `tenantId` and `sourceLearnerId` values are internal opaque identifiers.
They are not names, external identity-provider subjects, or safe provider object
keys. A production adapter must translate them through a separately authorized,
purpose-specific mapping and must not log or forward them unnecessarily.

## Data-subject transparency

Authorized learner exports include a privacy-minimized view of retained
research-artifact evidence. Each record identifies the artifact kind, version,
current status, research-only posture, and the subject's exact consent snapshot
and processing-purpose dependencies. It includes only quarantine events for the
exported learner and exposes action type, state, attempt count, completion time,
error category, and whether a receipt was recorded.

The export deliberately excludes artifact hashes, external receipt references,
idempotency keys, lease/worker details, and quarantine events belonging to
other participants. A shared artifact can therefore appear quarantined without
disclosing which other participant caused that status. This database-level
transparency foundation still requires counsel review and deployed export
verification before Gate 1 closes.

## Monitoring and deletion drills

`ArtifactOperationsService.getQuarantineHealth` is an audited, tenant-scoped
owner/reviewer read. It reports pending, processing, succeeded, expired,
overdue, and dead-letter counts plus counts by action type. The status is
`critical` for any dead letter or expired lease, `attention` for ready work
older than the configured threshold, and otherwise `healthy`. A healthy empty
queue is represented explicitly rather than treated as missing access.

`buildQuarantineAlertEvidence` evaluates that health state into deterministic
reason categories (`dead-letter`, `expired-lease`, and `overdue-ready`) and
appends a fingerprinted audit record. Its report is permanently local-only,
sets `deliveryEvidencePresent: false`, and lists the missing authenticated
channel, acknowledgement/escalation, and managed-environment test evidence. It
does not send or claim to send an alert.

`buildDeletionDrillReport` starts from an authorized completed deletion request
and independently checks that:

- the learner is logically deleted and device sessions, attempts, and analyses
  are gone;
- every dataset dependency and lineage descendant is quarantined and has a
  deletion-specific event;
- every deletion-event reason matches the artifact's role (direct dataset or
  descendant), rather than reusing an earlier consent-quarantine event;
- the action set exactly matches the kind-specific matrix, with no missing or
  unexpected actions, and every expected action succeeded with a bound receipt;
- no expected action is unresolved or dead-lettered; and
- the last completed action met the declared time target measured from logical
  deletion completion to outbox completion.

The report also counts locally verified signed receipts separately from merely
bound unsigned receipts. That count remains ineligible for Gate 3 until the
configured keys and receipts come from the reviewed managed provider path.

## Managed artifact objects

Migration `0009_managed_artifact_objects.sql` and
`ManagedArtifactObjectService` bind a research artifact to an external-provider
object without storing its URL, bucket, path, or provider locator. The database
retains only a provider ID, SHA-256 of the separately managed object reference,
provider object version, and the artifact's immutable expected SHA-256.
Registration is tenant-scoped, owner/reviewer-only, and rechecks active artifact
status plus every current research-consent dependency while locking affected
learners against concurrent supersession or deletion.

A provider adapter receives only a frozen inspection claim containing the
binding ID, provider ID, hashed object reference, provider version, and expected
digest. It receives no tenant, artifact identity/kind/status, or timestamps. The
adapter returns an existence, digest, and access-state observation. The service verifies binding
echoes, receipt shape, and a bounded provider timestamp, then appends immutable
evidence. Outcomes distinguish missing objects, digest mismatches, and access
mismatches. Active artifacts require `available`; quarantined or retired
artifacts require `revoked`. The observation insert uses the artifact's current
database state, so a quarantine racing with an external check is evaluated
conservatively. Composite foreign keys prevent evidence from being attached to
a different tenant, binding, or artifact.

Current adapters and receipts are local test doubles. Reconciliation records
are permanently `local-foundation` and `productionGateEligible: false`. The
hash-only object reference requires a separately authorized provider mapping;
it is not sufficient to locate an object by itself. Production still requires
an authenticated provider adapter, signed observations, managed locator
custody, scheduling, alerting, and direct provider-state tests.

The report is permanently marked `local-foundation` and
`productionGateEligible: false`. Even a fully passing local report cannot close
Gate 3 without provider-signed receipts, managed-Postgres concurrency evidence,
alert delivery, least-privilege verification, and independent review.

Quarantine is intentionally irreversible through the application API. A new
consent snapshot does not make an old artifact eligible again: operators must
construct a new compliant dataset and re-run every derived step. Even if a
privileged database operator incorrectly clears a status marker, registration
and use still fail because they re-evaluate the immutable dependencies.

## Production work still required

- Connect authenticated, signed dataset exports and every training/evaluation
  job to this service; direct database writes are not an approved workflow.
- Connect a separately authenticated worker schedule and reviewed provider
  adapters for the selected artifact store, deployment platform, and work
  tracker. No public route may expose lease tokens or worker operations.
- Connect reviewed provider keys and signed adapters, add key rotation/revocation,
  deliver alerts for retry backlog and dead letters, and reconcile successful
  receipts against provider state.
- Connect managed-object reference hashes to a separately authorized locator
  mapping and require provider-signed reconciliation observations.
- Validate concurrency, backup/restore, least-privilege roles, alerting, and
  deletion drills on the selected managed Postgres provider.
- Obtain privacy, security, clinical, and legal approval before registering any
  real participant dataset.

Focused verification is in `packages/platform-data/src/artifact-registry.test.ts`.
It covers role and tenant denial, wrong-purpose and stale consent, inherited
lineage, recursive supersession/deletion quarantine, audit receipts, and
fail-closed authorization after a simulated status-marker bypass.
Worker/outbox verification is in
`packages/platform-data/src/artifact-quarantine.test.ts`, including the complete
action matrix, a second-subject withdrawal, retries, lease recovery, stale
acknowledgement denial, malformed receipts, dead letters, and append-only event
history.
