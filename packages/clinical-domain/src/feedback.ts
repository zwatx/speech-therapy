import { createHash } from "node:crypto";

import type {
  AttemptEvaluationRequest,
  RoutingDecision,
  TargetProtocolId,
  TargetProtocolRegistry,
  ThresholdPolicy,
} from "./types.ts";
import { routeAttempt } from "./routing.ts";
import { parseAttemptEvaluationRequest } from "./validation.ts";

export const feedbackTemplateKinds = [
  "positive-reinforcement",
  "neutral-retry",
  "corrective-cue",
  "move-on",
] as const;
export type FeedbackTemplateKind = (typeof feedbackTemplateKinds)[number];

export const feedbackEvidenceKinds = [
  "confident-correct",
  "capture-quality-below-floor",
  "audio-evidence-uncertain",
  "bilabial-nonclosure",
  "retry-budget-exhausted",
  "distress-or-stop",
] as const;
export type FeedbackEvidenceKind = (typeof feedbackEvidenceKinds)[number];

export const feedbackClaimKinds = [
  "effort-reinforcement",
  "target-observation",
  "capture-uncertainty",
  "practice-instruction",
  "clinician-review",
] as const;
export type FeedbackClaimKind = (typeof feedbackClaimKinds)[number];

export const feedbackAuditScenarios = [
  "confident-correct",
  "capture-retry",
  "capture-exhausted",
  "uncertain-retry",
  "uncertain-exhausted",
  "corrective-cue",
  "corrective-exhausted",
  "distress",
  "stop-request",
] as const;
export type FeedbackAuditScenario = (typeof feedbackAuditScenarios)[number];

export interface FeedbackTemplate {
  readonly schemaVersion: "feedback-template-v1";
  readonly templateId: string;
  readonly version: string;
  readonly locale: "en-US";
  readonly protocolId: TargetProtocolId;
  readonly kind: FeedbackTemplateKind;
  readonly allowedEvidence: readonly FeedbackEvidenceKind[];
  readonly title: string;
  readonly body: string;
  readonly claims: readonly FeedbackClaimKind[];
  readonly slpAuthorLicenseEvidenceSha256: string;
  readonly slpContentApprovalEvidenceSha256: string;
  readonly approvedAt: string;
  readonly sha256: string;
}

export interface FeedbackTemplateCatalog {
  readonly schemaVersion: "feedback-template-catalog-v1";
  readonly version: string;
  readonly locale: "en-US";
  readonly releasePosture: "candidate-only";
  readonly learnerFeedbackEligible: false;
  readonly templates: readonly FeedbackTemplate[];
  readonly sha256: string;
}

export interface FeedbackRetryPolicy {
  readonly maximumCaptureRetries: 2;
  readonly maximumUncertainRetries: 2;
  readonly maximumCorrectiveCues: 2;
  readonly oneCuePerAttempt: true;
  readonly moveOnAtLimit: true;
  readonly clinicianReviewAtLimit: true;
  readonly stopOnDistressOrRequest: true;
  readonly maximumAuthorizationAgeSeconds: 900;
}

export interface FeedbackPopulationScope {
  readonly ageBand: string;
  readonly locale: "en-US";
  readonly dialectScope: string;
  readonly clinicalScope: string;
}

export interface FeedbackReleaseCandidate {
  readonly schemaVersion: "feedback-release-candidate-v1";
  readonly version: string;
  readonly catalogSha256: string;
  readonly protocolRegistryVersion: string;
  readonly protocolRegistrySha256: string;
  readonly routingThresholds: ThresholdPolicy;
  readonly protocolId: "bilabial-closure-v1";
  readonly population: FeedbackPopulationScope;
  readonly retryPolicy: FeedbackRetryPolicy;
  readonly minimumAuditSamples: number;
  readonly templateBindings: readonly {
    readonly kind: FeedbackTemplateKind;
    readonly templateId: string;
    readonly templateSha256: string;
  }[];
  readonly lockedAt: string;
  readonly expiresAt: string;
  readonly sha256: string;
}

export interface FeedbackReleaseEvidence {
  readonly schemaVersion: "feedback-release-evidence-v1";
  readonly candidateSha256: string;
  readonly unsupportedClaimAuditSha256: string;
  readonly clinicalGovernanceApprovalSha256: string;
  readonly usabilityEvidenceSha256: string;
  readonly accessibilityReviewSha256: string;
  readonly fusedUtilityEvidenceSha256: string;
  readonly authenticatedExportEvidenceSha256: string;
  readonly approvedAt: string;
  readonly sha256: string;
}

export interface FeedbackAuditSample {
  readonly sampleId: string;
  readonly scenario: FeedbackAuditScenario;
  readonly candidateSha256: string;
  readonly templateId: string;
  readonly templateSha256: string;
  readonly attempt: AttemptEvaluationRequest;
  readonly routingReason: RoutingDecision["reason"];
  readonly modelVisualOutcome:
    | "closure-observed"
    | "closure-not-observed"
    | "indeterminate"
    | "unobservable"
    | "not-run";
  readonly renderedTitle: string;
  readonly renderedBody: string;
  readonly cueAction: "bilabial-closure" | "none";
  readonly clinicianReviewQueued: boolean;
  readonly captureRetryCountBefore: number;
  readonly uncertainRetryCountBefore: number;
  readonly correctiveCueCountBefore: number;
  readonly distressObserved: boolean;
  readonly stopRequested: boolean;
}

export interface UnsupportedClaimFinding {
  readonly sampleId: string | null;
  readonly templateId: string;
  readonly code:
    | "forbidden-diagnostic-language"
    | "forbidden-causal-language"
    | "hidden-anatomy-claim"
    | "absolute-evaluation-language"
    | "undeclared-rendered-copy"
    | "evidence-mismatch"
    | "cue-without-supported-visual-evidence"
    | "retry-budget-exceeded"
    | "stop-or-distress-ignored"
    | "unbound-template"
    | "missing-required-scenario";
  readonly detail: string;
}

export interface UnsupportedClaimAuditReport {
  readonly schemaVersion: "unsupported-claim-audit-report-v1";
  readonly catalogSha256: string;
  readonly candidateSha256: string;
  readonly auditedAt: string;
  readonly sampleEvidenceSha256: string;
  readonly releaseSampleCount: number;
  readonly coveredTemplateCount: number;
  readonly coveredScenarioCount: number;
  readonly policyViolationCount: number;
  readonly findings: readonly UnsupportedClaimFinding[];
  readonly zeroDetectedPolicyViolations: boolean;
  readonly auditScope: "bounded-static-policy-and-lexical-v1";
  readonly researchOnly: true;
  readonly learnerFeedbackEligible: false;
  readonly productionGateEligible: false;
  readonly sha256: string;
}

