import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, randomUUID, sign } from "node:crypto";
import test from "node:test";

import { ArtifactRegistryService } from "./artifact-registry.ts";
import { PlatformDataError } from "./errors.ts";
import { ManagedArtifactObjectService } from "./managed-artifact-objects.ts";
import { applyFoundationMigration } from "./migrate.ts";
import { PGliteDatabase } from "./pglite.ts";
import {
  canonicalResearchJobExecutionClaimPayload,
  canonicalResearchJobAlertDeliveryPayload,
  canonicalResearchJobExternalTerminationPayload,
  canonicalResearchJobDispatchPayload,
  canonicalResearchJobCancellationAcknowledgementPayload,
  canonicalResearchJobHeartbeatPayload,
  canonicalResearchJobLaunchAttestationPayload,
  canonicalResearchJobLivenessSnapshotPayload,
  canonicalResearchJobTerminalAttestationPayload,
  ResearchJobAuthorizationService,
} from "./research-job-authorizations.ts";
import { ResearchWorkloadIdentityService } from "./research-workload-identities.ts";
import { PlatformDataService } from "./service.ts";
import type {
  ActorContext,
  ResearchJobRequestInput,
  ResearchJobDispatchReceipt,
  ResearchJobLaunchReceipt,
  ResearchJobLivenessSnapshot,
  SignedResearchJobExecutionClaim,
  SignedResearchJobAlertDeliveryAttestation,
  SignedResearchJobExternalTerminationAttestation,
  SignedResearchJobDispatch,
  SignedResearchJobCancellationAcknowledgement,
  SignedResearchJobHeartbeat,
  SignedResearchJobLaunchAttestation,
  SignedResearchJobTerminalAttestation,
} from "./types.ts";

