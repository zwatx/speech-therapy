export type MembershipRole = "owner" | "clinician" | "reviewer" | "support";

export interface ActorContext {
  readonly actorId: string;
  readonly tenantId: string;
  readonly role: MembershipRole;
}

export type AssentStatus =
  | "not-applicable"
  | "affirmed"
  | "declined"
  | "withdrawn";

export interface ConsentSnapshotInput {
  readonly learnerId: string;
  readonly noticeVersion: string;
  readonly audioProcessing: boolean;
  readonly videoProcessing: boolean;
  readonly clinicianReview: boolean;
  readonly researchUse: boolean;
  readonly assentStatus: AssentStatus;
}

export interface ConsentSnapshotRecord extends ConsentSnapshotInput {
  readonly id: string;
  readonly tenantId: string;
  readonly version: number;
  readonly capturedByActorId: string;
  readonly capturedAt: string;
  readonly supersedesSnapshotId?: string;
}

export interface LearnerConsentSummary {
  readonly id: string;
  readonly version: number;
  readonly noticeVersion: string;
  readonly audioProcessing: boolean;
  readonly videoProcessing: boolean;
  readonly clinicianReview: boolean;
  readonly researchUse: boolean;
  readonly assentStatus: AssentStatus;
  readonly capturedAt: string;
}

export interface LearnerRecord {
  readonly id: string;
  readonly displayLabel: string;
  readonly createdAt: string;
}

export interface LearnerSummary extends LearnerRecord {
  readonly latestConsent?: LearnerConsentSummary;
  readonly attemptCount: number;
  readonly lastPracticeAt?: string;
  readonly activeDeviceSessionCount: number;
}

export interface LearnerAttemptSummary {
  readonly attemptId: string;
  readonly exerciseId: string;
  readonly protocolId: string;
  readonly prompt?: string;
  readonly targetLabel?: string;
  readonly status: PracticeAttemptStatus;
  readonly durationMilliseconds: number;
  readonly reasonCodes: PracticeAttemptInput["reasonCodes"];
  readonly receivedAt: string;
  readonly benchmarkStatus?: "scored-ambiguous" | "unavailable";
}

export interface ReviewAttemptSummary extends LearnerAttemptSummary {
  readonly learnerId: string;
  readonly learnerDisplayLabel: string;
  readonly consentSnapshotId: string;
  readonly consentVersion: number;
  readonly assignmentId: string;
  readonly prompt: string;
  readonly targetLabel: string;
  readonly repetitionIndex: number;
  readonly retryIndex: number;
}

export interface LearnerDetail extends LearnerSummary {
  readonly consentSnapshots: readonly LearnerConsentSummary[];
  readonly recentAttempts: readonly LearnerAttemptSummary[];
}

export interface PracticeAssignmentInput {
  readonly learnerId: string;
  readonly exerciseId: string;
  readonly attemptTarget: number;
  readonly retryLimit: number;
}

export interface PracticeAssignmentRecord {
  readonly id: string;
  readonly tenantId: string;
  readonly learnerId: string;
  readonly version: number;
  readonly consentSnapshotId: string;
  readonly exerciseRegistryVersion: string;
  readonly exerciseDefinitionSha256: string;
  readonly exerciseId: string;
  readonly protocolId: string;
  readonly prompt: string;
  readonly targetLabel: string;
  readonly attemptTarget: number;
  readonly retryLimit: number;
  readonly visualProcessing: false;
  readonly releasePosture: "candidate-silent-only";
  readonly assignedByActorId: string;
  readonly assignedAt: string;
  readonly supersedesAssignmentId?: string;
}

export interface PracticeAssignmentSummary extends PracticeAssignmentRecord {
  readonly learnerDisplayLabel: string;
}

export type PracticeAssignmentProgress =
  | {
      readonly status: "ready";
      readonly acceptedRepetitions: number;
      readonly repetitionIndex: number;
      readonly retryIndex: number;
    }
  | {
      readonly status: "retry-limit-reached";
      readonly acceptedRepetitions: number;
      readonly repetitionIndex: number;
    }
  | {
      readonly status: "completed";
      readonly acceptedRepetitions: number;
    };

export interface ActivePracticeAssignment extends PracticeAssignmentRecord {
  readonly progress: PracticeAssignmentProgress;
}

export interface LearnerExport {
  readonly requestId: string;
  readonly learner: {
    readonly id: string;
    readonly displayLabel: string;
    readonly createdAt: string;
    readonly deletedAt?: string;
  };
  readonly consentSnapshots: readonly ConsentSnapshotRecord[];
  readonly practiceAssignments: readonly PracticeAssignmentRecord[];
  readonly practiceAttempts: readonly PracticeAttemptExportRecord[];
  readonly practiceAttemptAnalyses: readonly PracticeAttemptAnalysisExportRecord[];
  readonly researchArtifactImpacts: readonly ResearchArtifactImpactExportRecord[];
}

