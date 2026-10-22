import {
  latencyBuckets,
  thermalStates,
  visualCaptureIssues,
  visualFeasibilityScenarios,
  VisualReportError,
  type LatencyBucket,
  type VisualFeasibilityReport,
} from "./types.ts";

export function parseVisualFeasibilityReport(
  value: unknown,
): VisualFeasibilityReport {
  const root = object(value, "report", [
    "schemaVersion",
    "sessionID",
    "runtimeVersion",
    "startedAt",
    "endedAt",
    "configuration",
    "device",
    "frames",
    "latency",
    "runtime",
  ]);
  literal(root.schemaVersion, "visual-feasibility-report-v1", "schemaVersion");
  const sessionID = string(root.sessionID, "sessionID", 36);
  if (!/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(sessionID)) {
    fail("sessionID must be a version-4 UUID");
  }
  const runtimeVersion = identifier(root.runtimeVersion, "runtimeVersion");
  const startedAt = timestamp(root.startedAt, "startedAt");
  const endedAt = timestamp(root.endedAt, "endedAt");
  if (Date.parse(endedAt) < Date.parse(startedAt)) {
    fail("endedAt cannot precede startedAt");
  }

  const configuration = object(root.configuration, "configuration", [
    "protocolID",
    "scenario",
    "debugOnly",
    "rawFramesRetained",
    "rawLandmarksRetained",
    "uploaded",
  ]);
  const protocolID = identifier(configuration.protocolID, "configuration.protocolID");
  const scenario = enumeration(
    configuration.scenario,
    visualFeasibilityScenarios,
    "configuration.scenario",
  );
  literal(configuration.debugOnly, true, "configuration.debugOnly");
  literal(configuration.rawFramesRetained, false, "configuration.rawFramesRetained");
  literal(
    configuration.rawLandmarksRetained,
    false,
    "configuration.rawLandmarksRetained",
  );
  literal(configuration.uploaded, false, "configuration.uploaded");

  const device = object(root.device, "device", [
    "hardwareIdentifier",
    "systemName",
    "systemVersion",
    "appVersion",
    "buildVersion",
  ]);
  const parsedDevice = {
    hardwareIdentifier: physicalHardwareIdentifier(device.hardwareIdentifier),
    systemName: string(device.systemName, "device.systemName", 40),
    systemVersion: string(device.systemVersion, "device.systemVersion", 40),
    appVersion: string(device.appVersion, "device.appVersion", 40),
    buildVersion: string(device.buildVersion, "device.buildVersion", 40),
  };

  const frames = object(root.frames, "frames", [
    "totalFrames",
    "usableFrames",
    "framesWithAnyIssue",
    "challengeHitFrames",
    "extractionFailures",
    "usableFrameRate",
    "meanQualityScore",
    "issueCounts",
  ]);
  const totalFrames = integer(frames.totalFrames, "frames.totalFrames", 1);
  const usableFrames = integer(frames.usableFrames, "frames.usableFrames", 0);
  const framesWithAnyIssue = integer(
    frames.framesWithAnyIssue,
    "frames.framesWithAnyIssue",
    0,
  );
  const challengeHitFrames = integer(
    frames.challengeHitFrames,
    "frames.challengeHitFrames",
    0,
  );
  const extractionFailures = integer(
    frames.extractionFailures,
    "frames.extractionFailures",
    0,
  );
  if (usableFrames + extractionFailures > totalFrames) {
    fail("usableFrames plus extractionFailures exceeds totalFrames");
  }
  if (framesWithAnyIssue > totalFrames - extractionFailures) {
    fail("framesWithAnyIssue exceeds observed frames");
  }
  if (challengeHitFrames > framesWithAnyIssue) {
    fail("challengeHitFrames exceeds framesWithAnyIssue");
  }
  const usableFrameRate = probability(frames.usableFrameRate, "frames.usableFrameRate");
  if (Math.abs(usableFrameRate - usableFrames / totalFrames) > 1e-9) {
    fail("usableFrameRate does not match frame counts");
  }
  const meanQualityScore = probability(frames.meanQualityScore, "frames.meanQualityScore");
  const issueCounts = countMap(
    frames.issueCounts,
    visualCaptureIssues,
    "frames.issueCounts",
    totalFrames - extractionFailures,
  );
  const observedFrames = totalFrames - extractionFailures;
  if (usableFrames + framesWithAnyIssue > observedFrames) {
    fail("usableFrames plus framesWithAnyIssue exceeds observed frames");
  }
  if (Object.values(issueCounts).some((count) => count > framesWithAnyIssue)) {
    fail("an issue count exceeds framesWithAnyIssue");
  }
  const issueCountTotal = Object.values(issueCounts).reduce(
    (total, count) => total + count,
    0,
  );
  if (issueCountTotal < framesWithAnyIssue) {
    fail("issue counts do not cover framesWithAnyIssue");
  }
  const expectedCount = expectedChallengeIssues(scenario).reduce(
    (total, issue) => total + (issueCounts[issue] ?? 0),
    0,
  );
  if (challengeHitFrames > expectedCount) {
    fail("challengeHitFrames exceeds scenario-specific issue evidence");
  }

  const latency = object(
    root.latency,
    "latency",
    ["measuredFrames", "meanMilliseconds", "maximumMilliseconds", "bucketCounts"],
    ["p95Bucket"],
  );
  const measuredFrames = integer(latency.measuredFrames, "latency.measuredFrames", 0);
  if (measuredFrames > totalFrames - extractionFailures) {
    fail("latency.measuredFrames exceeds observed frames");
  }
  const meanMilliseconds = finiteNumber(
    latency.meanMilliseconds,
    "latency.meanMilliseconds",
    0,
  );
  const maximumMilliseconds = finiteNumber(
    latency.maximumMilliseconds,
    "latency.maximumMilliseconds",
    0,
  );
  if (meanMilliseconds > maximumMilliseconds) fail("latency mean exceeds maximum");
  const bucketCounts = countMap(
    latency.bucketCounts,
    latencyBuckets,
    "latency.bucketCounts",
    measuredFrames,
  );
  const bucketTotal = Object.values(bucketCounts).reduce((sum, count) => sum + count, 0);
  if (bucketTotal !== measuredFrames) {
    fail("latency bucket counts do not sum to measuredFrames");
  }
  if (measuredFrames === 0 && (meanMilliseconds !== 0 || maximumMilliseconds !== 0)) {
    fail("unmeasured latency must have zero mean and maximum");
  }
  if (measuredFrames > 0) {
    const maximumBucket = latencyBucketForValue(maximumMilliseconds);
    const highestObservedBucket = [...latencyBuckets]
      .reverse()
      .find((bucket) => (bucketCounts[bucket] ?? 0) > 0);
    if (maximumBucket !== highestObservedBucket) {
      fail("latency maximum does not match the highest populated bucket");
    }
  }
  const computedP95 = p95Bucket(bucketCounts, measuredFrames);
  const providedP95 = latency.p95Bucket === undefined || latency.p95Bucket === null
    ? undefined
    : enumeration(latency.p95Bucket, latencyBuckets, "latency.p95Bucket");
  if (providedP95 !== computedP95) fail("latency.p95Bucket does not match bucket counts");

  const runtime = object(root.runtime, "runtime", [
    "maximumThermalState",
    "lowPowerModeObserved",
  ]);
  const maximumThermalState = enumeration(
    runtime.maximumThermalState,
    thermalStates,
    "runtime.maximumThermalState",
  );
  const lowPowerModeObserved = boolean(
    runtime.lowPowerModeObserved,
    "runtime.lowPowerModeObserved",
  );

  return {
    schemaVersion: "visual-feasibility-report-v1",
    sessionID,
    runtimeVersion,
    startedAt,
    endedAt,
    configuration: {
      protocolID,
      scenario,
      debugOnly: true,
      rawFramesRetained: false,
      rawLandmarksRetained: false,
      uploaded: false,
    },
    device: parsedDevice,
    frames: {
      totalFrames,
      usableFrames,
      framesWithAnyIssue,
      challengeHitFrames,
      extractionFailures,
      usableFrameRate,
      meanQualityScore,
      issueCounts,
    },
    latency: {
      measuredFrames,
      meanMilliseconds,
      maximumMilliseconds,
      ...(providedP95 === undefined ? {} : { p95Bucket: providedP95 }),
      bucketCounts,
    },
    runtime: { maximumThermalState, lowPowerModeObserved },
  };
}

