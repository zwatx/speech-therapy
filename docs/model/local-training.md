# Local phone-head training

Implemented September 21–22, 2026 in `research/audio-head/`. This is an isolated,
executable engineering experiment. It has no connection to the web upload
handler, patient data, release registry, or learner feedback.

The real path loads a frozen `facebook/wav2vec2-base` encoder, extracts each
clip's last-layer frame embeddings, and optimizes a small linear CTC phone head
on the training split. The generated smoke fixtures contain tones labeled
`tone-a` and `tone-b`; they are not speech or synthetic patient examples. The
alternative spectral encoder is a deterministic test baseline, not a pretrained
speech model.

The pipeline now also imports a bounded public CMU Arctic speech subset and
trains against its **automatic phone alignments**. That is a separate manifest
mode: those labels are not expert judgments of what was actually produced.

## Setup and run

Use Python 3.13. The verified local environment was Python 3.13.14, PyTorch
2.8.0, Transformers 4.57.6, and Node.js 24.18.0 on Apple Silicon CPU. Node is
needed for the Python suite's cross-language CTC parity tests. The requirements lock pins
the resolved direct and transitive packages; no root JavaScript dependency
changes are needed.

On this machine `python3.13` resolves to `/opt/homebrew/bin/python3.13`; the
existing `.venv` is already installed and usable. The default `python3` is 3.14,
so use the explicit 3.13 command. On another machine, install Python 3.13 first.

From the repository root:

```sh
python3.13 -m venv research/audio-head/.venv
research/audio-head/.venv/bin/python -m pip install -r research/audio-head/requirements.lock.txt
research/audio-head/.venv/bin/python -m unittest discover -s research/audio-head -p 'test_*.py' -v
research/audio-head/.venv/bin/python research/audio-head/run.py fixtures research/audio-head/outputs/my-fixtures
research/audio-head/.venv/bin/python research/audio-head/run.py validate research/audio-head/outputs/my-fixtures/manifest.json
research/audio-head/.venv/bin/python research/audio-head/run.py train \
  research/audio-head/outputs/my-fixtures/manifest.json \
  research/audio-head/outputs/my-wav2vec2-run \
  --encoder wav2vec2-base --steps 200 --seed 7 --allow-model-download
research/audio-head/.venv/bin/python research/audio-head/run.py infer \
  research/audio-head/outputs/my-wav2vec2-run \
  research/audio-head/outputs/my-fixtures/test-02.wav \
  research/audio-head/outputs/my-wav2vec2-run/posteriors.json
```

The first real-encoder run downloads approximately 380 MB of weights. Downloads
are disabled unless `--allow-model-download` is supplied; later runs use the
local cache. Generated audio, model downloads, environments, reports, and
checkpoints stay under ignored local directories. Choose new fixture/run/output
names on reruns; the commands refuse to overwrite results. For a small offline
optimization check without downloading weights, use
`--encoder spectral-engineering-v1` with the generated fixtures.

## Pinned encoder and output contract