export interface ResearchArtifactImpactExportRecord {
  readonly artifactId: string;
  readonly kind: ArtifactKind;
  readonly version: string;
  readonly status: ArtifactRecord["status"];
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly consentSnapshotIds: readonly string[];
  readonly processingPurposes: readonly ArtifactProcessingPurpose[];
  readonly subjectQuarantineEvents: readonly ResearchArtifactQuarantineEventExportRecord[];
}

export interface ResearchArtifactQuarantineEventExportRecord {
  readonly reason: "consent-superseded" | "learner-deleted" | "ancestor-quarantined";
  readonly occurredAt: string;
  readonly actions: readonly ResearchArtifactActionExportRecord[];
}

export interface ResearchArtifactActionExportRecord {
  readonly actionType: ArtifactQuarantineActionType;
  readonly status: "pending" | "processing" | "succeeded" | "dead-letter";
  readonly attemptCount: number;
  readonly receiptRecorded: boolean;
  readonly completedAt?: string;
  readonly lastErrorCode?: ArtifactQuarantineActionFailureCode;
}

export interface PracticeAttemptExportRecord {
  readonly attemptId: string;
  readonly assignmentId?: string;
  readonly repetitionIndex?: number;
  readonly retryIndex?: number;
  readonly deviceSessionId: string;
  readonly consentSnapshotId: string;
  readonly exerciseId: string;
  readonly protocolId: string;
  readonly status: PracticeAttemptStatus;
  readonly durationMilliseconds: number;
  readonly sampleRateHertz: 16_000;
  readonly rmsDbfs: number;
  readonly peakAmplitude: number;
  readonly reasonCodes: PracticeAttemptInput["reasonCodes"];
  readonly mediaRetained: false;
  readonly receivedAt: string;
}

export interface DeletionReceipt {
  readonly requestId: string;
  readonly learnerId: string;
  readonly deletedAt: string;
  readonly retainedRecords: readonly [
    "consent-snapshots",
    "practice-assignments",
    "audit-events",
    "artifact-lineage",
    "quarantine-evidence",
  ];
}

export interface LearnerDeviceSessionReceipt {
  readonly id: string;
  readonly learnerId: string;
  readonly token: string;
  readonly expiresAt: string;
  readonly consentSnapshotId: string;
}

export type LearnerDeviceSessionStatus =
  | "active"
  | "expired"
  | "revoked"
  | "inactive"
  | "consent-invalidated";

export interface LearnerDeviceSessionSummary {
  readonly id: string;
  readonly learnerId: string;
  readonly consentSnapshotId: string;
  readonly consentVersion: number;
  readonly createdAt: string;
  readonly expiresAt: string;
  readonly status: LearnerDeviceSessionStatus;
  readonly revokedAt?: string;
}

export interface LearnerDeviceSessionRevocationReceipt {
  readonly id: string;
  readonly learnerId: string;
  readonly revokedAt: string;
  readonly alreadyRevoked: boolean;
}

export interface LearnerDeviceSessionRotationReceipt
  extends LearnerDeviceSessionReceipt {
  readonly rotatedFromSessionId: string;
  readonly rotatedAt: string;
}

export interface LearnerDeviceContext {
  readonly sessionId: string;
  readonly tenantId: string;
  readonly learnerId: string;
  readonly consentSnapshotId: string;
  readonly audioProcessing: true;
  readonly videoProcessing: boolean;
  readonly clinicianReview: boolean;
  readonly researchUse: boolean;
}

export type LearnerDeviceRequestOperation =
  | "assignment-read"
  | "attempt-upload";

export type PracticeAttemptStatus = "accepted-silent" | "retry-capture";

export interface PracticeAttemptInput {
  readonly attemptId: string;
  readonly assignmentId: string;
  readonly repetitionIndex: number;
  readonly retryIndex: number;
  readonly exerciseId: string;
  readonly protocolId: string;
  readonly status: PracticeAttemptStatus;
  readonly durationMilliseconds: number;
  readonly sampleRateHertz: 16_000;
  readonly rmsDbfs: number;
  readonly peakAmplitude: number;
  readonly reasonCodes: readonly (
    | "audio-clipping"
    | "audio-too-quiet"
    | "utterance-too-short"
    | "utterance-too-long"
    | "background-noise"
    | "multiple-speakers"
  )[];
}

export interface PracticeAttemptReceipt {
  readonly attemptId: string;
  readonly status: PracticeAttemptStatus;
  readonly feedbackAvailable: false;
  readonly mediaRetained: false;
  readonly reasonCodes: PracticeAttemptInput["reasonCodes"];
}

