import type {
  ActivePracticeAssignment,
  LearnerDeviceContext,
  PracticeAttemptAnalysisInput,
  PracticeAttemptInput,
  PracticeAttemptReceipt,
} from "@speech-therapy/platform-data";

import { ApiRequestError, apiErrorResponse, jsonNoStore } from "./api-response.ts";
import type {
  BenchmarkAttemptAnalysis,
  BenchmarkAttemptScoring,
} from "./benchmark-attempt-scorer.ts";
import { foundationExercise } from "./exercise-registry.ts";
import { learnerDeviceToken } from "./learner-device-authorization.ts";
import { decodePcm16Wave, type DecodedWaveCapture } from "./wave-capture.ts";

interface LearnerAttemptDataBoundary {
  authorizeLearnerDeviceRequest(
    token: string,
    operation: "attempt-upload",
  ): Promise<LearnerDeviceContext | undefined>;
  getActivePracticeAssignment(
    context: LearnerDeviceContext,
  ): Promise<ActivePracticeAssignment | undefined>;
  recordPracticeAttempt(
    context: LearnerDeviceContext,
    input: PracticeAttemptInput,
  ): Promise<PracticeAttemptReceipt>;
  hasPracticeAttemptAnalysis(
    context: LearnerDeviceContext,
    attemptId: string,
  ): Promise<boolean>;
  recordPracticeAttemptAnalysis(
    context: LearnerDeviceContext,
    input: PracticeAttemptAnalysisInput,
  ): Promise<void>;
}

export interface LearnerAttemptUploadDependencies {
  getService(): LearnerAttemptDataBoundary;
  getBenchmarkScorer(): BenchmarkAttemptScoring | undefined;
  reportBenchmarkError?(
    kind: "lookup-failed" | "inference-failed" | "persistence-failed",
  ): void;
}

const attemptIdentifier = /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/;

function integerHeader(request: Request, name: string): number | undefined {
  const value = request.headers.get(name);
  if (!value || !/^\d{1,2}$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : undefined;
}

function bindAttemptId(
  analysis: BenchmarkAttemptAnalysis,
  attemptId: string,
): PracticeAttemptAnalysisInput {
  return Object.assign({ attemptId }, analysis);
}

async function recordBenchmarkAnalysis(
  context: LearnerDeviceContext,
  attemptId: string,
  exerciseId: string,
  capture: DecodedWaveCapture,
  dependencies: LearnerAttemptUploadDependencies,
): Promise<void> {
  if (!context.researchUse || capture.evidence.status !== "accepted-silent") return;
  const scorer = dependencies.getBenchmarkScorer();
  if (!scorer) return;
  const service = dependencies.getService();
  try {
    if (await service.hasPracticeAttemptAnalysis(context, attemptId)) return;
  } catch {
    dependencies.reportBenchmarkError?.("lookup-failed");
    return;
  }

  const startedAt = performance.now();
  let analysis: BenchmarkAttemptAnalysis;
  try {
    analysis = await scorer.score(capture.audio, exerciseId);
  } catch {
    dependencies.reportBenchmarkError?.("inference-failed");
    try {
      analysis = scorer.unavailable(performance.now() - startedAt);
    } catch {
      return;
    }
  }
  try {
    await service.recordPracticeAttemptAnalysis(
      context,
      bindAttemptId(analysis, attemptId),
    );
  } catch {
    dependencies.reportBenchmarkError?.("persistence-failed");
  }
}

async function readBoundedBody(
  request: Request,
  maximumBytes: number,
): Promise<ArrayBuffer> {
  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximumBytes) {
        await reader.cancel();
        throw new ApiRequestError(
          413,
          "payload-too-large",
          "Practice audio is too large.",
        );
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const combined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return combined.buffer;
}

export async function handleLearnerAttemptUpload(
  request: Request,
  dependencies: LearnerAttemptUploadDependencies,
): Promise<Response> {
  try {
    const token = learnerDeviceToken(request);
    if (!token) {
      throw new ApiRequestError(
        401,
        "device-session-required",
        "This practice device must be enrolled again.",
      );
    }
    const context = await dependencies
      .getService()
      .authorizeLearnerDeviceRequest(token, "attempt-upload");
    if (!context) {
      throw new ApiRequestError(
        401,
        "device-session-expired",
        "This practice device session is no longer active.",
      );
    }
    const contentType = request.headers.get("content-type")?.split(";", 1)[0];
    if (contentType !== "audio/wav" && contentType !== "audio/x-wav") {
      throw new ApiRequestError(
        415,
        "unsupported-media-type",
        "Practice audio must be a PCM WAVE capture.",
      );
    }
    const declaredLength = Number(request.headers.get("content-length"));
    if (Number.isFinite(declaredLength) && declaredLength > 200_000) {
      throw new ApiRequestError(413, "payload-too-large", "Practice audio is too large.");
    }
    const attemptId = request.headers.get("x-cadence-attempt-id") ?? "";
    const exerciseId = request.headers.get("x-cadence-exercise-id") ?? "";
    if (!attemptIdentifier.test(attemptId)) {
      throw new ApiRequestError(
        422,
        "invalid-attempt",
        "A valid attempt identifier is required.",
      );
    }
    const exercise = foundationExercise(exerciseId);
    if (!exercise) {
      throw new ApiRequestError(
        422,
        "unsupported-exercise",
        "This exercise is not available for silent practice.",
      );
    }
    const assignmentId = request.headers.get("x-cadence-assignment-id") ?? "";
    const repetitionIndex = integerHeader(
      request,
      "x-cadence-repetition-index",
    );
    const retryIndex = integerHeader(request, "x-cadence-retry-index");
    if (
      !attemptIdentifier.test(assignmentId) ||
      repetitionIndex === undefined ||
      retryIndex === undefined
    ) {
      throw new ApiRequestError(
        422,
        "invalid-assignment-attempt",
        "Assignment, repetition, and retry evidence are required.",
      );
    }
    const assignment = await dependencies
      .getService()
      .getActivePracticeAssignment(context);
    if (
      !assignment ||
      assignment.id !== assignmentId ||
      assignment.exerciseId !== exerciseId ||
      repetitionIndex < 1 ||
      repetitionIndex > assignment.attemptTarget ||
      retryIndex < 0 ||
      retryIndex > assignment.retryLimit
    ) {
      throw new ApiRequestError(
        409,
        "assignment-changed",
        "The clinician assignment changed. Refresh practice before recording.",
      );
    }
    const bytes = await readBoundedBody(request, 200_000);
    let capture;
    try {
      capture = decodePcm16Wave(bytes);
    } catch {
      throw new ApiRequestError(
        422,
        "invalid-audio",
        "The practice capture could not be read safely.",
      );
    }
    const receipt = await dependencies.getService().recordPracticeAttempt(context, {
      attemptId,
      assignmentId,
      repetitionIndex,
      retryIndex,
      exerciseId: exercise.id,
      protocolId: exercise.protocolId,
      status: capture.evidence.status,
      durationMilliseconds: capture.evidence.durationMilliseconds,
      sampleRateHertz: capture.evidence.sampleRateHertz,
      rmsDbfs: capture.evidence.rmsDbfs,
      peakAmplitude: capture.evidence.peakAmplitude,
      reasonCodes: capture.evidence.reasonCodes,
    });
    await recordBenchmarkAnalysis(
      context,
      attemptId,
      exercise.id,
      capture,
      dependencies,
    );
    return jsonNoStore(receipt, { status: 201 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
