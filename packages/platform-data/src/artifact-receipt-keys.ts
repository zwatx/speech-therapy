import { createHash, createPublicKey, randomUUID } from "node:crypto";

import {
  Ed25519ArtifactQuarantineReceiptVerifier,
  type TrustedArtifactReceiptSigningKey,
} from "./artifact-quarantine.ts";
import type { DatabaseClient } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ActorContext,
  ArtifactReceiptSigningKeyRecord,
  ArtifactReceiptSigningKeyRegistration,
  ArtifactReceiptSigningKeyRevocationReason,
} from "./types.ts";

const opaqueIdentifier = /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/;
const signingIdentifier = /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/;

interface SigningKeyRow extends Record<string, unknown> {
  authorized: boolean;
  provider_id: string | null;
  signing_key_id: string | null;
  algorithm: "Ed25519" | null;
  public_key_pem?: string | null;
  public_key_sha256: string | null;
  valid_from: string | Date | null;
  valid_until: string | Date | null;
  registered_at: string | Date | null;
  status: ArtifactReceiptSigningKeyRecord["status"] | null;
  revoked_at: string | Date | null;
  revocation_reason: ArtifactReceiptSigningKeyRecord["revocationReason"] | null;
}

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function validateActor(actor: ActorContext): void {
  if (!opaqueIdentifier.test(actor.actorId) || !opaqueIdentifier.test(actor.tenantId)) {
    throw new PlatformDataError("invalid-identifier", "Actor and tenant identifiers must be opaque tokens.");
  }
}

function parseTimestamp(value: string, label: string): Date {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new PlatformDataError("invalid-artifact", `${label} must be a canonical ISO-8601 timestamp.`);
  }
  return parsed;
}

function keyIdentity(providerId: string, signingKeyId: string): void {
  if (!signingIdentifier.test(providerId) || !signingIdentifier.test(signingKeyId)) {
    throw new PlatformDataError("invalid-identifier", "Provider and signing key identifiers are invalid.");
  }
}

function canonicalPublicKey(publicKeyPem: string): {
  readonly pem: string;
  readonly sha256: string;
} {
  try {
    const key = createPublicKey(publicKeyPem);
    if (key.asymmetricKeyType !== "ed25519") {
      throw new Error("wrong-key-type");
    }
    const der = key.export({ type: "spki", format: "der" });
    return {
      pem: key.export({ type: "spki", format: "pem" }).toString(),
      sha256: createHash("sha256").update(der).digest("hex"),
    };
  } catch {
    throw new PlatformDataError("invalid-artifact", "The receipt signing key must be a valid Ed25519 public key.");
  }
}

function mapKey(row: SigningKeyRow): ArtifactReceiptSigningKeyRecord {
  if (!row.provider_id || !row.signing_key_id || !row.algorithm
    || !row.public_key_sha256 || !row.valid_from || !row.valid_until
    || !row.registered_at || !row.status) {
    throw new PlatformDataError("conflict", "Receipt signing key state is incomplete.");
  }
  return {
    providerId: row.provider_id,
    signingKeyId: row.signing_key_id,
    algorithm: row.algorithm,
    publicKeySha256: row.public_key_sha256,
    validFrom: timestamp(row.valid_from),
    validUntil: timestamp(row.valid_until),
    registeredAt: timestamp(row.registered_at),
    status: row.status,
    ...(row.revoked_at ? { revokedAt: timestamp(row.revoked_at) } : {}),
    ...(row.revocation_reason ? { revocationReason: row.revocation_reason } : {}),
  };
}

export class ArtifactReceiptSigningKeyService {
  readonly #database: DatabaseClient;

  constructor(database: DatabaseClient) {
    this.#database = database;
  }

