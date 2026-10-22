import {
  latencyBuckets,
  thermalStates,
  visualFeasibilityScenarios,
  type LatencyBucket,
  type ThermalState,
  type VisualCaptureIssue,
  type VisualFeasibilityReport,
  type VisualFeasibilityScenario,
} from "./types.ts";

export interface VisualFeasibilityThresholds {
  readonly minimumFramesPerScenarioPerHardware: number;
  readonly minimumDistinctHardware: number;
  readonly minimumCompliantUsableRate: number;
  readonly minimumChallengeDetectionRate: number;
  readonly maximumExtractionFailureRate: number;
  readonly maximumP95Bucket: LatencyBucket;
  readonly maximumThermalState: ThermalState;
}

export const defaultVisualFeasibilityThresholds: VisualFeasibilityThresholds = {
  minimumFramesPerScenarioPerHardware: 100,
  minimumDistinctHardware: 3,
  minimumCompliantUsableRate: 0.95,
  minimumChallengeDetectionRate: 0.9,
  maximumExtractionFailureRate: 0.01,
  maximumP95Bucket: "le-100",
  maximumThermalState: "fair",
};

export interface VisualFeasibilityCheck {
  readonly id: string;
  readonly passed: boolean;
  readonly measured: number | string;
  readonly required: number | string;
}

export interface VisualFeasibilityEvaluation {
  readonly status: "pass" | "fail";
  readonly reportCount: number;
  readonly checks: readonly VisualFeasibilityCheck[];
  readonly limitations: readonly string[];
}

const requiredScenarios = visualFeasibilityScenarios.filter(
  (scenario) => scenario !== "unstructured",
);

const expectedIssues: Readonly<
  Partial<Record<VisualFeasibilityScenario, readonly VisualCaptureIssue[]>>
> = {
  "low-light": [
    "noFace",
    "mouthLandmarksUnavailable",
    "poseUnavailable",
    "invalidObservation",
  ],
  "face-too-far": ["faceTooFar"],
  "face-too-close": ["faceTooClose"],
  "face-off-center": ["faceOffCenter"],
  "head-turned": ["headTurned"],
  "mouth-covered": ["mouthLandmarksUnavailable"],
  "multiple-faces": ["multipleFaces"],
};

export function evaluateVisualFeasibility(
  reports: readonly VisualFeasibilityReport[],
  thresholds: VisualFeasibilityThresholds = defaultVisualFeasibilityThresholds,
): VisualFeasibilityEvaluation {
  const checks: VisualFeasibilityCheck[] = [];
  const hardware = new Set(reports.map((report) => report.device.hardwareIdentifier));
  checks.push(check(
    "hardware-coverage",
    hardware.size >= thresholds.minimumDistinctHardware,
    hardware.size,
    thresholds.minimumDistinctHardware,
  ));

  const runtimeVersions = new Set(reports.map((report) => report.runtimeVersion));
  const protocols = new Set(reports.map((report) => report.configuration.protocolID));
  const sessionIDs = new Set(reports.map((report) => report.sessionID));
  const appBuilds = new Set(reports.map((report) =>
    `${report.device.appVersion}+${report.device.buildVersion}`));
  checks.push(check("single-runtime-version", runtimeVersions.size === 1, runtimeVersions.size, 1));
  checks.push(check("single-protocol", protocols.size === 1, protocols.size, 1));
  checks.push(check(
    "unique-session-ids",
    sessionIDs.size === reports.length,
    sessionIDs.size,
    reports.length,
  ));
  checks.push(check("single-app-build", appBuilds.size === 1, appBuilds.size, 1));
  const lowPowerReports = reports.filter(
    (report) => report.runtime.lowPowerModeObserved,
  ).length;
  checks.push(check("low-power-disabled", lowPowerReports === 0, lowPowerReports, 0));
  const incompleteLatencyReports = reports.filter((report) =>
    report.latency.measuredFrames
      !== report.frames.totalFrames - report.frames.extractionFailures).length;
  checks.push(check(
    "complete-latency-coverage",
    incompleteLatencyReports === 0,
    incompleteLatencyReports,
    0,
  ));

  for (const scenario of requiredScenarios) {
    for (const hardwareIdentifier of hardware) {
      evaluateScenarioHardware(
        checks,
        reports,
        scenario,
        hardwareIdentifier,
        thresholds,
      );
    }
  }

  const worstP95 = reports.reduce<LatencyBucket | undefined>((worst, report) => {
    const current = report.latency.p95Bucket;
    if (current === undefined) return worst;
    if (worst === undefined) return current;
    return latencyBuckets.indexOf(current) > latencyBuckets.indexOf(worst)
      ? current
      : worst;
  }, undefined);
  checks.push(check(
    "processing-latency-p95",
    worstP95 !== undefined
      && latencyBuckets.indexOf(worstP95)
        <= latencyBuckets.indexOf(thresholds.maximumP95Bucket),
    worstP95 ?? "unmeasured",
    thresholds.maximumP95Bucket,
  ));

  const worstThermal = reports.reduce<ThermalState>((worst, report) =>
    thermalStates.indexOf(report.runtime.maximumThermalState)
      > thermalStates.indexOf(worst)
      ? report.runtime.maximumThermalState
      : worst, "nominal");
  checks.push(check(
    "thermal-state",
    thermalStates.indexOf(worstThermal)
      <= thermalStates.indexOf(thresholds.maximumThermalState),
    worstThermal,
    thresholds.maximumThermalState,
  ));

  return {
    status: checks.every((item) => item.passed) ? "pass" : "fail",
    reportCount: reports.length,
    checks,
    limitations: [
      "This evaluates capture feasibility only; it does not validate an articulation cue or clinical claim.",
      "Reports are unsigned Debug exports and require protocol-controlled collection and provenance review.",
      "Network-capture, VoiceOver, interruption, memory, and unsupported-claim evidence are separate gates.",
    ],
  };
}

