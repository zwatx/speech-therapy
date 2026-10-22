/** Offline CPU2 q8 inference for a hash-bound, child inner-validation diagnostic. */
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { withVerifiedCheckpoint } from "../../packages/audio-model-adapter/src/model-cache.ts";
import { phonemeCtcBaselineManifest as checkpoint } from "../../packages/audio-model-adapter/src/manifest.ts";
import { convolutionFrames, logProbabilityBytes, readPcm16, sha256 } from "./multiphone_ctc_cache.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
export const SESSION_OPTIONS = { intraOpNumThreads: 2, interOpNumThreads: 1, executionMode: "sequential" as const };
interface Binding { path: string; sha256: string; }
interface Variant { condition: string; audioPath: string; audioSha256: string; sampleCount: number; }
interface Clip { id: string; age: number; speakerId: string; sampleCount: number; variants: Variant[]; }
interface Plan {
  complete: boolean; authorPartition: string; partition: string; fold: number; variantCount: number;
  selectedSpeakers: number; availableChildSpeakers: number; clips: Clip[]; bindings: Record<string, Binding>;
  recipe: { ctcSessionOptions: typeof SESSION_OPTIONS };
}
interface Runtime { infer(samples: Float32Array): Promise<{ data: ArrayLike<number>; dims: number[] }>; dispose(): Promise<unknown>; }

function requireCondition(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}
async function digest(path: string): Promise<string> {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}
export async function guard(bindings: Record<string, Binding>): Promise<void> {
  const checked = new Map<string, string>();
  for (const binding of Object.values(bindings)) {
    if (!checked.has(binding.path)) checked.set(binding.path, await digest(binding.path));
    requireCondition(checked.get(binding.path) === binding.sha256, "Diagnostic binding changed");
  }
}
export function validatePlan(plan: Plan): void {
  requireCondition(plan.complete === true && plan.authorPartition === "train" && plan.fold === 0 &&
    plan.partition === "innerValidationRows" && plan.selectedSpeakers === Math.min(8, plan.availableChildSpeakers) &&
    plan.clips.length === plan.selectedSpeakers && plan.clips.length > 0 &&
    new Set(plan.clips.map(c => c.speakerId)).size === plan.clips.length &&
    new Set(plan.clips.map(c => c.id)).size === plan.clips.length && plan.variantCount === 4 * plan.clips.length &&
    Object.entries(SESSION_OPTIONS).every(([k, v]) => plan.recipe.ctcSessionOptions[k as keyof typeof SESSION_OPTIONS] === v),
    "Diagnostic scope or CPU session configuration differs");
  for (const clip of plan.clips) {
    requireCondition(clip.age >= 6 && clip.age <= 12 && /^\d{9}$/.test(clip.id) &&
      clip.variants.map(v => v.condition).join(",") === "original,gain025,noise20db,noise10db" &&
      clip.variants.every(v => v.sampleCount === clip.sampleCount &&
        plan.bindings[`derived/${clip.id}/${v.condition}`]?.path === v.audioPath &&
        plan.bindings[`derived/${clip.id}/${v.condition}`]?.sha256 === v.audioSha256),
      "Diagnostic child/condition/audio binding differs");
  }
}

async function loadRuntime(): Promise<Runtime> {
  // Same installed ESM runtime as the frozen adapter; this separate loader adds
  // explicit CPU session thread limits without modifying the application loader.
  const { AutoConfig, AutoModelForCTC, AutoProcessor, env } = await import(
    "../../packages/audio-model-adapter/node_modules/@huggingface/transformers/dist/transformers.node.mjs");
  requireCondition(env.useFS && env.allowLocalModels && !env.useCustomCache && !env.useBrowserCache &&
    typeof env.cacheDir === "string", "Expected pinned local filesystem runtime");
  return withVerifiedCheckpoint(env.cacheDir, async modelDirectory => {
    const options = { revision: checkpoint.revision, dtype: "q8" as const, device: "cpu" as const,
      local_files_only: true, cache_dir: join(modelDirectory, "loader-cache") };
    const processor = await AutoProcessor.from_pretrained(modelDirectory, options);
    const config = await AutoConfig.from_pretrained(modelDirectory, options);
    const model = await AutoModelForCTC.from_pretrained(modelDirectory, { ...options, config,
      use_external_data_format: false, session_options: SESSION_OPTIONS });
    return { async infer(samples) {
      const output = await model(await processor(samples));
      return output.logits as { data: ArrayLike<number>; dims: number[] };
    }, async dispose() { return model.dispose(); } };
  });
}

export async function runCTC(planPath: string, expectedSha: string, output: string,
                             loader: () => Promise<Runtime> = loadRuntime): Promise<unknown> {
  requireCondition(await digest(planPath) === expectedSha, "Caller plan digest differs");
  const plan: Plan = JSON.parse(await readFile(planPath, "utf8"));
  validatePlan(plan);
  requireCondition(resolve(output).startsWith(resolve(dirname(planPath)) + "/") &&
    resolve(output) !== resolve(dirname(planPath)), "CTC output must be inside its prepared diagnostic");
  const bindings = { ...plan.bindings, plan: { path: planPath, sha256: expectedSha } };
  await guard(bindings);
  await mkdir(output, { mode: 0o700 }); // Fresh only; never reuse partial diagnostics.
  let fetchAttempts = 0;
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => { fetchAttempts++; throw new Error("Network forbidden for capture diagnostic"); };
  const entries: Record<string, unknown> = {};
  let runtime: Runtime | undefined;
  const started = performance.now();
  try {
    runtime = await loader();
    for (const clip of plan.clips) for (const variant of clip.variants) {
      const samples = readPcm16(await readFile(variant.audioPath), variant.audioSha256);
      requireCondition(samples.length === clip.sampleCount, "Derived waveform sample count changed");
      const before = performance.now();
      const logits = await runtime.infer(samples);
      requireCondition(logits.dims[1] === convolutionFrames(samples.length), "Derived CTC geometry differs");
      const bytes = logProbabilityBytes(logits.data, logits.dims);
      const path = `${clip.id}-${variant.condition}.f32`;
      await writeFile(join(output, path), bytes, { flag: "wx", mode: 0o600 });
      entries[clip.id + "/" + variant.condition] = { clipId: clip.id, condition: variant.condition,
        audioSha256: variant.audioSha256, sampleCount: samples.length, frames: logits.dims[1],
        path, sha256: sha256(bytes), inferenceMilliseconds: performance.now() - before };
      bindings["posterior/" + path] = { path: join(output, path), sha256: sha256(bytes) };
    }
    await guard(bindings);
    requireCondition(fetchAttempts === 0 && Object.keys(entries).length === plan.variantCount, "Network attempt or coverage differs");
    const report = { complete: true, planSha256: expectedSha, checkpoint, sessionOptions: SESSION_OPTIONS,
      entries, fetchAttempts, node: process.version, elapsedMilliseconds: performance.now() - started };
    await writeFile(join(output, "index.json"), JSON.stringify(report, null, 2) + "\n", { flag: "wx", mode: 0o600 });
    return report;
  } finally {
    await runtime?.dispose();
    globalThis.fetch = previousFetch;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [plan, sha, output] = process.argv.slice(2);
  requireCondition(plan && sha && output, "Usage: node multiphone_capture_ctc.ts PLAN SHA OUTPUT");
  runCTC(resolve(plan), sha, resolve(output)).then(() => console.log("Completed pinned q8 recording diagnostic"))
    .catch(error => { console.error(error); process.exitCode = 1; });
}
