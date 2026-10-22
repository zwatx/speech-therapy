import { createHash, createPublicKey, randomUUID } from "node:crypto";

import type { DatabaseClient } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ActorContext,
  ResearchWorkloadIdentityRecord,
  ResearchWorkloadRevocationReason,
  ResearchWorkloadSigningKeyRecord,
  ResearchWorkloadSigningKeyRegistration,
} from "./types.ts";

const opaque = /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/;
const signingIdentifier = /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/;

interface IdentityRow extends Record<string, unknown> {
  workload_id: string;
  purpose: ResearchWorkloadIdentityRecord["purpose"];
  registered_at: string | Date;
  status: "active" | "revoked";
  revoked_at: string | Date | null;
  revocation_reason: ResearchWorkloadRevocationReason | null;
}

interface KeyRow extends Record<string, unknown> {
  workload_id: string;
  signing_key_id: string;
  algorithm: "Ed25519";
  public_key_sha256: string;
  valid_from: string | Date;
  valid_until: string | Date;
  registered_at: string | Date;
  status: ResearchWorkloadSigningKeyRecord["status"];
  revoked_at: string | Date | null;
  revocation_reason: ResearchWorkloadRevocationReason | null;
}

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function validateActor(actor: ActorContext): void {
  if (!opaque.test(actor.actorId) || !opaque.test(actor.tenantId)) {
    throw new PlatformDataError("invalid-identifier", "Actor and tenant identifiers must be opaque tokens.");
  }
}

function validateIdentity(workloadId: string, signingKeyId?: string): void {
  if (!signingIdentifier.test(workloadId)
    || (signingKeyId !== undefined && !signingIdentifier.test(signingKeyId))) {
    throw new PlatformDataError("invalid-identifier", "Workload and signing key identifiers are invalid.");
  }
}

function parseTimestamp(value: string, label: string): Date {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new PlatformDataError("invalid-artifact", `${label} must be a canonical ISO-8601 timestamp.`);
  }
  return parsed;
}

function canonicalPublicKey(publicKeyPem: string) {
  try {
    const key = createPublicKey(publicKeyPem);
    if (key.asymmetricKeyType !== "ed25519") throw new Error("wrong-key-type");
    const der = key.export({ type: "spki", format: "der" });
    return {
      pem: key.export({ type: "spki", format: "pem" }).toString(),
      sha256: createHash("sha256").update(der).digest("hex"),
    };
  } catch {
    throw new PlatformDataError("invalid-artifact", "Research workload keys must be valid Ed25519 public keys.");
  }
}

function mapIdentity(row: IdentityRow): ResearchWorkloadIdentityRecord {
  return {
    workloadId: row.workload_id,
    purpose: row.purpose,
    registeredAt: timestamp(row.registered_at),
    status: row.status,
    ...(row.revoked_at === null ? {} : { revokedAt: timestamp(row.revoked_at) }),
    ...(row.revocation_reason === null ? {} : { revocationReason: row.revocation_reason }),
  };
}

function mapKey(row: KeyRow): ResearchWorkloadSigningKeyRecord {
  return {
    workloadId: row.workload_id,
    signingKeyId: row.signing_key_id,
    algorithm: row.algorithm,
    publicKeySha256: row.public_key_sha256,
    validFrom: timestamp(row.valid_from),
    validUntil: timestamp(row.valid_until),
    registeredAt: timestamp(row.registered_at),
    status: row.status,
    ...(row.revoked_at === null ? {} : { revokedAt: timestamp(row.revoked_at) }),
    ...(row.revocation_reason === null ? {} : { revocationReason: row.revocation_reason }),
  };
}

export class ResearchWorkloadIdentityService {
  readonly #database: DatabaseClient;

  constructor(database: DatabaseClient) {
    this.#database = database;
  }

