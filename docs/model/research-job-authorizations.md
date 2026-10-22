# Research job authorization envelopes

Status: signed workload claim, terminal, and cancellation acknowledgement research foundation

Migration `0010_research_job_authorizations.sql` and
`ResearchJobAuthorizationService` provide append-only authorization envelopes
for dataset export, feature extraction, training, calibration, evaluation, and
shadow evaluation. They do not run jobs or approve models for clinical use.

Every request binds:

- exact input artifact IDs, kinds, SHA-256 values, managed-object binding IDs,
  providers, hashed object references, and immutable provider versions;
- a legal job/output transition, globally unique output ID, and output version;
- a 40-character code revision, configuration SHA-256, and immutable
  `sha256:` runner image digest;
- intended use, explicit exclusions, requester, and a 5-minute–24-hour expiry;
- `research-only`, `learner_feedback_eligible: false`, and
  `productionGateEligible: false` postures.

Request creation locks every consent-dependent learner, requires current
research/modality consent and assent, and accepts only active artifacts whose
latest managed-object observation is consistent, available, and digest-exact.
The output transition matrix prevents a dataset-only request from claiming a
calibration/evaluation output. Output IDs are reserved globally to match the
artifact registry primary key, and absence is rechecked at request, approval,
and execution authorization.

A distinct active owner or reviewer must approve the request. Canonicalization
rebuilds every input in fixed field order, sorts inputs and exclusions, and
hashes the complete envelope plus approver identity with SHA-256. The approval
is an authenticated database attestation, not a cryptographic signature.

`authorizeExecution` accepts only a fresh Ed25519 claim from a registered,
tenant-scoped `research-job-runner` workload and recomputes the envelope hash
before rechecking expiry, workload/key trust, current consent, artifact
hash/status, managed binding, and latest provider observation. The claim ID,
tenant, workload, key, issuance time, job ID, and exact envelope hash are in the
canonical signed payload and the one-time claim is created atomically.
Consent withdrawal,
quarantine, object drift, missing evidence, access mismatch, or envelope
tampering fails closed. Any produced artifact must still be registered through
the lineage registry, which independently reauthorizes all parents.

Execution claims and cancellations are append-only. A job can be claimed only
once; replay attempts fail. New claims cannot name a human actor: a database
trigger requires the signed workload principal and verification evidence.
Raw signatures are not retained; the public-key, payload, and signature hashes
plus issuance time are persisted and the audit event is attributed to the
workload. Owners/reviewers can append an operator cancellation.
Identity and key revocation share monotonic trust gates with claim persistence.
Claims update the identity gate and then the key gate before inserting evidence;
revocation updates the same row to `revoked = true`. A waiting statement is
re-evaluated against the committed gate state, closing the stale-snapshot race.
Keys must cover both the signed issuance time and database `CURRENT_TIMESTAMP`;
scheduled and expired keys cannot exploit the allowed clock-skew window.
Signatures must also be canonical Base64URL encodings of exactly 64 bytes.
Artifact quarantine automatically appends `input-quarantined`, while any newer
non-consistent managed-object observation appends `provider-drift`. Authorized
state polling exposes these records to a runner. Each automatic/operator source
has its own immutable record; polling prioritizes input quarantine over provider
drift over operator stop while preserving all evidence. Claim creation and every
cancellation source serialize on the job row. A claim reports only that no
cancellation was observed at that instant and explicitly requires continued
polling. This is cancellation evidence and a polling contract—it does not
terminate an external process by itself.

After cancellation, the claiming workload can append a canonical Ed25519
acknowledgement for the currently effective cancellation. The signed payload
binds the tenant, workload, governed key, issuance time, exact claim and
envelope, monotonic cancellation revision, cancellation ledger sequence/source/
reason, termination outcome, and hashed termination evidence. A `process-stopped`
outcome also requires a hashed process reference; `not-started` forbids one.
Signature freshness, canonical encoding, current identity/key trust, key
validity, claim ownership, and issuance at or after the effective cancellation
are rechecked at persistence. Raw signatures are not stored. Replay,
pre-cancellation, stale-revision, stale-safety-precedence, and revoked-key
attempts fail closed.

Claimed jobs can append exactly one terminal receipt: `succeeded`, `failed`, or
`cancelled`. The terminal payload hash binds the exact claim and approved
envelope to either failure evidence or managed output provenance. Terminal
attestations are canonically signed by the same tenant/workload principal that
claimed the job, using a currently active governed key. Signature encoding,
freshness, key validity, and monotonic identity/key gates are rechecked at
persistence; raw signatures are replaced by public-key/payload/signature hashes.
A successful
receipt is one transaction that rechecks every input and current consent,
registers the reserved output ID/version/digest, creates all parent lineage and
inherited consent dependencies, registers the hashed managed-object binding,
records its initial consistent provider observation, advances the monotonic
gate, and audits completion. Any conflict rolls the entire statement back, so
an output artifact cannot be left orphaned from its terminal receipt.

