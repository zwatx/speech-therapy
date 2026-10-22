import type {
  AudioScoringPolicy,
  CalibrationArtifact,
  ClinicalLexiconEntry,
} from "./types.ts";

export interface BenchmarkScoringProfile {
  readonly exerciseId: string;
  readonly protocolId: string;
  readonly releasePosture: "benchmark-only";
  readonly lexicon: ClinicalLexiconEntry;
  readonly calibration: CalibrationArtifact;
  readonly policy: AudioScoringPolicy;
}

const unvalidatedCalibration: CalibrationArtifact = {
  version: "unvalidated-research-v0",
  datasetManifestHash: "0".repeat(64),
  temperature: 1,
  bias: 0,
  validated: false,
  fitSplit: "calibration",
  speakerIndependent: false,
  householdIndependent: false,
};

const benchmarkPolicy: AudioScoringPolicy = {
  version: "benchmark-policy-v1",
  blankToken: "<pad>",
  minimumHypothesisCoverage: 0.05,
  ambiguityMargin: 0.2,
};

const profiles: Readonly<Record<string, BenchmarkScoringProfile>> = {
  "foundation-ball-initial-b-v1": {
    exerciseId: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    releasePosture: "benchmark-only",
    lexicon: {
      id: "research-ball-initial-b",
      version: "research-ball-initial-b-v1",
      prompt: "ball",
      targetPhone: "b",
      hypotheses: [
        { id: "expected-open-o", kind: "expected", phones: ["b", "ɔ", "l"] },
        {
          id: "expected-back-a",
          kind: "acceptable-variant",
          phones: ["b", "ɑ", "l"],
        },
        {
          id: "expected-rounded-o",
          kind: "acceptable-variant",
          phones: ["b", "ɒ", "l"],
        },
        {
          id: "initial-b-omission-open-o",
          kind: "omission",
          phones: ["ɔ", "l"],
          likelyError: "omission",
        },
        {
          id: "initial-b-omission-back-a",
          kind: "omission",
          phones: ["ɑ", "l"],
          likelyError: "omission",
        },
        {
          id: "initial-b-omission-rounded-o",
          kind: "omission",
          phones: ["ɒ", "l"],
          likelyError: "omission",
        },
      ],
    },
    calibration: unvalidatedCalibration,
    policy: benchmarkPolicy,
  },
};

export function benchmarkScoringProfile(
  exerciseId: string,
): BenchmarkScoringProfile | undefined {
  return profiles[exerciseId];
}
