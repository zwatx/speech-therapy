import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { runCTC, SESSION_OPTIONS, validatePlan } from "./multiphone_capture_ctc.ts";
import { sha256 } from "./multiphone_ctc_cache.ts";

function wave(): Buffer {
  const b = Buffer.alloc(44+3200);
  b.write("RIFF"); b.writeUInt32LE(b.length-8, 4); b.write("WAVEfmt ", 8);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22);
  b.writeUInt32LE(16000, 24); b.writeUInt32LE(32000, 28);
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write("data", 36);
  b.writeUInt32LE(3200, 40); return b;
}
async function fixture(directory: string) {
  const bindings: Record<string, { path: string; sha256: string }> = {};
  const variants = [];
  for (const condition of ["original", "gain025", "noise20db", "noise10db"]) {
    const audioPath = join(directory, condition+".wav"), bytes = wave();
    await writeFile(audioPath, bytes);
    const audioSha256 = sha256(bytes);
    variants.push({ condition, audioPath, audioSha256, sampleCount: 1600 });
    bindings["derived/000000001/"+condition] = { path: audioPath, sha256: audioSha256 };
  }
  const plan = { complete: true, authorPartition: "train", partition: "innerValidationRows", fold: 0,
    variantCount: 4, selectedSpeakers: 1, availableChildSpeakers: 1, bindings,
    recipe: { ctcSessionOptions: SESSION_OPTIONS },
    clips: [{ id: "000000001", speakerId: "0001", age: 8, sampleCount: 1600, variants }] };
  const path = join(directory, "plan.json"); await writeFile(path, JSON.stringify(plan));
  return { plan, path, sha: sha256(await readFile(path)) };
}

test("scope, unique child speakers, fixed conditions and CPU limits fail closed", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-capture-scope-"));
  try {
    const { plan } = await fixture(directory); validatePlan(plan);
    assert.throws(() => validatePlan({ ...plan, partition: "outerHoldoutRows" }), /scope/);
    const adult = structuredClone(plan); adult.clips[0]!.age = 16;
    assert.throws(() => validatePlan(adult), /child/);
    const wrong = structuredClone(plan); wrong.clips[0]!.variants.reverse();
    assert.throws(() => validatePlan(wrong), /condition/);
    const threads = structuredClone(plan); threads.recipe.ctcSessionOptions.intraOpNumThreads = 8;
    assert.throws(() => validatePlan(threads), /CPU/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("mocked inference publishes all hash-bound 392-token matrices without a model", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-capture-ctc-"));
  try {
    const { path, sha } = await fixture(directory); let calls = 0, disposed = false;
    const result = await runCTC(path, sha, join(directory, "ctc"), async () => ({
      async infer(samples) { calls++; assert.equal(samples.length, 1600); return { data: new Float32Array(4*392), dims: [1, 4, 392] }; },
      async dispose() { disposed = true; }
    })) as { complete: boolean; entries: Record<string, { path: string; sha256: string }> };
    assert.equal(result.complete, true); assert.equal(calls, 4); assert.equal(disposed, true);
    for (const value of Object.values(result.entries)) assert.equal(sha256(await readFile(join(directory, "ctc", value.path))), value.sha256);
    await assert.rejects(runCTC(path, "wrong", join(directory, "wrong")), /digest/);
    await assert.rejects(runCTC(path, sha, join(directory, "ctc")), /EEXIST/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("a source changed during the last forward cannot publish a complete index", async () => {
  const directory = await mkdtemp(join(tmpdir(), "cadence-capture-race-"));
  try {
    const { path, sha, plan } = await fixture(directory); let calls = 0;
    await assert.rejects(runCTC(path, sha, join(directory, "ctc"), async () => ({
      async infer() {
        if (++calls === 4) await writeFile(plan.clips[0]!.variants[0]!.audioPath, "changed");
        return { data: new Float32Array(4*392), dims: [1, 4, 392] };
      }, async dispose() {}
    })), /binding changed/);
    await assert.rejects(readFile(join(directory, "ctc/index.json")), /ENOENT/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});