Cancellation and successful completion arbitrate on the same locked gate. A
cancellation that commits first prevents success and permits only a
`cancelled` receipt; a success that commits first makes later cancellation a
rejected transition. Failed receipts require an uncancelled claim, while a
cancelled receipt requires a current signed cancellation acknowledgement for
the exact claim. A stronger later cancellation—input quarantine over provider
drift over operator stop—increments the gate revision, invalidates an earlier
acknowledgement for terminalization, and requires new evidence. The cancelled
terminal signature itself binds the exact acknowledgement ID and revision, must
be issued at or after that acknowledgement, and persists the same binding on the terminal
receipt. Terminal receipts,
lineage, bindings, and observations are append-only. Later consent withdrawal
still recursively quarantines a successfully registered output through its
inherited lineage.

A small mutable execution gate supplies concurrency arbitration while immutable
claim/cancellation/acknowledgement rows remain the evidence ledger. Gate
booleans are database-constrained to move only `false → true`, and the
cancellation revision is monotonic. Claims, every cancellation source, signed
acknowledgement persistence, and terminalization serialize on the same row, so
PostgreSQL re-evaluates a waiting update against committed gate state instead
of relying on an earlier `READ COMMITTED` snapshot.

Cancellation acknowledgements are workload attestations, not independent proof
that an external process stopped. Their receipts therefore report
`evidencePosture: workload-attested`,
`independentlyVerifiedProcessTermination: false`, and
`productionGateEligible: false`. Provider/orchestrator-authenticated termination
evidence, heartbeat lease monitoring with external liveness verification, and
a termination controller remain mandatory before a managed pilot.

Migration `0015` enforces acknowledgement binding on every new cancelled
terminal but adds its terminal check and foreign key as `NOT VALID` so a legacy
foundation database can migrate without fabricating signatures for historical
rows. Any pre-existing unbound cancelled receipts must be enumerated and
disclosed or quarantined before deployment; they are not upgraded into trusted
evidence.

Migration `0016` adds append-only, canonically signed workload heartbeats for
an active claimed job. Each heartbeat binds the exact tenant, workload, key,
claim, approved envelope, one-time heartbeat ID, strictly next sequence,
runner state, cancellation revision, hashed process reference, and hashed
liveness evidence. `running` is legal only before cancellation at revision
zero. After cancellation, the next heartbeat must report
`cancellation-observed` and bind the gate's current positive revision. A
heartbeat issued before its claim, before the previous heartbeat, or before the
latest cancellation event fails closed.

Heartbeat insertion, cancellation, and terminalization update the same
execution-gate row. This prevents sequence forks, running-state persistence
after a committed cancellation, and heartbeat persistence after a terminal
receipt. Identity/key revocation uses the same monotonic trust gates as claims,
terminals, and acknowledgements. The ledger and its workload-attributed audits
are append-only; authorized owners/reviewers can read only the latest heartbeat.

These records prove only that the claiming workload signed a liveness assertion.
Receipts therefore report `evidencePosture: workload-attested`,
`independentlyVerifiedProcessLiveness: false`, and
`productionGateEligible: false`. No lease expiry, authenticated scheduler,
external process inspection, alert delivery, or automated termination decision
is implemented by the heartbeat ledger.

Migration `0017` adds a database-clock execution lease and append-only liveness
snapshots. Claim persistence starts a configurable 1–300 second lease (90
seconds by default); every accepted heartbeat renews it using database
`CURRENT_TIMESTAMP`, not the workload's signed clock. Owners and reviewers can
request an audited snapshot classified as `awaiting-first-heartbeat`, `fresh`,
`overdue`, `cancellation-pending`, `cancellation-observed`, or `terminal`.
Cancellation observation is current only when the latest heartbeat's revision
equals the execution gate's revision, so a later provider-drift, quarantine, or
operator cancellation returns the job to `cancellation-pending` until the
workload signs a new observation.

Snapshots preserve the lease bounds, latest heartbeat identity/sequence/state,
both heartbeat and gate cancellation revisions, terminal state, and whether an
alert is required. They hard-code external process verification, alert-delivery
evidence, and production eligibility to false. Expiry is detection evidence;
it neither proves process death nor cancels, kills, or reschedules work.

The lease tuple constraint is added `NOT VALID` for upgrade compatibility after
a deterministic backfill from legacy claim and latest-heartbeat timestamps.
New and backfilled service-created rows satisfy it, but a populated deployment
must audit legacy anomalies and validate the constraint before relying on lease
evidence operationally.

Migration `0018` separates scheduler authority from runner authority. A
tenant-scoped `research-job-scheduler` workload signs a bounded dispatch that
binds the exact approved job/envelope, revision, assigned runner, and expiry.
The scheduler attestation must be issued at or after approval, and a runner
claim must be issued at or after the dispatch is durably recorded and before
the signed dispatch expires.
Dispatch insertion rechecks the scheduler key and both scheduler/runner identity
gates, then advances the same execution gate used by claims and cancellation.
Reassignment appends a higher revision and invalidates every earlier dispatch.