export interface FeedbackAttemptState {
  readonly schemaVersion: "feedback-attempt-state-v1";
  readonly attemptId: string;
  readonly revision: number;
  readonly captureRetryCount: number;
  readonly uncertainRetryCount: number;
  readonly correctiveCueCount: number;
  readonly cueAlreadyEmittedForAttempt: boolean;
  readonly distressObserved: boolean;
  readonly stopRequested: boolean;
  readonly sha256: string;
}

export interface FeedbackSelectionRequest {
  readonly attempt: AttemptEvaluationRequest;
  readonly modelVisualOutcome:
    | "closure-observed"
    | "closure-not-observed"
    | "indeterminate"
    | "unobservable"
    | "not-run";
  readonly population: FeedbackPopulationScope;
  readonly selectedAt: string;
  readonly state: FeedbackAttemptState;
}

export type FeedbackSelection =
  | {
      readonly action: "show-template";
      readonly template: FeedbackTemplate;
      readonly cueAction: "bilabial-closure" | "none";
      readonly flagClinicianReview: boolean;
      readonly reason: FeedbackEvidenceKind;
      readonly simulationOnly: true;
      readonly selectionReceiptSha256: string;
    }
  | {
      readonly action: "abstain";
      readonly reason:
        | "feedback-release-unavailable"
        | "consent-or-quality-blocked"
        | "visual-evidence-insufficient"
        | "cue-already-emitted";
    };

const authorizedReleaseMarker: unique symbol = Symbol("authorized-feedback-release");

export interface AuthorizedFeedbackResearchEvaluation {
  readonly candidate: FeedbackReleaseCandidate;
  readonly evidence: FeedbackReleaseEvidence;
  readonly catalog: FeedbackTemplateCatalog;
  readonly protocolRegistry: TargetProtocolRegistry;
  readonly authorizedAt: string;
  readonly releasePosture: "research-simulation-only";
  readonly learnerFeedbackEligible: false;
  readonly productionGateEligible: false;
  readonly [authorizedReleaseMarker]: true;
}

const templateKeys = [
  "schemaVersion", "templateId", "version", "locale", "protocolId", "kind",
  "allowedEvidence", "title", "body", "claims", "slpAuthorLicenseEvidenceSha256",
  "slpContentApprovalEvidenceSha256", "approvedAt", "sha256",
] as const;
const sampleKeys = [
  "sampleId", "scenario", "candidateSha256", "templateId", "templateSha256", "routingReason",
  "attempt",
  "modelVisualOutcome", "renderedTitle", "renderedBody", "cueAction",
  "clinicianReviewQueued", "captureRetryCountBefore", "uncertainRetryCountBefore",
  "correctiveCueCountBefore", "distressObserved", "stopRequested",
] as const;

export function feedbackTemplateSha256(
  template: Omit<FeedbackTemplate, "sha256">,
): string {
  return digest({
    schemaVersion: template.schemaVersion,
    templateId: template.templateId,
    version: template.version,
    locale: template.locale,
    protocolId: template.protocolId,
    kind: template.kind,
    allowedEvidence: [...template.allowedEvidence].sort(compareText),
    title: template.title,
    body: template.body,
    claims: [...template.claims].sort(compareText),
    slpAuthorLicenseEvidenceSha256: template.slpAuthorLicenseEvidenceSha256,
    slpContentApprovalEvidenceSha256: template.slpContentApprovalEvidenceSha256,
    approvedAt: template.approvedAt,
  });
}

export function feedbackAttemptStateSha256(
  state: Omit<FeedbackAttemptState, "sha256">,
): string {
  return digest({
    schemaVersion: state.schemaVersion,
    attemptId: state.attemptId,
    revision: state.revision,
    captureRetryCount: state.captureRetryCount,
    uncertainRetryCount: state.uncertainRetryCount,
    correctiveCueCount: state.correctiveCueCount,
    cueAlreadyEmittedForAttempt: state.cueAlreadyEmittedForAttempt,
    distressObserved: state.distressObserved,
    stopRequested: state.stopRequested,
  });
}

export function feedbackTemplateCatalogSha256(
  catalog: Omit<FeedbackTemplateCatalog, "sha256">,
): string {
  return digest({
    schemaVersion: catalog.schemaVersion,
    version: catalog.version,
    locale: catalog.locale,
    releasePosture: catalog.releasePosture,
    learnerFeedbackEligible: catalog.learnerFeedbackEligible,
    templates: [...catalog.templates].sort((left, right) =>
      compareText(left.templateId, right.templateId)).map(canonicalTemplate),
  });
}

export function feedbackReleaseCandidateSha256(
  candidate: Omit<FeedbackReleaseCandidate, "sha256">,
): string {
  return digest({
    schemaVersion: candidate.schemaVersion,
    version: candidate.version,
    catalogSha256: candidate.catalogSha256,
    protocolRegistryVersion: candidate.protocolRegistryVersion,
    protocolRegistrySha256: candidate.protocolRegistrySha256,
    routingThresholds: canonicalRoutingThresholds(candidate.routingThresholds),
    protocolId: candidate.protocolId,
    population: canonicalPopulation(candidate.population),
    retryPolicy: canonicalRetryPolicy(candidate.retryPolicy),
    minimumAuditSamples: candidate.minimumAuditSamples,
    templateBindings: [...candidate.templateBindings]
      .sort((left, right) => compareText(left.kind, right.kind))
      .map((binding) => ({
        kind: binding.kind,
        templateId: binding.templateId,
        templateSha256: binding.templateSha256,
      })),
    lockedAt: candidate.lockedAt,
    expiresAt: candidate.expiresAt,
  });
}

export function feedbackTargetProtocolRegistrySha256(
  registry: TargetProtocolRegistry,
): string {
  return digest({
    version: registry.version,
    protocols: Object.fromEntries(Object.entries(registry.protocols)
      .sort(([left], [right]) => compareText(left, right))
      .map(([id, protocol]) => [id, {
        id: protocol.id,
        label: protocol.label,
        phonemes: [...protocol.phonemes],
        status: protocol.status,
        visualCue: protocol.visualCue,
      }])),
  });
}

