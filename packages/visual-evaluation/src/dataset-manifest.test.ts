import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";

import type { VisualCueAnnotationBundle } from "./annotation-types.ts";
import {
  authorizeVisualDatasetUse,
  bindVisualAnnotationsToDataset,
  buildVisualDatasetAgreementEvidence,
  consentEligibilitySha256,
  deletionLineageSha256,
  visualDatasetManifestSha256,
  verifyLockedVisualDatasetManifest,
} from "./dataset-manifest.ts";
import type {
  ConsentEligibilitySnapshot,
  DeletionLineageSnapshot,
  LockedVisualDatasetManifest,
  VisualDatasetManifestItem,
  VisualDatasetSplit,
} from "./dataset-types.ts";

test("the canonical visual manifest, deletion, and consent fixtures verify together", async () => {
  const [manifest, ledger, consent] = await Promise.all([
    readFixture("visual-dataset-manifest.valid.json"),
    readFixture("deletion-lineage-snapshot.valid.json"),
    readFixture("consent-eligibility-snapshot.valid.json"),
  ]);

  const verified = verifyLockedVisualDatasetManifest(manifest, ledger, consent);

  assert.equal(
    verified.sha256,
    "de59cb8b962cfe88d04bd2f66df200b959313cf6b4f9a89e7fa83899c606baf9",
  );
  assert.equal(verified.manifest.items.length, 4);
});

test("the dataset CLI produces manifest-bound research evidence from fixture bundles", () => {
  const script = fileURLToPath(new URL("dataset-cli.ts", import.meta.url));
  const manifest = fixturePath("visual-dataset-manifest.valid.json");
  const deletion = fixturePath("deletion-lineage-snapshot.valid.json");
  const consent = fixturePath("consent-eligibility-snapshot.valid.json");
  const annotations = fixturePath("visual-dataset-annotations.valid.json");
  const result = spawnSync(process.execPath, [
    script,
    "evidence",
    manifest,
    deletion,
    consent,
    deletion,
    consent,
    "2026-07-10T18:10:00.000Z",
    annotations,
  ], { encoding: "utf8" });

  assert.equal(result.status, 0, result.stderr);
  const evidence = JSON.parse(result.stdout) as Record<string, unknown>;
  assert.equal(evidence.manifestSha256, "de59cb8b962cfe88d04bd2f66df200b959313cf6b4f9a89e7fa83899c606baf9");
  assert.equal(evidence.releasePosture, "research-only");
  assert.equal(evidence.learnerFeedbackEligible, false);
});

test("a locked prospective manifest is canonical, consent-bound, and research-only", () => {
  const { lockedLedger, lockedConsent, manifest } = datasetAtLock();
  const verified = verifyLockedVisualDatasetManifest(
    manifest,
    lockedLedger,
    lockedConsent,
  );

  assert.equal(verified.sha256, manifest.sha256);
  assert.equal(verified.manifest.releasePosture, "research-only");
  assert.equal(verified.manifest.learnerFeedbackEligible, false);
  assert.equal(verified.manifest.rawMediaIncluded, false);
  assert.equal(verified.manifest.rawLandmarksIncluded, false);
  assert.equal(
    visualDatasetManifestSha256({
      ...withoutSha(manifest),
      items: [...manifest.items].reverse(),
    }),
    manifest.sha256,
  );
});

