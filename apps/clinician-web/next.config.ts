import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  transpilePackages: [
    "@speech-therapy/audio-model-adapter",
    "@speech-therapy/audio-scoring",
    "@speech-therapy/clinical-domain",
    "@speech-therapy/contracts",
    "@speech-therapy/platform-data",
  ],
  serverExternalPackages: ["@huggingface/transformers", "onnxruntime-node"],
};

export default nextConfig;
