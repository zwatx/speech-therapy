# Identity, consent, audit, export, and deletion persistence

Status: implementation foundation; production provisioning and security review pending

The canonical migrations are in `packages/platform-data/migrations`. They
target Postgres and create tenant, actor, membership, learner, immutable
consent, data-subject request, append-only audit, learner device-session,
derived practice-attempt/benchmark-analysis, and research artifact-lineage
tables.

## Runtime boundary

- Production code creates the Neon HTTP client lazily, only after a protected
  request reaches the data boundary. Builds never require `DATABASE_URL`.
- PGlite runs the same Postgres migration and prepared statements in tests and
  optional local development. PGlite is single-connection and is not approved
  as the production clinical database.
- Clerk supplies a verified user and active Organization. The portal HMACs both
  external IDs with purpose separation, then resolves them to an active internal
  tenant membership. Raw Clerk identifiers are not stored.
- Tenant, actor, and membership provisioning remain provider/operations work.
  Authorized owners and clinicians can create minimal learner records through
  the portal or tenant-scoped API; the UI explicitly discourages birth dates,
  diagnoses, and full legal names.
- Next.js proxy attaches Clerk context to `/api/v1`. Clinician Route Handlers
  independently require an authenticated user, active Organization, mapped
  membership, tenant-scoped query, and allowed role. The learner-attempt Route
  Handler independently requires a consent-bound device grant instead.
- Every clinical page and Server Action independently resolves the active Clerk
  organization to an internal membership. Proxy path matching is not an
  authorization boundary. Learner list/detail reads and provisioning writes
  are role-scoped and append an audit event in the same statement.

## Implemented invariants

- Consent snapshots are immutable, monotonically versioned, and linked through
  `supersedes_snapshot_id`.
- Declined or withdrawn learner assent disables every processing purpose.
- Learner device grants are random 256-bit tokens stored only as SHA-256 hashes,
  expire within 72 hours, bind to the exact latest consent snapshot, and fail
  after consent supersession, withdrawal, expiry, slot release, or learner
  deletion. A partial unique index permits at most five non-null active slots per
  tenant/learner. The migration refuses a populated learner with more than five
  current grants instead of silently dropping access.
- Raw PCM is bounded and inspected in request memory, never inserted into the
  database, and discarded after the response. Practice rows contain only
  consent/session IDs, exercise/protocol IDs, quality measurements, retry
  reasons, status, and an enforced `media_retained = FALSE` marker. Those rows
  are append-only and are included in the learner JSON export.
- Benchmark analysis additionally requires current research-use consent. Its
  append-only row stores only aggregate ambiguous evidence, inference latency,
  and pinned model/configuration provenance. Database checks enforce
  `benchmark-only`, `learner_feedback_eligible = FALSE`, uncalibrated evidence,
  and no error-family claim. Raw audio, frame posteriors, and hypothesis scores
  are never persisted. Analyses are included in exports and cascade with their
  attempt during deletion.
- Visual processing consent is currently rejected at the shared service
  boundary because no visual protocol is approved. The Debug-only native
  feasibility flow processes front-camera sample buffers in memory, emits only
  local framing/pose/mouth-geometry measurements, and does not persist or upload
  frames, landmarks, or derived visual measurements.
- Cross-tenant resource access returns the same access-denied outcome as a
  missing resource.
- Export reads and deletion operations create data-subject receipts and audit
  events in the same Postgres statement as the protected operation.
- Export is a JSON-only `POST`; cross-site navigation cannot create an export
  receipt or place a clinical download on the clinician's device.
- Authorized exports include subject-scoped retained research-artifact impact
  records: artifact kind/version/status, exact consent and processing-purpose
  linkage, and only that learner's quarantine events and action state. They do
  not expose artifact hashes, provider receipt references, idempotency keys,
  worker identity, or another learner's quarantine events. The append-only
  export receipt records the number of disclosed artifact impacts.
- Device-access listing returns every active learner grant and only the 25 most
  recent inactive records. Status is derived at read time from database expiry,
  current consent, and revocation state. Revocation preserves the random-token
  hash for idempotent historical identity, never returns it, and appends exactly
  one transition audit. Rotation clears and transfers the exact source slot,
  revokes the old token, inserts the replacement hash, and appends its old/new
  audit in one statement; any insert/audit failure rolls back all three. The
  replacement token is returned once and never persisted raw. Learner deletion
  still removes the session rows. Migration 0023 and the constraint-name retry
  path still require real PostgreSQL/Neon rehearsal before deployment.
