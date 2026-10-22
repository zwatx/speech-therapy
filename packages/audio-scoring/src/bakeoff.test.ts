import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash, generateKeyPairSync, sign, type KeyObject } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  audioBakeoffCandidateManifestSha256,
  audioBakeoffCharterSha256,
  audioBakeoffRunAttestationPayload,
  audioAdaptationAuthorizationPayload,
  audioAdaptationAuthorizationSha256,
  audioAdaptationDatasetManifestSha256,
  buildAudioBakeoffCandidateResult,
  evaluationReferenceSha256,
  evaluationThresholdsSha256,
  lockedEvaluationManifestEnvelopeSha256,
  evaluationSamplesSha256,
  ownedAudioAdaptationManifestSha256,
  scorecardAttestationPayload,
  selectAudioBakeoffCandidates,
  verifyOwnedAudioAdaptation,
  type AudioBakeoffCandidateManifest,
  type AudioBakeoffCharter,
  type AudioBakeoffMeasurements,
  type AudioBakeoffRunAttestation,
  type AudioAdaptationAuthorization,
  type AudioAdaptationDatasetManifest,
  type OwnedAudioAdaptationManifest,
} from "./bakeoff.ts";
import {
  evaluationManifestSha256,
  validateLockedEvaluationManifest,
} from "./evaluation.ts";
import type {
  EvaluationArtifactVersions,
  EvaluationManifestItem,
  EvaluationSample,
  EvaluationThresholds,
  LockedEvaluationManifest,
} from "./types.ts";

test("the locked bake-off ranks only gate-cleared adaptation candidates", () => {
  const fixture = bakeoffFixture();

  assert.equal(fixture.selection.recommendedTeacherCandidateId, "wavlm-base-plus-owned-head");
  assert.equal(fixture.selection.fallbackCandidateId, "wav2vec2-phone-ctc-owned-head");
  assert.equal(fixture.selection.selectionAuthority, "research-prioritization-only");
  assert.equal(fixture.selection.learnerFeedbackEligible, false);
  assert.equal(fixture.selection.productionEligible, false);

  const reference = fixture.selection.ranked.find((item) => item.candidateId === "whisper-reference");
  assert.equal(reference?.adaptationEligible, false);
  assert.ok(reference?.hardGateFailures.includes("prompt-aware-decoder"));
  assert.ok(reference?.hardGateFailures.includes("non-phone-output"));
  assert.ok(reference?.hardGateFailures.includes("commercial-health-rights"));
  assert.ok(fixture.results.every((result) =>
    result.learnerFeedbackEligible === false && result.productionEligible === false));
});

test("every candidate is rebuilt on the exact locked cohort and common head", () => {
  const fixture = bakeoffFixture();
  const candidate = fixture.candidates[0]!;
  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate,
    fixture.charter,
    fixture.samples.slice(1),
    fixture.thresholds,
    fixture.verifiedManifest,
    fixture.artifacts,
    measurements(80, candidate.candidateId, fixture.scorecardPrivateKey,
      fixture.charter.scorecardRubricSha256),
    fixture.charter.identicalHeadRecipeSha256,
    digest("container"),
    fixture.runs[0]!.runAttestation,
    "2026-07-10T19:00:00.000Z",
  ), /locked charter/);

  const wrongArtifacts = { ...fixture.artifacts, lexiconVersion: "convenient-lexicon-v2" };
  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate,
    fixture.charter,
    fixture.samples,
    fixture.thresholds,
    fixture.verifiedManifest,
    wrongArtifacts,
    measurements(80, candidate.candidateId, fixture.scorecardPrivateKey,
      fixture.charter.scorecardRubricSha256),
    fixture.charter.identicalHeadRecipeSha256,
    digest("container"),
    fixture.runs[0]!.runAttestation,
    "2026-07-10T19:00:00.000Z",
  ), /do not match the locked charter/);

  const relabeled = fixture.samples.map((sample, index) => index === 0
    ? { ...sample, label: "error" as const }
    : sample);
  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate, fixture.charter, relabeled, fixture.thresholds, fixture.verifiedManifest,
    fixture.artifacts, measurements(80, candidate.candidateId, fixture.scorecardPrivateKey,
      fixture.charter.scorecardRubricSha256), fixture.charter.identicalHeadRecipeSha256,
    digest("container"), fixture.runs[0]!.runAttestation,
    "2026-07-10T19:00:00.000Z",
  ), /locked charter/);

  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate, fixture.charter, fixture.samples,
    { ...fixture.thresholds, passThreshold: 0.85 }, fixture.verifiedManifest,
    fixture.artifacts, measurements(80, candidate.candidateId, fixture.scorecardPrivateKey,
      fixture.charter.scorecardRubricSha256), fixture.charter.identicalHeadRecipeSha256,
    digest("container"), fixture.runs[0]!.runAttestation,
    "2026-07-10T19:00:00.000Z",
  ), /locked charter/);

  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate, fixture.charter, fixture.samples, fixture.thresholds, fixture.verifiedManifest,
    fixture.artifacts, measurements(80, candidate.candidateId, fixture.scorecardPrivateKey,
      fixture.charter.scorecardRubricSha256), digest("substituted-head"),
    digest("container"), fixture.runs[0]!.runAttestation,
    "2026-07-10T19:00:00.000Z",
  ), /locked charter/);

  const forgedMeasurements = measurements(80, candidate.candidateId,
    fixture.scorecardPrivateKey, fixture.charter.scorecardRubricSha256);
  const forgedScorecard = {
    ...forgedMeasurements,
    scorecard: { ...forgedMeasurements.scorecard, scores: {
      ...forgedMeasurements.scorecard.scores, clinicalTaskFit: 100,
    } },
  };
  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate, fixture.charter, fixture.samples, fixture.thresholds, fixture.verifiedManifest,
    fixture.artifacts, forgedScorecard, fixture.charter.identicalHeadRecipeSha256,
    digest("container"), fixture.runs[0]!.runAttestation,
    "2026-07-10T19:00:00.000Z",
  ), /measurements and scorecard are invalid/);

  const tamperedCandidate = { ...candidate, trainingDataLineageSha256: digest("other-data") };
  assert.throws(() => buildAudioBakeoffCandidateResult(
    tamperedCandidate,
    fixture.charter,
    fixture.samples,
    fixture.thresholds,
    fixture.verifiedManifest,
    fixture.artifacts,
    measurements(80, candidate.candidateId, fixture.scorecardPrivateKey,
      fixture.charter.scorecardRubricSha256),
    fixture.charter.identicalHeadRecipeSha256,
    digest("container"),
    fixture.runs[0]!.runAttestation,
    "2026-07-10T19:00:00.000Z",
  ), /candidate provenance is invalid/);

  const run = fixture.runs[0]!;
  const forgedProbabilities = run.samples.map((sample, index) => index === 0
    ? { ...sample, pCorrect: 0.81 }
    : sample);
  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate, fixture.charter, forgedProbabilities, run.thresholds,
    fixture.verifiedManifest, run.artifacts, run.measurements, run.headRecipeSha256,
    run.inferenceContainerSha256, run.runAttestation, run.evaluatedAt,
  ), /full-run attestation/);

  const substitutedCalibration = {
    ...run.runAttestation,
    calibrationArtifactSha256: digest("substituted-calibration"),
  };
  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate, fixture.charter, run.samples, run.thresholds, fixture.verifiedManifest,
    run.artifacts, run.measurements, run.headRecipeSha256,
    run.inferenceContainerSha256, substitutedCalibration, run.evaluatedAt,
  ), /full-run attestation/);

  const movedManifest = {
    ...fixture.manifest,
    lockedAt: "2026-07-10T18:01:00.000Z",
  };
  const movedVerified = validateLockedEvaluationManifest(movedManifest);
  assert.throws(() => buildAudioBakeoffCandidateResult(
    candidate, fixture.charter, run.samples, run.thresholds, movedVerified,
    run.artifacts, run.measurements, run.headRecipeSha256,
    run.inferenceContainerSha256, run.runAttestation, run.evaluatedAt,
  ), /locked charter/);
});

