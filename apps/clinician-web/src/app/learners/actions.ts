"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";
import type { PortalActionState } from "@/lib/portal-action-state";
import { safePortalActionError } from "@/lib/portal-action-error";

export async function createLearnerAction(
  _previous: PortalActionState,
  formData: FormData,
): Promise<PortalActionState> {
  const displayLabel = formData.get("displayLabel");
  if (typeof displayLabel !== "string") {
    return { status: "error", message: "Enter a clinic-approved display label." };
  }
  let learnerId: string;
  try {
    const actor = await requireActorContext();
    const learner = await getPlatformDataService().createLearner(
      actor,
      displayLabel,
    );
    learnerId = learner.id;
  } catch (error) {
    return safePortalActionError(error);
  }
  revalidatePath("/learners");
  redirect(`/learners/${learnerId}`);
}
