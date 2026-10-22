import "server-only";

import { PlatformDataError } from "@speech-therapy/platform-data";

import type { PortalActionState } from "./portal-action-state.ts";
import { PortalAccessError } from "./platform-runtime.ts";

export function safePortalActionError(error: unknown): PortalActionState {
  if (error instanceof PlatformDataError) {
    return {
      status: "error",
      message:
        error.code === "access-denied"
          ? "Your current clinic role does not allow this action."
          : error.message,
    };
  }
  if (error instanceof PortalAccessError) {
    return {
      status: "error",
      message: "Your clinic access changed. Refresh and sign in again.",
    };
  }
  console.error(
    "Portal action failed",
    error instanceof Error ? error.name : "UnknownError",
  );
  return {
    status: "error",
    message: "The clinical workspace could not complete this action safely.",
  };
}
