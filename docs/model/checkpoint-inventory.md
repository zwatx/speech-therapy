# Acoustic checkpoint inventory

Status: reproducible benchmark adapter; not a clinical model release

## Visual landmark feasibility runtime

The native app currently uses the operating-system Apple Vision face-landmark
request under runtime identifier `apple-vision-landmarks-feasibility-v1` for
local capture-quality research only. There is no separately shipped visual
checkpoint, raw landmark persistence, visual upload, or articulation classifier.
The decision and MediaPipe re-evaluation gate are recorded in
[`visual-landmark-runtime.md`](visual-landmark-runtime.md).

## Acoustic benchmark

The first executable baseline is
[`onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX`](https://huggingface.co/onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX),
an Apache-2.0 ONNX conversion of Meta's
[`facebook/wav2vec2-lv-60-espeak-cv-ft`](https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft).
The upstream model card says it consumes 16 kHz audio and emits phonetic labels
after Common Voice fine-tuning. It is a general multilingual phoneme recognizer,
not a child/SSD pronunciation model.

## Pinned executable artifact

- ONNX repository revision:
  `c69750f5043e5e1f8a71ab95dd3b98338c280c92`
- Upstream checkpoint revision:
  `ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4`
- Runtime: `@huggingface/transformers@4.2.0`
- Runtime model: `onnx/model_quantized.onnx`, q8, 317,712,852 bytes
- Model SHA-256:
  `3d1479b5c70836645a4310902479f7f7e8bbc8c16c58745d918804f4f6f9d120`
- Vocabulary: `vocab.json`, 4,637 bytes; SHA-256:
  `d732ab2456c0c017930001dc9af0b41b3b93d25b2eb9740bf9d925508d7d87d0`
- Model configuration: `config.json`, 2,382 bytes; SHA-256:
  `428b7781d080ad9463dca0e17e5066073cb691bfc14a178a85e76ac79c1f4a0f`
- Preprocessor configuration: `preprocessor_config.json`, 212 bytes; SHA-256:
  `a2254a5b58f72cd4de3632f8eee64f3f098b7c1402128d2f419e7d00ae13e335`
- Posture: benchmark-only

`packages/audio-model-adapter` loads this revision lazily, verifies the pinned
model, configuration, preprocessor, and vocabulary bytes, validates 16 kHz normalized captures, preserves the full
392-token vocabulary, and converts logits to stable per-frame posterior
probabilities. A local synthetic-tone smoke run produced 49 frames whose first
posterior vector summed to `0.9999999999999983`; the downloaded model file also
matched the pinned SHA-256. No learner recording was used.

The same adapter is now connected to the consent-bound learner upload behind
`CADENCE_BENCHMARK_SCORING_ENABLED=1` plus current research-use consent. A
synthetic-tone end-to-end smoke run reached the constrained candidate lexicon
and returned an uncalibrated ambiguous result, as required. This connection is
benchmark infrastructure, not a clinical release.

The adapter enforces each file's byte length and SHA-256 before creating each
lazy runtime, including when files already exist in the revision-scoped
Transformers filesystem cache. Existing corrupt or truncated files fail closed
without silently downloading replacements. Missing files are downloaded from the
pinned official revision to temporary files, verified, and only then atomically
published to the cache. The metadata pins above were calculated from the exact
published bytes at that revision.

Loading streams all four cached files into a private, read-only temporary
snapshot while hashing. Transformers loads the configuration, processor, and
model from that exact snapshot with `local_files_only: true`; vocabulary parsing
uses the same snapshot. Every loader has a private cache directory, preventing
shared-cache fallback. The snapshot is removed after runtime construction,
including on failure. Shared cache changes cannot substitute different bytes
between verification and runtime loading. Custom/browser cache overrides are
rejected for this Node filesystem adapter; the adapter does not mutate global
Transformers settings. Signed distribution and deployment cache permissions
remain release-gate work.

A fully populated cache now supports a fresh runtime and inference without
network access. The pinned Transformers 4.2.0 processor reads the feature
extractor settings from `preprocessor_config.json`; this checkpoint does not
require tokenizer files. Missing assets still require a successful initial
download, and changing the runtime or checkpoint requires rechecking the asset
set and pins.

A September 22, 2026 local smoke check ran with macOS network access denied for
the entire process, as well as a fetch guard. It rejected same-length corruption
of each actual metadata file before runtime construction, then loaded the
existing 317,712,852-byte model and processed a synthetic one-second 220 Hz tone
with zero fetch attempts. Fresh runtime loading, snapshot verification/copying,
and inference took 762 ms; a second inference on the same runtime took 58 ms.
Both produced 49 frames with 392 tokens per frame; every posterior vector was
finite, nonnegative, and summed to one within 1e-12. Global Transformers settings
were unchanged. These are local development measurements, not device latency or
clinical-validation evidence. No learner recording was used and the model was
not downloaded again.

The opt-in check requires an already populated cache:

```sh
pnpm --filter @speech-therapy/audio-model-adapter test:offline
```

That command forbids fetch calls. The stronger macOS check used for the result
above also denies operating-system network access:

```sh
sandbox-exec -p '(version 1) (allow default) (deny network*)' \
  node packages/audio-model-adapter/scripts/offline-smoke.ts
```

The 22 adapter tests cover valid cached bytes, same-length corruption and
truncation of all four files, invalid downloads, metadata cache population,
offline cache reuse, shared-cache changes during loading, and snapshot cleanup
after loader failure. The opt-in actual-runtime smoke is separate from the
small, download-free default suite.

## Challengers and comparisons

- [`microsoft/wavlm-base-plus`](https://huggingface.co/microsoft/wavlm-base-plus)
  is a 16 kHz feature encoder trained on roughly 94,000 hours. Its model card
  explicitly requires a downstream tokenizer/head, so it cannot directly feed
  the phone-path scorer. It remains the owned-head challenger.
- [`nvidia/stt_en_conformer_ctc_small`](https://huggingface.co/nvidia/stt_en_conformer_ctc_small)
  is a roughly 13M-parameter CC BY 4.0 checkpoint, but its released vocabulary
  is lowercase English graphemes/SentencePiece rather than phones. It is useful
  for latency/engineering comparison, not as the current clinical evidence
  source.
- Whisper remains transcript/quality reference only; decoded word acceptance
  can infer the prompted word and must not determine pronunciation correctness.

Before any checkpoint can move beyond benchmark-only, legal review must verify
all code, weights, training-data, conversion, and redistribution terms; the
model must then clear the locked child/SSD target, calibration, subgroup,
latency, cost, and clinical-utility gates.

The candidate list can now be expressed as canonical manifests and evaluated by
the executable [audio model bake-off](audio-model-bakeoff.md). The inventory
above is still descriptive: no legal disposition or challenger measurement is
approved until authenticated evidence and a real locked cohort are supplied to
that harness.