interface PracticeAttemptAnalysisBase {
  readonly attemptId: string;
  readonly releasePosture: "benchmark-only";
  readonly learnerFeedbackEligible: false;
  readonly checkpointId: string;
  readonly checkpointRevision: string;
  readonly runtime: string;
  readonly modelFileSha256: string;
  readonly vocabularyFileSha256: string;
  readonly lexiconVersion: string;
  readonly calibrationVersion: string;
  readonly scoringPolicyVersion: string;
  readonly inferenceMilliseconds: number;
}

export type PracticeAttemptAnalysisInput =
  | (PracticeAttemptAnalysisBase & {
      readonly status: "scored-ambiguous";
      readonly pCorrect: number;
      readonly pError: number;
      readonly hypothesisCoverage: number;
      readonly calibrated: false;
      readonly ambiguous: true;
      readonly failureCode?: never;
    })
  | (PracticeAttemptAnalysisBase & {
      readonly status: "unavailable";
      readonly pCorrect?: never;
      readonly pError?: never;
      readonly hypothesisCoverage?: never;
      readonly calibrated?: never;
      readonly ambiguous?: never;
      readonly failureCode: "benchmark-unavailable";
    });

export type PracticeAttemptAnalysisExportRecord = PracticeAttemptAnalysisInput & {
  readonly receivedAt: string;
};

export type ArtifactKind =
  | "dataset"
  | "feature-cache"
  | "checkpoint"
  | "calibration"
  | "evaluation-report"
  | "deployment";

export type ArtifactProcessingPurpose = "audio-research" | "visual-research";

export interface ArtifactConsentDependency {
  readonly learnerId: string;
  readonly consentSnapshotId: string;
  readonly processingPurpose: ArtifactProcessingPurpose;
}

interface ArtifactRegistrationBase {
  readonly artifactId: string;
  readonly version: string;
  readonly sha256: string;
}

export interface DatasetArtifactRegistration extends ArtifactRegistrationBase {
  readonly kind: "dataset";
  readonly dependencies: readonly ArtifactConsentDependency[];
}

export interface DerivedArtifactRegistration extends ArtifactRegistrationBase {
  readonly kind: Exclude<ArtifactKind, "dataset">;
  readonly parentArtifactIds: readonly string[];
}

export interface ArtifactRecord {
  readonly id: string;
  readonly tenantId: string;
  readonly kind: ArtifactKind;
  readonly version: string;
  readonly sha256: string;
  readonly status: "active" | "quarantined" | "retired";
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly createdAt: string;
  readonly dependencyCount: number;
  readonly quarantinedAt?: string;
  readonly quarantineReason?:
    | "consent-superseded"
    | "learner-deleted"
    | "ancestor-quarantined";
}

export interface ArtifactUseAuthorization {
  readonly authorizationId: string;
  readonly authorizedAt: string;
  readonly artifact: ArtifactRecord;
}

export type ArtifactQuarantineActionType =
  | "revoke-artifact-access"
  | "purge-subject-data"
  | "purge-feature-cache"
  | "disable-deployment"
  | "schedule-retraining"
  | "schedule-reevaluation";

export type ArtifactQuarantineActionFailureCode =
  | "external-unavailable"
  | "verification-failed"
  | "permanent-rejection";

export interface ArtifactQuarantineActionClaim {
  readonly actionId: string;
  readonly tenantId: string;
  readonly artifactId: string;
  readonly artifactKind: ArtifactKind;
  readonly artifactSha256: string;
  readonly sourceLearnerId: string;
  readonly actionType: ArtifactQuarantineActionType;
  readonly quarantineReason: NonNullable<ArtifactRecord["quarantineReason"]>;
  readonly idempotencyKey: string;
  readonly attemptNumber: number;
  readonly leaseToken: string;
  readonly leaseExpiresAt: string;
}

export interface ArtifactQuarantineActionReceipt {
  readonly actionId: string;
  readonly idempotencyKey: string;
  readonly artifactSha256: string;
  readonly actionType: ArtifactQuarantineActionType;
  readonly receiptReference: string;
  readonly receiptSha256: string;
  readonly outcome: "performed" | "already-satisfied";
  readonly verification?: ArtifactQuarantineReceiptVerification;
}

export interface ArtifactQuarantineReceiptVerification {
  readonly providerId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly signatureSha256: string;
}

export interface SignedArtifactQuarantineActionReceipt
  extends Omit<ArtifactQuarantineActionReceipt, "verification"> {
  readonly signatureEnvelope: {
    readonly schemaVersion: "artifact-quarantine-receipt-signature-v1";
    readonly providerId: string;
    readonly signingKeyId: string;
    readonly algorithm: "Ed25519";
    readonly issuedAt: string;
    readonly signature: string;
  };
}