test("manifest parsing rejects unsafe consent, identity leakage, media, and simulators", () => {
  const { lockedLedger, lockedConsent } = datasetAtLock();
  const unsafeConsent = datasetAtLock().manifest;
  (unsafeConsent.items[0] as unknown as { researchUse: boolean }).researchUse = false;
  assert.throws(
    () => verifyLockedVisualDatasetManifest(unsafeConsent, lockedLedger, lockedConsent),
    /researchUse must equal true/,
  );

  const rawMedia = datasetAtLock().manifest;
  (rawMedia as unknown as { rawMediaIncluded: boolean }).rawMediaIncluded = true;
  assert.throws(
    () => verifyLockedVisualDatasetManifest(rawMedia, lockedLedger, lockedConsent),
    /rawMediaIncluded must equal false/,
  );

  const identity = datasetAtLock().manifest as unknown as Record<string, unknown>;
  (identity.items as Record<string, unknown>[])[0]!.learnerName = "Not allowed";
  assert.throws(
    () => verifyLockedVisualDatasetManifest(identity, lockedLedger, lockedConsent),
    /unknown fields: learnerName/,
  );

  const simulator = datasetAtLock().manifest;
  simulator.items[0]!.hardwareIdentifier = "arm64";
  assert.throws(
    () => verifyLockedVisualDatasetManifest(simulator, lockedLedger, lockedConsent),
    /physical iPhone or iPad/,
  );

  const unseparated = datasetAtLock().manifest;
  unseparated.items[0]!.deletionSubjectHash = unseparated.items[0]!.speakerHash;
  assert.throws(
    () => verifyLockedVisualDatasetManifest(unseparated, lockedLedger, lockedConsent),
    /purpose-separated/,
  );
});

test("speaker, household, prospective-site, split, and lock boundaries fail closed", () => {
  const { lockedLedger, lockedConsent } = datasetAtLock();

  const speakerLeak = datasetAtLock().manifest;
  speakerLeak.items[1]!.speakerHash = speakerLeak.items[0]!.speakerHash;
  assert.throws(
    () => verifyLockedVisualDatasetManifest(speakerLeak, lockedLedger, lockedConsent),
    /speakerHash cannot appear/,
  );

  const householdLeak = datasetAtLock().manifest;
  householdLeak.items[1]!.householdHash = householdLeak.items[0]!.householdHash;
  assert.throws(
    () => verifyLockedVisualDatasetManifest(householdLeak, lockedLedger, lockedConsent),
    /householdHash cannot appear/,
  );

  const siteLeak = datasetAtLock().manifest;
  siteLeak.items[3]!.siteHash = siteLeak.items[0]!.siteHash;
  assert.throws(
    () => verifyLockedVisualDatasetManifest(siteLeak, lockedLedger, lockedConsent),
    /prospective-test sites must be held out/,
  );

  const missingSplit = datasetAtLock().manifest;
  missingSplit.items = missingSplit.items.slice(0, 3);
  assert.throws(
    () => verifyLockedVisualDatasetManifest(missingSplit, lockedLedger, lockedConsent),
    /missing the prospective-test split/,
  );

  const futureCapture = datasetAtLock().manifest;
  futureCapture.items[0]!.capturedAt = "2026-07-10T18:11:00.000Z";
  assert.throws(
    () => verifyLockedVisualDatasetManifest(futureCapture, lockedLedger, lockedConsent),
    /captured after the manifest lock/,
  );
});

