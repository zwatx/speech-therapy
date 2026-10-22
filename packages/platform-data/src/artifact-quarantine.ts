import {
  createHash,
  createPublicKey,
  randomBytes,
  verify as verifySignature,
} from "node:crypto";

import type { DatabaseClient } from "./database.ts";
import { PlatformDataError } from "./errors.ts";
import type {
  ArtifactQuarantineActionClaim,
  ArtifactQuarantineActionFailureCode,
  ArtifactQuarantineActionReceipt,
  ArtifactQuarantineRunResult,
  SignedArtifactQuarantineActionReceipt,
} from "./types.ts";

const opaqueWorkerId = /^[A-Za-z0-9][A-Za-z0-9_-]{3,79}$/;
const sha256Pattern = /^[a-f0-9]{64}$/;
const receiptReferencePattern = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$/;
const signingIdentifierPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$/;
const ed25519SignaturePattern = /^[A-Za-z0-9_-]{86}$/;
const verifiedSignedReceipts = new WeakSet<object>();

interface ClaimRow extends Record<string, unknown> {
  id: string;
  tenant_id: string;
  artifact_id: string;
  artifact_kind: ArtifactQuarantineActionClaim["artifactKind"];
  artifact_sha256: string;
  source_learner_id: string;
  action_type: ArtifactQuarantineActionClaim["actionType"];
  idempotency_key: string;
  attempt_count: number;
  lease_expires_at: string | Date;
  quarantine_reason: ArtifactQuarantineActionClaim["quarantineReason"];
}

function timestamp(value: string | Date): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

