import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { runOne, validateJob, OPTIONS } from "./multiphone_research_ctc.ts";
import { sha256 } from "./multiphone_ctc_cache.ts";
import { phonemeCtcBaselineManifest } from "../../packages/audio-model-adapter/src/manifest.ts";

async function fixture(directory: string) {
  const pcm = Buffer.alloc(3244);
  pcm.write("RIFF"); pcm.writeUInt32LE(pcm.length-8, 4); pcm.write("WAVEfmt ", 8);
  pcm.writeUInt32LE(16, 16); pcm.writeUInt16LE(1, 20); pcm.writeUInt16LE(1, 22);
  pcm.writeUInt32LE(16000, 24); pcm.writeUInt32LE(32000, 28); pcm.writeUInt16LE(2, 32);
  pcm.writeUInt16LE(16, 34); pcm.write("data", 36); pcm.writeUInt32LE(3200, 40);
  const audioPath = join(directory, "original.wav"); await writeFile(audioPath, pcm);
  const audioSha256 = sha256(pcm);
  const job = { schemaVersion: 1, researchOnly: true, audioPath, audioSha256, sampleCount: 1600, expectedFrames: 4,
    bindings: { audio: { path: audioPath, sha256: audioSha256 } },
    ctcCheckpoint: { ...phonemeCtcBaselineManifest }, sessionOptions: { ...OPTIONS } };
  const path = join(directory, "job.json"); await writeFile(path, JSON.stringify(job));
  return { job, path, sha: sha256(await readFile(path)), pcm };
}

test("generic WAV request pins the exact checkpoint, frame count and CPU options", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-raw-contract-"));
  try {
    const { job } = await fixture(directory); validateJob(job);
    assert.throws(() => validateJob({ ...job, expectedFrames: 5 }), /contract/);
    assert.throws(() => validateJob({ ...job, sampleCount: 480001 }), /contract/);
    const changed = structuredClone(job); changed.ctcCheckpoint.revision = "another";
    assert.throws(() => validateJob(changed), /checkpoint/);
    const threads = structuredClone(job); threads.sessionOptions.intraOpNumThreads = 8;
    assert.throws(() => validateJob(threads), /CPU2/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("mocked single WAV forward preserves original and emits all392 posterior columns", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-raw-forward-"));
  try {
    const { job, path, sha, pcm } = await fixture(directory); let calls = 0, disposed = false;
    const result = await runOne(path, sha, async () => ({
      async infer(samples) { calls++; assert.equal(samples.length, 1600); return { data: new Float32Array(4*392), dims: [1, 4, 392] }; },
      async dispose() { disposed = true; }
    })) as { complete: boolean; posteriorsSha256: string };
    assert.equal(result.complete, true); assert.equal(calls, 1); assert.equal(disposed, true);
    const bytes = await readFile(join(directory, "ctc.f32")); assert.equal(bytes.length, 4*392*4);
    assert.equal(sha256(bytes), result.posteriorsSha256); assert.deepEqual(await readFile(job.audioPath), pcm);
    await assert.rejects(runOne(path, "wrong"), /job differs/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("source mutation during forward prevents complete publication", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-raw-mutation-"));
  try {
    const { job, path, sha } = await fixture(directory);
    await assert.rejects(runOne(path, sha, async () => ({
      async infer() { await writeFile(job.audioPath, "changed"); return { data: new Float32Array(4*392), dims: [1, 4, 392] }; },
      async dispose() {}
    })), /changed/);
    await assert.rejects(readFile(join(directory, "ctc.json")), /ENOENT/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("a swallowed network denial still fails and restores global fetch", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-raw-offline-"));
  const originalFetch = globalThis.fetch;
  try {
    const { path, sha } = await fixture(directory);
    await assert.rejects(runOne(path, sha, async () => {
      await globalThis.fetch("https://invalid.example/").catch(() => undefined);
      return { async infer() { return { data: new Float32Array(4*392), dims: [1, 4, 392] }; }, async dispose() {} };
    }), /Network access attempted/);
    assert.equal(globalThis.fetch, originalFetch);
    await assert.rejects(readFile(join(directory, "ctc.json")), /ENOENT/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});
