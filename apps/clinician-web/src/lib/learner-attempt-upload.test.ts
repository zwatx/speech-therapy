import assert from "node:assert/strict";
import test from "node:test";

import type {
  ActivePracticeAssignment,
  LearnerDeviceContext,
  PracticeAttemptAnalysisInput,
  PracticeAttemptInput,
  PracticeAttemptReceipt,
} from "@speech-therapy/platform-data";
import { PlatformDataError } from "@speech-therapy/platform-data";

import type {
  BenchmarkAttemptAnalysis,
  BenchmarkAttemptScoring,
} from "./benchmark-attempt-scorer.ts";
import {
  handleLearnerAttemptUpload,
  type LearnerAttemptUploadDependencies,
} from "./learner-attempt-upload.ts";
import { inspectPcm16Wave } from "./wave-capture.ts";

const token = "x".repeat(43);
const context: LearnerDeviceContext = {
  sessionId: "device-session-test",
  tenantId: "tenant-test",
  learnerId: "learner-test",
  consentSnapshotId: "consent-test",
  audioProcessing: true,
  videoProcessing: false,
  clinicianReview: true,
  researchUse: false,
};
const assignment: ActivePracticeAssignment = {
  id: "assignment-test",
  tenantId: "tenant-test",
  learnerId: "learner-test",
  version: 1,
  consentSnapshotId: "consent-test",
  exerciseRegistryVersion: "foundation-exercises-v1",
  exerciseDefinitionSha256: "a".repeat(64),
  exerciseId: "foundation-ball-initial-b-v1",
  protocolId: "bilabial-closure-v1",
  prompt: "ball",
  targetLabel: "Beginning /b/",
  attemptTarget: 5,
  retryLimit: 2,
  visualProcessing: false,
  releasePosture: "candidate-silent-only",
  assignedByActorId: "actor-test",
  assignedAt: "2026-07-10T00:00:00.000Z",
  progress: {
    status: "ready",
    acceptedRepetitions: 0,
    repetitionIndex: 1,
    retryIndex: 0,
  },
};

function pcmWave(
  durationSeconds: number = 1,
  amplitude: number = 0.2,
): ArrayBuffer {
  const sampleCount = Math.round(16_000 * durationSeconds);
  const dataLength = sampleCount * 2;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);
  const writeAscii = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16_000, true);
  view.setUint32(28, 32_000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(36, "data");
  view.setUint32(40, dataLength, true);
  for (let index = 0; index < sampleCount; index += 1) {
    const sample = amplitude * Math.sin((2 * Math.PI * 220 * index) / 16_000);
    view.setInt16(44 + index * 2, Math.round(sample * 32_767), true);
  }
  return buffer;
}

class FakeAttemptService {
  resolved = true;
  authorizationError?: Error;
  resolvedContext: LearnerDeviceContext = context;
  recorded?: PracticeAttemptInput;
  analysis?: PracticeAttemptAnalysisInput;
  analysisExists = false;
  analysisError = false;

  async authorizeLearnerDeviceRequest(
    _token: string,
    operation: "attempt-upload",
  ): Promise<LearnerDeviceContext | undefined> {
    assert.equal(operation, "attempt-upload");
    if (this.authorizationError) throw this.authorizationError;
    return this.resolved ? this.resolvedContext : undefined;
  }

  async getActivePracticeAssignment(): Promise<ActivePracticeAssignment> {
    return assignment;
  }

  async recordPracticeAttempt(
    _context: LearnerDeviceContext,
    input: PracticeAttemptInput,
  ): Promise<PracticeAttemptReceipt> {
    this.recorded = input;
    return {
      attemptId: input.attemptId,
      status: input.status,
      feedbackAvailable: false,
      mediaRetained: false,
      reasonCodes: input.reasonCodes,
    };
  }

  async hasPracticeAttemptAnalysis(): Promise<boolean> {
    return this.analysisExists;
  }

  async recordPracticeAttemptAnalysis(
    _context: LearnerDeviceContext,
    input: PracticeAttemptAnalysisInput,
  ): Promise<void> {
    if (this.analysisError) throw new Error("database unavailable");
    this.analysis = input;
    this.analysisExists = true;
  }
}

function dependencies(
  service = new FakeAttemptService(),
  scorer?: BenchmarkAttemptScoring,
): {
  dependencies: LearnerAttemptUploadDependencies;
  service: FakeAttemptService;
  errors: string[];
} {
  const errors: string[] = [];
  return {
    service,
    errors,
    dependencies: {
      getService: () => service,
      getBenchmarkScorer: () => scorer,
      reportBenchmarkError: (kind) => errors.push(kind),
    },
  };
}

const scoredAnalysis: BenchmarkAttemptAnalysis = {
  status: "scored-ambiguous",
  releasePosture: "benchmark-only",
  learnerFeedbackEligible: false,
  checkpointId: "onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX",
  checkpointRevision: "c69750f5043e5e1f8a71ab95dd3b98338c280c92",
  runtime: "@huggingface/transformers@4.2.0",
  modelFileSha256:
    "3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120",
  vocabularyFileSha256:
    "d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0",
  lexiconVersion: "research-ball-initial-b-v1",
  calibrationVersion: "unvalidated-research-v0",
  scoringPolicyVersion: "benchmark-policy-v1",
  pCorrect: 0.3,
  pError: 0.2,
  hypothesisCoverage: 0.5,
  calibrated: false,
  ambiguous: true,
  inferenceMilliseconds: 40,
};

