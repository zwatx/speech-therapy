import { timingSafeEqual } from "node:crypto";

import {
  AttemptValidationError,
  parseAttemptEvaluationRequest,
  routeAttempt,
} from "@speech-therapy/clinical-domain";
import type { AttemptEvaluationResponse } from "@speech-therapy/contracts";

import { apiErrorResponse, jsonNoStore, readJsonObject } from "./api-response.ts";

function configuredToken(value: string | undefined): Buffer | undefined {
  if (!value || Buffer.byteLength(value, "utf8") < 32) return undefined;
  return Buffer.from(value, "utf8");
}

function bearerToken(request: Request): Buffer | undefined {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) return undefined;
  const value = authorization.slice("Bearer ".length);
  return value ? Buffer.from(value, "utf8") : undefined;
}

function authorized(request: Request, expected: Buffer): boolean {
  const supplied = bearerToken(request);
  return (
    supplied !== undefined &&
    supplied.length === expected.length &&
    timingSafeEqual(supplied, expected)
  );
}

export async function handleTrustedEvaluation(
  request: Request,
  expectedToken: string | undefined,
): Promise<Response> {
  const expected = configuredToken(expectedToken);
  if (!expected) {
    return jsonNoStore(
      {
        error: "service-unavailable",
        message: "The trusted scoring boundary is not configured.",
      },
      { status: 503 },
    );
  }
  if (!authorized(request, expected)) {
    return jsonNoStore(
      {
        error: "authentication-required",
        message: "A trusted scoring service credential is required.",
      },
      { status: 401 },
    );
  }

  try {
    const attempt = parseAttemptEvaluationRequest(
      await readJsonObject(request, 16_384),
    );
    const response: AttemptEvaluationResponse = {
      attemptId: attempt.attemptId,
      decision: routeAttempt(attempt),
    };
    return jsonNoStore(response);
  } catch (error) {
    if (error instanceof AttemptValidationError) {
      return jsonNoStore(
        { error: "invalid-attempt", message: error.message },
        { status: 422 },
      );
    }
    return apiErrorResponse(error);
  }
}