const owner: ActorContext = { actorId: "actor-owner-a", tenantId: "tenant-a", role: "owner" };
const reviewer: ActorContext = { actorId: "actor-reviewer-a", tenantId: "tenant-a", role: "reviewer" };
const clinician: ActorContext = { actorId: "actor-clinician-a", tenantId: "tenant-a", role: "clinician" };
const foreignOwner: ActorContext = { actorId: "actor-owner-b", tenantId: "tenant-b", role: "owner" };
async function fixture(withObservation = true, executionLeaseSeconds = 90) {
  const database = new PGliteDatabase();
  await applyFoundationMigration(database);
  const fixtureNow = new Date();
  const fixtureNowIso = fixtureNow.toISOString();
  await database.query(
    `INSERT INTO tenants (id, display_name, external_organization_hash) VALUES
      ('tenant-a', 'Clinic A', $1), ('tenant-b', 'Clinic B', $2)`,
    ["a".repeat(64), "b".repeat(64)],
  );
  await database.query(
    `INSERT INTO actors (id, external_subject_hash) VALUES
      ('actor-owner-a', $1), ('actor-reviewer-a', $2),
      ('actor-clinician-a', $3), ('actor-owner-b', $4)`,
    ["c".repeat(64), "d".repeat(64), "e".repeat(64), "f".repeat(64)],
  );
  await database.query(
    `INSERT INTO tenant_memberships (tenant_id, actor_id, role) VALUES
      ('tenant-a', 'actor-owner-a', 'owner'),
      ('tenant-a', 'actor-reviewer-a', 'reviewer'),
      ('tenant-a', 'actor-clinician-a', 'clinician'),
      ('tenant-b', 'actor-owner-b', 'owner')`,
  );
  const workloadKeys = generateKeyPairSync("ed25519");
  const schedulerKeys = generateKeyPairSync("ed25519");
  const providerKeys = generateKeyPairSync("ed25519");
  const alertDeliveryKeys = generateKeyPairSync("ed25519");
  const workloads = new ResearchWorkloadIdentityService(database);
  await workloads.registerIdentity(owner, "research-runner-a");
  await workloads.registerSigningKey(owner, {
    workloadId: "research-runner-a",
    signingKeyId: "runner-key-a",
    publicKeyPem: workloadKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(Date.now() - 86_400_000).toISOString(),
    validUntil: new Date(Date.now() + 86_400_000).toISOString(),
  });
  await workloads.registerIdentity(
    owner,
    "research-alert-delivery-a",
    "research-job-alert-delivery",
  );
  await workloads.registerSigningKey(owner, {
    workloadId: "research-alert-delivery-a",
    signingKeyId: "alert-delivery-key-a",
    publicKeyPem: alertDeliveryKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(Date.now() - 86_400_000).toISOString(),
    validUntil: new Date(Date.now() + 86_400_000).toISOString(),
  });
  await workloads.registerIdentity(
    owner,
    "research-provider-a",
    "research-job-provider",
  );
  await workloads.registerSigningKey(owner, {
    workloadId: "research-provider-a",
    signingKeyId: "provider-key-a",
    publicKeyPem: providerKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(Date.now() - 86_400_000).toISOString(),
    validUntil: new Date(Date.now() + 86_400_000).toISOString(),
  });
  await workloads.registerIdentity(
    owner,
    "research-scheduler-a",
    "research-job-scheduler",
  );
  await workloads.registerSigningKey(owner, {
    workloadId: "research-scheduler-a",
    signingKeyId: "scheduler-key-a",
    publicKeyPem: schedulerKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(Date.now() - 86_400_000).toISOString(),
    validUntil: new Date(Date.now() + 86_400_000).toISOString(),
  });
  await database.query(
    "INSERT INTO learners (id, tenant_id, display_label) VALUES ('learner-a', 'tenant-a', 'Learner A')",
  );
  const platform = new PlatformDataService(database);
  const consent = await platform.createConsentSnapshot(clinician, {
    learnerId: "learner-a", noticeVersion: "research-v1",
    audioProcessing: true, videoProcessing: false,
    clinicianReview: true, researchUse: true, assentStatus: "affirmed",
  });
  const artifact = await new ArtifactRegistryService(database).registerDataset(reviewer, {
    artifactId: "dataset-job-v1", kind: "dataset", version: "dataset-v1",
    sha256: "1".repeat(64),
    dependencies: [{ learnerId: "learner-a", consentSnapshotId: consent.id, processingPurpose: "audio-research" }],
  });
  const objects = new ManagedArtifactObjectService(
    database, () => new Date(fixtureNow.getTime() + 30_000),
  );
  const binding = await objects.register(owner, {
    bindingId: "binding-job-v1", artifactId: artifact.id,
    providerId: "provider-test", objectReferenceSha256: "2".repeat(64),
    providerObjectVersion: "immutable:v1",
  });
  if (withObservation) {
    await objects.reconcile(owner, binding.bindingId, {
      inspect: async (claim) => ({
        bindingId: claim.bindingId, providerId: claim.providerId,
        objectReferenceSha256: claim.objectReferenceSha256,
        objectExists: true, observedSha256: claim.expectedSha256,
        accessState: "available", checkedAt: fixtureNowIso,
        receiptReference: "receipt/job-input", receiptSha256: "3".repeat(64),
      }),
    });
  }
  const jobs = new ResearchJobAuthorizationService(
    database, () => new Date(fixtureNow.getTime() + 30_000),
    executionLeaseSeconds,
  );
  async function dispatchAttestation(
    jobId: string,
    assignedWorkloadId = "research-runner-a",
    dispatchOverrides: Partial<SignedResearchJobDispatch["dispatch"]> = {},
  ): Promise<SignedResearchJobDispatch> {
    const context = await database.query<{
      envelope_sha256: string; approved_at: string | Date; dispatch_revision: number;
    }>(
      `SELECT approval.envelope_sha256, approval.approved_at, gate.dispatch_revision
       FROM research_job_approvals AS approval
       INNER JOIN research_job_execution_gates AS gate
         ON gate.job_id = approval.job_id AND gate.tenant_id = approval.tenant_id
       WHERE approval.job_id = $1 AND approval.tenant_id = 'tenant-a'`,
      [jobId],
    );
    const row = context.rows[0];
    assert.ok(row);
    const issuedAt = new Date(new Date(row.approved_at).getTime() + 1);
    const unsigned: Omit<SignedResearchJobDispatch, "signature"> = {
      schemaVersion: "research-job-dispatch-signature-v1",
      tenantId: "tenant-a",
      schedulerWorkloadId: "research-scheduler-a",
      signingKeyId: "scheduler-key-a",
      algorithm: "Ed25519",
      issuedAt: issuedAt.toISOString(),
      dispatch: {
        dispatchId: randomUUID(),
        jobId,
        envelopeSha256: row.envelope_sha256,
        dispatchRevision: Number(row.dispatch_revision) + 1,
        assignedWorkloadId,
        expiresAt: new Date(issuedAt.getTime() + 300_000).toISOString(),
        ...dispatchOverrides,
      },
    };
    const signed: SignedResearchJobDispatch = {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobDispatchPayload(unsigned)),
        schedulerKeys.privateKey,
      ).toString("base64url"),
    };
    return signed;
  }
  async function dispatchJob(
    jobId: string,
    assignedWorkloadId = "research-runner-a",
  ) {
    return jobs.recordDispatch(await dispatchAttestation(jobId, assignedWorkloadId));
  }
  async function launchAttestation(
    dispatch: ResearchJobDispatchReceipt,
    overrides: Partial<SignedResearchJobLaunchAttestation["launch"]> = {},
  ): Promise<SignedResearchJobLaunchAttestation> {
    const requestContext = await database.query<{
      runner_image_digest: string;
    }>(
      `SELECT runner_image_digest FROM research_job_requests
       WHERE id = $1 AND tenant_id = 'tenant-a'`,
      [dispatch.jobId],
    );
    const row = requestContext.rows[0];
    assert.ok(row);
    const unsigned: Omit<SignedResearchJobLaunchAttestation, "signature"> = {
      schemaVersion: "research-job-launch-attestation-signature-v1",
      tenantId: "tenant-a",
      providerWorkloadId: "research-provider-a",
      signingKeyId: "provider-key-a",
      algorithm: "Ed25519",
      issuedAt: new Date(new Date(dispatch.recordedAt).getTime() + 1).toISOString(),
      launch: {
        launchId: randomUUID(),
        jobId: dispatch.jobId,
        envelopeSha256: dispatch.envelopeSha256,
        dispatchId: dispatch.dispatchId,
        dispatchRevision: dispatch.dispatchRevision,
        assignedWorkloadId: dispatch.assignedWorkloadId,
        runnerImageDigest: row.runner_image_digest,
        processReferenceSha256: "c".repeat(64),
        executionIdentitySha256: "d".repeat(64),
        networkPolicySha256: "e".repeat(64),
        ...overrides,
      },
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobLaunchAttestationPayload(unsigned)),
        providerKeys.privateKey,
      ).toString("base64url"),
    };
  }
  async function launchDispatch(
    dispatch: ResearchJobDispatchReceipt,
  ): Promise<ResearchJobLaunchReceipt> {
    return jobs.recordLaunchAttestation(await launchAttestation(dispatch));
  }
  async function executionClaim(
    jobId: string,
    overrides: Partial<Omit<SignedResearchJobExecutionClaim, "signature">> = {},
    dispatchOverride?: Pick<ResearchJobDispatchReceipt,
      "dispatchId" | "dispatchRevision" | "recordedAt" | "jobId"
      | "envelopeSha256" | "assignedWorkloadId">,
    ensureLaunch = true,
  ): Promise<SignedResearchJobExecutionClaim> {
    const approval = await database.query<{ envelope_sha256: string }>(
      `SELECT envelope_sha256 FROM research_job_approvals
       WHERE job_id = $1 AND tenant_id = 'tenant-a'`,
      [jobId],
    );
    const activeDispatch = dispatchOverride === undefined
      ? await database.query<{
        dispatch_id: string; job_id: string; envelope_sha256: string;
        dispatch_revision: number; assigned_workload_id: string;
        expires_at: string | Date; dispatched_by_workload_id: string;
        signing_key_id: string; public_key_sha256: string;
        attestation_issued_at: string | Date;
        attestation_payload_sha256: string; signature_sha256: string;
        recorded_at: string | Date;
      }>(
        `SELECT dispatch.* FROM research_job_execution_gates AS gate
         INNER JOIN research_job_dispatches AS dispatch
           ON dispatch.dispatch_id = gate.active_dispatch_id
          AND dispatch.job_id = gate.job_id AND dispatch.tenant_id = gate.tenant_id
         WHERE gate.job_id = $1 AND gate.tenant_id = 'tenant-a'
           AND NOT gate.claimed AND NOT gate.cancellation_requested`,
        [jobId],
      )
      : undefined;
    const activeRow = activeDispatch?.rows[0];
    const dispatch = dispatchOverride ?? (activeRow ? {
      dispatchId: activeRow.dispatch_id,
      jobId: activeRow.job_id,
      envelopeSha256: activeRow.envelope_sha256,
      dispatchRevision: Number(activeRow.dispatch_revision),
      assignedWorkloadId: activeRow.assigned_workload_id,
      expiresAt: new Date(activeRow.expires_at).toISOString(),
      dispatchedByWorkloadId: activeRow.dispatched_by_workload_id,
      signingKeyId: activeRow.signing_key_id,
      publicKeySha256: activeRow.public_key_sha256,
      issuedAt: new Date(activeRow.attestation_issued_at).toISOString(),
      payloadSha256: activeRow.attestation_payload_sha256,
      signatureSha256: activeRow.signature_sha256,
      recordedAt: new Date(activeRow.recorded_at).toISOString(),
      evidencePosture: "workload-attested" as const,
      externalSchedulerLaunchVerified: false as const,
      productionGateEligible: false as const,
    } : await dispatchJob(jobId));
    let launchRecordedAt: string | undefined;
    if (ensureLaunch) {
      const existing = await database.query<{
        launch_id: string; recorded_at: string | Date;
      }>(
        `SELECT launch_id, recorded_at FROM research_job_launch_attestations
         WHERE dispatch_id = $1 AND tenant_id = 'tenant-a'`,
        [dispatch.dispatchId],
      );
      const existingLaunch = existing.rows[0];
      if (existingLaunch) {
        launchRecordedAt = existingLaunch.recorded_at instanceof Date
          ? existingLaunch.recorded_at.toISOString()
          : existingLaunch.recorded_at;
      } else {
        launchRecordedAt = (
          await launchDispatch(dispatch as ResearchJobDispatchReceipt)
        ).recordedAt;
      }
    }
    const claimIssuedAt = new Date(
      Math.max(
        new Date(dispatch.recordedAt).getTime(),
        launchRecordedAt === undefined ? 0 : new Date(launchRecordedAt).getTime(),
      ) + 1,
    ).toISOString();
    const unsigned = {
      schemaVersion: "research-job-execution-claim-signature-v2" as const,
      tenantId: "tenant-a",
      workloadId: "research-runner-a",
      signingKeyId: "runner-key-a",
      algorithm: "Ed25519" as const,
      issuedAt: claimIssuedAt,
      claimId: randomUUID(),
      jobId,
      envelopeSha256: approval.rows[0]?.envelope_sha256 ?? "0".repeat(64),
      dispatchId: dispatch.dispatchId,
      dispatchRevision: dispatch.dispatchRevision,
      ...overrides,
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobExecutionClaimPayload(unsigned)),
        workloadKeys.privateKey,
      ).toString("base64url"),
    };
  }
  async function claimExecution(jobId: string) {
    return jobs.claimExecution(await executionClaim(jobId));
  }
  async function terminalAttestation(
    terminal: SignedResearchJobTerminalAttestation["terminal"],
    overrides: Partial<Omit<SignedResearchJobTerminalAttestation, "signature" | "terminal">> = {},
  ): Promise<SignedResearchJobTerminalAttestation> {
    const approval = await database.query<{ envelope_sha256: string }>(
      `SELECT envelope_sha256 FROM research_job_approvals
       WHERE job_id = $1 AND tenant_id = 'tenant-a'`,
      [terminal.jobId],
    );
    const cancellationClock = terminal.status === "cancelled"
      ? await database.query<{ recorded_at: string | Date }>(
        `SELECT GREATEST(
           acknowledgement.recorded_at,
           COALESCE(termination.recorded_at, acknowledgement.recorded_at)
         ) AS recorded_at
         FROM research_job_cancellation_acknowledgements AS acknowledgement
         LEFT JOIN research_job_external_termination_attestations AS termination
           ON termination.job_id = acknowledgement.job_id
          AND termination.tenant_id = acknowledgement.tenant_id
          AND termination.claim_id = acknowledgement.claim_id
          AND termination.cancellation_revision = acknowledgement.cancellation_revision
         WHERE acknowledgement.acknowledgement_id = $1
           AND acknowledgement.tenant_id = 'tenant-a'`,
        [terminal.cancellationAcknowledgementId],
      )
      : undefined;
    const terminalIssuedAt = cancellationClock?.rows[0]
      ? new Date(new Date(cancellationClock.rows[0].recorded_at).getTime() + 1).toISOString()
      : fixtureNowIso;
    const unsigned = {
      schemaVersion: "research-job-terminal-signature-v1" as const,
      tenantId: "tenant-a",
      workloadId: "research-runner-a",
      signingKeyId: "runner-key-a",
      algorithm: "Ed25519" as const,
      issuedAt: terminalIssuedAt,
      terminal,
      ...overrides,
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobTerminalAttestationPayload(
          unsigned,
          approval.rows[0]?.envelope_sha256 ?? "0".repeat(64),
        )),
        workloadKeys.privateKey,
      ).toString("base64url"),
    };
  }
  async function recordTerminal(terminal: SignedResearchJobTerminalAttestation["terminal"]) {
    if (terminal.status === "cancelled") {
      const acknowledgement = await database.query<{ acknowledgement_id: string }>(
        `SELECT acknowledgement_id
         FROM research_job_cancellation_acknowledgements
         WHERE acknowledgement_id = $1 AND job_id = $2
           AND tenant_id = 'tenant-a' AND claim_id = $3
           AND cancellation_revision = $4`,
        [terminal.cancellationAcknowledgementId, terminal.jobId,
          terminal.claimId, terminal.cancellationRevision],
      );
      const existing = await database.query<{ termination_attestation_id: string }>(
        `SELECT termination_attestation_id
         FROM research_job_external_termination_attestations
         WHERE job_id = $1 AND tenant_id = 'tenant-a'
           AND claim_id = $2 AND cancellation_revision = $3`,
        [terminal.jobId, terminal.claimId, terminal.cancellationRevision],
      );
      if (acknowledgement.rows[0] && !existing.rows[0]) {
        await jobs.recordExternalTerminationAttestation(
          await externalTerminationAttestation(terminal.jobId, terminal.claimId),
        );
      }
    }
    return jobs.recordTerminal(await terminalAttestation(terminal));
  }
  async function cancellationAcknowledgement(
    jobId: string,
    claimId: string,
    terminationOutcome: "not-started" | "process-stopped" = "process-stopped",
    issuedAtOverride?: string,
  ): Promise<SignedResearchJobCancellationAcknowledgement> {
    const context = await database.query<{
      envelope_sha256: string; cancellation_revision: number; sequence_id: number;
      source: "operator" | "input-quarantined" | "provider-drift";
      reason: "operator-stop" | "incident" | "provider-drift" | "input-quarantined";
      cancelled_at: string | Date;
    }>(
      `SELECT approval.envelope_sha256, gate.cancellation_revision,
         cancellation.sequence_id,
         cancellation.source, cancellation.reason, cancellation.cancelled_at
       FROM research_job_approvals AS approval
       INNER JOIN research_job_execution_gates AS gate
         ON gate.job_id = approval.job_id AND gate.tenant_id = approval.tenant_id
       INNER JOIN LATERAL (
         SELECT * FROM research_job_cancellations
         WHERE job_id = approval.job_id AND tenant_id = approval.tenant_id
         ORDER BY CASE source WHEN 'input-quarantined' THEN 3
           WHEN 'provider-drift' THEN 2 ELSE 1 END DESC, sequence_id DESC LIMIT 1
       ) AS cancellation ON TRUE
       WHERE approval.job_id = $1 AND approval.tenant_id = 'tenant-a'`,
      [jobId],
    );
    const row = context.rows[0];
    assert.ok(row);
    const unsigned = {
      schemaVersion: "research-job-cancellation-acknowledgement-signature-v1" as const,
      tenantId: "tenant-a",
      workloadId: "research-runner-a",
      signingKeyId: "runner-key-a",
      algorithm: "Ed25519" as const,
      issuedAt: issuedAtOverride ?? new Date(
        new Date(row.cancelled_at).getTime() + 1,
      ).toISOString(),
      acknowledgement: {
        jobId,
        claimId,
        cancellationRevision: Number(row.cancellation_revision),
        cancellationSequenceId: Number(row.sequence_id),
        cancellationSource: row.source,
        cancellationReason: row.reason,
        terminationOutcome,
        ...(terminationOutcome === "process-stopped" ? {
          processReferenceSha256: "c".repeat(64),
        } : {}),
        terminationEvidenceSha256: "b".repeat(64),
      },
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobCancellationAcknowledgementPayload(
          unsigned,
          row.envelope_sha256,
        )),
        workloadKeys.privateKey,
      ).toString("base64url"),
    };
  }
  async function heartbeat(
    jobId: string,
    claimId: string,
    heartbeatSequence: number,
    runnerState: "running" | "cancellation-observed" = "running",
    cancellationRevision = runnerState === "running" ? 0 : 1,
    issuedAtOverride?: string,
    heartbeatOverrides: Partial<SignedResearchJobHeartbeat["heartbeat"]> = {},
  ): Promise<SignedResearchJobHeartbeat> {
    const context = await database.query<{
      envelope_sha256: string;
      claimed_at: string | Date;
      cancelled_at: string | Date | null;
    }>(
      `SELECT approval.envelope_sha256, claim.claimed_at,
         cancellation.cancelled_at
       FROM research_job_approvals AS approval
       INNER JOIN research_job_execution_claims AS claim
         ON claim.job_id = approval.job_id AND claim.tenant_id = approval.tenant_id
       LEFT JOIN LATERAL (
         SELECT cancelled_at FROM research_job_cancellations
         WHERE job_id = approval.job_id AND tenant_id = approval.tenant_id
         ORDER BY cancelled_at DESC, sequence_id DESC LIMIT 1
       ) AS cancellation ON TRUE
       WHERE approval.job_id = $1 AND approval.tenant_id = 'tenant-a'
         AND claim.claim_id = $2`,
      [jobId, claimId],
    );
    const row = context.rows[0];
    assert.ok(row);
    const evidenceTime = Math.max(
      new Date(row.claimed_at).getTime(),
      row.cancelled_at === null ? 0 : new Date(row.cancelled_at).getTime(),
    ) + 1;
    const unsigned = {
      schemaVersion: "research-job-heartbeat-signature-v1" as const,
      tenantId: "tenant-a",
      workloadId: "research-runner-a",
      signingKeyId: "runner-key-a",
      algorithm: "Ed25519" as const,
      issuedAt: issuedAtOverride ?? new Date(evidenceTime).toISOString(),
      heartbeat: {
        heartbeatId: randomUUID(),
        jobId,
        claimId,
        heartbeatSequence,
        runnerState,
        cancellationRevision,
        processReferenceSha256: "c".repeat(64),
        livenessEvidenceSha256: "d".repeat(64),
        ...heartbeatOverrides,
      },
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobHeartbeatPayload(
          unsigned,
          row.envelope_sha256,
        )),
        workloadKeys.privateKey,
      ).toString("base64url"),
    };
  }
  async function externalTerminationAttestation(
    jobId: string,
    claimId: string,
    overrides: Partial<
      SignedResearchJobExternalTerminationAttestation["termination"]
    > = {},
    issuedAtOverride?: string,
  ): Promise<SignedResearchJobExternalTerminationAttestation> {
    const context = await database.query<{
      envelope_sha256: string; launch_id: string; dispatch_id: string;
      dispatch_revision: number; claimed_by_workload_id: string;
      process_reference_sha256: string; cancellation_revision: number;
      sequence_id: number;
      source: "operator" | "input-quarantined" | "provider-drift";
      reason: "operator-stop" | "incident" | "provider-drift" | "input-quarantined";
      cancelled_at: string | Date; latest_cancelled_at: string | Date;
      launch_recorded_at: string | Date;
    }>(
      `SELECT claim.envelope_sha256, claim.launch_id, claim.dispatch_id,
         claim.dispatch_revision, claim.claimed_by_workload_id,
         launch.process_reference_sha256, gate.cancellation_revision,
         cancellation.sequence_id, cancellation.source, cancellation.reason,
         cancellation.cancelled_at, latest.cancelled_at AS latest_cancelled_at,
         launch.recorded_at AS launch_recorded_at
       FROM research_job_execution_claims AS claim
       INNER JOIN research_job_launch_attestations AS launch
         ON launch.launch_id = claim.launch_id
        AND launch.job_id = claim.job_id AND launch.tenant_id = claim.tenant_id
       INNER JOIN research_job_execution_gates AS gate
         ON gate.job_id = claim.job_id AND gate.tenant_id = claim.tenant_id
       INNER JOIN LATERAL (
         SELECT * FROM research_job_cancellations
         WHERE job_id = claim.job_id AND tenant_id = claim.tenant_id
         ORDER BY CASE source WHEN 'input-quarantined' THEN 3
           WHEN 'provider-drift' THEN 2 ELSE 1 END DESC,
           cancelled_at DESC, sequence_id DESC LIMIT 1
       ) AS cancellation ON TRUE
       INNER JOIN LATERAL (
         SELECT MAX(cancelled_at) AS cancelled_at FROM research_job_cancellations
         WHERE job_id = claim.job_id AND tenant_id = claim.tenant_id
       ) AS latest ON TRUE
       WHERE claim.job_id = $1 AND claim.tenant_id = 'tenant-a'
         AND claim.claim_id = $2`,
      [jobId, claimId],
    );
    const row = context.rows[0];
    assert.ok(row);
    const evidenceTime = Math.max(
      new Date(row.cancelled_at).getTime(),
      new Date(row.latest_cancelled_at).getTime(),
      new Date(row.launch_recorded_at).getTime(),
    ) + 1;
    const unsigned: Omit<
      SignedResearchJobExternalTerminationAttestation,
      "signature"
    > = {
      schemaVersion: "research-job-external-termination-signature-v1",
      tenantId: "tenant-a",
      providerWorkloadId: "research-provider-a",
      signingKeyId: "provider-key-a",
      algorithm: "Ed25519",
      issuedAt: issuedAtOverride ?? new Date(evidenceTime).toISOString(),
      termination: {
        terminationAttestationId: randomUUID(),
        jobId,
        claimId,
        envelopeSha256: row.envelope_sha256,
        launchId: row.launch_id,
        dispatchId: row.dispatch_id,
        dispatchRevision: Number(row.dispatch_revision),
        assignedWorkloadId: row.claimed_by_workload_id,
        cancellationRevision: Number(row.cancellation_revision),
        cancellationSequenceId: Number(row.sequence_id),
        cancellationSource: row.source,
        cancellationReason: row.reason,
        outcome: "process-stopped",
        processReferenceSha256: row.process_reference_sha256,
        terminationEvidenceSha256: "f".repeat(64),
        ...overrides,
      },
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobExternalTerminationPayload(unsigned)),
        providerKeys.privateKey,
      ).toString("base64url"),
    };
  }
  async function alertDeliveryAttestation(
    snapshot: ResearchJobLivenessSnapshot,
    overrides: Partial<SignedResearchJobAlertDeliveryAttestation["delivery"]> = {},
  ): Promise<SignedResearchJobAlertDeliveryAttestation> {
    const unsigned: Omit<SignedResearchJobAlertDeliveryAttestation, "signature"> = {
      schemaVersion: "research-job-alert-delivery-signature-v1",
      tenantId: "tenant-a",
      alertDeliveryWorkloadId: "research-alert-delivery-a",
      signingKeyId: "alert-delivery-key-a",
      algorithm: "Ed25519",
      issuedAt: new Date(new Date(snapshot.generatedAt).getTime() + 1).toISOString(),
      delivery: {
        deliveryId: randomUUID(),
        snapshotId: snapshot.snapshotId,
        jobId: snapshot.jobId,
        claimId: snapshot.claimId,
        snapshotStatus: snapshot.status as SignedResearchJobAlertDeliveryAttestation["delivery"]["snapshotStatus"],
        cancellationRevision: snapshot.cancellationRevision,
        snapshotGeneratedAt: snapshot.generatedAt,
        snapshotPayloadSha256: createHash("sha256")
          .update(canonicalResearchJobLivenessSnapshotPayload(snapshot))
          .digest("hex"),
        channelReferenceSha256: "8".repeat(64),
        deliveryReceiptSha256: "9".repeat(64),
        outcome: "delivered",
        ...overrides,
      },
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobAlertDeliveryPayload(unsigned)),
        alertDeliveryKeys.privateKey,
      ).toString("base64url"),
    };
  }
  return {
    database, platform, artifact, binding, objects, jobs, workloads,
    workloadKeys, schedulerKeys, providerKeys, alertDeliveryKeys,
    dispatchAttestation, dispatchJob,
    launchAttestation, launchDispatch,
    executionClaim, claimExecution,
    terminalAttestation, recordTerminal,
    cancellationAcknowledgement, heartbeat, externalTerminationAttestation,
    alertDeliveryAttestation,
  };
}

