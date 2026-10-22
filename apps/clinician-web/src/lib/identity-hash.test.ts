import assert from "node:assert/strict";
import test from "node:test";

import { hashExternalIdentity } from "./identity-hash.ts";

const secret = "test-secret-that-is-at-least-thirty-two-bytes-long";

test("external identities are deterministic and purpose separated", () => {
  const userHash = hashExternalIdentity("user_external_001", "clerk-user", secret);
  const organizationHash = hashExternalIdentity(
    "user_external_001",
    "clerk-organization",
    secret,
  );

  assert.equal(userHash.length, 64);
  assert.equal(
    userHash,
    "478a0c8b2ad282109a644d81c56d370de91a73073a74d3463cd401aea95c2c37",
  );
  assert.notEqual(userHash, organizationHash);
  assert.equal(
    userHash,
    hashExternalIdentity("user_external_001", "clerk-user", secret),
  );
});

test("identity hashing rejects short secrets", () => {
  assert.throws(
    () => hashExternalIdentity("user_external_001", "clerk-user", "short"),
    /at least 32 bytes/,
  );
});