test("current deletion and consent snapshots are mandatory before dataset use", () => {
  const { lockedLedger, lockedConsent, manifest } = datasetAtLock();
  const verified = verifyLockedVisualDatasetManifest(
    manifest,
    lockedLedger,
    lockedConsent,
  );
  const currentConsent = eligibility(
    "2026-07-10T18:20:00.000Z",
    manifest.items,
  );

  const stale = lineage("2026-07-10T18:09:59.999Z");
  assert.throws(
    () => authorizeVisualDatasetUse(
      verified,
      stale,
      currentConsent,
      "2026-07-10T18:20:00.000Z",
    ),
    /cannot predate the manifest lock/,
  );

  const revoked = lineage(
    "2026-07-10T18:20:00.000Z",
    [manifest.items[0]!.deletionSubjectHash],
  );
  assert.throws(
    () => authorizeVisualDatasetUse(
      verified,
      revoked,
      currentConsent,
      "2026-07-10T18:20:00.000Z",
    ),
    /subject present in deletion lineage/,
  );

  const current = lineage("2026-07-10T18:20:00.000Z");
  assert.doesNotThrow(() => authorizeVisualDatasetUse(
    verified,
    current,
    currentConsent,
    "2026-07-10T18:20:00.000Z",
  ));

  const withdrawn = eligibility(
    "2026-07-10T18:20:00.000Z",
    manifest.items.slice(1),
  );
  assert.throws(
    () => authorizeVisualDatasetUse(
      verified,
      current,
      withdrawn,
      "2026-07-10T18:20:00.000Z",
    ),
    /matching current consent eligibility/,
  );

  const supersededItems = manifest.items.map((item, index) =>
    index === 0
      ? { ...item, consentSnapshotHash: digest("superseding-consent") }
      : item);
  const superseded = eligibility(
    "2026-07-10T18:20:00.000Z",
    supersededItems,
  );
  assert.throws(
    () => authorizeVisualDatasetUse(
      verified,
      current,
      superseded,
      "2026-07-10T18:20:00.000Z",
    ),
    /matching current consent eligibility/,
  );

  const staleConsent = eligibility(
    "2026-07-10T18:09:59.999Z",
    manifest.items,
  );
  assert.throws(
    () => authorizeVisualDatasetUse(
      verified,
      current,
      staleConsent,
      "2026-07-10T18:20:00.000Z",
    ),
    /consent snapshot cannot predate the manifest lock/,
  );

  assert.throws(
    () => authorizeVisualDatasetUse(
      verified,
      current,
      currentConsent,
      "2026-07-10T18:21:00.000Z",
    ),
    /captured at authorization time/,
  );
});

test("annotations bind exactly to an authorized manifest and current deletion state", () => {
  const { lockedLedger, lockedConsent, manifest } = datasetAtLock();
  const verified = verifyLockedVisualDatasetManifest(
    manifest,
    lockedLedger,
    lockedConsent,
  );
  const current = lineage("2026-07-10T18:20:00.000Z");
  const currentConsent = eligibility(
    "2026-07-10T18:20:00.000Z",
    manifest.items,
  );
  const authorized = authorizeVisualDatasetUse(
    verified,
    current,
    currentConsent,
    "2026-07-10T18:20:00.000Z",
  );
  const bundles = manifest.items.map((item, index) =>
    agreeingBundle(item.itemID, index));

  const index = bindVisualAnnotationsToDataset(authorized, bundles);
  const evidence = buildVisualDatasetAgreementEvidence(authorized, bundles);

  assert.equal(index.items.length, manifest.items.length);
  assert.equal(index.manifestSha256, manifest.sha256);
  assert.equal(index.deletionLedgerSha256, current.sha256);
  assert.equal(index.consentLedgerSha256, currentConsent.sha256);
  assert.equal(index.authorizedAt, "2026-07-10T18:20:00.000Z");
  assert.equal(index.learnerFeedbackEligible, false);
  assert.equal(evidence.annotationIndexSha256, index.sha256);
  assert.equal(evidence.agreement.rawAgreement, 1);
  assert.equal(evidence.releasePosture, "research-only");

  assert.throws(
    () => bindVisualAnnotationsToDataset(authorized, bundles.slice(1)),
    /cover exactly/,
  );
  assert.throws(
    () => bindVisualAnnotationsToDataset(authorized, [...bundles, bundles[0]!]),
    /duplicate items/,
  );

  const futureBundles = manifest.items.map((item, itemIndex) =>
    agreeingBundle(item.itemID, itemIndex));
  (futureBundles[0]!.ratings[0] as unknown as { annotatedAt: string }).annotatedAt =
    "2026-07-10T18:21:00.000Z";
  assert.throws(
    () => bindVisualAnnotationsToDataset(authorized, futureBundles),
    /authorization must postdate annotations/,
  );

  const prematureBundles = manifest.items.map((item, itemIndex) =>
    agreeingBundle(item.itemID, itemIndex));
  (prematureBundles[3]!.ratings[0] as unknown as { annotatedAt: string }).annotatedAt =
    "2026-07-10T18:02:00.000Z";
  assert.throws(
    () => bindVisualAnnotationsToDataset(authorized, prematureBundles),
    /cannot predate their captured dataset item/,
  );
});

