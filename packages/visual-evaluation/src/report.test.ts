import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { evaluateVisualFeasibility } from "./evaluate.ts";
import { parseVisualFeasibilityReport } from "./parse.ts";
import {
  visualFeasibilityScenarios,
  VisualReportError,
  type VisualCaptureIssue,
  type VisualFeasibilityScenario,
} from "./types.ts";

const expectedIssue: Readonly<
  Partial<Record<VisualFeasibilityScenario, VisualCaptureIssue>>
> = {
  "low-light": "noFace",
  "face-too-far": "faceTooFar",
  "face-too-close": "faceTooClose",
  "face-off-center": "faceOffCenter",
  "head-turned": "headTurned",
  "mouth-covered": "mouthLandmarksUnavailable",
  "multiple-faces": "multipleFaces",
};

test("strict parsing accepts a privacy-safe aggregate report", () => {
  const report = parseVisualFeasibilityReport(validReport("protocol-compliant"));

  assert.equal(report.frames.totalFrames, 100);
  assert.equal(report.latency.p95Bucket, "le-100");
  assert.equal(report.configuration.rawFramesRetained, false);
  assert.equal(report.configuration.rawLandmarksRetained, false);
  assert.equal(report.configuration.uploaded, false);
});

test("the canonical Swift-compatible fixture parses without contract drift", async () => {
  const fixture = JSON.parse(await readFile(
    new URL("../fixtures/visual-feasibility-report.valid.json", import.meta.url),
    "utf8",
  )) as unknown;

  const report = parseVisualFeasibilityReport(fixture);

  assert.equal(report.sessionID, "00000000-0000-4000-8000-000000000001");
  assert.equal(report.frames.framesWithAnyIssue, 1);
  assert.equal(report.latency.p95Bucket, "le-200");
});

test("an unmeasured Swift latency summary may encode p95 as null", () => {
  const value = validReport("protocol-compliant") as unknown as Record<string, unknown>;
  const latency = value.latency as Record<string, unknown>;
  latency.measuredFrames = 0;
  latency.meanMilliseconds = 0;
  latency.maximumMilliseconds = 0;
  latency.p95Bucket = null;
  latency.bucketCounts = {};

  const report = parseVisualFeasibilityReport(value);

  assert.equal(report.latency.p95Bucket, undefined);
});

test("reports fail closed on retention, extra fields, and inconsistent summaries", () => {
  const retained = validReport("protocol-compliant");
  retained.configuration.rawFramesRetained = true;
  assert.throws(
    () => parseVisualFeasibilityReport(retained),
    (error) => error instanceof VisualReportError
      && /rawFramesRetained/.test(error.message),
  );

  const extra = validReport("protocol-compliant") as Record<string, unknown>;
  extra.rawLandmarks = [{ x: 0.2, y: 0.3 }];
  assert.throws(
    () => parseVisualFeasibilityReport(extra),
    /unknown fields/,
  );

  const inconsistent = validReport("protocol-compliant");
  inconsistent.latency.p95Bucket = "le-25";
  assert.throws(
    () => parseVisualFeasibilityReport(inconsistent),
    /p95Bucket does not match/,
  );

  const simulator = validReport("protocol-compliant");
  simulator.device.hardwareIdentifier = "arm64";
  assert.throws(
    () => parseVisualFeasibilityReport(simulator),
    /physical iPhone or iPad/,
  );

  const overlapping = validReport("face-too-far");
  overlapping.frames.framesWithAnyIssue = 20;
  overlapping.frames.challengeHitFrames = 20;
  assert.throws(
    () => parseVisualFeasibilityReport(overlapping),
    /issue count exceeds framesWithAnyIssue/,
  );

  const latencyMismatch = validReport("protocol-compliant");
  latencyMismatch.latency.meanMilliseconds = 10;
  latencyMismatch.latency.maximumMilliseconds = 20;
  assert.throws(
    () => parseVisualFeasibilityReport(latencyMismatch),
    /maximum does not match/,
  );
});

