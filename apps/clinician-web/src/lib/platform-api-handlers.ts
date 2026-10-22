import type {
  ActorContext,
  ConsentSnapshotInput,
  ConsentSnapshotRecord,
  DeletionReceipt,
  LearnerDetail,
  LearnerDeviceSessionReceipt,
  LearnerDeviceSessionRevocationReceipt,
  LearnerDeviceSessionRotationReceipt,
  LearnerDeviceSessionSummary,
  LearnerExport,
  LearnerRecord,
  LearnerSummary,
  PracticeAssignmentInput,
  PracticeAssignmentRecord,
} from "@speech-therapy/platform-data";

import {
  ApiRequestError,
  apiErrorResponse,
  jsonNoStore,
  readJsonObject,
} from "./api-response.ts";

interface PlatformDataBoundary {
  createLearner(actor: ActorContext, displayLabel: string): Promise<LearnerRecord>;
  listLearners(actor: ActorContext): Promise<readonly LearnerSummary[]>;
  getLearner(actor: ActorContext, learnerId: string): Promise<LearnerDetail>;
  createConsentSnapshot(
    actor: ActorContext,
    input: ConsentSnapshotInput,
  ): Promise<ConsentSnapshotRecord>;
  exportLearner(actor: ActorContext, learnerId: string): Promise<LearnerExport>;
  deleteLearner(actor: ActorContext, learnerId: string): Promise<DeletionReceipt>;
  issueLearnerDeviceSession(
    actor: ActorContext,
    learnerId: string,
    lifetimeHours?: number,
  ): Promise<LearnerDeviceSessionReceipt>;
  listLearnerDeviceSessions(
    actor: ActorContext,
    learnerId: string,
  ): Promise<readonly LearnerDeviceSessionSummary[]>;
  revokeLearnerDeviceSession(
    actor: ActorContext,
    learnerId: string,
    sessionId: string,
  ): Promise<LearnerDeviceSessionRevocationReceipt>;
  rotateLearnerDeviceSession(
    actor: ActorContext,
    learnerId: string,
    sessionId: string,
    lifetimeHours?: number,
  ): Promise<LearnerDeviceSessionRotationReceipt>;
  createPracticeAssignment(
    actor: ActorContext,
    input: PracticeAssignmentInput,
  ): Promise<PracticeAssignmentRecord>;
}

