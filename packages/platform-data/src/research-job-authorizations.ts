import {
  createHash,
  createPublicKey,
  randomUUID,
  verify as verifySignature,
} from "node:crypto";

import type { DatabaseClient } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ActorContext,
  ArtifactKind,
  ResearchJobAuthorizationEnvelope,
  ResearchJobAlertDeliveryReceipt,
  ResearchJobCancellationReason,
  ResearchJobCancellationAcknowledgementReceipt,
  ResearchJobDispatchReceipt,
  ResearchJobExternalTerminationReceipt,
  ResearchJobExecutionClaim,
  ResearchJobExecutionState,
  ResearchJobHeartbeatReceipt,
  ResearchJobLivenessSnapshot,
  ResearchJobLaunchReceipt,
  ResearchJobOutputKind,
  ResearchJobRequestInput,
  ResearchJobTerminalInput,
  ResearchJobTerminalReceipt,
  SignedResearchJobExecutionClaim,
  SignedResearchJobAlertDeliveryAttestation,
  SignedResearchJobHeartbeat,
  SignedResearchJobLaunchAttestation,
  SignedResearchJobCancellationAcknowledgement,
  SignedResearchJobDispatch,
  SignedResearchJobExternalTerminationAttestation,
  SignedResearchJobTerminalAttestation,
} from "./types.ts";

const opaque = /^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$/;
const artifactIdentifier = /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/;
const version = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const gitRevision = /^[a-f0-9]{40}$/;
const sha256 = /^[a-f0-9]{64}$/;
const imageDigest = /^sha256:[a-f0-9]{64}$/;
const providerIdentifier = /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/;
const objectVersion = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;
const receiptReference = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$/;
const signingIdentifier = /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/;
const ed25519Signature = /^[A-Za-z0-9_-]{86}$/;
const defaultExecutionLeaseSeconds = 90;

interface JobRow extends Record<string, unknown> {
  id: string;
  job_type: ResearchJobAuthorizationEnvelope["jobType"];
  output_kind: ResearchJobAuthorizationEnvelope["outputKind"];
  output_id: string;
  output_version: string;
  code_revision: string;
  configuration_sha256: string;
  runner_image_digest: string;
  intended_use: string;
  exclusions: string[] | string;
  requested_by_actor_id: string;
  requested_at: string | Date;
  expires_at: string | Date;
  approved_by_actor_id: string | null;
  approved_at: string | Date | null;
  envelope_sha256: string | null;
  inputs: ResearchJobAuthorizationEnvelope["inputs"] | string;
}

interface WorkloadJobRow extends JobRow {
  public_key_pem: string;
  public_key_sha256: string;
}

interface LaunchContextRow extends WorkloadJobRow {
  dispatch_recorded_at: string | Date;
  dispatch_expires_at: string | Date;
  scheduler_workload_id: string;
  scheduler_signing_key_id: string;
  scheduler_public_key_sha256: string;
}

interface ExternalTerminationContextRow extends WorkloadJobRow {
  cancellation_revision: number;
  cancellation_sequence_id: number;
  cancellation_cancelled_at: string | Date;
  cancellation_latest_at: string | Date;
  cancellation_source: SignedResearchJobExternalTerminationAttestation["termination"]["cancellationSource"];
  cancellation_reason: ResearchJobCancellationReason;
  launch_recorded_at: string | Date;
}

interface WorkloadVerification {
  readonly tenantId: string;
  readonly workloadId: string;
  readonly signingKeyId: string;
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly payloadSha256: string;
  readonly signatureSha256: string;
}

interface CancellationContextRow extends WorkloadJobRow {
  cancellation_revision: number;
  cancellation_sequence_id: number;
  cancellation_cancelled_at: string | Date;
  cancellation_latest_at: string | Date;
  cancellation_source: SignedResearchJobCancellationAcknowledgement["acknowledgement"]["cancellationSource"];
  cancellation_reason: ResearchJobCancellationReason;
}

interface CancellationAcknowledgementRow extends Record<string, unknown> {
  acknowledgement_id: string;
  job_id: string;
  claim_id: string;
  cancellation_revision: number;
  cancellation_sequence_id: number;
  cancellation_source: ResearchJobCancellationAcknowledgementReceipt["cancellationSource"];
  cancellation_reason: ResearchJobCancellationReason;
  termination_outcome: ResearchJobCancellationAcknowledgementReceipt["terminationOutcome"];
  process_reference_sha256: string | null;
  termination_evidence_sha256: string;
  acknowledged_by_workload_id: string;
  signing_key_id: string;
  public_key_sha256: string;
  attestation_issued_at: string | Date;
  attestation_payload_sha256: string;
  signature_sha256: string;
  recorded_at: string | Date;
}

interface HeartbeatRow extends Record<string, unknown> {
  heartbeat_id: string;
  job_id: string;
  claim_id: string;
  heartbeat_sequence: number;
  runner_state: ResearchJobHeartbeatReceipt["runnerState"];
  cancellation_revision: number;
  process_reference_sha256: string;
  liveness_evidence_sha256: string;
  reported_by_workload_id: string;
  signing_key_id: string;
  public_key_sha256: string;
  attestation_issued_at: string | Date;
  attestation_payload_sha256: string;
  signature_sha256: string;
  recorded_at: string | Date;
}

interface LivenessSnapshotRow extends Record<string, unknown> {
  snapshot_id: string;
  job_id: string;
  claim_id: string;
  status: ResearchJobLivenessSnapshot["status"];
  lease_duration_seconds: number;
  lease_started_at: string | Date;
  lease_expires_at: string | Date;
  lease_expired: boolean;
  last_heartbeat_id: string | null;
  last_heartbeat_sequence: number;
  last_heartbeat_state: "running" | "cancellation-observed" | null;
  last_heartbeat_cancellation_revision: number | null;
  cancellation_revision: number;
  terminal_status: "succeeded" | "failed" | "cancelled" | null;
  alert_required: boolean;
  generated_by_actor_id: string;
  generated_at: string | Date;
  alert_delivery_evidence_present: boolean;
}

interface AlertDeliveryContextRow extends LivenessSnapshotRow {
  public_key_pem: string;
  public_key_sha256: string;
}

interface AlertDeliveryRow extends Record<string, unknown> {
  delivery_id: string;
  snapshot_id: string;
  job_id: string;
  claim_id: string;
  snapshot_status: ResearchJobAlertDeliveryReceipt["snapshotStatus"];
  cancellation_revision: number;
  snapshot_generated_at: string | Date;
  snapshot_payload_sha256: string;
  channel_reference_sha256: string;
  delivery_receipt_sha256: string;
  outcome: "delivered";
  attested_by_workload_id: string;
  signing_key_id: string;
  public_key_sha256: string;
  attestation_issued_at: string | Date;
  attestation_payload_sha256: string;
  signature_sha256: string;
  recorded_at: string | Date;
}

interface DispatchRow extends Record<string, unknown> {
  dispatch_id: string;
  job_id: string;
  envelope_sha256: string;
  dispatch_revision: number;
  assigned_workload_id: string;
  expires_at: string | Date;
  dispatched_by_workload_id: string;
  signing_key_id: string;
  public_key_sha256: string;
  attestation_issued_at: string | Date;
  attestation_payload_sha256: string;
  signature_sha256: string;
  recorded_at: string | Date;
}

interface LaunchRow extends Record<string, unknown> {
  launch_id: string;
  job_id: string;
  envelope_sha256: string;
  dispatch_id: string;
  dispatch_revision: number;
  assigned_workload_id: string;
  runner_image_digest: string;
  process_reference_sha256: string;
  execution_identity_sha256: string;
  network_policy_sha256: string;
  attested_by_provider_workload_id: string;
  signing_key_id: string;
  public_key_sha256: string;
  attestation_issued_at: string | Date;
  attestation_payload_sha256: string;
  signature_sha256: string;
  recorded_at: string | Date;
}

interface ExternalTerminationRow extends Record<string, unknown> {
  termination_attestation_id: string;
  job_id: string;
  claim_id: string;
  envelope_sha256: string;
  launch_id: string;
  dispatch_id: string;
  dispatch_revision: number;
  assigned_workload_id: string;
  cancellation_revision: number;
  cancellation_sequence_id: number;
  cancellation_source: ResearchJobExternalTerminationReceipt["cancellationSource"];
  cancellation_reason: ResearchJobCancellationReason;
  outcome: "process-stopped";
  process_reference_sha256: string;
  termination_evidence_sha256: string;
  attested_by_provider_workload_id: string;
  signing_key_id: string;
  public_key_sha256: string;
  attestation_issued_at: string | Date;
  attestation_payload_sha256: string;
  signature_sha256: string;
  recorded_at: string | Date;
}

interface TerminalRow extends Record<string, unknown> {
  receipt_id: string;
  job_id: string;
  claim_id: string;
  envelope_sha256: string;
  terminal_status: ResearchJobTerminalReceipt["status"];
  terminal_payload_sha256: string;
  output_artifact_id: string | null;
  output_binding_id: string | null;
  requested_output_kind: ResearchJobOutputKind | null;
  output_artifact_kind: Exclude<ArtifactKind, "deployment"> | null;
  output_version: string | null;
  output_sha256: string | null;
  failure_code:
    | "runner-failed"
    | "output-validation-failed"
    | "cancellation-observed"
    | null;
  failure_detail_sha256: string | null;
  cancellation_acknowledgement_id: string | null;
  cancellation_revision: number | null;
  external_termination_attestation_id: string | null;
  completed_by_actor_id: string | null;
  completed_by_workload_id: string | null;
  signing_key_id: string | null;
  signature_algorithm: "Ed25519" | null;
  public_key_sha256: string | null;
  attestation_issued_at: string | Date | null;
  attestation_payload_sha256: string | null;
  signature_sha256: string | null;
  recorded_at: string | Date;
}

const freshInputCtes = `
  dependency AS (
    SELECT dependency.* FROM artifact_consent_dependencies AS dependency
    INNER JOIN research_job_inputs AS input
      ON input.artifact_id = dependency.artifact_id
     AND input.tenant_id = dependency.tenant_id
    WHERE input.job_id = $3 AND input.tenant_id = $1
  ), locked_learner AS MATERIALIZED (
    SELECT learner.* FROM learners AS learner
    INNER JOIN (SELECT DISTINCT learner_id FROM dependency) AS subject
      ON subject.learner_id = learner.id
    WHERE learner.tenant_id = $1
    ORDER BY learner.id
    FOR UPDATE OF learner
  ), current_input AS (
    SELECT input.artifact_id, input.binding_id
    FROM research_job_inputs AS input
    INNER JOIN ml_artifacts AS artifact
      ON artifact.id = input.artifact_id AND artifact.tenant_id = input.tenant_id
     AND artifact.status = 'active' AND artifact.sha256 = input.artifact_sha256
     AND artifact.kind = input.artifact_kind
    INNER JOIN managed_artifact_objects AS binding
      ON binding.id = input.binding_id AND binding.tenant_id = input.tenant_id
     AND binding.artifact_id = input.artifact_id
     AND binding.provider_id = input.provider_id
     AND binding.object_reference_sha256 = input.object_reference_sha256
     AND binding.provider_object_version = input.provider_object_version
     AND binding.expected_sha256 = input.artifact_sha256
    INNER JOIN LATERAL (
      SELECT observation.*
      FROM managed_artifact_object_observations AS observation
      WHERE observation.binding_id = binding.id
        AND observation.tenant_id = binding.tenant_id
        AND observation.artifact_id = binding.artifact_id
      ORDER BY observation.recorded_at DESC, observation.id DESC
      LIMIT 1
    ) AS latest ON latest.outcome = 'consistent'
      AND latest.artifact_status = 'active'
      AND latest.object_exists = TRUE
      AND latest.observed_sha256 = artifact.sha256
      AND latest.access_state = 'available'
    WHERE input.job_id = $3 AND input.tenant_id = $1
      AND EXISTS (
        SELECT 1 FROM artifact_consent_dependencies AS required_dependency
        WHERE required_dependency.artifact_id = input.artifact_id
          AND required_dependency.tenant_id = input.tenant_id
      )
      AND NOT EXISTS (
        SELECT 1 FROM artifact_consent_dependencies AS consent_dependency
        LEFT JOIN locked_learner AS learner
          ON learner.id = consent_dependency.learner_id
         AND learner.tenant_id = consent_dependency.tenant_id
        LEFT JOIN consent_snapshots AS consent
          ON consent.id = consent_dependency.consent_snapshot_id
         AND consent.tenant_id = consent_dependency.tenant_id
         AND consent.learner_id = consent_dependency.learner_id
        WHERE consent_dependency.artifact_id = input.artifact_id
          AND consent_dependency.tenant_id = input.tenant_id
          AND (
            learner.id IS NULL OR learner.deleted_at IS NOT NULL
            OR learner.current_consent_version <> consent.version
            OR consent.id IS NULL OR consent.research_use = FALSE
            OR consent.assent_status NOT IN ('affirmed', 'not-applicable')
            OR CASE consent_dependency.processing_purpose
              WHEN 'audio-research' THEN NOT consent.audio_processing
              WHEN 'visual-research' THEN NOT consent.video_processing
              ELSE TRUE
            END
          )
      )
  )`;

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function postgresErrorCode(error: unknown): string | undefined {
  return typeof error === "object" && error !== null && "code" in error
    && typeof error.code === "string" ? error.code : undefined;
}

function validateActor(actor: ActorContext): void {
  if (!opaque.test(actor.actorId) || !opaque.test(actor.tenantId)) {
    throw new PlatformDataError("invalid-identifier", "Actor and tenant identifiers must be opaque tokens.");
  }
}

function stringArray(value: string[] | string): readonly string[] {
  return typeof value === "string" ? JSON.parse(value) as string[] : value;
}

function inputs(value: ResearchJobAuthorizationEnvelope["inputs"] | string) {
  return typeof value === "string"
    ? JSON.parse(value) as ResearchJobAuthorizationEnvelope["inputs"]
    : value;
}

function mapEnvelope(row: JobRow): ResearchJobAuthorizationEnvelope {
  return {
    schemaVersion: "research-job-authorization-v1",
    jobId: row.id,
    jobType: row.job_type,
    inputs: inputs(row.inputs),
    outputKind: row.output_kind,
    outputId: row.output_id,
    outputVersion: row.output_version,
    codeRevision: row.code_revision,
    configurationSha256: row.configuration_sha256,
    runnerImageDigest: row.runner_image_digest,
    intendedUse: row.intended_use,
    exclusions: stringArray(row.exclusions),
    requestedByActorId: row.requested_by_actor_id,
    requestedAt: timestamp(row.requested_at),
    expiresAt: timestamp(row.expires_at),
    ...(row.approved_by_actor_id === null ? {} : { approvedByActorId: row.approved_by_actor_id }),
    ...(row.approved_at === null ? {} : { approvedAt: timestamp(row.approved_at) }),
    ...(row.envelope_sha256 === null ? {} : { envelopeSha256: row.envelope_sha256 }),
    releasePosture: "research-only",
    learnerFeedbackEligible: false,
    approvalPosture: row.approved_by_actor_id === null ? "pending" : "database-attested",
    cryptographicSignaturePresent: false,
    productionGateEligible: false,
  };
}

function mapTerminalReceipt(row: TerminalRow): ResearchJobTerminalReceipt {
  return {
    receiptId: row.receipt_id,
    jobId: row.job_id,
    claimId: row.claim_id,
    envelopeSha256: row.envelope_sha256,
    status: row.terminal_status,
    terminalPayloadSha256: row.terminal_payload_sha256,
    ...(row.output_artifact_id === null ? {} : { outputArtifactId: row.output_artifact_id }),
    ...(row.output_binding_id === null ? {} : { outputBindingId: row.output_binding_id }),
    ...(row.requested_output_kind === null ? {} : {
      requestedOutputKind: row.requested_output_kind,
    }),
    ...(row.output_artifact_kind === null ? {} : {
      outputArtifactKind: row.output_artifact_kind,
    }),
    ...(row.output_version === null ? {} : { outputVersion: row.output_version }),
    ...(row.output_sha256 === null ? {} : { outputSha256: row.output_sha256 }),
    ...(row.failure_code === null ? {} : { failureCode: row.failure_code }),
    ...(row.failure_detail_sha256 === null ? {} : {
      failureDetailSha256: row.failure_detail_sha256,
    }),
    ...(row.cancellation_acknowledgement_id === null ? {} : {
      cancellationAcknowledgementId: row.cancellation_acknowledgement_id,
    }),
    ...(row.cancellation_revision === null ? {} : {
      cancellationRevision: Number(row.cancellation_revision),
    }),
    ...(row.external_termination_attestation_id === null ? {} : {
      externalTerminationAttestationId: row.external_termination_attestation_id,
    }),
    ...(row.completed_by_actor_id === null ? {} : {
      completedByActorId: row.completed_by_actor_id,
    }),
    ...(row.completed_by_workload_id === null ? {} : {
      completedByWorkloadId: row.completed_by_workload_id,
    }),
    ...(row.signing_key_id === null || row.signature_algorithm === null
      || row.public_key_sha256 === null || row.attestation_issued_at === null
      || row.attestation_payload_sha256 === null || row.signature_sha256 === null
      ? {} : { signatureVerification: {
        signingKeyId: row.signing_key_id,
        algorithm: row.signature_algorithm,
        publicKeySha256: row.public_key_sha256,
        issuedAt: timestamp(row.attestation_issued_at),
        payloadSha256: row.attestation_payload_sha256,
        signatureSha256: row.signature_sha256,
      } }),
    recordedAt: timestamp(row.recorded_at),
    releasePosture: "research-only",
    learnerFeedbackEligible: false,
    evidencePosture: "local-foundation",
    productionGateEligible: false,
  };
}

function mapCancellationAcknowledgement(
  row: CancellationAcknowledgementRow,
): ResearchJobCancellationAcknowledgementReceipt {
  return {
    acknowledgementId: row.acknowledgement_id,
    jobId: row.job_id,
    claimId: row.claim_id,
    cancellationRevision: Number(row.cancellation_revision),
    cancellationSequenceId: Number(row.cancellation_sequence_id),
    cancellationSource: row.cancellation_source,
    cancellationReason: row.cancellation_reason,
    terminationOutcome: row.termination_outcome,
    ...(row.process_reference_sha256 === null ? {} : {
      processReferenceSha256: row.process_reference_sha256,
    }),
    terminationEvidenceSha256: row.termination_evidence_sha256,
    acknowledgedByWorkloadId: row.acknowledged_by_workload_id,
    signingKeyId: row.signing_key_id,
    publicKeySha256: row.public_key_sha256,
    issuedAt: timestamp(row.attestation_issued_at),
    payloadSha256: row.attestation_payload_sha256,
    signatureSha256: row.signature_sha256,
    recordedAt: timestamp(row.recorded_at),
    evidencePosture: "workload-attested",
    independentlyVerifiedProcessTermination: false,
    productionGateEligible: false,
  };
}

function mapHeartbeat(row: HeartbeatRow): ResearchJobHeartbeatReceipt {
  return {
    heartbeatId: row.heartbeat_id,
    jobId: row.job_id,
    claimId: row.claim_id,
    heartbeatSequence: Number(row.heartbeat_sequence),
    runnerState: row.runner_state,
    cancellationRevision: Number(row.cancellation_revision),
    processReferenceSha256: row.process_reference_sha256,
    livenessEvidenceSha256: row.liveness_evidence_sha256,
    reportedByWorkloadId: row.reported_by_workload_id,
    signingKeyId: row.signing_key_id,
    publicKeySha256: row.public_key_sha256,
    issuedAt: timestamp(row.attestation_issued_at),
    payloadSha256: row.attestation_payload_sha256,
    signatureSha256: row.signature_sha256,
    recordedAt: timestamp(row.recorded_at),
    evidencePosture: "workload-attested",
    independentlyVerifiedProcessLiveness: false,
    productionGateEligible: false,
  };
}

function mapLivenessSnapshot(
  row: LivenessSnapshotRow,
): ResearchJobLivenessSnapshot {
  return {
    snapshotId: row.snapshot_id,
    jobId: row.job_id,
    claimId: row.claim_id,
    status: row.status,
    leaseDurationSeconds: Number(row.lease_duration_seconds),
    leaseStartedAt: timestamp(row.lease_started_at),
    leaseExpiresAt: timestamp(row.lease_expires_at),
    leaseExpired: row.lease_expired,
    ...(row.last_heartbeat_id === null ? {} : {
      lastHeartbeatId: row.last_heartbeat_id,
    }),
    lastHeartbeatSequence: Number(row.last_heartbeat_sequence),
    ...(row.last_heartbeat_state === null ? {} : {
      lastHeartbeatState: row.last_heartbeat_state,
    }),
    ...(row.last_heartbeat_cancellation_revision === null ? {} : {
      lastHeartbeatCancellationRevision: Number(
        row.last_heartbeat_cancellation_revision,
      ),
    }),
    cancellationRevision: Number(row.cancellation_revision),
    ...(row.terminal_status === null ? {} : { terminalStatus: row.terminal_status }),
    alertRequired: row.alert_required,
    generatedByActorId: row.generated_by_actor_id,
    generatedAt: timestamp(row.generated_at),
    externalProcessLivenessVerified: false,
    alertDeliveryEvidencePresent: row.alert_delivery_evidence_present,
    evidencePosture: "local-foundation",
    productionGateEligible: false,
  };
}

