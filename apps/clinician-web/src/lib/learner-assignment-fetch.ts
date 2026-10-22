import type {
  ActivePracticeAssignment,
  LearnerDeviceContext,
} from "@speech-therapy/platform-data";

import { ApiRequestError, apiErrorResponse, jsonNoStore } from "./api-response.ts";
import { learnerDeviceToken } from "./learner-device-authorization.ts";

interface LearnerAssignmentDataBoundary {
  authorizeLearnerDeviceRequest(
    token: string,
    operation: "assignment-read",
  ): Promise<LearnerDeviceContext | undefined>;
  getActivePracticeAssignment(
    context: LearnerDeviceContext,
  ): Promise<ActivePracticeAssignment | undefined>;
}

export interface LearnerAssignmentFetchDependencies {
  getService(): LearnerAssignmentDataBoundary;
}

export async function handleLearnerAssignmentFetch(
  request: Request,
  dependencies: LearnerAssignmentFetchDependencies,
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
      .authorizeLearnerDeviceRequest(token, "assignment-read");
    if (!context) {
      throw new ApiRequestError(
        401,
        "device-session-expired",
        "This practice device session is no longer active.",
      );
    }
    const assignment = await dependencies
      .getService()
      .getActivePracticeAssignment(context);
    if (!assignment) {
      return new Response(null, {
        status: 204,
        headers: { "cache-control": "private, no-store, max-age=0" },
      });
    }
    return jsonNoStore({
      schemaVersion: "learner-practice-assignment-v1",
      assignmentId: assignment.id,
      version: assignment.version,
      exerciseRegistryVersion: assignment.exerciseRegistryVersion,
      exerciseDefinitionSha256: assignment.exerciseDefinitionSha256,
      exerciseId: assignment.exerciseId,
      protocolId: assignment.protocolId,
      prompt: assignment.prompt,
      targetLabel: assignment.targetLabel,
      attemptTarget: assignment.attemptTarget,
      retryLimit: assignment.retryLimit,
      progress: assignment.progress,
      visualProcessingEnabled: false,
      feedbackAvailable: false,
      releasePosture: "candidate-silent-only",
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
