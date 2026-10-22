import { createHash } from "node:crypto";

import { evaluateVisualCueAgreement } from "./agreement.ts";
import type { VisualCueAnnotationBundle } from "./annotation-types.ts";
import {
  VisualDatasetError,
  visualDatasetSplits,
  type ConsentEligibilityEntry,
  type ConsentEligibilitySnapshot,
  type DeletionLineageSnapshot,
  type LockedVisualDatasetManifest,
  type VisualDatasetAgreementEvidence,
  type VisualDatasetAnnotationIndex,
  type VisualDatasetManifestItem,
} from "./dataset-types.ts";
import { parseVisualCueAnnotationBundle } from "./parse-annotation.ts";

const verifiedManifestMarker: unique symbol = Symbol("verified-visual-dataset-manifest");
const authorizedDatasetMarker: unique symbol = Symbol("authorized-visual-dataset");

export interface VerifiedVisualDatasetManifest {
  readonly manifest: LockedVisualDatasetManifest;
  readonly sha256: string;
  readonly deletionLedgerAtLock: DeletionLineageSnapshot;
  readonly consentLedgerAtLock: ConsentEligibilitySnapshot;
  readonly [verifiedManifestMarker]: true;
}

export interface AuthorizedVisualDataset {
  readonly verifiedManifest: VerifiedVisualDatasetManifest;
  readonly currentDeletionLedger: DeletionLineageSnapshot;
  readonly currentConsentLedger: ConsentEligibilitySnapshot;
  readonly authorizedAt: string;
  readonly [authorizedDatasetMarker]: true;
}

export function assertAuthorizedVisualDataset(
  dataset: AuthorizedVisualDataset,
): void {
  if (dataset[authorizedDatasetMarker] !== true) {
    fail("current deletion and consent authorization is required");
  }
}

export function deletionLineageSha256(
  snapshot: Omit<DeletionLineageSnapshot, "sha256">,
): string {
  return sha256({
    schemaVersion: snapshot.schemaVersion,
    version: snapshot.version,
    asOf: snapshot.asOf,
    revokedSubjectHashes: [...snapshot.revokedSubjectHashes].sort(),
  });
}

export function consentEligibilitySha256(
  snapshot: Omit<ConsentEligibilitySnapshot, "sha256">,
): string {
  return sha256({
    schemaVersion: snapshot.schemaVersion,
    version: snapshot.version,
    asOf: snapshot.asOf,
    entries: [...snapshot.entries]
      .sort((left, right) => compareText(
        left.consentSnapshotHash,
        right.consentSnapshotHash,
      ))
      .map(canonicalConsentEntry),
  });
}

export function visualDatasetManifestSha256(
  manifest: Omit<LockedVisualDatasetManifest, "sha256">,
): string {
  return sha256({
    schemaVersion: manifest.schemaVersion,
    version: manifest.version,
    lockedAt: manifest.lockedAt,
    cueFamily: manifest.cueFamily,
    labelPolicyVersion: manifest.labelPolicyVersion,
    collectionProtocolVersion: manifest.collectionProtocolVersion,
    deletionLedgerSha256AtLock: manifest.deletionLedgerSha256AtLock,
    consentLedgerSha256AtLock: manifest.consentLedgerSha256AtLock,
    releasePosture: manifest.releasePosture,
    learnerFeedbackEligible: manifest.learnerFeedbackEligible,
    rawMediaIncluded: manifest.rawMediaIncluded,
    rawLandmarksIncluded: manifest.rawLandmarksIncluded,
    items: [...manifest.items]
      .sort((left, right) => compareText(left.itemID, right.itemID))
      .map(canonicalManifestItem),
  });
}

