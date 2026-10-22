export interface AudioModelCandidate {
  readonly id: string;
  readonly role: "primary-baseline" | "challenger" | "framework" | "reference";
  readonly codeLicense: string;
  readonly productionPosture: "candidate" | "benchmark-only" | "offline-tooling";
  readonly clinicalReason: string;
  readonly requiredReview: string;
}

export const audioModelRegistryVersion = "audio-candidates-2026-07-10";

export const audioModelCandidates: readonly AudioModelCandidate[] = [
  {
    id: "wav2vec2-base-xlsr",
    role: "primary-baseline",
    codeLicense: "MIT; exact checkpoint and training-data lineage still require review",
    productionPosture: "candidate",
    clinicalReason: "Frame-level CTC evidence supports constrained phone-path scoring without a broad word language model.",
    requiredReview: "Benchmark frozen features first, then evaluate partial fine-tuning only on consented child speech.",
  },
  {
    id: "wavlm-base-plus",
    role: "challenger",
    codeLicense: "MIT repository; exact checkpoint and upstream-data terms require review",
    productionPosture: "candidate",
    clinicalReason: "Noise-robust speech representations may improve phone evidence on real mobile captures.",
    requiredReview: "Must beat wav2vec2 on false-pass, calibration, subgroup, latency, and cost gates.",
  },
  {
    id: "nemo-conformer-ctc-compact",
    role: "framework",
    codeLicense: "Apache-2.0 toolkit; checkpoint terms vary",
    productionPosture: "candidate",
    clinicalReason: "Provides a reproducible compact CTC training and export path.",
    requiredReview: "Select one exact checkpoint or owned training recipe and audit every upstream asset.",
  },
  {
    id: "openai-whisper",
    role: "reference",
    codeLicense: "MIT code and released weights",
    productionPosture: "benchmark-only",
    clinicalReason: "Useful robustness and transcript comparator, but its decoder can infer the prompted word despite articulation errors.",
    requiredReview: "Never use decoded word acceptance as pronunciation truth.",
  },
  {
    id: "gopt",
    role: "reference",
    codeLicense: "BSD-3 code; all underlying ASR assets require separate review",
    productionPosture: "benchmark-only",
    clinicalReason: "Relevant pronunciation-scoring research baseline, but its non-native sentence task does not validate pediatric SSD decisions.",
    requiredReview: "Reproduce only as an offline comparator; do not transfer published thresholds.",
  },
  {
    id: "montreal-forced-aligner",
    role: "framework",
    codeLicense: "MIT application; acoustic model and dictionary terms vary",
    productionPosture: "offline-tooling",
    clinicalReason: "Useful for corpus alignment prefill and boundary-quality review.",
    requiredReview: "Keep out of learner runtime and audit every downloaded model and dictionary.",
  },
] as const;