class FakeBenchmarkScorer implements BenchmarkAttemptScoring {
  calls = 0;
  fails = false;

  async score(): Promise<BenchmarkAttemptAnalysis> {
    this.calls += 1;
    if (this.fails) throw new Error("checkpoint unavailable");
    return scoredAnalysis;
  }

  unavailable(inferenceMilliseconds: number): BenchmarkAttemptAnalysis {
    return {
      status: "unavailable",
      releasePosture: "benchmark-only",
      learnerFeedbackEligible: false,
      checkpointId: scoredAnalysis.checkpointId,
      checkpointRevision: scoredAnalysis.checkpointRevision,
      runtime: scoredAnalysis.runtime,
      modelFileSha256: scoredAnalysis.modelFileSha256,
      vocabularyFileSha256: scoredAnalysis.vocabularyFileSha256,
      lexiconVersion: scoredAnalysis.lexiconVersion,
      calibrationVersion: scoredAnalysis.calibrationVersion,
      scoringPolicyVersion: scoredAnalysis.scoringPolicyVersion,
      failureCode: "benchmark-unavailable",
      inferenceMilliseconds: Math.round(inferenceMilliseconds),
    };
  }
}

function uploadRequest(
  body: ArrayBuffer = pcmWave(),
  headers: Record<string, string> = {},
): Request {
  return new Request("https://api.example.test/api/v1/learner-attempts", {
    method: "POST",
    headers: {
      authorization: `CadenceDevice ${token}`,
      "content-type": "audio/wav",
      "x-cadence-attempt-id": "attempt-native-001",
      "x-cadence-assignment-id": assignment.id,
      "x-cadence-repetition-index": "1",
      "x-cadence-retry-index": "0",
      "x-cadence-exercise-id": "foundation-ball-initial-b-v1",
      ...headers,
    },
    body,
  });
}

test("PCM16 inspection derives accepted capture evidence", () => {
  const evidence = inspectPcm16Wave(pcmWave());
  assert.equal(evidence.sampleRateHertz, 16_000);
  assert.equal(evidence.durationMilliseconds, 1_000);
  assert.equal(evidence.status, "accepted-silent");
  assert.deepEqual(evidence.reasonCodes, []);
  assert.ok(evidence.rmsDbfs < 0);
});

test("quiet, short, and clipped captures request a retry", () => {
  const quietAndShort = inspectPcm16Wave(pcmWave(0.2, 0));
  assert.equal(quietAndShort.status, "retry-capture");
  assert.deepEqual(quietAndShort.reasonCodes, [
    "utterance-too-short",
    "audio-too-quiet",
  ]);
  const clipped = inspectPcm16Wave(pcmWave(1, 1));
  assert.ok(clipped.reasonCodes.includes("audio-clipping"));
});

test("bounded captures longer than the exercise window remain clean retries", () => {
  const evidence = inspectPcm16Wave(pcmWave(5.5));
  assert.equal(evidence.durationMilliseconds, 5_500);
  assert.equal(evidence.status, "retry-capture");
  assert.deepEqual(evidence.reasonCodes, ["utterance-too-long"]);
});

test("learner upload authenticates the device and records only derived evidence", async () => {
  const setup = dependencies();
  const response = await handleLearnerAttemptUpload(
    uploadRequest(),
    setup.dependencies,
  );
  const body = (await response.json()) as PracticeAttemptReceipt;

  assert.equal(response.status, 201);
  assert.equal(body.status, "accepted-silent");
  assert.equal(body.feedbackAvailable, false);
  assert.equal(body.mediaRetained, false);
  assert.equal(setup.service.recorded?.exerciseId, "foundation-ball-initial-b-v1");
  assert.equal(setup.service.recorded?.assignmentId, assignment.id);
  assert.equal(setup.service.recorded?.sampleRateHertz, 16_000);
  assert.equal(setup.service.analysis, undefined);
});

test("research-consented accepted audio records aggregate benchmark evidence", async () => {
  const service = new FakeAttemptService();
  service.resolvedContext = { ...context, researchUse: true };
  const scorer = new FakeBenchmarkScorer();
  const setup = dependencies(service, scorer);

  const response = await handleLearnerAttemptUpload(
    uploadRequest(),
    setup.dependencies,
  );
  const body = (await response.json()) as Record<string, unknown>;

  assert.equal(response.status, 201);
  assert.equal(scorer.calls, 1);
  assert.equal(service.analysis?.status, "scored-ambiguous");
  assert.equal(service.analysis?.attemptId, "attempt-native-001");
  assert.equal(service.analysis?.learnerFeedbackEligible, false);
  assert.equal("pCorrect" in body, false);
  assert.deepEqual(setup.errors, []);
});