export interface ArtifactReceiptSigningKeyRegistration {
  readonly providerId: string;
  readonly signingKeyId: string;
  readonly publicKeyPem: string;
  readonly validFrom: string;
  readonly validUntil: string;
}

export interface ArtifactReceiptSigningKeyRecord {
  readonly providerId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly publicKeySha256: string;
  readonly validFrom: string;
  readonly validUntil: string;
  readonly registeredAt: string;
  readonly status: "scheduled" | "active" | "expired" | "revoked";
  readonly revokedAt?: string;
  readonly revocationReason?: "rotated" | "compromised" | "provider-disabled";
}

export type ArtifactReceiptSigningKeyRevocationReason =
  | "rotated"
  | "compromised"
  | "provider-disabled";

export interface ManagedArtifactObjectRegistration {
  readonly bindingId: string;
  readonly artifactId: string;
  readonly providerId: string;
  readonly objectReferenceSha256: string;
  readonly providerObjectVersion: string;
}

export interface ManagedArtifactObjectRecord {
  readonly bindingId: string;
  readonly artifactId: string;
  readonly artifactKind: ArtifactKind;
  readonly artifactStatus: ArtifactRecord["status"];
  readonly providerId: string;
  readonly objectReferenceSha256: string;
  readonly providerObjectVersion: string;
  readonly expectedSha256: string;
  readonly registeredAt: string;
}

export interface ManagedArtifactObjectInspectionClaim {
  readonly bindingId: string;
  readonly providerId: string;
  readonly objectReferenceSha256: string;
  readonly providerObjectVersion: string;
  readonly expectedSha256: string;
}

export interface ManagedArtifactObjectObservationReceipt {
  readonly bindingId: string;
  readonly providerId: string;
  readonly objectReferenceSha256: string;
  readonly objectExists: boolean;
  readonly observedSha256?: string;
  readonly accessState: "available" | "revoked" | "unavailable";
  readonly checkedAt: string;
  readonly receiptReference: string;
  readonly receiptSha256: string;
}

export interface ManagedArtifactObjectReconciliationRecord {
  readonly observationId: string;
  readonly bindingId: string;
  readonly artifactId: string;
  readonly artifactStatus: ArtifactRecord["status"];
  readonly objectExists: boolean;
  readonly observedSha256?: string;
  readonly accessState: ManagedArtifactObjectObservationReceipt["accessState"];
  readonly outcome: "consistent" | "missing" | "digest-mismatch" | "access-mismatch";
  readonly checkedAt: string;
  readonly recordedAt: string;
  readonly evidencePosture: "local-foundation";
  readonly productionGateEligible: false;
}

export type ResearchJobType =
  | "dataset-export"
  | "feature-extraction"
  | "training"
  | "calibration"
  | "evaluation"
  | "shadow-evaluation";

export type ResearchJobOutputKind =
  | "managed-dataset-export"
  | "feature-cache"
  | "checkpoint"
  | "calibration"
  | "evaluation-report";

export interface ResearchJobRequestInput {
  readonly jobId: string;
  readonly jobType: ResearchJobType;
  readonly inputs: readonly {
    readonly artifactId: string;
    readonly bindingId: string;
  }[];
  readonly outputKind: ResearchJobOutputKind;
  readonly outputId: string;
  readonly outputVersion: string;
  readonly codeRevision: string;
  readonly configurationSha256: string;
  readonly runnerImageDigest: string;
  readonly intendedUse: string;
  readonly exclusions: readonly string[];
  readonly expiresAt: string;
}

export interface ResearchJobAuthorizationEnvelope {
  readonly schemaVersion: "research-job-authorization-v1";
  readonly jobId: string;
  readonly jobType: ResearchJobType;
  readonly inputs: readonly {
    readonly artifactId: string;
    readonly artifactKind: ArtifactKind;
    readonly artifactSha256: string;
    readonly bindingId: string;
    readonly providerId: string;
    readonly objectReferenceSha256: string;
    readonly providerObjectVersion: string;
  }[];
  readonly outputKind: ResearchJobOutputKind;
  readonly outputId: string;
  readonly outputVersion: string;
  readonly codeRevision: string;
  readonly configurationSha256: string;
  readonly runnerImageDigest: string;
  readonly intendedUse: string;
  readonly exclusions: readonly string[];
  readonly requestedByActorId: string;
  readonly requestedAt: string;
  readonly expiresAt: string;
  readonly approvedByActorId?: string;
  readonly approvedAt?: string;
  readonly envelopeSha256?: string;
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly approvalPosture: "pending" | "database-attested";
  readonly cryptographicSignaturePresent: false;
  readonly productionGateEligible: false;
}