test("hard clinical, subgroup, deployment, and rights gates override scorecard taste", () => {
  const fixture = bakeoffFixture();
  const candidate = fixture.candidates.find((item) =>
    item.candidateId === "engineered-acoustic-baseline")!;
  const unsafeSamples = fixture.samples.map((sample, index) => index === 2
    ? { ...sample, pCorrect: 0.95, pError: 0.03 }
    : { ...sample, latencyMilliseconds: 900 });
  const unsafeMeasurements = measurements(100, candidate.candidateId,
    fixture.scorecardPrivateKey, fixture.charter.scorecardRubricSha256,
    { peakMemoryBytes: 2_000_000_000, modelBytes: 900_000_000 });
  const unsafeContainer = digest("unsafe-container");
  const evaluatedAt = "2026-07-10T19:00:00.000Z";
  const attestation = runAttestation(candidate, fixture.charter, {
    samples: unsafeSamples,
    thresholds: fixture.thresholds,
    artifacts: fixture.artifacts,
    measurements: unsafeMeasurements,
    headRecipeSha256: fixture.charter.identicalHeadRecipeSha256,
    inferenceContainerSha256: unsafeContainer,
    evaluatedAt,
  }, fixture.runPrivateKey);
  const result = buildAudioBakeoffCandidateResult(
    candidate,
    fixture.charter,
    unsafeSamples,
    fixture.thresholds,
    fixture.verifiedManifest,
    fixture.artifacts,
    unsafeMeasurements,
    fixture.charter.identicalHeadRecipeSha256,
    unsafeContainer,
    attestation,
    evaluatedAt,
  );
  assert.equal(result.adaptationEligible, false);
  assert.ok(result.hardGateFailures.includes("false-pass-rate"));
  assert.ok(result.hardGateFailures.includes("latency"));
  assert.ok(result.hardGateFailures.includes("memory"));
  assert.ok(result.hardGateFailures.includes("model-size"));
  assert.ok(result.hardGateFailures.includes("commercial-health-rights"));
  assert.ok(result.hardGateFailures.includes("derivative-rights"));
  assert.equal(result.weightedScore, 100);
});

