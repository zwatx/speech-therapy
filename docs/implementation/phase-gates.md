# Implementation phase gates

This file translates the Lab plan into executable evidence. A gate is complete
only when every required artifact exists and its listed verification passes.
Unchecked items are not implied by adjacent work.

## Gate 0 — de-risk and foundation

- [x] Published product, clinical, technical, model, privacy, and validation plan.
- [x] Monorepo boundary for clinician web and shared clinical domain.
- [x] Versioned pass/analyze/abstain routing policy with focused tests.
- [x] Target eligibility registry separating candidate, research, and audio-only cues; no target is production-validated yet.
- [x] Versioned JSON Schema attempt contract with generated TypeScript and Swift clients plus drift tests.
- [ ] Paid clinical advisory group and named clinical safety lead.
- [ ] Counsel-reviewed intended-use and U.S. regulatory classification memo.
- [ ] Consent/data-flow map approved by privacy counsel.
- [ ] SLP-approved target protocol, error taxonomy, cue library, and claim ledger.
- [ ] Discovery interviews and capture feasibility study completed.
- [ ] Threat model reviewed by an independent security specialist.

Evidence required to advance: signed clinical, privacy, regulatory, product, and
engineering review. Code completion alone cannot close this gate.

## Gate 1 — audio-first vertical slice

- [ ] Authenticated, tenant-isolated clinician portal with persistent storage.
- [x] Postgres tenant/membership schema, immutable consent ledger, append-only audit events, and negative tenant/role integration tests.
- [x] Clerk user + active-organization mapping boundary and independently authorized consent/export/deletion Route Handlers; provider provisioning remains pending.
- [x] Resource-authorized dynamic learner list/detail workspace with role-aware provisioning, immutable consent ledger UI, one-time device enrollment, export/deletion controls, audited reads, and explicit unconfigured/empty/error states.
- [x] Tenant-scoped persisted attempt-review queue with current exact-snapshot
  clinician-review consent, audited authorized and empty reads, consent-renewal
  redaction, deterministic ordering, quality-only copy, and no raw media,
  pronunciation score, or learner feedback. Authenticated browser coverage and
  deployed least-privilege database isolation remain open.
- [x] Clinician-authored immutable practice-dose assignments for the bounded
  candidate-silent foundation exercise, with tenant/role/current-consent gates,
  content registry hashes, versioned supersession, assignment history export,
  token-scoped device fetch, and server-enforced assignment/repetition/retry
  binding on every new attempt. Provider deployment, invalid-token/IP edge
  throttling, managed migration/concurrency proof, and an SLP-approved target
  remain pending.
- [x] Clinician-visible device-access management returns every active grant plus
  bounded deterministic inactive history, derives expiry/consent/revocation
  status from the database clock, exposes no token/hash material, and supports
  explicit idempotent remote revocation with one transition audit. Concurrent
  revocation, large mixed histories, role/tenant denial, consent invalidation,
  expiry, and post-revocation attempt denial are locally tested. Managed
  PostgreSQL concurrency, learner-device invalid-token/IP throttling, and
  deployed browser/API authorization remain open.
- [x] Database-enforced learner-device capacity and rotation: five unique active
  slots per learner are backfilled under a fail-closed migration, stale slots
  are reclaimed, slot collisions retry with a fresh statement, and every token-
  consuming gate requires a live slot. Atomic rotation transfers the exact slot,
  revokes the old token, inserts the one-time replacement, and appends a token-
  free old/new audit link; forced audit failure rolls back the complete change.
  Interrupted-response recovery is explicit. Real PostgreSQL/Neon migration,
  driver constraint metadata, concurrent collision, and HTTP-loss tests remain
  required before deployment.
- [x] Database-backed clinician token-generation limits use fixed UTC-hour
  windows scoped to both tenant/actor (30) and tenant/learner (10), shared by
  issuance and rotation. The two counters are consumed atomically before token
  creation, internal slot retries count once, capacity conflicts count as
  generation attempts, learner-scoped buckets are removed on deletion, and a blocked
  request returns private `429`/`Retry-After`. Revocation is intentionally
  exempt. Real PostgreSQL contention/window-boundary tests and provider-edge
  learner-device/IP throttling remain required before deployment; an operations-
  owned retention job for inactive aggregate buckets also remains open.