function evaluateScenarioHardware(
  checks: VisualFeasibilityCheck[],
  reports: readonly VisualFeasibilityReport[],
  scenario: Exclude<VisualFeasibilityScenario, "unstructured">,
  hardwareIdentifier: string,
  thresholds: VisualFeasibilityThresholds,
): void {
  const matching = reports.filter(
    (report) => report.configuration.scenario === scenario
      && report.device.hardwareIdentifier === hardwareIdentifier,
  );
  const totalFrames = sum(matching, (report) => report.frames.totalFrames);
  const prefix = `scenario-${scenario}-hardware-${hardwareIdentifier}`;
  checks.push(check(
    `${prefix}-frames`,
    totalFrames >= thresholds.minimumFramesPerScenarioPerHardware,
    totalFrames,
    thresholds.minimumFramesPerScenarioPerHardware,
  ));

  const failures = sum(matching, (report) => report.frames.extractionFailures);
  const failureRate = totalFrames === 0 ? 1 : failures / totalFrames;
  checks.push(check(
    `${prefix}-extraction-failure-rate`,
    failureRate <= thresholds.maximumExtractionFailureRate,
    failureRate,
    thresholds.maximumExtractionFailureRate,
  ));

  if (scenario === "protocol-compliant") {
    const usable = sum(matching, (report) => report.frames.usableFrames);
    const usableRate = totalFrames === 0 ? 0 : usable / totalFrames;
    checks.push(check(
      `${prefix}-usable-rate`,
      usableRate >= thresholds.minimumCompliantUsableRate,
      usableRate,
      thresholds.minimumCompliantUsableRate,
    ));
  }

  const expected = expectedIssues[scenario];
  if (expected !== undefined) {
    const detections = sum(
      matching,
      (report) => report.frames.challengeHitFrames,
    );
    const detectionRate = totalFrames === 0 ? 0 : detections / totalFrames;
    checks.push(check(
      `${prefix}-detection-rate`,
      detectionRate >= thresholds.minimumChallengeDetectionRate,
      detectionRate,
      thresholds.minimumChallengeDetectionRate,
    ));
  }
}

function check(
  id: string,
  passed: boolean,
  measured: number | string,
  required: number | string,
): VisualFeasibilityCheck {
  return { id, passed, measured, required };
}

function sum<T>(values: readonly T[], select: (value: T) => number): number {
  return values.reduce((total, value) => total + select(value), 0);
}
