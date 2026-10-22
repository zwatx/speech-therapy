import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  auditUnsupportedFeedbackClaims,
  authorizeFeedbackResearchEvaluation,
  feedbackAttemptStateSha256,
  feedbackReleaseCandidateSha256,
  feedbackReleaseEvidenceSha256,
  feedbackTemplateCatalogSha256,
  feedbackTemplateSha256,
  feedbackTargetProtocolRegistrySha256,
  simulateFeedbackSelection,
  unsupportedClaimAuditReportSha256,
  type FeedbackAuditSample,
  type FeedbackAuditScenario,
  type FeedbackAttemptState,
  type FeedbackEvidenceKind,
  type FeedbackReleaseCandidate,
  type FeedbackReleaseEvidence,
  type FeedbackSelectionRequest,
  type FeedbackTemplate,
  type FeedbackTemplateCatalog,
} from "./feedback.ts";
import { targetProtocolRegistry } from "./protocols.ts";
import { defaultThresholdPolicy } from "./routing.ts";
import type { AttemptEvaluationRequest, TargetProtocolRegistry } from "./types.ts";

test("a zero-finding audit can authorize only an exact validated research fixture", () => {
  const fixture = feedbackFixture();

  assert.equal(fixture.audit.zeroDetectedPolicyViolations, true);
  assert.equal(fixture.audit.policyViolationCount, 0);
  assert.equal(fixture.audit.releaseSampleCount, 9);
  assert.equal(fixture.audit.coveredTemplateCount, 4);
  assert.equal(fixture.audit.researchOnly, true);
  assert.equal(fixture.audit.learnerFeedbackEligible, false);
  assert.equal(fixture.audit.productionGateEligible, false);

  const release = authorizeFeedbackResearchEvaluation(
    fixture.catalog,
    fixture.candidate,
    fixture.evidence,
    fixture.audit,
    fixture.samples,
    fixture.registry,
    "2026-07-10T18:30:00.000Z",
  );
  assert.equal(release.learnerFeedbackEligible, false);
  assert.equal(release.productionGateEligible, false);
  assert.equal(release.releasePosture, "research-simulation-only");
  assert.equal(release.candidate.sha256, fixture.candidate.sha256);
});

test("the shipped candidate protocol can never authorize learner feedback", () => {
  const fixture = feedbackFixture();
  assert.equal(targetProtocolRegistry.protocols["bilabial-closure-v1"].status, "candidate");
  const candidateBase = {
    ...withoutSha(fixture.candidate),
    protocolRegistryVersion: targetProtocolRegistry.version,
    protocolRegistrySha256: feedbackTargetProtocolRegistrySha256(targetProtocolRegistry),
  };
  const candidate = { ...candidateBase, sha256: feedbackReleaseCandidateSha256(candidateBase) };
  const samples = fixture.samples.map((sample) => ({
    ...sample,
    candidateSha256: candidate.sha256,
  }));
  const audit = auditUnsupportedFeedbackClaims(
    fixture.catalog,
    candidate,
    targetProtocolRegistry,
    samples,
    "2026-07-10T18:10:00.000Z",
  );
  const evidence = releaseEvidence(candidate, audit.sha256);
  assert.throws(() => authorizeFeedbackResearchEvaluation(
    fixture.catalog,
    candidate,
    evidence,
    audit,
    samples,
    targetProtocolRegistry,
    "2026-07-10T18:30:00.000Z",
  ), /validated target protocol registry/);
});