export type ResearchJobCancellationReason =
  | "operator-stop"
  | "incident"
  | "provider-drift"
  | "input-quarantined";

export type ResearchWorkloadRevocationReason = "rotated" | "compromised" | "disabled";

export interface ResearchWorkloadIdentityRecord {
  readonly workloadId: string;
  readonly purpose:
    | "research-job-runner"
    | "research-job-scheduler"
    | "research-job-provider"
    | "research-job-alert-delivery";
  readonly registeredAt: string;
  readonly status: "active" | "revoked";
  readonly revokedAt?: string;
  readonly revocationReason?: ResearchWorkloadRevocationReason;
}

export interface ResearchWorkloadSigningKeyRegistration {
  readonly workloadId: string;
  readonly signingKeyId: string;
  readonly publicKeyPem: string;
  readonly validFrom: string;
  readonly validUntil: string;
}

export interface ResearchWorkloadSigningKeyRecord {
  readonly workloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly publicKeySha256: string;
  readonly validFrom: string;
  readonly validUntil: string;
  readonly registeredAt: string;
  readonly status: "scheduled" | "active" | "expired" | "revoked" | "identity-revoked";
  readonly revokedAt?: string;
  readonly revocationReason?: ResearchWorkloadRevocationReason;
}

export interface SignedResearchJobExecutionClaim {
  readonly schemaVersion: "research-job-execution-claim-signature-v2";
  readonly tenantId: string;
  readonly workloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly claimId: string;
  readonly jobId: string;
  readonly envelopeSha256: string;
  readonly dispatchId: string;
  readonly dispatchRevision: number;
  readonly signature: string;
}

export interface SignedResearchJobDispatch {
  readonly schemaVersion: "research-job-dispatch-signature-v1";
  readonly tenantId: string;
  readonly schedulerWorkloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly dispatch: {
    readonly dispatchId: string;
    readonly jobId: string;
    readonly envelopeSha256: string;
    readonly dispatchRevision: number;
    readonly assignedWorkloadId: string;
    readonly expiresAt: string;
  };
  readonly signature: string;
}

export interface ResearchJobDispatchReceipt {
  readonly dispatchId: string;
  readonly jobId: string;
  readonly envelopeSha256: string;
  readonly dispatchRevision: number;
  readonly assignedWorkloadId: string;
  readonly expiresAt: string;
  readonly dispatchedByWorkloadId: string;
  readonly signingKeyId: string;
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly payloadSha256: string;
  readonly signatureSha256: string;
  readonly recordedAt: string;
  readonly evidencePosture: "workload-attested";
  readonly externalSchedulerLaunchVerified: false;
  readonly productionGateEligible: false;
}

export interface SignedResearchJobLaunchAttestation {
  readonly schemaVersion: "research-job-launch-attestation-signature-v1";
  readonly tenantId: string;
  readonly providerWorkloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly launch: {
    readonly launchId: string;
    readonly jobId: string;
    readonly envelopeSha256: string;
    readonly dispatchId: string;
    readonly dispatchRevision: number;
    readonly assignedWorkloadId: string;
    readonly runnerImageDigest: string;
    readonly processReferenceSha256: string;
    readonly executionIdentitySha256: string;
    readonly networkPolicySha256: string;
  };
  readonly signature: string;
}

export interface ResearchJobLaunchReceipt {
  readonly launchId: string;
  readonly jobId: string;
  readonly envelopeSha256: string;
  readonly dispatchId: string;
  readonly dispatchRevision: number;
  readonly assignedWorkloadId: string;
  readonly runnerImageDigest: string;
  readonly processReferenceSha256: string;
  readonly executionIdentitySha256: string;
  readonly networkPolicySha256: string;
  readonly attestedByProviderWorkloadId: string;
  readonly signingKeyId: string;
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly payloadSha256: string;
  readonly signatureSha256: string;
  readonly recordedAt: string;
  readonly launchAttestationVerified: true;
  readonly externalProviderKeyCustodyVerified: false;
  readonly productionGateEligible: false;
}

export interface SignedResearchJobExternalTerminationAttestation {
  readonly schemaVersion: "research-job-external-termination-signature-v1";
  readonly tenantId: string;
  readonly providerWorkloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly termination: {
    readonly terminationAttestationId: string;
    readonly jobId: string;
    readonly claimId: string;
    readonly envelopeSha256: string;
    readonly launchId: string;
    readonly dispatchId: string;
    readonly dispatchRevision: number;
    readonly assignedWorkloadId: string;
    readonly cancellationRevision: number;
    readonly cancellationSequenceId: number;
    readonly cancellationSource: "operator" | "input-quarantined" | "provider-drift";
    readonly cancellationReason: ResearchJobCancellationReason;
    readonly outcome: "process-stopped";
    readonly processReferenceSha256: string;
    readonly terminationEvidenceSha256: string;
  };
  readonly signature: string;
}