function tokenHash(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

function validateWorker(workerId: string): void {
  if (!opaqueWorkerId.test(workerId)) {
    throw new PlatformDataError("invalid-identifier", "Worker identifiers must be opaque tokens.");
  }
}

export interface ArtifactQuarantineAdapter {
  execute(action: ArtifactQuarantineActionClaim): Promise<ArtifactQuarantineActionReceipt>;
}

export interface SignedArtifactQuarantineAdapter {
  execute(action: ArtifactQuarantineActionClaim): Promise<SignedArtifactQuarantineActionReceipt>;
}

export interface TrustedArtifactReceiptSigningKey {
  readonly providerId: string;
  readonly signingKeyId: string;
  readonly publicKeyPem: string;
}

export function canonicalArtifactQuarantineReceiptPayload(
  receipt: Omit<SignedArtifactQuarantineActionReceipt, "signatureEnvelope">,
  envelope: Omit<SignedArtifactQuarantineActionReceipt["signatureEnvelope"], "signature">,
): string {
  return JSON.stringify({
    schemaVersion: envelope.schemaVersion,
    providerId: envelope.providerId,
    signingKeyId: envelope.signingKeyId,
    algorithm: envelope.algorithm,
    issuedAt: envelope.issuedAt,
    actionId: receipt.actionId,
    idempotencyKey: receipt.idempotencyKey,
    artifactSha256: receipt.artifactSha256,
    actionType: receipt.actionType,
    receiptReference: receipt.receiptReference,
    receiptSha256: receipt.receiptSha256,
    outcome: receipt.outcome,
  });
}

export class Ed25519ArtifactQuarantineReceiptVerifier {
  readonly #keys = new Map<string, {
    readonly publicKey: ReturnType<typeof createPublicKey>;
    readonly publicKeySha256: string;
  }>();
  readonly #maxReceiptAgeMilliseconds: number;
  readonly #futureSkewMilliseconds: number;
  readonly #now: () => Date;

  constructor(
    keys: readonly TrustedArtifactReceiptSigningKey[],
    options: {
      readonly maxReceiptAgeSeconds?: number;
      readonly futureSkewSeconds?: number;
      readonly now?: () => Date;
    } = {},
  ) {
    if (keys.length === 0) {
      throw new PlatformDataError("invalid-artifact", "At least one trusted receipt signing key is required.");
    }
    const maxReceiptAgeSeconds = options.maxReceiptAgeSeconds ?? 900;
    const futureSkewSeconds = options.futureSkewSeconds ?? 60;
    if (!Number.isInteger(maxReceiptAgeSeconds) || maxReceiptAgeSeconds < 1 || maxReceiptAgeSeconds > 86_400
      || !Number.isInteger(futureSkewSeconds) || futureSkewSeconds < 0 || futureSkewSeconds > 300) {
      throw new PlatformDataError("invalid-artifact", "Receipt verification time bounds are invalid.");
    }
    for (const key of keys) {
      if (!signingIdentifierPattern.test(key.providerId) || !signingIdentifierPattern.test(key.signingKeyId)) {
        throw new PlatformDataError("invalid-artifact", "Receipt provider and signing key identifiers are invalid.");
      }
      const identity = `${key.providerId}\u0000${key.signingKeyId}`;
      if (this.#keys.has(identity)) {
        throw new PlatformDataError("invalid-artifact", "Receipt signing key identities must be unique.");
      }
      let publicKey: ReturnType<typeof createPublicKey>;
      try {
        publicKey = createPublicKey(key.publicKeyPem);
      } catch {
        throw new PlatformDataError("invalid-artifact", "A receipt signing public key is malformed.");
      }
      if (publicKey.asymmetricKeyType !== "ed25519") {
        throw new PlatformDataError("invalid-artifact", "Receipt signing keys must use Ed25519.");
      }
      this.#keys.set(identity, {
        publicKey,
        publicKeySha256: createHash("sha256").update(
          publicKey.export({ type: "spki", format: "der" }),
        ).digest("hex"),
      });
    }
    this.#maxReceiptAgeMilliseconds = maxReceiptAgeSeconds * 1000;
    this.#futureSkewMilliseconds = futureSkewSeconds * 1000;
    this.#now = options.now ?? (() => new Date());
  }

  verify(
    claim: ArtifactQuarantineActionClaim,
    signed: SignedArtifactQuarantineActionReceipt,
  ): ArtifactQuarantineActionReceipt {
    if (typeof signed !== "object" || signed === null
      || typeof signed.signatureEnvelope !== "object"
      || signed.signatureEnvelope === null) {
      throw new ArtifactQuarantineAdapterError("verification-failed", false);
    }
    const envelope = signed.signatureEnvelope;
    if (typeof envelope.schemaVersion !== "string"
      || typeof envelope.algorithm !== "string"
      || typeof envelope.providerId !== "string"
      || typeof envelope.signingKeyId !== "string"
      || typeof envelope.issuedAt !== "string"
      || typeof envelope.signature !== "string") {
      throw new ArtifactQuarantineAdapterError("verification-failed", false);
    }
    const issuedAt = new Date(envelope.issuedAt);
    const now = this.#now().getTime();
    if (envelope.schemaVersion !== "artifact-quarantine-receipt-signature-v1"
      || envelope.algorithm !== "Ed25519"
      || signed.actionId !== claim.actionId
      || signed.idempotencyKey !== claim.idempotencyKey
      || signed.artifactSha256 !== claim.artifactSha256
      || signed.actionType !== claim.actionType
      || !signingIdentifierPattern.test(envelope.providerId)
      || !signingIdentifierPattern.test(envelope.signingKeyId)
      || !ed25519SignaturePattern.test(envelope.signature)
      || !Number.isFinite(issuedAt.getTime())
      || issuedAt.toISOString() !== envelope.issuedAt
      || issuedAt.getTime() < now - this.#maxReceiptAgeMilliseconds
      || issuedAt.getTime() > now + this.#futureSkewMilliseconds) {
      throw new ArtifactQuarantineAdapterError("verification-failed", false);
    }
    const trustedKey = this.#keys.get(`${envelope.providerId}\u0000${envelope.signingKeyId}`);
    if (!trustedKey) {
      throw new ArtifactQuarantineAdapterError("verification-failed", false);
    }
    const { signatureEnvelope: _signatureEnvelope, ...receipt } = signed;
    const payload = canonicalArtifactQuarantineReceiptPayload(receipt, {
      schemaVersion: envelope.schemaVersion,
      providerId: envelope.providerId,
      signingKeyId: envelope.signingKeyId,
      algorithm: envelope.algorithm,
      issuedAt: envelope.issuedAt,
    });
    const signature = Buffer.from(envelope.signature, "base64url");
    if (!verifySignature(null, Buffer.from(payload, "utf8"), trustedKey.publicKey, signature)) {
      throw new ArtifactQuarantineAdapterError("verification-failed", false);
    }
    const verification = Object.freeze({
      providerId: envelope.providerId,
      signingKeyId: envelope.signingKeyId,
      algorithm: "Ed25519" as const,
      publicKeySha256: trustedKey.publicKeySha256,
      issuedAt: envelope.issuedAt,
      signatureSha256: createHash("sha256").update(signature).digest("hex"),
    });
    const verified: ArtifactQuarantineActionReceipt = Object.freeze({
      ...receipt,
      verification,
    });
    verifiedSignedReceipts.add(verified);
    return verified;
  }
}

