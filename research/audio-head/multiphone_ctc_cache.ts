/** Offline, author-training-only CTC cache. App capture limits remain unchanged. */
import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir, rename, realpath, stat } from "node:fs/promises";
import { dirname, join, resolve, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadTransformersRuntime } from "../../packages/audio-model-adapter/src/adapter.ts";
import { phonemeCtcBaselineManifest as pin } from "../../packages/audio-model-adapter/src/manifest.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const TRAIN_MAP_SHA = "e83546f91fa7444547b8c690ef004ad514eee1f7066d38ec87f7a6c847c84737";
const SOURCES = ["multiphone_ctc_cache.ts", "../../packages/audio-model-adapter/src/adapter.ts",
  "../../packages/audio-model-adapter/src/model-cache.ts", "../../packages/audio-model-adapter/src/manifest.ts",
  "../../packages/audio-model-adapter/src/posteriors.ts"];

interface Clip {
  id: string; speakerId: string; audioPath: string; audioSha256: string;
  sampleCount: number; canonicalPhones: string[]; mappedTokens: string[]; mappedTokenIds: number[];
}
interface Manifest {
  schemaVersion: number; authorPartition: string; fold: number | null; partition: string;
  cohortPath: string; cohortSha256: string; splitsPath: string; splitsSha256: string;
  trainMapPath: string; trainMapSha256: string; audioRoot: string;
  vocabularyPath: string; vocabularySha256: string; clips: Clip[];
}
interface Entry {
  clipId: string; path: string; sha256: string; frames: number; vocabularySize: number;
  sampleCount: number; audioSha256: string; configSha256: string; inferenceMilliseconds: number;
  maxRssKiB: number;
}

function requireCondition(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}
export function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}
async function digest(path: string): Promise<string> { return sha256(await readFile(path)); }
async function exists(path: string): Promise<boolean> {
  try { await stat(path); return true; }
  catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return false; throw error; }
}
async function atomicJson(path: string, value: unknown): Promise<void> {
  await writeFile(path + ".tmp", JSON.stringify(value, null, 2) + "\n", { mode: 0o600 });
  await rename(path + ".tmp", path);
}
export async function publishCompletedIndex(path: string, report: { configSha256: string; entries: Record<string, unknown>; complete: boolean }): Promise<void> {
  if (await exists(path)) {
    const previous = JSON.parse(await readFile(path, "utf8"));
    if (previous.complete === true) {
      requireCondition(previous.configSha256 === report.configSha256 &&
        JSON.stringify(sortedValue(previous.entries)) === JSON.stringify(sortedValue(report.entries)),
        "Completed cache index content changed");
      return; // Keep every downstream provenance hash stable on a verified resume.
    }
  }
  await atomicJson(path, report);
}
function within(root: string, path: string): boolean {
  const part = relative(resolve(root), resolve(path));
  return part !== ".." && !part.startsWith("../") && !part.startsWith("/");
}
function sortedValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortedValue);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => [key, sortedValue(item)]));
  }
  return value;
}

/** Research reader; distinct from the application's 150 ms–5 s capture validator. */
export function readPcm16(bytes: Buffer, expectedSha: string): Float32Array {
  requireCondition(bytes.length <= 2_000_000 && sha256(bytes) === expectedSha, "WAV source hash/size differs");
  requireCondition(bytes.length >= 44 && bytes.toString("ascii", 0, 4) === "RIFF" &&
    bytes.toString("ascii", 8, 12) === "WAVE" && bytes.readUInt32LE(4) + 8 === bytes.length,
    "Expected an exact RIFF/WAVE container");
  let format: Buffer | undefined;
  let pcm: Buffer | undefined;
  let position = 12;
  while (position + 8 <= bytes.length) {
    const name = bytes.toString("ascii", position, position + 4);
    const length = bytes.readUInt32LE(position + 4);
    const start = position + 8;
    requireCondition(start + length <= bytes.length, "Truncated WAV chunk");
    if (name === "fmt ") { requireCondition(!format, "Duplicate WAV format"); format = bytes.subarray(start, start + length); }
    if (name === "data") { requireCondition(!pcm, "Duplicate WAV data"); pcm = bytes.subarray(start, start + length); }
    position = start + length + (length % 2);
  }
  requireCondition(position === bytes.length && format && pcm && format.length >= 16,
    "Malformed WAV chunk layout");
  requireCondition(format.readUInt16LE(0) === 1 && format.readUInt16LE(2) === 1 &&
    format.readUInt32LE(4) === 16000 && format.readUInt32LE(8) === 32000 &&
    format.readUInt16LE(12) === 2 && format.readUInt16LE(14) === 16 && pcm.length % 2 === 0,
    "Expected mono PCM16 16 kHz WAV");
  const count = pcm.length / 2;
  requireCondition(count >= 1600 && count <= 480000, "Research audio must be 0.1–30 seconds without truncation");
  return Float32Array.from({ length: count }, (_, i) => pcm!.readInt16LE(2 * i) / 32768);
}