  async register(
    actor: ActorContext,
    input: ArtifactReceiptSigningKeyRegistration,
  ): Promise<ArtifactReceiptSigningKeyRecord> {
    validateActor(actor);
    keyIdentity(input.providerId, input.signingKeyId);
    const validFrom = parseTimestamp(input.validFrom, "Key activation");
    const validUntil = parseTimestamp(input.validUntil, "Key expiry");
    if (validUntil <= validFrom) {
      throw new PlatformDataError("invalid-artifact", "Receipt signing key expiry must follow activation.");
    }
    const publicKey = canonicalPublicKey(input.publicKeyPem);
    const auditId = randomUUID();
    const result = await this.#database.query<SigningKeyRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role = 'owner'
      ), inserted AS (
        INSERT INTO artifact_receipt_signing_keys (
          tenant_id, provider_id, signing_key_id, algorithm,
          public_key_pem, public_key_sha256, valid_from, valid_until,
          registered_by_actor_id
        )
        SELECT $1, $3, $4, 'Ed25519', $5, $6, $7, $8, $2
        WHERE EXISTS (SELECT 1 FROM authorized)
        ON CONFLICT DO NOTHING
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $9, $1, $2, 'artifact.receipt-signing-key.registered',
          'artifact_receipt_signing_key', $4,
          jsonb_build_object(
            'provider_id', $3::TEXT,
            'public_key_sha256', $6::TEXT,
            'valid_from', $7::TIMESTAMPTZ,
            'valid_until', $8::TIMESTAMPTZ
          )
        FROM inserted RETURNING id
      )
      SELECT EXISTS (SELECT 1 FROM authorized) AS authorized,
        inserted.provider_id, inserted.signing_key_id, inserted.algorithm,
        inserted.public_key_sha256, inserted.valid_from, inserted.valid_until,
        inserted.registered_at,
        CASE
          WHEN inserted.valid_from > CURRENT_TIMESTAMP THEN 'scheduled'
          WHEN inserted.valid_until <= CURRENT_TIMESTAMP THEN 'expired'
          ELSE 'active'
        END AS status,
        NULL::TIMESTAMPTZ AS revoked_at, NULL::TEXT AS revocation_reason,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM (SELECT 1) AS singleton
      LEFT JOIN inserted ON TRUE
      `,
      [actor.tenantId, actor.actorId, input.providerId, input.signingKeyId,
        publicKey.pem, publicKey.sha256, input.validFrom, input.validUntil, auditId],
    );
    const row = result.rows[0];
    if (!row?.authorized) {
      throw new PlatformDataError("access-denied", "Only an active tenant owner can register receipt signing keys.");
    }
    if (!row.signing_key_id) {
      throw new PlatformDataError("conflict", "The receipt signing key identity or public key is already registered.");
    }
    return mapKey(row);
  }

  async revoke(
    actor: ActorContext,
    providerId: string,
    signingKeyId: string,
    reason: ArtifactReceiptSigningKeyRevocationReason,
  ): Promise<ArtifactReceiptSigningKeyRecord> {
    validateActor(actor);
    keyIdentity(providerId, signingKeyId);
    if (!(["rotated", "compromised", "provider-disabled"] as const).includes(reason)) {
      throw new PlatformDataError("invalid-artifact", "The signing key revocation reason is unsupported.");
    }
    const auditId = randomUUID();
    const result = await this.#database.query<SigningKeyRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role = 'owner'
      ), revoked AS (
        INSERT INTO artifact_receipt_signing_key_revocations (
          tenant_id, provider_id, signing_key_id, reason, revoked_by_actor_id
        )
        SELECT key.tenant_id, key.provider_id, key.signing_key_id, $5, $2
        FROM artifact_receipt_signing_keys AS key
        WHERE key.tenant_id = $1 AND key.provider_id = $3
          AND key.signing_key_id = $4
          AND EXISTS (SELECT 1 FROM authorized)
        ON CONFLICT DO NOTHING
        RETURNING *
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $6, $1, $2, 'artifact.receipt-signing-key.revoked',
          'artifact_receipt_signing_key', $4,
          jsonb_build_object('provider_id', $3::TEXT, 'reason', $5::TEXT)
        FROM revoked RETURNING id
      )
      SELECT EXISTS (SELECT 1 FROM authorized) AS authorized,
        key.provider_id, key.signing_key_id, key.algorithm,
        key.public_key_sha256, key.valid_from, key.valid_until,
        key.registered_at, 'revoked' AS status,
        revoked.revoked_at, revoked.reason AS revocation_reason,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM (SELECT 1) AS singleton
      LEFT JOIN revoked ON TRUE
      LEFT JOIN artifact_receipt_signing_keys AS key
        ON key.tenant_id = revoked.tenant_id
       AND key.provider_id = revoked.provider_id
       AND key.signing_key_id = revoked.signing_key_id
      `,
      [actor.tenantId, actor.actorId, providerId, signingKeyId, reason, auditId],
    );
    const row = result.rows[0];
    if (!row?.authorized) {
      throw new PlatformDataError("access-denied", "Only an active tenant owner can revoke receipt signing keys.");
    }
    if (!row.signing_key_id) {
      throw new PlatformDataError("conflict", "The receipt signing key is unavailable or already revoked.");
    }
    return mapKey(row);
  }

  async list(actor: ActorContext): Promise<readonly ArtifactReceiptSigningKeyRecord[]> {
    const rows = await this.#read(actor, false, "artifact.receipt-signing-keys.listed");
    return rows.filter((row) => row.signing_key_id !== null).map(mapKey);
  }

  async createVerifier(
    actor: ActorContext,
    options: ConstructorParameters<typeof Ed25519ArtifactQuarantineReceiptVerifier>[1] = {},
  ): Promise<Ed25519ArtifactQuarantineReceiptVerifier> {
    const rows = await this.#read(actor, true, "artifact.receipt-signing-keys.loaded");
    const keys: TrustedArtifactReceiptSigningKey[] = rows.flatMap((row) =>
      row.status === "active" && row.provider_id && row.signing_key_id && row.public_key_pem
        ? [{
            providerId: row.provider_id,
            signingKeyId: row.signing_key_id,
            publicKeyPem: row.public_key_pem,
          }]
        : []
    );
    return new Ed25519ArtifactQuarantineReceiptVerifier(keys, options);
  }

  async #read(
    actor: ActorContext,
    includePem: boolean,
    auditAction: string,
  ): Promise<readonly SigningKeyRow[]> {
    validateActor(actor);
    const auditId = randomUUID();
    const result = await this.#database.query<SigningKeyRow>(
      `
      WITH authorized AS (
        SELECT 1 FROM tenant_memberships
        WHERE tenant_id = $1 AND actor_id = $2 AND status = 'active'
          AND role IN ('owner', 'reviewer')
      ), audit AS (
        INSERT INTO audit_events (
          id, tenant_id, actor_id, action, resource_type, resource_id, metadata
        )
        SELECT $4, $1, $2, $3, 'artifact_receipt_signing_key', $1,
          jsonb_build_object('includes_public_key', $5::BOOLEAN)
        FROM authorized RETURNING id
      ), visible AS (
        SELECT key.*,
          CASE
            WHEN revocation.signing_key_id IS NOT NULL THEN 'revoked'
            WHEN key.valid_from > CURRENT_TIMESTAMP THEN 'scheduled'
            WHEN key.valid_until <= CURRENT_TIMESTAMP THEN 'expired'
            ELSE 'active'
          END AS lifecycle_status,
          revocation.revoked_at, revocation.reason AS revocation_reason
        FROM artifact_receipt_signing_keys AS key
        LEFT JOIN artifact_receipt_signing_key_revocations AS revocation
          ON revocation.tenant_id = key.tenant_id
         AND revocation.provider_id = key.provider_id
         AND revocation.signing_key_id = key.signing_key_id
        WHERE key.tenant_id = $1 AND EXISTS (SELECT 1 FROM authorized)
      )
      SELECT EXISTS (SELECT 1 FROM authorized) AS authorized,
        visible.provider_id, visible.signing_key_id, visible.algorithm,
        CASE WHEN $5::BOOLEAN THEN visible.public_key_pem ELSE NULL END AS public_key_pem,
        visible.public_key_sha256, visible.valid_from, visible.valid_until,
        visible.registered_at, visible.lifecycle_status AS status,
        visible.revoked_at, visible.revocation_reason,
        (SELECT id FROM audit LIMIT 1) AS audit_id
      FROM (SELECT 1) AS singleton
      LEFT JOIN visible ON TRUE
      ORDER BY visible.provider_id, visible.valid_from, visible.signing_key_id
      `,
      [actor.tenantId, actor.actorId, auditAction, auditId, includePem],
    );
    if (!result.rows[0]?.authorized) {
      throw new PlatformDataError("access-denied", "Only an active owner or reviewer can inspect receipt signing keys.");
    }
    return result.rows;
  }
}
