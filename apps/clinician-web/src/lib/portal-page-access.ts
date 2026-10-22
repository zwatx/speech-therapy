import "server-only";

import { redirect } from "next/navigation";

import type { ActorContext } from "@speech-therapy/platform-data";

import {
  PortalAccessError,
  requireActorContext,
} from "./platform-runtime.ts";

export async function requirePortalActor(): Promise<ActorContext> {
  try {
    return await requireActorContext();
  } catch (error) {
    if (!(error instanceof PortalAccessError)) throw error;
    redirect(`/access?reason=${encodeURIComponent(error.code)}`);
  }
}