export function convolutionFrames(samples: number): number {
  let result = samples;
  const kernels = [10, 3, 3, 3, 3, 2, 2];
  const strides = [5, 2, 2, 2, 2, 2, 2];
  for (let i = 0; i < kernels.length; i++) result = Math.floor((result - kernels[i]!) / strides[i]!) + 1;
  return result;
}

/** Preserve all logits and compute log-softmax before float32 serialization. */
export function logProbabilityBytes(data: ArrayLike<number>, dims: readonly number[]): Buffer {
  requireCondition(dims.length === 3 && dims[0] === 1 && Number.isInteger(dims[1]) && dims[1]! > 0 &&
    dims[2] === 392 && data.length === dims[1]! * 392, "Expected [1, frames, 392] logits");
  const output = Buffer.alloc(data.length * 4);
  for (let frame = 0; frame < dims[1]!; frame++) {
    let maximum = -Infinity;
    for (let token = 0; token < 392; token++) {
      const value = data[frame * 392 + token]!;
      requireCondition(Number.isFinite(value), "Nonfinite CTC logit");
      maximum = Math.max(maximum, value);
    }
    let total = 0;
    for (let token = 0; token < 392; token++) total += Math.exp(data[frame * 392 + token]! - maximum);
    const normalizer = maximum + Math.log(total);
    for (let token = 0; token < 392; token++) output.writeFloatLE(data[frame * 392 + token]! - normalizer, (frame * 392 + token) * 4);
  }
  validateLogProbabilityBytes(output, dims[1]!);
  return output;
}

export function validateLogProbabilityBytes(bytes: Buffer, frames: number): void {
  requireCondition(Number.isInteger(frames) && frames > 0 && frames <= 1500 && bytes.length === frames * 392 * 4,
    "Invalid posterior matrix length");
  for (let frame = 0; frame < frames; frame++) {
    let total = 0;
    for (let token = 0; token < 392; token++) {
      const value = bytes.readFloatLE((frame * 392 + token) * 4);
      requireCondition(Number.isFinite(value) && value <= 1e-6, "Invalid log posterior");
      total += Math.exp(value);
    }
    requireCondition(Math.abs(total - 1) <= 3e-5, "Full-vocabulary probabilities do not sum to one");
  }
}

export async function verifyEntry(output: string, entry: Entry, clip: Clip, configSha: string): Promise<void> {
  const path = resolve(output, entry.path);
  requireCondition(within(output, path) && entry.clipId === clip.id && entry.audioSha256 === clip.audioSha256 &&
    entry.sampleCount === clip.sampleCount && entry.frames === convolutionFrames(clip.sampleCount) &&
    entry.vocabularySize === 392 && entry.configSha256 === configSha, "Cached entry binding differs");
  const bytes = await readFile(path);
  requireCondition(sha256(bytes) === entry.sha256, "Cached posterior digest differs");
  validateLogProbabilityBytes(bytes, entry.frames);
}

/** Once complete, the index is authoritative even if a redundant sidecar is absent. */
export async function completedEntries(output: string, clips: Clip[], configSha: string): Promise<Record<string, Entry> | undefined> {
  const path = join(output, "index.json");
  if (!(await exists(path))) return undefined;
  const index = JSON.parse(await readFile(path, "utf8"));
  if (index.complete !== true) return undefined;
  requireCondition(index.configSha256 === configSha &&
    JSON.stringify(Object.keys(index.entries).sort()) === JSON.stringify(clips.map(clip => clip.id).sort()),
    "Completed index clip/config set differs");
  for (const clip of clips) {
    const sidecar = join(output, clip.id + ".json");
    if (await exists(sidecar)) {
      requireCondition(JSON.stringify(sortedValue(JSON.parse(await readFile(sidecar, "utf8")))) ===
        JSON.stringify(sortedValue(index.entries[clip.id])), "Completed index and sidecar differ");
    }
  }
  return index.entries;
}