test("selection binds one static template to evidence and enforces retry limits", () => {
  const fixture = feedbackFixture();
  const release = authorizeFixture(fixture);

  const correct = simulateFeedbackSelection(release, selection(fixture, "correct"));
  assert.equal(correct.action, "show-template");
  if (correct.action === "show-template") {
    assert.equal(correct.template.kind, "positive-reinforcement");
    assert.equal(correct.cueAction, "none");
  }

  const uncertain = simulateFeedbackSelection(release, selection(fixture, "uncertain"));
  assert.equal(uncertain.action, "show-template");
  if (uncertain.action === "show-template") {
    assert.equal(uncertain.template.kind, "neutral-retry");
  }
  const uncertainLimit = simulateFeedbackSelection(
    release,
    withState(selection(fixture, "uncertain"), { uncertainRetryCount: 2 }),
  );
  assert.equal(uncertainLimit.action, "show-template");
  if (uncertainLimit.action === "show-template") {
    assert.equal(uncertainLimit.template.kind, "move-on");
    assert.equal(uncertainLimit.flagClinicianReview, true);
  }

  const captureLimit = simulateFeedbackSelection(
    release,
    withState(selection(fixture, "capture"), { captureRetryCount: 2 }),
  );
  assert.equal(captureLimit.action, "show-template");
  if (captureLimit.action === "show-template") {
    assert.equal(captureLimit.template.kind, "move-on");
    assert.equal(captureLimit.flagClinicianReview, true);
  }

  const correction = simulateFeedbackSelection(release, selection(fixture, "mismatch"));
  assert.equal(correction.action, "show-template");
  if (correction.action === "show-template") {
    assert.equal(correction.template.kind, "corrective-cue");
    assert.equal(correction.cueAction, "bilabial-closure");
    assert.equal(correction.template.body, "Close both lips before the sound, then try once more.");
  }
  const replayedCorrection = simulateFeedbackSelection(
    release,
    selection(fixture, "mismatch"),
  );
  assert.equal(replayedCorrection.action, "show-template");
  if (correction.action === "show-template" && replayedCorrection.action === "show-template") {
    assert.equal(
      replayedCorrection.selectionReceiptSha256,
      correction.selectionReceiptSha256,
    );
  }
  const correctionLimit = simulateFeedbackSelection(
    release,
    withState(selection(fixture, "mismatch"), { correctiveCueCount: 2 }),
  );
  assert.equal(correctionLimit.action, "show-template");
  if (correctionLimit.action === "show-template") {
    assert.equal(correctionLimit.template.kind, "move-on");
  }

  const uncertainVision = simulateFeedbackSelection(release, {
    ...selection(fixture, "mismatch"),
    modelVisualOutcome: "indeterminate",
  });
  assert.deepEqual(uncertainVision,
    { action: "abstain", reason: "visual-evidence-insufficient" });

  const distress = simulateFeedbackSelection(
    release,
    withState(selection(fixture, "mismatch"), { distressObserved: true }),
  );
  assert.equal(distress.action, "show-template");
  if (distress.action === "show-template") assert.equal(distress.template.kind, "move-on");

  const expired = simulateFeedbackSelection(release, {
    ...selection(fixture, "correct"),
    selectedAt: fixture.candidate.expiresAt,
  });
  assert.deepEqual(expired,
    { action: "abstain", reason: "feedback-release-unavailable" });

  const wrongPopulation = simulateFeedbackSelection(release, {
    ...selection(fixture, "correct"),
    population: { ...fixture.candidate.population, ageBand: "13-17" },
  });
  assert.deepEqual(wrongPopulation,
    { action: "abstain", reason: "feedback-release-unavailable" });

  const substitutedRoute = simulateFeedbackSelection(release, {
    ...selection(fixture, "correct"),
    modelVisualOutcome: "closure-not-observed",
  });
  assert.equal(substitutedRoute.action, "show-template");
  if (substitutedRoute.action === "show-template") {
    assert.equal(substitutedRoute.template.kind, "positive-reinforcement");
    assert.equal(substitutedRoute.cueAction, "none");
  }

  const repeatedCue = simulateFeedbackSelection(
    release,
    withState(selection(fixture, "mismatch"), { cueAlreadyEmittedForAttempt: true }),
  );
  assert.deepEqual(repeatedCue, { action: "abstain", reason: "cue-already-emitted" });
});