test("benchmark inference is skipped for retries and completed idempotent analyses", async () => {
  const ordinaryService = new FakeAttemptService();
  const ordinaryScorer = new FakeBenchmarkScorer();
  await handleLearnerAttemptUpload(
    uploadRequest(),
    dependencies(ordinaryService, ordinaryScorer).dependencies,
  );
  assert.equal(ordinaryScorer.calls, 0);

  const retryService = new FakeAttemptService();
  retryService.resolvedContext = { ...context, researchUse: true };
  const retryScorer = new FakeBenchmarkScorer();
  await handleLearnerAttemptUpload(
    uploadRequest(pcmWave(0.2, 0)),
    dependencies(retryService, retryScorer).dependencies,
  );
  assert.equal(retryScorer.calls, 0);
  assert.equal(retryService.analysis, undefined);

  const repeatedService = new FakeAttemptService();
  repeatedService.resolvedContext = { ...context, researchUse: true };
  repeatedService.analysisExists = true;
  const repeatedScorer = new FakeBenchmarkScorer();
  await handleLearnerAttemptUpload(
    uploadRequest(),
    dependencies(repeatedService, repeatedScorer).dependencies,
  );
  assert.equal(repeatedScorer.calls, 0);
});

test("benchmark failures stay silent and persist only safe unavailability", async () => {
  const service = new FakeAttemptService();
  service.resolvedContext = { ...context, researchUse: true };
  const scorer = new FakeBenchmarkScorer();
  scorer.fails = true;
  const setup = dependencies(service, scorer);

  const response = await handleLearnerAttemptUpload(
    uploadRequest(),
    setup.dependencies,
  );
  const body = (await response.json()) as PracticeAttemptReceipt;

  assert.equal(response.status, 201);
  assert.equal(body.feedbackAvailable, false);
  assert.equal(service.analysis?.status, "unavailable");
  assert.deepEqual(setup.errors, ["inference-failed"]);

  service.analysisExists = false;
  service.analysisError = true;
  const persistenceSetup = dependencies(service, new FakeBenchmarkScorer());
  const persistenceResponse = await handleLearnerAttemptUpload(
    uploadRequest(),
    persistenceSetup.dependencies,
  );
  assert.equal(persistenceResponse.status, 201);
  assert.deepEqual(persistenceSetup.errors, ["persistence-failed"]);
});

test("learner upload fails closed for missing or expired device sessions", async () => {
  const missing = await handleLearnerAttemptUpload(
    new Request("https://api.example.test/api/v1/learner-attempts", {
      method: "POST",
      headers: { "content-type": "audio/wav" },
      body: pcmWave(),
    }),
    dependencies().dependencies,
  );
  assert.equal(missing.status, 401);

  const setup = dependencies();
  setup.service.resolved = false;
  const expired = await handleLearnerAttemptUpload(
    uploadRequest(),
    setup.dependencies,
  );
  assert.equal(expired.status, 401);
});

test("attempt upload limits return a private 429 with Retry-After", async () => {
  const setup = dependencies();
  setup.service.authorizationError = new PlatformDataError(
    "rate-limited",
    "This practice device has reached its hourly request limit. Try again after the current UTC hour.",
    { retryAfterSeconds: 71 },
  );
  const response = await handleLearnerAttemptUpload(
    uploadRequest(),
    setup.dependencies,
  );

  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), "71");
  assert.match(response.headers.get("cache-control") ?? "", /no-store/);
});

test("learner upload bounds bytes and rejects malformed audio and exercises", async () => {
  const oversized = await handleLearnerAttemptUpload(
    uploadRequest(pcmWave(), { "content-length": "200001" }),
    dependencies().dependencies,
  );
  assert.equal(oversized.status, 413);

  const streamedOversized = await handleLearnerAttemptUpload(
    uploadRequest(new ArrayBuffer(200_001)),
    dependencies().dependencies,
  );
  assert.equal(streamedOversized.status, 413);

  const malformed = await handleLearnerAttemptUpload(
    uploadRequest(new ArrayBuffer(44)),
    dependencies().dependencies,
  );
  assert.equal(malformed.status, 422);

  const unsupported = await handleLearnerAttemptUpload(
    uploadRequest(pcmWave(), { "x-cadence-exercise-id": "unknown-exercise" }),
    dependencies().dependencies,
  );
  assert.equal(unsupported.status, 422);
});

test("learner upload rejects missing, substituted, and out-of-dose assignment evidence", async () => {
  const missing = await handleLearnerAttemptUpload(
    uploadRequest(pcmWave(), { "x-cadence-assignment-id": "" }),
    dependencies().dependencies,
  );
  assert.equal(missing.status, 422);

  const substituted = await handleLearnerAttemptUpload(
    uploadRequest(new ArrayBuffer(0), {
      "x-cadence-assignment-id": "assignment-substituted",
    }),
    dependencies().dependencies,
  );
  assert.equal(substituted.status, 409);

  const overflow = await handleLearnerAttemptUpload(
    uploadRequest(new ArrayBuffer(0), {
      "x-cadence-repetition-index": "6",
    }),
    dependencies().dependencies,
  );
  assert.equal(overflow.status, 409);
});