test("tampered hashes and lock-time deletion lineage are rejected", () => {
  const { lockedLedger, lockedConsent, manifest } = datasetAtLock();
  manifest.sha256 = "0".repeat(64);
  assert.throws(
    () => verifyLockedVisualDatasetManifest(manifest, lockedLedger, lockedConsent),
    /manifest hash does not match/,
  );

  const validManifest = datasetAtLock().manifest;
  const otherLedger = lineage("2026-07-10T18:10:00.000Z", [digest("other-subject")]);
  assert.throws(
    () => verifyLockedVisualDatasetManifest(validManifest, otherLedger, lockedConsent),
    /does not match the lock-time snapshot/,
  );

  const tamperedLedger = { ...lockedLedger, sha256: "0".repeat(64) };
  assert.throws(
    () => verifyLockedVisualDatasetManifest(validManifest, tamperedLedger, lockedConsent),
    /deletion snapshot hash does not match/,
  );

  const otherConsent = eligibility(
    "2026-07-10T18:00:00.000Z",
    validManifest.items.slice(1),
  );
  assert.throws(
    () => verifyLockedVisualDatasetManifest(validManifest, lockedLedger, otherConsent),
    /consent ledger hash does not match/,
  );

  const ineligibleConsent = eligibility(
    "2026-07-10T18:10:00.000Z",
    validManifest.items,
  ) as unknown as { entries: Array<{ researchUse: boolean }> };
  ineligibleConsent.entries[0]!.researchUse = false;
  assert.throws(
    () => verifyLockedVisualDatasetManifest(
      validManifest,
      lockedLedger,
      ineligibleConsent,
    ),
    /researchUse must equal true/,
  );
});

type MutableItem = { -readonly [Key in keyof VisualDatasetManifestItem]: VisualDatasetManifestItem[Key] };
type MutableManifest = {
  -readonly [Key in keyof LockedVisualDatasetManifest]:
    Key extends "items" ? MutableItem[] : LockedVisualDatasetManifest[Key];
};

function lineage(
  asOf: string,
  revokedSubjectHashes: readonly string[] = [],
): DeletionLineageSnapshot {
  const base = {
    schemaVersion: "deletion-lineage-snapshot-v1" as const,
    version: "deletion-lineage-v1",
    asOf,
    revokedSubjectHashes,
  };
  return { ...base, sha256: deletionLineageSha256(base) };
}

function datasetAtLock(): {
  lockedLedger: DeletionLineageSnapshot;
  lockedConsent: ConsentEligibilitySnapshot;
  manifest: MutableManifest;
} {
  const lockedLedger = lineage("2026-07-10T18:10:00.000Z");
  const items = visualItems();
  const lockedConsent = eligibility("2026-07-10T18:10:00.000Z", items);
  return {
    lockedLedger,
    lockedConsent,
    manifest: visualManifest(lockedLedger, lockedConsent, items),
  };
}

function visualItems(): MutableItem[] {
  const splits: readonly VisualDatasetSplit[] = [
    "train",
    "calibration",
    "test",
    "prospective-test",
  ];
  return splits.map((split, index): MutableItem => ({
    itemID: `item-visual-${String(index + 1).padStart(4, "0")}`,
    speakerHash: digest(`speaker-${index}`),
    householdHash: digest(`household-${index}`),
    siteHash: digest(`site-${index}`),
    deletionSubjectHash: digest(`deletion-${index}`),
    consentSnapshotHash: digest(`consent-${index}`),
    consentNoticeVersion: "research-consent-v1",
    assentStatus: "affirmed",
    videoProcessing: true,
    clinicianReview: true,
    researchUse: true,
    split,
    hardwareIdentifier: ["iPhone15,2", "iPhone16,1", "iPad14,5", "iPhone17,1"][index]!,
    systemVersion: "26.2",
    capturedAt: `2026-07-10T18:0${index}:00.000Z`,
    targetWindowVersion: "bilabial-window-v1",
    annotationRequired: true,
  }));
}