function request(overrides: Partial<ResearchJobRequestInput> = {}): ResearchJobRequestInput {
  return {
    jobId: "research-job-v1",
    jobType: "training",
    inputs: [{ artifactId: "dataset-job-v1", bindingId: "binding-job-v1" }],
    outputKind: "checkpoint",
    outputId: "checkpoint-job-v1",
    outputVersion: "checkpoint-v1",
    codeRevision: "a".repeat(40),
    configurationSha256: "b".repeat(64),
    runnerImageDigest: `sha256:${"c".repeat(64)}`,
    intendedUse: "Research-only acoustic checkpoint bake-off.",
    exclusions: ["No learner feedback", "No clinical deployment"],
    // Stay inside the issuance window without tying fixtures to a calendar date.
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
    ...overrides,
  };
}

function successfulTerminal(jobId: string, claimId: string) {
  return {
    jobId,
    claimId,
    status: "succeeded" as const,
    outputSha256: "4".repeat(64),
    bindingId: `binding-output-${jobId}`,
    providerId: "provider-test",
    objectReferenceSha256: "5".repeat(64),
    providerObjectVersion: "immutable:output-v1",
    providerCheckedAt: new Date().toISOString(),
    providerReceiptReference: `receipt/${jobId}/output`,
    providerReceiptSha256: "6".repeat(64),
  };
}