test("subgroup equity uses pairwise gaps and requires both label classes", () => {
  const samples = [
    { ...sample("test-a-c1", "correct", 0.95, 0.03), subgroup: { ageBand: "a" } },
    { ...sample("test-a-c2", "correct", 0.95, 0.03), subgroup: { ageBand: "a" } },
    { ...sample("test-a-e1", "error", 0.03, 0.95), subgroup: { ageBand: "a" } },
    { ...sample("test-a-e2", "error", 0.03, 0.95), subgroup: { ageBand: "a" } },
    { ...sample("test-b-c1", "correct", 0.95, 0.03), subgroup: { ageBand: "b" } },
    { ...sample("test-b-c2", "correct", 0.95, 0.03), subgroup: { ageBand: "b" } },
    { ...sample("test-b-e1", "error", 0.95, 0.03), subgroup: { ageBand: "b" } },
    { ...sample("test-b-e2", "error", 0.03, 0.95), subgroup: { ageBand: "b" } },
  ];
  const fixture = bakeoffFixture(samples);
  const result = fixture.results.find((item) =>
    item.candidateId === "wavlm-base-plus-owned-head")!;
  assert.equal(result.maximumSubgroupRateGap, 0.5);
  assert.ok(result.hardGateFailures.includes("subgroup-rate-gap"));

  const missingClass = samples.map((entry) => entry.subgroup.ageBand === "b"
    ? { ...entry, label: "correct" as const }
    : entry);
  const missingFixture = bakeoffFixture(missingClass);
  const missingResult = missingFixture.results.find((item) =>
    item.candidateId === "wavlm-base-plus-owned-head")!;
  assert.ok(missingResult.hardGateFailures.includes("minimum-subgroup-error-samples"));
  assert.ok(missingResult.hardGateFailures.includes("subgroup-rate-unavailable"));
});

test("selection rejects missing, substituted, and caller-forged result evidence", () => {
  const fixture = bakeoffFixture();
  assert.throws(() => selectAudioBakeoffCandidates(
    fixture.charter,
    fixture.candidates.slice(1),
    fixture.results.slice(1),
  ), /exactly match the locked charter/);

  const forged = {
    ...fixture.results[0]!,
    weightedScore: 100,
  };
  assert.throws(() => selectAudioBakeoffCandidates(
    fixture.charter,
    fixture.candidates,
    [forged, ...fixture.results.slice(1)],
  ), /locally rebuilt candidate evidence/);

  assert.throws(() => selectAudioBakeoffCandidates(
    fixture.charter,
    fixture.candidates,
    [...fixture.results.slice(0, 4), fixture.results[2]!],
  ), /duplicated, or substituted/);
});

test("owned adaptation inherits the selected parent and cannot train on locked evaluation", () => {
  const fixture = bakeoffFixture();
  const parent = fixture.candidates.find((item) =>
    item.candidateId === fixture.selection.recommendedTeacherCandidateId)!;
  const parentResult = fixture.results.find((item) =>
    item.candidateId === parent.candidateId)!;
  const lineage = adaptationFixture(fixture, parent, parentResult);
  const base = lineage.manifest;
  const verified = verifyOwnedAudioAdaptation(
    base,
    parent,
    parentResult,
    fixture.selection,
    fixture.charter,
    fixture.verifiedManifest,
    lineage.trainingDataset,
    lineage.calibrationDataset,
    lineage.authorization,
    "2026-07-10T20:10:00.000Z",
  );
  assert.equal(verified.researchLineageStructurallyValid, true);
  assert.equal(verified.learnerFeedbackEligible, false);
  assert.equal(verified.productionEligible, false);

  const leakedBase = {
    ...withoutSha(base),
    trainingDatasetManifestSha256: fixture.charter.evaluationManifestSha256,
  };
  const leaked = { ...leakedBase, sha256: ownedAudioAdaptationManifestSha256(leakedBase) };
  assert.throws(() => verifyOwnedAudioAdaptation(
    leaked, parent, parentResult, fixture.selection, fixture.charter,
    fixture.verifiedManifest, lineage.trainingDataset, lineage.calibrationDataset,
    lineage.authorization, "2026-07-10T20:10:00.000Z",
  ), /lineage is incomplete or unsafe/);

  const sameOutputBase = {
    ...withoutSha(base),
    outputCheckpointSha256: parent.weights.sha256,
  };
  const sameOutput = {
    ...sameOutputBase,
    sha256: ownedAudioAdaptationManifestSha256(sameOutputBase),
  };
  assert.throws(() => verifyOwnedAudioAdaptation(
    sameOutput, parent, parentResult, fixture.selection, fixture.charter,
    fixture.verifiedManifest, lineage.trainingDataset, lineage.calibrationDataset,
    lineage.authorization, "2026-07-10T20:10:00.000Z",
  ), /lineage is incomplete or unsafe/);

  const fallback = fixture.candidates.find((item) =>
    item.candidateId === fixture.selection.fallbackCandidateId)!;
  const fallbackResult = fixture.results.find((item) =>
    item.candidateId === fallback.candidateId)!;
  const fallbackLineage = adaptationFixture(fixture, fallback, fallbackResult);
  const fallbackVerified = verifyOwnedAudioAdaptation(
    fallbackLineage.manifest,
    fallback,
    fallbackResult,
    fixture.selection,
    fixture.charter,
    fixture.verifiedManifest,
    fallbackLineage.trainingDataset,
    fallbackLineage.calibrationDataset,
    fallbackLineage.authorization,
    "2026-07-10T20:10:00.000Z",
  );
  assert.equal(fallbackVerified.researchLineageStructurallyValid, true);

  const rankThree = fixture.candidates.find((item) =>
    item.candidateId === "engineered-acoustic-baseline")!;
  const rankThreeResult = fixture.results.find((item) =>
    item.candidateId === rankThree.candidateId)!;
  const rankThreeLineage = adaptationFixture(fixture, rankThree, rankThreeResult);
  assert.throws(() => verifyOwnedAudioAdaptation(
    rankThreeLineage.manifest, rankThree, rankThreeResult, fixture.selection,
    fixture.charter, fixture.verifiedManifest, rankThreeLineage.trainingDataset,
    rankThreeLineage.calibrationDataset, rankThreeLineage.authorization,
    "2026-07-10T20:10:00.000Z",
  ), /lineage is incomplete or unsafe/);

  const evaluationSpeaker = fixture.manifest.items[0]!.speakerHash;
  const overlappingLineage = adaptationFixture(
    fixture, parent, parentResult, evaluationSpeaker,
  );
  assert.throws(() => verifyOwnedAudioAdaptation(
    overlappingLineage.manifest, parent, parentResult, fixture.selection,
    fixture.charter, fixture.verifiedManifest, overlappingLineage.trainingDataset,
    overlappingLineage.calibrationDataset, overlappingLineage.authorization,
    "2026-07-10T20:10:00.000Z",
  ), /lineage is incomplete or unsafe/);

  const futureLockedLineage = adaptationFixture(
    fixture, parent, parentResult, undefined, "2026-07-10T20:30:00.000Z",
  );
  assert.throws(() => verifyOwnedAudioAdaptation(
    futureLockedLineage.manifest, parent, parentResult, fixture.selection,
    fixture.charter, fixture.verifiedManifest, futureLockedLineage.trainingDataset,
    futureLockedLineage.calibrationDataset, futureLockedLineage.authorization,
    "2026-07-10T21:10:00.000Z",
  ), /lineage is incomplete or unsafe/);

  const earlyBase = { ...withoutSha(base), trainedAt: "2026-07-10T18:30:00.000Z" };
  const early = { ...earlyBase, sha256: ownedAudioAdaptationManifestSha256(earlyBase) };
  assert.throws(() => verifyOwnedAudioAdaptation(
    early, parent, parentResult, fixture.selection, fixture.charter,
    fixture.verifiedManifest, lineage.trainingDataset, lineage.calibrationDataset,
    lineage.authorization, "2026-07-10T20:10:00.000Z",
  ), /lineage is incomplete or unsafe/);
});