export function feedbackReleaseEvidenceSha256(
  evidence: Omit<FeedbackReleaseEvidence, "sha256">,
): string {
  return digest({
    schemaVersion: evidence.schemaVersion,
    candidateSha256: evidence.candidateSha256,
    unsupportedClaimAuditSha256: evidence.unsupportedClaimAuditSha256,
    clinicalGovernanceApprovalSha256: evidence.clinicalGovernanceApprovalSha256,
    usabilityEvidenceSha256: evidence.usabilityEvidenceSha256,
    accessibilityReviewSha256: evidence.accessibilityReviewSha256,
    fusedUtilityEvidenceSha256: evidence.fusedUtilityEvidenceSha256,
    authenticatedExportEvidenceSha256: evidence.authenticatedExportEvidenceSha256,
    approvedAt: evidence.approvedAt,
  });
}

export function auditUnsupportedFeedbackClaims(
  catalog: FeedbackTemplateCatalog,
  candidate: FeedbackReleaseCandidate,
  registry: TargetProtocolRegistry,
  samples: readonly FeedbackAuditSample[],
  auditedAt: string,
): UnsupportedClaimAuditReport {
  validateCatalog(catalog);
  validateCandidate(candidate, catalog);
  validateBoundRegistry(candidate, registry);
  timestamp(auditedAt, "auditedAt");
  if (Date.parse(auditedAt) < Date.parse(candidate.lockedAt)) {
    throw new TypeError("The claim audit cannot predate the locked release candidate.");
  }
  const templateByID = new Map(catalog.templates.map((template) =>
    [template.templateId, template]));
  const boundByID = new Map(candidate.templateBindings.map((binding) =>
    [binding.templateId, binding]));
  const findings: UnsupportedClaimFinding[] = [];
  for (const binding of candidate.templateBindings) {
    const template = templateByID.get(binding.templateId);
    if (!template || template.sha256 !== binding.templateSha256) continue;
    findings.push(...languageFindings(template, null, template.title, template.body));
  }
  const covered = new Set<string>();
  const coveredScenarios = new Set<FeedbackAuditScenario>();
  const sampleIDs = new Set<string>();
  for (const sample of samples) {
    validateAuditSample(sample);
    if (sampleIDs.has(sample.sampleId)) {
      throw new TypeError("Feedback audit sample IDs must be unique.");
    }
    sampleIDs.add(sample.sampleId);
    coveredScenarios.add(sample.scenario);
    if (sample.candidateSha256 !== candidate.sha256) {
      throw new TypeError("Every feedback audit sample must bind the release candidate.");
    }
    const routed = routeAttempt(sample.attempt, candidate.routingThresholds, registry);
    if (routed.reason !== sample.routingReason) {
      findings.push(finding(sample, "evidence-mismatch",
        "The declared routing reason does not match the recomputed attempt route."));
    }
    const template = templateByID.get(sample.templateId);
    const binding = boundByID.get(sample.templateId);
    if (!template || !binding || binding.templateSha256 !== sample.templateSha256
      || template.sha256 !== sample.templateSha256) {
      findings.push(finding(sample, "unbound-template",
        "The rendered sample does not match an exact bound template."));
      continue;
    }
    covered.add(template.templateId);
    findings.push(...languageFindings(
      template,
      sample.sampleId,
      sample.renderedTitle,
      sample.renderedBody,
    ));
    if (sample.renderedTitle !== template.title || sample.renderedBody !== template.body) {
      findings.push(finding(sample, "undeclared-rendered-copy",
        "Rendered learner copy must exactly match the approved static template."));
    }
    findings.push(...sampleEvidenceFindings(sample, template, candidate.retryPolicy));
    findings.push(...scenarioFindings(sample, template, candidate.retryPolicy));
  }
  for (const scenario of feedbackAuditScenarios) {
    if (!coveredScenarios.has(scenario)) {
      findings.push({
        sampleId: null,
        templateId: candidate.version,
        code: "missing-required-scenario",
        detail: `The release audit is missing the ${scenario} scenario.`,
      });
    }
  }
  const canonicalFindings = findings.sort((left, right) =>
    compareText(`${left.sampleId ?? ""}:${left.templateId}:${left.code}`,
      `${right.sampleId ?? ""}:${right.templateId}:${right.code}`));
  const base = {
    schemaVersion: "unsupported-claim-audit-report-v1" as const,
    catalogSha256: catalog.sha256,
    candidateSha256: candidate.sha256,
    auditedAt,
    sampleEvidenceSha256: feedbackAuditSamplesSha256(samples),
    releaseSampleCount: samples.length,
    coveredTemplateCount: covered.size,
    coveredScenarioCount: coveredScenarios.size,
    policyViolationCount: canonicalFindings.length,
    findings: canonicalFindings,
    zeroDetectedPolicyViolations: canonicalFindings.length === 0,
    auditScope: "bounded-static-policy-and-lexical-v1" as const,
    researchOnly: true as const,
    learnerFeedbackEligible: false as const,
    productionGateEligible: false as const,
  };
  return { ...base, sha256: unsupportedClaimAuditReportSha256(base) };
}

export function unsupportedClaimAuditReportSha256(
  report: Omit<UnsupportedClaimAuditReport, "sha256">,
): string {
  return digest({
    schemaVersion: report.schemaVersion,
    catalogSha256: report.catalogSha256,
    candidateSha256: report.candidateSha256,
    auditedAt: report.auditedAt,
    sampleEvidenceSha256: report.sampleEvidenceSha256,
    releaseSampleCount: report.releaseSampleCount,
    coveredTemplateCount: report.coveredTemplateCount,
    coveredScenarioCount: report.coveredScenarioCount,
    policyViolationCount: report.policyViolationCount,
    findings: report.findings.map((item) => ({
      sampleId: item.sampleId,
      templateId: item.templateId,
      code: item.code,
      detail: item.detail,
    })),
    zeroDetectedPolicyViolations: report.zeroDetectedPolicyViolations,
    auditScope: report.auditScope,
    researchOnly: report.researchOnly,
    learnerFeedbackEligible: report.learnerFeedbackEligible,
    productionGateEligible: report.productionGateEligible,
  });
}