function mapAlertDelivery(row: AlertDeliveryRow): ResearchJobAlertDeliveryReceipt {
  return {
    deliveryId: row.delivery_id,
    snapshotId: row.snapshot_id,
    jobId: row.job_id,
    claimId: row.claim_id,
    snapshotStatus: row.snapshot_status,
    cancellationRevision: Number(row.cancellation_revision),
    snapshotGeneratedAt: timestamp(row.snapshot_generated_at),
    snapshotPayloadSha256: row.snapshot_payload_sha256,
    channelReferenceSha256: row.channel_reference_sha256,
    deliveryReceiptSha256: row.delivery_receipt_sha256,
    outcome: row.outcome,
    attestedByWorkloadId: row.attested_by_workload_id,
    signingKeyId: row.signing_key_id,
    publicKeySha256: row.public_key_sha256,
    issuedAt: timestamp(row.attestation_issued_at),
    payloadSha256: row.attestation_payload_sha256,
    signatureSha256: row.signature_sha256,
    recordedAt: timestamp(row.recorded_at),
    authenticatedDeliveryAttestationVerified: true,
    externalProviderKeyCustodyVerified: false,
    productionGateEligible: false,
  };
}

function mapDispatch(row: DispatchRow): ResearchJobDispatchReceipt {
  return {
    dispatchId: row.dispatch_id,
    jobId: row.job_id,
    envelopeSha256: row.envelope_sha256,
    dispatchRevision: Number(row.dispatch_revision),
    assignedWorkloadId: row.assigned_workload_id,
    expiresAt: timestamp(row.expires_at),
    dispatchedByWorkloadId: row.dispatched_by_workload_id,
    signingKeyId: row.signing_key_id,
    publicKeySha256: row.public_key_sha256,
    issuedAt: timestamp(row.attestation_issued_at),
    payloadSha256: row.attestation_payload_sha256,
    signatureSha256: row.signature_sha256,
    recordedAt: timestamp(row.recorded_at),
    evidencePosture: "workload-attested",
    externalSchedulerLaunchVerified: false,
    productionGateEligible: false,
  };
}

function mapLaunch(row: LaunchRow): ResearchJobLaunchReceipt {
  return {
    launchId: row.launch_id,
    jobId: row.job_id,
    envelopeSha256: row.envelope_sha256,
    dispatchId: row.dispatch_id,
    dispatchRevision: Number(row.dispatch_revision),
    assignedWorkloadId: row.assigned_workload_id,
    runnerImageDigest: row.runner_image_digest,
    processReferenceSha256: row.process_reference_sha256,
    executionIdentitySha256: row.execution_identity_sha256,
    networkPolicySha256: row.network_policy_sha256,
    attestedByProviderWorkloadId: row.attested_by_provider_workload_id,
    signingKeyId: row.signing_key_id,
    publicKeySha256: row.public_key_sha256,
    issuedAt: timestamp(row.attestation_issued_at),
    payloadSha256: row.attestation_payload_sha256,
    signatureSha256: row.signature_sha256,
    recordedAt: timestamp(row.recorded_at),
    launchAttestationVerified: true,
    externalProviderKeyCustodyVerified: false,
    productionGateEligible: false,
  };
}

function mapExternalTermination(
  row: ExternalTerminationRow,
): ResearchJobExternalTerminationReceipt {
  return {
    terminationAttestationId: row.termination_attestation_id,
    jobId: row.job_id,
    claimId: row.claim_id,
    envelopeSha256: row.envelope_sha256,
    launchId: row.launch_id,
    dispatchId: row.dispatch_id,
    dispatchRevision: Number(row.dispatch_revision),
    assignedWorkloadId: row.assigned_workload_id,
    cancellationRevision: Number(row.cancellation_revision),
    cancellationSequenceId: Number(row.cancellation_sequence_id),
    cancellationSource: row.cancellation_source,
    cancellationReason: row.cancellation_reason,
    outcome: row.outcome,
    processReferenceSha256: row.process_reference_sha256,
    terminationEvidenceSha256: row.termination_evidence_sha256,
    attestedByProviderWorkloadId: row.attested_by_provider_workload_id,
    signingKeyId: row.signing_key_id,
    publicKeySha256: row.public_key_sha256,
    issuedAt: timestamp(row.attestation_issued_at),
    payloadSha256: row.attestation_payload_sha256,
    signatureSha256: row.signature_sha256,
    recordedAt: timestamp(row.recorded_at),
    externalTerminationAttestationVerified: true,
    externalProviderKeyCustodyVerified: false,
    productionGateEligible: false,
  };
}

export function canonicalResearchJobAuthorizationPayload(
  envelope: ResearchJobAuthorizationEnvelope,
  approvedByActorId: string,
): string {
  return JSON.stringify({
    schemaVersion: envelope.schemaVersion,
    jobId: envelope.jobId,
    jobType: envelope.jobType,
    inputs: [...envelope.inputs].sort((a, b) =>
      `${a.artifactId}\0${a.bindingId}`.localeCompare(`${b.artifactId}\0${b.bindingId}`)
    ).map((input) => ({
      artifactId: input.artifactId,
      artifactKind: input.artifactKind,
      artifactSha256: input.artifactSha256,
      bindingId: input.bindingId,
      providerId: input.providerId,
      objectReferenceSha256: input.objectReferenceSha256,
      providerObjectVersion: input.providerObjectVersion,
    })),
    outputKind: envelope.outputKind,
    outputId: envelope.outputId,
    outputVersion: envelope.outputVersion,
    codeRevision: envelope.codeRevision,
    configurationSha256: envelope.configurationSha256,
    runnerImageDigest: envelope.runnerImageDigest,
    intendedUse: envelope.intendedUse,
    exclusions: [...envelope.exclusions].sort(),
    requestedByActorId: envelope.requestedByActorId,
    requestedAt: envelope.requestedAt,
    expiresAt: envelope.expiresAt,
    approvedByActorId,
    releasePosture: "research-only",
    learnerFeedbackEligible: false,
  });
}

function envelopeHash(envelope: ResearchJobAuthorizationEnvelope, approvedByActorId: string): string {
  return createHash("sha256").update(
    canonicalResearchJobAuthorizationPayload(envelope, approvedByActorId),
  ).digest("hex");
}

export function canonicalResearchJobTerminalPayload(
  input: ResearchJobTerminalInput,
  envelopeSha256: string,
): string {
  return JSON.stringify({
    schemaVersion: "research-job-terminal-v1",
    jobId: input.jobId,
    claimId: input.claimId,
    envelopeSha256,
    status: input.status,
    ...(input.status === "succeeded" ? {
      outputSha256: input.outputSha256,
      bindingId: input.bindingId,
      providerId: input.providerId,
      objectReferenceSha256: input.objectReferenceSha256,
      providerObjectVersion: input.providerObjectVersion,
      providerCheckedAt: input.providerCheckedAt,
      providerReceiptReference: input.providerReceiptReference,
      providerReceiptSha256: input.providerReceiptSha256,
    } : input.status === "cancelled" ? {
      failureCode: input.failureCode,
      failureDetailSha256: input.failureDetailSha256,
      cancellationAcknowledgementId: input.cancellationAcknowledgementId,
      cancellationRevision: input.cancellationRevision,
    } : {
      failureCode: input.failureCode,
      failureDetailSha256: input.failureDetailSha256,
    }),
  });
}

export function canonicalResearchJobExecutionClaimPayload(
  claim: Omit<SignedResearchJobExecutionClaim, "signature">,
): string {
  return JSON.stringify({
    schemaVersion: claim.schemaVersion,
    tenantId: claim.tenantId,
    workloadId: claim.workloadId,
    signingKeyId: claim.signingKeyId,
    algorithm: claim.algorithm,
    issuedAt: claim.issuedAt,
    claimId: claim.claimId,
    jobId: claim.jobId,
    envelopeSha256: claim.envelopeSha256,
    dispatchId: claim.dispatchId,
    dispatchRevision: claim.dispatchRevision,
  });
}

export function canonicalResearchJobDispatchPayload(
  signed: Omit<SignedResearchJobDispatch, "signature">,
): string {
  return JSON.stringify({
    schemaVersion: signed.schemaVersion,
    tenantId: signed.tenantId,
    schedulerWorkloadId: signed.schedulerWorkloadId,
    signingKeyId: signed.signingKeyId,
    algorithm: signed.algorithm,
    issuedAt: signed.issuedAt,
    dispatch: {
      dispatchId: signed.dispatch.dispatchId,
      jobId: signed.dispatch.jobId,
      envelopeSha256: signed.dispatch.envelopeSha256,
      dispatchRevision: signed.dispatch.dispatchRevision,
      assignedWorkloadId: signed.dispatch.assignedWorkloadId,
      expiresAt: signed.dispatch.expiresAt,
    },
  });
}

export function canonicalResearchJobLaunchAttestationPayload(
  signed: Omit<SignedResearchJobLaunchAttestation, "signature">,
): string {
  return JSON.stringify({
    schemaVersion: signed.schemaVersion,
    tenantId: signed.tenantId,
    providerWorkloadId: signed.providerWorkloadId,
    signingKeyId: signed.signingKeyId,
    algorithm: signed.algorithm,
    issuedAt: signed.issuedAt,
    launch: {
      launchId: signed.launch.launchId,
      jobId: signed.launch.jobId,
      envelopeSha256: signed.launch.envelopeSha256,
      dispatchId: signed.launch.dispatchId,
      dispatchRevision: signed.launch.dispatchRevision,
      assignedWorkloadId: signed.launch.assignedWorkloadId,
      runnerImageDigest: signed.launch.runnerImageDigest,
      processReferenceSha256: signed.launch.processReferenceSha256,
      executionIdentitySha256: signed.launch.executionIdentitySha256,
      networkPolicySha256: signed.launch.networkPolicySha256,
    },
  });
}

export function canonicalResearchJobExternalTerminationPayload(
  signed: Omit<SignedResearchJobExternalTerminationAttestation, "signature">,
): string {
  return JSON.stringify({
    schemaVersion: signed.schemaVersion,
    tenantId: signed.tenantId,
    providerWorkloadId: signed.providerWorkloadId,
    signingKeyId: signed.signingKeyId,
    algorithm: signed.algorithm,
    issuedAt: signed.issuedAt,
    termination: {
      terminationAttestationId: signed.termination.terminationAttestationId,
      jobId: signed.termination.jobId,
      claimId: signed.termination.claimId,
      envelopeSha256: signed.termination.envelopeSha256,
      launchId: signed.termination.launchId,
      dispatchId: signed.termination.dispatchId,
      dispatchRevision: signed.termination.dispatchRevision,
      assignedWorkloadId: signed.termination.assignedWorkloadId,
      cancellationRevision: signed.termination.cancellationRevision,
      cancellationSequenceId: signed.termination.cancellationSequenceId,
      cancellationSource: signed.termination.cancellationSource,
      cancellationReason: signed.termination.cancellationReason,
      outcome: signed.termination.outcome,
      processReferenceSha256: signed.termination.processReferenceSha256,
      terminationEvidenceSha256: signed.termination.terminationEvidenceSha256,
    },
  });
}

export function canonicalResearchJobLivenessSnapshotPayload(
  snapshot: ResearchJobLivenessSnapshot,
): string {
  return JSON.stringify({
    snapshotId: snapshot.snapshotId,
    jobId: snapshot.jobId,
    claimId: snapshot.claimId,
    status: snapshot.status,
    leaseDurationSeconds: snapshot.leaseDurationSeconds,
    leaseStartedAt: snapshot.leaseStartedAt,
    leaseExpiresAt: snapshot.leaseExpiresAt,
    leaseExpired: snapshot.leaseExpired,
    lastHeartbeatId: snapshot.lastHeartbeatId ?? null,
    lastHeartbeatSequence: snapshot.lastHeartbeatSequence,
    lastHeartbeatState: snapshot.lastHeartbeatState ?? null,
    lastHeartbeatCancellationRevision:
      snapshot.lastHeartbeatCancellationRevision ?? null,
    cancellationRevision: snapshot.cancellationRevision,
    terminalStatus: snapshot.terminalStatus ?? null,
    alertRequired: snapshot.alertRequired,
    generatedByActorId: snapshot.generatedByActorId,
    generatedAt: snapshot.generatedAt,
  });
}

export function canonicalResearchJobAlertDeliveryPayload(
  signed: Omit<SignedResearchJobAlertDeliveryAttestation, "signature">,
): string {
  return JSON.stringify({
    schemaVersion: signed.schemaVersion,
    tenantId: signed.tenantId,
    alertDeliveryWorkloadId: signed.alertDeliveryWorkloadId,
    signingKeyId: signed.signingKeyId,
    algorithm: signed.algorithm,
    issuedAt: signed.issuedAt,
    delivery: {
      deliveryId: signed.delivery.deliveryId,
      snapshotId: signed.delivery.snapshotId,
      jobId: signed.delivery.jobId,
      claimId: signed.delivery.claimId,
      snapshotStatus: signed.delivery.snapshotStatus,
      cancellationRevision: signed.delivery.cancellationRevision,
      snapshotGeneratedAt: signed.delivery.snapshotGeneratedAt,
      snapshotPayloadSha256: signed.delivery.snapshotPayloadSha256,
      channelReferenceSha256: signed.delivery.channelReferenceSha256,
      deliveryReceiptSha256: signed.delivery.deliveryReceiptSha256,
      outcome: signed.delivery.outcome,
    },
  });
}

export function canonicalResearchJobTerminalAttestationPayload(
  attestation: Omit<SignedResearchJobTerminalAttestation, "signature">,
  envelopeSha256: string,
): string {
  return JSON.stringify({
    schemaVersion: attestation.schemaVersion,
    tenantId: attestation.tenantId,
    workloadId: attestation.workloadId,
    signingKeyId: attestation.signingKeyId,
    algorithm: attestation.algorithm,
    issuedAt: attestation.issuedAt,
    terminal: JSON.parse(
      canonicalResearchJobTerminalPayload(attestation.terminal, envelopeSha256),
    ) as unknown,
  });
}

export function canonicalResearchJobCancellationAcknowledgementPayload(
  signed: Omit<SignedResearchJobCancellationAcknowledgement, "signature">,
  envelopeSha256: string,
): string {
  return JSON.stringify({
    schemaVersion: signed.schemaVersion,
    tenantId: signed.tenantId,
    workloadId: signed.workloadId,
    signingKeyId: signed.signingKeyId,
    algorithm: signed.algorithm,
    issuedAt: signed.issuedAt,
    envelopeSha256,
    acknowledgement: {
      jobId: signed.acknowledgement.jobId,
      claimId: signed.acknowledgement.claimId,
      cancellationRevision: signed.acknowledgement.cancellationRevision,
      cancellationSequenceId: signed.acknowledgement.cancellationSequenceId,
      cancellationSource: signed.acknowledgement.cancellationSource,
      cancellationReason: signed.acknowledgement.cancellationReason,
      terminationOutcome: signed.acknowledgement.terminationOutcome,
      ...(signed.acknowledgement.processReferenceSha256 === undefined ? {} : {
        processReferenceSha256: signed.acknowledgement.processReferenceSha256,
      }),
      terminationEvidenceSha256: signed.acknowledgement.terminationEvidenceSha256,
    },
  });
}

export function canonicalResearchJobHeartbeatPayload(
  signed: Omit<SignedResearchJobHeartbeat, "signature">,
  envelopeSha256: string,
): string {
  return JSON.stringify({
    schemaVersion: signed.schemaVersion,
    tenantId: signed.tenantId,
    workloadId: signed.workloadId,
    signingKeyId: signed.signingKeyId,
    algorithm: signed.algorithm,
    issuedAt: signed.issuedAt,
    envelopeSha256,
    heartbeat: {
      heartbeatId: signed.heartbeat.heartbeatId,
      jobId: signed.heartbeat.jobId,
      claimId: signed.heartbeat.claimId,
      heartbeatSequence: signed.heartbeat.heartbeatSequence,
      runnerState: signed.heartbeat.runnerState,
      cancellationRevision: signed.heartbeat.cancellationRevision,
      processReferenceSha256: signed.heartbeat.processReferenceSha256,
      livenessEvidenceSha256: signed.heartbeat.livenessEvidenceSha256,
    },
  });
}

export class ResearchJobAuthorizationService {
  readonly #database: DatabaseClient;
  readonly #now: () => Date;
  readonly #executionLeaseSeconds: number;

  constructor(
    database: DatabaseClient,
    now: () => Date = () => new Date(),
    executionLeaseSeconds: number = defaultExecutionLeaseSeconds,
  ) {
    if (!Number.isInteger(executionLeaseSeconds)
      || executionLeaseSeconds < 1 || executionLeaseSeconds > 300) {
      throw new PlatformDataError(
        "invalid-artifact",
        "Research execution leases must last 1 to 300 seconds.",
      );
    }
    this.#database = database;
    this.#now = now;
    this.#executionLeaseSeconds = executionLeaseSeconds;
  }

  async request(actor: ActorContext, input: ResearchJobRequestInput): Promise<ResearchJobAuthorizationEnvelope> {
    validateActor(actor);
    this.#validateRequest(input);
    const auditId = randomUUID();
    const requested = JSON.stringify(input.inputs);
    const exclusions = JSON.stringify([...input.exclusions].sort());
    const result = await this.#database.query<JobRow>(
      `
      WITH requested AS (
        SELECT * FROM jsonb_to_recordset($14::JSONB) AS item(
          "artifactId" TEXT, "bindingId" TEXT
        )
      ), authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), dependency AS (
        SELECT dependency.* FROM artifact_consent_dependencies AS dependency
        INNER JOIN requested ON requested."artifactId" = dependency.artifact_id
        WHERE dependency.tenant_id = $1
      ), locked_learner AS MATERIALIZED (
        SELECT learner.* FROM learners AS learner
        INNER JOIN (SELECT DISTINCT learner_id FROM dependency) AS subject
          ON subject.learner_id = learner.id
        WHERE learner.tenant_id = $1 ORDER BY learner.id FOR UPDATE OF learner
      ), eligible AS (
        SELECT artifact.id AS artifact_id, artifact.kind AS artifact_kind,
          artifact.sha256 AS artifact_sha256, binding.id AS binding_id,
          binding.provider_id, binding.object_reference_sha256,
          binding.provider_object_version
        FROM requested
        INNER JOIN ml_artifacts AS artifact
          ON artifact.id = requested."artifactId" AND artifact.tenant_id = $1
         AND artifact.status = 'active'
        INNER JOIN managed_artifact_objects AS binding
          ON binding.id = requested."bindingId" AND binding.tenant_id = $1
         AND binding.artifact_id = artifact.id AND binding.expected_sha256 = artifact.sha256
        INNER JOIN LATERAL (
          SELECT observation.* FROM managed_artifact_object_observations AS observation
          WHERE observation.binding_id = binding.id AND observation.tenant_id = $1
            AND observation.artifact_id = artifact.id
          ORDER BY observation.recorded_at DESC, observation.id DESC LIMIT 1
        ) AS latest ON latest.outcome = 'consistent'
          AND latest.artifact_status = 'active' AND latest.object_exists = TRUE
          AND latest.observed_sha256 = artifact.sha256 AND latest.access_state = 'available'
        WHERE EXISTS (
          SELECT 1 FROM artifact_consent_dependencies AS required_dependency
          WHERE required_dependency.artifact_id = artifact.id
            AND required_dependency.tenant_id = artifact.tenant_id
        )
        AND NOT EXISTS (
          SELECT 1 FROM artifact_consent_dependencies AS consent_dependency
          LEFT JOIN locked_learner AS learner ON learner.id = consent_dependency.learner_id
            AND learner.tenant_id = consent_dependency.tenant_id
          LEFT JOIN consent_snapshots AS consent ON consent.id = consent_dependency.consent_snapshot_id
            AND consent.tenant_id = consent_dependency.tenant_id
            AND consent.learner_id = consent_dependency.learner_id
          WHERE consent_dependency.artifact_id = artifact.id
            AND consent_dependency.tenant_id = artifact.tenant_id
            AND (learner.id IS NULL OR learner.deleted_at IS NOT NULL
              OR learner.current_consent_version <> consent.version
              OR consent.id IS NULL OR consent.research_use = FALSE
              OR consent.assent_status NOT IN ('affirmed', 'not-applicable')
              OR CASE consent_dependency.processing_purpose
                WHEN 'audio-research' THEN NOT consent.audio_processing
                WHEN 'visual-research' THEN NOT consent.video_processing ELSE TRUE END)
        )
      ), transition AS (
        SELECT CASE $4
          WHEN 'dataset-export' THEN $5 = 'managed-dataset-export'
            AND bool_and(artifact_kind = 'dataset')
          WHEN 'feature-extraction' THEN $5 = 'feature-cache'
            AND bool_and(artifact_kind = 'dataset')
          WHEN 'training' THEN $5 = 'checkpoint'
            AND bool_and(artifact_kind IN ('dataset', 'feature-cache'))
          WHEN 'calibration' THEN $5 = 'calibration'
            AND bool_or(artifact_kind = 'dataset') AND bool_or(artifact_kind = 'checkpoint')
            AND bool_and(artifact_kind IN ('dataset', 'checkpoint'))
          WHEN 'evaluation' THEN $5 = 'evaluation-report'
            AND bool_or(artifact_kind = 'dataset')
            AND bool_or(artifact_kind IN ('checkpoint', 'calibration'))
            AND bool_and(artifact_kind IN ('dataset', 'checkpoint', 'calibration'))
          WHEN 'shadow-evaluation' THEN $5 = 'evaluation-report'
            AND bool_or(artifact_kind = 'dataset')
            AND bool_or(artifact_kind IN ('checkpoint', 'calibration'))
            AND bool_and(artifact_kind IN ('dataset', 'checkpoint', 'calibration'))
          ELSE FALSE END AS valid FROM eligible
      ), inserted AS (
        INSERT INTO research_job_requests (
          id, tenant_id, job_type, output_kind, output_id, output_version,
          code_revision, configuration_sha256, runner_image_digest,
          intended_use, exclusions, release_posture, learner_feedback_eligible,
          requested_by_actor_id, expires_at
        )
        SELECT $3, $1, $4, $5, $6, $7, $8, $9, $10, $11, $12,
          'research-only', FALSE, $2, $13
        WHERE EXISTS (SELECT 1 FROM authorized)
          AND (SELECT COUNT(*) FROM eligible) = $15
          AND (SELECT COUNT(*) FROM requested) = $15
          AND (SELECT valid FROM transition)
          AND NOT EXISTS (
            SELECT 1 FROM ml_artifacts WHERE id = $6
          )
        ON CONFLICT DO NOTHING RETURNING *
      ), execution_gate AS (
        INSERT INTO research_job_execution_gates (job_id, tenant_id)
        SELECT id, tenant_id FROM inserted
        RETURNING job_id
      ), inserted_input AS (
        INSERT INTO research_job_inputs (
          job_id, tenant_id, artifact_id, binding_id, artifact_kind,
          artifact_sha256, provider_id, object_reference_sha256,
          provider_object_version
        )
        SELECT $3, $1, eligible.artifact_id, eligible.binding_id,
          eligible.artifact_kind, eligible.artifact_sha256, eligible.provider_id,
          eligible.object_reference_sha256, eligible.provider_object_version
        FROM eligible WHERE EXISTS (SELECT 1 FROM execution_gate)
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $16, $1, $2, 'research-job.requested', 'research_job', id,
          jsonb_build_object('job_type', job_type, 'input_count', $15::INTEGER)
        FROM inserted RETURNING id
      )
      SELECT inserted.*, NULL::TEXT AS approved_by_actor_id,
        NULL::TIMESTAMPTZ AS approved_at, NULL::TEXT AS envelope_sha256,
        jsonb_agg(jsonb_build_object(
          'artifactId', inserted_input.artifact_id,
          'artifactKind', inserted_input.artifact_kind,
          'artifactSha256', inserted_input.artifact_sha256,
          'bindingId', inserted_input.binding_id,
          'providerId', inserted_input.provider_id,
          'objectReferenceSha256', inserted_input.object_reference_sha256,
          'providerObjectVersion', inserted_input.provider_object_version
        ) ORDER BY inserted_input.artifact_id, inserted_input.binding_id) AS inputs,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM inserted INNER JOIN inserted_input ON TRUE
      GROUP BY inserted.id, inserted.tenant_id, inserted.job_type,
        inserted.output_kind, inserted.output_id, inserted.output_version,
        inserted.code_revision, inserted.configuration_sha256,
        inserted.runner_image_digest, inserted.intended_use, inserted.exclusions,
        inserted.release_posture, inserted.learner_feedback_eligible,
        inserted.requested_by_actor_id, inserted.requested_at, inserted.expires_at
      `,
      [actor.tenantId, actor.actorId, input.jobId, input.jobType, input.outputKind,
        input.outputId, input.outputVersion, input.codeRevision,
        input.configurationSha256, input.runnerImageDigest, input.intendedUse,
        exclusions, input.expiresAt, requested, input.inputs.length, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Research jobs require legal transitions, current consent, and consistent managed inputs.");
    }
    return mapEnvelope(row);
  }

