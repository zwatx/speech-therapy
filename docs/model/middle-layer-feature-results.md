# Intermediate-feature extraction results

Completed September 27, 2026. Both declared representations were extracted for
all 9,891 positions in 1,040 recordings from 52 children ages 6–12, covering all
23 supported consonants. This verifies the input to the planned comparison;
it does not establish an accuracy improvement.

The [fixed protocol](middle-layer-protocol.md) uses block 12 with parameter-free
per-frame normalization and the original final layer from the same forward pass.
Both use the original estimated windows and float64 mean pooling, cast to
float32. The 13 cached alignment scalars are unchanged. No labels entered encoder
inference, and no encoder weights were trained.

The Mac completed extraction in **205.78 seconds**. The first 20 recordings
projected 181.80 seconds, below the declared 45-minute local limit, so no Colab
runtime was allocated. The exact original local environment was retained:
Torch 2.8.0, Transformers 4.57.6, NumPy 2.2.6, float32 CPU, two threads,
deterministic algorithms and eager attention.

All **9,891 final-layer vectors match the old cache bit for bit**. This was
verified independently across the full matrix, beyond the first/longest
preflight checks. The first recording also repeated exactly at the end. An
independent reviewer replayed the first, longest and fixed midpoint-index
recordings through the actual encoder; both the normalized middle and final
representations matched their saved vectors exactly.

The independent audit checked both complete matrices against all 1,040 per-clip
artifacts, exact global row identities, original windows, cached scalar values,
model/source hashes, timing and preserved repeat outputs. No blocking findings
remain. The earlier metadata-only v1 declaration was never run; v2 added the
review-requested installed-implementation and synthetic-probe bindings before
inference.

The next stage compares 50 selection fits and 50 fresh refits using the unchanged
speaker/word partitions and training recipe. Its source review passed, including
the 25 reused scalar-reference cells and the declared nonregression screens.
Training outcomes remain separate from this extraction report. The existing
research candidate and all learner/clinical eligibility flags remain unchanged.

Evidence: [v2 extraction plan](../../research/audio-head/outputs/multiphone-20260927/middle-layer-features-v2/plan.json),
[frozen extraction report](../../research/audio-head/outputs/multiphone-20260927/middle-layer-features-v2/run/report.json),
[independent extraction audit](../../work/middle-layer-review-20260927/results-review.json),
[head plan](../../research/audio-head/outputs/multiphone-20260927/middle-layer-heads-v1/plan.json),
and [head source review](../../work/middle-layer-heads-review-20260927/review.json).