- [x] Valid learner-device requests use a separate database table with fixed
  UTC-hour, frozen-policy budgets per tenant/session/operation: 120 assignment
  reads and 120 attempt uploads. Authorization and one counter increment share
  a statement that requires a live slot, unexpired session, undeleted learner,
  exact current consent, audio permission, and valid assent. Plain internal
  resolution and invalid tokens create no bucket; operations do not share
  capacity; exhausted requests return private `429`/`Retry-After`; and the iOS
  client preserves the delay in calm retry copy. Every HTTP retry/idempotent
  replay consumes another request by design; 120 uploads allow one replay for
  every maximum-dose slot (20 repetitions × three attempts). Session deletion
  cascades its buckets. Migration 0025 and contention/revoke/rotation/deletion/
  UTC-rollover behavior still require managed PostgreSQL rehearsal, and trusted
  invalid-token/IP edge controls remain open.
- [x] Native iOS prompt, microphone capture, quality coaching, retry, permission-denial, and camera-off experience.
- [x] Automated accessibility foundation: axe WCAG A/AA checks for desktop,
  keyboard, mobile, reduced-motion and forced-colors web states; native XCTest
  audits for iOS enrollment, assignment loading/no-assignment/error, and ready
  practice; Dynamic Type clipping fixes,
  explicit status announcements, error associations, skip focus, current-page
  navigation, and high-contrast affordances. Physical-device VoiceOver,
  Windows screen readers, switch/voice control, disabled-participant testing,
  and authenticated end-to-end route coverage remain open.
- [x] Keychain-backed learner enrollment persisted only after server
  authentication, current-assignment refresh on restore, consent/assignment-
  bound raw PCM upload, server quality recheck, silent receipt, idempotent
  derived-attempt persistence, bounded dose/retry progression, and temporary-
  media deletion; provider deployment remains pending.
- [x] Clinician-recorded consent and assent flows with versioned snapshots, export, and deletion; caregiver authority verification and counsel approval remain Gate 0 requirements.
- [ ] Constrained phoneme scorer for one or two SLP-approved targets.
- [x] Model-independent constrained CTC phone-path scorer, fail-closed calibration artifacts, split-leakage validation, and analytic reporting harness; encoder and approved targets remain pending.
- [x] Pinned q8 phoneme-CTC benchmark adapter with immutable checkpoint/runtime/vocabulary provenance, real synthetic-audio inference smoke test, and no clinical release claim.
- [x] Off-by-default research-consented learner-to-benchmark connection with quality gating, forced abstention, aggregate append-only evidence, export/deletion propagation, and no learner feedback.
- [x] Canonical open-source bake-off charter/candidate/result contracts, local
  result rebuilding, exact locked primary/reference manifests and roles,
  reference-label/subgroup and numeric-threshold binding, signed rubric-bound
  scorecards, signed full-run/calibration/device evidence, complete locked
  evaluation-manifest envelopes, hard clinical/subgroup/deployment/rights gates, research-only
  weighted ranking, and signed owned-adaptation lineage with speaker/household-
  disjoint training, calibration, and evaluation manifests. Checked-in evidence
  and keys are synthetic; no model is selected for clinical use.
