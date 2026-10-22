# Fixed word-context pipeline sensitivity diagnostic

Declared September 26, 2026, before implementing or running this diagnostic.
The native practice app presents isolated words, whereas the research heads
were fitted on target positions in complete utterances. This bounded check asks
how the **whole research pipeline** changes when most surrounding waveform
context and canonical prompt context are removed. It is not an evaluation of
natural isolated-word pronunciation or a claim of deployment readiness.

## Fixed cases and models

Reuse all five clips in the already fixed capture diagnostic plan, SHA-256
`1ccb263465c987cd0185013db09942092e1d60f55f2ab7c977519fec5e3d0781`.
They are five children aged 6, 8, 10, 11 and 12 in fold-zero **inner validation**,
selected using speaker/clip metadata. They are not fitting clips or a new
independent cohort. Their original head-selection history remains disclosed.

Include every target-bearing word: **17 words and all 23 eligible target
positions** across the five clips. No score, posterior margin, duration or
observed prediction selects words. Keep the same original fold-zero all-age
and child-only target-plus-scalar heads, each at learning rate .0003 and its
previously selected epoch five. No training, model selection, coefficient
search or new model export occurs.

## Canonical mapping and fixed crop

Recover each original word's text and canonical phone sequence from the pinned
SpeechOcean author-training metadata. Verify that concatenated word phones
exactly equal the existing full canonical sequence and that every original
word index, phone index, target phone and target-row identity agrees. Preserve
original word/canonical indices alongside any crop-local indices. Canonical
phones describe the expected prompt, not what the child actually produced.

Run the existing Viterbi algorithm on the already saved original full392 CTC
log posteriors, with the unchanged complete canonical sequence. For each word,
use the first and last occupied canonical phone states belonging to that word,
including the internal gaps in their spanning interval. Every canonical state
must have finite, contiguous, nonempty occupancy. These are estimated emission
locations, **not validated phoneme or word-duration boundaries**.

For occupied frame span `[start, end)`, the pinned valid-convolution stack has
stride 320 samples and receptive field 400 samples. Its raw convolution support
is `[start*320, (end-1)*320+400)`. Add exactly **1,600 samples / 100 ms** on each
side, clipped to the source sample range. Copy exactly those original PCM16
samples into one crop. Do not resample, normalize, fade, pad with silence,
change gain or alter source audio. The encoder's own existing preprocessing
remains unchanged. Convolution coverage does not bound the transformer's
contextual receptive field.

Every word receives this one fixed crop attempt. No adaptive widening,
replacement word, alternate padding, confidence cutoff or exclusion based on
ratings is allowed. Record invalid geometry, the 0.1–30-second runtime limit,
an infeasible canonical CTC path or unalignable crop as a failed case with its
original identities and reason. Preserve the full 17-word/23-target denominator.
A file/source integrity violation, network attempt, model/runtime error or
original parity failure aborts the run and preserves its failure artifacts;
these must not be disguised as ordinary crop-alignment failures.

## Recomputed pipeline and verification

Before any cropped-audio model evaluation, rerun all five unmodified originals.
Require exact original q8 posteriors, scalar features and estimated windows;
phonetic pooled vectors and both saved head probabilities must agree within
absolute tolerance 2e-6. Keep the previously declared tolerance; a failure
stops rather than loosening it.

For each valid crop, recompute full392 q8 posteriors, then align only that word's
canonical phones to estimate target occupancy. Recompute all 13 scalar values and the frozen
full-precision 1,024-dimensional phonetic representation. Apply both unchanged
heads with their own original fit-only moments. This jointly changes waveform
context, encoder normalization, canonical sequence, alignment and the two
utterance-level scalar features. It does not isolate a causal encoder-context
effect. Cropping also retains original coarticulation, and 100 ms padding can
retain neighboring speech.

Use local files only and CPU with two threads. Freeze source, recipe, protocol,
model, waveform, metadata, original-cache and head pins before execution. Save
crop sample ranges, exact waveform hashes, canonical offsets, original parity,
feature arrays, per-target probabilities and any failures. Publish completion
only after rechecking the bound artifacts. No author-test audio or new outer
model-performance evaluation is accessed.

## Reporting and limits

Report every word and target's status, crop duration and estimated alignment
movement in original sample coordinates. For successful paired targets report
full-versus-crop total variation, expected-rating drift, class-probability,
entropy/confidence and argmax changes for both heads. Retain per-clip/per-word
results and target-weighted descriptive means with explicit successful and
planned denominators. Do not turn multiple words from the same child into
independent participants or compute an uncertainty interval from five speakers.

Do not transfer original human ratings to crops or calculate crop NLL, Brier,
accuracy, calibration, clinical thresholds or pronunciation correctness.
Smaller movement is not necessarily better; a model may preserve a mistaken
prediction. Larger movement could reflect truncated speech, contextual
conditioning, feature-definition changes or valid acoustic differences.
Human listening/boundary review and purpose-collected isolated-word child/SSD
recordings remain necessary before interpreting these estimated crops as
representative app inputs. This diagnostic supplies no learner-feedback gate.
