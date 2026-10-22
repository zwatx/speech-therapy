"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type {
  DeviceSessionActionState,
  PortalActionState,
} from "@/lib/portal-action-state";
import { safePortalActionError } from "@/lib/portal-action-error";
import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";

const noticeVersion = "cadence-practice-notice-v1";

function checked(formData: FormData, name: string): boolean {
  return formData.get(name) === "on";
}

export async function saveConsentAction(
  learnerId: string,
  _previous: PortalActionState,
  formData: FormData,
): Promise<PortalActionState> {
  const assentStatus = formData.get("assentStatus");
  if (
    typeof assentStatus !== "string" ||
    !["not-applicable", "affirmed", "declined", "withdrawn"].includes(
      assentStatus,
    )
  ) {
    return { status: "error", message: "Choose the learner assent status." };
  }
  try {
    const actor = await requireActorContext();
    const snapshot = await getPlatformDataService().createConsentSnapshot(actor, {
      learnerId,
      noticeVersion,
      audioProcessing: checked(formData, "audioProcessing"),
      videoProcessing: false,
      clinicianReview: checked(formData, "clinicianReview"),
      researchUse: checked(formData, "researchUse"),
      assentStatus: assentStatus as
        | "not-applicable"
        | "affirmed"
        | "declined"
        | "withdrawn",
    });
    revalidatePath("/learners");
    revalidatePath(`/learners/${learnerId}`);
    return {
      status: "success",
      message: `Consent snapshot v${snapshot.version} was recorded immutably.`,
    };
  } catch (error) {
    return safePortalActionError(error);
  }
}

export async function issueDeviceSessionAction(
  learnerId: string,
  _previous: DeviceSessionActionState,
  formData: FormData,
): Promise<DeviceSessionActionState> {
  const lifetimeValue = formData.get("lifetimeHours");
  const lifetimeHours =
    typeof lifetimeValue === "string" ? Number(lifetimeValue) : Number.NaN;
  if (!Number.isInteger(lifetimeHours) || lifetimeHours < 1 || lifetimeHours > 72) {
    return { status: "error", message: "Choose access between 1 and 72 hours." };
  }
  try {
    const actor = await requireActorContext();
    const receipt = await getPlatformDataService().issueLearnerDeviceSession(
      actor,
      learnerId,
      lifetimeHours,
    );
    revalidatePath(`/learners/${learnerId}`);
    return {
      status: "success",
      message: "A one-time learner-device token was issued.",
      token: receipt.token,
      expiresAt: receipt.expiresAt,
    };
  } catch (error) {
    return safePortalActionError(error);
  }
}

export async function revokeDeviceSessionAction(
  learnerId: string,
  sessionId: string,
  _previous: PortalActionState,
  formData: FormData,
): Promise<PortalActionState> {
  if (formData.get("confirmation") !== "on") {
    return {
      status: "error",
      message: "Confirm that this device must be enrolled again.",
    };
  }
  try {
    const actor = await requireActorContext();
    const receipt = await getPlatformDataService().revokeLearnerDeviceSession(
      actor,
      learnerId,
      sessionId,
    );
    revalidatePath(`/learners/${learnerId}`);
    return {
      status: "success",
      message: receipt.alreadyRevoked
        ? "Device access was already revoked."
        : "Device access was revoked immediately.",
    };
  } catch (error) {
    return safePortalActionError(error);
  }
}

export async function rotateDeviceSessionAction(
  learnerId: string,
  sessionId: string,
  _previous: DeviceSessionActionState,
  formData: FormData,
): Promise<DeviceSessionActionState> {
  const lifetimeValue = formData.get("lifetimeHours");
  const lifetimeHours =
    typeof lifetimeValue === "string" ? Number(lifetimeValue) : Number.NaN;
  if (formData.get("confirmation") !== "on") {
    return {
      status: "error",
      message: "Confirm that the old token will stop working immediately.",
    };
  }
  if (!Number.isInteger(lifetimeHours) || lifetimeHours < 1 || lifetimeHours > 72) {
    return { status: "error", message: "Choose access between 1 and 72 hours." };
  }
  try {
    const actor = await requireActorContext();
    const receipt = await getPlatformDataService().rotateLearnerDeviceSession(
      actor,
      learnerId,
      sessionId,
      lifetimeHours,
    );
    return {
      status: "success",
      message:
        "The old token was revoked and a replacement was issued. Enter it on the device before refreshing this page.",
      token: receipt.token,
      expiresAt: receipt.expiresAt,
    };
  } catch (error) {
    return safePortalActionError(error);
  }
}

export async function deleteLearnerAction(
  learnerId: string,
  _previous: PortalActionState,
  formData: FormData,
): Promise<PortalActionState> {
  if (formData.get("confirmation") !== "DELETE LEARNER DATA") {
    return {
      status: "error",
      message: "Type DELETE LEARNER DATA exactly to confirm deletion.",
    };
  }
  try {
    const actor = await requireActorContext();
    await getPlatformDataService().deleteLearner(actor, learnerId);
  } catch (error) {
    return safePortalActionError(error);
  }
  revalidatePath("/learners");
  redirect("/learners");
}