- Device-token issuance and rotation consume the same fixed UTC-hour rate
  budget in `device_access_rate_buckets`: 30 attempts per tenant/actor and 10
  per tenant/learner. One ordered Postgres upsert updates both scopes before a
  token is generated; a blocked response includes the database-derived time to
  the next window. Capacity conflicts consume a request, while internal slot-
  collision retries do not consume again. Revocation never consults this table.
  Buckets contain opaque internal IDs and aggregate counts only—no IP address,
  raw token, token hash, or clinical content. Rows older than 48 hours are
  not yet pruned automatically; learner-scoped rows are deleted immediately
  with the learner, and a bounded operations-owned retention job remains a
  deployment requirement. Migration 0024 and concurrent lock-ordering/window-
  boundary behavior still require managed PostgreSQL rehearsal.
- Valid enrolled-device assignment reads and attempt uploads use
  `learner_device_request_rate_buckets`, keyed by tenant, device session,
  operation, and explicit UTC-hour start. The authorization statement first
  resolves a live exact-consent session, then atomically consumes one frozen
  in-window budget. Assignment and upload capacity are independent; plain
  internal session resolution and invalid tokens do not write. The table stores
  opaque session IDs, aggregate counts, request UUIDs, and timestamps only. A
  composite foreign key cascades rows when the session is deleted. Revoked
  session rows—and therefore their aggregate buckets—remain until ordinary
  retention or learner deletion. Migration 0025, its table-locking unique
  constraint, and concurrency behavior require managed PostgreSQL rehearsal.
- Deletion currently pseudonymizes the learner record, deletes device sessions
  and their derived practice-attempt/analysis rows, and retains consent, audit,
  artifact-lineage, and quarantine evidence as explicitly disclosed by the
  deletion receipt. There is no media store. Registered research datasets and
  every lineage descendant are quarantined transactionally on deletion or
  consent supersession; fresh use authorization rechecks current consent even
  if a status marker is bypassed. The same transaction creates subject-specific
  external-action outbox records. Lease, retry, dead-letter, and receipt
  transitions are durable and audited. A provider-neutral Ed25519 verifier now
  persists provider/key/issuance/signature-hash evidence. An append-only
  tenant-scoped public-key registry enforces activation, expiry, rotation
  overlap, and reasoned revocation at both verifier load and signed-success
  persistence. Only ephemeral private test keys are exercised; production
  provider adapters, reviewed KMS/HSM custody and ceremony, and provider-backed
  receipts remain pending. See
  `docs/model/artifact-registry.md`.
- Authorized owner/reviewer health reads and local deletion-drill reports are
  audited. Local reports can validate database/outbox mechanics but are
  hard-coded as ineligible for production gate evidence.
- Local alert-evidence snapshots categorize overdue, expired, and dead-letter
  states and are audited, but explicitly contain no delivery or acknowledgement
  evidence and cannot close an operations gate.
- Managed research-artifact bindings store provider ID, object-reference hash,
  immutable provider version, and expected digest without URLs, buckets, paths,
  or raw locators. Append-only local observations compare existence, digest, and
  access state against the artifact's current active/quarantined state. No
  authenticated artifact-store adapter, signed provider observation, or managed
  locator mapping is deployed.

## Still required before Gate 1 closes

- Provision Clerk and a managed Postgres environment under reviewed vendor,
  privacy, residency, backup, and incident terms.
- Add a non-owner application database role and database-enforced tenant
  isolation; never connect the application with an owner or `BYPASSRLS` role.
- Provision Clerk sign-in and organization selection under reviewed operations;
  the application already fails closed to a dedicated access state when the
  provider, active organization, membership, or database is unavailable.
- Add caregiver authority records, counsel-approved notice delivery,
  restoration drills, and deployed export/deletion verification.
- Run independent authorization, penetration, privacy, and deletion reviews.
- Have counsel verify that the subject-export categories and retained-record
  descriptions satisfy the deployed jurisdictions and organizational policy.
- Verify the visual feasibility runtime on physical devices, including a
  network capture proving that camera frames and derived features remain local.
