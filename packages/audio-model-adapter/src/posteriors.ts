import type { FramePosterior } from "@speech-therapy/audio-scoring";

export interface LogitTensor {
  readonly data: ArrayLike<number>;
  readonly dims: readonly number[];
}

function validateVocabulary(idToToken: readonly string[], vocabularySize: number): void {
  if (idToToken.length !== vocabularySize || new Set(idToToken).size !== vocabularySize) {
    throw new TypeError("The checkpoint vocabulary does not match its logits.");
  }
  if (idToToken.some((token) => token.length === 0)) {
    throw new TypeError("Checkpoint vocabulary tokens cannot be empty.");
  }
}

export function logitsToFramePosteriors(
  logits: LogitTensor,
  idToToken: readonly string[],
): readonly FramePosterior[] {
  if (
    logits.dims.length !== 3 ||
    logits.dims[0] !== 1 ||
    !Number.isInteger(logits.dims[1]) ||
    !Number.isInteger(logits.dims[2]) ||
    logits.dims[1]! <= 0 ||
    logits.dims[2]! <= 1
  ) {
    throw new TypeError("CTC logits must have shape [1, frames, vocabulary].");
  }
  const frameCount = logits.dims[1]!;
  const vocabularySize = logits.dims[2]!;
  if (logits.data.length !== frameCount * vocabularySize) {
    throw new TypeError("CTC logit data does not match its declared shape.");
  }
  validateVocabulary(idToToken, vocabularySize);

  const frames: FramePosterior[] = [];
  for (let frameIndex = 0; frameIndex < frameCount; frameIndex += 1) {
    const offset = frameIndex * vocabularySize;
    let maximum = Number.NEGATIVE_INFINITY;
    for (let tokenIndex = 0; tokenIndex < vocabularySize; tokenIndex += 1) {
      const value = logits.data[offset + tokenIndex]!;
      if (!Number.isFinite(value)) {
        throw new TypeError("CTC logits must be finite numbers.");
      }
      maximum = Math.max(maximum, value);
    }
    let denominator = 0;
    for (let tokenIndex = 0; tokenIndex < vocabularySize; tokenIndex += 1) {
      denominator += Math.exp(logits.data[offset + tokenIndex]! - maximum);
    }
    const frame: Record<string, number> = {};
    for (let tokenIndex = 0; tokenIndex < vocabularySize; tokenIndex += 1) {
      frame[idToToken[tokenIndex]!] =
        Math.exp(logits.data[offset + tokenIndex]! - maximum) / denominator;
    }
    frames.push(frame);
  }
  return frames;
}

export function vocabularyById(value: unknown): readonly string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new TypeError("Checkpoint vocabulary must be a token-to-ID object.");
  }
  const entries = Object.entries(value);
  if (
    entries.length < 2 ||
    entries.some(
      ([token, id]) =>
        token.length === 0 ||
        typeof id !== "number" ||
        !Number.isInteger(id) ||
        id < 0 ||
        id >= entries.length,
    )
  ) {
    throw new TypeError("Checkpoint vocabulary IDs must be contiguous integers.");
  }
  const result = Array<string>(entries.length);
  for (const [token, id] of entries as [string, number][]) {
    if (result[id] !== undefined) {
      throw new TypeError("Checkpoint vocabulary IDs must be unique.");
    }
    result[id] = token;
  }
  if (result.some((token) => token === undefined)) {
    throw new TypeError("Checkpoint vocabulary IDs must be contiguous integers.");
  }
  return result;
}