test("claim audit detects hidden anatomy, diagnosis, dynamic copy, and unsupported cues", () => {
  assert.throws(() => feedbackFixture({
    correctiveBody: "Your tongue did not touch the roof of your mouth because your speech is wrong.",
  }), /feedback template catalog/);
  assert.throws(() => feedbackFixture({
    correctiveClaims: ["target-observation"],
  }), /feedback template catalog/);

  const fixture = feedbackFixture();
  const unsafeSamples = fixture.samples.map((sample) => {
    if (sample.templateId.includes("corrective")) {
      return {
        ...sample,
        modelVisualOutcome: "closure-observed" as const,
        renderedBody: `${sample.renderedBody} You have a speech disorder.`,
      };
    }
    return sample.templateId.includes("neutral")
      ? { ...sample, uncertainRetryCountBefore: 2 }
      : sample;
  });
  const report = auditUnsupportedFeedbackClaims(
    fixture.catalog,
    fixture.candidate,
    fixture.registry,
    unsafeSamples,
    "2026-07-10T18:10:00.000Z",
  );
  assert.ok(report.findings.some((item) => item.code === "forbidden-diagnostic-language"));
  assert.ok(report.findings.some((item) => item.code === "undeclared-rendered-copy"));
  assert.ok(report.findings.some(
    (item) => item.code === "cue-without-supported-visual-evidence"));
  assert.ok(report.findings.some((item) => item.code === "retry-budget-exceeded"));

  const substitutedAttempts = fixture.samples.map((sample) =>
    sample.templateId.includes("corrective")
      ? { ...sample, attempt: attempt("correct") }
      : sample);
  const substitutedReport = auditUnsupportedFeedbackClaims(
    fixture.catalog,
    fixture.candidate,
    fixture.registry,
    substitutedAttempts,
    "2026-07-10T18:10:00.000Z",
  );
  assert.ok(substitutedReport.findings.some((item) => item.code === "evidence-mismatch"));

  const sameVersionTamper: TargetProtocolRegistry = {
    ...fixture.registry,
    protocols: {
      ...fixture.registry.protocols,
      "bilabial-closure-v1": {
        ...fixture.registry.protocols["bilabial-closure-v1"],
        label: "Substituted protocol",
      },
    },
  };
  assert.throws(() => auditUnsupportedFeedbackClaims(
    fixture.catalog,
    fixture.candidate,
    sameVersionTamper,
    fixture.samples,
    "2026-07-10T18:10:00.000Z",
  ), /registry does not match/);
});