export function parseDeletionLineageSnapshot(value: unknown): DeletionLineageSnapshot {
  const root = object(value, "deletion snapshot", [
    "schemaVersion",
    "version",
    "sha256",
    "asOf",
    "revokedSubjectHashes",
  ]);
  literal(root.schemaVersion, "deletion-lineage-snapshot-v1", "schemaVersion");
  const version = identifier(root.version, "version");
  const digest = hash(root.sha256, "sha256");
  const asOf = timestamp(root.asOf, "asOf");
  if (!Array.isArray(root.revokedSubjectHashes)) {
    fail("revokedSubjectHashes must be an array");
  }
  const revokedSubjectHashes = root.revokedSubjectHashes.map((item, index) =>
    hash(item, `revokedSubjectHashes[${index}]`));
  if (new Set(revokedSubjectHashes).size !== revokedSubjectHashes.length) {
    fail("revokedSubjectHashes cannot contain duplicates");
  }
  const snapshot: DeletionLineageSnapshot = {
    schemaVersion: "deletion-lineage-snapshot-v1",
    version,
    sha256: digest,
    asOf,
    revokedSubjectHashes,
  };
  if (deletionLineageSha256(snapshot) !== digest) {
    fail("deletion snapshot hash does not match its contents");
  }
  return snapshot;
}

export function parseConsentEligibilitySnapshot(
  value: unknown,
): ConsentEligibilitySnapshot {
  const root = object(value, "consent snapshot", [
    "schemaVersion",
    "version",
    "sha256",
    "asOf",
    "entries",
  ]);
  literal(root.schemaVersion, "consent-eligibility-snapshot-v1", "schemaVersion");
  const version = identifier(root.version, "version");
  const digest = hash(root.sha256, "sha256");
  const asOf = timestamp(root.asOf, "asOf");
  if (!Array.isArray(root.entries)) fail("consent entries must be an array");
  const entries = root.entries.map(parseConsentEntry);
  if (new Set(entries.map((entry) => entry.consentSnapshotHash)).size !== entries.length) {
    fail("consent snapshot hashes must be unique");
  }
  if (new Set(entries.map((entry) => entry.deletionSubjectHash)).size !== entries.length) {
    fail("consent eligibility must contain at most one current entry per subject");
  }
  const snapshot: ConsentEligibilitySnapshot = {
    schemaVersion: "consent-eligibility-snapshot-v1",
    version,
    sha256: digest,
    asOf,
    entries,
  };
  if (consentEligibilitySha256(snapshot) !== digest) {
    fail("consent eligibility snapshot hash does not match its contents");
  }
  return snapshot;
}

export function verifyLockedVisualDatasetManifest(
  manifestValue: unknown,
  deletionLedgerAtLockValue: unknown,
  consentLedgerAtLockValue: unknown,
): VerifiedVisualDatasetManifest {
  const manifest = parseManifest(manifestValue);
  const deletionLedgerAtLock = parseDeletionLineageSnapshot(deletionLedgerAtLockValue);
  const consentLedgerAtLock = parseConsentEligibilitySnapshot(consentLedgerAtLockValue);
  if (manifest.deletionLedgerSha256AtLock !== deletionLedgerAtLock.sha256) {
    fail("manifest deletion ledger hash does not match the lock-time snapshot");
  }
  if (deletionLedgerAtLock.asOf !== manifest.lockedAt) {
    fail("the deletion snapshot must be captured at the manifest lock time");
  }
  if (manifest.consentLedgerSha256AtLock !== consentLedgerAtLock.sha256) {
    fail("manifest consent ledger hash does not match the lock-time snapshot");
  }
  if (consentLedgerAtLock.asOf !== manifest.lockedAt) {
    fail("the consent snapshot must be captured at the manifest lock time");
  }
  rejectRevokedItems(manifest, deletionLedgerAtLock);
  requireEligibleConsent(manifest, consentLedgerAtLock);
  return Object.freeze({
    manifest,
    sha256: manifest.sha256,
    deletionLedgerAtLock,
    consentLedgerAtLock,
    [verifiedManifestMarker]: true as const,
  });
}