Runner claims use signature schema v2 and bind the active dispatch ID/revision.
Claim persistence requires the designated runner, unexpired latest dispatch,
current scheduler identity/key trust, and current runner identity/key trust.
Dispatch, claim, cancellation, and reassignment therefore serialize on the job
gate: a claim cannot race through an assignment change, expired dispatch, or
scheduler revocation. Legacy claim rows remain visible but the new-claim trigger
requires signed dispatch fields and the composite dispatch foreign key.
Runner and scheduler trust gates are acquired through explicit runner-to-scheduler
dependencies in both dispatch and claim persistence so PostgreSQL cannot choose
opposite identity-lock orders for the two operations.

Dispatch receipts report `externalSchedulerLaunchVerified: false` and
`productionGateEligible: false`. They authorize which workload may claim; they
do not prove that a cloud scheduler launched a container, used the requested
image, or isolated its network and credentials.

Migration `0019` adds a separate `research-job-provider` signing purpose and an
append-only launch-attestation boundary. One accepted launch binds the exact
tenant, job, approved envelope, active dispatch/revision, assigned runner,
requested image digest, hashed process reference, hashed execution identity,
and hashed network policy. Issuance must follow durable dispatch recording and
precede dispatch expiry. Persistence rechecks runner, scheduler, and provider
identity/key trust in that lock order and advances the execution gate only while
the job is unclaimed, uncancelled, and nonterminal.

The runner signature remains execution-claim schema v2 because it already binds
the exact dispatch and only one launch may be accepted for that dispatch. Claim
persistence resolves the gate's launch ID, stores it on the immutable claim,
and enforces a composite launch-to-dispatch-to-runner-to-envelope foreign key.
Claims must be issued after launch recording and current provider revocation or
key expiry blocks them. Subsequent heartbeats must use the launch's hashed
process reference; a launched claim's workload cancellation acknowledgement
cannot report `not-started` and must bind that same process hash.

Launch receipts report `launchAttestationVerified: true`,
`externalProviderKeyCustodyVerified: false`, and
`productionGateEligible: false`. The first field means the canonical payload was
verified against the currently registered tenant-scoped key. It does not prove
that AWS, GCP, Azure, or another provider owns that key, that an API call was
made, or that the claimed IAM/network configuration exists. Those statements
require a reviewed provider adapter, provider-native credentials, and deployed
integration evidence.

Migration `0020` adds append-only external termination attestations using the
same narrowly scoped provider workload. A stop attestation binds the immutable
launch and dispatch, claim and assigned runner, approved envelope, launched
process hash, and the exact current effective cancellation revision, sequence,
source, and reason. Issuance must follow the launch, claim, and every cancellation
in the revision. Provider trust and the execution gate are rechecked atomically;
an escalation to a stronger or later cancellation revision invalidates earlier
termination evidence.

A launched cancelled job now requires two independent statements before its
terminal receipt can commit: the runner's current cancellation acknowledgement
and the provider workload's current external stop attestation. Terminal
persistence resolves and stores the external attestation ID, rechecks provider
identity/key trust, and rejects provider revocation after attestation. Legacy
pre-launch claims retain their prior cancellation path. The external receipt
still reports provider-key custody and production eligibility as false: a
registered tenant key is not proof of a real provider API stop until deployed
credentials, process inspection, and integration drills exist.

Migration `0021` adds a fourth least-privilege workload purpose for alert
delivery. A signed delivered receipt binds one immutable alert-required liveness
snapshot by tenant, snapshot, job, claim, status, cancellation revision, and
generation time. It also binds a canonical snapshot hash, hashed channel
reference, and hashed delivery receipt without storing an address, token, or
message body. One receipt is accepted per snapshot; non-alert states, replay,
tampering, chronology violations, and identity/key revocation fail closed.

Liveness snapshots remain append-only. Delivery visibility is derived by joining
the receipt, so inserting evidence cannot rewrite the monitored state or its
canonical hash. Receipts report `authenticatedDeliveryAttestationVerified: true`,
`externalProviderKeyCustodyVerified: false`, and `productionGateEligible: false`.
They prove what the registered tenant key signed, not that an approved recipient
was configured or that a real email, pager, webhook, or incident platform
delivered the alert. Those claims require a destination registry, reviewed
sender adapter, provider-native receipt verification, retries/escalation, and
managed-environment drills.

## Production work still required

- Provision workload private keys in KMS/HSM custody with ceremony, dual
  control, rotation, emergency revocation, and least-privilege database roles;
  the repository contains public-key governance and ephemeral test keys only.
- Connect the launch boundary to one reviewed provider API and provider-native
  credentials, connect termination evidence to real provider process inspection,
  connect alert evidence to an approved destination registry and real sender,
  then add signed logs. Output provider receipts are still not cryptographically
  authenticated.
- Connect signed dataset exports and provider-backed managed-object evidence.
- Validate concurrency, least privilege, schedules, alerts, rollback, and
  incident handling in the managed environment.

Focused tests are in
`packages/platform-data/src/research-job-authorizations.test.ts`.