export function authorizeFeedbackResearchEvaluation(
  catalog: FeedbackTemplateCatalog,
  candidate: FeedbackReleaseCandidate,
  evidence: FeedbackReleaseEvidence,
  audit: UnsupportedClaimAuditReport,
  auditSamples: readonly FeedbackAuditSample[],
  registry: TargetProtocolRegistry,
  authorizedAt: string,
): AuthorizedFeedbackResearchEvaluation {
  validateCatalog(catalog);
  validateCandidate(candidate, catalog);
  validateReleaseEvidence(evidence, candidate);
  validateAuditReport(audit, catalog, candidate);
  const recomputedAudit = auditUnsupportedFeedbackClaims(
    catalog,
    candidate,
    registry,
    auditSamples,
    audit.auditedAt,
  );
  timestamp(authorizedAt, "authorizedAt");
  if (registry.version !== candidate.protocolRegistryVersion
    || registry.protocols[candidate.protocolId]?.status !== "validated"
    || registry.protocols[candidate.protocolId]?.visualCue !== "bilabial-closure") {
    throw new TypeError("Feedback requires an exact validated target protocol registry.");
  }
  if (recomputedAudit.sha256 !== audit.sha256
    || evidence.unsupportedClaimAuditSha256 !== audit.sha256
    || audit.sampleEvidenceSha256 !== feedbackAuditSamplesSha256(auditSamples)
    || !audit.zeroDetectedPolicyViolations
    || audit.releaseSampleCount < candidate.minimumAuditSamples
    || audit.coveredTemplateCount !== candidate.templateBindings.length
    || audit.coveredScenarioCount !== feedbackAuditScenarios.length) {
    throw new TypeError("Feedback release requires a complete zero-finding claim audit.");
  }
  if (Date.parse(evidence.approvedAt) < Date.parse(audit.auditedAt)
    || Date.parse(authorizedAt) < Date.parse(evidence.approvedAt)
    || Date.parse(authorizedAt) < Date.parse(candidate.lockedAt)
    || Date.parse(authorizedAt) >= Date.parse(candidate.expiresAt)) {
    throw new TypeError("Feedback release evidence is stale or chronologically invalid.");
  }
  return Object.freeze({
    catalog,
    candidate,
    evidence,
    protocolRegistry: registry,
    authorizedAt,
    releasePosture: "research-simulation-only" as const,
    learnerFeedbackEligible: false as const,
    productionGateEligible: false as const,
    [authorizedReleaseMarker]: true as const,
  });
}

export function simulateFeedbackSelection(
  release: AuthorizedFeedbackResearchEvaluation,
  request: FeedbackSelectionRequest,
): FeedbackSelection {
  if (release[authorizedReleaseMarker] !== true) {
    return { action: "abstain", reason: "feedback-release-unavailable" };
  }
  validateSelectionRequest(request);
  if (!samePopulation(release.candidate.population, request.population)
    || request.attempt.protocolId !== release.candidate.protocolId) {
    return { action: "abstain", reason: "feedback-release-unavailable" };
  }
  const routingDecision = routeAttempt(
    request.attempt,
    release.candidate.routingThresholds,
    release.protocolRegistry,
  );
  if (Date.parse(request.selectedAt) < Date.parse(release.authorizedAt)
    || Date.parse(request.selectedAt) >= Date.parse(release.candidate.expiresAt)
    || Date.parse(request.selectedAt) - Date.parse(release.authorizedAt)
      > release.candidate.retryPolicy.maximumAuthorizationAgeSeconds * 1_000) {
    return { action: "abstain", reason: "feedback-release-unavailable" };
  }
  const templates = templatesByKind(release);
  const choose = (
    template: FeedbackTemplate | undefined,
    reason: FeedbackEvidenceKind,
    cueAction: "bilabial-closure" | "none",
  ) => show(template, reason, cueAction, release, request);
  if (request.state.stopRequested || request.state.distressObserved) {
    return choose(templates.get("move-on"), "distress-or-stop", "none");
  }
  switch (routingDecision.kind) {
    case "correct":
      return choose(templates.get("positive-reinforcement"), "confident-correct", "none");
    case "retry-capture":
      return request.state.captureRetryCount < release.candidate.retryPolicy.maximumCaptureRetries
        ? choose(templates.get("neutral-retry"), "capture-quality-below-floor", "none")
        : choose(templates.get("move-on"), "retry-budget-exhausted", "none");
    case "retry-or-abstain":
      return request.state.uncertainRetryCount < release.candidate.retryPolicy.maximumUncertainRetries
        ? choose(templates.get("neutral-retry"), "audio-evidence-uncertain", "none")
        : choose(templates.get("move-on"), "retry-budget-exhausted", "none");
    case "needs-deep-analysis":
      if (request.modelVisualOutcome !== "closure-not-observed") {
        return { action: "abstain", reason: "visual-evidence-insufficient" };
      }
      if (request.state.cueAlreadyEmittedForAttempt) {
        return { action: "abstain", reason: "cue-already-emitted" };
      }
      return request.state.correctiveCueCount < release.candidate.retryPolicy.maximumCorrectiveCues
        ? choose(templates.get("corrective-cue"), "bilabial-nonclosure", "bilabial-closure")
        : choose(templates.get("move-on"), "retry-budget-exhausted", "none");
    case "blocked-consent":
    case "audio-cue-or-review":
      return { action: "abstain", reason: "consent-or-quality-blocked" };
  }
}

function validateCatalog(catalog: FeedbackTemplateCatalog): void {
  if (!exactKeys(catalog, ["schemaVersion", "version", "locale", "releasePosture",
    "learnerFeedbackEligible", "templates", "sha256"])
    || catalog.schemaVersion !== "feedback-template-catalog-v1"
    || !identifier(catalog.version) || catalog.locale !== "en-US"
    || catalog.releasePosture !== "candidate-only"
    || catalog.learnerFeedbackEligible !== false
    || !Array.isArray(catalog.templates) || catalog.templates.length !== 4
    || new Set(catalog.templates.map((item) => item.templateId)).size
      !== catalog.templates.length
    || new Set(catalog.templates.map((item) => item.kind)).size
      !== feedbackTemplateKinds.length
    || catalog.templates.some((template) => !validTemplate(template))
    || feedbackTemplateCatalogSha256(catalog) !== catalog.sha256) {
    throw new TypeError("A strict hash-bound feedback template catalog is required.");
  }
}

function validTemplate(template: FeedbackTemplate): boolean {
  return exactKeys(template, templateKeys)
    && template.schemaVersion === "feedback-template-v1"
    && identifier(template.templateId) && identifier(template.version)
    && template.locale === "en-US" && template.protocolId === "bilabial-closure-v1"
    && feedbackTemplateKinds.includes(template.kind)
    && Array.isArray(template.allowedEvidence) && template.allowedEvidence.length > 0
    && new Set(template.allowedEvidence).size === template.allowedEvidence.length
    && template.allowedEvidence.every((item) => feedbackEvidenceKinds.includes(item))
    && allowedEvidenceMatchesKind(template.kind, template.allowedEvidence)
    && typeof template.title === "string" && template.title.length >= 3
    && template.title.length <= 80
    && typeof template.body === "string" && template.body.length >= 3
    && template.body.length <= 220
    && Array.isArray(template.claims) && template.claims.length > 0
    && new Set(template.claims).size === template.claims.length
    && template.claims.every((claim) => feedbackClaimKinds.includes(claim))
    && claimsMatchKind(template.kind, template.claims)
    && copyMatchesCandidatePolicy(template.kind, template.title, template.body)
    && hash(template.slpAuthorLicenseEvidenceSha256)
    && hash(template.slpContentApprovalEvidenceSha256)
    && canonicalTimestamp(template.approvedAt)
    && feedbackTemplateSha256(template) === template.sha256;
}

