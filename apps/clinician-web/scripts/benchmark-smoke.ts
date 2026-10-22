import { BenchmarkAttemptScorer } from "../src/lib/benchmark-attempt-scorer.ts";

const sampleRateHertz = 16_000 as const;
const samples = Float32Array.from(
  { length: sampleRateHertz },
  (_, index) => 0.15 * Math.sin((2 * Math.PI * 220 * index) / sampleRateHertz),
);
const result = await new BenchmarkAttemptScorer().score(
  { samples, sampleRateHertz },
  "foundation-ball-initial-b-v1",
);
if (
  result.status !== "scored-ambiguous" ||
  result.calibrated ||
  !result.ambiguous ||
  result.learnerFeedbackEligible
) {
  throw new Error("The benchmark smoke run crossed the release boundary.");
}
console.log(
  JSON.stringify(
    {
      status: result.status,
      checkpointId: result.checkpointId,
      checkpointRevision: result.checkpointRevision,
      lexiconVersion: result.lexiconVersion,
      calibrationVersion: result.calibrationVersion,
      pCorrect: result.pCorrect,
      pError: result.pError,
      hypothesisCoverage: result.hypothesisCoverage,
      inferenceMilliseconds: result.inferenceMilliseconds,
    },
    null,
    2,
  ),
);