export function authorizeVisualDatasetUse(
  verifiedManifest: VerifiedVisualDatasetManifest,
  currentDeletionLedgerValue: unknown,
  currentConsentLedgerValue: unknown,
  authorizationAtValue: unknown,
): AuthorizedVisualDataset {
  if (verifiedManifest[verifiedManifestMarker] !== true) {
    fail("a verified visual dataset manifest is required");
  }
  const currentDeletionLedger = parseDeletionLineageSnapshot(currentDeletionLedgerValue);
  const currentConsentLedger = parseConsentEligibilitySnapshot(currentConsentLedgerValue);
  const authorizedAt = timestamp(authorizationAtValue, "authorizationAt");
  if (
    Date.parse(currentDeletionLedger.asOf)
    < Date.parse(verifiedManifest.manifest.lockedAt)
  ) {
    fail("the current deletion snapshot cannot predate the manifest lock");
  }
  rejectRevokedItems(verifiedManifest.manifest, currentDeletionLedger);
  if (Date.parse(currentConsentLedger.asOf) < Date.parse(verifiedManifest.manifest.lockedAt)) {
    fail("the current consent snapshot cannot predate the manifest lock");
  }
  requireEligibleConsent(verifiedManifest.manifest, currentConsentLedger);
  if (
    currentDeletionLedger.asOf !== authorizedAt
    || currentConsentLedger.asOf !== authorizedAt
  ) {
    fail("consent and deletion snapshots must be captured at authorization time");
  }
  return Object.freeze({
    verifiedManifest,
    currentDeletionLedger,
    currentConsentLedger,
    authorizedAt,
    [authorizedDatasetMarker]: true as const,
  });
}

export function bindVisualAnnotationsToDataset(
  authorizedDataset: AuthorizedVisualDataset,
  bundleValues: readonly VisualCueAnnotationBundle[],
): VisualDatasetAnnotationIndex {
  if (authorizedDataset[authorizedDatasetMarker] !== true) {
    fail("current deletion authorization is required before binding annotations");
  }
  const bundles = bundleValues.map(parseVisualCueAnnotationBundle);
  const bundleByItem = new Map(bundles.map((bundle) => [bundle.itemID, bundle]));
  if (bundleByItem.size !== bundles.length) fail("annotation bundles contain duplicate items");
  const manifestItems = authorizedDataset.verifiedManifest.manifest.items;
  const expectedItems = new Set(manifestItems.map((item) => item.itemID));
  if (
    bundles.length !== manifestItems.length
    || bundles.some((bundle) => !expectedItems.has(bundle.itemID))
  ) {
    fail("annotations must cover exactly the authorized manifest items");
  }
  const items = manifestItems
    .map((item) => {
      const bundle = bundleByItem.get(item.itemID);
      if (!bundle) fail(`missing annotation for ${item.itemID}`);
      const annotationTimes = [
        ...bundle.ratings.map((rating) => rating.annotatedAt),
        ...(bundle.adjudication ? [bundle.adjudication.adjudicatedAt] : []),
      ];
      if (annotationTimes.some((value) =>
        Date.parse(value) < Date.parse(item.capturedAt))) {
        fail("annotations cannot predate their captured dataset item");
      }
      if (annotationTimes.some((value) =>
        Date.parse(value) > Date.parse(authorizedDataset.authorizedAt))) {
        fail("current consent and deletion authorization must postdate annotations");
      }
      return {
        itemID: item.itemID,
        annotationBundleSha256: visualAnnotationBundleSha256(bundle),
        finalLabel: bundle.adjudication?.finalLabel ?? bundle.ratings[0].label,
      };
    })
    .sort((left, right) => compareText(left.itemID, right.itemID));
  const base = {
    schemaVersion: "visual-dataset-annotation-index-v1" as const,
    manifestSha256: authorizedDataset.verifiedManifest.sha256,
    deletionLedgerSha256: authorizedDataset.currentDeletionLedger.sha256,
    consentLedgerSha256: authorizedDataset.currentConsentLedger.sha256,
    authorizedAt: authorizedDataset.authorizedAt,
    labelPolicyVersion: "bilabial-closure-observation-v1" as const,
    releasePosture: "research-only" as const,
    learnerFeedbackEligible: false as const,
    items,
  };
  return { ...base, sha256: visualDatasetAnnotationIndexSha256(base) };
}

