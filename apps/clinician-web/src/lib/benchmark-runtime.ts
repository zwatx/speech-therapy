import "server-only";

import {
  BenchmarkAttemptScorer,
  benchmarkScoringEnabled,
} from "./benchmark-attempt-scorer.ts";

let benchmarkScorer: BenchmarkAttemptScorer | undefined;

export function getEnabledBenchmarkAttemptScorer():
  | BenchmarkAttemptScorer
  | undefined {
  if (!benchmarkScoringEnabled(process.env.CADENCE_BENCHMARK_SCORING_ENABLED)) {
    return undefined;
  }
  benchmarkScorer ??= new BenchmarkAttemptScorer();
  return benchmarkScorer;
}