function validateCandidate(
  candidate: FeedbackReleaseCandidate,
  catalog: FeedbackTemplateCatalog,
): void {
  if (!exactKeys(candidate, ["schemaVersion", "version", "catalogSha256",
    "protocolRegistryVersion", "protocolRegistrySha256", "routingThresholds",
    "protocolId", "population", "retryPolicy",
    "minimumAuditSamples", "templateBindings", "lockedAt", "expiresAt", "sha256"])
    || candidate.schemaVersion !== "feedback-release-candidate-v1"
    || !identifier(candidate.version) || candidate.catalogSha256 !== catalog.sha256
    || !identifier(candidate.protocolRegistryVersion)
    || !hash(candidate.protocolRegistrySha256)
    || !validRoutingThresholds(candidate.routingThresholds)
    || candidate.protocolId !== "bilabial-closure-v1"
    || !validPopulation(candidate.population)
    || !validRetryPolicy(candidate.retryPolicy)
    || !Number.isSafeInteger(candidate.minimumAuditSamples)
    || candidate.minimumAuditSamples < feedbackAuditScenarios.length
    || !Array.isArray(candidate.templateBindings)
    || candidate.templateBindings.length !== feedbackTemplateKinds.length
    || new Set(candidate.templateBindings.map((item) => item.kind)).size
      !== feedbackTemplateKinds.length
    || candidate.templateBindings.some((binding) => !exactKeys(binding,
      ["kind", "templateId", "templateSha256"])
      || !feedbackTemplateKinds.includes(binding.kind)
      || !identifier(binding.templateId) || !hash(binding.templateSha256)
      || catalog.templates.find((item) => item.templateId === binding.templateId)?.sha256
        !== binding.templateSha256
      || catalog.templates.find((item) => item.templateId === binding.templateId)?.kind
        !== binding.kind)
    || !canonicalTimestamp(candidate.lockedAt)
    || !canonicalTimestamp(candidate.expiresAt)
    || Date.parse(candidate.expiresAt) <= Date.parse(candidate.lockedAt)
    || catalog.templates.some((template) =>
      Date.parse(template.approvedAt) > Date.parse(candidate.lockedAt))
    || candidate.population.locale !== catalog.locale
    || feedbackReleaseCandidateSha256(candidate) !== candidate.sha256) {
    throw new TypeError("A strict hash-bound feedback release candidate is required.");
  }
}

function validateReleaseEvidence(
  evidence: FeedbackReleaseEvidence,
  candidate: FeedbackReleaseCandidate,
): void {
  if (!exactKeys(evidence, ["schemaVersion", "candidateSha256",
    "unsupportedClaimAuditSha256", "clinicalGovernanceApprovalSha256",
    "usabilityEvidenceSha256", "accessibilityReviewSha256", "fusedUtilityEvidenceSha256",
    "authenticatedExportEvidenceSha256", "approvedAt", "sha256"])
    || evidence.schemaVersion !== "feedback-release-evidence-v1"
    || evidence.candidateSha256 !== candidate.sha256
    || !hash(evidence.unsupportedClaimAuditSha256)
    || !hash(evidence.clinicalGovernanceApprovalSha256)
    || !hash(evidence.usabilityEvidenceSha256)
    || !hash(evidence.accessibilityReviewSha256)
    || !hash(evidence.fusedUtilityEvidenceSha256)
    || !hash(evidence.authenticatedExportEvidenceSha256)
    || !canonicalTimestamp(evidence.approvedAt)
    || feedbackReleaseEvidenceSha256(evidence) !== evidence.sha256) {
    throw new TypeError("Complete hash-bound feedback release evidence is required.");
  }
}

function validateAuditReport(
  report: UnsupportedClaimAuditReport,
  catalog: FeedbackTemplateCatalog,
  candidate: FeedbackReleaseCandidate,
): void {
  if (report.schemaVersion !== "unsupported-claim-audit-report-v1"
    || report.catalogSha256 !== catalog.sha256
    || report.candidateSha256 !== candidate.sha256
    || !canonicalTimestamp(report.auditedAt)
    || !hash(report.sampleEvidenceSha256)
    || report.auditScope !== "bounded-static-policy-and-lexical-v1"
    || report.researchOnly !== true || report.learnerFeedbackEligible !== false
    || report.productionGateEligible !== false
    || unsupportedClaimAuditReportSha256(report) !== report.sha256) {
    throw new TypeError("A current canonical unsupported-claim audit is required.");
  }
}

function validateAuditSample(sample: FeedbackAuditSample): void {
  if (!exactKeys(sample, sampleKeys) || !identifier(sample.sampleId)
    || !feedbackAuditScenarios.includes(sample.scenario)
    || !hash(sample.candidateSha256) || !identifier(sample.templateId)
    || !hash(sample.templateSha256)
    || !validAttempt(sample.attempt)
    || sample.attempt.protocolId !== "bilabial-closure-v1"
    || !(["closure-observed", "closure-not-observed", "indeterminate",
      "unobservable", "not-run"] as const).includes(sample.modelVisualOutcome)
    || typeof sample.renderedTitle !== "string" || typeof sample.renderedBody !== "string"
    || !["bilabial-closure", "none"].includes(sample.cueAction)
    || typeof sample.clinicianReviewQueued !== "boolean"
    || !Number.isSafeInteger(sample.captureRetryCountBefore)
    || sample.captureRetryCountBefore < 0
    || !Number.isSafeInteger(sample.uncertainRetryCountBefore)
    || sample.uncertainRetryCountBefore < 0
    || !Number.isSafeInteger(sample.correctiveCueCountBefore)
    || sample.correctiveCueCountBefore < 0
    || typeof sample.distressObserved !== "boolean"
    || typeof sample.stopRequested !== "boolean") {
    throw new TypeError("Feedback audit samples must use the strict evidence schema.");
  }
}

