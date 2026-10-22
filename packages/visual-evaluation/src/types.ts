export const visualFeasibilityScenarios = [
  "protocol-compliant",
  "low-light",
  "face-too-far",
  "face-too-close",
  "face-off-center",
  "head-turned",
  "mouth-covered",
  "multiple-faces",
  "unstructured",
] as const;

export type VisualFeasibilityScenario =
  (typeof visualFeasibilityScenarios)[number];

export const visualCaptureIssues = [
  "noFace",
  "multipleFaces",
  "faceTooFar",
  "faceTooClose",
  "faceOffCenter",
  "headTurned",
  "mouthLandmarksUnavailable",
  "poseUnavailable",
  "invalidObservation",
] as const;

export type VisualCaptureIssue = (typeof visualCaptureIssues)[number];

export const latencyBuckets = [
  "le-25",
  "le-50",
  "le-100",
  "le-200",
  "le-500",
  "gt-500",
] as const;

export type LatencyBucket = (typeof latencyBuckets)[number];

export const thermalStates = [
  "nominal",
  "fair",
  "serious",
  "critical",
  "unknown",
] as const;

export type ThermalState = (typeof thermalStates)[number];

export interface VisualFeasibilityReport {
  readonly schemaVersion: "visual-feasibility-report-v1";
  readonly sessionID: string;
  readonly runtimeVersion: string;
  readonly startedAt: string;
  readonly endedAt: string;
  readonly configuration: {
    readonly protocolID: string;
    readonly scenario: VisualFeasibilityScenario;
    readonly debugOnly: true;
    readonly rawFramesRetained: false;
    readonly rawLandmarksRetained: false;
    readonly uploaded: false;
  };
  readonly device: {
    readonly hardwareIdentifier: string;
    readonly systemName: string;
    readonly systemVersion: string;
    readonly appVersion: string;
    readonly buildVersion: string;
  };
  readonly frames: {
    readonly totalFrames: number;
    readonly usableFrames: number;
    readonly framesWithAnyIssue: number;
    readonly challengeHitFrames: number;
    readonly extractionFailures: number;
    readonly usableFrameRate: number;
    readonly meanQualityScore: number;
    readonly issueCounts: Readonly<Partial<Record<VisualCaptureIssue, number>>>;
  };
  readonly latency: {
    readonly measuredFrames: number;
    readonly meanMilliseconds: number;
    readonly maximumMilliseconds: number;
    readonly p95Bucket?: LatencyBucket;
    readonly bucketCounts: Readonly<Partial<Record<LatencyBucket, number>>>;
  };
  readonly runtime: {
    readonly maximumThermalState: ThermalState;
    readonly lowPowerModeObserved: boolean;
  };
}

export class VisualReportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VisualReportError";
  }
}