The [official model](https://huggingface.co/facebook/wav2vec2-base) snapshot is
`0b5b8e868dd84f03fd87d01f9c4ff0f080fecfe8`. `encoders.py` pins SHA-256 values for
the weights, model config, and preprocessing config, and checks all three
before loading. The weight digest was obtained from the official repository's
LFS metadata; config digests were calculated from the exact revision's files.
The model loads local verified files with restricted weights-only loading and
no remote code. Its parameters have gradients disabled and remain in eval mode.
Clips are encoded individually to avoid padded-audio normalization effects.

Each training run writes:

- `head.pt`: only the linear head weights, not a duplicate encoder.
- `checkpoint.json`: head digest, exact encoder identity, vocabulary, manifest
  digest, seed, fixed step budget, and hard-false release flags.
- `report.json`: observed losses and sequence matches per split, training
  curve, timings, runtime versions, source-file digests, and limitations.

Inference verifies the head digest and encoder identity, then writes an envelope
whose `frames` field has the existing TypeScript `FramePosterior[]` structure:
every row includes the complete vocabulary and `<blank>`, with finite
probabilities summing to one. The envelope always contains `calibrated: false`,
`productionEligible: false`, and `learnerFeedbackEligible: false`. It does not
produce `pCorrect`, a clinical error label, a signed bake-off entry, or a release
authorization. JSON posterior export is implemented; ONNX/Core ML export is not.

## Fixture manifest

See a generated `manifest.json` for a complete example. The root requires
`schemaVersion: 1`, `purpose`, `labelSource: "produced-phones"`, `vocabulary`,
`items`, and both release flags set to false. Vocabulary index zero must be
`<blank>`; targets cannot contain that token.

Each item requires `id`, a relative `audioPath`, `audioSha256`, `speakerHash`,
`householdHash`, `split`, `producedPhones`, and `provenance`. Allowed splits are
`train`, `calibration`, and `test`; all three must exist. All sessions from a
speaker or household must stay in one split. The validator rejects duplicate
audio bytes or decoded PCM across any items (including metadata-only WAV
variations), duplicate IDs, unsupported phones, unknown
fields, missing partitions, escaping paths, mismatched hashes, truncated WAVs,
wrong channel/rate/encoding, clipped/silent captures, and clips outside 150 ms
to 5 seconds. It requires mono 16 kHz 16-bit PCM WAVs and does not resample.

For version 1, `purpose` is restricted to `synthetic-engineering` or
`permitted-engineering`. A provenance string is an operator-supplied reference,
not authenticated permission. This tool does not implement patient-data
consent checks, dataset authorization, or deletion operations. Do not use it to
import application recordings; governed research integration remains separate.

Training targets describe **produced** phones, never the intended prompt. The
linear head trains only on `train`; the other partitions are reported after
the fixed optimization budget. There is no automatic hyperparameter selection
or early stopping against held-out labels. Despite its partition name,
`calibration` currently only receives an uncalibrated evaluation report; no
calibration is fitted. CTC input lengths mask padded frames, and repeated
targets require enough frames for intervening blanks. Impossible alignments and
nonfinite losses/gradients abort instead of silently zeroing the loss.

## Observed local smoke run

The initial real-checkpoint run used 30 generated, variable-length tone clips:
18 train, 6 calibration, and 6 test. With seed 7, 200 AdamW steps, learning rate
0.01, two CPU threads, and a 2,307-parameter linear head:

| Observation | Measured value |
| --- | --- |
| Training CTC loss, before → after | 7.85854 → 0.20929 |
| Training exact tone-sequence matches | 12 / 18 |
| Held-out calibration tone-sequence matches | 3 / 6 |
| Held-out test tone-sequence matches | 2 / 6 |
| First encoder load, including download | 26.17 seconds |
| Frozen feature extraction, 30 clips | 0.68 seconds |
| Head optimization, 200 steps | 0.075 seconds |
| Complete initial run | 26.93 seconds |
| Saved head weight file | 11,021 bytes |
| Separate warm inference for one clip | 46.72 ms, 23 frames |

These are single local measurements, not latency percentiles, calibrated speech
accuracy, or clinical results. The low held-out sequence accuracy is reported
as observed; we did not tune on that test set to improve the displayed number.
Repeated experiments on the same generated test set remain exploratory.

After review added the decoded-PCM duplicate guard, the final implementation
was rerun at `research/audio-head/outputs/wav2vec2-verified-seed7/`. Its report's
Python source hashes record that implementation; the seed and fixed recipe reproduced
the same losses and match counts. With cached weights that complete run took
2.04 seconds (1.25 seconds loading, 0.70 seconds extracting features, and 0.085
seconds optimizing). The initial run is preserved separately at
`outputs/wav2vec2-seed7/`; its source hashes record the earlier implementation.

The exported real-encoder posteriors were also passed directly into the
existing TypeScript `ctcSequenceLogProbability`. All 23 rows met the scorer's
normalization/vocabulary requirements and yielded finite constrained sequence
log probabilities. This checks interoperability, not pronunciation correctness.

Seventeen focused tests cover manifest leakage/corruption, audio validation,
unsupported phones, repeated-token CTC math, padding gradients, posterior
normalization, pinned-artifact corruption, actual loss reduction, deterministic
seed behavior, checkpoint reload/export parity, and release flags. They use
small synthetic fixtures and do not download encoder weights. The separate
real-checkpoint smoke provides the upstream runtime execution evidence.

## Public speech experiment

CMU Arctic provides studio read speech and automatically aligned phone labels.
The official [corpus paper](https://www.cs.cmu.edu/~awb/papers/ssw5/arctic.pdf)
describes the recordings and reuse; the source
[README](http://festvox.org/cmu_arctic/cmu_arctic/cmu_us_bdl_arctic/README)
identifies the phone labels as automatic. The
[per-speaker COPYING](http://festvox.org/cmu_arctic/cmu_arctic/cmu_us_bdl_arctic/COPYING)
permits use and modification for any purpose subject to retaining notices and
marking modifications. The importer preserves every selected speaker's full
COPYING and README, checks the reviewed license hashes, and adds a modification
notice. Original WAV/LAB bytes are unchanged. No speech synthesis is performed.

```sh
research/audio-head/.venv/bin/python research/audio-head/import_arctic.py \
  research/audio-head/outputs/my-arctic
research/audio-head/.venv/bin/python research/audio-head/run.py train \
  research/audio-head/outputs/my-arctic/manifest.json \
  research/audio-head/outputs/my-arctic-head \
  --encoder wav2vec2-base --steps 200 --seed 7 --learning-rate 0.01
```

This importer downloads individual files from the official host rather than
whole archives. Its default single-speaker profile has a 25 MB transfer budget
and per-file size limits. It
selects the first valid short clips in predeclared, nonoverlapping prompt ranges:
32 from corpus speaker `bdl` for training, 12 from `rms` for calibration, and 12
from `slt` for test. Eligibility checks use format, duration, level, supported
phone labels, and consistent increasing alignment boundaries; they do not use
model predictions. The first import downloaded 6,486,234 bytes, accepted 56
clips, and rejected 10 clips. Every rejection reason is in `import-report.json`.

The public corpus does not provide household relationships. Version 2 manifests
therefore require `householdHash: null` and the explicit basis
`speaker-disjoint-households-unknown`; they never fabricate household independence.
The vocabulary is a fixed 45-token Festival/CMU inventory plus CTC blank,
declared independently of holdout labels. `pau` is an automatic silence label,
distinct from CTC blank.

Version 2 uses `purpose: "public-speech-engineering"`,
`labelSource: "automatic-phone-alignment"`, and `pseudoPhones`, with local
alignment paths/digests and a source-lock digest. The loader binds the complete
selection's speaker-derived identity, split, and paired WAV/LAB paths to the
source lock. It checks label-file hashes and that pseudo targets exactly match the
automatic alignment. It also applies existing audio/duplicate/speaker checks.
Version 1 continues to require `produced-phones`; converting expected text into
phones does not satisfy that contract. Reports and inference exports preserve
automatic-label provenance and unknown-household limitations.

Every observed source URL, byte count, and SHA-256 is recorded in
`source-lock.json`. The official files were available over HTTP; these hashes
pin observed bytes for reproducibility, not authenticated transport or an
immutable upstream release. Replay a selection with exact byte verification:

```sh
research/audio-head/.venv/bin/python research/audio-head/import_arctic.py \
  research/audio-head/outputs/my-arctic-replay \
  --source-lock research/audio-head/outputs/my-arctic/source-lock.json
```

The first real-speech run is retained at
`research/audio-head/outputs/cmu-arctic-head-seed7/`. It used the same frozen
wav2vec2 encoder and fixed 200-step budget, with a 35,374-parameter linear head:

| Metric against automatic alignment | Train: 32 clips | Calibration: 12 clips | Test: 12 clips |
| --- | --- | --- | --- |
| Final CTC loss | 0.6536 | 3.3331 | 3.6130 |
| Token edits / reference tokens | 216 / 1,160 | 282 / 406 | 267 / 379 |
| Token error rate | 18.62% | 69.46% | 70.45% |
| Exact sequences | 2 / 32 | 0 / 12 | 0 / 12 |

Initial training CTC loss was 12.3691. The run took 6.75 seconds locally,
including 3.69 seconds extracting frozen features and 1.56 seconds optimizing.
Token error rate is edit distance divided by reference tokens and may exceed
100% when insertions are numerous. Here its reference is the automatic corpus
alignment, not human-reviewed produced phones. A separate test speaker and
different prompts expose the poor generalization of this tiny experiment;
speaker, prompt, and recording differences are confounded. No clinical,
subgroup, or prospective population performance can be inferred.

The reviewed fixed-recipe rerun is preserved at
`outputs/cmu-arctic-verified-seed7/`; it reproduced the same losses and edit
counts and captured the updated source digests. Its diagnostics break the 267
test edits into 141 substitutions, 119 deletions, and 7 insertions. The greedy
path selected blank on 79.33% of frames and emitted 70.45% as many phone tokens
as the reference. This is substantial underprediction plus substitution,
rather than complete blank collapse. The report also includes per-reference
phone support and substitution pairs. These are descriptive automatic-label
agreement measures; they do not select a checkpoint or set clinical thresholds.

The expanded 33-test suite covers automatic-label provenance, source-lock
speaker/split relabeling, WAV/LAB pairing, alignment corruption/boundaries,
unknown-household handling, bounded downloads, and diagnostic edit attribution.
An actual download replay produced a byte-identical source lock. Every report
retains hashes of its executed source version; later code updates do not rewrite
historical results.

## Predeclared four-speaker expansion

The expanded `four-speaker-v1` profile accepts 48 clips from each of `bdl`,
`awb`, `clb`, and `jmk` for 192 training recordings. Training candidates remain
`arctic_a0001` through `arctic_a0080`; eligibility uses the same format, duration,
level, and automatic-alignment checks. It replays the original 12 `rms`
calibration and 12 `slt` test recordings from their source lock. These holdouts
were already inspected during the one-speaker experiment and are not fresh
confirmatory evidence. Household relationships remain unknown.

The recipe in `research/audio-head/experiments/cmu-arctic-four-speaker-v1.json`
was recorded before either expanded training run. It fixes the same encoder,
linear head, seed 7, learning rate 0.01, and two step budgets: 200 and 800. Both
runs are retained and reported; neither holdout selects a checkpoint or winner.
The 200-step comparison changes both training speaker coverage and clip count,
so it cannot isolate a causal speaker-diversity effect. The 800-step run examines
additional optimization on that same expanded training set.

```sh
research/audio-head/.venv/bin/python research/audio-head/import_arctic.py \
  research/audio-head/outputs/my-arctic-four-speaker \
  --profile four-speaker-v1 \
  --holdout-lock research/audio-head/outputs/cmu-arctic-v1/source-lock.json
research/audio-head/.venv/bin/python research/audio-head/run.py train \
  research/audio-head/outputs/my-arctic-four-speaker/manifest.json \
  research/audio-head/outputs/my-arctic-four-speaker-200 \
  --encoder wav2vec2-base --steps 200 --seed 7 --learning-rate 0.01
research/audio-head/.venv/bin/python research/audio-head/run.py train \
  research/audio-head/outputs/my-arctic-four-speaker/manifest.json \
  research/audio-head/outputs/my-arctic-four-speaker-800 \
  --encoder wav2vec2-base --steps 800 --seed 7 --learning-rate 0.01
```

The completed import at `outputs/cmu-arctic-four-speaker-v1/` downloaded
24,811,576 bytes, accepted 216 recordings, and rejected 7 candidates within its
100 MB hard transfer cap. All 24 original holdout manifest records and paired
WAV/LAB bytes were independently checked as identical. The named profile
validator enforces each speaker's split, prompt range, unique membership, and
exact count. The importer requires a prior holdout lock for a new expanded
selection and preserves all six speakers' source notices.

Actual runs are preserved at `outputs/cmu-arctic-four-speaker-200-seed7/` and
`outputs/cmu-arctic-four-speaker-800-seed7/`. Both used the existing verified
encoder cache with model downloads disabled, the same 35,374-parameter head,
two CPU threads, and 143,245-byte head checkpoints.

| Fixed run | Train edits / tokens (rate) | Calibration edits / tokens (rate) | Test edits / tokens (rate) | Total local time |
| --- | --- | --- | --- | --- |
| Original one speaker, 200 steps | 216 / 1,160 (18.62%) | 282 / 406 (69.46%) | 267 / 379 (70.45%) | 6.75 s initial run |
| Four speakers, 200 steps | 2,695 / 6,888 (39.13%) | 215 / 406 (52.96%) | 226 / 379 (59.63%) | 26.57 s |
| Four speakers, 800 steps | 1,434 / 6,888 (20.82%) | 204 / 406 (50.25%) | 189 / 379 (49.87%) | 54.64 s |

The expanded runs' initial training CTC loss was 14.9444. Final train,
calibration, and test losses were respectively 1.1546, 1.9616, and 2.0345 at
200 steps, and 0.5444, 2.4464, and 2.0856 at 800 steps. More optimization lowered
greedy token edit rates but increased both held-out CTC losses. This divergence
does not support a blanket claim that the longer run is better. Neither run
matched any complete calibration or test phone sequence; training exact matches
were 0/192 and 2/192 respectively.

On test, the 200-step run made 72 substitutions, 153 deletions, and 1 insertion;
81.95% of greedy frames were blank. The 800-step run made 80 substitutions,
104 deletions, and 5 insertions; 76.83% of frames were blank. Underprediction
remains substantial. These tiny, repeated, one-speaker-per-holdout measurements
have no population confidence claim and cannot establish learner-error detection.
Automatic alignments can themselves be wrong. Both artifacts remain
uncalibrated and ineligible for production or learner feedback.

Each saved head was independently reloaded and used to export the same original
test recording, `slt/arctic_a0201.wav`. Both `posteriors-slt-a0201.json` files
contain 127 normalized frames over all 46 vocabulary entries, retain exact
checkpoint linkage and automatic-label/unknown-household provenance, and keep
all release flags false. This verifies inference/export execution, not target
pronunciation correctness. The 40-test Python suite at this stage passed,
including profile counts/ranges, locked holdout requirements, diagnostic math,
and comparison provenance/arithmetic rejection cases.

Compare preserved runs in a supplied order, with exact holdout identity checks:

```sh
research/audio-head/.venv/bin/python research/audio-head/comparison.py \
  --run research/audio-head/outputs/cmu-arctic-verified-seed7 \
    research/audio-head/outputs/cmu-arctic-v1/manifest.json \
  --run research/audio-head/outputs/cmu-arctic-four-speaker-200-seed7 \
    research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json \
  --run research/audio-head/outputs/cmu-arctic-four-speaker-800-seed7 \
    research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json \
  --output research/audio-head/outputs/my-arctic-comparison.json
```

The comparison verifies manifest/checkpoint/report linkage, metric arithmetic,
compatible encoder/vocabulary/head, and identical held-out recordings, labels,
and identities. It reports differences from the first supplied run and never
ranks or selects a winner. It does not independently recompute predictions or
authenticate historical report claims. All paths must refer to existing local
runs and manifests; use a new comparison output name.

## Fixed gain and noise stress check

`stress.py` evaluates every supplied head on the same original held-out
recordings under four fixed conditions: unchanged waveform, −6 dB gain, and
deterministic white noise at 20 dB and 10 dB signal-to-noise ratio (SNR). The
recipe was recorded before execution in
`research/audio-head/experiments/cmu-arctic-stress-v1.json`. Seed 17 and each
original recording hash determine its noise stream; both noise levels use that
same stream. No training, tuning, filtering, or winner selection is performed.

SNR uses whole-recording RMS, including silence. Noise magnitude is set from
that signal/noise power ratio. If the mixture would exceed a 0.99 peak, one
shared scalar reduces both signal and noise, preserving the ratio without hard
clipping. The report records measured SNR from the delivered float32 waveform,
the mixture scale, peaks, and transformed waveform hash for every recording.
Phone labels, sample count, timing, and pitch remain unchanged. This artificial
white-noise check does not represent speech-active SNR, microphones, rooms,
competing speech, or a clinical noise-robustness evaluation.

All runs pass the comparison module's checkpoint/report/manifest and exact
holdout checks first. The frozen encoder loads once with downloads disabled;
each condition's transformed features are shared across all heads, then
discarded. There is no persistent waveform or feature cache. The original
condition recomputes each stored holdout's counts, token edits, exact matches,
and CTC loss; a material discrepancy aborts the report. Gain behavior includes
the pinned encoder's per-recording waveform normalization.

```sh
research/audio-head/.venv/bin/python research/audio-head/stress.py \
  --run research/audio-head/outputs/cmu-arctic-verified-seed7 \
    research/audio-head/outputs/cmu-arctic-v1/manifest.json \
  --run research/audio-head/outputs/cmu-arctic-four-speaker-200-seed7 \
    research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json \
  --run research/audio-head/outputs/cmu-arctic-four-speaker-800-seed7 \
    research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json \
  --recipe research/audio-head/experiments/cmu-arctic-stress-v1.json \
  --output research/audio-head/outputs/my-arctic-stress.json
```

The actual report is preserved at `outputs/cmu-arctic-stress-v1.json`. It
evaluated all three heads on exactly 24 original holdout clips × four conditions
with 96 encoder calls and one encoder load, taking 7.70 seconds locally. The
original-condition recomputation matched the stored metrics for every head.
Each cell below is **calibration / test token error rate against automatic
alignments**; the reference denominators remain 406 / 379 tokens respectively.
The JSON preserves all edit counts, CTC losses, diagnostics, and per-clip
transform measurements for every head and condition.

| Condition | One speaker, 200 steps | Four speakers, 200 steps | Four speakers, 800 steps |
| --- | --- | --- | --- |
| Original | 69.46% / 70.45% | 52.96% / 59.63% | 50.25% / 49.87% |
| −6 dB gain | 69.46% / 70.45% | 52.96% / 59.63% | 50.25% / 49.87% |
| White noise, 20 dB SNR | 91.38% / 95.25% | 73.40% / 77.57% | 70.44% / 83.64% |
| White noise, 10 dB SNR | 118.47% / 112.66% | 104.19% / 118.47% | 166.50% / 133.51% |

Every −6 dB greedy edit count stayed unchanged, consistent with the encoder's
waveform normalization; this does not establish invariance to arbitrary capture
conditions. Noise worsened each head's loss and edit rate. The longer expanded
run had lower clean test edits but higher noisy test edits than the 200-step
expanded run at both noise levels. There is no overall ranking or selected
winner. At 10 dB, many inserted tokens drive rates above 100%; those rates are
valid and are not capped. For example, the longer expanded run's test edits
were 226 substitutions + 2 deletions + 278 insertions = 506 / 379 tokens.
No head matched a complete held-out sequence under any condition.

Phone coverage is also limited: each training manifest contains 39 distinct
phones from the fixed 45 nonblank entries. Calibration has no reference phone
absent from training, but test contains two `zh` tokens that never occur in
training. We report this observed coverage gap without changing the corpus or
recipe in response to holdout labels.

Delivered SNR was within 0.000001 dB of each nominal target across all clips.
No selected recording required joint peak scaling; the largest noise-condition
peak was 0.71632. The synthetic loud-signal test separately exercises the
scaling branch and verifies SNR preservation without hard clipping. All 48
Python tests passed, including deterministic transforms, original-condition
equivalence, shared extraction, and fail-before-encoder checks for changed
holdouts or corrupt heads. No fresh model download, patient audio, paid compute,
or release eligibility was introduced.

## Predeclared WavLM representation comparison

The paired experiment uses `microsoft/wavlm-base-plus` at revision
`4c66d4806a428f2e922ccfa1a962776e232d487b` on the identical 216-clip manifest,
46-entry vocabulary, linear head, seed 7, learning rate 0.01, and 200/800-step
budgets. Its matched wav2vec2 control runs use the same settings. The recipe in
`experiments/cmu-arctic-paired-encoders-v2.json` was recorded before any of these
four runs and binds the dataset, encoders, license evidence,
and unchanged stress recipe. All holdouts were already inspected; this is
exploratory representation comparison with no automatic winner selection.

An explicit `--head-seed 7` resets the random generator immediately before
creating each linear head. All four initial weight digests must match. The
global seed alone is insufficient to guarantee this because encoder construction
consumes random numbers differently. Omitting the new option preserves the
older trainer behavior and its existing artifacts. New reports/checkpoints
record `headInitializationSeed` and `initialHeadSha256`; the digest hashes the
initial float32 weight matrix then bias vector in little-endian order.

The [pinned Microsoft model card](https://huggingface.co/microsoft/wavlm-base-plus/blob/4c66d4806a428f2e922ccfa1a962776e232d487b/README.md)
links to the [Microsoft UniSpeech CC BY-SA 3.0 license](https://github.com/microsoft/UniSpeech/blob/6112826ac13a4327f4c9a7afa2a505e35b763514/LICENSE).
The experiment conservatively follows those stated terms for private engineering
use and preserves the complete card, license, source hashes, and attribution at
`outputs/wavlm-source-inspection-v1/`. The distinct MIT license for UniLM code
is not asserted to license these weights. Checkpoint/report/inference encoder
identities retain both immutable source links and content hashes. This is no
redistribution, product-license clearance, or production selection.

The pinned weights are 377,617,425 bytes; config and preprocessing files add
2,232 and 215 bytes, for 377,619,872 bytes total. Their SHA-256 values and sizes
are enforced before loading. Installed Transformers 4.57.6 already provides
`WavLMModel`, so no package upgrade is required. The official preprocessing sets
`do_normalize: false`, unlike the wav2vec2 baseline; it is preserved exactly.
That difference is part of the checkpoint comparison and is not silently
harmonized. Frozen parameters stay in evaluation mode, and only the same
35,374-parameter linear head is optimized.

With both pinned encoders already cached, the paired command pattern is:

```sh
for encoder in wav2vec2-base wavlm-base-plus; do
  for steps in 200 800; do
    research/audio-head/.venv/bin/python research/audio-head/run.py train \
      research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json \
      "research/audio-head/outputs/my-paired-${encoder}-${steps}" \
      --encoder "$encoder" --steps "$steps" --seed 7 --head-seed 7 --learning-rate 0.01
  done
done
```

An uncached first load requires the existing explicit `--allow-model-download`
option. WavLM's first verified fetch and load took 25.37 seconds locally; the
subsequent fixed runs used only the populated cache. Run the unchanged stress
command separately for each encoder's two new heads. Its default same-encoder
guard is retained, so transformed features are never passed between encoder
families. For a report-only contrast between the paired families, the comparison
CLI requires explicit `--allow-encoder-comparison`; it still enforces matching
holdout identities, labels, vocabulary, head architecture, and label provenance.
Training settings and initial-head digests are reported for inspection rather
than assumed equal by that generic comparison command.

The four completed runs are preserved as
`outputs/cmu-arctic-paired-{wav2vec2,wavlm}-{200,800}-headseed7/`.
All four initial heads matched SHA-256
`73d9a5e2612b2b70401910eb5824832489db326f5baed45c72e559527cc90090`.
The checked cross-encoder report is `outputs/cmu-arctic-paired-comparison-v2.json`;
the training partition also matches across all four runs, in addition to the
required identical holdouts. Earlier runs remain unchanged and separately
reported above.

| Paired encoder / steps | Train edits / 6,888 (rate) | Calibration edits / 406 (rate) | Test edits / 379 (rate) | Local run time |
| --- | --- | --- | --- | --- |
| wav2vec2 / 200 | 2,735 (39.71%) | 214 (52.71%) | 232 (61.21%) | 26.38 s |
| wav2vec2 / 800 | 1,472 (21.37%) | 205 (50.49%) | 196 (51.72%) | 53.85 s |
| WavLM / 200 | 356 (5.17%) | 58 (14.29%) | 50 (13.19%) | 26.49 s |
| WavLM / 800 | 86 (1.25%) | 61 (15.02%) | 40 (10.55%) | 55.08 s |

| Paired encoder / steps | Final CTC loss: train / calibration / test | Exact sequences: train / calibration / test |
| --- | --- | --- |
| wav2vec2 / 200 | 1.1889 / 1.9629 / 2.0574 | 0/192 / 0/12 / 0/12 |
| wav2vec2 / 800 | 0.5642 / 2.4518 / 2.0892 | 5/192 / 0/12 / 0/12 |
| WavLM / 200 | 0.1907 / 0.6749 / 0.5574 | 50/192 / 1/12 / 0/12 |
| WavLM / 800 | 0.0540 / 0.7537 / 0.6914 | 128/192 / 1/12 / 1/12 |

Initial train losses were 15.1379 for wav2vec2 and 15.2200 for WavLM. These
different initial losses occur despite identical head weights because their
encoder features differ. WavLM produced fewer edits in this small repeated
sample check, but more optimization did not improve every measure: its
800-step run had higher calibration edits and higher calibration/test CTC
losses than its 200-step run despite lower clean test edits.

Separate same-encoder stress reports are preserved at
`outputs/cmu-arctic-paired-wav2vec2-stress-v2.json` and
`outputs/cmu-arctic-paired-wavlm-stress-v2.json`. Every transformed waveform
hash and measurement matched across the two reports (96 records each), so each
encoder received identical perturbations. The original condition reproduced
the saved run metrics. Cells again show **calibration / test automatic-label
token error rate**, with 406 / 379 reference tokens throughout.

| Condition | wav2vec2 / 200 | wav2vec2 / 800 | WavLM / 200 | WavLM / 800 |
| --- | --- | --- | --- | --- |
| Original | 52.71% / 61.21% | 50.49% / 51.72% | 14.29% / 13.19% | 15.02% / 10.55% |
| −6 dB gain | 52.71% / 61.21% | 50.49% / 51.72% | 14.53% / 13.19% | 15.02% / 10.29% |
| White noise, 20 dB SNR | 67.98% / 72.56% | 68.97% / 70.18% | 14.29% / 14.78% | 16.01% / 14.78% |
| White noise, 10 dB SNR | 108.37% / 116.62% | 157.64% / 119.79% | 17.73% / 21.11% | 18.97% / 23.75% |

WavLM gain perturbation changed a few greedy decisions, consistent with retaining
its different official preprocessing. At 10 dB noise, its 800-step run had more
test edits than its 200-step run. Both complete fixed budgets and every stress
condition remain reported; there is no selected checkpoint. The two stress
runs took 9.92 and 7.93 seconds respectively, each with one encoder load and
96 feature extractions. These are single local elapsed measurements, with some
overlapping CPU work, not isolated latency benchmarks.

Both WavLM checkpoints were also reloaded and used to export
`posteriors-slt-a0201.json` within their own run directories. Each real export
passed 127-frame/46-token normalization, checkpoint linkage, exact license
evidence, automatic-label/unknown-household provenance, and false release flags.
The expanded 54-test suite passed, including asset corruption and independent
head-seed behavior; separate review checked the recipe and legacy compatibility.

This controls our corpus, labels, head initialization, and optimizer settings.
It does not control the encoders' different upstream pretraining or official
preprocessing. Pretraining-corpus overlap with this evaluation corpus was not
audited or excluded. The references remain automatic alignments of adult studio
read speech, not reviewed child speech productions or clinical errors. The
holdouts are small and previously inspected. No clinical robustness, population
performance, deployment winner, or redistribution permission is inferred.

## Head-initialization stability

The bounded recipe, `experiments/cmu-arctic-head-seed-stability-v1.json`,
adds head seeds 17 and 29 to the preserved paired seed-7 runs. Global seed 7,
both encoders, the exact 216-clip manifest, the linear head, learning rate 0.01,
and both 200/800-step budgets stay fixed. Eight additional runs execute
sequentially with two CPU threads and the existing verified caches. There are
no new downloads, data changes, hyperparameter choices, or repeated noise tests.
The recipe and runner hash were recorded before those runs began.

The transparent experiment runner reuses the existing manifest/checkpoint/report
validators and compares groups of three within the comparison tool's ten-run
limit. It verifies all seed-7 anchors first, validates every completed run,
requires identical training/holdout partitions, and requires one exact paired
initial-head hash across both encoders and budgets for each seed. It preserves
all twelve run records and reports each metric's three values, mean, minimum,
maximum, and sample standard deviation for each encoder/step group.

These summaries describe **head-initialization variability only** on the same
already-inspected holdouts. Three head seeds are not three independent speakers
or cohorts. The sample standard deviation uses a denominator of `n − 1`; it is
not a population confidence interval or a standard error. No best seed or
checkpoint is selected, and all earlier model limitations still apply.

```sh
research/audio-head/.venv/bin/python \
  research/audio-head/experiments/run_head_seed_stability.py
```

The script resumes validated completed run directories after an interruption,
but refuses to replace a completed stability report. A changed protocol needs
a separately declared recipe and new output names.

All eight added runs completed. The full twelve-run evidence and aggregates are
preserved at `outputs/cmu-arctic-head-seed-stability-v1.json`; added run directory
names follow the existing pattern with `headseed17` and `headseed29`. Each seed
has an identical initial head across both encoders and budgets, with distinct
hashes between seeds. All six 200-step training curves exactly match the first
200 steps of their separately executed 800-step pair.

Every seed's observed holdout edit counts are shown below as **calibration /
test**, against the unchanged 406 / 379 reference tokens:

| Encoder / steps | Head seed 7 | Head seed 17 | Head seed 29 |
| --- | --- | --- | --- |
| wav2vec2 / 200 | 214 / 232 | 218 / 224 | 214 / 221 |
| wav2vec2 / 800 | 205 / 196 | 211 / 191 | 212 / 194 |
| WavLM / 200 | 58 / 50 | 56 / 47 | 50 / 48 |
| WavLM / 800 | 61 / 40 | 53 / 38 | 54 / 43 |

Initialization-only summaries of token error rate, with sample SD in percentage
points (pp):

| Encoder / steps | Calibration mean; min–max; SD | Test mean; min–max; SD |
| --- | --- | --- |
| wav2vec2 / 200 | 53.04%; 52.71–53.69%; 0.57 pp | 59.54%; 58.31–61.21%; 1.50 pp |
| wav2vec2 / 800 | 51.56%; 50.49–52.22%; 0.93 pp | 51.10%; 50.40–51.72%; 0.66 pp |
| WavLM / 200 | 13.46%; 12.32–14.29%; 1.03 pp | 12.75%; 12.40–13.19%; 0.40 pp |
| WavLM / 800 | 13.79%; 13.05–15.02%; 1.07 pp | 10.64%; 10.03–11.35%; 0.66 pp |

The JSON also retains every training metric and the same summaries for CTC loss
and exact-sequence rate across all three partitions. WavLM's lower edit rates
on these repeated recordings persist across the three head initializations,
but this does not quantify uncertainty across new speakers, devices, or clinical
populations. Added seeds received clean evaluation only; earlier noise results
do not establish noise stability across these seeds. No seed was selected or
dropped, no calibration was fitted, and all release flags remain false.

The next work is independently reviewed produced-phone labels, grouped training
folds, broader encoder comparisons, calibration, and governed research data
integration. The [model roadmap](model-development-roadmap.md) defines that
sequence and the evidence needed before learner-feedback claims.

## Local runtime measurements on public speech

The fixed recipe `experiments/cmu-arctic-runtime-v1.json` uses the paired
200-step, head-seed-7 artifacts for both encoders. This is a same-architecture
compute comparison; the fixed budget does not select a model by accuracy.
`measure_runtime.py` verifies each run, manifest, and checkpoint before loading
its pinned encoder with downloads disabled. Each encoder was run in a separate,
fresh Python CLI process, sequentially, on an Apple M3 Max with 48 GiB physical
memory, CPU execution, and two Torch threads. The model files were already
cached; filesystem cache and background host load were not controlled.

Each process reports runtime construction and its first inference separately,
then makes three fixed passes over all 24 original calibration/test clips in
recording-ID order: 72 measured calls per encoder. Clips range from 1.155 to
4.005 seconds. The first call uses the same 1.735-second clip,
`cmu-rms-arctic_a0102`. Features are recomputed for every call; no feature or
posterior cache is used. Every repeated clip produced the identical normalized
posterior hash, including the separately reported first call.

| Measurement | wav2vec2 + owned head | WavLM + owned head |
| --- | --- | --- |
| Runtime construction with cached weights | 1.805 s | 1.200 s |
| First inference | 71.35 ms | 75.90 ms |
| Repeated inference median | 65.51 ms | 67.70 ms |
| Repeated inference p95, nearest rank | 81.37 ms | 83.77 ms |
| Repeated inference maximum | 85.22 ms | 87.11 ms |
| Median real-time factor | 0.02201 | 0.02270 |
| p95 real-time factor, nearest rank | 0.02528 | 0.02644 |
| Peak whole-process resident memory | 1,313.69 MiB | 1,321.72 MiB |

Real-time factor is inference time divided by that recording's duration. The
latency timer includes waveform preprocessing, frozen encoder, owned head,
softmax and validation, and conversion to Python frame dictionaries. It excludes
audio-file decoding, JSON serialization, output hashing, and transport. Runtime
construction includes head and encoder loading/integrity checks after dataset
validation. Peak memory covers the entire process, including Python/Torch,
manifest validation and decoded audio, model integrity checks, and inference;
it is not a model-only allocation or a serving-memory requirement.

Actual reports are `outputs/cmu-arctic-runtime-wav2vec2-v1.json` and
`outputs/cmu-arctic-runtime-wavlm-v1.json`. They retain all per-call timings,
recording hashes/durations, posterior hashes, frame counts, exact run and encoder
provenance, software environment, and research-only flags. The recipe pins the
measurement script, manifest, source lock, and input reports. Four focused tests
cover percentile math, one-load reuse, changed-output rejection, and failure
before encoder loading for invalid bounds or corrupted head weights.

Reproduce with separate CLI processes and fresh output names:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
research/audio-head/.venv/bin/python research/audio-head/measure_runtime.py \
  research/audio-head/outputs/cmu-arctic-paired-wav2vec2-200-headseed7 \
  research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json \
  research/audio-head/outputs/my-runtime-wav2vec2.json --repeats 3
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
research/audio-head/.venv/bin/python research/audio-head/measure_runtime.py \
  research/audio-head/outputs/cmu-arctic-paired-wavlm-200-headseed7 \
  research/audio-head/outputs/cmu-arctic-four-speaker-v1/manifest.json \
  research/audio-head/outputs/my-runtime-wavlm.json --repeats 3
```

The observed encoder speeds are similar on this host. Three passes reuse the
same clips and runtime; they do not provide independent participant samples or
population latency confidence intervals. No concurrent requests, queueing,
mobile device, energy budget, deployed service, or clinical performance was
measured. Pinned upstream libraries emitted configuration/mask deprecation
warnings; both processes completed successfully without dependency changes.

After the HuBERT third-encoder fits, the same unchanged measurement script ran
the 200-step, head-seed-7 HuBERT head in one additional fresh process with
cached weights and downloads disabled. This is a supplementary measurement,
not part of the earlier two-encoder locked runtime recipe. The 72 repeated
calls had a 62.99 ms median, 78.22 ms nearest-rank p95, 0.02112 median
real-time factor, and 1,309.95 MiB whole-process peak. Runtime construction
took 1.032 s and the separately measured first inference took 67.28 ms. Every
repeated clip preserved its posterior digest. The owner-only report is
`outputs/cmu-arctic-runtime-hubert-v1.json`; the same machine, corpus, and
measurement limitations above apply. The small timing differences among
encoders are not a deployment or model-selection decision.

## Python and application CTC score parity

`check_ctc_parity.py` loads a verified checkpoint, report, manifest, and
preserved posterior export before passing the export's full phone vocabulary to
the unchanged `packages/audio-scoring/src/ctc.ts` implementation. It compares
that implementation's sequence log probability with PyTorch's float64 CTC loss
for the same frames and targets. It does not renormalize probabilities over
expected phones. Synthetic checks cover repeated phones and required blanks,
impossible paths, residual vocabulary mass, low probabilities, variable frame
lengths, and rejection of malformed inputs.

The first saved report, `outputs/cmu-arctic-ctc-parity-v1.json`, checked one
already-inspected recording under four checkpoints: 22 total cases, maximum
finite difference 4.44 × 10⁻¹⁶. The expanded
`outputs/cmu-arctic-ctc-parity-v2.json` checks three distinct held-out public
recordings (`cmu-rms-arctic_a0102`, `cmu-slt-arctic_a0201`, and
`cmu-slt-arctic_a0212`) under each of the four preserved wav2vec2/WavLM
200/800-step heads. Its 12 exports produce 24 real paths, each with the
automatic alignment target and a mathematical repeated-phone probe. Including
the fourteen synthetic or rejection cases, all 38 checks matched: 32 finite
numeric results had a maximum absolute log-probability difference of
1.42 × 10⁻¹⁴, two impossible paths returned negative infinity, and four
invalid inputs were rejected. The three recordings vary from 1.74 to 3.95
seconds and 17 to 49 automatic-alignment phones. Neither report compares model
quality or selects a head.

Reproduce the expanded check from `research/audio-head` with the existing
Python environment, cached encoders, imported public corpus, and Node.js 24.
Use a fresh `tag` on each replay because inference and reports never overwrite
earlier evidence. This runs 12 local inferences; it does not train or download:

```bash
cd research/audio-head
set -euo pipefail
tag=my-parity-01
runs=(cmu-arctic-four-speaker-200-seed7 cmu-arctic-four-speaker-800-seed7 cmu-arctic-paired-wavlm-200-headseed7 cmu-arctic-paired-wavlm-800-headseed7)
recordings=(rms:0102 slt:0201 slt:0212)
parity_args=()
for run in "${runs[@]}"; do
  for item in "${recordings[@]}"; do
    speaker="${item%%:*}"
    number="${item##*:}"
    export_path="outputs/$run/posteriors-$speaker-a$number-$tag.json"
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python run.py infer \
      "outputs/$run" "outputs/cmu-arctic-four-speaker-v1/$speaker/arctic_a$number.wav" "$export_path"
    parity_args+=(--export "outputs/$run" "outputs/cmu-arctic-four-speaker-v1/manifest.json" \
      "cmu-$speaker-arctic_a$number" "$export_path")
  done
done
.venv/bin/python check_ctc_parity.py "${parity_args[@]}" --output "outputs/$tag-report.json"
```

This verifies the CTC arithmetic on exported probabilities. It does not
validate the waveform-to-posterior model, clinical pronunciation judgments, or
calibration. The report keeps `calibrated`, `productionEligible`, and
`learnerFeedbackEligible` false and performs no model selection.

## Train-only automatic /r/ crop preflight

The [locked crop recipe](../../research/audio-head/experiments/cmu-arctic-r-crop-preflight-v1.json)
pins the existing four-speaker CMU Arctic manifest, source lock, corpus recipe,
and frozen wav2vec2 Base revision. Its runner first uses the strict manifest
loader to check **all** source WAVs, LABs, and split identities against those
pins. It then reads timed automatic alignments and runs the frozen encoder on
`r` crops from the **192 training clips only**; no calibration or test crop
reaches inference. The timed parser retains each LAB row's exact decimal end
time and uses the preceding end as its start. Crops contain the marked samples
with the documented floor/ceil boundary rule, no padding, and no extra context.
An interval shorter than the encoder's 400-sample receptive field is recorded
as excluded; other invalid geometry or changed source bytes stop the run.

On the pinned local source, 151 training clips contain 279 automatic `r`
intervals. The frozen encoder returned finite 768-wide frames for 276 crops;
three 300-sample intervals were too short and received no inference. The 276
valid crops yielded 829 frames total, with 1–11 frames per crop. The ignored,
owner-only `outputs/cmu-arctic-r-crop-preflight-v1/report.json` records each
interval's decimal times, sample bounds, disposition, frame count where valid,
source/code hashes, and research-only flags. Its SHA-256 is
`ea222f25d864644b66acaa9a3a2b3eca3b12350b884e243ee13ba69670df1218`.
The command refuses to overwrite the report and uses the verified local model
cache without downloading weights:

```sh
research/audio-head/.venv/bin/python research/audio-head/cmu_arctic_r_crop_preflight.py
```

These are **automatic adult read-speech phone timings**, not reviewed
productions or /ɹ/ error labels. This is an extraction and encoder-shape
preflight, with no fitted head, pronunciation score, model selection, or
learner-feedback implication. It does not license use of the provisional
SpeechOcean reviewer export as training data. The separate qualified target
annotation gate remains necessary.

## Public expert-rating metadata audit

`speechocean_audit.py` fetches and validates only the authors' pinned
[SpeechOcean762 metadata](https://github.com/jimbozhang/speechocean762/tree/613968e3b0b789fc33936fb5eba1973176ba7d11):
the two score files, train/test speaker and demographic maps, and README.
[OpenSLR SLR101](https://openslr.org/101/) lists the corpus under CC BY 4.0.
The nine files total 29,539,513 bytes; each has a size and SHA-256 pin. This
metadata-only audit fetched no audio. The saved research-only report is
`outputs/speechocean762-metadata-v1/audit-report-final.json`.

The audit found 5,000 scored utterances, 125 distinct speakers in each of the
author-supplied train and test splits with no overlap, 31,816 words, and 94,445
canonical phone positions. At every position the aggregate phone score matches
the mean of the five annotated rater scores. The report retains the full score
distribution, 2,653 marked insertions across raters, and 3,403 selective
low-score mispronunciation notes. These are structural properties of the
published metadata, not a model evaluation. In particular, canonical phones
and selective notes do not form complete produced-phone CTC targets; the
validator rejects fields that would present them as such.

The five raters assigned the same 0/1/2 score at 78,492 phone positions and
different scores at 15,953 positions. The score range across raters was zero
at 78,492 positions, one at 7,205, and two at 8,748. This describes agreement
over canonical positions only; it is not a reliability coefficient, clinical
threshold, or proof that the unanimous ratings are correct.

From the repository root, reproduce with a fresh destination and report name:

```sh
python3 research/audio-head/speechocean_audit.py fetch \
  research/audio-head/outputs/speechocean762-metadata-my-audit
python3 research/audio-head/speechocean_audit.py audit \
  research/audio-head/outputs/speechocean762-metadata-my-audit \
  --report research/audio-head/outputs/speechocean762-metadata-my-audit/audit-report.json
```

This is a separate rating-data path. It does not train a head, calibrate scores,
read audio, validate child SSD decisions, or enable learner feedback.

## Public /R/ rating probe with real audio

`speechocean_r_probe.py` is the first locally trained head on public speech and
expert ratings, separate from the produced-phone CTC trainer. It selects
utterances with exactly one *canonical* `R` phone and uses that position's
five-rater mean score (0–2) as a continuous rating label. It does not treat a
canonical phone as the phone the speaker actually produced. The input is the
entire mono PCM16 16 kHz utterance: there is no inferred /R/ boundary or
truncation. Frozen wav2vec2 Base frame features are mean-pooled, standardized
using training data, and fit with a linear ridge head.

The run uses the authors' speaker-disjoint train/test split: 766 training
utterances from 124 speakers and 759 test utterances from 125 speakers. A
deterministic 25-speaker subset of the training side (151 utterances) chooses
the ridge penalty from 1, 10, 100, and 1,000 by mean absolute error; the
chosen head is then refit on all 766 training utterances. Target-word and
transcript-plus-word baselines choose smoothing on the same training-side
validation partition. The test labels and simple baselines were inspected
before the recipe was fixed, so this is an **exploratory known holdout**, not
an untouched confirmatory evaluation. Eleven exact prompts occur on both sides
of the published split.

The source is the [OpenSLR SLR101 archive](https://openslr.org/101/) under its
listed CC BY 4.0 terms. The downloaded 520,810,923-byte archive has SHA-256
`876c34b828c2ebcc35ba2ff1ba5947d50e6b0162fc4a4af91db0942422b3bdd5`.
The probe verifies that archive, every selected extracted WAV against its
archive member, the pinned author metadata, and each reused feature cache's
audio hashes, encoder identity, recipe, index, and feature bytes. The archive's
older `scores.json` differs from the pinned authors' metadata only in 1,877
selective mispronunciation note fields across 961 utterances; all aggregate
ratings and prompts match. Labels come from the pinned authors' metadata. The
fresh v2 run encoded 1,525 full clips in 100.86 seconds and saved
`outputs/speechocean-r-probe-v2/{report.json,provenance.json,rating-head.npz,feature-index.json,feature-progress.json,features.npy}`.

| Held-out test predictor | MAE ↓ | MSE ↓ |
| --- | ---: | ---: |
| Frozen-audio ridge | 0.271251 | 0.164728 |
| Training-mean constant | 0.273035 | 0.166055 |
| Target-word mean | 0.265806 | 0.189093 |
| Transcript and target-word mean | 0.266540 | 0.191945 |
| Always predict 2.0 | **0.146245** | 0.184295 |

The audio head offers no useful MAE gain over the stronger simple baselines.
The always-2.0 predictor's low MAE reflects the skewed test ratings, not
pronunciation understanding; 81.29% of selected test scores equal 2. The
audio head also predicts above the allowed score range for 125 of 759 test
utterances. Its slightly lower MSE than the training-mean constant does not
establish calibration or a useful clinical decision. Child (age ≤15) and adult
(age ≥19) test partitions are descriptive corpus strata, not a child
speech-sound-disorder validation.

From the repository root, reproduce the pinned public-data run with a fresh
output directory. Hash-check the archive **before** extracting it:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_audit.py fetch \
  research/audio-head/outputs/speechocean762-metadata-v1
mkdir -p research/audio-head/outputs/speechocean762-audio-v1
curl -fL https://openslr.trmal.net/resources/101/speechocean762.tar.gz \
  -o research/audio-head/outputs/speechocean762-audio-v1/speechocean762.tar.gz
echo '876c34b828c2ebcc35ba2ff1ba5947d50e6b0162fc4a4af91db0942422b3bdd5  research/audio-head/outputs/speechocean762-audio-v1/speechocean762.tar.gz' | shasum -a 256 -c
tar -xzf research/audio-head/outputs/speechocean762-audio-v1/speechocean762.tar.gz \
  -C research/audio-head/outputs/speechocean762-audio-v1
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  research/audio-head/.venv/bin/python research/audio-head/speechocean_r_probe.py \
  --output research/audio-head/outputs/speechocean-r-probe-my-run
```

The frozen encoder must already be present in the verified local model cache
described above. All outputs remain ignored research artifacts. The saved
report's production, calibration, learner-feedback, and clinical-use eligibility
flags are false. This experiment supplies neither produced-phone labels nor a
validated /R/ score; it must not be connected to learner feedback.

## Matched WavLM rating contrast

The predeclared `experiments/speechocean-r-wavlm-v1.json` fixes a second frozen
encoder run before extraction. It preserves the exact 1,525 utterances,
speaker partitions, five-rater labels, full-clip pooling, ridge candidates,
validation metric, and baseline settings above. Only the encoder changes to
the pinned WavLM Base+ snapshot, with its official waveform preprocessing.
The original wav2vec2 report SHA-256 and head digest are fixed in the recipe;
the WavLM feature cache and output are separate. The pinned model was already
in the verified local cache, so this run made no model download. The
[WavLM model card](https://huggingface.co/microsoft/wavlm-base-plus) links
CC BY-SA 3.0 license evidence retained in the encoder identity; this is
private research, with no redistribution or production authorization inferred.

| Same known test set | MAE ↓ | MSE ↓ | Predictions above 2 / 759 |
| --- | ---: | ---: | ---: |
| Frozen wav2vec2 Base + ridge | 0.271251 | 0.164728 | 125 |
| Frozen WavLM Base+ + ridge | 0.258918 | 0.164510 | 163 |
| Target-word mean | 0.265806 | 0.189093 | — |
| Always predict 2.0 | **0.146245** | 0.184295 | 0 |

WavLM's MAE is 0.01233 lower than wav2vec2's on this already-inspected test
set, but it produces more out-of-range ratings and remains far worse than the
constant-2 MAE baseline. Its small MSE difference does not establish a
reliable encoder winner or clinical utility. Both heads are uncalibrated,
whole-utterance rating probes; neither isolates the /R/ interval. The fresh
WavLM extraction covered all 1,525 archive-verified clips in 108.48 seconds.
Independent review recomputed the fit and metrics and regenerated three
offline WavLM feature vectors bit-for-bit. The full Python suite passed 80
tests after the contrast.

With the same public audio, metadata, and verified local model cache prepared
as above, reproduce the separate WavLM run from the repository root:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  research/audio-head/.venv/bin/python research/audio-head/speechocean_r_probe.py \
  --encoder wavlm-base-plus
```

The predeclared recipe pins its output to
`research/audio-head/outputs/speechocean-r-probe-wavlm-v1/`. Its report retains
false production, calibration, clinical-use, and learner-feedback flags.

## Training-side target-location feasibility check

Before training on a presumed /R/ segment, `alignment_pilot.py` tests whether
the existing phone CTC heads can support a *canonical-prompt* alignment. The
predeclared recipe selects one utterance from each of 20 deterministic,
distinct speakers on the authors' **training** side only. All 766 eligible
training prompts map into the existing head vocabulary after stress stripping.
The pilot uses the pinned WavLM encoder and three previously trained 800-step
CMU Arctic phone heads (seeds 7, 17, and 29), then computes an exact CTC
Viterbi path constrained to each full canonical phone sequence. Unit tests
compare its result with exhaustive path enumeration, including repeated phones.
The source archive, selected WAV bytes, recipe, encoder, and head checkpoints
are verified; the final ignored report is
`outputs/speechocean-r-alignment-pilot-v1/report-v2.json`.

| Internal pilot check | Observed result |
| --- | ---: |
| Selected utterances / distinct train speakers | 20 / 20 |
| Clips with at least one predeclared support or stability flag | 9 / 20 |
| Low /R/ argmax support / low posterior / short duration / low head overlap | 8 / 6 / 8 / 4 |
| Full canonical prompt greedily decoded exactly | 0 / 20 for each head |
| Median center spread across heads | 0.01 s |
| Median minimum interval overlap (IoU) | 0.633 |

A constrained path will place an `R` somewhere even when a learner omits or
changes it. Small center spread among these heads is not independent timing
evidence, and the observed greedy errors and support flags make the locations
unsuitable as trusted training boundaries. SpeechOcean supplies no reference
phone times, so localization accuracy is **unmeasured**. This check does not
produce target crops, ratings, or feedback, and it inspects no published test
audio. Independent review replayed all 60 head/clip diagnostics and matched
the report exactly. The full local Python suite passed 86 tests afterward.

To reproduce from the repository root with a fresh ignored report path and
the same verified local assets:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  research/audio-head/.venv/bin/python research/audio-head/alignment_pilot.py \
  --output research/audio-head/outputs/speechocean-r-alignment-pilot-v1/my-replay.json
```

The useful next step is a small, independently reviewed sample with verified
produced-phone and target-time annotations, or a source that already supplies
them. Forced canonical alignment alone is not an adequate target-localization
label for another head.

### Label-free estimated-word integration check

The separate [locked preflight recipe](../../research/audio-head/experiments/speechocean-r-estimated-word-preflight-v1.json)
checks the mechanics on the existing 40 author-training clips prepared for
review. It reads their verified private frame caches, uses the three WavLM
phone heads to force the full canonical prompt, and takes the target word's
first-to-last phone-state span from the fixed seed-7 path. The other two heads
provide internal stability checks. It then mean-pools **separate wav2vec2**
contextual frames over that estimated span, an equal-length edge window wholly
outside it when available, and the full clip. The edge window is chosen by
available frame space and may contain leading or trailing silence; it is a
geometry check, not a matched acoustic comparator. All output remains in
ignored owner-only files, separate from the blinded reviewer packs.

The local run produced 40 geometric word-span hypotheses and 40 equal-length
off-word windows. Twenty-two clips had at least one /R/ support or stability
flag (20 short/long duration, 19 low argmax support, 17 low posterior, 11 low
interval overlap, 3 unstable centers; flags overlap). Its private report and
numeric vectors are under
`research/audio-head/outputs/speechocean-r-estimated-word-preflight-v1/`.
The vector archive has separate `estimatedWord`, `fullClip`, `offWord`, and
`offWordRowIndices` arrays, so an unavailable control never becomes a fabricated
acoustic vector. The report binds the sample, archive, frame caches, heads,
recipe, code, and vector hashes and retains all release and training flags
false. It contains opaque clip IDs and hashes, not ratings or source IDs.

This is **not** target-word timing validation. Forced canonical alignment can
place a word and `/R/` when they were altered or omitted. The three phone heads
share automatic-label CMU Arctic training, and Wav2vec2 positions can attend to
audio outside the pooled interval. The 40 clips were balanced by corpus rating
for a later annotation feasibility study, so their flag frequency does not
estimate population prevalence. No rating head was fitted, no accuracy was
measured, and no output was sent to reviewers. Verified target times and
produced-phone evidence remain the next dependency before interpreting a
target-localized rating comparison.

Run the preflight once in the existing offline environment:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_estimated_word_preflight.py
```

## Train-only speaker cross-validation

`speechocean_train_cv.py` reuses the two already verified frozen feature caches
and fits new ridge heads in five **outer speaker-disjoint folds** of the 766
author-training clips. Within each outer training set, a separate deterministic
speaker group selects ridge alpha and target-word baseline smoothing by MAE;
each selected head is refit on that fold's full outer training speakers before
predicting its held-out speakers. The [predeclared recipe](../../research/audio-head/experiments/speechocean-r-train-cv-v1.json)
pins source and feature-cache hashes, fold assignment, candidates, baselines,
and research-only scope. No published author-test labels or metrics enter this
cross-validation's fitting, selection, or scoring. The score-file reader now
decodes only author-train objects; the existing feature indexes are still
parsed whole before train positions are selected. A replay after this reader
change reproduced the saved out-of-fold and provenance hashes exactly. Its
test set was inspected
in earlier experiments, so this remains exploratory research rather than a
fresh independent validation.

| Pooled out-of-fold predictor (766 train clips) | MAE ↓ | MSE ↓ |
| --- | ---: | ---: |
| Frozen wav2vec2 Base + ridge | 0.294228 | 0.200687 |
| Frozen WavLM Base+ + ridge | 0.294270 | 0.202416 |
| Target-word mean | 0.311897 | 0.256113 |
| Training-fold mean | 0.323419 | 0.248021 |
| Always predict 2.0 | **0.202350** | 0.288512 |

The encoders' pooled MAEs differ by only 0.000042; WavLM is lower on three
folds and higher on two. This does not reproduce a stable encoder advantage
from the previously inspected author test. Both audio heads beat the word and
fold-mean baselines on MSE, but the constant-2 predictor remains much better
on MAE. The inner search selected alpha 1,000 and word smoothing 1 in all
five folds. Exact prompt text happened not to overlap outer training and
held-out clips in any fold; speaker grouping alone does not guarantee prompt
separation in another partition. The audio heads predict above the 0–2 range
for 130 wav2vec2 and 193 WavLM out-of-fold clips. There is no calibrated
rating, encoder winner, or clinical-use claim.

The ignored artifacts are `outputs/speechocean-r-train-cv-v1/report.json`,
`provenance.json`, and `out-of-fold.json`. The report hashes the latter two,
and the recipe binds both complete feature caches to their source WAV and
encoder identities. Independent review replayed all 766 predictions, inner
trials, selections, and fold summaries exactly. The full Python suite passed
90 tests after this experiment. With those same pinned caches available, run:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_train_cv.py
```

## Training-label agreement at /R/

The separate `speechocean_r_label_audit.py` reads only the 2,500 author-train
score objects from the pinned authors' metadata. It reconstructs each of the
five individual ratings for the same 766 exact-one-`R` clips, verifies every
published aggregate against their mean, and opens no audio or published-test
score object. Its ignored report is
`outputs/speechocean-r-label-audit-v1/report.json`.

| Train-only /R/ label pattern | Clips |
| --- | ---: |
| All five raters gave 2 | 611 |
| All five raters gave 0 | 29 |
| All five raters gave 1 | 0 |
| Raters disagreed | 126 |
| Total | 766 |

Of the 155 clips whose aggregate score is below 2, 126 have mixed rater
scores. Across all 766 clips, the five-rater score range is 0 for 640, 1 for
20, and 2 for 106. The high proportion of unanimous top scores helps explain
the constant-2 MAE baseline; the mixed lower scores make a binary
“incorrect /R/” interpretation of every below-2 mean especially fragile.
These are descriptive annotations, not a reliability coefficient, a verified
produced-phone reference, or evidence about child speech-sound disorders.
Independent review reconstructed all 3,830 selected individual ratings and
the report exactly. The full Python suite passed 96 tests after this audit.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_label_audit.py \
  --output research/audio-head/outputs/speechocean-r-label-audit-v1/my-replay.json
```

The authors also include selective `pronounced-phone` notes for very low
averaged phone scores. A separate read-only audit checks their index and
canonical phone against the same pinned author-training metadata. Among the
766 exactly-one-`R` clips, 49 from 23 speakers have an /R/-position note:
`<unk>` 15, `<DEL>` 12, `L` 8, `R*` 7, `S` 4, and one each of `Y`, `D R`, and
`AY`. Only five notes occur in child-band clips (four speakers): three `R*`
and two `<unk>`. Note presence matches aggregate /R/ score below 0.5 exactly
(49 both, 717 neither). A binary classifier for note presence would therefore
retrain the existing score threshold, not learn an independent produced-phone
target. The audit prints aggregate JSON without opening audio or writing an
artifact:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_mispronunciation_audit.py
```

The [target-interval annotation plan](r-target-annotation-plan.md) specifies
the next bounded reference-label dependency before any segment-head training.

## Blinded /R/ annotation-feasibility sample

The locked [sample recipe](../../research/audio-head/experiments/speechocean-r-annotation-sample-v1.json)
selects 40 author-**train** clips with exactly one canonical `R`: ten from
each child age ≤15/adult age ≥19 × aggregate rating 2/below 2 group, with 40
distinct speakers. The 766 candidate clips divide 301/48 child and 310/107
adult across those two rating bands. Selection uses a fixed seed and source
IDs, never model predictions or forced boundaries. The official archive hash,
pinned author metadata, and all 40 selected WAV byte hashes were verified.

`speechocean_r_annotation_sample.py` writes ignored
`outputs/speechocean-r-annotation-sample-v1/{internal-manifest.json,reviewer-queue.json,report.json}`.
The private internal manifest maps source IDs, age, ratings, and audio digests
to opaque reviewer IDs. The reviewer queue has only those IDs, canonical
prompts, target words, and zero-based positions. A local-only preparation tool
copies the same 40 public WAVs into `local-reviewer-packs/reviewer-a` and
`reviewer-b` with opaque filenames and independently keyed presentation orders.
Each pack includes the source attribution and CC BY 4.0 link. The reviewer
queues contain no source IDs, ages, ratings, model outputs, or key. Prompt text
could still allow source lookup by someone with corpus access; this is not a
promise of anonymity. The packs remain ignored local artifacts and have not
been distributed. No SLP annotations exist, and all production, calibration,
feedback, and clinical flags remain false. The generators set the sample and
pack directories to owner-only `0700` and their JSON and copied WAV files to
owner-only `0600`, including when verified existing artifacts are regenerated.
Preserve controlled permissions if any pack is later moved to an approved
reviewer workspace.

From the repository root, after preparing the pinned metadata and official
audio as above:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_annotation_sample.py
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_annotation_pack.py
```

The [annotation plan](r-target-annotation-plan.md) requires qualified reviewer
signoff on the task and agreement criteria before these packs can establish
reference target intervals for a segment model.

### Frozen-frame interval pooling preparation

`research/audio-head/target_pool.py` now provides a research-only mean pool of
frozen encoder positions whose convolutional receptive-field centers fall
inside a supplied half-open time interval. It derives the receptive field,
hop, and expected frame
count from the encoder's convolution kernels and strides, checks that the frame
tensor matches the audio duration, and rejects intervals with no frame center.
For the wav2vec2/WavLM front end, a 16 kHz, one-second clip has a 400-sample
receptive field, 320-sample hop, and 49 frames. The helper reports its selected
frame range for later audit; it does not read reviewer exports, fit a head, or
approve a label. The transformer hidden states can attend to the *whole*
utterance even at those positions, so this is not isolated /R/ audio. The
helper also has an explicitly bounded cropped-input path: floor/ceil sample
boundaries retain the marked interval with at most one boundary sample beyond
either edge and no added context window. Intervals too short for its
convolution front end are rejected. Cropped-input normalization can differ
from full-clip normalization, so a future comparison must treat preprocessing
as part of the method. The
169-test Python suite includes interval, crop, shape, dtype, finite-value, and
geometry checks.

The pinned SpeechOcean metadata contains canonical phone positions but **no
author phone timestamps**. Its prior forced-alignment pilot flagged only 9 of
20 train-side clips for internal support/stability and had no timing reference.
The existing 1,525 × 768 feature caches are full-utterance pools and cannot be
cropped afterward. A future target-position comparison needs approved reviewed
intervals, fresh frame extraction from pinned audio, a locked grouped split,
and non-acoustic and off-target controls. A claim about target-only acoustics
would require use of the cropped-input or another genuinely local extractor,
plus controls for coarticulation, interval edge error, and preprocessing. The
crop path has only been smoke-checked on an arbitrary 0.1–0.3 s interval of
one verified public author-training WAV: both cached encoders returned nine
768-wide frames from the 3,200-sample crop. This is an integration check, not
a /R/ example or a model fit. This helper does not change the
current no-feedback decision.

The private `speechocean_r_frame_cache.py` preparation command can save all
full-clip frozen frames for the same 40 author-training pilot WAVs before any
reviewed interval exists. It rechecks the locked sample, each WAV against the
official archive, and both pinned encoders offline. Each encoder gets an
ignored, owner-only frame array and index under
`outputs/speechocean-r-frozen-frames-v1/`. The index records only opaque clip
IDs, WAV hashes, sample counts, frame offsets/counts, extraction provenance,
and research-only authority flags; it contains no ratings, demographics,
prompts, reviewer labels, or blinding key. Complete caches are published
atomically and validated by hashes, geometry, shape, and finite values on reuse.
The 40 WAVs span 190.8 seconds and require about 56 MiB total for both float32
frame arrays. After code review, run from the repository root:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_frame_cache.py
```

The index includes source WAV hashes that can reidentify public clips by
comparison with the corpus. Keep the entire cache private and do not give its
index to blinded reviewers. On September 23, 2026, the local extraction
produced 9,511 frames for each pinned encoder across all 40 clips; a second
run verified the saved hashes and reused both arrays. This is preparation,
not a new model fit.

These are contextual full-clip hidden states, so pooling positions inside a
later reviewed interval does not isolate that interval's acoustics. The
cropped-input method needs separate extraction. No pilot labels have been
collected or approved for training, and this cache does not change that gate.

## Train-only probabilistic expert-rating probe

The [locked rater-CV recipe](../../research/audio-head/experiments/speechocean-r-rater-cv-v1.json)
fits a three-class softmax head for the five individual 0/1/2 ratings of each
of the same 766 author-training /R/ clips. It reuses the hash-verified frozen
wav2vec2 and WavLM features. Five outer speaker-held-out folds (124 distinct
train speakers) each use a separate inner speaker validation split to choose
L2 regularization; baselines use only the corresponding training-fold ratings.
The source score reader selectively decodes only the 766 chosen author-train
objects. The existing pinned feature indexes contain earlier cached author-test
rows and are parsed whole, but their positions do not enter this fit, model
selection, or evaluation. The previously inspected author test remains a known
exploratory set, not a fresh final cohort. These train speakers and outer-fold
assignments were also used in the earlier ridge comparison, so this softmax
experiment is iterative model development rather than a new confirmatory split.

| Out-of-fold predictor | Per-rater natural-log loss ↓ | Per-rater multiclass Brier ↓ |
| --- | ---: | ---: |
| Frozen wav2vec2 + softmax | 0.318038 | 0.170638 |
| Frozen WavLM + softmax | 0.321751 | 0.171995 |
| Training-fold class prior | 0.371679 | 0.191641 |
| Smoothed target-word prior | 0.367545 | 0.191921 |

These are **train-side out-of-fold** scores over all 3,830 rater judgments, not
an independent clinical evaluation. Both acoustic representations improve the
proper scores relative to these baselines, but their difference is small and
does not establish an encoder winner. The five ratings on a clip are related
judgments, not five independent patients or objective produced-phone labels.
Whole-utterance features may capture speaker/accent or recording conditions
without localizing /R/. Seven of ten outer softmax fits reached the
predeclared 80-iteration cap. The separately locked
[v2 optimizer-sensitivity recipe](../../research/audio-head/experiments/speechocean-r-rater-cv-convergence-v2.json)
raised only that limit to 400, keeping folds, candidates, objective, sources,
and baselines fixed. All ten outer fits stopped below the new cap; one of
thirty inner trials still hit it (an unselected WavLM α=0.001 trial). Every
selected setting stayed the same. Pooled log loss changed by only +0.00000158
for wav2vec2 and +0.00000014 for WavLM; baseline scores were identical. This
supports numerical stability of the selected outer results, but stopping
below a cap alone does not prove convergence, and this remains an exploratory
sensitivity check rather than independent validation. Valid three-class
probabilities keep every expected rating within 0–2; that mathematical bound
is not calibration.

Ignored artifacts are `outputs/speechocean-r-rater-cv-v1/{report.json,provenance.json,out-of-fold.json,outer-fold-heads.npz}`;
the v2 counterparts are under `outputs/speechocean-r-rater-cv-convergence-v2/`.
An independent reviewer replayed every out-of-fold prediction, fit choice,
baseline, and proper score for both versions, with no blocking findings. The
full Python suite passed 108 tests after v2.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_rater_cv.py
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_rater_cv.py --experiment v2
```

This head remains research-only. Independently reviewed target intervals are
not yet available for segment training. The run does not establish diagnostic
validity for children with speech-sound disorders or enable learner feedback.

### Speaker and target-word purge stress test

Exact prompted sentences are unique in the 766 selected author-training clips,
so the existing speaker folds already hold out each exact prompt. Target words
repeat, however. The [locked stress-test recipe](../../research/audio-head/experiments/speechocean-r-speaker-word-purged-v1.json)
keeps those same five speaker holdouts and removes from each outer fit every
clip whose canonical `/R/` target word occurs in that fold's holdout. An
analogous purge separates inner fit and validation words before selecting the
same L2 candidates. The only baseline is a fit-fold class prior; a target-word
baseline would reduce to that prior when all holdout words are unseen. The
reader still verifies pinned author-training features, WAVs, and five-rater
labels. No author-test row is fit or scored.

| Train-side out-of-fold predictor | Per-rater log loss ↓ | Per-rater Brier ↓ |
| --- | ---: | ---: |
| Frozen WavLM + softmax | 0.345606 | 0.182765 |
| Frozen wav2vec2 + softmax | 0.350184 | 0.185241 |
| Fit-fold class prior | 0.373878 | 0.191899 |

All 766 clips receive one held-out prediction. The outer fits shrink to
264–318 clips, with only 7–20 class-1 rater judgments per fit; the inner fits
have 175–203 clips and 6 of 30 inner softmax fits reach the 400-iteration
cap. The acoustic heads improve on the prior within this particular stress
test, but its tiny, skewed fits make the encoder ordering unstable evidence.
Purging changes training size and composition, so comparing these losses with
the earlier speaker-only scores does **not** isolate reliance on target words.
Whole-clip states can still encode other prompt and capture cues. This is
iterative train-side sensitivity analysis, not independent target-production
validation, a clinical model comparison, or permission to enable feedback.
The ignored report, out-of-fold predictions, provenance, and fold heads are
owner-only under `outputs/speechocean-r-speaker-word-purged-v1/`.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_speaker_word_purged.py
```

## Train-only word-and-age categorical negative control

The [locked categorical recipe](../../research/audio-head/experiments/speechocean-r-word-age-negative-control-v1.json)
tests whether the saved acoustic-head gain persists against a stronger
non-acoustic corpus baseline. It uses only each clip's canonical target word,
the speaker's author-training age band, and the five expert ratings. The exact
766 author-training IDs, pinned score files and age map, and the existing five
outer speaker folds are checked against the SHA-256-pinned v2 report and
out-of-fold predictions. No audio, feature cache, author-test score object, or
author-test inference is opened for this run.

For each outer fold, a global class prior uses one pseudocount per class.
Separate word and age priors shrink toward it, and each word×age cell shrinks
toward an equal blend of those two priors. A predeclared 3×3×3 smoothing grid
is selected by per-rater log loss using only inner training speakers. Unseen
cells use the same backoff; 260 held-out clips have no matching word×age cell
in their outer training fold. All five folds selected the largest cell
smoothing candidate (100), which is a reason to treat this as one bounded
categorical control rather than an optimized ceiling for metadata predictors.

| Matched train-side OOF predictor | Per-rater log loss ↓ | Per-rater multiclass Brier ↓ |
| --- | ---: | ---: |
| Word + corpus age band | 0.348362 | 0.185346 |
| Saved v2 wav2vec2 head | 0.318040 | 0.170639 |
| Saved v2 WavLM head | 0.321751 | 0.171995 |
| Saved v2 training-fold prior | 0.371679 | 0.191641 |
| Saved v2 target-word prior | 0.367545 | 0.191921 |

On identical rows and folds, the acoustic heads retain pooled log-loss gains
of 0.030322 (wav2vec2) and 0.026611 (WavLM) over the word-plus-age control;
their Brier gains are 0.014707 and 0.013351. The categorical baseline also
improves on the saved target-word and fold-prior baselines. These differences
are descriptive and have no uncertainty interval here. Corpus age and prompt
word probe dataset confounding; they are **not** proposed inference inputs or
clinically appropriate attributes. The five judgments are subjective, and
301 of 349 child-band clips are unanimously top rated. Neither the pooled
gain nor this control isolates an acoustic /R/ cue or supports child clinical
use.

The ignored `outputs/speechocean-r-word-age-negative-control-v1/` directory
contains the paired out-of-fold probabilities, fold selections, report, and
source-code/metadata SHA-256 provenance. The runner is deliberately one-shot:
it refuses to overwrite that existing ignored directory in this workspace.
Run the following command only in a fresh research workspace with the pinned
source artifacts prepared; inspect the saved `report.json` here instead.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_word_age_negative_control.py
```

A separate [locked paired speaker bootstrap](../../research/audio-head/experiments/speechocean-r-word-age-paired-bootstrap-v1.json)
resamples all 124 speakers 2,000 times while keeping each speaker's five
ratings, acoustic predictions, and word-plus-age prediction together. On
**fixed, already-inspected OOF predictions**, wav2vec2 minus word-plus-age
log loss is −0.03032 with a 95% percentile interval [−0.05504, −0.00459].
WavLM minus word-plus-age is −0.02661 [−0.05501, +0.00267], crossing zero.
These exploratory intervals omit retraining and smoothing-selection
uncertainty, and do not establish an /ɹ/ production cue or clinical validity.
The ignored report is
`outputs/speechocean-r-word-age-paired-bootstrap-v1/report.json`.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_word_age_paired_bootstrap.py
```

## Train-only duration and RMS confound probe

The [locked capture-feature recipe](../../research/audio-head/experiments/speechocean-r-capture-confound-v1.json)
tests whether simple full-clip properties account for part of the acoustic
head's rating association. It uses exactly the same 766 author-training clips,
124 speakers, five saved outer speaker folds, and five rater scores per clip.
The selected WAVs were checked against the SHA-256-pinned official archive.
Duration is the PCM frame count divided by 16,000; RMS uses every PCM sample,
including silence, after division by 32,768. No target interval, pretrained
encoder, author-test label, or author-test inference enters this fit.

Two paired linear softmax controls use the canonical word and corpus age band;
the second adds duration and RMS. Each fold builds its word vocabulary and
feature standardization on fit speakers only. A fixed three-value L2 grid is
selected by per-rater log loss on inner training speakers and refitted on all
outer-training speakers. All 30 inner fits and ten outer fits finished below
the 400-iteration optimizer cap. The previous word-plus-age categorical OOF
and saved acoustic OOF predictions are compared on the identical rows.

| Same train-side OOF rows | Per-rater log loss ↓ | Per-rater Brier ↓ |
| --- | ---: | ---: |
| Word + age, paired softmax | 0.369881 | 0.193606 |
| Word + age + duration + RMS, paired softmax | 0.331949 | 0.174185 |
| Earlier word + age categorical control | 0.348362 | 0.185346 |
| Saved wav2vec2 head | 0.318040 | 0.170639 |
| Saved WavLM head | 0.321751 | 0.171995 |

Adding duration and RMS improves the paired softmax's log loss by 0.037932,
and its score is below the earlier categorical word-plus-age control by
0.016413. The earlier control uses a different model class, so the paired
softmax difference is the cleaner test of the two added columns. The new
control still scores above wav2vec2 by 0.013909 and WavLM by 0.010198 in
pooled log loss. Each of the five outer folds improved over its paired
word-plus-age softmax, but these descriptive differences have no independent
test cohort or refitting uncertainty interval. Duration and full-file RMS
can reflect prompt, speaker, speech content, and capture conditions; they do
not isolate an /ɹ/ cue. Corpus age is a confound probe, not a proposed product
input. Five subjective ratings remain neither target-time nor verified
produced-phone labels, and the author-test partition remains known from prior
work. This experiment provides no clinical child validation or learner-feedback
authority.

Ignored outputs in `outputs/speechocean-r-capture-confound-v1/` include every
outer fold's settings and metrics, paired out-of-fold probabilities, exact
selected WAV hashes and capture features, saved fold heads, and source/recipe
hashes. The command is one-shot and refuses to overwrite that result. The
recipe was SHA-256-pinned before model fitting; a fresh research workspace
with the existing verified source artifacts can reproduce it with:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_capture_confound.py
```

## Incremental frozen audio beyond the capture control

The [locked incremental-audio recipe](../../research/audio-head/experiments/speechocean-r-incremental-audio-v1.json)
asks whether frozen full-clip wav2vec2 or WavLM features add information beyond
the canonical target word, corpus age band, full-clip duration, and full-clip
RMS. The recipe SHA-256 (`e24a8c70cf1a909eac24c4c3bf453b2981a6f0ec00444f39767a8d1185a4bb3a`)
was fixed before this run. It pins the 766 author-training clip IDs, 124 speakers,
official archive and metadata hashes, both 768-column feature caches, and the
capture-feature evidence. The loader independently rechecks source rows, WAV
hashes, five rater counts, target words, age bands, and saved fold assignments.
It performs no author-test inference.

Five model types receive new paired fits: the capture control, audio alone for
each encoder, and the capture columns plus each encoder. The same five outer
speaker holdouts and inner speaker selections are used throughout. Every inner
fit learns its word vocabulary and column means/scales only from its fit rows;
each model chooses among L2 values 0.001, 0.01, and 0.1 by inner per-rater log
loss, then refits on all outer-training speakers. The pooled scores cover the
same 766 held-out clips and 3,830 subjective ratings.
Canonical target words can repeat across these speaker folds; this experiment
does not measure performance on unseen target words.

| Fresh train-side out-of-fold fit | Per-rater log loss ↓ | Per-rater Brier ↓ |
| --- | ---: | ---: |
| Word + age + duration + RMS | 0.331949 | 0.174185 |
| wav2vec2 audio alone | 0.318040 | 0.170639 |
| wav2vec2 audio + capture control | 0.313094 | 0.167497 |
| WavLM audio alone | 0.321751 | 0.171995 |
| WavLM audio + capture control | 0.310753 | 0.165055 |

Adding wav2vec2 to the capture control changes pooled log loss by −0.018855
and Brier by −0.006688; adding WavLM changes them by −0.021196 and −0.009130.
Negative values favor the combined model. The wav2vec2 combined fit improves
three of five folds by log loss, and the WavLM combined fit improves four of
five. Six unselected inner candidates reached the 400-iteration optimizer cap;
all selected inner candidates and all outer fits finished below it. The fresh
capture-only and audio-only probabilities match their earlier saved paired OOF
predictions exactly, row by row.

These are exploratory associations on previously inspected author-training
folds, not independent validation or evidence of a target-localized /ɹ/ cue.
The ratings are subjective and provide no /R/ timing or verified produced-phone
labels. Full-clip features can retain prompt, speaker, speech-content, and
recording cues beyond duration and RMS; the four control inputs cannot remove
every confound. The point differences omit refitting and new-corpus uncertainty,
and no representative clinical child cohort is evaluated. The result supplies
no calibration or learner-feedback authority.

Ignored private outputs under `outputs/speechocean-r-incremental-audio-v1/`
contain the full fold trials, OOF probabilities, saved heads, and source hashes.
The directory has mode 0700 and its files mode 0600. The command refuses to
overwrite a completed run:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_incremental_audio.py
```

The v1 runner checked upstream feature-recipe fields and validated the cache
files against hashes read from that recipe, but did not SHA-256-pin the upstream
recipe file itself. Its predeclaration therefore did not cryptographically
freeze those cache hashes. No source-row or cache mismatch was observed. The
word-purged run below closes that provenance gap by checking the upstream
recipe's SHA-256 before loading either cache.

### Incremental audio with unseen speakers and target words

The separate [locked word-purged recipe](../../research/audio-head/experiments/speechocean-r-incremental-audio-word-purged-v1.json)
reuses the same 766 author-training clips, 124 speakers, five speaker holdouts,
frozen feature caches, and pinned capture values. It pins the upstream feature
recipe, capture recipe and evidence, and existing word-purge recipe and report
by SHA-256. For each outer fold, it removes from the fit every clip whose exact
canonical `/R/` target word appears in that fold's holdout. It then chooses
inner validation speakers from the retained fit and removes inner-fit clips
sharing their target words. Every holdout clip still receives one prediction.
No author-test row is fit or scored.

Fresh capture-only, wav2vec2/WavLM audio-only, and combined softmax heads use
identical purged splits. Each fit learns its word vocabulary and column
standardization on its own fit rows, and selects L2 by inner per-rater log loss.
The outer fits retain 264–318 clips; inner fits retain 175–203. Each outer fit
contains only 7–20 class-1 rater judgments. Fifteen unselected inner candidates
reach the 400-iteration cap; no selected inner or outer fit does. The audio-only
probabilities exactly match the previous word-purged acoustic OOF predictions
row by row.

| Word-purged train-side OOF fit | Per-rater log loss ↓ | Per-rater Brier ↓ |
| --- | ---: | ---: |
| Fit-word vocabulary + age + duration + RMS | 0.360987 | 0.181370 |
| wav2vec2 audio alone | 0.350184 | 0.185241 |
| wav2vec2 audio + capture control | 0.334255 | 0.177542 |
| WavLM audio alone | 0.345606 | 0.182765 |
| WavLM audio + capture control | 0.332117 | 0.173028 |

Relative to the paired capture-only fit, the wav2vec2 combined fit changes
pooled log loss by −0.026732 and Brier by −0.003828; the WavLM combined fit
changes them by −0.028870 and −0.008342. Negative values favor the combined
head. Each combined fit improves log loss in four of five folds. The fixed-OOF
speaker intervals below quantify one source of variation; neither run has
independent validation.
Every held-out target word is unseen in the corresponding fit, so the capture
head's word indicators are zero at evaluation; this is not an adjustment for
known holdout word identity.
Word purging removes about half the candidate fit clips and changes their class
mix, so differences from speaker-only scores do not isolate dependence on
target words or identify a model winner. Full-clip features can still carry
other prompt, speaker, speech-content, and capture cues. The five subjective
ratings provide no /R/ timing or verified produced-phone label, and these
previously inspected training folds cannot establish clinical child validity
or authorize learner feedback.

The ignored `outputs/speechocean-r-incremental-audio-word-purged-v1/` report,
OOF predictions, heads, and provenance are owner-only (0700 directory, 0600
files). This one-shot command refuses to overwrite the locked result:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_incremental_audio_word_purged.py
```

### Paired speaker uncertainty for both incremental runs

The [locked paired-bootstrap recipe](../../research/audio-head/experiments/speechocean-r-incremental-audio-paired-bootstrap-v1.json)
pins both incremental reports and OOF files by SHA-256. It verifies the exact
766 clip IDs, 124 speakers, five-score vectors, fold assignments, probability
sums, and saved pooled and fold metrics before analysis. It then draws all 124
speakers with replacement 10,000 times, keeping every clip and its five
ratings together. Each draw uses equal clip weighting and compares the same
held-out clips. Negative combined-minus-capture differences favor adding the
frozen audio columns.

| Fixed OOF run | Added audio | Log-loss difference [95% speaker interval] | Brier difference [95% speaker interval] |
| --- | --- | ---: | ---: |
| Speaker held out | wav2vec2 | −0.01886 [−0.03849, +0.00061] | −0.00669 [−0.01628, +0.00210] |
| Speaker held out | WavLM | −0.02120 [−0.04642, +0.00279] | −0.00913 [−0.02228, +0.00298] |
| Speaker and word purged | wav2vec2 | −0.02673 [−0.06410, +0.00550] | −0.00383 [−0.01930, +0.01049] |
| Speaker and word purged | WavLM | −0.02887 [−0.06334, +0.00115] | −0.00834 [−0.02299, +0.00403] |

All eight descriptive intervals cross zero. This does not establish a reliable
incremental gain or an encoder winner. The speakers and folds were already
inspected, and the bootstrap holds fitted heads and L2 selections fixed. Its
intervals omit retraining, selection, and new-corpus uncertainty. The purged
fits are especially small and class-skewed. Neither interval set identifies an
/ɹ/ production cue, substitutes for a representative clinical child cohort,
or supports calibration or learner feedback.

The ignored `outputs/speechocean-r-incremental-audio-paired-bootstrap-v1/report.json`
records the exact source and draw hashes, point differences, percentile
intervals, and each fold's paired differences. Its directory is 0700 and file
0600. The command refuses to overwrite the locked result:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_incremental_audio_paired_bootstrap.py
```

A separate [locked paired bootstrap](../../research/audio-head/experiments/speechocean-r-capture-paired-bootstrap-v1.json)
joins that fixed capture-control OOF to the saved acoustic OOF by exact clip ID,
speaker, fold, and five-rater count. It resamples all 124 whole speakers 2,000
times with each speaker's clips kept together. Positive log-loss differences
below favor the acoustic head:

| Fixed OOF difference: capture control minus | Point difference | Descriptive 95% percentile interval |
| --- | ---: | ---: |
| wav2vec2 | +0.01391 | [−0.01060, +0.03782] |
| WavLM | +0.01020 | [−0.01850, +0.03888] |

Both intervals cross zero. They describe variation from resampling speakers
while keeping predictions and fitted settings fixed; they omit retraining,
model-selection, and corpus-sampling uncertainty. These speakers and folds
were already inspected during development, and the author test is known from
earlier work. The intervals cannot select an encoder, show a target-specific
/ɹ/ cue, or establish child clinical validity. The existing
[rater-disagreement diagnostic](#rater-disagreement-diagnostics-on-saved-predictions)
also shows that pooled performance is not a reliable description of the 126
mixed-rater clips.

The ignored `outputs/speechocean-r-capture-paired-bootstrap-v1/report.json`
records exact source hashes, bootstrap seed and draw hash, point differences,
and intervals. This one-shot command does no model fitting or test inference:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_capture_paired_bootstrap.py
```

### Capture control by corpus age band

The [locked age-slice recipe](../../research/audio-head/experiments/speechocean-r-capture-age-diagnostics-v1.json)
joins the same pinned capture-control and acoustic out-of-fold predictions to
the pinned author-training age map. It pairs each clip by ID, speaker, outer
fold, and five ratings, then recomputes log loss and Brier score. The child
band (age ≤15) contains 349 clips from 57 speakers; the adult band (age ≥19)
contains 417 clips from 67 speakers. The two slices reconstruct all three
pinned pooled scores. No model is fit or selected in this diagnostic.

| Fixed train-side OOF age band | Capture log loss / Brier ↓ | Wav2vec2 log loss / Brier ↓ | WavLM log loss / Brier ↓ |
| --- | ---: | ---: | ---: |
| Child | 0.231886 / 0.094838 | 0.214430 / 0.092838 | 0.255640 / 0.112011 |
| Adult | 0.415695 / 0.240593 | 0.404754 / 0.235754 | 0.377081 / 0.222198 |

A paired 2,000-draw bootstrap resamples whole speakers **within** each age
band while retaining their clips, ratings, and all three predictions together.
The table reports capture-control minus acoustic log loss; positive values
favor the acoustic head.

| Age band | Comparison | Difference | Descriptive 95% speaker percentile interval |
| --- | --- | ---: | ---: |
| Child | Capture − wav2vec2 | +0.01746 | [−0.00406, +0.04301] |
| Child | Capture − WavLM | −0.02375 | [−0.05435, +0.00390] |
| Adult | Capture − wav2vec2 | +0.01094 | [−0.02692, +0.04862] |
| Adult | Capture − WavLM | +0.03861 | [−0.00759, +0.08390] |

All four log-loss intervals cross zero. The report also contains fixed-score
Brier differences and intervals. This is an exploratory split of already
inspected author-training predictions: resampling omits refitting, model
selection, and new-corpus uncertainty. The public child band is heavily
top-scored and is not a speech-sound-disorder reference cohort. Full-clip
duration, RMS, and pooled acoustic embeddings do not localize /ɹ/ or establish
pronunciation correctness. The ignored report is
`outputs/speechocean-r-capture-age-diagnostics-v1/report.json`.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_capture_age_diagnostics.py
```

## Train-only rating-permutation control

The [locked negative-control recipe](../../research/audio-head/experiments/speechocean-r-rater-negative-control-v1.json)
tests whether the v2 result depends on the audio-feature/rating pairing. Within
each of the five author-train outer folds, the script rotates intact five-score
vectors between speakers with the same number of clips, matching each speaker's
clips by sorted source ID. It then reruns the full nested selection and all
four predictors, including priors recomputed from the permuted training fold.
Every fold retains its exact clip count, rater-score distribution, and speaker
assignment. The reference recipe, report, feature caches, and source archive
are SHA-256 pinned; the author test is not scored.

| Train-side out-of-fold predictor | Original v2 log loss ↓ | Permuted log loss ↓ |
| --- | ---: | ---: |
| Frozen wav2vec2 + softmax | 0.318040 | 0.418762 |
| Frozen WavLM + softmax | 0.321751 | 0.438817 |
| Training-fold class prior | 0.371679 | 0.371679 |
| Smoothed target-word prior | 0.367545 | 0.386671 |

The fixed permutation moved source IDs for 690 of 766 clips across 111 of 124
speaker blocks. Thirteen singleton strata left 76 clips paired as before.
Because many clips share the same unanimous rating, only 233 clips received a
different five-score vector. Both acoustic heads lost their advantage over the
training-fold prior under this control. This is one deterministic sanity check,
not a permutation distribution, p-value, evidence of a causal /R/ cue, or
external validation. It also breaks prompt/feature associations, so it cannot
separate pronunciation information from prompt or recording cues. The ignored
report, provenance, out-of-fold predictions, and fold heads are under
`outputs/speechocean-r-rater-negative-control-v1/`.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_rater_negative_control.py
```

## Twenty train-only rating permutations

The [locked sensitivity recipe](../../research/audio-head/experiments/speechocean-r-rater-permutation-sensitivity-v1.json)
predeclares 20 distinct seeds after the single control above was inspected.
Each run uses that control's intact five-rating speaker-block rotation within
the reference outer fold and equal clip-count stratum. It repeats the full v2
nested model and baseline selection on the permuted author-train labels. Source
archive, selected IDs, feature caches, code, reference recipe/report, and the
earlier control are SHA-256 pinned. No author-test score or test inference is
used. The ignored [report](../../research/audio-head/outputs/speechocean-r-rater-permutation-sensitivity-v1/report.json)
keeps every seed, mapping hash, count of rating vectors changed, selected fold
settings, and pooled log loss and Brier score for all four predictors; it
does not save 20 redundant model-head and prediction arrays.

| Train-side predictor | Unchanged log loss ↓ | Permuted log loss range | Permuted median | Permutations below unchanged |
| --- | ---: | ---: | ---: | ---: |
| Frozen wav2vec2 + softmax | 0.3180 | 0.3926–0.4627 | 0.4234 | 0/20 |
| Frozen WavLM + softmax | 0.3218 | 0.4248–0.4813 | 0.4463 | 0/20 |
| Training-fold class prior | 0.3717 | 0.3717–0.3717 | 0.3717 | 0/20 |
| Smoothed target-word prior | 0.3675 | 0.3794–0.3978 | 0.3825 | 0/20 |

The acoustic heads also had higher Brier scores in all 20 permutations. Each
mapping moved source IDs for 690 clips, but only 228–236 clips received a
different five-rating vector, because many vectors are identical. The
training-fold prior is invariant within floating-point tolerance because each
outer fold keeps its rating distribution. The fixed unchanged result ranks
below all 20 permuted acoustic losses, but **this is an exploratory rank, not a
confirmatory p-value**: the unchanged result and first control were already
inspected before these seeds were fixed. The permutation also disrupts prompt
and recording associations, so it does not isolate a pronunciation cue.
No target-time, child clinical reference, calibrated feedback, or external
validation follows from this train-only diagnostic.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_rater_permutation_sensitivity.py
```

## Rater-disagreement diagnostics on saved predictions

The locked [diagnostic recipe](../../research/audio-head/experiments/speechocean-r-oof-diagnostics-v1.json)
reads only the pinned v2 **train-side out-of-fold predictions**; it performs no
new fit and uses no published author-test labels. It separates 611 clips where
all five raters chose 2, 29 where all chose 0, and 126 with mixed ratings.
There are no unanimous-1 clips. The wav2vec2 head's per-rater log loss is
0.0831 on unanimous-2 clips versus 0.1128 for the training-fold prior; 1.6999
versus 2.3482 on unanimous-0 clips; and 1.1394 versus 1.1719 on mixed clips.
That last, small difference is a warning against treating the overall gain as
reliable detection of a disputed /R/ production. The WavLM head's mixed-clip
log loss is 1.2055, worse than the prior's 1.1719.

A paired 2,000-resample bootstrap draws the 124 training speakers with
replacement, keeping every clip and its five ratings together. For natural-log
loss differences (first minus second), the fixed-prediction 95% percentile
intervals are wav2vec2 minus train prior −0.05364 [−0.07979, −0.03188],
wav2vec2 minus target-word −0.04951 [−0.07454, −0.02684], and WavLM minus
wav2vec2 +0.00371 [−0.01736, +0.02796]. These intervals are **descriptive
for saved out-of-fold predictions**: they omit retraining and hyperparameter
selection uncertainty, and the folds were already used during model
development. They do not establish a model winner or clinical reliability.
An independent reviewer recomputed all 6,000 paired differences and group
metrics exactly. Ignored outputs live in
`outputs/speechocean-r-oof-diagnostics-v1/`; the full Python suite passed 112
tests after this diagnostic.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_oof_diagnostics.py
```

## Corpus age slices of saved /R/ rating predictions

The separate [locked age-slice recipe](../../research/audio-head/experiments/speechocean-r-age-diagnostics-v1.json)
joins the saved **author-train** speaker-held-out predictions to the pinned
author-train age map. It refits nothing and never reads published author-test
ratings. The child band has 349 clips from 57 speakers (age ≤15), including
301 unanimously rated 2 and one unanimously rated 0. The adult band has 417
clips from 67 speakers (age ≥19), including 310 unanimously rated 2 and 28
unanimously rated 0.

| Train-side OOF slice | Wav2vec2 log loss ↓ | WavLM log loss ↓ | Fold prior log loss ↓ |
| --- | ---: | ---: | ---: |
| Child band | 0.2144 | 0.2556 | 0.2521 |
| Adult band | 0.4048 | 0.3771 | 0.4717 |

The child WavLM slice is slightly worse than its fold prior despite the pooled
gain, while wav2vec2 is below the prior in both bands. This is descriptive of
one public corpus and the same exploratory OOF fits; no child speech-sound-
disorder reference, target-time label, clinical threshold, or model selection
follows from it. The report also saves Brier scores and
checks that clip-weighted age slices reconstruct every pooled source metric.
Ignored output is `outputs/speechocean-r-age-diagnostics-v1/report.json`.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_age_diagnostics.py
```

A separate [locked age-band bootstrap](../../research/audio-head/experiments/speechocean-r-age-bootstrap-v1.json)
resamples speakers **within each band** 2,000 times, retaining all of a
speaker's clips, five ratings, and saved predictions together. It compares
the fixed acoustic OOF log loss to the fixed training-fold prior; negative
differences favor the acoustic head.

| Age band | Fixed OOF comparison | Difference | 95% speaker percentile interval |
| --- | --- | ---: | ---: |
| Child | Wav2vec2 − prior | −0.0377 | [−0.0512, −0.0242] |
| Child | WavLM − prior | +0.0035 | [−0.0305, +0.0433] |
| Adult | Wav2vec2 − prior | −0.0670 | [−0.1151, −0.0264] |
| Adult | WavLM − prior | −0.0947 | [−0.1499, −0.0477] |

These are exploratory intervals on predictions inspected during model
development. They omit retraining and model-selection uncertainty; they do
not quantify performance in a clinical child population. The child band's
301/349 unanimous top ratings also limit what this comparison can say about
error detection. Ignored output is
`outputs/speechocean-r-age-bootstrap-v1/report.json`.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_age_bootstrap.py
```

## Directional age transfer within author training

The separate [locked transfer recipe](../../research/audio-head/experiments/speechocean-r-cross-age-transfer-v1.json)
fits the fixed α=0.1 three-class head on one corpus age band and evaluates it
on the other, then reverses direction. It uses the same two frozen full-clip
feature caches, five ratings per clip, and 400-iteration optimizer as the
train-side final fit. The exact 349 child clips/57 speakers and 417 adult
clips/67 speakers are pinned by ID and speaker digests. Each direction's
baseline is the three-class rating prior computed **only from its training
band** with one pseudocount per class. The cached feature-index JSON is parsed
for integrity, but only author-train features and score objects enter the
experiment; no author-test inference or setting selection is performed.

| Train → evaluate | Encoder | Head log loss ↓ | Source prior log loss ↓ | Head Brier ↓ | Source prior Brier ↓ |
| --- | --- | ---: | ---: | ---: | ---: |
| Adult → child | Wav2vec2 | 0.2510 | 0.2949 | 0.1074 | 0.1171 |
| Adult → child | WavLM | 0.2922 | 0.2949 | 0.1331 | 0.1171 |
| Child → adult | Wav2vec2 | 0.6707 | 0.5664 | 0.2892 | 0.2870 |
| Child → adult | WavLM | 0.7020 | 0.5664 | 0.2984 | 0.2870 |

All four fits stopped below the 400-iteration cap (118, 103, 64, and 49
iterations in table order). Adult-trained wav2vec2 improves log loss on the
child band against its source prior, whereas both child-trained heads lose
substantially to their source prior on the adult band. WavLM's small adult →
child log-loss gain accompanies worse Brier. The child training band is 301/349
unanimous-2 clips, making transfer from it especially sensitive to its rating
distribution. This exploratory public-corpus check has no uncertainty interval,
independent clinical cohort, produced-phone label, or /R/ timing. Age, word,
speaker, and recording differences can all affect it. The ignored
`outputs/speechocean-r-cross-age-transfer-v1/report.json` records source,
cache, recipe, cohort, and code hashes along with all metrics and fit details.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_cross_age_transfer.py
```

## Fixed research-only rater head fit on author training

The [locked final-fit recipe](../../research/audio-head/experiments/speechocean-r-rater-final-fit-v1.json)
uses the two existing frozen feature caches and all 766 selected author-train
clips (124 speakers, 3,830 individual rater judgments). All five outer folds
of the earlier train-side converged CV selected L2 α=0.1 for both encoders, so
this run fixes that value and performs no further search. It reuses the same
float64 linear softmax trainer and 400-iteration cap. The source archive,
selected IDs, metadata, feature caches, CV selection report, trainer code, and
recipe have SHA-256 provenance in the ignored final-fit artifacts. Existing
feature-index JSON includes cached author-test rows and is parsed whole for
integrity, but only author-train positions are loaded into the fit; published
test score objects and test-set inference are not used.

Both fixed fits stopped below the optimizer cap: wav2vec2 took 77 iterations
(final gradient norm 1.92×10⁻⁵), and WavLM took 75 (7.17×10⁻⁶). Training-input
probabilities formed valid three-class simplexes, giving expected ratings
within 0–2. These checks establish finite saved weights and numerical bounds,
not convergence proof, calibration, held-out performance, or /R/ localization.
The weights are private research artifacts under
`research/audio-head/outputs/speechocean-r-rater-final-fit-v1/`:
`heads.npz`, `provenance.json`, and `report.json`. The run does not authorize
release, clinical interpretation, or learner feedback. WavLM's source-license
evidence remains in the cache provenance and limits it to private engineering.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_rater_final_fit.py
```

## Offline replay of the final /R/ rater heads

`research/audio-head/speechocean_r_local_infer.py` replays one saved final-fit head
on an **exact public SpeechOcean author-training WAV**. It verifies the locked
report, provenance, NPZ digest and shapes, current trainer/final-fit code hashes,
encoder identity and feature-index
digest, and the WAV's recorded SHA-256. It loads the pinned frozen encoder from
the local cache with downloads disabled, applies the same mono PCM16 decoding,
full-clip frame mean, float32 feature precision, train-set standardization, and
three-class softmax as the fit. The selected author-test partition and arbitrary
local recordings are rejected, so this command cannot ingest patient media or
create another author-test evaluation.

For example, after the public corpus and final-fit artifacts have been prepared:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_local_infer.py \
  research/audio-head/outputs/speechocean762-audio-v1/speechocean762/WAVE/SPEAKER0001/000010011.WAV \
  --encoder wav2vec2-base
```

`--encoder wavlm-base-plus` replays the other fitted head. The JSON prints
artifact identities and **uncalibrated probabilities for
subjective corpus rating classes 0, 1, and 2**. These are whole-clip judgments;
they do not locate /R/, assess a produced phone, or establish pronunciation
correctness. All release and clinical eligibility flags remain false. The
example clip is in the fit set, so its output is an artifact replay and carries
no held-out performance evidence. Both encoders' real replays of public clip
`000010011.WAV` matched the probabilities from their saved feature rows within
1×10⁻⁶ absolute probability, allowing tiny CPU math order differences. Focused
tests also reject a different path, the published author-test partition,
corrupted final artifacts, and a mismatched feature index. No network access or
new model training is needed for replay.

## Third frozen encoder: HuBERT Base

The locked `experiments/cmu-arctic-hubert-third-v1.json` adds the official
[HuBERT Base LS960 checkpoint](https://huggingface.co/facebook/hubert-base-ls960)
at revision `dba3bb02fda4248b6e082697eee756de8fe8aa8a` to the existing
four-speaker CMU Arctic comparison. Its model card carries an Apache-2.0 tag;
the exact card and three model artifacts are pinned by SHA-256 and size. The
snapshot has no separate license file, so the tag is recorded as source evidence
for private engineering, not product or redistribution clearance. The frozen
`HubertModel` uses the checkpoint's 16 kHz feature extractor, which normalizes
each clip and does not return an attention mask. This preprocessing difference
from the other encoders is retained. The adapter uses local files only, no
remote code, and a 768-wide linear head; it exports the same uncalibrated
posterior contract as the earlier heads.

The runner verifies the pinned manifest, source lock, model card, training code,
dependency lock, recipe, and all twelve earlier wav2vec2/WavLM runs before
fitting. It then trains six HuBERT heads with global seed 7, independent head
seeds 7/17/29, learning rate 0.01, and fixed 200/800-step budgets. Each fit
uses the same 192 training, 12 calibration, and 12 test recordings and the same
automatic phone alignment labels. All 18 runs have matching partition digests;
within each head seed, their initial linear weights match exactly across all
three encoders and both budgets. No held-out result chooses a head or budget.

```sh
research/audio-head/.venv/bin/python research/audio-head/experiments/run_hubert_third.py
```

The command consumes the already cached weights and refuses to overwrite an
existing report. Its private, owner-only output is
`research/audio-head/outputs/cmu-arctic-hubert-third-v1/report.json`; it retains
all 18 validated run records, per-run losses and edit counts, and the three
head-seed values plus mean/minimum/maximum/sample standard deviation for every
split. The observed **test automatic-alignment token error rates** are:

| Frozen encoder | 200 steps, mean ± seed SD | 800 steps, mean ± seed SD |
| --- | ---: | ---: |
| wav2vec2 Base | 59.54% ± 1.50 points | 51.10% ± 0.66 points |
| WavLM Base+ | 12.75% ± 0.40 points | 10.64% ± 0.66 points |
| HuBERT Base | 15.83% ± 0.46 points | 14.86% ± 0.55 points |

HuBERT's 200/800-step mean calibration rates were 19.13%/17.65%, while its
test CTC losses were 0.6869/0.8438. Its test exact-sequence accuracy was zero
at both budgets for all three head seeds. More optimization lowered mean test
edit rate while raising mean test CTC loss. These quantities describe agreement
with automatic labels on repeatedly inspected adult studio speech. The three
head seeds sample initialization variation, not speaker or population
uncertainty. Upstream pretraining, normalization, and possible corpus overlap
remain confounded. The report explicitly has `selectionPerformed: false`,
`productionEligible: false`, and `learnerFeedbackEligible: false`; there is no
clinical or target-localized result from this experiment.

The 200-step, head-seed-7 HuBERT checkpoint also exported normalized full-phone
posteriors for the fixed calibration recording `cmu-rms-arctic_a0102` (86 frames)
and test recording `cmu-slt-arctic_a0201` (127 frames). The existing
`check_ctc_parity.py` compared those exports with the TypeScript CTC scorer:
all 18 synthetic, rejection, and real-export cases passed, with maximum finite
log-probability difference 4.45×10⁻¹⁶. The owner-only evidence is
`outputs/cmu-arctic-hubert-parity-v1.json`. This checks export shape and score
arithmetic, not audio interpretation or pronunciation accuracy.