function validateSelectionRequest(request: FeedbackSelectionRequest): void {
  if (!exactKeys(request, ["attempt", "modelVisualOutcome", "population", "selectedAt", "state"])
    || !validAttempt(request.attempt)
    || !(["closure-observed", "closure-not-observed", "indeterminate",
      "unobservable", "not-run"] as const).includes(request.modelVisualOutcome)
    || !validPopulation(request.population)
    || !canonicalTimestamp(request.selectedAt)
    || !validAttemptState(request.state, request.attempt.attemptId)) {
    throw new TypeError("Feedback selection request is invalid.");
  }
}

function sampleEvidenceFindings(
  sample: FeedbackAuditSample,
  template: FeedbackTemplate,
  retry: FeedbackRetryPolicy,
): UnsupportedClaimFinding[] {
  const findings: UnsupportedClaimFinding[] = [];
  const expectedReason: Partial<Record<FeedbackEvidenceKind, RoutingDecision["reason"] | null>> = {
    "confident-correct": "confident-correct",
    "capture-quality-below-floor": "capture-quality-below-floor",
    "audio-evidence-uncertain": "audio-evidence-uncertain",
    "bilabial-nonclosure": "confident-mismatch-on-supported-target",
    "retry-budget-exhausted": null,
    "distress-or-stop": null,
  };
  const routeMatches = template.allowedEvidence.some((evidence) => {
    const route = expectedReason[evidence];
    return route === null ? template.kind === "move-on" : route === sample.routingReason;
  });
  if (!routeMatches) {
    findings.push(finding(sample, "evidence-mismatch",
      "The template evidence requirement does not match the routing reason."));
  }
  if (template.kind === "corrective-cue"
    && (sample.modelVisualOutcome !== "closure-not-observed"
      || sample.cueAction !== "bilabial-closure")) {
    findings.push(finding(sample, "cue-without-supported-visual-evidence",
      "A corrective cue requires an observable model non-closure result."));
  }
  if (template.kind !== "corrective-cue" && sample.cueAction !== "none") {
    findings.push(finding(sample, "cue-without-supported-visual-evidence",
      "Only the bound corrective template may emit a visual cue."));
  }
  if ((template.kind === "neutral-retry"
      && ((sample.routingReason === "capture-quality-below-floor"
          && sample.captureRetryCountBefore >= retry.maximumCaptureRetries)
        || (sample.routingReason === "audio-evidence-uncertain"
          && sample.uncertainRetryCountBefore >= retry.maximumUncertainRetries)))
    || (template.kind === "corrective-cue"
      && sample.correctiveCueCountBefore >= retry.maximumCorrectiveCues)) {
    findings.push(finding(sample, "retry-budget-exceeded",
      "The rendered template exceeds the locked retry or cue budget."));
  }
  if ((sample.distressObserved || sample.stopRequested) && template.kind !== "move-on") {
    findings.push(finding(sample, "stop-or-distress-ignored",
      "Stop requests and distress must select the move-on template."));
  }
  if (template.kind === "move-on"
    && !sample.distressObserved && !sample.stopRequested
    && sample.captureRetryCountBefore < retry.maximumCaptureRetries
    && sample.uncertainRetryCountBefore < retry.maximumUncertainRetries
    && sample.correctiveCueCountBefore < retry.maximumCorrectiveCues) {
    findings.push(finding(sample, "evidence-mismatch",
      "Move-on feedback requires a stop signal, distress, or an exhausted retry budget."));
  }
  if ((template.kind === "move-on") !== sample.clinicianReviewQueued) {
    findings.push(finding(sample, "evidence-mismatch",
      "Move-on feedback must queue clinician review, and other templates must not."));
  }
  return findings;
}

function scenarioFindings(
  sample: FeedbackAuditSample,
  template: FeedbackTemplate,
  retry: FeedbackRetryPolicy,
): UnsupportedClaimFinding[] {
  const noSignals = !sample.distressObserved && !sample.stopRequested;
  let matches = false;
  switch (sample.scenario) {
    case "confident-correct":
      matches = template.kind === "positive-reinforcement"
        && sample.routingReason === "confident-correct" && noSignals;
      break;
    case "capture-retry":
      matches = template.kind === "neutral-retry"
        && sample.routingReason === "capture-quality-below-floor"
        && sample.captureRetryCountBefore < retry.maximumCaptureRetries && noSignals;
      break;
    case "capture-exhausted":
      matches = template.kind === "move-on"
        && sample.routingReason === "capture-quality-below-floor"
        && sample.captureRetryCountBefore >= retry.maximumCaptureRetries && noSignals;
      break;
    case "uncertain-retry":
      matches = template.kind === "neutral-retry"
        && sample.routingReason === "audio-evidence-uncertain"
        && sample.uncertainRetryCountBefore < retry.maximumUncertainRetries && noSignals;
      break;
    case "uncertain-exhausted":
      matches = template.kind === "move-on"
        && sample.routingReason === "audio-evidence-uncertain"
        && sample.uncertainRetryCountBefore >= retry.maximumUncertainRetries && noSignals;
      break;
    case "corrective-cue":
      matches = template.kind === "corrective-cue"
        && sample.routingReason === "confident-mismatch-on-supported-target"
        && sample.modelVisualOutcome === "closure-not-observed"
        && sample.correctiveCueCountBefore < retry.maximumCorrectiveCues
        && sample.cueAction === "bilabial-closure" && noSignals;
      break;
    case "corrective-exhausted":
      matches = template.kind === "move-on"
        && sample.routingReason === "confident-mismatch-on-supported-target"
        && sample.correctiveCueCountBefore >= retry.maximumCorrectiveCues
        && sample.cueAction === "none" && noSignals;
      break;
    case "distress":
      matches = template.kind === "move-on" && sample.distressObserved;
      break;
    case "stop-request":
      matches = template.kind === "move-on" && sample.stopRequested;
      break;
  }
  return matches ? [] : [finding(sample, "evidence-mismatch",
    `The sample does not satisfy the closed ${sample.scenario} scenario contract.`)];
}

function languageFindings(
  template: FeedbackTemplate,
  sampleId: string | null,
  title: string,
  body: string,
): UnsupportedClaimFinding[] {
  const text = `${title} ${body}`.toLowerCase();
  const rules: readonly [UnsupportedClaimFinding["code"], RegExp, string][] = [
    ["forbidden-diagnostic-language", /\b(you have|speech disorder|speech impediment|diagnos(?:e|is))\b/,
      "Learner feedback cannot diagnose a disorder or impairment."],
    ["forbidden-causal-language", /\b(the cause is|because your|this means your)\b/,
      "Learner feedback cannot infer a physical or clinical cause."],
    ["hidden-anatomy-claim", /\b(tongue.{0,24}(roof|palate|ridge|touch)|inside your mouth)\b/,
      "A front camera cannot support hidden-articulator claims."],
    ["hidden-anatomy-claim", /\b(jaw|teeth|tooth|throat|vocal cords?|speech muscles?|palate)\b/,
      "The bilabial camera protocol cannot support claims about other anatomy."],
    ["absolute-evaluation-language", /\b(perfect speech|you were wrong|bad speech|always|never)\b/,
      "Feedback cannot make absolute, shaming, or overgeneralized evaluations."],
  ];
  return rules.filter(([, pattern]) => pattern.test(text)).map(([code, , detail]) => ({
    sampleId,
    templateId: template.templateId,
    code,
    detail,
  }));
}