test("authorization rejects incomplete coverage, stale evidence, tampering, and expiry", () => {
  const fixture = feedbackFixture();
  const incompleteAudit = auditUnsupportedFeedbackClaims(
    fixture.catalog,
    fixture.candidate,
    fixture.registry,
    fixture.samples.slice(1),
    "2026-07-10T18:10:00.000Z",
  );
  const incompleteEvidence = releaseEvidence(fixture.candidate, incompleteAudit.sha256);
  assert.throws(() => authorizeFeedbackResearchEvaluation(
    fixture.catalog, fixture.candidate, incompleteEvidence, incompleteAudit,
    fixture.samples.slice(1),
    fixture.registry, "2026-07-10T18:30:00.000Z",
  ), /complete zero-finding claim audit/);

  const swappedSamples = fixture.samples.map((sample, index) => index === 0
    ? { ...sample, sampleId: "feedback-audit-substituted-cohort" }
    : sample);
  assert.throws(() => authorizeFeedbackResearchEvaluation(
    fixture.catalog,
    fixture.candidate,
    fixture.evidence,
    fixture.audit,
    swappedSamples,
    fixture.registry,
    "2026-07-10T18:30:00.000Z",
  ), /complete zero-finding claim audit/);

  assert.throws(() => authorizeFeedbackResearchEvaluation(
    fixture.catalog,
    fixture.candidate,
    { ...fixture.evidence, usabilityEvidenceSha256: digest("tampered") },
    fixture.audit,
    fixture.samples,
    fixture.registry,
    "2026-07-10T18:30:00.000Z",
  ), /Complete hash-bound feedback release evidence/);

  assert.throws(() => authorizeFeedbackResearchEvaluation(
    fixture.catalog, fixture.candidate, fixture.evidence, fixture.audit,
    fixture.samples,
    fixture.registry, "2026-07-11T18:00:00.000Z",
  ), /stale or chronologically invalid/);

  const extra = { ...fixture.samples[0]!, diagnosis: "not allowed" } as FeedbackAuditSample;
  assert.throws(() => auditUnsupportedFeedbackClaims(
    fixture.catalog,
    fixture.candidate,
    fixture.registry,
    [extra, ...fixture.samples.slice(1)],
    "2026-07-10T18:10:00.000Z",
  ), /strict evidence schema/);

  const unsafeSamples = fixture.samples.map((sample) => sample.templateId.includes("corrective")
    ? { ...sample, renderedBody: `${sample.renderedBody} You have a speech disorder.` }
    : sample);
  const unsafeAudit = auditUnsupportedFeedbackClaims(
    fixture.catalog,
    fixture.candidate,
    fixture.registry,
    unsafeSamples,
    "2026-07-10T18:10:00.000Z",
  );
  const forgedBase = {
    ...withoutSha(unsafeAudit),
    policyViolationCount: 0,
    findings: [],
    zeroDetectedPolicyViolations: true,
  };
  const forgedAudit = {
    ...forgedBase,
    sha256: unsupportedClaimAuditReportSha256(forgedBase),
  };
  const forgedEvidence = releaseEvidence(fixture.candidate, forgedAudit.sha256);
  assert.throws(() => authorizeFeedbackResearchEvaluation(
    fixture.catalog,
    fixture.candidate,
    forgedEvidence,
    forgedAudit,
    unsafeSamples,
    fixture.registry,
    "2026-07-10T18:30:00.000Z",
  ), /complete zero-finding claim audit/);
});

test("a caller cannot forge the opaque release boundary", () => {
  const fixture = feedbackFixture();
  const forged = {
    catalog: fixture.catalog,
    candidate: fixture.candidate,
    evidence: fixture.evidence,
    authorizedAt: "2026-07-10T18:30:00.000Z",
    learnerFeedbackEligible: false,
  } as unknown as Parameters<typeof simulateFeedbackSelection>[0];
  assert.deepEqual(simulateFeedbackSelection(forged, selection(fixture, "mismatch")),
    { action: "abstain", reason: "feedback-release-unavailable" });
});