export class VerifyingArtifactQuarantineAdapter implements ArtifactQuarantineAdapter {
  readonly #adapter: SignedArtifactQuarantineAdapter;
  readonly #verifier: Ed25519ArtifactQuarantineReceiptVerifier;

  constructor(
    adapter: SignedArtifactQuarantineAdapter,
    verifier: Ed25519ArtifactQuarantineReceiptVerifier,
  ) {
    this.#adapter = adapter;
    this.#verifier = verifier;
  }

  async execute(action: ArtifactQuarantineActionClaim): Promise<ArtifactQuarantineActionReceipt> {
    return this.#verifier.verify(action, await this.#adapter.execute(action));
  }
}

export class ArtifactQuarantineAdapterError extends Error {
  readonly code: ArtifactQuarantineActionFailureCode;
  readonly retryable: boolean;

  constructor(code: ArtifactQuarantineActionFailureCode, retryable: boolean) {
    super(code);
    this.name = "ArtifactQuarantineAdapterError";
    this.code = code;
    this.retryable = retryable;
  }
}

export class ArtifactQuarantineService {
  readonly #database: DatabaseClient;

  constructor(database: DatabaseClient) {
    this.#database = database;
  }

  async claimNext(workerId: string, leaseSeconds = 60): Promise<ArtifactQuarantineActionClaim | undefined> {
    validateWorker(workerId);
    if (!Number.isInteger(leaseSeconds) || leaseSeconds < 5 || leaseSeconds > 900) {
      throw new PlatformDataError("invalid-artifact", "Quarantine leases must last 5 to 900 seconds.");
    }
    const leaseToken = randomBytes(32).toString("base64url");
    const leaseTokenSha256 = tokenHash(leaseToken);
    const result = await this.#database.query<ClaimRow>(
      `
      WITH expired_terminal AS (
        UPDATE artifact_quarantine_actions
        SET status = 'dead-letter', leased_by = NULL,
            lease_token_sha256 = NULL, lease_expires_at = NULL,
            last_error_code = 'external-unavailable', updated_at = CURRENT_TIMESTAMP
        WHERE status = 'processing' AND attempt_count = 8
          AND lease_expires_at <= CURRENT_TIMESTAMP
        RETURNING id, attempt_count
      ), terminal_event AS (
        INSERT INTO artifact_quarantine_action_events (
          action_id, attempt_number, event_type, worker_id, error_code
        )
        SELECT id, attempt_count, 'dead-lettered', $1, 'external-unavailable'
        FROM expired_terminal
      ), candidate AS (
        SELECT id
        FROM artifact_quarantine_actions
        WHERE attempt_count < 8
          AND (
            (status = 'pending' AND available_at <= CURRENT_TIMESTAMP)
            OR
            (status = 'processing' AND lease_expires_at <= CURRENT_TIMESTAMP)
          )
        ORDER BY available_at, created_at, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
      ), claimed AS (
        UPDATE artifact_quarantine_actions AS action
        SET status = 'processing',
            attempt_count = attempt_count + 1,
            leased_by = $1,
            lease_token_sha256 = $2,
            lease_expires_at = CURRENT_TIMESTAMP + ($3 * INTERVAL '1 second'),
            last_error_code = NULL,
            updated_at = CURRENT_TIMESTAMP
        FROM candidate
        WHERE action.id = candidate.id
        RETURNING action.*
      ), event AS (
        INSERT INTO artifact_quarantine_action_events (
          action_id, attempt_number, event_type, worker_id
        )
        SELECT id, attempt_count, 'claimed', $1 FROM claimed
        RETURNING action_id
      )
      SELECT claimed.id, claimed.tenant_id, claimed.artifact_id,
        artifact.kind AS artifact_kind, artifact.sha256 AS artifact_sha256,
        claimed.source_learner_id, claimed.action_type, claimed.idempotency_key,
        claimed.attempt_count, claimed.lease_expires_at,
        quarantine.reason AS quarantine_reason
      FROM claimed
      INNER JOIN event ON event.action_id = claimed.id
      INNER JOIN ml_artifacts AS artifact
        ON artifact.id = claimed.artifact_id
       AND artifact.tenant_id = claimed.tenant_id
      INNER JOIN artifact_quarantine_events AS quarantine
        ON quarantine.sequence_id = claimed.quarantine_event_sequence_id
      `,
      [workerId, leaseTokenSha256, leaseSeconds],
    );
    const row = result.rows[0];
    if (!row) return undefined;
    return {
      actionId: row.id,
      tenantId: row.tenant_id,
      artifactId: row.artifact_id,
      artifactKind: row.artifact_kind,
      artifactSha256: row.artifact_sha256,
      sourceLearnerId: row.source_learner_id,
      actionType: row.action_type,
      idempotencyKey: row.idempotency_key,
      attemptNumber: Number(row.attempt_count),
      leaseToken,
      leaseExpiresAt: timestamp(row.lease_expires_at),
      quarantineReason: row.quarantine_reason,
    };
  }

  async recordSuccess(
    workerId: string,
    claim: ArtifactQuarantineActionClaim,
    receipt: ArtifactQuarantineActionReceipt,
  ): Promise<void> {
    validateWorker(workerId);
    const verification = receipt.verification;
    if (
      receipt.actionId !== claim.actionId
      || receipt.idempotencyKey !== claim.idempotencyKey
      || receipt.artifactSha256 !== claim.artifactSha256
      || receipt.actionType !== claim.actionType
      || !receiptReferencePattern.test(receipt.receiptReference)
      || !sha256Pattern.test(receipt.receiptSha256)
      || !["performed", "already-satisfied"].includes(receipt.outcome)
      || (verification !== undefined && !verifiedSignedReceipts.has(receipt))
    ) {
      throw new PlatformDataError("invalid-artifact", "The external quarantine receipt failed verification.");
    }
    const result = await this.#database.query<Record<string, unknown> & {
      candidate_id: string;
      id: string | null;
    }>(
      `
      WITH candidate AS (
        SELECT action.id,
          $8::TEXT IS NULL OR EXISTS (
            SELECT 1 FROM artifact_receipt_signing_keys AS signing_key
            LEFT JOIN artifact_receipt_signing_key_revocations AS revocation
              ON revocation.tenant_id = signing_key.tenant_id
             AND revocation.provider_id = signing_key.provider_id
             AND revocation.signing_key_id = signing_key.signing_key_id
            WHERE signing_key.tenant_id = action.tenant_id
              AND signing_key.provider_id = $8
              AND signing_key.signing_key_id = $9
              AND signing_key.algorithm = $10
              AND signing_key.public_key_sha256 = $13
              AND signing_key.valid_from <= $11::TIMESTAMPTZ
              AND signing_key.valid_until > $11::TIMESTAMPTZ
              AND revocation.signing_key_id IS NULL
          ) AS signing_key_trusted
        FROM artifact_quarantine_actions AS action
        WHERE action.id = $2 AND action.status = 'processing'
          AND action.leased_by = $1 AND action.lease_token_sha256 = $3
          AND action.lease_expires_at > CURRENT_TIMESTAMP
          AND action.attempt_count = $4
      ), completed AS (
        UPDATE artifact_quarantine_actions
        SET status = 'succeeded', completed_at = CURRENT_TIMESTAMP,
            receipt_reference = $5, receipt_sha256 = $6,
            receipt_outcome = $7, last_error_code = NULL,
            receipt_provider_id = $8, receipt_signing_key_id = $9,
            receipt_public_key_sha256 = $13,
            receipt_signature_algorithm = $10, receipt_issued_at = $11,
            receipt_signature_sha256 = $12,
            leased_by = NULL, lease_token_sha256 = NULL,
            lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
        FROM candidate
        WHERE artifact_quarantine_actions.id = candidate.id
          AND candidate.signing_key_trusted
        RETURNING artifact_quarantine_actions.id,
          artifact_quarantine_actions.attempt_count
      ), event AS (
        INSERT INTO artifact_quarantine_action_events (
          action_id, attempt_number, event_type, worker_id,
          receipt_reference, receipt_sha256, receipt_outcome,
          receipt_provider_id, receipt_signing_key_id,
          receipt_public_key_sha256,
          receipt_signature_algorithm, receipt_issued_at,
          receipt_signature_sha256
        )
        SELECT id, attempt_count, 'succeeded', $1, $5, $6, $7,
          $8, $9, $13, $10, $11, $12
        FROM completed
        RETURNING action_id
      )
      SELECT candidate.id AS candidate_id,
        (SELECT completed.id FROM completed
         INNER JOIN event ON event.action_id = completed.id) AS id
      FROM candidate
      `,
      [workerId, claim.actionId, tokenHash(claim.leaseToken), claim.attemptNumber,
        receipt.receiptReference, receipt.receiptSha256, receipt.outcome,
        verification?.providerId ?? null, verification?.signingKeyId ?? null,
        verification?.algorithm ?? null, verification?.issuedAt ?? null,
        verification?.signatureSha256 ?? null,
        verification?.publicKeySha256 ?? null],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("conflict", "The quarantine action lease is stale or expired.");
    }
    if (!row.id) {
      throw new PlatformDataError("invalid-artifact", "The receipt signing key is not currently trusted for this tenant.");
    }
  }

  async recordFailure(
    workerId: string,
    claim: ArtifactQuarantineActionClaim,
    code: ArtifactQuarantineActionFailureCode,
    retryable: boolean,
  ): Promise<"retry-scheduled" | "dead-lettered"> {
    validateWorker(workerId);
    if (!["external-unavailable", "verification-failed", "permanent-rejection"].includes(code)) {
      throw new PlatformDataError("invalid-artifact", "The quarantine failure code is unsupported.");
    }
    const result = await this.#database.query<Record<string, unknown> & { event_type: "retry-scheduled" | "dead-lettered" }>(
      `
      WITH failed AS (
        UPDATE artifact_quarantine_actions
        SET status = CASE WHEN $5 AND attempt_count < 8 THEN 'pending' ELSE 'dead-letter' END,
            available_at = CASE WHEN $5 AND attempt_count < 8
              THEN CURRENT_TIMESTAMP
                + (LEAST(3600, (POWER(2, attempt_count - 1) * 30)::INTEGER) * INTERVAL '1 second')
              ELSE available_at END,
            last_error_code = $6,
            leased_by = NULL, lease_token_sha256 = NULL,
            lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2 AND status = 'processing' AND leased_by = $1
          AND lease_token_sha256 = $3
          AND attempt_count = $4
        RETURNING id, attempt_count, status
      ), event AS (
        INSERT INTO artifact_quarantine_action_events (
          action_id, attempt_number, event_type, worker_id, error_code
        )
        SELECT id, attempt_count,
          CASE WHEN status = 'pending' THEN 'retry-scheduled' ELSE 'dead-lettered' END,
          $1, $6
        FROM failed
        RETURNING event_type
      )
      SELECT event_type FROM event
      `,
      [workerId, claim.actionId, tokenHash(claim.leaseToken), claim.attemptNumber, retryable, code],
    );
    const row = result.rows[0];
    if (!row) {
      throw new PlatformDataError("conflict", "The quarantine action lease is stale.");
    }
    return row.event_type;
  }
}

