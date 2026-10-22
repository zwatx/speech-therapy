import {
  PhonemeCtcAdapter,
  phonemeCtcBaselineManifest,
  type PhonemeCtcResult,
} from "@speech-therapy/audio-model-adapter";
import {
  benchmarkScoringProfile,
  scoreConstrainedPronunciation,
} from "@speech-therapy/audio-scoring";
import type { PracticeAttemptAnalysisInput } from "@speech-therapy/platform-data";

type WithoutAttemptId<T> = T extends PracticeAttemptAnalysisInput
  ? Omit<T, "attemptId">
  : never;

export type BenchmarkAttemptAnalysis = WithoutAttemptId<
  PracticeAttemptAnalysisInput
>;

export interface BenchmarkAttemptScoring {
  score(
    audio: { readonly samples: Float32Array; readonly sampleRateHertz: 16_000 },
    exerciseId: string,
  ): Promise<BenchmarkAttemptAnalysis>;
  unavailable(inferenceMilliseconds: number): BenchmarkAttemptAnalysis;
}

export function benchmarkScoringEnabled(value: string | undefined): boolean {
  return value === "1";
}

interface PhonemeInference {
  infer(audio: {
    readonly samples: Float32Array;
    readonly sampleRateHertz: 16_000;
  }): Promise<PhonemeCtcResult>;
}

function benchmarkProvenance(exerciseId: string) {
  const profile = benchmarkScoringProfile(exerciseId);
  if (!profile) {
    throw new TypeError("The exercise has no benchmark scoring profile.");
  }
  return {
    profile,
    persisted: {
      releasePosture: profile.releasePosture,
      learnerFeedbackEligible: false as const,
      checkpointId: phonemeCtcBaselineManifest.id,
      checkpointRevision: phonemeCtcBaselineManifest.revision,
      runtime: phonemeCtcBaselineManifest.runtime,
      modelFileSha256: phonemeCtcBaselineManifest.modelFileSha256,
      vocabularyFileSha256: phonemeCtcBaselineManifest.vocabularyFileSha256,
      lexiconVersion: profile.lexicon.version,
      calibrationVersion: profile.calibration.version,
      scoringPolicyVersion: profile.policy.version,
    },
  };
}

export class BenchmarkAttemptScorer implements BenchmarkAttemptScoring {
  readonly #adapter: PhonemeInference;
  readonly #exerciseId: string;

  constructor(
    adapter: PhonemeInference = new PhonemeCtcAdapter(),
    exerciseId: string = "foundation-ball-initial-b-v1",
  ) {
    this.#adapter = adapter;
    this.#exerciseId = exerciseId;
  }

  async score(
    audio: { readonly samples: Float32Array; readonly sampleRateHertz: 16_000 },
    exerciseId: string,
  ): Promise<BenchmarkAttemptAnalysis> {
    if (exerciseId !== this.#exerciseId) {
      throw new TypeError("The benchmark scorer is not configured for this exercise.");
    }
    const startedAt = performance.now();
    const { profile, persisted: provenance } = benchmarkProvenance(exerciseId);
    const inference = await this.#adapter.infer(audio);
    if (
      inference.checkpointId !== provenance.checkpointId ||
      inference.checkpointRevision !== provenance.checkpointRevision ||
      inference.runtime !== provenance.runtime
    ) {
      throw new TypeError("The acoustic result does not match the pinned checkpoint.");
    }
    const score = scoreConstrainedPronunciation(
      inference.frames,
      profile.lexicon,
      profile.calibration,
      undefined,
      profile.policy,
    );
    if (score.evidence.calibrated || !score.evidence.ambiguous) {
      throw new TypeError("A benchmark-only profile cannot emit released evidence.");
    }
    return {
      status: "scored-ambiguous",
      ...provenance,
      pCorrect: score.evidence.pCorrect,
      pError: score.evidence.pError,
      hypothesisCoverage: score.hypothesisCoverage,
      calibrated: false,
      ambiguous: true,
      inferenceMilliseconds: Math.min(
        300_000,
        Math.max(0, Math.round(performance.now() - startedAt)),
      ),
    };
  }

  unavailable(inferenceMilliseconds: number): BenchmarkAttemptAnalysis {
    const { persisted: provenance } = benchmarkProvenance(this.#exerciseId);
    return {
      status: "unavailable",
      ...provenance,
      failureCode: "benchmark-unavailable",
      inferenceMilliseconds: Math.min(
        300_000,
        Math.max(0, Math.round(inferenceMilliseconds)),
      ),
    };
  }
}