test("the advancement evaluator requires every scenario and device gate", () => {
  const scenarios = visualFeasibilityScenarios.filter(
    (scenario) => scenario !== "unstructured",
  );
  const reports = scenarios.flatMap((scenario, scenarioIndex) =>
    [0, 1, 2].map((hardwareIndex) =>
      parseVisualFeasibilityReport(validReport(
        scenario,
        ["iPhone15,2", "iPhone16,1", "iPad14,5"][hardwareIndex]!,
        scenarioIndex * 3 + hardwareIndex,
      ))));

  const evaluation = evaluateVisualFeasibility(reports);

  assert.equal(evaluation.status, "pass");
  assert.ok(evaluation.checks.length > 60);
  assert.equal(evaluation.checks.every((check) => check.passed), true);
  assert.match(evaluation.limitations[0] ?? "", /does not validate an articulation cue/);
});

test("green compliant frames alone cannot pass the feasibility gate", () => {
  const report = parseVisualFeasibilityReport(validReport("protocol-compliant"));
  const evaluation = evaluateVisualFeasibility([report, report]);

  assert.equal(evaluation.status, "fail");
  assert.equal(
    evaluation.checks.find((check) => check.id === "hardware-coverage")?.passed,
    false,
  );
  assert.equal(
    evaluation.checks.find((check) =>
      check.id === "scenario-low-light-hardware-iPhone15,2-frames")?.passed,
    false,
  );
  assert.equal(
    evaluation.checks.find((check) => check.id === "unique-session-ids")?.passed,
    false,
  );
});

test("reports without full latency coverage cannot pass", () => {
  const value = validReport("protocol-compliant") as unknown as Record<string, unknown>;
  const latency = value.latency as Record<string, unknown>;
  latency.measuredFrames = 0;
  latency.meanMilliseconds = 0;
  latency.maximumMilliseconds = 0;
  latency.p95Bucket = null;
  latency.bucketCounts = {};
  const report = parseVisualFeasibilityReport(value);

  const evaluation = evaluateVisualFeasibility([report]);

  assert.equal(
    evaluation.checks.find((check) => check.id === "complete-latency-coverage")?.passed,
    false,
  );
});

test("every advancement threshold fails independently when its evidence regresses", () => {
  type RawReport = ReturnType<typeof validReport>;
  const cases: readonly {
    name: string;
    checkID: string;
    mutate: (reports: RawReport[]) => void;
  }[] = [
    {
      name: "minimum frame count",
      checkID: "scenario-low-light-hardware-iPhone15,2-frames",
      mutate: (reports) => {
        const report = reports[3]!;
        report.frames.totalFrames = 99;
        report.latency.measuredFrames = 99;
        report.latency.bucketCounts["le-100"] = 89;
      },
    },
    {
      name: "compliant usable rate",
      checkID: "scenario-protocol-compliant-hardware-iPhone15,2-usable-rate",
      mutate: (reports) => {
        reports[0]!.frames.usableFrames = 94;
        reports[0]!.frames.usableFrameRate = 0.94;
      },
    },
    {
      name: "challenge detection rate",
      checkID: "scenario-low-light-hardware-iPhone15,2-detection-rate",
      mutate: (reports) => {
        reports[3]!.frames.challengeHitFrames = 89;
      },
    },
    {
      name: "extraction failure rate",
      checkID: "scenario-low-light-hardware-iPhone15,2-extraction-failure-rate",
      mutate: (reports) => {
        const report = reports[3]!;
        report.frames.extractionFailures = 2;
        report.latency.measuredFrames = 98;
        report.latency.bucketCounts["le-100"] = 88;
      },
    },
    {
      name: "processing latency",
      checkID: "processing-latency-p95",
      mutate: (reports) => {
        const report = reports[0]!;
        report.latency.maximumMilliseconds = 150;
        report.latency.p95Bucket = "le-200";
        const buckets: Record<string, number> = report.latency.bucketCounts;
        delete buckets["le-100"];
        buckets["le-200"] = 90;
      },
    },
    {
      name: "thermal state",
      checkID: "thermal-state",
      mutate: (reports) => {
        reports[0]!.runtime.maximumThermalState = "serious";
      },
    },
    {
      name: "Low Power Mode",
      checkID: "low-power-disabled",
      mutate: (reports) => {
        reports[0]!.runtime.lowPowerModeObserved = true;
      },
    },
    {
      name: "runtime consistency",
      checkID: "single-runtime-version",
      mutate: (reports) => {
        reports[0]!.runtimeVersion = "different-runtime-v1";
      },
    },
    {
      name: "protocol consistency",
      checkID: "single-protocol",
      mutate: (reports) => {
        reports[0]!.configuration.protocolID = "different-protocol-v1";
      },
    },
    {
      name: "app build consistency",
      checkID: "single-app-build",
      mutate: (reports) => {
        reports[0]!.device.buildVersion = "2";
      },
    },
  ];

  for (const gateCase of cases) {
    const rawReports = fullPassingMatrix();
    gateCase.mutate(rawReports);
    const evaluation = evaluateVisualFeasibility(
      rawReports.map(parseVisualFeasibilityReport),
    );
    const result = evaluation.checks.find((check) => check.id === gateCase.checkID);

    assert.equal(result?.passed, false, gateCase.name);
    assert.equal(evaluation.status, "fail", gateCase.name);
  }
});