export class ArtifactQuarantineReconciler {
  readonly #service: ArtifactQuarantineService;
  readonly #adapter: ArtifactQuarantineAdapter;

  constructor(service: ArtifactQuarantineService, adapter: ArtifactQuarantineAdapter) {
    this.#service = service;
    this.#adapter = adapter;
  }

  async runOnce(workerId: string): Promise<ArtifactQuarantineRunResult> {
    const action = await this.#service.claimNext(workerId);
    if (!action) return { status: "idle" };
    try {
      const receipt = await this.#adapter.execute(action);
      try {
        await this.#service.recordSuccess(workerId, action, receipt);
      } catch (error) {
        if (error instanceof PlatformDataError && error.code === "invalid-artifact") {
          await this.#service.recordFailure(workerId, action, "verification-failed", false);
          return { status: "dead-lettered", actionId: action.actionId };
        }
        throw error;
      }
      return { status: "succeeded", actionId: action.actionId };
    } catch (error) {
      if (error instanceof PlatformDataError && error.code === "conflict") throw error;
      const adapterError = error instanceof ArtifactQuarantineAdapterError ? error : undefined;
      const disposition = await this.#service.recordFailure(
        workerId,
        action,
        adapterError?.code ?? "external-unavailable",
        adapterError?.retryable ?? true,
      );
      return { status: disposition, actionId: action.actionId };
    }
  }
}
