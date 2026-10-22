export type PlatformDataErrorCode =
  | "access-denied"
  | "conflict"
  | "invalid-consent"
  | "invalid-artifact"
  | "invalid-identifier"
  | "rate-limited";

export class PlatformDataError extends Error {
  readonly code: PlatformDataErrorCode;
  readonly retryAfterSeconds?: number;

  constructor(
    code: PlatformDataErrorCode,
    message: string,
    options: { readonly retryAfterSeconds?: number } = {},
  ) {
    super(message);
    this.name = "PlatformDataError";
    this.code = code;
    if (options.retryAfterSeconds !== undefined) {
      this.retryAfterSeconds = options.retryAfterSeconds;
    }
  }
}