export function visualDatasetAnnotationIndexSha256(
  index: Omit<VisualDatasetAnnotationIndex, "sha256">,
): string {
  return sha256({
    schemaVersion: index.schemaVersion,
    manifestSha256: index.manifestSha256,
    deletionLedgerSha256: index.deletionLedgerSha256,
    consentLedgerSha256: index.consentLedgerSha256,
    authorizedAt: index.authorizedAt,
    labelPolicyVersion: index.labelPolicyVersion,
    releasePosture: index.releasePosture,
    learnerFeedbackEligible: index.learnerFeedbackEligible,
    items: [...index.items]
      .sort((left, right) => compareText(left.itemID, right.itemID))
      .map((item) => ({
        itemID: item.itemID,
        annotationBundleSha256: item.annotationBundleSha256,
        finalLabel: item.finalLabel,
      })),
  });
}

export function buildVisualDatasetAgreementEvidence(
  authorizedDataset: AuthorizedVisualDataset,
  bundleValues: readonly VisualCueAnnotationBundle[],
): VisualDatasetAgreementEvidence {
  const annotationIndex = bindVisualAnnotationsToDataset(
    authorizedDataset,
    bundleValues,
  );
  const agreement = evaluateVisualCueAgreement(bundleValues);
  const base = {
    schemaVersion: "visual-dataset-agreement-evidence-v1" as const,
    manifestSha256: annotationIndex.manifestSha256,
    annotationIndexSha256: annotationIndex.sha256,
    deletionLedgerSha256: annotationIndex.deletionLedgerSha256,
    consentLedgerSha256: annotationIndex.consentLedgerSha256,
    authorizedAt: annotationIndex.authorizedAt,
    releasePosture: "research-only" as const,
    learnerFeedbackEligible: false as const,
    agreement,
  };
  return { ...base, sha256: sha256(base) };
}

export function visualAnnotationBundleSha256(
  value: VisualCueAnnotationBundle,
): string {
  const bundle = parseVisualCueAnnotationBundle(value);
  return sha256({
    schemaVersion: bundle.schemaVersion,
    itemID: bundle.itemID,
    labelPolicyVersion: bundle.labelPolicyVersion,
    ratings: bundle.ratings,
    ...(bundle.adjudication ? { adjudication: bundle.adjudication } : {}),
  });
}

