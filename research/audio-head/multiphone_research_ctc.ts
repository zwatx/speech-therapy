/** Single explicit WAV, pinned q8 checkpoint, local CPU2, no dataset discovery. */
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { withVerifiedCheckpoint } from "../../packages/audio-model-adapter/src/model-cache.ts";
import { phonemeCtcBaselineManifest as checkpoint } from "../../packages/audio-model-adapter/src/manifest.ts";
import { convolutionFrames, logProbabilityBytes, readPcm16, sha256 } from "./multiphone_ctc_cache.ts";

export const OPTIONS = { intraOpNumThreads: 2, interOpNumThreads: 1, executionMode: "sequential" as const };
export interface Pin { path: string; sha256: string; }
export interface Runtime { infer(x: Float32Array): Promise<{ data: ArrayLike<number>; dims: number[] }>; dispose(): Promise<unknown>; }
interface Job {
  schemaVersion: number; researchOnly: boolean; audioPath: string; audioSha256: string;
  sampleCount: number; expectedFrames: number; bindings: Record<string, Pin>;
  ctcCheckpoint: Record<string, unknown>; sessionOptions: typeof OPTIONS;
}
function requireCondition(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}
async function digest(path: string): Promise<string> {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}
export async function guard(bindings: Record<string, Pin>): Promise<void> {
  const checked = new Map<string, string>();
  for (const pin of Object.values(bindings)) {
    if (!checked.has(pin.path)) checked.set(pin.path, await digest(pin.path));
    requireCondition(checked.get(pin.path) === pin.sha256, "Source or input changed during CTC inference");
  }
}
export function validateJob(job: Job): void {
  requireCondition(job.schemaVersion === 1 && job.researchOnly === true &&
    Number.isInteger(job.sampleCount) && job.sampleCount >= 1600 && job.sampleCount <= 480000 &&
    job.expectedFrames === convolutionFrames(job.sampleCount) &&
    job.bindings.audio?.path === job.audioPath && job.bindings.audio?.sha256 === job.audioSha256 &&
    Object.keys(job.ctcCheckpoint).length === Object.keys(checkpoint).length &&
    Object.entries(checkpoint).every(([key, value]) => JSON.stringify(job.ctcCheckpoint[key]) === JSON.stringify(value)) &&
    Object.keys(job.sessionOptions).length === Object.keys(OPTIONS).length &&
    Object.entries(OPTIONS).every(([key, value]) => job.sessionOptions[key as keyof typeof OPTIONS] === value),
    "Unsupported WAV, checkpoint or CPU2 CTC contract");
}

/** Caller must install its network-denial guard before loading, as runOne does. */
export async function loadRuntime(): Promise<Runtime> {
  const { AutoConfig, AutoModelForCTC, AutoProcessor, env } = await import(
    "../../packages/audio-model-adapter/node_modules/@huggingface/transformers/dist/transformers.node.mjs");
  requireCondition(env.useFS && env.allowLocalModels && !env.useCustomCache && !env.useBrowserCache &&
    typeof env.cacheDir === "string", "Expected pinned local filesystem runtime");
  return withVerifiedCheckpoint(env.cacheDir, async modelDirectory => {
    const options = { revision: checkpoint.revision, dtype: "q8" as const, device: "cpu" as const,
      local_files_only: true, cache_dir: join(modelDirectory, "loader-cache") };
    const processor = await AutoProcessor.from_pretrained(modelDirectory, options);
    const config = await AutoConfig.from_pretrained(modelDirectory, options);
    const model = await AutoModelForCTC.from_pretrained(modelDirectory, {
      ...options, config, use_external_data_format: false, session_options: OPTIONS });
    return { async infer(x) { return (await model(await processor(x))).logits as { data: ArrayLike<number>; dims: number[] }; },
      async dispose() { return model.dispose(); } };
  });
}

export async function runOne(jobPath: string, expectedSha: string,
                              loader: () => Promise<Runtime> = loadRuntime): Promise<unknown> {
  const bytes = await readFile(jobPath);
  requireCondition(sha256(bytes) === expectedSha, "Caller-pinned CTC job differs");
  const job: Job = JSON.parse(bytes.toString("utf8")); validateJob(job);
  const bindings = { ...job.bindings, job: { path: jobPath, sha256: expectedSha } };
  await guard(bindings);
  const samples = readPcm16(await readFile(job.audioPath), job.audioSha256);
  requireCondition(samples.length === job.sampleCount, "WAV sample count differs");
  const originalFetch = globalThis.fetch;
  let fetchAttempts = 0, runtime: Runtime | undefined;
  globalThis.fetch = async () => { fetchAttempts++; throw new Error("Network forbidden for local research audio"); };
  const start = performance.now();
  try {
    runtime = await loader();
    const loaded = performance.now();
    const logits = await runtime.infer(samples);
    const inferred = performance.now();
    requireCondition(logits.dims[1] === job.expectedFrames, "CTC frame geometry differs");
    const output = logProbabilityBytes(logits.data, logits.dims);
    const path = join(dirname(jobPath), "ctc.f32");
    await writeFile(path, output, { mode: 0o600, flag: "wx" });
    bindings.posteriors = { path, sha256: sha256(output) };
    await guard(bindings);
    requireCondition(fetchAttempts === 0, "Network access attempted");
    const result = { complete: true, jobSha256: expectedSha, audioSha256: job.audioSha256,
      sampleCount: job.sampleCount, frames: job.expectedFrames, checkpoint, sessionOptions: OPTIONS,
      posteriorsPath: "ctc.f32", posteriorsSha256: sha256(output), fetchAttempts, node: process.version,
      modelLoadSeconds: (loaded-start)/1000, forwardSeconds: (inferred-loaded)/1000 };
    await writeFile(join(dirname(jobPath), "ctc.json"), JSON.stringify(result, null, 2)+"\n", { mode: 0o600, flag: "wx" });
    return result;
  } finally {
    try { await runtime?.dispose(); }
    finally { globalThis.fetch = originalFetch; }
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [job, sha] = process.argv.slice(2);
  requireCondition(job && sha, "Usage: node multiphone_research_ctc.ts JOB SHA256");
  runOne(resolve(job), sha).then(() => console.log("Completed local q8 research forward"))
    .catch(error => { console.error(error); process.exitCode = 1; });
}