async function verifyManifest(manifest: Manifest): Promise<void> {
  requireCondition(manifest.schemaVersion === 1 && manifest.authorPartition === "train" &&
    ((manifest.partition === "innerFitRows" && manifest.fold === 0) ||
     (manifest.partition === "allEligibleAuthorTrain" && manifest.fold === null)) && manifest.clips.length > 0,
    "Only declared author-training scopes are supported");
  requireCondition(await digest(manifest.cohortPath) === manifest.cohortSha256 &&
    await digest(manifest.splitsPath) === manifest.splitsSha256 && manifest.trainMapSha256 === TRAIN_MAP_SHA &&
    await digest(manifest.trainMapPath) === TRAIN_MAP_SHA && manifest.vocabularySha256 === pin.vocabularyFileSha256 &&
    await digest(manifest.vocabularyPath) === pin.vocabularyFileSha256, "Manifest source pin differs");
  const cohort = JSON.parse(await readFile(manifest.cohortPath, "utf8"));
  const splits = JSON.parse(await readFile(manifest.splitsPath, "utf8"));
  // File digests are authoritative here; Python's canonical JSON hash is verified by the manifest builder.
  requireCondition(cohort.authorPartition === "train" && splits.authorPartition === "train", "Not author training");
  const allowed = new Set<number>(manifest.partition === "innerFitRows" ? splits.folds[0].innerFitClips :
    cohort.rows.filter((row: {trainingEligible: boolean}) => row.trainingEligible)
      .map((row: {clipIndex: number}) => row.clipIndex));
  const train = new Map((await readFile(manifest.trainMapPath, "utf8")).trim().split(/\r?\n/).map(line => {
    const [id, speaker] = line.trim().split(/\s+/); return [id, speaker];
  }));
  const vocabulary = JSON.parse(await readFile(manifest.vocabularyPath, "utf8"));
  const seen = new Set<string>();
  for (const clip of manifest.clips) {
    const index = cohort.clips.findIndex((source: Clip) => source.id === clip.id);
    requireCondition(/^\d{9}$/.test(clip.id) && !seen.has(clip.id) && allowed.has(index) &&
      train.get(clip.id) === clip.speakerId, "Clip outside unique verified inner-fit speakers");
    const source = cohort.clips[index];
    for (const key of ["speakerId", "audioPath", "audioSha256", "sampleCount"] as const) {
      requireCondition(clip[key] === source[key], "Clip differs from bound cohort");
    }
    const canonical = join(manifest.audioRoot, "WAVE", "SPEAKER" + clip.speakerId, clip.id + ".WAV");
    requireCondition(await realpath(clip.audioPath) === await realpath(canonical), "WAV differs from canonical author-train path");
    requireCondition(clip.canonicalPhones.length === clip.mappedTokens.length &&
      clip.mappedTokens.length === clip.mappedTokenIds.length && clip.mappedTokens.length > 0 &&
      clip.mappedTokens.every((token, i) => vocabulary[token] === clip.mappedTokenIds[i] && clip.mappedTokenIds[i]! > 3),
      "Canonical mapping differs from pinned vocabulary");
    seen.add(clip.id);
  }
}