test("scenario evidence cannot be substituted with an unrelated capture issue", () => {
  const unrelated = validReport("low-light");
  unrelated.frames.issueCounts = { faceOffCenter: 90 };

  assert.throws(
    () => parseVisualFeasibilityReport(unrelated),
    /challengeHitFrames exceeds scenario-specific issue evidence/,
  );

  const uncovered = validReport("low-light");
  uncovered.frames.framesWithAnyIssue = 91;
  assert.throws(
    () => parseVisualFeasibilityReport(uncovered),
    /issue counts do not cover framesWithAnyIssue/,
  );
});

function fullPassingMatrix(): ReturnType<typeof validReport>[] {
  const scenarios = visualFeasibilityScenarios.filter(
    (scenario) => scenario !== "unstructured",
  );
  return scenarios.flatMap((scenario, scenarioIndex) =>
    ["iPhone15,2", "iPhone16,1", "iPad14,5"].map(
      (hardwareIdentifier, hardwareIndex) => validReport(
        scenario,
        hardwareIdentifier,
        scenarioIndex * 3 + hardwareIndex,
      ),
    ));
}

function validReport(
  scenario: Exclude<VisualFeasibilityScenario, "unstructured">,
  hardwareIdentifier = "iPhone15,2",
  sessionIndex = 0,
) {
  const issue = expectedIssue[scenario];
  const compliant = scenario === "protocol-compliant";
  return {
    schemaVersion: "visual-feasibility-report-v1",
    sessionID: `00000000-0000-4000-8000-${String(sessionIndex + 1).padStart(12, "0")}`,
    runtimeVersion: "apple-vision-landmarks-feasibility-v1",
    startedAt: "2026-07-10T18:00:00.000Z",
    endedAt: "2026-07-10T18:01:00.000Z",
    configuration: {
      protocolID: "bilabial-closure-v1",
      scenario,
      debugOnly: true,
      rawFramesRetained: false,
      rawLandmarksRetained: false,
      uploaded: false,
    },
    device: {
      hardwareIdentifier,
      systemName: "iOS",
      systemVersion: "26.2",
      appVersion: "0.1.0",
      buildVersion: "1",
    },
    frames: {
      totalFrames: 100,
      usableFrames: compliant ? 95 : 0,
      framesWithAnyIssue: compliant ? 0 : 90,
      challengeHitFrames: compliant ? 0 : 90,
      extractionFailures: 0,
      usableFrameRate: compliant ? 0.95 : 0,
      meanQualityScore: compliant ? 0.9 : 0.2,
      issueCounts: issue === undefined ? {} : { [issue]: 90 },
    },
    latency: {
      measuredFrames: 100,
      meanMilliseconds: 60,
      maximumMilliseconds: 95,
      p95Bucket: "le-100",
      bucketCounts: { "le-50": 10, "le-100": 90 },
    },
    runtime: {
      maximumThermalState: "fair",
      lowPowerModeObserved: false,
    },
  };
}