export interface ResearchJobExternalTerminationReceipt {
  readonly terminationAttestationId: string;
  readonly jobId: string;
  readonly claimId: string;
  readonly envelopeSha256: string;
  readonly launchId: string;
  readonly dispatchId: string;
  readonly dispatchRevision: number;
  readonly assignedWorkloadId: string;
  readonly cancellationRevision: number;
  readonly cancellationSequenceId: number;
  readonly cancellationSource: "operator" | "input-quarantined" | "provider-drift";
  readonly cancellationReason: ResearchJobCancellationReason;
  readonly outcome: "process-stopped";
  readonly processReferenceSha256: string;
  readonly terminationEvidenceSha256: string;
  readonly attestedByProviderWorkloadId: string;
  readonly signingKeyId: string;
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly payloadSha256: string;
  readonly signatureSha256: string;
  readonly recordedAt: string;
  readonly externalTerminationAttestationVerified: true;
  readonly externalProviderKeyCustodyVerified: false;
  readonly productionGateEligible: false;
}

export interface SignedResearchJobAlertDeliveryAttestation {
  readonly schemaVersion: "research-job-alert-delivery-signature-v1";
  readonly tenantId: string;
  readonly alertDeliveryWorkloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly delivery: {
    readonly deliveryId: string;
    readonly snapshotId: string;
    readonly jobId: string;
    readonly claimId: string;
    readonly snapshotStatus: "overdue" | "cancellation-pending" | "cancellation-observed";
    readonly cancellationRevision: number;
    readonly snapshotGeneratedAt: string;
    readonly snapshotPayloadSha256: string;
    readonly channelReferenceSha256: string;
    readonly deliveryReceiptSha256: string;
    readonly outcome: "delivered";
  };
  readonly signature: string;
}

export interface ResearchJobAlertDeliveryReceipt {
  readonly deliveryId: string;
  readonly snapshotId: string;
  readonly jobId: string;
  readonly claimId: string;
  readonly snapshotStatus: "overdue" | "cancellation-pending" | "cancellation-observed";
  readonly cancellationRevision: number;
  readonly snapshotGeneratedAt: string;
  readonly snapshotPayloadSha256: string;
  readonly channelReferenceSha256: string;
  readonly deliveryReceiptSha256: string;
  readonly outcome: "delivered";
  readonly attestedByWorkloadId: string;
  readonly signingKeyId: string;
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly payloadSha256: string;
  readonly signatureSha256: string;
  readonly recordedAt: string;
  readonly authenticatedDeliveryAttestationVerified: true;
  readonly externalProviderKeyCustodyVerified: false;
  readonly productionGateEligible: false;
}

export interface ResearchJobExecutionClaim {
  readonly claimId: string;
  readonly jobId: string;
  readonly envelope: ResearchJobAuthorizationEnvelope;
  readonly envelopeSha256: string;
  readonly claimedByActorId?: string;
  readonly claimedByWorkloadId?: string;
  readonly claimedAt: string;
  readonly dispatchId: string;
  readonly dispatchRevision: number;
  readonly launchId: string;
  readonly leaseDurationSeconds: number;
  readonly leaseStartedAt: string;
  readonly leaseExpiresAt: string;
  readonly signatureVerification?: {
    readonly signingKeyId: string;
    readonly algorithm: "Ed25519";
    readonly publicKeySha256: string;
    readonly issuedAt: string;
    readonly payloadSha256: string;
    readonly signatureSha256: string;
  };
  readonly cancellationObservedAtClaim: false;
  readonly cancellationPollingRequired: true;
  readonly evidencePosture: "local-foundation";
  readonly productionGateEligible: false;
}

export interface ResearchJobExecutionState {
  readonly claimId: string;
  readonly jobId: string;
  readonly envelopeSha256: string;
  readonly claimedByActorId?: string;
  readonly claimedByWorkloadId?: string;
  readonly claimedAt: string;
  readonly dispatchId?: string;
  readonly dispatchRevision?: number;
  readonly launchId?: string;
  readonly leaseDurationSeconds: number;
  readonly leaseStartedAt: string;
  readonly leaseExpiresAt: string;
  readonly cancellationRequested: boolean;
  readonly cancellationSource?: "operator" | "input-quarantined" | "provider-drift";
  readonly cancellationReason?: ResearchJobCancellationReason;
  readonly cancelledAt?: string;
  readonly terminalStatus?: "succeeded" | "failed" | "cancelled";
  readonly terminalReceiptId?: string;
  readonly terminalRecordedAt?: string;
  readonly evidencePosture: "local-foundation";
  readonly productionGateEligible: false;
}

