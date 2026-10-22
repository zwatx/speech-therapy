import assert from "node:assert/strict";
import test from "node:test";

import { PhonemeCtcAdapter, type AcousticRuntimeLoader } from "./adapter.ts";
import { phonemeCtcBaselineManifest } from "./manifest.ts";

test("the adapter maps trusted runtime logits and records checkpoint provenance", async () => {
  let loads = 0;
  const loader: AcousticRuntimeLoader = async () => {
    loads += 1;
    return {
      idToToken: ["<pad>", "b", "a"],
      runtime: {
        infer: async () => ({
          data: new Float32Array([4, 2, 1, 1, 2, 4]),
          dims: [1, 2, 3],
        }),
      },
    };
  };
  const adapter = new PhonemeCtcAdapter(loader);
  const audio = {
    samples: new Float32Array(16_000),
    sampleRateHertz: 16_000 as const,
  };

  const first = await adapter.infer(audio);
  const second = await adapter.infer(audio);

  assert.equal(loads, 1);
  assert.equal(first.frames.length, 2);
  assert.equal(second.checkpointId, phonemeCtcBaselineManifest.id);
  assert.equal(
    second.checkpointRevision,
    phonemeCtcBaselineManifest.revision,
  );
});

test("a failed lazy load can be retried", async () => {
  let attempts = 0;
  const adapter = new PhonemeCtcAdapter(async () => {
    attempts += 1;
    if (attempts === 1) throw new Error("temporary cache failure");
    return {
      idToToken: ["<pad>", "a"],
      runtime: {
        infer: async () => ({ data: [0, 1], dims: [1, 1, 2] }),
      },
    };
  });
  const audio = {
    samples: new Float32Array(16_000),
    sampleRateHertz: 16_000 as const,
  };

  await assert.rejects(adapter.infer(audio), /temporary cache failure/);
  await assert.doesNotReject(adapter.infer(audio));
  assert.equal(attempts, 2);
});
