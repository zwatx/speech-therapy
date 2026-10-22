"use server";

import { revalidatePath } from "next/cache";

import type { AssignmentActionState } from "@/lib/portal-action-state";
import { safePortalActionError } from "@/lib/portal-action-error";
import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";

export async function createPracticeAssignmentAction(
  _previous: AssignmentActionState,
  formData: FormData,
): Promise<AssignmentActionState> {
  const learnerId = formData.get("learnerId");
  const exerciseId = formData.get("exerciseId");
  const attemptTarget = Number(formData.get("attemptTarget"));
  const retryLimit = Number(formData.get("retryLimit"));
  const planFitConfirmed = formData.get("planFitConfirmed") === "true";
  const revision = formData.get("formRevision");
  const formRevision = typeof revision === "string" && /^\d{1,10}$/.test(revision)
    ? revision
    : undefined;
  if (
    typeof learnerId !== "string" ||
    typeof exerciseId !== "string" ||
    !Number.isInteger(attemptTarget) ||
    attemptTarget < 1 ||
    attemptTarget > 20 ||
    !Number.isInteger(retryLimit) ||
    retryLimit < 0 ||
    retryLimit > 2
  ) {
    return {
      status: "error",
      message: "Choose an eligible learner, dose, and retry limit.",
      formRevision,
    };
  }
  if (!planFitConfirmed) {
    return {
      status: "error",
      message: "Confirm that this exercise fits the learner's current practice plan.",
      formRevision,
    };
  }
  try {
    const actor = await requireActorContext();
    const assignment = await getPlatformDataService().createPracticeAssignment(
      actor,
      { learnerId, exerciseId, attemptTarget, retryLimit },
    );
    revalidatePath("/assignments");
    revalidatePath(`/learners/${learnerId}`);
    return {
      status: "success",
      message: `Assignment v${assignment.version} is active and bound to current consent.`,
      formRevision,
      assignedLearnerId: assignment.learnerId,
    };
  } catch (error) {
    return { ...safePortalActionError(error), formRevision };
  }
}