- [x] Persistent research-only artifact lineage registry with exact consent dependencies, inherited dataset → feature/checkpoint/report/deployment lineage, fresh use authorization, and recursive consent/deletion quarantine; external job authorization remains pending.
- [x] Durable subject-specific quarantine action outbox with kind-specific purge/disable/retrain/re-evaluate actions, expiring leases, stable idempotency, bounded retries, dead letters, adapter receipt binding, append-only transition evidence, a provider-neutral Ed25519 verification path, and an audited append-only tenant public-key lifecycle with activation/expiry/rotation/revocation enforcement; production adapters, KMS/HSM custody and ceremony, and scheduling remain pending.
- [x] Audited tenant-scoped quarantine health summary and executable deletion-drill report covering transient-data purge, lineage/event/action completeness, receipt presence, dead letters, and completion time; report is hard-coded local-only and cannot satisfy the Gate 3 production drill.
- [x] Authorized subject exports disclose privacy-minimized retained artifact lineage and subject-specific quarantine/action evidence while excluding provider secrets and other participants' events; counsel review and deployed verification remain pending.
- [x] Audited local alert-evidence snapshots categorize dead letters, expired leases, and overdue work while hard-coding delivery evidence and production eligibility false; authenticated channel delivery, acknowledgement, escalation, and managed-environment tests remain pending.
- [x] Privacy-safe managed-artifact object bindings and append-only existence/digest/access reconciliation evidence with current consent and quarantine-state enforcement; authenticated provider adapters, signed observations, managed locator custody, and scheduling remain pending.
- [x] Hash-bound research-job authorization envelopes with legal input/output transitions, immutable code/config/runner provenance, distinct reviewer attestation, expiry, and fresh consent/artifact/provider-evidence execution checks; cryptographic workload signing, dedicated runner identity, terminal state, and scheduling remain pending.
- [x] Globally one-time append-only research-job execution claims with operator cancellation plus automatic input-quarantine/provider-drift cancellation records and authorized polling; external termination control and scheduling remain pending.
- [x] Append-only succeeded/failed/cancelled research-job receipts with monotonic completion/cancellation arbitration and atomic output artifact, consent-lineage, managed-binding, and initial provider-observation registration; signed provider evidence, independently verified termination, and scheduling remain pending.
- [x] Dedicated tenant-scoped research-runner identities and governed Ed25519 public-key lifecycle with signed one-time execution claims, workload-attributed audits, replay/tamper/staleness/revocation/tenant-isolation enforcement, and no human-actor claim bypass; KMS/HSM custody and managed-environment IAM remain pending.
- [x] Workload-signed terminal attestations bind the exact claim/envelope and succeeded/failed/cancelled evidence; successful outputs, bindings, observations, terminal receipts, and audits are workload-attributed and trust-gate reauthorized atomically. Signed provider receipts and managed key custody remain pending.
- [x] Append-only workload-signed cancellation acknowledgements bind the exact claim/envelope, effective safety-precedence cancellation, monotonic cancellation revision, post-cancellation issuance, termination outcome, and hashed workload evidence; cancelled terminal signatures and receipts bind the exact current acknowledgement/revision and must be issued at or after it, while acknowledgement receipts explicitly deny independent termination verification and production-gate eligibility. Registered external stop attestations are tracked separately; a real provider termination controller and legacy-unbound-row migration audit remain pending.
- [x] Append-only workload-signed heartbeats bind the exact claim/envelope, monotonic sequence/time, hashed process/liveness evidence, and cancellation-aware runner state; shared trust/execution gates reject replay, gaps, revocation, running-after-cancellation, and post-terminal writes. Evidence explicitly denies independent liveness verification and production eligibility; signed logs, managed scheduling, authenticated alerts, and external process inspection remain pending.
- [x] Database-clock execution leases begin atomically with a signed claim and renew only through accepted heartbeats. Append-only audited liveness snapshots distinguish awaiting, fresh, overdue, cancellation-pending/currently-observed, and terminal states while invalidating observations after a stronger cancellation revision. Registered-key alert receipts are joined without mutating snapshots; external process liveness verification and production eligibility remain false. Populated-schema legacy validation and real provider launch/inspection/termination/alert adapters remain pending.
- [x] Separate tenant-scoped scheduler workloads issue append-only signed, expiring, revisioned dispatches for an exact approved envelope and designated runner. Runner claim signatures bind the active dispatch ID/revision; reassignment, expiry, scheduler/runner revocation, substitution, replay, and claim/dispatch races fail closed. Dispatch alone still reports external scheduler launch verification and production eligibility as false; a provider-native cloud launch adapter, managed IAM/network inspection, and dispatch/legacy migration validation remain pending.
- [x] Registered provider-workload keys sign one append-only launch attestation per active dispatch, binding the exact envelope, runner, image digest, and hashed process/IAM/network evidence. The execution gate and immutable claim store the resolved launch ID; provider revocation, chronology, substitution, relaunch/reassignment, and heartbeat process-reference mismatches fail closed. This verifies only a configured tenant-scoped Ed25519 attester: provider-native key custody, real cloud API launch, IAM/network inspection, managed migration validation, authenticated alerts, and real provider termination remain pending, and production eligibility stays false.
- [x] A registered provider workload signs append-only external stop evidence bound to the exact launch/dispatch, claim/runner, process hash, and current effective cancellation revision/sequence/source/reason. A launched cancelled terminal requires both the runner acknowledgement and this external attestation; escalation, substitution, replay, chronology violations, and provider revocation fail closed. Provider-native key custody, real process inspection/API termination, managed concurrency and migration rehearsal, a real alert sender/escalation workflow, and production eligibility remain pending.
- [x] A separate registered alert-delivery workload signs one append-only delivered receipt per immutable alert-required liveness snapshot, binding exact state/cancellation chronology, a canonical snapshot hash, and hashed channel/receipt references. Non-alert substitution, hash/signature tampering, replay, and revocation fail closed; joined visibility never mutates the snapshot. An approved destination registry, real channel sender/provider receipt, retry/escalation workflow, provider-native key custody, managed concurrency testing, and production eligibility remain pending.
- [ ] Locked speaker/household-independent evaluation manifest.
  - [x] Synthetic manifest and bake-off invariants prove exact cohort, shared
    executed head/lexicon/policy/numeric threshold, immutable labels/subgroups,
    signed scoring and full-run/calibration/device evidence, complete manifest
    envelope hash, sample hash, and speaker/household split-leakage
    enforcement.
  - [ ] Representative consented child/SSD manifest is authenticated and locked.
