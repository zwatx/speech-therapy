import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  captureReasonCodes,
  likelyErrorKinds,
  routingDecisionKinds,
  routingDecisionReasons,
  learnerAttemptStatuses,
  targetProtocolIds,
} from "./index.ts";

const packageRoot = new URL("../", import.meta.url);

async function readJson(path: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(new URL(path, packageRoot), "utf8")) as Record<
    string,
    unknown
  >;
}

test("generated enums match the canonical schema", async () => {
  const schema = await readJson("schema/attempt-evaluation.schema.json");
  const definitions = schema.$defs as Record<
    string,
    { enum?: readonly string[] }
  >;

  assert.deepEqual(targetProtocolIds, definitions.TargetProtocolId?.enum);
  assert.deepEqual(captureReasonCodes, definitions.CaptureReasonCode?.enum);
  assert.deepEqual(likelyErrorKinds, definitions.LikelyError?.enum);
  assert.deepEqual(routingDecisionKinds, definitions.RoutingDecisionKind?.enum);
  assert.deepEqual(
    routingDecisionReasons,
    definitions.RoutingDecisionReason?.enum,
  );
  assert.deepEqual(
    learnerAttemptStatuses,
    definitions.LearnerAttemptStatus?.enum,
  );
});

test("the checked-in request fixture satisfies cross-field invariants", async () => {
  const fixture = await readJson(
    "fixtures/attempt-evaluation-request.valid.json",
  );
  const audio = fixture.audio as { pCorrect: number; pError: number };
  const quality = fixture.quality as {
    videoScore?: number;
    reasonCodes: string[];
  };

  assert.match(String(fixture.attemptId), /^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/);
  assert.ok(targetProtocolIds.includes(fixture.protocolId as never));
  assert.ok(audio.pCorrect + audio.pError <= 1);
  assert.ok(
    !quality.reasonCodes.includes("video-unavailable") ||
      quality.videoScore === undefined,
  );
});

test("the Swift client contains every contract boundary", async () => {
  const swift = await readFile(
    new URL(
      "swift/Sources/CadenceContracts/AttemptEvaluationModels.swift",
      packageRoot,
    ),
    "utf8",
  );

  for (const boundary of [
    "AttemptEvaluationRequest",
    "AttemptEvaluationResponse",
    "RoutingDecision",
    "clinicianReviewPermitted",
    "researchUsePermitted",
    "LearnerAttemptReceipt",
    "mediaRetained",
  ]) {
    assert.match(swift, new RegExp(boundary));
  }
});

test("generated clients contain every schema object field and optional marker", async () => {
  const schema = await readJson("schema/attempt-evaluation.schema.json");
  const definitions = schema.$defs as Record<
    string,
    {
      type?: string;
      properties?: Record<string, unknown>;
      required?: readonly string[];
    }
  >;
  const typescript = await readFile(
    new URL("src/generated/attempt-evaluation.ts", packageRoot),
    "utf8",
  );
  const swift = await readFile(
    new URL(
      "swift/Sources/CadenceContracts/AttemptEvaluationModels.swift",
      packageRoot,
    ),
    "utf8",
  );

  for (const definition of Object.values(definitions)) {
    if (definition.type !== "object" || !definition.properties) continue;
    const required = new Set(definition.required ?? []);
    for (const propertyName of Object.keys(definition.properties)) {
      const optionalMarker = required.has(propertyName) ? "" : "\\?";
      assert.match(
        typescript,
        new RegExp(`readonly ${propertyName}${optionalMarker}:`),
      );
      assert.match(
        swift,
        new RegExp(
          `public let ${propertyName}: [^\\n]+${required.has(propertyName) ? "$" : "\\?$"}`,
          "m",
        ),
      );
    }
  }
});
