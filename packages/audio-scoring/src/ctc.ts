import type {
  AudioScoringPolicy,
  CalibrationArtifact,
  ClinicalLexiconEntry,
  ConstrainedAudioScore,
  FramePosterior,
  HypothesisScore,
  PronunciationHypothesis,
} from "./types.ts";
import type { VerifiedEvaluationManifest } from "./evaluation.ts";

const probabilityTolerance = 1e-4;
const correctHypothesisKinds: ReadonlySet<PronunciationHypothesis["kind"]> =
  new Set(["expected", "acceptable-variant"]);

function logSumExp(values: readonly number[]): number {
  const maximum = Math.max(...values);
  if (maximum === Number.NEGATIVE_INFINITY) return maximum;
  let sum = 0;
  for (const value of values) sum += Math.exp(value - maximum);
  return maximum + Math.log(sum);
}

function probability(frame: FramePosterior, token: string): number {
  const value = frame[token];
  if (value === undefined) {
    throw new TypeError(`The encoder vocabulary does not include ${token}.`);
  }
  return value;
}

function validateFrames(
  frames: readonly FramePosterior[],
  blankToken: string,
  requiredPhones: readonly string[],
): void {
  if (frames.length === 0) throw new TypeError("At least one audio frame is required.");
  const vocabulary = Object.keys(frames[0]!).sort();
  if (!Object.hasOwn(frames[0]!, blankToken)) {
    throw new TypeError("Every audio frame must include the CTC blank token.");
  }
  for (const phone of requiredPhones) {
    if (!Object.hasOwn(frames[0]!, phone)) {
      throw new TypeError(`The encoder vocabulary does not include ${phone}.`);
    }
  }
  for (const frame of frames) {
    const values = Object.values(frame);
    const frameVocabulary = Object.keys(frame).sort();
    if (!Object.hasOwn(frame, blankToken) || values.length === 0) {
      throw new TypeError("Every audio frame must include the CTC blank token.");
    }
    if (
      frameVocabulary.length !== vocabulary.length ||
      frameVocabulary.some((token, index) => token !== vocabulary[index])
    ) {
      throw new TypeError("Every audio frame must use the same encoder vocabulary.");
    }
    if (values.some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
      throw new TypeError("Frame posteriors must be finite probabilities.");
    }
    const total = values.reduce((sum, value) => sum + value, 0);
    if (Math.abs(total - 1) > probabilityTolerance) {
      throw new TypeError("Frame posterior probabilities must sum to one.");
    }
  }
}

export function ctcSequenceLogProbability(
  frames: readonly FramePosterior[],
  phones: readonly string[],
  blankToken: string,
): number {
  validateFrames(frames, blankToken, phones);
  if (phones.length === 0 || phones.some((phone) => phone === blankToken)) {
    throw new TypeError("A hypothesis must contain non-blank phones.");
  }

  return ctcSequenceLogProbabilityValidated(frames, phones, blankToken);
}

function ctcSequenceLogProbabilityValidated(
  frames: readonly FramePosterior[],
  phones: readonly string[],
  blankToken: string,
): number {

  const states: string[] = [blankToken];
  for (const phone of phones) states.push(phone, blankToken);
  let previous = states.map(() => Number.NEGATIVE_INFINITY);
  previous[0] = Math.log(probability(frames[0]!, blankToken));
  if (states.length > 1) {
    previous[1] = Math.log(probability(frames[0]!, states[1]!));
  }

  for (let frameIndex = 1; frameIndex < frames.length; frameIndex += 1) {
    const frame = frames[frameIndex]!;
    const current = states.map(() => Number.NEGATIVE_INFINITY);
    for (let stateIndex = 0; stateIndex < states.length; stateIndex += 1) {
      const state = states[stateIndex]!;
      const predecessors = [previous[stateIndex]!];
      if (stateIndex > 0) predecessors.push(previous[stateIndex - 1]!);
      if (
        stateIndex > 1 &&
        state !== blankToken &&
        state !== states[stateIndex - 2]
      ) {
        predecessors.push(previous[stateIndex - 2]!);
      }
      current[stateIndex] =
        Math.log(probability(frame, state)) + logSumExp(predecessors);
    }
    previous = current;
  }

  return logSumExp(
    states.length === 1
      ? [previous[0]!]
      : [previous[states.length - 1]!, previous[states.length - 2]!],
  );
}

function isCorrectHypothesis(hypothesis: PronunciationHypothesis): boolean {
  return correctHypothesisKinds.has(hypothesis.kind);
}

function validateLexicon(entry: ClinicalLexiconEntry, blankToken: string): void {
  if (!entry.id || !entry.version || !entry.targetPhone || !entry.prompt) {
    throw new TypeError("The clinical lexicon entry is incomplete.");
  }
  if (!entry.hypotheses.some(isCorrectHypothesis)) {
    throw new TypeError("The lexicon must include an expected or acceptable path.");
  }
  if (!entry.hypotheses.some((hypothesis) => !isCorrectHypothesis(hypothesis))) {
    throw new TypeError("The lexicon must include at least one error path.");
  }
  const identifiers = new Set<string>();
  const sequences = new Set<string>();
  for (const hypothesis of entry.hypotheses) {
    if (
      hypothesis.phones.length === 0 ||
      hypothesis.phones.includes(blankToken)
    ) {
      throw new TypeError("A hypothesis must contain non-blank phones.");
    }
    const key = hypothesis.phones.join("\u0000");
    if (
      !hypothesis.id ||
      identifiers.has(hypothesis.id) ||
      sequences.has(key)
    ) {
      throw new TypeError("Hypothesis identifiers and phone paths must be unique.");
    }
    identifiers.add(hypothesis.id);
    sequences.add(key);
  }
}