function eligibility(
  asOf: string,
  items: readonly VisualDatasetManifestItem[],
): ConsentEligibilitySnapshot {
  const entries = items.map((item) => ({
    consentSnapshotHash: item.consentSnapshotHash,
    deletionSubjectHash: item.deletionSubjectHash,
    consentNoticeVersion: item.consentNoticeVersion,
    assentStatus: item.assentStatus,
    videoProcessing: true as const,
    clinicianReview: true as const,
    researchUse: true as const,
    capturedAt: "2026-07-10T17:00:00.000Z",
  }));
  const base = {
    schemaVersion: "consent-eligibility-snapshot-v1" as const,
    version: "consent-eligibility-v1",
    asOf,
    entries,
  };
  return { ...base, sha256: consentEligibilitySha256(base) };
}

function visualManifest(
  ledger: DeletionLineageSnapshot,
  consent: ConsentEligibilitySnapshot,
  items: MutableItem[],
): MutableManifest {
  const base = {
    schemaVersion: "visual-dataset-manifest-v1" as const,
    version: "bilabial-prospective-dataset-v1",
    lockedAt: "2026-07-10T18:10:00.000Z",
    cueFamily: "bilabial-closure" as const,
    labelPolicyVersion: "bilabial-closure-observation-v1" as const,
    collectionProtocolVersion: "bilabial-collection-v1",
    deletionLedgerSha256AtLock: ledger.sha256,
    consentLedgerSha256AtLock: consent.sha256,
    releasePosture: "research-only" as const,
    learnerFeedbackEligible: false as const,
    rawMediaIncluded: false as const,
    rawLandmarksIncluded: false as const,
    items,
  };
  return { ...base, sha256: visualDatasetManifestSha256(base) };
}

function withoutSha(manifest: LockedVisualDatasetManifest) {
  const { sha256: _sha256, ...without } = manifest;
  return without;
}

function agreeingBundle(itemID: string, index: number): VisualCueAnnotationBundle {
  const label = index % 2 === 0 ? "closure-observed" : "closure-not-observed";
  return {
    schemaVersion: "visual-cue-adjudication-v1",
    itemID,
    labelPolicyVersion: "bilabial-closure-observation-v1",
    ratings: [
      annotation(itemID, index * 2, "reviewer-slp-001", label),
      annotation(itemID, index * 2 + 1, "reviewer-slp-002", label),
    ],
  };
}

function annotation(
  itemID: string,
  index: number,
  reviewerID: string,
  label: "closure-observed" | "closure-not-observed",
) {
  return {
    schemaVersion: "visual-cue-annotation-v1" as const,
    annotationID: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    itemID,
    cueFamily: "bilabial-closure" as const,
    labelPolicyVersion: "bilabial-closure-observation-v1" as const,
    reviewerID,
    annotatedAt: "2026-07-10T18:12:00.000Z",
    label,
    confidence: "high" as const,
    qualityReasons: [],
    blinding: { modelOutputHidden: true as const, peerRatingsHidden: true as const },
  };
}

function digest(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

async function readFixture(name: string): Promise<unknown> {
  return JSON.parse(await readFile(
    new URL(`../fixtures/${name}`, import.meta.url),
    "utf8",
  )) as unknown;
}

function fixturePath(name: string): string {
  return fileURLToPath(new URL(`../fixtures/${name}`, import.meta.url));
}