test("canonical hashes ignore candidate, charter, sample, and seed ordering", () => {
  const fixture = bakeoffFixture();
  const charter = fixture.charter;
  assert.equal(audioBakeoffCharterSha256({
    ...withoutSha(charter),
    requiredCandidateIds: [...charter.requiredCandidateIds].reverse(),
    subgroupKeys: [...charter.subgroupKeys].reverse(),
  }), charter.sha256);

  const candidate = fixture.candidates[0]!;
  const reorderedCandidate = {
    productionEligible: candidate.productionEligible,
    learnerFeedbackEligible: candidate.learnerFeedbackEligible,
    releasePosture: candidate.releasePosture,
    interface: {
      supportsConstrainedPhoneHead: candidate.interface.supportsConstrainedPhoneHead,
      usesPromptAwareDecoder: candidate.interface.usesPromptAwareDecoder,
      outputKind: candidate.interface.outputKind,
    },
    rights: {
      mobileBundling: candidate.rights.mobileBundling,
      redistribution: candidate.rights.redistribution,
      derivativeTraining: candidate.rights.derivativeTraining,
      commercialHealthInference: candidate.rights.commercialHealthInference,
      benchmarkUse: candidate.rights.benchmarkUse,
    },
    legalReviewEvidenceSha256: candidate.legalReviewEvidenceSha256,
    trainingDataLineageSha256: candidate.trainingDataLineageSha256,
    weights: {
      licenseIdentifier: candidate.weights.licenseIdentifier,
      sha256: candidate.weights.sha256,
      revision: candidate.weights.revision,
      artifactId: candidate.weights.artifactId,
    },
    code: {
      licenseIdentifier: candidate.code.licenseIdentifier,
      sha256: candidate.code.sha256,
      revision: candidate.code.revision,
      repository: candidate.code.repository,
    },
    strategy: candidate.strategy,
    role: candidate.role,
    version: candidate.version,
    candidateId: candidate.candidateId,
    schemaVersion: candidate.schemaVersion,
  } satisfies Omit<AudioBakeoffCandidateManifest, "sha256">;
  assert.equal(audioBakeoffCandidateManifestSha256(reorderedCandidate), candidate.sha256);
  assert.equal(evaluationSamplesSha256([...fixture.samples].reverse()),
    evaluationSamplesSha256(fixture.samples));

  const parent = fixture.candidates.find((item) =>
    item.candidateId === fixture.selection.recommendedTeacherCandidateId)!;
  const result = fixture.results.find((item) => item.candidateId === parent.candidateId)!;
  const adaptation = adaptationFixture(fixture, parent, result).manifest;
  assert.equal(ownedAudioAdaptationManifestSha256({
    ...withoutSha(adaptation), randomSeeds: [...adaptation.randomSeeds].reverse(),
  }), adaptation.sha256);
});

