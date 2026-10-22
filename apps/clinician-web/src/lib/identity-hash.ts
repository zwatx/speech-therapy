import { createHmac } from "node:crypto";

export type IdentityHashPurpose = "clerk-organization" | "clerk-user";

export function hashExternalIdentity(
  value: string,
  purpose: IdentityHashPurpose,
  secret: string,
): string {
  if (Buffer.byteLength(secret, "utf8") < 32) {
    throw new TypeError("The identity hash secret must be at least 32 bytes.");
  }
  if (value.length < 4 || value.length > 256) {
    throw new TypeError("The external identity is outside the supported range.");
  }
  return createHmac("sha256", secret)
    .update(`cadence:${purpose}:v1\0${value}`, "utf8")
    .digest("hex");
}