function parseManifest(value: unknown): LockedVisualDatasetManifest {
  const root = object(value, "manifest", [
    "schemaVersion",
    "version",
    "sha256",
    "lockedAt",
    "cueFamily",
    "labelPolicyVersion",
    "collectionProtocolVersion",
    "deletionLedgerSha256AtLock",
    "consentLedgerSha256AtLock",
    "releasePosture",
    "learnerFeedbackEligible",
    "rawMediaIncluded",
    "rawLandmarksIncluded",
    "items",
  ]);
  literal(root.schemaVersion, "visual-dataset-manifest-v1", "schemaVersion");
  const version = identifier(root.version, "version");
  const digest = hash(root.sha256, "sha256");
  const lockedAt = timestamp(root.lockedAt, "lockedAt");
  literal(root.cueFamily, "bilabial-closure", "cueFamily");
  literal(
    root.labelPolicyVersion,
    "bilabial-closure-observation-v1",
    "labelPolicyVersion",
  );
  const collectionProtocolVersion = identifier(
    root.collectionProtocolVersion,
    "collectionProtocolVersion",
  );
  const deletionLedgerSha256AtLock = hash(
    root.deletionLedgerSha256AtLock,
    "deletionLedgerSha256AtLock",
  );
  const consentLedgerSha256AtLock = hash(
    root.consentLedgerSha256AtLock,
    "consentLedgerSha256AtLock",
  );
  literal(root.releasePosture, "research-only", "releasePosture");
  literal(root.learnerFeedbackEligible, false, "learnerFeedbackEligible");
  literal(root.rawMediaIncluded, false, "rawMediaIncluded");
  literal(root.rawLandmarksIncluded, false, "rawLandmarksIncluded");
  if (!Array.isArray(root.items) || root.items.length === 0) {
    fail("manifest items must be a non-empty array");
  }
  const items = root.items.map(parseManifestItem);
  const itemIDs = new Set(items.map((item) => item.itemID));
  if (itemIDs.size !== items.length) fail("manifest item IDs must be unique");
  requireEverySplit(items);
  validatePartition(items, "speakerHash");
  validatePartition(items, "householdHash");
  validateProspectiveSiteHoldout(items);
  if (items.some((item) => Date.parse(item.capturedAt) > Date.parse(lockedAt))) {
    fail("manifest items cannot be captured after the manifest lock");
  }
  const manifest: LockedVisualDatasetManifest = {
    schemaVersion: "visual-dataset-manifest-v1",
    version,
    sha256: digest,
    lockedAt,
    cueFamily: "bilabial-closure",
    labelPolicyVersion: "bilabial-closure-observation-v1",
    collectionProtocolVersion,
    deletionLedgerSha256AtLock,
    consentLedgerSha256AtLock,
    releasePosture: "research-only",
    learnerFeedbackEligible: false,
    rawMediaIncluded: false,
    rawLandmarksIncluded: false,
    items,
  };
  if (visualDatasetManifestSha256(manifest) !== digest) {
    fail("visual dataset manifest hash does not match its contents");
  }
  return manifest;
}

function parseManifestItem(value: unknown, index: number): VisualDatasetManifestItem {
  const path = `items[${index}]`;
  const root = object(value, path, [
    "itemID",
    "speakerHash",
    "householdHash",
    "siteHash",
    "deletionSubjectHash",
    "consentSnapshotHash",
    "consentNoticeVersion",
    "assentStatus",
    "videoProcessing",
    "clinicianReview",
    "researchUse",
    "split",
    "hardwareIdentifier",
    "systemVersion",
    "capturedAt",
    "targetWindowVersion",
    "annotationRequired",
  ]);
  const item = {
    itemID: opaqueID(root.itemID, `${path}.itemID`),
    speakerHash: hash(root.speakerHash, `${path}.speakerHash`),
    householdHash: hash(root.householdHash, `${path}.householdHash`),
    siteHash: hash(root.siteHash, `${path}.siteHash`),
    deletionSubjectHash: hash(
      root.deletionSubjectHash,
      `${path}.deletionSubjectHash`,
    ),
    consentSnapshotHash: hash(
      root.consentSnapshotHash,
      `${path}.consentSnapshotHash`,
    ),
    consentNoticeVersion: identifier(
      root.consentNoticeVersion,
      `${path}.consentNoticeVersion`,
    ),
    assentStatus: enumeration(
      root.assentStatus,
      ["affirmed", "not-applicable"] as const,
      `${path}.assentStatus`,
    ),
    split: enumeration(root.split, visualDatasetSplits, `${path}.split`),
    hardwareIdentifier: physicalHardwareIdentifier(
      root.hardwareIdentifier,
      `${path}.hardwareIdentifier`,
    ),
    systemVersion: boundedString(root.systemVersion, `${path}.systemVersion`, 40),
    capturedAt: timestamp(root.capturedAt, `${path}.capturedAt`),
    targetWindowVersion: identifier(
      root.targetWindowVersion,
      `${path}.targetWindowVersion`,
    ),
  };
  literal(root.videoProcessing, true, `${path}.videoProcessing`);
  literal(root.clinicianReview, true, `${path}.clinicianReview`);
  literal(root.researchUse, true, `${path}.researchUse`);
  literal(root.annotationRequired, true, `${path}.annotationRequired`);
  if (new Set([
    item.speakerHash,
    item.householdHash,
    item.siteHash,
    item.deletionSubjectHash,
    item.consentSnapshotHash,
  ]).size !== 5) {
    fail(`${path} hashes must use purpose-separated identifiers`);
  }
  return {
    ...item,
    videoProcessing: true,
    clinicianReview: true,
    researchUse: true,
    annotationRequired: true,
  };
}

