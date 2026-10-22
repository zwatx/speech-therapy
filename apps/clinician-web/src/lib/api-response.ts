import { PlatformDataError } from "@speech-therapy/platform-data";

export class ApiRequestError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

export async function readJsonObject(
  request: Request,
  maximumBytes: number = 16_384,
): Promise<Record<string, unknown>> {
  if (!request.headers.get("content-type")?.includes("application/json")) {
    throw new ApiRequestError(
      415,
      "unsupported-media-type",
      "Content-Type must be application/json.",
    );
  }
  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maximumBytes) {
    throw new ApiRequestError(413, "payload-too-large", "Request body is too large.");
  }
  const text = await request.text();
  if (Buffer.byteLength(text, "utf8") > maximumBytes) {
    throw new ApiRequestError(413, "payload-too-large", "Request body is too large.");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new ApiRequestError(400, "invalid-json", "Request body must be valid JSON.");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new ApiRequestError(422, "invalid-request", "Request body must be an object.");
  }
  return parsed as Record<string, unknown>;
}

export function jsonNoStore(
  body: unknown,
  init: ResponseInit = {},
): Response {
  const headers = new Headers(init.headers);
  headers.set("cache-control", "private, no-store, max-age=0");
  headers.set("pragma", "no-cache");
  return Response.json(body, { ...init, headers });
}

export function apiErrorResponse(error: unknown): Response {
  if (error instanceof ApiRequestError) {
    return jsonNoStore(
      { error: error.code, message: error.message },
      { status: error.status },
    );
  }
  if (error instanceof PlatformDataError) {
    const status =
      error.code === "access-denied"
        ? 403
        : error.code === "conflict"
          ? 409
          : error.code === "rate-limited"
            ? 429
            : 422;
    const headers = new Headers();
    if (
      error.code === "rate-limited" &&
      error.retryAfterSeconds !== undefined
    ) {
      headers.set("retry-after", String(error.retryAfterSeconds));
    }
    return jsonNoStore(
      { error: error.code, message: error.message },
      { status, headers },
    );
  }

  const accessCode =
    typeof error === "object" && error !== null && "code" in error
      ? error.code
      : undefined;
  if (accessCode === "authentication-required") {
    return jsonNoStore(
      { error: "authentication-required", message: "A clinician session is required." },
      { status: 401 },
    );
  }
  if (
    accessCode === "organization-required" ||
    accessCode === "membership-required"
  ) {
    return jsonNoStore(
      { error: String(accessCode), message: "Active clinic access is required." },
      { status: 403 },
    );
  }
  if (accessCode === "platform-not-configured") {
    return jsonNoStore(
      { error: "service-unavailable", message: "Clinical data services are not configured." },
      { status: 503 },
    );
  }
  return jsonNoStore(
    { error: "internal-error", message: "The request could not be completed safely." },
    { status: 500 },
  );
}