function object(
  value: unknown,
  path: string,
  required: readonly string[],
  optional: readonly string[] = [],
): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(`${path} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set([...required, ...optional]);
  const unknown = Object.keys(record).filter((key) => !allowed.has(key));
  if (unknown.length > 0) fail(`${path} contains unknown fields: ${unknown.join(", ")}`);
  const missing = required.filter((key) => !(key in record));
  if (missing.length > 0) fail(`${path} is missing fields: ${missing.join(", ")}`);
  return record;
}

function physicalHardwareIdentifier(value: unknown): string {
  const parsed = string(value, "device.hardwareIdentifier", 40);
  if (!/^(?:iPhone|iPad)\d+,\d+$/.test(parsed)) {
    fail("device.hardwareIdentifier must identify a physical iPhone or iPad");
  }
  return parsed;
}

function string(value: unknown, path: string, maximum: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum) {
    fail(`${path} must be a non-empty string of at most ${maximum} characters`);
  }
  return value;
}

function identifier(value: unknown, path: string): string {
  const parsed = string(value, path, 120);
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{2,119}$/.test(parsed)) {
    fail(`${path} must be an opaque version identifier`);
  }
  return parsed;
}

function timestamp(value: unknown, path: string): string {
  const parsed = string(value, path, 80);
  if (!Number.isFinite(Date.parse(parsed)) || !parsed.includes("T")) {
    fail(`${path} must be an ISO-8601 timestamp`);
  }
  return parsed;
}

function integer(value: unknown, path: string, minimum: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) {
    fail(`${path} must be an integer at least ${minimum}`);
  }
  return value;
}

function finiteNumber(value: unknown, path: string, minimum: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum) {
    fail(`${path} must be a finite number at least ${minimum}`);
  }
  return value;
}

function probability(value: unknown, path: string): number {
  const parsed = finiteNumber(value, path, 0);
  if (parsed > 1) fail(`${path} must be at most 1`);
  return parsed;
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") fail(`${path} must be boolean`);
  return value;
}

function literal<T extends string | boolean>(value: unknown, expected: T, path: string): T {
  if (value !== expected) fail(`${path} must equal ${String(expected)}`);
  return expected;
}

function enumeration<const T extends readonly string[]>(
  value: unknown,
  values: T,
  path: string,
): T[number] {
  if (typeof value !== "string" || !(values as readonly string[]).includes(value)) {
    fail(`${path} is unsupported`);
  }
  return value as T[number];
}

function countMap<const T extends readonly string[]>(
  value: unknown,
  keys: T,
  path: string,
  maximum: number,
): Partial<Record<T[number], number>> {
  const parsed = object(value, path, [], keys);
  const result: Partial<Record<T[number], number>> = {};
  for (const [key, count] of Object.entries(parsed)) {
    const validated = integer(count, `${path}.${key}`, 0);
    if (validated > maximum) fail(`${path}.${key} exceeds available frames`);
    result[key as T[number]] = validated;
  }
  return result;
}

function p95Bucket(
  counts: Readonly<Partial<Record<LatencyBucket, number>>>,
  total: number,
): LatencyBucket | undefined {
  if (total === 0) return undefined;
  const target = Math.ceil(total * 0.95);
  let cumulative = 0;
  for (const bucket of latencyBuckets) {
    cumulative += counts[bucket] ?? 0;
    if (cumulative >= target) return bucket;
  }
  return undefined;
}

function latencyBucketForValue(milliseconds: number): LatencyBucket {
  if (milliseconds <= 25) return "le-25";
  if (milliseconds <= 50) return "le-50";
  if (milliseconds <= 100) return "le-100";
  if (milliseconds <= 200) return "le-200";
  if (milliseconds <= 500) return "le-500";
  return "gt-500";
}

function expectedChallengeIssues(
  scenario: (typeof visualFeasibilityScenarios)[number],
): readonly (typeof visualCaptureIssues)[number][] {
  switch (scenario) {
  case "low-light":
    return ["noFace", "mouthLandmarksUnavailable", "poseUnavailable", "invalidObservation"];
  case "face-too-far": return ["faceTooFar"];
  case "face-too-close": return ["faceTooClose"];
  case "face-off-center": return ["faceOffCenter"];
  case "head-turned": return ["headTurned"];
  case "mouth-covered": return ["mouthLandmarksUnavailable"];
  case "multiple-faces": return ["multipleFaces"];
  case "protocol-compliant":
  case "unstructured":
    return [];
  }
}

function fail(message: string): never {
  throw new VisualReportError(message);
}