function finding(
  sample: FeedbackAuditSample,
  code: UnsupportedClaimFinding["code"],
  detail: string,
): UnsupportedClaimFinding {
  return { sampleId: sample.sampleId, templateId: sample.templateId, code, detail };
}

function templatesByKind(release: AuthorizedFeedbackResearchEvaluation) {
  const byID = new Map(release.catalog.templates.map((template) =>
    [template.templateId, template]));
  return new Map(release.candidate.templateBindings.map((binding) =>
    [binding.kind, byID.get(binding.templateId)]));
}

function show(
  template: FeedbackTemplate | undefined,
  reason: FeedbackEvidenceKind,
  cueAction: "bilabial-closure" | "none",
  release: AuthorizedFeedbackResearchEvaluation,
  request: FeedbackSelectionRequest,
): FeedbackSelection {
  if (!template) return { action: "abstain", reason: "feedback-release-unavailable" };
  if (!template.allowedEvidence.includes(reason)) {
    return { action: "abstain", reason: "feedback-release-unavailable" };
  }
  return {
    action: "show-template",
    template,
    cueAction,
    flagClinicianReview: template.kind === "move-on",
    reason,
    simulationOnly: true,
    selectionReceiptSha256: digest({
      schemaVersion: "feedback-selection-receipt-v1",
      candidateSha256: release.candidate.sha256,
      evidenceSha256: release.evidence.sha256,
      attemptId: request.attempt.attemptId,
      attemptStateSha256: request.state.sha256,
      templateSha256: template.sha256,
      reason,
      cueAction,
    }),
  };
}

function canonicalTemplate(template: FeedbackTemplate) {
  return {
    schemaVersion: template.schemaVersion,
    templateId: template.templateId,
    version: template.version,
    locale: template.locale,
    protocolId: template.protocolId,
    kind: template.kind,
    allowedEvidence: [...template.allowedEvidence].sort(compareText),
    title: template.title,
    body: template.body,
    claims: [...template.claims].sort(compareText),
    slpAuthorLicenseEvidenceSha256: template.slpAuthorLicenseEvidenceSha256,
    slpContentApprovalEvidenceSha256: template.slpContentApprovalEvidenceSha256,
    approvedAt: template.approvedAt,
    sha256: template.sha256,
  };
}

function canonicalPopulation(population: FeedbackPopulationScope) {
  return {
    ageBand: population.ageBand,
    locale: population.locale,
    dialectScope: population.dialectScope,
    clinicalScope: population.clinicalScope,
  };
}

export function feedbackAuditSamplesSha256(
  samples: readonly FeedbackAuditSample[],
): string {
  return digest([...samples]
    .sort((left, right) => compareText(left.sampleId, right.sampleId))
    .map((sample) => ({
      sampleId: sample.sampleId,
      scenario: sample.scenario,
      candidateSha256: sample.candidateSha256,
      templateId: sample.templateId,
      templateSha256: sample.templateSha256,
      attempt: canonicalAttempt(sample.attempt),
      routingReason: sample.routingReason,
      modelVisualOutcome: sample.modelVisualOutcome,
      renderedTitle: sample.renderedTitle,
      renderedBody: sample.renderedBody,
      cueAction: sample.cueAction,
      clinicianReviewQueued: sample.clinicianReviewQueued,
      captureRetryCountBefore: sample.captureRetryCountBefore,
      uncertainRetryCountBefore: sample.uncertainRetryCountBefore,
      correctiveCueCountBefore: sample.correctiveCueCountBefore,
      distressObserved: sample.distressObserved,
      stopRequested: sample.stopRequested,
    })));
}

function canonicalAttempt(attempt: AttemptEvaluationRequest) {
  return {
    attemptId: attempt.attemptId,
    protocolId: attempt.protocolId,
    quality: {
      audioScore: attempt.quality.audioScore,
      ...(attempt.quality.videoScore === undefined
        ? {} : { videoScore: attempt.quality.videoScore }),
      reasonCodes: [...attempt.quality.reasonCodes],
    },
    audio: {
      pCorrect: attempt.audio.pCorrect,
      pError: attempt.audio.pError,
      calibrated: attempt.audio.calibrated,
      ambiguous: attempt.audio.ambiguous,
      ...(attempt.audio.likelyError === undefined
        ? {} : { likelyError: attempt.audio.likelyError }),
    },
    consent: {
      audioProcessing: attempt.consent.audioProcessing,
      videoProcessing: attempt.consent.videoProcessing,
      clinicianReview: attempt.consent.clinicianReview,
      researchUse: attempt.consent.researchUse,
    },
  };
}

function canonicalRetryPolicy(policy: FeedbackRetryPolicy) {
  return {
    maximumCaptureRetries: policy.maximumCaptureRetries,
    maximumUncertainRetries: policy.maximumUncertainRetries,
    maximumCorrectiveCues: policy.maximumCorrectiveCues,
    oneCuePerAttempt: policy.oneCuePerAttempt,
    moveOnAtLimit: policy.moveOnAtLimit,
    clinicianReviewAtLimit: policy.clinicianReviewAtLimit,
    stopOnDistressOrRequest: policy.stopOnDistressOrRequest,
    maximumAuthorizationAgeSeconds: policy.maximumAuthorizationAgeSeconds,
  };
}

function canonicalRoutingThresholds(policy: ThresholdPolicy) {
  return {
    version: policy.version,
    audioQualityFloor: policy.audioQualityFloor,
    videoQualityFloor: policy.videoQualityFloor,
    passThreshold: policy.passThreshold,
    analysisThreshold: policy.analysisThreshold,
  };
}

function validRoutingThresholds(policy: ThresholdPolicy): boolean {
  return exactKeys(policy, ["version", "audioQualityFloor", "videoQualityFloor",
    "passThreshold", "analysisThreshold"])
    && identifier(policy.version)
    && [policy.audioQualityFloor, policy.videoQualityFloor, policy.passThreshold,
      policy.analysisThreshold].every((value) =>
      Number.isFinite(value) && value >= 0 && value <= 1);
}