  async registerIdentity(
    actor: ActorContext,
    workloadId: string,
    purpose: ResearchWorkloadIdentityRecord["purpose"] = "research-job-runner",
  ): Promise<ResearchWorkloadIdentityRecord> {
    validateActor(actor);
    validateIdentity(workloadId);
    if (!(purpose === "research-job-runner"
      || purpose === "research-job-scheduler"
      || purpose === "research-job-provider"
      || purpose === "research-job-alert-delivery")) {
      throw new PlatformDataError("invalid-artifact", "The workload purpose is unsupported.");
    }
    const auditId = randomUUID();
    const result = await this.#database.query<IdentityRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships WHERE tenant_id = $1 AND actor_id = $2
          AND status = 'active' AND role = 'owner'
      ), inserted AS (
        INSERT INTO research_workload_identities (
          tenant_id, workload_id, purpose, registered_by_actor_id
        )
        SELECT $1, $3, $4, $2
        WHERE EXISTS (SELECT 1 FROM authorized)
        ON CONFLICT DO NOTHING RETURNING *
      ), identity_gate AS (
        INSERT INTO research_workload_identity_gates (tenant_id, workload_id)
        SELECT tenant_id, workload_id FROM inserted
        RETURNING tenant_id, workload_id
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        ) SELECT $5, $1, $2, 'research-workload.registered',
          'research_workload', inserted.workload_id,
          jsonb_build_object('purpose', inserted.purpose)
        FROM inserted INNER JOIN identity_gate
          ON identity_gate.tenant_id = inserted.tenant_id
         AND identity_gate.workload_id = inserted.workload_id
        RETURNING id
      )
      SELECT inserted.*, 'active' AS status, NULL::TIMESTAMPTZ AS revoked_at,
        NULL::TEXT AS revocation_reason
      FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
      `,
      [actor.tenantId, actor.actorId, workloadId, purpose, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "Only an active owner can register a unique research workload.");
    }
    return mapIdentity(row);
  }

  async registerSigningKey(
    actor: ActorContext,
    input: ResearchWorkloadSigningKeyRegistration,
  ): Promise<ResearchWorkloadSigningKeyRecord> {
    validateActor(actor);
    validateIdentity(input.workloadId, input.signingKeyId);
    const validFrom = parseTimestamp(input.validFrom, "Key activation");
    const validUntil = parseTimestamp(input.validUntil, "Key expiry");
    if (validUntil <= validFrom) {
      throw new PlatformDataError("invalid-artifact", "Workload key expiry must follow activation.");
    }
    const publicKey = canonicalPublicKey(input.publicKeyPem);
    const auditId = randomUUID();
    const result = await this.#database.query<KeyRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships WHERE tenant_id = $1 AND actor_id = $2
          AND status = 'active' AND role = 'owner'
      ), trusted_identity AS (
        UPDATE research_workload_identity_gates AS gate
        SET updated_at = CURRENT_TIMESTAMP
        WHERE gate.tenant_id = $1 AND gate.workload_id = $3
          AND NOT gate.revoked AND EXISTS (SELECT 1 FROM authorized)
        RETURNING gate.tenant_id, gate.workload_id
      ), identity AS (
        SELECT identity.* FROM research_workload_identities AS identity
        INNER JOIN trusted_identity
          ON trusted_identity.tenant_id = identity.tenant_id
         AND trusted_identity.workload_id = identity.workload_id
        WHERE identity.tenant_id = $1 AND identity.workload_id = $3
      ), inserted AS (
        INSERT INTO research_workload_signing_keys (
          tenant_id, workload_id, signing_key_id, algorithm, public_key_pem,
          public_key_sha256, valid_from, valid_until, registered_by_actor_id
        )
        SELECT $1, workload_id, $4, 'Ed25519', $5, $6, $7, $8, $2
        FROM identity ON CONFLICT DO NOTHING RETURNING *
      ), key_gate AS (
        INSERT INTO research_workload_signing_key_gates (
          tenant_id, workload_id, signing_key_id
        ) SELECT tenant_id, workload_id, signing_key_id FROM inserted
        RETURNING tenant_id, workload_id, signing_key_id
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        ) SELECT $9, $1, $2, 'research-workload.signing-key.registered',
          'research_workload_signing_key', inserted.signing_key_id,
          jsonb_build_object('workload_id', inserted.workload_id,
            'public_key_sha256', inserted.public_key_sha256,
            'valid_from', inserted.valid_from, 'valid_until', inserted.valid_until)
        FROM inserted INNER JOIN key_gate
          ON key_gate.tenant_id = inserted.tenant_id
         AND key_gate.workload_id = inserted.workload_id
         AND key_gate.signing_key_id = inserted.signing_key_id
        RETURNING id
      )
      SELECT inserted.*,
        CASE WHEN valid_from > CURRENT_TIMESTAMP THEN 'scheduled'
          WHEN valid_until <= CURRENT_TIMESTAMP THEN 'expired' ELSE 'active' END AS status,
        NULL::TIMESTAMPTZ AS revoked_at, NULL::TEXT AS revocation_reason
      FROM inserted WHERE EXISTS (SELECT 1 FROM audit)
      `,
      [actor.tenantId, actor.actorId, input.workloadId, input.signingKeyId,
        publicKey.pem, publicKey.sha256, input.validFrom, input.validUntil, auditId],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("access-denied", "The workload key is unauthorized, revoked, or already registered.");
    }
    return mapKey(row);
  }

  async revokeSigningKey(
    actor: ActorContext,
    workloadId: string,
    signingKeyId: string,
    reason: ResearchWorkloadRevocationReason,
  ): Promise<void> {
    await this.#revoke(actor, workloadId, signingKeyId, reason);
  }

  async revokeIdentity(
    actor: ActorContext,
    workloadId: string,
    reason: ResearchWorkloadRevocationReason,
  ): Promise<void> {
    await this.#revoke(actor, workloadId, undefined, reason);
  }

  async #revoke(
    actor: ActorContext,
    workloadId: string,
    signingKeyId: string | undefined,
    reason: ResearchWorkloadRevocationReason,
  ): Promise<void> {
    validateActor(actor);
    validateIdentity(workloadId, signingKeyId);
    if (!(["rotated", "compromised", "disabled"] as const).includes(reason)) {
      throw new PlatformDataError("invalid-artifact", "The workload revocation reason is unsupported.");
    }
    const auditId = randomUUID();
    const keyRevocation = signingKeyId !== undefined;
    const result = await this.#database.query<{ id: string }>(
      keyRevocation ? `
        WITH authorized AS (
          SELECT 1 FROM tenant_memberships WHERE tenant_id = $1 AND actor_id = $2
            AND status = 'active' AND role = 'owner'
        ), gated AS (
          UPDATE research_workload_signing_key_gates AS gate
          SET revoked = TRUE, updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $3
            AND gate.signing_key_id = $4 AND NOT gate.revoked
            AND EXISTS (SELECT 1 FROM authorized)
          RETURNING gate.tenant_id, gate.workload_id, gate.signing_key_id
        ), revoked AS (
          INSERT INTO research_workload_signing_key_revocations (
            tenant_id, workload_id, signing_key_id, reason, revoked_by_actor_id
          ) SELECT key.tenant_id, key.workload_id, key.signing_key_id, $5, $2
          FROM research_workload_signing_keys AS key
          INNER JOIN gated ON gated.tenant_id = key.tenant_id
            AND gated.workload_id = key.workload_id
            AND gated.signing_key_id = key.signing_key_id
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          ) SELECT $6, $1, $2, 'research-workload.signing-key.revoked',
            'research_workload_signing_key', signing_key_id,
            jsonb_build_object('workload_id', workload_id, 'reason', reason)
          FROM revoked RETURNING id
        ) SELECT id FROM audit
      ` : `
        WITH authorized AS (
          SELECT 1 FROM tenant_memberships WHERE tenant_id = $1 AND actor_id = $2
            AND status = 'active' AND role = 'owner'
        ), gated AS (
          UPDATE research_workload_identity_gates AS gate
          SET revoked = TRUE, updated_at = CURRENT_TIMESTAMP
          WHERE gate.tenant_id = $1 AND gate.workload_id = $3
            AND NOT gate.revoked AND EXISTS (SELECT 1 FROM authorized)
          RETURNING gate.tenant_id, gate.workload_id
        ), revoked AS (
          INSERT INTO research_workload_identity_revocations (
            tenant_id, workload_id, reason, revoked_by_actor_id
          ) SELECT identity.tenant_id, identity.workload_id, $4, $2
          FROM research_workload_identities AS identity
          INNER JOIN gated ON gated.tenant_id = identity.tenant_id
            AND gated.workload_id = identity.workload_id
          RETURNING *
        ), audit AS (
          INSERT INTO audit_events (
            id, tenant_id, actor_id, action, resource_type, resource_id, metadata
          ) SELECT $5, $1, $2, 'research-workload.revoked',
            'research_workload', workload_id,
            jsonb_build_object('reason', reason)
          FROM revoked RETURNING id
        ) SELECT id FROM audit
      `,
      keyRevocation
        ? [actor.tenantId, actor.actorId, workloadId, signingKeyId, reason, auditId]
        : [actor.tenantId, actor.actorId, workloadId, reason, auditId],
    );
    if (!result.rows[0]) {
      throw new PlatformDataError("conflict", "The workload or signing key is unavailable or already revoked.");
    }
  }
}