test("distinct review approves a reproducible research-only envelope and execution rechecks inputs", async (t) => {
  const { database, platform, jobs, claimExecution, executionClaim } = await fixture();
  t.after(() => database.close());

  await assert.rejects(
    jobs.request(clinician, request()),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    jobs.request(foreignOwner, request()),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    jobs.request(reviewer, request({
      jobId: "research-job-long-output",
      outputId: "o".repeat(65),
    })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  const draft = await jobs.request(reviewer, request());
  assert.equal(draft.approvalPosture, "pending");
  assert.equal(draft.cryptographicSignaturePresent, false);
  assert.equal(draft.productionGateEligible, false);
  assert.equal(draft.inputs[0]?.artifactSha256, "1".repeat(64));
  assert.doesNotMatch(JSON.stringify(draft), /learner-a/);
  await assert.rejects(
    jobs.request(reviewer, request({
      jobId: "research-job-duplicate-output",
    })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    jobs.request(reviewer, request({
      jobId: "research-job-existing-output",
      outputId: "dataset-job-v1",
    })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    jobs.approve(reviewer, draft.jobId),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );

  const approved = await jobs.approve(owner, draft.jobId);
  assert.equal(approved.approvalPosture, "database-attested");
  assert.equal(approved.approvedByActorId, owner.actorId);
  assert.match(approved.envelopeSha256 ?? "", /^[a-f0-9]{64}$/);
  const claim = await claimExecution(draft.jobId);
  assert.equal(claim.envelopeSha256, approved.envelopeSha256);
  assert.equal(claim.claimedByActorId, undefined);
  assert.equal(claim.claimedByWorkloadId, "research-runner-a");
  assert.equal(claim.signatureVerification?.signingKeyId, "runner-key-a");
  assert.equal(claim.signatureVerification?.algorithm, "Ed25519");
  assert.match(claim.signatureVerification?.payloadSha256 ?? "", /^[a-f0-9]{64}$/);
  assert.match(claim.signatureVerification?.signatureSha256 ?? "", /^[a-f0-9]{64}$/);
  const workloadAudit = await database.query<{
    actor_id: string | null; workload_id: string | null;
  }>(
    `SELECT actor_id, workload_id FROM audit_events
     WHERE action = 'research-job.execution-claimed'`,
  );
  assert.deepEqual(workloadAudit.rows, [{
    actor_id: null, workload_id: "research-runner-a",
  }]);
  await assert.rejects(
    database.query(
      `INSERT INTO research_job_execution_claims (
         claim_id, job_id, tenant_id, envelope_sha256, claimed_by_actor_id
       ) VALUES ('human-claim-bypass', $1, 'tenant-a', $2, 'actor-owner-a')`,
      [draft.jobId, approved.envelopeSha256],
    ),
    /signed provider-launched workload identity/,
  );
  assert.equal(claim.cancellationObservedAtClaim, false);
  assert.equal(claim.cancellationPollingRequired, true);
  assert.equal(claim.productionGateEligible, false);
  await assert.rejects(
    async () => jobs.claimExecution(await executionClaim(draft.jobId)),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  assert.equal((await jobs.getExecutionState(owner, draft.jobId)).cancellationRequested, false);

  await platform.deleteLearner(owner, "learner-a");
  const cancelled = await jobs.getExecutionState(reviewer, draft.jobId);
  assert.equal(cancelled.cancellationRequested, true);
  assert.equal(cancelled.cancellationSource, "input-quarantined");
  assert.equal(cancelled.cancellationReason, "input-quarantined");
  await assert.rejects(
    async () => jobs.authorizeExecution(await executionClaim(draft.jobId)),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    database.query("UPDATE research_job_approvals SET envelope_sha256 = $1", ["f".repeat(64)]),
    /append-only/,
  );
  const audits = await database.query<{ action: string; count: number }>(
    `SELECT action, COUNT(*)::INTEGER AS count FROM audit_events
     WHERE action LIKE 'research-job.%' GROUP BY action ORDER BY action`,
  );
  assert.deepEqual(audits.rows, [
    { action: "research-job.approved", count: 1 },
    { action: "research-job.dispatched", count: 1 },
    { action: "research-job.execution-claimed", count: 1 },
    { action: "research-job.launch-attested", count: 1 },
    { action: "research-job.requested", count: 1 },
  ]);
});

test("research job expiry accepts only the five-minute to 24-hour issuance window", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  const issuedAt = new Date();
  const jobs = new ResearchJobAuthorizationService(context.database, () => issuedAt);
  for (const offset of [-60_000, 300_000 - 1, 86_400_000 + 1]) {
    await assert.rejects(
      jobs.request(reviewer, request({
        expiresAt: new Date(issuedAt.getTime() + offset).toISOString(),
      })),
      (error: unknown) => error instanceof PlatformDataError
        && error.code === "invalid-artifact"
        && /expiry must be 5 minutes to 24 hours/.test(error.message),
    );
  }
  for (const offset of [300_000, 86_400_000]) {
    const expiresAt = new Date(issuedAt.getTime() + offset).toISOString();
    const envelope = await jobs.request(reviewer, request({
      jobId: `research-job-expiry-${offset}`,
      outputId: `checkpoint-expiry-${offset}`,
      expiresAt,
    }));
    assert.equal(envelope.expiresAt, expiresAt);
  }
});

test("operator cancellation blocks unclaimed jobs and remains append-only", async (t) => {
  const { database, jobs, executionClaim } = await fixture();
  t.after(() => database.close());
  await jobs.request(reviewer, request({
    jobId: "research-job-cancelled",
    outputId: "checkpoint-cancelled",
  }));
  await jobs.approve(owner, "research-job-cancelled");
  await assert.rejects(
    jobs.cancel(clinician, "research-job-cancelled", "operator-stop"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const cancellation = await jobs.cancel(reviewer, "research-job-cancelled", "incident");
  assert.deepEqual(cancellation, {
    jobId: "research-job-cancelled",
    cancellationRequested: true,
  });
  await assert.rejects(
    async () => jobs.claimExecution(await executionClaim("research-job-cancelled")),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    jobs.cancel(owner, "research-job-cancelled", "operator-stop"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    database.query("DELETE FROM research_job_cancellations"),
    /append-only/,
  );
});

test("signed scheduler dispatches bind claims to the latest assigned workload", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-dispatch",
    outputId: "checkpoint-dispatch",
  }));
  await context.jobs.approve(owner, "research-job-dispatch");
  const signed = await context.dispatchAttestation("research-job-dispatch");
  const replacement = signed.signature[0] === "A" ? "B" : "A";
  await assert.rejects(
    context.jobs.recordDispatch({
      ...signed,
      signature: `${replacement}${signed.signature.slice(1)}`,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  const first = await context.jobs.recordDispatch(signed);
  assert.equal(first.dispatchRevision, 1);
  assert.equal(first.assignedWorkloadId, "research-runner-a");
  assert.equal(first.dispatchedByWorkloadId, "research-scheduler-a");
  assert.equal(first.externalSchedulerLaunchVerified, false);
  assert.equal(first.productionGateEligible, false);
  await assert.rejects(
    context.jobs.recordDispatch(signed),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const staleClaim = await context.executionClaim(
    "research-job-dispatch",
    {},
    first,
    false,
  );
  const second = await context.dispatchJob("research-job-dispatch");
  assert.equal(second.dispatchRevision, 2);
  await assert.rejects(
    context.jobs.claimExecution(staleClaim),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const claim = await context.jobs.claimExecution(
    await context.executionClaim("research-job-dispatch", {}, second),
  );
  assert.equal(claim.dispatchId, second.dispatchId);
  assert.equal(claim.dispatchRevision, 2);
  await assert.rejects(
    context.database.query("DELETE FROM research_job_dispatches"),
    /append-only/,
  );
  const audits = await context.database.query<{ action: string; count: number }>(
    `SELECT action, COUNT(*)::INTEGER AS count FROM audit_events
     WHERE resource_id = 'research-job-dispatch'
       AND action IN ('research-job.dispatched', 'research-job.execution-claimed')
     GROUP BY action ORDER BY action`,
  );
  assert.deepEqual(audits.rows, [
    { action: "research-job.dispatched", count: 2 },
    { action: "research-job.execution-claimed", count: 1 },
  ]);
});

test("dispatch expiry, runner substitution, and scheduler revocation fail closed", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-dispatch-negative",
    outputId: "checkpoint-dispatch-negative",
  }));
  await context.jobs.approve(owner, "research-job-dispatch-negative");
  await assert.rejects(
    context.jobs.recordDispatch(await context.dispatchAttestation(
      "research-job-dispatch-negative",
      "research-runner-a",
      { expiresAt: new Date(Date.now() - 60_000).toISOString() },
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  const shortExpiry = new Date(Date.now() + 40_000).toISOString();
  const shortDispatch = await context.jobs.recordDispatch(
    await context.dispatchAttestation(
      "research-job-dispatch-negative",
      "research-runner-a",
      { expiresAt: shortExpiry },
    ),
  );
  await assert.rejects(
    context.jobs.claimExecution(await context.executionClaim(
      "research-job-dispatch-negative",
      { issuedAt: new Date(new Date(shortExpiry).getTime() + 1).toISOString() },
      shortDispatch,
      false,
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await context.workloads.registerIdentity(owner, "research-runner-two");
  const wrongRunnerDispatch = await context.dispatchJob(
    "research-job-dispatch-negative",
    "research-runner-two",
  );
  await assert.rejects(
    context.jobs.claimExecution(await context.executionClaim(
      "research-job-dispatch-negative",
      {},
      wrongRunnerDispatch,
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );

  const revoked = await fixture();
  t.after(() => revoked.database.close());
  await revoked.jobs.request(reviewer, request({
    jobId: "research-job-dispatch-revoked",
    outputId: "checkpoint-dispatch-revoked",
  }));
  await revoked.jobs.approve(owner, "research-job-dispatch-revoked");
  const dispatch = await revoked.dispatchJob("research-job-dispatch-revoked");
  const claim = await revoked.executionClaim("research-job-dispatch-revoked", {}, dispatch);
  await revoked.workloads.revokeSigningKey(
    owner,
    "research-scheduler-a",
    "scheduler-key-a",
    "compromised",
  );
  await assert.rejects(
    revoked.jobs.claimExecution(claim),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const persisted = await revoked.database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM research_job_execution_claims
     WHERE job_id = 'research-job-dispatch-revoked'`,
  );
  assert.equal(persisted.rows[0]?.count, 0);
});

test("provider launch attestations bind image, dispatch, process, and current trust", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-launch",
    outputId: "checkpoint-launch",
  }));
  await context.jobs.approve(owner, "research-job-launch");
  const dispatch = await context.dispatchJob("research-job-launch");
  const signed = await context.launchAttestation(dispatch);
  const replacement = signed.signature[0] === "A" ? "B" : "A";
  await assert.rejects(
    context.jobs.recordLaunchAttestation({
      ...signed,
      signature: `${replacement}${signed.signature.slice(1)}`,
    }),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "invalid-artifact",
  );
  await assert.rejects(
    context.jobs.recordLaunchAttestation(await context.launchAttestation(
      dispatch,
      { runnerImageDigest: `sha256:${"f".repeat(64)}` },
    )),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  const launch = await context.jobs.recordLaunchAttestation(signed);
  assert.equal(launch.dispatchId, dispatch.dispatchId);
  assert.equal(launch.assignedWorkloadId, "research-runner-a");
  assert.equal(launch.processReferenceSha256, "c".repeat(64));
  assert.equal(launch.launchAttestationVerified, true);
  assert.equal(launch.externalProviderKeyCustodyVerified, false);
  assert.equal(launch.productionGateEligible, false);
  await assert.rejects(
    context.jobs.recordLaunchAttestation(await context.launchAttestation(dispatch)),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  await assert.rejects(
    context.dispatchJob("research-job-launch"),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  const claim = await context.jobs.claimExecution(
    await context.executionClaim("research-job-launch", {}, dispatch),
  );
  assert.equal(claim.launchId, launch.launchId);
  assert.equal(
    (await context.jobs.getExecutionState(owner, "research-job-launch"))?.launchId,
    launch.launchId,
  );
  await assert.rejects(
    context.jobs.recordHeartbeat(await context.heartbeat(
      "research-job-launch",
      claim.claimId,
      1,
      "running",
      0,
      undefined,
      { processReferenceSha256: "f".repeat(64) },
    )),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  await assert.rejects(
    context.database.query("DELETE FROM research_job_launch_attestations"),
    /append-only/,
  );

  const revoked = await fixture();
  t.after(() => revoked.database.close());
  await revoked.jobs.request(reviewer, request({
    jobId: "research-job-launch-revoked",
    outputId: "checkpoint-launch-revoked",
  }));
  await revoked.jobs.approve(owner, "research-job-launch-revoked");
  const revokedDispatch = await revoked.dispatchJob("research-job-launch-revoked");
  await revoked.launchDispatch(revokedDispatch);
  const preSignedClaim = await revoked.executionClaim(
    "research-job-launch-revoked",
    {},
    revokedDispatch,
  );
  await revoked.workloads.revokeSigningKey(
    owner,
    "research-provider-a",
    "provider-key-a",
    "compromised",
  );
  await assert.rejects(
    revoked.jobs.claimExecution(preSignedClaim),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  const persisted = await revoked.database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM research_job_execution_claims
     WHERE job_id = 'research-job-launch-revoked'`,
  );
  assert.equal(persisted.rows[0]?.count, 0);
});

test("external termination binds the current cancellation and gates cancelled terminal state", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-external-termination",
    outputId: "checkpoint-external-termination",
  }));
  await context.jobs.approve(owner, "research-job-external-termination");
  const claim = await context.claimExecution("research-job-external-termination");
  await context.jobs.cancel(owner, "research-job-external-termination", "operator-stop");
  const acknowledgement = await context.jobs.acknowledgeCancellation(
    await context.cancellationAcknowledgement(
      "research-job-external-termination",
      claim.claimId,
    ),
  );
  const terminalInput = {
    jobId: "research-job-external-termination",
    claimId: claim.claimId,
    status: "cancelled" as const,
    failureCode: "cancellation-observed" as const,
    failureDetailSha256: "a".repeat(64),
    cancellationAcknowledgementId: acknowledgement.acknowledgementId,
    cancellationRevision: acknowledgement.cancellationRevision,
  };
  await assert.rejects(
    context.jobs.recordTerminal(await context.terminalAttestation(terminalInput)),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  const signed = await context.externalTerminationAttestation(
    "research-job-external-termination",
    claim.claimId,
  );
  const replacement = signed.signature[0] === "A" ? "B" : "A";
  await assert.rejects(
    context.jobs.recordExternalTerminationAttestation({
      ...signed,
      signature: `${replacement}${signed.signature.slice(1)}`,
    }),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "invalid-artifact",
  );
  await assert.rejects(
    context.jobs.recordExternalTerminationAttestation(
      await context.externalTerminationAttestation(
        "research-job-external-termination",
        claim.claimId,
        { processReferenceSha256: "9".repeat(64) },
      ),
    ),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  const termination = await context.jobs.recordExternalTerminationAttestation(signed);
  assert.equal(termination.claimId, claim.claimId);
  assert.equal(termination.launchId, claim.launchId);
  assert.equal(termination.cancellationRevision, 1);
  assert.equal(termination.externalTerminationAttestationVerified, true);
  assert.equal(termination.externalProviderKeyCustodyVerified, false);
  assert.equal(termination.productionGateEligible, false);
  await assert.rejects(
    context.jobs.recordExternalTerminationAttestation(signed),
    (error: unknown) => error instanceof PlatformDataError
      && ["conflict", "access-denied"].includes(error.code),
  );
  const terminal = await context.recordTerminal(terminalInput);
  assert.equal(
    terminal.externalTerminationAttestationId,
    termination.terminationAttestationId,
  );
  await assert.rejects(
    context.database.query("DELETE FROM research_job_external_termination_attestations"),
    /append-only/,
  );

  const revoked = await fixture();
  t.after(() => revoked.database.close());
  await revoked.jobs.request(reviewer, request({
    jobId: "research-job-termination-revoked",
    outputId: "checkpoint-termination-revoked",
  }));
  await revoked.jobs.approve(owner, "research-job-termination-revoked");
  const revokedClaim = await revoked.claimExecution("research-job-termination-revoked");
  await revoked.jobs.cancel(owner, "research-job-termination-revoked", "operator-stop");
  const revokedAck = await revoked.jobs.acknowledgeCancellation(
    await revoked.cancellationAcknowledgement(
      "research-job-termination-revoked",
      revokedClaim.claimId,
    ),
  );
  await revoked.jobs.recordExternalTerminationAttestation(
    await revoked.externalTerminationAttestation(
      "research-job-termination-revoked",
      revokedClaim.claimId,
    ),
  );
  await revoked.workloads.revokeSigningKey(
    owner,
    "research-provider-a",
    "provider-key-a",
    "compromised",
  );
  await assert.rejects(
    revoked.recordTerminal({
      jobId: "research-job-termination-revoked",
      claimId: revokedClaim.claimId,
      status: "cancelled",
      failureCode: "cancellation-observed",
      failureDetailSha256: "b".repeat(64),
      cancellationAcknowledgementId: revokedAck.acknowledgementId,
      cancellationRevision: revokedAck.cancellationRevision,
    }),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
});

test("concurrent claim and cancellation serialize to a safe pollable result", async (t) => {
  const { database, jobs, claimExecution } = await fixture();
  t.after(() => database.close());
  await jobs.request(reviewer, request({
    jobId: "research-job-race",
    outputId: "checkpoint-race",
  }));
  await jobs.approve(owner, "research-job-race");
  const [claimResult, cancelResult] = await Promise.allSettled([
    claimExecution("research-job-race"),
    jobs.cancel(owner, "research-job-race", "operator-stop"),
  ]);
  assert.equal(cancelResult.status, "fulfilled");
  const counts = await database.query<{ claims: number; cancellations: number }>(
    `SELECT
       (SELECT COUNT(*)::INTEGER FROM research_job_execution_claims
        WHERE job_id = 'research-job-race') AS claims,
       (SELECT COUNT(*)::INTEGER FROM research_job_cancellations
        WHERE job_id = 'research-job-race') AS cancellations`,
  );
  assert.equal(counts.rows[0]?.cancellations, 1);
  assert.ok((counts.rows[0]?.claims ?? 0) <= 1);
  const gate = await database.query<{ claimed: boolean; cancellation_requested: boolean }>(
    `SELECT claimed, cancellation_requested FROM research_job_execution_gates
     WHERE job_id = 'research-job-race'`,
  );
  assert.equal(gate.rows[0]?.cancellation_requested, true);
  assert.equal(gate.rows[0]?.claimed, counts.rows[0]?.claims === 1);
  if (claimResult.status === "fulfilled") {
    assert.equal(claimResult.value.cancellationPollingRequired, true);
    assert.equal(
      (await jobs.getExecutionState(owner, "research-job-race")).cancellationRequested,
      true,
    );
  } else {
    assert.ok(claimResult.reason instanceof PlatformDataError);
  }
  await assert.rejects(
    database.query(
      `UPDATE research_job_execution_gates
       SET cancellation_requested = FALSE WHERE job_id = 'research-job-race'`,
    ),
    /monotonic/,
  );
});

test("provider drift and later input quarantine both remain visible with safety precedence", async (t) => {
  const { database, jobs, objects, binding, platform, claimExecution } = await fixture();
  t.after(() => database.close());
  await jobs.request(reviewer, request({
    jobId: "research-job-provider-drift",
    outputId: "checkpoint-provider-drift",
  }));
  await jobs.approve(owner, "research-job-provider-drift");
  await claimExecution("research-job-provider-drift");
  await objects.reconcile(owner, binding.bindingId, {
    inspect: async (claim) => ({
      bindingId: claim.bindingId,
      providerId: claim.providerId,
      objectReferenceSha256: claim.objectReferenceSha256,
      objectExists: true,
      observedSha256: "9".repeat(64),
      accessState: "available",
      checkedAt: new Date().toISOString(),
      receiptReference: "receipt/provider-drift-cancel",
      receiptSha256: "7".repeat(64),
    }),
  });
  const state = await jobs.getExecutionState(owner, "research-job-provider-drift");
  assert.equal(state.cancellationRequested, true);
  assert.equal(state.cancellationSource, "provider-drift");
  assert.equal(state.cancellationReason, "provider-drift");
  await platform.deleteLearner(owner, "learner-a");
  const escalated = await jobs.getExecutionState(owner, "research-job-provider-drift");
  assert.equal(escalated.cancellationSource, "input-quarantined");
  assert.equal(escalated.cancellationReason, "input-quarantined");
  const cancellationEvidence = await database.query<{ source: string }>(
    `SELECT source FROM research_job_cancellations
     WHERE job_id = 'research-job-provider-drift' ORDER BY sequence_id`,
  );
  assert.deepEqual(cancellationEvidence.rows, [
    { source: "provider-drift" },
    { source: "input-quarantined" },
  ]);
});

test("illegal transitions, missing reconciliation, expiry, and stale provider evidence fail closed", async (t) => {
  const missing = await fixture(false);
  t.after(() => missing.database.close());
  await assert.rejects(
    missing.jobs.request(reviewer, request()),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );

  const context = await fixture();
  t.after(() => context.database.close());
  await context.database.query(
    `INSERT INTO ml_artifacts (
       id, tenant_id, kind, version, sha256, release_posture,
       learner_feedback_eligible, created_by_actor_id
     ) VALUES ('dataset-no-lineage', 'tenant-a', 'dataset', 'orphan-v1', $1,
       'research-only', FALSE, 'actor-owner-a')`,
    ["0".repeat(64)],
  );
  await context.database.query(
    `INSERT INTO managed_artifact_objects (
       id, tenant_id, artifact_id, provider_id, object_reference_sha256,
       provider_object_version, expected_sha256, registered_by_actor_id
     ) VALUES ('binding-no-lineage', 'tenant-a', 'dataset-no-lineage',
       'provider-orphan', $1, 'immutable:v1', $2, 'actor-owner-a')`,
    ["a".repeat(64), "0".repeat(64)],
  );
  await context.database.query(
    `INSERT INTO managed_artifact_object_observations (
       id, binding_id, tenant_id, artifact_id, artifact_status, object_exists,
       observed_sha256, access_state, outcome, provider_checked_at,
       receipt_reference, receipt_sha256, recorded_by_actor_id
     ) VALUES ('observation-no-lineage', 'binding-no-lineage', 'tenant-a',
       'dataset-no-lineage', 'active', TRUE, $1, 'available', 'consistent',
       CURRENT_TIMESTAMP, 'receipt/no-lineage', $2, 'actor-owner-a')`,
    ["0".repeat(64), "b".repeat(64)],
  );
  await assert.rejects(
    context.jobs.request(reviewer, request({
      jobId: "research-job-no-lineage",
      inputs: [{ artifactId: "dataset-no-lineage", bindingId: "binding-no-lineage" }],
      outputId: "checkpoint-no-lineage",
    })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    context.jobs.request(reviewer, request({
      jobId: "research-job-illegal",
      jobType: "calibration",
      outputKind: "calibration",
      outputId: "calibration-job-v1",
    })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    context.jobs.request(reviewer, request({
      jobId: "research-job-expired",
      expiresAt: new Date(Date.now() - 60_000).toISOString(),
    })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  await context.objects.reconcile(owner, context.binding.bindingId, {
    inspect: async (claim) => ({
      bindingId: claim.bindingId, providerId: claim.providerId,
      objectReferenceSha256: claim.objectReferenceSha256,
      objectExists: true, observedSha256: "9".repeat(64),
      accessState: "available", checkedAt: new Date().toISOString(),
      receiptReference: "receipt/drift", receiptSha256: "8".repeat(64),
    }),
  });
  await assert.rejects(
    context.jobs.request(reviewer, request({ jobId: "research-job-drift" })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});

test("output collisions introduced before approval or execution fail globally", async (t) => {
  const beforeApproval = await fixture();
  t.after(() => beforeApproval.database.close());
  await beforeApproval.jobs.request(reviewer, request({
    jobId: "research-job-before-approval",
    outputId: "checkpoint-before-approval",
  }));
  await new ArtifactRegistryService(beforeApproval.database).registerDerivedArtifact(reviewer, {
    artifactId: "checkpoint-before-approval",
    kind: "checkpoint",
    version: "external-v1",
    sha256: "6".repeat(64),
    parentArtifactIds: [beforeApproval.artifact.id],
  });
  await assert.rejects(
    beforeApproval.jobs.approve(owner, "research-job-before-approval"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );

  const beforeExecution = await fixture();
  t.after(() => beforeExecution.database.close());
  await beforeExecution.jobs.request(reviewer, request({
    jobId: "research-job-before-execution",
    outputId: "checkpoint-before-execution",
  }));
  await beforeExecution.jobs.approve(owner, "research-job-before-execution");
  await new ArtifactRegistryService(beforeExecution.database).registerDerivedArtifact(reviewer, {
    artifactId: "checkpoint-before-execution",
    kind: "checkpoint",
    version: "external-v1",
    sha256: "7".repeat(64),
    parentArtifactIds: [beforeExecution.artifact.id],
  });
  await assert.rejects(
    beforeExecution.jobs.authorizeExecution(
      await beforeExecution.executionClaim("research-job-before-execution"),
    ),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );

  const crossTenant = await fixture();
  t.after(() => crossTenant.database.close());
  await crossTenant.database.query(
    `INSERT INTO ml_artifacts (
       id, tenant_id, kind, version, sha256, release_posture,
       learner_feedback_eligible, created_by_actor_id
     ) VALUES ('checkpoint-global-collision', 'tenant-b', 'checkpoint',
       'foreign-v1', $1, 'research-only', FALSE, 'actor-owner-b')`,
    ["8".repeat(64)],
  );
  await assert.rejects(
    crossTenant.jobs.request(reviewer, request({
      jobId: "research-job-global-collision",
      outputId: "checkpoint-global-collision",
    })),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});

test("successful terminal receipt atomically registers output lineage and managed evidence", async (t) => {
  const { database, jobs, platform, claimExecution, terminalAttestation, recordTerminal } = await fixture();
  t.after(() => database.close());
  const draft = await jobs.request(reviewer, request({
    jobId: "research-job-success",
    outputId: "checkpoint-success",
  }));
  await jobs.approve(owner, draft.jobId);
  const claim = await claimExecution(draft.jobId);
  await assert.rejects(
    database.query(
      `INSERT INTO research_job_terminal_receipts (
         receipt_id, job_id, tenant_id, claim_id, envelope_sha256,
         terminal_status, terminal_payload_sha256, output_artifact_id,
         output_binding_id, requested_output_kind, output_artifact_kind,
         output_version, output_sha256, completed_by_workload_id,
         signing_key_id, signature_algorithm, public_key_sha256,
         attestation_issued_at, attestation_payload_sha256, signature_sha256
       ) VALUES ('terminal-forged-output', $1, 'tenant-a', $2, $3,
         'succeeded', $4, 'dataset-job-v1', 'binding-job-v1', 'checkpoint',
         'checkpoint', 'dataset-v1', $5, 'research-runner-a', 'runner-key-a',
         'Ed25519', $6, CURRENT_TIMESTAMP, $7, $8)`,
      [draft.jobId, claim.claimId, claim.envelopeSha256,
        "e".repeat(64), "1".repeat(64),
        claim.signatureVerification?.publicKeySha256,
        "7".repeat(64), "8".repeat(64)],
    ),
    /foreign key/i,
  );
  await assert.rejects(
    (async () => {
      const signed = await terminalAttestation(successfulTerminal(draft.jobId, claim.claimId));
      const replacement = signed.signature.startsWith("A") ? "B" : "A";
      return jobs.recordTerminal({ ...signed, signature: `${replacement}${signed.signature.slice(1)}` });
    })(),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );

  const receipt = await recordTerminal(successfulTerminal(draft.jobId, claim.claimId));
  assert.equal(receipt.status, "succeeded");
  assert.equal(receipt.outputArtifactId, "checkpoint-success");
  assert.equal(receipt.outputBindingId, `binding-output-${draft.jobId}`);
  assert.equal(receipt.releasePosture, "research-only");
  assert.equal(receipt.learnerFeedbackEligible, false);
  assert.equal(receipt.productionGateEligible, false);
  assert.equal(receipt.completedByActorId, undefined);
  assert.equal(receipt.completedByWorkloadId, "research-runner-a");
  assert.equal(receipt.signatureVerification?.algorithm, "Ed25519");
  assert.match(receipt.terminalPayloadSha256, /^[a-f0-9]{64}$/);
  assert.deepEqual(await jobs.getTerminalReceipt(owner, draft.jobId), receipt);

  const registered = await database.query<{
    kind: string; status: string; parent: string; binding_sha256: string;
    observation_outcome: string; dependency_count: number;
    artifact_actor: string | null; artifact_workload: string | null;
    binding_actor: string | null; binding_workload: string | null;
    observation_actor: string | null; observation_workload: string | null;
  }>(
    `SELECT artifact.kind, artifact.status, edge.parent_artifact_id AS parent,
       binding.expected_sha256 AS binding_sha256,
       observation.outcome AS observation_outcome,
       artifact.created_by_actor_id AS artifact_actor,
       artifact.created_by_workload_id AS artifact_workload,
       binding.registered_by_actor_id AS binding_actor,
       binding.registered_by_workload_id AS binding_workload,
       observation.recorded_by_actor_id AS observation_actor,
       observation.recorded_by_workload_id AS observation_workload,
       (SELECT COUNT(*)::INTEGER FROM artifact_consent_dependencies
        WHERE artifact_id = artifact.id) AS dependency_count
     FROM ml_artifacts AS artifact
     INNER JOIN artifact_lineage_edges AS edge
       ON edge.child_artifact_id = artifact.id AND edge.tenant_id = artifact.tenant_id
     INNER JOIN managed_artifact_objects AS binding
       ON binding.artifact_id = artifact.id AND binding.tenant_id = artifact.tenant_id
     INNER JOIN managed_artifact_object_observations AS observation
       ON observation.binding_id = binding.id AND observation.tenant_id = binding.tenant_id
     WHERE artifact.id = 'checkpoint-success'`,
  );
  assert.deepEqual(registered.rows, [{
    kind: "checkpoint",
    status: "active",
    parent: "dataset-job-v1",
    binding_sha256: "4".repeat(64),
    observation_outcome: "consistent",
    dependency_count: 1,
    artifact_actor: null,
    artifact_workload: "research-runner-a",
    binding_actor: null,
    binding_workload: "research-runner-a",
    observation_actor: null,
    observation_workload: "research-runner-a",
  }]);
  const state = await jobs.getExecutionState(owner, draft.jobId);
  assert.equal(state.terminalStatus, "succeeded");
  assert.equal(state.terminalReceiptId, receipt.receiptId);
  await assert.rejects(
    recordTerminal(successfulTerminal(draft.jobId, claim.claimId)),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    jobs.cancel(owner, draft.jobId, "operator-stop"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    database.query("DELETE FROM research_job_terminal_receipts"),
    /append-only/,
  );

  await platform.deleteLearner(owner, "learner-a");
  const quarantined = await database.query<{ status: string; quarantine_reason: string }>(
    "SELECT status, quarantine_reason FROM ml_artifacts WHERE id = 'checkpoint-success'",
  );
  assert.deepEqual(quarantined.rows, [{
    status: "quarantined", quarantine_reason: "ancestor-quarantined",
  }]);
});

test("failed and cancelled terminal receipts enforce mutually exclusive legal outcomes", async (t) => {
  const failed = await fixture();
  t.after(() => failed.database.close());
  await failed.jobs.request(reviewer, request({
    jobId: "research-job-failed",
    outputId: "checkpoint-failed",
  }));
  await failed.jobs.approve(owner, "research-job-failed");
  const failedClaim = await failed.claimExecution("research-job-failed");
  await assert.rejects(
    failed.database.query(
      `INSERT INTO research_job_terminal_receipts (
         receipt_id, job_id, tenant_id, claim_id, envelope_sha256,
         terminal_status, terminal_payload_sha256, failure_code,
         failure_detail_sha256, completed_by_workload_id, signing_key_id,
         signature_algorithm, public_key_sha256, attestation_issued_at,
         attestation_payload_sha256, signature_sha256
       ) VALUES ('terminal-forged-envelope', 'research-job-failed', 'tenant-a',
         $1, $2, 'failed', $3, 'runner-failed', $4, 'research-runner-a',
         'runner-key-a', 'Ed25519', $5, CURRENT_TIMESTAMP, $6, $7)`,
      [failedClaim.claimId, "f".repeat(64), "e".repeat(64), "d".repeat(64),
        failedClaim.signatureVerification?.publicKeySha256,
        "6".repeat(64), "7".repeat(64)],
    ),
    /foreign key/i,
  );
  await assert.rejects(
    failed.database.query(
      `INSERT INTO research_job_terminal_receipts (
         receipt_id, job_id, tenant_id, claim_id, envelope_sha256,
         terminal_status, terminal_payload_sha256, failure_code,
         failure_detail_sha256, completed_by_workload_id, signing_key_id,
         signature_algorithm, public_key_sha256, attestation_issued_at,
         attestation_payload_sha256, signature_sha256
       ) VALUES ('terminal-illegal-failure', 'research-job-failed', 'tenant-a',
         $1, $2, 'failed', $3, 'cancellation-observed', $4,
         'research-runner-a', 'runner-key-a', 'Ed25519', $5,
         CURRENT_TIMESTAMP, $6, $7)`,
      [failedClaim.claimId, failedClaim.envelopeSha256,
        "e".repeat(64), "d".repeat(64),
        failedClaim.signatureVerification?.publicKeySha256,
        "6".repeat(64), "7".repeat(64)],
    ),
    /check constraint/i,
  );
  const failedReceipt = await failed.recordTerminal({
    jobId: "research-job-failed",
    claimId: failedClaim.claimId,
    status: "failed",
    failureCode: "runner-failed",
    failureDetailSha256: "7".repeat(64),
  });
  assert.equal(failedReceipt.status, "failed");
  assert.equal(failedReceipt.outputArtifactId, undefined);
  assert.equal((await failed.jobs.getExecutionState(owner, "research-job-failed")).terminalStatus, "failed");
  const absentOutput = await failed.database.query<{ count: number }>(
    "SELECT COUNT(*)::INTEGER AS count FROM ml_artifacts WHERE id = 'checkpoint-failed'",
  );
  assert.equal(absentOutput.rows[0]?.count, 0);

  const cancelled = await fixture();
  t.after(() => cancelled.database.close());
  await cancelled.jobs.request(reviewer, request({
    jobId: "research-job-terminal-cancel",
    outputId: "checkpoint-terminal-cancel",
  }));
  await cancelled.jobs.approve(owner, "research-job-terminal-cancel");
  const cancelledClaim = await cancelled.claimExecution("research-job-terminal-cancel");
  await assert.rejects(
    cancelled.recordTerminal({
      jobId: "research-job-terminal-cancel",
      claimId: cancelledClaim.claimId,
      status: "cancelled",
      failureCode: "cancellation-observed",
      failureDetailSha256: "8".repeat(64),
      cancellationAcknowledgementId: "missing-acknowledgement",
      cancellationRevision: 1,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await cancelled.jobs.cancel(owner, "research-job-terminal-cancel", "operator-stop");
  await assert.rejects(
    cancelled.recordTerminal({
      jobId: "research-job-terminal-cancel",
      claimId: cancelledClaim.claimId,
      status: "cancelled",
      failureCode: "cancellation-observed",
      failureDetailSha256: "8".repeat(64),
      cancellationAcknowledgementId: "missing-acknowledgement",
      cancellationRevision: 1,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const acknowledgement = await cancelled.jobs.acknowledgeCancellation(
    await cancelled.cancellationAcknowledgement(
      "research-job-terminal-cancel",
      cancelledClaim.claimId,
      "process-stopped",
    ),
  );
  assert.equal(acknowledgement.terminationOutcome, "process-stopped");
  assert.equal(acknowledgement.independentlyVerifiedProcessTermination, false);
  await assert.rejects(
    cancelled.recordTerminal(successfulTerminal(
      "research-job-terminal-cancel",
      cancelledClaim.claimId,
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const cancelledReceipt = await cancelled.recordTerminal({
    jobId: "research-job-terminal-cancel",
    claimId: cancelledClaim.claimId,
    status: "cancelled",
    failureCode: "cancellation-observed",
    failureDetailSha256: "8".repeat(64),
    cancellationAcknowledgementId: acknowledgement.acknowledgementId,
    cancellationRevision: acknowledgement.cancellationRevision,
  });
  assert.equal(cancelledReceipt.status, "cancelled");
  assert.equal(cancelledReceipt.failureCode, "cancellation-observed");
  assert.equal(
    cancelledReceipt.cancellationAcknowledgementId,
    acknowledgement.acknowledgementId,
  );
  assert.equal(cancelledReceipt.cancellationRevision, acknowledgement.cancellationRevision);
  assert.equal(
    (await cancelled.jobs.getExecutionState(owner, "research-job-terminal-cancel")).terminalStatus,
    "cancelled",
  );
});

test("signed cancellation acknowledgements reject tampering, malformed outcomes, and revoked keys", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-cancellation-negative",
    outputId: "checkpoint-cancellation-negative",
  }));
  await context.jobs.approve(owner, "research-job-cancellation-negative");
  const claim = await context.claimExecution("research-job-cancellation-negative");
  await context.jobs.cancel(owner, "research-job-cancellation-negative", "operator-stop");
  const signed = await context.cancellationAcknowledgement(
    "research-job-cancellation-negative",
    claim.claimId,
    "process-stopped",
  );
  const cancellationIssuedAt = new Date(signed.issuedAt);
  const predating = await context.cancellationAcknowledgement(
    "research-job-cancellation-negative",
    claim.claimId,
    "process-stopped",
    new Date(cancellationIssuedAt.getTime() - 1_000).toISOString(),
  );
  await assert.rejects(
    context.jobs.acknowledgeCancellation(predating),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  const replacement = signed.signature[0] === "A" ? "B" : "A";
  await assert.rejects(
    context.jobs.acknowledgeCancellation({
      ...signed,
      signature: `${replacement}${signed.signature.slice(1)}`,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  await assert.rejects(
    context.jobs.acknowledgeCancellation({
      ...signed,
      acknowledgement: {
        ...signed.acknowledgement,
        processReferenceSha256: undefined,
      },
    } as unknown as SignedResearchJobCancellationAcknowledgement),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  await context.workloads.revokeSigningKey(
    owner,
    "research-runner-a",
    "runner-key-a",
    "compromised",
  );
  await assert.rejects(
    context.jobs.acknowledgeCancellation(signed),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const persisted = await context.database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count
     FROM research_job_cancellation_acknowledgements
     WHERE job_id = 'research-job-cancellation-negative'`,
  );
  assert.equal(persisted.rows[0]?.count, 0);
});

test("cancellation acknowledgement replay and stale safety evidence fail closed", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-cancellation-stale",
    outputId: "checkpoint-cancellation-stale",
  }));
  await context.jobs.approve(owner, "research-job-cancellation-stale");
  const claim = await context.claimExecution("research-job-cancellation-stale");
  await context.jobs.cancel(owner, "research-job-cancellation-stale", "operator-stop");
  const operatorAcknowledgement = await context.cancellationAcknowledgement(
    "research-job-cancellation-stale",
    claim.claimId,
  );
  const preAcknowledgementTerminal = await context.terminalAttestation({
    jobId: "research-job-cancellation-stale",
    claimId: claim.claimId,
    status: "cancelled",
    failureCode: "cancellation-observed",
    failureDetailSha256: "b".repeat(64),
    cancellationAcknowledgementId: "future-acknowledgement",
    cancellationRevision: 1,
  });
  const firstReceipt = await context.jobs.acknowledgeCancellation(operatorAcknowledgement);
  assert.equal(firstReceipt.cancellationRevision, 1);
  assert.equal(firstReceipt.evidencePosture, "workload-attested");
  assert.equal(firstReceipt.independentlyVerifiedProcessTermination, false);
  assert.equal(firstReceipt.productionGateEligible, false);
  const predatingTerminal = await context.terminalAttestation({
    jobId: "research-job-cancellation-stale",
    claimId: claim.claimId,
    status: "cancelled",
    failureCode: "cancellation-observed",
    failureDetailSha256: "a".repeat(64),
    cancellationAcknowledgementId: firstReceipt.acknowledgementId,
    cancellationRevision: firstReceipt.cancellationRevision,
  }, {
    issuedAt: new Date(new Date(firstReceipt.issuedAt).getTime() - 1).toISOString(),
  });
  await assert.rejects(
    context.jobs.recordTerminal(predatingTerminal),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    context.jobs.acknowledgeCancellation(operatorAcknowledgement),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  await context.platform.deleteLearner(owner, "learner-a");
  await assert.rejects(
    context.recordTerminal({
      jobId: "research-job-cancellation-stale",
      claimId: claim.claimId,
      status: "cancelled",
      failureCode: "cancellation-observed",
      failureDetailSha256: "c".repeat(64),
      cancellationAcknowledgementId: firstReceipt.acknowledgementId,
      cancellationRevision: firstReceipt.cancellationRevision,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    context.jobs.acknowledgeCancellation(operatorAcknowledgement),
    (error: unknown) => error instanceof PlatformDataError
      && ["invalid-artifact", "conflict"].includes(error.code),
  );
  const safetyAcknowledgement = await context.cancellationAcknowledgement(
    "research-job-cancellation-stale",
    claim.claimId,
  );
  const safetyReceipt = await context.jobs.acknowledgeCancellation(safetyAcknowledgement);
  assert.equal(safetyReceipt.cancellationRevision, 2);
  assert.equal(safetyReceipt.cancellationSource, "input-quarantined");
  await assert.rejects(
    context.jobs.recordTerminal(preAcknowledgementTerminal),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const terminal = await context.recordTerminal({
    jobId: "research-job-cancellation-stale",
    claimId: claim.claimId,
    status: "cancelled",
    failureCode: "cancellation-observed",
    failureDetailSha256: "d".repeat(64),
    cancellationAcknowledgementId: safetyReceipt.acknowledgementId,
    cancellationRevision: safetyReceipt.cancellationRevision,
  });
  assert.equal(terminal.status, "cancelled");
  await assert.rejects(
    context.database.query(
      `DELETE FROM research_job_cancellation_acknowledgements
       WHERE acknowledgement_id = $1`,
      [firstReceipt.acknowledgementId],
    ),
    /append-only/,
  );
  const audits = await context.database.query<{
    actor_id: string | null; workload_id: string | null; count: number;
  }>(
    `SELECT actor_id, workload_id, COUNT(*)::INTEGER AS count
     FROM audit_events
     WHERE action = 'research-job.cancellation-acknowledged'
       AND resource_id = 'research-job-cancellation-stale'
     GROUP BY actor_id, workload_id`,
  );
  assert.deepEqual(audits.rows, [{
    actor_id: null,
    workload_id: "research-runner-a",
    count: 2,
  }]);
});

test("signed heartbeats advance one monotonic workload-attributed liveness sequence", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-heartbeat",
    outputId: "checkpoint-heartbeat",
  }));
  await context.jobs.approve(owner, "research-job-heartbeat");
  const claim = await context.claimExecution("research-job-heartbeat");
  const candidates = await Promise.all([
    context.heartbeat("research-job-heartbeat", claim.claimId, 1),
    context.heartbeat("research-job-heartbeat", claim.claimId, 1),
  ]);
  const concurrent = await Promise.allSettled(
    candidates.map((signed) => context.jobs.recordHeartbeat(signed)),
  );
  assert.equal(concurrent.filter((result) => result.status === "fulfilled").length, 1);
  assert.equal(concurrent.filter((result) => result.status === "rejected").length, 1);
  const first = concurrent.find((result) => result.status === "fulfilled");
  assert.ok(first?.status === "fulfilled");
  assert.equal(first.value.runnerState, "running");
  assert.equal(first.value.evidencePosture, "workload-attested");
  assert.equal(first.value.independentlyVerifiedProcessLiveness, false);
  assert.equal(first.value.productionGateEligible, false);
  await assert.rejects(
    context.jobs.recordHeartbeat(await context.heartbeat(
      "research-job-heartbeat",
      claim.claimId,
      2,
      "running",
      0,
      new Date(new Date(first.value.issuedAt).getTime() - 1).toISOString(),
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const second = await context.jobs.recordHeartbeat(
    await context.heartbeat("research-job-heartbeat", claim.claimId, 2),
  );
  assert.equal(second.heartbeatSequence, 2);
  assert.equal(second.reportedByWorkloadId, "research-runner-a");
  assert.deepEqual(await context.jobs.getLatestHeartbeat(owner, "research-job-heartbeat"), second);
  await assert.rejects(
    context.jobs.getLatestHeartbeat(clinician, "research-job-heartbeat"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const gate = await context.database.query<{
    last_heartbeat_sequence: number; last_heartbeat_id: string;
  }>(
    `SELECT last_heartbeat_sequence, last_heartbeat_id
     FROM research_job_execution_gates WHERE job_id = 'research-job-heartbeat'`,
  );
  assert.deepEqual(gate.rows, [{
    last_heartbeat_sequence: 2,
    last_heartbeat_id: second.heartbeatId,
  }]);
  await assert.rejects(
    context.database.query("DELETE FROM research_job_heartbeats"),
    /append-only/,
  );
  const audits = await context.database.query<{
    actor_id: string | null; workload_id: string | null; count: number;
  }>(
    `SELECT actor_id, workload_id, COUNT(*)::INTEGER AS count
     FROM audit_events WHERE action = 'research-job.heartbeat-recorded'
     GROUP BY actor_id, workload_id`,
  );
  assert.deepEqual(audits.rows, [{
    actor_id: null,
    workload_id: "research-runner-a",
    count: 2,
  }]);
});

test("heartbeats reject tampering, replay, sequence gaps, and stale cancellation state", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-heartbeat-negative",
    outputId: "checkpoint-heartbeat-negative",
  }));
  await context.jobs.approve(owner, "research-job-heartbeat-negative");
  const claim = await context.claimExecution("research-job-heartbeat-negative");
  const first = await context.heartbeat("research-job-heartbeat-negative", claim.claimId, 1);
  const replacement = first.signature[0] === "A" ? "B" : "A";
  await assert.rejects(
    context.jobs.recordHeartbeat({
      ...first,
      signature: `${replacement}${first.signature.slice(1)}`,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  await assert.rejects(
    context.jobs.recordHeartbeat(
      await context.heartbeat("research-job-heartbeat-negative", claim.claimId, 2),
    ),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await context.jobs.recordHeartbeat(first);
  await assert.rejects(
    context.jobs.recordHeartbeat(first),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  const staleRunning = await context.heartbeat(
    "research-job-heartbeat-negative",
    claim.claimId,
    2,
  );
  const predatingCancellation = await context.heartbeat(
    "research-job-heartbeat-negative",
    claim.claimId,
    2,
    "cancellation-observed",
    1,
  );
  await context.jobs.cancel(owner, "research-job-heartbeat-negative", "operator-stop");
  await assert.rejects(
    context.jobs.recordHeartbeat(staleRunning),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    context.jobs.recordHeartbeat(predatingCancellation),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const observed = await context.jobs.recordHeartbeat(await context.heartbeat(
    "research-job-heartbeat-negative",
    claim.claimId,
    2,
    "cancellation-observed",
    1,
  ));
  assert.equal(observed.runnerState, "cancellation-observed");
  assert.equal(observed.cancellationRevision, 1);
  await assert.rejects(
    context.jobs.recordHeartbeat(await context.heartbeat(
      "research-job-heartbeat-negative",
      claim.claimId,
      3,
      "cancellation-observed",
      2,
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});

test("terminal state and key revocation close heartbeat persistence", async (t) => {
  const terminalContext = await fixture();
  t.after(() => terminalContext.database.close());
  await terminalContext.jobs.request(reviewer, request({
    jobId: "research-job-heartbeat-terminal",
    outputId: "checkpoint-heartbeat-terminal",
  }));
  await terminalContext.jobs.approve(owner, "research-job-heartbeat-terminal");
  const terminalClaim = await terminalContext.claimExecution("research-job-heartbeat-terminal");
  await terminalContext.jobs.recordHeartbeat(await terminalContext.heartbeat(
    "research-job-heartbeat-terminal",
    terminalClaim.claimId,
    1,
  ));
  await terminalContext.recordTerminal(successfulTerminal(
    "research-job-heartbeat-terminal",
    terminalClaim.claimId,
  ));
  await assert.rejects(
    terminalContext.jobs.recordHeartbeat(await terminalContext.heartbeat(
      "research-job-heartbeat-terminal",
      terminalClaim.claimId,
      2,
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );

  const revokedContext = await fixture();
  t.after(() => revokedContext.database.close());
  await revokedContext.jobs.request(reviewer, request({
    jobId: "research-job-heartbeat-revoked",
    outputId: "checkpoint-heartbeat-revoked",
  }));
  await revokedContext.jobs.approve(owner, "research-job-heartbeat-revoked");
  const revokedClaim = await revokedContext.claimExecution("research-job-heartbeat-revoked");
  const signed = await revokedContext.heartbeat(
    "research-job-heartbeat-revoked",
    revokedClaim.claimId,
    1,
  );
  await revokedContext.workloads.revokeSigningKey(
    owner,
    "research-runner-a",
    "runner-key-a",
    "compromised",
  );
  await assert.rejects(
    revokedContext.jobs.recordHeartbeat(signed),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const count = await revokedContext.database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM research_job_heartbeats
     WHERE job_id = 'research-job-heartbeat-revoked'`,
  );
  assert.equal(count.rows[0]?.count, 0);
});

test("database-clock liveness snapshots track lease, cancellation, and terminal states", async (t) => {
  const context = await fixture(true, 1);
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-liveness",
    outputId: "checkpoint-liveness",
  }));
  await context.jobs.approve(owner, "research-job-liveness");
  const claim = await context.claimExecution("research-job-liveness");
  assert.equal(claim.leaseDurationSeconds, 1);
  assert.ok(new Date(claim.leaseExpiresAt) > new Date(claim.leaseStartedAt));
  const awaiting = await context.jobs.inspectLiveness(owner, "research-job-liveness");
  assert.equal(awaiting.status, "awaiting-first-heartbeat");
  assert.equal(awaiting.leaseExpired, false);
  assert.equal(awaiting.lastHeartbeatSequence, 0);
  assert.equal(awaiting.alertRequired, false);
  assert.equal(awaiting.externalProcessLivenessVerified, false);
  assert.equal(awaiting.alertDeliveryEvidencePresent, false);
  assert.equal(awaiting.productionGateEligible, false);
  await assert.rejects(
    context.database.query(
      `UPDATE research_job_execution_gates
       SET lease_expires_at = lease_expires_at + INTERVAL '60 seconds'
       WHERE job_id = 'research-job-liveness'`,
    ),
    /monotonic/,
  );
  await assert.rejects(
    context.jobs.inspectLiveness(clinician, "research-job-liveness"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await context.jobs.recordHeartbeat(await context.heartbeat(
    "research-job-liveness",
    claim.claimId,
    1,
  ));
  const fresh = await context.jobs.inspectLiveness(reviewer, "research-job-liveness");
  assert.equal(fresh.status, "fresh");
  assert.equal(fresh.lastHeartbeatSequence, 1);
  await new Promise((resolve) => setTimeout(resolve, 1_100));
  const overdue = await context.jobs.inspectLiveness(owner, "research-job-liveness");
  assert.equal(overdue.status, "overdue");
  assert.equal(overdue.leaseExpired, true);
  assert.equal(overdue.alertRequired, true);
  await assert.rejects(
    context.jobs.recordAlertDelivery(await context.alertDeliveryAttestation(
      overdue,
      { snapshotPayloadSha256: "0".repeat(64) },
    )),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "invalid-artifact",
  );
  const signedDelivery = await context.alertDeliveryAttestation(overdue);
  const replacement = signedDelivery.signature[0] === "A" ? "B" : "A";
  await assert.rejects(
    context.jobs.recordAlertDelivery({
      ...signedDelivery,
      signature: `${replacement}${signedDelivery.signature.slice(1)}`,
    }),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "invalid-artifact",
  );
  const delivery = await context.jobs.recordAlertDelivery(signedDelivery);
  assert.equal(delivery.snapshotId, overdue.snapshotId);
  assert.equal(delivery.snapshotStatus, "overdue");
  assert.equal(delivery.authenticatedDeliveryAttestationVerified, true);
  assert.equal(delivery.externalProviderKeyCustodyVerified, false);
  assert.equal(delivery.productionGateEligible, false);
  assert.equal(
    (await context.jobs.getLivenessSnapshot(owner, overdue.snapshotId))
      .alertDeliveryEvidencePresent,
    true,
  );
  await assert.rejects(
    context.jobs.recordAlertDelivery(signedDelivery),
    (error: unknown) => error instanceof PlatformDataError
      && ["conflict", "access-denied"].includes(error.code),
  );
  await assert.rejects(
    context.jobs.recordAlertDelivery(await context.alertDeliveryAttestation(
      awaiting,
      { snapshotStatus: "overdue" },
    )),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  await assert.rejects(
    context.database.query("DELETE FROM research_job_alert_delivery_attestations"),
    /append-only/,
  );
  await context.jobs.cancel(owner, "research-job-liveness", "operator-stop");
  const pending = await context.jobs.inspectLiveness(owner, "research-job-liveness");
  assert.equal(pending.status, "cancellation-pending");
  assert.equal(pending.alertRequired, true);
  const pendingDelivery = await context.alertDeliveryAttestation(pending);
  await context.workloads.revokeSigningKey(
    owner,
    "research-alert-delivery-a",
    "alert-delivery-key-a",
    "compromised",
  );
  await assert.rejects(
    context.jobs.recordAlertDelivery(pendingDelivery),
    (error: unknown) => error instanceof PlatformDataError
      && error.code === "access-denied",
  );
  await context.jobs.recordHeartbeat(await context.heartbeat(
    "research-job-liveness",
    claim.claimId,
    2,
    "cancellation-observed",
    1,
  ));
  const observed = await context.jobs.inspectLiveness(owner, "research-job-liveness");
  assert.equal(observed.status, "cancellation-observed");
  assert.equal(observed.cancellationRevision, 1);
  assert.equal(observed.lastHeartbeatCancellationRevision, 1);
  assert.equal(observed.alertRequired, true);
  await context.platform.deleteLearner(owner, "learner-a");
  const escalatedPending = await context.jobs.inspectLiveness(
    owner,
    "research-job-liveness",
  );
  assert.equal(escalatedPending.status, "cancellation-pending");
  assert.equal(escalatedPending.cancellationRevision, 2);
  assert.equal(escalatedPending.lastHeartbeatCancellationRevision, 1);
  await context.jobs.recordHeartbeat(await context.heartbeat(
    "research-job-liveness",
    claim.claimId,
    3,
    "cancellation-observed",
    2,
  ));
  const escalatedObserved = await context.jobs.inspectLiveness(
    owner,
    "research-job-liveness",
  );
  assert.equal(escalatedObserved.status, "cancellation-observed");
  assert.equal(escalatedObserved.lastHeartbeatCancellationRevision, 2);
  const acknowledgement = await context.jobs.acknowledgeCancellation(
    await context.cancellationAcknowledgement("research-job-liveness", claim.claimId),
  );
  await context.recordTerminal({
    jobId: "research-job-liveness",
    claimId: claim.claimId,
    status: "cancelled",
    failureCode: "cancellation-observed",
    failureDetailSha256: "e".repeat(64),
    cancellationAcknowledgementId: acknowledgement.acknowledgementId,
    cancellationRevision: acknowledgement.cancellationRevision,
  });
  const terminal = await context.jobs.inspectLiveness(owner, "research-job-liveness");
  assert.equal(terminal.status, "terminal");
  assert.equal(terminal.terminalStatus, "cancelled");
  assert.equal(terminal.alertRequired, false);
  const evidence = await context.database.query<{ snapshots: number; audits: number }>(
    `SELECT
       (SELECT COUNT(*)::INTEGER FROM research_job_liveness_snapshots
        WHERE job_id = 'research-job-liveness') AS snapshots,
       (SELECT COUNT(*)::INTEGER FROM audit_events
        WHERE action = 'research-job.liveness-inspected'
          AND resource_id = 'research-job-liveness') AS audits`,
  );
  assert.deepEqual(evidence.rows, [{ snapshots: 8, audits: 8 }]);
  await assert.rejects(
    context.database.query("DELETE FROM research_job_liveness_snapshots"),
    /append-only/,
  );
  await assert.rejects(
    context.database.query(
      "UPDATE research_job_liveness_snapshots SET alert_required = FALSE",
    ),
    /append-only/,
  );
  await assert.rejects(
    context.database.query("TRUNCATE research_job_liveness_snapshots"),
    /append-only|foreign key constraint/,
  );
});

test("successful completion and cancellation serialize without an orphan output", async (t) => {
  const {
    database, jobs, claimExecution, recordTerminal, cancellationAcknowledgement,
  } = await fixture();
  t.after(() => database.close());
  await jobs.request(reviewer, request({
    jobId: "research-job-terminal-race",
    outputId: "checkpoint-terminal-race",
  }));
  await jobs.approve(owner, "research-job-terminal-race");
  const claim = await claimExecution("research-job-terminal-race");
  const [success, cancellation] = await Promise.allSettled([
    recordTerminal(successfulTerminal("research-job-terminal-race", claim.claimId)),
    jobs.cancel(owner, "research-job-terminal-race", "operator-stop"),
  ]);
  assert.notEqual(success.status, cancellation.status);
  const artifact = await database.query<{ count: number }>(
    "SELECT COUNT(*)::INTEGER AS count FROM ml_artifacts WHERE id = 'checkpoint-terminal-race'",
  );
  const state = await jobs.getExecutionState(owner, "research-job-terminal-race");
  if (success.status === "fulfilled") {
    assert.equal(artifact.rows[0]?.count, 1);
    assert.equal(state.terminalStatus, "succeeded");
    assert.equal(state.cancellationRequested, false);
  } else {
    assert.equal(artifact.rows[0]?.count, 0);
    assert.equal(state.cancellationRequested, true);
    assert.equal(state.terminalStatus, undefined);
    const acknowledgement = await jobs.acknowledgeCancellation(await cancellationAcknowledgement(
      "research-job-terminal-race",
      claim.claimId,
    ));
    await recordTerminal({
      jobId: "research-job-terminal-race",
      claimId: claim.claimId,
      status: "cancelled",
      failureCode: "cancellation-observed",
      failureDetailSha256: "9".repeat(64),
      cancellationAcknowledgementId: acknowledgement.acknowledgementId,
      cancellationRevision: acknowledgement.cancellationRevision,
    });
  }
});

test("managed-output binding conflicts roll back artifact registration", async (t) => {
  const { database, jobs, claimExecution, recordTerminal } = await fixture();
  t.after(() => database.close());
  await jobs.request(reviewer, request({
    jobId: "research-job-binding-conflict",
    outputId: "checkpoint-binding-conflict",
  }));
  await jobs.approve(owner, "research-job-binding-conflict");
  const claim = await claimExecution("research-job-binding-conflict");
  await assert.rejects(
    recordTerminal({
      ...successfulTerminal("research-job-binding-conflict", claim.claimId),
      bindingId: "binding-job-v1",
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  const evidence = await database.query<{ artifacts: number; terminals: number }>(
    `SELECT
       (SELECT COUNT(*)::INTEGER FROM ml_artifacts
        WHERE id = 'checkpoint-binding-conflict') AS artifacts,
       (SELECT COUNT(*)::INTEGER FROM research_job_terminal_receipts
        WHERE job_id = 'research-job-binding-conflict') AS terminals`,
  );
  assert.deepEqual(evidence.rows, [{ artifacts: 0, terminals: 0 }]);
  const state = await jobs.getExecutionState(owner, "research-job-binding-conflict");
  assert.equal(state.terminalStatus, undefined);
});

test("an existing terminal receipt advances the gate and prevents later output writes", async (t) => {
  const { database, jobs, claimExecution, recordTerminal } = await fixture();
  t.after(() => database.close());
  await jobs.request(reviewer, request({
    jobId: "research-job-existing-terminal",
    outputId: "checkpoint-existing-terminal",
  }));
  await jobs.approve(owner, "research-job-existing-terminal");
  const claim = await claimExecution("research-job-existing-terminal");
  const existing = await recordTerminal({
    jobId: "research-job-existing-terminal",
    claimId: claim.claimId,
    status: "failed",
    failureCode: "runner-failed",
    failureDetailSha256: "d".repeat(64),
  });
  const state = await jobs.getExecutionState(owner, "research-job-existing-terminal");
  assert.equal(state.terminalStatus, "failed");
  assert.equal(state.terminalReceiptId, existing.receiptId);
  await assert.rejects(
    recordTerminal(successfulTerminal("research-job-existing-terminal", claim.claimId)),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const artifact = await database.query<{ count: number }>(
    `SELECT COUNT(*)::INTEGER AS count FROM ml_artifacts
     WHERE id = 'checkpoint-existing-terminal'`,
  );
  assert.equal(artifact.rows[0]?.count, 0);
});

test("managed dataset exports map to consent-lineage dataset artifacts", async (t) => {
  const { database, jobs, claimExecution, recordTerminal } = await fixture();
  t.after(() => database.close());
  await jobs.request(reviewer, request({
    jobId: "research-job-dataset-export",
    jobType: "dataset-export",
    outputKind: "managed-dataset-export",
    outputId: "dataset-export-output",
    outputVersion: "export-v1",
  }));
  await jobs.approve(owner, "research-job-dataset-export");
  const claim = await claimExecution("research-job-dataset-export");
  const receipt = await recordTerminal(successfulTerminal(
    "research-job-dataset-export",
    claim.claimId,
  ));
  assert.equal(receipt.requestedOutputKind, "managed-dataset-export");
  assert.equal(receipt.outputArtifactKind, "dataset");
  assert.equal(receipt.outputVersion, "export-v1");
  assert.equal(receipt.outputSha256, "4".repeat(64));
  const artifact = await database.query<{ kind: string; dependencies: number }>(
    `SELECT artifact.kind,
       (SELECT COUNT(*)::INTEGER FROM artifact_consent_dependencies
        WHERE artifact_id = artifact.id) AS dependencies
     FROM ml_artifacts AS artifact WHERE id = 'dataset-export-output'`,
  );
  assert.deepEqual(artifact.rows, [{ kind: "dataset", dependencies: 1 }]);
});

test("signed workload claims fail closed on tampering, staleness, and key revocation", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await assert.rejects(
    context.workloads.registerIdentity(reviewer, "unauthorized-runner"),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await context.jobs.request(reviewer, request({
    jobId: "research-job-signed-security",
    outputId: "checkpoint-signed-security",
  }));
  await context.jobs.approve(owner, "research-job-signed-security");
  const valid = await context.executionClaim("research-job-signed-security");
  const replacement = valid.signature.startsWith("A") ? "B" : "A";
  await assert.rejects(
    context.jobs.claimExecution({
      ...valid,
      signature: `${replacement}${valid.signature.slice(1)}`,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  const base64url = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  const canonicalTail = base64url.indexOf(valid.signature.at(-1) ?? "");
  const nonCanonicalTail = base64url[canonicalTail + 1];
  assert.ok(nonCanonicalTail);
  await assert.rejects(
    context.jobs.claimExecution({
      ...valid,
      signature: `${valid.signature.slice(0, -1)}${nonCanonicalTail}`,
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  await assert.rejects(
    context.jobs.claimExecution(await context.executionClaim(
      "research-job-signed-security",
      { issuedAt: new Date(Date.now() - 360_000).toISOString() },
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "invalid-artifact",
  );
  await assert.rejects(
    context.jobs.claimExecution(await context.executionClaim(
      "research-job-signed-security",
      { envelopeSha256: "f".repeat(64) },
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await context.workloads.revokeSigningKey(
    owner,
    "research-runner-a",
    "runner-key-a",
    "compromised",
  );
  await assert.rejects(
    context.jobs.claimExecution(valid),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    context.database.query("DELETE FROM research_workload_signing_key_revocations"),
    /append-only/,
  );
});

test("claim ID replay rolls back a second job gate atomically", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-claim-id-a",
    outputId: "checkpoint-claim-id-a",
  }));
  await context.jobs.approve(owner, "research-job-claim-id-a");
  await context.jobs.request(reviewer, request({
    jobId: "research-job-claim-id-b",
    outputId: "checkpoint-claim-id-b",
  }));
  await context.jobs.approve(owner, "research-job-claim-id-b");
  const sharedClaimId = "shared-signed-claim-id";
  await context.jobs.claimExecution(await context.executionClaim(
    "research-job-claim-id-a",
    { claimId: sharedClaimId },
  ));
  await assert.rejects(
    context.jobs.claimExecution(await context.executionClaim(
      "research-job-claim-id-b",
      { claimId: sharedClaimId },
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "conflict",
  );
  const gate = await context.database.query<{ claimed: boolean }>(
    `SELECT claimed FROM research_job_execution_gates
     WHERE job_id = 'research-job-claim-id-b'`,
  );
  assert.equal(gate.rows[0]?.claimed, false);
});

test("workload trust is tenant-scoped and identity revocation blocks signed claims", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  const foreignKeys = generateKeyPairSync("ed25519");
  await context.workloads.registerIdentity(foreignOwner, "foreign-research-runner");
  await context.workloads.registerSigningKey(foreignOwner, {
    workloadId: "foreign-research-runner",
    signingKeyId: "foreign-runner-key",
    publicKeyPem: foreignKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(Date.now() - 86_400_000).toISOString(),
    validUntil: new Date(Date.now() + 86_400_000).toISOString(),
  });
  await context.jobs.request(reviewer, request({
    jobId: "research-job-workload-tenant",
    outputId: "checkpoint-workload-tenant",
  }));
  await context.jobs.approve(owner, "research-job-workload-tenant");
  const local = await context.executionClaim("research-job-workload-tenant");
  const { signature: _localSignature, ...localUnsigned } = local;
  const foreignUnsigned = {
    ...localUnsigned,
    workloadId: "foreign-research-runner",
    signingKeyId: "foreign-runner-key",
  };
  await assert.rejects(
    context.jobs.claimExecution({
      ...foreignUnsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobExecutionClaimPayload(foreignUnsigned)),
        foreignKeys.privateKey,
      ).toString("base64url"),
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await context.workloads.revokeIdentity(owner, "research-runner-a", "disabled");
  await assert.rejects(
    context.jobs.claimExecution(local),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});

test("scheduled and expired workload keys cannot claim at database time", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  const clock = await context.database.query<{ now: string | Date }>(
    "SELECT CURRENT_TIMESTAMP AS now",
  );
  const databaseNow = new Date(clock.rows[0]?.now ?? 0);
  const scheduledKeys = generateKeyPairSync("ed25519");
  const expiredKeys = generateKeyPairSync("ed25519");
  await context.workloads.registerIdentity(owner, "timed-research-runner");
  await context.workloads.registerSigningKey(owner, {
    workloadId: "timed-research-runner",
    signingKeyId: "scheduled-runner-key",
    publicKeyPem: scheduledKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(databaseNow.getTime() + 30_000).toISOString(),
    validUntil: new Date(databaseNow.getTime() + 3_600_000).toISOString(),
  });
  await context.workloads.registerSigningKey(owner, {
    workloadId: "timed-research-runner",
    signingKeyId: "expired-runner-key",
    publicKeyPem: expiredKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(databaseNow.getTime() - 3_600_000).toISOString(),
    validUntil: new Date(databaseNow.getTime() - 1_000).toISOString(),
  });
  const timedJobs = new ResearchJobAuthorizationService(
    context.database,
    () => databaseNow,
  );
  await timedJobs.request(reviewer, request({
    jobId: "research-job-key-time",
    outputId: "checkpoint-key-time",
  }));
  const approved = await timedJobs.approve(owner, "research-job-key-time");
  const dispatch = await context.dispatchJob(
    "research-job-key-time",
    "timed-research-runner",
  );
  async function signedWith(
    signingKeyId: string,
    issuedAt: string,
    privateKey: typeof scheduledKeys.privateKey,
  ): Promise<SignedResearchJobExecutionClaim> {
    const unsigned = {
      schemaVersion: "research-job-execution-claim-signature-v2" as const,
      tenantId: "tenant-a",
      workloadId: "timed-research-runner",
      signingKeyId,
      algorithm: "Ed25519" as const,
      issuedAt,
      claimId: randomUUID(),
      jobId: "research-job-key-time",
      envelopeSha256: approved.envelopeSha256 ?? "0".repeat(64),
      dispatchId: dispatch.dispatchId,
      dispatchRevision: dispatch.dispatchRevision,
    };
    return {
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobExecutionClaimPayload(unsigned)),
        privateKey,
      ).toString("base64url"),
    };
  }
  await assert.rejects(
    timedJobs.claimExecution(await signedWith(
      "scheduled-runner-key",
      new Date(databaseNow.getTime() + 30_000).toISOString(),
      scheduledKeys.privateKey,
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  await assert.rejects(
    timedJobs.claimExecution(await signedWith(
      "expired-runner-key",
      new Date(databaseNow.getTime() - 2_000).toISOString(),
      expiredKeys.privateKey,
    )),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});

test("key revocation and claim persistence serialize on the trust gate", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-key-revoke-race",
    outputId: "checkpoint-key-revoke-race",
  }));
  await context.jobs.approve(owner, "research-job-key-revoke-race");
  const signed = await context.executionClaim("research-job-key-revoke-race");
  const [revocation, claim] = await Promise.allSettled([
    context.workloads.revokeSigningKey(
      owner,
      "research-runner-a",
      "runner-key-a",
      "compromised",
    ),
    context.jobs.claimExecution(signed),
  ]);
  assert.equal(revocation.status, "fulfilled");
  const evidence = await context.database.query<{
    claim_count: number; revoked: boolean;
  }>(
    `SELECT
       (SELECT COUNT(*)::INTEGER FROM research_job_execution_claims
        WHERE job_id = 'research-job-key-revoke-race') AS claim_count,
       gate.revoked
     FROM research_workload_signing_key_gates AS gate
     WHERE gate.tenant_id = 'tenant-a' AND gate.workload_id = 'research-runner-a'
       AND gate.signing_key_id = 'runner-key-a'`,
  );
  assert.equal(evidence.rows[0]?.revoked, true);
  assert.equal(evidence.rows[0]?.claim_count, claim.status === "fulfilled" ? 1 : 0);
  if (claim.status === "rejected") {
    assert.ok(claim.reason instanceof PlatformDataError);
  }
  await assert.rejects(
    context.database.query(
      `UPDATE research_workload_signing_key_gates SET revoked = FALSE
       WHERE workload_id = 'research-runner-a'`,
    ),
    /monotonic/,
  );
});

test("terminal persistence rechecks workload key trust and leaves no output after revocation", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  await context.jobs.request(reviewer, request({
    jobId: "research-job-terminal-revoked-key",
    outputId: "checkpoint-terminal-revoked-key",
  }));
  await context.jobs.approve(owner, "research-job-terminal-revoked-key");
  const claim = await context.claimExecution("research-job-terminal-revoked-key");
  const signed = await context.terminalAttestation(successfulTerminal(
    "research-job-terminal-revoked-key",
    claim.claimId,
  ));
  await context.workloads.revokeSigningKey(
    owner,
    "research-runner-a",
    "runner-key-a",
    "compromised",
  );
  await assert.rejects(
    context.jobs.recordTerminal(signed),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
  const evidence = await context.database.query<{ artifacts: number; terminals: number }>(
    `SELECT
       (SELECT COUNT(*)::INTEGER FROM ml_artifacts
        WHERE id = 'checkpoint-terminal-revoked-key') AS artifacts,
       (SELECT COUNT(*)::INTEGER FROM research_job_terminal_receipts
        WHERE job_id = 'research-job-terminal-revoked-key') AS terminals`,
  );
  assert.deepEqual(evidence.rows, [{ artifacts: 0, terminals: 0 }]);
});

test("a second same-tenant workload cannot complete another workload's claim", async (t) => {
  const context = await fixture();
  t.after(() => context.database.close());
  const otherKeys = generateKeyPairSync("ed25519");
  await context.workloads.registerIdentity(owner, "research-runner-two");
  await context.workloads.registerSigningKey(owner, {
    workloadId: "research-runner-two",
    signingKeyId: "runner-key-two",
    publicKeyPem: otherKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    validFrom: new Date(Date.now() - 86_400_000).toISOString(),
    validUntil: new Date(Date.now() + 86_400_000).toISOString(),
  });
  await context.jobs.request(reviewer, request({
    jobId: "research-job-wrong-terminal-workload",
    outputId: "checkpoint-wrong-terminal-workload",
  }));
  const approved = await context.jobs.approve(owner, "research-job-wrong-terminal-workload");
  const claim = await context.claimExecution("research-job-wrong-terminal-workload");
  const unsigned = {
    schemaVersion: "research-job-terminal-signature-v1" as const,
    tenantId: "tenant-a",
    workloadId: "research-runner-two",
    signingKeyId: "runner-key-two",
    algorithm: "Ed25519" as const,
    issuedAt: new Date().toISOString(),
    terminal: successfulTerminal("research-job-wrong-terminal-workload", claim.claimId),
  };
  await assert.rejects(
    context.jobs.recordTerminal({
      ...unsigned,
      signature: sign(
        null,
        Buffer.from(canonicalResearchJobTerminalAttestationPayload(
          unsigned,
          approved.envelopeSha256 ?? "0".repeat(64),
        )),
        otherKeys.privateKey,
      ).toString("base64url"),
    }),
    (error: unknown) => error instanceof PlatformDataError && error.code === "access-denied",
  );
});