function validateBoundRegistry(
  candidate: FeedbackReleaseCandidate,
  registry: TargetProtocolRegistry,
): void {
  if (!validTargetProtocolRegistry(registry)
    || registry.version !== candidate.protocolRegistryVersion
    || feedbackTargetProtocolRegistrySha256(registry) !== candidate.protocolRegistrySha256) {
    throw new TypeError("The target protocol registry does not match the release candidate.");
  }
}

function validTargetProtocolRegistry(registry: TargetProtocolRegistry): boolean {
  const expectedIDs = [
    "audio-only-v1",
    "bilabial-closure-v1",
    "interdental-visibility-v1",
    "l-tip-lift-research-v1",
    "labiodental-contact-v1",
  ];
  if (!exactKeys(registry, ["version", "protocols"])
    || !identifier(registry.version)
    || !exactKeys(registry.protocols, expectedIDs)) return false;
  return Object.entries(registry.protocols).every(([id, protocol]) =>
    exactKeys(protocol, ["id", "label", "phonemes", "status", "visualCue"])
    && protocol.id === id
    && typeof protocol.label === "string" && protocol.label.length > 0
    && Array.isArray(protocol.phonemes) && protocol.phonemes.length > 0
    && protocol.phonemes.every((phoneme) =>
      typeof phoneme === "string" && phoneme.length > 0)
    && ["candidate", "validated", "research", "audio-only"].includes(protocol.status));
}

function validAttempt(attempt: AttemptEvaluationRequest): boolean {
  try {
    parseAttemptEvaluationRequest(attempt);
    return true;
  } catch {
    return false;
  }
}

function validAttemptState(state: FeedbackAttemptState, attemptId: string): boolean {
  return exactKeys(state, ["schemaVersion", "attemptId", "revision",
    "captureRetryCount", "uncertainRetryCount", "correctiveCueCount",
    "cueAlreadyEmittedForAttempt", "distressObserved", "stopRequested", "sha256"])
    && state.schemaVersion === "feedback-attempt-state-v1"
    && state.attemptId === attemptId
    && Number.isSafeInteger(state.revision) && state.revision >= 0
    && Number.isSafeInteger(state.captureRetryCount) && state.captureRetryCount >= 0
    && Number.isSafeInteger(state.uncertainRetryCount) && state.uncertainRetryCount >= 0
    && Number.isSafeInteger(state.correctiveCueCount) && state.correctiveCueCount >= 0
    && typeof state.cueAlreadyEmittedForAttempt === "boolean"
    && typeof state.distressObserved === "boolean"
    && typeof state.stopRequested === "boolean"
    && feedbackAttemptStateSha256(state) === state.sha256;
}

function validRetryPolicy(policy: FeedbackRetryPolicy): boolean {
  return exactKeys(policy, ["maximumCaptureRetries", "maximumUncertainRetries", "maximumCorrectiveCues",
    "oneCuePerAttempt", "moveOnAtLimit", "clinicianReviewAtLimit",
    "stopOnDistressOrRequest", "maximumAuthorizationAgeSeconds"])
    && policy.maximumCaptureRetries === 2
    && policy.maximumUncertainRetries === 2
    && policy.maximumCorrectiveCues === 2
    && policy.oneCuePerAttempt === true && policy.moveOnAtLimit === true
    && policy.clinicianReviewAtLimit === true && policy.stopOnDistressOrRequest === true
    && policy.maximumAuthorizationAgeSeconds === 900;
}

function allowedEvidenceMatchesKind(
  kind: FeedbackTemplateKind,
  actual: readonly FeedbackEvidenceKind[],
): boolean {
  const expected: Record<FeedbackTemplateKind, readonly FeedbackEvidenceKind[]> = {
    "positive-reinforcement": ["confident-correct"],
    "neutral-retry": ["capture-quality-below-floor", "audio-evidence-uncertain"],
    "corrective-cue": ["bilabial-nonclosure"],
    "move-on": ["retry-budget-exhausted", "distress-or-stop"],
  };
  const left = [...actual].sort(compareText);
  const right = [...expected[kind]].sort(compareText);
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function claimsMatchKind(
  kind: FeedbackTemplateKind,
  actual: readonly FeedbackClaimKind[],
): boolean {
  const expected: Record<FeedbackTemplateKind, readonly FeedbackClaimKind[]> = {
    "positive-reinforcement": ["effort-reinforcement", "target-observation"],
    "neutral-retry": ["capture-uncertainty"],
    "corrective-cue": ["practice-instruction"],
    "move-on": ["clinician-review", "effort-reinforcement"],
  };
  const left = [...actual].sort(compareText);
  const right = [...expected[kind]].sort(compareText);
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function copyMatchesCandidatePolicy(
  kind: FeedbackTemplateKind,
  title: string,
  body: string,
): boolean {
  const approved: Record<FeedbackTemplateKind, readonly [string, string]> = {
    "positive-reinforcement": [
      "Nice work",
      "You made the beginning sound clearly.",
    ],
    "neutral-retry": [
      "Let’s try once more",
      "I couldn’t get a clear read. Say the word one more time.",
    ],
    "corrective-cue": [
      "Try one small change",
      "Close both lips before the sound, then try once more.",
    ],
    "move-on": [
      "Let’s move on",
      "We’ll save this one for your speech teacher and try the next word.",
    ],
  };
  return approved[kind][0] === title && approved[kind][1] === body;
}

function validPopulation(population: FeedbackPopulationScope): boolean {
  return exactKeys(population, ["ageBand", "locale", "dialectScope", "clinicalScope"])
    && population.locale === "en-US"
    && Object.values(population).every((value) =>
      typeof value === "string" && value.length >= 2 && value.length <= 80);
}

function samePopulation(left: FeedbackPopulationScope, right: FeedbackPopulationScope): boolean {
  return left.ageBand === right.ageBand && left.locale === right.locale
    && left.dialectScope === right.dialectScope
    && left.clinicalScope === right.clinicalScope;
}

function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function exactKeys(value: unknown, expected: readonly string[]): boolean {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort(compareText);
  const wanted = [...expected].sort(compareText);
  return actual.length === wanted.length
    && actual.every((key, index) => key === wanted[index]);
}

function identifier(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/.test(value);
}

function hash(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

function timestamp(value: unknown, label: string): asserts value is string {
  if (!canonicalTimestamp(value)) {
    throw new TypeError(`${label} must be a canonical ISO-8601 timestamp.`);
  }
}

function canonicalTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString() === value;
}

function compareText(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}