export async function handleLearnerList(
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const learners = await dependencies.getService().listLearners(actor);
    return jsonNoStore({ learners });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleLearnerGet(
  learnerId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const learner = await dependencies.getService().getLearner(actor, learnerId);
    return jsonNoStore({ learner });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleLearnerCreate(
  request: Request,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const body = await readJsonObject(request);
    if (
      Object.keys(body).length !== 1 ||
      typeof body.displayLabel !== "string"
    ) {
      throw new ApiRequestError(
        422,
        "invalid-learner",
        "A clinic-approved learner display label is required.",
      );
    }
    const learner = await dependencies
      .getService()
      .createLearner(actor, body.displayLabel);
    return jsonNoStore({ learner }, { status: 201 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export interface PlatformApiDependencies {
  requireActor(): Promise<ActorContext>;
  getService(): PlatformDataBoundary;
}

const consentKeys = [
  "noticeVersion",
  "audioProcessing",
  "videoProcessing",
  "clinicianReview",
  "researchUse",
  "assentStatus",
] as const;

function parseConsentBody(
  learnerId: string,
  value: Record<string, unknown>,
): ConsentSnapshotInput {
  if (
    Object.keys(value).some(
      (key) => !(consentKeys as readonly string[]).includes(key),
    ) ||
    typeof value.noticeVersion !== "string" ||
    typeof value.audioProcessing !== "boolean" ||
    typeof value.videoProcessing !== "boolean" ||
    typeof value.clinicianReview !== "boolean" ||
    typeof value.researchUse !== "boolean" ||
    typeof value.assentStatus !== "string" ||
    !["not-applicable", "affirmed", "declined", "withdrawn"].includes(
      value.assentStatus,
    )
  ) {
    throw new ApiRequestError(
      422,
      "invalid-consent",
      "Consent choices and assent status are incomplete or unsupported.",
    );
  }
  return {
    learnerId,
    noticeVersion: value.noticeVersion,
    audioProcessing: value.audioProcessing,
    videoProcessing: value.videoProcessing,
    clinicianReview: value.clinicianReview,
    researchUse: value.researchUse,
    assentStatus: value.assentStatus as ConsentSnapshotInput["assentStatus"],
  };
}

export async function handleConsentPost(
  request: Request,
  learnerId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const input = parseConsentBody(learnerId, await readJsonObject(request));
    const snapshot = await dependencies
      .getService()
      .createConsentSnapshot(actor, input);
    return jsonNoStore({ snapshot }, { status: 201 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleDeviceSessionPost(
  request: Request,
  learnerId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const body = await readJsonObject(request);
    if (
      Object.keys(body).some((key) => key !== "lifetimeHours") ||
      (body.lifetimeHours !== undefined &&
        (typeof body.lifetimeHours !== "number" ||
          !Number.isInteger(body.lifetimeHours)))
    ) {
      throw new ApiRequestError(
        422,
        "invalid-device-session",
        "Device-session lifetime must be a whole number of hours.",
      );
    }
    const receipt = await dependencies
      .getService()
      .issueLearnerDeviceSession(
        actor,
        learnerId,
        body.lifetimeHours as number | undefined,
      );
    return jsonNoStore({ receipt }, { status: 201 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleDeviceSessionList(
  learnerId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const sessions = await dependencies
      .getService()
      .listLearnerDeviceSessions(actor, learnerId);
    return jsonNoStore({ sessions });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleDeviceSessionDelete(
  request: Request,
  learnerId: string,
  sessionId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const body = await readJsonObject(request);
    if (
      Object.keys(body).length !== 1 ||
      body.confirmation !== "REVOKE DEVICE ACCESS"
    ) {
      throw new ApiRequestError(
        422,
        "invalid-device-session-revocation",
        "Explicit device-access revocation confirmation is required.",
      );
    }
    const receipt = await dependencies
      .getService()
      .revokeLearnerDeviceSession(actor, learnerId, sessionId);
    return jsonNoStore({ receipt });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleDeviceSessionRotate(
  request: Request,
  learnerId: string,
  sessionId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const body = await readJsonObject(request);
    if (
      Object.keys(body).length !== 2 ||
      body.confirmation !== "ROTATE DEVICE ACCESS" ||
      typeof body.lifetimeHours !== "number" ||
      !Number.isInteger(body.lifetimeHours)
    ) {
      throw new ApiRequestError(
        422,
        "invalid-device-session-rotation",
        "Explicit rotation confirmation and a whole-number lifetime are required.",
      );
    }
    const receipt = await dependencies
      .getService()
      .rotateLearnerDeviceSession(
        actor,
        learnerId,
        sessionId,
        body.lifetimeHours,
      );
    return jsonNoStore({ receipt }, { status: 201 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handlePracticeAssignmentPost(
  request: Request,
  learnerId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const body = await readJsonObject(request);
    const allowedKeys = ["exerciseId", "attemptTarget", "retryLimit", "planFitConfirmed"];
    if (
      Object.keys(body).some((key) => !allowedKeys.includes(key)) ||
      Object.keys(body).length !== allowedKeys.length ||
      typeof body.exerciseId !== "string" ||
      typeof body.attemptTarget !== "number" ||
      !Number.isInteger(body.attemptTarget) ||
      typeof body.retryLimit !== "number" ||
      !Number.isInteger(body.retryLimit) ||
      body.planFitConfirmed !== true
    ) {
      throw new ApiRequestError(
        422,
        "invalid-practice-assignment",
        "Exercise, dose, retry limit, and clinician plan-fit confirmation are required.",
      );
    }
    const assignment = await dependencies.getService().createPracticeAssignment(
      actor,
      {
        learnerId,
        exerciseId: body.exerciseId,
        attemptTarget: body.attemptTarget,
        retryLimit: body.retryLimit,
      },
    );
    return jsonNoStore({ assignment }, { status: 201 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleLearnerExport(
  request: Request,
  learnerId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const body = await readJsonObject(request);
    if (Object.keys(body).length !== 0) {
      throw new ApiRequestError(
        422,
        "invalid-request",
        "Learner exports do not accept request fields.",
      );
    }
    const exported = await dependencies.getService().exportLearner(actor, learnerId);
    return jsonNoStore(exported, {
      headers: {
        "content-disposition": `attachment; filename="cadence-learner-${learnerId}.json"`,
      },
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function handleDeletionPost(
  request: Request,
  learnerId: string,
  dependencies: PlatformApiDependencies,
): Promise<Response> {
  try {
    const actor = await dependencies.requireActor();
    const body = await readJsonObject(request);
    if (
      Object.keys(body).length !== 1 ||
      body.confirmation !== "DELETE LEARNER DATA"
    ) {
      throw new ApiRequestError(
        422,
        "deletion-confirmation-required",
        "Explicit deletion confirmation is required.",
      );
    }
    const receipt = await dependencies.getService().deleteLearner(actor, learnerId);
    return jsonNoStore({ receipt });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
