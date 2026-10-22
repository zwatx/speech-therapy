import type {
  VisualCueAgreementReport,
  VisualCueLabel,
} from "./annotation-types.ts";

export const visualDatasetSplits = [
  "train",
  "calibration",
  "test",
  "prospective-test",
] as const;

export type VisualDatasetSplit = (typeof visualDatasetSplits)[number];

export interface VisualDatasetManifestItem {
  readonly itemID: string;
  readonly speakerHash: string;
  readonly householdHash: string;
  readonly siteHash: string;
  readonly deletionSubjectHash: string;
  readonly consentSnapshotHash: string;
  readonly consentNoticeVersion: string;
  readonly assentStatus: "affirmed" | "not-applicable";
  readonly videoProcessing: true;
  readonly clinicianReview: true;
  readonly researchUse: true;
  readonly split: VisualDatasetSplit;
  readonly hardwareIdentifier: string;
  readonly systemVersion: string;
  readonly capturedAt: string;
  readonly targetWindowVersion: string;
  readonly annotationRequired: true;
}

export interface LockedVisualDatasetManifest {
  readonly schemaVersion: "visual-dataset-manifest-v1";
  readonly version: string;
  readonly sha256: string;
  readonly lockedAt: string;
  readonly cueFamily: "bilabial-closure";
  readonly labelPolicyVersion: "bilabial-closure-observation-v1";
  readonly collectionProtocolVersion: string;
  readonly deletionLedgerSha256AtLock: string;
  readonly consentLedgerSha256AtLock: string;
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly rawMediaIncluded: false;
  readonly rawLandmarksIncluded: false;
  readonly items: readonly VisualDatasetManifestItem[];
}

export interface DeletionLineageSnapshot {
  readonly schemaVersion: "deletion-lineage-snapshot-v1";
  readonly version: string;
  readonly sha256: string;
  readonly asOf: string;
  readonly revokedSubjectHashes: readonly string[];
}

export interface ConsentEligibilityEntry {
  readonly consentSnapshotHash: string;
  readonly deletionSubjectHash: string;
  readonly consentNoticeVersion: string;
  readonly assentStatus: "affirmed" | "not-applicable";
  readonly videoProcessing: true;
  readonly clinicianReview: true;
  readonly researchUse: true;
  readonly capturedAt: string;
}

export interface ConsentEligibilitySnapshot {
  readonly schemaVersion: "consent-eligibility-snapshot-v1";
  readonly version: string;
  readonly sha256: string;
  readonly asOf: string;
  readonly entries: readonly ConsentEligibilityEntry[];
}

export interface VisualDatasetAnnotationIndexItem {
  readonly itemID: string;
  readonly annotationBundleSha256: string;
  readonly finalLabel: VisualCueLabel;
}

export interface VisualDatasetAnnotationIndex {
  readonly schemaVersion: "visual-dataset-annotation-index-v1";
  readonly manifestSha256: string;
  readonly deletionLedgerSha256: string;
  readonly consentLedgerSha256: string;
  readonly authorizedAt: string;
  readonly labelPolicyVersion: "bilabial-closure-observation-v1";
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly sha256: string;
  readonly items: readonly VisualDatasetAnnotationIndexItem[];
}

export interface VisualDatasetAgreementEvidence {
  readonly schemaVersion: "visual-dataset-agreement-evidence-v1";
  readonly manifestSha256: string;
  readonly annotationIndexSha256: string;
  readonly deletionLedgerSha256: string;
  readonly consentLedgerSha256: string;
  readonly authorizedAt: string;
  readonly releasePosture: "research-only";
  readonly learnerFeedbackEligible: false;
  readonly agreement: VisualCueAgreementReport;
  readonly sha256: string;
}

export class VisualDatasetError extends TypeError {
  override readonly name = "VisualDatasetError";
}