export async function runCache(manifestPath: string, output: string): Promise<unknown> {
  requireCondition(within(join(HERE, "outputs"), output), "Keep research cache in ignored outputs");
  const manifest: Manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  await verifyManifest(manifest);
  // No downloads: missing assets fail through this guard as well as local_files_only.
  let fetchAttempts = 0;
  globalThis.fetch = async () => { fetchAttempts++; throw new Error("Network forbidden for local CTC research"); };
  const sourceSha256 = Object.fromEntries(await Promise.all(SOURCES.map(async name => [name, await digest(join(HERE, name))])));
  const config = { schemaVersion: 1, manifestPath: resolve(manifestPath), manifestSha256: await digest(manifestPath),
    checkpoint: pin, sourceSha256, node: process.version, dtype: "float32-little-endian-log-softmax",
    shape: "frames,392", frameStrideSamples: 320, frameReceptiveFieldSamples: 400,
    authorPartition: "train", frameTimesValidated: false, clinicalUseEligible: false, learnerFeedbackEligible: false };
  await mkdir(output, { recursive: true, mode: 0o700 });
  const configPath = join(output, "config.json");
  if (await exists(configPath)) {
    requireCondition(JSON.stringify(sortedValue(JSON.parse(await readFile(configPath, "utf8")))) ===
      JSON.stringify(sortedValue(config)), "Cache configuration changed; choose a new output");
  } else await atomicJson(configPath, config);
  const configSha = await digest(configPath);
  const authoritativeEntries = await completedEntries(output, manifest.clips, configSha);
  let loaded: Awaited<ReturnType<typeof loadTransformersRuntime>> | undefined;
  let loadMilliseconds = 0;
  let resumed = 0;
  const entries: Record<string, Entry> = {};
  const started = performance.now();
  for (const clip of manifest.clips) {
    const samples = readPcm16(await readFile(clip.audioPath), clip.audioSha256);
    requireCondition(samples.length === clip.sampleCount, "Decoded sample count differs");
    if (authoritativeEntries) {
      const entry = authoritativeEntries[clip.id]!;
      await verifyEntry(output, entry, clip, configSha);
      entries[clip.id] = entry;
      resumed++;
      continue; // A completed cache can never fall back to inference or index replacement.
    }
    const entryPath = join(output, clip.id + ".json");
    if (await exists(entryPath)) {
      const entry: Entry = JSON.parse(await readFile(entryPath, "utf8"));
      await verifyEntry(output, entry, clip, configSha);
      entries[clip.id] = entry;
      resumed++;
      continue;
    }
    if (!loaded) {
      const start = performance.now();
      loaded = await loadTransformersRuntime();
      loadMilliseconds = performance.now() - start;
      requireCondition(loaded.idToToken.length === 392 && loaded.idToToken[0] === "<pad>", "Unexpected full vocabulary");
    }
    const start = performance.now();
    const logits = await loaded.runtime.infer(samples);
    const inferenceMilliseconds = performance.now() - start;
    requireCondition(logits.dims[1] === convolutionFrames(samples.length), "CTC frame grid differs from pinned convolution geometry");
    const bytes = logProbabilityBytes(logits.data, logits.dims);
    const name = clip.id + ".f32";
    await writeFile(join(output, name + ".tmp"), bytes, { mode: 0o600 });
    await rename(join(output, name + ".tmp"), join(output, name));
    const entry: Entry = { clipId: clip.id, path: name, sha256: sha256(bytes), frames: logits.dims[1]!, vocabularySize: 392,
      sampleCount: samples.length, audioSha256: clip.audioSha256, configSha256: configSha,
      inferenceMilliseconds, maxRssKiB: process.resourceUsage().maxRSS };
    await atomicJson(entryPath, entry);
    entries[clip.id] = entry;
    await atomicJson(join(output, "index.json"), { configSha256: configSha, entries, complete: false });
    console.log(JSON.stringify({ clipId: clip.id, seconds: samples.length / 16000, frames: entry.frames,
      inferenceMilliseconds, maxRssKiB: entry.maxRssKiB }));
  }
  requireCondition(await digest(manifestPath) === config.manifestSha256 && fetchAttempts === 0,
    "Input changed or network access attempted during cache generation");
  for (const name of SOURCES) requireCondition(await digest(join(HERE, name)) === sourceSha256[name], "Source changed during extraction");
  const report = { configSha256: configSha, entries, complete: true, resumed, fetchAttempts, loadMilliseconds,
    elapsedMilliseconds: performance.now() - started, maxRssKiB: process.resourceUsage().maxRSS };
  await publishCompletedIndex(join(output, "index.json"), report);
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [manifest, output] = process.argv.slice(2);
  requireCondition(manifest && output, "Usage: node multiphone_ctc_cache.ts MANIFEST OUTPUT");
  runCache(resolve(manifest), resolve(output)).then(result => console.log(JSON.stringify(result)))
    .catch(error => { console.error(error); process.exitCode = 1; });
}
