import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { PhonemeCtcAdapter } from "../src/adapter.ts";
import { phonemeCtcBaselineManifest as pin } from "../src/manifest.ts";
import { withVerifiedCheckpoint } from "../src/model-cache.ts";

// This opt-in check requires an already populated cache and never downloads files.
let fetchAttempts = 0;
globalThis.fetch = async () => {
  fetchAttempts += 1;
  throw new Error("Network fetch is forbidden during the offline smoke check.");
};
const { env } = await import("@huggingface/transformers");
const before = JSON.stringify(env);
const cache = env.cacheDir;
assert.ok(typeof cache === "string");

// Corrupt actual published metadata, without touching the shared model cache.
const metadataFiles = ["config.json", "preprocessor_config.json", "vocab.json"];
const isolatedCache = await mkdtemp(join(tmpdir(), "cadence-offline-corruption-"));
try {
  const metadataDirectory = join(isolatedCache, pin.id, pin.revision);
  await mkdir(metadataDirectory, { recursive: true });
  for (const filename of metadataFiles) {
    const original = await readFile(join(cache, pin.id, pin.revision, filename));
    const corrupted = Buffer.from(original);
    corrupted[0] = (corrupted[0] ?? 0) ^ 1;
    await writeFile(join(metadataDirectory, filename), corrupted);
    await assert.rejects(
      withVerifiedCheckpoint(isolatedCache, async () => assert.fail("Corrupt metadata reached the loader")),
      /SHA-256 integrity check/,
    );
    await writeFile(join(metadataDirectory, filename), original);
  }
} finally {
  await rm(isolatedCache, { recursive: true, force: true });
}

const samples = Float32Array.from({ length: 16_000 }, (_, i) =>
  0.1 * Math.sin(2 * Math.PI * 220 * i / 16_000));
const adapter = new PhonemeCtcAdapter();
const start = performance.now();
const result = await adapter.infer({ samples, sampleRateHertz: 16_000 });
const coldRuntimeMilliseconds = performance.now() - start;
const secondStart = performance.now();
const repeated = await adapter.infer({ samples, sampleRateHertz: 16_000 });
const reusedRuntimeMilliseconds = performance.now() - secondStart;
assert.equal(result.frames.length, 49);
assert.equal(repeated.frames.length, 49);
for (const frame of result.frames) {
  assert.equal(Object.keys(frame).length, 392);
  const values = Object.values(frame);
  assert.ok(values.every((value) => Number.isFinite(value) && value >= 0 && value <= 1));
  assert.ok(Math.abs(values.reduce((sum, value) => sum + value, 0) - 1) < 1e-12);
}
assert.equal(fetchAttempts, 0);
assert.equal(JSON.stringify(env), before, "The adapter must not change global Transformers settings");
console.log(JSON.stringify({
  metadataCorruptionChecks: metadataFiles.length,
  fetchAttempts,
  frames: result.frames.length,
  tokensPerFrame: Object.keys(result.frames[0]!).length,
  coldRuntimeMilliseconds: Math.round(coldRuntimeMilliseconds),
  reusedRuntimeMilliseconds: Math.round(reusedRuntimeMilliseconds),
}));