export interface ResearchJobLivenessSnapshot {
  readonly snapshotId: string;
  readonly jobId: string;
  readonly claimId: string;
  readonly status:
    | "awaiting-first-heartbeat"
    | "fresh"
    | "overdue"
    | "cancellation-pending"
    | "cancellation-observed"
    | "terminal";
  readonly leaseDurationSeconds: number;
  readonly leaseStartedAt: string;
  readonly leaseExpiresAt: string;
  readonly leaseExpired: boolean;
  readonly lastHeartbeatId?: string;
  readonly lastHeartbeatSequence: number;
  readonly lastHeartbeatState?: "running" | "cancellation-observed";
  readonly lastHeartbeatCancellationRevision?: number;
  readonly cancellationRevision: number;
  readonly terminalStatus?: "succeeded" | "failed" | "cancelled";
  readonly alertRequired: boolean;
  readonly generatedByActorId: string;
  readonly generatedAt: string;
  readonly externalProcessLivenessVerified: false;
  readonly alertDeliveryEvidencePresent: boolean;
  readonly evidencePosture: "local-foundation";
  readonly productionGateEligible: false;
}

export type ResearchJobTerminalInput =
  | {
      readonly jobId: string;
      readonly claimId: string;
      readonly status: "succeeded";
      readonly outputSha256: string;
      readonly bindingId: string;
      readonly providerId: string;
      readonly objectReferenceSha256: string;
      readonly providerObjectVersion: string;
      readonly providerCheckedAt: string;
      readonly providerReceiptReference: string;
      readonly providerReceiptSha256: string;
    }
  | {
      readonly jobId: string;
      readonly claimId: string;
      readonly status: "failed";
      readonly failureCode: "runner-failed" | "output-validation-failed";
      readonly failureDetailSha256: string;
    }
  | {
      readonly jobId: string;
      readonly claimId: string;
      readonly status: "cancelled";
      readonly failureCode: "cancellation-observed";
      readonly failureDetailSha256: string;
      readonly cancellationAcknowledgementId: string;
      readonly cancellationRevision: number;
    };

export interface SignedResearchJobTerminalAttestation {
  readonly schemaVersion: "research-job-terminal-signature-v1";
  readonly tenantId: string;
  readonly workloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly terminal: ResearchJobTerminalInput;
  readonly signature: string;
}

export interface SignedResearchJobCancellationAcknowledgement {
  readonly schemaVersion: "research-job-cancellation-acknowledgement-signature-v1";
  readonly tenantId: string;
  readonly workloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly acknowledgement: {
    readonly jobId: string;
    readonly claimId: string;
    readonly cancellationRevision: number;
    readonly cancellationSequenceId: number;
    readonly cancellationSource: "operator" | "input-quarantined" | "provider-drift";
    readonly cancellationReason: ResearchJobCancellationReason;
    readonly terminationOutcome: "not-started" | "process-stopped";
    readonly processReferenceSha256?: string;
    readonly terminationEvidenceSha256: string;
  };
  readonly signature: string;
}

export interface ResearchJobCancellationAcknowledgementReceipt {
  readonly acknowledgementId: string;
  readonly jobId: string;
  readonly claimId: string;
  readonly cancellationRevision: number;
  readonly cancellationSequenceId: number;
  readonly cancellationSource: "operator" | "input-quarantined" | "provider-drift";
  readonly cancellationReason: ResearchJobCancellationReason;
  readonly terminationOutcome: "not-started" | "process-stopped";
  readonly processReferenceSha256?: string;
  readonly terminationEvidenceSha256: string;
  readonly acknowledgedByWorkloadId: string;
  readonly signingKeyId: string;
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly payloadSha256: string;
  readonly signatureSha256: string;
  readonly recordedAt: string;
  readonly evidencePosture: "workload-attested";
  readonly independentlyVerifiedProcessTermination: false;
  readonly productionGateEligible: false;
}

export interface SignedResearchJobHeartbeat {
  readonly schemaVersion: "research-job-heartbeat-signature-v1";
  readonly tenantId: string;
  readonly workloadId: string;
  readonly signingKeyId: string;
  readonly algorithm: "Ed25519";
  readonly issuedAt: string;
  readonly heartbeat: {
    readonly heartbeatId: string;
    readonly jobId: string;
    readonly claimId: string;
    readonly heartbeatSequence: number;
    readonly runnerState: "running" | "cancellation-observed";
    readonly cancellationRevision: number;
    readonly processReferenceSha256: string;
    readonly livenessEvidenceSha256: string;
  };
  readonly signature: string;
}

