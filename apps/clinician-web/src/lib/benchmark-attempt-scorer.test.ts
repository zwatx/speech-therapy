import assert from "node:assert/strict";
import test from "node:test";

import { phonemeCtcBaselineManifest } from "@speech-therapy/audio-model-adapter";

import {
  BenchmarkAttemptScorer,
  benchmarkScoringEnabled,
} from "./benchmark-attempt-scorer.ts";

const frames = [
  { "<pad>": 0.05, b: 0.8, "ɔ": 0.05, "ɑ": 0.03, "ɒ": 0.02, l: 0.05 },
  { "<pad>": 0.05, b: 0.02, "ɔ": 0.75, "ɑ": 0.08, "ɒ": 0.05, l: 0.05 },
  { "<pad>": 0.05, b: 0.02, "ɔ": 0.03, "ɑ": 0.03, "ɒ": 0.02, l: 0.85 },
];

function inference(checkpointRevision = phonemeCtcBaselineManifest.revision) {
  return {
    infer: async () => ({
      frames,
      checkpointId: phonemeCtcBaselineManifest.id,
      checkpointRevision,
      runtime: phonemeCtcBaselineManifest.runtime,
    }),
  };
}

test("the server benchmark scorer emits aggregate ambiguous evidence only", async () => {
  const scorer = new BenchmarkAttemptScorer(inference());
  const result = await scorer.score(
    { samples: new Float32Array(16_000), sampleRateHertz: 16_000 },
    "foundation-ball-initial-b-v1",
  );

  assert.ok(result.status === "scored-ambiguous");
  assert.equal(result.releasePosture, "benchmark-only");
  assert.equal(result.learnerFeedbackEligible, false);
  assert.equal(result.calibrated, false);
  assert.equal(result.ambiguous, true);
  assert.equal(result.checkpointRevision, phonemeCtcBaselineManifest.revision);
  assert.ok(result.pCorrect + result.pError <= 1.000001);
  assert.equal("profile" in result, false);
});

test("checkpoint provenance mismatches fail before evidence is stored", async () => {
  const scorer = new BenchmarkAttemptScorer(inference("f".repeat(40)));
  await assert.rejects(
    scorer.score(
      { samples: new Float32Array(16_000), sampleRateHertz: 16_000 },
      "foundation-ball-initial-b-v1",
    ),
    /pinned checkpoint/,
  );
});

test("unavailable evidence carries provenance but no probabilities", () => {
  const result = new BenchmarkAttemptScorer(inference()).unavailable(42);
  assert.equal(result.status, "unavailable");
  assert.equal(result.failureCode, "benchmark-unavailable");
  assert.equal("pCorrect" in result, false);
  assert.equal(result.inferenceMilliseconds, 42);
});

test("benchmark scoring is off unless the server flag is exactly enabled", () => {
  assert.equal(benchmarkScoringEnabled(undefined), false);
  assert.equal(benchmarkScoringEnabled("0"), false);
  assert.equal(benchmarkScoringEnabled("true"), false);
  assert.equal(benchmarkScoringEnabled("1"), true);
});
