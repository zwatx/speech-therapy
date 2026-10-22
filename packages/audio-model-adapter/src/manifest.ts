export interface AcousticCheckpointManifest {
  readonly id: string;
  readonly revision: string;
  readonly upstreamId: string;
  readonly upstreamRevision: string;
  readonly runtime: string;
  readonly modelFile: string;
  readonly modelFileSha256: string;
  readonly modelFileBytes: number;
  readonly vocabularyFileSha256: string;
  readonly vocabularyFileBytes: number;
  readonly configFileSha256: string;
  readonly configFileBytes: number;
  readonly preprocessorFileSha256: string;
  readonly preprocessorFileBytes: number;
  readonly sampleRateHertz: number;
  readonly output: "phoneme-ctc-logits";
  readonly license: string;
  readonly trainingData: readonly string[];
  readonly releasePosture: "benchmark-only";
}

export const phonemeCtcBaselineManifest: AcousticCheckpointManifest = {
  id: "onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX",
  revision: "c69750f5043e5e1f8a71ab95dd3b98338c280c92",
  upstreamId: "facebook/wav2vec2-lv-60-espeak-cv-ft",
  upstreamRevision: "ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4",
  runtime: "@huggingface/transformers@4.2.0",
  modelFile: "onnx/model_quantized.onnx",
  modelFileSha256:
    // Enforced on downloaded and cached model bytes before runtime construction.
    "3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120",
  modelFileBytes: 317_712_852,
  vocabularyFileSha256:
    "d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0",
  vocabularyFileBytes: 4_637,
  configFileSha256:
    "428b7781d080ad9463dca0e17e5066073cb691bfc14a178a85e76ac79c1f4a0f",
  configFileBytes: 2_382,
  preprocessorFileSha256:
    "a2254a5b58f72cd4de3632f8eee64f3f098b7c1402128d2f419e7d00ae13e335",
  preprocessorFileBytes: 212,
  sampleRateHertz: 16_000,
  output: "phoneme-ctc-logits",
  license: "Apache-2.0 checkpoint metadata; legal/data-lineage review pending",
  trainingData: ["Mozilla Common Voice (upstream model card)"],
  releasePosture: "benchmark-only",
};