export interface ResearchJobHeartbeatReceipt {
  readonly heartbeatId: string;
  readonly jobId: string;
  readonly claimId: string;
  readonly heartbeatSequence: number;
  readonly runnerState: "running" | "cancellation-observed";
  readonly cancellationRevision: number;
  readonly processReferenceSha256: string;
  readonly livenessEvidenceSha256: string;
  readonly reportedByWorkloadId: string;
  readonly signingKeyId: string;
  readonly publicKeySha256: string;
  readonly issuedAt: string;
  readonly payloadSha256: string;
  readonly signatureSha256: string;
  readonly recordedAt: string;
  readonly evidencePosture: "workload-attested";
  readonly independentlyVerifiedProcessLiveness: false;
  readonly productionGateEligible: false;
}

export interface ResearchJobTerminalReceipt {
  readonly receiptId: string;
  readonly jobId: string;
  readonly claimId: string;
  readonly envelopeSha256: string;
  readonly status: "succeeded" | "failed" | "cancelled";
  readonly terminalPayloadSha256: string;
  readonly outputArtifactId?: string;
  readonly outputBindingId?: string;
  readonly requestedOutputKind?: ResearchJobOutputKind;
  readonly outputArtifactKind?: Exclude<ArtifactKind, "deployment">;
  readonly outputVersion?: string;
  readonly outputSha256?: string;
  readonly failureCode?: "runner-failed" | "output-validation-failed" | "cancellation-observed";
  readonly failureDetailSha256?: string;
  readonly cancellationAcknowledgementId?: string;
  readonly cancellationRevision?: number;
  readonly externalTerminationAttestationId?: string;
  readonly completedByActorId?: string;
  readonly completedByWorkloadId?: string;
  readonly signatureVerification?: {
    readonly signingKeyId: string;
    readonly algorithm: "Ed25519";
    readonly publicKeySha256: string;
    readonly issuedAt: string;
    readonly payloadSha256: string;
    readonly signatureSha256: string;
  };
  readonly recordedAt: string;
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly evidencePosture: "local-foundation";
  readonly productionGateEligible: false;
}

export type ArtifactQuarantineRunResult =
  | { readonly status: "idle" }
  | {
      readonly status: "succeeded" | "retry-scheduled" | "dead-lettered";
      readonly actionId: string;
    };

export interface ArtifactQuarantineHealth {
  readonly generatedAt: string;
  readonly status: "healthy" | "attention" | "critical";
  readonly overdueAfterSeconds: number;
  readonly pendingCount: number;
  readonly processingCount: number;
  readonly succeededCount: number;
  readonly deadLetterCount: number;
  readonly expiredLeaseCount: number;
  readonly overdueReadyCount: number;
  readonly oldestReadySeconds: number | null;
  readonly countsByActionType: Readonly<Record<ArtifactQuarantineActionType, number>>;
}

export interface ArtifactQuarantineAlertEvidence {
  readonly schemaVersion: "artifact-quarantine-alert-evidence-v1";
  readonly evidencePosture: "local-foundation";
  readonly productionGateEligible: false;
  readonly generatedAt: string;
  readonly status: ArtifactQuarantineHealth["status"];
  readonly alertRequired: boolean;
  readonly reasons: readonly ("dead-letter" | "expired-lease" | "overdue-ready")[];
  readonly fingerprintSha256: string;
  readonly counts: {
    readonly deadLetters: number;
    readonly expiredLeases: number;
    readonly overdueReady: number;
  };
  readonly deliveryEvidencePresent: false;
  readonly missingProductionEvidence: readonly string[];
}

export interface DeletionDrillReport {
  readonly schemaVersion: "deletion-drill-report-v1";
  readonly evidencePosture: "local-foundation";
  readonly productionGateEligible: false;
  readonly requestId: string;
  readonly requestedAt: string;
  readonly completedAt: string;
  readonly completionTargetSeconds: number;
  readonly maximumCompletionSeconds: number | null;
  readonly counts: {
    readonly expectedArtifacts: number;
    readonly quarantinedArtifacts: number;
    readonly quarantineEvents: number;
    readonly expectedActions: number;
    readonly succeededActions: number;
    readonly unresolvedActions: number;
    readonly deadLetters: number;
    readonly unexpectedActions: number;
    readonly signedReceipts: number;
  };
  readonly checks: {
    readonly learnerDeleted: boolean;
    readonly transientClinicalDataPurged: boolean;
    readonly lineageFullyQuarantined: boolean;
    readonly requiredActionsSucceeded: boolean;
    readonly completionTargetMet: boolean;
  };
  readonly foundationChecksPassed: boolean;
  readonly missingProductionEvidence: readonly string[];
}
