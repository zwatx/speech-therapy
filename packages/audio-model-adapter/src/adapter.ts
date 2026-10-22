import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { FramePosterior } from "@speech-therapy/audio-scoring";

import { validateNormalizedAudio, type NormalizedAudio } from "./audio.ts";
import { phonemeCtcBaselineManifest } from "./manifest.ts";
import { withVerifiedCheckpoint } from "./model-cache.ts";
import {
  logitsToFramePosteriors,
  vocabularyById,
  type LogitTensor,
} from "./posteriors.ts";

interface AcousticRuntime {
  infer(samples: Float32Array): Promise<LogitTensor>;
}

export interface PhonemeCtcResult {
  readonly frames: readonly FramePosterior[];
  readonly checkpointId: string;
  readonly checkpointRevision: string;
  readonly runtime: string;
}

export type AcousticRuntimeLoader = () => Promise<{
  readonly runtime: AcousticRuntime;
  readonly idToToken: readonly string[];
}>;

export async function loadTransformersRuntime(): Promise<{
  readonly runtime: AcousticRuntime;
  readonly idToToken: readonly string[];
}> {
  const { AutoConfig, AutoModelForCTC, AutoProcessor, env } = await import("@huggingface/transformers");
  // A custom/browser cache could substitute a different file for the verified local snapshot.
  const cacheDirectory = env.cacheDir;
  if (!env.useFS || !env.allowLocalModels || env.useCustomCache || env.useBrowserCache
    || typeof cacheDirectory !== "string") {
    throw new Error("The pinned acoustic runtime requires local filesystem loading without a custom cache.");
  }
  const { processor, model, idToToken } = await withVerifiedCheckpoint(cacheDirectory, async (modelDirectory) => {
    const options = {
      revision: phonemeCtcBaselineManifest.revision,
      dtype: "q8" as const,
      device: "cpu" as const,
      local_files_only: true,
      // Keep every loader's cache search inside the private snapshot.
      cache_dir: join(modelDirectory, "loader-cache"),
    };
    const [processor, config, vocabulary] = await Promise.all([
      AutoProcessor.from_pretrained(modelDirectory, options),
      AutoConfig.from_pretrained(modelDirectory, options),
      readFile(join(modelDirectory, "vocab.json"), "utf8"),
    ]);
    const idToToken = vocabularyById(JSON.parse(vocabulary) as unknown);
    const model = await AutoModelForCTC.from_pretrained(modelDirectory, {
      ...options,
      config,
      use_external_data_format: false,
    });
    return { processor, model, idToToken };
  });
  return {
    idToToken,
    runtime: {
      async infer(samples: Float32Array): Promise<LogitTensor> {
        const inputs = await processor(samples);
        const output = (await model(inputs)) as { logits?: unknown };
        if (
          typeof output.logits !== "object" ||
          output.logits === null ||
          !("data" in output.logits) ||
          !("dims" in output.logits)
        ) {
          throw new Error("The acoustic checkpoint returned malformed logits.");
        }
        return output.logits as LogitTensor;
      },
    },
  };
}

export class PhonemeCtcAdapter {
  readonly #loader: AcousticRuntimeLoader;
  #loaded:
    | Promise<{
        readonly runtime: AcousticRuntime;
        readonly idToToken: readonly string[];
      }>
    | undefined;

  constructor(loader: AcousticRuntimeLoader = loadTransformersRuntime) {
    this.#loader = loader;
  }

  async infer(audio: NormalizedAudio): Promise<PhonemeCtcResult> {
    validateNormalizedAudio(audio);
    this.#loaded ??= this.#loader().catch((error: unknown) => {
      this.#loaded = undefined;
      throw error;
    });
    const { runtime, idToToken } = await this.#loaded;
    const logits = await runtime.infer(audio.samples);
    return {
      frames: logitsToFramePosteriors(logits, idToToken),
      checkpointId: phonemeCtcBaselineManifest.id,
      checkpointRevision: phonemeCtcBaselineManifest.revision,
      runtime: phonemeCtcBaselineManifest.runtime,
    };
  }
}