- [ ] False-pass, false-reject, calibration, abstention, subgroup, latency, and cost report.
- [ ] Learner/caregiver/SLP usability findings resolved.

## Gate 2 — supported visual feedback

- [ ] On-device face/mouth quality and landmark extraction.
  - [x] Swappable native extractor boundary, ephemeral front-camera pipeline,
    Apple Vision face/lip landmark feasibility runtime, derived-only framing
    evidence, and accessible camera coaching behind a Debug launch flag.
  - [x] Deterministic tests for no face, multiple faces, framing, pose, mouth
    observability, permission denial, camera-off default, and lifecycle cleanup.
  - [x] Debug-only aggregate feasibility report, explicit JSON export, strict
    cross-platform parser, multi-device/scenario advancement evaluator, and
    executable physical-device protocol with honest residual limitations.
  - [ ] Physical-device lighting/pose/appearance feasibility study and runtime
    latency, memory, thermal, interruption, VoiceOver, and network-capture report.
  - [ ] MediaPipe binary/model provenance and metrics/privacy disposition before
    any production SDK integration.
- [ ] One externally observable cue family with prospective labels.
  - [x] Research-only bilabial-closure observation taxonomy, strict blinded
    double-label/adjudication contract, immutable-rating fixture, and agreement
    report harness.
  - [x] Canonically hashed synthetic manifest harness with speaker/household
    split isolation, prospective-site holdout, current consent and deletion
    authorization, exact annotation binding, and research-only evidence hashes.
  - [ ] SLP-approved label policy, locked prospective manifest, collected labels,
    adjudication, subgroup agreement report, and deletion-lineage evidence.
- [ ] Selective vision routing proven to skip correct and uncertain attempts.
  - [x] Fail-closed evaluator recomputes routes and enforces zero vision for
    correct/uncertain/ineligible attempts plus exact invocation for eligible
    mismatches on synthetic prospective fixtures.
  - [ ] Locked real prospective run passes the predeclared routing thresholds.
- [ ] Evidence-bound SLP-authored feedback templates and retry safeguards.
  - [x] Candidate-only canonical template catalog, exact evidence allow-lists,
    two-retry/two-cue limits, per-attempt cue state, distress/stop handling,
    clinician-review escalation, short-lived research-simulation authorization,
    and static-copy simulation are implemented. Learner eligibility stays false.
  - [ ] Qualified SLP authorship, approved content and population scope, real
    usability/accessibility/utility evidence, and runtime clinician-review and
    rollback integration are complete.
- [ ] Audio-only versus fused comparison shows incremental clinical utility.
  - [x] Hash-bound audio-only versus fused harness reports safety, abstention,
    subgroup, latency, cost, paired discordance, and exact McNemar evidence.
  - [ ] Blinded SLP reference study demonstrates significant incremental utility
    without a safety, subgroup, privacy, or accessibility regression.
- [ ] Unsupported-claim audit reports zero release samples.
  - [x] Executable bounded audit content-hashes the exact nine-scenario cohort
    and rejects unbound/dynamic copy, unsupported diagnosis,
    cause or anatomy claims, evidence mismatch, unsafe cues, retry overflow, and
    ignored stop/distress signals on synthetic candidate samples.
  - [ ] The locked real release sample set passes with zero findings under
    authenticated evidence and independent clinical review.

## Gate 3 — silent clinical pilot

- [ ] Multi-clinic silent deployment with no model-generated corrective feedback.
- [ ] Independent SLP labels, adjudication, and real-world agreement report.
- [ ] Security assessment, penetration test, deletion drill, and incident drill.
- [ ] Target-by-target device, subgroup, reliability, privacy, and cost gates pass.

## Gate 4 — limited feedback pilot

- [ ] Corrective feedback enabled only for approved target/population flags.
- [ ] Prospective safety monitoring, complaints, overrides, and rollback exercised.
- [ ] Feasibility and safety endpoints met over the predeclared pilot period.
- [ ] Regulatory classification and claim set reconfirmed.

## Gate 5 — clinical utility and scale

- [ ] Pre-registered controlled clinical utility study completed.
- [ ] Blinded scoring distinguishes trained-word gains from generalization.
- [ ] Android/device expansion passes the full analytic and safety suite.
- [ ] Enterprise operations, support, quality, accessibility, and integrations verified.
- [ ] Evidence supports every commercial claim and intended population.

## Completion audit

The active goal is complete only after Gate 5 and a requirement-by-requirement
audit against the published Lab plan. No prototype, demo, green build, or single
pilot can substitute for that audit.
