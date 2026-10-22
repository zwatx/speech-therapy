import { likelyErrorKinds, targetProtocolIds } from "./types.ts";
import type {
  AttemptEvaluationRequest,
  CaptureReasonCode,
  LikelyError,
  TargetProtocolId,
} from "./types.ts";

export class AttemptValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AttemptValidationError";
  }
}

const captureReasonCodes = new Set<CaptureReasonCode>([
  "audio-clipping",
  "background-noise",
  "multiple-speakers",
  "face-out-of-frame",
  "mouth-occluded",
  "video-unavailable",
]);

function isCaptureReasonCodeArray(
  value: unknown,
): value is CaptureReasonCode[] {
  return (
    Array.isArray(value) &&
    value.every(
      (reason) =>
        typeof reason === "string" &&
        captureReasonCodes.has(reason as CaptureReasonCode),
    )
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isProbability(value: unknown): value is number {
  return typeof value === "number" && value >= 0 && value <= 1;
}

function isProtocolId(value: unknown): value is TargetProtocolId {
  return (
    typeof value === "string" &&
    targetProtocolIds.includes(value as TargetProtocolId)
  );
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function hasOnlyKeys(
  value: Record<string, unknown>,
  allowedKeys: readonly string[],
): boolean {
  const allowed = new Set(allowedKeys);
  return Object.keys(value).every((key) => allowed.has(key));
}

function isLikelyError(value: unknown): value is LikelyError {
  return (
    typeof value === "string" &&
    likelyErrorKinds.includes(value as LikelyError)
  );
}

export function parseAttemptEvaluationRequest(
  value: unknown,
): AttemptEvaluationRequest {
  if (!isRecord(value)) {
    throw new AttemptValidationError("Request body must be an object.");
  }
  if (
    !hasOnlyKeys(value, ["attemptId", "protocolId", "quality", "audio", "consent"])
  ) {
    throw new AttemptValidationError("Request body contains unsupported fields.");
  }

  const { attemptId, protocolId, quality, audio, consent } = value;
  if (
    typeof attemptId !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9_-]{3,63}$/.test(attemptId)
  ) {
    throw new AttemptValidationError(
      "attemptId must be a 4-64 character opaque token using letters, numbers, underscores, or hyphens.",
    );
  }
  if (!isProtocolId(protocolId)) {
    throw new AttemptValidationError("protocolId is not supported.");
  }
  if (!isRecord(quality) || !isProbability(quality.audioScore)) {
    throw new AttemptValidationError(
      "quality.audioScore must be between 0 and 1.",
    );
  }
  if (!hasOnlyKeys(quality, ["audioScore", "videoScore", "reasonCodes"])) {
    throw new AttemptValidationError("quality contains unsupported fields.");
  }
  if (
    quality.videoScore !== undefined &&
    !isProbability(quality.videoScore)
  ) {
    throw new AttemptValidationError(
      "quality.videoScore must be between 0 and 1.",
    );
  }
  if (!isCaptureReasonCodeArray(quality.reasonCodes)) {
    throw new AttemptValidationError(
      "quality.reasonCodes contains an unsupported value.",
    );
  }
  if (new Set(quality.reasonCodes).size !== quality.reasonCodes.length) {
    throw new AttemptValidationError("quality.reasonCodes cannot contain duplicates.");
  }
  if (
    quality.videoScore !== undefined &&
    quality.reasonCodes.includes("video-unavailable")
  ) {
    throw new AttemptValidationError(
      "quality.videoScore cannot be provided when video is unavailable.",
    );
  }
  if (
    !isRecord(audio) ||
    !isProbability(audio.pCorrect) ||
    !isProbability(audio.pError) ||
    !isBoolean(audio.calibrated) ||
    !isBoolean(audio.ambiguous)
  ) {
    throw new AttemptValidationError(
      "audio evidence is incomplete or out of range.",
    );
  }
  if (
    !hasOnlyKeys(audio, [
      "pCorrect",
      "pError",
      "calibrated",
      "ambiguous",
      "likelyError",
    ])
  ) {
    throw new AttemptValidationError("audio contains unsupported fields.");
  }
  if (audio.pCorrect + audio.pError > 1 + Number.EPSILON) {
    throw new AttemptValidationError(
      "audio probabilities cannot sum to more than 1.",
    );
  }
  if (
    audio.likelyError !== undefined &&
    !isLikelyError(audio.likelyError)
  ) {
    throw new AttemptValidationError("audio.likelyError is not supported.");
  }
  if (
    !isRecord(consent) ||
    !isBoolean(consent.audioProcessing) ||
    !isBoolean(consent.videoProcessing) ||
    !isBoolean(consent.clinicianReview) ||
    !isBoolean(consent.researchUse)
  ) {
    throw new AttemptValidationError("consent snapshot is incomplete.");
  }
  if (
    !hasOnlyKeys(consent, [
      "audioProcessing",
      "videoProcessing",
      "clinicianReview",
      "researchUse",
    ])
  ) {
    throw new AttemptValidationError("consent contains unsupported fields.");
  }

  return {
    attemptId: attemptId.trim(),
    protocolId,
    quality: {
      audioScore: quality.audioScore,
      ...(quality.videoScore === undefined
        ? {}
        : { videoScore: quality.videoScore }),
      reasonCodes: quality.reasonCodes,
    },
    audio: {
      pCorrect: audio.pCorrect,
      pError: audio.pError,
      calibrated: audio.calibrated,
      ambiguous: audio.ambiguous,
      ...(audio.likelyError === undefined
        ? {}
        : {
            likelyError: audio.likelyError,
          }),
    },
    consent: {
      audioProcessing: consent.audioProcessing,
      videoProcessing: consent.videoProcessing,
      clinicianReview: consent.clinicianReview,
      researchUse: consent.researchUse,
    },
  };
}