function canonicalManifestItem(item: VisualDatasetManifestItem) {
  return {
    itemID: item.itemID,
    speakerHash: item.speakerHash,
    householdHash: item.householdHash,
    siteHash: item.siteHash,
    deletionSubjectHash: item.deletionSubjectHash,
    consentSnapshotHash: item.consentSnapshotHash,
    consentNoticeVersion: item.consentNoticeVersion,
    assentStatus: item.assentStatus,
    videoProcessing: item.videoProcessing,
    clinicianReview: item.clinicianReview,
    researchUse: item.researchUse,
    split: item.split,
    hardwareIdentifier: item.hardwareIdentifier,
    systemVersion: item.systemVersion,
    capturedAt: item.capturedAt,
    targetWindowVersion: item.targetWindowVersion,
    annotationRequired: item.annotationRequired,
  };
}

function parseConsentEntry(value: unknown, index: number): ConsentEligibilityEntry {
  const path = `entries[${index}]`;
  const root = object(value, path, [
    "consentSnapshotHash",
    "deletionSubjectHash",
    "consentNoticeVersion",
    "assentStatus",
    "videoProcessing",
    "clinicianReview",
    "researchUse",
    "capturedAt",
  ]);
  const entry = {
    consentSnapshotHash: hash(root.consentSnapshotHash, `${path}.consentSnapshotHash`),
    deletionSubjectHash: hash(root.deletionSubjectHash, `${path}.deletionSubjectHash`),
    consentNoticeVersion: identifier(
      root.consentNoticeVersion,
      `${path}.consentNoticeVersion`,
    ),
    assentStatus: enumeration(
      root.assentStatus,
      ["affirmed", "not-applicable"] as const,
      `${path}.assentStatus`,
    ),
    capturedAt: timestamp(root.capturedAt, `${path}.capturedAt`),
  };
  literal(root.videoProcessing, true, `${path}.videoProcessing`);
  literal(root.clinicianReview, true, `${path}.clinicianReview`);
  literal(root.researchUse, true, `${path}.researchUse`);
  return {
    ...entry,
    videoProcessing: true,
    clinicianReview: true,
    researchUse: true,
  };
}

function canonicalConsentEntry(entry: ConsentEligibilityEntry) {
  return {
    consentSnapshotHash: entry.consentSnapshotHash,
    deletionSubjectHash: entry.deletionSubjectHash,
    consentNoticeVersion: entry.consentNoticeVersion,
    assentStatus: entry.assentStatus,
    videoProcessing: entry.videoProcessing,
    clinicianReview: entry.clinicianReview,
    researchUse: entry.researchUse,
    capturedAt: entry.capturedAt,
  };
}

function requireEverySplit(items: readonly VisualDatasetManifestItem[]): void {
  const splits = new Set(items.map((item) => item.split));
  for (const split of visualDatasetSplits) {
    if (!splits.has(split)) fail(`visual dataset manifest is missing the ${split} split`);
  }
}

function validatePartition(
  items: readonly VisualDatasetManifestItem[],
  key: "speakerHash" | "householdHash",
): void {
  const splitByIdentity = new Map<string, string>();
  for (const item of items) {
    const existing = splitByIdentity.get(item[key]);
    if (existing && existing !== item.split) {
      fail(`${key} cannot appear in more than one visual dataset split`);
    }
    splitByIdentity.set(item[key], item.split);
  }
}