test("the bake-off CLI rebuilds selection and owned adaptation evidence", () => {
  const fixture = bakeoffFixture();
  const directory = mkdtempSync(join(tmpdir(), "audio-bakeoff-"));
  try {
    const charterPath = join(directory, "charter.json");
    const manifestPath = join(directory, "manifest.json");
    const candidatesPath = join(directory, "candidates.json");
    const runsPath = join(directory, "runs.json");
    const adaptationPath = join(directory, "adaptation.json");
    const trainingDatasetPath = join(directory, "training-dataset.json");
    const calibrationDatasetPath = join(directory, "calibration-dataset.json");
    const authorizationPath = join(directory, "authorization.json");
    writeFileSync(charterPath, JSON.stringify(fixture.charter));
    writeFileSync(manifestPath, JSON.stringify(fixture.manifest));
    writeFileSync(candidatesPath, JSON.stringify(fixture.candidates));
    writeFileSync(runsPath, JSON.stringify(fixture.runs));
    const script = fileURLToPath(new URL("./bakeoff-cli.ts", import.meta.url));
    const selected = spawnSync(process.execPath, [
      script, "select", charterPath, manifestPath, candidatesPath, runsPath,
    ], { encoding: "utf8" });
    assert.equal(selected.status, 0, selected.stderr);
    const selectedBody = JSON.parse(selected.stdout) as {
      selection: { recommendedTeacherCandidateId: string; productionEligible: boolean };
    };
    assert.equal(selectedBody.selection.recommendedTeacherCandidateId,
      "wavlm-base-plus-owned-head");
    assert.equal(selectedBody.selection.productionEligible, false);

    const extraThresholdField = fixture.runs.map((run, index) => index === 0
      ? { ...run, thresholds: { ...run.thresholds, unsupported: true } }
      : run);
    writeFileSync(runsPath, JSON.stringify(extraThresholdField));
    const strict = spawnSync(process.execPath, [
      script, "select", charterPath, manifestPath, candidatesPath, runsPath,
    ], { encoding: "utf8" });
    assert.equal(strict.status, 1);
    assert.match(strict.stderr, /strict schema/);
    writeFileSync(runsPath, JSON.stringify(fixture.runs));

    const parent = fixture.candidates.find((item) =>
      item.candidateId === fixture.selection.recommendedTeacherCandidateId)!;
    const parentResult = fixture.results.find((item) =>
      item.candidateId === parent.candidateId)!;
    const lineage = adaptationFixture(fixture, parent, parentResult);
    writeFileSync(adaptationPath, JSON.stringify(lineage.manifest));
    writeFileSync(trainingDatasetPath, JSON.stringify(lineage.trainingDataset));
    writeFileSync(calibrationDatasetPath, JSON.stringify(lineage.calibrationDataset));
    writeFileSync(authorizationPath, JSON.stringify(lineage.authorization));
    const adapted = spawnSync(process.execPath, [
      script, "adaptation", charterPath, manifestPath, candidatesPath, runsPath,
      adaptationPath, trainingDatasetPath, calibrationDatasetPath, authorizationPath,
      "2026-07-10T20:10:00.000Z",
    ], { encoding: "utf8" });
    assert.equal(adapted.status, 0, adapted.stderr);
    const adaptedBody = JSON.parse(adapted.stdout) as {
      status: string;
      productionEligible: boolean;
    };
    assert.equal(adaptedBody.status, "verified-research-adaptation-lineage");
    assert.equal(adaptedBody.productionEligible, false);

    writeFileSync(runsPath, "not-json");
    const malformed = spawnSync(process.execPath, [
      script, "select", charterPath, manifestPath, candidatesPath, runsPath,
    ], { encoding: "utf8" });
    assert.equal(malformed.status, 1);
    assert.match(malformed.stderr, /Audio bake-off failed/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

function bakeoffFixture(samples: EvaluationSample[] = goodSamples()) {
  const manifestItems: EvaluationManifestItem[] = [
    item("train-001", "train", 1),
    item("calibration-001", "calibration", 2),
    ...samples.map((sample, index) => item(sample.attemptId, "test", index + 3)),
  ];
  const manifest: LockedEvaluationManifest = {
    version: "audio-bakeoff-dataset-v1",
    sha256: evaluationManifestSha256(manifestItems),
    lockedAt: "2026-07-10T18:00:00.000Z",
    items: manifestItems,
  };
  const verifiedManifest = validateLockedEvaluationManifest(manifest);
  const candidates = [
    candidateManifest("wav2vec2-phone-ctc-owned-head", "primary-baseline"),
    candidateManifest("wavlm-base-plus-owned-head", "challenger"),
    candidateManifest("engineered-acoustic-baseline", "framework", {
      commercialHealthInference: "unverified",
      derivativeTraining: "unverified",
    }, "owned-engineered-feature-baseline", "engineered-features"),
    candidateManifest("whisper-reference", "reference", {
      commercialHealthInference: "restricted",
      derivativeTraining: "restricted",
      }, "reference-only", "transcript", true, false),
    candidateManifest("gopt-reference", "reference", {
      commercialHealthInference: "unverified",
      derivativeTraining: "unverified",
    }, "reference-only", "aligned-embeddings", false, false),
  ] as const;
  const thresholds: EvaluationThresholds = {
    version: "bakeoff-thresholds-v1",
    passThreshold: 0.8,
    analysisThreshold: 0.8,
  };
  const scorecardKeys = generateKeyPairSync("ed25519");
  const runKeys = generateKeyPairSync("ed25519");
  const adaptationKeys = generateKeyPairSync("ed25519");
  const candidateManifestSha256ById = Object.fromEntries(candidates.map((candidate) =>
    [candidate.candidateId, candidate.sha256]));
  const candidateRoleById = Object.fromEntries(candidates.map((candidate) =>
    [candidate.candidateId, candidate.role]));
  const charterBase = {
    schemaVersion: "audio-bakeoff-charter-v1" as const,
    version: "frozen-encoder-bakeoff-v1",
    lockedAt: "2026-07-10T18:05:00.000Z",
    evaluationManifestSha256: manifest.sha256,
    evaluationManifestEnvelopeSha256: lockedEvaluationManifestEnvelopeSha256(manifest),
    evaluationReferenceSha256: evaluationReferenceSha256(samples),
    stage: "frozen-encoder-owned-head" as const,
    requiredCandidateIds: [
      "wav2vec2-phone-ctc-owned-head",
      "wavlm-base-plus-owned-head",
      "engineered-acoustic-baseline",
    ],
    referenceCandidateIds: ["whisper-reference", "gopt-reference"],
    candidateManifestSha256ById,
    candidateRoleById,
    subgroupKeys: ["ageBand"],
    thresholdVersion: thresholds.version,
    thresholdsSha256: evaluationThresholdsSha256(thresholds),
    lexiconVersion: "bilabial-lexicon-v1",
    scoringPolicyVersion: "constrained-phone-policy-v1",
    identicalHeadRecipeSha256: digest("identical-head-recipe"),
    calibrationRecipeSha256: digest("locked-calibration-recipe"),
    deploymentProtocolSha256: digest("locked-device-profiling-protocol"),
    labelPolicySha256: digest("slp-label-policy"),
    scorecardRubricSha256: digest("locked-scorecard-rubric"),
    scorecardAuthority: {
      keyId: "scorecard-authority-v1",
      publicKeyPem: scorecardKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    },
    runAuthority: {
      keyId: "run-authority-v1",
      publicKeyPem: runKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    },
    adaptationAuthority: {
      keyId: "adaptation-authority-v1",
      publicKeyPem: adaptationKeys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    },
    legalPolicyVersion: "open-source-intake-v1",
    minimumTestSamples: samples.length,
    minimumSubgroupSamples: 4,
    minimumSubgroupCorrectSamples: 2,
    minimumSubgroupErrorSamples: 2,
    gates: {
      maximumFalsePassRate: 0.05,
      maximumFalseRejectRate: 0.1,
      maximumAbstentionRate: 0.25,
      maximumConditionalEce: 0.2,
      maximumSubgroupRateGap: 0.1,
      maximumP95LatencyMilliseconds: 500,
      maximumColdStartMilliseconds: 1_000,
      maximumAverageCostUsd: 0.01,
      maximumPeakMemoryBytes: 1_000_000_000,
      maximumModelBytes: 500_000_000,
    },
    weights: {
      clinicalTaskFit: 0.25,
      childDomainFit: 0.2,
      safetyEquityEvidence: 0.15,
      commercialLegalFit: 0.15,
      deploymentFit: 0.1,
      interpretability: 0.1,
      maintenance: 0.05,
    },
  };
  const charter: AudioBakeoffCharter = {
    ...charterBase,
    sha256: audioBakeoffCharterSha256(charterBase),
  };
  const artifacts: EvaluationArtifactVersions = {
    lexiconVersion: charter.lexiconVersion,
    calibrationVersion: "candidate-calibration-v1",
    scoringPolicyVersion: charter.scoringPolicyVersion,
  };
  const scores = [85, 92, 76, 99, 88];
  const runs = candidates.map((candidate, index) => {
    const unsignedRun = {
      candidateId: candidate.candidateId,
      samples: samples.map((sample) => ({
        ...sample,
        latencyMilliseconds: 100 + index * 20,
      })),
      thresholds,
      artifacts: { ...artifacts, calibrationVersion: `candidate-calibration-v${index + 1}` },
      measurements: measurements(scores[index]!, candidate.candidateId,
        scorecardKeys.privateKey, charter.scorecardRubricSha256),
      headRecipeSha256: charter.identicalHeadRecipeSha256,
      inferenceContainerSha256: digest(`container-${candidate.candidateId}`),
      evaluatedAt: `2026-07-10T19:0${index}:00.000Z`,
    };
    return {
      ...unsignedRun,
      runAttestation: runAttestation(candidate, charter, unsignedRun, runKeys.privateKey),
    };
  });
  const results = candidates.map((candidate, index) => {
    const run = runs[index]!;
    return buildAudioBakeoffCandidateResult(
      candidate, charter, run.samples, run.thresholds, verifiedManifest,
      run.artifacts, run.measurements, run.headRecipeSha256,
      run.inferenceContainerSha256, run.runAttestation, run.evaluatedAt,
    );
  });
  const selection = selectAudioBakeoffCandidates(charter, candidates, results);
  return {
    manifest,
    verifiedManifest,
    charter,
    candidates,
    samples,
    thresholds,
    artifacts,
    runs,
    results,
    selection,
    scorecardPrivateKey: scorecardKeys.privateKey,
    runPrivateKey: runKeys.privateKey,
    adaptationPrivateKey: adaptationKeys.privateKey,
  };
}

function candidateManifest(
  candidateId: string,
  role: AudioBakeoffCandidateManifest["role"],
  rightsOverrides: Partial<AudioBakeoffCandidateManifest["rights"]> = {},
  strategy: AudioBakeoffCandidateManifest["strategy"] = "frozen-open-encoder-owned-head",
  outputKind: AudioBakeoffCandidateManifest["interface"]["outputKind"] = "phone-posteriors",
  usesPromptAwareDecoder = false,
  supportsConstrainedPhoneHead = true,
): AudioBakeoffCandidateManifest {
  const base = {
    schemaVersion: "audio-bakeoff-candidate-v1" as const,
    candidateId,
    version: "1.0.0",
    role,
    strategy,
    code: {
      repository: `https://example.invalid/${candidateId}`,
      revision: "revision-0001",
      sha256: digest(`code-${candidateId}`),
      licenseIdentifier: "reviewed-license",
    },
    weights: {
      artifactId: `weights-${candidateId}`,
      revision: "weights-revision-0001",
      sha256: digest(`weights-${candidateId}`),
      licenseIdentifier: "reviewed-weights-license",
    },
    trainingDataLineageSha256: digest(`lineage-${candidateId}`),
    legalReviewEvidenceSha256: digest(`legal-${candidateId}`),
    rights: {
      benchmarkUse: "approved" as const,
      commercialHealthInference: "approved" as const,
      derivativeTraining: "approved" as const,
      redistribution: "unverified" as const,
      mobileBundling: "unverified" as const,
      ...rightsOverrides,
    },
    interface: {
      outputKind,
      usesPromptAwareDecoder,
      supportsConstrainedPhoneHead,
    },
    releasePosture: "research-candidate-only" as const,
    learnerFeedbackEligible: false as const,
    productionEligible: false as const,
  };
  return { ...base, sha256: audioBakeoffCandidateManifestSha256(base) };
}

function measurements(
  score: number,
  candidateId: string,
  privateKey: KeyObject,
  rubricSha256: string,
  overrides: Partial<Pick<AudioBakeoffMeasurements, "modelBytes" | "peakMemoryBytes">> = {},
): AudioBakeoffMeasurements {
  const unsigned = {
    rubricSha256,
    scorerKeyId: "scorecard-authority-v1",
    scores: {
      clinicalTaskFit: score,
      childDomainFit: score,
      safetyEquityEvidence: score,
      commercialLegalFit: score,
      deploymentFit: score,
      interpretability: score,
      maintenance: score,
    },
    evidence: {
      clinicalTaskFit: digest(`task-${score}`),
      childDomainFit: digest(`domain-${score}`),
      safetyEquityEvidence: digest(`safety-${score}`),
      commercialLegalFit: digest(`legal-${score}`),
      deploymentFit: digest(`deployment-${score}`),
      interpretability: digest(`interpretability-${score}`),
      maintenance: digest(`maintenance-${score}`),
    },
  };
  return {
    modelBytes: overrides.modelBytes ?? 300_000_000,
    peakMemoryBytes: overrides.peakMemoryBytes ?? 700_000_000,
    coldStartMilliseconds: 250,
    scorecard: {
      ...unsigned,
      signatureBase64: sign(null,
        Buffer.from(scorecardAttestationPayload(candidateId, unsigned), "utf8"),
        privateKey).toString("base64"),
    },
  };
}

function runAttestation(
  candidate: AudioBakeoffCandidateManifest,
  charter: AudioBakeoffCharter,
  run: {
    samples: readonly EvaluationSample[];
    thresholds: EvaluationThresholds;
    artifacts: EvaluationArtifactVersions;
    measurements: AudioBakeoffMeasurements;
    headRecipeSha256: string;
    inferenceContainerSha256: string;
    evaluatedAt: string;
  },
  privateKey: KeyObject,
): AudioBakeoffRunAttestation {
  const unsigned = {
    keyId: charter.runAuthority.keyId,
    algorithm: "Ed25519" as const,
    calibrationArtifactSha256: digest(`calibration-artifact-${candidate.candidateId}`),
    calibrationManifestSha256: charter.evaluationManifestEnvelopeSha256,
    calibrationRecipeSha256: charter.calibrationRecipeSha256,
    deploymentProtocolSha256: charter.deploymentProtocolSha256,
  };
  const evidence = {
    charterSha256: charter.sha256,
    candidateId: candidate.candidateId,
    candidateManifestSha256: candidate.sha256,
    evaluationManifestSha256: charter.evaluationManifestSha256,
    evaluationReferenceSha256: charter.evaluationReferenceSha256,
    sampleEvidenceSha256: evaluationSamplesSha256(run.samples),
    thresholdsSha256: evaluationThresholdsSha256(run.thresholds),
    artifacts: run.artifacts,
    measurements: run.measurements,
    headRecipeSha256: run.headRecipeSha256,
    inferenceContainerSha256: run.inferenceContainerSha256,
    evaluatedAt: run.evaluatedAt,
  };
  return {
    ...unsigned,
    signatureBase64: sign(null,
      Buffer.from(audioBakeoffRunAttestationPayload(evidence, unsigned), "utf8"),
      privateKey).toString("base64"),
  };
}

function goodSamples(): EvaluationSample[] {
  return [
    sample("test-001", "correct", 0.95, 0.03),
    sample("test-002", "correct", 0.9, 0.05),
    sample("test-003", "error", 0.03, 0.95),
    sample("test-004", "error", 0.05, 0.9),
  ];
}

function sample(
  attemptId: string,
  label: "correct" | "error",
  pCorrect: number,
  pError: number,
): EvaluationSample {
  return {
    attemptId,
    label,
    pCorrect,
    pError,
    ambiguous: false,
    latencyMilliseconds: 100,
    estimatedCostUsd: 0.002,
    subgroup: { ageBand: "all" },
  };
}

function item(
  attemptId: string,
  split: EvaluationManifestItem["split"],
  index: number,
): EvaluationManifestItem {
  return {
    attemptId,
    speakerHash: digest(`speaker-${index}`),
    householdHash: digest(`household-${index}`),
    split,
    targetProtocolId: "bilabial-closure-v1",
  };
}

function adaptationFixture(
  fixture: {
    charter: AudioBakeoffCharter;
    selection: ReturnType<typeof selectAudioBakeoffCandidates>;
    adaptationPrivateKey: KeyObject;
  },
  parent: AudioBakeoffCandidateManifest,
  parentResult: ReturnType<typeof buildAudioBakeoffCandidateResult>,
  trainingSpeakerOverride?: string,
  datasetLockedAt = "2026-07-10T19:15:00.000Z",
): {
  manifest: OwnedAudioAdaptationManifest;
  trainingDataset: AudioAdaptationDatasetManifest;
  calibrationDataset: AudioAdaptationDatasetManifest;
  authorization: AudioAdaptationAuthorization;
} {
  const consentSnapshotSha256 = digest("current-training-consent");
  const deletionLedgerSha256 = digest("current-deletion-ledger");
  const trainingDataset = adaptationDataset("training", 100,
    fixture.charter.labelPolicySha256, consentSnapshotSha256, deletionLedgerSha256,
    trainingSpeakerOverride, datasetLockedAt);
  const calibrationDataset = adaptationDataset("calibration", 200,
    fixture.charter.labelPolicySha256, consentSnapshotSha256, deletionLedgerSha256,
    undefined, datasetLockedAt);
  const unsignedAuthorization = {
    schemaVersion: "audio-adaptation-authorization-v1" as const,
    keyId: fixture.charter.adaptationAuthority.keyId,
    algorithm: "Ed25519" as const,
    parentSelectionReportSha256: fixture.selection.sha256,
    parentBakeoffResultSha256: parentResult.sha256,
    trainingDatasetManifestSha256: trainingDataset.sha256,
    calibrationDatasetManifestSha256: calibrationDataset.sha256,
    consentSnapshotSha256,
    deletionLedgerSha256,
    labelPolicySha256: fixture.charter.labelPolicySha256,
    authorizedAt: "2026-07-10T19:30:00.000Z",
    expiresAt: "2026-07-10T21:00:00.000Z",
  };
  const signedAuthorization = {
    ...unsignedAuthorization,
    signatureBase64: sign(null,
      Buffer.from(audioAdaptationAuthorizationPayload(unsignedAuthorization), "utf8"),
      fixture.adaptationPrivateKey).toString("base64"),
  };
  const authorization: AudioAdaptationAuthorization = {
    ...signedAuthorization,
    sha256: audioAdaptationAuthorizationSha256(signedAuthorization),
  };
  const base = {
    schemaVersion: "owned-audio-adaptation-manifest-v1" as const,
    version: "owned-child-bilabial-adaptation-v1",
    strategy: "parameter-efficient" as const,
    parentCandidateManifestSha256: parent.sha256,
    parentBakeoffResultSha256: parentResult.sha256,
    parentSelectionReportSha256: fixture.selection.sha256,
    trainingDatasetManifestSha256: trainingDataset.sha256,
    calibrationDatasetManifestSha256: calibrationDataset.sha256,
    consentSnapshotSha256,
    deletionLedgerSha256,
    authorizationSha256: authorization.sha256,
    labelPolicySha256: fixture.charter.labelPolicySha256,
    trainingRecipeSha256: digest("owned-training-recipe"),
    trainingCodeSha256: digest("owned-training-code"),
    trainingContainerSha256: digest("owned-training-container"),
    outputCheckpointSha256: digest("owned-output-checkpoint"),
    randomSeeds: [11, 29, 47],
    trainedAt: "2026-07-10T20:00:00.000Z",
    releasePosture: "research-adaptation-only" as const,
    learnerFeedbackEligible: false as const,
    productionEligible: false as const,
  };
  return {
    manifest: { ...base, sha256: ownedAudioAdaptationManifestSha256(base) },
    trainingDataset,
    calibrationDataset,
    authorization,
  };
}

function adaptationDataset(
  purpose: AudioAdaptationDatasetManifest["purpose"],
  index: number,
  labelPolicySha256: string,
  consentSnapshotSha256: string,
  deletionLedgerSha256: string,
  firstSpeakerOverride?: string,
  lockedAt = "2026-07-10T19:15:00.000Z",
): AudioAdaptationDatasetManifest {
  const base = {
    schemaVersion: "audio-adaptation-dataset-manifest-v1" as const,
    version: `${purpose}-dataset-v1`,
    purpose,
    lockedAt,
    labelPolicySha256,
    consentSnapshotSha256,
    deletionLedgerSha256,
    items: [1, 2].map((offset) => ({
      attemptId: `${purpose}-attempt-${offset}`,
      speakerHash: offset === 1 && firstSpeakerOverride
        ? firstSpeakerOverride
        : digest(`${purpose}-speaker-${index + offset}`),
      householdHash: digest(`${purpose}-household-${index + offset}`),
      deletionSubjectHash: digest(`${purpose}-subject-${index + offset}`),
      consentSnapshotHash: digest(`${purpose}-consent-${index + offset}`),
    })),
  };
  return { ...base, sha256: audioAdaptationDatasetManifestSha256(base) };
}

function withoutSha<T extends { readonly sha256: string }>(value: T): Omit<T, "sha256"> {
  const { sha256: _sha256, ...rest } = value;
  return rest;
}

function digest(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
