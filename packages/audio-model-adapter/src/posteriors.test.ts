import assert from "node:assert/strict";
import test from "node:test";

import { validateNormalizedAudio } from "./audio.ts";
import { phonemeCtcBaselineManifest } from "./manifest.ts";
import { logitsToFramePosteriors, vocabularyById } from "./posteriors.ts";

test("checkpoint provenance is pinned to immutable revisions and a model hash", () => {
  assert.match(phonemeCtcBaselineManifest.revision, /^[a-f0-9]{40}$/);
  assert.match(phonemeCtcBaselineManifest.upstreamRevision, /^[a-f0-9]{40}$/);
  assert.match(phonemeCtcBaselineManifest.modelFileSha256, /^[a-f0-9]{64}$/);
  assert.equal(phonemeCtcBaselineManifest.releasePosture, "benchmark-only");
});

test("logits become numerically stable frame probabilities", () => {
  const frames = logitsToFramePosteriors(
    { data: [1000, 999, 998, -1000, -999, -998], dims: [1, 2, 3] },
    ["<pad>", "b", "a"],
  );

  assert.equal(frames.length, 2);
  for (const frame of frames) {
    const total = Object.values(frame).reduce((sum, value) => sum + value, 0);
    assert.ok(Math.abs(total - 1) < 1e-12);
  }
  assert.ok(frames[0]!["<pad>"]! > frames[0]!.b!);
  assert.ok(frames[1]!.a! > frames[1]!.b!);
});

test("vocabulary IDs are validated and ordered", () => {
  assert.deepEqual(vocabularyById({ b: 2, "<pad>": 0, a: 1 }), [
    "<pad>",
    "a",
    "b",
  ]);
  assert.throws(() => vocabularyById({ a: 0, b: 2 }), /contiguous/);
});

test("audio validation enforces normalized short 16 kHz captures", () => {
  assert.doesNotThrow(() =>
    validateNormalizedAudio({
      samples: new Float32Array(16_000),
      sampleRateHertz: 16_000,
    }),
  );
  assert.throws(
    () =>
      validateNormalizedAudio({
        samples: new Float32Array(100),
        sampleRateHertz: 16_000,
      }),
    /duration/,
  );
});