function validCalibration(
  artifact: CalibrationArtifact,
  manifest: VerifiedEvaluationManifest | undefined,
): boolean {
  return (
    manifest !== undefined &&
    artifact.validated &&
    artifact.version.length > 0 &&
    /^[a-f0-9]{64}$/.test(artifact.datasetManifestHash) &&
    artifact.datasetManifestHash === manifest.sha256 &&
    Number.isFinite(artifact.temperature) &&
    artifact.temperature > 0 &&
    Number.isFinite(artifact.bias) &&
    artifact.fitSplit === "calibration" &&
    artifact.speakerIndependent &&
    artifact.householdIndependent
  );
}

function sigmoid(value: number): number {
  if (value >= 0) return 1 / (1 + Math.exp(-value));
  const exponential = Math.exp(value);
  return exponential / (1 + exponential);
}

function clampProbability(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function scoreConstrainedPronunciation(
  frames: readonly FramePosterior[],
  lexicon: ClinicalLexiconEntry,
  calibration: CalibrationArtifact,
  manifest: VerifiedEvaluationManifest | undefined,
  policy: AudioScoringPolicy,
): ConstrainedAudioScore {
  if (
    !policy.version ||
    !policy.blankToken ||
    !Number.isFinite(policy.minimumHypothesisCoverage) ||
    policy.minimumHypothesisCoverage <= 0 ||
    policy.minimumHypothesisCoverage > 1 ||
    !Number.isFinite(policy.ambiguityMargin) ||
    policy.ambiguityMargin <= 0 ||
    policy.ambiguityMargin > 1
  ) {
    throw new TypeError("The audio scoring policy is invalid.");
  }
  validateLexicon(lexicon, policy.blankToken);

  validateFrames(
    frames,
    policy.blankToken,
    lexicon.hypotheses.flatMap((hypothesis) => hypothesis.phones),
  );

  const hypothesisScores: HypothesisScore[] = lexicon.hypotheses.map(
    (hypothesis) => ({
      id: hypothesis.id,
      kind: hypothesis.kind,
      logProbability: ctcSequenceLogProbabilityValidated(
        frames,
        hypothesis.phones,
        policy.blankToken,
      ),
    }),
  );
  const correctScores = hypothesisScores.filter((score) =>
    correctHypothesisKinds.has(score.kind),
  );
  const errorScores = hypothesisScores.filter(
    (score) => !correctHypothesisKinds.has(score.kind),
  );
  const correctLogProbability = logSumExp(
    correctScores.map((score) => score.logProbability),
  );
  const errorLogProbability = logSumExp(
    errorScores.map((score) => score.logProbability),
  );
  const coveredLogProbability = logSumExp([
    correctLogProbability,
    errorLogProbability,
  ]);
  const hypothesisCoverage = clampProbability(Math.exp(coveredLogProbability));
  const rawLogOdds =
    coveredLogProbability === Number.NEGATIVE_INFINITY
      ? 0
      : correctLogProbability - errorLogProbability;
  const calibrationIsValid = validCalibration(calibration, manifest);
  const temperature = calibrationIsValid ? calibration.temperature : 1;
  const bias = calibrationIsValid ? calibration.bias : 0;
  const conditionalCorrectProbability = sigmoid(
    rawLogOdds / temperature + bias,
  );
  const pCorrect = hypothesisCoverage * conditionalCorrectProbability;
  const pError = hypothesisCoverage * (1 - conditionalCorrectProbability);
  const highestError = errorScores.reduce((best, candidate) =>
    candidate.logProbability > best.logProbability ? candidate : best,
  );
  const highestErrorIds = new Set(
    errorScores
      .filter((score) => score.logProbability === highestError.logProbability)
      .map((score) => score.id),
  );
  // A tie can support an error without identifying which error family it is.
  const errorFamilies = new Set(
    lexicon.hypotheses
      .filter((hypothesis) => highestErrorIds.has(hypothesis.id))
      .map((hypothesis) => hypothesis.likelyError),
  );
  const likelyError =
    Number.isFinite(highestError.logProbability) && errorFamilies.size === 1
      ? errorFamilies.values().next().value
      : undefined;
  const ambiguous =
    !calibrationIsValid ||
    hypothesisCoverage < policy.minimumHypothesisCoverage ||
    Math.abs(pCorrect - pError) < policy.ambiguityMargin;

  return {
    evidence: {
      pCorrect,
      pError,
      calibrated: calibrationIsValid,
      ambiguous,
      ...(!ambiguous &&
      calibrationIsValid &&
      pError > pCorrect &&
      likelyError
        ? { likelyError }
        : {}),
    },
    hypothesisCoverage,
    conditionalCorrectProbability,
    lexiconVersion: lexicon.version,
    calibrationVersion: calibration.version,
    scoringPolicyVersion: policy.version,
    hypothesisScores,
  };
}