function validateProspectiveSiteHoldout(
  items: readonly VisualDatasetManifestItem[],
): void {
  const prospectiveSites = new Set(
    items.filter((item) => item.split === "prospective-test").map((item) => item.siteHash),
  );
  if (items.some((item) =>
    item.split !== "prospective-test" && prospectiveSites.has(item.siteHash))) {
    fail("prospective-test sites must be held out from development splits");
  }
}

function rejectRevokedItems(
  manifest: LockedVisualDatasetManifest,
  snapshot: DeletionLineageSnapshot,
): void {
  const revoked = new Set(snapshot.revokedSubjectHashes);
  const affected = manifest.items.filter((item) => revoked.has(item.deletionSubjectHash));
  if (affected.length > 0) {
    fail("the visual dataset contains a subject present in deletion lineage");
  }
}

function requireEligibleConsent(
  manifest: LockedVisualDatasetManifest,
  snapshot: ConsentEligibilitySnapshot,
): void {
  const byConsentHash = new Map(
    snapshot.entries.map((entry) => [entry.consentSnapshotHash, entry]),
  );
  for (const item of manifest.items) {
    const consent = byConsentHash.get(item.consentSnapshotHash);
    if (
      !consent
      || consent.deletionSubjectHash !== item.deletionSubjectHash
      || consent.consentNoticeVersion !== item.consentNoticeVersion
      || consent.assentStatus !== item.assentStatus
      || Date.parse(consent.capturedAt) > Date.parse(item.capturedAt)
    ) {
      fail("every visual dataset item requires matching current consent eligibility");
    }
  }
}

function object(
  value: unknown,
  path: string,
  fields: readonly string[],
): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(`${path} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set(fields);
  const unknown = Object.keys(record).filter((key) => !allowed.has(key));
  if (unknown.length > 0) fail(`${path} contains unknown fields: ${unknown.join(", ")}`);
  const missing = fields.filter((key) => !(key in record));
  if (missing.length > 0) fail(`${path} is missing fields: ${missing.join(", ")}`);
  return record;
}

function literal<T>(value: unknown, expected: T, path: string): asserts value is T {
  if (value !== expected) fail(`${path} must equal ${String(expected)}`);
}

function enumeration<const T extends readonly string[]>(
  value: unknown,
  allowed: T,
  path: string,
): T[number] {
  if (typeof value !== "string" || !allowed.includes(value)) {
    fail(`${path} must be one of ${allowed.join(", ")}`);
  }
  return value as T[number];
}

function opaqueID(value: unknown, path: string): string {
  if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(value)) {
    fail(`${path} must be a bounded opaque identifier`);
  }
  return value;
}

function identifier(value: unknown, path: string): string {
  if (typeof value !== "string" || !/^[a-z0-9][a-z0-9._-]{2,79}$/.test(value)) {
    fail(`${path} must be a versioned identifier`);
  }
  return value;
}

function hash(value: unknown, path: string): string {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) {
    fail(`${path} must be a lowercase SHA-256 digest`);
  }
  return value;
}

function timestamp(value: unknown, path: string): string {
  if (
    typeof value !== "string"
    || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)
    || !Number.isFinite(Date.parse(value))
    || new Date(value).toISOString() !== value
  ) {
    fail(`${path} must be a canonical UTC timestamp with milliseconds`);
  }
  return value;
}

function boundedString(value: unknown, path: string, maximum: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum) {
    fail(`${path} must be a bounded string`);
  }
  return value;
}

function physicalHardwareIdentifier(value: unknown, path: string): string {
  if (typeof value !== "string" || !/^(?:iPhone|iPad)\d+,\d+$/.test(value)) {
    fail(`${path} must identify a physical iPhone or iPad`);
  }
  return value;
}

function sha256(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function fail(message: string): never {
  throw new VisualDatasetError(message);
}