  async approve(actor: ActorContext, jobId: string): Promise<ResearchJobAuthorizationEnvelope> {
    validateActor(actor);
    if (!opaque.test(jobId)) throw new PlatformDataError("invalid-identifier", "Job identifiers must be opaque tokens.");
    const draft = await this.#load(actor, jobId);
    if (draft.approvedByActorId) throw new PlatformDataError("conflict", "The research job is already approved.");
    if (draft.requestedByActorId === actor.actorId) {
      throw new PlatformDataError("access-denied", "Research job approval requires a distinct owner or reviewer.");
    }
    const hash = envelopeHash(draft, actor.actorId);
    const auditId = randomUUID();
    const result = await this.#database.query<Record<string, unknown> & { approved_at: string | Date }>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), target AS (
        SELECT * FROM research_job_requests
        WHERE id = $3 AND tenant_id = $1 AND requested_by_actor_id <> $2
          AND expires_at > CURRENT_TIMESTAMP AND EXISTS (SELECT 1 FROM authorized)
          AND NOT EXISTS (
            SELECT 1 FROM ml_artifacts WHERE id = research_job_requests.output_id
          )
          AND NOT EXISTS (
            SELECT 1 FROM research_job_cancellations
            WHERE job_id = $3 AND tenant_id = $1
          )
      ), ${freshInputCtes}, approved AS (
        INSERT INTO research_job_approvals (
          job_id, tenant_id, envelope_sha256, approved_by_actor_id
        )
        SELECT target.id, $1, $4, $2 FROM target
        WHERE (SELECT COUNT(*) FROM current_input) =
          (SELECT COUNT(*) FROM research_job_inputs WHERE job_id = $3 AND tenant_id = $1)
        ON CONFLICT DO NOTHING RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        ) SELECT $5, $1, $2, 'research-job.approved', 'research_job', job_id,
          jsonb_build_object('envelope_sha256', envelope_sha256)
        FROM approved RETURNING id
      )
      SELECT approved.approved_at, (SELECT id FROM audit LIMIT 1) AS audit_id FROM approved
      `,
      [actor.tenantId, actor.actorId, jobId, hash, auditId],
    );
    const row = result.rows[0];
    if (!row) throw new PlatformDataError("access-denied", "Research job approval requires fresh eligible inputs and distinct review.");
    return {
      ...draft,
      approvedByActorId: actor.actorId,
      approvedAt: timestamp(row.approved_at),
      envelopeSha256: hash,
      approvalPosture: "database-attested",
    };
  }

  async recordDispatch(
    signed: SignedResearchJobDispatch,
  ): Promise<ResearchJobDispatchReceipt> {
    this.#validateSignedDispatch(signed);
    const dispatch = signed.dispatch;
    const context = await this.#loadDispatchContext(signed);
    const envelope = mapEnvelope(context);
    if (!envelope.approvedByActorId || !envelope.envelopeSha256
      || envelopeHash(envelope, envelope.approvedByActorId) !== envelope.envelopeSha256
      || envelope.envelopeSha256 !== dispatch.envelopeSha256) {
      throw new PlatformDataError("invalid-artifact", "The dispatch envelope is invalid.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobDispatchPayload(unsigned);
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The dispatch signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The dispatch signing key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The dispatch signature is invalid.");
    }
    const payloadSha256 = createHash("sha256").update(payload).digest("hex");
    const signatureSha256 = createHash("sha256").update(signatureBytes).digest("hex");
    const auditId = randomUUID();
    let result;
    try {
      result = await this.#database.query<DispatchRow>(
        `
        WITH trusted_runner AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $9 AND NOT gate.revoked
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_scheduler AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_runner)
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_key AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2
            AND gate.signing_key_id = $5 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_scheduler)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), authorized AS (
          SELECT 1 FROM research_workload_signing_keys AS key
          INNER JOIN research_workload_identities AS scheduler
            ON scheduler.tenant_id = key.tenant_id
           AND scheduler.workload_id = key.workload_id
          INNER JOIN trusted_key ON trusted_key.tenant_id = key.tenant_id
            AND trusted_key.workload_id = key.workload_id
            AND trusted_key.signing_key_id = key.signing_key_id
          WHERE key.public_key_sha256 = $7 AND key.algorithm = 'Ed25519'
            AND scheduler.purpose = 'research-job-scheduler'
            AND key.valid_from <= $6::TIMESTAMPTZ AND key.valid_until > $6::TIMESTAMPTZ
            AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
            AND EXISTS (
              SELECT 1 FROM research_workload_identities AS runner
              INNER JOIN trusted_runner ON trusted_runner.tenant_id = runner.tenant_id
                AND trusted_runner.workload_id = runner.workload_id
              WHERE runner.tenant_id = $1 AND runner.workload_id = $9
                AND runner.purpose = 'research-job-runner'
            )
        ), inserted AS (
          INSERT INTO research_job_dispatches (
            dispatch_id, job_id, tenant_id, envelope_sha256,
            dispatch_revision, assigned_workload_id, expires_at,
            dispatched_by_workload_id, signing_key_id, signature_algorithm,
            public_key_sha256, attestation_issued_at,
            attestation_payload_sha256, signature_sha256
          )
          SELECT $8, approval.job_id, $1, $4, $10, $9, $11,
            $2, $5, 'Ed25519', $7, $6, $12, $13
          FROM research_job_approvals AS approval
          WHERE approval.job_id = $3 AND approval.tenant_id = $1
            AND approval.envelope_sha256 = $4
            AND approval.approved_at <= $6::TIMESTAMPTZ
            AND $11::TIMESTAMPTZ > CURRENT_TIMESTAMP
            AND EXISTS (SELECT 1 FROM authorized)
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, workload_id, action,
            resource_type, resource_id, metadata
          ) SELECT $14, $1, NULL, $2, 'research-job.dispatched',
            'research_job', job_id,
            jsonb_build_object('dispatch_id', dispatch_id,
              'dispatch_revision', dispatch_revision,
              'assigned_workload_id', assigned_workload_id,
              'expires_at', expires_at)
          FROM inserted RETURNING id
        ) SELECT inserted.* FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
        `,
        [signed.tenantId, signed.schedulerWorkloadId, dispatch.jobId,
          dispatch.envelopeSha256, signed.signingKeyId, signed.issuedAt,
          context.public_key_sha256, dispatch.dispatchId,
          dispatch.assignedWorkloadId, dispatch.dispatchRevision,
          dispatch.expiresAt, payloadSha256, signatureSha256, auditId],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError("conflict", "The dispatch ID or revision already exists.");
      }
      if (postgresErrorCode(error) === "P0001") {
        throw new PlatformDataError("access-denied", "The dispatch revision is stale or unavailable.");
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Dispatch requires an active scheduler, runner, and approved job.");
    }
    return mapDispatch(row);
  }

  async recordLaunchAttestation(
    signed: SignedResearchJobLaunchAttestation,
  ): Promise<ResearchJobLaunchReceipt> {
    this.#validateSignedLaunchAttestation(signed);
    const launch = signed.launch;
    const context = await this.#loadLaunchContext(signed);
    const envelope = mapEnvelope(context);
    if (!envelope.approvedByActorId || !envelope.envelopeSha256
      || envelopeHash(envelope, envelope.approvedByActorId) !== envelope.envelopeSha256
      || envelope.envelopeSha256 !== launch.envelopeSha256
      || new Date(signed.issuedAt).getTime()
        < new Date(context.dispatch_recorded_at).getTime()
      || new Date(signed.issuedAt).getTime()
        >= new Date(context.dispatch_expires_at).getTime()) {
      throw new PlatformDataError("invalid-artifact", "The launch attestation context is invalid.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobLaunchAttestationPayload(unsigned);
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The launch signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The launch signing key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The launch signature is invalid.");
    }
    const payloadSha256 = createHash("sha256").update(payload).digest("hex");
    const signatureSha256 = createHash("sha256").update(signatureBytes).digest("hex");
    const auditId = randomUUID();
    let result;
    try {
      result = await this.#database.query<LaunchRow>(
        `
        WITH trusted_runner AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $9 AND NOT gate.revoked
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_scheduler AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $14 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_runner)
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_scheduler_key AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $14
            AND gate.signing_key_id = $15 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_scheduler)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), trusted_provider AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_scheduler_key)
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_provider_key AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2
            AND gate.signing_key_id = $6 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_provider)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), locked_gate AS (
          UPDATE research_job_execution_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.job_id = $3 AND gate.tenant_id = $1
            AND gate.active_dispatch_id = $7 AND gate.dispatch_revision = $8
            AND gate.active_dispatch_workload_id = $9
            AND gate.active_launch_id IS NULL
            AND NOT gate.claimed AND NOT gate.cancellation_requested
            AND gate.terminal_status IS NULL
            AND EXISTS (SELECT 1 FROM trusted_provider_key)
          RETURNING gate.job_id
        ), authorized AS (
          SELECT dispatch.dispatch_id FROM research_job_dispatches AS dispatch
          INNER JOIN research_job_requests AS request
            ON request.id = dispatch.job_id AND request.tenant_id = dispatch.tenant_id
          INNER JOIN research_job_approvals AS approval
            ON approval.job_id = dispatch.job_id AND approval.tenant_id = dispatch.tenant_id
           AND approval.envelope_sha256 = dispatch.envelope_sha256
          INNER JOIN research_workload_identities AS provider
            ON provider.tenant_id = dispatch.tenant_id AND provider.workload_id = $2
           AND provider.purpose = 'research-job-provider'
          INNER JOIN research_workload_signing_keys AS provider_key
            ON provider_key.tenant_id = provider.tenant_id
           AND provider_key.workload_id = provider.workload_id
           AND provider_key.signing_key_id = $6
          INNER JOIN research_workload_identities AS runner
            ON runner.tenant_id = dispatch.tenant_id
           AND runner.workload_id = dispatch.assigned_workload_id
           AND runner.purpose = 'research-job-runner'
          INNER JOIN research_workload_identities AS scheduler
            ON scheduler.tenant_id = dispatch.tenant_id
           AND scheduler.workload_id = dispatch.dispatched_by_workload_id
           AND scheduler.purpose = 'research-job-scheduler'
          INNER JOIN research_workload_signing_keys AS scheduler_key
            ON scheduler_key.tenant_id = scheduler.tenant_id
           AND scheduler_key.workload_id = scheduler.workload_id
           AND scheduler_key.signing_key_id = dispatch.signing_key_id
           AND scheduler_key.public_key_sha256 = dispatch.public_key_sha256
          WHERE dispatch.dispatch_id = $7 AND dispatch.job_id = $3
            AND dispatch.tenant_id = $1 AND dispatch.dispatch_revision = $8
            AND dispatch.assigned_workload_id = $9
            AND dispatch.envelope_sha256 = $4
            AND request.runner_image_digest = $10
            AND dispatch.recorded_at <= $5::TIMESTAMPTZ
            AND dispatch.expires_at > $5::TIMESTAMPTZ
            AND dispatch.expires_at > CURRENT_TIMESTAMP
            AND provider_key.public_key_sha256 = $16
            AND provider_key.algorithm = 'Ed25519'
            AND provider_key.valid_from <= $5::TIMESTAMPTZ
            AND provider_key.valid_until > $5::TIMESTAMPTZ
            AND provider_key.valid_from <= CURRENT_TIMESTAMP
            AND provider_key.valid_until > CURRENT_TIMESTAMP
            AND scheduler_key.valid_from <= CURRENT_TIMESTAMP
            AND scheduler_key.valid_until > CURRENT_TIMESTAMP
            AND EXISTS (SELECT 1 FROM locked_gate)
        ), inserted AS (
          INSERT INTO research_job_launch_attestations (
            launch_id, job_id, tenant_id, envelope_sha256,
            dispatch_id, dispatch_revision, assigned_workload_id,
            runner_image_digest, process_reference_sha256,
            execution_identity_sha256, network_policy_sha256,
            attested_by_provider_workload_id, signing_key_id,
            signature_algorithm, public_key_sha256, attestation_issued_at,
            attestation_payload_sha256, signature_sha256
          )
          SELECT $17, $3, $1, $4, $7, $8, $9, $10, $11, $12, $13,
            $2, $6, 'Ed25519', $16, $5, $18, $19
          WHERE EXISTS (SELECT 1 FROM authorized)
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, workload_id, action,
            resource_type, resource_id, metadata
          ) SELECT $20, $1, NULL, $2, 'research-job.launch-attested',
            'research_job', job_id,
            jsonb_build_object('launch_id', launch_id,
              'dispatch_id', dispatch_id,
              'dispatch_revision', dispatch_revision,
              'assigned_workload_id', assigned_workload_id,
              'runner_image_digest', runner_image_digest,
              'process_reference_sha256', process_reference_sha256)
          FROM inserted RETURNING id
        ) SELECT inserted.* FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
        `,
        [signed.tenantId, signed.providerWorkloadId, launch.jobId,
          launch.envelopeSha256, signed.issuedAt, signed.signingKeyId,
          launch.dispatchId, launch.dispatchRevision,
          launch.assignedWorkloadId, launch.runnerImageDigest,
          launch.processReferenceSha256, launch.executionIdentitySha256,
          launch.networkPolicySha256, context.scheduler_workload_id,
          context.scheduler_signing_key_id, context.public_key_sha256,
          launch.launchId, payloadSha256, signatureSha256, auditId],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError("conflict", "This dispatch already has launch evidence.");
      }
      if (postgresErrorCode(error) === "P0001") {
        throw new PlatformDataError("access-denied", "The launch transition is stale or unavailable.");
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Launch evidence requires current provider, scheduler, runner, and dispatch trust.");
    }
    return mapLaunch(row);
  }

  async claimExecution(signed: SignedResearchJobExecutionClaim): Promise<ResearchJobExecutionClaim> {
    this.#validateSignedClaim(signed);
    const context = await this.#loadSignedClaim(signed);
    const envelope = mapEnvelope(context);
    if (!envelope.approvedByActorId || !envelope.envelopeSha256
      || envelopeHash(envelope, envelope.approvedByActorId) !== envelope.envelopeSha256
      || envelope.envelopeSha256 !== signed.envelopeSha256) {
      throw new PlatformDataError("invalid-artifact", "The research job envelope hash is invalid or unapproved.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobExecutionClaimPayload(unsigned);
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The workload execution signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The workload signing key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload, "utf8"), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The workload execution signature is invalid.");
    }
    const payloadSha256 = createHash("sha256").update(payload).digest("hex");
    const signatureSha256 = createHash("sha256").update(signatureBytes).digest("hex");
    const auditId = randomUUID();
    let result;
    try {
      result = await this.#database.query<Record<string, unknown> & {
        claim_id: string;
        launch_id: string;
        claimed_at: string | Date;
        lease_duration_seconds: number;
        lease_started_at: string | Date;
        lease_expires_at: string | Date;
      }>(`
      WITH trusted_identity AS (
        UPDATE research_workload_identity_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        WHERE gate.tenant_id = $1 AND gate.workload_id = $2
          AND NOT gate.revoked
        RETURNING gate.tenant_id, gate.workload_id
      ), trusted_key AS (
        UPDATE research_workload_signing_key_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        WHERE gate.tenant_id = $1 AND gate.workload_id = $2
          AND gate.signing_key_id = $6 AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_identity)
        RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
      ), authorized AS (
        SELECT key.public_key_sha256
        FROM research_workload_identities AS identity
        INNER JOIN research_workload_signing_keys AS key
          ON key.tenant_id = identity.tenant_id
         AND key.workload_id = identity.workload_id
        INNER JOIN trusted_key
          ON trusted_key.tenant_id = key.tenant_id
         AND trusted_key.workload_id = key.workload_id
         AND trusted_key.signing_key_id = key.signing_key_id
        WHERE identity.tenant_id = $1 AND identity.workload_id = $2
          AND key.signing_key_id = $6 AND key.algorithm = 'Ed25519'
          AND key.public_key_sha256 = $10
          AND key.valid_from <= $7::TIMESTAMPTZ
          AND key.valid_until > $7::TIMESTAMPTZ
          AND key.valid_from <= CURRENT_TIMESTAMP
          AND key.valid_until > CURRENT_TIMESTAMP
      ), active_dispatch AS (
        SELECT dispatch.* FROM research_job_dispatches AS dispatch
        INNER JOIN research_job_execution_gates AS gate
          ON gate.job_id = dispatch.job_id AND gate.tenant_id = dispatch.tenant_id
         AND gate.active_dispatch_id = dispatch.dispatch_id
         AND gate.dispatch_revision = dispatch.dispatch_revision
        WHERE dispatch.dispatch_id = $12 AND dispatch.job_id = $3
          AND dispatch.tenant_id = $1 AND dispatch.dispatch_revision = $13
          AND dispatch.assigned_workload_id = $2
          AND dispatch.envelope_sha256 = $4
          AND dispatch.expires_at > CURRENT_TIMESTAMP
          AND dispatch.expires_at > $7::TIMESTAMPTZ
          AND dispatch.recorded_at <= $7::TIMESTAMPTZ
      ), trusted_scheduler_identity AS (
        UPDATE research_workload_identity_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        FROM active_dispatch AS dispatch
        WHERE gate.tenant_id = dispatch.tenant_id
          AND gate.workload_id = dispatch.dispatched_by_workload_id
          AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_key)
        RETURNING gate.tenant_id, gate.workload_id
      ), trusted_scheduler_key AS (
        UPDATE research_workload_signing_key_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        FROM active_dispatch AS dispatch
        WHERE gate.tenant_id = dispatch.tenant_id
          AND gate.workload_id = dispatch.dispatched_by_workload_id
          AND gate.signing_key_id = dispatch.signing_key_id
          AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_scheduler_identity)
        RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
      ), scheduler_authorized AS (
        SELECT 1 FROM active_dispatch AS dispatch
        INNER JOIN research_workload_identities AS scheduler
          ON scheduler.tenant_id = dispatch.tenant_id
         AND scheduler.workload_id = dispatch.dispatched_by_workload_id
         AND scheduler.purpose = 'research-job-scheduler'
        INNER JOIN research_workload_signing_keys AS key
          ON key.tenant_id = dispatch.tenant_id
         AND key.workload_id = dispatch.dispatched_by_workload_id
         AND key.signing_key_id = dispatch.signing_key_id
         AND key.public_key_sha256 = dispatch.public_key_sha256
        INNER JOIN trusted_scheduler_key
          ON trusted_scheduler_key.tenant_id = key.tenant_id
         AND trusted_scheduler_key.workload_id = key.workload_id
         AND trusted_scheduler_key.signing_key_id = key.signing_key_id
        WHERE key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
      ), active_launch AS (
        SELECT launch.* FROM research_job_launch_attestations AS launch
        INNER JOIN active_dispatch AS dispatch
          ON dispatch.dispatch_id = launch.dispatch_id
         AND dispatch.job_id = launch.job_id AND dispatch.tenant_id = launch.tenant_id
         AND dispatch.dispatch_revision = launch.dispatch_revision
         AND dispatch.assigned_workload_id = launch.assigned_workload_id
         AND dispatch.envelope_sha256 = launch.envelope_sha256
        INNER JOIN research_job_execution_gates AS gate
          ON gate.job_id = launch.job_id AND gate.tenant_id = launch.tenant_id
         AND gate.active_launch_id = launch.launch_id
        WHERE launch.recorded_at <= $7::TIMESTAMPTZ
      ), trusted_provider_identity AS (
        UPDATE research_workload_identity_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        FROM active_launch AS launch
        WHERE gate.tenant_id = launch.tenant_id
          AND gate.workload_id = launch.attested_by_provider_workload_id
          AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM scheduler_authorized)
        RETURNING gate.tenant_id, gate.workload_id
      ), trusted_provider_key AS (
        UPDATE research_workload_signing_key_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        FROM active_launch AS launch
        WHERE gate.tenant_id = launch.tenant_id
          AND gate.workload_id = launch.attested_by_provider_workload_id
          AND gate.signing_key_id = launch.signing_key_id
          AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_provider_identity)
        RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
      ), provider_authorized AS (
        SELECT 1 FROM active_launch AS launch
        INNER JOIN research_workload_identities AS provider
          ON provider.tenant_id = launch.tenant_id
         AND provider.workload_id = launch.attested_by_provider_workload_id
         AND provider.purpose = 'research-job-provider'
        INNER JOIN research_workload_signing_keys AS key
          ON key.tenant_id = launch.tenant_id
         AND key.workload_id = launch.attested_by_provider_workload_id
         AND key.signing_key_id = launch.signing_key_id
         AND key.public_key_sha256 = launch.public_key_sha256
        INNER JOIN trusted_provider_key
          ON trusted_provider_key.tenant_id = key.tenant_id
         AND trusted_provider_key.workload_id = key.workload_id
         AND trusted_provider_key.signing_key_id = key.signing_key_id
        WHERE key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
      ), target AS (
        SELECT request.id FROM research_job_requests AS request
        INNER JOIN research_job_approvals AS approval
          ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
        WHERE request.id = $3 AND request.tenant_id = $1
          AND request.expires_at > CURRENT_TIMESTAMP
          AND approval.envelope_sha256 = $4
          AND EXISTS (SELECT 1 FROM authorized)
          AND EXISTS (SELECT 1 FROM scheduler_authorized)
          AND EXISTS (SELECT 1 FROM provider_authorized)
          AND NOT EXISTS (
            SELECT 1 FROM ml_artifacts WHERE id = request.output_id
          )
          AND NOT EXISTS (
            SELECT 1 FROM research_job_cancellations AS cancellation
            WHERE cancellation.job_id = request.id
              AND cancellation.tenant_id = request.tenant_id
          )
        FOR UPDATE OF request
      ), ${freshInputCtes}, gated AS (
        UPDATE research_job_execution_gates AS gate
        SET claimed = TRUE,
          lease_duration_seconds = $14::INTEGER,
          lease_started_at = CURRENT_TIMESTAMP,
          lease_expires_at = CURRENT_TIMESTAMP
            + ($14::INTEGER * INTERVAL '1 second'),
          updated_at = CURRENT_TIMESTAMP
        WHERE gate.job_id = $3 AND gate.tenant_id = $1
          AND NOT gate.claimed AND NOT gate.cancellation_requested
          AND gate.active_dispatch_id = $12
          AND gate.dispatch_revision = $13
          AND gate.active_dispatch_workload_id = $2
          AND gate.active_dispatch_expires_at > CURRENT_TIMESTAMP
          AND gate.active_launch_id = (SELECT launch_id FROM active_launch)
          AND EXISTS (SELECT 1 FROM target)
          AND (SELECT COUNT(*) FROM current_input) =
            (SELECT COUNT(*) FROM research_job_inputs WHERE job_id = $3 AND tenant_id = $1)
        RETURNING gate.job_id, gate.lease_duration_seconds,
          gate.lease_started_at, gate.lease_expires_at, gate.active_launch_id
      ), claimed AS (
        INSERT INTO research_job_execution_claims (
          claim_id, job_id, tenant_id, envelope_sha256,
          dispatch_id, dispatch_revision, launch_id,
          claimed_by_workload_id, signing_key_id, signature_algorithm,
          public_key_sha256, attestation_issued_at,
          attestation_payload_sha256, signature_sha256
        )
        SELECT $5, target.id, $1, $4, $12, $13, gated.active_launch_id,
          $2, $6, 'Ed25519', $10, $7, $8, $9
        FROM target
        INNER JOIN gated ON gated.job_id = target.id
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, workload_id, action,
          resource_type, resource_id, metadata
        ) SELECT $11, $1, NULL, $2, 'research-job.execution-claimed',
          'research_job', claimed.job_id,
          jsonb_build_object(
            'claim_id', claimed.claim_id,
            'dispatch_id', claimed.dispatch_id,
            'dispatch_revision', claimed.dispatch_revision,
            'launch_id', claimed.launch_id,
            'envelope_sha256', claimed.envelope_sha256,
            'signing_key_id', claimed.signing_key_id,
            'public_key_sha256', claimed.public_key_sha256,
            'attestation_payload_sha256', claimed.attestation_payload_sha256,
            'signature_sha256', claimed.signature_sha256
          )
        FROM claimed
        RETURNING id
      ) SELECT claimed.claim_id, claimed.claimed_at, claimed.launch_id,
        gated.lease_duration_seconds, gated.lease_started_at,
        gated.lease_expires_at,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM claimed INNER JOIN gated ON gated.job_id = claimed.job_id
      `,
      [signed.tenantId, signed.workloadId, signed.jobId, envelope.envelopeSha256,
        signed.claimId, signed.signingKeyId, signed.issuedAt, payloadSha256,
        signatureSha256, context.public_key_sha256, auditId,
        signed.dispatchId, signed.dispatchRevision,
        this.#executionLeaseSeconds]);
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError("conflict", "The signed execution claim has already been used.");
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) throw new PlatformDataError("access-denied", "Research job execution requires fresh approved unclaimed inputs.");
    return {
      claimId: row.claim_id,
      jobId: signed.jobId,
      envelope,
      envelopeSha256: envelope.envelopeSha256,
      claimedByWorkloadId: signed.workloadId,
      claimedAt: timestamp(row.claimed_at),
      dispatchId: signed.dispatchId,
      dispatchRevision: signed.dispatchRevision,
      launchId: row.launch_id,
      leaseDurationSeconds: Number(row.lease_duration_seconds),
      leaseStartedAt: timestamp(row.lease_started_at),
      leaseExpiresAt: timestamp(row.lease_expires_at),
      signatureVerification: {
        signingKeyId: signed.signingKeyId,
        algorithm: "Ed25519",
        publicKeySha256: context.public_key_sha256,
        issuedAt: signed.issuedAt,
        payloadSha256,
        signatureSha256,
      },
      cancellationObservedAtClaim: false,
      cancellationPollingRequired: true,
      evidencePosture: "local-foundation",
      productionGateEligible: false,
    };
  }

  async authorizeExecution(signed: SignedResearchJobExecutionClaim): Promise<ResearchJobAuthorizationEnvelope> {
    return (await this.claimExecution(signed)).envelope;
  }

  async recordTerminal(
    signed: SignedResearchJobTerminalAttestation,
  ): Promise<ResearchJobTerminalReceipt> {
    this.#validateSignedTerminal(signed);
    const input = signed.terminal;
    this.#validateTerminalInput(input);
    const context = await this.#loadWorkloadJobContext(
      signed,
      input.jobId,
      input.claimId,
      "terminal",
    );
    const envelope = mapEnvelope(context);
    if (!envelope.approvedByActorId || !envelope.envelopeSha256
      || envelopeHash(envelope, envelope.approvedByActorId) !== envelope.envelopeSha256) {
      throw new PlatformDataError("invalid-artifact", "The research job envelope hash is invalid or unapproved.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobTerminalAttestationPayload(
      unsigned,
      envelope.envelopeSha256,
    );
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The workload terminal signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The workload signing key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The workload terminal signature is invalid.");
    }
    const verification = {
      tenantId: signed.tenantId,
      workloadId: signed.workloadId,
      signingKeyId: signed.signingKeyId,
      publicKeySha256: context.public_key_sha256,
      issuedAt: signed.issuedAt,
      payloadSha256: createHash("sha256").update(payload).digest("hex"),
      signatureSha256: createHash("sha256").update(signatureBytes).digest("hex"),
    };
    const receiptId = randomUUID();
    const auditId = randomUUID();
    const terminalPayloadSha256 = createHash("sha256").update(
      canonicalResearchJobTerminalPayload(input, envelope.envelopeSha256),
    ).digest("hex");
    let row: TerminalRow | undefined;
    try {
      row = input.status === "succeeded"
        ? await this.#recordSuccess(
          verification, input, envelope.envelopeSha256, receiptId,
          terminalPayloadSha256, auditId,
        )
        : await this.#recordNonSuccess(
          verification, input, envelope.envelopeSha256, receiptId,
          terminalPayloadSha256, auditId,
        );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError(
          "conflict",
          "Research output identity or managed-object provenance conflicts with existing evidence.",
        );
      }
      if (["23503", "23514"].includes(postgresErrorCode(error) ?? "")) {
        throw new PlatformDataError(
          "invalid-artifact",
          "Research terminal evidence violates its approved output identity or lineage.",
        );
      }
      if (postgresErrorCode(error) === "P0001") {
        throw new PlatformDataError(
          "access-denied",
          "The terminal transition lacks required cancellation acknowledgement or gate state.",
        );
      }
      throw error;
    }
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "Terminal evidence requires the exact active claim, legal cancellation state, and fresh lineage.",
      );
    }
    return mapTerminalReceipt(row);
  }

  async getTerminalReceipt(
    actor: ActorContext,
    jobId: string,
  ): Promise<ResearchJobTerminalReceipt> {
    validateActor(actor);
    if (!opaque.test(jobId)) {
      throw new PlatformDataError("invalid-identifier", "Job identifiers must be opaque tokens.");
    }
    const result = await this.#database.query<TerminalRow>(
      `
      SELECT receipt.* FROM research_job_terminal_receipts AS receipt
      WHERE receipt.job_id = $3 AND receipt.tenant_id = $1
        AND EXISTS (SELECT 1 FROM tenant_memberships WHERE tenant_id = $1
          AND actor_id = $2 AND status = 'active' AND role IN ('owner', 'reviewer'))
      `,
      [actor.tenantId, actor.actorId, jobId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The terminal receipt is unavailable to this actor.");
    }
    return mapTerminalReceipt(row);
  }

  async recordExternalTerminationAttestation(
    signed: SignedResearchJobExternalTerminationAttestation,
  ): Promise<ResearchJobExternalTerminationReceipt> {
    this.#validateSignedExternalTermination(signed);
    const termination = signed.termination;
    const context = await this.#loadExternalTerminationContext(signed);
    const envelope = mapEnvelope(context);
    if (!envelope.approvedByActorId || !envelope.envelopeSha256
      || envelopeHash(envelope, envelope.approvedByActorId) !== envelope.envelopeSha256
      || envelope.envelopeSha256 !== termination.envelopeSha256
      || Number(context.cancellation_revision) !== termination.cancellationRevision
      || Number(context.cancellation_sequence_id) !== termination.cancellationSequenceId
      || context.cancellation_source !== termination.cancellationSource
      || context.cancellation_reason !== termination.cancellationReason
      || new Date(signed.issuedAt).getTime()
        < new Date(context.cancellation_cancelled_at).getTime()
      || new Date(signed.issuedAt).getTime()
        < new Date(context.cancellation_latest_at).getTime()
      || new Date(signed.issuedAt).getTime()
        < new Date(context.launch_recorded_at).getTime()) {
      throw new PlatformDataError("invalid-artifact", "The external termination context is invalid.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobExternalTerminationPayload(unsigned);
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The external termination signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The external termination key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The external termination signature is invalid.");
    }
    const payloadSha256 = createHash("sha256").update(payload).digest("hex");
    const signatureSha256 = createHash("sha256").update(signatureBytes).digest("hex");
    const auditId = randomUUID();
    let result;
    try {
      result = await this.#database.query<ExternalTerminationRow>(
        `
        WITH trusted_provider AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_provider_key AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2
            AND gate.signing_key_id = $6 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_provider)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), locked_gate AS (
          UPDATE research_job_execution_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.job_id = $3 AND gate.tenant_id = $1
            AND gate.claimed AND gate.cancellation_requested
            AND gate.cancellation_revision = $14
            AND gate.terminal_status IS NULL
            AND NOT EXISTS (
              SELECT 1 FROM research_job_cancellations AS later
              WHERE later.job_id = gate.job_id AND later.tenant_id = gate.tenant_id
                AND later.cancelled_at > $7::TIMESTAMPTZ
            )
            AND EXISTS (SELECT 1 FROM trusted_provider_key)
          RETURNING gate.job_id
        ), authorized AS (
          SELECT 1 FROM research_workload_identities AS provider
          INNER JOIN research_workload_signing_keys AS key
            ON key.tenant_id = provider.tenant_id
           AND key.workload_id = provider.workload_id
          INNER JOIN trusted_provider_key
            ON trusted_provider_key.tenant_id = key.tenant_id
           AND trusted_provider_key.workload_id = key.workload_id
           AND trusted_provider_key.signing_key_id = key.signing_key_id
          WHERE provider.tenant_id = $1 AND provider.workload_id = $2
            AND provider.purpose = 'research-job-provider'
            AND key.signing_key_id = $6 AND key.public_key_sha256 = $8
            AND key.algorithm = 'Ed25519'
            AND key.valid_from <= $7::TIMESTAMPTZ
            AND key.valid_until > $7::TIMESTAMPTZ
            AND key.valid_from <= CURRENT_TIMESTAMP
            AND key.valid_until > CURRENT_TIMESTAMP
            AND EXISTS (SELECT 1 FROM locked_gate)
        ), effective AS (
          SELECT cancellation.* FROM research_job_cancellations AS cancellation
          WHERE cancellation.job_id = $3 AND cancellation.tenant_id = $1
            AND cancellation.cancelled_at <= $7::TIMESTAMPTZ
          ORDER BY CASE cancellation.source WHEN 'input-quarantined' THEN 3
            WHEN 'provider-drift' THEN 2 ELSE 1 END DESC,
            cancellation.cancelled_at DESC, cancellation.sequence_id DESC
          LIMIT 1
        ), bound_claim AS (
          SELECT claim.* FROM research_job_execution_claims AS claim
          INNER JOIN research_job_launch_attestations AS launch
            ON launch.launch_id = claim.launch_id
           AND launch.job_id = claim.job_id AND launch.tenant_id = claim.tenant_id
          WHERE claim.claim_id = $4 AND claim.job_id = $3 AND claim.tenant_id = $1
            AND claim.envelope_sha256 = $5
            AND claim.claimed_by_workload_id = $13
            AND claim.launch_id = $10 AND claim.dispatch_id = $11
            AND claim.dispatch_revision = $12
            AND launch.process_reference_sha256 = $18
            AND launch.recorded_at <= $7::TIMESTAMPTZ
            AND claim.claimed_at <= $7::TIMESTAMPTZ
            AND EXISTS (SELECT 1 FROM authorized)
        ), inserted AS (
          INSERT INTO research_job_external_termination_attestations (
            termination_attestation_id, job_id, tenant_id, claim_id,
            envelope_sha256, launch_id, dispatch_id, dispatch_revision,
            assigned_workload_id, cancellation_revision,
            cancellation_sequence_id, cancellation_source, cancellation_reason,
            outcome, process_reference_sha256, termination_evidence_sha256,
            attested_by_provider_workload_id, signing_key_id,
            signature_algorithm, public_key_sha256, attestation_issued_at,
            attestation_payload_sha256, signature_sha256
          )
          SELECT $9, claim.job_id, $1, claim.claim_id, $5, $10, $11, $12,
            $13, $14, effective.sequence_id, effective.source, effective.reason,
            'process-stopped', $18, $19, $2, $6, 'Ed25519', $8, $7, $20, $21
          FROM bound_claim AS claim CROSS JOIN effective
          WHERE effective.sequence_id = $15 AND effective.source = $16
            AND effective.reason = $17
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, workload_id, action,
            resource_type, resource_id, metadata
          ) SELECT $22, $1, NULL, $2, 'research-job.external-termination-attested',
            'research_job', job_id,
            jsonb_build_object(
              'termination_attestation_id', termination_attestation_id,
              'launch_id', launch_id,
              'claim_id', claim_id,
              'cancellation_revision', cancellation_revision,
              'cancellation_sequence_id', cancellation_sequence_id,
              'process_reference_sha256', process_reference_sha256,
              'termination_evidence_sha256', termination_evidence_sha256)
          FROM inserted RETURNING id
        ) SELECT inserted.* FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
        `,
        [signed.tenantId, signed.providerWorkloadId, termination.jobId,
          termination.claimId, termination.envelopeSha256, signed.signingKeyId,
          signed.issuedAt, context.public_key_sha256,
          termination.terminationAttestationId, termination.launchId,
          termination.dispatchId, termination.dispatchRevision,
          termination.assignedWorkloadId, termination.cancellationRevision,
          termination.cancellationSequenceId, termination.cancellationSource,
          termination.cancellationReason, termination.processReferenceSha256,
          termination.terminationEvidenceSha256, payloadSha256,
          signatureSha256, auditId],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError("conflict", "This cancellation revision already has external termination evidence.");
      }
      if (postgresErrorCode(error) === "P0001") {
        throw new PlatformDataError("access-denied", "The external termination transition is stale.");
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "External termination requires current provider trust and cancellation state.");
    }
    return mapExternalTermination(row);
  }

  async acknowledgeCancellation(
    signed: SignedResearchJobCancellationAcknowledgement,
  ): Promise<ResearchJobCancellationAcknowledgementReceipt> {
    this.#validateSignedCancellationAcknowledgement(signed);
    const context = await this.#loadCancellationContext(signed);
    const envelope = mapEnvelope(context);
    if (!envelope.approvedByActorId || !envelope.envelopeSha256
      || envelopeHash(envelope, envelope.approvedByActorId) !== envelope.envelopeSha256
      || Number(context.cancellation_revision)
        !== signed.acknowledgement.cancellationRevision
      || Number(context.cancellation_sequence_id)
        !== signed.acknowledgement.cancellationSequenceId
      || new Date(signed.issuedAt).getTime()
        < new Date(context.cancellation_cancelled_at).getTime()
      || new Date(signed.issuedAt).getTime()
        < new Date(context.cancellation_latest_at).getTime()
      || context.cancellation_source !== signed.acknowledgement.cancellationSource
      || context.cancellation_reason !== signed.acknowledgement.cancellationReason) {
      throw new PlatformDataError("invalid-artifact", "The cancellation acknowledgement context is invalid.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobCancellationAcknowledgementPayload(
      unsigned,
      envelope.envelopeSha256,
    );
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The cancellation signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The cancellation signing key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The cancellation acknowledgement signature is invalid.");
    }
    const payloadSha256 = createHash("sha256").update(payload).digest("hex");
    const signatureSha256 = createHash("sha256").update(signatureBytes).digest("hex");
    const acknowledgementId = randomUUID();
    const auditId = randomUUID();
    let result;
    try {
      result = await this.#database.query<CancellationAcknowledgementRow>(
        `
        WITH trusted_identity AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_key AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2
            AND gate.signing_key_id = $6 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_identity)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), locked_gate AS (
          UPDATE research_job_execution_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.job_id = $3 AND gate.tenant_id = $1
            AND gate.claimed AND gate.cancellation_requested
            AND gate.cancellation_revision = $10
            AND gate.terminal_status IS NULL
            AND NOT EXISTS (
              SELECT 1 FROM research_job_cancellations AS cancellation
              WHERE cancellation.job_id = gate.job_id
                AND cancellation.tenant_id = gate.tenant_id
                AND cancellation.cancelled_at > $7::TIMESTAMPTZ
            )
          RETURNING gate.job_id, gate.tenant_id, gate.cancellation_revision
        ), authorized AS (
          SELECT 1 FROM research_workload_signing_keys AS key
          INNER JOIN trusted_key ON trusted_key.tenant_id = key.tenant_id
            AND trusted_key.workload_id = key.workload_id
            AND trusted_key.signing_key_id = key.signing_key_id
          WHERE key.public_key_sha256 = $8 AND key.algorithm = 'Ed25519'
            AND key.valid_from <= $7::TIMESTAMPTZ AND key.valid_until > $7::TIMESTAMPTZ
            AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
            AND EXISTS (SELECT 1 FROM locked_gate)
        ), effective AS (
          SELECT cancellation.* FROM research_job_cancellations AS cancellation
          WHERE cancellation.job_id = $3 AND cancellation.tenant_id = $1
            AND cancellation.cancelled_at <= $7::TIMESTAMPTZ
          ORDER BY CASE cancellation.source WHEN 'input-quarantined' THEN 3
            WHEN 'provider-drift' THEN 2 ELSE 1 END DESC,
            cancellation.cancelled_at DESC, cancellation.sequence_id DESC
          LIMIT 1
        ), claim AS (
          SELECT claim.* FROM research_job_execution_claims AS claim
          LEFT JOIN research_job_launch_attestations AS launch
            ON launch.launch_id = claim.launch_id
           AND launch.job_id = claim.job_id AND launch.tenant_id = claim.tenant_id
          WHERE claim.job_id = $3 AND claim.tenant_id = $1 AND claim.claim_id = $4
            AND claim.envelope_sha256 = $5 AND claim.claimed_by_workload_id = $2
            AND (
              (claim.launch_id IS NULL AND $14::TEXT = 'not-started'
                AND $15::TEXT IS NULL)
              OR (launch.launch_id IS NOT NULL AND $14::TEXT = 'process-stopped'
                AND launch.process_reference_sha256 = $15::TEXT)
            )
            AND EXISTS (SELECT 1 FROM authorized)
        ), inserted AS (
          INSERT INTO research_job_cancellation_acknowledgements (
            acknowledgement_id, job_id, tenant_id, claim_id, envelope_sha256,
            cancellation_revision, cancellation_sequence_id,
            cancellation_source, cancellation_reason,
            termination_outcome, process_reference_sha256,
            termination_evidence_sha256, acknowledged_by_workload_id,
            signing_key_id, signature_algorithm, public_key_sha256,
            attestation_issued_at, attestation_payload_sha256, signature_sha256
          )
          SELECT $9, claim.job_id, $1, claim.claim_id, $5, $10,
            effective.sequence_id, effective.source, effective.reason,
            $14, $15, $16, $2, $6, 'Ed25519', $8, $7, $17, $18
          FROM claim CROSS JOIN effective
          WHERE effective.sequence_id = $11 AND effective.source = $12
            AND effective.reason = $13
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, workload_id, action,
            resource_type, resource_id, metadata
          ) SELECT $19, $1, NULL, $2, 'research-job.cancellation-acknowledged',
            'research_job', job_id,
            jsonb_build_object('acknowledgement_id', acknowledgement_id,
              'cancellation_sequence_id', cancellation_sequence_id,
              'termination_outcome', termination_outcome,
              'termination_evidence_sha256', termination_evidence_sha256)
          FROM inserted RETURNING id
        ) SELECT inserted.* FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
        `,
        [signed.tenantId, signed.workloadId, signed.acknowledgement.jobId,
          signed.acknowledgement.claimId, envelope.envelopeSha256,
          signed.signingKeyId, signed.issuedAt, context.public_key_sha256,
          acknowledgementId, signed.acknowledgement.cancellationRevision,
          signed.acknowledgement.cancellationSequenceId,
          signed.acknowledgement.cancellationSource,
          signed.acknowledgement.cancellationReason,
          signed.acknowledgement.terminationOutcome,
          signed.acknowledgement.processReferenceSha256 ?? null,
          signed.acknowledgement.terminationEvidenceSha256,
          payloadSha256, signatureSha256, auditId],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError("conflict", "This cancellation evidence is already acknowledged.");
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Cancellation acknowledgement requires current effective cancellation and workload trust.");
    }
    return mapCancellationAcknowledgement(row);
  }

  async recordHeartbeat(
    signed: SignedResearchJobHeartbeat,
  ): Promise<ResearchJobHeartbeatReceipt> {
    this.#validateSignedHeartbeat(signed);
    const heartbeat = signed.heartbeat;
    const context = await this.#loadWorkloadJobContext(
      signed,
      heartbeat.jobId,
      heartbeat.claimId,
      "heartbeat",
    );
    const envelope = mapEnvelope(context);
    if (!envelope.approvedByActorId || !envelope.envelopeSha256
      || envelopeHash(envelope, envelope.approvedByActorId) !== envelope.envelopeSha256) {
      throw new PlatformDataError("invalid-artifact", "The heartbeat envelope is invalid.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobHeartbeatPayload(unsigned, envelope.envelopeSha256);
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The heartbeat signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The heartbeat signing key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The heartbeat signature is invalid.");
    }
    const payloadSha256 = createHash("sha256").update(payload).digest("hex");
    const signatureSha256 = createHash("sha256").update(signatureBytes).digest("hex");
    const auditId = randomUUID();
    let result;
    try {
      result = await this.#database.query<HeartbeatRow>(
        `
        WITH trusted_identity AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_key AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2
            AND gate.signing_key_id = $6 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_identity)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), authorized AS (
          SELECT 1 FROM research_workload_signing_keys AS key
          INNER JOIN trusted_key ON trusted_key.tenant_id = key.tenant_id
            AND trusted_key.workload_id = key.workload_id
            AND trusted_key.signing_key_id = key.signing_key_id
          WHERE key.public_key_sha256 = $8 AND key.algorithm = 'Ed25519'
            AND key.valid_from <= $7::TIMESTAMPTZ AND key.valid_until > $7::TIMESTAMPTZ
            AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
        ), claim AS (
          SELECT claim.* FROM research_job_execution_claims AS claim
          WHERE claim.job_id = $3 AND claim.tenant_id = $1 AND claim.claim_id = $4
            AND claim.envelope_sha256 = $5 AND claim.claimed_by_workload_id = $2
            AND claim.claimed_at <= $7::TIMESTAMPTZ
            AND EXISTS (SELECT 1 FROM authorized)
        ), inserted AS (
          INSERT INTO research_job_heartbeats (
            heartbeat_id, job_id, tenant_id, claim_id, envelope_sha256,
            heartbeat_sequence, runner_state, cancellation_revision,
            process_reference_sha256, liveness_evidence_sha256,
            reported_by_workload_id, signing_key_id, signature_algorithm,
            public_key_sha256, attestation_issued_at,
            attestation_payload_sha256, signature_sha256
          )
          SELECT $9, claim.job_id, $1, claim.claim_id, $5,
            $10, $11, $12, $13, $14, $2, $6, 'Ed25519', $8, $7, $15, $16
          FROM claim
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, workload_id, action,
            resource_type, resource_id, metadata
          ) SELECT $17, $1, NULL, $2, 'research-job.heartbeat-recorded',
            'research_job', job_id,
            jsonb_build_object('heartbeat_id', heartbeat_id,
              'heartbeat_sequence', heartbeat_sequence,
              'runner_state', runner_state,
              'cancellation_revision', cancellation_revision,
              'liveness_evidence_sha256', liveness_evidence_sha256)
          FROM inserted RETURNING id
        ) SELECT inserted.* FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
        `,
        [signed.tenantId, signed.workloadId, heartbeat.jobId, heartbeat.claimId,
          envelope.envelopeSha256, signed.signingKeyId, signed.issuedAt,
          context.public_key_sha256, heartbeat.heartbeatId,
          heartbeat.heartbeatSequence, heartbeat.runnerState,
          heartbeat.cancellationRevision, heartbeat.processReferenceSha256,
          heartbeat.livenessEvidenceSha256, payloadSha256, signatureSha256,
          auditId],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError("conflict", "This heartbeat sequence or ID already exists.");
      }
      if (postgresErrorCode(error) === "P0001") {
        throw new PlatformDataError(
          "access-denied",
          "Heartbeat state is stale for the execution or cancellation gate.",
        );
      }
      if (["23503", "23514"].includes(postgresErrorCode(error) ?? "")) {
        throw new PlatformDataError("invalid-artifact", "Heartbeat evidence violates its claim.");
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Heartbeat evidence requires an active trusted claim.");
    }
    return mapHeartbeat(row);
  }

  async getLatestHeartbeat(
    actor: ActorContext,
    jobId: string,
  ): Promise<ResearchJobHeartbeatReceipt> {
    validateActor(actor);
    if (!opaque.test(jobId)) {
      throw new PlatformDataError("invalid-identifier", "Job identifiers must be opaque tokens.");
    }
    const result = await this.#database.query<HeartbeatRow>(
      `
      SELECT heartbeat.* FROM research_job_heartbeats AS heartbeat
      WHERE heartbeat.job_id = $3 AND heartbeat.tenant_id = $1
        AND EXISTS (SELECT 1 FROM tenant_memberships WHERE tenant_id = $1
          AND actor_id = $2 AND status = 'active' AND role IN ('owner', 'reviewer'))
      ORDER BY heartbeat.heartbeat_sequence DESC
      LIMIT 1
      `,
      [actor.tenantId, actor.actorId, jobId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The research job heartbeat is unavailable.");
    }
    return mapHeartbeat(row);
  }

  async inspectLiveness(
    actor: ActorContext,
    jobId: string,
  ): Promise<ResearchJobLivenessSnapshot> {
    validateActor(actor);
    if (!opaque.test(jobId)) {
      throw new PlatformDataError("invalid-identifier", "Job identifiers must be opaque tokens.");
    }
    const snapshotId = randomUUID();
    const auditId = randomUUID();
    const result = await this.#database.query<LivenessSnapshotRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), state AS (
        SELECT gate.job_id, gate.tenant_id, claim.claim_id,
          gate.lease_duration_seconds, gate.lease_started_at,
          gate.lease_expires_at,
          gate.lease_expires_at <= CURRENT_TIMESTAMP AS lease_expired,
          gate.last_heartbeat_id, gate.last_heartbeat_sequence,
          heartbeat.runner_state AS last_heartbeat_state,
          heartbeat.cancellation_revision AS last_heartbeat_cancellation_revision,
          gate.cancellation_requested, gate.cancellation_revision,
          gate.terminal_status
        FROM research_job_execution_gates AS gate
        INNER JOIN research_job_execution_claims AS claim
          ON claim.job_id = gate.job_id AND claim.tenant_id = gate.tenant_id
        LEFT JOIN research_job_heartbeats AS heartbeat
          ON heartbeat.heartbeat_id = gate.last_heartbeat_id
         AND heartbeat.job_id = gate.job_id
         AND heartbeat.tenant_id = gate.tenant_id
        WHERE gate.job_id = $3 AND gate.tenant_id = $1 AND gate.claimed
          AND EXISTS (SELECT 1 FROM authorized)
      ), classified AS (
        SELECT state.*,
          CASE
            WHEN terminal_status IS NOT NULL THEN 'terminal'
            WHEN cancellation_requested
              AND last_heartbeat_state = 'cancellation-observed'
              AND last_heartbeat_cancellation_revision = cancellation_revision
              THEN 'cancellation-observed'
            WHEN cancellation_requested THEN 'cancellation-pending'
            WHEN lease_expired THEN 'overdue'
            WHEN last_heartbeat_sequence = 0 THEN 'awaiting-first-heartbeat'
            ELSE 'fresh'
          END AS liveness_status
        FROM state
      ), inserted AS (
        INSERT INTO research_job_liveness_snapshots (
          snapshot_id, job_id, tenant_id, claim_id, status,
          lease_duration_seconds, lease_started_at, lease_expires_at,
          lease_expired, last_heartbeat_id, last_heartbeat_sequence,
          last_heartbeat_state, last_heartbeat_cancellation_revision,
          cancellation_revision, terminal_status,
          alert_required, generated_by_actor_id
        )
        SELECT $4, job_id, tenant_id, claim_id, liveness_status,
          lease_duration_seconds, lease_started_at, lease_expires_at,
          lease_expired, last_heartbeat_id, last_heartbeat_sequence,
          last_heartbeat_state, last_heartbeat_cancellation_revision,
          cancellation_revision, terminal_status,
          liveness_status IN ('overdue', 'cancellation-pending',
            'cancellation-observed'), $2
        FROM classified
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        ) SELECT $5, $1, $2, 'research-job.liveness-inspected',
          'research_job', job_id,
          jsonb_build_object('snapshot_id', snapshot_id, 'status', status,
            'lease_expired', lease_expired,
            'last_heartbeat_sequence', last_heartbeat_sequence,
            'cancellation_revision', cancellation_revision,
            'alert_required', alert_required,
            'external_process_liveness_verified', false,
            'alert_delivery_evidence_present', false,
            'production_gate_eligible', false)
        FROM inserted RETURNING id
      ) SELECT inserted.* FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
      `,
      [actor.tenantId, actor.actorId, jobId, snapshotId, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        "Only an active owner or reviewer can inspect claimed-job liveness.",
      );
    }
    return mapLivenessSnapshot(row);
  }

  async recordAlertDelivery(
    signed: SignedResearchJobAlertDeliveryAttestation,
  ): Promise<ResearchJobAlertDeliveryReceipt> {
    this.#validateSignedAlertDelivery(signed);
    const delivery = signed.delivery;
    const contextResult = await this.#database.query<AlertDeliveryContextRow>(
      `
      SELECT snapshot.*, key.public_key_pem, key.public_key_sha256,
        EXISTS (
          SELECT 1 FROM research_job_alert_delivery_attestations AS existing
          WHERE existing.snapshot_id = snapshot.snapshot_id
            AND existing.tenant_id = snapshot.tenant_id
        ) AS alert_delivery_evidence_present
      FROM research_job_liveness_snapshots AS snapshot
      INNER JOIN research_workload_identities AS identity
        ON identity.tenant_id = snapshot.tenant_id
       AND identity.workload_id = $2
       AND identity.purpose = 'research-job-alert-delivery'
      INNER JOIN research_workload_signing_keys AS key
        ON key.tenant_id = identity.tenant_id
       AND key.workload_id = identity.workload_id
       AND key.signing_key_id = $3
      LEFT JOIN research_workload_identity_revocations AS identity_revocation
        ON identity_revocation.tenant_id = identity.tenant_id
       AND identity_revocation.workload_id = identity.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS key_revocation
        ON key_revocation.tenant_id = key.tenant_id
       AND key_revocation.workload_id = key.workload_id
       AND key_revocation.signing_key_id = key.signing_key_id
      WHERE snapshot.snapshot_id = $5 AND snapshot.tenant_id = $1
        AND snapshot.job_id = $6 AND snapshot.claim_id = $7
        AND snapshot.status = $8
        AND snapshot.cancellation_revision = $9
        AND snapshot.generated_at = $10::TIMESTAMPTZ
        AND snapshot.alert_required
        AND snapshot.generated_at <= $4::TIMESTAMPTZ
        AND key.algorithm = 'Ed25519'
        AND key.valid_from <= $4::TIMESTAMPTZ
        AND key.valid_until > $4::TIMESTAMPTZ
        AND key.valid_from <= CURRENT_TIMESTAMP
        AND key.valid_until > CURRENT_TIMESTAMP
        AND identity_revocation.workload_id IS NULL
        AND key_revocation.signing_key_id IS NULL
        AND NOT EXISTS (
          SELECT 1 FROM research_job_alert_delivery_attestations AS existing
          WHERE existing.snapshot_id = snapshot.snapshot_id
            AND existing.tenant_id = snapshot.tenant_id
        )
      `,
      [signed.tenantId, signed.alertDeliveryWorkloadId, signed.signingKeyId,
        signed.issuedAt, delivery.snapshotId, delivery.jobId, delivery.claimId,
        delivery.snapshotStatus, delivery.cancellationRevision,
        delivery.snapshotGeneratedAt],
    );
    const context = contextResult.rows[0];
    if (!context) {
      throw new PlatformDataError("access-denied", "The alert-required liveness snapshot or delivery identity is unavailable.");
    }
    const snapshot = mapLivenessSnapshot(context);
    const snapshotPayloadSha256 = createHash("sha256")
      .update(canonicalResearchJobLivenessSnapshotPayload(snapshot))
      .digest("hex");
    if (snapshotPayloadSha256 !== delivery.snapshotPayloadSha256) {
      throw new PlatformDataError("invalid-artifact", "The alert delivery snapshot hash is invalid.");
    }
    const { signature, ...unsigned } = signed;
    const payload = canonicalResearchJobAlertDeliveryPayload(unsigned);
    const signatureBytes = Buffer.from(signature, "base64url");
    if (signatureBytes.length !== 64 || signatureBytes.toString("base64url") !== signature) {
      throw new PlatformDataError("invalid-artifact", "The alert delivery signature encoding is invalid.");
    }
    let publicKey: ReturnType<typeof createPublicKey>;
    try {
      publicKey = createPublicKey(context.public_key_pem);
    } catch {
      throw new PlatformDataError("invalid-artifact", "The alert delivery key is malformed.");
    }
    if (publicKey.asymmetricKeyType !== "ed25519"
      || !verifySignature(null, Buffer.from(payload), publicKey, signatureBytes)) {
      throw new PlatformDataError("invalid-artifact", "The alert delivery signature is invalid.");
    }
    const payloadSha256 = createHash("sha256").update(payload).digest("hex");
    const signatureSha256 = createHash("sha256").update(signatureBytes).digest("hex");
    const auditId = randomUUID();
    let result;
    try {
      result = await this.#database.query<AlertDeliveryRow>(
        `
        WITH trusted_identity AS (
          UPDATE research_workload_identity_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
          RETURNING gate.tenant_id, gate.workload_id
        ), trusted_key AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $2
            AND gate.signing_key_id = $3 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM trusted_identity)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), authorized AS (
          SELECT 1 FROM research_workload_identities AS identity
          INNER JOIN research_workload_signing_keys AS key
            ON key.tenant_id = identity.tenant_id
           AND key.workload_id = identity.workload_id
          INNER JOIN trusted_key
            ON trusted_key.tenant_id = key.tenant_id
           AND trusted_key.workload_id = key.workload_id
           AND trusted_key.signing_key_id = key.signing_key_id
          WHERE identity.tenant_id = $1 AND identity.workload_id = $2
            AND identity.purpose = 'research-job-alert-delivery'
            AND key.signing_key_id = $3 AND key.public_key_sha256 = $11
            AND key.algorithm = 'Ed25519'
            AND key.valid_from <= $4::TIMESTAMPTZ
            AND key.valid_until > $4::TIMESTAMPTZ
            AND key.valid_from <= CURRENT_TIMESTAMP
            AND key.valid_until > CURRENT_TIMESTAMP
        ), snapshot AS (
          SELECT snapshot.* FROM research_job_liveness_snapshots AS snapshot
          WHERE snapshot.snapshot_id = $5 AND snapshot.tenant_id = $1
            AND snapshot.job_id = $6 AND snapshot.claim_id = $7
            AND snapshot.status = $8
            AND snapshot.cancellation_revision = $9
            AND snapshot.generated_at = $10::TIMESTAMPTZ
            AND snapshot.alert_required
            AND snapshot.generated_at <= $4::TIMESTAMPTZ
            AND EXISTS (SELECT 1 FROM authorized)
            AND NOT EXISTS (
              SELECT 1 FROM research_job_alert_delivery_attestations AS existing
              WHERE existing.snapshot_id = snapshot.snapshot_id
                AND existing.tenant_id = snapshot.tenant_id
            )
        ), inserted AS (
          INSERT INTO research_job_alert_delivery_attestations (
            delivery_id, snapshot_id, job_id, tenant_id, claim_id,
            snapshot_status, cancellation_revision, snapshot_generated_at,
            snapshot_payload_sha256, channel_reference_sha256,
            delivery_receipt_sha256, outcome, attested_by_workload_id,
            signing_key_id, signature_algorithm, public_key_sha256,
            attestation_issued_at, attestation_payload_sha256, signature_sha256
          )
          SELECT $12, snapshot.snapshot_id, snapshot.job_id, $1,
            snapshot.claim_id, snapshot.status, snapshot.cancellation_revision,
            snapshot.generated_at, $13, $14, $15, 'delivered', $2, $3,
            'Ed25519', $11, $4, $16, $17
          FROM snapshot
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, workload_id, action,
            resource_type, resource_id, metadata
          ) SELECT $18, $1, NULL, $2, 'research-job.alert-delivery-attested',
            'research_job', job_id,
            jsonb_build_object('delivery_id', delivery_id,
              'snapshot_id', snapshot_id, 'snapshot_status', snapshot_status,
              'cancellation_revision', cancellation_revision,
              'snapshot_payload_sha256', snapshot_payload_sha256,
              'channel_reference_sha256', channel_reference_sha256,
              'delivery_receipt_sha256', delivery_receipt_sha256)
          FROM inserted RETURNING id
        ) SELECT inserted.* FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
        `,
        [signed.tenantId, signed.alertDeliveryWorkloadId, signed.signingKeyId,
          signed.issuedAt, delivery.snapshotId, delivery.jobId, delivery.claimId,
          delivery.snapshotStatus, delivery.cancellationRevision,
          delivery.snapshotGeneratedAt, context.public_key_sha256,
          delivery.deliveryId, delivery.snapshotPayloadSha256,
          delivery.channelReferenceSha256, delivery.deliveryReceiptSha256,
          payloadSha256, signatureSha256, auditId],
      );
    } catch (error) {
      if (postgresErrorCode(error) === "23505") {
        throw new PlatformDataError("conflict", "This liveness snapshot already has delivery evidence.");
      }
      throw error;
    }
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Alert delivery requires current delivery trust and an undelivered alert snapshot.");
    }
    return mapAlertDelivery(row);
  }

  async getLivenessSnapshot(
    actor: ActorContext,
    snapshotId: string,
  ): Promise<ResearchJobLivenessSnapshot> {
    validateActor(actor);
    if (!opaque.test(snapshotId)) {
      throw new PlatformDataError("invalid-identifier", "Snapshot identifiers must be opaque tokens.");
    }
    const result = await this.#database.query<LivenessSnapshotRow>(
      `
      SELECT snapshot.*,
        EXISTS (
          SELECT 1 FROM research_job_alert_delivery_attestations AS delivery
          WHERE delivery.snapshot_id = snapshot.snapshot_id
            AND delivery.tenant_id = snapshot.tenant_id
        ) AS alert_delivery_evidence_present
      FROM research_job_liveness_snapshots AS snapshot
      WHERE snapshot.snapshot_id = $3 AND snapshot.tenant_id = $1
        AND EXISTS (
          SELECT 1 FROM tenant_memberships
          WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
            AND role IN ('owner', 'reviewer')
        )
      `,
      [actor.tenantId, actor.actorId, snapshotId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The liveness snapshot is unavailable.");
    }
    return mapLivenessSnapshot(row);
  }

  async cancel(
    actor: ActorContext,
    jobId: string,
    reason: "operator-stop" | "incident",
  ): Promise<ResearchJobExecutionState | { readonly jobId: string; readonly cancellationRequested: true }> {
    validateActor(actor);
    if (!opaque.test(jobId)) throw new PlatformDataError("invalid-identifier", "Job identifiers must be opaque tokens.");
    if (!(["operator-stop", "incident"] as const).includes(reason)) {
      throw new PlatformDataError("invalid-artifact", "The research job cancellation reason is unsupported.");
    }
    const auditId = randomUUID();
    const result = await this.#database.query<Record<string, unknown> & { job_id: string }>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships WHERE tenant_id = $1 AND actor_id = $2
          AND status = 'active' AND role IN ('owner', 'reviewer')
      ), target AS (
        SELECT request.id FROM research_job_requests AS request
        WHERE request.id = $3 AND request.tenant_id = $1
          AND EXISTS (SELECT 1 FROM authorized)
        FOR UPDATE OF request
      ), locked_gate AS MATERIALIZED (
        SELECT gate.job_id
        FROM research_job_execution_gates AS gate
        INNER JOIN target ON target.id = gate.job_id
        WHERE gate.tenant_id = $1 AND gate.terminal_status IS NULL
        FOR UPDATE OF gate
      ), cancelled AS (
        INSERT INTO research_job_cancellations (
          job_id, tenant_id, source, reason, requested_by_actor_id
        )
        SELECT locked_gate.job_id, $1, 'operator', $4, $2 FROM locked_gate
        ON CONFLICT DO NOTHING RETURNING job_id
      ), gated AS (
        UPDATE research_job_execution_gates AS gate
        SET cancellation_requested = TRUE,
          cancellation_revision = gate.cancellation_revision + 1,
          updated_at = CURRENT_TIMESTAMP
        FROM cancelled
        WHERE gate.job_id = cancelled.job_id AND gate.tenant_id = $1
          AND gate.terminal_status IS NULL
        RETURNING gate.job_id
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        ) SELECT $5, $1, $2, 'research-job.cancelled', 'research_job',
          cancelled.job_id,
          jsonb_build_object('source', 'operator', 'reason', $4::TEXT)
        FROM cancelled INNER JOIN gated ON gated.job_id = cancelled.job_id
        RETURNING id
      ) SELECT cancelled.job_id, (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM cancelled INNER JOIN gated ON gated.job_id = cancelled.job_id
      `,
      [actor.tenantId, actor.actorId, jobId, reason, auditId],
    );
    if (!result.rows[0]) {
      throw new PlatformDataError("access-denied", "The research job is unavailable or already cancelled.");
    }
    const claim = await this.#loadExecutionState(actor, jobId);
    return claim ?? { jobId, cancellationRequested: true };
  }

  async getExecutionState(actor: ActorContext, jobId: string): Promise<ResearchJobExecutionState> {
    validateActor(actor);
    if (!opaque.test(jobId)) throw new PlatformDataError("invalid-identifier", "Job identifiers must be opaque tokens.");
    const state = await this.#loadExecutionState(actor, jobId);
    if (!state) throw new PlatformDataError("access-denied", "The research job has not been claimed for execution.");
    return state;
  }

  async #loadExecutionState(
    actor: ActorContext,
    jobId: string,
  ): Promise<ResearchJobExecutionState | undefined> {
    const result = await this.#database.query<Record<string, unknown> & {
      claim_id: string;
      envelope_sha256: string;
      claimed_by_actor_id: string | null;
      claimed_by_workload_id: string | null;
      claimed_at: string | Date;
      dispatch_id: string | null;
      dispatch_revision: number | null;
      launch_id: string | null;
      lease_duration_seconds: number;
      lease_started_at: string | Date;
      lease_expires_at: string | Date;
      source: "operator" | "input-quarantined" | "provider-drift" | null;
      reason: ResearchJobCancellationReason | null;
      cancelled_at: string | Date | null;
      terminal_status: "succeeded" | "failed" | "cancelled" | null;
      terminal_receipt_id: string | null;
      terminal_recorded_at: string | Date | null;
    }>(
      `
      SELECT claim.claim_id, claim.envelope_sha256, claim.claimed_by_actor_id,
        claim.claimed_by_workload_id,
        claim.claimed_at, claim.dispatch_id, claim.dispatch_revision,
        claim.launch_id,
        gate.lease_duration_seconds,
        gate.lease_started_at, gate.lease_expires_at,
        cancellation.source, cancellation.reason,
        cancellation.cancelled_at, terminal.terminal_status,
        terminal.receipt_id AS terminal_receipt_id,
        terminal.recorded_at AS terminal_recorded_at
      FROM research_job_execution_claims AS claim
      INNER JOIN research_job_execution_gates AS gate
        ON gate.job_id = claim.job_id AND gate.tenant_id = claim.tenant_id
      LEFT JOIN LATERAL (
        SELECT cancellation.* FROM research_job_cancellations AS cancellation
        WHERE cancellation.job_id = claim.job_id
          AND cancellation.tenant_id = claim.tenant_id
        ORDER BY CASE cancellation.source
          WHEN 'input-quarantined' THEN 3
          WHEN 'provider-drift' THEN 2
          ELSE 1 END DESC,
          cancellation.cancelled_at DESC, cancellation.sequence_id DESC
        LIMIT 1
      ) AS cancellation ON TRUE
      LEFT JOIN research_job_terminal_receipts AS terminal
        ON terminal.job_id = claim.job_id AND terminal.tenant_id = claim.tenant_id
      WHERE claim.job_id = $3 AND claim.tenant_id = $1
        AND EXISTS (SELECT 1 FROM tenant_memberships WHERE tenant_id = $1
          AND actor_id = $2 AND status = 'active' AND role IN ('owner', 'reviewer'))
      `,
      [actor.tenantId, actor.actorId, jobId],
    );
    const row = result.rows[0];
    if (!row) return undefined;
    return {
      claimId: row.claim_id,
      jobId,
      envelopeSha256: row.envelope_sha256,
      ...(row.claimed_by_actor_id === null ? {} : {
        claimedByActorId: row.claimed_by_actor_id,
      }),
      ...(row.claimed_by_workload_id === null ? {} : {
        claimedByWorkloadId: row.claimed_by_workload_id,
      }),
      claimedAt: timestamp(row.claimed_at),
      ...(row.dispatch_id === null ? {} : { dispatchId: row.dispatch_id }),
      ...(row.dispatch_revision === null ? {} : {
        dispatchRevision: Number(row.dispatch_revision),
      }),
      ...(row.launch_id === null ? {} : { launchId: row.launch_id }),
      leaseDurationSeconds: Number(row.lease_duration_seconds),
      leaseStartedAt: timestamp(row.lease_started_at),
      leaseExpiresAt: timestamp(row.lease_expires_at),
      cancellationRequested: row.source !== null,
      ...(row.source === null ? {} : { cancellationSource: row.source }),
      ...(row.reason === null ? {} : { cancellationReason: row.reason }),
      ...(row.cancelled_at === null ? {} : { cancelledAt: timestamp(row.cancelled_at) }),
      ...(row.terminal_status === null ? {} : { terminalStatus: row.terminal_status }),
      ...(row.terminal_receipt_id === null ? {} : {
        terminalReceiptId: row.terminal_receipt_id,
      }),
      ...(row.terminal_recorded_at === null ? {} : {
        terminalRecordedAt: timestamp(row.terminal_recorded_at),
      }),
      evidencePosture: "local-foundation",
      productionGateEligible: false,
    };
  }

  async #recordSuccess(
    verification: WorkloadVerification,
    input: Extract<ResearchJobTerminalInput, { readonly status: "succeeded" }>,
    envelopeSha256: string,
    receiptId: string,
    terminalPayloadSha256: string,
    auditId: string,
  ): Promise<TerminalRow | undefined> {
    const observationId = randomUUID();
    const result = await this.#database.query<TerminalRow>(
      `
      WITH trusted_identity AS (
        UPDATE research_workload_identity_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
        RETURNING gate.tenant_id, gate.workload_id
      ), trusted_key AS (
        UPDATE research_workload_signing_key_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        WHERE gate.tenant_id = $1 AND gate.workload_id = $2
          AND gate.signing_key_id = $18 AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_identity)
        RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
      ), authorized AS (
        SELECT 1 FROM research_workload_signing_keys AS key
        INNER JOIN trusted_key ON trusted_key.tenant_id = key.tenant_id
          AND trusted_key.workload_id = key.workload_id
          AND trusted_key.signing_key_id = key.signing_key_id
        WHERE key.public_key_sha256 = $20 AND key.algorithm = 'Ed25519'
          AND key.valid_from <= $19::TIMESTAMPTZ
          AND key.valid_until > $19::TIMESTAMPTZ
          AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
      ), claim AS (
        SELECT request.*, execution.claim_id, execution.envelope_sha256
        FROM research_job_requests AS request
        INNER JOIN research_job_execution_claims AS execution
          ON execution.job_id = request.id AND execution.tenant_id = request.tenant_id
        WHERE request.id = $3 AND request.tenant_id = $1
          AND execution.claim_id = $4 AND execution.envelope_sha256 = $5
          AND execution.claimed_by_workload_id = $2
          AND EXISTS (SELECT 1 FROM authorized)
      ), ${freshInputCtes}, locked_gate AS MATERIALIZED (
        SELECT gate.* FROM research_job_execution_gates AS gate
        WHERE gate.job_id = $3 AND gate.tenant_id = $1
          AND gate.claimed AND NOT gate.cancellation_requested
          AND gate.terminal_status IS NULL
          AND EXISTS (SELECT 1 FROM claim)
          AND (SELECT COUNT(*) FROM current_input) =
            (SELECT COUNT(*) FROM research_job_inputs WHERE job_id = $3 AND tenant_id = $1)
        FOR UPDATE OF gate
      ), output AS (
        INSERT INTO ml_artifacts (
          id, tenant_id, kind, version, sha256, release_posture,
          learner_feedback_eligible, created_by_actor_id, created_by_workload_id
        )
        SELECT claim.output_id, $1,
          CASE claim.output_kind
            WHEN 'managed-dataset-export' THEN 'dataset'
            ELSE claim.output_kind
          END,
          claim.output_version, $8, 'research-only', FALSE, NULL, $2
        FROM claim
        WHERE EXISTS (SELECT 1 FROM locked_gate)
        ON CONFLICT DO NOTHING
        RETURNING *
      ), lineage AS (
        INSERT INTO artifact_lineage_edges (
          tenant_id, parent_artifact_id, child_artifact_id
        )
        SELECT DISTINCT $1, input.artifact_id, output.id
        FROM research_job_inputs AS input CROSS JOIN output
        WHERE input.job_id = $3 AND input.tenant_id = $1
        RETURNING parent_artifact_id
      ), consent_lineage AS (
        INSERT INTO artifact_consent_dependencies (
          artifact_id, tenant_id, learner_id, consent_snapshot_id, processing_purpose
        )
        SELECT DISTINCT output.id, dependency.tenant_id, dependency.learner_id,
          dependency.consent_snapshot_id, dependency.processing_purpose
        FROM output
        INNER JOIN research_job_inputs AS input
          ON input.job_id = $3 AND input.tenant_id = $1
        INNER JOIN artifact_consent_dependencies AS dependency
          ON dependency.artifact_id = input.artifact_id
         AND dependency.tenant_id = input.tenant_id
        RETURNING artifact_id
      ), binding AS (
        INSERT INTO managed_artifact_objects (
          id, tenant_id, artifact_id, provider_id, object_reference_sha256,
          provider_object_version, expected_sha256, registered_by_actor_id,
          registered_by_workload_id
        )
        SELECT $9, $1, output.id, $10, $11, $12, output.sha256, NULL, $2
        FROM output
        WHERE EXISTS (SELECT 1 FROM lineage)
          AND EXISTS (SELECT 1 FROM consent_lineage)
        RETURNING *
      ), observation AS (
        INSERT INTO managed_artifact_object_observations (
          id, binding_id, tenant_id, artifact_id, artifact_status,
          object_exists, observed_sha256, access_state, outcome,
          provider_checked_at, receipt_reference, receipt_sha256,
          recorded_by_actor_id, recorded_by_workload_id
        )
        SELECT $16, binding.id, $1, binding.artifact_id, 'active',
          TRUE, $8, 'available', 'consistent', $13, $14, $15, NULL, $2
        FROM binding
        RETURNING artifact_id, binding_id
      ), terminal AS (
        INSERT INTO research_job_terminal_receipts (
          receipt_id, job_id, tenant_id, claim_id, envelope_sha256,
          terminal_status, terminal_payload_sha256, output_artifact_id,
          output_binding_id, requested_output_kind, output_artifact_kind,
          output_version, output_sha256, completed_by_actor_id,
          completed_by_workload_id, signing_key_id, signature_algorithm,
          public_key_sha256, attestation_issued_at,
          attestation_payload_sha256, signature_sha256
        )
        SELECT $6, claim.id, $1, claim.claim_id, $5,
          'succeeded', $7, observation.artifact_id, observation.binding_id,
          claim.output_kind, output.kind, output.version, output.sha256,
          NULL, $2, $18, 'Ed25519', $20, $19, $21, $22
        FROM claim CROSS JOIN observation
        INNER JOIN output ON output.id = observation.artifact_id
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, workload_id, action,
          resource_type, resource_id, metadata
        )
        SELECT $17, $1, NULL, $2, 'research-job.succeeded',
          'research_job', terminal.job_id,
          jsonb_build_object(
            'receipt_id', terminal.receipt_id,
            'terminal_payload_sha256', terminal.terminal_payload_sha256,
            'output_artifact_id', terminal.output_artifact_id,
            'output_binding_id', terminal.output_binding_id
          )
        FROM terminal
        RETURNING id
      )
      SELECT terminal.* FROM terminal
      WHERE EXISTS (SELECT 1 FROM audit)
      `,
      [verification.tenantId, verification.workloadId, input.jobId, input.claimId,
        envelopeSha256, receiptId, terminalPayloadSha256, input.outputSha256,
        input.bindingId, input.providerId, input.objectReferenceSha256,
        input.providerObjectVersion, input.providerCheckedAt,
        input.providerReceiptReference, input.providerReceiptSha256,
        observationId, auditId, verification.signingKeyId,
        verification.issuedAt, verification.publicKeySha256,
        verification.payloadSha256, verification.signatureSha256],
    );
    return result.rows[0];
  }

  async #recordNonSuccess(
    verification: WorkloadVerification,
    input: Exclude<ResearchJobTerminalInput, { readonly status: "succeeded" }>,
    envelopeSha256: string,
    receiptId: string,
    terminalPayloadSha256: string,
    auditId: string,
  ): Promise<TerminalRow | undefined> {
    const result = await this.#database.query<TerminalRow>(
      `
      WITH trusted_identity AS (
        UPDATE research_workload_identity_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        WHERE gate.tenant_id = $1 AND gate.workload_id = $2 AND NOT gate.revoked
        RETURNING gate.tenant_id, gate.workload_id
      ), trusted_key AS (
        UPDATE research_workload_signing_key_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        WHERE gate.tenant_id = $1 AND gate.workload_id = $2
          AND gate.signing_key_id = $12 AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_identity)
        RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
      ), authorized AS (
        SELECT 1 FROM research_workload_signing_keys AS key
        INNER JOIN trusted_key ON trusted_key.tenant_id = key.tenant_id
          AND trusted_key.workload_id = key.workload_id
          AND trusted_key.signing_key_id = key.signing_key_id
        WHERE key.public_key_sha256 = $14 AND key.algorithm = 'Ed25519'
          AND key.valid_from <= $13::TIMESTAMPTZ
          AND key.valid_until > $13::TIMESTAMPTZ
          AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
      ), claim AS (
        SELECT execution.* FROM research_job_execution_claims AS execution
        WHERE execution.job_id = $3 AND execution.tenant_id = $1
          AND execution.claim_id = $4 AND execution.envelope_sha256 = $5
          AND execution.claimed_by_workload_id = $2
          AND EXISTS (SELECT 1 FROM authorized)
      ), current_acknowledgement AS (
        SELECT acknowledgement.*
        FROM research_job_cancellation_acknowledgements AS acknowledgement
        WHERE $6 = 'cancelled'
          AND acknowledgement.acknowledgement_id = $17
          AND acknowledgement.job_id = $3 AND acknowledgement.tenant_id = $1
          AND acknowledgement.claim_id = $4
          AND acknowledgement.cancellation_revision = $18
          AND acknowledgement.attestation_issued_at <= $13::TIMESTAMPTZ
      ), current_external_termination AS (
        SELECT termination.*
        FROM research_job_external_termination_attestations AS termination
        WHERE $6 = 'cancelled'
          AND termination.job_id = $3 AND termination.tenant_id = $1
          AND termination.claim_id = $4
          AND termination.cancellation_revision = $18
          AND termination.attestation_issued_at <= $13::TIMESTAMPTZ
      ), trusted_provider_identity AS (
        UPDATE research_workload_identity_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        FROM current_external_termination AS termination
        WHERE gate.tenant_id = termination.tenant_id
          AND gate.workload_id = termination.attested_by_provider_workload_id
          AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_key)
        RETURNING gate.tenant_id, gate.workload_id
      ), trusted_provider_key AS (
        UPDATE research_workload_signing_key_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        FROM current_external_termination AS termination
        WHERE gate.tenant_id = termination.tenant_id
          AND gate.workload_id = termination.attested_by_provider_workload_id
          AND gate.signing_key_id = termination.signing_key_id
          AND NOT gate.revoked
          AND EXISTS (SELECT 1 FROM trusted_provider_identity)
        RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
      ), provider_authorized AS (
        SELECT 1 FROM current_external_termination AS termination
        INNER JOIN research_workload_identities AS provider
          ON provider.tenant_id = termination.tenant_id
         AND provider.workload_id = termination.attested_by_provider_workload_id
         AND provider.purpose = 'research-job-provider'
        INNER JOIN research_workload_signing_keys AS key
          ON key.tenant_id = termination.tenant_id
         AND key.workload_id = termination.attested_by_provider_workload_id
         AND key.signing_key_id = termination.signing_key_id
         AND key.public_key_sha256 = termination.public_key_sha256
        INNER JOIN trusted_provider_key
          ON trusted_provider_key.tenant_id = key.tenant_id
         AND trusted_provider_key.workload_id = key.workload_id
         AND trusted_provider_key.signing_key_id = key.signing_key_id
        WHERE key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
      ), locked_gate AS MATERIALIZED (
        SELECT gate.* FROM research_job_execution_gates AS gate
        WHERE gate.job_id = $3 AND gate.tenant_id = $1
          AND gate.claimed AND gate.terminal_status IS NULL
          AND (($6 = 'cancelled' AND gate.cancellation_requested
              AND gate.cancellation_revision = $18
              AND EXISTS (SELECT 1 FROM current_acknowledgement)
              AND (
                EXISTS (SELECT 1 FROM claim WHERE claim.launch_id IS NULL)
                OR (EXISTS (SELECT 1 FROM current_external_termination)
                  AND EXISTS (SELECT 1 FROM provider_authorized))
              ))
            OR ($6 = 'failed' AND NOT gate.cancellation_requested))
          AND EXISTS (SELECT 1 FROM claim)
        FOR UPDATE OF gate
      ), terminal AS (
        INSERT INTO research_job_terminal_receipts (
          receipt_id, job_id, tenant_id, claim_id, envelope_sha256,
          terminal_status, terminal_payload_sha256, failure_code,
          failure_detail_sha256, completed_by_actor_id,
          cancellation_acknowledgement_id, cancellation_revision,
          external_termination_attestation_id,
          external_termination_cancellation_revision,
          completed_by_workload_id, signing_key_id, signature_algorithm,
          public_key_sha256, attestation_issued_at,
          attestation_payload_sha256, signature_sha256
        )
        SELECT $7, claim.job_id, $1, claim.claim_id, $5,
          $6, $8, $9, $10, NULL, $17, $18,
          (SELECT termination_attestation_id FROM current_external_termination),
          (SELECT cancellation_revision FROM current_external_termination),
          $2, $12, 'Ed25519', $14, $13, $15, $16
        FROM claim
        WHERE EXISTS (SELECT 1 FROM locked_gate)
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, workload_id, action,
          resource_type, resource_id, metadata
        )
        SELECT $11, $1, NULL, $2, 'research-job.' || terminal.terminal_status,
          'research_job', terminal.job_id,
          jsonb_build_object(
            'receipt_id', terminal.receipt_id,
            'terminal_payload_sha256', terminal.terminal_payload_sha256,
            'failure_code', terminal.failure_code,
            'failure_detail_sha256', terminal.failure_detail_sha256,
            'cancellation_acknowledgement_id',
              terminal.cancellation_acknowledgement_id,
            'cancellation_revision', terminal.cancellation_revision,
            'external_termination_attestation_id',
              terminal.external_termination_attestation_id
          )
        FROM terminal
        RETURNING id
      )
      SELECT terminal.* FROM terminal
      WHERE EXISTS (SELECT 1 FROM audit)
      `,
      [verification.tenantId, verification.workloadId, input.jobId, input.claimId,
        envelopeSha256, input.status, receiptId, terminalPayloadSha256,
        input.failureCode, input.failureDetailSha256, auditId,
        verification.signingKeyId, verification.issuedAt,
        verification.publicKeySha256, verification.payloadSha256,
        verification.signatureSha256,
        input.status === "cancelled" ? input.cancellationAcknowledgementId : null,
        input.status === "cancelled" ? input.cancellationRevision : null],
    );
    return result.rows[0];
  }

  async #loadCancellationContext(
    signed: SignedResearchJobCancellationAcknowledgement,
  ): Promise<CancellationContextRow> {
    const result = await this.#database.query<CancellationContextRow>(
      `
      SELECT request.*, approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, key.public_key_pem, key.public_key_sha256,
        gate.cancellation_revision,
        cancellation.sequence_id AS cancellation_sequence_id,
        cancellation.source AS cancellation_source,
        cancellation.reason AS cancellation_reason,
        cancellation.cancelled_at AS cancellation_cancelled_at,
        latest_cancellation.cancelled_at AS cancellation_latest_at,
        jsonb_agg(jsonb_build_object(
          'artifactId', input.artifact_id, 'artifactKind', input.artifact_kind,
          'artifactSha256', input.artifact_sha256, 'bindingId', input.binding_id,
          'providerId', input.provider_id,
          'objectReferenceSha256', input.object_reference_sha256,
          'providerObjectVersion', input.provider_object_version
        ) ORDER BY input.artifact_id, input.binding_id) AS inputs
      FROM research_job_requests AS request
      INNER JOIN research_job_inputs AS input
        ON input.job_id = request.id AND input.tenant_id = request.tenant_id
      INNER JOIN research_job_approvals AS approval
        ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
      INNER JOIN research_job_execution_claims AS claim
        ON claim.job_id = request.id AND claim.tenant_id = request.tenant_id
       AND claim.claim_id = $4 AND claim.claimed_by_workload_id = $2
      INNER JOIN research_job_execution_gates AS gate
        ON gate.job_id = request.id AND gate.tenant_id = request.tenant_id
      INNER JOIN LATERAL (
        SELECT cancellation.* FROM research_job_cancellations AS cancellation
        WHERE cancellation.job_id = request.id AND cancellation.tenant_id = request.tenant_id
        ORDER BY CASE cancellation.source WHEN 'input-quarantined' THEN 3
          WHEN 'provider-drift' THEN 2 ELSE 1 END DESC,
          cancellation.cancelled_at DESC, cancellation.sequence_id DESC
        LIMIT 1
      ) AS cancellation ON TRUE
      INNER JOIN LATERAL (
        SELECT MAX(latest.cancelled_at) AS cancelled_at
        FROM research_job_cancellations AS latest
        WHERE latest.job_id = request.id AND latest.tenant_id = request.tenant_id
      ) AS latest_cancellation ON TRUE
      INNER JOIN research_workload_identities AS identity
        ON identity.tenant_id = request.tenant_id AND identity.workload_id = $2
      INNER JOIN research_workload_signing_keys AS key
        ON key.tenant_id = identity.tenant_id AND key.workload_id = identity.workload_id
       AND key.signing_key_id = $5
      LEFT JOIN research_workload_identity_revocations AS identity_revocation
        ON identity_revocation.tenant_id = identity.tenant_id
       AND identity_revocation.workload_id = identity.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS key_revocation
        ON key_revocation.tenant_id = key.tenant_id
       AND key_revocation.workload_id = key.workload_id
       AND key_revocation.signing_key_id = key.signing_key_id
      WHERE request.id = $3 AND request.tenant_id = $1
        AND key.algorithm = 'Ed25519'
        AND key.valid_from <= $6::TIMESTAMPTZ AND key.valid_until > $6::TIMESTAMPTZ
        AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
        AND identity_revocation.workload_id IS NULL
        AND key_revocation.signing_key_id IS NULL
      GROUP BY request.id, request.tenant_id, request.job_type,
        request.output_kind, request.output_id, request.output_version,
        request.code_revision, request.configuration_sha256,
        request.runner_image_digest, request.intended_use, request.exclusions,
        request.release_posture, request.learner_feedback_eligible,
        request.requested_by_actor_id, request.requested_at, request.expires_at,
        gate.cancellation_revision,
        approval.approved_by_actor_id, approval.approved_at, approval.envelope_sha256,
        key.public_key_pem, key.public_key_sha256, cancellation.sequence_id,
        cancellation.source, cancellation.reason, cancellation.cancelled_at,
        latest_cancellation.cancelled_at
      `,
      [signed.tenantId, signed.workloadId, signed.acknowledgement.jobId,
        signed.acknowledgement.claimId, signed.signingKeyId, signed.issuedAt],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The signed cancellation context is unavailable.");
    }
    return row;
  }

  async #loadExternalTerminationContext(
    signed: SignedResearchJobExternalTerminationAttestation,
  ): Promise<ExternalTerminationContextRow> {
    const termination = signed.termination;
    const result = await this.#database.query<ExternalTerminationContextRow>(
      `
      SELECT request.*, approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, provider_key.public_key_pem,
        provider_key.public_key_sha256, gate.cancellation_revision,
        cancellation.sequence_id AS cancellation_sequence_id,
        cancellation.source AS cancellation_source,
        cancellation.reason AS cancellation_reason,
        cancellation.cancelled_at AS cancellation_cancelled_at,
        latest.cancelled_at AS cancellation_latest_at,
        launch.recorded_at AS launch_recorded_at,
        jsonb_agg(jsonb_build_object(
          'artifactId', input.artifact_id, 'artifactKind', input.artifact_kind,
          'artifactSha256', input.artifact_sha256, 'bindingId', input.binding_id,
          'providerId', input.provider_id,
          'objectReferenceSha256', input.object_reference_sha256,
          'providerObjectVersion', input.provider_object_version
        ) ORDER BY input.artifact_id, input.binding_id) AS inputs
      FROM research_job_requests AS request
      INNER JOIN research_job_inputs AS input
        ON input.job_id = request.id AND input.tenant_id = request.tenant_id
      INNER JOIN research_job_approvals AS approval
        ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
      INNER JOIN research_job_execution_claims AS claim
        ON claim.job_id = request.id AND claim.tenant_id = request.tenant_id
       AND claim.claim_id = $4 AND claim.envelope_sha256 = $5
       AND claim.claimed_by_workload_id = $10
       AND claim.launch_id = $6 AND claim.dispatch_id = $7
       AND claim.dispatch_revision = $8
      INNER JOIN research_job_launch_attestations AS launch
        ON launch.launch_id = claim.launch_id
       AND launch.job_id = claim.job_id AND launch.tenant_id = claim.tenant_id
       AND launch.process_reference_sha256 = $9
      INNER JOIN research_job_execution_gates AS gate
        ON gate.job_id = request.id AND gate.tenant_id = request.tenant_id
      INNER JOIN LATERAL (
        SELECT cancellation.* FROM research_job_cancellations AS cancellation
        WHERE cancellation.job_id = request.id AND cancellation.tenant_id = request.tenant_id
        ORDER BY CASE cancellation.source WHEN 'input-quarantined' THEN 3
          WHEN 'provider-drift' THEN 2 ELSE 1 END DESC,
          cancellation.cancelled_at DESC, cancellation.sequence_id DESC
        LIMIT 1
      ) AS cancellation ON TRUE
      INNER JOIN LATERAL (
        SELECT MAX(item.cancelled_at) AS cancelled_at
        FROM research_job_cancellations AS item
        WHERE item.job_id = request.id AND item.tenant_id = request.tenant_id
      ) AS latest ON TRUE
      INNER JOIN research_workload_identities AS provider
        ON provider.tenant_id = request.tenant_id AND provider.workload_id = $2
       AND provider.purpose = 'research-job-provider'
      INNER JOIN research_workload_signing_keys AS provider_key
        ON provider_key.tenant_id = provider.tenant_id
       AND provider_key.workload_id = provider.workload_id
       AND provider_key.signing_key_id = $11
      LEFT JOIN research_workload_identity_revocations AS provider_revocation
        ON provider_revocation.tenant_id = provider.tenant_id
       AND provider_revocation.workload_id = provider.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS provider_key_revocation
        ON provider_key_revocation.tenant_id = provider_key.tenant_id
       AND provider_key_revocation.workload_id = provider_key.workload_id
       AND provider_key_revocation.signing_key_id = provider_key.signing_key_id
      WHERE request.id = $3 AND request.tenant_id = $1
        AND gate.claimed AND gate.cancellation_requested
        AND gate.cancellation_revision = $12 AND gate.terminal_status IS NULL
        AND cancellation.sequence_id = $13
        AND cancellation.source = $14 AND cancellation.reason = $15
        AND cancellation.cancelled_at <= $16::TIMESTAMPTZ
        AND latest.cancelled_at <= $16::TIMESTAMPTZ
        AND launch.recorded_at <= $16::TIMESTAMPTZ
        AND provider_key.algorithm = 'Ed25519'
        AND provider_key.valid_from <= $16::TIMESTAMPTZ
        AND provider_key.valid_until > $16::TIMESTAMPTZ
        AND provider_key.valid_from <= CURRENT_TIMESTAMP
        AND provider_key.valid_until > CURRENT_TIMESTAMP
        AND provider_revocation.workload_id IS NULL
        AND provider_key_revocation.signing_key_id IS NULL
      GROUP BY request.id, request.tenant_id, request.job_type,
        request.output_kind, request.output_id, request.output_version,
        request.code_revision, request.configuration_sha256,
        request.runner_image_digest, request.intended_use, request.exclusions,
        request.release_posture, request.learner_feedback_eligible,
        request.requested_by_actor_id, request.requested_at, request.expires_at,
        approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, provider_key.public_key_pem,
        provider_key.public_key_sha256, gate.cancellation_revision,
        cancellation.sequence_id, cancellation.source, cancellation.reason,
        cancellation.cancelled_at, latest.cancelled_at, launch.recorded_at
      `,
      [signed.tenantId, signed.providerWorkloadId, termination.jobId,
        termination.claimId, termination.envelopeSha256, termination.launchId,
        termination.dispatchId, termination.dispatchRevision,
        termination.processReferenceSha256, termination.assignedWorkloadId,
        signed.signingKeyId, termination.cancellationRevision,
        termination.cancellationSequenceId, termination.cancellationSource,
        termination.cancellationReason, signed.issuedAt],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The external termination context is unavailable.");
    }
    return row;
  }

  async #loadWorkloadJobContext(
    signed: Pick<SignedResearchJobTerminalAttestation,
      "tenantId" | "workloadId" | "signingKeyId" | "issuedAt">,
    jobId: string,
    claimId: string,
    evidenceKind: "terminal" | "heartbeat",
  ): Promise<WorkloadJobRow> {
    const result = await this.#database.query<WorkloadJobRow>(
      `
      SELECT request.*, approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, key.public_key_pem, key.public_key_sha256,
        jsonb_agg(jsonb_build_object(
          'artifactId', input.artifact_id, 'artifactKind', input.artifact_kind,
          'artifactSha256', input.artifact_sha256, 'bindingId', input.binding_id,
          'providerId', input.provider_id,
          'objectReferenceSha256', input.object_reference_sha256,
          'providerObjectVersion', input.provider_object_version
        ) ORDER BY input.artifact_id, input.binding_id) AS inputs
      FROM research_job_requests AS request
      INNER JOIN research_job_inputs AS input
        ON input.job_id = request.id AND input.tenant_id = request.tenant_id
      INNER JOIN research_job_approvals AS approval
        ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
      INNER JOIN research_job_execution_claims AS claim
        ON claim.job_id = request.id AND claim.tenant_id = request.tenant_id
       AND claim.claim_id = $4 AND claim.claimed_by_workload_id = $2
      INNER JOIN research_workload_identities AS identity
        ON identity.tenant_id = request.tenant_id AND identity.workload_id = $2
      INNER JOIN research_workload_signing_keys AS key
        ON key.tenant_id = identity.tenant_id AND key.workload_id = identity.workload_id
       AND key.signing_key_id = $5
      LEFT JOIN research_workload_identity_revocations AS identity_revocation
        ON identity_revocation.tenant_id = identity.tenant_id
       AND identity_revocation.workload_id = identity.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS key_revocation
        ON key_revocation.tenant_id = key.tenant_id
       AND key_revocation.workload_id = key.workload_id
       AND key_revocation.signing_key_id = key.signing_key_id
      WHERE request.id = $3 AND request.tenant_id = $1
        AND key.algorithm = 'Ed25519'
        AND key.valid_from <= $6::TIMESTAMPTZ AND key.valid_until > $6::TIMESTAMPTZ
        AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
        AND identity_revocation.workload_id IS NULL
        AND key_revocation.signing_key_id IS NULL
      GROUP BY request.id, request.tenant_id, request.job_type,
        request.output_kind, request.output_id, request.output_version,
        request.code_revision, request.configuration_sha256,
        request.runner_image_digest, request.intended_use, request.exclusions,
        request.release_posture, request.learner_feedback_eligible,
        request.requested_by_actor_id, request.requested_at, request.expires_at,
        approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, key.public_key_pem, key.public_key_sha256
      `,
      [signed.tenantId, signed.workloadId, jobId,
        claimId, signed.signingKeyId, signed.issuedAt],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError(
        "access-denied",
        `The signed workload ${evidenceKind} context is unavailable.`,
      );
    }
    return row;
  }

  async #loadDispatchContext(signed: SignedResearchJobDispatch): Promise<WorkloadJobRow> {
    const result = await this.#database.query<WorkloadJobRow>(
      `
      SELECT request.*, approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, key.public_key_pem, key.public_key_sha256,
        jsonb_agg(jsonb_build_object(
          'artifactId', input.artifact_id, 'artifactKind', input.artifact_kind,
          'artifactSha256', input.artifact_sha256, 'bindingId', input.binding_id,
          'providerId', input.provider_id,
          'objectReferenceSha256', input.object_reference_sha256,
          'providerObjectVersion', input.provider_object_version
        ) ORDER BY input.artifact_id, input.binding_id) AS inputs
      FROM research_job_requests AS request
      INNER JOIN research_job_inputs AS input
        ON input.job_id = request.id AND input.tenant_id = request.tenant_id
      INNER JOIN research_job_approvals AS approval
        ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
      INNER JOIN research_job_execution_gates AS gate
        ON gate.job_id = request.id AND gate.tenant_id = request.tenant_id
      INNER JOIN research_workload_identities AS identity
        ON identity.tenant_id = request.tenant_id
       AND identity.workload_id = $2
       AND identity.purpose = 'research-job-scheduler'
      INNER JOIN research_workload_signing_keys AS key
        ON key.tenant_id = identity.tenant_id AND key.workload_id = identity.workload_id
       AND key.signing_key_id = $4
      INNER JOIN research_workload_identities AS runner
        ON runner.tenant_id = request.tenant_id
       AND runner.workload_id = $6
       AND runner.purpose = 'research-job-runner'
      LEFT JOIN research_workload_identity_revocations AS identity_revocation
        ON identity_revocation.tenant_id = identity.tenant_id
       AND identity_revocation.workload_id = identity.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS key_revocation
        ON key_revocation.tenant_id = key.tenant_id
       AND key_revocation.workload_id = key.workload_id
       AND key_revocation.signing_key_id = key.signing_key_id
      LEFT JOIN research_workload_identity_revocations AS runner_revocation
        ON runner_revocation.tenant_id = runner.tenant_id
       AND runner_revocation.workload_id = runner.workload_id
      WHERE request.id = $3 AND request.tenant_id = $1
        AND approval.envelope_sha256 = $7
        AND approval.approved_at <= $5::TIMESTAMPTZ
        AND request.expires_at > CURRENT_TIMESTAMP
        AND NOT gate.claimed AND NOT gate.cancellation_requested
        AND gate.terminal_status IS NULL
        AND gate.dispatch_revision = $8::BIGINT - 1
        AND key.algorithm = 'Ed25519'
        AND key.valid_from <= $5::TIMESTAMPTZ AND key.valid_until > $5::TIMESTAMPTZ
        AND key.valid_from <= CURRENT_TIMESTAMP AND key.valid_until > CURRENT_TIMESTAMP
        AND identity_revocation.workload_id IS NULL
        AND key_revocation.signing_key_id IS NULL
        AND runner_revocation.workload_id IS NULL
      GROUP BY request.id, request.tenant_id, request.job_type,
        request.output_kind, request.output_id, request.output_version,
        request.code_revision, request.configuration_sha256,
        request.runner_image_digest, request.intended_use, request.exclusions,
        request.release_posture, request.learner_feedback_eligible,
        request.requested_by_actor_id, request.requested_at, request.expires_at,
        approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, key.public_key_pem, key.public_key_sha256
      `,
      [signed.tenantId, signed.schedulerWorkloadId, signed.dispatch.jobId,
        signed.signingKeyId, signed.issuedAt, signed.dispatch.assignedWorkloadId,
        signed.dispatch.envelopeSha256, signed.dispatch.dispatchRevision],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The signed scheduler dispatch context is unavailable.");
    }
    return row;
  }

  async #loadLaunchContext(
    signed: SignedResearchJobLaunchAttestation,
  ): Promise<LaunchContextRow> {
    const launch = signed.launch;
    const result = await this.#database.query<LaunchContextRow>(
      `
      SELECT request.*, approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256,
        provider_key.public_key_pem, provider_key.public_key_sha256,
        dispatch.recorded_at AS dispatch_recorded_at,
        dispatch.expires_at AS dispatch_expires_at,
        dispatch.dispatched_by_workload_id AS scheduler_workload_id,
        dispatch.signing_key_id AS scheduler_signing_key_id,
        dispatch.public_key_sha256 AS scheduler_public_key_sha256,
        jsonb_agg(jsonb_build_object(
          'artifactId', input.artifact_id, 'artifactKind', input.artifact_kind,
          'artifactSha256', input.artifact_sha256, 'bindingId', input.binding_id,
          'providerId', input.provider_id,
          'objectReferenceSha256', input.object_reference_sha256,
          'providerObjectVersion', input.provider_object_version
        ) ORDER BY input.artifact_id, input.binding_id) AS inputs
      FROM research_job_requests AS request
      INNER JOIN research_job_inputs AS input
        ON input.job_id = request.id AND input.tenant_id = request.tenant_id
      INNER JOIN research_job_approvals AS approval
        ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
      INNER JOIN research_job_execution_gates AS gate
        ON gate.job_id = request.id AND gate.tenant_id = request.tenant_id
      INNER JOIN research_job_dispatches AS dispatch
        ON dispatch.dispatch_id = $7 AND dispatch.job_id = request.id
       AND dispatch.tenant_id = request.tenant_id
       AND dispatch.dispatch_revision = $8
       AND dispatch.assigned_workload_id = $9
       AND dispatch.envelope_sha256 = approval.envelope_sha256
      INNER JOIN research_workload_identities AS provider
        ON provider.tenant_id = request.tenant_id
       AND provider.workload_id = $2
       AND provider.purpose = 'research-job-provider'
      INNER JOIN research_workload_signing_keys AS provider_key
        ON provider_key.tenant_id = provider.tenant_id
       AND provider_key.workload_id = provider.workload_id
       AND provider_key.signing_key_id = $4
      INNER JOIN research_workload_identities AS runner
        ON runner.tenant_id = dispatch.tenant_id
       AND runner.workload_id = dispatch.assigned_workload_id
       AND runner.purpose = 'research-job-runner'
      INNER JOIN research_workload_identities AS scheduler
        ON scheduler.tenant_id = dispatch.tenant_id
       AND scheduler.workload_id = dispatch.dispatched_by_workload_id
       AND scheduler.purpose = 'research-job-scheduler'
      LEFT JOIN research_workload_identity_revocations AS provider_revocation
        ON provider_revocation.tenant_id = provider.tenant_id
       AND provider_revocation.workload_id = provider.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS provider_key_revocation
        ON provider_key_revocation.tenant_id = provider_key.tenant_id
       AND provider_key_revocation.workload_id = provider_key.workload_id
       AND provider_key_revocation.signing_key_id = provider_key.signing_key_id
      LEFT JOIN research_workload_identity_revocations AS runner_revocation
        ON runner_revocation.tenant_id = runner.tenant_id
       AND runner_revocation.workload_id = runner.workload_id
      LEFT JOIN research_workload_identity_revocations AS scheduler_revocation
        ON scheduler_revocation.tenant_id = scheduler.tenant_id
       AND scheduler_revocation.workload_id = scheduler.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS scheduler_key_revocation
        ON scheduler_key_revocation.tenant_id = dispatch.tenant_id
       AND scheduler_key_revocation.workload_id = dispatch.dispatched_by_workload_id
       AND scheduler_key_revocation.signing_key_id = dispatch.signing_key_id
      WHERE request.id = $3 AND request.tenant_id = $1
        AND approval.envelope_sha256 = $6
        AND request.runner_image_digest = $10
        AND gate.active_dispatch_id = dispatch.dispatch_id
        AND gate.dispatch_revision = dispatch.dispatch_revision
        AND gate.active_dispatch_workload_id = dispatch.assigned_workload_id
        AND gate.active_launch_id IS NULL
        AND NOT gate.claimed AND NOT gate.cancellation_requested
        AND gate.terminal_status IS NULL
        AND dispatch.recorded_at <= $5::TIMESTAMPTZ
        AND dispatch.expires_at > $5::TIMESTAMPTZ
        AND dispatch.expires_at > CURRENT_TIMESTAMP
        AND provider_key.algorithm = 'Ed25519'
        AND provider_key.valid_from <= $5::TIMESTAMPTZ
        AND provider_key.valid_until > $5::TIMESTAMPTZ
        AND provider_key.valid_from <= CURRENT_TIMESTAMP
        AND provider_key.valid_until > CURRENT_TIMESTAMP
        AND provider_revocation.workload_id IS NULL
        AND provider_key_revocation.signing_key_id IS NULL
        AND runner_revocation.workload_id IS NULL
        AND scheduler_revocation.workload_id IS NULL
        AND scheduler_key_revocation.signing_key_id IS NULL
      GROUP BY request.id, request.tenant_id, request.job_type,
        request.output_kind, request.output_id, request.output_version,
        request.code_revision, request.configuration_sha256,
        request.runner_image_digest, request.intended_use, request.exclusions,
        request.release_posture, request.learner_feedback_eligible,
        request.requested_by_actor_id, request.requested_at, request.expires_at,
        approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, provider_key.public_key_pem,
        provider_key.public_key_sha256, dispatch.recorded_at,
        dispatch.expires_at, dispatch.dispatched_by_workload_id,
        dispatch.signing_key_id, dispatch.public_key_sha256
      `,
      [signed.tenantId, signed.providerWorkloadId, launch.jobId,
        signed.signingKeyId, signed.issuedAt, launch.envelopeSha256,
        launch.dispatchId, launch.dispatchRevision,
        launch.assignedWorkloadId, launch.runnerImageDigest],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The signed launch context is unavailable.");
    }
    return row;
  }

  async #loadSignedClaim(signed: SignedResearchJobExecutionClaim): Promise<WorkloadJobRow> {
    const result = await this.#database.query<WorkloadJobRow>(
      `
      SELECT request.*, approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, key.public_key_pem, key.public_key_sha256,
        jsonb_agg(jsonb_build_object(
          'artifactId', input.artifact_id, 'artifactKind', input.artifact_kind,
          'artifactSha256', input.artifact_sha256, 'bindingId', input.binding_id,
          'providerId', input.provider_id,
          'objectReferenceSha256', input.object_reference_sha256,
          'providerObjectVersion', input.provider_object_version
        ) ORDER BY input.artifact_id, input.binding_id) AS inputs
      FROM research_job_requests AS request
      INNER JOIN research_job_inputs AS input
        ON input.job_id = request.id AND input.tenant_id = request.tenant_id
      INNER JOIN research_job_approvals AS approval
        ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
      INNER JOIN research_job_execution_gates AS execution_gate
        ON execution_gate.job_id = request.id
       AND execution_gate.tenant_id = request.tenant_id
      INNER JOIN research_job_dispatches AS dispatch
        ON dispatch.dispatch_id = $7 AND dispatch.job_id = request.id
       AND dispatch.tenant_id = request.tenant_id
       AND dispatch.dispatch_revision = $8
       AND dispatch.assigned_workload_id = $2
       AND dispatch.envelope_sha256 = approval.envelope_sha256
      INNER JOIN research_job_launch_attestations AS launch
        ON launch.launch_id = execution_gate.active_launch_id
       AND launch.job_id = request.id AND launch.tenant_id = request.tenant_id
       AND launch.dispatch_id = dispatch.dispatch_id
       AND launch.dispatch_revision = dispatch.dispatch_revision
       AND launch.assigned_workload_id = dispatch.assigned_workload_id
       AND launch.envelope_sha256 = dispatch.envelope_sha256
      INNER JOIN research_workload_identities AS provider
        ON provider.tenant_id = launch.tenant_id
       AND provider.workload_id = launch.attested_by_provider_workload_id
       AND provider.purpose = 'research-job-provider'
      INNER JOIN research_workload_signing_keys AS provider_key
        ON provider_key.tenant_id = provider.tenant_id
       AND provider_key.workload_id = provider.workload_id
       AND provider_key.signing_key_id = launch.signing_key_id
       AND provider_key.public_key_sha256 = launch.public_key_sha256
      INNER JOIN research_workload_identities AS identity
        ON identity.tenant_id = request.tenant_id AND identity.workload_id = $2
       AND identity.purpose = 'research-job-runner'
      INNER JOIN research_workload_signing_keys AS key
        ON key.tenant_id = identity.tenant_id
       AND key.workload_id = identity.workload_id
       AND key.signing_key_id = $4
      LEFT JOIN research_workload_identity_revocations AS identity_revocation
        ON identity_revocation.tenant_id = identity.tenant_id
       AND identity_revocation.workload_id = identity.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS key_revocation
        ON key_revocation.tenant_id = key.tenant_id
       AND key_revocation.workload_id = key.workload_id
       AND key_revocation.signing_key_id = key.signing_key_id
      LEFT JOIN research_workload_identity_revocations AS scheduler_revocation
        ON scheduler_revocation.tenant_id = dispatch.tenant_id
       AND scheduler_revocation.workload_id = dispatch.dispatched_by_workload_id
      LEFT JOIN research_workload_signing_key_revocations AS scheduler_key_revocation
        ON scheduler_key_revocation.tenant_id = dispatch.tenant_id
       AND scheduler_key_revocation.workload_id = dispatch.dispatched_by_workload_id
       AND scheduler_key_revocation.signing_key_id = dispatch.signing_key_id
      LEFT JOIN research_workload_identity_revocations AS provider_revocation
        ON provider_revocation.tenant_id = provider.tenant_id
       AND provider_revocation.workload_id = provider.workload_id
      LEFT JOIN research_workload_signing_key_revocations AS provider_key_revocation
        ON provider_key_revocation.tenant_id = provider_key.tenant_id
       AND provider_key_revocation.workload_id = provider_key.workload_id
       AND provider_key_revocation.signing_key_id = provider_key.signing_key_id
      WHERE request.id = $3 AND request.tenant_id = $1
        AND approval.envelope_sha256 = $5
        AND execution_gate.active_dispatch_id = dispatch.dispatch_id
        AND execution_gate.dispatch_revision = dispatch.dispatch_revision
        AND execution_gate.active_dispatch_workload_id = $2
        AND execution_gate.active_dispatch_expires_at > CURRENT_TIMESTAMP
        AND dispatch.expires_at > CURRENT_TIMESTAMP
        AND dispatch.expires_at > $6::TIMESTAMPTZ
        AND dispatch.recorded_at <= $6::TIMESTAMPTZ
        AND launch.recorded_at <= $6::TIMESTAMPTZ
        AND key.algorithm = 'Ed25519'
        AND key.valid_from <= $6::TIMESTAMPTZ
        AND key.valid_until > $6::TIMESTAMPTZ
        AND key.valid_from <= CURRENT_TIMESTAMP
        AND key.valid_until > CURRENT_TIMESTAMP
        AND identity_revocation.workload_id IS NULL
        AND key_revocation.signing_key_id IS NULL
        AND scheduler_revocation.workload_id IS NULL
        AND scheduler_key_revocation.signing_key_id IS NULL
        AND provider_key.valid_from <= CURRENT_TIMESTAMP
        AND provider_key.valid_until > CURRENT_TIMESTAMP
        AND provider_revocation.workload_id IS NULL
        AND provider_key_revocation.signing_key_id IS NULL
      GROUP BY request.id, request.tenant_id, request.job_type,
        request.output_kind, request.output_id, request.output_version,
        request.code_revision, request.configuration_sha256,
        request.runner_image_digest, request.intended_use, request.exclusions,
        request.release_posture, request.learner_feedback_eligible,
        request.requested_by_actor_id, request.requested_at, request.expires_at,
        approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256, key.public_key_pem, key.public_key_sha256
      `,
      [signed.tenantId, signed.workloadId, signed.jobId, signed.signingKeyId,
        signed.envelopeSha256, signed.issuedAt, signed.dispatchId,
        signed.dispatchRevision],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The signed workload, key, or research job is unavailable.");
    }
    return row;
  }

  async #load(actor: ActorContext, jobId: string): Promise<ResearchJobAuthorizationEnvelope> {
    const result = await this.#database.query<JobRow>(
      `
      SELECT request.*, approval.approved_by_actor_id, approval.approved_at,
        approval.envelope_sha256,
        jsonb_agg(jsonb_build_object(
          'artifactId', input.artifact_id, 'artifactKind', input.artifact_kind,
          'artifactSha256', input.artifact_sha256, 'bindingId', input.binding_id,
          'providerId', input.provider_id,
          'objectReferenceSha256', input.object_reference_sha256,
          'providerObjectVersion', input.provider_object_version
        ) ORDER BY input.artifact_id, input.binding_id) AS inputs
      FROM research_job_requests AS request
      INNER JOIN research_job_inputs AS input
        ON input.job_id = request.id AND input.tenant_id = request.tenant_id
      LEFT JOIN research_job_approvals AS approval
        ON approval.job_id = request.id AND approval.tenant_id = request.tenant_id
      WHERE request.id = $3 AND request.tenant_id = $1
        AND EXISTS (SELECT 1 FROM tenant_memberships WHERE tenant_id = $1
          AND actor_id = $2 AND status = 'active' AND role IN ('owner', 'reviewer'))
      GROUP BY request.id, request.tenant_id, request.job_type,
        request.output_kind, request.output_id, request.output_version,
        request.code_revision, request.configuration_sha256,
        request.runner_image_digest, request.intended_use, request.exclusions,
        request.release_posture, request.learner_feedback_eligible,
        request.requested_by_actor_id, request.requested_at, request.expires_at,
        approval.approved_by_actor_id, approval.approved_at, approval.envelope_sha256
      `,
      [actor.tenantId, actor.actorId, jobId],
    );
    const row = result.rows[0];
    if (!row) throw new PlatformDataError("access-denied", "The research job is unavailable to this actor.");
    return mapEnvelope(row);
  }

  #validateRequest(input: ResearchJobRequestInput): void {
    if (!opaque.test(input.jobId) || !artifactIdentifier.test(input.outputId)
      || !version.test(input.outputVersion) || !gitRevision.test(input.codeRevision)
      || !sha256.test(input.configurationSha256) || !imageDigest.test(input.runnerImageDigest)
      || input.intendedUse.length < 10 || input.intendedUse.length > 500
      || input.inputs.length < 1 || input.inputs.length > 20
      || input.exclusions.length < 1 || input.exclusions.length > 20
      || input.exclusions.some((item) => item.length < 1 || item.length > 200)) {
      throw new PlatformDataError("invalid-artifact", "Research job provenance and scope are invalid.");
    }
    const keys = input.inputs.map((item) => `${item.artifactId}\0${item.bindingId}`);
    if (new Set(keys).size !== keys.length
      || input.inputs.some((item) => !opaque.test(item.artifactId) || !opaque.test(item.bindingId))
      || new Set(input.exclusions).size !== input.exclusions.length) {
      throw new PlatformDataError("invalid-artifact", "Research job inputs and exclusions must be unique opaque values.");
    }
    const expires = new Date(input.expiresAt);
    const now = this.#now().getTime();
    if (!Number.isFinite(expires.getTime()) || expires.toISOString() !== input.expiresAt
      || expires.getTime() < now + 300_000 || expires.getTime() > now + 86_400_000) {
      throw new PlatformDataError("invalid-artifact", "Research job expiry must be 5 minutes to 24 hours from issuance.");
    }
  }

  #validateSignedClaim(signed: SignedResearchJobExecutionClaim): void {
    if (typeof signed !== "object" || signed === null) {
      throw new PlatformDataError("invalid-artifact", "A signed workload execution claim is required.");
    }
    const issuedAt = new Date(signed.issuedAt);
    const now = this.#now().getTime();
    if (signed.schemaVersion !== "research-job-execution-claim-signature-v2"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.workloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !opaque.test(signed.claimId)
      || !opaque.test(signed.jobId)
      || !sha256.test(signed.envelopeSha256)
      || !opaque.test(signed.dispatchId)
      || !Number.isSafeInteger(signed.dispatchRevision)
      || signed.dispatchRevision < 1
      || !ed25519Signature.test(signed.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000) {
      throw new PlatformDataError("invalid-artifact", "The signed workload execution claim is malformed or stale.");
    }
  }

  #validateSignedDispatch(signed: SignedResearchJobDispatch): void {
    if (typeof signed !== "object" || signed === null
      || typeof signed.dispatch !== "object" || signed.dispatch === null) {
      throw new PlatformDataError("invalid-artifact", "A signed scheduler dispatch is required.");
    }
    const issuedAt = new Date(signed.issuedAt);
    const expiresAt = new Date(signed.dispatch.expiresAt);
    const now = this.#now().getTime();
    if (signed.schemaVersion !== "research-job-dispatch-signature-v1"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.schedulerWorkloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !opaque.test(signed.dispatch.dispatchId)
      || !opaque.test(signed.dispatch.jobId)
      || !sha256.test(signed.dispatch.envelopeSha256)
      || !Number.isSafeInteger(signed.dispatch.dispatchRevision)
      || signed.dispatch.dispatchRevision < 1
      || !signingIdentifier.test(signed.dispatch.assignedWorkloadId)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || !Number.isFinite(expiresAt.getTime())
      || expiresAt.toISOString() !== signed.dispatch.expiresAt
      || expiresAt <= issuedAt
      || expiresAt.getTime() > issuedAt.getTime() + 900_000
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000
      || expiresAt.getTime() <= now
      || !ed25519Signature.test(signed.signature)) {
      throw new PlatformDataError("invalid-artifact", "The signed scheduler dispatch is malformed or stale.");
    }
  }

  #validateSignedLaunchAttestation(signed: SignedResearchJobLaunchAttestation): void {
    if (typeof signed !== "object" || signed === null
      || typeof signed.launch !== "object" || signed.launch === null) {
      throw new PlatformDataError("invalid-artifact", "A signed launch attestation is required.");
    }
    const issuedAt = new Date(signed.issuedAt);
    const now = this.#now().getTime();
    const launch = signed.launch;
    if (signed.schemaVersion !== "research-job-launch-attestation-signature-v1"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.providerWorkloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !opaque.test(launch.launchId)
      || !opaque.test(launch.jobId)
      || !sha256.test(launch.envelopeSha256)
      || !opaque.test(launch.dispatchId)
      || !Number.isSafeInteger(launch.dispatchRevision)
      || launch.dispatchRevision < 1
      || !signingIdentifier.test(launch.assignedWorkloadId)
      || !imageDigest.test(launch.runnerImageDigest)
      || !sha256.test(launch.processReferenceSha256)
      || !sha256.test(launch.executionIdentitySha256)
      || !sha256.test(launch.networkPolicySha256)
      || !ed25519Signature.test(signed.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000) {
      throw new PlatformDataError("invalid-artifact", "The signed launch attestation is malformed or stale.");
    }
  }

  #validateSignedExternalTermination(
    signed: SignedResearchJobExternalTerminationAttestation,
  ): void {
    if (typeof signed !== "object" || signed === null
      || typeof signed.termination !== "object" || signed.termination === null) {
      throw new PlatformDataError("invalid-artifact", "A signed external termination attestation is required.");
    }
    const issuedAt = new Date(signed.issuedAt);
    const now = this.#now().getTime();
    const termination = signed.termination;
    if (signed.schemaVersion !== "research-job-external-termination-signature-v1"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.providerWorkloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !opaque.test(termination.terminationAttestationId)
      || !opaque.test(termination.jobId)
      || !opaque.test(termination.claimId)
      || !sha256.test(termination.envelopeSha256)
      || !opaque.test(termination.launchId)
      || !opaque.test(termination.dispatchId)
      || !Number.isSafeInteger(termination.dispatchRevision)
      || termination.dispatchRevision < 1
      || !signingIdentifier.test(termination.assignedWorkloadId)
      || !Number.isSafeInteger(termination.cancellationRevision)
      || termination.cancellationRevision < 1
      || !Number.isSafeInteger(termination.cancellationSequenceId)
      || termination.cancellationSequenceId < 1
      || !(["operator", "input-quarantined", "provider-drift"] as const)
        .includes(termination.cancellationSource)
      || !(["operator-stop", "incident", "provider-drift", "input-quarantined"] as const)
        .includes(termination.cancellationReason)
      || termination.outcome !== "process-stopped"
      || !sha256.test(termination.processReferenceSha256)
      || !sha256.test(termination.terminationEvidenceSha256)
      || !ed25519Signature.test(signed.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000) {
      throw new PlatformDataError("invalid-artifact", "The signed external termination attestation is malformed or stale.");
    }
  }

  #validateSignedAlertDelivery(
    signed: SignedResearchJobAlertDeliveryAttestation,
  ): void {
    if (typeof signed !== "object" || signed === null
      || typeof signed.delivery !== "object" || signed.delivery === null) {
      throw new PlatformDataError("invalid-artifact", "A signed alert delivery attestation is required.");
    }
    const issuedAt = new Date(signed.issuedAt);
    const generatedAt = new Date(signed.delivery.snapshotGeneratedAt);
    const now = this.#now().getTime();
    const delivery = signed.delivery;
    if (signed.schemaVersion !== "research-job-alert-delivery-signature-v1"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.alertDeliveryWorkloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !opaque.test(delivery.deliveryId)
      || !opaque.test(delivery.snapshotId)
      || !opaque.test(delivery.jobId)
      || !opaque.test(delivery.claimId)
      || !(["overdue", "cancellation-pending", "cancellation-observed"] as const)
        .includes(delivery.snapshotStatus)
      || !Number.isSafeInteger(delivery.cancellationRevision)
      || delivery.cancellationRevision < 0
      || !sha256.test(delivery.snapshotPayloadSha256)
      || !sha256.test(delivery.channelReferenceSha256)
      || !sha256.test(delivery.deliveryReceiptSha256)
      || delivery.outcome !== "delivered"
      || !ed25519Signature.test(signed.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || !Number.isFinite(generatedAt.getTime())
      || generatedAt.toISOString() !== delivery.snapshotGeneratedAt
      || issuedAt < generatedAt
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000) {
      throw new PlatformDataError("invalid-artifact", "The signed alert delivery attestation is malformed or stale.");
    }
  }

  #validateSignedTerminal(signed: SignedResearchJobTerminalAttestation): void {
    if (typeof signed !== "object" || signed === null
      || typeof signed.terminal !== "object" || signed.terminal === null) {
      throw new PlatformDataError("invalid-artifact", "A signed workload terminal attestation is required.");
    }
    const issuedAt = new Date(signed.issuedAt);
    const now = this.#now().getTime();
    if (signed.schemaVersion !== "research-job-terminal-signature-v1"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.workloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !ed25519Signature.test(signed.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000) {
      throw new PlatformDataError("invalid-artifact", "The signed workload terminal is malformed or stale.");
    }
  }

  #validateSignedCancellationAcknowledgement(
    signed: SignedResearchJobCancellationAcknowledgement,
  ): void {
    if (typeof signed !== "object" || signed === null
      || typeof signed.acknowledgement !== "object" || signed.acknowledgement === null) {
      throw new PlatformDataError("invalid-artifact", "A signed cancellation acknowledgement is required.");
    }
    const acknowledgement = signed.acknowledgement;
    const issuedAt = new Date(signed.issuedAt);
    const now = this.#now().getTime();
    const outcomeShape = acknowledgement.terminationOutcome === "not-started"
      ? acknowledgement.processReferenceSha256 === undefined
      : acknowledgement.terminationOutcome === "process-stopped"
        && acknowledgement.processReferenceSha256 !== undefined
        && sha256.test(acknowledgement.processReferenceSha256);
    if (signed.schemaVersion !== "research-job-cancellation-acknowledgement-signature-v1"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.workloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !opaque.test(acknowledgement.jobId)
      || !opaque.test(acknowledgement.claimId)
      || !Number.isSafeInteger(acknowledgement.cancellationSequenceId)
      || acknowledgement.cancellationSequenceId < 1
      || !Number.isSafeInteger(acknowledgement.cancellationRevision)
      || acknowledgement.cancellationRevision < 1
      || !["operator", "input-quarantined", "provider-drift"].includes(
        acknowledgement.cancellationSource,
      )
      || !["operator-stop", "incident", "provider-drift", "input-quarantined"].includes(
        acknowledgement.cancellationReason,
      )
      || !outcomeShape
      || !sha256.test(acknowledgement.terminationEvidenceSha256)
      || !ed25519Signature.test(signed.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000) {
      throw new PlatformDataError("invalid-artifact", "The signed cancellation acknowledgement is malformed or stale.");
    }
  }

  #validateSignedHeartbeat(signed: SignedResearchJobHeartbeat): void {
    if (typeof signed !== "object" || signed === null
      || typeof signed.heartbeat !== "object" || signed.heartbeat === null) {
      throw new PlatformDataError("invalid-artifact", "A signed workload heartbeat is required.");
    }
    const heartbeat = signed.heartbeat;
    const issuedAt = new Date(signed.issuedAt);
    const now = this.#now().getTime();
    const stateShape = heartbeat.runnerState === "running"
      ? heartbeat.cancellationRevision === 0
      : heartbeat.runnerState === "cancellation-observed"
        && Number.isSafeInteger(heartbeat.cancellationRevision)
        && heartbeat.cancellationRevision > 0;
    if (signed.schemaVersion !== "research-job-heartbeat-signature-v1"
      || signed.algorithm !== "Ed25519"
      || !opaque.test(signed.tenantId)
      || !signingIdentifier.test(signed.workloadId)
      || !signingIdentifier.test(signed.signingKeyId)
      || !opaque.test(heartbeat.heartbeatId)
      || !opaque.test(heartbeat.jobId)
      || !opaque.test(heartbeat.claimId)
      || !Number.isSafeInteger(heartbeat.heartbeatSequence)
      || heartbeat.heartbeatSequence < 1
      || !stateShape
      || !sha256.test(heartbeat.processReferenceSha256)
      || !sha256.test(heartbeat.livenessEvidenceSha256)
      || !ed25519Signature.test(signed.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== signed.issuedAt
      || issuedAt.getTime() < now - 300_000
      || issuedAt.getTime() > now + 60_000) {
      throw new PlatformDataError("invalid-artifact", "The signed workload heartbeat is malformed or stale.");
    }
  }

  #validateTerminalInput(input: ResearchJobTerminalInput): void {
    if (!opaque.test(input.jobId) || !opaque.test(input.claimId)) {
      throw new PlatformDataError("invalid-identifier", "Job and claim identifiers must be opaque tokens.");
    }
    if (input.status === "succeeded") {
      const checkedAt = new Date(input.providerCheckedAt);
      const now = this.#now().getTime();
      if (!sha256.test(input.outputSha256) || !opaque.test(input.bindingId)
        || !providerIdentifier.test(input.providerId)
        || !sha256.test(input.objectReferenceSha256)
        || !objectVersion.test(input.providerObjectVersion)
        || !receiptReference.test(input.providerReceiptReference)
        || !sha256.test(input.providerReceiptSha256)
        || !Number.isFinite(checkedAt.getTime())
        || checkedAt.toISOString() !== input.providerCheckedAt
        || checkedAt.getTime() < now - 900_000
        || checkedAt.getTime() > now + 60_000) {
        throw new PlatformDataError(
          "invalid-artifact",
          "Successful terminal evidence requires fresh digest-exact managed-output provenance.",
        );
      }
      return;
    }
    if (!sha256.test(input.failureDetailSha256)
      || (input.status === "failed"
        && !(["runner-failed", "output-validation-failed"] as const).includes(input.failureCode))
      || (input.status === "cancelled" && input.failureCode !== "cancellation-observed")) {
      throw new PlatformDataError("invalid-artifact", "Terminal failure evidence is invalid.");
    }
    if (input.status === "cancelled"
      && (!opaque.test(input.cancellationAcknowledgementId)
        || !Number.isSafeInteger(input.cancellationRevision)
        || input.cancellationRevision < 1)) {
      throw new PlatformDataError(
        "invalid-artifact",
        "Cancelled terminal evidence must bind a current cancellation acknowledgement.",
      );
    }
  }
}
