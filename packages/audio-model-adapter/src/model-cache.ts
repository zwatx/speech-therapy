import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { chmod, mkdir, mkdtemp, open, rename, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

import { phonemeCtcBaselineManifest, type AcousticCheckpointManifest } from "./manifest.ts";

type CheckpointPin = Pick<AcousticCheckpointManifest,
  "id" | "revision" | "modelFile" | "modelFileBytes" | "modelFileSha256"
  | "vocabularyFileBytes" | "vocabularyFileSha256" | "configFileBytes" | "configFileSha256"
  | "preprocessorFileBytes" | "preprocessorFileSha256"
>;

interface FilePin {
  readonly path: string;
  readonly bytes: number;
  readonly sha256: string;
}

function checkpointFiles(pin: CheckpointPin): readonly FilePin[] {
  return [
    { path: "config.json", bytes: pin.configFileBytes, sha256: pin.configFileSha256 },
    { path: "preprocessor_config.json", bytes: pin.preprocessorFileBytes, sha256: pin.preprocessorFileSha256 },
    { path: "vocab.json", bytes: pin.vocabularyFileBytes, sha256: pin.vocabularyFileSha256 },
    { path: pin.modelFile, bytes: pin.modelFileBytes, sha256: pin.modelFileSha256 },
  ];
}

async function writeVerifiedFile(
  chunks: AsyncIterable<Uint8Array>,
  destination: string,
  pin: FilePin,
): Promise<void> {
  const file = await open(destination, "wx", 0o600);
  const hash = createHash("sha256");
  let bytes = 0;
  try {
    for await (const chunk of chunks) {
      bytes += chunk.byteLength;
      if (bytes > pin.bytes) {
        throw new Error(`Checkpoint file ${pin.path} exceeds its pinned byte length.`);
      }
      hash.update(chunk);
      await file.writeFile(chunk);
    }
    if (bytes !== pin.bytes || hash.digest("hex") !== pin.sha256) {
      throw new Error(`Checkpoint file ${pin.path} failed its pinned byte-length or SHA-256 integrity check.`);
    }
  } finally {
    await file.close();
  }
  await chmod(destination, 0o400);
}

async function* responseChunks(response: Response): AsyncGenerator<Uint8Array> {
  if (!response.body) throw new Error("The checkpoint file download has no body.");
  const reader = response.body.getReader();
  let complete = false;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) {
        complete = true;
        return;
      }
      yield next.value;
    }
  } finally {
    if (!complete) await reader.cancel();
    reader.releaseLock();
  }
}

async function ensureCachedFile(
  cacheDirectory: string,
  checkpoint: CheckpointPin,
  pin: FilePin,
  fetchFile: typeof fetch,
): Promise<string> {
  // Runtime cache assets are verified downloads, not build-time project dependencies.
  // This matches the revision-scoped FileCache layout in the pinned Transformers runtime.
  const filePath = join(/* turbopackIgnore: true */ cacheDirectory, checkpoint.id, checkpoint.revision, pin.path);
  try {
    const metadata = await stat(/* turbopackIgnore: true */ filePath);
    if (!metadata.isFile() || metadata.size !== pin.bytes) {
      throw new Error(`Cached checkpoint file ${pin.path} failed its pinned byte-length integrity check.`);
    }
    return filePath;
  } catch (error) {
    if (!(error instanceof Error && "code" in error && error.code === "ENOENT")) throw error;
  }

  await mkdir(dirname(filePath), { recursive: true });
  const response = await fetchFile(
    `https://huggingface.co/${checkpoint.id}/resolve/${checkpoint.revision}/${pin.path}`,
    { redirect: "follow" },
  );
  if (!response.ok) {
    await response.body?.cancel();
    throw new Error(`Unable to download pinned checkpoint file ${pin.path} (${response.status}).`);
  }
  const temporaryPath = `${filePath}.download-${randomUUID()}`;
  try {
    await writeVerifiedFile(responseChunks(response), temporaryPath, pin);
    await rename(temporaryPath, filePath);
  } finally {
    await response.body?.cancel().catch(() => undefined);
    await rm(temporaryPath, { force: true });
  }
  return filePath;
}

/** Loads only a verified private copy; an existing corrupt cache fails closed without redownload. */
export async function withVerifiedCheckpoint<T>(
  cacheDirectory: string,
  load: (modelDirectory: string) => Promise<T>,
  pin: CheckpointPin = phonemeCtcBaselineManifest,
  fetchFile: typeof fetch = fetch,
): Promise<T> {
  const directory = await mkdtemp(join(/* turbopackIgnore: true */ tmpdir(), "cadence-verified-model-"));
  try {
    for (const file of checkpointFiles(pin)) {
      const source = await ensureCachedFile(cacheDirectory, pin, file, fetchFile);
      const destination = join(/* turbopackIgnore: true */ directory, file.path);
      await mkdir(dirname(destination), { recursive: true });
      await writeVerifiedFile(createReadStream(/* turbopackIgnore: true */ source), destination, file);
    }
    return await load(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