test("the feedback audit CLI emits a machine-readable report and fails unsafe releases", () => {
  const fixture = feedbackFixture();
  const directory = mkdtempSync(join(tmpdir(), "feedback-audit-"));
  try {
    const catalogPath = join(directory, "catalog.json");
    const candidatePath = join(directory, "candidate.json");
    const registryPath = join(directory, "registry.json");
    const samplesPath = join(directory, "samples.json");
    writeFileSync(catalogPath, JSON.stringify(fixture.catalog));
    writeFileSync(candidatePath, JSON.stringify(fixture.candidate));
    writeFileSync(registryPath, JSON.stringify(fixture.registry));
    writeFileSync(samplesPath, JSON.stringify(fixture.samples));
    const script = fileURLToPath(new URL("./feedback-audit-cli.ts", import.meta.url));
    const safe = spawnSync(process.execPath, [
      script, catalogPath, candidatePath, registryPath, samplesPath,
      "2026-07-10T18:10:00.000Z",
    ], { encoding: "utf8" });
    assert.equal(safe.status, 0, safe.stderr);
    const safeReport = JSON.parse(safe.stdout) as { zeroDetectedPolicyViolations: boolean };
    assert.equal(safeReport.zeroDetectedPolicyViolations, true);

    const unsafe = fixture.samples.map((sample) => sample.templateId.includes("corrective")
      ? { ...sample, renderedBody: `${sample.renderedBody} The cause is your jaw.` }
      : sample);
    writeFileSync(samplesPath, JSON.stringify(unsafe));
    const failed = spawnSync(process.execPath, [
      script, catalogPath, candidatePath, registryPath, samplesPath,
      "2026-07-10T18:10:00.000Z",
    ], { encoding: "utf8" });
    assert.equal(failed.status, 3, failed.stderr);
    const failedReport = JSON.parse(failed.stdout) as { policyViolationCount: number };
    assert.ok(failedReport.policyViolationCount > 0);

    writeFileSync(samplesPath, "not-json");
    const malformed = spawnSync(process.execPath, [
      script, catalogPath, candidatePath, registryPath, samplesPath,
      "2026-07-10T18:10:00.000Z",
    ], { encoding: "utf8" });
    assert.equal(malformed.status, 1);
    assert.match(malformed.stderr, /Feedback audit failed/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

function feedbackFixture(options: {
  correctiveBody?: string;
  correctiveClaims?: FeedbackTemplate["claims"];
} = {}) {
  const templates = [
    template("feedback-positive-v1", "positive-reinforcement",
      ["confident-correct"], "Nice work", "You made the beginning sound clearly.",
      ["effort-reinforcement", "target-observation"]),
    template("feedback-neutral-retry-v1", "neutral-retry",
      ["capture-quality-below-floor", "audio-evidence-uncertain"],
      "Let’s try once more", "I couldn’t get a clear read. Say the word one more time.",
      ["capture-uncertainty"]),
    template("feedback-corrective-bilabial-v1", "corrective-cue",
      ["bilabial-nonclosure"], "Try one small change",
      options.correctiveBody ?? "Close both lips before the sound, then try once more.",
      options.correctiveClaims ?? ["practice-instruction"]),
    template("feedback-move-on-v1", "move-on",
      ["retry-budget-exhausted", "distress-or-stop"],
      "Let’s move on", "We’ll save this one for your speech teacher and try the next word.",
      ["clinician-review", "effort-reinforcement"]),
  ];
  const catalogBase = {
    schemaVersion: "feedback-template-catalog-v1" as const,
    version: "bilabial-feedback-catalog-v1",
    locale: "en-US" as const,
    releasePosture: "candidate-only" as const,
    learnerFeedbackEligible: false as const,
    templates,
  };
  const catalog: FeedbackTemplateCatalog = {
    ...catalogBase,
    sha256: feedbackTemplateCatalogSha256(catalogBase),
  };
  const registry: TargetProtocolRegistry = {
    ...targetProtocolRegistry,
    version: "feedback-evaluation-registry-v1",
    protocols: {
      ...targetProtocolRegistry.protocols,
      "bilabial-closure-v1": {
        ...targetProtocolRegistry.protocols["bilabial-closure-v1"],
        status: "validated",
      },
    },
  };
  const candidateBase = {
    schemaVersion: "feedback-release-candidate-v1" as const,
    version: "bilabial-feedback-release-v1",
    catalogSha256: catalog.sha256,
    protocolRegistryVersion: registry.version,
    protocolRegistrySha256: feedbackTargetProtocolRegistrySha256(registry),
    routingThresholds: defaultThresholdPolicy,
    protocolId: "bilabial-closure-v1" as const,
    population: {
      ageBand: "6-12",
      locale: "en-US" as const,
      dialectScope: "study-approved-English-scope-v1",
      clinicalScope: "selected-idiopathic-speech-sound-errors",
    },
    retryPolicy: {
      maximumCaptureRetries: 2 as const,
      maximumUncertainRetries: 2 as const,
      maximumCorrectiveCues: 2 as const,
      oneCuePerAttempt: true as const,
      moveOnAtLimit: true as const,
      clinicianReviewAtLimit: true as const,
      stopOnDistressOrRequest: true as const,
      maximumAuthorizationAgeSeconds: 900 as const,
    },
    minimumAuditSamples: 9,
    templateBindings: templates.map((item) => ({
      kind: item.kind,
      templateId: item.templateId,
      templateSha256: item.sha256,
    })),
    lockedAt: "2026-07-10T18:00:00.000Z",
    expiresAt: "2026-07-11T18:00:00.000Z",
  };
  const candidate: FeedbackReleaseCandidate = {
    ...candidateBase,
    sha256: feedbackReleaseCandidateSha256(candidateBase),
  };
  const byKind = new Map(templates.map((item) => [item.kind, item]));
  const positive = byKind.get("positive-reinforcement")!;
  const retry = byKind.get("neutral-retry")!;
  const cue = byKind.get("corrective-cue")!;
  const moveOn = byKind.get("move-on")!;
  const samples: readonly FeedbackAuditSample[] = [
    auditSample("confident-correct", positive, candidate, "correct"),
    auditSample("capture-retry", retry, candidate, "capture"),
    auditSample("capture-exhausted", moveOn, candidate, "capture", {
      captureRetryCountBefore: 2,
    }),
    auditSample("uncertain-retry", retry, candidate, "uncertain"),
    auditSample("uncertain-exhausted", moveOn, candidate, "uncertain", {
      uncertainRetryCountBefore: 2,
    }),
    auditSample("corrective-cue", cue, candidate, "mismatch", {
      modelVisualOutcome: "closure-not-observed",
      cueAction: "bilabial-closure",
    }),
    auditSample("corrective-exhausted", moveOn, candidate, "mismatch", {
      correctiveCueCountBefore: 2,
    }),
    auditSample("distress", moveOn, candidate, "mismatch", {
      distressObserved: true,
    }),
    auditSample("stop-request", moveOn, candidate, "mismatch", {
      stopRequested: true,
    }),
  ];
  const audit = auditUnsupportedFeedbackClaims(
    catalog,
    candidate,
    registry,
    samples,
    "2026-07-10T18:10:00.000Z",
  );
  const evidence = releaseEvidence(candidate, audit.sha256);
  return { catalog, registry, candidate, samples, audit, evidence };
}

function template(
  templateId: string,
  kind: FeedbackTemplate["kind"],
  allowedEvidence: readonly FeedbackEvidenceKind[],
  title: string,
  body: string,
  claims: FeedbackTemplate["claims"],
): FeedbackTemplate {
  const base = {
    schemaVersion: "feedback-template-v1" as const,
    templateId,
    version: "1.0.0",
    locale: "en-US" as const,
    protocolId: "bilabial-closure-v1" as const,
    kind,
    allowedEvidence,
    title,
    body,
    claims,
    slpAuthorLicenseEvidenceSha256: digest(`license-${templateId}`),
    slpContentApprovalEvidenceSha256: digest(`approval-${templateId}`),
    approvedAt: "2026-07-10T17:00:00.000Z",
  };
  return { ...base, sha256: feedbackTemplateSha256(base) };
}

function auditSample(
  scenario: FeedbackAuditScenario,
  template: FeedbackTemplate,
  candidate: FeedbackReleaseCandidate,
  route: "correct" | "capture" | "uncertain" | "mismatch",
  overrides: Partial<FeedbackAuditSample> = {},
): FeedbackAuditSample {
  const base: FeedbackAuditSample = {
    sampleId: `feedback-audit-${scenario}`,
    scenario,
    candidateSha256: candidate.sha256,
    templateId: template.templateId,
    templateSha256: template.sha256,
    attempt: attempt(route),
    routingReason: route === "correct" ? "confident-correct"
      : route === "capture" ? "capture-quality-below-floor"
        : route === "uncertain" ? "audio-evidence-uncertain"
          : "confident-mismatch-on-supported-target",
    modelVisualOutcome: "not-run",
    renderedTitle: template.title,
    renderedBody: template.body,
    cueAction: "none",
    clinicianReviewQueued: template.kind === "move-on",
    captureRetryCountBefore: 0,
    uncertainRetryCountBefore: 0,
    correctiveCueCountBefore: 0,
    distressObserved: false,
    stopRequested: false,
  };
  return { ...base, ...overrides };
}

function attemptState(
  attemptId: string,
  overrides: Partial<Omit<FeedbackAttemptState, "schemaVersion" | "attemptId" | "sha256">> = {},
): FeedbackAttemptState {
  const base = {
    schemaVersion: "feedback-attempt-state-v1" as const,
    attemptId,
    revision: 0,
    captureRetryCount: 0,
    uncertainRetryCount: 0,
    correctiveCueCount: 0,
    cueAlreadyEmittedForAttempt: false,
    distressObserved: false,
    stopRequested: false,
    ...overrides,
  };
  return { ...base, sha256: feedbackAttemptStateSha256(base) };
}

function withState(
  request: FeedbackSelectionRequest,
  overrides: Partial<Omit<FeedbackAttemptState, "schemaVersion" | "attemptId" | "sha256">>,
): FeedbackSelectionRequest {
  return { ...request, state: attemptState(request.attempt.attemptId, overrides) };
}

function releaseEvidence(
  candidate: FeedbackReleaseCandidate,
  auditSha256: string,
): FeedbackReleaseEvidence {
  const base = {
    schemaVersion: "feedback-release-evidence-v1" as const,
    candidateSha256: candidate.sha256,
    unsupportedClaimAuditSha256: auditSha256,
    clinicalGovernanceApprovalSha256: digest("clinical-governance-approval"),
    usabilityEvidenceSha256: digest("usability-evidence"),
    accessibilityReviewSha256: digest("accessibility-review"),
    fusedUtilityEvidenceSha256: digest("fused-utility-evidence"),
    authenticatedExportEvidenceSha256: digest("authenticated-export-evidence"),
    approvedAt: "2026-07-10T18:20:00.000Z",
  };
  return { ...base, sha256: feedbackReleaseEvidenceSha256(base) };
}

function authorizeFixture(fixture: ReturnType<typeof feedbackFixture>) {
  return authorizeFeedbackResearchEvaluation(
    fixture.catalog,
    fixture.candidate,
    fixture.evidence,
    fixture.audit,
    fixture.samples,
    fixture.registry,
    "2026-07-10T18:30:00.000Z",
  );
}

function selection(
  fixture: ReturnType<typeof feedbackFixture>,
  route: "correct" | "capture" | "uncertain" | "mismatch",
): FeedbackSelectionRequest {
  return {
    attempt: attempt(route),
    modelVisualOutcome: route === "mismatch" ? "closure-not-observed" : "not-run",
    population: fixture.candidate.population,
    selectedAt: "2026-07-10T18:31:00.000Z",
    state: attemptState(attempt(route).attemptId),
  };
}

function attempt(route: "correct" | "capture" | "uncertain" | "mismatch"): AttemptEvaluationRequest {
  return {
    attemptId: `attempt-${route}-001`,
    protocolId: "bilabial-closure-v1",
    quality: route === "capture"
      ? { audioScore: 0.3, videoScore: 0.95, reasonCodes: [] }
      : { audioScore: 0.95, videoScore: 0.95, reasonCodes: [] },
    audio: route === "correct"
      ? { pCorrect: 0.95, pError: 0.03, calibrated: true, ambiguous: false }
      : route === "uncertain"
        ? { pCorrect: 0.45, pError: 0.5, calibrated: true, ambiguous: true }
        : { pCorrect: 0.03, pError: 0.95, calibrated: true, ambiguous: false },
    consent: {
      audioProcessing: true,
      videoProcessing: true,
      clinicianReview: true,
      researchUse: false,
    },
  };
}

function withoutSha<T extends { readonly sha256: string }>(value: T): Omit<T, "sha256"> {
  const { sha256: _sha256, ...rest } = value;
  return rest;
}

function digest(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}
