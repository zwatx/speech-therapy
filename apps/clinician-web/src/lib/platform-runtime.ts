import "server-only";

import { auth } from "@clerk/nextjs/server";
import {
  createNeonDatabase,
  PlatformDataService,
  type ActorContext,
} from "@speech-therapy/platform-data";

import { hashExternalIdentity } from "./identity-hash.ts";

export type PortalAccessErrorCode =
  | "authentication-required"
  | "organization-required"
  | "membership-required"
  | "platform-not-configured";

export class PortalAccessError extends Error {
  readonly code: PortalAccessErrorCode;

  constructor(code: PortalAccessErrorCode, message: string) {
    super(message);
    this.name = "PortalAccessError";
    this.code = code;
  }
}

let platformService: PlatformDataService | undefined;

export function getPlatformDataService(): PlatformDataService {
  if (platformService) return platformService;
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    throw new PortalAccessError(
      "platform-not-configured",
      "Persistent storage is not configured.",
    );
  }
  platformService = new PlatformDataService(createNeonDatabase(databaseUrl));
  return platformService;
}

export async function requireActorContext(): Promise<ActorContext> {
  const session = await auth();
  if (!session.isAuthenticated || !session.userId) {
    throw new PortalAccessError(
      "authentication-required",
      "A clinician session is required.",
    );
  }
  if (!session.orgId) {
    throw new PortalAccessError(
      "organization-required",
      "Select an active clinic organization before accessing clinical data.",
    );
  }
  const hashSecret = process.env.CADENCE_IDENTITY_HASH_SECRET;
  if (!hashSecret || Buffer.byteLength(hashSecret, "utf8") < 32) {
    throw new PortalAccessError(
      "platform-not-configured",
      "Identity mapping is not configured.",
    );
  }
  const actor = await getPlatformDataService().resolveActorContext(
    hashExternalIdentity(session.userId, "clerk-user", hashSecret),
    hashExternalIdentity(session.orgId, "clerk-organization", hashSecret),
  );
  if (!actor) {
    throw new PortalAccessError(
      "membership-required",
      "The signed-in identity does not have an active clinic membership.",
    );
  }
  return actor;
}
