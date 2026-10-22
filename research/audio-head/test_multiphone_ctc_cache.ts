import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { completedEntries, convolutionFrames, logProbabilityBytes, publishCompletedIndex, readPcm16, sha256,
  validateLogProbabilityBytes, verifyEntry } from "./multiphone_ctc_cache.ts";

function wav(samples: number): Buffer {
  const value = Buffer.alloc(44 + samples * 2);
  value.write("RIFF", 0); value.writeUInt32LE(value.length - 8, 4); value.write("WAVEfmt ", 8);
  value.writeUInt32LE(16, 16); value.writeUInt16LE(1, 20); value.writeUInt16LE(1, 22);
  value.writeUInt32LE(16000, 24); value.writeUInt32LE(32000, 28);
  value.writeUInt16LE(2, 32); value.writeUInt16LE(16, 34); value.write("data", 36);
  value.writeUInt32LE(samples * 2, 40);
  value.writeInt16LE(-32768, 44); value.writeInt16LE(32767, 46);
  return value;
}

test("research reader accepts full 0.1–30 second PCM16 without changing app policy", () => {
  for (const count of [1600, 16000, 480000]) {
    const value = wav(count);
    const samples = readPcm16(value, sha256(value));
    assert.equal(samples.length, count);
    assert.equal(samples[0], -1);
    assert.equal(samples[1], 32767 / 32768);
  }
  for (const count of [1599, 480001]) {
    const value = wav(count);
    assert.throws(() => readPcm16(value, sha256(value)), /0.1–30/);
  }
});

test("WAV byte identity, declared length, format and truncation fail closed", () => {
  const value = wav(1600);
  assert.throws(() => readPcm16(value, "wrong"), /hash/);
  const wrongRate = Buffer.from(value); wrongRate.writeUInt32LE(48000, 24);
  assert.throws(() => readPcm16(wrongRate, sha256(wrongRate)), /PCM16/);
  const truncated = value.subarray(0, -2);
  assert.throws(() => readPcm16(truncated, sha256(truncated)), /RIFF/);
  const odd = Buffer.from(value); odd.writeUInt32LE(3199, 40);
  assert.throws(() => readPcm16(odd, sha256(odd)), /PCM16/);
});

test("stable log-softmax retains all 392 tokens with extreme logits", () => {
  const logits = Float32Array.from({ length: 784 }, (_, i) => i === 1 ? 10000 : -10000 + i % 392);
  const bytes = logProbabilityBytes(logits, [1, 2, 392]);
  assert.equal(bytes.length, 784 * 4);
  validateLogProbabilityBytes(bytes, 2);
  assert.equal(bytes.readFloatLE(4), 0);
  assert.ok(Number.isFinite(bytes.readFloatLE(0)));
  assert.throws(() => logProbabilityBytes([Infinity], [1, 1, 1]), /392/);
  logits[2] = NaN;
  assert.throws(() => logProbabilityBytes(logits, [1, 2, 392]), /Nonfinite/);
});

test("frame geometry uses unpadded convolution rather than duration rounding", () => {
  assert.equal(convolutionFrames(1600), 4);
  assert.equal(convolutionFrames(16000), 49);
  assert.equal(convolutionFrames(480000), 1499);
});

test("resumption verifies posterior hash, source waveform, config and frame grid", async () => {
  const root = await mkdtemp(join(tmpdir(), "cadence-ctc-cache-test-"));
  try {
    const bytes = logProbabilityBytes(new Float32Array(49 * 392), [1, 49, 392]);
    const clip = { id: "clip", speakerId: "speaker", audioPath: "unused", audioSha256: "audio", sampleCount: 16000,
      canonicalPhones: ["B"], mappedTokens: ["b"], mappedTokenIds: [26] };
    const entry = { clipId: "clip", path: "clip.f32", sha256: sha256(bytes), frames: 49, vocabularySize: 392,
      sampleCount: 16000, audioSha256: "audio", configSha256: "config", inferenceMilliseconds: 1, maxRssKiB: 1 };
    await writeFile(join(root, entry.path), bytes);
    await verifyEntry(root, entry, clip, "config");
    await assert.rejects(verifyEntry(root, { ...entry, frames: 50 }, clip, "config"), /binding/);
    await assert.rejects(verifyEntry(root, entry, clip, "changed"), /binding/);
    await assert.rejects(verifyEntry(root, { ...entry, path: "../escape" }, clip, "config"), /binding/);
    const corrupted = await readFile(join(root, entry.path)); corrupted[0] = corrupted[0]! ^ 1;
    await writeFile(join(root, entry.path), corrupted);
    await assert.rejects(verifyEntry(root, entry, clip, "config"), /digest/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("verified resumption keeps the completed index byte-identical", async () => {
  const root = await mkdtemp(join(tmpdir(), "cadence-ctc-index-test-"));
  try {
    const path = join(root, "index.json");
    const report = { configSha256: "config", entries: { clip: { sha256: "data" } }, complete: true, resumed: 0 };
    await publishCompletedIndex(path, report);
    const before = await readFile(path);
    const resumedReport = { ...report, resumed: 1 };
    await publishCompletedIndex(path, resumedReport);
    assert.deepEqual(await readFile(path), before);
    await assert.rejects(publishCompletedIndex(path, { ...report, entries: {} }), /content changed/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("completed index remains authoritative when a redundant per-clip sidecar is missing", async () => {
  const root = await mkdtemp(join(tmpdir(), "cadence-ctc-sidecar-test-"));
  try {
    const bytes = logProbabilityBytes(new Float32Array(49 * 392), [1, 49, 392]);
    const clip = { id: "clip", speakerId: "speaker", audioPath: "unused", audioSha256: "audio", sampleCount: 16000,
      canonicalPhones: ["B"], mappedTokens: ["b"], mappedTokenIds: [26] };
    const entry = { clipId: "clip", path: "clip.f32", sha256: sha256(bytes), frames: 49, vocabularySize: 392,
      sampleCount: 16000, audioSha256: "audio", configSha256: "config", inferenceMilliseconds: 1, maxRssKiB: 1 };
    await writeFile(join(root, "clip.f32"), bytes);
    const index = { configSha256: "config", entries: { clip: entry }, complete: true };
    await publishCompletedIndex(join(root, "index.json"), index);
    const before = await readFile(join(root, "index.json"));
    const authoritative = await completedEntries(root, [clip], "config");
    assert.ok(authoritative);
    await verifyEntry(root, authoritative.clip!, clip, "config");
    assert.deepEqual(await readFile(join(root, "index.json")), before);
    await assert.rejects(completedEntries(root, [], "config"), /clip\/config set/);
    await writeFile(join(root, "clip.json"), JSON.stringify({ ...entry, sha256: "changed" }));
    await assert.rejects(completedEntries(root, [clip], "config"), /sidecar differ/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
